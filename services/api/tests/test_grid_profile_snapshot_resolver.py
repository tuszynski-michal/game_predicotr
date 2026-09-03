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
    payload = {
        "schemaVersion": 2,
        "calibrationPolicy": "source-specific-36-corner-registration-v2",
        "anchorSourceChecksums": selected,
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
