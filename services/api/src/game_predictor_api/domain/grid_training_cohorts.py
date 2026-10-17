"""Deterministic geometry cohort policy, independent of transport and persistence."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterable
from typing import Any

from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceImageBounds,
    SourceLatticeNodes,
    SourcePoint,
)

POLICY = "application-grid-cohort-v1"
SNAPSHOT_FORMAT = "application-grid-snapshot-v1"
WEIGHT_POLICY = "correction-weight-4-to-1-v1"
ROLES = ("TRAIN", "VALIDATION", "REGRESSION")
SOURCE_BYTE_LIMIT = 64 * 1024 * 1024
METADATA_PAGE_SIZE = 200
MATERIALIZATION_PAGE_SIZE = 5
COMMAND_SECONDS = 60


class GridCohortError(ValueError):
    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def exact_lattice(
    geometry: dict[str, Any], width: int, height: int
) -> tuple[list[dict[str, float]], list[list[dict[str, float]]]]:
    """Keep every stored point, including deformed inner nodes, without quad fitting."""

    raw = geometry.get("latticeNodes")
    if (
        not isinstance(raw, list)
        or len(raw) != 24
        or any(not isinstance(point, dict) or set(point) != {"x", "y"} for point in raw)
    ):
        raise GridCohortError("EXACT_LATTICE_REQUIRED", "The exact 24 stored nodes are required.")
    try:
        lattice = SourceLatticeNodes(tuple(SourcePoint(point["x"], point["y"]) for point in raw))
        lattice.require_within(SourceImageBounds(width, height))
        cells = [
            lattice.cell_quad(
                topology=BoardTopology(3, 5), row_index=row, column_index=column
            ).to_dict()
            for row in range(3)
            for column in range(5)
        ]
    except ImageGeometryContractError as error:
        raise GridCohortError(error.code, str(error)) from error
    return lattice.to_dict(), cells


def target_fence(target: dict[str, Any]) -> dict[str, Any]:
    """Pin geometry and its issues, independently of symbol labels and confidence."""

    board, review = target.get("board") or {}, target.get("review") or {}
    return {
        "board": {
            key: board.get(key)
            for key in (
                "id",
                "source_image_id",
                "position_index",
                "sequence_number",
                "geometry_revision",
                "source_geometry_revision_id",
                "geometry_checksum_sha256",
                "board_geometry",
                "grid_rows",
                "grid_columns",
                "completeness_status",
                "unavailable_cell_indices",
                "geometry_qualification",
                "geometry_engine_name",
                "geometry_engine_version",
                "asset_mode",
                "approved_geometry_revision",
                "geometry_approved_by",
                "geometry_approved_at",
            )
        },
        "reviewId": review.get("id"),
        "owner": target.get("owner"),
        "foreignOwner": target.get("foreignOwner"),
        "rejected": board.get("status") == "rejected" or review.get("status") == "superseded",
        "pending": target.get("pending"),
        "issues": [
            {key: cell.get(key) for key in ("id", "quality_issue", "geometry_revision")}
            for cell in target.get("cells", [])
            if cell.get("quality_issue") == "grid_issue" and cell.get("review_state") == "pending"
        ],
        "renders": target.get("renders", []),
    }


def role_summary(mode: str, members: Iterable[dict[str, Any]]) -> dict[str, Any]:
    counters: dict[str, Counter[str]] = {role: Counter() for role in ROLES}
    recordings: dict[str, set[str]] = {role: set() for role in ROLES}
    reasons: Counter[str] = Counter()
    for member in members:
        reasons.update(member.get("reasons", []))
        role = member.get("role")
        if role not in counters or member.get("used") is not True:
            continue
        boards = int(member.get("boardEligibleCount", 0))
        full = bool(member.get("screenEligible"))
        recording = member.get("recording") or {}
        if recording.get("qualification") != "eligible":
            continue
        counters[role]["boards"] += boards
        counters[role]["photos"] += bool(boards)
        counters[role]["full"] += full
        if boards:
            recordings[role].add(recording["groupId"])
    output = []
    for role in ROLES:
        train = role == "TRAIN"
        boards, photos, required_full = (
            (30, 10, 10 if mode == "screen+grid" else 0) if train else (15, 5, 5)
        )
        count = counters[role]
        output.append(
            {
                "role": role,
                "requiredBoards": boards,
                "requiredPhotos": photos,
                "requiredFullPhotos": required_full,
                "eligibleBoards": count["boards"],
                "eligiblePhotos": count["photos"],
                "eligibleFullPhotos": count["full"],
                "missingBoards": max(0, boards - count["boards"]),
                "missingPhotos": max(0, photos - count["photos"]),
                "missingFullPhotos": max(0, required_full - count["full"]),
                "recordingRequired": not bool(recordings[role]),
            }
        )
    return {"roles": output, "reasonCounts": dict(sorted(reasons.items()))}


def require_minima(summary: dict[str, Any]) -> None:
    if any(
        row["missingBoards"]
        or row["missingPhotos"]
        or row["missingFullPhotos"]
        or row["recordingRequired"]
        for row in summary["roles"]
    ):
        raise GridCohortError(
            "GRID_COHORT_MINIMUM_NOT_MET",
            "Each role requires its own independent recording, boards and fully annotated photos.",
        )
