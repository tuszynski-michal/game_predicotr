"""Application boundary for durable symbol-model training commands."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import Job, JobConflictError, JobNotFoundError
from game_predictor_api.domain.symbol_model_iterations import (
    SymbolModelIteration,
    SymbolTrainingConfiguration,
)


class SymbolModelIterationRepository(Protocol):
    def create_training(
        self,
        *,
        game_id: UUID,
        cohort_id: UUID,
        idempotency_key: UUID,
        configuration: SymbolTrainingConfiguration,
    ) -> tuple[SymbolModelIteration, Job, bool]: ...

    def get(self, *, game_id: UUID, iteration_id: UUID) -> SymbolModelIteration | None: ...

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelIteration, ...]: ...


class SymbolModelIterationService:
    def __init__(self, repository: SymbolModelIterationRepository) -> None:
        self._repository = repository

    def create_training(
        self,
        *,
        game_id: UUID,
        cohort_id: UUID,
        idempotency_key: UUID,
        configuration: SymbolTrainingConfiguration,
    ) -> tuple[SymbolModelIteration, Job, bool]:
        try:
            configuration.validate()
        except ValueError as error:
            raise JobConflictError("SYMBOL_TRAINING_CONFIG_INVALID", str(error)) from error
        return self._repository.create_training(
            game_id=game_id,
            cohort_id=cohort_id,
            idempotency_key=idempotency_key,
            configuration=configuration,
        )

    def get(self, *, game_id: UUID, iteration_id: UUID) -> SymbolModelIteration:
        value = self._repository.get(game_id=game_id, iteration_id=iteration_id)
        if value is None:
            raise JobNotFoundError(
                "SYMBOL_MODEL_ITERATION_NOT_FOUND", "Symbol model iteration does not exist."
            )
        return value

    def list(self, *, game_id: UUID, limit: int = 50) -> tuple[SymbolModelIteration, ...]:
        if not 1 <= limit <= 200:
            raise JobConflictError("SYMBOL_MODEL_ITERATION_LIMIT_INVALID", "limit must be 1..200.")
        return self._repository.list(game_id=game_id, limit=limit)


__all__ = ["SymbolModelIterationRepository", "SymbolModelIterationService"]
