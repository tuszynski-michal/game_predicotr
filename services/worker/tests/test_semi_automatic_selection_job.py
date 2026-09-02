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
    SemiAutomaticSelectionWorkflowMode,
    create_semi_automatic_selection_run,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.engine import grouping_policy_fingerprint
from game_predictor_worker.semi_automatic_selection.five_anchor_range_label_locator import (
    FiveAnchorBoundingBox,
    FiveAnchorLabelCrop,
    FiveAnchorLocation,
    FiveAnchorLocatorMode,
    FiveAnchorLocatorResult,
    FiveAnchorPosition,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_runtime import (
    FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
)
from game_predictor_worker.semi_automatic_selection.job import (
    SelectionApplyOutcome,
    SemiAutomaticImageSelectionJobHandler,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (
    FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
    MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
    ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
    five_anchor_grouping_policy_fingerprint,
    middle_row_grouping_policy_fingerprint,
    row_first_grouping_policy_fingerprint,
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
    RangeOnlyLabelEvidence,
    RangeOnlyRecognition,
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


class _WaitForReview(RuntimeError):
    pass


class _Context:
    def __init__(self) -> None:
        self.lease_token = uuid4()
        self.checkpoints: list[dict[str, object]] = []

    def now(self) -> datetime:
        return datetime.now(UTC)

    def checkpoint(self, **values: object) -> None:
        payload = values["checkpoint_payload"]
        assert isinstance(payload, dict)
        assert payload.get("schema_version") == 1
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


class _RowFirstLocator:
    fingerprint = "e" * 64

    def __init__(self, values: Sequence[tuple[tuple[int, int, int], tuple[int, int, int]]]) -> None:
        self.values = list(values)

    def locate(self, _source: CanonicalSourceImage) -> RowFirstLocatorResult:
        top_values, middle_values = self.values.pop(0)
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

        def build_row(
            row: RangeRowOffset,
            values: tuple[int, int, int],
        ) -> RowFirstRowHypothesis:
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
                row=row,
                centers=((2, 3), (6, 3), (10, 3)),
                component_boxes=boxes,
                crops=crops,  # type: ignore[arg-type]
                baseline_slope=0,
                score=0.95,
                source_roi_level=0,
            )

        return RowFirstLocatorResult(
            location=RowFirstLocation(
                rows=(
                    build_row(RangeRowOffset.TOP, top_values),
                    build_row(RangeRowOffset.MIDDLE, middle_values),
                ),
                candidate_boxes=(),
                locator_fingerprint=self.fingerprint,
            ),
            reason_code=None,
            diagnostics={},
        )


class _FiveAnchorLocator:
    fingerprint = "f" * 64

    def __init__(self, values: Sequence[tuple[int, int, int, int, int]]) -> None:
        self.values = list(values)

    def locate(self, _rgb: np.ndarray) -> FiveAnchorLocatorResult:
        values = self.values.pop(0)
        cells = (np.indices((6, 12)).sum(axis=0) % 2).astype(np.uint8)
        base = np.kron(cells, np.ones((4, 4), dtype=np.uint8)) * 228 + 16
        pattern = np.stack((base, base, base), axis=2)

        def crop_pixels(value: int) -> np.ndarray:
            pixels = pattern.copy()
            pixels[0, 0] = value
            return pixels

        crops = tuple(
            FiveAnchorLabelCrop(
                position=position,
                box=FiveAnchorBoundingBox(left=0, top=0, right=48, bottom=24),
                rgb=crop_pixels(value),
                complete=True,
                mode=FiveAnchorLocatorMode.VIEWPORT_FALLBACK,
            )
            for position, value in zip(FiveAnchorPosition, values, strict=True)
        )
        return FiveAnchorLocatorResult(
            location=FiveAnchorLocation(crops=crops, fingerprint=self.fingerprint),
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
        self.apply_selection_calls = 0

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
        self.apply_selection_calls += 1
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
            if group_selection.selection_method in {
                MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
                ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
                FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
            }:
                counters["selectedRanges"] = counters.get("selectedRanges", 0) + 1
        else:
            counters["duplicateGroups"] = counters.get("duplicateGroups", 0) + 1
            if group_selection.selection_method in {
                MIDDLE_ROW_EVIDENCE_SELECTOR_VERSION,
                ROW_FIRST_EVIDENCE_SELECTOR_VERSION,
                FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION,
            }:
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

    def reset_unacknowledged_filename_selections(
        self,
        *,
        persisted_at: datetime,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        restored = 0
        for key, item in tuple(self.ranges.items()):
            if item.status is not ApiRangeStatus.AUTO_SELECTED:
                continue
            self.ranges[key] = replace(
                item,
                status=ApiRangeStatus.MISSING,
                source_index=None,
                source_relative_path=None,
                source_size_bytes=None,
                source_checksum_sha256=None,
                group_first_source_index=None,
                group_last_source_index=None,
                range_confidence=None,
                selection_method=None,
                output_checksum_sha256=None,
                revision=item.revision + 1,
                updated_at=persisted_at,
            )
            restored += 1
        if restored:
            counters = dict(self.run.counters)
            counters["autoSelected"] = max(0, counters.get("autoSelected", 0) - restored)
            counters["missing"] = counters.get("missing", 0) + restored
            self.run = replace(
                self.run,
                counters=counters,
                revision=self.run.revision + 1,
                updated_at=persisted_at,
            )
        return self.run

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

    def begin_filename_verification_cleanup(
        self,
        *,
        persisted_at: datetime,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        self.run = replace(
            self.run,
            status=SemiAutomaticSelectionRunStatus.CLEANUP_PENDING,
            checkpoint={**self.run.checkpoint, "cleanup": "pending", "phase": "cleanup_pending"},
            revision=self.run.revision + 1,
            updated_at=persisted_at,
        )
        return self.run

    def complete_filename_verification_cleanup(
        self,
        *,
        persisted_at: datetime,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        self.ranges.clear()
        self.run = replace(
            self.run,
            status=SemiAutomaticSelectionRunStatus.COMPLETED,
            checkpoint={
                "cleanup": "completed",
                "observationCount": self.run.source.source_count,
                "phase": "cleanup_complete",
                "schemaVersion": 1,
            },
            diagnostics_relative_path=None,
            diagnostics_checksum_sha256=None,
            revision=self.run.revision + 1,
            updated_at=persisted_at,
        )
        return self.run

    def mark_filename_verification_cleanup_blocked(
        self,
        *,
        persisted_at: datetime,
        error_code: str,
        **_values: object,
    ) -> SemiAutomaticSelectionRun:
        self.run = replace(
            self.run,
            status=SemiAutomaticSelectionRunStatus.CLEANUP_BLOCKED,
            checkpoint={
                **self.run.checkpoint,
                "cleanup": "blocked",
                "cleanupErrorCode": error_code,
                "phase": "cleanup_blocked",
            },
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
    source_relative_paths: Sequence[str] | None = None,
    workflow_mode: SemiAutomaticSelectionWorkflowMode = (
        SemiAutomaticSelectionWorkflowMode.SELECTION
    ),
) -> tuple[SemiAutomaticSelectionRun, tuple[ApiRange, ...]]:
    upload_id = uuid4()
    source_root = tmp_path / "imports" / "browser-selections" / str(upload_id)
    source_root.mkdir(parents=True)
    sources: list[SemiAutomaticSelectionSource] = []
    files: list[dict[str, object]] = []
    for index in range(source_count):
        content = _jpeg(source_color or (10 + index, 20 + index, 30 + index))
        checksum = hashlib.sha256(content).hexdigest()
        relative_path = (
            source_relative_paths[index]
            if source_relative_paths is not None
            else f"selection/photo-{index + 1}.jpg"
        )
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
            else (
                row_first_grouping_policy_fingerprint()
                if recognizer_fingerprint == ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5
                else (
                    five_anchor_grouping_policy_fingerprint()
                    if recognizer_fingerprint == FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
                    else grouping_policy_fingerprint()
                )
            )
        ),
        workflow_mode=workflow_mode,
    )


def _exact(start: int, end: int, confidence: float) -> RangeOnlyRecognition:
    return RangeOnlyRecognition(
        observed_range=SemiAutomaticSelectionRange(start=start, end=end),
        confidence=confidence,
        has_strong_local_proof=True,
        reason_codes=("TEST_EXACT_RANGE",),
    )


def _filename_verified_exact(start: int, end: int) -> RangeOnlyRecognition:
    return RangeOnlyRecognition(
        observed_range=SemiAutomaticSelectionRange(start=start, end=end),
        confidence=0.95,
        has_strong_local_proof=True,
        reason_codes=("TEST_EXACT_RANGE",),
        label_evidence=tuple(
            RangeOnlyLabelEvidence(
                position_index=position,
                sequence_number=start + position,
                confidence=0.95,
                route="test",
            )
            for position in (0, 4, 8)
        ),
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


def test_filename_verification_finishes_without_selection_or_progress_regression(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        source_count=2,
        source_relative_paths=("seq_1-9.jpg", "seq_10-18.jpg"),
        workflow_mode=SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION,
    )
    store = _MemoryStore(run, ranges)
    recognizer = _ScriptedRecognizer(
        [_exact(1, 9, 0.95), _exact(10, 18, 0.95)],
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

    assert recognizer.calls == 2
    assert store.apply_selection_calls == 0
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["filenameVerified"] == 0
    assert store.run.counters["filenameUnreadable"] == 2
    assert store.run.counters["filenameReviewRequired"] == 2
    assert [item.status for item in store.ranges.values()] == [
        ApiRangeStatus.MISSING,
        ApiRangeStatus.MISSING,
    ]
    assert context.checkpoints[-1]["success_count"] == 0
    assert context.checkpoints[-1]["review_count"] == 2

    def fail_if_recognizer_is_rebuilt(_path: Path, _contract: str) -> NoReturn:
        raise AssertionError("A completed filename verification must not rerun OCR.")

    resumed_handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=fail_if_recognizer_is_rebuilt,
    )
    resumed_context = _Context()
    with pytest.raises(_WaitForReview):
        resumed_handler(resumed_context, run.job)  # type: ignore[arg-type]

    assert resumed_context.checkpoints[-1]["current"] == 2
    assert resumed_context.checkpoints[-1]["success_count"] == 0
    assert resumed_context.checkpoints[-1]["review_count"] == 2


def test_filename_verification_with_only_matching_files_cleans_working_data(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        source_count=2,
        source_relative_paths=("seq_1-9.jpg", "seq_10-18.jpg"),
        workflow_mode=SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION,
    )
    store = _MemoryStore(run, ranges)
    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=tmp_path / "artifacts",
        repository_root=tmp_path,
        recognizer_factory=lambda _path, _contract: _ScriptedRecognizer(
            [_filename_verified_exact(1, 9), _filename_verified_exact(10, 18)]
        ),
    )
    context = _Context()

    handler(context, run.job)  # type: ignore[arg-type]

    assert store.apply_selection_calls == 0
    assert store.run.status is SemiAutomaticSelectionRunStatus.COMPLETED
    assert store.run.checkpoint["cleanup"] == "completed"
    assert store.run.diagnostics_relative_path is None
    assert store.ranges == {}
    assert not (
        tmp_path / "imports" / "browser-selections" / str(run.source.upload_id)
    ).exists()
    assert not (
        tmp_path / "artifacts" / "exports" / "semi-automatic-selection" / str(run.id)
    ).exists()


def test_filename_cleanup_blocks_without_deleting_staging_on_unsafe_artifact(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        source_count=1,
        source_relative_paths=("seq_1-9.jpg",),
        workflow_mode=SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION,
    )
    store = _MemoryStore(
        replace(run, status=SemiAutomaticSelectionRunStatus.CLEANUP_PENDING),
        ranges,
    )
    artifact_root = tmp_path / "artifacts"
    unsafe_artifact = artifact_root / "exports" / "semi-automatic-selection" / str(run.id)
    unsafe_artifact.parent.mkdir(parents=True)
    unsafe_artifact.write_text("not a directory", encoding="utf-8")
    handler = SemiAutomaticImageSelectionJobHandler(
        store,  # type: ignore[arg-type]
        browser_upload_root=tmp_path / "imports",
        artifact_root=artifact_root,
        repository_root=tmp_path,
    )

    with pytest.raises(JobHandlerError) as error:
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert error.value.code == "SEMI_AUTOMATIC_SELECTION_CLEANUP_BLOCKED"
    assert store.run.status is SemiAutomaticSelectionRunStatus.CLEANUP_BLOCKED
    assert (
        tmp_path / "imports" / "browser-selections" / str(run.source.upload_id)
    ).is_dir()


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


def test_v5_batch_checkpoint_resumes_without_duplicate_observations(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        recognizer_fingerprint=ROW_FIRST_RECOGNIZER_CONTRACT_FINGERPRINT_V5,
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
        row_first_locator_factory=lambda: _RowFirstLocator(
            tuple((((1, 2, 3), (4, 5, 6))) for _ in range(6))
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(_WaitForReview):
        first_handler(_Context(), run.job)  # type: ignore[arg-type]

    assert store.run.status is SemiAutomaticSelectionRunStatus.PAUSED
    assert store.run.checkpoint["observationCount"] == 6
    assert store.run.checkpoint["lastCommittedBatch"] == 0
    assert store.run.checkpoint["sourceBatchSize"] == 6
    assert first_backend.batch_sizes == [9, 9, 9, 9]

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
        row_first_locator_factory=lambda: _RowFirstLocator(
            (((10, 11, 12), (13, 14, 15)), ((10, 11, 12), (13, 14, 15)))
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(_WaitForReview):
        resumed_handler(_Context(), run.job)  # type: ignore[arg-type]

    persisted_observations = [
        json.loads(line) for line in observations_path.read_text(encoding="utf-8").splitlines()
    ]
    assert len(persisted_observations) == 8
    assert [item["sourceIndex"] for item in persisted_observations] == list(range(8))
    assert len({item["observationKey"] for item in persisted_observations}) == 8
    assert resumed_backend.batch_sizes == [9, 3]
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["selectedRanges"] == 2
    assert store.ranges[(1, 9)].source_index == 2
    assert store.ranges[(10, 18)].source_index == 6


def test_v6_five_anchor_contract_uses_a_separate_durable_runtime_and_selector(
    tmp_path: Path,
) -> None:
    run, ranges = _ready_run(
        tmp_path,
        recognizer_fingerprint=FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
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
        five_anchor_locator_factory=lambda: _FiveAnchorLocator(
            tuple((1, 3, 5, 7, 9) for _ in range(6))
        ),  # type: ignore[arg-type]
    )

    with pytest.raises(_WaitForReview):
        handler(_Context(), run.job)  # type: ignore[arg-type]

    assert backend.batch_sizes == [9, 9, 9, 3]
    assert store.run.status is SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE
    assert store.run.counters["selectedRanges"] == 1
    assert store.ranges[(1, 9)].source_index == 2
    assert store.run.checkpoint["runtimeVariant"] == (
        FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6
    )
    assert store.ranges[(1, 9)].selection_method == FIVE_ANCHOR_EVIDENCE_SELECTOR_VERSION


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
