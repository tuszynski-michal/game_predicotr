import pytest
from game_predictor_worker.semi_automatic_selection.v7_draft_coverage import (
    suggest_complete_choices,
)
from test_v7_draft_selection import frame


def select(items, pages=4, occupied=frozenset(), direction="ascending", source_count=None):
    return suggest_complete_choices(
        items,
        first=1,
        last=pages * 9,
        source_count=source_count if source_count is not None else len(items),
        occupied=occupied,
        direction=direction,
    )


@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_twenty_frames_two_missing_groups_choose_fifth_and_fifteenth(direction):
    descending = direction == "descending"
    items = [frame(0, 28 if descending else 1, 5, 0.95, True)]
    items += [frame(n, 1, 0) for n in range(1, 21)]
    items += [frame(21, 1 if descending else 28, 5, 0.95, True)]
    result = select(items, occupied=frozenset({0, 3}), direction=direction)
    ordered = sorted(result, key=lambda item: item.source_index)
    assert [item.source_index for item in ordered] == [5, 15]
    assert [(item.interval_first, item.interval_last) for item in ordered] == [(1, 10), (11, 20)]
    assert [item.range_start for item in ordered] == ([19, 10] if descending else [10, 19])
    assert result == select(list(reversed(items)), occupied=frozenset({0, 3}), direction=direction)


def test_conflicting_readings_do_not_leave_a_group_without_a_picture():
    items = [frame(0, 1, 5, 0.95, True)]
    items += [frame(n, 900, 1) for n in range(1, 21)]
    items += [frame(21, 28, 5, 0.95, True)]
    result = select(items, occupied=frozenset({0, 3}))
    assert [item.source_index for item in result] == [5, 15]
    assert [item.conflicting_labels for item in result] == [1, 1]
    assert all(item.reason == "estimated_partition" for item in result)


def test_light_verification_prefers_matching_image_within_the_partition():
    items = [frame(0, 1, 5, 0.95, True)]
    items += [frame(n, 900, 1) for n in range(1, 21)]
    items[7] = frame(7, 10, 1)
    items += [frame(21, 28, 5, 0.95, True)]
    assert select(items, occupied=frozenset({0, 3}))[0].source_index == 7


def test_prefix_and_suffix_receive_central_photos():
    items = [frame(n, 1, 0) for n in range(25)]
    for source in range(10, 15):
        items[source] = frame(source, 19, 5, 0.95, True)
    result = select(items, pages=5, occupied=frozenset({2}))
    assert [item.source_index for item in result] == [2, 7, 17, 22]
    assert [item.reason for item in result] == [
        "estimated_prefix",
        "estimated_prefix",
        "estimated_suffix",
        "estimated_suffix",
    ]


@pytest.mark.parametrize("direction", ["ascending", "descending"])
def test_no_anchors_partitions_entire_source_without_omissions(direction):
    result = select([], pages=4, direction=direction, source_count=20)
    assert {item.expected_index for item in result} == set(range(4))
    assert [item.source_index for item in result] == (
        [2, 7, 12, 17] if direction == "ascending" else [17, 12, 7, 2]
    )
    assert all(item.reason == "estimated_whole_source" for item in result)


def test_short_empty_intervals_and_reuse_remain_explicit_choices():
    result = select([], pages=4, source_count=1)
    assert len(result) == 4
    assert {item.source_index for item in result} == {0}
    assert sum(item.reused_source for item in result) == 3
    assert result[0].reason == "estimated_nearest_available"
    items = [frame(0, 1, 5, 0.95, True), frame(1, 28, 5, 0.95, True)]
    assert len(select(items, occupied=frozenset({0, 3}))) == 2


def test_large_gap_has_no_arbitrary_128_group_limit():
    items = [frame(0, 1, 5, 0.95, True), frame(1, 1351, 5, 0.95, True)]
    result = select(items, pages=151, occupied=frozenset({0, 150}))
    assert {item.expected_index for item in result} == set(range(1, 150))


def test_repeated_and_reversed_occurrences_have_deterministic_complete_coverage():
    items = [
        frame(0, 1, 5, 0.95, True),
        frame(1, 28, 5, 0.95, True),
        frame(2, 1, 5, 0.95, True),
        frame(3, 19, 5, 0.95, True),
        frame(4, 28, 5, 0.95, True),
    ]
    result = select(items)
    assert {item.expected_index for item in result} == set(range(4))
    assert result == select(list(reversed(items)))
    assert next(item for item in result if item.expected_index == 1).right_anchor_source == 3


def test_source_errors_use_nearby_image_without_suppressing_the_group():
    items = [frame(n, 1, 0) for n in range(4)]
    items[0]["sourceErrorCode"] = "JPEG_INVALID"
    assert len(select(items)) == 4
    assert all(item.source_index != 0 for item in select(items))
    for item in items:
        item["sourceErrorCode"] = "JPEG_INVALID"
    with pytest.raises(ValueError, match="no usable source"):
        select(items)


def test_occupied_choices_keep_precedence_and_do_not_need_a_source():
    items = [frame(0, 1, 0)]
    items[0]["sourceErrorCode"] = "JPEG_INVALID"
    assert not select(items, pages=1, occupied=frozenset({0}))


@pytest.mark.parametrize(
    "kwargs,match",
    [
        ({"first": 0}, "complete"),
        ({"last": 8}, "complete"),
        ({"source_count": 0}, "at least one"),
        ({"direction": "random"}, "direction"),
        ({"occupied": frozenset({1})}, "Occupied"),
    ],
)
def test_invalid_configuration_is_an_error_not_fake_coverage(kwargs, match):
    args = {"first": 1, "last": 9, "source_count": 1, **kwargs}
    with pytest.raises(ValueError, match=match):
        suggest_complete_choices([], **args)


@pytest.mark.parametrize("items", [[frame(0, 1, 0)] * 2, [frame(2, 1, 0)]])
def test_duplicate_and_out_of_bounds_source_indexes_fail(items):
    with pytest.raises(ValueError, match="source diagnostics"):
        select(items, source_count=1)
