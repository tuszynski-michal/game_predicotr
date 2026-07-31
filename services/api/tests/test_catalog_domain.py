from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.catalog import CatalogRepository, CatalogService
from game_predictor_api.domain.catalog import (
    CatalogError,
    Game,
    GameStatus,
    Symbol,
    SymbolStatus,
    validate_image_path,
)


class EmptyCatalogRepository(CatalogRepository):
    def list_games(self) -> list[Game]:
        return []

    def get_game(self, game_id: UUID) -> Game | None:
        return None

    def add_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int,
    ) -> Game:
        timestamp = datetime.now(UTC)
        return Game(
            uuid4(),
            code,
            name,
            status,
            expected_layout_count,
            timestamp,
            timestamp,
        )

    def save_game(self, game: Game) -> Game:
        return game

    def list_symbols(self, game_id: UUID) -> list[Symbol]:
        return []

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None:
        return None

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
    ) -> Symbol:
        raise AssertionError("Game existence must be checked first.")

    def save_symbol(self, symbol: Symbol) -> Symbol:
        return symbol

    def symbol_is_used_in_rules(self, symbol_id: UUID) -> bool:
        return False


@pytest.mark.parametrize("code", ["", "has space", ".hidden", "a" * 65])
def test_game_stable_code_validation_is_domain_owned(code: str) -> None:
    service = CatalogService(EmptyCatalogRepository())

    with pytest.raises(CatalogError) as error:
        service.create_game(code=code, name="Game", status=GameStatus.DRAFT)

    assert error.value.code == "INVALID_STABLE_CODE"


def test_missing_parent_game_stops_symbol_creation() -> None:
    service = CatalogService(EmptyCatalogRepository())
    missing_game_id = uuid4()

    with pytest.raises(CatalogError) as error:
        service.create_symbol(
            missing_game_id,
            mobile_code=1,
            code="S1",
            name="Symbol 1",
            image_path=None,
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )

    assert error.value.code == "GAME_NOT_FOUND"


@pytest.mark.parametrize(
    "image_path",
    ["../symbol.png", "symbols/../symbol.png", r"C:\symbols\s1.png", "C:/symbols/s1.png"],
)
def test_reference_image_path_must_be_relative_and_portable(image_path: str) -> None:
    with pytest.raises(CatalogError) as error:
        validate_image_path(image_path)

    assert error.value.code == "INVALID_IMAGE_PATH"
