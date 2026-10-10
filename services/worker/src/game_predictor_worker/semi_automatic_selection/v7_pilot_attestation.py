"""Recheck immutable calibration provenance and installed OCR without inference."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast
from uuid import UUID

from game_predictor_api.domain.v7_selection_delivery import V7PilotGate, require_sha256

from .v7_calibration import (
    V7CropAssessment,
    V7GeometryProfile,
    V7LabelGeometryAnnotation,
    calibrate_v7_label_geometry,
)
from .v7_configuration import V7CorpusSplit


def validate_v7_pilot_attestation(
    runtime_root: Path,
    profile: V7GeometryProfile,
    profile_export_checksum: str,
    gate: V7PilotGate,
) -> None:
    """Use the provider's verified receipt; read only its exact immutable export.

    This validates historical metadata. Current source bytes are separately
    fenced by the exact source manifest/binding, without reading other cases.
    No writable store, session recovery, JPEG decoder or Paddle constructor runs.
    """
    receipt = gate.acceptance_receipt
    if receipt is None:
        raise ValueError("Missing verified acceptance receipt.")
    try:
        runtime_version = version("paddlepaddle")
    except PackageNotFoundError as error:
        raise ValueError("Accepted OCR runtime is not installed.") from error
    if receipt["ocrRuntimeIdentity"] != {
        "name": "paddlepaddle-cpu",
        "version": runtime_version,
    }:
        raise ValueError("Installed OCR runtime differs from the acceptance receipt.")
    checksum = _text(receipt["sessionExportChecksumSha256"])
    require_sha256(checksum)
    if checksum != profile_export_checksum:
        raise ValueError("Profile and acceptance refer to different immutable exports.")
    session_id = _text(receipt["calibrationSessionId"])
    if str(UUID(session_id)) != session_id:
        raise ValueError("Invalid canonical calibration session identity.")
    path = (
        runtime_root
        / "v7-label-geometry"
        / "sessions"
        / session_id
        / "exports"
        / f"{checksum[:24]}.json"
    )
    for ancestor in (path, *path.parents):
        stat = ancestor.lstat()
        if ancestor.is_symlink() or getattr(stat, "st_file_attributes", 0) & 0x400:
            raise ValueError("Immutable export cannot use a link/reparse path.")
    if not path.is_file() or path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("Immutable export is unavailable or oversized.")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError("Immutable export bytes differ from the accepted full SHA256.")
    wrapper = _mapping(json.loads(content))
    if (
        set(wrapper) != {"schemaVersion", "session"}
        or type(wrapper["schemaVersion"]) is not int
        or wrapper["schemaVersion"] != 1
    ):
        raise ValueError("Invalid immutable export schema.")
    session = _mapping(wrapper["session"])
    if (
        session["sessionId"] != session_id
        or type(session["revision"]) is not int
        or session["revision"] != profile.revision
        or session["geometryFamilyId"] != gate.geometry_family_id
        or session["manifestFingerprint"] != receipt["historicalManifestFingerprint"]
        or session["manifestFingerprint"] != profile.calibration.manifest_fingerprint
        or session["status"] != "active"
    ):
        raise ValueError("Immutable export provenance differs from the accepted profile.")
    annotations = _annotations(session, _text(gate.geometry_family_id))
    calibration = calibrate_v7_label_geometry(
        annotations,
        manifest_fingerprint=_text(session["manifestFingerprint"]),
        geometry_family_id=_text(session["geometryFamilyId"]),
    )
    if calibration.as_dict() != profile.calibration.as_dict():
        raise ValueError("Immutable annotations do not reproduce the accepted calibration.")


def _annotations(session: dict[str, object], family: str) -> tuple[V7LabelGeometryAnnotation, ...]:
    sources: dict[str, dict[str, object]] = {}
    for source in _objects(session["sources"]):
        identity = _text(source["sourceId"])
        require_sha256(_text(source["sourceChecksumSha256"]))
        if (
            identity in sources
            or source["split"] != "calibration"
            or source["geometryFamilyId"] != family
        ):
            raise ValueError("Invalid immutable calibration source identity.")
        sources[identity] = source
    groups: dict[str, str] = {}
    for group in _objects(session["captureGroups"]):
        identity = _text(group["sourceId"])
        if identity not in sources or identity in groups:
            raise ValueError("Invalid immutable capture group identity.")
        groups[identity] = _text(group["captureGroupId"])
    result: list[V7LabelGeometryAnnotation] = []
    slots: set[tuple[str, int]] = set()
    for slot in _objects(session["slots"]):
        identity = _text(slot["sourceId"])
        index = slot["positionIndex"]
        if type(index) is not int or not 0 <= index < 9 or identity not in sources:
            raise ValueError("Invalid immutable slot identity.")
        key = (identity, index)
        if key in slots:
            raise ValueError("Duplicate immutable slot identity.")
        slots.add(key)
        if (
            slot["state"] != "annotated"
            or slot["cropAssessment"] != "contained"
            or identity not in groups
        ):
            continue
        source = sources[identity]
        result.append(
            V7LabelGeometryAnnotation(
                source_id=identity,
                source_checksum_sha256=_text(source["sourceChecksumSha256"]),
                split=V7CorpusSplit.CALIBRATION,
                position_index=index,
                center_x=_number(slot["centerX"]),
                center_y=_number(slot["centerY"]),
                geometry_family_id=family,
                capture_group_id=groups[identity],
                crop_assessment=V7CropAssessment.CONTAINED,
            )
        )
    if len(slots) != len(sources) * 9:
        raise ValueError("Immutable export lacks the complete slot metadata.")
    return tuple(result)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Expected immutable metadata object.")
    return cast(dict[str, object], value)


def _objects(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        raise ValueError("Expected immutable metadata list.")
    return tuple(_mapping(item) for item in value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected nonempty immutable text.")
    return value


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Expected immutable coordinate.")
    return float(cast(int | float, value))
