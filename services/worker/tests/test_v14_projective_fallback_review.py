from __future__ import annotations

import json
from pathlib import Path

from game_predictor_worker.images.v14_projective_fallback_review import (
    REVIEW_VERSION,
    SELECTION_VERSION,
    SUGGESTION_VERSION,
    V14ProjectiveFallbackReview,
)


def test_real_v14_fallback_review_selects_only_fourteen_failed_boards(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "v14-fallback-review.json"
    review = V14ProjectiveFallbackReview(
        repository_root=root,
        manifest_path=root / "ai_docs/quality/m5-corpus-manifest.json",
        annotations_path=root / "ai_docs/quality/m5-golden-annotations.json",
        crop_report_path=root / "ai_docs/quality/m5-board-cell-crops-report.json",
        crop_root=root / "artifacts/m5-board-crops",
        preflight_report_path=(
            root / "ai_docs/quality/m5-global-bbox-fallback-v14-full-preflight-report.json"
        ),
        output_path=output,
    )
    state = review.state(status="all", limit=100)
    samples = state["samples"]
    assert isinstance(samples, list)

    assert review.progress() == {"accepted": 0, "pending": 14, "total": 14}
    assert [sample["sequenceNumber"] for sample in samples] == [
        33,
        38,
        123,
        163,
        203,
        237,
        254,
        255,
        325,
        333,
        334,
        335,
        346,
        379,
    ]
    assert all(sample["sourceQuad"] == sample["detectedSourceQuad"] for sample in samples)
    assert all(sample["suggestionVersion"] == SUGGESTION_VERSION for sample in samples)

    document = json.loads(output.read_bytes())
    assert document["goldenVersion"] == REVIEW_VERSION
    assert document["selection"]["selectionVersion"] == SELECTION_VERSION
    assert document["selection"]["fallbackCount"] == 14

    reloaded = V14ProjectiveFallbackReview(
        repository_root=root,
        manifest_path=root / "ai_docs/quality/m5-corpus-manifest.json",
        annotations_path=root / "ai_docs/quality/m5-golden-annotations.json",
        crop_report_path=root / "ai_docs/quality/m5-board-cell-crops-report.json",
        crop_root=root / "artifacts/m5-board-crops",
        preflight_report_path=(
            root / "ai_docs/quality/m5-global-bbox-fallback-v14-full-preflight-report.json"
        ),
        output_path=output,
    )
    assert reloaded.progress() == review.progress()
