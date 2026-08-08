"""Application boundary for explicit symbol-model activation and rollback."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_registry import (
    SymbolModelActivation,
    SymbolModelActivationAction,
    SymbolModelActivationPreview,
    activation_command_sha256,
)


class SymbolModelRegistryRepository(Protocol):
    def preview(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        action: SymbolModelActivationAction,
    ) -> SymbolModelActivationPreview: ...

    def activate(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_current_model_iteration_id: UUID | None,
        action: SymbolModelActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
        command_sha256: str,
    ) -> tuple[SymbolModelActivation, bool]: ...

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelActivation, ...]: ...


class SymbolModelRegistryService:
    def __init__(self, repository: SymbolModelRegistryRepository) -> None:
        self._repository = repository

    def preview(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        action: SymbolModelActivationAction,
    ) -> SymbolModelActivationPreview:
        return self._repository.preview(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            action=action,
        )

    def activate(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID,
        expected_manifest_checksum_sha256: str,
        expected_current_model_iteration_id: UUID | None,
        action: SymbolModelActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
    ) -> tuple[SymbolModelActivation, bool]:
        normalized_actor = actor.strip()
        normalized_reason = None if reason is None else reason.strip() or None
        if not normalized_actor or len(normalized_actor) > 200:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTOR_INVALID", "Activation actor must contain 1..200 characters."
            )
        if normalized_reason is not None and len(normalized_reason) > 2000:
            raise JobConflictError(
                "SYMBOL_MODEL_REASON_INVALID",
                "Activation reason must contain at most 2000 characters.",
            )
        command_sha256 = activation_command_sha256(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            expected_current_model_iteration_id=expected_current_model_iteration_id,
            action=action,
            actor=normalized_actor,
            reason=normalized_reason,
        )
        return self._repository.activate(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            expected_manifest_checksum_sha256=expected_manifest_checksum_sha256,
            expected_current_model_iteration_id=expected_current_model_iteration_id,
            action=action,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )

    def list(self, *, game_id: UUID, limit: int = 50) -> tuple[SymbolModelActivation, ...]:
        if not 1 <= limit <= 200:
            raise JobConflictError("SYMBOL_MODEL_ACTIVATION_LIMIT_INVALID", "limit must be 1..200.")
        return self._repository.list(game_id=game_id, limit=limit)


__all__ = ["SymbolModelRegistryRepository", "SymbolModelRegistryService"]
