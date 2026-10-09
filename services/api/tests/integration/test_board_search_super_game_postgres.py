"""Super game markers of board search on PostgreSQL (TASK-0935).

Uses the series fixtures of TASK-0933 (real application role, RLS, game
partitions): the marker read runs as the application role in the game scope.
"""

from __future__ import annotations

import os
from uuid import UUID

import pytest
from game_predictor_api.domain.super_game_markers import SuperGameMarkerKind, SuperGameMarkers
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.management_game_adapter import SqlAlchemyManagementGameAdapter
from game_predictor_api.storage.super_game_marker_repository import (
    SqlAlchemySuperGameMarkerRepository,
)
from sqlalchemy import text
from test_super_game_series_postgres import (  # type: ignore[import-not-found]
    Board,
    Fixture,
    _boards,
    _define,
    _derive,
    _seed,
    _series,
    _set_trigger_cells,
    fixture,  # noqa: F401  (pytest fixture shared with the series tests)
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires the disposable PostgreSQL integration database.",
)


def _markers(fixture_: Fixture, positions: list[int]) -> SuperGameMarkers:
    with fixture_.factory() as session, session.begin(), game_storage_scope(fixture_.game_id):
        return SqlAlchemySuperGameMarkerRepository(session).markers(fixture_.game_id, positions)


def _seed_two_series(fixture_: Fixture) -> dict[int, UUID]:
    _seed(
        fixture_,
        _boards(
            130,
            {
                100: Board(100, trigger_cells=3, human_cells=3),
                125: Board(125, trigger_cells=3, human_cells=0),
            },
        ),
    )
    _derive(fixture_)
    return {row[0]: row[8] for row in _series(fixture_)}


def test_markers_cover_the_trigger_the_spins_and_the_symbol_code(fixture: Fixture) -> None:  # noqa: F811
    series = _seed_two_series(fixture)
    _define(fixture, series[100], fixture.ordinary_symbol, 0)

    markers = _markers(fixture, [99, 100, 105, 110, 111, 125, 130, 131])

    assert sorted(markers.by_position) == [100, 105, 110, 125, 130, 131]
    trigger = markers.by_position[100]
    assert (trigger.kind, trigger.spin_index, trigger.series_id) == (
        SuperGameMarkerKind.TRIGGER,
        None,
        series[100],
    )
    assert trigger.series_length == 10 and trigger.super_symbol_code == "K"
    assert trigger.completeness.value == "complete" and trigger.run_verification.value == "verified"
    assert markers.by_position[105].spin_index == 5
    assert markers.by_position[105].super_symbol_code == "K"
    assert markers.by_position[110].spin_index == 10
    # 111 lies after the last spin of the first series and before the next trigger.
    assert 111 not in markers.by_position
    undefined = markers.by_position[125]
    assert (undefined.kind, undefined.super_symbol_code) == (SuperGameMarkerKind.TRIGGER, None)
    assert undefined.completeness.value == "incomplete"
    assert undefined.run_verification.value == "unverified"
    assert markers.by_position[130].series_id == series[125]
    assert markers.by_position[130].spin_index == 5
    assert markers.by_position[131].spin_index == 6
    assert markers.state.fresh and markers.state.has_super_game


def test_a_new_trigger_before_the_job_has_no_marker_but_the_state_is_stale(
    fixture: Fixture,  # noqa: F811
) -> None:
    _seed_two_series(fixture)
    _set_trigger_cells(fixture, 115, 3)  # a human correction; the job has not run

    markers = _markers(fixture, [105, 115, 118])

    assert 115 not in markers.by_position and 118 not in markers.by_position
    assert markers.by_position[105].spin_index == 5  # the last generation is served
    assert not markers.state.fresh
    assert markers.state.generation_input_version is not None
    assert markers.state.input_version > markers.state.generation_input_version

    _derive(fixture)
    after = _markers(fixture, [115, 118])
    assert after.by_position[115].kind is SuperGameMarkerKind.TRIGGER
    assert after.by_position[118].spin_index == 3
    assert after.state.fresh


def test_a_game_without_a_super_game_kind_has_no_markers_and_is_fresh(
    fixture: Fixture,  # noqa: F811
) -> None:
    _seed_two_series(fixture)
    with fixture.database.owner_engine.begin() as connection:
        connection.execute(
            text("UPDATE public.games SET super_game_kind = 'none' WHERE id = :g"),
            {"g": fixture.game_id},
        )

    markers = _markers(fixture, [100, 105])

    assert markers.by_position == {}
    assert markers.state.fresh and not markers.state.has_super_game


def test_no_positions_still_reads_the_state(fixture: Fixture) -> None:  # noqa: F811
    _seed_two_series(fixture)

    empty = _markers(fixture, [])

    assert empty.by_position == {}
    assert empty.state.fresh and empty.state.has_super_game


def test_the_management_adapter_reads_the_same_markers(fixture: Fixture) -> None:  # noqa: F811
    series = _seed_two_series(fixture)

    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        markers = SqlAlchemyManagementGameAdapter(session).super_game_row_markers(
            fixture.game_id, {100, 105, 999}
        )

    assert sorted(markers.by_position) == [100, 105]
    assert markers.by_position[105].series_id == series[100]
    assert markers.state.fresh
