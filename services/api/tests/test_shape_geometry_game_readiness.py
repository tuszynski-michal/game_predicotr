from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from game_predictor_api.domain.catalog import (
    GameShapeGeometryConfiguration,
    ShapeGeometryReadinessStatus,
)
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
from game_predictor_api.storage.global_shape_geometry_readiness import (
    GlobalShapeGeometryReadinessResolver,
)


class _Profiles:
    def __init__(self, profiles: tuple[GlobalGeometryProfileWithEvidence, ...]) -> None:
        self.profiles = profiles
        self.calls: list[str] = []

    def list_active_profiles_with_evidence(
        self, *, geometry_family: str
    ) -> tuple[GlobalGeometryProfileWithEvidence, ...]:
        self.calls.append(geometry_family)
        return self.profiles


class _UnreadableProfiles:
    def list_active_profiles_with_evidence(
        self, *, geometry_family: str
    ) -> tuple[GlobalGeometryProfileWithEvidence, ...]:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_PROFILE_INVALID", "bad descriptor"
        )


def _profile(
    *, status: GlobalGeometryProfileStatus = GlobalGeometryProfileStatus.ACTIVE,
    number: int = 7,
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
    return GlobalGeometryProfileWithEvidence(
        profile=GlobalGeometryProfileVersion(
            id=uuid4(),
            profile_number=number,
            status=status,
            geometry_family=candidate.geometry_family,
            topology=candidate.topology,
            normalized_template=candidate.normalized_template,
            frame_appearance=candidate.frame_appearance,
            evidence_summary=candidate.evidence_summary,
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            created_at=datetime.now(UTC),
        ),
        evidence=candidate.evidence,
    )


def test_clarification_is_explicit_and_does_not_read_the_shared_library() -> None:
    repository = _Profiles((_profile(),))

    readiness = GlobalShapeGeometryReadinessResolver(repository).resolve(None)

    assert readiness.configuration is GameShapeGeometryConfiguration.REQUIRES_CLARIFICATION
    assert readiness.status is ShapeGeometryReadinessStatus.REQUIRES_CLARIFICATION
    assert readiness.reason_code == "SHAPE_GEOMETRY_CONFIGURATION_REQUIRED"
    assert readiness.shared_profile is None
    assert repository.calls == []


def test_framed_page_with_one_integral_shared_profile_is_ready_for_preflight() -> None:
    stored = _profile()
    repository = _Profiles((stored,))

    readiness = GlobalShapeGeometryReadinessResolver(repository).resolve(
        GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2
    )

    assert readiness.status is ShapeGeometryReadinessStatus.READY_FOR_SHARED_PREFLIGHT
    assert readiness.reason_code == "SHAPE_GEOMETRY_V2_SHARED_PROFILE_READY"
    assert readiness.shared_profile is not None
    assert readiness.shared_profile.profile_id == stored.profile.id
    assert readiness.shared_profile.profile_number == stored.profile.profile_number
    assert readiness.shared_profile.profile_checksum_sha256 == (
        stored.profile.profile_checksum_sha256
    )
    assert repository.calls == [SUPPORTED_GEOMETRY_FAMILY]


def test_framed_page_requires_manual_review_when_profile_is_missing_invalid_or_conflicted() -> None:
    invalid = _profile()
    invalid = replace(
        invalid,
        profile=replace(invalid.profile, profile_checksum_sha256="a" * 64),
    )
    cases = (
        ((), "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_REQUIRED"),
        ((invalid,), "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID"),
        ((_profile(number=7), _profile(number=8)), "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_CONFLICT"),
    )

    for profiles, reason_code in cases:
        readiness = GlobalShapeGeometryReadinessResolver(_Profiles(profiles)).resolve(
            GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2
        )

        assert readiness.status is ShapeGeometryReadinessStatus.MANUAL_REVIEW_REQUIRED
        assert readiness.reason_code == reason_code
    assert readiness.shared_profile is None


def test_framed_page_never_uses_candidate_rejected_or_retired_profile() -> None:
    statuses = (
        GlobalGeometryProfileStatus.CANDIDATE,
        GlobalGeometryProfileStatus.REJECTED,
        GlobalGeometryProfileStatus.RETIRED,
    )

    for status in statuses:
        resolver = GlobalShapeGeometryReadinessResolver(
            _Profiles((_profile(status=status),))
        )
        readiness = resolver.resolve(
            GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2
        )

        assert readiness.status is ShapeGeometryReadinessStatus.MANUAL_REVIEW_REQUIRED
        assert readiness.reason_code == "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_REQUIRED"
        assert readiness.shared_profile is None


def test_framed_page_fails_closed_when_profile_repository_rejects_a_descriptor() -> None:
    readiness = GlobalShapeGeometryReadinessResolver(_UnreadableProfiles()).resolve(
        GameShapeGeometryConfiguration.FRAMED_FULL_PAGE_V2
    )

    assert readiness.status is ShapeGeometryReadinessStatus.MANUAL_REVIEW_REQUIRED
    assert readiness.reason_code == "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID"
    assert readiness.shared_profile is None
