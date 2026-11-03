from dataclasses import replace

import pytest
from game_predictor_api.domain.grid_correction_incremental_split import solve_incremental_split
from game_predictor_api.domain.grid_correction_progress import correction_progress_counts
from game_predictor_api.domain.grid_correction_split import CorrectionSplitError
from test_grid_correction_split import source


def islands():
    return [
        replace(
            source(i, boards=3 if i < 10 or 20 <= i < 25 or 35 <= i < 40 or i >= 50 else 0),
            frozen_role="TRAIN"
            if i < 10
            else "VALIDATION"
            if 20 <= i < 25
            else "REGRESSION"
            if 35 <= i < 40
            else None,
            frozen_buffer=10 <= i < 20 or 25 <= i < 35,
        )
        for i in range(80)
    ]


def test_growth_after_control_with_ten_all_source_photos_and_no_tail_reservation():
    values = islands()
    result = solve_incremental_split(values)
    assignments = dict(result.assignments)
    assert assignments[values[50].source_id] == "TRAIN"
    assert [c.boards for c in result.role_counts] == [120, 15, 15]
    assert all(assignments[values[i].source_id] == "REGRESSION" for i in range(35, 40))
    assert all(values[i].source_id in result.buffers for i in range(40, 50))
    assert result == solve_incremental_split(reversed(values))


def test_protected_reserve_is_not_released_and_future_reserves_are_bounded():
    values = islands() + [source(i, boards=0) for i in range(80, 100)]
    values[49] = replace(values[49], frozen_role="REGRESSION")
    result = solve_incremental_split(values)
    assert dict(result.assignments)[values[49].source_id] == "REGRESSION"
    assert dict(result.assignments)[values[50].source_id] is None
    for role in ("VALIDATION", "REGRESSION"):
        assert (
            sum(
                r == role and values[int(k.rsplit("-", 1)[1])].eligible_boards == 0
                for k, r in result.assignments
            )
            <= 5
        )
    assert all(dict(result.assignments)[values[i].source_id] is None for i in range(80, 100))


def test_session_alias_and_unordered_import_never_cross_roles():
    values = islands()
    values[65] = replace(values[65], component_ids=("session",))
    values[35] = replace(values[35], component_ids=("session",))
    result = solve_incremental_split(values)
    assert dict(result.assignments)[values[65].source_id] == "REGRESSION"
    values[0] = replace(values[0], attestation_checksum_sha256="0" * 64)
    with pytest.raises(CorrectionSplitError):
        solve_incremental_split(values)


def test_work_limit_fails_closed():
    with pytest.raises(CorrectionSplitError, match="budget"):
        solve_incremental_split(islands(), max_work=1)


def test_future_reserve_uses_only_pending_photos_and_caps_five_without_reducing_train():
    values = [replace(source(i, import_id="train"), frozen_role="TRAIN") for i in range(10)]
    values += [
        replace(
            source(i, import_id="validation", boards=3 if i < 5 else 0),
            frozen_role="VALIDATION" if i < 5 else None,
            pending_correction=5 <= i < 13,
        )
        for i in range(16)
    ]
    values += [
        replace(source(i, import_id="regression"), frozen_role="REGRESSION") for i in range(5)
    ]
    result = solve_incremental_split(values)
    assignments = dict(result.assignments)
    pending = [s for s in values if s.pending_correction]
    assert sum(assignments[s.source_id] == "VALIDATION" for s in pending) == 5
    assert all(
        assignments[s.source_id] is None
        for s in values
        if s.import_id == "validation" and s.eligible_boards == 0 and not s.pending_correction
    )
    assert result.role_counts[0].boards == 30


def test_new_position_on_used_photo_is_a_new_board_and_photo_counts_overlap():
    counts = correction_progress_counts(
        {
            "sources": [
                {
                    "representative": True,
                    "eligibleBoards": 3,
                    "usedTrainBoards": 2,
                    "role": "TRAIN",
                    "buffer": False,
                },
                {
                    "representative": True,
                    "eligibleBoards": 0,
                    "role": "VALIDATION",
                    "buffer": False,
                    "pendingCorrection": True,
                },
                {"representative": True, "eligibleBoards": 1, "role": None, "buffer": True},
                {"representative": False, "eligibleBoards": 3, "role": "TRAIN", "buffer": False},
            ]
        }
    )
    assert counts["availableTrain"] == {"photos": 1, "boards": 3}
    assert counts["usedTrain"] == {"photos": 1, "boards": 2}
    assert counts["newTrain"] == {"photos": 1, "boards": 1}
    assert counts["validationReserve"] == {"photos": 1, "boards": 0}
    assert counts["approved"] == {"photos": 2, "boards": 4}
    assert counts["excluded"] == {"photos": 1, "boards": 1}


def test_nonpending_control_is_explained_without_counting_as_a_future_reserve():
    counts = correction_progress_counts(
        {
            "sources": [
                {
                    "representative": True,
                    "eligibleBoards": 0,
                    "role": "REGRESSION",
                    "buffer": False,
                    "pendingCorrection": False,
                },
            ]
        }
    )
    assert counts["regressionReserve"] == {"photos": 0, "boards": 0}
    assert counts["excluded"] == {"photos": 1, "boards": 0}
    assert counts["exclusionReasons"] == [
        {"reason": "GRID_CORRECTION_CONTROL_NOT_PENDING", "photos": 1, "boards": 0}
    ]


def test_reserve_distance_precomputation_uses_linear_budget():
    values = [replace(source(i, import_id="train"), frozen_role="TRAIN") for i in range(10)]
    values += [
        replace(source(i, import_id="regression"), frozen_role="REGRESSION") for i in range(5)
    ]
    values += [
        replace(
            source(i, import_id="validation", boards=3 if i < 5 else 0),
            frozen_role="VALIDATION" if i < 5 else None,
            pending_correction=i >= 5,
        )
        for i in range(1255)
    ]
    result = solve_incremental_split(values, max_work=10_000)
    roles = dict(result.assignments)
    reserved = [s for s in values if s.pending_correction and roles[s.source_id] == "VALIDATION"]
    assert reserved == values[20:25]
    assert result == solve_incremental_split(reversed(values), max_work=10_000)
