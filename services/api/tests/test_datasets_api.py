from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetNotFoundError,
    DatasetVersion,
    DatasetVersionStatus,
)
from game_predictor_api.main import create_app


class FakeDatasetService:
    def __init__(self, game_id: UUID) -> None:
        self.game_id = game_id
        self.items: dict[UUID, DatasetVersion] = {}
        self.last_request: tuple[UUID, UUID, int] | None = None

    def list_dataset_versions(self, game_id: UUID) -> list[DatasetVersion]:
        if game_id != self.game_id:
            raise DatasetNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        return list(self.items.values())

    def get_dataset_version(self, dataset_version_id: UUID) -> DatasetVersion:
        item = self.items.get(dataset_version_id)
        if item is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
            )
        return item

    def generate_mock_dataset(
        self,
        game_id: UUID,
        *,
        rules_version_id: UUID,
        seed: int,
    ) -> DatasetVersion:
        if game_id != self.game_id:
            raise DatasetNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        if rules_version_id == UUID(int=1):
            raise DatasetConflictError(
                "RULES_VERSION_NOT_PUBLISHED",
                "Rules version is not published.",
            )
        self.last_request = (game_id, rules_version_id, seed)
        item = DatasetVersion(
            id=uuid4(),
            game_id=game_id,
            version=len(self.items) + 1,
            rows=3,
            columns=5,
            signature_cell_width=2,
            layout_count=1000,
            status=DatasetVersionStatus.STAGING,
            generation_seed=seed,
            generator_version="mock-v1",
            source_job_id=None,
            created_at=datetime.now(UTC),
            published_at=None,
        )
        self.items[item.id] = item
        return item


def _client(service: FakeDatasetService) -> TestClient:
    return TestClient(
        create_app(
            ApiSettings.from_environment({}),
            dataset_service_dependency=lambda: service,
        )
    )


def test_mock_generation_list_and_get_contract() -> None:
    game_id = uuid4()
    rules_version_id = uuid4()
    service = FakeDatasetService(game_id)

    with _client(service) as client:
        created = client.post(
            f"/api/v1/admin/games/{game_id}/dataset-versions/mock",
            json={"rulesVersionId": str(rules_version_id), "seed": 71401},
        )
        assert created.status_code == 201
        body = created.json()
        assert {
            "gameId": body["gameId"],
            "version": body["version"],
            "rows": body["rows"],
            "columns": body["columns"],
            "signatureCellWidth": body["signatureCellWidth"],
            "layoutCount": body["layoutCount"],
            "status": body["status"],
            "generationSeed": body["generationSeed"],
            "generatorVersion": body["generatorVersion"],
            "publishedAt": body["publishedAt"],
        } == {
            "gameId": str(game_id),
            "version": 1,
            "rows": 3,
            "columns": 5,
            "signatureCellWidth": 2,
            "layoutCount": 1000,
            "status": "staging",
            "generationSeed": 71401,
            "generatorVersion": "mock-v1",
            "publishedAt": None,
        }
        assert service.last_request == (game_id, rules_version_id, 71401)
        dataset_id = body["id"]
        assert (
            client.get(
                f"/api/v1/admin/dataset-versions/{dataset_id}"
            ).status_code
            == 200
        )
        listed = client.get(
            f"/api/v1/admin/games/{game_id}/dataset-versions"
        )
        assert [item["id"] for item in listed.json()] == [dataset_id]


def test_dataset_api_reports_validation_conflict_and_missing() -> None:
    game_id = uuid4()
    service = FakeDatasetService(game_id)

    with _client(service) as client:
        invalid = client.post(
            f"/api/v1/admin/games/{game_id}/dataset-versions/mock",
            json={"rulesVersionId": str(uuid4()), "seed": -1},
        )
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"

        conflict = client.post(
            f"/api/v1/admin/games/{game_id}/dataset-versions/mock",
            json={"rulesVersionId": str(UUID(int=1)), "seed": 1},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "RULES_VERSION_NOT_PUBLISHED"

        missing = client.get(
            f"/api/v1/admin/dataset-versions/{uuid4()}"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "DATASET_VERSION_NOT_FOUND"
