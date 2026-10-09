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
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_approximate_win import ApproximateWinDocument
from game_predictor_api.domain.board_search_board_detail import (
    BoardSearchBoardCell,
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
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSymbolReviewCellModel,
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

    def begin_read_snapshot(self) -> None:
        """Start the request transaction as one REPEATABLE READ snapshot.

        Audit TASK-0936 P0-3: the range calculator and the board detail read
        the rules, the board documents, the super game markers and the
        derivation state; one snapshot keeps a correction plus a generation
        publication committed in between from pairing old boards with a new
        series generation and ``fresh = true``. It must be the first use of the
        session (the isolation level is set when the transaction procures its
        connection); it is not READ ONLY because the game storage router binds
        unknown statements with write intent. The pool resets the isolation
        level on release. Applied to every game: for a game without a super
        game kind it only makes the reads consistent, the numbers are the same.
        """

        if self._session.get_bind().dialect.name != "postgresql":
            return
        if self._session.in_transaction():
            raise RuntimeError("A board-search read snapshot must be the first use of the session.")
        connection = self._session.connection(
            execution_options={"isolation_level": "REPEATABLE READ"}
        )
        if connection.get_isolation_level() != "REPEATABLE READ":
            raise RuntimeError("A board-search read snapshot must be REPEATABLE READ.")

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

    def rules_configuration(
        self, *, game_id: UUID, rules_version_id: UUID
    ) -> RulesPayoutConfiguration | None:
        """One draft or published rules version of this game, for the
        Admin-only draft preview (TASK-0932); `None` for any other version.
        """
        found = self._session.scalar(
            select(RulesVersionModel.id).where(
                RulesVersionModel.id == rules_version_id,
                RulesVersionModel.game_id == game_id,
                RulesVersionModel.status.in_(
                    (RulesVersionStatus.DRAFT, RulesVersionStatus.PUBLISHED)
                ),
            )
        )
        if found is None:
            return None
        return load_rules_payout_configuration(self._session, found)

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

        An operational document points at the current review item; its
        board's identity checksum is compared with the document by the caller.
        """
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
        current = board.geometry_checksum_sha256
        return BoardSearchBoardViewSource(
            image_relative_path=source.relative_path,
            image_checksum_sha256=source.checksum_sha256,
            geometry=dict(board.board_geometry),
            current_board_checksum_sha256=current or "",
        )

    def board_cells(
        self,
        *,
        game_id: UUID,
        document: BoardSearchBoardDocument,
    ) -> tuple[BoardSearchBoardCell, ...]:
        """Cell review records of the document's board at its current
        geometry revision (same rule as `_current_cell_decisions`)."""
        if document.review_item_id is None:
            return ()
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        board = self._session.execute(
            select(RecognizedBoardModel.id, RecognizedBoardModel.geometry_revision)
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .where(ImageReviewItemModel.id == document.review_item_id)
        ).one_or_none()
        if board is None:
            return ()
        board_id, geometry_revision = board
        cell = ImageSymbolReviewCellModel
        rows = self._session.execute(
            select(
                cell.cell_index,
                cell.id,
                cell.revision,
                cell.geometry_revision,
                cell.crop_sample_id,
                cell.crop_checksum_sha256,
                cell.review_state,
                cell.quality_issue,
                SymbolModel.code,
            )
            .outerjoin(SymbolModel, SymbolModel.id == cell.assigned_symbol_id)
            .where(
                cell.game_id == game_id,
                cell.review_item_id == document.review_item_id,
                cell.recognized_board_id == board_id,
                cell.geometry_revision == geometry_revision,
            )
            .order_by(cell.cell_index)
        ).tuples()
        return tuple(
            BoardSearchBoardCell(
                cell_index=int(cell_index),
                cell_review_id=cell_review_id,
                revision=int(revision),
                geometry_revision=int(cell_geometry_revision),
                crop_sample_id=crop_sample_id,
                crop_checksum_sha256=crop_checksum,
                review_state=review_state,
                quality_issue=quality_issue,
                assigned_symbol_code=symbol_code,
            )
            for (
                cell_index,
                cell_review_id,
                revision,
                cell_geometry_revision,
                crop_sample_id,
                crop_checksum,
                review_state,
                quality_issue,
                symbol_code,
            ) in rows
        )

    def refresh_board_document(
        self,
        *,
        game_id: UUID,
        document: BoardSearchBoardDocument,
    ) -> None:
        """Resynchronise one board's search candidate and document."""
        if document.review_item_id is None:
            raise BoardSearchError(
                "BOARD_SEARCH_BOARD_REFRESH_UNSUPPORTED",
                "Only operational board-search documents can be refreshed.",
            )
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.WRITE)
        # Every candidate that could own this position, not only the current
        # owner, so the reconciled document reflects all current records.
        self._projection.sync_review_item(document.review_item_id)
        self._projection.sync_sequence_candidates(game_id, document.sequence_number)
        self._session.flush()
        # Core upserts do not refresh loaded ORM rows; later reads must see
        # the rebuilt document, not a cached copy.
        self._session.expire_all()

    def stale_document_sequence_numbers(
        self,
        *,
        game_id: UUID,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[int, ...]:
        """Positions whose search document predates the board's current
        identity, in sequence order after a cursor (TASK-0814).

        Same rule as the board detail's staleness check: the board's current
        geometry checksum differs from the checksum the document was written
        with. Read-only.
        """
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
        document = ImageBoardSearchFastDocumentModel
        return tuple(
            int(sequence_number)
            for sequence_number in self._session.scalars(
                select(document.sequence_number)
                .join(ImageReviewItemModel, ImageReviewItemModel.id == document.review_item_id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .where(
                    document.game_id == game_id,
                    document.sequence_number > after_sequence_number,
                    func.coalesce(RecognizedBoardModel.geometry_checksum_sha256, "")
                    != document.board_checksum_sha256,
                )
                .order_by(document.sequence_number)
                .limit(limit)
            )
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
