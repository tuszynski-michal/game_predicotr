"""PostgreSQL adapter for production mobile snapshot generation."""

from __future__ import annotations

from uuid import UUID

from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    LayoutModel,
    LayoutPayoutModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from sqlalchemy import and_, select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.payouts.readiness import PayoutCompletenessFacts
from game_predictor_worker.payouts.store import SqlAlchemyPayoutStore
from game_predictor_worker.snapshots.contracts import (
    SnapshotGameSelection,
    SnapshotGameSource,
    SnapshotLayout,
    SnapshotSymbol,
)


class SqlAlchemyProductionSnapshotStore:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._payout_store = SqlAlchemyPayoutStore(session_factory)

    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None:
        return self._payout_store.get_completeness_facts(
            dataset_version_id,
            rules_version_id,
            algorithm_version,
        )

    def load_snapshot_game(
        self,
        selection: SnapshotGameSelection,
    ) -> SnapshotGameSource | None:
        with self._session_factory() as session:
            dataset = session.get(
                DatasetVersionModel,
                selection.dataset_version_id,
            )
            rules = session.get(RulesVersionModel, selection.rules_version_id)
            if dataset is None or rules is None:
                return None
            game = session.get(GameModel, dataset.game_id)
            if game is None:
                return None
            symbols = tuple(
                SnapshotSymbol(
                    mobile_code=symbol.mobile_code,
                    code=symbol.code,
                    name=symbol.name,
                    is_wildcard=symbol.is_wildcard,
                    display_order=symbol.display_order,
                    image_asset_key=symbol.image_path,
                )
                for _, symbol in session.execute(
                    select(RulesVersionSymbolModel, SymbolModel)
                    .join(
                        SymbolModel,
                        SymbolModel.id == RulesVersionSymbolModel.symbol_id,
                    )
                    .where(
                        RulesVersionSymbolModel.rules_version_id
                        == selection.rules_version_id,
                        RulesVersionSymbolModel.is_active.is_(True),
                    )
                    .order_by(SymbolModel.mobile_code, SymbolModel.id)
                )
            )
            return SnapshotGameSource(
                game_id=game.id,
                game_code=game.code,
                game_name=game.name,
                dataset_version_id=dataset.id,
                dataset_version=dataset.version,
                rules_version_id=rules.id,
                rules_version=rules.version,
                algorithm_version=selection.algorithm_version,
                rows=rules.rows,
                columns=rules.columns,
                spin_cost=rules.spin_cost,
                signature_cell_width=dataset.signature_cell_width,
                layout_count=dataset.layout_count,
                symbols=symbols,
            )

    def list_snapshot_layout_batch(
        self,
        selection: SnapshotGameSelection,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> list[SnapshotLayout]:
        if limit <= 0:
            raise ValueError("Snapshot batch limit must be positive.")
        exact_payout = and_(
            LayoutPayoutModel.dataset_version_id
            == selection.dataset_version_id,
            LayoutPayoutModel.rules_version_id == selection.rules_version_id,
            LayoutPayoutModel.algorithm_version == selection.algorithm_version,
            LayoutPayoutModel.sequence_number == LayoutModel.sequence_number,
        )
        with self._session_factory() as session:
            records = session.execute(
                select(
                    LayoutModel.sequence_number,
                    LayoutModel.signature,
                    LayoutPayoutModel.total_payout,
                )
                .join(LayoutPayoutModel, exact_payout)
                .where(
                    LayoutModel.dataset_version_id
                    == selection.dataset_version_id,
                    LayoutModel.sequence_number > after_sequence_number,
                )
                .order_by(LayoutModel.sequence_number, LayoutModel.id)
                .limit(limit)
            )
            return [
                SnapshotLayout(
                    sequence_number=sequence_number,
                    signature=signature,
                    payout=total_payout,
                )
                for sequence_number, signature, total_payout in records
            ]

