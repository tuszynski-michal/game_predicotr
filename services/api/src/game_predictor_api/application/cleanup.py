"""Application service for preview-bound cleanup of local working data."""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.cleanup import (
    CleanupCommand,
    CleanupConflictError,
    CleanupPreview,
    CleanupResult,
    CleanupSnapshot,
    cleanup_preview,
)


class CleanupRepository(Protocol):
    def release_snapshot(
        self,
        mobile_release_id: UUID,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot: ...

    def game_snapshot(
        self,
        game_id: UUID,
        *,
        for_update: bool = False,
    ) -> CleanupSnapshot: ...

    def completed_result(
        self,
        kind: str,
        target_id: UUID,
        preview_token: str,
    ) -> CleanupResult | None: ...

    def delete_release(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None: ...

    def reset_game(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None: ...


class CleanupArtifactStore(Protocol):
    def delete(self, relative_paths: tuple[str, ...]) -> None: ...


class ManagedCleanupArtifactStore:
    """Delete only explicit, non-symlink targets below the configured artifact root."""

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve()

    def delete(self, relative_paths: tuple[str, ...]) -> None:
        for relative_path in sorted(set(relative_paths)):
            candidate = self._safe_target(relative_path)
            try:
                if candidate.is_dir():
                    shutil.rmtree(candidate)
                else:
                    candidate.unlink(missing_ok=True)
            except OSError as error:
                raise CleanupConflictError(
                    "CLEANUP_ARTIFACT_DELETE_FAILED",
                    "A managed artifact could not be removed; database records were preserved.",
                    details={"artifactPath": relative_path},
                ) from error

    def _safe_target(self, relative_path: str) -> Path:
        relative = PurePosixPath(relative_path)
        if (
            not relative.parts
            or relative.is_absolute()
            or ".." in relative.parts
            or "\\" in relative_path
        ):
            self._unsafe(relative_path)
        cursor = self._root
        for part in relative.parts:
            cursor /= part
            if cursor.is_symlink():
                self._unsafe(relative_path)
        candidate = self._root.joinpath(*relative.parts).resolve()
        if candidate == self._root or not candidate.is_relative_to(self._root):
            self._unsafe(relative_path)
        return candidate

    @staticmethod
    def _unsafe(relative_path: str) -> None:
        raise CleanupConflictError(
            "CLEANUP_ARTIFACT_PATH_UNSAFE",
            "A persisted cleanup artifact path is outside managed storage.",
            details={"artifactPath": relative_path},
        )


class CleanupService:
    def __init__(
        self,
        repository: CleanupRepository,
        artifact_store: CleanupArtifactStore,
    ) -> None:
        self._repository = repository
        self._artifact_store = artifact_store

    def preview_release(self, mobile_release_id: UUID) -> CleanupPreview:
        return cleanup_preview(self._repository.release_snapshot(mobile_release_id))

    def preview_game_reset(self, game_id: UUID) -> CleanupPreview:
        return cleanup_preview(self._repository.game_snapshot(game_id))

    def delete_release(
        self,
        mobile_release_id: UUID,
        command: CleanupCommand,
    ) -> CleanupResult:
        completed = self._repository.completed_result(
            "mobile_release",
            mobile_release_id,
            command.preview_token,
        )
        if completed is not None:
            return _as_completed(completed)
        preview = cleanup_preview(
            self._repository.release_snapshot(mobile_release_id, for_update=True)
        )
        self._validate(command, preview)
        self._artifact_store.delete(preview.snapshot.artifact_paths)
        result = _result(preview)
        self._repository.delete_release(preview.snapshot, result)
        return result

    def reset_game(
        self,
        game_id: UUID,
        command: CleanupCommand,
    ) -> CleanupResult:
        completed = self._repository.completed_result(
            "game_layout_data",
            game_id,
            command.preview_token,
        )
        if completed is not None:
            return _as_completed(completed)
        preview = cleanup_preview(self._repository.game_snapshot(game_id, for_update=True))
        self._validate(command, preview)
        self._artifact_store.delete(preview.snapshot.artifact_paths)
        result = _result(preview)
        self._repository.reset_game(preview.snapshot, result)
        return result

    @staticmethod
    def _validate(command: CleanupCommand, preview: CleanupPreview) -> None:
        if not command.confirmed or (
            command.confirmation_target != preview.snapshot.confirmation_target
        ):
            raise CleanupConflictError(
                "CLEANUP_CONFIRMATION_MISMATCH",
                "Cleanup requires the exact target identifier and explicit confirmation.",
            )
        if command.preview_token != preview.preview_token:
            raise CleanupConflictError(
                "CLEANUP_PREVIEW_STALE",
                "The cleanup preview no longer matches current data. Generate a new preview.",
            )
        if preview.snapshot.blockers:
            raise CleanupConflictError(
                "CLEANUP_BLOCKED",
                "Cleanup is blocked by an active or shared dependency.",
                details={"blockers": list(preview.snapshot.blockers)},
            )


def _result(preview: CleanupPreview) -> CleanupResult:
    snapshot = preview.snapshot
    return CleanupResult(
        kind=snapshot.kind,
        target_id=snapshot.target_id,
        target_label=snapshot.target_label,
        preview_token=preview.preview_token,
        deleted_counts=snapshot.counts,
        deleted_artifact_count=len(snapshot.artifact_paths),
        retained_shared_artifact_count=snapshot.retained_shared_artifact_count,
    )


def _as_completed(result: CleanupResult) -> CleanupResult:
    return CleanupResult(
        kind=result.kind,
        target_id=result.target_id,
        target_label=result.target_label,
        preview_token=result.preview_token,
        deleted_counts=result.deleted_counts,
        deleted_artifact_count=result.deleted_artifact_count,
        retained_shared_artifact_count=result.retained_shared_artifact_count,
        already_completed=True,
    )


__all__ = [
    "CleanupArtifactStore",
    "CleanupRepository",
    "CleanupService",
    "ManagedCleanupArtifactStore",
]
