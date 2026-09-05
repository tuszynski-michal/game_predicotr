from __future__ import annotations

from typing import cast
from uuid import UUID

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewFilterState,
    SymbolCellReviewListFilter,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session


class _ScalarSession:
    def __init__(self, result: UUID | None) -> None:
        self.result = result
        self.statement: object | None = None

    def scalar(self, statement: object) -> UUID | None:
        self.statement = statement
        return self.result


def _compiled(statement: object) -> str:
    return str(
        statement.compile(  # type: ignore[attr-defined]
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_active_model_cohort_uses_latest_activation_for_the_same_game() -> None:
    game_id = UUID(int=1)
    cohort_id = UUID(int=2)
    session = _ScalarSession(cohort_id)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, session))

    assert repository.active_model_cohort_id(game_id) == cohort_id

    sql = _compiled(session.statement)
    assert "JOIN game_symbol_model_activations" in sql
    assert "game_symbol_model_activations.game_id" in sql
    assert "symbol_model_iterations.game_id" in sql
    assert "ORDER BY game_symbol_model_activations.activation_number DESC" in sql
    assert "LIMIT 1" in sql


def test_active_model_cohort_filter_requires_the_exact_current_crop_identity() -> None:
    cohort_id = UUID(int=3)
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT,
        include_all_symbols=True,
        model_cohort_id=cohort_id,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "image_symbol_review_cells.review_state = 'approved'" in sql
    assert "JOIN verified_training_cohort_cells ON" in sql
    assert "verified_training_cohort_cells.cohort_id" in sql
    assert "verified_training_cohort_cells.cell_review_id = image_symbol_review_cells.id" in sql
    assert (
        "verified_training_cohort_cells.crop_checksum_sha256 = "
        "image_symbol_review_cells.crop_checksum_sha256" in sql
    )
    assert "verified_training_cohort_cells.asset_mode = image_symbol_review_cells.asset_mode" in sql
    assert sql.count("IS NOT DISTINCT FROM") == 3


def test_active_model_cohort_filter_without_an_activation_is_empty() -> None:
    repository = SqlAlchemySymbolCellReviewQueryRepository(cast(Session, object()))
    review_filter = SymbolCellReviewListFilter(
        game_id=UUID(int=1),
        symbol_id=None,
        state=SymbolCellReviewFilterState.ACTIVE_MODEL_COHORT,
        include_all_symbols=True,
        model_cohort_id=None,
    )

    sql = _compiled(repository._candidate_seek_statement(review_filter=review_filter))

    assert "false" in sql.lower()
    assert "verified_training_cohort_cells" not in sql
