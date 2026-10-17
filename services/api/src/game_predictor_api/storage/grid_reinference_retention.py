"""Detach removable live links while retaining immutable D-551 history."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from game_predictor_api.storage.grid_quality_measurement_models import (
    GridQualityMeasurementMemberModel,
)
from game_predictor_api.storage.grid_reinference_models import GridReinferenceSourceModel
from game_predictor_api.storage.grid_training_cohort_models import GridTrainingCohortMemberModel

_RETAINED_MODELS = (
    GridReinferenceSourceModel,
    GridQualityMeasurementMemberModel,
    GridTrainingCohortMemberModel,
)


def retained_grid_source_link_count(
    session: Session, game_id: UUID, source_ids: Sequence[UUID]
) -> int:
    if not source_ids:
        return 0
    return sum(
        int(
            session.scalar(
                select(func.count())
                .select_from(model)
                .where(model.game_id == game_id, model.live_source_image_id.in_(source_ids))
            )
            or 0
        )
        for model in _RETAINED_MODELS
    )


def detach_grid_source_links(session: Session, game_id: UUID, source_ids: Sequence[UUID]) -> None:
    """Caller owns deletion guards and transaction; never alter frozen payloads."""
    if source_ids:
        # Persist this before graph cleanup removes the operational approval
        # events. Source removal blocks new use without withdrawing the label.
        session.execute(
            text("""
          INSERT INTO grid_training_cohort_events(game_id,id,cohort_id,kind,source_id,document)
          SELECT game_id,gen_random_uuid(),cohort_id,'currentness_notice',source_id,
            jsonb_build_object('reasonCode','SOURCE_REMOVED_NEW_USE_BLOCKED',
              'operation','detach_live_source')
          FROM grid_training_cohort_members
          WHERE game_id=:game AND live_source_image_id=ANY(CAST(:sources AS uuid[]))
        """),
            {"game": game_id, "sources": list(source_ids)},
        )
        for model in _RETAINED_MODELS:
            session.execute(
                update(model)
                .where(model.game_id == game_id, model.live_source_image_id.in_(source_ids))
                .values(live_source_image_id=None)
            )
