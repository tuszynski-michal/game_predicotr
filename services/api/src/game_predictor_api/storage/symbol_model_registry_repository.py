"""Transactional append-only registry for active symbol-model iterations."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryRepository
from game_predictor_api.domain.jobs import JobConflictError, JobNotFoundError
from game_predictor_api.domain.symbol_model_iterations import SymbolModelIterationStatus
from game_predictor_api.domain.symbol_model_registry import (
    SymbolModelActivation,
    SymbolModelActivationAction,
    SymbolModelActivationPreview,
)
from game_predictor_api.storage.lab_symbol_candidate_validation import require_iteration_candidate
from game_predictor_api.storage.models import (
    GameModel,
    GameSymbolModelActivationModel,
    SymbolModelIterationModel,
)


class SqlAlchemySymbolModelRegistryRepository(SymbolModelRegistryRepository):
    def __init__(self, session: Session, *, artifact_root: Path | None = None) -> None:
        self._session = session
        self._artifact_root = artifact_root

    def preview(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID | None,
        action: SymbolModelActivationAction,
    ) -> SymbolModelActivationPreview:
        current = self._current(game_id)
        if action is SymbolModelActivationAction.DEACTIVATE:
            if (
                model_iteration_id is not None
                or current is None
                or current.model_iteration_id is None
            ):
                raise JobConflictError(
                    "SYMBOL_MODEL_NOT_ACTIVE", "No active model can be disabled."
                )
            return SymbolModelActivationPreview(
                game_id=game_id,
                model_iteration_id=None,
                candidate_manifest_checksum_sha256=None,
                current_model_iteration_id=current.model_iteration_id,
                action=action,
                can_activate=True,
            )
        if model_iteration_id is None:
            raise JobConflictError("SYMBOL_MODEL_ACTIVATION_TARGET_INVALID", "Target is required.")
        target = self._eligible_target(game_id, model_iteration_id)
        self._validate_transition(
            game_id=game_id,
            target_id=model_iteration_id,
            current=current,
            action=action,
        )
        assert target.candidate_manifest_checksum_sha256 is not None
        return SymbolModelActivationPreview(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            candidate_manifest_checksum_sha256=target.candidate_manifest_checksum_sha256,
            current_model_iteration_id=(None if current is None else current.model_iteration_id),
            action=action,
            can_activate=True,
            pilot_summary=(
                dict(target.configuration_payload) if target.origin == "lab_import" else None
            ),
        )

    def activate(
        self,
        *,
        game_id: UUID,
        model_iteration_id: UUID | None,
        expected_manifest_checksum_sha256: str | None,
        expected_current_model_iteration_id: UUID | None,
        action: SymbolModelActivationAction,
        actor: str,
        reason: str | None,
        idempotency_key: UUID,
        command_sha256: str,
    ) -> tuple[SymbolModelActivation, bool]:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            raise JobNotFoundError("GAME_NOT_FOUND", "Game does not exist.")
        existing = self._session.scalar(
            select(GameSymbolModelActivationModel).where(
                GameSymbolModelActivationModel.game_id == game_id,
                GameSymbolModelActivationModel.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.command_sha256 != command_sha256:
                raise JobConflictError(
                    "SYMBOL_MODEL_ACTIVATION_IDEMPOTENCY_CONFLICT",
                    "The idempotency key was already used for another activation command.",
                )
            return _to_domain(existing), False
        if action is SymbolModelActivationAction.DEACTIVATE:
            if model_iteration_id is not None or expected_manifest_checksum_sha256 is not None:
                raise JobConflictError(
                    "SYMBOL_MODEL_ACTIVATION_TARGET_INVALID", "Deactivation has no target."
                )
            target = None
        else:
            if model_iteration_id is None:
                raise JobConflictError(
                    "SYMBOL_MODEL_ACTIVATION_TARGET_INVALID", "Target is required."
                )
            target = self._eligible_target(game_id, model_iteration_id)
        if (
            target is not None
            and target.candidate_manifest_checksum_sha256 != expected_manifest_checksum_sha256
        ):
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVATION_PREVIEW_STALE",
                "Candidate manifest differs from the explicitly confirmed preview.",
            )
        current = self._current(game_id)
        current_id = None if current is None else current.model_iteration_id
        if current_id != expected_current_model_iteration_id:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVATION_PREVIEW_STALE",
                "The active model changed after preview; refresh and confirm again.",
            )
        if action is SymbolModelActivationAction.DEACTIVATE and current_id is None:
            raise JobConflictError("SYMBOL_MODEL_NOT_ACTIVE", "No active model can be disabled.")
        self._validate_transition(
            game_id=game_id,
            target_id=model_iteration_id,
            current=current,
            action=action,
        )
        record = GameSymbolModelActivationModel(
            game_id=game_id,
            model_iteration_id=model_iteration_id,
            previous_model_iteration_id=current_id,
            action=action.value,
            activation_number=(1 if current is None else current.activation_number + 1),
            actor=actor,
            reason=reason,
            idempotency_key=idempotency_key,
            command_sha256=command_sha256,
        )
        self._session.add(record)
        try:
            self._session.flush()
        except IntegrityError as error:
            raise JobConflictError(
                "SYMBOL_MODEL_ACTIVATION_WRITE_CONFLICT",
                "The model activation changed concurrently; retry after refresh.",
            ) from error
        self._session.refresh(record)
        return _to_domain(record), True

    def list(self, *, game_id: UUID, limit: int) -> tuple[SymbolModelActivation, ...]:
        records = self._session.scalars(
            select(GameSymbolModelActivationModel)
            .where(GameSymbolModelActivationModel.game_id == game_id)
            .order_by(
                GameSymbolModelActivationModel.activation_number.desc(),
            )
            .limit(limit)
        ).all()
        return tuple(_to_domain(record) for record in records)

    def _eligible_target(
        self, game_id: UUID, model_iteration_id: UUID
    ) -> SymbolModelIterationModel:
        target = self._session.get(SymbolModelIterationModel, model_iteration_id)
        if target is None or target.game_id != game_id:
            raise JobNotFoundError(
                "SYMBOL_MODEL_ITERATION_NOT_FOUND", "Symbol model iteration does not exist."
            )
        if (
            target.status != SymbolModelIterationStatus.CANDIDATE_READY.value
            or target.candidate_manifest_checksum_sha256 is None
            or target.candidate_manifest_relative_path is None
            or target.gate_report_checksum_sha256 is None
            or target.gate_report_relative_path is None
        ):
            raise JobConflictError(
                "SYMBOL_MODEL_CANDIDATE_NOT_READY",
                "Only a candidate with a complete passed gate may be activated.",
            )
        if target.origin == "lab_import":
            if self._artifact_root is None:
                raise JobConflictError(
                    "LAB_CANDIDATE_STORAGE_REQUIRED", "Managed candidate storage is unavailable."
                )
            require_iteration_candidate(self._session, self._artifact_root, target)
        return target

    def _current(self, game_id: UUID) -> GameSymbolModelActivationModel | None:
        return self._session.scalar(
            select(GameSymbolModelActivationModel)
            .where(GameSymbolModelActivationModel.game_id == game_id)
            .order_by(
                GameSymbolModelActivationModel.activation_number.desc(),
            )
            .limit(1)
        )

    def _validate_transition(
        self,
        *,
        game_id: UUID,
        target_id: UUID | None,
        current: GameSymbolModelActivationModel | None,
        action: SymbolModelActivationAction,
    ) -> None:
        current_id = None if current is None else current.model_iteration_id
        if current_id == target_id:
            raise JobConflictError(
                "SYMBOL_MODEL_ALREADY_ACTIVE", "The selected model is already active."
            )
        if action is SymbolModelActivationAction.ROLLBACK:
            historical = self._session.scalar(
                select(GameSymbolModelActivationModel.id)
                .where(
                    GameSymbolModelActivationModel.game_id == game_id,
                    GameSymbolModelActivationModel.model_iteration_id == target_id,
                )
                .limit(1)
            )
            if historical is None:
                raise JobConflictError(
                    "SYMBOL_MODEL_ROLLBACK_TARGET_INVALID",
                    "Rollback target was never active for this game.",
                )


def _to_domain(record: GameSymbolModelActivationModel) -> SymbolModelActivation:
    return SymbolModelActivation(
        id=record.id,
        game_id=record.game_id,
        model_iteration_id=record.model_iteration_id,
        previous_model_iteration_id=record.previous_model_iteration_id,
        action=SymbolModelActivationAction(record.action),
        activation_number=record.activation_number,
        actor=record.actor,
        reason=record.reason,
        idempotency_key=record.idempotency_key,
        command_sha256=record.command_sha256,
        created_at=record.created_at,
    )


__all__ = ["SqlAlchemySymbolModelRegistryRepository"]
