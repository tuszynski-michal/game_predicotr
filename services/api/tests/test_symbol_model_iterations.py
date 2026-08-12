from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from game_predictor_api.application.symbol_model_iterations import (
    SymbolModelIterationRepository,
    SymbolModelIterationService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.domain.symbol_model_iterations import (
    SymbolModelIteration,
    SymbolModelIterationStatus,
    SymbolTrainingConfiguration,
)
from game_predictor_api.main import create_app


class MemoryIterationRepository(SymbolModelIterationRepository):
    def __init__(self, game_id: UUID, cohort_id: UUID) -> None:
        self.game_id = game_id
        self.cohort_id = cohort_id
        self.values: dict[UUID, tuple[SymbolModelIteration, Job]] = {}

    def create_training(
        self,
        *,
        game_id: UUID,
        cohort_id: UUID,
        idempotency_key: UUID,
        configuration: SymbolTrainingConfiguration,
    ) -> tuple[SymbolModelIteration, Job, bool]:
        if idempotency_key in self.values:
            iteration, job = self.values[idempotency_key]
            return iteration, job, False
        assert game_id == self.game_id
        assert cohort_id == self.cohort_id
        now = datetime.now(UTC)
        job = create_job(
            JobType.SYMBOL_TRAINING,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "cohort_id": str(cohort_id),
                "cohort_checksum_sha256": "a" * 64,
                "configuration": configuration.to_payload(),
                "configuration_fingerprint": configuration.fingerprint,
                "idempotency_key": str(idempotency_key),
            },
        )
        iteration = SymbolModelIteration(
            id=uuid4(),
            game_id=game_id,
            cohort_id=cohort_id,
            job_id=job.id,
            iteration_number=len(self.values) + 1,
            status=SymbolModelIterationStatus.CREATED,
            configuration_fingerprint=configuration.fingerprint,
            configuration_payload=configuration.to_payload(),
            dataset_manifest_checksum_sha256=None,
            dataset_manifest_relative_path=None,
            checkpoint_checksum_sha256=None,
            checkpoint_relative_path=None,
            gate_configuration_fingerprint=None,
            gate_configuration_payload=None,
            candidate_manifest_checksum_sha256=None,
            candidate_manifest_relative_path=None,
            gate_report_checksum_sha256=None,
            gate_report_relative_path=None,
            gate_metrics={},
            rejection_reasons=(),
            last_completed_epoch=0,
            partial_metrics={},
            error_code=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self.values[idempotency_key] = (iteration, job)
        return iteration, job, True

    def get(self, *, game_id: UUID, iteration_id: UUID) -> SymbolModelIteration | None:
        return next(
            (
                iteration
                for iteration, _job in self.values.values()
                if iteration.game_id == game_id and iteration.id == iteration_id
            ),
            None,
        )

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelIteration, ...]:
        return tuple(
            iteration for iteration, _job in self.values.values() if iteration.game_id == game_id
        )[:limit]


def _settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings.from_environment(
        {
            "GAME_PREDICTOR_DATABASE_URL": (
                "postgresql+psycopg://unused:unused@localhost:5432/unused"
            ),
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
        }
    )


def test_create_symbol_training_is_fast_idempotent_and_visible_as_job(tmp_path: Path) -> None:
    game_id = uuid4()
    cohort_id = uuid4()
    repository = MemoryIterationRepository(game_id, cohort_id)
    service = SymbolModelIterationService(repository)
    app = create_app(
        _settings(tmp_path),
        symbol_model_iteration_service_dependency=lambda: service,
    )
    idempotency_key = uuid4()
    body = {"cohortId": str(cohort_id), "idempotencyKey": str(idempotency_key)}
    with TestClient(app) as client:
        first = client.post(f"/api/v1/admin/games/{game_id}/symbol-model-iterations", json=body)
        second = client.post(f"/api/v1/admin/games/{game_id}/symbol-model-iterations", json=body)
        listed = client.get(f"/api/v1/admin/games/{game_id}/symbol-model-iterations")

    assert first.status_code == 200
    assert first.json()["created"] is True
    assert first.json()["job"]["jobType"] == "symbol_training"
    assert first.json()["job"]["status"] == "created"
    assert second.status_code == 200
    assert second.json()["created"] is False
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    assert listed.status_code == 200
    assert [value["id"] for value in listed.json()] == [first.json()["iteration"]["id"]]
