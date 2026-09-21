from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileVersion,
    GlobalGeometryProfileWithEvidence,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.global_geometry_profile_snapshot_resolver import (
    SqlAlchemyGlobalGeometryProfileSnapshotResolver,
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


def test_resolver_pins_one_integral_active_profile_without_game_routing() -> None:
    stored = _profile()
    repository = _Profiles((stored,))

    payload = SqlAlchemyGlobalGeometryProfileSnapshotResolver(repository).resolve()

    assert payload is not None
    assert payload["profileId"] == str(stored.profile.id)
    assert payload["profileNumber"] == 7
    assert payload["profileChecksumSha256"] == stored.profile.profile_checksum_sha256
    assert len(str(payload["profileDescriptorChecksumSha256"])) == 64
    assert payload["localVerification"] == {
        "schemaVersion": "shape-geometry-v2-local-policy-v1",
        "colorCompatibility": "structural_only",
    }
    assert "gameId" not in payload
    assert repository.calls == [SUPPORTED_GEOMETRY_FAMILY]


@pytest.mark.parametrize(
    "status",
    [
        GlobalGeometryProfileStatus.CANDIDATE,
        GlobalGeometryProfileStatus.REJECTED,
        GlobalGeometryProfileStatus.RETIRED,
    ],
)
def test_resolver_never_uses_an_inactive_profile(status: GlobalGeometryProfileStatus) -> None:
    resolver = SqlAlchemyGlobalGeometryProfileSnapshotResolver(
        _Profiles((_profile(status=status),))
    )
    assert resolver.resolve() is None


def test_resolver_rejects_multiple_active_profiles() -> None:
    resolver = SqlAlchemyGlobalGeometryProfileSnapshotResolver(
        _Profiles((_profile(number=8), _profile(number=7)))
    )

    with pytest.raises(JobConflictError) as error:
        resolver.resolve()

    assert error.value.code == "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_CONFLICT"


def test_resolver_fails_closed_for_an_invalid_active_descriptor() -> None:
    stored = _profile()
    invalid = replace(
        stored,
        profile=replace(stored.profile, normalized_template={"unexpected": "descriptor"}),
    )
    resolver = SqlAlchemyGlobalGeometryProfileSnapshotResolver(_Profiles((invalid,)))

    with pytest.raises(JobConflictError) as error:
        resolver.resolve()

    assert error.value.code == "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID"


def test_resolver_fails_closed_when_persisted_profile_checksum_is_not_its_evidence() -> None:
    stored = _profile()
    tampered = replace(
        stored,
        profile=replace(stored.profile, profile_checksum_sha256="a" * 64),
    )

    with pytest.raises(JobConflictError) as error:
        SqlAlchemyGlobalGeometryProfileSnapshotResolver(_Profiles((tampered,))).resolve()

    assert error.value.code == "SHAPE_GEOMETRY_V2_ACTIVE_PROFILE_INVALID"
