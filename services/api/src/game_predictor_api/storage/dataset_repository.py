"""SQLAlchemy dataset staging repository."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.datasets import DatasetRepository
from game_predictor_api.domain.datasets import (
    MOCK_GENERATOR_VERSION,
    DatasetConflictError,
    DatasetGenerationSource,
    DatasetValidationSource,
    DatasetVersion,
    DatasetVersionStatus,
    LayoutDraft,
    LayoutValidationRecord,
)
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    LayoutModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)


class SqlAlchemyDatasetRepository(DatasetRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.scalar(select(GameModel.id).where(GameModel.id == game_id)) is not None

    def list_dataset_versions(self, game_id: UUID) -> list[DatasetVersion]:
        records = self._session.scalars(
            select(DatasetVersionModel)
            .where(DatasetVersionModel.game_id == game_id)
            .order_by(
                DatasetVersionModel.version.desc(),
                DatasetVersionModel.id,
            )
        )
        return [_to_dataset_version(record) for record in records]

    def get_dataset_version(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None:
        record = self._session.get(
            DatasetVersionModel,
            dataset_version_id,
        )
        return None if record is None else _to_dataset_version(record)

    def get_dataset_version_for_update(
        self,
        dataset_version_id: UUID,
    ) -> DatasetVersion | None:
        record = self._session.scalar(
            select(DatasetVersionModel)
            .where(DatasetVersionModel.id == dataset_version_id)
            .with_for_update()
        )
        return None if record is None else _to_dataset_version(record)

    def get_generation_source(
        self,
        game_id: UUID,
        rules_version_id: UUID,
    ) -> DatasetGenerationSource | None:
        rules = self._session.scalar(
            select(RulesVersionModel)
            .where(
                RulesVersionModel.id == rules_version_id,
                RulesVersionModel.game_id == game_id,
            )
            .with_for_update()
        )
        if rules is None:
            return None
        mobile_codes = tuple(
            self._session.scalars(
                select(SymbolModel.mobile_code)
                .join(
                    RulesVersionSymbolModel,
                    RulesVersionSymbolModel.symbol_id == SymbolModel.id,
                )
                .where(
                    RulesVersionSymbolModel.rules_version_id == rules_version_id,
                    RulesVersionSymbolModel.is_active.is_(True),
                    SymbolModel.game_id == game_id,
                )
                .order_by(SymbolModel.mobile_code)
            )
        )
        return DatasetGenerationSource(
            rules_version_id=rules.id,
            game_id=rules.game_id,
            rows=rules.rows,
            columns=rules.columns,
            rules_status=rules.status,
            symbol_mobile_codes=mobile_codes,
        )

    def add_mock_dataset(
        self,
        *,
        source: DatasetGenerationSource,
        seed: int,
        signature_width: int,
        layouts: Sequence[LayoutDraft],
    ) -> DatasetVersion | None:
        game = self._session.scalar(
            select(GameModel).where(GameModel.id == source.game_id).with_for_update()
        )
        if game is None:
            return None
        latest = self._session.scalar(
            select(func.max(DatasetVersionModel.version)).where(
                DatasetVersionModel.game_id == source.game_id
            )
        )
        record = DatasetVersionModel(
            game_id=source.game_id,
            version=(latest or 0) + 1,
            rows=source.rows,
            columns=source.columns,
            signature_cell_width=signature_width,
            expected_layout_count=game.expected_layout_count,
            layout_count=len(layouts),
            status=DatasetVersionStatus.STAGING,
            generation_seed=seed,
            generator_version=MOCK_GENERATOR_VERSION,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        self._session.add_all(
            [
                LayoutModel(
                    dataset_version_id=record.id,
                    sequence_number=layout.sequence_number,
                    signature=layout.signature,
                    cells=list(layout.cells),
                )
                for layout in layouts
            ]
        )
        self._flush_or_raise_conflict()
        self._session.refresh(record)
        return _to_dataset_version(record)

    def get_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None:
        dataset_record = self._session.get(
            DatasetVersionModel,
            dataset_version_id,
        )
        if dataset_record is None:
            return None
        return self._validation_source(dataset_record)

    def get_locked_validation_source(
        self,
        dataset_version_id: UUID,
    ) -> DatasetValidationSource | None:
        dataset_record = self._session.scalar(
            select(DatasetVersionModel)
            .where(DatasetVersionModel.id == dataset_version_id)
            .with_for_update()
        )
        if dataset_record is None:
            return None
        return self._validation_source(dataset_record)

    def list_layouts(
        self,
        dataset_version_id: UUID,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> list[LayoutValidationRecord]:
        records = self._session.scalars(
            select(LayoutModel)
            .where(
                LayoutModel.dataset_version_id == dataset_version_id,
                LayoutModel.sequence_number > after_sequence_number,
            )
            .order_by(LayoutModel.sequence_number, LayoutModel.id)
            .limit(limit)
        )
        return [
            LayoutValidationRecord(
                sequence_number=record.sequence_number,
                signature=record.signature,
                cells=tuple(record.cells),
                source_board_id=record.source_board_id,
            )
            for record in records
        ]

    def save_dataset_version(
        self,
        dataset_version: DatasetVersion,
    ) -> DatasetVersion:
        record = self._session.get(
            DatasetVersionModel,
            dataset_version.id,
        )
        if record is None:
            raise RuntimeError("Dataset version disappeared during a transaction.")
        record.status = dataset_version.status
        record.published_at = dataset_version.published_at
        self._flush_or_raise_conflict()
        return _to_dataset_version(record)

    def _validation_source(
        self,
        dataset_record: DatasetVersionModel,
    ) -> DatasetValidationSource:
        allowed_codes = tuple(
            self._session.scalars(
                select(SymbolModel.mobile_code)
                .where(SymbolModel.game_id == dataset_record.game_id)
                .order_by(SymbolModel.mobile_code)
            )
        )
        layout_records = self._session.scalars(
            select(LayoutModel)
            .where(LayoutModel.dataset_version_id == dataset_record.id)
            .order_by(LayoutModel.sequence_number, LayoutModel.id)
        )
        return DatasetValidationSource(
            dataset_version=_to_dataset_version(dataset_record),
            allowed_symbol_mobile_codes=allowed_codes,
            layouts=tuple(
                LayoutValidationRecord(
                    sequence_number=record.sequence_number,
                    signature=record.signature,
                    cells=tuple(record.cells),
                    source_board_id=record.source_board_id,
                )
                for record in layout_records
            ),
        )

    def _flush_or_raise_conflict(self) -> None:
        try:
            self._session.flush()
        except IntegrityError as error:
            raise DatasetConflictError(
                "DATASET_STAGING_CONFLICT",
                "Dataset staging conflicts with canonical data.",
            ) from error


def _to_dataset_version(record: DatasetVersionModel) -> DatasetVersion:
    return DatasetVersion(
        id=record.id,
        game_id=record.game_id,
        version=record.version,
        rows=record.rows,
        columns=record.columns,
        signature_cell_width=record.signature_cell_width,
        expected_layout_count=record.expected_layout_count,
        layout_count=record.layout_count,
        status=record.status,
        generation_seed=record.generation_seed,
        generator_version=record.generator_version,
        source_job_id=record.source_job_id,
        created_at=record.created_at,
        published_at=record.published_at,
    )
