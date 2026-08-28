from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    _require_ready_state as require_bulk_ready_state,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    SqlAlchemySymbolCellReviewQueryRepository,
)


def _repository(*, status: str, preserve_ready_projection: bool):
    session = MagicMock()
    state = SimpleNamespace(status=status, catalog_revision=17)
    session.get.side_effect = [SimpleNamespace(), state]
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(
            input_payload={
                "preserve_ready_projection": preserve_ready_projection,
            }
        )
    ]
    return SqlAlchemySymbolCellReviewQueryRepository(session)


def test_ready_projection_remains_available_during_marked_reconciliation() -> None:
    repository = _repository(status="rebuilding", preserve_ready_projection=True)

    assert repository.require_ready_game(uuid4()) == 17


def test_mutation_remains_available_during_marked_reconciliation() -> None:
    session = MagicMock()
    state = SimpleNamespace(status="rebuilding", catalog_revision=17)
    session.get.side_effect = [SimpleNamespace(), state]
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(input_payload={"preserve_ready_projection": True})
    ]
    repository = SqlAlchemySymbolCellReviewMutationRepository(session)

    assert repository._require_ready_state(uuid4()) is state


def test_bulk_preview_remains_available_during_marked_reconciliation() -> None:
    session = MagicMock()
    state = SimpleNamespace(status="rebuilding", catalog_revision=17)
    session.get.return_value = SimpleNamespace()
    session.scalar.return_value = state
    session.scalars.return_value.all.return_value = [
        SimpleNamespace(input_payload={"preserve_ready_projection": True})
    ]

    assert require_bulk_ready_state(session, game_id=uuid4(), for_update=False) is state


@pytest.mark.parametrize("status", ["not_started", "rebuilding", "failed"])
def test_incomplete_projection_remains_fail_closed(status: str) -> None:
    repository = _repository(status=status, preserve_ready_projection=False)

    with pytest.raises(SymbolCellReviewError) as raised:
        repository.require_ready_game(uuid4())

    assert raised.value.code == "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE"
