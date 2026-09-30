"""PostgreSQL repository for the admin "Przybliżona wygrana" range calculator.

Combines three read-only concerns that `BoardSearchApproximateWinService`
needs and that do not naturally belong to a single existing repository: the
game's sequence length, the latest published rules version's payout
configuration (reused from the worker package, independent of any dataset —
TASK-0650), and board-search projection evidence for a contiguous sequence
range (delegated to `SqlAlchemyBoardSearchProjectionRepository`, so both
board search and approximate win read the exact same source and raise the
exact same readiness errors).
"""

from __future__ import annotations

from uuid import UUID

from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from game_predictor_worker.payouts.store import load_rules_payout_configuration
from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import ApproximateWinDocument
from game_predictor_api.domain.board_search_board_detail import (
    BoardSearchBoardDocument,
    BoardSearchBoardViewSource,
    PaylineLabel,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageReviewItemModel,
    PaylineModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
    SymbolModel,
)


class SqlAlchemyBoardSearchApproximateWinRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._projection = SqlAlchemyBoardSearchProjectionRepository(session)

    def game_sequence_length(self, game_id: UUID) -> int:
        """The game's current completeness target (`games.expected_layout_count`),
        i.e. the deterministic sequence length `L` used to plan and wrap the
        approximate-win range.
        """
        game = self._session.get(GameModel, game_id)
        if game is None:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        return int(game.expected_layout_count)

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        """The most recently published rules version's payout configuration,
        or `None` when the game has never published one.
        """
        rules_version_id = self._session.scalar(
            select(RulesVersionModel.id)
            .where(
                RulesVersionModel.game_id == game_id,
                RulesVersionModel.status == RulesVersionStatus.PUBLISHED,
            )
            .order_by(RulesVersionModel.version.desc())
            .limit(1)
        )
        if rules_version_id is None:
            return None
        return load_rules_payout_configuration(self._session, rules_version_id)

    def range_documents(
        self,
        *,
        game_id: UUID,
        first_sequence_number: int,
        last_sequence_number: int,
    ) -> tuple[BoardSearchAssetMode, tuple[ApproximateWinDocument, ...]]:
        """Delegate to the board-search projection repository so approximate
        win reads the same source, with the same readiness errors, as
        partial board search.
        """
        return self._projection.range_documents(
            game_id=game_id,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
        )

    def board_document(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
    ) -> tuple[BoardSearchAssetMode, BoardSearchBoardDocument | None]:
        return self._projection.board_document(game_id=game_id, sequence_number=sequence_number)

    def board_view_source(
        self,
        *,
        game_id: UUID,
        document: BoardSearchBoardDocument,
    ) -> BoardSearchBoardViewSource | None:
        """Pixels and saved geometry behind one search document.

        The archive holds a single-board image and no cell geometry. An
        operational document points at the current review item; its board's
        identity checksum is compared with the document by the caller.
        """
        if document.asset_mode is BoardSearchAssetMode.LEGACY_ARCHIVE:
            if document.archive_relative_path is None:
                return None
            return BoardSearchBoardViewSource(
                image_relative_path=document.archive_relative_path,
                image_checksum_sha256=document.board_checksum_sha256,
                geometry=None,
                current_board_checksum_sha256=document.board_checksum_sha256,
            )
        if document.review_item_id is None:
            return None
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        row = self._session.execute(
            select(RecognizedBoardModel, SourceImageModel)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .where(ImageReviewItemModel.id == document.review_item_id)
        ).one_or_none()
        if row is None:
            return None
        board, source = row
        # Same identity rule as the projection writer (`_payload_from_records`).
        current = (
            board.board_checksum_sha256
            if board.asset_mode == "legacy_file"
            else board.geometry_checksum_sha256
        )
        return BoardSearchBoardViewSource(
            image_relative_path=source.relative_path,
            image_checksum_sha256=source.checksum_sha256,
            geometry=dict(board.board_geometry),
            current_board_checksum_sha256=current or "",
        )

    def payline_labels(self, rules_version_id: UUID) -> dict[str, PaylineLabel]:
        return {
            str(record.id): PaylineLabel(
                payline_id=str(record.id),
                code=record.code,
                name=record.name,
                display_order=int(record.display_order),
                row_path=tuple(int(value) for value in record.row_path),
            )
            for record in self._session.scalars(
                select(PaylineModel).where(PaylineModel.rules_version_id == rules_version_id)
            )
        }

    def symbol_codes(self, game_id: UUID) -> dict[int, str]:
        return {
            int(mobile_code): code
            for code, mobile_code in self._session.execute(
                select(SymbolModel.code, SymbolModel.mobile_code).where(
                    SymbolModel.game_id == game_id
                )
            ).tuples()
        }


__all__ = ["SqlAlchemyBoardSearchApproximateWinRepository"]
