"""Super game series as a state of the layout sequence (D-535, TASK-0933).

The derivation is one pass over the positions ``1 … expected_layout_count``
that starts in base mode at position 1.  A cut board in base mode with at
least ``N`` cells assigned to a trigger symbol (``N`` is that symbol's
``super_game_trigger_count``) opens a series on the following positions
(``start = trigger + 1``, ``length = series_length`` of the game's super game
kind).  Inside a series, a cut board with at least ``N`` trigger cells
extends the running series by ``retrigger_extension`` and is recorded as a
retrigger.  A position without a cut board is an empty board: it consumes a
spin and never triggers.  The wrap-around ``N -> 1`` does not carry a series:
positions beyond ``expected_layout_count`` do not exist.

The pass is streaming: :class:`SuperGameSeriesDeriver` keeps only the series
that is currently running, so a caller can feed boards in batches without
loading the whole sequence.  Positions that do not trigger never change the
state, so a caller may feed only the boards that reach a trigger threshold;
the result is the same as feeding every position.

Two attributes are derived per series:

- ``completeness`` is ``incomplete`` when the real end of the series
  (``trigger + length``) lies beyond the last known cut board; every series
  closed by a later board is therefore complete.  This includes a series at
  the end of the sequence whose spins would fall beyond
  ``expected_layout_count``: those spins are unknown, not known to be empty,
  and they are never carried over to position 1 (audit TASK-0933 P0-2);
- ``run_verification`` is ``verified`` only when the trigger and every
  retrigger reach their threshold on human-decided cells alone.

This module is pure: no I/O, no ORM, deterministic for a given input.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final
from uuid import UUID

SUPER_GAME_SERIES_MAX_SEQUENCE_NUMBER: Final = 10_000_000


class SeriesCompleteness(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


class RunVerification(StrEnum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"


class SuperGameSeriesError(ValueError):
    """Stable domain failure of super game series derivation or definition."""

    def __init__(
        self, code: str, message: str, *, details: Mapping[str, object] | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = dict(details or {})


class SuperGameSeriesNotFoundError(SuperGameSeriesError):
    """The series (or its game) does not exist."""


class SuperGameSeriesConflictError(SuperGameSeriesError):
    """A compare-and-set precondition no longer holds."""


@dataclass(frozen=True, slots=True)
class TriggerCellCount:
    """Cells of one trigger symbol on one cut board.

    ``assigned`` counts every cell with that assigned symbol (human decision or
    model prediction); ``human`` counts the subset decided by a human.
    """

    assigned: int
    human: int

    def __post_init__(self) -> None:
        if self.assigned < 0 or self.human < 0 or self.human > self.assigned:
            raise SuperGameSeriesError(
                "SUPER_GAME_TRIGGER_COUNT_INVALID",
                "Trigger cell counts must satisfy 0 <= human <= assigned.",
            )


@dataclass(frozen=True, slots=True)
class BoardTrigger:
    """A cut board that reaches the threshold of at least one trigger symbol."""

    sequence_number: int
    human_verified: bool


def evaluate_board_trigger(
    sequence_number: int,
    counts: Mapping[UUID, TriggerCellCount],
    thresholds: Mapping[UUID, int],
) -> BoardTrigger | None:
    """Return the trigger of one cut board, or ``None`` when it does not trigger.

    A board triggers when some trigger symbol has at least its threshold of
    assigned cells.  The trigger is human-verified when some trigger symbol
    reaches its threshold on human-decided cells alone, i.e. the trigger does
    not rely on any model prediction.
    """

    triggered = False
    verified = False
    for symbol_id, threshold in thresholds.items():
        count = counts.get(symbol_id)
        if count is None or threshold < 1:
            continue
        if count.assigned >= threshold:
            triggered = True
        if count.human >= threshold:
            verified = True
    if not triggered:
        return None
    return BoardTrigger(sequence_number=sequence_number, human_verified=verified)


@dataclass(frozen=True, slots=True)
class DerivedSuperGameSeries:
    trigger_sequence_number: int
    start_sequence_number: int
    length: int
    retrigger_sequence_numbers: tuple[int, ...]
    completeness: SeriesCompleteness
    run_verification: RunVerification

    @property
    def end_sequence_number(self) -> int:
        return self.start_sequence_number + self.length - 1


@dataclass(slots=True)
class _RunningSeries:
    trigger: int
    length: int
    verified: bool
    retriggers: list[int] = field(default_factory=list)

    @property
    def start(self) -> int:
        return self.trigger + 1

    @property
    def end(self) -> int:
        return self.trigger + self.length

    def close(self, completeness: SeriesCompleteness) -> DerivedSuperGameSeries:
        return DerivedSuperGameSeries(
            trigger_sequence_number=self.trigger,
            start_sequence_number=self.start,
            length=self.length,
            retrigger_sequence_numbers=tuple(self.retriggers),
            completeness=completeness,
            run_verification=(
                RunVerification.VERIFIED if self.verified else RunVerification.UNVERIFIED
            ),
        )


class SuperGameSeriesDeriver:
    """Streaming state machine of one derivation pass.

    Feed :class:`BoardTrigger` values in strictly ascending sequence order
    with :meth:`feed`; each call returns the series that the fed position
    closed.  :meth:`finish` closes the running series using the last known
    cut board of the whole pass.
    """

    def __init__(
        self,
        *,
        series_length: int,
        retrigger_extension: int,
        expected_layout_count: int,
    ) -> None:
        if series_length < 1 or retrigger_extension < 0:
            raise SuperGameSeriesError(
                "SUPER_GAME_KIND_WITHOUT_SERIES",
                "Only a super game kind with series can be derived.",
            )
        if not 1 <= expected_layout_count <= SUPER_GAME_SERIES_MAX_SEQUENCE_NUMBER:
            raise SuperGameSeriesError(
                "SUPER_GAME_SEQUENCE_LENGTH_INVALID",
                "The expected layout count is outside the supported range.",
            )
        self._series_length = series_length
        self._retrigger_extension = retrigger_extension
        self._expected_layout_count = expected_layout_count
        self._running: _RunningSeries | None = None
        self._last_sequence_number = 0
        self._finished = False

    def feed(self, board: BoardTrigger) -> list[DerivedSuperGameSeries]:
        if self._finished:
            raise SuperGameSeriesError(
                "SUPER_GAME_DERIVATION_FINISHED", "The derivation pass is already finished."
            )
        position = board.sequence_number
        if position <= self._last_sequence_number:
            raise SuperGameSeriesError(
                "SUPER_GAME_SEQUENCE_ORDER",
                "Boards must be fed in strictly ascending sequence order.",
                details={"sequenceNumber": position, "previous": self._last_sequence_number},
            )
        if position > self._expected_layout_count:
            # Wrap-around does not carry a series; such positions do not exist.
            raise SuperGameSeriesError(
                "SUPER_GAME_SEQUENCE_OUT_OF_RANGE",
                "A board lies beyond the expected layout count of the game.",
                details={"sequenceNumber": position},
            )
        self._last_sequence_number = position
        closed: list[DerivedSuperGameSeries] = []
        running = self._running
        if running is not None and position > running.end:
            # A later board is known, so every position of the series is known.
            closed.append(running.close(SeriesCompleteness.COMPLETE))
            running = self._running = None
        if running is None:
            self._running = _RunningSeries(
                trigger=position,
                length=self._series_length,
                verified=board.human_verified,
            )
        else:
            running.length += self._retrigger_extension
            running.retriggers.append(position)
            running.verified = running.verified and board.human_verified
        return closed

    def finish(self, *, last_known_sequence_number: int | None) -> list[DerivedSuperGameSeries]:
        """Close the running series; ``last_known_sequence_number`` is the last cut board."""

        if self._finished:
            raise SuperGameSeriesError(
                "SUPER_GAME_DERIVATION_FINISHED", "The derivation pass is already finished."
            )
        self._finished = True
        running = self._running
        self._running = None
        if running is None:
            return []
        last_known = max(last_known_sequence_number or 0, self._last_sequence_number)
        # The real end, not capped at the sequence end (audit P0-2).
        completeness = (
            SeriesCompleteness.COMPLETE
            if running.end <= last_known
            else SeriesCompleteness.INCOMPLETE
        )
        return [running.close(completeness)]


def derive_super_game_series(
    boards: Iterable[BoardTrigger],
    *,
    series_length: int,
    retrigger_extension: int,
    expected_layout_count: int,
    last_known_sequence_number: int | None,
) -> list[DerivedSuperGameSeries]:
    """Convenience wrapper over :class:`SuperGameSeriesDeriver` for small inputs."""

    deriver = SuperGameSeriesDeriver(
        series_length=series_length,
        retrigger_extension=retrigger_extension,
        expected_layout_count=expected_layout_count,
    )
    result: list[DerivedSuperGameSeries] = []
    for board in boards:
        result.extend(deriver.feed(board))
    result.extend(deriver.finish(last_known_sequence_number=last_known_sequence_number))
    return result


def series_positions(
    trigger_sequence_number: int, length: int, expected_layout_count: int
) -> range:
    """Positions shown for one series: the trigger and every series spin.

    Positions beyond ``expected_layout_count`` do not exist (no wrap-around).
    """

    last = min(trigger_sequence_number + length, expected_layout_count)
    return range(trigger_sequence_number, last + 1)


@dataclass(frozen=True, slots=True)
class SuperGameState:
    """Freshness of the published series of one game.

    Staleness is never stored: it is always derived from the input version of
    the game and the input version of the published generation.  A game
    without a super game kind has nothing to derive and is always fresh.
    """

    input_version: int
    generation_input_version: int | None
    has_super_game: bool

    @property
    def fresh(self) -> bool:
        if not self.has_super_game:
            return True
        return self.generation_input_version == self.input_version


def validate_super_symbol_candidate(
    *,
    is_wildcard: bool,
    super_game_trigger_count: int | None,
    status: str,
) -> None:
    """A super symbol must be an ordinary active symbol (not Wild, not a trigger)."""

    if is_wildcard or super_game_trigger_count is not None or status != "active":
        raise SuperGameSeriesError(
            "SUPER_SYMBOL_NOT_ORDINARY",
            "A super symbol must be an ordinary active symbol, neither Wild nor a trigger.",
            details={
                "isWildcard": is_wildcard,
                "superGameTriggerCount": super_game_trigger_count,
                "status": status,
            },
        )


__all__ = [
    "SUPER_GAME_SERIES_MAX_SEQUENCE_NUMBER",
    "BoardTrigger",
    "DerivedSuperGameSeries",
    "RunVerification",
    "SeriesCompleteness",
    "SuperGameSeriesConflictError",
    "SuperGameSeriesDeriver",
    "SuperGameSeriesError",
    "SuperGameSeriesNotFoundError",
    "SuperGameState",
    "TriggerCellCount",
    "derive_super_game_series",
    "evaluate_board_trigger",
    "series_positions",
    "validate_super_symbol_candidate",
]
