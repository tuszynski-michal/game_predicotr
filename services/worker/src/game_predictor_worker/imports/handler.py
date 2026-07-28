"""Resumable raw staging handler for attested layout import files."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

from game_predictor_api.application.layout_imports import (
    InspectedLayoutImportSource,
)
from game_predictor_api.domain.jobs import Job, JobError, JobType

from game_predictor_worker.imports.contracts import (
    ImportFileFormat,
    LayoutImportStagingStore,
)
from game_predictor_worker.imports.errors import ImportContractError
from game_predictor_worker.imports.streaming import (
    DEFAULT_IMPORT_BATCH_SIZE,
    INITIAL_IMPORT_PREFIX_CHAIN,
    calculate_import_prefix_chain,
    read_import_batch,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

_PAYLOAD_FIELDS: Final = frozenset(
    {
        "schema_version",
        "import_kind",
        "source_path",
        "source_checksum",
        "source_size_bytes",
        "file_format",
        "contract_version",
    }
)


class LayoutImportSourceAttestor(Protocol):
    def inspect(
        self,
        source_path: str,
        *,
        contract_version: int,
    ) -> InspectedLayoutImportSource: ...


@dataclass(frozen=True, slots=True)
class _ImportSource:
    relative_path: str
    checksum: str
    size_bytes: int
    file_format: ImportFileFormat
    contract_version: int


@dataclass(frozen=True, slots=True)
class _ResumeState:
    byte_offset: int
    line_number: int
    prefix_chain: str
    processed_count: int
    success_count: int
    failure_count: int
    stream_complete: bool


class LayoutImportStagingHandler:
    def __init__(
        self,
        store: LayoutImportStagingStore,
        source_attestor: LayoutImportSourceAttestor,
        *,
        batch_size: int = DEFAULT_IMPORT_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive.")
        self._store = store
        self._source_attestor = source_attestor
        self._batch_size = batch_size

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        source_spec = _parse_job(job)
        attested = self._inspect_source(source_spec)
        state = _resume_state(job, source_spec)
        if state.stream_complete:
            self._store.delete_rows_after(
                job.id,
                line_number=state.line_number,
            )
            return

        try:
            with attested.absolute_path.open("rb") as source:
                actual_prefix_chain = calculate_import_prefix_chain(
                    source,
                    byte_offset=state.byte_offset,
                )
                if actual_prefix_chain != state.prefix_chain:
                    self._store.delete_rows_after(job.id, line_number=0)
                    state = _initial_resume_state()
                    _checkpoint(context, source_spec, state)
                else:
                    self._store.delete_rows_after(
                        job.id,
                        line_number=state.line_number,
                    )
                while True:
                    batch = read_import_batch(
                        source,
                        file_format=source_spec.file_format,
                        byte_offset=state.byte_offset,
                        line_number=state.line_number,
                        prefix_chain=state.prefix_chain,
                        batch_size=self._batch_size,
                    )
                    success_delta = sum(row.is_success for row in batch.rows)
                    failure_delta = len(batch.rows) - success_delta
                    if batch.rows:
                        self._store.upsert_rows(job.id, batch.rows)
                        state = _ResumeState(
                            byte_offset=batch.byte_offset,
                            line_number=batch.line_number,
                            prefix_chain=batch.prefix_chain,
                            processed_count=state.processed_count + len(batch.rows),
                            success_count=state.success_count + success_delta,
                            failure_count=state.failure_count + failure_delta,
                            stream_complete=False,
                        )
                        _checkpoint(context, source_spec, state)
                    else:
                        state = _ResumeState(
                            byte_offset=batch.byte_offset,
                            line_number=batch.line_number,
                            prefix_chain=batch.prefix_chain,
                            processed_count=state.processed_count,
                            success_count=state.success_count,
                            failure_count=state.failure_count,
                            stream_complete=False,
                        )
                    if batch.reached_eof:
                        break
        except ImportContractError as error:
            self._store.delete_rows_after(job.id, line_number=0)
            _reset_checkpoint(context, source_spec)
            raise JobHandlerError(
                error.code.value,
                str(error),
            ) from error
        except ValueError as error:
            self._store.delete_rows_after(job.id, line_number=0)
            _reset_checkpoint(context, source_spec)
            raise JobHandlerError(
                "INVALID_LAYOUT_IMPORT_CHECKPOINT",
                "The layout import checkpoint is not on a record boundary.",
            ) from error
        except OSError as error:
            self._store.delete_rows_after(job.id, line_number=0)
            _reset_checkpoint(context, source_spec)
            raise JobHandlerError(
                "IMPORT_SOURCE_READ_FAILED",
                "The import source could not be read during staging.",
            ) from error

        try:
            self._inspect_source(source_spec)
        except JobHandlerError:
            self._store.delete_rows_after(job.id, line_number=0)
            _reset_checkpoint(context, source_spec)
            raise

        completed = _ResumeState(
            byte_offset=source_spec.size_bytes,
            line_number=state.line_number,
            prefix_chain=state.prefix_chain,
            processed_count=state.processed_count,
            success_count=state.success_count,
            failure_count=state.failure_count,
            stream_complete=True,
        )
        _checkpoint(context, source_spec, completed)

    def _inspect_source(
        self,
        source_spec: _ImportSource,
    ) -> InspectedLayoutImportSource:
        try:
            inspected = self._source_attestor.inspect(
                source_spec.relative_path,
                contract_version=source_spec.contract_version,
            )
        except JobError as error:
            raise JobHandlerError(error.code, error.message) from error
        if (
            inspected.relative_path != source_spec.relative_path
            or inspected.file_format is not source_spec.file_format
            or inspected.contract_version != source_spec.contract_version
            or inspected.size_bytes != source_spec.size_bytes
            or inspected.checksum != source_spec.checksum
        ):
            raise JobHandlerError(
                "IMPORT_SOURCE_ATTESTATION_MISMATCH",
                "The import source no longer matches the attested job input.",
            )
        return inspected


def _parse_job(job: Job) -> _ImportSource:
    if job.job_type is not JobType.IMPORT:
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_JOB_TYPE",
            "The layout import handler only accepts import jobs.",
        )
    if job.game_id is None:
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_PAYLOAD",
            "A layout import job must belong to one game.",
        )
    payload = job.input_payload
    if payload.get("schema_version") != 1:
        raise JobHandlerError(
            "UNSUPPORTED_LAYOUT_IMPORT_PAYLOAD_VERSION",
            "The layout import job requires input payload schema version 1.",
        )
    if set(payload) != _PAYLOAD_FIELDS or payload.get("import_kind") != "layout_file":
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_PAYLOAD",
            "The layout import job payload is not server-attested.",
        )
    relative_path = payload.get("source_path")
    checksum = payload.get("source_checksum")
    size_bytes = payload.get("source_size_bytes")
    contract_version = payload.get("contract_version")
    file_format_value = payload.get("file_format")
    if not isinstance(file_format_value, str):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_PAYLOAD",
            "The layout import job contains an unsupported file format.",
        )
    try:
        file_format = ImportFileFormat(file_format_value)
    except (TypeError, ValueError) as error:
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_PAYLOAD",
            "The layout import job contains an unsupported file format.",
        ) from error
    if (
        not isinstance(relative_path, str)
        or not relative_path
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or checksum.lower() != checksum
        or any(character not in "0123456789abcdef" for character in checksum)
        or isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or size_bytes < 1
        or isinstance(contract_version, bool)
        or not isinstance(contract_version, int)
        or contract_version != 1
    ):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_PAYLOAD",
            "The layout import job payload is incomplete or invalid.",
        )
    return _ImportSource(
        relative_path=relative_path,
        checksum=checksum,
        size_bytes=size_bytes,
        file_format=file_format,
        contract_version=contract_version,
    )


def _resume_state(job: Job, source: _ImportSource) -> _ResumeState:
    checkpoint = job.checkpoint_payload
    if checkpoint is None:
        return _initial_resume_state()
    expected = {
        "schema_version": 1,
        "workflow": "layout_import",
        "source_path": source.relative_path,
        "source_checksum": source.checksum,
        "source_size_bytes": source.size_bytes,
        "file_format": source.file_format.value,
        "contract_version": source.contract_version,
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise JobHandlerError(
            "LAYOUT_IMPORT_CHECKPOINT_MISMATCH",
            "The layout import checkpoint does not match the job input.",
        )
    byte_offset = _checkpoint_integer(checkpoint, "byte_offset")
    line_number = _checkpoint_integer(checkpoint, "line_number")
    processed = _checkpoint_integer(checkpoint, "processed_count")
    succeeded = _checkpoint_integer(checkpoint, "success_count")
    failed = _checkpoint_integer(checkpoint, "failure_count")
    prefix_chain = checkpoint.get("prefix_chain")
    stream_complete = checkpoint.get("stream_complete")
    if (
        not isinstance(prefix_chain, str)
        or len(prefix_chain) != 64
        or prefix_chain.lower() != prefix_chain
        or any(character not in "0123456789abcdef" for character in prefix_chain)
        or not isinstance(stream_complete, bool)
    ):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_CHECKPOINT",
            "The layout import checkpoint contains invalid cursor values.",
        )
    if (
        byte_offset < 0
        or byte_offset > source.size_bytes
        or line_number < 0
        or processed < 0
        or succeeded < 0
        or failed < 0
        or processed != succeeded + failed
        or line_number < processed
        or ((byte_offset == 0) != (line_number == 0))
        or (stream_complete and processed < 1)
        or (stream_complete and byte_offset != source.size_bytes)
        or job.progress_current != byte_offset
        or job.progress_total != source.size_bytes
        or job.success_count != succeeded
        or job.failure_count != failed
    ):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_CHECKPOINT",
            "The layout import checkpoint is inconsistent with job progress.",
        )
    return _ResumeState(
        byte_offset,
        line_number,
        prefix_chain,
        processed,
        succeeded,
        failed,
        stream_complete,
    )


def _initial_resume_state() -> _ResumeState:
    return _ResumeState(
        byte_offset=0,
        line_number=0,
        prefix_chain=INITIAL_IMPORT_PREFIX_CHAIN,
        processed_count=0,
        success_count=0,
        failure_count=0,
        stream_complete=False,
    )


def _checkpoint_integer(
    checkpoint: dict[str, object],
    key: str,
) -> int:
    value = checkpoint.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_CHECKPOINT",
            "The layout import checkpoint contains invalid cursor values.",
        )
    return value


def _checkpoint(
    context: JobExecutionContext,
    source: _ImportSource,
    state: _ResumeState,
) -> None:
    context.checkpoint(
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "layout_import",
            "source_path": source.relative_path,
            "source_checksum": source.checksum,
            "source_size_bytes": source.size_bytes,
            "file_format": source.file_format.value,
            "contract_version": source.contract_version,
            "byte_offset": state.byte_offset,
            "line_number": state.line_number,
            "prefix_chain": state.prefix_chain,
            "processed_count": state.processed_count,
            "success_count": state.success_count,
            "failure_count": state.failure_count,
            "stream_complete": state.stream_complete,
        },
        stage=("staged_import_rows" if state.stream_complete else "staging_import_rows"),
        current=state.byte_offset,
        total=source.size_bytes,
        success_count=state.success_count,
        failure_count=state.failure_count,
        review_count=0,
    )


def _reset_checkpoint(
    context: JobExecutionContext,
    source: _ImportSource,
) -> None:
    _checkpoint(
        context,
        source,
        _initial_resume_state(),
    )
