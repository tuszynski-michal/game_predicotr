from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.global_geometry_pilot import GlobalGeometryPilotService
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryCandidate,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationOutcome,
    GlobalGeometryQualificationResult,
    build_global_geometry_qualification_report,
)


def _candidate() -> GlobalGeometryCandidate:
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    return build_global_geometry_candidate(
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
            "fullSourceCount": 1,
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
                    "metrics": {"frameSupport": 0.91},
                },
            )
        ],
    )


def _report(candidate: GlobalGeometryCandidate):
    return build_global_geometry_qualification_report(
        candidate_profile_checksum_sha256=candidate.profile_checksum_sha256,
        baseline_active_profile_checksum_sha256="a" * 64,
        replay_snapshot_checksum_sha256="b" * 64,
        regression_snapshot_checksum_sha256="c" * 64,
        transfer_snapshot_checksum_sha256="d" * 64,
        contributor_game_refs=["mummies"],
        transfer_target_game_ref="gang",
        replay_expected_source_count=1,
        replay_evaluated_source_count=1,
        replay_automatic_incorrect_source_count=0,
        regression_expected_source_count=1,
        regression_evaluated_source_count=1,
        regression_baseline_automatic_incorrect_source_count=0,
        regression_candidate_automatic_incorrect_source_count=0,
        transfer_expected_source_count=1,
        transfer_evaluated_source_count=1,
        transfer_automatic_incorrect_source_count=0,
    )


class _Repository:
    def __init__(self, candidate: GlobalGeometryCandidate) -> None:
        self.profile = GlobalGeometryProfileVersion(
            id=uuid4(),
            profile_number=7,
            status=GlobalGeometryProfileStatus.CANDIDATE,
            geometry_family=candidate.geometry_family,
            topology=candidate.topology,
            normalized_template=candidate.normalized_template,
            frame_appearance=candidate.frame_appearance,
            evidence_summary=candidate.evidence_summary,
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            created_at=datetime.now(UTC),
        )
        self.result = GlobalGeometryQualificationResult(
            id=uuid4(),
            profile_id=self.profile.id,
            previous_active_profile_id=None,
            outcome=GlobalGeometryQualificationOutcome.NOT_EVALUABLE,
            reason_codes=("GLOBAL_GEOMETRY_QUALIFICATION_TRANSFER_INCOMPLETE",),
            report=None,
            qualification_checksum_sha256="e" * 64,
            created_at=datetime.now(UTC),
        )
        self.create_calls: list[tuple[GlobalGeometryCandidate, UUID]] = []
        self.qualify_calls: list[tuple[UUID, object, UUID]] = []

    def create_candidate(
        self, *, candidate: GlobalGeometryCandidate, idempotency_key: UUID
    ) -> tuple[GlobalGeometryProfileVersion, bool]:
        self.create_calls.append((candidate, idempotency_key))
        return self.profile, True

    def qualify_candidate(self, *, profile_id: UUID, report: object, idempotency_key: UUID):
        self.qualify_calls.append((profile_id, report, idempotency_key))
        return self.result, True


def test_pilot_service_persists_candidate_then_qualifies_returned_profile() -> None:
    candidate = _candidate()
    report = _report(candidate)
    repository = _Repository(candidate)
    candidate_key = uuid4()
    qualification_key = uuid4()

    publication = GlobalGeometryPilotService(repository).publish(
        candidate=candidate,
        report=report,
        candidate_idempotency_key=candidate_key,
        qualification_idempotency_key=qualification_key,
    )

    assert publication.profile == repository.profile
    assert publication.profile_created is True
    assert publication.qualification == repository.result
    assert publication.qualification_created is True
    assert repository.create_calls == [(candidate, candidate_key)]
    assert repository.qualify_calls == [(repository.profile.id, report, qualification_key)]


def test_pilot_service_requires_distinct_idempotency_keys_before_writing() -> None:
    candidate = _candidate()
    repository = _Repository(candidate)
    key = uuid4()

    with pytest.raises(ValueError, match="must differ"):
        GlobalGeometryPilotService(repository).publish(
            candidate=candidate,
            report=_report(candidate),
            candidate_idempotency_key=key,
            qualification_idempotency_key=key,
        )

    assert repository.create_calls == []
    assert repository.qualify_calls == []
