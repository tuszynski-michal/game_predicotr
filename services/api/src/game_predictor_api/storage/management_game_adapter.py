"""Panel adapters use the existing game search, calculator and human writer."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import BoardSearchBoardDetailService
from game_predictor_api.application.board_search_share_corrections import share_cell_version
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationCommand,
)
from game_predictor_api.domain.board_search import BoardSearchQueryCell, validate_board_search_query
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAction
from game_predictor_api.domain.management import ManagementError
from game_predictor_api.schemas.board_search import BoardSearchResponse, to_board_search_response
from game_predictor_api.schemas.board_search_approximate_win import (
    ApproximateWinResponse,
    to_approximate_win_response,
)
from game_predictor_api.schemas.board_search_shares import (
    BoardSearchShareCellCorrectionResponse,
    BoardSearchSharePublicBoardDetailResponse,
    BoardSearchSharePublicCellResponse,
)
from game_predictor_api.schemas.management_stakes import (
    ManagementCorrectionCommand,
    ManagementSearchCommand,
)
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.image_review_repository import acquire_image_review_sequence_locks
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    enter_cell_decision,
)
from game_predictor_api.storage.management_result_snapshots import freeze_result
from game_predictor_api.storage.models import ImageSymbolReviewCellModel, SymbolModel
from game_predictor_api.storage.super_game_marker_repository import (
    SqlAlchemySuperGameMarkerRepository,
)


class SqlAlchemyManagementGameAdapter:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.boards = SqlAlchemyBoardSearchApproximateWinRepository(session)
        self.super_game_markers = SqlAlchemySuperGameMarkerRepository(session)

    def search(self, game_id: UUID, command: ManagementSearchCommand) -> BoardSearchResponse:
        GameStorageRouter().bind(self.session, game_id, intent=GameStorageIntent.READ)
        query = validate_board_search_query(
            BoardSearchQueryCell(cell.cell_index, cell.symbol_code) for cell in command.cells
        )
        outcome = BoardSearchService(
            SqlAlchemyBoardSearchProjectionRepository(self.session),
            self.super_game_markers,
        ).search_with_super_game(
            game_id=game_id,
            cells=query,
            scope=command.scope,
            limit=command.limit,
        )
        return to_board_search_response(
            game_id=game_id,
            scope=command.scope,
            query_cell_count=len(query),
            results=outcome.results,
            super_game=outcome.super_game,
        )

    def snapshot(
        self, game_id: UUID, start: int, count: int
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        """The frozen result (digest, payload, summary) of a stake save."""

        _live, digest, payload, summary = self._read(game_id, start, count)
        return digest, payload, summary

    def preview(self, game_id: UUID, start: int, count: int) -> ApproximateWinResponse:
        """The live calculation a save would freeze, with row markers and the
        series generation's freshness read in the same snapshot."""

        live, _digest, _payload, _summary = self._read(game_id, start, count)
        return live

    @contextmanager
    def _snapshot_reader(self, game_id: UUID, *, read_only: bool = True) -> Iterator[Session]:
        """A separate REPEATABLE READ session bound to the game (one snapshot)."""

        bind = self.session.get_bind()
        if not isinstance(bind, Engine):
            raise RuntimeError("Management snapshot requires an application engine.")
        # Separate read snapshot avoids fixing the mutation transaction's snapshot
        # before concurrent UUID lock wait. No writer locks are acquired here.
        snapshot_engine = create_engine(
            bind.url,
            isolation_level="REPEATABLE READ",
            poolclass=NullPool,
            connect_args={"connect_timeout": 5},
        )
        try:
            with GameStorageSession(snapshot_engine) as reader:
                connection = reader.connection()
                if read_only:
                    connection.exec_driver_sql("SET TRANSACTION READ ONLY")
                connection.exec_driver_sql("SET LOCAL statement_timeout = '20s'")
                connection.exec_driver_sql("SET LOCAL lock_timeout = '3s'")
                GameStorageRouter().bind(reader, game_id, intent=GameStorageIntent.READ)
                yield reader
        finally:
            snapshot_engine.dispose()

    def _read(
        self, game_id: UUID, start: int, count: int
    ) -> tuple[ApproximateWinResponse, str, dict[str, Any], dict[str, Any]]:
        with self._snapshot_reader(game_id) as reader:
            return self._snapshot(
                SqlAlchemyBoardSearchApproximateWinRepository(reader),
                SqlAlchemySuperGameMarkerRepository(reader),
                game_id,
                start,
                count,
            )

    @staticmethod
    def _snapshot(
        boards: SqlAlchemyBoardSearchApproximateWinRepository,
        markers: SqlAlchemySuperGameMarkerRepository,
        game_id: UUID,
        start: int,
        count: int,
    ) -> tuple[ApproximateWinResponse, str, dict[str, Any], dict[str, Any]]:
        configuration = boards.latest_published_rules(game_id)
        _mode, document = boards.board_document(game_id=game_id, sequence_number=start)
        if document is None:
            raise ManagementError(
                "MANAGEMENT_START_BOARD_MISSING", "The starting board is unavailable."
            )
        # The per-position mode projection (TASK-0936) is read in the same
        # REPEATABLE READ snapshot as the boards; a game without a super game
        # kind projects every position as base mode, so its frozen result is
        # byte-identical to the one written before the projection existed.
        domain_calculation = BoardSearchApproximateWinService(boards, markers).calculate(
            game_id=game_id,
            start_sequence_number=start,
            requested_spin_count=count,
        )
        calculation = to_approximate_win_response(domain_calculation)
        if configuration is None:
            raise AssertionError("Calculator accepted missing published rules.")
        if configuration.rules_version_id != calculation.rules.rules_version_id:
            raise AssertionError("Management calculation rules changed within one snapshot.")
        codes = boards.symbol_codes(game_id)
        symbols = tuple(None if code is None else codes.get(code) for code in document.mobile_codes)
        digest, payload, summary = freeze_result(
            calculation, configuration, symbols, document.board_checksum_sha256
        )
        return calculation, digest, payload, summary

    def detail(
        self, game_id: UUID, sequence_number: int
    ) -> BoardSearchSharePublicBoardDetailResponse:
        from game_predictor_api.schemas.board_search_approximate_win import (
            to_board_search_board_detail_response,
        )

        if self.session.get_bind().dialect.name == "postgresql":
            # Rules, document, markers and state from one snapshot (audit
            # TASK-0936 P0-3); not READ ONLY, like the request detail.
            with self._snapshot_reader(game_id, read_only=False) as reader:
                detail = BoardSearchBoardDetailService(
                    SqlAlchemyBoardSearchApproximateWinRepository(reader),
                    SqlAlchemySuperGameMarkerRepository(reader),
                ).detail(game_id=game_id, sequence_number=sequence_number)
        else:
            GameStorageRouter().bind(self.session, game_id, intent=GameStorageIntent.READ)
            detail = BoardSearchBoardDetailService(self.boards, self.super_game_markers).detail(
                game_id=game_id, sequence_number=sequence_number
            )
        response = to_board_search_board_detail_response(detail).model_dump(mode="python")
        response["cells"] = (
            None
            if detail.cells is None
            else tuple(
                BoardSearchSharePublicCellResponse(
                    cell_index=cell.cell_index,
                    cell_version=share_cell_version(game_id, sequence_number, cell),
                    review_state=cell.review_state,
                    quality_issue=cell.quality_issue,
                    assigned_symbol_code=cell.assigned_symbol_code,
                )
                for cell in detail.cells
            )
        )
        return BoardSearchSharePublicBoardDetailResponse.model_validate(response)

    def correct(
        self,
        game_id: UUID,
        sequence: int,
        cell_index: int,
        command: ManagementCorrectionCommand,
        actor: str,
    ) -> tuple[BoardSearchShareCellCorrectionResponse, dict[str, Any], dict[str, Any]]:
        GameStorageRouter().bind(self.session, game_id, intent=GameStorageIntent.WRITE)
        _mode, document = self.boards.board_document(game_id=game_id, sequence_number=sequence)
        if document is None or document.review_item_id is None:
            raise ManagementError("MANAGEMENT_BOARD_NOT_FOUND", "The board is unavailable.", 404)
        # TASK-0971 (P0-5): ownership lock before the sequence lock.
        enter_cell_decision(self.session, game_id=game_id, review_item_id=document.review_item_id)
        acquire_image_review_sequence_locks(
            self.session,
            game_id=game_id,
            review_item_id=document.review_item_id,
            requested_sequence_number=sequence,
        )
        detail = BoardSearchBoardDetailService(self.boards).detail(
            game_id=game_id, sequence_number=sequence
        )
        cells = detail.cells or ()
        cell = next((value for value in cells if value.cell_index == cell_index), None)
        if (
            cell is None
            or share_cell_version(game_id, sequence, cell) != command.expected_cell_version
        ):
            raise ManagementError(
                "MANAGEMENT_CELL_CONFLICT", "Reload the current board before correcting it."
            )
        target = None
        if command.target_symbol_code is not None:
            target = self.session.scalar(
                select(SymbolModel.id).where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.code == command.target_symbol_code,
                    SymbolModel.status == "active",
                )
            )
            if target is None:
                raise ManagementError(
                    "MANAGEMENT_SYMBOL_INVALID", "Choose an active symbol of this game."
                )
        SqlAlchemySymbolCellReviewMutationRepository(self.session).apply_mutation(
            SymbolCellReviewMutationCommand(
                game_id=game_id,
                cell_review_id=cell.cell_review_id,
                action=SymbolCellReviewAction(command.action),
                expected_revision=cell.revision,
                expected_geometry_revision=cell.geometry_revision,
                expected_crop_sample_id=cell.crop_sample_id,
                expected_crop_checksum_sha256=cell.crop_checksum_sha256,
                target_symbol_id=target,
                actor=actor,
            )
        )
        updated = self.session.get(
            ImageSymbolReviewCellModel, cell.cell_review_id, populate_existing=True
        )
        if updated is None:
            raise ManagementError(
                "MANAGEMENT_CELL_CONFLICT", "The written cell is no longer current."
            )
        symbol = (
            self.session.get(SymbolModel, updated.assigned_symbol_id)
            if updated.assigned_symbol_id
            else None
        )
        after = replace(
            cell,
            revision=updated.revision,
            geometry_revision=updated.geometry_revision,
            crop_sample_id=updated.crop_sample_id,
            crop_checksum_sha256=updated.crop_checksum_sha256,
            review_state=updated.review_state,
            quality_issue=updated.quality_issue,
            assigned_symbol_code=symbol.code if symbol else None,
        )
        before_data = {
            "symbolCode": cell.assigned_symbol_code,
            "qualityIssue": cell.quality_issue,
            "reviewState": cell.review_state,
        }
        after_data = {
            "symbolCode": after.assigned_symbol_code,
            "qualityIssue": after.quality_issue,
            "reviewState": after.review_state,
        }
        receipt = BoardSearchShareCellCorrectionResponse(
            sequence_number=sequence,
            cell_index=cell_index,
            cell_version=share_cell_version(game_id, sequence, after),
            changed=before_data != after_data,
            saved=True,
        )
        return receipt, before_data, after_data
