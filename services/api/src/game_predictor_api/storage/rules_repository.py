"""SQLAlchemy implementation of the rules-version repository port."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.rules import RulesRepository
from game_predictor_api.domain.rules import (
    Payline,
    PayoutRule,
    RulesConflictError,
    RulesSymbolDefinition,
    RulesVersion,
    RulesVersionStatus,
    RulesVersionSymbol,
)
from game_predictor_api.storage.models import (
    GameModel,
    PaylineModel,
    PayoutRuleModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
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
    "uq_payout_rules_version_symbol_length": (
        "PAYOUT_RULE_ALREADY_EXISTS",
        "A payout rule for this symbol and matchLength already exists.",
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

    def get_rules_version_for_update(
        self,
        rules_version_id: UUID,
    ) -> RulesVersion | None:
        record = self._session.scalar(
            select(RulesVersionModel)
            .where(RulesVersionModel.id == rules_version_id)
            .with_for_update()
        )
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
        record.status = rules_version.status
        record.published_at = rules_version.published_at
        self._flush_or_raise_conflict()
        return _to_rules_version(record)

    def get_or_clone_current_draft(
        self,
        source: RulesVersion,
    ) -> RulesVersion:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == source.game_id).with_for_update()
        )
        if game is None:
            raise RuntimeError("Rules source game disappeared during cloning.")
        current = self._session.scalar(
            select(RulesVersionModel)
            .where(
                RulesVersionModel.game_id == source.game_id,
                RulesVersionModel.status == RulesVersionStatus.DRAFT,
            )
            .order_by(RulesVersionModel.version.desc(), RulesVersionModel.id)
            .limit(1)
        )
        if current is not None:
            return _to_rules_version(current)

        latest = self._session.scalar(
            select(func.max(RulesVersionModel.version)).where(
                RulesVersionModel.game_id == source.game_id
            )
        )
        draft = RulesVersionModel(
            game_id=source.game_id,
            version=(latest or 0) + 1,
            rows=source.rows,
            columns=source.columns,
            spin_cost=source.spin_cost,
            status=RulesVersionStatus.DRAFT,
        )
        self._session.add(draft)
        self._flush_or_raise_conflict()

        for payline in self._session.scalars(
            select(PaylineModel).where(
                PaylineModel.rules_version_id == source.id
            )
        ):
            self._session.add(
                PaylineModel(
                    rules_version_id=draft.id,
                    code=payline.code,
                    name=payline.name,
                    row_path=list(payline.row_path),
                    display_order=payline.display_order,
                    is_active=payline.is_active,
                )
            )
        for configuration in self._session.scalars(
            select(RulesVersionSymbolModel).where(
                RulesVersionSymbolModel.rules_version_id == source.id
            )
        ):
            self._session.add(
                RulesVersionSymbolModel(
                    rules_version_id=draft.id,
                    symbol_id=configuration.symbol_id,
                    minimum_match_length=configuration.minimum_match_length,
                    is_active=configuration.is_active,
                )
            )
        for payout in self._session.scalars(
            select(PayoutRuleModel).where(
                PayoutRuleModel.rules_version_id == source.id
            )
        ):
            self._session.add(
                PayoutRuleModel(
                    rules_version_id=draft.id,
                    symbol_id=payout.symbol_id,
                    match_length=payout.match_length,
                    payout_credits=payout.payout_credits,
                    is_active=payout.is_active,
                )
            )
        self._flush_or_raise_conflict()
        self._session.refresh(draft)
        return _to_rules_version(draft)

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

    def payout_configuration_fits_columns(
        self,
        rules_version_id: UUID,
        *,
        columns: int,
    ) -> bool:
        minimums = self._session.scalars(
            select(RulesVersionSymbolModel.minimum_match_length).where(
                RulesVersionSymbolModel.rules_version_id == rules_version_id,
                RulesVersionSymbolModel.minimum_match_length.is_not(None),
            )
        )
        if any(
            minimum is not None and minimum > columns
            for minimum in minimums
        ):
            return False
        match_lengths = self._session.scalars(
            select(PayoutRuleModel.match_length).where(
                PayoutRuleModel.rules_version_id == rules_version_id
            )
        )
        return all(match_length <= columns for match_length in match_lengths)

    def get_rules_symbol_definition(
        self,
        symbol_id: UUID,
    ) -> RulesSymbolDefinition | None:
        record = self._session.get(SymbolModel, symbol_id)
        if record is None:
            return None
        return RulesSymbolDefinition(
            id=record.id,
            game_id=record.game_id,
            is_wildcard=record.is_wildcard,
        )

    def list_rules_version_symbols(
        self,
        rules_version_id: UUID,
    ) -> list[RulesVersionSymbol]:
        records = self._session.scalars(
            select(RulesVersionSymbolModel)
            .join(
                SymbolModel,
                SymbolModel.id == RulesVersionSymbolModel.symbol_id,
            )
            .where(
                RulesVersionSymbolModel.rules_version_id == rules_version_id
            )
            .order_by(
                SymbolModel.display_order,
                SymbolModel.mobile_code,
                SymbolModel.id,
            )
        )
        return [_to_rules_version_symbol(record) for record in records]

    def get_rules_version_symbol(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
    ) -> RulesVersionSymbol | None:
        record = self._session.get(
            RulesVersionSymbolModel,
            (rules_version_id, symbol_id),
        )
        return None if record is None else _to_rules_version_symbol(record)

    def save_rules_version_symbol(
        self,
        rules_version_symbol: RulesVersionSymbol,
    ) -> RulesVersionSymbol:
        record = self._session.get(
            RulesVersionSymbolModel,
            (
                rules_version_symbol.rules_version_id,
                rules_version_symbol.symbol_id,
            ),
        )
        if record is None:
            record = RulesVersionSymbolModel(
                rules_version_id=rules_version_symbol.rules_version_id,
                symbol_id=rules_version_symbol.symbol_id,
                minimum_match_length=rules_version_symbol.minimum_match_length,
                is_active=rules_version_symbol.is_active,
            )
            self._session.add(record)
        else:
            record.minimum_match_length = (
                rules_version_symbol.minimum_match_length
            )
            record.is_active = rules_version_symbol.is_active
        self._flush_or_raise_conflict()
        return _to_rules_version_symbol(record)

    def archive_payout_rules_below(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        minimum_match_length: int,
    ) -> None:
        records = self._session.scalars(
            select(PayoutRuleModel).where(
                PayoutRuleModel.rules_version_id == rules_version_id,
                PayoutRuleModel.symbol_id == symbol_id,
                PayoutRuleModel.match_length < minimum_match_length,
                PayoutRuleModel.is_active.is_(True),
            )
        )
        for record in records:
            record.is_active = False
        self._flush_or_raise_conflict()

    def list_payout_rules(self, rules_version_id: UUID) -> list[PayoutRule]:
        records = self._session.scalars(
            select(PayoutRuleModel)
            .join(SymbolModel, SymbolModel.id == PayoutRuleModel.symbol_id)
            .where(PayoutRuleModel.rules_version_id == rules_version_id)
            .order_by(
                SymbolModel.display_order,
                SymbolModel.mobile_code,
                PayoutRuleModel.match_length,
                PayoutRuleModel.id,
            )
        )
        return [_to_payout_rule(record) for record in records]

    def get_payout_rule(
        self,
        rules_version_id: UUID,
        payout_rule_id: UUID,
    ) -> PayoutRule | None:
        record = self._session.scalar(
            select(PayoutRuleModel).where(
                PayoutRuleModel.id == payout_rule_id,
                PayoutRuleModel.rules_version_id == rules_version_id,
            )
        )
        return None if record is None else _to_payout_rule(record)

    def find_payout_rule(
        self,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
    ) -> PayoutRule | None:
        record = self._session.scalar(
            select(PayoutRuleModel).where(
                PayoutRuleModel.rules_version_id == rules_version_id,
                PayoutRuleModel.symbol_id == symbol_id,
                PayoutRuleModel.match_length == match_length,
            )
        )
        return None if record is None else _to_payout_rule(record)

    def add_payout_rule(
        self,
        *,
        rules_version_id: UUID,
        symbol_id: UUID,
        match_length: int,
        payout_credits: int,
        is_active: bool,
    ) -> PayoutRule:
        record = PayoutRuleModel(
            rules_version_id=rules_version_id,
            symbol_id=symbol_id,
            match_length=match_length,
            payout_credits=payout_credits,
            is_active=is_active,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        return _to_payout_rule(record)

    def save_payout_rule(self, payout_rule: PayoutRule) -> PayoutRule:
        record = self._session.get(PayoutRuleModel, payout_rule.id)
        if record is None or record.rules_version_id != payout_rule.rules_version_id:
            raise RuntimeError(
                "Payout rule disappeared during a rules transaction."
            )
        record.payout_credits = payout_rule.payout_credits
        record.is_active = payout_rule.is_active
        self._flush_or_raise_conflict()
        return _to_payout_rule(record)

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


def _to_rules_version_symbol(
    record: RulesVersionSymbolModel,
) -> RulesVersionSymbol:
    return RulesVersionSymbol(
        rules_version_id=record.rules_version_id,
        symbol_id=record.symbol_id,
        minimum_match_length=record.minimum_match_length,
        is_active=record.is_active,
    )


def _to_payout_rule(record: PayoutRuleModel) -> PayoutRule:
    return PayoutRule(
        id=record.id,
        rules_version_id=record.rules_version_id,
        symbol_id=record.symbol_id,
        match_length=record.match_length,
        payout_credits=record.payout_credits,
        is_active=record.is_active,
    )
