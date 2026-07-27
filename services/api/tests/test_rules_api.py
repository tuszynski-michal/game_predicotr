from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.rules import RulesRepository, RulesService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.rules import Payline, RulesVersion, RulesVersionStatus
from game_predictor_api.main import create_app


class MemoryRulesRepository(RulesRepository):
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, RulesVersion] = {}
        self.paylines: dict[UUID, Payline] = {}

    def game_exists(self, game_id: UUID) -> bool:
        return game_id == self.game_id

    def list_rules_versions(self, game_id: UUID) -> list[RulesVersion]:
        return sorted(
            (item for item in self.items.values() if item.game_id == game_id),
            key=lambda item: item.version,
            reverse=True,
        )

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion | None:
        return self.items.get(rules_version_id)

    def add_next_rules_version(
        self,
        *,
        game_id: UUID,
        rows: int,
        columns: int,
        spin_cost: int,
    ) -> RulesVersion | None:
        if not self.game_exists(game_id):
            return None
        item = RulesVersion(
            id=uuid4(),
            game_id=game_id,
            version=len(self.items) + 1,
            rows=rows,
            columns=columns,
            spin_cost=spin_cost,
            status=RulesVersionStatus.DRAFT,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.items[item.id] = item
        return item

    def save_rules_version(self, rules_version: RulesVersion) -> RulesVersion:
        self.items[rules_version.id] = rules_version
        return rules_version

    def paylines_fit_dimensions(
        self,
        rules_version_id: UUID,
        *,
        rows: int,
        columns: int,
    ) -> bool:
        return all(
            len(item.row_path) == columns and max(item.row_path) < rows
            for item in self.paylines.values()
            if item.rules_version_id == rules_version_id
        )

    def list_paylines(self, rules_version_id: UUID) -> list[Payline]:
        return sorted(
            (item for item in self.paylines.values() if item.rules_version_id == rules_version_id),
            key=lambda item: (item.display_order, item.code, item.id),
        )

    def get_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
    ) -> Payline | None:
        item = self.paylines.get(payline_id)
        return item if item is not None and item.rules_version_id == rules_version_id else None

    def find_payline_by_code(
        self,
        rules_version_id: UUID,
        code: str,
    ) -> Payline | None:
        return next(
            (
                item
                for item in self.paylines.values()
                if item.rules_version_id == rules_version_id and item.code == code
            ),
            None,
        )

    def find_payline_by_row_path(
        self,
        rules_version_id: UUID,
        row_path: tuple[int, ...],
    ) -> Payline | None:
        return next(
            (
                item
                for item in self.paylines.values()
                if item.rules_version_id == rules_version_id and item.row_path == row_path
            ),
            None,
        )

    def add_payline(
        self,
        *,
        rules_version_id: UUID,
        code: str,
        name: str,
        row_path: tuple[int, ...],
        display_order: int,
        is_active: bool,
    ) -> Payline:
        item = Payline(
            id=uuid4(),
            rules_version_id=rules_version_id,
            code=code,
            name=name,
            row_path=row_path,
            display_order=display_order,
            is_active=is_active,
        )
        self.paylines[item.id] = item
        return item

    def save_payline(self, payline: Payline) -> Payline:
        self.paylines[payline.id] = payline
        return payline


def _client(repository: MemoryRulesRepository) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings.from_environment({}),
            rules_service_dependency=lambda: RulesService(repository),
        )
    )


def test_rules_version_create_list_get_and_update_contract() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)

    with _client(repository) as client:
        created = client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 3, "columns": 5, "spinCost": 10},
        )
        assert created.status_code == 201
        body = created.json()
        assert {
            "gameId": body["gameId"],
            "version": body["version"],
            "rows": body["rows"],
            "columns": body["columns"],
            "spinCost": body["spinCost"],
            "status": body["status"],
            "publishedAt": body["publishedAt"],
        } == {
            "gameId": str(game_id),
            "version": 1,
            "rows": 3,
            "columns": 5,
            "spinCost": 10,
            "status": "draft",
            "publishedAt": None,
        }

        rules_version_id = body["id"]
        updated = client.patch(
            f"/api/v1/admin/rules-versions/{rules_version_id}",
            json={"rows": 4, "spinCost": 25},
        )
        assert updated.status_code == 200
        assert updated.json()["rows"] == 4
        assert updated.json()["columns"] == 5
        assert updated.json()["spinCost"] == 25

        listed = client.get(f"/api/v1/admin/games/{game_id}/rules-versions")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [rules_version_id]
        assert client.get(f"/api/v1/admin/rules-versions/{rules_version_id}").status_code == 200


def test_rules_api_reports_validation_missing_and_immutable_errors() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)

    with _client(repository) as client:
        invalid = client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 0, "columns": 5, "spinCost": 10},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"

        missing = client.get(f"/api/v1/admin/rules-versions/{uuid4()}")
        assert missing.status_code == 404
        assert missing.json()["code"] == "RULES_VERSION_NOT_FOUND"

        created = client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 3, "columns": 5, "spinCost": 10},
        ).json()
        rules_version_id = UUID(created["id"])
        repository.items[rules_version_id] = replace(
            repository.items[rules_version_id],
            status=RulesVersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        immutable = client.patch(
            f"/api/v1/admin/rules-versions/{rules_version_id}",
            json={"spinCost": 15},
        )
        assert immutable.status_code == 409
        assert immutable.json()["code"] == "RULES_VERSION_IMMUTABLE"

        missing_game = client.get(f"/api/v1/admin/games/{uuid4()}/rules-versions")
        assert missing_game.status_code == 404
        assert missing_game.json()["code"] == "GAME_NOT_FOUND"


def test_payline_crud_uses_zero_based_paths_and_archive_only_delete() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)

    with _client(repository) as client:
        rules_version = client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 3, "columns": 5, "spinCost": 10},
        ).json()
        rules_version_id = rules_version["id"]
        created = client.post(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            json={
                "code": "line-v",
                "name": "V",
                "rowPath": [0, 1, 2, 1, 0],
                "displayOrder": 10,
            },
        )
        assert created.status_code == 201
        payline = created.json()
        payline_id = payline["id"]
        assert payline["rowPath"] == [0, 1, 2, 1, 0]
        assert payline["isActive"] is True

        updated = client.patch(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
            json={
                "name": "V line",
                "rowPath": [2, 1, 0, 1, 2],
                "displayOrder": 5,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["code"] == "line-v"
        assert updated.json()["rowPath"] == [2, 1, 0, 1, 2]

        listed = client.get(f"/api/v1/admin/rules-versions/{rules_version_id}/paylines")
        assert [item["id"] for item in listed.json()] == [payline_id]
        assert (
            client.get(
                f"/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}"
            ).status_code
            == 200
        )
        assert (
            client.delete(
                f"/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}"
            ).status_code
            == 204
        )
        assert repository.paylines[UUID(payline_id)].is_active is False
        reactivated = client.patch(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
            json={"isActive": True},
        )
        assert reactivated.json()["isActive"] is True


def test_payline_api_reports_duplicate_invalid_and_immutable_errors() -> None:
    game_id = uuid4()
    repository = MemoryRulesRepository(game_id)

    with _client(repository) as client:
        rules_version = client.post(
            f"/api/v1/admin/games/{game_id}/rules-versions",
            json={"rows": 3, "columns": 5, "spinCost": 10},
        ).json()
        rules_version_id = rules_version["id"]
        first = client.post(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            json={
                "code": "line-v",
                "name": "V",
                "rowPath": [0, 1, 2, 1, 0],
                "displayOrder": 10,
            },
        ).json()

        duplicate = client.post(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            json={
                "code": "line-copy",
                "name": "Copy",
                "rowPath": [0, 1, 2, 1, 0],
                "displayOrder": 20,
            },
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "DUPLICATE_PAYLINE"
        assert duplicate.json()["details"]["existingPaylineId"] == first["id"]

        invalid = client.post(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines",
            json={
                "code": "short",
                "name": "Short",
                "rowPath": [0, 1, 2],
                "displayOrder": 20,
            },
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "INVALID_PAYLINE_LENGTH"

        rules_id = UUID(rules_version_id)
        repository.items[rules_id] = replace(
            repository.items[rules_id],
            status=RulesVersionStatus.PUBLISHED,
            published_at=datetime.now(UTC),
        )
        immutable = client.patch(
            f"/api/v1/admin/rules-versions/{rules_version_id}/paylines/{first['id']}",
            json={"name": "Changed"},
        )
        assert immutable.status_code == 409
        assert immutable.json()["code"] == "RULES_VERSION_IMMUTABLE"
