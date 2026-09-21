from __future__ import annotations

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
    GlobalGeometryProfileStatus,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationDecision,
    GlobalGeometryQualificationOutcome,
    build_global_geometry_qualification_report,
    qualification_command_sha256,
    qualification_result_checksum_sha256,
)
from game_predictor_api.storage.global_geometry_library_repository import (
    SqlAlchemyGlobalGeometryLibraryRepository,
)
from game_predictor_api.storage.models import (
    GlobalGeometryProfileQualificationReceiptModel,
    GlobalGeometryProfileQualificationResultModel,
)
from sqlalchemy.exc import IntegrityError

NOW = datetime(2026, 9, 21, 12, 0, tzinfo=UTC)


def _candidate(*, aspect_minimum: float = 0.5):
    topology = GlobalGeometryTopology(3, 3, 3, 5)
    return build_global_geometry_candidate(
        geometry_family=SUPPORTED_GEOMETRY_FAMILY,
        topology=topology,
        normalized_template={
            "schemaVersion": NORMALIZED_TEMPLATE_SCHEMA_VERSION,
            "topology": topology.to_dict(),
            "frameQuad": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
            "aspectRatioRange": {"minimum": aspect_minimum, "maximum": 2.0},
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


def _profile_model(candidate, *, number: int, status: GlobalGeometryProfileStatus):
    return SimpleNamespace(
        id=uuid4(),
        profile_number=number,
        status=status.value,
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


def _evidence_models(candidate) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            source_game_ref=evidence.source_game_ref,
            evidence_checksum_sha256=evidence.evidence_checksum_sha256,
            evidence_payload=evidence.evidence_payload,
        )
        for evidence in candidate.evidence
    ]


def _report(candidate, *, baseline: str | None, regression_incorrect: int = 0):
    return build_global_geometry_qualification_report(
        candidate_profile_checksum_sha256=candidate.profile_checksum_sha256,
        baseline_active_profile_checksum_sha256=baseline,
        replay_snapshot_checksum_sha256="a" * 64,
        regression_snapshot_checksum_sha256="b" * 64,
        transfer_snapshot_checksum_sha256="c" * 64,
        contributor_game_refs=["mummies"],
        transfer_target_game_ref="gang",
        replay_expected_source_count=2,
        replay_evaluated_source_count=2,
        replay_automatic_incorrect_source_count=0,
        regression_expected_source_count=2,
        regression_evaluated_source_count=2,
        regression_baseline_automatic_incorrect_source_count=0,
        regression_candidate_automatic_incorrect_source_count=regression_incorrect,
        transfer_expected_source_count=2,
        transfer_evaluated_source_count=2,
        transfer_automatic_incorrect_source_count=0,
    )


def _qualification_session(candidate_model, candidate, previous_model=None, previous=None):
    session = Mock()
    scopes = [candidate_model] if previous_model is None else [previous_model, candidate_model]
    scalar_values = [None, candidate_model, None]
    session.scalar.side_effect = scalar_values
    scalar_rows = [
        SimpleNamespace(all=lambda: scopes),
        SimpleNamespace(all=lambda: _evidence_models(candidate)),
    ]
    if previous is not None:
        scalar_rows.append(SimpleNamespace(all=lambda: _evidence_models(previous)))
    session.scalars.side_effect = scalar_rows
    added: list[object] = []

    def add(value: object) -> None:
        added.append(value)
        if isinstance(value, GlobalGeometryProfileQualificationResultModel):
            value.created_at = NOW

    session.add.side_effect = add
    return session, added


def test_passed_qualification_retires_previous_active_and_activates_candidate() -> None:
    candidate = _candidate()
    previous = _candidate(aspect_minimum=0.4)
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    previous_model = _profile_model(previous, number=7, status=GlobalGeometryProfileStatus.ACTIVE)
    session, added = _qualification_session(
        candidate_model, candidate, previous_model, previous
    )
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    result, created = repository.qualify_candidate(
        profile_id=candidate_model.id,
        report=_report(candidate, baseline=previous.profile_checksum_sha256),
        idempotency_key=uuid4(),
    )

    assert created is True
    assert result.outcome is GlobalGeometryQualificationOutcome.PASSED
    assert previous_model.status == GlobalGeometryProfileStatus.RETIRED.value
    assert candidate_model.status == GlobalGeometryProfileStatus.ACTIVE.value
    assert [type(value) for value in added] == [
        GlobalGeometryProfileQualificationResultModel,
        GlobalGeometryProfileQualificationReceiptModel,
    ]
    assert session.flush.call_count == 2
    assert "FOR UPDATE" in str(session.scalars.call_args_list[0].args[0])


def test_missing_report_is_audited_without_changing_candidate_or_active_profile() -> None:
    candidate = _candidate()
    previous = _candidate(aspect_minimum=0.4)
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    previous_model = _profile_model(previous, number=7, status=GlobalGeometryProfileStatus.ACTIVE)
    session, _ = _qualification_session(candidate_model, candidate, previous_model, previous)

    result, created = SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
        profile_id=candidate_model.id,
        report=None,
        idempotency_key=uuid4(),
    )

    assert created is True
    assert result.outcome is GlobalGeometryQualificationOutcome.NOT_EVALUABLE
    assert candidate_model.status == GlobalGeometryProfileStatus.CANDIDATE.value
    assert previous_model.status == GlobalGeometryProfileStatus.ACTIVE.value


def test_quality_regression_rejects_only_the_candidate() -> None:
    candidate = _candidate()
    previous = _candidate(aspect_minimum=0.4)
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    previous_model = _profile_model(previous, number=7, status=GlobalGeometryProfileStatus.ACTIVE)
    session, _ = _qualification_session(candidate_model, candidate, previous_model, previous)

    result, _ = SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
        profile_id=candidate_model.id,
        report=_report(
            candidate,
            baseline=previous.profile_checksum_sha256,
            regression_incorrect=1,
        ),
        idempotency_key=uuid4(),
    )

    assert result.outcome is GlobalGeometryQualificationOutcome.REJECTED
    assert "GLOBAL_GEOMETRY_QUALIFICATION_REGRESSION" in result.reason_codes
    assert candidate_model.status == GlobalGeometryProfileStatus.REJECTED.value
    assert previous_model.status == GlobalGeometryProfileStatus.ACTIVE.value


def test_idempotent_retry_returns_receipted_result_and_payload_mismatch_conflicts() -> None:
    candidate = _candidate()
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    report = _report(candidate, baseline=None)
    receipt = SimpleNamespace(
        command_sha256=qualification_command_sha256(profile_id=candidate_model.id, report=report),
        result_id=uuid4(),
    )
    stored_result = SimpleNamespace(
        id=receipt.result_id,
        profile_id=candidate_model.id,
        previous_active_profile_id=None,
        outcome=GlobalGeometryQualificationOutcome.PASSED.value,
        reason_codes=[],
        report_payload=report.as_dict(),
        qualification_checksum_sha256=qualification_result_checksum_sha256(
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            previous_active_profile_checksum_sha256=None,
            decision=GlobalGeometryQualificationDecision(
                GlobalGeometryQualificationOutcome.PASSED, ()
            ),
            report=report,
        ),
        created_at=NOW,
    )
    session = Mock()
    session.scalar.return_value = receipt
    session.get.side_effect = [stored_result, candidate_model]
    repository = SqlAlchemyGlobalGeometryLibraryRepository(session)

    retried, created = repository.qualify_candidate(
        profile_id=candidate_model.id,
        report=report,
        idempotency_key=uuid4(),
    )

    assert created is False
    assert retried.id == stored_result.id
    with pytest.raises(GlobalGeometryLibraryConflictError) as error:
        repository.qualify_candidate(
            profile_id=candidate_model.id,
            report=None,
            idempotency_key=uuid4(),
        )
    assert error.value.code == "GLOBAL_GEOMETRY_QUALIFICATION_IDEMPOTENCY_CONFLICT"


def test_concurrent_retry_rechecks_the_receipt_after_waiting_for_scope_lock() -> None:
    candidate = _candidate()
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.ACTIVE
    )
    report = _report(candidate, baseline=None)
    receipt = SimpleNamespace(
        command_sha256=qualification_command_sha256(profile_id=candidate_model.id, report=report),
        result_id=uuid4(),
    )
    stored_result = SimpleNamespace(
        id=receipt.result_id,
        profile_id=candidate_model.id,
        previous_active_profile_id=None,
        outcome=GlobalGeometryQualificationOutcome.PASSED.value,
        reason_codes=[],
        report_payload=report.as_dict(),
        qualification_checksum_sha256=qualification_result_checksum_sha256(
            profile_checksum_sha256=candidate.profile_checksum_sha256,
            previous_active_profile_checksum_sha256=None,
            decision=GlobalGeometryQualificationDecision(
                GlobalGeometryQualificationOutcome.PASSED, ()
            ),
            report=report,
        ),
        created_at=NOW,
    )
    session = Mock()
    session.scalar.side_effect = [None, candidate_model, receipt]
    session.scalars.return_value.all.return_value = [candidate_model]
    session.get.side_effect = [stored_result, candidate_model]

    result, created = SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
        profile_id=candidate_model.id,
        report=report,
        idempotency_key=uuid4(),
    )

    assert created is False
    assert result.id == stored_result.id
    assert session.scalar.call_count == 3


def test_receipted_result_with_tampered_checksum_is_rejected_on_read() -> None:
    candidate = _candidate()
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    report = _report(candidate, baseline=None)
    receipt = SimpleNamespace(
        command_sha256=qualification_command_sha256(profile_id=candidate_model.id, report=report),
        result_id=uuid4(),
    )
    stored_result = SimpleNamespace(
        id=receipt.result_id,
        profile_id=candidate_model.id,
        previous_active_profile_id=None,
        outcome=GlobalGeometryQualificationOutcome.PASSED.value,
        reason_codes=[],
        report_payload=report.as_dict(),
        qualification_checksum_sha256="0" * 64,
        created_at=NOW,
    )
    session = Mock()
    session.scalar.return_value = receipt
    session.get.side_effect = [stored_result, candidate_model]

    with pytest.raises(GlobalGeometryLibraryConflictError) as error:
        SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
            profile_id=candidate_model.id,
            report=report,
            idempotency_key=uuid4(),
        )

    assert error.value.code == "GLOBAL_GEOMETRY_QUALIFICATION_RESULT_INVALID"


def test_flush_conflict_is_reported_for_the_surrounding_transaction_to_rollback() -> None:
    candidate = _candidate()
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    session, _ = _qualification_session(candidate_model, candidate)
    session.flush.side_effect = IntegrityError("insert", {}, Exception("duplicate"))

    with pytest.raises(GlobalGeometryLibraryConflictError) as error:
        SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
            profile_id=candidate_model.id,
            report=_report(candidate, baseline=None),
            idempotency_key=uuid4(),
        )

    assert error.value.code == "GLOBAL_GEOMETRY_QUALIFICATION_WRITE_CONFLICT"


def test_scope_is_locked_in_one_global_order_before_any_candidate_row_lock() -> None:
    candidate = _candidate()
    candidate_model = _profile_model(
        candidate, number=8, status=GlobalGeometryProfileStatus.CANDIDATE
    )
    session, _ = _qualification_session(candidate_model, candidate)

    SqlAlchemyGlobalGeometryLibraryRepository(session).qualify_candidate(
        profile_id=candidate_model.id,
        report=None,
        idempotency_key=uuid4(),
    )

    initial_lookup = str(session.scalar.call_args_list[1].args[0])
    scope_lock = str(session.scalars.call_args_list[0].args[0])
    assert "FOR UPDATE" not in initial_lookup
    assert "ORDER BY global_geometry_profile_versions.profile_number ASC" in scope_lock
    assert "FOR UPDATE" in scope_lock
