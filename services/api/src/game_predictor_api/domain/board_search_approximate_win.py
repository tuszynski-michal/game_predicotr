"""Pure domain calculator for the admin "Przybliżona wygrana" range.

Given a starting logical board `S` and a positive spin count `N`, this module
plans the deterministic range `S+1..S+N` (the same cyclic full-cycle
definition already accepted for the mobile target forecast, `ALGORITHMS.md`
§C, D-116) and turns per-position projected symbol evidence into a payout
summary, a completeness breakdown and a compact table of winning spins.

This module owns no I/O and knows nothing about SQLAlchemy, FastAPI or the
worker package: it receives already-loaded `ApproximateWinDocument` values
and an injected `evaluate` callback (the caller wires in a real payout
evaluator, e.g. `PreparedPayoutEvaluator.evaluate` from
`game_predictor_worker.domain.payout`). A missing position never calls
`evaluate`; any exception `evaluate` raises for a symbol outside the active
rules configuration is left to propagate uncaught, so an unrecognized code
fails the whole range instead of being silently skipped.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from game_predictor_api.domain.board_search import BOARD_SEARCH_CELL_COUNT, BoardSearchError

# Reuse the same 3x5 cell count as partial board search: both read the same
# `image_board_search_fast_documents` / `legacy_board_search_archive_documents`
# projection.
APPROXIMATE_WIN_CELL_COUNT = BOARD_SEARCH_CELL_COUNT

_UNKNOWN_MOBILE_CODE = 0
"""Sentinel used by `evaluate_payout`/`PreparedPayoutEvaluator` for an unknown
or missing cell (D-247); never a real catalog symbol."""


@dataclass(frozen=True, slots=True)
class ApproximateWinDocument:
    """One logical board's projected symbol evidence for the calculator.

    `mobile_codes` has exactly `APPROXIMATE_WIN_CELL_COUNT` row-major
    entries; `None` means a logical `?`, an unrecognized/unavailable cell or
    a cell cut off by partial geometry — never a guessed value.
    """

    sequence_number: int
    status: str
    board_checksum_sha256: str
    mobile_codes: tuple[int | None, ...]

    def __post_init__(self) -> None:
        if self.sequence_number < 1:
            raise ValueError("sequence_number must be positive")
        if len(self.mobile_codes) != APPROXIMATE_WIN_CELL_COUNT:
            raise ValueError(
                f"mobile_codes must contain exactly {APPROXIMATE_WIN_CELL_COUNT} entries"
            )

    @property
    def is_complete(self) -> bool:
        return all(code is not None for code in self.mobile_codes)


@dataclass(frozen=True, slots=True)
class ApproximateWinRow:
    """One evaluated spin with a positive recognized payout."""

    spin_number: int
    sequence_number: int
    payout_credits: int
    cumulative_payout_credits: int
    cumulative_cost_credits: int
    cumulative_balance_credits: int
    payout_kind: str
    """`"exact"` for a complete board, `"confirmed_minimum"` for a partial
    board whose visible prefix already guarantees this payout."""
    board_status: str


@dataclass(frozen=True, slots=True)
class ApproximateWinSummary:
    recognized_payout_credits: int
    spin_cost_credits: int
    balance_credits: int


@dataclass(frozen=True, slots=True)
class ApproximateWinCompleteness:
    """Disjoint counts over the evaluated range; always sum to
    `evaluated_spin_count`. A partial board with a confirmed payout is still
    counted as partial, never as complete."""

    complete_board_count: int
    partial_board_count: int
    missing_board_count: int


@dataclass(frozen=True, slots=True)
class ApproximateWinResult:
    start_sequence_number: int
    requested_spin_count: int
    evaluated_spin_count: int
    sequence_length: int
    wrapped_at_sequence_end: bool
    summary: ApproximateWinSummary
    completeness: ApproximateWinCompleteness
    rows: tuple[ApproximateWinRow, ...]
    data_fingerprint_sha256: str


def plan_approximate_win_positions(
    *,
    start_sequence_number: int,
    requested_spin_count: int,
    sequence_length: int,
) -> tuple[int, ...]:
    """Plan the deterministic range `S+1..S+N`, wrapping cyclically past the
    sequence end and never re-including the starting position `S`.

    Mirrors the mobile target forecast's full-cycle definition
    (`ALGORITHMS.md` §C, D-116): `evaluated_spin_count = min(N, L - 1)`, and
    `sequence_number(n) = ((S - 1 + n) mod L) + 1` for `n = 1..evaluated_spin_count`.
    """

    if sequence_length < 1:
        raise BoardSearchError(
            "APPROXIMATE_WIN_START_OUT_OF_RANGE",
            "The game's sequence length must be positive.",
        )
    if not 1 <= start_sequence_number <= sequence_length:
        raise BoardSearchError(
            "APPROXIMATE_WIN_START_OUT_OF_RANGE",
            "The starting board must belong to the game's sequence.",
        )
    if requested_spin_count < 1:
        raise BoardSearchError(
            "APPROXIMATE_WIN_SPIN_COUNT_INVALID",
            "The approximate-win spin count must be a positive integer.",
        )

    evaluated_spin_count = min(requested_spin_count, sequence_length - 1)
    return tuple(
        ((start_sequence_number - 1 + n) % sequence_length) + 1
        for n in range(1, evaluated_spin_count + 1)
    )


def calculate_approximate_win(
    *,
    start_sequence_number: int,
    requested_spin_count: int,
    sequence_length: int,
    documents: Sequence[ApproximateWinDocument],
    evaluate: Callable[[Sequence[int]], int],
    spin_cost: int,
) -> ApproximateWinResult:
    """Calculate the approximate-win range `S+1..S+N`.

    A missing position (no document) never calls `evaluate`: it contributes
    its spin cost and zero recognized payout, and counts toward
    `missing_board_count`. Every existing document is evaluated once,
    regardless of whether it is complete or partial; a partial board that
    still earns a confirmed minimum payout is never reclassified as
    complete. Cumulative payout/cost/balance in every row account for every
    prior evaluated spin, including missing boards and rows that never
    appear in `rows` because their payout is zero.
    """

    if spin_cost < 0:
        raise ValueError("spin_cost must be non-negative")

    positions = plan_approximate_win_positions(
        start_sequence_number=start_sequence_number,
        requested_spin_count=requested_spin_count,
        sequence_length=sequence_length,
    )

    documents_by_sequence: dict[int, ApproximateWinDocument] = {}
    for candidate in documents:
        if candidate.sequence_number in documents_by_sequence:
            raise ValueError(
                f"Duplicate approximate-win document for sequence_number "
                f"{candidate.sequence_number}."
            )
        documents_by_sequence[candidate.sequence_number] = candidate

    complete_count = 0
    partial_count = 0
    missing_count = 0
    cumulative_payout = 0
    cumulative_cost = 0
    rows: list[ApproximateWinRow] = []
    fingerprint_parts: list[str] = []

    for spin_number, sequence_number in enumerate(positions, start=1):
        cumulative_cost += spin_cost
        document = documents_by_sequence.get(sequence_number)

        if document is None:
            missing_count += 1
            fingerprint_parts.append(f"{sequence_number}:missing")
            continue

        fingerprint_parts.append(
            f"{sequence_number}:{document.status}:{document.board_checksum_sha256}:"
            + ",".join("?" if code is None else str(code) for code in document.mobile_codes)
        )

        if document.is_complete:
            complete_count += 1
        else:
            partial_count += 1

        cells = tuple(
            _UNKNOWN_MOBILE_CODE if code is None else code for code in document.mobile_codes
        )
        payout_credits = evaluate(cells)
        cumulative_payout += payout_credits

        if payout_credits > 0:
            rows.append(
                ApproximateWinRow(
                    spin_number=spin_number,
                    sequence_number=sequence_number,
                    payout_credits=payout_credits,
                    cumulative_payout_credits=cumulative_payout,
                    cumulative_cost_credits=cumulative_cost,
                    cumulative_balance_credits=cumulative_payout - cumulative_cost,
                    payout_kind="exact" if document.is_complete else "confirmed_minimum",
                    board_status=document.status,
                )
            )

    evaluated_spin_count = len(positions)
    wrapped_at_sequence_end = (start_sequence_number + evaluated_spin_count) > sequence_length
    fingerprint = hashlib.sha256("|".join(fingerprint_parts).encode("utf-8")).hexdigest()

    return ApproximateWinResult(
        start_sequence_number=start_sequence_number,
        requested_spin_count=requested_spin_count,
        evaluated_spin_count=evaluated_spin_count,
        sequence_length=sequence_length,
        wrapped_at_sequence_end=wrapped_at_sequence_end,
        summary=ApproximateWinSummary(
            recognized_payout_credits=cumulative_payout,
            spin_cost_credits=cumulative_cost,
            balance_credits=cumulative_payout - cumulative_cost,
        ),
        completeness=ApproximateWinCompleteness(
            complete_board_count=complete_count,
            partial_board_count=partial_count,
            missing_board_count=missing_count,
        ),
        rows=tuple(rows),
        data_fingerprint_sha256=fingerprint,
    )


__all__ = [
    "APPROXIMATE_WIN_CELL_COUNT",
    "ApproximateWinCompleteness",
    "ApproximateWinDocument",
    "ApproximateWinResult",
    "ApproximateWinRow",
    "ApproximateWinSummary",
    "calculate_approximate_win",
    "plan_approximate_win_positions",
]
