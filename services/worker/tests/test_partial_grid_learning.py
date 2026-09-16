from __future__ import annotations

import json

import pytest
from game_predictor_worker.images.partial_grid_learning import (
    PartialGridLearningError,
    PartialGridTrainingProfile,
    build_partial_grid_training_profile,
)


def _qualification(mask: tuple[int, ...], *, included: bool = True) -> dict[str, object]:
    return {
        "version": "manual-geometry-qualification-v2",
        "completenessStatus": "pending_partial",
        "unavailableCellIndices": list(mask),
        "excludeFromGeometryTraining": True,
        "includeInPartialGridTraining": included,
        "exclusionReason": "missing_pixels",
    }


def _entry(*qualifications: dict[str, object]) -> dict[str, object]:
    return {"slotQualifications": list(qualifications)}


def test_profile_requires_three_distinct_sources_and_deduplicates_source_support() -> None:
    left = (0, 5, 10)
    profile = build_partial_grid_training_profile(
        {
            "a" * 64: _entry(_qualification(left), _qualification(left)),
            "b" * 64: _entry(_qualification(left)),
        }
    )
    assert profile is not None
    assert profile.sample_count == 3
    assert profile.source_count == 2
    assert profile.ready_pattern_count == 0
    assert profile.select_mask((left,)) is None

    ready = build_partial_grid_training_profile(
        {
            "a" * 64: _entry(_qualification(left), _qualification(left)),
            "b" * 64: _entry(_qualification(left)),
            "c" * 64: _entry(_qualification(left)),
        }
    )
    assert ready is not None
    assert ready.ready_pattern_count == 1
    assert ready.select_mask((left, (4, 9, 14))) == left


def test_profile_ignores_v1_opt_out_and_non_lateral_masks() -> None:
    v1 = _qualification((0, 5, 10)) | {"version": "manual-geometry-qualification-v1"}
    assert (
        build_partial_grid_training_profile(
            {
                "a" * 64: _entry(v1),
                "b" * 64: _entry(_qualification((0, 5, 10), included=False)),
                "c" * 64: _entry(_qualification((0, 1, 2))),
            }
        )
        is None
    )


def test_profile_roundtrip_is_checksum_bound_and_ties_fail_closed() -> None:
    left = (0, 5, 10)
    right = (4, 9, 14)
    raw = {
        **{character * 64: _entry(_qualification(left)) for character in "abc"},
        **{character * 64: _entry(_qualification(right)) for character in "def"},
    }
    profile = build_partial_grid_training_profile(raw)
    assert profile is not None
    replay = PartialGridTrainingProfile.from_payload(json.loads(json.dumps(profile.to_payload())))
    assert replay == profile
    assert replay.select_mask((left, right)) is None
    drifted = replay.to_payload()
    drifted["sampleCount"] = 99
    with pytest.raises(PartialGridLearningError):
        PartialGridTrainingProfile.from_payload(drifted)
