from __future__ import annotations

import ast
from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceStatus,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_label_locator import (
    FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE,
    FiveAnchorBoundingBox,
    FiveAnchorLabelCrop,
    FiveAnchorLocation,
    FiveAnchorLocatorMode,
    FiveAnchorLocatorResult,
    FiveAnchorPosition,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_proof import (
    FiveAnchorExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_runtime import (
    DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY,
    FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
    FiveAnchorBatchRuntime,
    FiveAnchorSourcePayload,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    MiddleRowPaddleRecognitionAdapter,
)
from PIL import Image


class _Backend:
    version = "fake-paddle-v1"
    model_name = "fake"
    model_fingerprint = "a" * 64
    model_files = {"recognition": "b" * 64}
    runtime_name = "fake-runtime"
    runtime_version = "1"

    def __init__(self, values: list[tuple[str, float]]) -> None:
        self.values = values
        self.offset = 0
        self.calls = 0
        self.preprocessing_seconds = 0.0
        self.inference_seconds = 0.0

    def recognize_many(self, rgb_images: Sequence[object]) -> list[object]:
        self.calls += 1
        values = self.values[self.offset : self.offset + len(rgb_images)]
        self.offset += len(rgb_images)
        if len(values) != len(rgb_images):
            raise AssertionError("Test backend received more OCR crops than configured.")
        return [
            SimpleNamespace(raw_text=text, confidence=confidence)
            for _image, (text, confidence) in zip(rgb_images, values, strict=True)
        ]


class _Locator:
    fingerprint = "c" * 64

    def __init__(self, result: FiveAnchorLocatorResult) -> None:
        self.result = result
        self.seen_shapes: list[tuple[int, int, int]] = []

    def locate(self, rgb: np.ndarray) -> FiveAnchorLocatorResult:
        self.seen_shapes.append(tuple(rgb.shape))
        return self.result


def _source(index: int = 0) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=f"source-{index}.jpg",
        size_bytes=100,
        checksum_sha256=f"{index + 1:064x}",
    )


def _bounds() -> SemiAutomaticSequenceBounds:
    return SemiAutomaticSequenceBounds(
        first_sequence_number=1,
        last_sequence_number=18,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
    )


def _jpeg(*, orientation: int | None = None) -> bytes:
    image = Image.fromarray(np.full((200, 100, 3), 160, dtype=np.uint8), mode="RGB")
    output = BytesIO()
    kwargs: dict[str, object] = {}
    if orientation is not None:
        exif = Image.Exif()
        exif[274] = orientation
        kwargs["exif"] = exif
    image.save(output, format="JPEG", **kwargs)
    return output.getvalue()


def _pattern() -> np.ndarray:
    cells = (np.indices((6, 12)).sum(axis=0) % 2).astype(np.uint8)
    gray = np.kron(cells, np.ones((4, 4), dtype=np.uint8)) * 228 + 16
    return np.stack((gray, gray, gray), axis=2)


def _location(*, rgb: np.ndarray | None = None) -> FiveAnchorLocatorResult:
    pixels = _pattern() if rgb is None else rgb
    crops = []
    for position in FiveAnchorPosition:
        crops.append(
            FiveAnchorLabelCrop(
                position=position,
                box=FiveAnchorBoundingBox(
                    left=0, top=0, right=pixels.shape[1], bottom=pixels.shape[0]
                ),
                rgb=pixels.copy(),
                complete=True,
                mode=FiveAnchorLocatorMode.VIEWPORT_FALLBACK,
            )
        )
    return FiveAnchorLocatorResult(
        location=FiveAnchorLocation(
            crops=(crops[0], crops[1], crops[2], crops[3], crops[4]),
            fingerprint="d" * 64,
        ),
        reason_code=None,
        diagnostics={"coordinateSpace": FIVE_ANCHOR_RANGE_LABEL_COORDINATE_SPACE},
    )


def _runtime(
    values: list[tuple[str, float]],
    *,
    location: FiveAnchorLocatorResult | None = None,
) -> tuple[FiveAnchorBatchRuntime, _Backend, _Locator]:
    backend = _Backend(values)
    locator = _Locator(location or _location())
    runtime = FiveAnchorBatchRuntime(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        expected_ranges=FiveAnchorExpectedRangeTable.from_bounds(_bounds()),
        locator=locator,  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(backend),
    )
    return runtime, backend, locator


def test_runtime_maps_five_visible_values_to_exact_range_and_source_order() -> None:
    runtime, backend, _locator = _runtime([(str(value), 0.99) for value in (1, 3, 5, 7, 9)])

    result = runtime.process_batch((FiveAnchorSourcePayload(source=_source(), content=_jpeg()),))

    assert result[0].status is RangeEvidenceStatus.EXACT_RANGE
    assert result[0].observed_range is not None
    assert result[0].observed_range.as_dict() == {"end": 9, "start": 1}
    assert result[0].reason_codes == ("FIVE_ANCHOR_SPANNED_EXACT",)
    assert result[0].runtime_diagnostics is not None
    assert result[0].runtime_diagnostics["confirmingAnchors"] == [
        "top_left",
        "top_right",
        "center",
        "bottom_left",
        "bottom_right",
    ]
    assert backend.calls == 1
    assert runtime.counters.values["ocrCrops"] == 5


def test_runtime_skips_paddle_for_local_blur_and_returns_manual_unknown() -> None:
    runtime, backend, _locator = _runtime(
        [],
        location=_location(rgb=np.zeros((24, 48, 3), dtype=np.uint8)),
    )

    result = runtime.process_batch((FiveAnchorSourcePayload(source=_source(), content=_jpeg()),))

    assert result[0].status is RangeEvidenceStatus.RANGE_UNREADABLE
    assert result[0].reason_codes == ("LOCAL_BLUR",)
    assert backend.calls == 0
    assert runtime.counters.values["unknownLocalBlur"] == 1


def test_runtime_returns_conflict_without_repairing_ocr_text() -> None:
    runtime, _backend, _locator = _runtime([(str(value), 0.99) for value in (1, 3, 5, 999, 9)])

    result = runtime.process_batch((FiveAnchorSourcePayload(source=_source(), content=_jpeg()),))

    assert result[0].status is RangeEvidenceStatus.RANGE_AMBIGUOUS
    assert result[0].reason_codes == ("CONFLICTING_ANCHOR_VALUES",)
    assert result[0].observed_range is None


def test_runtime_batches_six_sources_and_preserves_order() -> None:
    values = [(str(value), 0.99) for _source in range(6) for value in (1, 3, 5, 7, 9)]
    runtime, backend, _locator = _runtime(values)
    payloads = tuple(
        FiveAnchorSourcePayload(source=_source(index), content=_jpeg()) for index in range(6)
    )

    results = runtime.process_batch(payloads)

    assert [item.source.source_index for item in results] == list(range(6))
    assert all(item.status is RangeEvidenceStatus.EXACT_RANGE for item in results)
    assert backend.calls == 4  # 30 cropów, maksymalnie dziewięć na wywołanie Paddle.
    assert runtime.counters.values["ocrInternalBatches"] == 4
    with pytest.raises(ValueError, match="exceeds"):
        runtime.process_batch(
            payloads + (FiveAnchorSourcePayload(source=_source(6), content=_jpeg()),)
        )


def test_runtime_applies_exif_once_before_it_calls_locator() -> None:
    runtime, _backend, locator = _runtime([(str(value), 0.99) for value in (1, 3, 5, 7, 9)])

    runtime.process_batch(
        (FiveAnchorSourcePayload(source=_source(), content=_jpeg(orientation=6)),)
    )

    assert locator.seen_shapes == [(100, 200, 3)]


def test_runtime_fingerprint_and_observation_key_are_stable_and_bound_to_source() -> None:
    first, _backend, _locator = _runtime([(str(value), 0.99) for value in (1, 3, 5, 7, 9)])
    second, _backend_two, _locator_two = _runtime([(str(value), 0.99) for value in (1, 3, 5, 7, 9)])

    first_result = first.process_batch(
        (FiveAnchorSourcePayload(source=_source(), content=_jpeg()),)
    )[0]
    second_result = second.process_batch(
        (FiveAnchorSourcePayload(source=_source(), content=_jpeg()),)
    )[0]

    assert first.runtime_fingerprint == second.runtime_fingerprint
    assert first_result.observation_key == second_result.observation_key
    assert len(FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6) == 64
    assert DEFAULT_FIVE_ANCHOR_RUNTIME_POLICY.batch.source_batch_size == 6


def test_runtime_module_has_no_direct_job_geometry_or_symbol_pipeline_imports() -> None:
    module_path = (
        "services/worker/src/game_predictor_worker/semi_automatic_selection/"
        "five_anchor_range_runtime.py"
    )
    tree = ast.parse(Path(module_path).read_text(encoding="utf-8"))
    imports = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ] + [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]

    forbidden = (".job", ".engine", "board", "geometry", "symbol", "storage")
    assert not any(any(token in item.lower() for token in forbidden) for item in imports)
