"""Immutable export/runtime drift must fail before OCR and writable delivery."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from game_predictor_api.domain.v7_selection_delivery import V7PilotGate
from game_predictor_worker.semi_automatic_selection import v7_pilot_attestation as attestation
from test_v7_label_geometry_calibration_api import _complete_calibration_session, _service


@pytest.mark.parametrize(
    "drift", ["none", "bytes", "runtime", "session", "revision", "manifest", "profile_export"]
)
def test_export_and_installed_runtime_are_revalidated_without_store_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    record = service.create_profile(session.session_id, expected_revision=session.revision)
    runtime = tmp_path / "runtime"
    export = next(
        (runtime / "v7-label-geometry" / "sessions" / session.session_id / "exports").glob("*.json")
    )
    payload: dict[str, object] = {
        "ocrRuntimeIdentity": {"name": "paddlepaddle-cpu", "version": "installed"},
        "calibrationSessionId": session.session_id,
        "sessionExportChecksumSha256": record.session_export_checksum_sha256,
        "historicalManifestFingerprint": record.profile.calibration.manifest_fingerprint,
    }
    monkeypatch.setattr(attestation, "version", lambda name: "installed")
    profile = record.profile
    checksum = record.session_export_checksum_sha256
    if drift == "bytes":
        export.write_bytes(export.read_bytes() + b" ")
    elif drift == "runtime":
        monkeypatch.setattr(attestation, "version", lambda name: "replacement")
    elif drift == "session":
        payload["calibrationSessionId"] = "../outside"
    elif drift == "revision":
        profile = replace(profile, revision=profile.revision + 1)
    elif drift == "manifest":
        payload["historicalManifestFingerprint"] = "0" * 64
    elif drift == "profile_export":
        checksum = "0" * 64
    gate = V7PilotGate(
        geometry_family_id=profile.calibration.geometry_family_id,
        acceptance_receipt=payload,
    )
    # An abandoned writable snapshot must remain untouched by immutable validation.
    temporary = export.parent.parent / "state.json.tmp"
    temporary.write_bytes(b"foreign unrecoverable metadata")
    before = {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in runtime.rglob("*")
        if path.is_file()
    }
    if drift == "none":
        attestation.validate_v7_pilot_attestation(runtime, profile, checksum, gate)
        attestation.validate_v7_pilot_attestation(runtime, profile, checksum, gate)
    else:
        with pytest.raises(ValueError):
            attestation.validate_v7_pilot_attestation(runtime, profile, checksum, gate)
    assert before == {
        str(path): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in runtime.rglob("*")
        if path.is_file()
    }
