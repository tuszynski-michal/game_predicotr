from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from game_predictor_worker.symbols import reference_library_writer as writer
from game_predictor_worker.symbols.reference_library_writer import (
    LIBRARY_CONFIDENCE,
    MODEL_VERSION,
    TARGET_QUALITY_CHANGED,
    ReferenceLibraryWriteError,
    TargetCell,
    predictions_digest,
    revert_checksum,
    rewrite_predictions,
)


def _predictions() -> list[dict[str, object]]:
    return [
        {
            "rowIndex": index // 5,
            "columnIndex": index % 5,
            "symbolCode": "ARBUZ" if index == 7 else "WISNIA",
            "confidence": 0.5,
            "alternatives": [{"symbolCode": "ARBUZ", "confidence": 0.5}],
            "virtualCell": {"renderSpec": {"cellIndex": index}},
        }
        for index in range(15)
    ]


def _target(index: int = 7, old: str = "ARBUZ", new: str = "CYTRYNA") -> TargetCell:
    return TargetCell(uuid4(), index, "a" * 64, old, new, 7, 7)


def test_only_target_cells_are_rewritten_and_provenance_is_kept() -> None:
    original = _predictions()

    rewritten = rewrite_predictions(original, [_target()])

    assert rewritten[7]["symbolCode"] == "CYTRYNA"
    assert rewritten[7]["confidence"] == LIBRARY_CONFIDENCE
    assert rewritten[7]["alternatives"] == [
        {"symbolCode": "CYTRYNA", "confidence": LIBRARY_CONFIDENCE}
    ]
    assert rewritten[7]["virtualCell"] == original[7]["virtualCell"]
    assert rewritten[7]["referenceLibrary"]["version"] == MODEL_VERSION
    assert rewritten[7]["referenceLibrary"]["previousSymbolCode"] == "ARBUZ"
    assert [entry for index, entry in enumerate(rewritten) if index != 7] == [
        entry for index, entry in enumerate(original) if index != 7
    ]
    assert original[7]["symbolCode"] == "ARBUZ"


def test_confirmation_keeps_the_symbol_and_records_the_library() -> None:
    rewritten = rewrite_predictions(_predictions(), [_target(new="ARBUZ")])

    assert rewritten[7]["symbolCode"] == "ARBUZ"
    assert rewritten[7]["confidence"] == LIBRARY_CONFIDENCE


def test_prediction_drift_and_unknown_cells_are_errors() -> None:
    with pytest.raises(ReferenceLibraryWriteError) as drift:
        rewrite_predictions(_predictions(), [_target(old="GWIAZDA")])
    with pytest.raises(ReferenceLibraryWriteError) as missing:
        rewrite_predictions(_predictions()[:10], [_target(index=12, old="WISNIA")])
    duplicated = _predictions() + [_predictions()[0]]
    with pytest.raises(ReferenceLibraryWriteError) as twice:
        rewrite_predictions(duplicated, [_target()])

    assert drift.value.code == "SYMBOL_REFERENCE_PREDICTION_DRIFT"
    assert missing.value.code == "SYMBOL_REFERENCE_PREDICTION_INVALID"
    assert twice.value.code == "SYMBOL_REFERENCE_PREDICTION_INVALID"


def test_prediction_digest_ignores_key_order_but_not_values() -> None:
    first = [{"a": 1, "b": 2}]
    reordered = [{"b": 2, "a": 1}]

    assert predictions_digest(first) == predictions_digest(reordered)
    assert predictions_digest(first) != predictions_digest([{"a": 1, "b": 3}])


def test_revert_checksum_is_distinct_and_valid() -> None:
    library = "b" * 64

    checksum = revert_checksum(library)

    assert checksum != library
    assert len(checksum) == 64
    assert checksum == revert_checksum(library)
    assert checksum != revert_checksum("c" * 64)


class _Cell(SimpleNamespace):
    pass


class _Session:
    def __init__(self, cells: list[_Cell], symbol_id: UUID) -> None:
        self.cells = cells
        self.symbol_id = symbol_id

    def add(self, revision: Any) -> None:
        revision.id = uuid4()

    def flush(self) -> None:
        return None

    def execute(self, _statement: object) -> list[tuple[UUID, str]]:
        return [(self.symbol_id, "POMARANCZ")]

    def scalars(self, _statement: object) -> list[_Cell]:
        return self.cells

    def refresh(self, _cell: object) -> None:
        return None


def _write(
    monkeypatch: pytest.MonkeyPatch, *, flag_target: bool, flag_other: bool, target_first: bool
) -> None:
    symbol_id = uuid4()

    def cell(index: int) -> _Cell:
        return _Cell(
            id=uuid4(),
            sequence_number=10,
            review_state="pending",
            assigned_symbol_id=symbol_id,
            assignment_source="model",
            quality_issue=None,
            prediction_revision_id=None,
            prediction_symbol_code="POMARANCZ",
            cell_index=index,
        )

    target, other = cell(4), cell(5)
    cells = [target, other] if target_first else [other, target]
    revision = SimpleNamespace(id=None)

    class Coordinator:
        def __init__(self, _session: object) -> None:
            return None

        def synchronize_after_prediction_refresh(self, **_kwargs: object) -> bool:
            for flagged, value in ((flag_target, target), (flag_other, other)):
                value.prediction_revision_id = revision.id
                if flagged:
                    value.quality_issue = "partial_visibility"
                    value.assignment_source = "geometry_partial"
                    value.assigned_symbol_id = None
            return True

    class Projection:
        def __init__(self, _session: object) -> None:
            return None

        def sync_review_item(self, _review_item_id: object) -> None:
            return None

    monkeypatch.setattr(writer, "SymbolCellReviewWriteThroughCoordinator", Coordinator)
    monkeypatch.setattr(writer, "SqlAlchemyBoardSearchProjectionRepository", Projection)
    session = _Session(cells, symbol_id)
    plan = writer.BoardPlan(uuid4(), uuid4(), uuid4(), "0" * 64, ())
    writer._write_revision(
        cast(Any, session),
        game_id=uuid4(),
        plan=plan,
        cells={value.id: cast(Any, value) for value in cells},
        revision=cast(Any, revision),
        expected_symbols={target.id: "POMARANCZ"},
    )


@pytest.mark.parametrize("target_first", [True, False])
def test_target_gaining_a_quality_issue_is_reported_before_side_effects(
    monkeypatch: pytest.MonkeyPatch, target_first: bool
) -> None:
    with pytest.raises(ReferenceLibraryWriteError) as error:
        _write(monkeypatch, flag_target=True, flag_other=True, target_first=target_first)

    assert error.value.code == TARGET_QUALITY_CHANGED


def test_non_target_gaining_a_quality_issue_is_a_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ReferenceLibraryWriteError) as error:
        _write(monkeypatch, flag_target=False, flag_other=True, target_first=True)

    assert error.value.code == "SYMBOL_REFERENCE_WRITE_SIDE_EFFECT"


def test_clean_refresh_passes_the_post_write_check(monkeypatch: pytest.MonkeyPatch) -> None:
    _write(monkeypatch, flag_target=False, flag_other=False, target_first=True)


def _rgb_target(
    status: str = "confirmed", *, old: str = "ARBUZ", new: str = "CYTRYNA"
) -> TargetCell:
    return TargetCell(
        uuid4(),
        7,
        "a" * 64,
        old,
        new,
        7,
        6,
        writer.RgbTarget(
            status=cast(Any, status),
            cnn_symbol=new,
            library_symbol=new if status == "confirmed" else None,
            old_confidence=0.5,
            old_source="reference_library",
            original_model_confidence=0.42,
        ),
    )


def test_rgb_v2_targets_record_their_own_provenance() -> None:
    from game_predictor_worker.symbols import rgb_v2

    predictions = _predictions()
    predictions[7]["referenceLibrary"] = {"version": MODEL_VERSION}
    policy = writer.rgb_v2_policy({"checkpointSha256": "c" * 64})

    confirmed = rewrite_predictions(predictions, [_rgb_target()], policy=policy)
    tentative = rewrite_predictions(predictions, [_rgb_target("tentative")], policy=policy)

    entry = confirmed[7]
    assert (entry["symbolCode"], entry["confidence"]) == ("CYTRYNA", rgb_v2.CONFIRMED_CONFIDENCE)
    assert entry["alternatives"] == [
        {"symbolCode": "CYTRYNA", "confidence": rgb_v2.CONFIRMED_CONFIDENCE}
    ]
    # One source per cell: the replaced library provenance leaves the entry.
    assert "referenceLibrary" not in entry
    assert entry["rgbV2"] == {
        "version": rgb_v2.MODEL_VERSION,
        "status": "confirmed",
        "cnnSymbolCode": "CYTRYNA",
        "librarySymbolCode": "CYTRYNA",
        "shapeVotes": 7,
        "combinedVotes": 6,
        "previousSymbolCode": "ARBUZ",
        "previousConfidence": 0.5,
        "previousSource": "reference_library",
        "originalModelConfidence": 0.42,
        "checkpointSha256": "c" * 64,
    }
    assert tentative[7]["confidence"] == rgb_v2.TENTATIVE_CONFIDENCE
    assert tentative[7]["rgbV2"]["status"] == "tentative"
    assert tentative[7]["rgbV2"]["librarySymbolCode"] is None
    assert [e for i, e in enumerate(confirmed) if i != 7] == [
        e for i, e in enumerate(predictions) if i != 7
    ]
    assert predictions[7]["referenceLibrary"] == {"version": MODEL_VERSION}


def test_rgb_v2_target_requires_the_rgb_policy() -> None:
    with pytest.raises(ReferenceLibraryWriteError) as error:
        rewrite_predictions(_predictions(), [_rgb_target()])

    assert error.value.code == "SYMBOL_REFERENCE_POLICY_MISMATCH"


def test_library_policy_is_the_default_and_unchanged() -> None:
    assert writer.LIBRARY_POLICY.model_version == MODEL_VERSION
    assert writer.LIBRARY_POLICY.actor == writer.ACTOR
    assert writer.rgb_v2_policy({}).model_version == "symbol-rgb-v2"
