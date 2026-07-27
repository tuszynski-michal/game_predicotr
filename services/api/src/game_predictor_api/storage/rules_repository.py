"""SQLAlchemy implementation of the rules-version repository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.rules import RulesRepository
from game_predictor_api.domain.rules import Payline, RulesConflictError, RulesVersion
from game_predictor_api.storage.models import (
    GameModel,
    PaylineModel,
    RulesVersionModel,
)

_CONFLICTS = {
    "uq_rules_versions_game_version": (
        "RULES_VERSION_NUMBER_ALREADY_EXISTS",
        "This rules version number already exists for the game.",
    ),
    "uq_paylines_rules_version_code": (
        "PAYLINE_CODE_ALREADY_EXISTS",
        "A payline with this code already exists in the rules version.",
    ),
    "uq_paylines_rules_version_row_path": (
        "DUPLICATE_PAYLINE",
        "A payline with this rowPath already exists.",
    ),
}


class SqlAlchemyRulesRepository(RulesRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is not None

    def list_rules_versions(self, game_id: UUID) -> list[RulesVersion]:
        records = self._session.scalars(
            select(RulesVersionModel)
            .where(RulesVersionModel.game_id == game_id)
            .order_by(RulesVersionModel.version.desc(), RulesVersionModel.id)
        )
        return [_to_rules_version(record) for record in records]

    def get_rules_version(self, rules_version_id: UUID) -> RulesVersion | None:
        record = self._session.get(RulesVersionModel, rules_version_id)
        return None if record is None else _to_rules_version(record)

    def add_next_rules_version(
        self,
        *,
        game_id: UUID,
        rows: int,
        columns: int,
        spin_cost: int,
    ) -> RulesVersion | None:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        )
        if game is None:
            return None
        latest = self._session.scalar(
            select(func.max(RulesVersionModel.version)).where(RulesVersionModel.game_id == game_id)
        )
        record = RulesVersionModel(
            game_id=game_id,
            version=(latest or 0) + 1,
            rows=rows,
            columns=columns,
            spin_cost=spin_cost,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        self._session.refresh(record)
        return _to_rules_version(record)

    def save_rules_version(self, rules_version: RulesVersion) -> RulesVersion:
        record = self._session.get(RulesVersionModel, rules_version.id)
        if record is None:
            raise RuntimeError("Rules version disappeared during a transaction.")
        record.rows = rules_version.rows
        record.columns = rules_version.columns
        record.spin_cost = rules_version.spin_cost
        self._flush_or_raise_conflict()
        return _to_rules_version(record)

    def paylines_fit_dimensions(
        self,
        rules_version_id: UUID,
        *,
        rows: int,
        columns: int,
    ) -> bool:
        row_paths = self._session.scalars(
            select(PaylineModel.row_path).where(PaylineModel.rules_version_id == rules_version_id)
        )
        return all(
            len(row_path) == columns and all(row < rows for row in row_path)
            for row_path in row_paths
        )

    def list_paylines(self, rules_version_id: UUID) -> list[Payline]:
        records = self._session.scalars(
            select(PaylineModel)
            .where(PaylineModel.rules_version_id == rules_version_id)
            .order_by(
                PaylineModel.display_order,
                PaylineModel.code,
                PaylineModel.id,
            )
        )
        return [_to_payline(record) for record in records]

    def get_payline(
        self,
        rules_version_id: UUID,
        payline_id: UUID,
    ) -> Payline | None:
        record = self._session.scalar(
            select(PaylineModel).where(
                PaylineModel.id == payline_id,
                PaylineModel.rules_version_id == rules_version_id,
            )
        )
        return None if record is None else _to_payline(record)

    def find_payline_by_code(
        self,
        rules_version_id: UUID,
        code: str,
    ) -> Payline | None:
        record = self._session.scalar(
            select(PaylineModel).where(
                PaylineModel.rules_version_id == rules_version_id,
                PaylineModel.code == code,
            )
        )
        return None if record is None else _to_payline(record)

    def find_payline_by_row_path(
        self,
        rules_version_id: UUID,
        row_path: tuple[int, ...],
    ) -> Payline | None:
        record = self._session.scalar(
            select(PaylineModel).where(
                PaylineModel.rules_version_id == rules_version_id,
                PaylineModel.row_path == list(row_path),
            )
        )
        return None if record is None else _to_payline(record)

    def add_payline(
        self,
        *,
        rules_version_id: UUID,
        code: str,
        name: str,
        row_path: tuple[int, ...],
        display_order: int,
        is_active: bool,
    ) -> Payline:
        record = PaylineModel(
            rules_version_id=rules_version_id,
            code=code,
            name=name,
            row_path=list(row_path),
            display_order=display_order,
            is_active=is_active,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        return _to_payline(record)

    def save_payline(self, payline: Payline) -> Payline:
        record = self._session.get(PaylineModel, payline.id)
        if record is None or record.rules_version_id != payline.rules_version_id:
            raise RuntimeError("Payline disappeared during a rules transaction.")
        record.name = payline.name
        record.row_path = list(payline.row_path)
        record.display_order = payline.display_order
        record.is_active = payline.is_active
        self._flush_or_raise_conflict()
        return _to_payline(record)

    def _flush_or_raise_conflict(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            conflict = _CONFLICTS.get(constraint_name) if isinstance(constraint_name, str) else None
            if conflict is None:
                raise
            code, message = conflict
            raise RulesConflictError(code, message) from error


def _to_rules_version(record: RulesVersionModel) -> RulesVersion:
    return RulesVersion(
        id=record.id,
        game_id=record.game_id,
        version=record.version,
        rows=record.rows,
        columns=record.columns,
        spin_cost=record.spin_cost,
        status=record.status,
        created_at=record.created_at,
        published_at=record.published_at,
    )


def _to_payline(record: PaylineModel) -> Payline:
    return Payline(
        id=record.id,
        rules_version_id=record.rules_version_id,
        code=record.code,
        name=record.name,
        row_path=tuple(record.row_path),
        display_order=record.display_order,
        is_active=record.is_active,
    )
