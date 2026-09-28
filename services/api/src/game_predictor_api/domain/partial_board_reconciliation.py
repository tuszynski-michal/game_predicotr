"""Immutable, explicitly scoped input for the partial-board repair pilot."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

PILOT_GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")
FOLLOWUP_777_SEQUENCES = (225930, 225933, 225939, 225942, 225948, 225957)
PILOT_SEQUENCES = (
    60856,
    61018,
    61027,
    61036,
    61852,
    61855,
    61864,
    61873,
    61879,
    61882,
    61888,
    61891,
    61897,
    61900,
    61906,
    61909,
    61918,
    61927,
    62053,
    62062,
    62071,
    62287,
    62296,
    62404,
    62440,
    62575,
    62977,
    62980,
    62986,
    62989,
    62995,
    62998,
    63004,
    63007,
    63013,
    63016,
    63022,
    63025,
    63031,
    63034,
    63040,
    63043,
    63049,
    63052,
    63058,
    63061,
    63067,
    63070,
    63076,
    63079,
    63085,
    63088,
    63094,
    63097,
    63103,
    63106,
    63112,
    63115,
    63121,
    63124,
    63133,
    63160,
    109591,
    109600,
    109627,
    109636,
    109645,
    114625,
    114628,
    114631,
)
SCHEMA = "partial-board-reconciliation-preview-v1"
RECEIPT_SCHEMA = "partial-board-reconciliation-receipt-v1"
MAX_APPLY_BOARDS = 5
MAX_AUDIT_BOARDS = 50


class ReconciliationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str, allow_nan=False))


def digest(value: object) -> str:
    payload = json.dumps(
        value, default=str, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def blocked_board(sequence_number: int, code: str, message: str) -> dict[str, Any]:
    return {
        "sequenceNumber": sequence_number,
        "status": "blocked",
        "code": code,
        "message": message,
    }


def build_manifest(
    *,
    game_id: UUID,
    boards: Sequence[Mapping[str, Any]],
    storage_generation: int,
    sequences: Sequence[int] = PILOT_SEQUENCES,
) -> dict[str, Any]:
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "gameId": str(game_id),
        "storageGeneration": storage_generation,
        "sequences": list(sequences),
        "boards": json_value(boards),
        "countRebuild": {
            "requiredAfterApply": True,
            "semanticVersion": 2,
            "mode": "separate-bounded-operation",
            "executed": False,
        },
    }
    report["previewSha256"] = digest(report)
    validate_manifest(report)
    return report


def validate_manifest(value: Mapping[str, Any]) -> None:
    """Validate the complete input before consulting an idempotency receipt."""
    try:
        UUID(value["gameId"])
        allowed_sequences = (PILOT_SEQUENCES, FOLLOWUP_777_SEQUENCES)
        valid = (
            value["schema"] == SCHEMA
            and type(value["storageGeneration"]) is int
            and value["storageGeneration"] >= 2
            and value["sequences"] in [list(scope) for scope in allowed_sequences]
            and isinstance(value["boards"], list)
            and [row["sequenceNumber"] for row in value["boards"]] == value["sequences"]
            and value["previewSha256"]
            == digest({key: item for key, item in value.items() if key != "previewSha256"})
        )
        for row in value["boards"]:
            if row["status"] == "blocked":
                valid = valid and isinstance(row["code"], str)
                continue
            valid = valid and (
                row["status"] == "ready"
                and row["guardSha256"] == digest(row["guard"])
                and len(row["sourceVisibility"]) == 15
                and all(v in {"full", "partial", "outside"} for v in row["sourceVisibility"])
                and row["guard"]["sequence_number"] == row["sequenceNumber"]
            )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ReconciliationError("RECONCILIATION_MANIFEST_INVALID", "Preview input is invalid.")


def manifest_board(manifest: Mapping[str, Any], sequence_number: int) -> Mapping[str, Any]:
    validate_manifest(manifest)
    rows = [row for row in manifest["boards"] if row["sequenceNumber"] == sequence_number]
    if len(rows) != 1 or rows[0]["status"] != "ready":
        raise ReconciliationError("RECONCILIATION_BOARD_BLOCKED", "Board has no ready preview.")
    return cast(Mapping[str, Any], rows[0])


def human_decisions(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Protect operator choices while allowing a newly discovered visibility badge."""
    return {
        str(cell["cell_index"]): {
            key: cell.get(key)
            for key in (
                "id",
                "assigned_symbol_id",
                "assignment_source",
                "review_state",
                "approved_crop_sample_id",
                "approved_crop_checksum_sha256",
                "approved_geometry_revision",
                "verification_outcome",
                "verified_symbol_id_v2",
                "approved_asset_mode",
                "approved_source_geometry_revision_id",
                "approved_render_spec_checksum_sha256",
                "approved_rendered_pixel_checksum_sha256",
            )
        }
        | {
            "quality_issue": (
                None
                if cell.get("quality_issue") == "partial_visibility"
                else cell.get("quality_issue")
            )
        }
        for cell in cells
        if cell.get("assignment_source") in {"human", "board_decision"}
        or cell.get("review_state") == "approved"
        or cell.get("quality_issue") in {"blurry", "unreadable", "grid_issue"}
    }
