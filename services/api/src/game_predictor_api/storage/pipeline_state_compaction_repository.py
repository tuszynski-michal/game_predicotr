"""Bounded preview generation for reproducible image-pipeline state compaction."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.pipeline_state_compaction import (
    DISPOSABLE_STAGE_PAYLOADS,
    PIPELINE_COMPACTION_SCHEMA,
    PipelineStageDigest,
    canonical_json_bytes,
    manifest_checksum,
    stage_digest,
    terminal_manifest_payload,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)

PREVIEW_PAGE_SIZE = 200


@dataclass(frozen=True, slots=True)
class PipelineCompactionPreview:
    preview_id: UUID
    manifest_relative_path: str
    manifest_checksum_sha256: str
    preview_token: str
    candidate_count: int
    stage_result_count: int
    candidate_bytes: int
    cutoff_at: datetime


class SqlAlchemyPipelineStateCompactionRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self._session = session
        self._artifact_root = artifact_root.resolve()

    def create_preview(self, *, cutoff_at: datetime) -> PipelineCompactionPreview:
        preview_id = uuid4()
        relative = (
            Path("data")
            / "exports"
            / "storage-gc"
            / "pipeline-state"
            / str(preview_id)
            / "manifest.jsonl"
        )
        destination = self._artifact_root / relative
        destination.parent.mkdir(parents=True, exist_ok=False)
        candidate_count = stage_count = candidate_bytes = 0
        with tempfile.NamedTemporaryFile(
            mode="wb", delete=False, dir=destination.parent, prefix="entries-", suffix=".tmp"
        ) as entries_file:
            entries_path = Path(entries_file.name)
            after_key: str | None = None
            while True:
                executions = self._candidate_page(cutoff_at=cutoff_at, after_key=after_key)
                if not executions:
                    break
                keys = tuple(item.file_execution_key for item in executions)
                stages_by_key = self._stages(keys)
                source_ids, board_ids = self._final_ids(keys)
                for execution in executions:
                    stages = stages_by_key.get(execution.file_execution_key, ())
                    if not any(item.stage in DISPOSABLE_STAGE_PAYLOADS for item in stages):
                        continue
                    payload = terminal_manifest_payload(
                        file_execution_key=execution.file_execution_key,
                        source_checksum_sha256=execution.source_checksum_sha256,
                        pipeline_fingerprint=execution.pipeline_fingerprint,
                        execution_status=execution.status,
                        execution_updated_at=execution.updated_at,
                        stages=stages,
                        source_image_ids=source_ids.get(execution.file_execution_key, ()),
                        recognized_board_ids=board_ids.get(execution.file_execution_key, ()),
                    )
                    disposable = tuple(
                        item for item in stages if item.stage in DISPOSABLE_STAGE_PAYLOADS
                    )
                    entry = {
                        "fileExecutionKey": execution.file_execution_key,
                        "executionUpdatedAt": execution.updated_at.isoformat(),
                        "terminalManifestChecksumSha256": manifest_checksum(payload),
                        "terminalManifest": payload,
                        "disposableStageCount": len(disposable),
                        "disposableBytes": sum(item.payload_bytes for item in disposable),
                    }
                    entries_file.write(canonical_json_bytes(entry))
                    candidate_count += 1
                    stage_count += len(disposable)
                    candidate_bytes += int(entry["disposableBytes"])
                after_key = executions[-1].file_execution_key
        header = {
            "schemaVersion": PIPELINE_COMPACTION_SCHEMA,
            "previewId": str(preview_id),
            "cutoffAt": cutoff_at.isoformat(),
            "candidateCount": candidate_count,
            "stageResultCount": stage_count,
            "candidateBytes": candidate_bytes,
        }
        with destination.open("xb") as target, entries_path.open("rb") as entries:
            target.write(canonical_json_bytes(header))
            shutil.copyfileobj(entries, target, length=1024 * 1024)
            target.flush()
            os.fsync(target.fileno())
        entries_path.unlink(missing_ok=True)
        checksum = _file_sha256(destination)
        token = hashlib.sha256(
            f"{checksum}:pipeline-compaction-confirmation-v1".encode("ascii")
        ).hexdigest()
        return PipelineCompactionPreview(
            preview_id=preview_id,
            manifest_relative_path=relative.as_posix(),
            manifest_checksum_sha256=checksum,
            preview_token=token,
            candidate_count=candidate_count,
            stage_result_count=stage_count,
            candidate_bytes=candidate_bytes,
            cutoff_at=cutoff_at,
        )

    def _candidate_page(
        self, *, cutoff_at: datetime, after_key: str | None
    ) -> tuple[ImageFileExecutionModel, ...]:
        active_job = exists(
            select(ImageImportJobFileModel.file_execution_key)
            .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
            .where(
                ImageImportJobFileModel.file_execution_key
                == ImageFileExecutionModel.file_execution_key,
                JobModel.status.in_(("created", "processing")),
            )
        )
        failed_link = exists(
            select(ImageImportJobFileModel.file_execution_key).where(
                ImageImportJobFileModel.file_execution_key
                == ImageFileExecutionModel.file_execution_key,
                ImageImportJobFileModel.workflow_status == "failed",
            )
        )
        unresolved_geometry = exists(
            select(ImageBoardGeometryPendingModel.id)
            .join(
                SourceImageModel,
                SourceImageModel.id == ImageBoardGeometryPendingModel.source_image_id,
            )
            .where(
                SourceImageModel.file_execution_key
                == ImageFileExecutionModel.file_execution_key,
                ImageBoardGeometryPendingModel.status != "resolved",
            )
        )
        has_disposable = exists(
            select(ImagePipelineStageResultModel.file_execution_key).where(
                ImagePipelineStageResultModel.file_execution_key
                == ImageFileExecutionModel.file_execution_key,
                ImagePipelineStageResultModel.stage.in_(DISPOSABLE_STAGE_PAYLOADS),
            )
        )
        statement = (
            select(ImageFileExecutionModel)
            .where(
                ImageFileExecutionModel.updated_at <= cutoff_at,
                ImageFileExecutionModel.status.in_(("waiting_for_review", "completed")),
                ~active_job,
                ~failed_link,
                ~unresolved_geometry,
                has_disposable,
            )
            .order_by(ImageFileExecutionModel.file_execution_key)
            .limit(PREVIEW_PAGE_SIZE)
        )
        if after_key is not None:
            statement = statement.where(ImageFileExecutionModel.file_execution_key > after_key)
        return tuple(self._session.scalars(statement).all())

    def _stages(self, keys: tuple[str, ...]) -> dict[str, tuple[PipelineStageDigest, ...]]:
        grouped: dict[str, list[PipelineStageDigest]] = {key: [] for key in keys}
        rows = self._session.scalars(
            select(ImagePipelineStageResultModel)
            .where(ImagePipelineStageResultModel.file_execution_key.in_(keys))
            .order_by(
                ImagePipelineStageResultModel.file_execution_key,
                ImagePipelineStageResultModel.stage,
            )
        ).all()
        for row in rows:
            grouped[row.file_execution_key].append(
                stage_digest(
                    stage=row.stage,
                    adapter_version=row.adapter_version,
                    payload=row.result_payload,
                )
            )
        return {key: tuple(value) for key, value in grouped.items()}

    def _final_ids(
        self, keys: tuple[str, ...]
    ) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[str, ...]]]:
        sources: dict[str, list[str]] = {key: [] for key in keys}
        boards: dict[str, list[str]] = {key: [] for key in keys}
        rows = self._session.execute(
            select(SourceImageModel.file_execution_key, SourceImageModel.id).where(
                SourceImageModel.file_execution_key.in_(keys)
            )
        ).all()
        source_to_key = {source_id: key for key, source_id in rows}
        for key, source_id in rows:
            sources[key].append(str(source_id))
        if source_to_key:
            for source_id, board_id in self._session.execute(
                select(RecognizedBoardModel.source_image_id, RecognizedBoardModel.id).where(
                    RecognizedBoardModel.source_image_id.in_(tuple(source_to_key))
                )
            ).all():
                boards[source_to_key[source_id]].append(str(board_id))
        return (
            {key: tuple(value) for key, value in sources.items()},
            {key: tuple(value) for key, value in boards.items()},
        )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["PipelineCompactionPreview", "SqlAlchemyPipelineStateCompactionRepository"]
