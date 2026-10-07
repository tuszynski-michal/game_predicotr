from __future__ import annotations

import pytest
from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationApiError,
    read_immutable_v7_geometry_profile,
)
from test_v7_label_geometry_calibration_api import _complete_calibration_session, _service


def test_public_immutable_loader_never_recovers_or_mutates_session_runtime(tmp_path):
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    profiles = tmp_path / "runtime" / "v7-label-geometry" / "profiles"
    abandoned = profiles / ".abandoned-profile.part"
    abandoned.write_bytes(b"incomplete foreign state")

    def snapshot():
        return {
            str(path.relative_to(tmp_path)): (path.read_bytes(), path.stat().st_mtime_ns)
            for path in tmp_path.rglob("*")
            if path.is_file()
        }

    before = snapshot()
    assert (
        read_immutable_v7_geometry_profile(profiles, profile.profile.profile_fingerprint) == profile
    )
    assert snapshot() == before
    missing = tmp_path / "missing" / "profiles"
    with pytest.raises(V7LabelGeometryCalibrationApiError):
        read_immutable_v7_geometry_profile(missing, "a" * 64)
    assert not missing.parent.exists()
