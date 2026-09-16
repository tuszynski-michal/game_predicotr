"""Framework-independent contracts for destructive local cleanup workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal
from uuid import UUID

CleanupKind = Literal["mobile_release", "game_layout_data", "board_source_ranges"]


class CleanupError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class CleanupNotFoundError(CleanupError):
    """The exact cleanup target does not exist."""


class CleanupConflictError(CleanupError):
    """The current state cannot be removed safely."""


@dataclass(frozen=True, slots=True)
class BoardSourceCleanupSelection:
    """The explicit board numbers used to select whole image-source ranges."""

    sequence_numbers: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.sequence_numbers:
            raise CleanupError(
                "CLEANUP_SEQUENCE_SELECTION_EMPTY",
                "Select at least one board number for source cleanup.",
            )
        if any(number <= 0 for number in self.sequence_numbers):
            raise CleanupError(
                "CLEANUP_SEQUENCE_NUMBER_INVALID",
                "Board numbers selected for cleanup must be positive.",
            )
        if tuple(sorted(set(self.sequence_numbers))) != self.sequence_numbers:
            raise CleanupError(
                "CLEANUP_SEQUENCE_SELECTION_NOT_CANONICAL",
                "Board numbers selected for cleanup must be unique and sorted.",
            )


@dataclass(frozen=True, slots=True)
class CleanupCount:
    name: str
    count: int


@dataclass(frozen=True, slots=True)
class CleanupSnapshot:
    kind: CleanupKind
    target_id: UUID
    target_label: str
    confirmation_target: str
    counts: tuple[CleanupCount, ...]
    artifact_paths: tuple[str, ...]
    retained_shared_artifact_count: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CleanupPreview:
    snapshot: CleanupSnapshot
    preview_token: str


@dataclass(frozen=True, slots=True)
class CleanupCommand:
    preview_token: str
    confirmation_target: str
    confirmed: bool


@dataclass(frozen=True, slots=True)
class CleanupResult:
    kind: CleanupKind
    target_id: UUID
    target_label: str
    preview_token: str
    deleted_counts: tuple[CleanupCount, ...]
    deleted_artifact_count: int
    retained_shared_artifact_count: int
    already_completed: bool = False
    quarantine_key: str | None = None


def cleanup_preview(snapshot: CleanupSnapshot) -> CleanupPreview:
    payload = {
        "artifactPaths": list(snapshot.artifact_paths),
        "blockers": list(snapshot.blockers),
        "confirmationTarget": snapshot.confirmation_target,
        "counts": [{"count": item.count, "name": item.name} for item in snapshot.counts],
        "kind": snapshot.kind,
        "retainedSharedArtifactCount": snapshot.retained_shared_artifact_count,
        "targetId": str(snapshot.target_id),
        "targetLabel": snapshot.target_label,
        "warnings": list(snapshot.warnings),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return CleanupPreview(
        snapshot=snapshot,
        preview_token=hashlib.sha256(canonical).hexdigest(),
    )


__all__ = [
    "BoardSourceCleanupSelection",
    "CleanupCommand",
    "CleanupConflictError",
    "CleanupCount",
    "CleanupError",
    "CleanupKind",
    "CleanupNotFoundError",
    "CleanupPreview",
    "CleanupResult",
    "CleanupSnapshot",
    "cleanup_preview",
]
