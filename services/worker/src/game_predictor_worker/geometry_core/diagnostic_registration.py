"""Strict metadata-only staging for the existing recording-use ledger."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from .input_diagnostics import (
    SUPPORTED_PREPROCESSING_VERSION,
    decode_record,
    diagnostic_uses,
    digest,
)
from .settings import BoardPreset, ScreenPreset


def registration_request(document: dict[str, Any]) -> dict[str, Any]:
    record = decode_record(document)
    if digest(record.archived_preset) != record.model.preset_sha256:
        raise ValueError("DIAGNOSTIC_PRESET_HASH_MISMATCH")
    if (
        record.model.preprocessing_version != SUPPORTED_PREPROCESSING_VERSION
        or record.archived_preset.get("preprocessing_version") != record.model.preprocessing_version
    ):
        raise ValueError("DIAGNOSTIC_PREPROCESSING_VERSION_MISMATCH")
    if (
        ScreenPreset.model_validate(record.archived_preset.get("screen")) != record.screen_preset
        or BoardPreset.model_validate(record.archived_preset.get("board")) != record.board_preset
    ):
        raise ValueError("DIAGNOSTIC_PRESET_CONTRACT_MISMATCH")
    key = diagnostic_uses([record])[0]["deduplicationKey"]
    record_sha = document["sha256"]
    return {
        "schemaVersion": "diagnostic-registration-v1",
        "idempotencyKey": str(uuid5(NAMESPACE_URL, f"grid-diagnostic:{key}:{record_sha}")),
        "recordJson": json.dumps(
            document["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
        "recordSha256": record_sha,
        "presetJson": json.dumps(
            record.archived_preset, sort_keys=True, separators=(",", ":"), allow_nan=False
        ),
        "deduplicationKey": key,
    }


def stage_registration(game: UUID, documents: Iterable[dict[str, Any]]) -> dict[str, Any]:
    requests = {}
    for document in documents:
        request = registration_request(document)
        requests[request["recordSha256"]] = request
        if len(requests) > 250:
            raise ValueError("DIAGNOSTIC_REGISTRATION_BATCH_LIMIT")
    if not requests:
        raise ValueError("DIAGNOSTIC_REGISTRATION_EMPTY")
    body = {
        "schemaVersion": "diagnostic-registration-manifest-v1",
        "gameId": str(game),
        "status": "staged_not_registered",
        "purpose": "diagnostic_comparison",
        "readinessAccessIncluded": False,
        "requests": [requests[key] for key in sorted(requests)],
    }
    return {**body, "sha256": digest(body)}


def require_registration(value: Mapping[str, Any]) -> dict[str, Any]:
    documents = []
    for request in value.get("requests", []):
        documents.append(
            {"payload": json.loads(request["recordJson"]), "sha256": request["recordSha256"]}
        )
    expected = stage_registration(UUID(value["gameId"]), documents)
    if dict(value) != expected:
        raise ValueError("DIAGNOSTIC_REGISTRATION_MANIFEST_MISMATCH")
    return expected
