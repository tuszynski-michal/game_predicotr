from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceResult,
    RangeEvidenceStatus,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
    BoundingBox,
    CanonicalSourceImage,
    LocalQualityScores,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    MiddleRowPaddleRecognitionAdapter,
)
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import RangeRowOffset
from game_predictor_worker.semi_automatic_selection.row_first_locator_v5 import (
    RowFirstLabelCrop,
    RowFirstLocation,
    RowFirstLocatorResult,
    RowFirstRowHypothesis,
)
from game_predictor_worker.semi_automatic_selection.row_first_runtime_v5 import (
    ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
)
from PIL import Image

_SCRIPT = Path(__file__).parents[3] / "scripts" / "run_row_first_range_ocr_v5_acceptance.py"
_SPEC = importlib.util.spec_from_file_location("row_first_v5_acceptance", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


@dataclass(frozen=True)
class _Recognition:
    raw_text: str
    confidence: float


class _RecognitionBackend:
    version = "fake-row-first-acceptance-paddle-v1"
    model_name = "fake-digits"
    model_fingerprint = "a" * 64
    model_files: Mapping[str, str] = {"model.bin": "b" * 64}
    runtime_name = "fake-paddle-cpu"
    runtime_version = "1.0"

    def recognize_many(self, images: Sequence[np.ndarray]) -> tuple[_Recognition, ...]:
        return tuple(_Recognition(str(int(image[0, 0, 0])), 0.96) for image in images)


class _Locator:
    fingerprint = "c" * 64

    def __init__(self, locations: Sequence[RowFirstLocation]) -> None:
        self._locations = list(locations)

    def locate(self, _source: CanonicalSourceImage) -> RowFirstLocatorResult:
        return RowFirstLocatorResult(
            location=self._locations.pop(0),
            reason_code=None,
            diagnostics={"fixture": True},
        )


def _row(offset: RangeRowOffset, values: tuple[int, int, int]) -> RowFirstRowHypothesis:
    boxes = (
        BoundingBox(1, 5, 3, 7),
        BoundingBox(5, 5, 7, 7),
        BoundingBox(9, 5, 11, 7),
    )
    quality = LocalQualityScores(
        tenengrad=50,
        contrast=20,
        edge_density=0.2,
        dark_ratio=0.2,
        bright_ratio=0.2,
        directional_blur_ratio=1,
    )
    crops = tuple(
        RowFirstLabelCrop(
            box=box,
            component_box=box,
            rgb=np.full((2, 2, 3), value, dtype=np.uint8),
            complete=True,
            quality=quality,
            readable=True,
        )
        for box, value in zip(boxes, values, strict=True)
    )
    return RowFirstRowHypothesis(
        row=offset,
        centers=((2, 6), (6, 6), (10, 6)),
        component_boxes=boxes,
        crops=crops,  # type: ignore[arg-type]
        baseline_slope=0,
        score=0.95,
        source_roi_level=0,
    )


def _location() -> RowFirstLocation:
    return RowFirstLocation(
        rows=(
            _row(RangeRowOffset.TOP, (1, 2, 3)),
            _row(RangeRowOffset.MIDDLE, (4, 5, 6)),
        ),
        candidate_boxes=(),
        locator_fingerprint="c" * 64,
    )


def _jpeg(path: Path, value: int) -> str:
    stream = BytesIO()
    Image.new("RGB", (24, 18), (value, 20, 30)).save(stream, format="JPEG")
    path.write_bytes(stream.getvalue())
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case(index: int, path: Path, checksum: str) -> object:
    return _MODULE.AcceptanceCase(
        sample_index=index,
        source_index=index,
        relative_path=path.name,
        checksum_sha256=checksum,
        size_bytes=path.stat().st_size,
        human_label=_MODULE.HumanLabel(
            "human_readable_exact",
            SemiAutomaticSelectionRange(1, 9),
        ),
    )


def test_v5_acceptance_harness_uses_only_v5_runtime_and_own_proof(tmp_path: Path) -> None:
    source_root = tmp_path / "raw"
    source_root.mkdir()
    first = source_root / "camera-a.jpg"
    second = source_root / "camera-b.jpg"
    cases = (_case(0, first, _jpeg(first, 10)), _case(1, second, _jpeg(second, 20)))
    model_root = tmp_path / "model"
    model_root.mkdir()
    backend = _RecognitionBackend()

    report = _MODULE.run_acceptance(
        source_root=source_root,
        cases=cases,
        bounds=SemiAutomaticSequenceBounds(1, 9),
        model_root=model_root,
        warmup_count=0,
        selected_reviews={},
        recognizer_factory=lambda _path: MiddleRowPaddleRecognitionAdapter(backend),
        locator_factory=lambda: _Locator((_location(), _location())),  # type: ignore[arg-type]
    )

    assert report["contract"] == "row-first-range-ocr-v5-acceptance-v1"
    assert (
        report["recognizer"]["contractFingerprint"] == ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5
    )
    assert report["quality"]["falseExactCount"] == 0
    assert report["diagnostics"]["exactSources"] == 2
    assert report["grouping"]["selected"][0]["selectionMethod"] == (
        "row-first-evidence-span-midpoint-v1"
    )


def test_v5_harness_manifest_remains_checksum_bound(tmp_path: Path) -> None:
    source_root = tmp_path / "raw"
    source_root.mkdir()
    source = source_root / "camera.jpg"
    checksum = _jpeg(source, 10)
    manifest = tmp_path / "golden.json"
    manifest.write_text(
        json.dumps(
            {
                "contract": "middle-row-range-ocr-v4-corpus-v1",
                "cases": [
                    {
                        "relativePath": source.name,
                        "sha256": checksum,
                        "humanLabel": {
                            "kind": "human_readable_exact",
                            "expectedRange": [1, 9],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    _MODULE._load_manifest(
        manifest,
        source_root=source_root,
        inventory=(source,),
    )
    source.write_bytes(source.read_bytes() + b"changed")

    with pytest.raises(ValueError, match="checksum differs"):
        _MODULE._load_manifest(
            manifest,
            source_root=source_root,
            inventory=(source,),
        )


def test_exact_on_unreadable_label_is_a_false_exact() -> None:
    source = SemiAutomaticSelectionSource(
        source_index=0,
        relative_path="camera.jpg",
        size_bytes=10,
        checksum_sha256="1" * 64,
    )
    case = _MODULE.AcceptanceCase(
        sample_index=0,
        source_index=0,
        relative_path=source.relative_path,
        checksum_sha256=source.checksum_sha256,
        size_bytes=source.size_bytes,
        human_label=_MODULE.HumanLabel("unreadable", None),
    )
    evidence = RangeEvidenceResult(
        source=source,
        status=RangeEvidenceStatus.EXACT_RANGE,
        observed_range=SemiAutomaticSelectionRange(1, 9),
        expected_index=0,
        confidence=0.99,
        reason_codes=("ROW_FIRST_TWO_ROW_EXACT",),
    )

    metrics = _MODULE._quality_metrics(((case, evidence),))

    assert metrics["falseExactCount"] == 1
    assert metrics["unreadableUnknownRate"] == 0.0


def test_selected_review_metrics_require_every_selected_range() -> None:
    selected = (
        {"relativePath": "a.jpg", "rangeStart": 1, "rangeEnd": 9},
        {"relativePath": "b.jpg", "rangeStart": 10, "rangeEnd": 18},
    )
    review = _MODULE.SelectedReview(
        relative_path="a.jpg",
        expected_range=SemiAutomaticSelectionRange(1, 9),
        correct_range=True,
        own_exact_proof_visible=True,
        near_evidence_midpoint=True,
    )

    metrics = _MODULE._selected_metrics(selected, {"a.jpg": review})

    assert metrics["allSelectedReviewed"] is False
    assert metrics["selectedRangePrecision"] is None
