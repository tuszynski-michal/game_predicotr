"""Immutable scopes and canonical-free retirement provenance."""

from __future__ import annotations

from typing import Any

from game_predictor_api.domain.symbol_readability import digest


def planned_scope(document: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in document.items()
        if key not in {"id", "phase", "revision", "scope_digest", "failure_code"}
    }


def scope_digest(document: dict[str, Any]) -> str:
    if document.get("compact_schema") == "source-replacement-compact-v1":
        return str(document["frozen_scope_digest"])
    return digest(planned_scope(document))


def retirement_resolved_value(
    prior: dict[str, Any], *, batch: str, entry: str, source_sha256: str
) -> dict[str, Any]:
    """The whole prior row includes its complete, possibly nested resolved_value."""
    return {
        "action": "superseded",
        "reason": "source_replacement_retired",
        "batchId": batch,
        "entryId": entry,
        "sourceSha256": source_sha256,
        "sequenceNumber": prior["sequence_number"],
        "previous": prior,
    }
