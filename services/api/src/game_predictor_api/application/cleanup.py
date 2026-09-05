"""Application service for preview-bound cleanup of local working data."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.cleanup import (
    BoardSourceCleanupSelection,
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

    def board_source_snapshot(
        self,
        game_id: UUID,
        selection: BoardSourceCleanupSelection,
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

    def delete_board_sources(
        self,
        snapshot: CleanupSnapshot,
        result: CleanupResult,
    ) -> None: ...


class CleanupArtifactStore(Protocol):
    def delete(self, relative_paths: tuple[str, ...]) -> None: ...

    def quarantine(self, operation_key: str, relative_paths: tuple[str, ...]) -> None: ...

    def restore(self, operation_key: str) -> None: ...

    def finalize(self, operation_key: str) -> None: ...

    def recover(self, completed_operation_keys: set[str]) -> None: ...


class ManagedCleanupArtifactStore:
    """Manage explicit artifact cleanup with a durable rollback quarantine."""

    def __init__(self, artifact_root: Path) -> None:
        self._root = artifact_root.resolve()
        self._quarantine_root = self._root / "cleanup-quarantine"

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

    def quarantine(self, operation_key: str, relative_paths: tuple[str, ...]) -> None:
        quarantine = self._quarantine_target(operation_key)
        if quarantine.exists():
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_QUARANTINE_EXISTS",
                "A previous cleanup quarantine with this operation key still exists.",
            )
        try:
            quarantine.mkdir(parents=True, exist_ok=False)
            candidates = [
                (relative_path, self._safe_target(relative_path))
                for relative_path in _non_overlapping_paths(relative_paths)
            ]
            moved = [relative_path for relative_path, candidate in candidates if candidate.exists()]
            self._write_quarantine_receipt(quarantine, operation_key, moved)
            for relative_path, candidate in candidates:
                if relative_path not in moved:
                    continue
                destination = quarantine.joinpath(*PurePosixPath(relative_path).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                candidate.replace(destination)
        except CleanupConflictError:
            # Validation happens before the receipt or any move. Do not leave an
            # empty quarantine directory that would make later startup recovery
            # treat a rejected request as an incomplete cleanup.
            shutil.rmtree(quarantine, ignore_errors=True)
            raise
        except OSError as error:
            self._restore_quarantine(quarantine, operation_key, suppress_errors=True)
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_QUARANTINE_FAILED",
                "Managed artifacts could not be moved to cleanup quarantine.",
            ) from error

    def restore(self, operation_key: str) -> None:
        self._restore_quarantine(
            self._quarantine_target(operation_key),
            operation_key,
            suppress_errors=False,
        )

    def finalize(self, operation_key: str) -> None:
        quarantine = self._quarantine_target(operation_key)
        if not quarantine.exists():
            return
        try:
            shutil.rmtree(quarantine)
        except OSError as error:
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_FINALIZE_FAILED",
                "The committed cleanup quarantine could not be finalized.",
            ) from error

    def recover(self, completed_operation_keys: set[str]) -> None:
        if not self._quarantine_root.exists():
            return
        for quarantine in sorted(self._quarantine_root.iterdir()):
            if not quarantine.is_dir() or quarantine.is_symlink():
                raise CleanupConflictError(
                    "CLEANUP_ARTIFACT_QUARANTINE_UNSAFE",
                    "Cleanup quarantine contains an unsafe entry.",
                )
            operation_key = quarantine.name
            self._validate_operation_key(operation_key)
            if operation_key in completed_operation_keys:
                self.finalize(operation_key)
            else:
                self.restore(operation_key)

    def _restore_quarantine(
        self,
        quarantine: Path,
        operation_key: str,
        *,
        suppress_errors: bool,
    ) -> None:
        if not quarantine.exists():
            return
        try:
            receipt = json.loads((quarantine / "receipt.json").read_text("utf-8"))
            if receipt.get("operationKey") != operation_key or not isinstance(
                receipt.get("movedPaths"), list
            ):
                raise ValueError("invalid cleanup quarantine receipt")
            for relative_path in sorted(receipt["movedPaths"], key=_path_depth, reverse=True):
                if not isinstance(relative_path, str):
                    raise ValueError("invalid cleanup quarantine path")
                destination = self._safe_target(relative_path)
                source = quarantine.joinpath(*PurePosixPath(relative_path).parts)
                if destination.exists() and not source.exists():
                    continue
                if not source.exists():
                    raise ValueError("missing cleanup quarantine artifact")
                if destination.exists():
                    raise ValueError("cleanup artifact restore would overwrite a file")
                destination.parent.mkdir(parents=True, exist_ok=True)
                source.replace(destination)
            shutil.rmtree(quarantine)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            if suppress_errors:
                return
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_RESTORE_FAILED",
                "Cleanup artifacts could not be restored after a failed transaction.",
            ) from error

    def _quarantine_target(self, operation_key: str) -> Path:
        self._validate_operation_key(operation_key)
        target = (self._quarantine_root / operation_key).resolve()
        root = self._quarantine_root.resolve()
        if not target.is_relative_to(root):
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_QUARANTINE_UNSAFE",
                "Cleanup quarantine target is outside managed storage.",
            )
        return target

    @staticmethod
    def _validate_operation_key(operation_key: str) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", operation_key) is None:
            raise CleanupConflictError(
                "CLEANUP_ARTIFACT_QUARANTINE_UNSAFE",
                "Cleanup quarantine operation key is invalid.",
            )

    @staticmethod
    def _write_quarantine_receipt(
        quarantine: Path,
        operation_key: str,
        moved_paths: list[str],
    ) -> None:
        (quarantine / "receipt.json").write_text(
            json.dumps(
                {"movedPaths": moved_paths, "operationKey": operation_key},
                separators=(",", ":"),
                sort_keys=True,
            ),
            encoding="utf-8",
        )

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
        self._pending_quarantines: set[str] = set()

    def preview_release(self, mobile_release_id: UUID) -> CleanupPreview:
        return cleanup_preview(self._repository.release_snapshot(mobile_release_id))

    def preview_game_reset(self, game_id: UUID) -> CleanupPreview:
        return cleanup_preview(self._repository.game_snapshot(game_id))

    def preview_board_sources(
        self,
        game_id: UUID,
        selection: BoardSourceCleanupSelection,
    ) -> CleanupPreview:
        return cleanup_preview(self._repository.board_source_snapshot(game_id, selection))

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

    def delete_board_sources(
        self,
        game_id: UUID,
        selection: BoardSourceCleanupSelection,
        command: CleanupCommand,
    ) -> CleanupResult:
        completed = self._repository.completed_result(
            "board_source_ranges",
            game_id,
            command.preview_token,
        )
        if completed is not None:
            return _as_completed(completed)
        preview = cleanup_preview(
            self._repository.board_source_snapshot(game_id, selection, for_update=True)
        )
        self._validate(command, preview)
        quarantine_key = preview.preview_token
        self._artifact_store.quarantine(
            quarantine_key,
            preview.snapshot.artifact_paths,
        )
        result = _result(preview, quarantine_key=quarantine_key)
        try:
            self._repository.delete_board_sources(preview.snapshot, result)
        except BaseException:
            self._artifact_store.restore(quarantine_key)
            raise
        self._pending_quarantines.add(quarantine_key)
        return result

    def finalize_committed_artifacts(self) -> None:
        for quarantine_key in tuple(self._pending_quarantines):
            self._artifact_store.finalize(quarantine_key)
            self._pending_quarantines.remove(quarantine_key)

    def restore_uncommitted_artifacts(self) -> None:
        for quarantine_key in tuple(self._pending_quarantines):
            self._artifact_store.restore(quarantine_key)
            self._pending_quarantines.remove(quarantine_key)

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


def _result(
    preview: CleanupPreview,
    *,
    quarantine_key: str | None = None,
) -> CleanupResult:
    snapshot = preview.snapshot
    return CleanupResult(
        kind=snapshot.kind,
        target_id=snapshot.target_id,
        target_label=snapshot.target_label,
        preview_token=preview.preview_token,
        deleted_counts=snapshot.counts,
        deleted_artifact_count=len(snapshot.artifact_paths),
        retained_shared_artifact_count=snapshot.retained_shared_artifact_count,
        quarantine_key=quarantine_key,
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
        quarantine_key=result.quarantine_key,
    )


def _path_depth(relative_path: str) -> tuple[int, str]:
    return (len(PurePosixPath(relative_path).parts), relative_path)


def _non_overlapping_paths(relative_paths: tuple[str, ...]) -> tuple[str, ...]:
    selected: list[str] = []
    for relative_path in sorted(set(relative_paths), key=_path_depth):
        parts = PurePosixPath(relative_path).parts
        if any(
            parts[: len(PurePosixPath(parent).parts)] == PurePosixPath(parent).parts
            for parent in selected
        ):
            continue
        selected.append(relative_path)
    return tuple(selected)


__all__ = [
    "CleanupArtifactStore",
    "CleanupRepository",
    "CleanupService",
    "ManagedCleanupArtifactStore",
]
