"""Checkpointed compaction of reproducible image-pipeline stage payloads."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path, PurePosixPath

from game_predictor_api.domain.jobs import Job
from game_predictor_api.domain.pipeline_state_compaction import (
    DISPOSABLE_STAGE_PAYLOADS,
    PIPELINE_COMPACTION_SCHEMA,
    manifest_checksum,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImagePipelineTerminalManifestModel,
    JobModel,
    SourceImageModel,
)
from game_predictor_api.storage.pipeline_state_compaction_repository import (
    load_pipeline_stage_digests,
)
from sqlalchemy import delete, exists, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

BATCH_SIZE = 200


class PipelineStateCompactionHandler:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifact_root: Path,
        engine: Engine,
    ) -> None:
        self._session_factory = session_factory
        self._artifact_root = artifact_root.resolve()
        self._engine = engine

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        manifest_path = self._manifest_path(job)
        expected_checksum = str(job.input_payload.get("manifest_checksum_sha256", ""))
        if _file_sha256(manifest_path) != expected_checksum:
            raise JobHandlerError(
                "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED",
                "The immutable pipeline compaction preview changed.",
            )
        mode = str(job.input_payload.get("mode", ""))
        if mode not in {"observe_only", "execute"}:
            raise JobHandlerError(
                "STORAGE_PIPELINE_COMPACTION_PAYLOAD_INVALID",
                "The pipeline compaction mode is invalid.",
            )
        checkpoint = job.checkpoint_payload or {}
        start_index = _non_negative_integer(checkpoint.get("checkpoint_index", 0))
        compacted = _non_negative_integer(checkpoint.get("compacted_count", 0))
        compacted_bytes = _non_negative_integer(checkpoint.get("compacted_bytes", 0))
        conflicts = _non_negative_integer(checkpoint.get("conflict_count", 0))
        header, entries = _manifest_entries(manifest_path)
        total = _non_negative_integer(header.get("candidateCount"))
        batch: list[Mapping[str, object]] = []
        for index, entry in enumerate(entries):
            if index < start_index:
                continue
            batch.append(entry)
            if len(batch) < BATCH_SIZE:
                continue
            applied, freed, blocked = self._process_batch(batch, mode=mode, now=context.now())
            compacted += applied
            compacted_bytes += freed
            conflicts += blocked
            start_index = index + 1
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "checkpoint_index": start_index,
                    "compacted_count": compacted,
                    "compacted_bytes": compacted_bytes,
                    "conflict_count": conflicts,
                    "mode": mode,
                },
                stage="pipeline_state_compaction",
                current=start_index,
                total=total,
                success_count=compacted,
                failure_count=0,
                review_count=conflicts,
            )
            batch = []
        if batch:
            applied, freed, blocked = self._process_batch(batch, mode=mode, now=context.now())
            compacted += applied
            compacted_bytes += freed
            conflicts += blocked
            start_index += len(batch)
            context.checkpoint(
                checkpoint_payload={
                    "schema_version": 1,
                    "checkpoint_index": start_index,
                    "compacted_count": compacted,
                    "compacted_bytes": compacted_bytes,
                    "conflict_count": conflicts,
                    "mode": mode,
                },
                stage="pipeline_state_compaction",
                current=start_index,
                total=total,
                success_count=compacted,
                failure_count=0,
                review_count=conflicts,
            )
        if start_index != total:
            raise JobHandlerError(
                "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED",
                "The pipeline compaction manifest entry count changed.",
            )
        if mode == "execute" and compacted > 0:
            with self._engine.connect().execution_options(
                isolation_level="AUTOCOMMIT"
            ) as connection:
                connection.execute(text("VACUUM (ANALYZE) image_pipeline_stage_results"))

    def _process_batch(
        self,
        entries: list[Mapping[str, object]],
        *,
        mode: str,
        now: datetime,
    ) -> tuple[int, int, int]:
        applied = freed = blocked = 0
        with self._session_factory.begin() as session:
            for entry in entries:
                outcome, size = _compact_entry(session, entry, mode=mode, now=now)
                if outcome:
                    applied += 1
                    freed += size
                else:
                    blocked += 1
        return applied, freed, blocked

    def _manifest_path(self, job: Job) -> Path:
        raw = str(job.input_payload.get("manifest_relative_path", ""))
        relative = PurePosixPath(raw)
        if (
            relative.is_absolute()
            or relative.parts[:4] != ("data", "exports", "storage-gc", "pipeline-state")
            or relative.name != "manifest.jsonl"
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise JobHandlerError(
                "STORAGE_PIPELINE_COMPACTION_PATH_UNSAFE",
                "The pipeline compaction manifest path is unsafe.",
            )
        path = self._artifact_root.joinpath(*relative.parts)
        if not path.resolve().is_relative_to(self._artifact_root):
            raise JobHandlerError(
                "STORAGE_PIPELINE_COMPACTION_PATH_UNSAFE",
                "The pipeline compaction manifest escapes managed storage.",
            )
        return path


def _compact_entry(
    session: Session,
    entry: Mapping[str, object],
    *,
    mode: str,
    now: datetime,
) -> tuple[bool, int]:
    key = str(entry.get("fileExecutionKey", ""))
    execution = session.get(ImageFileExecutionModel, key, with_for_update=True)
    if execution is None or execution.status == "failed":
        return False, 0
    if execution.updated_at.isoformat() != entry.get("executionUpdatedAt"):
        return False, 0
    active_job = session.scalar(
        select(
            exists(
                select(ImageImportJobFileModel.file_execution_key)
                .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
                .where(
                    ImageImportJobFileModel.file_execution_key == key,
                    JobModel.status.in_(("created", "processing")),
                )
            )
        )
    )
    unresolved = session.scalar(
        select(
            exists(
                select(ImageBoardGeometryPendingModel.id)
                .join(
                    SourceImageModel,
                    SourceImageModel.id == ImageBoardGeometryPendingModel.source_image_id,
                )
                .where(
                    SourceImageModel.file_execution_key == key,
                    ImageBoardGeometryPendingModel.status != "resolved",
                )
            )
        )
    )
    if active_job or unresolved:
        return False, 0
    current = {
        item.stage: item for item in load_pipeline_stage_digests(session, (key,)).get(key, ())
    }
    terminal_payload = entry.get("terminalManifest")
    if not isinstance(terminal_payload, Mapping):
        return False, 0
    expected_stages = terminal_payload.get("stages")
    if not isinstance(expected_stages, list):
        return False, 0
    for expected in expected_stages:
        if not isinstance(expected, Mapping):
            return False, 0
        stage = str(expected.get("stage", ""))
        observed = current.get(stage)
        if observed is None:
            if stage in DISPOSABLE_STAGE_PAYLOADS:
                continue
            return False, 0
        if observed.adapter_version != expected.get(
            "adapterVersion"
        ) or observed.payload_checksum_sha256 != expected.get("payloadChecksumSha256"):
            return False, 0
    checksum = manifest_checksum(terminal_payload)
    if checksum != entry.get("terminalManifestChecksumSha256"):
        return False, 0
    disposable_bytes = sum(
        item.payload_bytes for item in current.values() if item.stage in DISPOSABLE_STAGE_PAYLOADS
    )
    record = session.scalar(
        select(ImagePipelineTerminalManifestModel)
        .where(
            ImagePipelineTerminalManifestModel.file_execution_key == key,
            ImagePipelineTerminalManifestModel.manifest_checksum_sha256 == checksum,
        )
        .with_for_update()
    )
    if record is None:
        if mode != "execute":
            return True, 0
        record = ImagePipelineTerminalManifestModel(
            file_execution_key=key,
            schema_version=2,
            manifest_checksum_sha256=checksum,
            manifest_payload=dict(terminal_payload),
            stage_result_count=len(current),
            stage_result_bytes=sum(item.payload_bytes for item in current.values()),
            compacted_at=now,
            last_verified_at=now,
        )
        session.add(record)
    else:
        record.last_verified_at = now
    if mode == "execute":
        session.execute(
            delete(ImagePipelineStageResultModel).where(
                ImagePipelineStageResultModel.file_execution_key == key,
                ImagePipelineStageResultModel.stage.in_(DISPOSABLE_STAGE_PAYLOADS),
            )
        )
    return True, disposable_bytes if mode == "execute" else 0


def _manifest_entries(
    path: Path,
) -> tuple[Mapping[str, object], Iterator[Mapping[str, object]]]:
    source = path.open("rb")
    try:
        first = source.readline()
        header_value = json.loads(first)
        if (
            not isinstance(header_value, Mapping)
            or header_value.get("schemaVersion") != PIPELINE_COMPACTION_SCHEMA
        ):
            raise ValueError

        def entries() -> Iterator[Mapping[str, object]]:
            try:
                for raw in source:
                    value = json.loads(raw)
                    if not isinstance(value, Mapping):
                        raise ValueError
                    yield value
            finally:
                source.close()

        return header_value, entries()
    except (AttributeError, json.JSONDecodeError, ValueError) as error:
        source.close()
        raise JobHandlerError(
            "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED",
            "The pipeline compaction manifest is invalid.",
        ) from error


def _non_negative_integer(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise JobHandlerError(
            "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED",
            "The pipeline compaction manifest counters are invalid.",
        )
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise JobHandlerError(
            "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED",
            "The pipeline compaction manifest is unavailable.",
        ) from error
    return digest.hexdigest()


__all__ = ["PipelineStateCompactionHandler"]
