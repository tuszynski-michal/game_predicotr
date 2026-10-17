"""Deterministic selection, explicit coverage and durable immutable metadata."""

from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_quality_measurements import (
    PopulationSampler,
    empty_judgments,
    measurement_report,
)
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.schemas.grid_quality_measurements import QualityAssessCommand
from game_predictor_api.storage.grid_quality_manifest import GridQualityManifestStore
from pydantic import ValidationError


def sample(seed="seed", metadata="a", size=10):
    sampler = PopulationSampler(seed, size)
    for index in range(501):
        sampler.add({"sourceId": str(UUID(int=index + 1)), "metadata": metadata})
    return sampler


def test_seed_population_digest_and_bounded_metadata_selection():
    first, same, changed = sample(), sample(), sample(metadata="b")
    assert first.selected == same.selected == changed.selected
    assert first.population_sha256 == same.population_sha256 != changed.population_sha256
    assert first.selected != sample(seed="different").selected
    assert first.count == 501 and len(first._selected) == 10
    assert len(sample(size=100)._selected) == 100


def test_sampler_requires_stable_unique_keyset():
    sampler = PopulationSampler("x", 1)
    sampler.add({"sourceId": str(UUID(int=1))})
    with pytest.raises(ValueError):
        sampler.add({"sourceId": str(UUID(int=1))})


def member(sample_kind="random", verdict="unreviewed", producer=None):
    return {
        "sampleKind": sample_kind,
        "positions": [
            {
                "positionIndex": index,
                "currentManualSymbolCount": 0,
                "currentSymbolCellCount": 15,
                "original": {"producer": producer},
            }
            for index in range(9)
        ],
        "judgments": [{**item, "geometry": verdict} for item in empty_judgments()],
        "unexpectedDetections": [],
    }


def test_hard_never_changes_random_denominator_and_missing_is_unknown():
    report = measurement_report([member(), member("hard", "incorrect")])
    assert report["random"]["axes"]["geometry"]["correctRate"] is None
    assert report["random"]["expectedPositionCount"] == 9
    assert report["random"]["completeUnknownCount"] == 1
    assert report["hard"]["axes"]["geometry"]["incorrect"] == 9
    assert report["random"]["producerCoverage"]["coverageGapCount"] == 9


def test_all_nine_geometry_and_all_axes_needed_for_complete_correct():
    value = member(verdict="correct", producer={"engineSnapshot": {"model": "a"}})
    assert measurement_report([value])["random"]["fullyReviewedCount"] == 1
    assert measurement_report([value])["random"]["completeCorrectCount"] == 0
    for item in value["judgments"]:
        item.update(detection="correct", sequence="correct")
    assert measurement_report([value])["random"]["completeCorrectCount"] == 1
    value["judgments"][4]["geometry"] = "not_assessable"
    assert measurement_report([value])["random"]["fullyAssessableCount"] == 0
    assert measurement_report([value])["random"]["completeUnknownCount"] == 1


def test_producer_coverage_separates_mixed_models_and_manual_symbol_counts():
    rows = [member(producer={"engineSnapshot": {"model": value}}) for value in ("a", "b")]
    rows[0]["positions"][0]["currentManualSymbolCount"] = 2
    report = measurement_report(rows)["random"]
    assert len(report["producerCoverage"]["producers"]) == 2
    assert report["producerCoverage"]["activeModelAccuracy"] is None
    assert report["symbols"]["currentManualConfirmationCount"] == 2
    assert report["symbols"]["classifierAccuracy"] is None


def assessment():
    return {
        "idempotencyKey": str(uuid4()),
        "sourceId": str(uuid4()),
        "sampleKind": "random",
        "expectedRevision": 0,
        "manifestSha256": "a" * 64,
        "positions": empty_judgments(),
    }


@pytest.mark.parametrize("kind", ["missing", "duplicate", "actor", "unexpected_duplicate"])
def test_closed_assessment_requires_nine_distinct_explicit_positions(kind):
    body = assessment()
    if kind == "missing":
        body["positions"].pop()
    elif kind == "duplicate":
        body["positions"][4]["positionIndex"] = 3
    elif kind == "actor":
        body["actor"] = "spoof"
    else:
        body["unexpected"] = [{"index": 1, "verdict": "correct"}] * 2
    with pytest.raises(ValidationError):
        QualityAssessCommand.model_validate(body)


def test_manifest_atomic_publication_cold_replay_and_missing_changed_blockers(tmp_path):
    first = GridQualityManifestStore(tmp_path)
    relative, sha = first.publish({"nine": list(range(9))})
    second = GridQualityManifestStore(tmp_path)
    assert second.publish({"nine": list(range(9))}) == (relative, sha)
    path = tmp_path / relative
    assert not list(path.parent.glob("*.staged"))
    path.write_text("changed")
    with pytest.raises(ImageReviewConflictError, match="checksum"):
        second.verify(relative, sha)

    path.unlink()
    with pytest.raises(ImageReviewConflictError, match="missing"):
        second.verify(relative, sha)


def test_pending_own_review_is_guarded_by_positive_live_identity_and_foreign_owner():
    from game_predictor_api.storage.grid_quality_observations import own_target

    target = {
        "board": {"id": "board", "source_image_id": "source", "status": "pending_review"},
        "review": {"id": "review", "status": "pending"},
        "owner": None,
        "foreignOwner": None,
    }
    assert own_target(target)
    target["foreignOwner"] = {"review_item_id": "other"}
    assert not own_target(target)
    target["foreignOwner"] = None
    target["owner"] = {
        "recognized_board_id": "other",
        "review_item_id": "other",
        "source_image_id": "other",
    }
    assert not own_target(target)
    target["owner"] = None
    target["review"]["status"] = "superseded"
    assert not own_target(target)
