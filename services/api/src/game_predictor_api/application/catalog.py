"""Application service and repository port for the game catalog."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.catalog import (
    CatalogNotFoundError,
    Game,
    GameStatus,
    Symbol,
    SymbolStatus,
    validate_display_order,
    validate_image_path,
    validate_mobile_code,
    validate_name,
    validate_stable_code,
)


class CatalogRepository(Protocol):
    def list_games(self) -> Sequence[Game]: ...

    def get_game(self, game_id: UUID) -> Game | None: ...

    def add_game(self, *, code: str, name: str, status: GameStatus) -> Game: ...

    def save_game(self, game: Game) -> Game: ...

    def list_symbols(self, game_id: UUID) -> Sequence[Symbol]: ...

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None: ...

    def add_symbol(
        self,
        *,
        game_id: UUID,
        mobile_code: int,
        code: str,
        name: str,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
    ) -> Symbol: ...

    def save_symbol(self, symbol: Symbol) -> Symbol: ...


class CatalogService:
    """Transactional use cases independent of HTTP and SQLAlchemy."""

    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    def list_games(self) -> Sequence[Game]:
        return self._repository.list_games()

    def get_game(self, game_id: UUID) -> Game:
        game = self._repository.get_game(game_id)
        if game is None:
            raise CatalogNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        return game

    def create_game(self, *, code: str, name: str, status: GameStatus) -> Game:
        return self._repository.add_game(
            code=validate_stable_code(code, field_name="code"),
            name=validate_name(name),
            status=status,
        )

    def update_game(
        self,
        game_id: UUID,
        *,
        name: str | None = None,
        status: GameStatus | None = None,
    ) -> Game:
        game = self.get_game(game_id)
        updated = replace(
            game,
            name=game.name if name is None else validate_name(name),
            status=game.status if status is None else status,
        )
        return self._repository.save_game(updated)

    def archive_game(self, game_id: UUID) -> Game:
        return self.update_game(game_id, status=GameStatus.ARCHIVED)

    def list_symbols(self, game_id: UUID) -> Sequence[Symbol]:
        self.get_game(game_id)
        return self._repository.list_symbols(game_id)

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol:
        self.get_game(game_id)
        symbol = self._repository.get_symbol(game_id, symbol_id)
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
                details={"gameId": str(game_id), "symbolId": str(symbol_id)},
            )
        return symbol

    def create_symbol(
        self,
        game_id: UUID,
        *,
        mobile_code: int,
        code: str,
        name: str,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
    ) -> Symbol:
        self.get_game(game_id)
        return self._repository.add_symbol(
            game_id=game_id,
            mobile_code=validate_mobile_code(mobile_code),
            code=validate_stable_code(code, field_name="code"),
            name=validate_name(name),
            image_path=validate_image_path(image_path),
            is_wildcard=is_wildcard,
            display_order=validate_display_order(display_order),
            status=status,
        )

    def update_symbol(
        self,
        game_id: UUID,
        symbol_id: UUID,
        *,
        name: str | None = None,
        image_path: str | None = None,
        update_image_path: bool = False,
        is_wildcard: bool | None = None,
        display_order: int | None = None,
        status: SymbolStatus | None = None,
    ) -> Symbol:
        symbol = self.get_symbol(game_id, symbol_id)
        updated = replace(
            symbol,
            name=symbol.name if name is None else validate_name(name),
            image_path=(
                symbol.image_path
                if not update_image_path
                else validate_image_path(image_path)
            ),
            is_wildcard=(
                symbol.is_wildcard if is_wildcard is None else is_wildcard
            ),
            display_order=(
                symbol.display_order
                if display_order is None
                else validate_display_order(display_order)
            ),
            status=symbol.status if status is None else status,
        )
        return self._repository.save_symbol(updated)

    def archive_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol:
        return self.update_symbol(
            game_id,
            symbol_id,
            status=SymbolStatus.ARCHIVED,
        )
