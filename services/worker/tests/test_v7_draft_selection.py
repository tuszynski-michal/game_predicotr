from game_predictor_worker.semi_automatic_selection.v7_draft_selection import suggest_draft_choices


def frame(source, start, count, confidence=0.8, proven=False):
    return {
        "sourceIndex": source,
        "sourceErrorCode": None,
        "proof": {
            "kind": "strong_five_label" if proven else "none",
            "rangeStart": start if proven else None,
        },
        "labels": [
            {
                "positionIndex": p,
                "sequenceNumber": start + p,
                "recognitionConfidence": confidence,
                "positionConfidence": 0.95,
            }
            for p in range(count)
        ],
    }


def test_four_partial_labels_are_a_draft_not_a_proof():
    result = suggest_draft_choices([frame(1, 10, 4)], first=1, last=27)
    assert len(result) == 1
    assert (result[0].range_start, result[0].source_index, result[0].reason) == (
        10,
        1,
        "partial_four_labels",
    )


def test_two_votes_require_close_proven_neighbours_and_no_interpolation():
    frames = [frame(0, 1, 5, 0.95, True), frame(1, 10, 2), frame(2, 19, 5, 0.95, True)]
    choices = suggest_draft_choices(frames, first=1, last=27, occupied=frozenset({0, 2}))
    assert [choice.range_start for choice in choices] == [10]
    assert not suggest_draft_choices([frame(1, 10, 2)], first=1, last=27)
    assert not suggest_draft_choices([frame(1, 10, 0)], first=1, last=27)


def test_owners_and_neighbour_bounds_win():
    frames = [frame(0, 1, 5, 0.95, True), frame(1, 19, 4), frame(2, 10, 5, 0.95, True)]
    assert not suggest_draft_choices(frames, first=1, last=27, occupied=frozenset({0, 1}))


def test_conflict_is_recorded_and_restart_order_is_deterministic():
    item = frame(1, 10, 4)
    item["labels"].append(
        {
            "positionIndex": 8,
            "sequenceNumber": 200,
            "recognitionConfidence": 0.99,
            "positionConfidence": 0.95,
        }
    )
    choices = suggest_draft_choices([item], first=1, last=27)
    assert choices[0].conflicting_labels == 1
    assert choices == suggest_draft_choices([item], first=1, last=27)
