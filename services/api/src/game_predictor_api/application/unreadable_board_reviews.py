"""Application boundary for resolving unreadable cells in whole-board context."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationResult,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError


class UnreadableBoardReviewView(StrEnum):
    PENDING = "pending"
    ALL = "all"


@dataclass(frozen=True, slots=True)
class UnreadableBoardReviewListItem:
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int
    board_status: str
    grid_rows: int
    grid_columns: int
    unreadable_count: int
    pending_unreadable_count: int

    @property
    def cursor_key(self) -> tuple[int, str]:
        return self.sequence_number, str(self.review_item_id)


@dataclass(frozen=True, slots=True)
class UnreadableBoardReviewCell:
    cell_review_id: UUID
    cell_index: int
    row_index: int
    column_index: int
    assigned_symbol_id: UUID | None
    assigned_symbol_code: str | None
    assigned_symbol_name: str | None
    prediction_symbol_code: str | None
    review_state: str
    quality_issue: str | None
    revision: int
    geometry_revision: int
    crop_sample_id: str
    crop_checksum_sha256: str


@dataclass(frozen=True, slots=True)
class UnreadableBoardReviewDetail:
    review_item_id: UUID
    recognized_board_id: UUID
    import_job_id: UUID
    sequence_number: int
    board_status: str
    grid_rows: int
    grid_columns: int
    cells: tuple[UnreadableBoardReviewCell, ...]


@dataclass(frozen=True, slots=True)
class UnreadableBoardReviewSlice:
    items: tuple[UnreadableBoardReviewListItem, ...]
    has_next: bool


@dataclass(frozen=True, slots=True)
class UnreadableBoardReviewPage:
    items: tuple[UnreadableBoardReviewListItem, ...]
    next_cursor: str | None


@dataclass(frozen=True, slots=True)
class ResolveUnreadableCellCommand:
    game_id: UUID
    review_item_id: UUID
    cell_index: int
    expected_revision: int
    expected_geometry_revision: int
    expected_crop_sample_id: str
    expected_crop_checksum_sha256: str
    target_symbol_id: UUID | None
    actor: str


class UnreadableBoardReviewRepository(Protocol):
    def require_ready_game(self, game_id: UUID) -> None: ...

    def list_boards(
        self,
        *,
        game_id: UUID,
        view: UnreadableBoardReviewView,
        after_key: tuple[int, str] | None,
        limit: int,
    ) -> UnreadableBoardReviewSlice: ...

    def get_board(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
    ) -> UnreadableBoardReviewDetail | None: ...

    def resolve_cell(
        self,
        command: ResolveUnreadableCellCommand,
    ) -> SymbolCellReviewMutationResult: ...


class UnreadableBoardReviewService:
    def __init__(self, repository: UnreadableBoardReviewRepository) -> None:
        self._repository = repository

    def list(
        self,
        *,
        game_id: UUID,
        view: UnreadableBoardReviewView,
        after_cursor: str | None,
        limit: int,
    ) -> UnreadableBoardReviewPage:
        if not 1 <= limit <= 100:
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_PAGE_INVALID",
                "Unreadable board review pages must contain between 1 and 100 boards.",
            )
        self._repository.require_ready_game(game_id)
        after_key = (
            decode_unreadable_board_cursor(after_cursor, game_id=game_id, view=view)
            if after_cursor
            else None
        )
        page = self._repository.list_boards(
            game_id=game_id,
            view=view,
            after_key=after_key,
            limit=limit,
        )
        return UnreadableBoardReviewPage(
            items=page.items,
            next_cursor=(
                encode_unreadable_board_cursor(
                    game_id=game_id,
                    view=view,
                    key=page.items[-1].cursor_key,
                )
                if page.items and page.has_next
                else None
            ),
        )

    def detail(self, *, game_id: UUID, review_item_id: UUID) -> UnreadableBoardReviewDetail:
        self._repository.require_ready_game(game_id)
        detail = self._repository.get_board(game_id=game_id, review_item_id=review_item_id)
        if detail is None:
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_NOT_FOUND",
                "The unreadable board is not a current logical owner in this game.",
            )
        return detail

    def resolve(
        self,
        *,
        game_id: UUID,
        review_item_id: UUID,
        cell_index: int,
        expected_revision: int,
        expected_geometry_revision: int,
        expected_crop_sample_id: str,
        expected_crop_checksum_sha256: str,
        target_symbol_id: UUID | None,
        actor: str,
    ) -> SymbolCellReviewMutationResult:
        if cell_index < 0:
            raise SymbolCellReviewError(
                "UNREADABLE_BOARD_REVIEW_CELL_INVALID",
                "The unreadable cell index cannot be negative.",
            )
        return self._repository.resolve_cell(
            ResolveUnreadableCellCommand(
                game_id=game_id,
                review_item_id=review_item_id,
                cell_index=cell_index,
                expected_revision=expected_revision,
                expected_geometry_revision=expected_geometry_revision,
                expected_crop_sample_id=expected_crop_sample_id,
                expected_crop_checksum_sha256=expected_crop_checksum_sha256,
                target_symbol_id=target_symbol_id,
                actor=actor,
            )
        )


def encode_unreadable_board_cursor(
    *,
    game_id: UUID,
    view: UnreadableBoardReviewView,
    key: tuple[int, str],
) -> str:
    payload = {"gameId": str(game_id), "key": list(key), "version": 1, "view": view.value}
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_unreadable_board_cursor(
    value: str,
    *,
    game_id: UUID,
    view: UnreadableBoardReviewView,
) -> tuple[int, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        key = payload["key"]
        if (
            payload.get("version") != 1
            or payload.get("gameId") != str(game_id)
            or payload.get("view") != view.value
            or not isinstance(key, list)
            or len(key) != 2
            or not isinstance(key[0], int)
            or isinstance(key[0], bool)
            or key[0] < 1
            or not isinstance(key[1], str)
        ):
            raise ValueError
        UUID(key[1])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise SymbolCellReviewError(
            "UNREADABLE_BOARD_REVIEW_CURSOR_INVALID",
            "The unreadable board review cursor is invalid for this queue.",
        ) from error
    return key[0], key[1]


__all__ = [
    "ResolveUnreadableCellCommand",
    "UnreadableBoardReviewCell",
    "UnreadableBoardReviewDetail",
    "UnreadableBoardReviewListItem",
    "UnreadableBoardReviewPage",
    "UnreadableBoardReviewRepository",
    "UnreadableBoardReviewService",
    "UnreadableBoardReviewSlice",
    "UnreadableBoardReviewView",
    "decode_unreadable_board_cursor",
    "encode_unreadable_board_cursor",
]
