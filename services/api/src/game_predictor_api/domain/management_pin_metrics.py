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


def approximate_win_pin_metrics(
    result: PinResult,
    spin: int,
    *,
    super_spin_ranges: Sequence[tuple[int, int]] = (),
    super_spin_cost: int = 0,
) -> tuple[int, int | None, int | None]:
    """Return net balance, required investment and machine cash in credits.

    Investment tracks the lowest balance before each payout, including the
    cost of the first spin. The chart's zero point is explicitly all-zero.
    Unavailable pins keep the legacy balance but never invent investment/cash.
    """

    def cost_at(position: int) -> int:
        super_spins = sum(
            max(0, min(last, position) - first + 1) for first, last in super_spin_ranges
        )
        return (position - super_spins) * result.rules.spin_cost + super_spins * super_spin_cost

    cumulative = 0
    for row in result.rows:
        if row.spin_number > spin:
            break
        cumulative = row.cumulative_payout_credits
    balance = cumulative - cost_at(spin)
    if spin > result.evaluated_spin_count:
        return balance, None, None
    if spin == 0:
        return 0, 0, 0
    lowest = min(-cost_at(1), balance)
    for row in result.rows:
        if row.spin_number <= spin:
            paid = 0 if getattr(row, "payout_kind", None) == "provisional" else row.payout_credits
            lowest = min(lowest, row.cumulative_balance_credits - paid)
    investment = -lowest
    return balance, investment, investment + balance
