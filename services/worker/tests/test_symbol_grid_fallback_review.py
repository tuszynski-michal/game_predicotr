from __future__ import annotations

import json
from pathlib import Path

from game_predictor_worker.images.symbol_grid_fallback_review import (
    REVIEW_VERSION,
    SELECTION_VERSION,
    SUGGESTION_VERSION,
    SymbolGridFallbackReview,
)


def test_real_strict_fallback_review_selects_only_six_failed_boards(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "fallback-review.json"
    review = SymbolGridFallbackReview(
        repository_root=root,
        manifest_path=root / "ai_docs/quality/m5-corpus-manifest.json",
        annotations_path=root / "ai_docs/quality/m5-golden-annotations.json",
        crop_report_path=root / "ai_docs/quality/m5-board-cell-crops-report.json",
        crop_root=root / "artifacts/m5-board-crops",
        refinement_report_path=(
            root / "ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json"
        ),
        output_path=output,
    )
    state = review.state(status="all", limit=100)
    samples = state["samples"]
    assert isinstance(samples, list)

    assert review.progress() == {"accepted": 0, "pending": 6, "total": 6}
    assert [sample["sequenceNumber"] for sample in samples] == [11, 33, 123, 172, 266, 337]
    assert all(sample["sourceQuad"] == sample["detectedSourceQuad"] for sample in samples)
    assert all(sample["suggestionVersion"] == SUGGESTION_VERSION for sample in samples)
    assert {sample["fallbackReason"] for sample in samples} == {
        "SYMBOL_GRID_INSUFFICIENT_INLIERS",
        "SYMBOL_GRID_REFINED_QUAD_IMPLAUSIBLE",
    }

    document = json.loads(output.read_bytes())
    assert document["goldenVersion"] == REVIEW_VERSION
    assert document["selection"]["selectionVersion"] == SELECTION_VERSION
    assert document["selection"]["fallbackCount"] == 6

    reloaded = SymbolGridFallbackReview(
        repository_root=root,
        manifest_path=root / "ai_docs/quality/m5-corpus-manifest.json",
        annotations_path=root / "ai_docs/quality/m5-golden-annotations.json",
        crop_report_path=root / "ai_docs/quality/m5-board-cell-crops-report.json",
        crop_root=root / "artifacts/m5-board-crops",
        refinement_report_path=(
            root / "ai_docs/quality/m5-full-symbol-grid-refinement-detector-report.json"
        ),
        output_path=output,
    )
    assert reloaded.progress() == review.progress()
