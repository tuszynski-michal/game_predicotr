from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain import lab_symbol_candidate as candidate


@pytest.fixture
def qualified(monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, bytes]:
    model = b"qualified-export-test-fixture"
    payload = {"classes": list(candidate.MUMIE_CLASS_LABELS), "eligible": True}
    checksum = candidate.digest(payload)
    monkeypatch.setattr(candidate, "MUMIE_ELIGIBILITY_ID", checksum)
    monkeypatch.setattr(candidate, "MUMIE_R2_ONNX_SHA256", hashlib.sha256(model).hexdigest())
    return model, candidate.canonical({"payload": payload, "sha256": checksum})


def test_package_is_idempotent_and_preserves_lab_origin(
    tmp_path: Path, qualified: tuple[bytes, bytes]
) -> None:
    model, evidence = qualified
    game_id = uuid4()
    first = candidate.prepare_mumie_candidate(
        tmp_path,
        game_id=game_id,
        onnx_content=model,
        eligibility_content=evidence,
    )
    second = candidate.prepare_mumie_candidate(
        tmp_path,
        game_id=game_id,
        onnx_content=model,
        eligibility_content=evidence,
    )
    assert first == second == candidate.load_lab_symbol_candidate(tmp_path, first.fingerprint)
    identity = first.manifest["identity"]
    assert isinstance(identity, dict)
    assert identity["origin"] == "lab_import"
    assert identity["developmentOrigins"] == {"human": 283, "ai_visual_assessment": 44}
    assert identity["populationAccuracy"] is None
    assert identity["r2CombinedAccepted"] is identity["v5Accepted"] is False


@pytest.mark.parametrize(
    "name", ["model.onnx", "classes.json", "calibration.json", "eligibility.json"]
)
def test_artifact_drift_is_rejected(
    tmp_path: Path, qualified: tuple[bytes, bytes], name: str
) -> None:
    model, evidence = qualified
    first = candidate.prepare_mumie_candidate(
        tmp_path,
        game_id=uuid4(),
        onnx_content=model,
        eligibility_content=evidence,
    )
    path = (tmp_path / first.manifest_relative_path).parent / name
    path.write_bytes(path.read_bytes() + b"x")
    with pytest.raises(ValueError, match="DRIFT"):
        candidate.load_lab_symbol_candidate(tmp_path, first.fingerprint)


def test_resigned_wrong_temperature_is_rejected(
    tmp_path: Path, qualified: tuple[bytes, bytes]
) -> None:
    model, evidence = qualified
    first = candidate.prepare_mumie_candidate(
        tmp_path,
        game_id=uuid4(),
        onnx_content=model,
        eligibility_content=evidence,
    )
    manifest_path = tmp_path / first.manifest_relative_path
    manifest = json.loads(manifest_path.read_bytes())
    manifest["identity"]["temperature"] = 0.01
    new_fingerprint = candidate.digest(manifest["identity"])
    manifest["candidateFingerprint"] = new_fingerprint
    new_directory = manifest_path.parent.parent / new_fingerprint
    new_directory.mkdir()
    (new_directory / "manifest.json").write_bytes(candidate.canonical(manifest))
    with pytest.raises(ValueError, match="ORIGIN_DRIFT"):
        candidate.load_lab_symbol_candidate(tmp_path, new_fingerprint)


@pytest.mark.parametrize("value", ["../model", "A" * 64, "abc", "0" * 63])
def test_unsafe_fingerprint_is_rejected(tmp_path: Path, value: str) -> None:
    with pytest.raises(ValueError, match="FINGERPRINT_INVALID"):
        candidate.load_lab_symbol_candidate(tmp_path, value)


def test_resigned_wrong_eligibility_never_becomes_a_gate_pass(
    tmp_path: Path, qualified: tuple[bytes, bytes]
) -> None:
    model, evidence = qualified
    altered = json.loads(evidence)
    altered["payload"]["eligible"] = False
    altered["sha256"] = candidate.digest(altered["payload"])
    with pytest.raises(ValueError, match="ELIGIBILITY_DRIFT"):
        candidate.prepare_mumie_candidate(
            tmp_path,
            game_id=uuid4(),
            onnx_content=model,
            eligibility_content=candidate.canonical(altered),
        )
