import pytest
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_worker.images.page_geometry_preflight import (
    _profile_with_manual_override_anchors,
    _strong_auto_anchor,
)


def test_excluded_slot_prevents_manual_and_auto_page_anchor() -> None:
    checksum = "a" * 64
    complete = GeometryQualification().to_dict()
    excluded = GeometryQualification(
        exclude_from_geometry_training=True, exclusion_reason="manual_exclusion"
    ).to_dict()
    raw = {
        "imageWidth": 300,
        "imageHeight": 200,
        "quads": [[]] * 9,
        "slotQualifications": [complete] * 8 + [excluded],
    }
    result = _profile_with_manual_override_anchors(
        {}, {checksum: raw}, available_checksums={checksum}
    )
    assert result["anchors"] == []
    assert (
        _profile_with_manual_override_anchors(
            {"anchors": [{"sourceChecksumSha256": checksum}]},
            {checksum: raw},
            available_checksums={checksum},
        )["anchors"]
        == []
    )
    raw["slotQualifications"] = [complete] * 9
    assert (
        len(
            _profile_with_manual_override_anchors(
                {}, {checksum: raw}, available_checksums={checksum}
            )["anchors"]
        )
        == 1
    )
    entry = {
        **raw,
        "status": "registered",
        "boardRedEdgeCoverages": [1.0] * 9,
        "inlierCount": 100,
        "inlierRatio": 1.0,
        "p95ReprojectionError": 0.1,
        "meanRedEdgeCoverage": 1.0,
    }
    assert _strong_auto_anchor(entry)
    entry["slotQualifications"] = [complete] * 8 + [excluded]
    assert not _strong_auto_anchor(entry)


@pytest.mark.parametrize("count", [1, 5, 8])
def test_qualified_terminal_page_is_not_a_full_page_anchor(count):
    checksum = "a" * 64
    raw = {
        "imageWidth": 300,
        "imageHeight": 200,
        "quads": [[]] * count,
        "slotQualifications": [GeometryQualification().to_dict()] * count,
    }
    assert (
        _profile_with_manual_override_anchors({}, {checksum: raw}, available_checksums={checksum})[
            "anchors"
        ]
        == []
    )
    assert not _strong_auto_anchor(raw)
