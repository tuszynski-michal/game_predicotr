"""Reusable frozen-result metrics matching the approximate-win chart helpers."""

from collections.abc import Sequence
from typing import Protocol


class PinRow(Protocol):
    @property
    def spin_number(self) -> int: ...

    @property
    def cumulative_payout_credits(self) -> int: ...

    @property
    def cumulative_balance_credits(self) -> int: ...

    @property
    def payout_credits(self) -> int: ...


class PinRules(Protocol):
    @property
    def spin_cost(self) -> int: ...


class PinResult(Protocol):
    @property
    def rows(self) -> Sequence[PinRow]: ...

    @property
    def rules(self) -> PinRules: ...

    @property
    def evaluated_spin_count(self) -> int: ...


def approximate_win_pin_metrics(result: PinResult, spin: int) -> tuple[int, int | None, int | None]:
    """Return net balance, required investment and machine cash in credits.

    Investment tracks the lowest balance before each payout, including the
    cost of the first spin. The chart's zero point is explicitly all-zero.
    Unavailable pins keep the legacy balance but never invent investment/cash.
    """
    cumulative = 0
    for row in result.rows:
        if row.spin_number > spin:
            break
        cumulative = row.cumulative_payout_credits
    balance = cumulative - spin * result.rules.spin_cost
    if spin > result.evaluated_spin_count:
        return balance, None, None
    if spin == 0:
        return 0, 0, 0
    lowest = min(-result.rules.spin_cost, balance)
    for row in result.rows:
        if row.spin_number <= spin:
            lowest = min(lowest, row.cumulative_balance_credits - row.payout_credits)
    investment = -lowest
    return balance, investment, investment + balance
