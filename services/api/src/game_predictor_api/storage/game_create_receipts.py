"""Public catalogue create-command ledger, independent of a game's lifetime."""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_model_registry import canonical_json, descriptor_sha256
from game_predictor_api.storage.grid_model_registry_models import GameCreateReceiptModel


class SqlAlchemyGameCreateReceiptRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def receipt(self, key: UUID) -> GameCreateReceiptModel | None:
        return self.session.get(GameCreateReceiptModel, key)

    def game_receipt(self, game_id: UUID) -> GameCreateReceiptModel | None:
        return self.session.scalar(
            select(GameCreateReceiptModel).where(GameCreateReceiptModel.game_id == game_id)
        )

    def record(self, command: dict[str, Any], reservation: dict[str, Any]) -> None:
        # Public control writes share the reservation transaction. ORM pending
        # game_id records would incorrectly enter the MIGRATING data-plane gate.
        self.session.connection().execute(
            cast(Table, GameCreateReceiptModel.__table__)
            .insert()
            .values(
                idempotency_key=UUID(command["idempotencyKey"]),
                game_id=UUID(reservation["gameId"]),
                command_json=canonical_json(command),
                command_sha256=descriptor_sha256(command),
                reservation_json=canonical_json(reservation),
                reservation_sha256=descriptor_sha256(reservation),
                actor=command["actor"],
            )
        )
