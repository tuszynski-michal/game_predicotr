"""A capability lock is retained until mutation/audit commit or rollback."""

from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.management_access import ManagementSessionRecord
from game_predictor_api.storage.management_session_models import (
    ManagementSessionAuditModel,
    ManagementSessionModel,
)

MANAGEMENT_INGRESS_LOCK = 0x6D676D745F696E


def record(model: ManagementSessionModel) -> ManagementSessionRecord:
    return ManagementSessionRecord(
        **{key: getattr(model, key) for key in ManagementSessionRecord.__dataclass_fields__}
    )


class SqlAlchemyManagementSessionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_ingress(self) -> None:
        self.session.execute(
            text("SELECT pg_advisory_xact_lock(:key)"), {"key": MANAGEMENT_INGRESS_LOCK}
        )

    def get(self, session_id: UUID, *, lock: bool = False) -> ManagementSessionRecord | None:
        statement = (
            select(ManagementSessionModel)
            .where(ManagementSessionModel.id == session_id)
            .execution_options(populate_existing=True)
        )
        if lock:
            statement = statement.with_for_update()
        value = self.session.scalar(statement)
        return record(value) if value is not None else None

    def find_token(self, token_hash: bytes) -> ManagementSessionRecord | None:
        value = self.session.scalar(
            select(ManagementSessionModel)
            .where(ManagementSessionModel.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        return record(value) if value is not None else None

    def save(self, value: ManagementSessionRecord) -> None:
        model = self.session.get(ManagementSessionModel, value.id)
        if model is None:
            self.session.add(ManagementSessionModel(**asdict(value)))
        else:
            for key, item in asdict(value).items():
                setattr(model, key, item)
        self.session.flush()

    def list(self, limit: int) -> tuple[ManagementSessionRecord, ...]:
        return tuple(
            record(value)
            for value in self.session.scalars(
                select(ManagementSessionModel)
                .order_by(
                    ManagementSessionModel.created_at.desc(), ManagementSessionModel.id.desc()
                )
                .limit(limit)
            )
        )

    def audit(self, value: ManagementSessionRecord, event: str, at: datetime) -> None:
        self.session.add(
            ManagementSessionAuditModel(
                id=uuid4(),
                session_id=value.id,
                event_type=event,
                payload={"failedAttempts": value.failed_attempts},
                created_at=at,
            )
        )
        self.session.flush()
