"""SQL facts for the grid model evaluation job (TASK-0997, D-559).

Cohort facts are read in a session bound to that game only; the public catalogue and
reports use a plain session of the same engine, as the API does. Proofs reuse the
application's per-game ``prove_cohort`` protocol.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.application.grid_model_evaluation import EVALUATOR_ACTOR, prove_cohort
from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_model_evaluation import PRODUCER
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage import grid_model_evaluation_repository as evidence
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..jobs.runtime import JobHandlerError
from .grid_training_store import SqlGridTrainingStore


class SqlGridModelEvaluationStore:
    def __init__(
        self, session_factory: sessionmaker[Session], engine: Engine, artifact_root: Path
    ) -> None:
        self.session_factory, self.engine = session_factory, engine
        self.artifact_root = artifact_root
        self._cohorts = SqlGridTrainingStore(session_factory, engine, artifact_root)

    def catalogue(
        self, version_id: UUID, base_version_id: UUID
    ) -> tuple[dict[str, Any], dict[str, Any], str]:
        with Session(self.engine) as session:
            registry = GridModelRegistryService(
                SqlAlchemyGridModelRegistryRepository(session),
                GridModelArtifactInspector(self.artifact_root),
            )
            records = []
            for identifier in (version_id, base_version_id):
                record = registry.repository.version(identifier)
                if record is None:
                    raise JobHandlerError("GRID_EVALUATION_MODEL_MISSING", "Model is unknown.")
                try:
                    view = registry.view(record, include_eligibility=False)
                except GridModelRegistryError as error:
                    raise JobHandlerError(error.code, error.message) from error
                if not view["available"]:
                    raise JobHandlerError(
                        "GRID_EVALUATION_CANDIDATE_UNAVAILABLE", str(view["reasonCode"])
                    )
                records.append(record)
            candidate, base = records
            return (
                dict(json.loads(candidate.manifest_json)),
                dict(json.loads(base.manifest_json)),
                str(base.manifest_sha256),
            )

    def cohort(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]:
        return self._cohorts.cohort(game_id, cohort_id)

    def eligibility(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]:
        return self._cohorts.eligibility(game_id, cohort_id)

    def recordings(self, game_id: UUID, cohort_id: UUID) -> dict[str, str]:
        return self._cohorts.recordings(game_id, cohort_id)

    def store_report(
        self, report_id: UUID, version_id: UUID, report_json: str, report_sha256: str
    ) -> None:
        with Session(self.engine) as session:
            try:
                evidence.store_report(
                    session,
                    report_id=report_id,
                    version_id=version_id,
                    producer=PRODUCER,
                    report_json=report_json,
                    report_sha256=report_sha256,
                )
                session.commit()
            except GridModelRegistryError as error:
                session.rollback()
                raise JobHandlerError(error.code, error.message) from error

    def prove(self, report_id: UUID, game_id: UUID, cohort_id: UUID, manifest_sha256: str) -> None:
        try:
            prove_cohort(
                self.session_factory,
                self.artifact_root,
                report_id=report_id,
                game_id=game_id,
                cohort_id=cohort_id,
                manifest_sha256=manifest_sha256,
                actor=EVALUATOR_ACTOR,
            )
        except GridCohortError as error:
            raise JobHandlerError(error.code, error.message) from error
