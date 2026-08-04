from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobStatus,
    JobType,
    create_job,
    start_job,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.job import (
    ImageSelectionJobHandler,
    ImageSelectionJobRun,
    _assert_fence,
)
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    LEGACY_SELECTOR_MANIFEST_V2,
    SelectorManifest,
)
from game_predictor_worker.images.selection.output import PublishedImageSelection
from game_predictor_worker.images.selection.telemetry import StageTimingCollector
from PIL import Image

NOW = datetime(2026, 8, 3, 10, tzinfo=UTC)


def test_v9_production_adapter_factory_does_not_construct_sequence_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    monkeypatch.setattr(
        "game_predictor_worker.images.selection.job.PaddleSequenceNumberRecognizer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Sequence OCR must not be constructed for v9.")
        ),
    )
    handler = ImageSelectionJobHandler(
        SimpleNamespace(),  # type: ignore[arg-type]
        browser_upload_root=tmp_path,
        artifact_root=tmp_path,
        repository_root=tmp_path,
        selector_manifest=APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    )

    analyzer, verifier = handler._default_adapter_factory(  # noqa: SLF001
        source_root,
        APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
        StageTimingCollector(),
    )

    assert analyzer is not None
    assert verifier is not None


@dataclass
class _Store:
    run: ImageSelectionJobRun
    groups: tuple[SelectionGroupResult, ...] = ()
    published: PublishedImageSelection | None = None

    def get_run_for_job(self, job_id: UUID) -> ImageSelectionJobRun:
        assert job_id == self.run.job_id
        return self.run

    def load_groups(self, run_id: UUID) -> tuple[SelectionGroupResult, ...]:
        assert run_id == self.run.id
        return self.groups

    def persist_groups(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        groups: tuple[SelectionGroupResult, ...],
        persisted_at: datetime,
    ) -> None:
        del lease_token, persisted_at
        assert (job_id, run_id) == (self.run.job_id, self.run.id)
        values = {group.group_order: group for group in self.groups}
        values.update({group.group_order: group for group in groups})
        self.groups = tuple(values[index] for index in sorted(values))

    def record_output(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        published: PublishedImageSelection,
        persisted_at: datetime,
    ) -> None:
        del lease_token, persisted_at
        assert (job_id, run_id) == (self.run.job_id, self.run.id)
        self.published = published
        self.run = replace(
            self.run,
            output_manifest_sha256=published.manifest_sha256,
            output_manifest_relative_path=published.manifest_relative_path,
        )


class _Context:
    def __init__(
        self,
        job: Job,
        *,
        cancel_at_first_checkpoint: bool = False,
    ) -> None:
        self.job = job
        self.lease_token = uuid4()
        self.checkpoints: list[dict[str, object]] = []
        self._cancel_at_first_checkpoint = cancel_at_first_checkpoint
        self._now = NOW

    def now(self) -> datetime:
        value = self._now
        self._now += timedelta(seconds=1)
        return value

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(dict(values))
        checkpoint_payload = values["checkpoint_payload"]
        assert isinstance(checkpoint_payload, dict)
        self.job = replace(
            self.job,
            checkpoint_payload=checkpoint_payload,
            progress_current=int(values["current"]),
            progress_total=int(values["total"]),
            success_count=int(values["success_count"]),
            failure_count=int(values["failure_count"]),
            review_count=int(values["review_count"]),
        )
        if self._cancel_at_first_checkpoint:
            raise _CancelledAtCheckpoint

    def wait_for_review(self) -> None:
        raise AssertionError("The fixture is expected to produce an automatic selection.")


class _CancelledAtCheckpoint(RuntimeError):
    pass


@dataclass
class _Analyzer:
    corrupt_index: int | None = None
    calls: list[int] | None = None

    def analyze(self, source: ImageSelectionSource) -> CheapImageObservation:
        assert self.calls is not None
        self.calls.append(source.order_index)
        corrupted = source.order_index == self.corrupt_index
        score = 0.0 if corrupted else 0.95
        return CheapImageObservation(
            source=source,
            width=1 if corrupted else 64,
            height=1 if corrupted else 48,
            fingerprint_hex="0" * 64,
            geometry_signature=(0.2, 0.2, 0.2, 0.2),
            board_count=None if corrupted else 9,
            geometry_confidence=0.0 if corrupted else 0.95,
            quality=ImageQualityMetrics(*(score for _ in range(8))),
            reason_codes=(("IMAGE_SELECTION_SCAN_DECODE_FAILED",) if corrupted else ()),
        )


class _Verifier:
    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del observation
        return CandidateVerification(
            recognized_range=SequenceRange(1, 9, 0.98),
            board_count=expected_board_count,
            geometry_complete=True,
            full_frame_visible=True,
            reason_codes=(),
        )


class _ManualVerifier:
    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        del observation, expected_board_count
        return CandidateVerification(
            recognized_range=None,
            board_count=None,
            geometry_complete=False,
            full_frame_visible=False,
            reason_codes=("RANGE_ANCHOR_UNREADABLE",),
        )


class _WaitingForReview(RuntimeError):
    pass


class _ReviewContext(_Context):
    def wait_for_review(self) -> None:
        raise _WaitingForReview


def _fixture(
    tmp_path: Path,
    *,
    file_count: int,
    manifest: SelectorManifest,
) -> tuple[Path, Path, Job, _Store]:
    import_root = tmp_path / "imports"
    artifact_root = tmp_path / "artifacts"
    selection_id = uuid4()
    source_root = import_root / "browser-selections" / str(selection_id)
    source_root.mkdir(parents=True)
    files: list[dict[str, object]] = []
    for index in range(file_count):
        stored_name = f"{index + 1:08d}.jpg"
        image_path = source_root / stored_name
        Image.new("RGB", (64, 48), (20 + index, 40, 80)).save(
            image_path,
            format="JPEG",
        )
        content = image_path.read_bytes()
        files.append(
            {
                "checksumSha256": hashlib.sha256(content).hexdigest(),
                "orderIndex": index,
                "relativePath": f"photos/photo{index + 1}.jpg",
                "sizeBytes": len(content),
                "storedFileName": stored_name,
            }
        )
    payload = {
        "files": files,
        "orderingPolicy": "natural_relative_path_v1",
        "purpose": "photo_selection",
        "schemaVersion": 1,
    }
    content = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    (source_root / "_browser_manifest.json").write_bytes(content)
    (source_root / "_upload_metrics.json").write_text(
        json.dumps({"durationSeconds": 12.5}),
        encoding="utf-8",
    )
    created = create_job(
        JobType.IMAGE_SELECTION,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "source_selection_id": str(selection_id),
            "input_manifest_sha256": hashlib.sha256(content).hexdigest(),
            "selector_fingerprint": manifest.fingerprint,
            "contract_version": 1,
        },
        created_at=NOW,
    )
    claimed = start_job(
        created,
        worker_version="worker-test",
        worker_id="worker-test",
        lease_token=uuid4(),
        lease_expires_at=NOW + timedelta(minutes=1),
        started_at=NOW,
    )
    run = ImageSelectionJobRun(
        id=uuid4(),
        job_id=claimed.id,
        source_selection_id=selection_id,
        input_manifest_sha256=hashlib.sha256(content).hexdigest(),
        selector_fingerprint=manifest.fingerprint,
        output_manifest_sha256=None,
        output_manifest_relative_path=None,
    )
    return import_root, artifact_root, claimed, _Store(run)


def test_job_isolates_one_bad_scan_and_publishes_bounded_diagnostics(
    tmp_path: Path,
) -> None:
    manifest = SelectorManifest(scan_batch_size=2)
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=3,
        manifest=manifest,
    )
    calls: list[int] = []
    context = _Context(job)
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=manifest,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(corrupt_index=1, calls=calls),
            _Verifier(),
        ),
    )

    handler(context, job)  # type: ignore[arg-type]

    assert calls == [0, 1, 2]
    assert store.published is not None
    final = context.checkpoints[-1]
    payload = final["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["error_count"] == 1
    assert payload["upload_duration_seconds"] == 12.5
    assert float(payload["processing_duration_seconds"]) > 0
    stage_timing = payload["stage_timing"]
    assert isinstance(stage_timing, dict)
    assert stage_timing["stages"]["output"]["count"] == 1
    assert stage_timing["stages"]["persistence"]["count"] >= 1
    assert stage_timing["counters"]["persistenceWrites"] >= 1
    diagnostic = payload["diagnostic"]
    assert isinstance(diagnostic, dict)
    path = artifact_root / str(diagnostic["relativePath"])
    diagnostic_content = path.read_bytes()
    assert len(diagnostic_content) < 16 * 1024
    assert hashlib.sha256(diagnostic_content).hexdigest() == diagnostic["checksumSha256"]
    assert str(tmp_path).encode() not in diagnostic_content
    assert b"photo2.jpg" not in diagnostic_content


def test_default_handler_resumes_a_persisted_v2_run_with_its_original_manifest(
    tmp_path: Path,
) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=2,
        manifest=LEGACY_SELECTOR_MANIFEST_V2,
    )
    calls: list[int] = []
    selected_manifests: list[SelectorManifest] = []

    def adapters(
        _root: Path,
        manifest: SelectorManifest,
    ) -> tuple[_Analyzer, _Verifier]:
        selected_manifests.append(manifest)
        return _Analyzer(calls=calls), _Verifier()

    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        adapter_factory=adapters,
    )

    handler(_Context(job), job)  # type: ignore[arg-type]

    assert selected_manifests == [LEGACY_SELECTOR_MANIFEST_V2]
    assert calls == [0, 1]
    assert store.published is not None


def test_cancel_stops_at_the_next_bounded_checkpoint_and_keeps_sources(
    tmp_path: Path,
) -> None:
    manifest = SelectorManifest(scan_batch_size=2)
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=5,
        manifest=manifest,
    )
    calls: list[int] = []
    context = _Context(job, cancel_at_first_checkpoint=True)
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=manifest,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=calls),
            _Verifier(),
        ),
    )

    with pytest.raises(_CancelledAtCheckpoint):
        handler(context, job)  # type: ignore[arg-type]

    assert calls == [0, 1]
    selection_root = import_root / "browser-selections" / str(store.run.source_selection_id)
    assert len(tuple(selection_root.glob("*.jpg"))) == 5
    assert store.published is None


def test_retry_reconciles_projection_written_just_before_checkpoint(
    tmp_path: Path,
) -> None:
    manifest = SelectorManifest(scan_batch_size=2)
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=1,
        manifest=manifest,
    )
    first_calls: list[int] = []
    crashing_context = _Context(job, cancel_at_first_checkpoint=True)
    crashing_handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=manifest,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=first_calls),
            _Verifier(),
        ),
    )

    with pytest.raises(_CancelledAtCheckpoint):
        crashing_handler(crashing_context, job)  # type: ignore[arg-type]

    assert first_calls == [0]
    assert len(store.groups) == 1
    assert job.checkpoint_payload is None

    resumed_calls: list[int] = []
    resumed_context = _Context(job)
    resumed_handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=manifest,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=resumed_calls),
            _Verifier(),
        ),
    )

    resumed_handler(resumed_context, job)  # type: ignore[arg-type]

    assert resumed_calls == [0]
    assert len(store.groups) == 1
    assert store.published is not None


def test_manual_completion_resumes_without_progress_regression(
    tmp_path: Path,
) -> None:
    manifest = SelectorManifest(scan_batch_size=2)
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=1,
        manifest=manifest,
    )
    first_context = _ReviewContext(job)
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=manifest,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=[]),
            _ManualVerifier(),
        ),
    )

    with pytest.raises(_WaitingForReview):
        handler(first_context, job)  # type: ignore[arg-type]

    pending = store.groups[0]
    selected = replace(
        pending.top_candidates[0],
        decision=CandidateDecision.SELECTED_MANUAL,
        recognized_range=SequenceRange(1, 9, 1.0),
    )
    store.groups = (
        replace(
            pending,
            range=SequenceRange(1, 9, 1.0),
            status=SelectionGroupStatus.MANUALLY_SELECTED,
            selected_candidate=selected,
            top_candidates=(selected,),
        ),
    )
    resumed_job = replace(
        first_context.job,
        status=JobStatus.PROCESSING,
        lease_token=uuid4(),
        lease_expires_at=NOW + timedelta(minutes=1),
    )
    resumed_context = _Context(resumed_job)

    handler(resumed_context, resumed_job)  # type: ignore[arg-type]

    assert store.published is not None
    final = resumed_context.checkpoints[-1]
    payload = final["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["manual_count"] == 0
    assert final["review_count"] == 1


def test_stale_lease_is_fenced_before_selector_projection_write() -> None:
    expected_token = uuid4()
    stale_token = uuid4()
    record = SimpleNamespace(
        status=JobStatus.PROCESSING,
        lease_token=expected_token,
        lease_expires_at=NOW + timedelta(minutes=1),
    )
    session = SimpleNamespace(scalar=lambda _statement: record)

    with pytest.raises(JobConflictError) as error:
        _assert_fence(session, uuid4(), stale_token, NOW)  # type: ignore[arg-type]

    assert error.value.code == "JOB_LEASE_LOST"
