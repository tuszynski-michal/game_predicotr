from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from PIL import Image

_ROOT = Path(__file__).parent / "fixtures" / "range_ocr_real_v6"
_MANIFEST = _ROOT / "manifest.json"


def _manifest() -> Mapping[str, object]:
    value = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_real_range_ocr_corpus_is_checksum_bound_and_filename_neutral() -> None:
    manifest = _manifest()
    assert manifest["contract"] == "range-ocr-real-regression-corpus-v1"
    cases = manifest["cases"]
    assert isinstance(cases, list)
    assert len(cases) == 4

    names: list[str] = []
    for raw in cases:
        assert isinstance(raw, dict)
        relative_path = raw["relativePath"]
        assert isinstance(relative_path, str)
        names.append(relative_path)
        assert "seq_" not in relative_path.casefold()
        assert not any(token in relative_path for token in ("28", "36", "55", "63", "64", "72"))
        path = _ROOT / relative_path
        assert path.is_file()
        assert _sha256(path) == raw["sha256"]
        assert path.stat().st_size == raw["sizeBytes"]

    assert names == ["screen-a.jpg", "screen-b.jpg", "screen-c.jpg", "transition-d.jpg"]


def test_real_range_ocr_corpus_labels_include_three_exact_cases_and_transition() -> None:
    cases = _manifest()["cases"]
    assert isinstance(cases, list)
    labels = [case["humanLabel"] for case in cases if isinstance(case, dict)]
    assert labels == [
        {"kind": "readable_exact", "expectedRange": [64, 72]},
        {"kind": "readable_exact", "expectedRange": [55, 63]},
        {"kind": "readable_exact", "expectedRange": [28, 36]},
        {
            "kind": "transition",
            "visibleRanges": [[124130, 124138], [124139, 124147]],
        },
    ]


def test_redacted_regions_hide_external_ui_but_preserve_source_canvas() -> None:
    cases = _manifest()["cases"]
    assert isinstance(cases, list)
    for raw in cases:
        assert isinstance(raw, dict)
        image = np.asarray(Image.open(_ROOT / str(raw["relativePath"])).convert("RGB"))
        assert image.shape == (1280, 720, 3)
        regions = raw["redactedRegions"]
        assert isinstance(regions, list)
        for region in regions:
            assert isinstance(region, list)
            left, top, right, bottom = region
            pixels = image[int(top) : int(bottom), int(left) : int(right)]
            # JPEG re-encoding leaks a few boundary pixels into a black mask;
            # no readable UI may remain inside its interior.
            assert pixels.size > 0
            assert float(pixels.mean()) <= 0.1
            assert float(np.percentile(pixels, 99)) <= 1.0
