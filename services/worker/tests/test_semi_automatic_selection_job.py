from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import NoReturn
from uuid import UUID, uuid4

import numpy as np
import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionDirection as ApiDirection,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRange as ApiRange,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRangeStatus as ApiRangeStatus,
)
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSourceManifest,
    create_semi_automatic_selection_run,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.engine import grouping_policy_fingerprint
from game_predictor_worker.semi_automatic_selection.job import (
    SelectionApplyOutcome,
    SemiAutomaticImageSelectionJobHandler,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    middle_row_grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.middle_row_locator import (
    BoundingBox,
    CanonicalSourceImage,
    LocalQualityScores,
    MiddleRowLabelCrop,
    MiddleRowLocation,
    MiddleRowLocatorMode,
    MiddleRowLocatorResult,
)
from game_predictor_worker.semi_automatic_selection.middle_row_runtime import (
    MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
    MiddleRowPaddleRecognitionAdapter,
    MiddleRowRunOrientation,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
    RangeOnlyRecognition,
)
from PIL import Image


class _WaitForReview(RuntimeError):
    pass


class _Context:
    def __init__(self) -> None:
        self.lease_token = uuid4()
        self.checkpoints: list[dict[str, object]] = []

    def now(self) -> datetime:
        return datetime.now(UTC)

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(dict(values))

    def wait_for_review(self) -> NoReturn:
        raise _WaitForReview


class _ScriptedRecognizer:
    version = "scripted-range-only-v1"

    def __init__(
        self,
        recognitions: list[RangeOnlyRecognition],
        *,
        fingerprint: str = "1" * 64,
    ) -> None:
        self._recognitions = recognitions
        self.fingerprint = fingerprint
        self.calls = 0

    def recognize(
        self,
        rgb_image: np.ndarray[tuple[int, ...], np.dtype[np.uint8]],
    ) -> RangeOnlyRecognition:
        assert rgb_image.ndim == 3
        result = self._recognitions[self.calls]
        self.calls += 1
        return result


class _MiddleRowRecognitionBackend:
    version = "fake-middle-row-paddle-v1"
    model_name = "fake-digits"
    model_fingerprint = "a" * 64
    model_files: Mapping[str, str] = {"model.bin": "b" * 64}
    runtime_name = "fake-paddle-cpu"
    runtime_version = "1.0"

    def __init__(self) -> None:
        self.batch_sizes: list[int] = []

    def recognize_many(
        self,
        rgb_images: Sequence[np.ndarray],
    ) -> tuple[object, ...]:
        self.batch_sizes.append(len(rgb_images))

        class _Value:
            def __init__(self, image: np.ndarray) -> None:
                self.raw_text = str(int(image[0, 0, 0]))
                self.confidence = 0.96

        return tuple(_Value(image) for image in rgb_images)


class _MiddleRowLocator:
    fingerprint = "c" * 64

    def __init__(self, values: Sequence[tuple[int, int, int]]) -> None:
        self.values = list(values)

    def locate(
        self,
        _source: CanonicalSourceImage,
        *,
        prior: object = None,
    ) -> MiddleRowLocatorResult:
        del prior
        values = self.values.pop(0)
        boxes = (
            BoundingBox(1, 2, 3, 4),
            BoundingBox(5, 2, 7, 4),
            BoundingBox(9, 2, 11, 4),
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
                row_axes=(2, 5, 8),
                middle_row_centers=((2, 5), (6, 5), (10, 5)),
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
            diagnostics={},
        )


class _MemoryStore:
    def __init__(
        self,
        run: SemiAutomaticSelectionRun,
        ranges: tuple[ApiRange, ...],
    ) -> None:
        self.run = run
        self.ranges = {(item.range_start, item.range_end): item for item in ranges}
        self.pause_after_processed_sources: int | None = None

    def get_run_for_job(self, job_id: UUID) -> SemiAutomaticSelectionRun:
        assert job_id == self.run.job.id
        return self.run

    def persist_checkpoint(
        self,
        *,
        checkpoint: dict[str, object] | object,
        counters: dict[str, int] | object,
        persisted_at: datetime,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        status = SemiAutomaticSelectionRunStatus.RUNNING
        parsed_counters = dict(counters)  # type: ignore[arg-type]
        if parsed_counters.get("processedSources") == self.pause_after_processed_sources:
            status = SemiAutomaticSelectionRunStatus.PAUSED
            self.pause_after_processed_sources = None
        self.run = replace(
            self.run,
            status=status,
            checkpoint=dict(checkpoint),  # type: ignore[arg-type]
            counters=parsed_counters,
            revision=self.run.revision + 1,
            updated_at=persisted_at,
        )
        return self.run

    def apply_selection(
        self,
        *,
        selection: object,
        checkpoint: object,
        increment_out_of_order: bool,
        persisted_at: datetime,
        **_values: object,
    ) -> SelectionApplyOutcome:
        group_selection = selection
        group = group_selection.group  # type: ignore[attr-defined]
        evidence = group_selection.evidence  # type: ignore[attr-defined]
        key = (group.sequence_range.start, group.sequence_range.end)
        item = self.ranges[key]
        counters = dict(self.run.counters)
        applied = item.status is ApiRangeStatus.MISSING
        if applied:
            source = evidence.source
            self.ranges[key] = replace(
                item,
                status=ApiRangeStatus.AUTO_SELECTED,
                source_index=source.source_index,
                source_relative_path=source.relative_path,
                source_size_bytes=source.size_bytes,
                source_checksum_sha256=source.checksum_sha256,
                group_first_source_index=group.first_source_index,
                group_last_source_index=group.last_source_index,
                range_confidence=evidence.confidence,
                selection_method=group_selection.selection_method,
                revision=item.revision + 1,
                updated_at=persisted_at,
            )
            counters["autoSelected"] += 1
            counters["missing"] -= 1
            if group_selection.selection_method == MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION:
                counters["selectedRanges"] = counters.get("selectedRanges", 0) + 1
        else:
            counters["duplicateGroups"] = counters.get("duplicateGroups", 0) + 1
            if group_selection.selection_method == MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION:
                counters["duplicateRanges"] = counters.get("duplicateRanges", 0) + 1
        if increment_out_of_order:
            counters["outOfOrderGroups"] = counters.get("outOfOrderGroups", 0) + 1
        self.run = replace(
            self.run,
            status=SemiAutomaticSelectionRunStatus.RUNNING,
            checkpoint=dict(checkpoint),  # type: ignore[arg-type]
            counters=counters,
            revision=self.run.revision + 1,
            updated_at=persisted_at,
        )
        return SelectionApplyOutcome(run=self.run, applied=applied)

    def missing_ranges(self, _run_id: UUID) -> tuple[tuple[int, int, int], ...]:
        return tuple(
            (item.expected_index, item.range_start, item.range_end)
            for item in sorted(self.ranges.values(), key=lambda value: value.expected_index)
            if item.status is ApiRangeStatus.MISSING
        )

    def finalize_analysis(
        self,
        *,
        checkpoint: object,
        counters: object,
        diagnostics_relative_path: str,
        diagnostics_checksum_sha256: str,
        persisted_at: datetime,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        self.run = replace(
            self.run,
            status=SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
            checkpoint=dict(checkpoint),  # type: ignore[arg-type]
            counters=dict(counters),  # type: ignore[arg-type]
            diagnostics_relative_path=diagnostics_relative_path,
            diagnostics_checksum_sha256=diagnostics_checksum_sha256,
            revision=self.run.revision + 1,
            updated_at=persisted_at,
        )
        return self.run


def _jpeg(color: tuple[int, int, int]) -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 18), color).save(output, format="JPEG")
    return output.getvalue()


def _ready_run(
    tmp_path: Path,
    *,
    recognizer_fingerprint: str = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
    source_count: int = 4,
    source_color: tuple[int, int, int] | None = None,
) -> tuple[SemiAutomaticSelectionRun, tuple[ApiRange, ...]]:
    upload_id = uuid4()
    source_root = tmp_path / "imports" / "browser-selections" / str(upload_id)
    source_root.mkdir(parents=True)
    sources: list[SemiAutomaticSelectionSource] = []
    files: list[dict[str, object]] = []
    for index in range(source_count):
        content = _jpeg(source_color or (10 + index, 20 + index, 30 + index))
        checksum = hashlib.sha256(content).hexdigest()
        relative_path = f"selection/photo-{index + 1}.jpg"
        stored_file_name = f"{index + 1:08d}.jpg"
        (source_root / stored_file_name).write_bytes(content)
        source = SemiAutomaticSelectionSource(
            source_index=index,
            relative_path=relative_path,
            size_bytes=len(content),
            checksum_sha256=checksum,
        )
        sources.append(source)
        files.append(
            {
                "checksumSha256": checksum,
                "orderIndex": index,
                "relativePath": relative_path,
                "sizeBytes": len(content),
                "storedFileName": stored_file_name,
            }
        )
    manifest = {
        "files": files,
        "gameId": None,
        "orderingPolicy": "natural_relative_path_v1",
        "purpose": "semi_automatic_selection",
        "schemaVersion": 1,
    }
    content = json.dumps(manifest, separators=(",", ":"), sort_keys=True).encode("utf-8")
    (source_root / "_browser_manifest.json").write_bytes(content)
    source_manifest = SemiAutomaticSelectionSourceManifest(
        upload_id=upload_id,
        display_name="selection",
        manifest_checksum_sha256=hashlib.sha256(content).hexdigest(),
        source_fingerprint=hashlib.sha256(
            json.dumps(
                [source.as_dict() for source in sources],
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
        source_count=len(sources),
        source_total_bytes=sum(source.size_bytes for source in sources),
    )
    return create_semi_automatic_selection_run(
        source=source_manifest,
        first_sequence_number=1,
        last_sequence_number=18,
        direction=ApiDirection.ASCENDING,
        recognizer_fingerprint=recognizer_fingerprint,
        grouping_policy_fingerprint=(
            middle_row_grouping_policy_fingerprint()
            if recognizer_fingerprint == MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4
            else grouping_policy_fingerprint()
        ),
    )


def _exact(start: int, end: int, confidence: float) -> RangeOnlyRecognition:
    return RangeOnlyRecognition(
        observed_range=SemiAutomaticSelectionRange(start=start, end=end),
        confidence=confidence,
        has_strong_local_proof=True,
        reason_codes=("TEST_EXACT_RANGE",),
    )


def test_handler_scans_once_selects_middle_and_resumes_without_ocr(tmp_path: Path) -> None:
    run, ranges = _ready_run(tmp_path)
    store = _MemoryStore(run, ranges)
    recognizer = _ScriptedRecognizer(
        [
            _exact(1, 9, 0.91),
            _exact(1, 9, 0.96),
            _exact(10, 18, 0.95),
            _exact(10, 18, 0.92),
        ]
    )
    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: recognizer,
    )
    context = _Context()

    with pytest.raises(_WaitForReview):
        handler(context, run.job)  # type: ignore[arg-type]

    assert recognizer.calls == 4
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["autoSelected"] == 2
    assert store.run.counters["missing"] == 0
    assert store.ranges[(1, 9)].source_index == 1
    assert store.ranges[(10, 18)].source_index == 2
    assert store.run.diagnostics_relative_path is not None
    report_path = tmp_path / "artifacts" / store.run.diagnostics_relative_path
    assert report_path.is_file()
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == (
        store.run.diagnostics_checksum_sha256
    )

    def fail_if_recognizer_is_rebuilt(_path: Path, _contract: str) -> NoReturn:
        raise AssertionError("A completed checkpoint must not rerun OCR.")

    resumed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=fail_if_recognizer_is_rebuilt,
    )
    with pytest.raises(_WaitForReview):
        resumed_handler(_Context(), run.job)  # type: ignore[arg-type]


def test_handler_resumes_a_paused_scan_from_the_next_source(tmp_path: Path) -> None:
    run, ranges = _ready_run(tmp_path)
    store = _MemoryStore(run, ranges)
    store.pause_after_processed_sources = 2
    first_recognizer = _ScriptedRecognizer([_exact(1, 9, 0.95), _exact(1, 9, 0.96)])
    first_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: first_recognizer,
    )

    with pytest.raises(_WaitForReview):
        first_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert first_recognizer.calls == 2
    assert store.run.status is SemiAutomaticSelectionRunStatus.PAUSED
    assert store.run.checkpoint["observationCount"] == 2

    store.run = replace(store.run, status=SemiAutomaticSelectionRunStatus.READY)
    changed_recognizer = _ScriptedRecognizer(
        [_exact(10, 18, 0.95), _exact(10, 18, 0.94)],
        fingerprint="2" * 64,
    )
    changed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: changed_recognizer,
    )
    with pytest.raises(JobHandlerError) as changed:
        changed_handler(_Context(), run.job)  # type: ignore[arg-type]
    assert changed.value.code == "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID"
    assert changed_recognizer.calls == 0

    resumed_recognizer = _ScriptedRecognizer([_exact(10, 18, 0.95), _exact(10, 18, 0.94)])
    resumed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: resumed_recognizer,
    )

    with pytest.raises(_WaitForReview):
        resumed_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert resumed_recognizer.calls == 2
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["processedSources"] == 4


def test_v3_scheduler_resumes_and_avoids_redundant_ocr(tmp_path: Path) -> None:
    run, ranges = _ready_run(
        tmp_path,
        recognizer_fingerprint=RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
        source_count=11,
        source_color=(20, 30, 40),
    )
    store = _MemoryStore(run, ranges)
    store.pause_after_processed_sources = 10
    first_recognizer = _ScriptedRecognizer([_exact(1, 9, 0.95), _exact(1, 9, 0.96)])
    first_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: first_recognizer,
    )

    with pytest.raises(_WaitForReview):
        first_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert first_recognizer.calls == 2
    assert store.run.checkpoint["observationCount"] == 10
    scheduling = store.run.checkpoint["ocrSchedulingState"]
    assert isinstance(scheduling, dict)
    assert scheduling["nextSourceIndex"] == 10

    store.run = replace(store.run, status=SemiAutomaticSelectionRunStatus.READY)
    resumed_recognizer = _ScriptedRecognizer([_exact(1, 9, 0.97)])
    resumed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: resumed_recognizer,
    )

    with pytest.raises(_WaitForReview):
        resumed_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert resumed_recognizer.calls == 1
    assert store.run.counters["processedSources"] == 11
    assert store.run.counters["ocrProbedSources"] == 3
    assert store.run.counters["ocrSkippedSources"] == 8


def test_v4_batch_checkpoint_resumes_without_duplicate_observations(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        recognizer_fingerprint=MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
        source_count=8,
    )
    store = _MemoryStore(run, ranges)
    store.pause_after_processed_sources = 6
    first_backend = _MiddleRowRecognitionBackend()
    first_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        middle_row_recognizer_factory=lambda _path: MiddleRowPaddleRecognitionAdapter(
            first_backend
        ),
        middle_row_locator_factory=lambda: _MiddleRowLocator(
            (
                (4, 5, 6),
                (4, 5, 6),
                (4, 5, 6),
                (4, 5, 6),
                (4, 5, 6),
                (4, 5, 6),
            )
        ),  # type: ignore[arg-type]
        v4_orientation_override=MiddleRowRunOrientation.DEG_0,
    )

    with pytest.raises(_WaitForReview):
        first_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert store.run.status is SemiAutomaticSelectionRunStatus.PAUSED
    assert store.run.checkpoint["observationCount"] == 6
    assert store.run.checkpoint["lastCommittedBatch"] == 0
    assert store.run.checkpoint["sourceBatchSize"] == 6
    assert first_backend.batch_sizes == [9, 9]

    observations_path = (
        tmp_path
        / "artifacts"
        / "exports"
        / "semi-automatic-selection"
        / str(run.id)
        / "observations.jsonl"
    )
    with observations_path.open("a", encoding="utf-8") as stream:
        stream.write("{}\n")

    store.run = replace(store.run, status=SemiAutomaticSelectionRunStatus.READY)
    resumed_backend = _MiddleRowRecognitionBackend()
    resumed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        middle_row_recognizer_factory=lambda _path: MiddleRowPaddleRecognitionAdapter(
            resumed_backend
        ),
        middle_row_locator_factory=lambda: _MiddleRowLocator(((13, 14, 15), (13, 14, 15))),  # type: ignore[arg-type]
        v4_orientation_override=MiddleRowRunOrientation.DEG_0,
    )

    with pytest.raises(_WaitForReview):
        resumed_handler(_Context(), run.job)  # type: ignore[arg-type]

    persisted_observations = [
        json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(persisted_observations) == 8
    assert [item["sourceIndex"] for item in persisted_observations] == list(range(8))
    assert len({item["observationKey"] for item in persisted_observations}) == 8
    assert resumed_backend.batch_sizes == [6]
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["selectedRanges"] == 2
    assert store.ranges[(1, 9)].source_index == 2
    assert store.ranges[(10, 18)].source_index == 6


def test_v4_already_saved_and_out_of_order_ranges_remain_diagnostic(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        recognizer_fingerprint=MIDDLE_ROW_RECOGNIZER_CONTRACT_FINGERPRINT_V4,
        source_count=6,
    )
    store = _MemoryStore(run, ranges)
    backend = _MiddleRowRecognitionBackend()
    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        middle_row_recognizer_factory=lambda _path: MiddleRowPaddleRecognitionAdapter(backend),
        middle_row_locator_factory=lambda: _MiddleRowLocator(
            (
                (13, 14, 15),
                (13, 14, 15),
                (4, 5, 6),
                (4, 5, 6),
                (13, 14, 15),
                (13, 14, 15),
            )
        ),  # type: ignore[arg-type]
        v4_orientation_override=MiddleRowRunOrientation.DEG_0,
    )

    with pytest.raises(_WaitForReview):
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert backend.batch_sizes == [9, 9]
    assert store.run.counters["selectedRanges"] == 2
    assert store.run.counters["duplicateRanges"] == 1
    assert store.run.counters["outOfOrderGroups"] == 1
    assert store.ranges[(10, 18)].source_index == 0
    assert store.ranges[(1, 9)].source_index == 2


def test_handler_preserves_lease_conflict_from_the_store(tmp_path: Path) -> None:
    run, _ranges = _ready_run(tmp_path)

    class _LeaseLostStore:
        def get_run_for_job(self, _job_id: UUID) -> NoReturn:
            raise JobConflictError("JOB_LEASE_LOST", "The job lease is no longer valid.")

    handler = SemiAutomaticImageSelectionJobHandler(
        _LeaseLostStore(),  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: pytest.fail(
            "OCR must not start without a lease."
        ),
    )

    with pytest.raises(JobConflictError) as error:
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert error.value.code == "JOB_LEASE_LOST"


@pytest.mark.parametrize(
    "contract_fingerprint",
    (
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V1,
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
        RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V3,
    ),
)
def test_handler_resolves_the_recognizer_from_the_durable_run_contract(
    tmp_path: Path,
    contract_fingerprint: str,
) -> None:
    run, ranges = _ready_run(tmp_path, recognizer_fingerprint=contract_fingerprint)
    store = _MemoryStore(run, ranges)
    recognizer = _ScriptedRecognizer(
        [_exact(1, 9, 0.95), _exact(1, 9, 0.96), _exact(10, 18, 0.95), _exact(10, 18, 0.94)]
    )
    requested_contracts: list[str] = []

    def factory(_path: Path, requested_contract: str) -> _ScriptedRecognizer:
        requested_contracts.append(requested_contract)
        return recognizer

    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=factory,
    )

    with pytest.raises(_WaitForReview):
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert requested_contracts == [contract_fingerprint]


def test_handler_rejects_an_unknown_durable_recognizer_before_ocr(tmp_path: Path) -> None:
    run, ranges = _ready_run(tmp_path, recognizer_fingerprint="f" * 64)
    store = _MemoryStore(run, ranges)
    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: pytest.fail(
            "An unsupported durable contract must fail before OCR construction."
        ),
    )

    with pytest.raises(JobHandlerError) as error:
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_UNSUPPORTED"
