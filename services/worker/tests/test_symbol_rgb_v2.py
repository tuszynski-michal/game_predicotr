from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
from game_predictor_worker.symbols.rgb_v2 import (
    CONFIRMED_CONFIDENCE,
    TENTATIVE_CONFIDENCE,
    CurrentPrediction,
    band_of,
    current_status,
    decide_rgb,
    needs_write,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT))
_SPEC = importlib.util.spec_from_file_location(
    "symbol_rgb_v2_test_module", REPOSITORY_ROOT / "scripts" / "symbol_rgb_v2.py"
)
assert _SPEC is not None and _SPEC.loader is not None
runner: Any = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)

CODES = ("ARBUZ", "CYTRYNA", "GWIAZDA", "POMARANCZ", "SIEDEM", "SLIWKA", "WINOGRON", "WISNIA")


def _index(code: str) -> int:
    return CODES.index(code)


@pytest.mark.parametrize(
    ("confidence", "band"),
    [
        (0.0, "lt60"),
        (0.5999, "lt60"),
        (0.6, "60-80"),
        (0.8, "80-90"),
        (0.9, "90-99"),
        (0.98999999, "90-99"),
        (0.99, "99-100"),
        (1.0, "99-100"),
    ],
)
def test_bands_are_half_open_in_processing_order(confidence: float, band: str) -> None:
    assert band_of(confidence) == band


def test_confidence_outside_every_band_is_rejected() -> None:
    with pytest.raises(ValueError):
        band_of(1.5)


def test_library_consensus_on_the_cnn_class_confirms() -> None:
    confirmed = decide_rgb(CODES, _index("WINOGRON"), _index("WINOGRON"))
    disagreement = decide_rgb(CODES, _index("WINOGRON"), _index("SLIWKA"))
    no_consensus = decide_rgb(CODES, _index("WINOGRON"), None)

    assert (confirmed.symbol_code, confirmed.status) == ("WINOGRON", "confirmed")
    assert confirmed.confidence == CONFIRMED_CONFIDENCE
    # The CNN chooses; the library never replaces the symbol.
    assert (disagreement.symbol_code, disagreement.status) == ("WINOGRON", "tentative")
    assert disagreement.library_symbol_code == "SLIWKA"
    assert (no_consensus.status, no_consensus.confidence) == ("tentative", TENTATIVE_CONFIDENCE)


def test_candidate_outside_the_catalogue_is_rejected() -> None:
    with pytest.raises(ValueError):
        decide_rgb(CODES, 8, None)


def _current(symbol: str, confidence: float, source: str = "model") -> CurrentPrediction:
    return CurrentPrediction(symbol, confidence, source, confidence)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("current", "cnn", "library", "write"),
    [
        # Plan table "zapis tylko przy różnicy", row by row.
        (_current("WINOGRON", 0.55), "WINOGRON", "WINOGRON", True),
        (_current("WINOGRON", 0.995), "WINOGRON", "WINOGRON", False),
        (_current("SIEDEM", 0.99, "reference_library"), "SIEDEM", "SIEDEM", False),
        (_current("SIEDEM", 0.99, "reference_library"), "WINOGRON", "WINOGRON", True),
        (_current("SLIWKA", 0.999), "SLIWKA", None, True),
        (_current("ARBUZ", 0.70), "WISNIA", None, True),
        # A tentative cell that stays tentative on the same symbol is not rewritten.
        (_current("ARBUZ", 0.50, "rgb_v2"), "ARBUZ", None, False),
        # The unanimous library keeps the current symbol against a lone CNN dissent.
        (_current("ARBUZ", 0.99, "reference_library"), "POMARANCZ", "ARBUZ", False),
        (_current("GWIAZDA", 0.45), "CYTRYNA", "GWIAZDA", False),
        # Without that library support the CNN proposal is written for review.
        (_current("GWIAZDA", 0.45), "CYTRYNA", "SLIWKA", True),
    ],
)
def test_write_only_when_symbol_or_status_changes(
    current: CurrentPrediction, cnn: str, library: str | None, write: bool
) -> None:
    decision = decide_rgb(CODES, _index(cnn), None if library is None else _index(library))

    assert needs_write(current, decision) is write


def test_current_status_threshold() -> None:
    assert current_status(0.99) == "confirmed"
    assert current_status(0.9899) == "tentative"


def test_shard_twin_matches_the_sql_formula() -> None:
    # ('x' || left(md5(id), 7))::bit(28)::int: the first seven hex digits as an integer.
    cell_id = "576d3124-2079-439d-9d8c-1a4ee4f074e8"
    import hashlib

    expected = int(hashlib.md5(cell_id.encode()).hexdigest()[:7], 16) % 6
    assert runner.shard_of(cell_id, 6) == expected
    assert runner.shard_of(cell_id, 1) == 0


def test_scope_selects_one_band_and_shard_in_id_order() -> None:
    rows = [
        ["b", 0.99, "reference_library", 0.55],
        ["a", 0.40, "model", 0.40],
        ["c", 0.99, "model", 0.995],
        ["d", 0.99, "reference_library", None],
    ]

    selected = runner.select_scope(rows, "lt60", (0, 1))

    assert [row["id"] for row in selected] == ["a", "b"]
    assert selected[1]["source"] == "reference_library"
    assert selected[1]["originalConfidence"] == 0.55
    assert all(
        runner.shard_of(row["id"], 2) == 1 for row in runner.select_scope(rows, "lt60", (1, 2))
    )


def test_index_summary_counts_unknown_original_confidence() -> None:
    summary = runner.index_rows_to_summary(
        [["a", 0.4, "model", 0.4], ["b", 0.99, "reference_library", None]]
    )

    assert summary == {"lt60": {"model": 1}, "unknown": {"reference_library": 1}}


def _row(cell_id: str, **overrides: Any) -> dict[str, Any]:
    row = {
        "cellReviewId": cell_id,
        "renderedPixelChecksumSha256": "p" + cell_id,
        "currentSymbol": "WINOGRON",
        "currentConfidence": 0.99,
        "currentSource": "reference_library",
        "originalConfidence": 0.55,
        "symbol": "SIEDEM",
        "status": "confirmed",
        "cnnSymbol": "SIEDEM",
        "librarySymbol": "SIEDEM",
        "shapeVotes": 7,
        "combinedVotes": 7,
        "write": True,
    }
    row.update(overrides)
    return row


def _cell(cell_id: str, item: str, **overrides: Any) -> dict[str, Any]:
    cell = {
        "id": cell_id,
        "review_item_id": item,
        "recognized_board_id": "board-" + item,
        "prediction_revision_id": "rev-" + item,
        "cell_index": 3,
        "review_state": "pending",
        "assignment_source": "model",
        "quality_issue": None,
        "prediction_symbol_code": "WINOGRON",
        "prediction_confidence": 0.99,
        "rendered_pixel_checksum_sha256": "p" + cell_id,
    }
    cell.update(overrides)
    return cell


def test_boards_group_targets_and_exclude_cells_that_moved() -> None:
    targets = {key: _row(key) for key in ("a", "b", "c", "d", "e")}
    cells = {
        "a": _cell("a", "i1"),
        "b": _cell("b", "i1"),
        "c": _cell("c", "i2", review_state="approved"),
        "d": _cell("d", "i3", prediction_symbol_code="SIEDEM"),
        "e": _cell("e", "i4", prediction_revision_id="older"),
    }
    latest = {item: {"id": "rev-" + item, "predictions": []} for item in ("i1", "i2", "i3", "i4")}

    boards, excluded, moves = runner.build_boards(targets, cells, latest)

    assert [board["reviewItemId"] for board in boards] == ["i1"]
    assert [t["cellReviewId"] for t in boards[0]["targets"]] == ["a", "b"]
    assert boards[0]["targets"][0]["oldSource"] == "reference_library"
    assert boards[0]["targets"][0]["originalModelConfidence"] == 0.55
    assert excluded == {
        "not_pending": 1,
        "prediction_changed": 1,
        "revision_not_current": 1,
    }
    assert moves == {"WINOGRON->SIEDEM:confirmed": 2}


def _manifest_target(**overrides: Any) -> dict[str, Any]:
    target = {
        "cellReviewId": "00000000-0000-0000-0000-000000000001",
        "cellIndex": 4,
        "renderedPixelChecksumSha256": "p" * 64,
        "oldSymbol": "WINOGRON",
        "oldConfidence": 0.99,
        "oldSource": "reference_library",
        "originalModelConfidence": 0.55,
        "newSymbol": "SIEDEM",
        "status": "tentative",
        "cnnSymbol": "SIEDEM",
        "librarySymbol": None,
        "shapeVotes": 3,
        "combinedVotes": 4,
    }
    target.update(overrides)
    return target


def test_board_plan_carries_the_rgb_guard_and_provenance() -> None:
    board = {
        "reviewItemId": "00000000-0000-0000-0000-00000000000a",
        "recognizedBoardId": "00000000-0000-0000-0000-00000000000b",
        "predictionRevisionId": "00000000-0000-0000-0000-00000000000c",
        "predictionsSha256": "d" * 64,
        "targets": [_manifest_target()],
    }

    plan = runner.board_plan(board)

    target = plan.targets[0]
    assert (target.old_symbol, target.new_symbol) == ("WINOGRON", "SIEDEM")
    assert target.rgb.status == "tentative"
    assert target.rgb.old_confidence == 0.99
    assert target.rgb.library_symbol is None
    assert target.rgb.original_model_confidence == 0.55


def test_manifest_must_match_its_checksum_and_format(tmp_path: Path) -> None:
    import hashlib
    import json

    path = tmp_path / "apply-manifest.json"
    path.write_text(json.dumps({"format": "other"}), encoding="utf-8")
    checksum = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(runner.RgbError) as invalid:
        runner.read_manifest(path, checksum)
    with pytest.raises(runner.RgbError) as mismatch:
        runner.read_manifest(path, "0" * 64)

    assert invalid.value.code == "SYMBOL_RGB_MANIFEST_INVALID"
    assert mismatch.value.code == "SYMBOL_RGB_MANIFEST_MISMATCH"


@pytest.mark.parametrize(
    ("row", "state"),
    [
        ({"review_state": "approved"}, "decided_by_operator"),
        ({"model_checksum_sha256": "other"}, "other_rgb_run"),
        ({}, "rgb_prediction"),
        (
            {
                "model_version": "m",
                "model_checksum_sha256": "revert",
                "prediction_symbol_code": "X",
            },
            "reverted",
        ),
        (
            {
                "model_version": "m",
                "model_checksum_sha256": "x",
                "prediction_symbol_code": "WINOGRON",
                "prediction_confidence": 0.99,
            },
            "unchanged",
        ),
    ],
)
def test_read_back_states(row: dict[str, Any], state: str) -> None:
    base = {
        "review_state": "pending",
        "model_version": "symbol-rgb-v2",
        "model_checksum_sha256": "run",
        "prediction_symbol_code": "SIEDEM",
        "prediction_confidence": 0.5,
    }
    base.update(row)
    if base["model_checksum_sha256"] == "revert":
        base["model_checksum_sha256"] = runner.revert_checksum("run")

    assert runner.classify_target(base, _manifest_target(), "run") == state


def test_side_effect_and_quality_change_are_skippable() -> None:
    assert {
        "SYMBOL_REFERENCE_TARGET_QUALITY_CHANGED",
        "SYMBOL_REFERENCE_WRITE_SIDE_EFFECT",
    } == runner.SKIPPABLE


def test_writer_version_matches_the_admin_filter_constant() -> None:
    from game_predictor_api.domain.image_symbol_reviews import RGB_V2_PREDICTION_MODEL_VERSION
    from game_predictor_worker.symbols.rgb_v2 import MODEL_VERSION

    assert MODEL_VERSION == RGB_V2_PREDICTION_MODEL_VERSION
