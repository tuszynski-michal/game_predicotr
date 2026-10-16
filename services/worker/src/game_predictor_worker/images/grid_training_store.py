"""SQL facts for the grid-training supervisor (TASK-0996).

Cohort reads use the routed session of the claimed game. The public model catalogue is
read and written through a plain session of the same engine, as the API does, because it
holds no game payload and must not enter the game storage router.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.storage.grid_model_registry import (
    GridModelArtifactInspector,
    SqlAlchemyGridModelRegistryRepository,
)
from game_predictor_api.storage.grid_training_cohort_repository import (
    SqlAlchemyGridTrainingCohortRepository,
)
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..jobs.runtime import JobHandlerError


class SqlGridTrainingStore:
    def __init__(
        self, session_factory: sessionmaker[Session], engine: Engine, artifact_root: Path
    ) -> None:
        self.session_factory, self.engine = session_factory, engine
        self.artifact_root = artifact_root

    def _service(self, session: Session) -> GridTrainingCohortService:
        return GridTrainingCohortService(
            SqlAlchemyGridTrainingCohortRepository(session, self.artifact_root), self.artifact_root
        )

    def cohort(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]:
        with self.session_factory() as session:
            try:
                service = self._service(session)
                service.repository.bind(game_id)
                row = service.repository.cohort(game_id, cohort_id)
                return {**service.repository.view(row), "manifestPath": row.manifest_path}
            except GridCohortError as error:
                raise JobHandlerError(error.code, error.message) from error

    def eligibility(self, game_id: UUID, cohort_id: UUID) -> Mapping[str, Any]:
        with self.session_factory() as session:
            try:
                return self._service(session).eligibility(game_id, cohort_id)
            except GridCohortError as error:
                raise JobHandlerError(error.code, error.message) from error

    def _registry(self, session: Session) -> GridModelRegistryService:
        return GridModelRegistryService(
            SqlAlchemyGridModelRegistryRepository(session),
            GridModelArtifactInspector(self.artifact_root),
        )

    def base_version(self, version_id: UUID) -> Mapping[str, Any]:
        with Session(self.engine) as session:
            record = SqlAlchemyGridModelRegistryRepository(session).version(version_id)
            if record is None:
                raise JobHandlerError("GRID_TRAINING_BASE_MISSING", "Base version is unknown.")
            try:
                view = self._registry(session).view(record, include_eligibility=False)
            except GridModelRegistryError as error:
                raise JobHandlerError(error.code, error.message) from error
            if not view["available"]:
                raise JobHandlerError("GRID_TRAINING_BASE_UNAVAILABLE", str(view["reasonCode"]))
            return dict(json.loads(record.manifest_json))

    def register(self, key: UUID, payload: dict[str, Any]) -> Mapping[str, Any]:
        with Session(self.engine) as session:
            try:
                view = self._registry(session).register(key, payload)
                session.commit()
            except GridModelRegistryError as error:
                session.rollback()
                raise JobHandlerError(error.code, error.message) from error
            return view
