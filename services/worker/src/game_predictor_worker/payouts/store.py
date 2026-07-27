"""PostgreSQL source and idempotent sink for payout batches."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    LayoutModel,
    LayoutPayoutModel,
    PaylineModel,
    PayoutRuleModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.domain.contracts import (
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
)
from game_predictor_worker.payouts.contracts import (
    CalculatedLayoutPayout,
    PayoutLayout,
    PayoutSource,
)


class SqlAlchemyPayoutStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load_source(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
    ) -> PayoutSource | None:
        with self._session_factory() as session:
            dataset = session.get(DatasetVersionModel, dataset_version_id)
            rules = session.get(RulesVersionModel, rules_version_id)
            if dataset is None or rules is None:
                return None
            game = session.get(GameModel, dataset.game_id)
            if game is None:
                return None

            configured_symbols = tuple(
                session.execute(
                    select(RulesVersionSymbolModel, SymbolModel)
                    .join(
                        SymbolModel,
                        SymbolModel.id == RulesVersionSymbolModel.symbol_id,
                    )
                    .where(
                        RulesVersionSymbolModel.rules_version_id == rules_version_id,
                        RulesVersionSymbolModel.is_active.is_(True),
                    )
                    .order_by(
                        SymbolModel.display_order,
                        SymbolModel.mobile_code,
                        SymbolModel.id,
                    )
                )
            )
            symbols = tuple(
                SymbolDefinition(
                    mobile_code=symbol.mobile_code,
                    code=symbol.code,
                    name=symbol.name,
                    is_wildcard=symbol.is_wildcard,
                    display_order=symbol.display_order,
                )
                for _, symbol in configured_symbols
            )
            payout_symbols = tuple(
                PayoutSymbolDefinition(
                    symbol_mobile_code=symbol.mobile_code,
                    minimum_match_length=configuration.minimum_match_length,
                )
                for configuration, symbol in configured_symbols
                if not symbol.is_wildcard and configuration.minimum_match_length is not None
            )
            paylines = tuple(
                PaylineDefinition(
                    id=str(record.id),
                    row_path=tuple(record.row_path),
                )
                for record in session.scalars(
                    select(PaylineModel)
                    .where(
                        PaylineModel.rules_version_id == rules_version_id,
                        PaylineModel.is_active.is_(True),
                    )
                    .order_by(
                        PaylineModel.display_order,
                        PaylineModel.code,
                        PaylineModel.id,
                    )
                )
            )
            payout_rules = tuple(
                PayoutRuleDefinition(
                    symbol_mobile_code=symbol.mobile_code,
                    match_length=rule.match_length,
                    payout_credits=rule.payout_credits,
                )
                for rule, symbol in session.execute(
                    select(PayoutRuleModel, SymbolModel)
                    .join(SymbolModel, SymbolModel.id == PayoutRuleModel.symbol_id)
                    .where(
                        PayoutRuleModel.rules_version_id == rules_version_id,
                        PayoutRuleModel.is_active.is_(True),
                    )
                    .order_by(
                        SymbolModel.display_order,
                        SymbolModel.mobile_code,
                        PayoutRuleModel.match_length,
                        PayoutRuleModel.id,
                    )
                )
            )
            return PayoutSource(
                dataset_version_id=dataset.id,
                rules_version_id=rules.id,
                game_id=dataset.game_id,
                rules_game_id=rules.game_id,
                dataset_status=dataset.status,
                rules_status=rules.status,
                dataset_rows=dataset.rows,
                dataset_columns=dataset.columns,
                layout_count=dataset.layout_count,
                game=GameConfig(
                    id=str(game.id),
                    code=game.code,
                    name=game.name,
                    rows=rules.rows,
                    columns=rules.columns,
                    spin_cost=rules.spin_cost,
                    signature_cell_width=dataset.signature_cell_width,
                    symbols=symbols,
                ),
                paylines=paylines,
                payout_symbols=payout_symbols,
                payout_rules=payout_rules,
            )

    def list_layout_batch(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> list[PayoutLayout]:
        if limit <= 0:
            raise ValueError("Payout batch limit must be positive.")
        with self._session_factory() as session:
            records = session.scalars(
                select(LayoutModel)
                .where(
                    LayoutModel.dataset_version_id == dataset_version_id,
                    LayoutModel.sequence_number > after_sequence_number,
                )
                .order_by(LayoutModel.sequence_number, LayoutModel.id)
                .limit(limit)
            )
            return [
                PayoutLayout(
                    sequence_number=record.sequence_number,
                    cells=tuple(record.cells),
                )
                for record in records
            ]

    def upsert_payouts(
        self,
        payouts: Sequence[CalculatedLayoutPayout],
    ) -> None:
        if not payouts:
            return
        values = [
            {
                "dataset_version_id": payout.dataset_version_id,
                "rules_version_id": payout.rules_version_id,
                "sequence_number": payout.sequence_number,
                "algorithm_version": payout.algorithm_version,
                "total_payout": payout.total_payout,
                "audit_path": payout.audit_path,
                "calculated_at": payout.calculated_at,
            }
            for payout in payouts
        ]
        statement = insert(LayoutPayoutModel).values(values)
        statement = statement.on_conflict_do_update(
            index_elements=[
                LayoutPayoutModel.dataset_version_id,
                LayoutPayoutModel.rules_version_id,
                LayoutPayoutModel.sequence_number,
                LayoutPayoutModel.algorithm_version,
            ],
            set_={
                "total_payout": statement.excluded.total_payout,
                "audit_path": statement.excluded.audit_path,
                "calculated_at": statement.excluded.calculated_at,
            },
        )
        with self._session_factory() as session, session.begin():
            session.execute(statement)
