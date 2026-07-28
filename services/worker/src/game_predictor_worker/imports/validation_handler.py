"""Resumable bounded normalization of raw layout import staging."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobType

from game_predictor_worker.imports.contracts import LayoutImportNormalizationStore
from game_predictor_worker.imports.normalization import normalize_layout_import_row
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

DEFAULT_NORMALIZATION_BATCH_SIZE: Final = 1000
_PAYLOAD_FIELDS: Final = frozenset(
    {
        "schema_version",
        "validation_kind",
        "import_job_id",
        "rules_version_id",
    }
)


@dataclass(frozen=True, slots=True)
class _ValidationInput:
    import_job_id: UUID
    rules_version_id: UUID


@dataclass(frozen=True, slots=True)
class _ValidationState:
    line_number: int
    processed_count: int
    success_count: int
    failure_count: int
    validation_complete: bool


class LayoutImportValidationHandler:
    def __init__(
        self,
        store: LayoutImportNormalizationStore,
        *,
        batch_size: int = DEFAULT_NORMALIZATION_BATCH_SIZE,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be positive.")
        self._store = store
        self._batch_size = batch_size

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        validation_input = _parse_job(job)
        assert job.game_id is not None
        source = self._store.load_normalization_source(
            validation_job_id=job.id,
            game_id=job.game_id,
            import_job_id=validation_input.import_job_id,
            rules_version_id=validation_input.rules_version_id,
        )
        state = _resume_state(job, validation_input, source.row_count)
        if state.validation_complete:
            return

        while True:
            raw_rows = self._store.fetch_raw_rows(
                source.import_job_id,
                after_line_number=state.line_number,
                limit=self._batch_size,
            )
            if not raw_rows:
                break
            normalized = tuple(normalize_layout_import_row(row, source) for row in raw_rows)
            self._store.upsert_normalized_rows(job.id, source, normalized)
            success_delta = sum(row.is_success for row in normalized)
            state = _ValidationState(
                line_number=raw_rows[-1].line_number,
                processed_count=state.processed_count + len(normalized),
                success_count=state.success_count + success_delta,
                failure_count=(state.failure_count + len(normalized) - success_delta),
                validation_complete=False,
            )
            _checkpoint(
                context,
                validation_input,
                state,
                total=source.row_count,
            )

        if state.processed_count != source.row_count:
            raise JobHandlerError(
                "LAYOUT_IMPORT_STAGING_CHANGED",
                "The raw layout import staging changed during validation.",
            )
        _checkpoint(
            context,
            validation_input,
            _ValidationState(
                line_number=state.line_number,
                processed_count=state.processed_count,
                success_count=state.success_count,
                failure_count=state.failure_count,
                validation_complete=True,
            ),
            total=source.row_count,
        )


def _parse_job(job: Job) -> _ValidationInput:
    if job.job_type is not JobType.VALIDATE or job.game_id is None:
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_VALIDATION_JOB",
            "Layout import validation requires a game-scoped validate job.",
        )
    payload = job.input_payload
    if (
        set(payload) != _PAYLOAD_FIELDS
        or payload.get("schema_version") != 1
        or payload.get("validation_kind") != "layout_import"
    ):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_VALIDATION_PAYLOAD",
            "The layout import validation payload is invalid.",
        )
    try:
        return _ValidationInput(
            import_job_id=UUID(str(payload["import_job_id"])),
            rules_version_id=UUID(str(payload["rules_version_id"])),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_VALIDATION_PAYLOAD",
            "The layout import validation identifiers are invalid.",
        ) from error


def _resume_state(
    job: Job,
    validation_input: _ValidationInput,
    total: int,
) -> _ValidationState:
    checkpoint = job.checkpoint_payload
    if checkpoint is None:
        if any(
            value != 0
            for value in (
                job.progress_current,
                job.success_count,
                job.failure_count,
                job.review_count,
            )
        ):
            raise JobHandlerError(
                "INVALID_LAYOUT_IMPORT_VALIDATION_CHECKPOINT",
                "Validation progress exists without a checkpoint.",
            )
        return _ValidationState(0, 0, 0, 0, False)
    expected = {
        "schema_version": 1,
        "workflow": "layout_import_validation",
        "import_job_id": str(validation_input.import_job_id),
        "rules_version_id": str(validation_input.rules_version_id),
        "row_count": total,
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        raise JobHandlerError(
            "LAYOUT_IMPORT_VALIDATION_CHECKPOINT_MISMATCH",
            "The validation checkpoint does not match the selected staging.",
        )
    line_number = _checkpoint_integer(checkpoint, "line_number")
    processed = _checkpoint_integer(checkpoint, "processed_count")
    succeeded = _checkpoint_integer(checkpoint, "success_count")
    failed = _checkpoint_integer(checkpoint, "failure_count")
    complete = checkpoint.get("validation_complete")
    if (
        not isinstance(complete, bool)
        or line_number < 0
        or processed < 0
        or processed > total
        or processed != succeeded + failed
        or job.progress_current != processed
        or job.progress_total != total
        or job.success_count != succeeded
        or job.failure_count != failed
        or job.review_count != 0
        or (complete and processed != total)
    ):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_VALIDATION_CHECKPOINT",
            "The validation checkpoint is inconsistent with job progress.",
        )
    return _ValidationState(line_number, processed, succeeded, failed, complete)


def _checkpoint_integer(checkpoint: dict[str, object], key: str) -> int:
    value = checkpoint.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise JobHandlerError(
            "INVALID_LAYOUT_IMPORT_VALIDATION_CHECKPOINT",
            "The validation checkpoint contains an invalid cursor.",
        )
    return value


def _checkpoint(
    context: JobExecutionContext,
    validation_input: _ValidationInput,
    state: _ValidationState,
    *,
    total: int,
) -> None:
    context.checkpoint(
        checkpoint_payload={
            "schema_version": 1,
            "workflow": "layout_import_validation",
            "import_job_id": str(validation_input.import_job_id),
            "rules_version_id": str(validation_input.rules_version_id),
            "row_count": total,
            "line_number": state.line_number,
            "processed_count": state.processed_count,
            "success_count": state.success_count,
            "failure_count": state.failure_count,
            "validation_complete": state.validation_complete,
        },
        stage=("validated_import_rows" if state.validation_complete else "validating_import_rows"),
        current=state.processed_count,
        total=total,
        success_count=state.success_count,
        failure_count=state.failure_count,
        review_count=0,
    )
