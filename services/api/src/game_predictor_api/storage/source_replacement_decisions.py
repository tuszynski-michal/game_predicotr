"""Immutable chronology written in the same transaction as the A2 command receipt."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.symbol_readability import crop_identity
from game_predictor_api.storage.sequence_ownership_lock import require_exclusive_sequence_ownership


def append_quality_decision(
    session: Session,
    *,
    game: UUID,
    key: UUID,
    run: UUID,
    cell: UUID,
    revision: int,
    state: str,
    overlap: bool | None,
    snapshot: dict[str, Any],
    prior_item: dict[str, Any],
) -> None:
    require_exclusive_sequence_ownership(session, game_id=game)
    retained = dict(snapshot)
    # A non-decisive command must not erase a pre-ledger judgment. Preserve it
    # as unordered legacy evidence, never invent an ordinal for the old decision.
    if prior_item["ever_labelled"] and prior_item["state"] in {"readable", "unreadable"}:
        retained["prior_quality_judgment"] = {
            name: prior_item[name]
            for name in (
                "cell_id",
                "run_id",
                "revision",
                "identity",
                "state",
                "overlap",
                "ever_labelled",
            )
        }
    session.execute(
        text("""INSERT INTO symbol_readability_decisions
      (game_id,cell_id,ordinal,idempotency_key,run_id,item_revision,identity,state,overlap,snapshot)
      SELECT :game,:cell,COALESCE(max(ordinal),0)+1,:key,:run,:revision,:identity,:state,:overlap,
        CAST(:snapshot AS jsonb) FROM symbol_readability_decisions
      WHERE game_id=:game AND cell_id=:cell"""),
        {
            "game": game,
            "cell": cell,
            "key": key,
            "run": run,
            "revision": revision,
            "identity": crop_identity(snapshot),
            "state": state,
            "overlap": overlap,
            "snapshot": json.dumps(retained, default=str),
        },
    )
