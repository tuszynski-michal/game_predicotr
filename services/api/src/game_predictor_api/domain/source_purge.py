"""Small immutable replacement scopes; file receipts live outside the manifest."""

from typing import Any

from game_predictor_api.domain.source_replacement_retirement import scope_digest

PURGE_MODE = "replace_delete_source"
COMPACT_SCHEMA = "source-replacement-compact-v1"


def compact_entry(entry: dict[str, Any]) -> dict[str, Any]:
    result = {
        key: entry[key]
        for key in (
            "source_ids",
            "source_sha256",
            "range_start",
            "range_end",
            "sequence_numbers",
            "blockers",
        )
    }
    result.update(
        compact_schema=COMPACT_SCHEMA,
        frozen_scope_digest=scope_digest(entry),
        reasons=[
            {"sequence_number": r["sequence_number"], "cell_index": r["cell_index"]}
            for r in entry["reasons"]
        ],
        retained_metadata={
            name: len(items)
            for name, items in entry["dependencies"].items()
            if name != "active_jobs"
        },
    )
    # Existing manifest clients keep their shape, but none of the old graph is copied.
    for key in (
        "sources",
        "geometry_revisions",
        "boards",
        "pending_slots",
        "canonical",
        "pending",
        "reservations",
        "retired",
        "evidence",
    ):
        result[key] = []
    result["dependencies"] = {}
    return result
