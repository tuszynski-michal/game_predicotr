"""D-462 data migration plan (TASK-0728): pure plan and manifest rules.

The migration never verifies a cell. It only takes back approvals of other
pixels (R10), reopens a board resolved on such approvals, closes a board whose
cells are all evidence (R2) and refreshes stale board-search documents (R8).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

MANIFEST_VERSION = "cell-level-verification-migration-v1"
MIGRATION_ACTOR = "cell-level-migration"
REOPEN_REASON = "approval_pixels_changed"
RESOLVED_STATUSES = frozenset({"accepted", "corrected"})
MIGRATED_STATUSES = frozenset({"pending", *RESOLVED_STATUSES})
CLOSE_ACTIONS = frozenset({"accepted", "corrected"})


class CellLevelMigrationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CellFingerprint:
    cell_index: int
    revision: int
    review_state: str
    crop_checksum_sha256: str | None
    rendered_pixel_checksum_sha256: str | None


@dataclass(frozen=True, slots=True)
class BoardMigrationPlan:
    review_item_id: UUID
    sequence_number: int | None
    status: str
    fingerprint: str
    reopen: bool
    recheck_cell_indices: tuple[int, ...]
    close_action: str | None
    refresh_projection: bool

    @property
    def has_actions(self) -> bool:
        return (
            self.reopen
            or bool(self.recheck_cell_indices)
            or self.close_action is not None
            or self.refresh_projection
        )

    def to_manifest(self) -> dict[str, Any]:
        return {
            "reviewItemId": str(self.review_item_id),
            "sequenceNumber": self.sequence_number,
            "status": self.status,
            "fingerprint": self.fingerprint,
            "reopen": self.reopen,
            "recheckCellIndices": list(self.recheck_cell_indices),
            "closeAction": self.close_action,
            "refreshProjection": self.refresh_projection,
        }

    @classmethod
    def from_manifest(cls, value: Mapping[str, Any]) -> BoardMigrationPlan:
        try:
            plan = cls(
                review_item_id=UUID(str(value["reviewItemId"])),
                sequence_number=_optional_int(value["sequenceNumber"]),
                status=str(value["status"]),
                fingerprint=str(value["fingerprint"]),
                reopen=_bool(value["reopen"]),
                recheck_cell_indices=tuple(_int(index) for index in value["recheckCellIndices"]),
                close_action=(None if value["closeAction"] is None else str(value["closeAction"])),
                refresh_projection=_bool(value["refreshProjection"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CellLevelMigrationError(
                "CELL_MIGRATION_MANIFEST_INVALID",
                f"A manifest board entry is invalid: {error}",
            ) from error
        if (
            plan.status not in MIGRATED_STATUSES
            or (plan.close_action is not None and plan.close_action not in CLOSE_ACTIONS)
            or list(plan.recheck_cell_indices) != sorted(set(plan.recheck_cell_indices))
            or not plan.has_actions
        ):
            raise CellLevelMigrationError(
                "CELL_MIGRATION_MANIFEST_INVALID",
                "A manifest board entry has no valid action.",
            )
        return plan


def board_fingerprint(
    *,
    status: str,
    resolution_revision: int,
    geometry_revision: int,
    cells: Iterable[CellFingerprint],
) -> str:
    """Identity of every value a plan depends on; any change is a drift."""

    payload = {
        "status": status,
        "resolutionRevision": resolution_revision,
        "geometryRevision": geometry_revision,
        "cells": [
            [
                cell.cell_index,
                cell.revision,
                cell.review_state,
                cell.crop_checksum_sha256,
                cell.rendered_pixel_checksum_sha256,
            ]
            for cell in sorted(cells, key=lambda cell: cell.cell_index)
        ],
    }
    return _sha256(payload)


def plan_board_migration(
    *,
    review_item_id: UUID,
    sequence_number: int | None,
    status: str,
    fingerprint: str,
    changed_pixel_approvals: Iterable[int],
    resolution_after_recheck: str | None,
    projection_stale: bool,
) -> BoardMigrationPlan:
    """Decide the actions of one board.

    `resolution_after_recheck` is the board decision derived from the cells as
    they are after the recheck (rechecked cells pending), or `None`.
    """

    if status not in MIGRATED_STATUSES:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_STATUS_INVALID",
            "Only pending or resolved boards take part in the migration.",
        )
    if resolution_after_recheck is not None and resolution_after_recheck not in CLOSE_ACTIONS:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_RESOLUTION_INVALID",
            "A cell-derived board decision must accept or correct the board.",
        )
    recheck = tuple(sorted(set(changed_pixel_approvals)))
    reopen = status in RESOLVED_STATUSES and bool(recheck)
    # A rechecked cell is pending, so it can never be part of a closing decision.
    close_action = resolution_after_recheck if status == "pending" and not recheck else None
    return BoardMigrationPlan(
        review_item_id=review_item_id,
        sequence_number=sequence_number,
        status=status,
        fingerprint=fingerprint,
        reopen=reopen,
        recheck_cell_indices=recheck,
        close_action=close_action,
        refresh_projection=projection_stale,
    )


def manifest_counts(plans: Sequence[BoardMigrationPlan], *, scanned: int) -> dict[str, int]:
    return {
        "scannedBoards": scanned,
        "boards": len(plans),
        "recheckCells": sum(len(plan.recheck_cell_indices) for plan in plans),
        "recheckBoards": sum(1 for plan in plans if plan.recheck_cell_indices),
        "reopenBoards": sum(1 for plan in plans if plan.reopen),
        "closeBoards": sum(1 for plan in plans if plan.close_action is not None),
        "refreshProjectionBoards": sum(1 for plan in plans if plan.refresh_projection),
    }


def build_manifest(
    *,
    game_id: UUID,
    plans: Sequence[BoardMigrationPlan],
    scanned: int,
    generated_at: str,
    notes: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    ordered = sorted(plans, key=lambda plan: str(plan.review_item_id))
    body: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "gameId": str(game_id),
        "counts": manifest_counts(ordered, scanned=scanned),
        "boards": [plan.to_manifest() for plan in ordered],
        "notes": {key: sorted(values) for key, values in (notes or {}).items()},
    }
    return {**body, "generatedAt": generated_at, "previewSha256": _sha256(body)}


def validate_manifest(manifest: Mapping[str, Any]) -> tuple[UUID, tuple[BoardMigrationPlan, ...]]:
    """Return the game and plans of a manifest whose checksum still matches."""

    try:
        body = {
            "version": manifest["version"],
            "gameId": manifest["gameId"],
            "counts": manifest["counts"],
            "boards": manifest["boards"],
            "notes": manifest["notes"],
        }
        checksum = manifest["previewSha256"]
        game_id = UUID(str(manifest["gameId"]))
    except (KeyError, TypeError, ValueError) as error:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_MANIFEST_INVALID", f"The manifest is incomplete: {error}"
        ) from error
    if body["version"] != MANIFEST_VERSION:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_MANIFEST_VERSION", "The manifest version is not supported."
        )
    if _sha256(body) != checksum:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_MANIFEST_CHECKSUM", "The manifest content does not match its checksum."
        )
    plans = tuple(BoardMigrationPlan.from_manifest(board) for board in body["boards"])
    if len({plan.review_item_id for plan in plans}) != len(plans):
        raise CellLevelMigrationError(
            "CELL_MIGRATION_MANIFEST_INVALID", "A board appears more than once in the manifest."
        )
    counts = body["counts"]
    scanned = counts.get("scannedBoards") if isinstance(counts, Mapping) else None
    if not isinstance(scanned, int) or manifest_counts(plans, scanned=scanned) != counts:
        raise CellLevelMigrationError(
            "CELL_MIGRATION_MANIFEST_INVALID", "The manifest counts do not match its boards."
        )
    return game_id, plans


def _sha256(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("expected an integer")
    return value


def _optional_int(value: object) -> int | None:
    return None if value is None else _int(value)


def _bool(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("expected a boolean")
    return value


__all__ = [
    "CLOSE_ACTIONS",
    "MANIFEST_VERSION",
    "MIGRATION_ACTOR",
    "REOPEN_REASON",
    "BoardMigrationPlan",
    "CellFingerprint",
    "CellLevelMigrationError",
    "board_fingerprint",
    "build_manifest",
    "manifest_counts",
    "plan_board_migration",
    "validate_manifest",
]
