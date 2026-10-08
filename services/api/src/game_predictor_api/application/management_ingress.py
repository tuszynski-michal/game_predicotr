"""Retain shared ingress while any live capability still needs it."""

from datetime import UTC, datetime

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from game_predictor_api.application.reviewer_ingress import ReviewerIngressService
from game_predictor_api.storage.management_session_models import ManagementSessionModel
from game_predictor_api.storage.management_session_repository import (
    SqlAlchemyManagementSessionRepository,
)
from game_predictor_api.storage.models import BoardSearchShareSessionModel


def stop_unused_shared_ingress(engine: Engine, ingress: ReviewerIngressService) -> None:
    # The creation transaction takes this same lock before starting ingress.
    with Session(engine) as session, session.begin():
        SqlAlchemyManagementSessionRepository(session).lock_ingress()
        for model in (ManagementSessionModel, BoardSearchShareSessionModel):
            active = session.scalar(
                select(func.count(model.id)).where(
                    model.revoked_at.is_(None),
                    model.locked_at.is_(None),
                    model.expires_at > datetime.now(UTC),
                )
            )
            if active:
                return
        status = ingress.status()
        if status.instance_id is not None:
            ingress.stop_if_current(status.instance_id)
