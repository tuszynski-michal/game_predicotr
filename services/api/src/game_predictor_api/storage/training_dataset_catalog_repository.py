"""SQLAlchemy adapter for the active game symbol training catalog."""

from __future__ import annotations

from uuid import UUID

from game_predictor_worker.symbols import TrainingSymbol
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.verified_training_datasets import (
    TrainingDatasetCatalog,
    TrainingDatasetCatalogRepository,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.storage.models import GameModel, SymbolModel


class SqlAlchemyTrainingDatasetCatalogRepository(TrainingDatasetCatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, *, game_id: UUID) -> TrainingDatasetCatalog | None:
        game = self._session.get(GameModel, game_id)
        if game is None:
            return None
        records = self._session.scalars(
            select(SymbolModel)
            .where(
                SymbolModel.game_id == game_id,
                SymbolModel.status == SymbolStatus.ACTIVE,
            )
            .order_by(SymbolModel.display_order, SymbolModel.code, SymbolModel.id)
        ).all()
        return TrainingDatasetCatalog(
            game_code=game.code,
            symbols=tuple(
                TrainingSymbol(id=str(record.id), code=record.code) for record in records
            ),
        )


__all__ = ["SqlAlchemyTrainingDatasetCatalogRepository"]
