from __future__ import annotations

from game_predictor_worker.images.geometry import Point
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_VERSION,
)

from scripts.evaluate_page_registration_variants import (
    _geometry_error,
    _profile_variant,
    _summary,
    _without_source_anchor,
    build_report,
)


def test_acceptance_profile_is_source_disjoint_and_versions_variants() -> None:
    profile = {
        "policy": PAGE_REGISTRATION_VERSION,
        "anchors": [
            {"sourceChecksumSha256": "a" * 64},
            {"sourceChecksumSha256": "b" * 64},
        ],
    }

    disjoint = _without_source_anchor(profile, "a" * 64)
    standard = _profile_variant(disjoint, masked=False)
    masked = _profile_variant(disjoint, masked=True)

    assert disjoint["anchors"] == [{"sourceChecksumSha256": "b" * 64}]
    assert standard["policy"] == PAGE_REGISTRATION_VERSION
    assert "anchorMaskVersion" not in standard
    assert masked["policy"] == PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION
    assert masked["anchorMaskPaddingRatio"] == 0.1


def test_acceptance_error_and_summary_use_real_corner_distances() -> None:
    reference = ((Point(0, 0), Point(10, 0), Point(10, 10), Point(0, 10)),)
    shifted = ((Point(3, 4), Point(13, 4), Point(13, 14), Point(3, 14)),)

    error = _geometry_error(shifted, reference)
    summary = _summary(
        [
            {
                "candidate": {
                    "geometryError": error,
                    "registered": True,
                    "totalSeconds": 0.25,
                }
            },
            {"candidate": {"registered": False, "totalSeconds": 0.75}},
        ],
        "candidate",
    )

    assert error == {
        "medianCornerErrorPx": 5.0,
        "p95CornerErrorPx": 5.0,
        "maximumBoardMeanCornerErrorPx": 5.0,
    }
    assert summary["registeredSourceCount"] == 1
    assert summary["registrationRate"] == 0.5
    assert summary["medianCornerErrorPx"] == 5.0
    assert summary["medianSecondsPerSource"] == 0.5


def test_acceptance_report_enforces_bounded_limit(tmp_path) -> None:
    try:
        build_report(
            artifact_root=tmp_path,
            database_url="unused",
            game_ids=(),
            limit=51,
            diagnostic_source_checksum=None,
            diagnostic_source_path=None,
        )
    except RuntimeError as error:
        assert str(error) == "--limit must be between 1 and 50."
    else:
        raise AssertionError("An unbounded acceptance run must be rejected.")
