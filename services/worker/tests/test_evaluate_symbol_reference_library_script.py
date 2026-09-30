from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from game_predictor_worker.images.normalization import rgb_pixel_checksum_sha256
from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_symbol_reference_library_test_module",
    REPOSITORY_ROOT / "scripts" / "evaluate_symbol_reference_library.py",
)
assert _SPEC is not None and _SPEC.loader is not None
runner: Any = importlib.util.module_from_spec(_SPEC)
# Dataclasses resolve their module through sys.modules while the script executes.
sys.modules[_SPEC.name] = runner
_SPEC.loader.exec_module(runner)

QUAD = ((10.0, 10.0), (60.0, 10.0), (60.0, 60.0), (10.0, 60.0))


def _source(root: Path) -> tuple[str, str]:
    """Write one managed JPEG and return its checksum and the exact crop checksum."""

    rng = np.random.default_rng(7)
    pixels = rng.integers(0, 255, (80, 80, 3), dtype=np.uint8)
    staging = root / "staging.jpg"
    Image.fromarray(pixels).save(staging, format="JPEG", quality=95)
    checksum = hashlib.sha256(staging.read_bytes()).hexdigest()
    managed = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    managed.parent.mkdir(parents=True)
    staging.replace(managed)
    with Image.open(managed) as image:
        decoded = np.asarray(image.convert("RGB"), dtype=np.uint8)
    crop = source_direct_warp_rgb(decoded, source_quad=QUAD, output_width=64, output_height=64)
    return checksum, rgb_pixel_checksum_sha256(crop)


def _cell(identifier: str, source: str, pixels: str) -> Any:
    return runner.Cell(
        id=identifier,
        import_job_id="import",
        sequence_number=1,
        cell_index=0,
        prediction_symbol_code="ARBUZ",
        prediction_confidence=0.7,
        rendered_pixel_checksum_sha256=pixels,
        source_checksum_sha256=source,
        padded_quad=QUAD,
        source_quad=QUAD,
        label="ARBUZ",
    )


def test_pixel_checksum_mismatch_is_excluded_and_counted(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    good = _cell("good", source, pixels)
    drifted = _cell("drifted", source, "0" * 64)

    cache, remaining = runner._render(
        [good, drifted],
        artifact_root=tmp_path,
        cache_path=tmp_path / "cache.npz",
        deadline=time.monotonic() + 60,
    )
    usable, excluded = runner._usable([good, drifted], cache)

    assert remaining == 0
    assert [cell.id for cell in usable] == ["good"]
    assert excluded == {"IMAGE_VIRTUAL_CELL_PIXEL_CHECKSUM_MISMATCH": 1}
    assert rgb_pixel_checksum_sha256(cache[runner._cache_key(good)]["crop"]) == pixels


def test_cache_resumes_without_rendering_again(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    cell = _cell("good", source, pixels)
    cache_path = tmp_path / "cache.npz"

    runner._render(
        [cell], artifact_root=tmp_path, cache_path=cache_path, deadline=time.monotonic() + 60
    )
    # A past deadline would stop any new rendering; the cached crop must still be returned.
    cache, remaining = runner._render(
        [cell], artifact_root=tmp_path, cache_path=cache_path, deadline=0.0
    )

    assert remaining == 0
    assert cache[runner._cache_key(cell)]["status"] == "ok"


def test_expired_budget_reports_remaining_crops(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)

    _cache, remaining = runner._render(
        [_cell("first", source, pixels), _cell("second", source, pixels)],
        artifact_root=tmp_path,
        cache_path=tmp_path / "cache.npz",
        deadline=0.0,
    )

    assert remaining == 2


def test_missing_original_is_an_error_and_is_not_cached(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.npz"

    with pytest.raises(runner.EvaluationError) as error:
        runner._render(
            [_cell("missing", "a" * 64, "0" * 64)],
            artifact_root=tmp_path,
            cache_path=cache_path,
            deadline=time.monotonic() + 60,
        )

    assert error.value.code == "SYMBOL_REFERENCE_SOURCE_UNAVAILABLE"
    assert not cache_path.exists()


def test_incomplete_render_spec_is_a_contract_error() -> None:
    row = {
        "id": "cell",
        "import_job_id": "import",
        "sequence_number": 1,
        "cell_index": 0,
        "prediction_symbol_code": "ARBUZ",
        "prediction_confidence": 0.7,
        "rendered_pixel_checksum_sha256": "0" * 64,
        "label": None,
        "render_spec": {"configuration": {"outputWidth": 64, "outputHeight": 64}},
    }

    with pytest.raises(runner.EvaluationError) as error:
        runner._cell(row)

    assert error.value.code == "SYMBOL_REFERENCE_RENDER_SPEC_INVALID"


def test_evaluation_excludes_the_cells_own_import() -> None:
    labels = np.array([0] * 7 + [1] * 7, dtype=np.int64)
    imports = np.array(["a"] * 7 + ["b"] * 7)
    descriptors = np.array([[1.0, 0.0]] * 7 + [[0.0, 1.0]] * 7, dtype=np.float32)

    proposals = runner._proposals(
        descriptors,
        descriptors,
        descriptors,
        descriptors,
        labels,
        class_count=2,
        exclusions=[imports == value for value in imports],
    )

    # With its own import removed, each cell only sees the other symbol's cells.
    assert [proposal.class_index for proposal in proposals] == [1] * 7 + [0] * 7


def _frozen(proposals: list[tuple[str, str, str]]) -> dict[str, Any]:
    return {
        "format": runner.BLIND_FORMAT,
        "game": {"id": "game"},
        "cells": [
            {"cellReviewId": identifier, "activeModelSymbol": model, "proposal": proposal}
            for identifier, model, proposal in proposals
        ],
    }


def _ratings(values: dict[str, str], frozen_sha: str = "f" * 64) -> dict[str, Any]:
    return {"format": runner.RATINGS_FORMAT, "frozenSha256": frozen_sha, "ratings": values}


def test_compare_rejects_ratings_for_another_freeze() -> None:
    frozen = _frozen([("a", "ARBUZ", "ARBUZ")])

    with pytest.raises(runner.EvaluationError) as error:
        runner._compare_ratings(frozen, "f" * 64, _ratings({"a": "ARBUZ"}, "e" * 64))

    assert error.value.code == "SYMBOL_REFERENCE_RATINGS_MISMATCH"


def test_compare_rejects_unknown_cells_and_values() -> None:
    frozen = _frozen([("a", "ARBUZ", "ARBUZ")])

    with pytest.raises(runner.EvaluationError):
        runner._compare_ratings(frozen, "f" * 64, _ratings({"b": "ARBUZ"}))
    with pytest.raises(runner.EvaluationError):
        runner._compare_ratings(frozen, "f" * 64, _ratings({"a": "BANAN"}))


def test_non_symbol_ratings_are_reported_but_not_counted_as_errors() -> None:
    frozen = _frozen([("a", "ARBUZ", "WISNIA"), ("b", "ARBUZ", "ARBUZ")])

    report = runner._compare_ratings(frozen, "f" * 64, _ratings({"a": "ZASLONIETY", "b": "ARBUZ"}))

    assert report["confidentProposals"] == 1
    assert report["confidentAccuracy"] == 1.0
    assert report["confidentProposalsOnNonSymbolRatings"] == {"ZASLONIETY": 1}


def test_gate_requires_complete_ratings_and_per_symbol_accuracy() -> None:
    cells = [(f"a{i}", "CYTRYNA", "ARBUZ") for i in range(10)]
    cells += [(f"w{i}", "WISNIA", "WISNIA") for i in range(10)]
    cells.append(("review", "ARBUZ", runner.REVIEW))
    frozen = _frozen(cells)
    ratings = {identifier: proposal for identifier, _model, proposal in cells[:-1]}

    incomplete = runner._compare_ratings(frozen, "f" * 64, _ratings(ratings))
    ratings["review"] = "ARBUZ"
    passed = runner._compare_ratings(frozen, "f" * 64, _ratings(ratings))
    ratings["a0"] = "CYTRYNA"
    failed = runner._compare_ratings(frozen, "f" * 64, _ratings(ratings))

    assert incomplete["gate"]["passed"] is False
    assert passed["gate"]["passed"] is True
    assert passed["activeModelAccuracy"] == round(11 / 21, 6)
    # 9/10 for ARBUZ is below the per-symbol threshold although 19/20 overall is 95%.
    assert failed["gate"]["passed"] is False
    assert failed["confidentErrors"] == [
        {"cellReviewId": "a0", "operator": "CYTRYNA", "proposal": "ARBUZ"}
    ]


def test_symbols_below_minimum_support_are_unconfirmed() -> None:
    frozen = _frozen([("a", "ARBUZ", "ARBUZ")])

    report = runner._compare_ratings(frozen, "f" * 64, _ratings({"a": "ARBUZ"}))

    assert report["unconfirmedSymbols"] == ["ARBUZ"]
    assert report["gate"]["passed"] is True


def test_blind_page_contains_pixels_and_ids_only(tmp_path: Path) -> None:
    crop = np.zeros((64, 64, 3), dtype=np.uint8)
    item = {
        "id": "cell-1",
        "crop": runner._crop_uri(crop, 192),
        "context": runner._context_uri(
            np.zeros((224, 224, 3), dtype=np.uint8), np.zeros((4, 2), dtype=np.float32)
        ),
    }

    page = runner._blind_html([item], [("ARBUZ", "Arbuz")], "a" * 64)

    assert "cell-1" in page and "a" * 64 in page
    for leaked in ("proposal", "activeModel", "Confidence", runner.REVIEW):
        assert leaked not in page
    assert "__PAYLOAD__" not in page


def test_previously_shown_cells_are_read_from_both_formats(tmp_path: Path) -> None:
    proposals = tmp_path / "proposals.json"
    proposals.write_text('[{"cellReviewId": "a"}]', encoding="utf-8")
    chat = tmp_path / "chat.json"
    chat.write_text('[{"id": "b"}]', encoding="utf-8")
    broken = tmp_path / "broken.json"
    broken.write_text('[{"other": 1}]', encoding="utf-8")

    assert runner._excluded_ids([proposals, chat]) == {"a", "b"}
    with pytest.raises(runner.EvaluationError):
        runner._excluded_ids([broken])


def test_band_labels_follow_numeric_order_and_reject_outside_values() -> None:
    assert runner._band(0.05, [0.1, 0.6], 0.0, 0.8) == "0–10%"
    assert runner._band(0.6, [0.1, 0.6], 0.0, 0.8) == "60–80%"
    assert [runner._band_label(a, b) for a, b in runner._band_bounds([0.6, 0.1], 0.0, 0.8)] == [
        "0–10%",
        "10–60%",
        "60–80%",
    ]
    with pytest.raises(runner.EvaluationError):
        runner._band(0.8, [0.6], 0.0, 0.8)


def test_display_confidence_never_rounds_up_to_the_band_edge() -> None:
    assert runner._display_confidence(0.79996) == "0.79"
    assert runner._display_confidence(0.6) == "0.60"


def test_preview_groups_are_deterministic_and_capped() -> None:
    rows = [
        {"cellReviewId": f"cell-{i}", "band": "60–80%", "proposal": "ARBUZ" if i % 3 else "WISNIA"}
        for i in range(30)
    ]

    first = runner._preview_groups(rows, 5)
    second = runner._preview_groups(list(reversed(rows)), 5)

    assert first == second
    assert sorted(first) == [("60–80%", "ARBUZ"), ("60–80%", "WISNIA")]
    assert all(len(members) == 5 for members in first.values())


def test_crop_only_cache_round_trips(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    cell = _cell("good", source, pixels)
    cache_path = tmp_path / "crops.npz"

    runner._render(
        [cell],
        artifact_root=tmp_path,
        cache_path=cache_path,
        deadline=time.monotonic() + 60,
        context_size=0,
    )
    reloaded = runner._load_cache(cache_path)[runner._cache_key(cell)]

    assert reloaded["status"] == "ok"
    assert reloaded["context"].shape == (0, 0, 3)
    assert rgb_pixel_checksum_sha256(reloaded["crop"]) == pixels


def test_frozen_crops_must_match_their_checksum(tmp_path: Path) -> None:
    source, pixels = _source(tmp_path)
    cell = _cell("good", source, pixels)
    cache, _ = runner._render(
        [cell],
        artifact_root=tmp_path,
        cache_path=tmp_path / "cache.npz",
        deadline=time.monotonic() + 60,
    )
    row = {"cellReviewId": "good", "renderedPixelChecksumSha256": pixels}

    assert len(runner._cached_crops(cache, [row])) == 1
    with pytest.raises(runner.EvaluationError) as error:
        runner._cached_crops(cache, [{**row, "renderedPixelChecksumSha256": "0" * 64}])

    assert error.value.code == "SYMBOL_REFERENCE_FROZEN_PIXELS_MISSING"


def test_cached_preview_rows_require_the_same_key(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_bytes(runner._json_bytes({"key": "a", "rows": [{"cellReviewId": "x"}]}))

    assert runner._cached_preview_rows(path, "a") == [{"cellReviewId": "x"}]
    assert runner._cached_preview_rows(path, "b") is None
    assert runner._cached_preview_rows(tmp_path / "missing.json", "a") is None


def test_partial_rows_resume_and_only_complete_rows_are_final(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    runner._write_rows_cache(path, "a", [{"cellReviewId": "x"}], complete=False)

    assert runner._cached_preview_rows(path, "a") is None
    assert runner._partial_preview_rows(path, "a") == [{"cellReviewId": "x"}]
    assert runner._partial_preview_rows(path, "b") == []

    runner._write_rows_cache(path, "a", [{"cellReviewId": "x"}], complete=True)

    assert runner._cached_preview_rows(path, "a") == [{"cellReviewId": "x"}]
    assert runner._partial_preview_rows(path, "a") == []


def test_damaged_preview_rows_cache_is_ignored(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_text('{"key": "a", "rows": [', encoding="utf-8")

    assert runner._cached_preview_rows(path, "a") is None


def test_review_hint_accuracy_counts_only_review_cells_with_a_symbol() -> None:
    from game_predictor_worker.symbols.reference_library import Proposal, Vote

    def review(weights: tuple[float, ...]) -> Proposal:
        vote = Vote(0, 7, 4, 0.9, class_weights=weights)
        return Proposal(None, "not_unanimous", vote, vote)

    sure = Proposal(0, "unanimous", Vote(0, 7, 7, 0.9), Vote(0, 7, 7, 0.9))
    rows = [
        {"cellReviewId": "a", "activeModelSymbol": "ARBUZ"},
        {"cellReviewId": "b", "activeModelSymbol": "ARBUZ"},
        {"cellReviewId": "c", "activeModelSymbol": "ARBUZ"},
        {"cellReviewId": "d", "activeModelSymbol": "ARBUZ"},
    ]
    report = runner._review_hint_accuracy(
        rows,
        [review((3.0, 2.0)), review((1.0, 2.0)), sure, review((1.0, 0.0))],
        ["ARBUZ", "WISNIA"],
        {"a": "WISNIA", "b": "WISNIA", "c": "ARBUZ", "d": "ZASLONIETY"},
    )

    assert report == {
        "cells": 2,
        "fused1": 1,
        "fused1OrModel": 1,
        "fused2": 2,
        "model": 0,
        # Both shape votes name ARBUZ, the operator saw WISNIA.
        "shape": 0,
    }
    assert runner._review_hint_accuracy([], [], ["ARBUZ"], {}) == {
        "cells": 0,
        "fused1": 0,
        "fused1OrModel": 0,
        "fused2": 0,
        "model": 0,
        "shape": 0,
    }


def test_failed_receipts_are_retried_and_final_ones_are_skipped() -> None:
    receipts = {"a": "applied", "b": "failed:DeadlockDetected", "c": "stale:cell_changed"}

    assert runner._done(receipts) == {"a", "c"}


def test_prediction_entry_is_found_by_cell_position() -> None:
    predictions = [{"rowIndex": 1, "columnIndex": 2, "symbolCode": "ARBUZ"}]

    assert runner._entry_for_cell(predictions, 7)["symbolCode"] == "ARBUZ"
    assert runner._entry_for_cell(predictions, 8) == {}


def test_manifest_without_a_run_checksum_is_rejected(tmp_path: Path) -> None:
    manifest = tmp_path / "apply-manifest.json"
    manifest.write_text(json.dumps({"format": runner.APPLY_MANIFEST_FORMAT}), encoding="utf-8")
    checksum = hashlib.sha256(manifest.read_bytes()).hexdigest()

    with pytest.raises(runner.EvaluationError) as error:
        runner._read_manifest(manifest, checksum)
    with pytest.raises(runner.EvaluationError) as mismatch:
        runner._read_manifest(manifest, "0" * 64)

    assert error.value.code == "SYMBOL_REFERENCE_APPLY_MANIFEST_INVALID"
    assert mismatch.value.code == "SYMBOL_REFERENCE_APPLY_MANIFEST_MISMATCH"
