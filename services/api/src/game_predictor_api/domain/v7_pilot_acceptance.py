"""Canonical acceptance identity for the existing, selectively enabled V7 gate."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from game_predictor_api.domain.v7_selection_delivery import (
    V7PilotGate,
    payload_fingerprint,
    require_sha256,
)

RECEIPT_VERSION = "v7-reviewed-pilot-acceptance-v1"
OPERATOR_RECEIPT_VERSION = "v7-reviewed-pilot-acceptance-v2"
_SHA_FIELDS = (
    "profileFingerprint",
    "sessionExportChecksumSha256",
    "historicalManifestFingerprint",
    "observerFingerprint",
    "ocrModelFingerprint",
    "functionalReportFingerprint",
    "reviewReportFingerprint",
)
_TEXT_FIELDS = (
    "geometryFamilyId",
    "sourceGameRef",
    "databaseName",
    "actor",
    "acceptedAt",
    "operatorDecisionReference",
    "calibrationSessionId",
)
_BINDING_FIELDS = ("sourceRoot", "sourceFingerprint", "sourceGameRef", "geometryFamilyId")


def validate_pilot_acceptance(payload: dict[str, object], database_name: str) -> None:
    """Validate the entire semantic payload, including fixture confinement."""
    required = {
        "version",
        "scope",
        "mode",
        "manualConfirmationRequired",
        "automaticAllowed",
        "countsTowardT12",
        "fixtureRoot",
        "sourceBindings",
        "ocrRuntimeIdentity",
        *_SHA_FIELDS,
        *_TEXT_FIELDS,
    }
    operator_sources = payload.get("version") == OPERATOR_RECEIPT_VERSION
    if operator_sources:
        required.add("sourcePolicy")
    if set(payload) != required or payload["version"] not in (
        RECEIPT_VERSION,
        OPERATOR_RECEIPT_VERSION,
    ):
        raise ValueError("Invalid acceptance receipt schema.")
    if (
        payload["mode"] != "semi_automatic"
        or payload["manualConfirmationRequired"] is not True
        or payload["automaticAllowed"] is not False
        or payload["countsTowardT12"] is not False
        or payload["databaseName"] != database_name
    ):
        raise ValueError("Invalid acceptance policy/database identity.")
    for key in (*_SHA_FIELDS, *_TEXT_FIELDS):
        if operator_sources and key == "sourceGameRef":
            continue
        value = payload[key]
        if not isinstance(value, str) or not value or len(value) > 200:
            raise ValueError(f"Invalid acceptance field {key}.")
        if key in _SHA_FIELDS:
            require_sha256(value)
    timestamp = datetime.fromisoformat(str(payload["acceptedAt"]))
    if timestamp.tzinfo is None:
        raise ValueError("Acceptance timestamp requires a timezone.")
    runtime = payload["ocrRuntimeIdentity"]
    if (
        not isinstance(runtime, dict)
        or set(runtime) != {"name", "version"}
        or not all(isinstance(value, str) and value for value in runtime.values())
    ):
        raise ValueError("Missing OCR runtime identity.")
    bindings = payload["sourceBindings"]
    if not isinstance(bindings, list):
        raise ValueError("Missing exact source bindings.")
    if operator_sources:
        if (
            payload["sourcePolicy"] != "operator_selected_local_folder"
            or payload["scope"] != "real_pilot"
            or payload["fixtureRoot"] is not None
            or payload["sourceGameRef"] is not None
            or bindings
        ):
            raise ValueError("Operator-selected sources require a real, game-independent receipt.")
        return
    if not bindings:
        raise ValueError("Missing exact source bindings.")
    roots: list[str] = []
    fixture_root = payload["fixtureRoot"]
    scope = payload["scope"]
    if scope == "technical_fixture":
        if not isinstance(fixture_root, str) or database_name != "game_predictor_v7_pilot":
            raise ValueError("Technical fixture requires its isolated database/root.")
        fixture = Path(fixture_root)
        if (
            fixture.parts[-3:] != (".claude", "v7-pilot-runtime", "fixtures")
            or str(fixture.resolve(strict=True)) != fixture_root
        ):
            raise ValueError("Fixture root must be the exact task-owned directory.")
    elif scope == "real_pilot":
        if fixture_root is not None:
            raise ValueError("Real pilot cannot use a fixture authorization.")
    else:
        raise ValueError("Unknown acceptance scope.")
    for binding in bindings:
        if not isinstance(binding, dict) or set(binding) != set(_BINDING_FIELDS):
            raise ValueError("Invalid binding schema.")
        if not all(isinstance(binding[key], str) and binding[key] for key in _BINDING_FIELDS):
            raise ValueError("Invalid binding values.")
        source_root = str(binding["sourceRoot"])
        canonical = Path(source_root).resolve(strict=True)
        if str(canonical) != source_root or (
            scope == "technical_fixture" and not canonical.is_relative_to(Path(str(fixture_root)))
        ):
            raise ValueError("Source root is outside its approved scope.")
        if (
            binding["sourceGameRef"] != payload["sourceGameRef"]
            or binding["geometryFamilyId"] != payload["geometryFamilyId"]
        ):
            raise ValueError("Binding family/game mismatch.")
        require_sha256(str(binding["sourceFingerprint"]))
        roots.append(source_root)
    if roots != sorted(set(roots)):
        raise ValueError("Bindings require unique canonical roots in sorted order.")


def receipt_matches_gate(
    payload: dict[str, object], fingerprint: str, gate: V7PilotGate, database_name: str
) -> bool:
    """A fingerprint string or accepted metadata alone never enables a gate."""
    try:
        validate_pilot_acceptance(payload, database_name)
        return (
            payload_fingerprint(payload) == fingerprint == gate.receipt_fingerprint
            and payload["geometryFamilyId"] == gate.geometry_family_id
            and payload["sourceGameRef"] == gate.source_game_ref
            and payload["profileFingerprint"] == gate.profile_fingerprint
            and payload["observerFingerprint"] == gate.observer_fingerprint
            and payload["ocrModelFingerprint"] == gate.ocr_model_fingerprint
            and payload["sourceBindings"] == list(gate.source_bindings)
            and payload.get("sourcePolicy", "exact_sources") == gate.source_policy
        )
    except (ValueError, OSError, TypeError):
        return False
