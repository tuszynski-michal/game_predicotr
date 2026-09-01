from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from io import BytesIO
from uuid import UUID

import numpy as np
import pytest
from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer
from game_predictor_worker.semi_automatic_selection.contracts import (
    RangeEvidenceStatus,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionSource,
    SemiAutomaticSequenceBounds,
)
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
    BoundingBox,
    CanonicalSourceImage,
    ImageDimensions,
    LocalQualityScores,
    MiddleRowLabelCrop,
    MiddleRowLatticePrior,
    MiddleRowLocation,
    MiddleRowLocatorMode,
    MiddleRowLocatorResult,
)
from game_predictor_worker.semi_automatic_selection.middle_row_range import (
    ExpectedRangeTable,
    MiddleRowUnknownReason,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    DEFAULT_MIDDLE_ROW_RUNTIME_POLICY,
    MiddleRowBatchPolicy,
    MiddleRowBatchRuntime,
    MiddleRowLatticePriorTracker,
    MiddleRowOrientationCalibration,
    MiddleRowOrientationSource,
    MiddleRowPaddleRecognitionAdapter,
    MiddleRowPriorPolicy,
    MiddleRowRunOrientation,
    MiddleRowSourcePayload,
    calibrate_middle_row_orientation,
    deterministic_orientation_sample_indexes,
    middle_row_observation_key,
)
from numpy.typing import NDArray
from PIL import Image


@dataclass(frozen=True)
class _Recognition:
    raw_text: str
    confidence: float


class _RecognitionBackend:
    version = "fake-paddle-recognition-v1"
    model_name = "fake-digits"
    model_fingerprint = "a" * 64
    model_files: Mapping[str, str] = {"model.bin": "b" * 64}
    runtime_name = "fake-paddle-cpu"
    runtime_version = "1.0"

    def __init__(self, scripted: Sequence[_Recognition] | None = None) -> None:
        self.scripted = list(scripted or ())
        self.batch_sizes: list[int] = []

    def recognize_many(
        self,
        rgb_images: Sequence[NDArray[np.uint8]],
    ) -> tuple[_Recognition, ...]:
        self.batch_sizes.append(len(rgb_images))
        if self.scripted:
            values = tuple(self.scripted[: len(rgb_images)])
            del self.scripted[: len(rgb_images)]
            return values
        return tuple(_Recognition(str(int(image[0, 0, 0])), 0.96) for image in rgb_images)


class _Locator:
    fingerprint = "c" * 64

    def __init__(self, results: Sequence[MiddleRowLocatorResult]) -> None:
        self.results = list(results)
        self.priors: list[MiddleRowLatticePrior | None] = []

    def locate(
        self,
        _source: CanonicalSourceImage,
        *,
        prior: MiddleRowLatticePrior | None = None,
    ) -> MiddleRowLocatorResult:
        self.priors.append(prior)
        return self.results.pop(0)


class _CornerLocator:
    fingerprint = "d" * 64

    def __init__(self, target_corner: str | None) -> None:
        self.target_corner = target_corner

    def locate(
        self,
        source: CanonicalSourceImage,
        *,
        prior: MiddleRowLatticePrior | None = None,
    ) -> MiddleRowLocatorResult:
        del prior
        positions = {
            "top_left": source.rgb[0, 0, 0],
            "top_right": source.rgb[0, -1, 0],
            "bottom_left": source.rgb[-1, 0, 0],
            "bottom_right": source.rgb[-1, -1, 0],
        }
        if self.target_corner is not None and positions[self.target_corner] == 255:
            return _located((4, 5, 6))
        return _unknown_location(MiddleRowUnknownReason.UNKNOWN_LATTICE)


class _BatchInputHandle:
    def __init__(self) -> None:
        self.batch: NDArray[np.float32] | None = None

    def reshape(self, _shape: tuple[int, ...]) -> None:
        return None

    def copy_from_cpu(self, batch: NDArray[np.float32]) -> None:
        self.batch = batch.copy()


class _BatchOutputHandle:
    def __init__(self, output: NDArray[np.float32]) -> None:
        self.output = output

    def copy_to_cpu(self) -> NDArray[np.float32]:
        return self.output.copy()


class _BatchPredictor:
    def __init__(self, output: NDArray[np.float32]) -> None:
        self.input = _BatchInputHandle()
        self.output = _BatchOutputHandle(output)
        self.run_count = 0

    def get_input_handle(self, name: str) -> _BatchInputHandle:
        assert name == "input"
        return self.input

    def get_output_handle(self, name: str) -> _BatchOutputHandle:
        assert name == "output"
        return self.output

    def run(self) -> None:
        self.run_count += 1


def _source(index: int) -> SemiAutomaticSelectionSource:
    return SemiAutomaticSelectionSource(
        source_index=index,
        relative_path=f"photos/frame-{index:04d}.jpg",
        size_bytes=100 + index,
        checksum_sha256=f"{index + 1:064x}",
    )


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 18), (10, 20, 30)).save(output, format="JPEG")
    return output.getvalue()


def _payload(index: int) -> MiddleRowSourcePayload:
    return MiddleRowSourcePayload(source=_source(index), content=_jpeg())


def _canonical_with_top_left_marker() -> CanonicalSourceImage:
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[0, 0, 0] = 255
    dimensions = ImageDimensions(width=6, height=4)
    return CanonicalSourceImage(
        rgb=rgb,
        raw_dimensions=dimensions,
        oriented_dimensions=dimensions,
        exif_orientation=1,
    )


def _located(values: tuple[int, int, int]) -> MiddleRowLocatorResult:
    boxes = (
        BoundingBox(1, 6, 3, 8),
        BoundingBox(5, 6, 7, 8),
        BoundingBox(9, 6, 11, 8),
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
        MiddleRowLabelCrop(
            box=box,
            rgb=np.full((2, 2, 3), value, dtype=np.uint8),
            component_box=box,
            complete=True,
            quality=quality,
            readable=True,
        )
        for box, value in zip(boxes, values, strict=True)
    )
    return MiddleRowLocatorResult(
        location=MiddleRowLocation(
            locator_mode=MiddleRowLocatorMode.FULL_LATTICE,
            column_axes=(2, 6, 10),
            row_axes=(3, 7, 11),
            middle_row_centers=((2, 7), (6, 7), (10, 7)),
            candidate_boxes=boxes,
            crop_boxes=boxes,
            crops=crops,  # type: ignore[arg-type]
            best_score=0.95,
            second_best_score=0.2,
            ambiguity_margin=0.75,
            local_scale=2,
            local_slant=0,
        ),
        reason_code=None,
        diagnostics={"expandedRoi": False},
    )


def _unknown_location(reason: MiddleRowUnknownReason) -> MiddleRowLocatorResult:
    return MiddleRowLocatorResult(
        location=None,
        reason_code=reason,
        diagnostics={"reason": reason.value},
    )


def _expected_ranges() -> ExpectedRangeTable:
    return ExpectedRangeTable.from_bounds(
        SemiAutomaticSequenceBounds(
            first_sequence_number=1,
            last_sequence_number=18,
            direction=SemiAutomaticSelectionDirection.ASCENDING,
            full_range_size=9,
        )
    )


def test_real_paddle_recognition_method_executes_one_inference_for_nine_crops() -> None:
    output = np.zeros((9, 4, 11), dtype=np.float32)
    for batch_index in range(9):
        output[batch_index, 0, 2] = 0.96
        output[batch_index, 1, 2] = 0.96
        output[batch_index, 2, 0] = 0.96
        output[batch_index, 3, 3] = 0.96
    predictor = _BatchPredictor(output)
    backend = object.__new__(PaddleSequenceNumberRecognizer)
    backend.version = "sequence-number-ocr-v1"  # type: ignore[misc]
    backend.model_name = "fake-digits"
    backend.model_fingerprint = "a" * 64
    backend.model_files = {"model.bin": "b" * 64}
    backend.runtime_name = "paddlepaddle-cpu"  # type: ignore[misc]
    backend.runtime_version = "test"
    backend._characters = tuple("0123456789")
    backend._predictor = predictor
    backend._input_name = "input"
    backend._output_name = "output"
    adapter = MiddleRowPaddleRecognitionAdapter(backend)

    values = adapter.recognize_many(
        tuple(np.full((32, 80, 3), 127, dtype=np.uint8) for _ in range(9))
    )

    assert len(values) == 9
    assert predictor.run_count == 1
    assert adapter.metrics.internal_batches == 1
    assert adapter.metrics.batch_fill_ratio == 1
    assert not hasattr(backend, "text_detector")
    assert not hasattr(backend, "angle_classifier")


@pytest.mark.parametrize(
    ("source_count", "expected_batches"),
    ((1, [3]), (3, [9]), (6, [9, 9]), (12, [9, 9, 9, 9])),
)
def test_source_batch_contract_maps_to_bounded_recognition_batches(
    source_count: int,
    expected_batches: list[int],
) -> None:
    backend = _RecognitionBackend()
    adapter = MiddleRowPaddleRecognitionAdapter(backend)

    adapter.recognize_many(
        tuple(np.full((2, 2, 3), index, dtype=np.uint8) for index in range(source_count * 3))
    )

    assert backend.batch_sizes == expected_batches
    assert adapter.metrics.crops == source_count * 3


def test_last_partial_batch_is_supported_without_padding_or_reordering() -> None:
    backend = _RecognitionBackend()
    adapter = MiddleRowPaddleRecognitionAdapter(backend)

    values = adapter.recognize_many(
        tuple(np.full((2, 2, 3), index, dtype=np.uint8) for index in range(12))
    )

    assert backend.batch_sizes == [9, 3]
    assert [value.raw_text for value in values] == [str(index) for index in range(12)]


def test_batch_runtime_preserves_source_order_and_skips_ocr_without_lattice() -> None:
    backend = _RecognitionBackend()
    adapter = MiddleRowPaddleRecognitionAdapter(backend)
    locator = _Locator(
        (
            _located((4, 5, 6)),
            _unknown_location(MiddleRowUnknownReason.LOCAL_BLUR),
            _located((13, 14, 15)),
        )
    )
    runtime = MiddleRowBatchRuntime(
        run_id=UUID(int=1),
        expected_ranges=_expected_ranges(),
        rotation=MiddleRowRunOrientation.DEG_0,
        locator=locator,  # type: ignore[arg-type]
        recognizer=adapter,
    )

    results = runtime.process_batch(tuple(_payload(index) for index in range(3)))

    assert [value.source.source_index for value in results] == [0, 1, 2]
    assert [value.status for value in results] == [
        RangeEvidenceStatus.EXACT_RANGE,
        RangeEvidenceStatus.RANGE_UNREADABLE,
        RangeEvidenceStatus.EXACT_RANGE,
    ]
    assert [value.expected_index for value in results] == [0, None, 1]
    assert backend.batch_sizes == [6]
    assert runtime.counters.values["unknownLocalBlur"] == 1
    assert all(value.observation_key is not None for value in results)


def test_no_source_with_missing_lattice_or_blur_reaches_paddle() -> None:
    backend = _RecognitionBackend()
    runtime = MiddleRowBatchRuntime(
        run_id=UUID(int=1),
        expected_ranges=_expected_ranges(),
        rotation=MiddleRowRunOrientation.DEG_0,
        locator=_Locator(
            (
                _unknown_location(MiddleRowUnknownReason.UNKNOWN_LATTICE),
                _unknown_location(MiddleRowUnknownReason.LOCAL_BLUR),
            )
        ),  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(backend),
    )

    results = runtime.process_batch((_payload(0), _payload(1)))

    assert backend.batch_sizes == []
    assert [value.reason_codes for value in results] == [("UNKNOWN_LATTICE",), ("LOCAL_BLUR",)]


def test_runtime_fingerprint_pins_source_batch_and_orientation() -> None:
    adapter = MiddleRowPaddleRecognitionAdapter(_RecognitionBackend())
    common = {
        "run_id": UUID(int=1),
        "expected_ranges": _expected_ranges(),
        "locator": _Locator(()),
        "recognizer": adapter,
    }
    batch_one = MiddleRowBatchRuntime(
        **common,  # type: ignore[arg-type]
        rotation=MiddleRowRunOrientation.DEG_0,
        policy=replace(
            DEFAULT_MIDDLE_ROW_RUNTIME_POLICY,
            batch=MiddleRowBatchPolicy(source_batch_size=1),
        ),
    )
    batch_three = MiddleRowBatchRuntime(
        **common,  # type: ignore[arg-type]
        rotation=MiddleRowRunOrientation.DEG_0,
    )
    rotated = MiddleRowBatchRuntime(
        **common,  # type: ignore[arg-type]
        rotation=MiddleRowRunOrientation.DEG_180,
    )

    assert (
        len(
            {
                batch_one.runtime_fingerprint,
                batch_three.runtime_fingerprint,
                rotated.runtime_fingerprint,
            }
        )
        == 3
    )


def test_orientation_sampling_is_deterministic_and_bounded() -> None:
    assert deterministic_orientation_sample_indexes(1) == (0,)
    assert deterministic_orientation_sample_indexes(19) == (0, 3, 5, 8, 10, 13, 15, 18)
    assert deterministic_orientation_sample_indexes(100, sample_count=4) == (0, 33, 66, 99)


@pytest.mark.parametrize(
    ("target_corner", "expected"),
    (
        ("top_left", MiddleRowRunOrientation.DEG_0),
        ("bottom_right", MiddleRowRunOrientation.DEG_180),
        ("top_right", MiddleRowRunOrientation.DEG_90),
    ),
)
def test_auto_orientation_calibrates_zero_half_and_bounded_quarter_turns(
    monkeypatch: pytest.MonkeyPatch,
    target_corner: str,
    expected: MiddleRowRunOrientation,
) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.middle_row_runtime.canonicalize_source_image",
        lambda _content: _canonical_with_top_left_marker(),
    )
    calibration = calibrate_middle_row_orientation(
        payloads=(_payload(0), _payload(1)),
        expected_ranges=_expected_ranges(),
        locator=_CornerLocator(target_corner),  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(_RecognitionBackend()),
    )

    assert calibration.orientation is expected
    assert calibration.orientation_source is MiddleRowOrientationSource.AUTOMATIC
    assert calibration.unresolved is False
    if expected is MiddleRowRunOrientation.DEG_90:
        assert set(calibration.proof_counts) == {"0", "180", "90", "270"}
    else:
        assert set(calibration.proof_counts) == {"0", "180"}


def test_manual_orientation_override_wins_without_decoding_or_ocr() -> None:
    backend = _RecognitionBackend()
    calibration = calibrate_middle_row_orientation(
        payloads=(),
        expected_ranges=_expected_ranges(),
        locator=_Locator(()),  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(backend),
        override=MiddleRowRunOrientation.DEG_270,
    )

    assert calibration.orientation is MiddleRowRunOrientation.DEG_270
    assert calibration.orientation_source is MiddleRowOrientationSource.MANUAL_OVERRIDE
    assert calibration.sample_indexes == ()
    assert backend.batch_sizes == []


def test_unresolved_orientation_and_checkpoint_round_trip_are_stable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "game_predictor_worker.semi_automatic_selection.middle_row_runtime.canonicalize_source_image",
        lambda _content: _canonical_with_top_left_marker(),
    )
    calibration = calibrate_middle_row_orientation(
        payloads=(_payload(0), _payload(1)),
        expected_ranges=_expected_ranges(),
        locator=_CornerLocator(None),  # type: ignore[arg-type]
        recognizer=MiddleRowPaddleRecognitionAdapter(_RecognitionBackend()),
    )

    assert calibration.orientation is None
    assert calibration.unresolved is True
    assert MiddleRowOrientationCalibration.from_dict(calibration.as_dict()) == calibration


def test_lattice_prior_is_bounded_periodically_verified_and_reset_after_drift() -> None:
    policy = MiddleRowPriorPolicy(history_size=2, reset_after_failures=3, full_search_interval=10)
    tracker = MiddleRowLatticePriorTracker(policy)
    location = _located((4, 5, 6)).location
    assert location is not None
    dimensions = ImageDimensions(width=24, height=18)
    tracker.record_success(location, dimensions)

    assert tracker.prior_for(1) is not None
    assert tracker.prior_for(10) is None
    restored = MiddleRowLatticePriorTracker(policy, checkpoint=tracker.checkpoint())
    assert restored.current == tracker.current
    restored.record_failure()
    restored.record_failure()
    assert restored.current is not None
    restored.record_failure()
    assert restored.current is None


def test_observation_key_is_idempotent_and_bound_to_run_source_and_runtime() -> None:
    source = _source(0)
    first = middle_row_observation_key(
        run_id=UUID(int=1), source=source, runtime_fingerprint="a" * 64
    )

    assert first == middle_row_observation_key(
        run_id=UUID(int=1), source=source, runtime_fingerprint="a" * 64
    )
    assert first != middle_row_observation_key(
        run_id=UUID(int=2), source=source, runtime_fingerprint="a" * 64
    )
    assert first != middle_row_observation_key(
        run_id=UUID(int=1), source=source, runtime_fingerprint="b" * 64
    )
