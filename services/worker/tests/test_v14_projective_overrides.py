from __future__ import annotations

import json
from pathlib import Path

import cv2
from game_predictor_worker.images.source_projective_lattice_crops import (
    build_reviewed_source_quad_crops,
)
from game_predictor_worker.images.v14_projective_overrides import (
    OVERRIDE_SET_VERSION,
    ReviewedV14ProjectiveOverrides,
)


def test_real_reviewed_v14_overrides_cover_and_crop_all_fourteen_fallbacks() -> None:
    root = Path(__file__).resolve().parents[3]
    report_path = root / "ai_docs/quality/m5-global-bbox-fallback-v14-full-preflight-report.json"
    overrides = ReviewedV14ProjectiveOverrides.from_files(
        root / "artifacts/m5-v14-projective-fallback-review/reviewed-geometry.json",
        report_path,
    )
    detection = json.loads(
        (root / "ai_docs/quality/m5-page-board-detection-report.json").read_bytes()
    )
    normalized_by_source = {
        entry["sourceChecksumSha256"]: entry["normalizedRelativePath"]
        for entry in detection["detections"]
    }

    assert overrides.version == OVERRIDE_SET_VERSION
    assert overrides.override_count == 14
    assert [item.sequence_number for item in overrides.overrides] == [
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

    for override in overrides.overrides:
        normalized_path = (
            root
            / "artifacts/m5-normalization"
            / normalized_by_source[override.source_checksum_sha256]
        )
        source_bgr = cv2.imread(str(normalized_path), cv2.IMREAD_COLOR)
        assert source_bgr is not None
        result = build_reviewed_source_quad_crops(
            cv2.cvtColor(source_bgr, cv2.COLOR_BGR2RGB),
            override.source_quad,
            primary_fallback_reason=override.fallback_reason,
        )

        assert result.status == "cropped", override.sequence_number
        assert result.minimum_support_fraction == 1.0
        assert len(result.cells) == 15
