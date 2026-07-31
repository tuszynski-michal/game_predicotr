from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetLayoutPage,
    DatasetNotFoundError,
    DatasetValidationCheck,
    DatasetValidationCheckCode,
    DatasetValidationCheckStatus,
    DatasetValidationReport,
    DatasetVersion,
    DatasetVersionStatus,
    LayoutValidationRecord,
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
            expected_layout_count=1000,
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

    def get_validation_report(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationReport:
        item = self.items.get(dataset_version_id)
        if item is None:
            raise DatasetNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
            )
        if item.generator_version != "mock-v1":
            raise DatasetConflictError(
                "DATASET_VALIDATION_REQUIRES_JOB",
                "This dataset must be validated by a worker job.",
            )
        return DatasetValidationReport(
            dataset_version_id=item.id,
            dataset_version=item.version,
            ready_for_publication=True,
            declared_layout_count=1000,
            actual_layout_count=1000,
            min_sequence_number=1,
            max_sequence_number=1000,
            checks=(
                DatasetValidationCheck(
                    code=DatasetValidationCheckCode.DUPLICATE_SIGNATURE,
                    status=DatasetValidationCheckStatus.WARNING,
                    issue_count=6,
                    message="Duplicate layout signatures are allowed and were found.",
                ),
            ),
            duplicate_signature_group_count=6,
            duplicate_signature_affected_layout_count=12,
            duplicate_signature_excess_layout_count=6,
            duplicate_signatures=(),
            duplicate_signatures_truncated=False,
        )

    def list_layouts(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> DatasetLayoutPage:
        item = self.get_dataset_version(dataset_version_id)
        records = tuple(
            LayoutValidationRecord(
                sequence_number=sequence_number,
                signature=f"{sequence_number:02d}" * 15,
                cells=tuple([sequence_number] * 15),
            )
            for sequence_number in range(
                after_sequence_number + 1,
                min(after_sequence_number + limit, 3) + 1,
            )
        )
        return DatasetLayoutPage(
            dataset_version_id=item.id,
            dataset_version=item.version,
            rows=item.rows,
            columns=item.columns,
            items=records,
            next_after_sequence_number=(
                records[-1].sequence_number
                if records and records[-1].sequence_number < 3
                else None
            ),
        )

    def publish_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion:
        item = self.get_dataset_version(dataset_version_id)
        if item.status is not DatasetVersionStatus.STAGING:
            raise DatasetConflictError(
                "DATASET_VERSION_NOT_STAGING",
                "Only staging can be published.",
            )
        published = DatasetVersion(
            id=item.id,
            game_id=item.game_id,
            version=item.version,
            rows=item.rows,
            columns=item.columns,
            signature_cell_width=item.signature_cell_width,
            expected_layout_count=item.expected_layout_count,
            layout_count=item.layout_count,
            status=DatasetVersionStatus.PUBLISHED,
            generation_seed=item.generation_seed,
            generator_version=item.generator_version,
            source_job_id=item.source_job_id,
            created_at=item.created_at,
            published_at=datetime.now(UTC),
        )
        self.items[item.id] = published
        return published

    def archive_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion:
        item = self.get_dataset_version(dataset_version_id)
        if item.status is DatasetVersionStatus.ARCHIVED:
            return item
        if item.status is not DatasetVersionStatus.PUBLISHED:
            raise DatasetConflictError(
                "DATASET_VERSION_NOT_PUBLISHED",
                "Only published can be archived.",
            )
        archived = DatasetVersion(
            id=item.id,
            game_id=item.game_id,
            version=item.version,
            rows=item.rows,
            columns=item.columns,
            signature_cell_width=item.signature_cell_width,
            expected_layout_count=item.expected_layout_count,
            layout_count=item.layout_count,
            status=DatasetVersionStatus.ARCHIVED,
            generation_seed=item.generation_seed,
            generator_version=item.generator_version,
            source_job_id=item.source_job_id,
            created_at=item.created_at,
            published_at=item.published_at,
        )
        self.items[item.id] = archived
        return archived


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
        report = client.get(
            f"/api/v1/admin/dataset-versions/{dataset_id}/validation-report"
        )
        assert report.status_code == 200
        assert report.json() == {
            "datasetVersionId": dataset_id,
            "datasetVersion": 1,
            "readyForPublication": True,
            "declaredLayoutCount": 1000,
            "actualLayoutCount": 1000,
            "minSequenceNumber": 1,
            "maxSequenceNumber": 1000,
            "checks": [
                {
                    "code": "DUPLICATE_SIGNATURE",
                    "status": "warning",
                    "issueCount": 6,
                    "message": (
                        "Duplicate layout signatures are allowed and were found."
                    ),
                    "sequenceNumbers": [],
                    "mobileCodes": [],
                    "truncated": False,
                }
            ],
            "duplicateSignatureGroupCount": 6,
            "duplicateSignatureAffectedLayoutCount": 12,
            "duplicateSignatureExcessLayoutCount": 6,
            "duplicateSignatures": [],
            "duplicateSignaturesTruncated": False,
        }
        layouts = client.get(
            f"/api/v1/admin/dataset-versions/{dataset_id}/layouts",
            params={"afterSequenceNumber": 0, "limit": 2},
        )
        assert layouts.status_code == 200
        assert [
            item["sequenceNumber"] for item in layouts.json()["items"]
        ] == [1, 2]
        assert layouts.json()["nextAfterSequenceNumber"] == 2

        published = client.post(
            f"/api/v1/admin/dataset-versions/{dataset_id}/publish"
        )
        assert published.status_code == 200
        assert published.json()["status"] == "published"
        assert published.json()["publishedAt"] is not None

        archived = client.delete(
            f"/api/v1/admin/dataset-versions/{dataset_id}"
        )
        assert archived.status_code == 204
        assert service.items[UUID(dataset_id)].status is DatasetVersionStatus.ARCHIVED


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

        imported_id = uuid4()
        service.items[imported_id] = DatasetVersion(
            id=imported_id,
            game_id=game_id,
            version=1,
            rows=3,
            columns=5,
            signature_cell_width=2,
            expected_layout_count=500000,
            layout_count=500000,
            status=DatasetVersionStatus.STAGING,
            generation_seed=1,
            generator_version="import-v1",
            source_job_id=uuid4(),
            created_at=datetime.now(UTC),
            published_at=None,
        )
        requires_job = client.get(
            f"/api/v1/admin/dataset-versions/{imported_id}/validation-report"
        )
        assert requires_job.status_code == 409
        assert (
            requires_job.json()["code"]
            == "DATASET_VALIDATION_REQUIRES_JOB"
        )
