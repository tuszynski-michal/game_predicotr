from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

import cv2
import numpy as np
import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7_CALIBRATION_POSITION_CONFIDENCE,
    V7_DYNAMIC_GEOMETRY_FAMILY_ID,
    V7_STANDARD_GEOMETRY_FAMILY_ID,
    V7GeometryCalibration,
    V7GeometryProfile,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
    V7DynamicGridLabelLocatorConfig,
    V7GridLabelLocatorConfig,
)
from game_predictor_worker.semi_automatic_selection.v7_occurrences import (
    V7OccurrenceObservation,
    V7OccurrenceTracker,
)
from game_predictor_worker.semi_automatic_selection.v7_profile_bound_observer import (
    V7ProfileBoundObserverFactory,
    v7_profile_bound_localizer_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import V7RangeProofKind
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7PinnedSource
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7SourceObservationRequest,
    V7WorkerConfiguration,
    V7WorkerRuntimeError,
)
from PIL import Image


@dataclass(frozen=True)
class _Recognition:
    raw_text: str
    confidence: float


class _ScriptedRecognizer:
    def __init__(self, responses: list[tuple[_Recognition, ...]]) -> None:
        self._responses = responses
        self.crop_counts: list[int] = []

    def recognize_many(self, crops: list[np.ndarray]) -> tuple[_Recognition, ...]:
        self.crop_counts.append(len(crops))
        return self._responses.pop(0)


def _profile(*, dynamic: bool = False) -> V7GeometryProfile:
    calibration = V7GeometryCalibration(
        manifest_fingerprint="a" * 64,
        input_fingerprint="b" * 64,
        geometry_family_id=(
            V7_DYNAMIC_GEOMETRY_FAMILY_ID if dynamic else V7_STANDARD_GEOMETRY_FAMILY_ID
        ),
        locator_config=(
            V7DynamicGridLabelLocatorConfig(position_confidence=V7_CALIBRATION_POSITION_CONFIDENCE)
            if dynamic
            else V7GridLabelLocatorConfig(position_confidence=V7_CALIBRATION_POSITION_CONFIDENCE)
        ),
        source_count_by_position=(5,) * 9,
        capture_group_count_by_position=(2,) * 9,
        p95_center_residual_by_position=(0.01,) * 9,
        p95_center_residual=0.01,
        maximum_p95_center_residual=0.04,
        minimum_sources_per_position=5,
        minimum_capture_groups_per_position=2,
    )
    return V7GeometryProfile("c" * 64, calibration, revision=0)


def _configuration(profile: V7GeometryProfile) -> V7WorkerConfiguration:
    return V7WorkerConfiguration(
        first_sequence_number=1,
        last_sequence_number=9,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
        border_style=V7BorderStyle.TOP_AND_SIDES,
        calibration_fingerprint=profile.profile_fingerprint,
        localizer_fingerprint=v7_profile_bound_localizer_fingerprint(profile),
    )


def _source(index: int, content: bytes) -> V7PinnedSource:
    return V7PinnedSource.from_source(
        SemiAutomaticSelectionSource(
            source_index=index,
            relative_path=f"{index}.jpg",
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
        )
    )


def _jpeg_bytes(*, reversed_gradient: bool = False) -> bytes:
    gradient = np.linspace(0, 255, 140, dtype=np.uint8)
    if reversed_gradient:
        gradient = gradient[::-1]
    rgb = np.repeat(gradient[None, :, None], 100, axis=0)
    rgb = np.repeat(rgb, 3, axis=2)
    stream = BytesIO()
    Image.fromarray(rgb, "RGB").save(stream, format="JPEG", quality=95)
    return stream.getvalue()


def _reencode_jpeg(content: bytes, *, quality: int) -> bytes:
    with Image.open(BytesIO(content)) as image:
        stream = BytesIO()
        image.convert("RGB").save(stream, format="JPEG", quality=quality)
    return stream.getvalue()


def _textured_jpeg_bytes() -> bytes:
    random = np.random.default_rng(0)
    rgb = random.integers(0, 256, size=(100, 140, 3), dtype=np.uint8)
    stream = BytesIO()
    Image.fromarray(rgb, "RGB").save(stream, format="JPEG", quality=95)
    return stream.getvalue()


def _dynamic_grid_jpeg_bytes() -> bytes:
    rgb = np.full((360, 560, 3), 18, dtype=np.uint8)
    destination = np.asarray([[110, 104], [432, 86], [461, 272], [86, 294]], dtype=np.float32)
    transform = cv2.getPerspectiveTransform(
        np.asarray([[0, 0], [2, 0], [2, 2], [0, 2]], dtype=np.float32), destination
    )
    points = cv2.perspectiveTransform(
        np.asarray([[(column, row) for row in range(3) for column in range(3)]], dtype=np.float32),
        transform,
    )[0]
    for position, (x, y) in enumerate(points):
        cv2.putText(
            rgb,
            f"{position + 101:06d}",
            (round(x - 42), round(y + 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.52,
            (248, 248, 248),
            2,
            cv2.LINE_AA,
        )
    stream = BytesIO()
    Image.fromarray(rgb, "RGB").save(stream, format="JPEG", quality=95)
    return stream.getvalue()


def _values(labels: dict[int, int]) -> tuple[_Recognition, ...]:
    return tuple(
        _Recognition(raw_text=str(labels.get(index, "")), confidence=0.99) for index in range(9)
    )


def _request(source: V7PinnedSource, content: bytes) -> V7SourceObservationRequest:
    return V7SourceObservationRequest(source=source, source_content=content)


def _assert_reencoded_source_is_dependent(first_content: bytes) -> None:
    profile = _profile()
    second_content = _reencode_jpeg(first_content, quality=30)
    first_source = _source(0, first_content)
    second_source = _source(1, second_content)
    observer = V7ProfileBoundObserverFactory(
        profile,
        lambda: _ScriptedRecognizer([_values({0: 1, 4: 5, 8: 9}), _values({1: 2, 3: 4, 7: 8})]),
    ).create(_configuration(profile), object())

    first = observer.observe(_request(first_source, first_content))
    second = observer.observe(_request(second_source, second_content))
    assert first.weak_evidence is not None
    assert second.weak_evidence is not None
    assert first.weak_evidence.visual_signature == second.weak_evidence.visual_signature

    tracker = V7OccurrenceTracker((SemiAutomaticSelectionRange(1, 9),))
    tracker.consume(
        V7OccurrenceObservation(0, first_source.source_id, first.proof, first.weak_evidence)
    )
    restored = V7OccurrenceTracker(
        (SemiAutomaticSelectionRange(1, 9),),
        checkpoint=tracker.checkpoint(),
    )
    restored.consume(
        V7OccurrenceObservation(1, second_source.source_id, second.proof, second.weak_evidence)
    )
    assert restored.finish() == ()


def test_passed_profile_yields_a_strong_source_local_five_label_proof() -> None:
    profile = _profile()
    recognizer = _ScriptedRecognizer([_values({0: 1, 1: 2, 3: 4, 5: 6, 8: 9})])
    observer = V7ProfileBoundObserverFactory(profile, lambda: recognizer).create(
        _configuration(profile), object()
    )
    content = _jpeg_bytes()
    source = _source(0, content)

    result = observer.observe(_request(source, content))

    assert result.proof.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert result.proof.sequence_range == SemiAutomaticSelectionRange(1, 9)
    assert result.proof.supporting_source_ids == (source.source_id,)
    assert recognizer.crop_counts == [9]
    assert result.quality is not None
    assert len(result.quality.boards) == 9
    assert all(board.visibility.value == "unknown" for board in result.quality.boards)


def test_dynamic_profile_uses_only_its_source_local_lattice_for_a_proof() -> None:
    profile = _profile(dynamic=True)
    recognizer = _ScriptedRecognizer([_values({0: 1, 1: 2, 3: 4, 5: 6, 8: 9})])
    observer = V7ProfileBoundObserverFactory(profile, lambda: recognizer).create(
        _configuration(profile), object()
    )
    content = _dynamic_grid_jpeg_bytes()

    result = observer.observe(_request(_source(0, content), content))

    assert result.proof.kind is V7RangeProofKind.STRONG_FIVE_LABEL
    assert recognizer.crop_counts == [9]


def test_profile_binding_fails_before_the_recognizer_or_source_is_opened() -> None:
    profile = _profile()
    called = False

    def recognizer_factory() -> _ScriptedRecognizer:
        nonlocal called
        called = True
        return _ScriptedRecognizer([])

    configuration = _configuration(profile)
    mismatched = V7WorkerConfiguration(
        first_sequence_number=configuration.first_sequence_number,
        last_sequence_number=configuration.last_sequence_number,
        direction=configuration.direction,
        border_style=configuration.border_style,
        calibration_fingerprint="d" * 64,
        localizer_fingerprint=configuration.localizer_fingerprint,
    )

    with pytest.raises(V7WorkerRuntimeError) as error:
        V7ProfileBoundObserverFactory(profile, recognizer_factory).create(mismatched, object())

    assert error.value.code == "V7_CALIBRATION_FINGERPRINT_MISMATCH"
    assert called is False


def test_three_labels_are_source_local_evidence_and_three_plus_two_is_not() -> None:
    profile = _profile()
    first_content = _jpeg_bytes()
    second_content = _jpeg_bytes(reversed_gradient=True)
    first_source = _source(0, first_content)
    second_source = _source(1, second_content)
    first_recognizer = _ScriptedRecognizer([_values({0: 1, 4: 5, 8: 9})])
    observer = V7ProfileBoundObserverFactory(profile, lambda: first_recognizer).create(
        _configuration(profile), object()
    )

    initial = observer.observe(_request(first_source, first_content))

    assert initial.proof.kind is V7RangeProofKind.NONE
    assert initial.weak_evidence is not None
    assert initial.weak_evidence.source_id == first_source.source_id

    three_plus_two = V7ProfileBoundObserverFactory(
        profile,
        lambda: _ScriptedRecognizer([_values({0: 1, 4: 5, 8: 9}), _values({1: 2, 3: 4})]),
    ).create(_configuration(profile), object())
    first_result = three_plus_two.observe(_request(first_source, first_content))
    second_result = three_plus_two.observe(_request(second_source, second_content))
    assert first_result.proof.kind is V7RangeProofKind.NONE
    assert first_result.weak_evidence is not None
    assert second_result.proof.kind is V7RangeProofKind.NONE
    assert second_result.weak_evidence is None


def test_a_credible_sixth_conflict_cannot_yield_weak_evidence() -> None:
    profile = _profile()
    content = _jpeg_bytes()
    first_source = _source(0, content)
    conflict = V7ProfileBoundObserverFactory(
        profile,
        lambda: _ScriptedRecognizer([_values({0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 99})]),
    ).create(_configuration(profile), object())
    conflict_result = conflict.observe(_request(first_source, content))
    assert conflict_result.proof.kind is V7RangeProofKind.NONE
    assert conflict_result.proof.reason_codes == ("CONFLICTING_RELIABLE_LABEL",)
    assert conflict_result.weak_evidence is None


def test_four_labels_cannot_enter_the_exact_three_plus_three_path() -> None:
    profile = _profile()
    content = _jpeg_bytes()
    first_source = _source(0, content)
    second_source = _source(1, content)
    observer = V7ProfileBoundObserverFactory(
        profile,
        lambda: _ScriptedRecognizer(
            [
                _values({0: 1, 1: 2, 4: 5, 8: 9}),
                _values({0: 1, 1: 2, 3: 4, 7: 8}),
            ]
        ),
    ).create(_configuration(profile), object())

    first = observer.observe(_request(first_source, content))
    second = observer.observe(_request(second_source, content))

    assert first.proof.kind is V7RangeProofKind.NONE
    assert second.proof.kind is V7RangeProofKind.NONE
    assert first.weak_evidence is None
    assert second.weak_evidence is None


def test_reencoded_source_stays_visually_dependent_after_tracker_restart() -> None:
    _assert_reencoded_source_is_dependent(_jpeg_bytes())


def test_textured_reencoded_source_stays_visually_dependent_after_tracker_restart() -> None:
    _assert_reencoded_source_is_dependent(_textured_jpeg_bytes())


def test_corrupt_source_is_a_single_source_decode_error() -> None:
    profile = _profile()
    recognizer = _ScriptedRecognizer([])
    observer = V7ProfileBoundObserverFactory(profile, lambda: recognizer).create(
        _configuration(profile), object()
    )
    content = b"not-a-jpeg"

    result = observer.observe(_request(_source(0, content), content))

    assert result.source_error_code == "SOURCE_DECODE_ERROR"
    assert result.proof.kind is V7RangeProofKind.NONE
    assert recognizer.crop_counts == []
