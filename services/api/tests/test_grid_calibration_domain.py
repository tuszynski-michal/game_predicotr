import hashlib
import json
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


def _gate_report(
    cohort_checksum: str,
    *,
    active_board_count: int = 900,
    final_ready: int = 890,
    baseline_ready: int = 890,
) -> dict[str, object]:
    base_count, remainder = divmod(active_board_count, 100)
    sources = [
        {
            "sourceChecksumSha256": hashlib.sha256(f"gate-{index}".encode()).hexdigest(),
            "qualityAngleBucket": f"bucket-{index % 5}",
            "activeBoardCount": base_count + (1 if index < remainder else 0),
        }
        for index in range(100)
    ]
    sources.sort(key=lambda item: item["sourceChecksumSha256"])
    corpus = {"schemaVersion": 1, "sources": sources}
    corpus_checksum = hashlib.sha256(
        json.dumps(corpus, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
            "ascii"
        )
    ).hexdigest()
    return {
        "schemaVersion": "grid-profile-end-to-end-gate-report-v1",
        "policyVersion": "v0.10-page-and-cell-production-gate-v1",
        "cohortChecksumSha256": cohort_checksum,
        "corpusChecksumSha256": corpus_checksum,
        "sourceCount": 100,
        "activeBoardCount": active_board_count,
        "pageRegistrationReadyBoardCount": active_board_count,
        "finalCellGridReadyBoardCount": final_ready,
        "baselineFinalCellGridReadyBoardCount": baseline_ready,
        "qualityAngleBucketCounts": {f"bucket-{index}": 20 for index in range(5)},
        "invariantViolationCounts": {
            "checksum": 0,
            "ordering": 0,
            "topology": 0,
            "overlap": 0,
            "sourceSupport": 0,
        },
        "deferralReasonCounts": {"incomplete_lattice": active_board_count - final_ready},
        "knownRegressionCaseCount": 2,
        "coveredRegressionCaseCount": 2,
        "regressionCorpusVersion": "grid-regressions-v1",
        "sources": sources,
    }


def _sample(
    checksum: str,
    *,
    offset: float,
    position: int = 0,
    run_id=None,
) -> VerifiedGeometrySample:
    row, column = divmod(position, 3)
    left = 5.0 + column * 31.0
    top = 5.0 + row * 31.0
    detected = (
        (left, top),
        (left + 25.0, top + 1.0),
        (left + 24.0, top + 25.0),
        (left + 1.0, top + 24.0),
    )
    final = tuple((x + offset, y + offset) for x, y in detected)
    return VerifiedGeometrySample(
        board_id=uuid4(),
        review_item_id=uuid4(),
        source_image_id=uuid4(),
        source_checksum_sha256=checksum,
        image_selection_run_id=run_id or uuid4(),
        position_index=position,
        image_width=100,
        image_height=100,
        geometry_revision=1,
        resolution_revision=1,
        detected_quad=detected,
        final_quad=final,  # type: ignore[arg-type]
    )


def _page(checksum: str, *, offset: float, run_id=None) -> tuple[VerifiedGeometrySample, ...]:
    source_id = uuid4()
    samples = tuple(
        replace(
            _sample(checksum, offset=offset, position=position, run_id=run_id),
            source_image_id=source_id,
        )
        for position in range(9)
    )
    return samples


def test_manifest_split_is_source_disjoint_and_candidate_improves_validation() -> None:
    game_id = uuid4()
    run_id = uuid4()
    training = _page("0" * 64, offset=5.0, run_id=run_id)
    second_training = _page("8" * 64, offset=3.0, run_id=run_id)
    validation = _page("f" * 64, offset=5.0, run_id=run_id)

    manifest, checksum = build_geometry_manifest(game_id, validation + training + second_training)
    profile, metrics, reasons = train_grid_profile(
        manifest,
        end_to_end_report=_gate_report(checksum),
    )

    rows = manifest["samples"]
    assert isinstance(rows, list)
    by_source = {row["sourceChecksumSha256"]: row["split"] for row in rows}
    assert by_source == {
        "0" * 64: "training",
        "8" * 64: "training",
        "f" * 64: "validation",
    }
    assert manifest["schemaVersion"] == 2
    assert metrics["passed"] is True
    assert reasons == ()
    assert profile["cohortChecksumSha256"] == checksum
    assert profile["calibrationPolicy"] == "source-specific-36-corner-registration-v2"
    assert profile["cornerCountPerSource"] == 36
    assert set(profile["anchorSourceChecksums"]) == {"0" * 64, "8" * 64}
    assert "f" * 64 not in profile["anchorSourceChecksums"]
    assert profile["scopes"] == []
    assert profile["positionFallbacks"] == []
    assert len(profile_checksum(profile)) == 64
    assert metrics["trainingCornerCount"] == 72
    assert metrics["validationCornerCount"] == 36
    assert metrics["runtimeFailClosed"] is True


def test_profile_is_rejected_without_an_independent_validation_source() -> None:
    manifest, _checksum = build_geometry_manifest(uuid4(), _page("0" * 64, offset=2.0))

    _profile, metrics, reasons = train_grid_profile(manifest)

    assert metrics["passed"] is False
    assert "INSUFFICIENT_COMPLETE_SOURCE_COVERAGE" in reasons
    assert "TRAINING_SOURCE_SET_INSUFFICIENT" in reasons
    assert "VALIDATION_SOURCE_SET_EMPTY" in reasons


def test_direct_import_without_selection_run_uses_position_fallback() -> None:
    training = tuple(
        replace(sample, image_selection_run_id=None) for sample in _page("0" * 64, offset=4.0)
    )
    second_training = tuple(
        replace(sample, image_selection_run_id=None) for sample in _page("8" * 64, offset=2.0)
    )
    validation = tuple(
        replace(sample, image_selection_run_id=None) for sample in _page("f" * 64, offset=4.0)
    )

    manifest, checksum = build_geometry_manifest(uuid4(), training + second_training + validation)
    profile, metrics, reasons = train_grid_profile(
        manifest,
        end_to_end_report=_gate_report(checksum),
    )

    rows = manifest["samples"]
    assert isinstance(rows, list)
    assert all(row["imageSelectionRunId"] is None for row in rows)
    assert profile["scopes"] == []
    assert profile["positionFallbacks"] == []
    assert len(profile["anchorSourceChecksums"]) == 2
    assert metrics["passed"] is True
    assert reasons == ()


def test_incomplete_source_never_becomes_a_36_corner_anchor() -> None:
    complete_training = _page("0" * 64, offset=2.0)
    complete_training_2 = _page("8" * 64, offset=3.0)
    validation = _page("f" * 64, offset=1.0)
    incomplete = _page("7" * 64, offset=6.0)[:-1]

    manifest, checksum = build_geometry_manifest(
        uuid4(), complete_training + complete_training_2 + validation + incomplete
    )
    profile, metrics, reasons = train_grid_profile(
        manifest,
        end_to_end_report=_gate_report(checksum),
    )

    assert reasons == ()
    assert "7" * 64 not in profile["anchorSourceChecksums"]
    assert metrics["incompleteSourceCount"] == 1


def test_legacy_manifest_keeps_the_offset_profile_replay_contract() -> None:
    run_id = uuid4()
    manifest, _checksum = build_geometry_manifest(
        uuid4(),
        (
            _sample("0" * 64, offset=5.0, run_id=run_id),
            _sample("f" * 64, offset=5.0, run_id=run_id),
        ),
    )
    manifest["schemaVersion"] = 1

    profile, metrics, reasons = train_grid_profile(manifest)

    assert profile["calibrationPolicy"] == "robust-normalized-corner-offset-v1"
    assert len(profile["scopes"]) == 1
    assert metrics["passed"] is True
    assert reasons == ()


def test_v2_profile_without_end_to_end_report_is_not_ready() -> None:
    manifest, _checksum = build_geometry_manifest(
        uuid4(),
        _page("0" * 64, offset=1.0)
        + _page("8" * 64, offset=1.0)
        + _page("f" * 64, offset=1.0),
    )

    profile, metrics, reasons = train_grid_profile(manifest)

    assert "END_TO_END_GATE_REPORT_REQUIRED" in reasons
    assert metrics["endToEndGateReportPresent"] is False
    assert metrics["passed"] is False
    assert "endToEndGateReportChecksumSha256" not in profile


def test_complete_36_corner_candidate_with_two_of_19800_final_grids_is_rejected() -> None:
    manifest, checksum = build_geometry_manifest(
        uuid4(),
        _page("0" * 64, offset=1.0)
        + _page("8" * 64, offset=1.0)
        + _page("f" * 64, offset=1.0),
    )

    _profile, metrics, reasons = train_grid_profile(
        manifest,
        end_to_end_report=_gate_report(
            checksum,
            active_board_count=19_800,
            final_ready=2,
            baseline_ready=19_800,
        ),
    )

    assert metrics["finalCellGridReadyRate"] == 2 / 19_800
    assert "END_TO_END_FINAL_CELL_GRID_RATE_BELOW_THRESHOLD" in reasons
    assert "END_TO_END_FINAL_CELL_GRID_REGRESSION" in reasons
    assert metrics["passed"] is False
