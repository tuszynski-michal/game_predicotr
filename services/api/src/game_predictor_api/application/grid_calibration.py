"""Application boundary for immutable grid calibration and activation."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.grid_calibration import (
    GeometryCohort,
    GridCalibrationProfile,
    GridProfileActivation,
    GridProfileActivationAction,
    GridProfileActivationPreview,
    activation_command_sha256,
)
from game_predictor_api.domain.jobs import JobConflictError


class GridCalibrationRepository(Protocol):
    def create_candidate(
        self, *, game_id: UUID
    ) -> tuple[GeometryCohort, GridCalibrationProfile, bool]: ...

    def list_profiles(self, *, game_id: UUID, limit: int) -> tuple[GridCalibrationProfile, ...]: ...

    def preview_activation(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        action: GridProfileActivationAction,
    ) -> GridProfileActivationPreview: ...

    def activate(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        expected_profile_checksum_sha256: str,
        expected_current_profile_id: UUID | None,
        action: GridProfileActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
        command_sha256: str,
    ) -> tuple[GridProfileActivation, bool]: ...

    def list_activations(
        self, *, game_id: UUID, limit: int
    ) -> tuple[GridProfileActivation, ...]: ...


class GridCalibrationService:
    def __init__(self, repository: GridCalibrationRepository) -> None:
        self._repository = repository

    def create_candidate(
        self, *, game_id: UUID
    ) -> tuple[GeometryCohort, GridCalibrationProfile, bool]:
        return self._repository.create_candidate(game_id=game_id)

    def list_profiles(
        self, *, game_id: UUID, limit: int = 50
    ) -> tuple[GridCalibrationProfile, ...]:
        _validate_limit(limit)
        return self._repository.list_profiles(game_id=game_id, limit=limit)

    def preview_activation(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        action: GridProfileActivationAction,
    ) -> GridProfileActivationPreview:
        return self._repository.preview_activation(
            game_id=game_id, profile_id=profile_id, action=action
        )

    def activate(
        self,
        *,
        game_id: UUID,
        profile_id: UUID,
        expected_profile_checksum_sha256: str,
        expected_current_profile_id: UUID | None,
        action: GridProfileActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
    ) -> tuple[GridProfileActivation, bool]:
        normalized_actor = actor.strip()
        normalized_reason = None if reason is None else reason.strip() or None
        if not normalized_actor or len(normalized_actor) > 200:
            raise JobConflictError(
                "GRID_PROFILE_ACTOR_INVALID", "Activation actor must contain 1..200 characters."
            )
        if normalized_reason is not None and len(normalized_reason) > 2000:
            raise JobConflictError(
                "GRID_PROFILE_REASON_INVALID",
                "Activation reason must contain at most 2000 characters.",
            )
        command_sha256 = activation_command_sha256(
            game_id=game_id,
            profile_id=profile_id,
            expected_profile_checksum_sha256=expected_profile_checksum_sha256,
            expected_current_profile_id=expected_current_profile_id,
            action=action,
            actor=normalized_actor,
            reason=normalized_reason,
        )
        return self._repository.activate(
            game_id=game_id,
            profile_id=profile_id,
            expected_profile_checksum_sha256=expected_profile_checksum_sha256,
            expected_current_profile_id=expected_current_profile_id,
            action=action,
            actor=normalized_actor,
            reason=normalized_reason,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )

    def list_activations(
        self, *, game_id: UUID, limit: int = 50
    ) -> tuple[GridProfileActivation, ...]:
        _validate_limit(limit)
        return self._repository.list_activations(game_id=game_id, limit=limit)


def _validate_limit(limit: int) -> None:
    if not 1 <= limit <= 200:
        raise JobConflictError("GRID_PROFILE_LIMIT_INVALID", "limit must be 1..200.")


__all__ = ["GridCalibrationRepository", "GridCalibrationService"]
