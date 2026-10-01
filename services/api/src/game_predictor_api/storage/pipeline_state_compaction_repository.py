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

from sqlalchemy import Text, cast, exists, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.pipeline_state_compaction import (
    DISPOSABLE_STAGE_PAYLOADS,
    PIPELINE_COMPACTION_SCHEMA,
    GameExecutionReferences,
    PipelineExecutionReferences,
    PipelineStageDigest,
    canonical_json_bytes,
    manifest_checksum,
    merge_game_execution_references,
    terminal_manifest_payload,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageStatus,
    game_storage_scope,
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

# The preview retains only compact digests. A larger keyset window avoids
# hundreds of repeated PostgreSQL round-trips while keeping memory bounded.
PREVIEW_PAGE_SIZE = 2_000
ACTIVE_IMPORT_JOB_STATUSES = ("created", "processing")


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


@dataclass(frozen=True, slots=True)
class _CandidateExecution:
    file_execution_key: str
    source_checksum_sha256: str
    pipeline_fingerprint: str
    status: str
    updated_at: datetime


class SqlAlchemyPipelineStateCompactionRepository:
    """Build the immutable preview from global executions and per-game guards.

    Candidates come from the shared ``public`` execution tables. Import links,
    source images and board geometry are game-owned V2 partitions (D-374), so
    their guards run per game store in a separately bound transaction.
    """

    def __init__(self, session_factory: sessionmaker[Session], artifact_root: Path) -> None:
        self._session_factory = session_factory
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
                with self._session_factory() as session, session.begin():
                    executions = _candidate_page(session, cutoff_at=cutoff_at, after_key=after_key)
                if not executions:
                    break
                references = load_pipeline_execution_references(
                    self._session_factory,
                    tuple(item.file_execution_key for item in executions),
                )
                selected = tuple(
                    item
                    for item in executions
                    if item.file_execution_key in references.compactable_keys
                )
                stages_by_key: dict[str, tuple[PipelineStageDigest, ...]] = {}
                if selected:
                    with self._session_factory() as session, session.begin():
                        stages_by_key = load_pipeline_stage_digests(
                            session, tuple(item.file_execution_key for item in selected)
                        )
                for execution in selected:
                    key = execution.file_execution_key
                    stages = stages_by_key.get(key, ())
                    if not any(item.stage in DISPOSABLE_STAGE_PAYLOADS for item in stages):
                        continue
                    payload = terminal_manifest_payload(
                        file_execution_key=key,
                        source_checksum_sha256=execution.source_checksum_sha256,
                        pipeline_fingerprint=execution.pipeline_fingerprint,
                        execution_status=execution.status,
                        execution_updated_at=execution.updated_at,
                        stages=stages,
                        source_image_ids=references.source_image_ids.get(key, ()),
                        recognized_board_ids=references.recognized_board_ids.get(key, ()),
                    )
                    disposable = tuple(
                        item for item in stages if item.stage in DISPOSABLE_STAGE_PAYLOADS
                    )
                    disposable_bytes = sum(item.payload_bytes for item in disposable)
                    entry = {
                        "fileExecutionKey": key,
                        "executionUpdatedAt": execution.updated_at.isoformat(),
                        "terminalManifestChecksumSha256": manifest_checksum(payload),
                        "terminalManifest": payload,
                        "disposableStageCount": len(disposable),
                        "disposableBytes": disposable_bytes,
                    }
                    entries_file.write(canonical_json_bytes(entry))
                    candidate_count += 1
                    stage_count += len(disposable)
                    candidate_bytes += disposable_bytes
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
            f"{checksum}:pipeline-compaction-confirmation-v2".encode("ascii")
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
    session: Session, *, cutoff_at: datetime, after_key: str | None
) -> tuple[_CandidateExecution, ...]:
    """Page global executions only; game-owned guards run per game store."""

    has_disposable = exists(
        select(ImagePipelineStageResultModel.file_execution_key).where(
            ImagePipelineStageResultModel.file_execution_key
            == ImageFileExecutionModel.file_execution_key,
            ImagePipelineStageResultModel.stage.in_(DISPOSABLE_STAGE_PAYLOADS),
        )
    )
    statement = (
        select(
            ImageFileExecutionModel.file_execution_key,
            ImageFileExecutionModel.source_checksum_sha256,
            ImageFileExecutionModel.pipeline_fingerprint,
            ImageFileExecutionModel.status,
            ImageFileExecutionModel.updated_at,
        )
        .where(
            ImageFileExecutionModel.updated_at <= cutoff_at,
            ImageFileExecutionModel.status.in_(("waiting_for_review", "completed")),
            has_disposable,
        )
        .order_by(ImageFileExecutionModel.file_execution_key)
        .limit(PREVIEW_PAGE_SIZE)
    )
    if after_key is not None:
        statement = statement.where(ImageFileExecutionModel.file_execution_key > after_key)
    return tuple(
        _CandidateExecution(
            file_execution_key=str(key),
            source_checksum_sha256=str(source_checksum),
            pipeline_fingerprint=str(fingerprint),
            status=str(status),
            updated_at=updated_at,
        )
        for key, source_checksum, fingerprint, status, updated_at in session.execute(
            statement
        ).all()
    )


def load_pipeline_execution_references(
    session_factory: sessionmaker[Session],
    keys: tuple[str, ...],
) -> PipelineExecutionReferences:
    """Evaluate game-owned guards for global executions, one game store at a time.

    One transaction may bind only one game store
    (``GameStorageRouter._require_same_binding``), so every registered game
    gets a fresh session with a READ binding. Games that are not ``active``
    are read too and protect every key they own; results are merged
    fail-closed by :func:`merge_game_execution_references`.
    """

    if not keys:
        return merge_game_execution_references(())
    with session_factory() as session, session.begin():
        registry = session.execute(
            text("SELECT game_id, status FROM public.game_storage_locations ORDER BY game_id")
        ).all()
    games: list[GameExecutionReferences] = []
    for raw_game_id, raw_status in registry:
        game_id = raw_game_id if isinstance(raw_game_id, UUID) else UUID(str(raw_game_id))
        with (
            game_storage_scope(game_id),
            session_factory() as session,
            session.begin(),
        ):
            GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
            games.append(
                _game_execution_references(
                    session,
                    game_id,
                    keys,
                    storage_active=str(raw_status) == GameStorageStatus.ACTIVE.value,
                )
            )
    return merge_game_execution_references(games)


def _game_execution_references(
    session: Session, game_id: UUID, keys: tuple[str, ...], *, storage_active: bool
) -> GameExecutionReferences:
    """Read one bound game store; every query is limited to ``keys``.

    RLS on ``game_data_v2`` does not apply to a superuser or BYPASSRLS role
    (the local Docker role is one), so each query is also scoped explicitly to
    ``game_id`` through the owning import job or the row's own ``game_id``.
    """

    game_link = (
        select(ImageImportJobFileModel.file_execution_key)
        .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
        .where(
            JobModel.game_id == game_id,
            ImageImportJobFileModel.file_execution_key.in_(keys),
        )
        .distinct()
    )
    game_source = (
        select(SourceImageModel.file_execution_key, SourceImageModel.id)
        .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
        .where(
            JobModel.game_id == game_id,
            SourceImageModel.file_execution_key.in_(keys),
        )
    )
    linked = session.scalars(game_link).all()
    source_rows = session.execute(game_source).all()
    active_job = session.scalars(
        game_link.where(JobModel.status.in_(ACTIVE_IMPORT_JOB_STATUSES))
    ).all()
    # A failed link, or a link that never reached a terminal workflow state (its job may
    # be retried and would recompute the stages), protects the execution.
    unsettled_link = session.scalars(
        game_link.where(
            ImageImportJobFileModel.workflow_status.not_in(("waiting_for_review", "completed"))
        )
    ).all()
    unresolved_geometry = session.scalars(
        select(SourceImageModel.file_execution_key)
        .join(
            ImageBoardGeometryPendingModel,
            ImageBoardGeometryPendingModel.source_image_id == SourceImageModel.id,
        )
        .where(
            ImageBoardGeometryPendingModel.game_id == game_id,
            SourceImageModel.file_execution_key.in_(keys),
            ImageBoardGeometryPendingModel.status != "resolved",
        )
        .distinct()
    ).all()
    sources: dict[str, list[str]] = {}
    source_to_key: dict[UUID, str] = {}
    for key, source_id in source_rows:
        sources.setdefault(key, []).append(str(source_id))
        source_to_key[source_id] = key
    boards: dict[str, list[str]] = {}
    if source_to_key:
        for source_id, board_id in session.execute(
            select(RecognizedBoardModel.source_image_id, RecognizedBoardModel.id).where(
                RecognizedBoardModel.source_image_id.in_(tuple(source_to_key))
            )
        ).all():
            boards.setdefault(source_to_key[source_id], []).append(str(board_id))
    return GameExecutionReferences(
        storage_active=storage_active,
        owned_keys=frozenset((*linked, *sources)),
        blocked_keys=frozenset((*active_job, *unsettled_link, *unresolved_geometry)),
        source_image_ids={key: tuple(value) for key, value in sources.items()},
        recognized_board_ids={key: tuple(value) for key, value in boards.items()},
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_pipeline_stage_digests(
    session: Session,
    keys: tuple[str, ...],
) -> dict[str, tuple[PipelineStageDigest, ...]]:
    """Hash JSONB in PostgreSQL so previews do not transfer large payloads."""

    grouped: dict[str, list[PipelineStageDigest]] = {key: [] for key in keys}
    payload_text = cast(ImagePipelineStageResultModel.result_payload, Text)
    payload_bytes = func.convert_to(payload_text, "UTF8")
    rows = session.execute(
        select(
            ImagePipelineStageResultModel.file_execution_key,
            ImagePipelineStageResultModel.stage,
            ImagePipelineStageResultModel.adapter_version,
            func.encode(func.digest(payload_bytes, "sha256"), "hex"),
            func.octet_length(payload_bytes),
        )
        .where(ImagePipelineStageResultModel.file_execution_key.in_(keys))
        .order_by(
            ImagePipelineStageResultModel.file_execution_key,
            ImagePipelineStageResultModel.stage,
        )
    ).all()
    for key, stage, adapter_version, checksum, size in rows:
        grouped[key].append(
            PipelineStageDigest(
                stage=str(stage),
                adapter_version=str(adapter_version),
                payload_checksum_sha256=str(checksum),
                payload_bytes=int(size),
            )
        )
    return {key: tuple(value) for key, value in grouped.items()}


__all__ = [
    "ACTIVE_IMPORT_JOB_STATUSES",
    "PipelineCompactionPreview",
    "SqlAlchemyPipelineStateCompactionRepository",
    "load_pipeline_execution_references",
    "load_pipeline_stage_digests",
]
