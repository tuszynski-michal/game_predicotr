"""Bounded rebuild interleavings with a serialized state checkpoint.

The fake session exercises repository batching and durable field choices, not
PostgreSQL lock scheduling. Migration/transaction tests cover the database.
"""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
    _apply_count_deltas,
    _CountedCellState,
)


def _state():
    return SimpleNamespace(
        status="ready",
        count_projection_status="ready",
        count_projection={"all": {"pending": 999}},
        count_projection_revision=8,
        count_rebuild_cursor=None,
        count_rebuild_accumulator={},
        count_projection_failure_message=None,
        catalog_revision=20,
    )


def _session(state, batches):
    session = Mock()
    session.get.return_value = state
    session.execute.side_effect = [SimpleNamespace(all=lambda rows=rows: rows) for rows in batches]
    return session


@pytest.mark.parametrize("change", ["regroup_scanned", "insert_before_cursor"])
def test_background_write_restarts_bounded_counts_after_checkpoint_restore(change):
    game_id, symbol_id = UUID(int=100), UUID(int=200)
    first = (UUID(int=10), True, None, "pending", None, "full")
    last = (UUID(int=20), False, None, "pending", None, "outside")
    state = _state()
    session = _session(state, [[first]])
    repository = SqlAlchemyImageSymbolReviewRepository(session)
    repository.start_count_rebuild(game_id)
    assert not repository.rebuild_count_projection_next_batch(game_id, batch_size=1)
    assert state.count_rebuild_cursor == first[0]
    assert state.count_rebuild_accumulator["unknown"]["pending"] == 1

    if change == "regroup_scanned":
        before = (_CountedCellState(True, None, "pending", None, "full"),)
        after = (_CountedCellState(True, symbol_id, "approved", None, "full"),)
        current = [(first[0], True, symbol_id, "approved", None, "full"), last]
    else:
        before = ()
        after = (_CountedCellState(False, None, "pending", None, "outside"),)
        current = [(UUID(int=5), False, None, "pending", None, "outside"), first, last]
    _apply_count_deltas(state, before=before, after=after)
    assert state.count_rebuild_cursor is None
    assert state.count_rebuild_accumulator == {"_building": {"version": 2}}

    # All restart information must live in serializable model fields, with no
    # dependency on the previous repository or Session.info in memory.
    restored = SimpleNamespace(**json.loads(json.dumps(vars(state))))
    restarted_session = _session(restored, [[row] for row in current] + [[]])
    restarted = SqlAlchemyImageSymbolReviewRepository(restarted_session)
    for _ in current:
        assert not restarted.rebuild_count_projection_next_batch(game_id, batch_size=1)
    assert restarted.rebuild_count_projection_next_batch(game_id, batch_size=1)

    first_query = restarted_session.execute.call_args_list[0].args[0]
    assert first_query.compile().params.get("id_1") is None
    assert all(
        call.args[0].compile().params["param_1"] == 1
        for call in restarted_session.execute.call_args_list
    )
    expected = (
        {
            "all": {"approved": 1, "pending": 1},
            "outside": {"pending": 1},
            f"symbol:{symbol_id}": {"approved": 1},
            "_semantics": {"version": 2},
        }
        if change == "regroup_scanned"
        else {
            "all": {"pending": 3},
            "outside": {"pending": 2},
            "unknown": {"pending": 1},
            "_semantics": {"version": 2},
        }
    )
    assert restored.count_projection == expected
    assert restored.status == restored.count_projection_status == "ready"
    assert restored.count_rebuild_cursor is None
    assert restored.count_rebuild_accumulator == {}


@pytest.mark.parametrize("old_marker", [None, {"version": 1}])
def test_pre_upgrade_checkpoint_rescans_instead_of_publishing_old_semantics(old_marker):
    game_id = UUID(int=100)
    state = _state()
    state.status = state.count_projection_status = "rebuilding"
    state.count_rebuild_cursor = UUID(int=99)
    state.count_rebuild_accumulator = {"all": {"pending": 999}}
    if old_marker is not None:
        state.count_rebuild_accumulator["_building"] = old_marker
    row = (UUID(int=5), False, None, "pending", None, "outside")
    session = _session(state, [[row], []])
    repository = SqlAlchemyImageSymbolReviewRepository(session)
    assert not repository.rebuild_count_projection_next_batch(game_id, batch_size=1)
    assert state.count_rebuild_cursor is None
    assert state.count_rebuild_accumulator == {"_building": {"version": 2}}
    session.execute.assert_not_called()
    assert not repository.rebuild_count_projection_next_batch(game_id, batch_size=1)
    assert repository.rebuild_count_projection_next_batch(game_id, batch_size=1)
    assert state.count_projection == {
        "all": {"pending": 1},
        "outside": {"pending": 1},
        "_semantics": {"version": 2},
    }


def test_backfill_finishes_unavailable_counts_and_resumes_a_cold_cursor():
    game_id = UUID(int=100)
    row = (UUID(int=5), True, None, "pending", None, "full")
    state = _state()
    state.count_projection_status = "unavailable"
    session = _session(state, [[row]])
    repository = SqlAlchemyImageSymbolReviewRepository(session)
    assert not repository.ensure_current_count_projection_next_batch(game_id, batch_size=1)
    assert state.count_rebuild_cursor == row[0]
    restored = SimpleNamespace(**vars(state))
    cold_session = _session(restored, [[]])
    cold = SqlAlchemyImageSymbolReviewRepository(cold_session)
    assert cold.ensure_current_count_projection_next_batch(game_id, batch_size=1)
    assert restored.count_projection == {
        "_semantics": {"version": 2},
        "all": {"pending": 1},
        "unknown": {"pending": 1},
    }
    assert restored.status == restored.count_projection_status == "ready"


def test_backfill_keeps_ready_current_counts_without_a_scan():
    state = _state()
    state.count_projection["_semantics"] = {"version": 2}
    session = _session(state, [])
    assert SqlAlchemyImageSymbolReviewRepository(
        session
    ).ensure_current_count_projection_next_batch(UUID(int=100))
    session.execute.assert_not_called()
    assert state.catalog_revision == 20
