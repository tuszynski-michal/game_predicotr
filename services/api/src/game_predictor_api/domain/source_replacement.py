"""Exact, non-destructive plans and independent human-quality evidence."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Mapping, Sequence
from typing import Any

from game_predictor_api.domain.symbol_readability import crop_identity, digest


class SourceReplacementError(ValueError):
    def __init__(
        self, code: str, message: str, *, details: dict[str, object] | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


def qualification(
    current: Mapping[str, Any],
    decisions: Sequence[Mapping[str, Any]],
    legacy: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Latest decisive human judgment for these pixels; never rank by scan age."""
    identity = crop_identity(current)
    decisive = [
        row
        for row in decisions
        if row["identity"] == identity and row["state"] in {"readable", "unreadable"}
    ]
    if decisive:
        last = max(decisive, key=lambda row: int(row["ordinal"]))
        return {
            "state": last["state"],
            "identity": identity,
            "proof": [dict(last)],
            "blocker": None,
        }
    candidates = [
        *legacy,
        *(
            row["prior_quality_judgment"]
            for row in decisions
            if row.get("prior_quality_judgment") is not None
        ),
    ]
    # Consensus includes retained pre-ledger states. Their capture order is not
    # the chronology of the original human judgments.
    old_by_proof = {
        (str(row["run_id"]), int(row["revision"]), row["state"]): row
        for row in candidates
        if row["identity"] == identity
        and row["ever_labelled"]
        and row["state"] in {"readable", "unreadable"}
    }
    old = list(old_by_proof.values())
    states = {row["state"] for row in old}
    return {
        "state": next(iter(states))
        if len(states) == 1
        else (
            "unreadable" if not states and current.get("quality_issue") == "unreadable" else None
        ),
        "identity": identity,
        "proof": [
            dict(row)
            for row in sorted(
                old, key=lambda row: (str(row["run_id"]), int(row["revision"]), row["state"])
            )
        ],
        "blocker": "SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS" if len(states) > 1 else None,
    }


def manifest_csv(document: Mapping[str, Any]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "game_id",
            "source_ids",
            "source_sha256",
            "sequence_number",
            "board_id",
            "review_id",
            "geometry_revision",
            "resolution_revision",
            "state",
            "reasons",
            "batch_id",
            "entry_id",
        ]
    )
    for entry in document["entries"]:
        represented = {board["sequence_number"] for board in entry["boards"]}
        rows = list(entry["boards"]) + [
            {"sequence_number": number}
            for number in entry.get("sequence_numbers", [])
            if number not in represented
        ]
        for board in rows:
            writer.writerow(
                [
                    document["game_id"],
                    "|".join(entry["source_ids"]),
                    entry["source_sha256"],
                    board["sequence_number"],
                    board.get("id"),
                    board.get("review_id"),
                    board.get("geometry_revision"),
                    board.get("resolution_revision"),
                    document.get("status", "preview"),
                    json.dumps(entry["reasons"], ensure_ascii=False, sort_keys=True),
                    document.get("id"),
                    entry.get("id"),
                ]
            )
    return output.getvalue()


def preview_document(
    game_id: str, selected: list[str], entries: list[dict[str, Any]]
) -> dict[str, Any]:
    document = {
        "schema_version": "source-replacement-manifest-v1",
        "game_id": game_id,
        "mode": "replace_preserve_history",
        "selected_source_ids": sorted(set(selected)),
        "entries": entries,
        "revision": 0,
        "status": "preview",
        "retirement_available": False,
    }
    return {**document, "preview_token": digest(document)}
