"""Share-scoped symbol corrections and the owner's durable review (D-492)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

from game_predictor_api.application.board_search_share_access import BoardSearchShareContext
from game_predictor_api.domain.board_search_board_detail import BoardSearchBoardCell

CorrectionAction = Literal["approve", "reassign", "mark_unreadable", "mark_grid_issue"]
CorrectionStatus = Literal["pending", "reviewed", "all"]


def correction_fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def share_cell_version(game_id: UUID, sequence_number: int, cell: BoardSearchBoardCell) -> str:
    """One-way identity of the exact current owner, pixels and decision."""
    return correction_fingerprint(
        ["board-search-share-cell-v1", str(game_id), sequence_number, asdict(cell)]
    )


def share_board_version(
    game_id: UUID, sequence_number: int, cells: tuple[BoardSearchBoardCell, ...]
) -> str:
    return correction_fingerprint(
        [share_cell_version(game_id, sequence_number, cell) for cell in cells]
    )


@dataclass(frozen=True, slots=True)
class ShareCellCorrectionCommand:
    operation_id: UUID
    sequence_number: int
    cell_index: int
    expected_cell_version: str
    action: CorrectionAction
    target_symbol_code: str | None = None
    search_context_id: UUID | None = None
    start_sequence_number: int | None = None
    spin_count: int | None = None
    stake_grosze: int | None = None


@dataclass(frozen=True, slots=True)
class ShareCellCorrectionReceipt:
    sequence_number: int
    cell_index: int
    cell_version: str
    changed: bool
    saved: Literal[True] = True


@dataclass(frozen=True, slots=True)
class ShareCorrectionBoard:
    sequence_number: int
    revision: int
    changed_cell_count: int
    pending: bool
    last_changed_at: datetime
    last_event_id: UUID
    stake_grosze: int | None
    start_sequence_number: int | None


@dataclass(frozen=True, slots=True)
class ShareCorrectionPage:
    entries: tuple[ShareCorrectionBoard, ...]
    next_cursor: str | None
    total_count: int = 0
    pending_count: int = 0


@dataclass(frozen=True, slots=True)
class ShareCorrectionChange:
    id: UUID
    occurred_at: datetime
    cell_index: int
    before_symbol_code: str | None
    after_symbol_code: str | None
    before_quality_issue: str | None
    after_quality_issue: str | None
    before_review_state: str
    after_review_state: str


@dataclass(frozen=True, slots=True)
class ShareCorrectionDetail:
    board: ShareCorrectionBoard
    board_version: str
    changes: tuple[ShareCorrectionChange, ...]
    next_cursor: str | None


class BoardSearchShareCorrectionRepository(Protocol):
    def correct(
        self,
        context: BoardSearchShareContext,
        access_token: str,
        command: ShareCellCorrectionCommand,
    ) -> ShareCellCorrectionReceipt: ...

    def list_boards(
        self,
        session_id: UUID,
        *,
        status: CorrectionStatus,
        before: str | None,
        limit: int,
        pattern: list[str] | None,
    ) -> ShareCorrectionPage: ...

    def detail(
        self, session_id: UUID, sequence_number: int, *, before: str | None, limit: int
    ) -> ShareCorrectionDetail: ...

    def review(
        self,
        session_id: UUID,
        sequence_number: int,
        *,
        expected_revision: int,
        expected_board_version: str,
    ) -> ShareCorrectionBoard: ...


class BoardSearchShareCorrectionService:
    def __init__(self, repository: BoardSearchShareCorrectionRepository) -> None:
        self._repository = repository

    def correct(
        self,
        context: BoardSearchShareContext,
        access_token: str,
        command: ShareCellCorrectionCommand,
    ) -> ShareCellCorrectionReceipt:
        return self._repository.correct(context, access_token, command)

    def list_boards(
        self,
        session_id: UUID,
        *,
        status: CorrectionStatus = "pending",
        before: str | None = None,
        limit: int = 25,
        pattern: list[str] | None = None,
    ) -> ShareCorrectionPage:
        return self._repository.list_boards(
            session_id, status=status, before=before, limit=limit, pattern=pattern
        )

    def detail(
        self, session_id: UUID, sequence_number: int, *, before: str | None = None, limit: int = 50
    ) -> ShareCorrectionDetail:
        return self._repository.detail(session_id, sequence_number, before=before, limit=limit)

    def review(
        self,
        session_id: UUID,
        sequence_number: int,
        *,
        expected_revision: int,
        expected_board_version: str,
    ) -> ShareCorrectionBoard:
        return self._repository.review(
            session_id,
            sequence_number,
            expected_revision=expected_revision,
            expected_board_version=expected_board_version,
        )
