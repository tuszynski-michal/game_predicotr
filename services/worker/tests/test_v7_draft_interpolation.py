import pytest
from game_predictor_worker.semi_automatic_selection.v7_draft_selection import (
    suggest_interpolated_choices,
)
from test_v7_draft_selection import frame


def gap(ascending=True):
    return [
        frame(0, 1 if ascending else 28, 5, 0.95, True),
        *[frame(n, 1, 0) for n in range(1, 31)],
        frame(31, 28 if ascending else 1, 5, 0.95, True),
    ]


@pytest.mark.parametrize("direction,starts", [("ascending", [10, 19]), ("descending", [19, 10])])
def test_thirty_images_split_into_fifteen_then_choose_middle(direction, starts):
    result = suggest_interpolated_choices(
        gap(direction == "ascending"), first=1, last=36, direction=direction
    )
    ordered = sorted(result, key=lambda row: row.source_index)
    assert [row.range_start for row in ordered] == starts
    assert [row.source_index for row in ordered] == [8, 23]
    assert [(row.interval_first, row.interval_last) for row in ordered] == [(1, 15), (16, 30)]
    assert result == suggest_interpolated_choices(
        list(reversed(gap(direction == "ascending"))), first=1, last=36, direction=direction
    )


def test_existing_choices_source_errors_and_contrary_labels_win():
    items = gap()
    items[8]["sourceErrorCode"] = "JPEG_INVALID"
    items[7] = frame(7, 28, 1)
    choices = suggest_interpolated_choices(items, first=1, last=36, occupied=frozenset({2}))
    assert len(choices) == 1 and choices[0].source_index == 9


def test_no_anchors_edges_short_interval_or_wrong_direction():
    assert not suggest_interpolated_choices([frame(0, 1, 0)], first=1, last=36)
    assert not suggest_interpolated_choices(gap()[:-1], first=1, last=36)
    assert not suggest_interpolated_choices(
        [frame(0, 1, 5, 0.95, True), frame(1, 10, 0), frame(2, 28, 5, 0.95, True)], first=1, last=36
    )
    assert not suggest_interpolated_choices(gap(), first=1, last=36, direction="descending")


def test_occurrence_edges_not_midpoint_define_partition():
    items = [frame(n, 1, 5, 0.95, True) for n in range(10)]
    items += [frame(n, 1, 0) for n in range(10, 40)]
    items += [frame(n, 28, 5, 0.95, True) for n in range(40, 50)]
    choices = suggest_interpolated_choices(items, first=1, last=36)
    assert [row.source_index for row in choices] == [17, 32]
    assert all(row.left_anchor_source == 9 and row.right_anchor_source == 40 for row in choices)


def test_two_occurrences_cannot_silently_choose_different_images_for_the_same_gap():
    items = gap() + [{**item, "sourceIndex": item["sourceIndex"] + 32} for item in gap()]
    assert not suggest_interpolated_choices(items, first=1, last=36)
