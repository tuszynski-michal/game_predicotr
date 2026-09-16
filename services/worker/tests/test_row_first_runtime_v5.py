from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import BytesIO
from uuid import UUID

import numpy as np
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceStatus,
    SemiAutomaticSelectionDirection,
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
from game_predictor_worker.semi_automatic_selection.range_proof_v5 import (
    RangeRowOffset,
    RowExpectedRangeTable,
)
from game_predictor_worker.semi_automatic_selection.row_first_locator_v5 import (
    RowFirstLabelCrop,
    RowFirstLocation,
    RowFirstLocatorResult,
    RowFirstRowHypothesis,
)
from game_predictor_worker.semi_automatic_selection.row_first_runtime_v5 import (
    RowFirstBatchRuntime,
    RowFirstSourcePayload,
)
from PIL import Image


@dataclass(frozen=True)
class _Recognition:
    raw_text: str
    confidence: float


class _RecognitionBackend:
    version = "fake-row-first-paddle-v1"
    model_name = "fake-digits"
    model_fingerprint = "a" * 64
    model_files: Mapping[str, str] = {"model.bin": "b" * 64}
    runtime_name = "fake-paddle-cpu"
    runtime_version = "1.0"

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def recognize_many(self, images: Sequence[np.ndarray]) -> tuple[_Recognition, ...]:
        self.batch_sizes.append(len(images))
        return tuple(_Recognition(str(int(image[0, 0, 0])), 0.96) for image in images)


class _Locator:
    fingerprint = "c" * 64

    def __init__(self, locations: Sequence[RowFirstLocation]) -> None:
        self.locations = list(locations)

    def locate(self, _source: CanonicalSourceImage) -> RowFirstLocatorResult:
        return RowFirstLocatorResult(
            location=self.locations.pop(0),
            reason_code=None,
            diagnostics={"fixture": True},
        )


def _source(index: int) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=f"frames/frame-{index:04d}.jpg",
        size_bytes=100 + index,
        checksum_sha256=f"{index + 1:064x}",
    )


def _payload(index: int) -> RowFirstSourcePayload:
    image = BytesIO()
    Image.new("RGB", (24, 18), (10, 20, 30)).save(image, format="JPEG")
    return RowFirstSourcePayload(source=_source(index), content=image.getvalue())


def _expected_ranges() -> RowExpectedRangeTable:
    return RowExpectedRangeTable.from_bounds(
        SemiAutomaticSequenceBounds(
            first_sequence_number=1,
            last_sequence_number=18,
            direction=SemiAutomaticSelectionDirection.ASCENDING,
            full_range_size=9,
        )
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


def _location(*rows: RowFirstRowHypothesis) -> RowFirstLocation:
    return RowFirstLocation(rows=rows, candidate_boxes=(), locator_fingerprint="c" * 64)


def _runtime(
    locations: Sequence[RowFirstLocation],
) -> tuple[RowFirstBatchRuntime, _RecognitionBackend]:
    backend = _RecognitionBackend()
    runtime = RowFirstBatchRuntime(
        run_id=UUID(int=1),
        expected_ranges=_expected_ranges(),
        locator=_Locator(locations),  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(backend),
    )
    return runtime, backend


def test_two_matching_rows_produce_exact_and_crop_batches_remain_bounded() -> None:
    location = _location(
        _row(RangeRowOffset.TOP, (1, 2, 3)),
        _row(RangeRowOffset.MIDDLE, (4, 5, 6)),
    )
    runtime, backend = _runtime((location, location, location))

    results = runtime.process_batch((_payload(0), _payload(1), _payload(2)))

    assert [value.status for value in results] == [RangeEvidenceStatus.EXACT_RANGE] * 3
    assert [value.observed_range.as_dict() for value in results if value.observed_range] == [
        {"start": 1, "end": 9},
        {"start": 1, "end": 9},
        {"start": 1, "end": 9},
    ]
    assert backend.batch_sizes == [9, 9]
    assert runtime.counters.values["ocrCrops"] == 18
    assert all(value.observation_key is not None for value in results)


def test_single_row_remains_unknown_without_fabricating_a_range() -> None:
    runtime, backend = _runtime((_location(_row(RangeRowOffset.MIDDLE, (4, 5, 6))),))

    result = runtime.process_batch((_payload(0),))[0]

    assert result.status is RangeEvidenceStatus.RANGE_UNREADABLE
    assert result.observed_range is None
    assert result.reason_codes == ("FINAL_PROOF_INSUFFICIENT",)
    assert backend.batch_sizes == [3]


def test_conflicting_complete_rows_are_ambiguous_not_exact() -> None:
    runtime, _backend = _runtime(
        (
            _location(
                _row(RangeRowOffset.TOP, (1, 2, 3)),
                _row(RangeRowOffset.MIDDLE, (13, 14, 15)),
            ),
        )
    )

    result = runtime.process_batch((_payload(0),))[0]

    assert result.status is RangeEvidenceStatus.RANGE_AMBIGUOUS
    assert result.observed_range is None
    assert result.reason_codes == ("CONFLICTING_VISIBLE_ROWS",)


def test_observation_key_is_bound_to_runtime_and_source() -> None:
    location = _location(
        _row(RangeRowOffset.TOP, (1, 2, 3)),
        _row(RangeRowOffset.MIDDLE, (4, 5, 6)),
    )
    first, _backend = _runtime((location,))
    second, _backend = _runtime((location,))

    first_result = first.process_batch((_payload(0),))[0]
    second_result = second.process_batch((_payload(1),))[0]

    assert first_result.observation_key != second_result.observation_key
