from __future__ import annotations

from dataclasses import replace
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
    SymbolUsageSummary,
    stable_code_stem_from_name,
)
from game_predictor_api.main import create_app


class MemoryCatalogRepository(CatalogRepository):
    def __init__(self) -> None:
        self.games: dict[UUID, Game] = {}
        self.symbols: dict[UUID, Symbol] = {}
        self.rules_symbol_ids: set[UUID] = set()
        self.usage_overrides: dict[UUID, SymbolUsageSummary] = {}

    def list_games(self) -> list[Game]:
        return list(self.games.values())

    def get_game(self, game_id: UUID) -> Game | None:
        return self.games.get(game_id)

    def add_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int,
    ) -> Game:
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
            expected_layout_count=expected_layout_count,
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
        name_pl: str | None,
        name_en: str | None,
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
            name_pl=name_pl,
            name_en=name_en,
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

    def symbol_is_used_in_rules(self, symbol_id: UUID) -> bool:
        return symbol_id in self.rules_symbol_ids

    def add_manual_symbol(self, *, game_id: UUID, name: str, is_wildcard: bool) -> Symbol:
        game_symbols = self.list_symbols(game_id)
        stem = stable_code_stem_from_name(name)
        code = stem
        suffix = 2
        existing_codes = {symbol.code for symbol in game_symbols}
        while code in existing_codes:
            rendered_suffix = f"-{suffix}"
            code = f"{stem[: 64 - len(rendered_suffix)]}{rendered_suffix}"
            suffix += 1
        symbol = Symbol(
            id=uuid4(),
            game_id=game_id,
            mobile_code=max((item.mobile_code for item in game_symbols), default=0) + 1,
            code=code,
            name=name,
            image_path=None,
            is_wildcard=is_wildcard,
            display_order=max((item.display_order for item in game_symbols), default=-1) + 1,
            status=SymbolStatus.ACTIVE,
        )
        self.symbols[symbol.id] = symbol
        return symbol

    def symbol_usage_summary(self, *, game_id: UUID, symbol_id: UUID) -> SymbolUsageSummary | None:
        symbol = self.get_symbol(game_id, symbol_id)
        if symbol is None:
            return None
        if symbol_id in self.usage_overrides:
            return self.usage_overrides[symbol_id]
        return SymbolUsageSummary(rules=int(symbol_id in self.rules_symbol_ids))

    def delete_unused_symbol(self, *, game_id: UUID, symbol_id: UUID) -> None:
        del self.symbols[symbol_id]


def _client(repository: MemoryCatalogRepository) -> TestClient:
    service = CatalogService(repository)
    app = create_app(
        ApiSettings.from_environment({}),
        catalog_service_dependency=lambda: service,
    )
    return TestClient(app)


def test_game_and_symbol_crud_assigns_identity_and_deletes_only_unused_symbols() -> None:
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

        game_update = client.patch(
            f"/api/v1/admin/games/{game_id}",
            json={
                "name": "Blazing Hot v0.2",
                "status": "draft",
                "expectedLayoutCount": 750_000,
            },
        )
        assert game_update.status_code == 200
        assert game_update.json()["name"] == "Blazing Hot v0.2"
        assert game_update.json()["expectedLayoutCount"] == 750_000

        symbol_response = client.post(
            f"/api/v1/admin/games/{game_id}/symbols",
            json={
                "name": "Wildcard",
                "isWildcard": True,
            },
        )
        assert symbol_response.status_code == 201
        symbol = symbol_response.json()
        symbol_id = symbol["id"]
        assert symbol["gameId"] == game_id
        assert symbol["mobileCode"] == 1
        assert symbol["code"] == "WILDCARD"
        assert symbol["displayOrder"] == 0

        repository.rules_symbol_ids.add(UUID(symbol_id))
        identity_change = client.patch(
            f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            json={"isWildcard": False},
        )
        assert identity_change.status_code == 409
        assert identity_change.json()["code"] == "SYMBOL_RULES_IDENTITY_IN_USE"

        updated = client.patch(
            f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
            json={
                "name": "Wild",
            },
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Wild"
        assert updated.json()["code"] == "WILDCARD"
        assert updated.json()["mobileCode"] == 1

        listed = client.get(f"/api/v1/admin/games/{game_id}/symbols")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [symbol_id]

        blocked = client.delete(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}")
        assert blocked.status_code == 409
        assert blocked.json()["code"] == "SYMBOL_DELETE_BLOCKED"
        assert blocked.json()["details"]["rules"] == 1
        repository.rules_symbol_ids.clear()
        assert (
            client.delete(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}").status_code == 204
        )
        assert client.delete(f"/api/v1/admin/games/{game_id}").status_code == 204

        assert client.get(f"/api/v1/admin/games/{game_id}").json()["status"] == "archived"
        assert client.get(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}").status_code == 404
        assert len(repository.games) == 1
        assert len(repository.symbols) == 0


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
            json={"isWildcard": False},
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


def test_manual_symbol_creation_assigns_stable_identity_and_resolves_name_collisions() -> None:
    repository = MemoryCatalogRepository()

    with _client(repository) as client:
        game_id = client.post(
            "/api/v1/admin/games",
            json={"code": "game-1", "name": "Game 1"},
        ).json()["id"]
        first = client.post(
            f"/api/v1/admin/games/{game_id}/symbols",
            json={"name": "Cherries", "isWildcard": False},
        )
        second = client.post(
            f"/api/v1/admin/games/{game_id}/symbols",
            json={"name": "Cherries", "isWildcard": True},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert (first.json()["code"], second.json()["code"]) == ("CHERRIES", "CHERRIES-2")
    assert (first.json()["mobileCode"], second.json()["mobileCode"]) == (1, 2)
    assert (first.json()["displayOrder"], second.json()["displayOrder"]) == (0, 1)


def test_delete_reports_each_durable_usage_blocker() -> None:
    repository = MemoryCatalogRepository()
    usage_fields = (
        "pending_board_predictions",
        "resolved_board_decisions",
        "observation_predictions",
        "symbol_cell_assignments",
        "symbol_cell_review_events",
        "training_cohorts",
        "symbol_model_iterations",
        "symbol_model_activations",
    )

    with _client(repository) as client:
        game_id = client.post(
            "/api/v1/admin/games",
            json={"code": "game-1", "name": "Game 1"},
        ).json()["id"]
        for index, field_name in enumerate(usage_fields):
            symbol = client.post(
                f"/api/v1/admin/games/{game_id}/symbols",
                json={"name": f"Symbol {index}", "isWildcard": False},
            ).json()
            symbol_id = UUID(symbol["id"])
            repository.usage_overrides[symbol_id] = replace(SymbolUsageSummary(), **{field_name: 1})
            blocked = client.delete(f"/api/v1/admin/games/{game_id}/symbols/{symbol_id}")

            assert blocked.status_code == 409
            assert blocked.json()["code"] == "SYMBOL_DELETE_BLOCKED"
            assert any(value == 1 for value in blocked.json()["details"].values())
