from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryProfileWithEvidence,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationOutcome,
    build_global_geometry_qualification_report,
    evaluate_global_geometry_candidate,
    qualification_command_sha256,
    qualification_result_checksum_sha256,
    report_from_mapping,
)


def _stored_candidate(
    *, evidence_count: int = 1
) -> GlobalGeometryProfileWithEvidence:
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    candidate = build_global_geometry_candidate(
        geometry_family=SUPPORTED_GEOMETRY_FAMILY,
        topology=topology,
        normalized_template={
            "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
            "topology": topology.to_dict(),
            "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "aspectRatioRange": {"minimum": 0.5, "maximum": 2.0},
        },
        frame_appearance={
            "schemaVersion": FRAME_APPEARANCE_SCHEMA_VERSION,
            "sides": {
                "top": {
                    "clusters": [{"lab": [44.0, 12.0, -8.0], "hsv": [23.0, 0.5, 0.7]}],
                    "contrast": {"minimum": 0.2, "median": 0.4, "maximum": 0.8},
                    "continuity": 0.9,
                }
            },
        },
        evidence_summary={
            "schemaVersion": EVIDENCE_SUMMARY_SCHEMA_VERSION,
            "fullSourceCount": evidence_count,
            "partialSourceCount": 0,
            "sourceGameRefs": ["mummies"],
            "extractorVersion": "shape-geometry-v2-core-v1",
            "qualityMetrics": {"candidateCount": 1},
        },
        evidence=[
            (
                "mummies",
                {
                    "schemaVersion": GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
                    "coverageKind": "full",
                    "visibleFrameSides": ["top", "right", "bottom", "left"],
                    "extractorVersion": "shape-geometry-v2-core-v1",
                    "metrics": {"frameSupport": 0.91 + index / 100.0},
                },
            )
            for index in range(evidence_count)
        ],
    )
    return GlobalGeometryProfileWithEvidence(
        profile=GlobalGeometryProfileVersion(
            id=uuid4(),
            profile_number=7,
            status=GlobalGeometryProfileStatus.CANDIDATE,
            geometry_family=candidate.geometry_family,
            topology=candidate.topology,
            normalized_template=candidate.normalized_template,
            frame_appearance=candidate.frame_appearance,
            evidence_summary=candidate.evidence_summary,
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            created_at=datetime(2026, 9, 21, tzinfo=UTC),
        ),
        evidence=candidate.evidence,
    )


def _report(
    candidate: GlobalGeometryProfileWithEvidence,
    **overrides: object,
):
    values: dict[str, object] = {
        "candidate_profile_checksum_sha256": candidate.profile.profile_checksum_sha256,
        "baseline_active_profile_checksum_sha256": None,
        "replay_snapshot_checksum_sha256": "a" * 64,
        "regression_snapshot_checksum_sha256": "b" * 64,
        "transfer_snapshot_checksum_sha256": "c" * 64,
        "contributor_game_refs": ["mummies"],
        "transfer_target_game_ref": "gang",
        "replay_expected_source_count": 2,
        "replay_evaluated_source_count": 2,
        "replay_automatic_incorrect_source_count": 0,
        "regression_expected_source_count": 2,
        "regression_evaluated_source_count": 2,
        "regression_baseline_automatic_incorrect_source_count": 0,
        "regression_candidate_automatic_incorrect_source_count": 0,
        "transfer_expected_source_count": 2,
        "transfer_evaluated_source_count": 2,
        "transfer_automatic_incorrect_source_count": 0,
    }
    values.update(overrides)
    return build_global_geometry_qualification_report(**values)  # type: ignore[arg-type]


def test_complete_non_regressing_cross_game_report_passes() -> None:
    candidate = _stored_candidate()

    decision = evaluate_global_geometry_candidate(
        stored=candidate,
        report=_report(candidate),
        current_active_profile_checksum_sha256=None,
    )

    assert decision.outcome is GlobalGeometryQualificationOutcome.PASSED
    assert decision.reason_codes == ()


def test_multiple_evidence_samples_from_one_game_match_one_contributor_reference() -> None:
    candidate = _stored_candidate(evidence_count=2)

    decision = evaluate_global_geometry_candidate(
        stored=candidate,
        report=_report(candidate),
        current_active_profile_checksum_sha256=None,
    )

    assert decision.outcome is GlobalGeometryQualificationOutcome.PASSED


@pytest.mark.parametrize(
    ("report_overrides", "expected_outcome", "expected_code"),
    [
        (
            {"replay_evaluated_source_count": 1},
            GlobalGeometryQualificationOutcome.NOT_EVALUABLE,
            "GLOBAL_GEOMETRY_QUALIFICATION_REPLAY_INCOMPLETE",
        ),
        (
            {"transfer_target_game_ref": "mummies"},
            GlobalGeometryQualificationOutcome.REJECTED,
            "GLOBAL_GEOMETRY_QUALIFICATION_TRANSFER_TARGET_LEAKAGE",
        ),
        (
            {"regression_candidate_automatic_incorrect_source_count": 1},
            GlobalGeometryQualificationOutcome.REJECTED,
            "GLOBAL_GEOMETRY_QUALIFICATION_REGRESSION",
        ),
        (
            {"candidate_profile_checksum_sha256": "d" * 64},
            GlobalGeometryQualificationOutcome.REJECTED,
            "GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_CHECKSUM_MISMATCH",
        ),
    ],
)
def test_incomplete_or_unsafe_report_fails_closed(
    report_overrides: dict[str, object],
    expected_outcome: GlobalGeometryQualificationOutcome,
    expected_code: str,
) -> None:
    candidate = _stored_candidate()

    decision = evaluate_global_geometry_candidate(
        stored=candidate,
        report=_report(candidate, **report_overrides),
        current_active_profile_checksum_sha256=None,
    )

    assert decision.outcome is expected_outcome
    assert expected_code in decision.reason_codes


def test_missing_report_and_stale_active_baseline_remain_not_evaluable() -> None:
    candidate = _stored_candidate()

    missing = evaluate_global_geometry_candidate(
        stored=candidate,
        report=None,
        current_active_profile_checksum_sha256=None,
    )
    stale = evaluate_global_geometry_candidate(
        stored=candidate,
        report=_report(candidate, baseline_active_profile_checksum_sha256="e" * 64),
        current_active_profile_checksum_sha256=None,
    )

    assert missing.outcome is GlobalGeometryQualificationOutcome.NOT_EVALUABLE
    assert missing.reason_codes == ("GLOBAL_GEOMETRY_QUALIFICATION_REPORT_MISSING",)
    assert stale.outcome is GlobalGeometryQualificationOutcome.NOT_EVALUABLE
    assert stale.reason_codes == ("GLOBAL_GEOMETRY_QUALIFICATION_BASELINE_STALE",)


@pytest.mark.parametrize(
    "counter_overrides",
    [
        {"replay_evaluated_source_count": 1, "replay_automatic_incorrect_source_count": 2},
        {
            "regression_evaluated_source_count": 1,
            "regression_baseline_automatic_incorrect_source_count": 2,
        },
        {
            "transfer_evaluated_source_count": 1,
            "transfer_automatic_incorrect_source_count": 2,
        },
    ],
)
def test_report_rejects_impossible_incorrect_source_counts(
    counter_overrides: dict[str, object],
) -> None:
    candidate = _stored_candidate()

    with pytest.raises(GlobalGeometryLibraryError) as error:
        _report(candidate, **counter_overrides)

    assert error.value.code == "GLOBAL_GEOMETRY_QUALIFICATION_COUNTER_INVALID"


def test_report_round_trip_and_command_checksums_are_deterministic() -> None:
    candidate = _stored_candidate()
    report = _report(candidate)
    restored = report_from_mapping(report.as_dict())
    decision = evaluate_global_geometry_candidate(
        stored=candidate,
        report=report,
        current_active_profile_checksum_sha256=None,
    )

    assert restored == report
    assert qualification_command_sha256(profile_id=candidate.profile.id, report=report) == (
        qualification_command_sha256(profile_id=candidate.profile.id, report=restored)
    )
    assert qualification_result_checksum_sha256(
        profile_checksum_sha256=candidate.profile.profile_checksum_sha256,
        previous_active_profile_checksum_sha256=None,
        decision=decision,
        report=report,
    ) == qualification_result_checksum_sha256(
        profile_checksum_sha256=candidate.profile.profile_checksum_sha256,
        previous_active_profile_checksum_sha256=None,
        decision=decision,
        report=restored,
    )
