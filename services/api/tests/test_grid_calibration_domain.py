from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from game_predictor_api.domain.grid_calibration import (
    VerifiedGeometrySample,
    build_geometry_manifest,
    profile_checksum,
    train_grid_profile,
)

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _sample(checksum: str, *, offset: float, run_id=None) -> VerifiedGeometrySample:
    detected = ((10.0, 10.0), (90.0, 10.0), (90.0, 90.0), (10.0, 90.0))
    final = tuple((x + offset, y + offset) for x, y in detected)
    return VerifiedGeometrySample(
        board_id=uuid4(),
        review_item_id=uuid4(),
        source_image_id=uuid4(),
        source_checksum_sha256=checksum,
        image_selection_run_id=run_id or uuid4(),
        position_index=0,
        image_width=100,
        image_height=100,
        geometry_revision=1,
        resolution_revision=1,
        detected_quad=detected,
        final_quad=final,  # type: ignore[arg-type]
    )


def test_manifest_split_is_source_disjoint_and_candidate_improves_validation() -> None:
    game_id = uuid4()
    run_id = uuid4()
    training = _sample("0" * 64, offset=5.0, run_id=run_id)
    validation = _sample("f" * 64, offset=5.0, run_id=run_id)

    manifest, checksum = build_geometry_manifest(game_id, (validation, training))
    profile, metrics, reasons = train_grid_profile(manifest)

    rows = manifest["samples"]
    assert isinstance(rows, list)
    by_source = {row["sourceChecksumSha256"]: row["split"] for row in rows}
    assert by_source == {"0" * 64: "training", "f" * 64: "validation"}
    assert metrics["passed"] is True
    assert reasons == ()
    assert profile["cohortChecksumSha256"] == checksum
    assert len(profile_checksum(profile)) == 64
    baseline = metrics["baseline"]
    candidate = metrics["candidate"]
    assert isinstance(baseline, dict) and isinstance(candidate, dict)
    assert candidate["meanNormalizedCornerError"] < baseline["meanNormalizedCornerError"]


def test_profile_is_rejected_without_an_independent_validation_source() -> None:
    manifest, _checksum = build_geometry_manifest(uuid4(), (_sample("0" * 64, offset=2.0),))

    _profile, metrics, reasons = train_grid_profile(manifest)

    assert metrics["passed"] is False
    assert "INSUFFICIENT_SOURCE_IMAGE_COVERAGE" in reasons
    assert "VALIDATION_SET_EMPTY" in reasons


def test_direct_import_without_selection_run_uses_position_fallback() -> None:
    training = replace(_sample("0" * 64, offset=4.0), image_selection_run_id=None)
    validation = replace(_sample("f" * 64, offset=4.0), image_selection_run_id=None)

    manifest, _checksum = build_geometry_manifest(uuid4(), (training, validation))
    profile, metrics, reasons = train_grid_profile(manifest)

    rows = manifest["samples"]
    assert isinstance(rows, list)
    assert all(row["imageSelectionRunId"] is None for row in rows)
    assert profile["scopes"] == []
    assert len(profile["positionFallbacks"]) == 1
    assert metrics["passed"] is True
    assert reasons == ()
