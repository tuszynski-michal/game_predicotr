"""Control-plane persistence of immutable multi-game search links."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.application.board_search_panels import (
    BoardSearchPanelGame,
    BoardSearchPanelRecord,
    BoardSearchPanelRepository,
)
from game_predictor_api.storage.board_search_share_repository import (
    InMemoryBoardSearchShareRepository,
)
from game_predictor_api.storage.models import (
    BoardSearchPanelModel,
    BoardSearchShareSessionModel,
    GameModel,
)


class SqlAlchemyBoardSearchPanelRepository(BoardSearchPanelRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: BoardSearchPanelRecord) -> None:
        self._session.add(
            BoardSearchPanelModel(
                id=record.id,
                label=record.label,
                secret_hash=record.secret_hash,
                created_at=record.created_at,
                expires_at=record.expires_at,
                revoked_at=record.revoked_at,
            )
        )
        self._session.flush()

    def get(self, panel_id: UUID, *, lock: bool = False) -> BoardSearchPanelRecord | None:
        statement = select(BoardSearchPanelModel).where(BoardSearchPanelModel.id == panel_id)
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        model = self._session.scalar(statement)
        return None if model is None else _record(model)

    def save(self, record: BoardSearchPanelRecord) -> None:
        model = self._session.get(BoardSearchPanelModel, record.id)
        if model is None:
            raise RuntimeError("Panel disappeared.")
        model.revoked_at = record.revoked_at
        self._session.flush()

    def list(self, limit: int) -> Sequence[BoardSearchPanelRecord]:
        return tuple(
            _record(model)
            for model in self._session.scalars(
                select(BoardSearchPanelModel)
                .order_by(BoardSearchPanelModel.created_at.desc(), BoardSearchPanelModel.id.desc())
                .limit(limit)
            )
        )

    def games(self, panel_id: UUID) -> Sequence[BoardSearchPanelGame]:
        return tuple(
            BoardSearchPanelGame(game_id, name, session_id)
            for game_id, name, session_id in self._session.execute(
                select(GameModel.id, GameModel.name, BoardSearchShareSessionModel.id)
                .join(
                    BoardSearchShareSessionModel,
                    BoardSearchShareSessionModel.game_id == GameModel.id,
                )
                .where(BoardSearchShareSessionModel.panel_id == panel_id)
                .order_by(GameModel.id)
            )
        )


class InMemoryBoardSearchPanelRepository(BoardSearchPanelRepository):
    def __init__(self, shares: InMemoryBoardSearchShareRepository, names: dict[UUID, str]) -> None:
        self.shares, self.names = shares, names
        self.records: dict[UUID, BoardSearchPanelRecord] = {}

    def add(self, record: BoardSearchPanelRecord) -> None:
        self.records[record.id] = record

    def get(self, panel_id: UUID, *, lock: bool = False) -> BoardSearchPanelRecord | None:
        return self.records.get(panel_id)

    def save(self, record: BoardSearchPanelRecord) -> None:
        self.records[record.id] = record

    def list(self, limit: int) -> Sequence[BoardSearchPanelRecord]:
        return sorted(
            self.records.values(), key=lambda item: (item.created_at, item.id), reverse=True
        )[:limit]

    def games(self, panel_id: UUID) -> Sequence[BoardSearchPanelGame]:
        return tuple(
            BoardSearchPanelGame(record.game_id, self.names[record.game_id], record.id)
            for record in sorted(self.shares.records.values(), key=lambda item: item.game_id)
            if record.panel_id == panel_id
        )


def _record(model: BoardSearchPanelModel) -> BoardSearchPanelRecord:
    return BoardSearchPanelRecord(
        id=model.id,
        label=model.label,
        secret_hash=model.secret_hash,
        created_at=model.created_at,
        expires_at=model.expires_at,
        revoked_at=model.revoked_at,
    )
