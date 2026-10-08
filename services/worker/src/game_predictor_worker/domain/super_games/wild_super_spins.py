"""The ``wild_super_spins`` super game kind (D-535, plan MUMIE_SUPER_GAME).

A trigger opens a series of 10 free spins (cost 0) on the following positions
of the same sequence; a retrigger inside the series extends it by 10 without a
new super symbol. The board evaluation of a series spin (expanding the super
symbol over whole columns) arrives with TASK-0936; this module holds only the
constants of the kind.
"""

from __future__ import annotations

from typing import Final

from game_predictor_worker.domain.super_games.definition import SuperGameKindDefinition

WILD_SUPER_SPINS_CODE: Final = "wild_super_spins"
WILD_SUPER_SPINS_SERIES_LENGTH: Final = 10
WILD_SUPER_SPINS_RETRIGGER_EXTENSION: Final = 10
WILD_SUPER_SPINS_FREE_SPIN_COST: Final = 0

WILD_SUPER_SPINS: Final = SuperGameKindDefinition(
    code=WILD_SUPER_SPINS_CODE,
    label="Wild super spins",
    series_length=WILD_SUPER_SPINS_SERIES_LENGTH,
    retrigger_extension=WILD_SUPER_SPINS_RETRIGGER_EXTENSION,
    free_spin_cost=WILD_SUPER_SPINS_FREE_SPIN_COST,
)
