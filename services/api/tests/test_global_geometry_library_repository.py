from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.global_geometry_library import (
    EVIDENCE_SUMMARY_SCHEMA_VERSION,
    FRAME_APPEARANCE_SCHEMA_VERSION,
    GLOBAL_GEOMETRY_EVIDENCE_SCHEMA_VERSION,
    NORMALIZED_TEMPLATE_SCHEMA_VERSION,
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryLibraryConflictError,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.storage.global_geometry_library_repository import (
    SqlAlchemyGlobalGeometryLibraryRepository,
)
from game_predictor_api.storage.models import GlobalGeometryProfileVersionModel
from sqlalchemy.exc import IntegrityError

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _candidate():
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


def _stored_profile(candidate, *, profile_number: int = 1):
    return SimpleNamespace(
        id=uuid4(),
        profile_number=profile_number,
        status=GlobalGeometryProfileStatus.CANDIDATE.value,
        geometry_family=candidate.geometry_family,
        page_board_rows=candidate.topology.page_board_rows,
        page_board_columns=candidate.topology.page_board_columns,
        board_cell_rows=candidate.topology.board_cell_rows,
        board_cell_columns=candidate.topology.board_cell_columns,
        normalized_template=candidate.normalized_template,
        frame_appearance=candidate.frame_appearance,
        evidence_summary=candidate.evidence_summary,
        profile_checksum_sha256=candidate.profile_checksum_sha256,
        created_at=NOW,
    )


def test_create_candidate_writes_only_global_control_plane_models() -> None:
    candidate = _candidate()
    session = Mock()
    session.scalar.side_effect = [None, None]
    added: list[object] = []

    def add(record: object) -> None:
        added.append(record)
        if isinstance(record, GlobalGeometryProfileVersionModel):
            record.profile_number = 1
            record.created_at = NOW

    session.add.side_effect = add
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    profile, created = repository.create_candidate(
        candidate=candidate, idempotency_key=uuid4()
    )

    assert created is True
    assert profile.profile_number == 1
    assert len(added) == 3
    statement = str(session.scalar.call_args_list[1].args[0])
    assert "global_geometry_profile_versions" in statement
    assert "game_id" not in statement


def test_retry_returns_receipted_profile_without_new_write() -> None:
    candidate = _candidate()
    profile = _stored_profile(candidate)
    receipt = SimpleNamespace(
        profile_id=profile.id,
        command_sha256=candidate.command_sha256(),
    )
    session = Mock()
    session.scalar.return_value = receipt
    session.get.return_value = profile
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    result, created = repository.create_candidate(candidate=candidate, idempotency_key=uuid4())

    assert created is False
    assert result.id == profile.id
    session.add.assert_not_called()


def test_reused_idempotency_key_with_different_command_is_conflict() -> None:
    candidate = _candidate()
    session = Mock()
    session.scalar.return_value = SimpleNamespace(
        profile_id=uuid4(), command_sha256="0" * 64
    )
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    with pytest.raises(GlobalGeometryLibraryConflictError) as error:
        repository.create_candidate(candidate=candidate, idempotency_key=uuid4())

    assert error.value.code == "GLOBAL_GEOMETRY_IDEMPOTENCY_CONFLICT"


def test_existing_checksum_adds_retry_receipt_without_a_second_profile_number() -> None:
    candidate = _candidate()
    existing = _stored_profile(candidate, profile_number=7)
    session = Mock()
    session.scalar.side_effect = [None, existing]
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    profile, created = repository.create_candidate(candidate=candidate, idempotency_key=uuid4())

    assert created is False
    assert profile.profile_number == 7
    assert session.add.call_count == 1


def test_list_profiles_has_stable_global_order_and_never_routes_by_game() -> None:
    candidate = _candidate()
    session = Mock()
    session.scalars.return_value.all.return_value = [
        _stored_profile(candidate, profile_number=4),
        _stored_profile(candidate, profile_number=3),
    ]
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    profiles = repository.list_profiles(geometry_family=SUPPORTED_GEOMETRY_FAMILY, limit=2)

    assert [profile.profile_number for profile in profiles] == [4, 3]
    statement = str(session.scalars.call_args.args[0])
    assert "ORDER BY global_geometry_profile_versions.profile_number DESC" in statement
    assert "game_id" not in statement


def test_list_active_profiles_reads_all_active_versions_with_their_evidence() -> None:
    candidate = _candidate()
    stored = _stored_profile(candidate, profile_number=4)
    stored.status = GlobalGeometryProfileStatus.ACTIVE.value
    evidence = candidate.evidence[0]
    session = Mock()
    session.scalars.side_effect = [
        SimpleNamespace(all=lambda: [stored]),
        SimpleNamespace(
            all=lambda: [
                SimpleNamespace(
                    source_game_ref=evidence.source_game_ref,
                    evidence_checksum_sha256=evidence.evidence_checksum_sha256,
                    evidence_payload=evidence.evidence_payload,
                )
            ]
        ),
    ]
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    records = repository.list_active_profiles_with_evidence(
        geometry_family=SUPPORTED_GEOMETRY_FAMILY
    )

    assert [record.profile.profile_number for record in records] == [4]
    assert records[0].evidence == candidate.evidence
    statement = str(session.scalars.call_args_list[0].args[0])
    assert "status" in statement
    assert "LIMIT" not in statement


def test_repository_revalidates_a_manually_tampered_candidate_before_any_query() -> None:
    candidate = _candidate()
    tampered = replace(
        candidate,
        normalized_template={**candidate.normalized_template, "data": "data:image/png;base64,AAAA"},
    )
    session = Mock()
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    with pytest.raises(GlobalGeometryLibraryError) as error:
        repository.create_candidate(candidate=tampered, idempotency_key=uuid4())

    assert error.value.code == "GLOBAL_GEOMETRY_TEMPLATE_FIELDS_INVALID"
    session.scalar.assert_not_called()


def test_first_profile_flush_conflict_is_translated_to_stable_retry_error() -> None:
    candidate = _candidate()
    session = Mock()
    session.scalar.side_effect = [None, None]
    session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    with pytest.raises(GlobalGeometryLibraryConflictError) as error:
        repository.create_candidate(candidate=candidate, idempotency_key=uuid4())

    assert error.value.code == "GLOBAL_GEOMETRY_WRITE_CONFLICT"


def test_read_profile_deeply_freezes_ordinary_orm_json_values() -> None:
    candidate = _candidate()
    stored = _stored_profile(candidate)
    stored.normalized_template = json.loads(json.dumps(candidate.normalized_template))
    stored.frame_appearance = json.loads(json.dumps(candidate.frame_appearance))
    stored.evidence_summary = json.loads(json.dumps(candidate.evidence_summary))
    session = Mock()
    session.scalars.return_value.all.return_value = [stored]
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    result = repository.list_profiles(geometry_family=SUPPORTED_GEOMETRY_FAMILY, limit=1)[0]

    with pytest.raises(TypeError):
        result.normalized_template["frameQuad"][0][0] = 0.2  # type: ignore[index]
    assert stored.normalized_template["frameQuad"][0][0] == 0.0
