from __future__ import annotations

from collections.abc import Sequence
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7RangeProofKind,
    V7RangeProofResult,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7ScanObservation
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7SourceObservationRequest,
    V7WorkerConfiguration,
    V7WorkerRuntime,
    V7WorkerRuntimeError,
    V7WorkerRuntimeProgress,
)
from PIL import Image


class _StopAfterFirst(RuntimeError):
    pass


class _SourceErrorObserver:
    def __init__(self) -> None:
        self.observed_indexes: list[int] = []

    def observe(self, request: V7SourceObservationRequest) -> V7ScanObservation:
        self.observed_indexes.append(request.source.source_index)
        return V7ScanObservation(
            source_index=request.source.source_index,
            proof=V7RangeProofResult(
                kind=V7RangeProofKind.NONE,
                sequence_range=None,
                supporting_source_ids=(),
                reason_codes=("TEST_NO_PROOF",),
            ),
            quality=None,
            source_error_code="TEST_SOURCE_ERROR",
        )


class _Factory:
    def __init__(self, observers: Sequence[_SourceErrorObserver]) -> None:
        self._observers = list(observers)

    def create(
        self,
        _configuration: V7WorkerConfiguration,
        _manifest: object,
    ) -> _SourceErrorObserver:
        return self._observers.pop(0)


def _jpeg_bytes(value: int) -> bytes:
    stream = BytesIO()
    Image.new("RGB", (16, 12), (value, value, value)).save(stream, format="JPEG")
    return stream.getvalue()


def _manifest(tmp_path: Path):
    source_root = tmp_path / "source"
    source_root.mkdir()
    (source_root / "1.jpg").write_bytes(_jpeg_bytes(10))
    (source_root / "2.jpg").write_bytes(_jpeg_bytes(20))
    return build_local_source_manifest(
        source_root,
        selection_id=uuid4(),
        display_name="source",
    )


def _configuration() -> V7WorkerConfiguration:
    return V7WorkerConfiguration(
        first_sequence_number=1,
        last_sequence_number=9,
        direction=SemiAutomaticSelectionDirection.ASCENDING,
        border_style=V7BorderStyle.TOP_AND_SIDES,
        localizer_fingerprint="a" * 64,
        calibration_fingerprint="b" * 64,
    )


def test_runtime_resumes_ordered_prefix_and_finalizes_without_output(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    first_observer = _SourceErrorObserver()
    persisted: list[V7WorkerRuntimeProgress] = []

    def stop_after_first(progress: V7WorkerRuntimeProgress) -> None:
        persisted.append(progress)
        if progress.processed_sources == 1:
            raise _StopAfterFirst

    with pytest.raises(_StopAfterFirst):
        V7WorkerRuntime(_Factory((first_observer,))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=stop_after_first,
        )

    resumed_observer = _SourceErrorObserver()
    resumed_persisted: list[V7WorkerRuntimeProgress] = []
    result = V7WorkerRuntime(_Factory((resumed_observer,))).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint=persisted[-1].checkpoint,
        persist=resumed_persisted.append,
    )

    assert first_observer.observed_indexes == [0]
    assert resumed_observer.observed_indexes == [1]
    assert result.finalization.selections == ()
    assert result.checkpoint["scanState"]["phase"] == "finalized"
    assert not (tmp_path / "source cut").exists()


def test_runtime_blocks_changed_unselected_source_before_observer(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "source" / "2.jpg").write_bytes(_jpeg_bytes(99))
    observer = _SourceErrorObserver()
    persisted: list[V7WorkerRuntimeProgress] = []

    with pytest.raises(V7WorkerRuntimeError, match="pinned V7 source folder changed") as error:
        V7WorkerRuntime(_Factory((observer,))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=persisted.append,
        )

    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
    assert observer.observed_indexes == []
    assert persisted[-1].blocked_source_drift is True
    assert persisted[-1].checkpoint["blockedReason"] == "V7_SOURCE_MANIFEST_DRIFT"

    with pytest.raises(V7WorkerRuntimeError) as resumed_error:
        V7WorkerRuntime(_Factory((_SourceErrorObserver(),))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint=persisted[-1].checkpoint,
            persist=lambda _progress: None,
        )

    assert resumed_error.value.code == "V7_SOURCE_MANIFEST_DRIFT"


def test_default_runtime_rejects_missing_calibration_before_source_is_checked(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    (tmp_path / "source" / "1.jpg").unlink()

    with pytest.raises(V7WorkerRuntimeError) as error:
        V7WorkerRuntime().run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=lambda _progress: None,
        )

    assert error.value.code == "V7_CALIBRATION_UNAVAILABLE"


def test_runtime_keeps_source_drift_block_after_all_jpegs_are_restored(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    source_root = tmp_path / "source"
    original = {
        path.name: path.read_bytes()
        for path in (source_root / "1.jpg", source_root / "2.jpg")
    }
    (source_root / "1.jpg").unlink()
    (source_root / "2.jpg").unlink()
    persisted: list[V7WorkerRuntimeProgress] = []

    with pytest.raises(V7WorkerRuntimeError) as error:
        V7WorkerRuntime(_Factory((_SourceErrorObserver(),))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=persisted.append,
        )

    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
    assert persisted[-1].checkpoint["blockedReason"] == "V7_SOURCE_MANIFEST_DRIFT"
    for name, content in original.items():
        (source_root / name).write_bytes(content)
    resumed_observer = _SourceErrorObserver()

    with pytest.raises(V7WorkerRuntimeError) as resumed_error:
        V7WorkerRuntime(_Factory((resumed_observer,))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint=persisted[-1].checkpoint,
            persist=lambda _progress: None,
        )

    assert resumed_error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
    assert resumed_observer.observed_indexes == []


def test_runtime_allows_retry_after_the_whole_source_folder_becomes_available(
    tmp_path: Path,
) -> None:
    manifest = _manifest(tmp_path)
    source_root = tmp_path / "source"
    temporarily_unavailable = tmp_path / "source-unavailable"
    source_root.rename(temporarily_unavailable)
    persisted: list[V7WorkerRuntimeProgress] = []

    with pytest.raises(V7WorkerRuntimeError) as error:
        V7WorkerRuntime(_Factory((_SourceErrorObserver(),))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=persisted.append,
        )

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_SOURCE_UNAVAILABLE"
    assert persisted == []
    temporarily_unavailable.rename(source_root)
    observer = _SourceErrorObserver()
    result = V7WorkerRuntime(_Factory((observer,))).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=lambda _progress: None,
    )

    assert observer.observed_indexes == [0, 1]
    assert result.finalization.selections == ()


def test_runtime_configuration_keeps_ascending_range_names_for_descending_capture() -> None:
    configuration = V7WorkerConfiguration(
        first_sequence_number=1,
        last_sequence_number=18,
        direction=SemiAutomaticSelectionDirection.DESCENDING,
        border_style=V7BorderStyle.TOP_AND_SIDES,
        localizer_fingerprint="a" * 64,
        calibration_fingerprint="b" * 64,
    )

    assert [(item.start, item.end) for item in configuration.expected_ranges] == [
        (10, 18),
        (1, 9),
    ]
