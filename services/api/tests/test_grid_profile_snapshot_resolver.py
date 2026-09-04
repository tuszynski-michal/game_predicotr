from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.models import (
    GridCalibrationProfileModel,
    GridGeometryCohortModel,
)


def test_v2_snapshot_pins_the_exact_selected_36_corner_anchors() -> None:
    game_id = uuid4()
    profile_id = uuid4()
    selected = ["b" * 64, "a" * 64]
    gate_report = {"schemaVersion": "grid-profile-end-to-end-gate-report-v1"}
    gate_report_checksum = hashlib.sha256(
        json.dumps(
            gate_report,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    payload = {
        "schemaVersion": 2,
        "calibrationPolicy": "source-specific-36-corner-registration-v2",
        "anchorSourceChecksums": selected,
        "endToEndGateReportChecksumSha256": gate_report_checksum,
    }
    payload_checksum = hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode(
            "ascii"
        )
    ).hexdigest()
    activation = SimpleNamespace(id=uuid4(), profile_id=profile_id)
    profile = SimpleNamespace(
        id=profile_id,
        game_id=game_id,
        status="candidate_ready",
        profile_number=2,
        profile_payload=payload,
        profile_checksum_sha256=payload_checksum,
        cohort_id=uuid4(),
        gate_metrics={
            "endToEndGatePolicyVersion": "v0.10-page-and-cell-production-gate-v1",
            "endToEndGateReportChecksumSha256": gate_report_checksum,
            "endToEndGateReport": gate_report,
            "passed": True,
        },
    )
    cohort = SimpleNamespace(game_id=game_id, manifest_payload={"schemaVersion": 2})
    session = Mock()
    session.scalar.return_value = activation

    def get(model: object, identity: object) -> object | None:
        if model is GridCalibrationProfileModel and identity == profile_id:
            return profile
        if model is GridGeometryCohortModel and identity == profile.cohort_id:
            return cohort
        return None

    session.get.side_effect = get
    repository = SqlAlchemyGridProfileSnapshotResolver(session)
    registration_profile = {
        "schemaVersion": 2,
        "anchors": [{"sourceChecksumSha256": checksum} for checksum in selected],
    }

    with patch(
        "game_predictor_api.storage.grid_profile_snapshot_resolver."
        "build_verified_page_registration_profile",
        return_value=registration_profile,
    ) as build:
        snapshot = repository.resolve(game_id=game_id)

    build.assert_called_once_with(
        cohort.manifest_payload,
        anchor_source_checksums=tuple(selected),
    )
    assert snapshot["pageRegistrationProfile"] == registration_profile
    assert isinstance(snapshot["inferenceFingerprint"], str)


def test_active_v2_profile_without_current_end_to_end_gate_is_blocked_for_new_jobs() -> None:
    game_id = uuid4()
    profile_id = uuid4()
    activation = SimpleNamespace(id=uuid4(), profile_id=profile_id)
    profile = SimpleNamespace(
        id=profile_id,
        game_id=game_id,
        status="candidate_ready",
        profile_number=2,
        profile_payload={
            "schemaVersion": 2,
            "calibrationPolicy": "source-specific-36-corner-registration-v2",
            "anchorSourceChecksums": ["a" * 64],
        },
        profile_checksum_sha256="b" * 64,
        cohort_id=uuid4(),
        gate_metrics={"passed": True},
    )
    session = Mock()
    session.scalar.return_value = activation
    session.get.return_value = profile

    repository = SqlAlchemyGridProfileSnapshotResolver(session)

    from game_predictor_api.domain.jobs import JobConflictError

    try:
        repository.resolve(game_id=game_id)
    except JobConflictError as error:
        assert error.code == "GRID_PROFILE_END_TO_END_REVALIDATION_REQUIRED"
    else:
        raise AssertionError("The historical v2 gate must not be reused by a new job.")
