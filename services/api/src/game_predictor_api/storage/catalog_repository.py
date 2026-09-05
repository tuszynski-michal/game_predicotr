"""SQLAlchemy implementation of the catalog repository port."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.catalog import CatalogRepository
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    Game,
    GameStatus,
    Symbol,
    SymbolStatus,
    SymbolUsageSummary,
    stable_code_stem_from_name,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    GameSymbolModelActivationModel,
    ImageGeometryRolloutStateModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionSymbolModel,
    SourceImageModel,
    SymbolModel,
    SymbolModelIterationModel,
    SymbolReferenceImageModel,
    VerifiedTrainingCohortModel,
)

_CONFLICTS = {
    "uq_games_code": (
        "GAME_CODE_ALREADY_EXISTS",
        "A game with this code already exists.",
    ),
    "uq_symbols_game_code": (
        "SYMBOL_CODE_ALREADY_EXISTS",
        "A symbol with this code already exists in the game.",
    ),
    "uq_symbols_game_mobile_code": (
        "SYMBOL_MOBILE_CODE_ALREADY_EXISTS",
        "A symbol with this mobileCode already exists in the game.",
    ),
}


class SqlAlchemyCatalogRepository(CatalogRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_games(self) -> list[Game]:
        records = self._session.scalars(
            select(GameModel).order_by(GameModel.created_at, GameModel.id)
        )
        return [_to_game(record) for record in records]

    def get_game(self, game_id: UUID) -> Game | None:
        record = self._session.get(GameModel, game_id)
        return None if record is None else _to_game(record)

    def add_game(
        self,
        *,
        code: str,
        name: str,
        status: GameStatus,
        expected_layout_count: int,
    ) -> Game:
        record = GameModel(
            code=code,
            name=name,
            status=status,
            expected_layout_count=expected_layout_count,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        self._session.add(
            ImageGeometryRolloutStateModel(
                game_id=record.id,
                geometry_mode="legacy",
                cell_asset_mode="legacy_files",
                revision=0,
                backfill_status="not_started",
                updated_by="system:catalog-game-create",
            )
        )
        self._flush_or_raise_conflict()
        self._session.refresh(record)
        return _to_game(record)

    def save_game(self, game: Game) -> Game:
        record = self._session.get(GameModel, game.id)
        if record is None:
            raise RuntimeError("Game disappeared during a catalog transaction.")
        record.name = game.name
        record.status = game.status
        record.expected_layout_count = game.expected_layout_count
        record.updated_at = datetime.now(UTC)
        self._flush_or_raise_conflict()
        return _to_game(record)

    def list_symbols(self, game_id: UUID) -> list[Symbol]:
        records = self._session.execute(
            select(SymbolModel, SymbolReferenceImageModel.image_relative_path)
            .outerjoin(
                SymbolReferenceImageModel,
                SymbolReferenceImageModel.symbol_id == SymbolModel.id,
            )
            .where(SymbolModel.game_id == game_id)
            .order_by(
                SymbolModel.display_order,
                SymbolModel.mobile_code,
                SymbolModel.id,
            )
        )
        return [_to_symbol(record, image_path=image_path) for record, image_path in records]

    def get_symbol(self, game_id: UUID, symbol_id: UUID) -> Symbol | None:
        result = self._session.execute(
            select(SymbolModel, SymbolReferenceImageModel.image_relative_path)
            .outerjoin(
                SymbolReferenceImageModel,
                SymbolReferenceImageModel.symbol_id == SymbolModel.id,
            )
            .where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        ).one_or_none()
        return None if result is None else _to_symbol(result[0], image_path=result[1])

    def add_symbol(
        self,
        *,
        game_id: UUID,
        mobile_code: int,
        code: str,
        name: str,
        name_pl: str | None,
        name_en: str | None,
        image_path: str | None,
        is_wildcard: bool,
        display_order: int,
        status: SymbolStatus,
    ) -> Symbol:
        record = SymbolModel(
            game_id=game_id,
            mobile_code=mobile_code,
            code=code,
            name=name,
            name_pl=name_pl,
            name_en=name_en,
            image_path=image_path,
            is_wildcard=is_wildcard,
            display_order=display_order,
            status=status,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        return _to_symbol(record)

    def add_manual_symbol(
        self,
        *,
        game_id: UUID,
        name: str,
        is_wildcard: bool,
    ) -> Symbol:
        game = self._session.execute(
            select(GameModel).where(GameModel.id == game_id).with_for_update()
        ).scalar_one_or_none()
        if game is None:
            raise RuntimeError("Game disappeared during a catalog transaction.")
        existing = tuple(
            self._session.scalars(
                select(SymbolModel)
                .where(SymbolModel.game_id == game_id)
                .order_by(SymbolModel.mobile_code, SymbolModel.display_order, SymbolModel.code)
            )
        )
        record = SymbolModel(
            game_id=game_id,
            mobile_code=max((item.mobile_code for item in existing), default=0) + 1,
            code=_next_symbol_code(name, tuple(item.code for item in existing)),
            name=name,
            image_path=None,
            is_wildcard=is_wildcard,
            display_order=max((item.display_order for item in existing), default=-1) + 1,
            status=SymbolStatus.ACTIVE,
        )
        self._session.add(record)
        self._flush_or_raise_conflict()
        return _to_symbol(record)

    def save_symbol(self, symbol: Symbol) -> Symbol:
        record = self._session.get(SymbolModel, symbol.id)
        if record is None or record.game_id != symbol.game_id:
            raise RuntimeError("Symbol disappeared during a catalog transaction.")
        record.name = symbol.name
        record.name_pl = symbol.name_pl
        record.name_en = symbol.name_en
        record.image_path = symbol.image_path
        record.is_wildcard = symbol.is_wildcard
        record.display_order = symbol.display_order
        record.status = symbol.status
        self._flush_or_raise_conflict()
        reference_path = self._session.scalar(
            select(SymbolReferenceImageModel.image_relative_path).where(
                SymbolReferenceImageModel.symbol_id == record.id
            )
        )
        return _to_symbol(record, image_path=reference_path)

    def symbol_is_used_in_rules(self, symbol_id: UUID) -> bool:
        return (
            self._session.scalar(
                select(RulesVersionSymbolModel.symbol_id)
                .where(RulesVersionSymbolModel.symbol_id == symbol_id)
                .limit(1)
            )
            is not None
        )

    def symbol_usage_summary(self, *, game_id: UUID, symbol_id: UUID) -> SymbolUsageSummary | None:
        symbol = self._session.scalar(
            select(SymbolModel).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        if symbol is None:
            return None
        symbol_code = symbol.code
        resolved_symbols = ImageReviewItemModel.resolved_value["symbolCodes"].contains(
            [symbol_code]
        )
        predicted_symbol = CellObservationModel.prediction["symbolCode"].as_string()
        return SymbolUsageSummary(
            rules=_count(
                self._session,
                select(RulesVersionSymbolModel.symbol_id).where(
                    RulesVersionSymbolModel.symbol_id == symbol_id
                ),
            ),
            pending_board_predictions=_count(
                self._session,
                select(CellObservationModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .join(
                    ImageReviewItemModel,
                    ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
                )
                .where(
                    JobModel.game_id == game_id,
                    ImageReviewItemModel.status == "pending",
                    predicted_symbol == symbol_code,
                ),
            ),
            resolved_board_decisions=_count(
                self._session,
                select(ImageReviewItemModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(
                    JobModel.game_id == game_id,
                    ImageReviewItemModel.status != "pending",
                    resolved_symbols,
                ),
            ),
            observation_predictions=_count(
                self._session,
                select(CellObservationModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(JobModel.game_id == game_id, predicted_symbol == symbol_code),
            ),
            symbol_cell_assignments=_count(
                self._session,
                select(ImageSymbolReviewCellModel.id).where(
                    ImageSymbolReviewCellModel.game_id == game_id,
                    ImageSymbolReviewCellModel.assigned_symbol_id == symbol_id,
                ),
            ),
            symbol_cell_review_events=_count(
                self._session,
                select(ImageSymbolReviewEventModel.id).where(
                    (ImageSymbolReviewEventModel.previous_assigned_symbol_id == symbol_id)
                    | (ImageSymbolReviewEventModel.assigned_symbol_id == symbol_id)
                ),
            ),
            # Cohort and model artifacts are immutable game-level data. They
            # might retain the code only in an external content-addressed file,
            # so any retained artifact blocks deletion fail-closed.
            training_cohorts=_count(
                self._session,
                select(VerifiedTrainingCohortModel.id).where(
                    VerifiedTrainingCohortModel.game_id == game_id
                ),
            ),
            symbol_model_iterations=_count(
                self._session,
                select(SymbolModelIterationModel.id).where(
                    SymbolModelIterationModel.game_id == game_id
                ),
            ),
            symbol_model_activations=_count(
                self._session,
                select(GameSymbolModelActivationModel.id).where(
                    GameSymbolModelActivationModel.game_id == game_id
                ),
            ),
        )

    def delete_unused_symbol(self, *, game_id: UUID, symbol_id: UUID) -> None:
        symbol = self._session.execute(
            select(SymbolModel)
            .where(SymbolModel.id == symbol_id, SymbolModel.game_id == game_id)
            .with_for_update()
        ).scalar_one_or_none()
        if symbol is None:
            raise RuntimeError("Symbol disappeared during a catalog transaction.")
        self._session.execute(
            delete(SymbolReferenceImageModel).where(
                SymbolReferenceImageModel.symbol_id == symbol_id
            )
        )
        self._session.delete(symbol)
        self._session.flush()

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
            raise CatalogConflictError(code, message) from error


def _to_game(record: GameModel) -> Game:
    return Game(
        id=record.id,
        code=record.code,
        name=record.name,
        status=record.status,
        expected_layout_count=record.expected_layout_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _next_symbol_code(name: str, existing_codes: tuple[str, ...]) -> str:
    stem = stable_code_stem_from_name(name)
    used = set(existing_codes)
    if stem not in used:
        return stem
    suffix = 2
    while True:
        rendered_suffix = f"-{suffix}"
        candidate = f"{stem[: 64 - len(rendered_suffix)]}{rendered_suffix}"
        if candidate not in used:
            return candidate
        suffix += 1


def _count(session: Session, statement: Any) -> int:
    return int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())


def _to_symbol(record: SymbolModel, *, image_path: str | None = None) -> Symbol:
    return Symbol(
        id=record.id,
        game_id=record.game_id,
        mobile_code=record.mobile_code,
        code=record.code,
        name=record.name,
        name_pl=record.name_pl,
        name_en=record.name_en,
        # A legacy image_path is never an approved reference.  The outer join
        # deliberately hides it until a provenance row exists.
        image_path=image_path,
        is_wildcard=record.is_wildcard,
        display_order=record.display_order,
        status=record.status,
    )
