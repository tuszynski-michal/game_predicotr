"""Quality groups require verified cell truth and never compensate new damage."""

from copy import deepcopy

import pytest
from game_predictor_worker.images.comparison_content_changes import content_change


def evidence():
    model = {
        "state": "available",
        "matchAmbiguous": False,
        "cells": [
            {
                "cellIndex": i,
                "contentState": "visible",
                "assessment": {
                    "finalContentState": "preserved",
                    "wrongCell": False,
                    "tie": False,
                    "foreignFullSymbol": False,
                },
            }
            for i in range(15)
        ],
    }
    return {"state": "available", "models": {"base": deepcopy(model), "candidate": model}}


def test_same_board_new_damage_is_not_hidden_by_another_repaired_symbol():
    value = evidence()
    value["models"]["base"]["cells"][0]["assessment"]["finalContentState"] = "clipped"
    value["models"]["candidate"]["cells"][1]["assessment"]["finalContentState"] = "borderline"
    assert content_change(value) == {"state": "degraded", "improvedCells": 1, "degradedCells": 1}


@pytest.mark.parametrize("flag", ["wrongCell", "tie", "foreignFullSymbol"])
def test_foreign_or_wrong_assignment_is_damage_even_when_all_pixels_fit(flag):
    value = evidence()
    value["models"]["candidate"]["cells"][3]["assessment"][flag] = True
    assert content_change(value)["state"] == "degraded"


@pytest.mark.parametrize("failure", ["unknown", "occluded", "duplicate", "ambiguous", "no_truth"])
def test_missing_or_unresolved_reference_never_declares_improvement(failure):
    value = evidence()
    model = value["models"]["candidate"]
    if failure in ("unknown", "occluded"):
        model["cells"][0]["contentState"] = failure
    elif failure == "duplicate":
        model["cells"][1]["cellIndex"] = 0
    elif failure == "ambiguous":
        model["matchAmbiguous"] = True
    else:
        model["cells"][0]["assessment"] = None
    assert content_change(value)["state"] == "unresolved"


def test_repair_and_unchanged_are_separate_from_coordinate_displacement():
    value = evidence()
    assert content_change(value)["state"] == "unchanged"
    value["models"]["base"]["cells"][7]["assessment"]["finalContentState"] = "missing"
    assert content_change(value) == {"state": "improved", "improvedCells": 1, "degradedCells": 0}


def test_unknown_cell_does_not_hide_new_damage_in_another_visible_cell():
    value = evidence()
    value["models"]["candidate"]["cells"][0]["contentState"] = "unknown"
    value["models"]["candidate"]["cells"][8]["assessment"]["finalContentState"] = "clipped"
    assert content_change(value)["state"] == "degraded"
    assert content_change(value)["degradedCells"] == 1
