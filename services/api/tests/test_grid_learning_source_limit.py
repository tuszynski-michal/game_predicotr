"""D-610: one 20 000-source limit for grid-learning populations, in Python and SQL."""

from types import SimpleNamespace

import pytest
from game_predictor_api.domain.grid_correction_incremental_split import solve_incremental_split
from game_predictor_api.domain.grid_correction_split import (
    CORRECTION_SOURCE_LIMIT,
    CorrectionSplitError,
    solve_correction_split,
)
from game_predictor_api.storage import source_recording_source_limit as limit


def test_limit_is_twenty_thousand_sources() -> None:
    assert CORRECTION_SOURCE_LIMIT == limit.SOURCE_LIMIT == 20_000


@pytest.mark.parametrize("solve", [solve_correction_split, solve_incremental_split])
def test_solvers_reject_only_populations_above_the_limit(solve) -> None:
    too_many = [SimpleNamespace(source_id=f"{i:06d}") for i in range(CORRECTION_SOURCE_LIMIT + 1)]
    with pytest.raises(CorrectionSplitError, match="Source limit exceeded"):
        solve(too_many)
    # 7039 sources (Mumie A2, 2026-11-13) pass the limit and reach source validation.
    with pytest.raises(CorrectionSplitError) as error:
        solve([SimpleNamespace(source_id=f"{i:06d}", import_id="") for i in range(7039)])
    assert "Source limit exceeded" not in str(error.value)


class Connection:
    def __init__(self, definitions: dict[str, str], largest: int = 0) -> None:
        self.definitions, self.largest, self.executed = definitions, largest, []

    def scalar(self, statement, parameters=None):
        if parameters is None:
            return self.largest
        return self.definitions.get(parameters["signature"])

    def exec_driver_sql(self, sql: str) -> None:
        self.executed.append(sql)


def definitions(value: int) -> dict[str, str]:
    result = {
        signature: f"CREATE OR REPLACE FUNCTION {signature} ... "
        f"OR jsonb_array_length(plan->'sources')>{value} THEN"
        for signature in limit.COHORT_FUNCTIONS
    }
    result.update(
        {
            signature: f"CREATE OR REPLACE FUNCTION {signature} ... IF "
            f"cardinality(next_bytes)>{value} OR cardinality(next_pixels)>{value} THEN"
            for signature in limit.CONTEXT_FUNCTIONS
        }
    )
    return result


def test_upgrade_rewrites_only_the_exact_limit_predicates() -> None:
    connection = Connection(definitions(5000))
    limit.raise_source_limit(connection)
    assert len(connection.executed) == 6
    expected = definitions(20_000)
    assert connection.executed == [
        expected[s] for s in (*limit.COHORT_FUNCTIONS, *limit.CONTEXT_FUNCTIONS)
    ]


def test_unexpected_definitions_stop_the_migration() -> None:
    changed = definitions(5000)
    changed[limit.CONTEXT_FUNCTIONS[0]] = "CREATE FUNCTION nothing"
    with pytest.raises(RuntimeError, match="exactly one 5000 limit"):
        limit.raise_source_limit(Connection(changed))


def test_downgrade_restores_and_refuses_larger_cohorts() -> None:
    connection = Connection(definitions(20_000))
    limit.restore_source_limit(connection)
    assert connection.executed[0] == definitions(5000)[limit.COHORT_FUNCTIONS[0]]
    with pytest.raises(RuntimeError, match="above 5000 sources"):
        limit.restore_source_limit(Connection(definitions(20_000), largest=5001))
