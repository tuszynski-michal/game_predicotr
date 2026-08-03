"""SQLAlchemy implementation of the catalog repository port."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.catalog import CatalogRepository
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    Game,
    GameStatus,
    Symbol,
    SymbolStatus,
)
from game_predictor_api.storage.models import (
    GameModel,
    RulesVersionSymbolModel,
    SymbolModel,
)

_CONFLICTS = {
    "uq_games_code": (
        "GAME_CODE_ALREADY_EXISTS",
        "A game with this code already exists.",
    ),
    "uq_symbols_game_code": (
        "SYMBOL_CODE_ALREADY_EXISTS",
        "A symbol with this code already exists in the game.",
    ),
    "uq_symbols_game_mobile_code": (
        "SYMBOL_MOBILE_CODE_ALREADY_EXISTS",
        "A symbol with this mobileCode already exists in the game.",
    ),
}


class SqlAlchemyCatalogRepository(CatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_games(self) -> list[Game]:
        records = self._session.scalars(
            select(GameModel).order_by(GameModel.created_at, GameModel.id)
        )
        return [_to_game(record) for record in records]

    def get_game(self, game_id: UUID) -> Game | None:
        record = self._session.get(GameModel, game_id)
        return None if record is None else _to_game(record)

    def add_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int,
    ) -> Game:
        record = GameModel(
            code=code,
            name=name,
            status=status,
            expected_layout_count=expected_layout_count,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        self._session.refresh(record)
        return _to_game(record)

    def save_game(self, game: Game) -> Game:
        record = self._session.get(GameModel, game.id)
        if record is None:
            raise RuntimeError("Game disappeared during a catalog transaction.")
        record.name = game.name
        record.status = game.status
        record.expected_layout_count = game.expected_layout_count
        record.updated_at = datetime.now(UTC)
        self._flush_or_raise_conflict()
        return _to_game(record)

    def list_symbols(self, game_id: UUID) -> list[Symbol]:
        records = self._session.scalars(
            select(SymbolModel)
            .where(SymbolModel.game_id == game_id)
            .order_by(
                SymbolModel.display_order,
                SymbolModel.mobile_code,
                SymbolModel.id,
            )
        )
        return [_to_symbol(record) for record in records]

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None:
        record = self._session.scalar(
            select(SymbolModel).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        return None if record is None else _to_symbol(record)

    def add_symbol(
        self,
        *,
        game_id: UUID,
        mobile_code: int,
        code: str,
        name: str,
        name_pl: str | None,
        name_en: str | None,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
    ) -> Symbol:
        record = SymbolModel(
            game_id=game_id,
            mobile_code=mobile_code,
            code=code,
            name=name,
            name_pl=name_pl,
            name_en=name_en,
            image_path=image_path,
            is_wildcard=is_wildcard,
            display_order=display_order,
            status=status,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        return _to_symbol(record)

    def save_symbol(self, symbol: Symbol) -> Symbol:
        record = self._session.get(SymbolModel, symbol.id)
        if record is None or record.game_id != symbol.game_id:
            raise RuntimeError("Symbol disappeared during a catalog transaction.")
        record.name = symbol.name
        record.name_pl = symbol.name_pl
        record.name_en = symbol.name_en
        record.image_path = symbol.image_path
        record.is_wildcard = symbol.is_wildcard
        record.display_order = symbol.display_order
        record.status = symbol.status
        self._flush_or_raise_conflict()
        return _to_symbol(record)

    def symbol_is_used_in_rules(self, symbol_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(RulesVersionSymbolModel.symbol_id)
                .where(RulesVersionSymbolModel.symbol_id == symbol_id)
                .limit(1)
            )
            is not None
        )

    def _flush_or_raise_conflict(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            conflict = _CONFLICTS.get(constraint_name) if isinstance(constraint_name, str) else None
            if conflict is None:
                raise
            code, message = conflict
            raise CatalogConflictError(code, message) from error


def _to_game(record: GameModel) -> Game:
    return Game(
        id=record.id,
        code=record.code,
        name=record.name,
        status=record.status,
        expected_layout_count=record.expected_layout_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_symbol(record: SymbolModel) -> Symbol:
    return Symbol(
        id=record.id,
        game_id=record.game_id,
        mobile_code=record.mobile_code,
        code=record.code,
        name=record.name,
        name_pl=record.name_pl,
        name_en=record.name_en,
        image_path=record.image_path,
        is_wildcard=record.is_wildcard,
        display_order=record.display_order,
        status=record.status,
    )
