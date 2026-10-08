"""Shared description of one code-defined super game kind."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SuperGameKindDefinition:
    """Static parameters of one super game kind.

    ``series_length`` is the number of free spins a trigger opens,
    ``retrigger_extension`` the number of spins added by a retrigger inside a
    running series and ``free_spin_cost`` the credit cost of one series spin.
    The kind ``none`` has no series, so all three values are ``0``.
    """

    code: str
    label: str
    series_length: int
    retrigger_extension: int
    free_spin_cost: int

    @property
    def has_super_game(self) -> bool:
        return self.series_length > 0
