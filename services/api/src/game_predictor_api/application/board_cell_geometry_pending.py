"""Application contract for deferred board-cell geometry work."""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from game_predictor_api.domain.board_cell_geometry_pending import (
    BoardCellGeometryJobCounts,
    BoardCellGeometryPendingReason,
    BoardCellGeometryPendingStatus,
    BoardCellProcessingManifestV1,
    ImageBoardGeometryPending,
    board_cell_processing_artifact_relative_path,
)
from game_predictor_api.domain.jobs import JobConflictError, JobError, JobNotFoundError

BoardCellPendingOrderKey = tuple[int, int, UUID]


@dataclass(frozen=True, slots=True)
class BoardCellGeometryPendingPage:
    items: tuple[ImageBoardGeometryPending, ...]
    counts: BoardCellGeometryJobCounts
    next_cursor: str | None


class BoardCellGeometryPendingRepository(Protocol):
    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
        manifest_relative_path: str,
    ) -> tuple[ImageBoardGeometryPending, bool]: ...

    def get(self, pending_id: UUID) -> ImageBoardGeometryPending | None: ...

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        after_key: BoardCellPendingOrderKey | None,
        limit: int,
    ) -> Sequence[ImageBoardGeometryPending]: ...

    def counts(self, *, game_id: UUID, import_job_id: UUID) -> BoardCellGeometryJobCounts: ...

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending | None: ...


class BoardCellProcessingManifestStore(Protocol):
    def put(self, manifest: BoardCellProcessingManifestV1) -> str: ...


class ManagedBoardCellProcessingManifestStore:
    """Content-addressed storage; no source image bytes are copied."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()

    def put(self, manifest: BoardCellProcessingManifestV1) -> str:
        relative_path = board_cell_processing_artifact_relative_path(manifest.checksum_sha256)
        target = (self._artifact_root / relative_path).resolve()
        if not target.is_relative_to(self._artifact_root):
            raise JobError(
                "IMAGE_BOARD_CELL_MANIFEST_PATH_INVALID",
                "The board-cell processing manifest path is unsafe.",
            )
        payload = manifest.canonical_bytes()
        if target.exists():
            if target.read_bytes() != payload:
                raise JobConflictError(
                    "IMAGE_BOARD_CELL_MANIFEST_CONFLICT",
                    "A different artifact already exists for the processing manifest checksum.",
                )
            return relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return relative_path


class BoardCellGeometryPendingService:
    def __init__(
        self,
        repository: BoardCellGeometryPendingRepository,
        manifest_store: BoardCellProcessingManifestStore,
    ) -> None:
        self._repository = repository
        self._manifest_store = manifest_store

    def defer(
        self,
        *,
        manifest: BoardCellProcessingManifestV1,
        reason_code: BoardCellGeometryPendingReason,
    ) -> tuple[ImageBoardGeometryPending, bool]:
        relative_path = self._manifest_store.put(manifest)
        return self._repository.defer(
            manifest=manifest,
            reason_code=reason_code,
            manifest_relative_path=relative_path,
        )

    def get(
        self,
        pending_id: UUID,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> ImageBoardGeometryPending:
        value = self._repository.get(pending_id)
        if value is None or value.game_id != game_id or value.import_job_id != import_job_id:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist in this import.",
            )
        return value

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        status: BoardCellGeometryPendingStatus | None,
        cursor: str | None,
        limit: int,
    ) -> BoardCellGeometryPendingPage:
        after_key = None if cursor is None else decode_board_cell_pending_cursor(cursor)
        values = tuple(
            self._repository.list(
                game_id=game_id,
                import_job_id=import_job_id,
                status=status,
                after_key=after_key,
                limit=limit + 1,
            )
        )
        has_more = len(values) > limit
        items = values[:limit]
        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_board_cell_pending_cursor(
                (last.sequence_number, last.position_index, last.id)
            )
        return BoardCellGeometryPendingPage(
            items=items,
            counts=self._repository.counts(game_id=game_id, import_job_id=import_job_id),
            next_cursor=next_cursor,
        )

    def resolve(
        self,
        *,
        pending_id: UUID,
        expected_manifest_checksum_sha256: str,
        resolved_geometry_revision: int,
    ) -> ImageBoardGeometryPending:
        value = self._repository.resolve(
            pending_id=pending_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            resolved_geometry_revision=resolved_geometry_revision,
        )
        if value is None:
            raise JobNotFoundError(
                "IMAGE_BOARD_CELL_PENDING_NOT_FOUND",
                "The deferred board-cell geometry item does not exist.",
            )
        return value


def encode_board_cell_pending_cursor(key: BoardCellPendingOrderKey) -> str:
    payload = json.dumps([key[0], key[1], str(key[2])], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_board_cell_pending_cursor(value: str) -> BoardCellPendingOrderKey:
    try:
        payload = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        sequence, position, pending_id = json.loads(payload)
        if not isinstance(sequence, int) or sequence < 1:
            raise ValueError
        if not isinstance(position, int) or not 0 <= position <= 8:
            raise ValueError
        return sequence, position, UUID(pending_id)
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise JobError(
            "IMAGE_BOARD_CELL_PENDING_CURSOR_INVALID",
            "The deferred board-cell geometry cursor is invalid.",
        ) from error


__all__ = [
    "BoardCellGeometryPendingPage",
    "BoardCellGeometryPendingRepository",
    "BoardCellGeometryPendingService",
    "BoardCellProcessingManifestStore",
    "ManagedBoardCellProcessingManifestStore",
    "decode_board_cell_pending_cursor",
    "encode_board_cell_pending_cursor",
]
