"""Fresh REG is a protected, seeded preview, never an inferred recording declaration."""

from dataclasses import replace

from game_predictor_api.domain.grid_content_sampling import fresh_regression_preview
from game_predictor_api.domain.grid_correction_split import CorrectionSplitSource


def population():
    sources = [
        CorrectionSplitSource(
            str(i), f"import-{i}", f"{i:064x}", f"{i + 100:064x}", f"{i:064x}.jpg", 9
        )
        for i in range(1, 9)
    ]
    contexts = {
        s.source_id: {
            "proofSha256": f"{int(s.source_id) + 200:064x}",
            "priorRoles": [],
            "validationPurposes": [],
            "selectionExposed": False,
            "diagnosticExposed": False,
        }
        for s in sources
    }
    return sources, contexts


def test_seed_is_reproducible_order_independent_and_does_not_assign_ledger_roles():
    sources, contexts = population()
    labels = frozenset(contexts)
    first = fresh_regression_preview(sources, contexts, labels, ancestry_sha256="a" * 64)
    second = fresh_regression_preview(
        list(reversed(sources)), contexts, labels, ancestry_sha256="a" * 64
    )
    assert first == second
    assert first["seed"] == 20261108 and first["fullPhotos"] == 5
    assert first["roleWrites"] is False and first["recordingIndependence"] == "not_claimed"


def test_exposure_closes_over_known_session_and_copies_and_missing_ancestry_is_not_pass():
    sources, contexts = population()
    sources[0] = replace(sources[0], component_ids=("shared-session",))
    sources[1] = replace(sources[1], component_ids=("shared-session",))
    contexts[sources[0].source_id]["diagnosticExposed"] = True
    result = fresh_regression_preview(
        sources, contexts, frozenset(contexts), ancestry_sha256="a" * 64
    )
    assert not {"1", "2"} & set(result["sourceIds"])
    assert result["reasonCounts"]["CONTENT_REG_EXPOSURE_OR_UNKNOWN"] == 1
    missing = fresh_regression_preview(sources, contexts, frozenset(contexts), ancestry_sha256=None)
    assert missing["state"] == "not_evaluable" and missing["missingFullPhotos"] == 5


def test_protected_history_and_partial_photos_do_not_meet_full_photo_minimum():
    sources, contexts = population()
    for index in range(4):
        contexts[sources[index].source_id]["priorRoles"] = ["TRAIN"]
        sources[index] = replace(
            sources[index], frozen_role="TRAIN", allowed_roles=frozenset({"TRAIN"})
        )
    sources[4] = replace(sources[4], eligible_boards=8)
    result = fresh_regression_preview(
        sources, contexts, frozenset(contexts), ancestry_sha256="a" * 64
    )
    assert result["state"] == "not_evaluable" and result["fullPhotos"] == 3
    assert result["missingFullPhotos"] == 2


def test_five_full_photos_do_not_hide_unknown_members_of_the_same_session():
    sources, contexts = population()
    sources = [replace(s, component_ids=("session",)) for s in sources[:7]]
    contexts = {s.source_id: contexts[s.source_id] for s in sources}
    result = fresh_regression_preview(
        sources, contexts, frozenset(str(i) for i in range(1, 6)), ancestry_sha256="a" * 64
    )
    assert result["selectionState"] == "ready" and result["fullPhotos"] == 5
    assert result["state"] == "not_evaluable"
    assert result["populationCellSlots"] == 7 * 135
    assert result["unknownCellSlots"] == 2 * 135
    assert result["reasonCounts"]["CONTENT_UNKNOWN_LIMIT"] == 1
