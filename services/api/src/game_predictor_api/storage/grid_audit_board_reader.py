"""Read-only current state of the boards named by a grid-audit proposal list."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from game_predictor_api.application.grid_audit_proposals import GridAuditBoardReader
from game_predictor_api.domain.grid_audit_proposals import (
    GridAuditBoardState,
    GridAuditProposalItem,
)
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListFilter,
    ImageGridReviewListItem,
    ImageGridReviewView,
)
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.models import ImageReviewItemModel, RecognizedBoardModel

# The review item statuses of a current board (as the grid correction queue).
CURRENT_REVIEW_ITEM_STATUSES = ("pending", "accepted", "corrected")
_BOARD_ID_CHUNK = 1000
# One photo has at most nine boards plus deferred slots.
_PHOTO_SLOT_LIMIT = 100


class SqlAlchemyGridAuditBoardReader(GridAuditBoardReader):
    def __init__(self, session: Session) -> None:
        self._session = session

    def board_states(
        self, *, game_id: UUID, board_ids: Sequence[UUID]
    ) -> Mapping[UUID, GridAuditBoardState]:
        del game_id  # the board table is routed by the bound game storage scope
        board = RecognizedBoardModel
        review = ImageReviewItemModel
        current_review = exists(
            select(review.id).where(
                review.recognized_board_id == board.id,
                review.status.in_(CURRENT_REVIEW_ITEM_STATUSES),
            )
        )
        unique = list(dict.fromkeys(board_ids))
        states: dict[UUID, GridAuditBoardState] = {}
        for start in range(0, len(unique), _BOARD_ID_CHUNK):
            chunk = unique[start : start + _BOARD_ID_CHUNK]
            for board_id, revision, has_review in self._session.execute(
                select(board.id, board.geometry_revision, current_review).where(board.id.in_(chunk))
            ).tuples():
                states[board_id] = GridAuditBoardState(
                    recognized_board_id=board_id,
                    geometry_revision=int(revision),
                    current_review_item=bool(has_review),
                )
        return states

    def review_item(
        self, *, game_id: UUID, item: GridAuditProposalItem
    ) -> ImageGridReviewListItem | None:
        """The board as the correction queue serves it (same row mapping)."""

        page = SqlAlchemyImageGridReviewRepository(self._session).list_grid_reviews(
            review_filter=ImageGridReviewListFilter(
                game_id=game_id,
                view=ImageGridReviewView.ALL,
                import_job_id=None,
                source_image_id=item.source_image_id,
            ),
            after_key=None,
            before_key=None,
            limit=_PHOTO_SLOT_LIMIT,
        )
        for candidate in page.items:
            if candidate.recognized_board_id == item.recognized_board_id:
                return candidate
        return None


__all__ = ["CURRENT_REVIEW_ITEM_STATUSES", "SqlAlchemyGridAuditBoardReader"]
