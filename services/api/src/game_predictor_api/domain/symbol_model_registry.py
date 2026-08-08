"""Immutable activation history for game-scoped symbol models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class SymbolModelActivationAction(StrEnum):
    ACTIVATE = "activate"
    ROLLBACK = "rollback"


@dataclass(frozen=True, slots=True)
class SymbolModelActivation:
    id: UUID
    game_id: UUID
    model_iteration_id: UUID
    previous_model_iteration_id: UUID | None
    action: SymbolModelActivationAction
    activation_number: int
    actor: str
    reason: str | None
    idempotency_key: UUID
    command_sha256: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SymbolModelActivationPreview:
    game_id: UUID
    model_iteration_id: UUID
    candidate_manifest_checksum_sha256: str
    current_model_iteration_id: UUID | None
    action: SymbolModelActivationAction
    can_activate: bool


def activation_command_sha256(
    *,
    game_id: UUID,
    model_iteration_id: UUID,
    expected_manifest_checksum_sha256: str,
    expected_current_model_iteration_id: UUID | None,
    action: SymbolModelActivationAction,
    actor: str,
    reason: str | None,
) -> str:
    payload = {
        "action": action.value,
        "actor": actor.strip(),
        "expectedManifestChecksumSha256": expected_manifest_checksum_sha256,
        "expectedCurrentModelIterationId": (
            None
            if expected_current_model_iteration_id is None
            else str(expected_current_model_iteration_id)
        ),
        "gameId": str(game_id),
        "modelIterationId": str(model_iteration_id),
        "reason": None if reason is None else reason.strip() or None,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


__all__ = [
    "SymbolModelActivation",
    "SymbolModelActivationAction",
    "SymbolModelActivationPreview",
    "activation_command_sha256",
]
