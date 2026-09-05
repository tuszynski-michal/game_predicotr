from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.grid_calibration_repository import (
    SqlAlchemyGridCalibrationRepository,
)


def test_geometry_cohort_uses_current_owner_and_approved_geometry_revision() -> None:
    session = Mock()
    session.get.return_value = object()
    session.execute.return_value.all.return_value = []
    repository = SqlAlchemyGridCalibrationRepository(session)

    diagnostics = repository.cohort_diagnostics(game_id=uuid4())

    statement = str(session.execute.call_args.args[0])
    assert "image_board_search_fast_documents" in statement
    assert "approved_geometry_revision = recognized_boards.geometry_revision" in statement
    assert diagnostics.eligible_geometry_count == 0


def test_verified_geometry_samples_do_not_require_resolved_symbol_labels() -> None:
    session = Mock()
    session.execute.return_value.all.return_value = []
    repository = SqlAlchemyGridCalibrationRepository(session)

    assert repository._verified_samples(uuid4()) == ()

    statement = str(session.execute.call_args.args[0])
    assert "image_review_items.status IN" in statement
    assert "image_board_search_fast_documents" in statement
    assert "approved_geometry_revision = recognized_boards.geometry_revision" in statement


def test_historical_v2_profile_requires_current_gate_before_new_activation() -> None:
    game_id = uuid4()
    profile_id = uuid4()
    profile = SimpleNamespace(
        id=profile_id,
        game_id=game_id,
        status="candidate_ready",
        profile_payload={"schemaVersion": 2},
        gate_metrics={"passed": True},
    )
    session = Mock()
    session.get.return_value = profile
    repository = SqlAlchemyGridCalibrationRepository(session)

    with pytest.raises(JobConflictError) as error:
        repository._eligible_profile(game_id, profile_id)

    assert error.value.code == "GRID_PROFILE_END_TO_END_REVALIDATION_REQUIRED"
