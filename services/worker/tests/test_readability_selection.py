from collections import Counter

import pytest
from game_predictor_worker.symbols.readability_features import FrozenBase, ReadabilityError
from game_predictor_worker.symbols.readability_selection import freeze_pilot_selection


def row(index: int) -> dict:
    return dict(
        cell_id=f"cell{index}",
        source_id=f"source{index}",
        source_sha256=f"sha{index}",
        rendered_pixel_checksum_sha256=f"rgb{index}",
        recording_id=None,
        quality_issue="unreadable" if index % 2 == 0 else None,
    )


def test_test_is_frozen_before_rest_and_respects_base_recording_exposure() -> None:
    rows = [row(index) for index in range(800)]
    rows[0]["recording_id"] = rows[1]["recording_id"] = "base-training-recording"
    rows[2]["recording_id"] = rows[3]["recording_id"] = "base-control-recording"
    rows[160]["rendered_pixel_checksum_sha256"] = rows[2]["rendered_pixel_checksum_sha256"]
    # A protected baseline family is also discovered through its exact alias.
    base = FrozenBase(
        "c",
        "d",
        "s",
        ("a", "b"),
        (
            dict(
                sourceId="base-old",
                sourceSha256="oldsha",
                rgbSha256="rgb170",
                family="control",
                split="test",
            ),
        ),
    )
    exposure = {"base-training-recording": {"train"}, "base-control-recording": {"test"}}
    selected = freeze_pilot_selection(lambda: iter(rows), base, exposure)
    assert len(selected) == 600
    assert Counter(value["head_split"] for value in selected) == dict(
        test=120, validation=120, train=360
    )
    assert sum(value["quality_issue"] == "unreadable" for value in selected) == 300
    assert all(value["head_split"] == "test" for value in selected[:120])
    mapping = {value["cell_id"]: value["head_split"] for value in selected}
    assert mapping["cell0"] != "test" and mapping["cell1"] != "test"
    assert mapping["cell2"] == mapping["cell3"] == "test"
    assert "cell160" not in mapping and "cell170" not in mapping
    groups = {
        part: set().union(
            *(set(value["family_keys"]) for value in selected if value["head_split"] == part)
        )
        for part in ("test", "validation", "train")
    }
    assert not groups["test"] & groups["train"]
    assert not groups["test"] & groups["validation"]
    assert not groups["train"] & groups["validation"]
    labelled = [{**value, "overlap": True, "unreadable": False} for value in rows]
    repeated = freeze_pilot_selection(lambda: iter(labelled), base, exposure)
    assert [(r["cell_id"], r["head_split"]) for r in repeated] == [
        (r["cell_id"], r["head_split"]) for r in selected
    ]


def test_no_independent_test_population_stops_before_selecting_train() -> None:
    rows = [{**row(index), "recording_id": "training-recording"} for index in range(800)]
    base = FrozenBase("c", "d", "s", ("a", "b"), ())
    with pytest.raises(ReadabilityError) as stopped:
        freeze_pilot_selection(lambda: iter(rows), base, {"training-recording": {"train"}})
    assert stopped.value.code == "READABILITY_PILOT_STOP"
    assert "test" in str(stopped.value)
