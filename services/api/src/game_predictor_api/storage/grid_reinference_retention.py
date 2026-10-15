"""Detach removable live links while retaining immutable D-551 history."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from game_predictor_api.storage.grid_reinference_models import GridReinferenceSourceModel


def retained_grid_source_link_count(
    session: Session, game_id: UUID, source_ids: Sequence[UUID]
) -> int:
    if not source_ids:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(GridReinferenceSourceModel)
            .where(
                GridReinferenceSourceModel.game_id == game_id,
                GridReinferenceSourceModel.live_source_image_id.in_(source_ids),
            )
        )
        or 0
    )


def detach_grid_source_links(session: Session, game_id: UUID, source_ids: Sequence[UUID]) -> None:
    """Caller owns deletion guards and transaction; never alter frozen payloads."""
    if source_ids:
        session.execute(
            update(GridReinferenceSourceModel)
            .where(
                GridReinferenceSourceModel.game_id == game_id,
                GridReinferenceSourceModel.live_source_image_id.in_(source_ids),
            )
            .values(live_source_image_id=None)
        )
