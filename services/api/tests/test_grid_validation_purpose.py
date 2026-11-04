"""Explicit whole-component A/B refinement and historical exposure protections."""

from dataclasses import replace

import pytest
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.grid_validation_purpose import (
    constrain_validation_sources,
    refine_validation_purposes,
    validation_component_choices,
)
from test_grid_correction_split import source


def evidence():
    sources = [
        source(i, import_id=name)
        for name, count in (("train", 10), ("a", 5), ("b", 5), ("reg", 5))
        for i in range(count)
    ]
    pins = [
        {
            "sourceId": item.source_id,
            "role": "TRAIN"
            if item.import_id == "train"
            else "REGRESSION"
            if item.import_id == "reg"
            else "VALIDATION",
            "representative": True,
            "eligibleBoards": 3,
            "buffer": False,
        }
        for item in sources
    ]
    contexts = {
        item.source_id: {
            "proofSha256": "1" * 64,
            "validationPurposes": [],
            "selectionExposed": False,
            "diagnosticExposed": False,
        }
        for item in sources
    }
    assignments = {item.source_id: "B" for item in sources if item.import_id == "b"}
    return {"sources": pins}, sources, contexts, assignments


def test_existing_minima_and_partial_b_are_preserved_without_writes():
    split, sources, contexts, assignments = evidence()
    result = refine_validation_purposes(split, sources, contexts, assignments, full_training=False)
    assert result["purposeCounts"]["VALIDATION-A"]["boards"] == 15
    assert result["purposeCounts"]["VALIDATION-B"]["photos"] == 5
    assert "validationPurpose" not in split["sources"][0]


def test_no_b_keeps_existing_training_minima_without_claiming_automatic_qualification():
    split, sources, contexts, _ = evidence()
    result = refine_validation_purposes(split, sources, contexts, {}, full_training=False)
    assert result["purposeCounts"]["VALIDATION-A"]["photos"] == 10
    assert "VALIDATION-B" not in result["purposeCounts"]
    assert result["schemaVersion"] == "grid-correction-split-v4"


def test_public_choices_use_exact_component_closure_and_the_refinement_guards():
    split, sources, contexts, assignments = evidence()
    sources = [
        replace(item, component_ids=("paired",)) if item.source_id in ("a-0000", "b-0000") else item
        for item in sources
    ]
    contexts["a-0000"]["selectionExposed"] = True
    groups = validation_component_choices(sources, contexts)
    paired = next(
        item for item in groups if any(s["sourceId"] == "a-0000" for s in item["sources"])
    )
    assert {item["sourceId"] for item in paired["sources"]} == {"a-0000", "b-0000"}
    options = {item["purpose"]: item for item in paired["options"]}
    assert options["A"]["allowed"]
    assert not options["B"]["allowed"] and options["B"]["reasonCodes"] == [
        "GRID_VALIDATION_SELECTION_EXPOSED"
    ]
    with pytest.raises(GridCohortError, match="A-only"):
        refine_validation_purposes(split, sources, contexts, {"b-0000": "B"}, full_training=False)
    # A protected TRAIN component cannot be repurposed just because a UI group is eligible.
    protected = replace(sources[0], frozen_role="TRAIN")
    locked = validation_component_choices(
        [protected], {protected.source_id: contexts[protected.source_id]}
    )[0]
    assert not any(option["allowed"] for option in locked["options"])


@pytest.mark.parametrize("field", ["selectionExposed", "diagnosticExposed"])
def test_historical_selection_or_diagnostic_cannot_become_b(field):
    split, sources, contexts, assignments = evidence()
    contexts["b-0000"][field] = True
    with pytest.raises(GridCohortError):
        refine_validation_purposes(split, sources, contexts, assignments, full_training=False)


def test_session_component_cannot_be_split_between_a_and_b():
    split, sources, contexts, assignments = evidence()
    sources = [
        replace(item, component_ids=("same-session",)) if item.import_id in ("a", "b") else item
        for item in sources
    ]
    assignments["a-0000"] = "A"
    with pytest.raises(GridCohortError, match="component"):
        refine_validation_purposes(split, sources, contexts, assignments, full_training=False)


def test_screen_partial_a_does_not_count_as_full_selection():
    split, sources, contexts, assignments = evidence()
    with pytest.raises(GridCohortError, match="minima"):
        refine_validation_purposes(split, sources, contexts, assignments, full_training=True)


def test_explicit_b_pins_whole_component_without_releasing_train():
    _, sources, _, _ = evidence()
    sources = [
        replace(item, component_ids=("session-b",)) if item.import_id == "b" else item
        for item in sources
    ]
    constrained = constrain_validation_sources(sources, {"b-0000": "B"})
    assert all(item.frozen_role == "VALIDATION" for item in constrained if item.import_id == "b")
    protected = [
        replace(item, frozen_role="TRAIN") if item.import_id == "b" else item for item in sources
    ]
    with pytest.raises(GridCohortError, match="protected"):
        constrain_validation_sources(protected, {"b-0000": "B"})
