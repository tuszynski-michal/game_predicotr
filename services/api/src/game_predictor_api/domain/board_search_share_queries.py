"""Query log entries of board-search share links (D-472).

Every data query made through a share link is recorded with what is needed
to reproduce it in the Admin and a short result summary. Unlocks, context,
symbols and images are not queries. No IP address or browser header is ever
part of an entry.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from game_predictor_api.domain.board_search_shares import BoardSearchShareError

QUERY_REQUEST_MAX_BYTES: Final = 4096
QUERY_RESULT_SUMMARY_MAX_BYTES: Final = 2048
QUERY_SUMMARY_SEQUENCE_NUMBERS_MAX: Final = 5
QUERY_OUTCOME_OK: Final = "ok"


class BoardSearchShareQueryKind(StrEnum):
    SEARCH = "search"
    APPROXIMATE_WIN = "approximate_win"
    BOARD_DETAIL = "board_detail"


@dataclass(frozen=True, slots=True)
class BoardSearchShareQueryEntry:
    """A validated entry ready to be stored."""

    kind: BoardSearchShareQueryKind
    request: dict[str, object]
    result_summary: dict[str, object]
    outcome_code: str


def search_query_request(
    *,
    cells: Sequence[tuple[int, str | None]],
    scope: str,
    limit: int,
) -> dict[str, object]:
    """The full pattern, including unknown `?` cells, in the Admin query form
    `cellIndex:symbolCode|?`, ordered by cell index."""

    return {
        "cells": [
            f"{index}:{'?' if code is None else code}"
            for index, code in sorted(cells, key=lambda cell: cell[0])
        ],
        "scope": scope,
        "limit": limit,
    }


def search_query_summary(sequence_numbers: Sequence[int]) -> dict[str, object]:
    return {
        "resultCount": len(sequence_numbers),
        "firstSequenceNumbers": list(sequence_numbers[:QUERY_SUMMARY_SEQUENCE_NUMBERS_MAX]),
    }


def approximate_win_query_request(
    *, start_sequence_number: int, spin_count: int
) -> dict[str, object]:
    return {"startSequenceNumber": start_sequence_number, "spinCount": spin_count}


# A stake far above any real one only bounds the stored integer.
QUERY_STAKE_GROSZE_MAX: Final = 10_000_000


def approximate_win_stake_query_request(
    *, start_sequence_number: int, spin_count: int, stake_grosze: int | None
) -> dict[str, object]:
    """The stake the recipient views an already calculated range at (D-487).

    Stored as a range entry with `stakeGrosze` (`None` is the base stake of
    the published rules) and an empty summary: nothing is calculated."""

    return {
        "startSequenceNumber": start_sequence_number,
        "spinCount": spin_count,
        "stakeGrosze": stake_grosze,
    }


def approximate_win_query_summary(
    *,
    evaluated_spin_count: int,
    recognized_payout_credits: int,
    spin_cost_credits: int,
    balance_credits: int,
    row_count: int,
) -> dict[str, object]:
    return {
        "evaluatedSpinCount": evaluated_spin_count,
        "recognizedPayoutCredits": recognized_payout_credits,
        "spinCostCredits": spin_cost_credits,
        "balanceCredits": balance_credits,
        "rowCount": row_count,
    }


def board_detail_query_request(*, sequence_number: int) -> dict[str, object]:
    return {"sequenceNumber": sequence_number}


def board_detail_query_summary(*, payout_credits: int, document_stale: bool) -> dict[str, object]:
    return {"payoutCredits": payout_credits, "documentStale": document_stale}


_REQUEST_KEYS: Final = {
    BoardSearchShareQueryKind.SEARCH: (frozenset({"cells", "scope", "limit"}),),
    BoardSearchShareQueryKind.APPROXIMATE_WIN: (
        frozenset({"startSequenceNumber", "spinCount"}),
        frozenset({"startSequenceNumber", "spinCount", "stakeGrosze"}),
    ),
    BoardSearchShareQueryKind.BOARD_DETAIL: (frozenset({"sequenceNumber"}),),
}


def build_board_search_share_query_entry(
    *,
    kind: BoardSearchShareQueryKind,
    request: dict[str, object],
    result_summary: dict[str, object] | None,
    outcome_code: str,
) -> BoardSearchShareQueryEntry:
    """Validate one entry. A wrong shape or size is a programming error
    (`ValueError`), never user data to truncate silently."""

    if set(request) not in _REQUEST_KEYS[kind]:
        raise ValueError(f"Query log request keys do not match kind {kind.value!r}.")
    summary = {} if result_summary is None else dict(result_summary)
    if not outcome_code.strip() or len(outcome_code) > 100:
        raise ValueError("Query log outcome code must contain 1-100 characters.")
    if outcome_code != QUERY_OUTCOME_OK and summary:
        raise ValueError("A failed query has no result summary.")
    if _json_size(request) > QUERY_REQUEST_MAX_BYTES:
        raise ValueError("Query log request exceeds 4 KiB.")
    if _json_size(summary) > QUERY_RESULT_SUMMARY_MAX_BYTES:
        raise ValueError("Query log result summary exceeds 2 KiB.")
    return BoardSearchShareQueryEntry(
        kind=kind,
        request=dict(request),
        result_summary=summary,
        outcome_code=outcome_code,
    )


def _json_size(value: dict[str, object]) -> int:
    # The default separators match PostgreSQL's `jsonb::text` spacing, which
    # the table's size constraint measures.
    return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))


QUERY_LOG_PAGE_SIZE_MAX: Final = 50


def encode_query_log_cursor(occurred_at: datetime, event_id: UUID) -> str:
    """Opaque keyset cursor `(occurred_at, id)` of the last entry on a page."""

    raw = json.dumps(
        {"at": occurred_at.isoformat(), "id": str(event_id)}, separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_query_log_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        occurred_at = datetime.fromisoformat(payload["at"])
        event_id = UUID(payload["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_QUERY_CURSOR_INVALID", "The query log cursor is invalid."
        ) from error
    if occurred_at.tzinfo is None:
        raise BoardSearchShareError(
            "BOARD_SEARCH_SHARE_QUERY_CURSOR_INVALID", "The query log cursor is invalid."
        )
    return occurred_at, event_id


__all__ = [
    "QUERY_LOG_PAGE_SIZE_MAX",
    "QUERY_OUTCOME_OK",
    "QUERY_REQUEST_MAX_BYTES",
    "QUERY_RESULT_SUMMARY_MAX_BYTES",
    "QUERY_STAKE_GROSZE_MAX",
    "BoardSearchShareQueryEntry",
    "BoardSearchShareQueryKind",
    "approximate_win_query_request",
    "approximate_win_query_summary",
    "approximate_win_stake_query_request",
    "board_detail_query_request",
    "board_detail_query_summary",
    "build_board_search_share_query_entry",
    "decode_query_log_cursor",
    "encode_query_log_cursor",
    "search_query_request",
    "search_query_summary",
]
