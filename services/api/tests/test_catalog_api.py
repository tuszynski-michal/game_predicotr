from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.catalog import CatalogRepository, CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    Game,
    GameStatus,
    Symbol,
    SymbolStatus,
)
from game_predictor_api.main import create_app


class MemoryCatalogRepository(CatalogRepository):
    def __init__(self) -> None:
        self.games: dict[UUID, Game] = {}
        self.symbols: dict[UUID, Symbol] = {}

    def list_games(self) -> list[Game]:
        return list(self.games.values())

    def get_game(self, game_id: UUID) -> Game | None:
        return self.games.get(game_id)

    def add_game(self, *, code: str, name: str, status: GameStatus) -> Game:
        if any(game.code == code for game in self.games.values()):
            raise CatalogConflictError(
                "GAME_CODE_ALREADY_EXISTS",
                "A game with this code already exists.",
            )
        timestamp = datetime.now(UTC)
        game = Game(
            id=uuid4(),
            code=code,
            name=name,
            status=status,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.games[game.id] = game
        return game

    def save_game(self, game: Game) -> Game:
        self.games[game.id] = game
        return game

    def list_symbols(self, game_id: UUID) -> list[Symbol]:
        return sorted(
            (symbol for symbol in self.symbols.values() if symbol.game_id == game_id),
            key=lambda symbol: (symbol.display_order, symbol.mobile_code),
        )

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None:
        symbol = self.symbols.get(symbol_id)
        return symbol if symbol is not None and symbol.game_id == game_id else None

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
        game_symbols = self.list_symbols(game_id)
        if any(symbol.code == code for symbol in game_symbols):
            raise CatalogConflictError(
                "SYMBOL_CODE_ALREADY_EXISTS",
                "A symbol with this code already exists in the game.",
            )
        if any(symbol.mobile_code == mobile_code for symbol in game_symbols):
            raise CatalogConflictError(
                "SYMBOL_MOBILE_CODE_ALREADY_EXISTS",
                "A symbol with this mobileCode already exists in the game.",
            )
        symbol = Symbol(
            id=uuid4(),
            game_id=game_id,
            mobile_code=mobile_code,
            code=code,
            name=name,
            image_path=image_path,
            is_wildcard=is_wildcard,
            display_order=display_order,
            status=status,
        )
        self.symbols[symbol.id] = symbol
        return symbol

    def save_symbol(self, symbol: Symbol) -> Symbol:
        self.symbols[symbol.id] = symbol
        return symbol


def _client(repository: MemoryCatalogRepository) -> TestClient:
    service = CatalogService(repository)
    app = create_app(
        ApiSettings.from_environment({}),
        catalog_service_dependency=lambda: service,
    )
    return TestClient(app)


def test_game_and_symbol_crud_archives_without_physical_deletion() -> None:
    repository = MemoryCatalogRepository()

    with _client(repository) as client:
        game_response = client.post(
            "/api/v1/admin/games",
            json={"code": "blazing-hot", "name": " Blazing Hot "},
        )
        assert game_response.status_code == 201
        game = game_response.json()
        game_id = game["id"]
        assert game["name"] == "Blazing Hot"
        assert game["status"] == "draft"

        symbol_response = client.post(
            f"/api/v1/admin/games/{game_id}/symbols",
            json={
                "mobileCode": 12,
                "code": "WILD",
                "name": "Wildcard",
                "imagePath": "symbols/blazing-hot/wild.png",
                "isWildcard": True,
                "displayOrder": 5,
            },
        )
        assert symbol_response.status_code == 201
        symbol = symbol_response.json()
        symbol_id = symbol["id"]
        assert symbol["gameId"] == game_id
        assert symbol["mobileCode"] == 12

        updated = client.patch(
            f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            json={"name": "Wild", "imagePath": None, "displayOrder": 1},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Wild"
        assert updated.json()["imagePath"] is None

        listed = client.get(f"/api/v1/admin/games/{game_id}/symbols")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [symbol_id]

        assert (
            client.delete(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}").status_code == 204
        )
        assert client.delete(f"/api/v1/admin/games/{game_id}").status_code == 204

        assert client.get(f"/api/v1/admin/games/{game_id}").json()["status"] == "archived"
        assert (
            client.get(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}").json()["status"]
            == "archived"
        )
        assert len(repository.games) == 1
        assert len(repository.symbols) == 1


def test_api_returns_stable_conflict_not_found_and_validation_errors() -> None:
    repository = MemoryCatalogRepository()

    with _client(repository) as client:
        created = client.post(
            "/api/v1/admin/games",
            json={"code": "game-1", "name": "Game 1"},
        )
        game_id = created.json()["id"]

        duplicate = client.post(
            "/api/v1/admin/games",
            json={"code": "game-1", "name": "Duplicate"},
        )
        assert duplicate.status_code == 409
        assert duplicate.json() == {
            "code": "GAME_CODE_ALREADY_EXISTS",
            "message": "A game with this code already exists.",
            "details": {},
        }

        invalid = client.post(
            f"/api/v1/admin/games/{game_id}/symbols",
            json={
                "mobileCode": 0,
                "code": "S1",
                "name": "Symbol",
                "displayOrder": 0,
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"

        immutable_code = client.patch(
            f"/api/v1/admin/games/{game_id}",
            json={"code": "changed"},
        )
        assert immutable_code.status_code == 422
        assert immutable_code.json()["code"] == "VALIDATION_ERROR"

        missing = client.get(f"/api/v1/admin/games/{uuid4()}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "GAME_NOT_FOUND"
