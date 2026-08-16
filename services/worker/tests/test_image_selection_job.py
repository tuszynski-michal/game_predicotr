from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.image_selections import ImageSelectionExecutionMode
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobExecutionSlot,
    JobStatus,
    JobType,
    create_job,
    start_job,
)
from game_predictor_worker.images.selection.adapters import (
    DeterministicParallelCandidateVerifier,
    FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer,
    TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
)
from game_predictor_worker.images.selection.contracts import (
    CandidateDecision,
    CandidateResult,
    CandidateVerification,
    CheapImageObservation,
    ImageQualityMetrics,
    ImageSelectionSource,
    RangeEvidence,
    RepresentativeAssessment,
    SelectionGroupResult,
    SelectionGroupStatus,
    SequenceRange,
)
from game_predictor_worker.images.selection.io import load_browser_selection_manifest
from game_predictor_worker.images.selection.job import (
    ImageSelectionJobHandler,
    ImageSelectionJobRun,
    _assert_fence,
    _upsert_candidate,
)
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
    DEFAULT_SELECTOR_MANIFEST,
    FUSED_RANGE_EVIDENCE_SELECTOR_MANIFEST_V1011,
    LEGACY_SELECTOR_MANIFEST_V2,
    QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
    SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
    STAGED_OCR_SELECTOR_MANIFEST_V1016,
    TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
    SelectorManifest,
)
from game_predictor_worker.images.selection.output import PublishedImageSelection
from game_predictor_worker.images.selection.recovery import (
    RecoveryProjection,
    RecoverySourceGroup,
)
from game_predictor_worker.images.selection.telemetry import StageTimingCollector
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image

NOW = datetime(2026, 8, 3, 10, tzinfo=UTC)


def _persistence_candidate(order_index: int = 7) -> CandidateResult:
    source = ImageSelectionSource(
        order_index=order_index,
        relative_path=f"source/{order_index}.jpg",
        stored_relative_path=f"{order_index:08d}.jpg",
        checksum_sha256=hashlib.sha256(f"candidate:{order_index}".encode()).hexdigest(),
        size_bytes=1024,
    )
    return CandidateResult(
        source=source,
        decision=CandidateDecision.ELIGIBLE,
        quality=ImageQualityMetrics(*(0.9 for _ in range(8))),
        recognized_range=SequenceRange(280, 288, 0.99),
        reason_codes=(),
        width=1080,
        height=1920,
    )


def _persistence_group(candidate: CandidateResult) -> SelectionGroupResult:
    return SelectionGroupResult(
        group_order=3,
        source_count=2,
        range=candidate.recognized_range,
        fingerprint_sha256="0" * 64,
        board_count_consensus=9,
        status=SelectionGroupStatus.AUTO_SELECTED,
        selected_candidate=candidate,
        top_candidates=(candidate,),
    )


def test_full_candidate_promotes_same_gallery_source_to_authoritative_group() -> None:
    candidate = _persistence_candidate()
    group = _persistence_group(candidate)
    final_group_id = uuid4()
    record = SimpleNamespace(
        group_id=uuid4(),
        checksum_sha256=candidate.source.checksum_sha256,
        quality_metrics={"manualGalleryOnly": True},
    )
    session = SimpleNamespace(scalar=lambda _query: record)

    _upsert_candidate(
        session,  # type: ignore[arg-type]
        run_id=uuid4(),
        group_id=final_group_id,
        group=group,
        candidate=candidate,
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        persisted_at=NOW,
    )

    assert record.group_id == final_group_id
    assert record.quality_metrics.get("manualGalleryOnly") is None
    assert record.decision.value == CandidateDecision.SELECTED_AUTOMATIC.value


@pytest.mark.parametrize("gallery_only", (False, True))
def test_full_candidate_keeps_real_persistence_conflicts(
    gallery_only: bool,
) -> None:
    candidate = _persistence_candidate()
    group = _persistence_group(candidate)
    record = SimpleNamespace(
        group_id=uuid4(),
        checksum_sha256=(candidate.source.checksum_sha256 if not gallery_only else "f" * 64),
        quality_metrics={"manualGalleryOnly": gallery_only},
    )
    session = SimpleNamespace(scalar=lambda _query: record)

    with pytest.raises(JobHandlerError) as raised:
        _upsert_candidate(
            session,  # type: ignore[arg-type]
            run_id=uuid4(),
            group_id=uuid4(),
            group=group,
            candidate=candidate,
            decision=CandidateDecision.SELECTED_AUTOMATIC,
            persisted_at=NOW,
        )

    assert raised.value.code == "IMAGE_SELECTION_PERSISTENCE_CONFLICT"


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


@pytest.mark.parametrize(
    ("selector_manifest", "recognizer_type"),
    (
        (
            FUSED_RANGE_EVIDENCE_SELECTOR_MANIFEST_V1011,
            FusedRangeEvidenceVisibleSequenceLabelRangeRecognizer,
        ),
        (
            TWO_LABEL_CONSENSUS_SELECTOR_MANIFEST_V1012,
            TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
        ),
        (
            STAGED_OCR_SELECTOR_MANIFEST_V1016,
            TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
        ),
        (
            QUANTILE_SAMPLED_SELECTOR_MANIFEST_V1017,
            TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
        ),
        (
            SINGLE_FRAME_EARLY_EXIT_SELECTOR_MANIFEST_V1018,
            TwoLabelConsensusVisibleSequenceLabelRangeRecognizer,
        ),
    ),
)
def test_production_factory_preserves_historical_and_builds_staged_ocr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    selector_manifest: SelectorManifest,
    recognizer_type: type[object],
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir()
    predictors: list[object] = []
    built_verifiers: list[object] = []
    fallback_recognizers: list[object] = []
    fast_recognizers: list[object | None] = []

    def build_predictor(*_args: object, **_kwargs: object) -> object:
        predictor = object()
        predictors.append(predictor)
        return predictor

    class _FactoryVerifier:
        def verify(
            self,
            observation: CheapImageObservation,
            *,
            expected_board_count: int | None,
        ) -> CandidateVerification:
            del observation, expected_board_count
            return CandidateVerification(
                representative=RepresentativeAssessment(9, True, True),
                range_evidence=RangeEvidence(None),
            )

    def build_adapters(*_args: object, **kwargs: object) -> tuple[object, _FactoryVerifier]:
        verifier = _FactoryVerifier()
        built_verifiers.append(verifier)
        fallback_recognizers.append(kwargs["fallback_range_recognizer"])
        fast_recognizers.append(kwargs.get("fast_range_recognizer"))
        return object(), verifier

    monkeypatch.setattr(
        "game_predictor_worker.images.selection.job.PaddleSequenceNumberRecognizer",
        build_predictor,
    )
    monkeypatch.setattr(
        "game_predictor_worker.images.selection.job.build_default_adapters",
        build_adapters,
    )
    handler = ImageSelectionJobHandler(
        SimpleNamespace(),  # type: ignore[arg-type]
        browser_upload_root=tmp_path,
        artifact_root=tmp_path,
        repository_root=tmp_path,
        selector_manifest=selector_manifest,
        verification_workers=2,
    )

    _, verifier = handler._default_adapter_factory(  # noqa: SLF001
        source_root,
        selector_manifest,
        StageTimingCollector(),
    )

    assert len(predictors) == 2
    assert len({id(predictor) for predictor in predictors}) == 2
    assert len({id(item) for item in built_verifiers}) == 2
    assert all(isinstance(item, recognizer_type) for item in fallback_recognizers)
    if selector_manifest is STAGED_OCR_SELECTOR_MANIFEST_V1016:
        assert all(
            isinstance(item, TwoLabelConsensusVisibleSequenceLabelRangeRecognizer)
            for item in fast_recognizers
        )
    else:
        assert fast_recognizers == [None, None]
    assert isinstance(verifier, DeterministicParallelCandidateVerifier)
    assert verifier.worker_count == 2


@dataclass
class _Store:
    run: ImageSelectionJobRun
    groups: tuple[SelectionGroupResult, ...] = ()
    published: PublishedImageSelection | None = None
    gallery_sources: dict[int, tuple[CheapImageObservation, ...]] = field(default_factory=dict)
    recovery_source_run_id: UUID | None = None
    recovery_snapshot: str | None = None
    recovery_source_groups: tuple[RecoverySourceGroup, ...] = ()
    recovery_origins: dict[int, UUID] = field(default_factory=dict)
    reconciled_persist_count: int = 0

    def get_run_for_job(self, job_id: UUID) -> ImageSelectionJobRun:
        assert job_id == self.run.job_id
        return self.run

    def load_groups(self, run_id: UUID) -> tuple[SelectionGroupResult, ...]:
        assert run_id == self.run.id
        return self.groups

    def load_recovery_source(
        self,
        run_id: UUID,
    ) -> tuple[str, tuple[RecoverySourceGroup, ...]]:
        assert run_id == self.recovery_source_run_id
        assert self.recovery_snapshot is not None
        return self.recovery_snapshot, self.recovery_source_groups

    def persist_groups(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        groups: tuple[SelectionGroupResult, ...],
        group_sources: Mapping[int, Sequence[CheapImageObservation]],
        persisted_at: datetime,
    ) -> None:
        del lease_token, persisted_at
        assert (job_id, run_id) == (self.run.job_id, self.run.id)
        values = {group.group_order: group for group in self.groups}
        values.update({group.group_order: group for group in groups})
        self.groups = tuple(values[index] for index in sorted(values))
        self.gallery_sources.update(
            {group_order: tuple(sources) for group_order, sources in group_sources.items()}
        )

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

    def persist_reconciled_groups(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        lease_token: UUID,
        groups: Sequence[SelectionGroupResult],
        persisted_at: datetime,
    ) -> None:
        del lease_token, persisted_at
        assert (job_id, run_id) == (self.run.job_id, self.run.id)
        self.groups = tuple(groups)
        self.reconciled_persist_count += 1

    def persist_recovery_projection(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        source_run_id: UUID,
        expected_source_snapshot_sha256: str,
        lease_token: UUID,
        projection: RecoveryProjection,
        persisted_at: datetime,
    ) -> None:
        del lease_token, persisted_at
        assert (job_id, run_id) == (self.run.job_id, self.run.id)
        assert source_run_id == self.recovery_source_run_id
        assert expected_source_snapshot_sha256 == self.recovery_snapshot
        self.groups = projection.groups
        self.gallery_sources = dict(projection.group_sources)
        self.recovery_origins = dict(projection.origin_group_ids)


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
        assert int(values["current"]) >= self.job.progress_current
        assert int(values["success_count"]) >= self.job.success_count
        assert int(values["failure_count"]) >= self.job.failure_count
        assert int(values["review_count"]) >= self.job.review_count
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
            appearance_signature=(() if corrupted else (0.2, 0.4, 0.6)),
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
            representative=RepresentativeAssessment(
                expected_board_count,
                True,
                True,
            ),
            range_evidence=RangeEvidence(SequenceRange(1, 9, 0.98)),
        )


class _PartitionVerifier:
    def __init__(self, *, sources_per_group: int) -> None:
        self._sources_per_group = sources_per_group

    def verify(
        self,
        observation: CheapImageObservation,
        *,
        expected_board_count: int | None,
    ) -> CandidateVerification:
        group_index = observation.source.order_index // self._sources_per_group
        start = 1 + group_index * 9
        return CandidateVerification(
            representative=RepresentativeAssessment(
                expected_board_count,
                True,
                True,
            ),
            range_evidence=RangeEvidence(SequenceRange(start, start + 8, 0.98)),
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
            representative=RepresentativeAssessment(None, False, False),
            range_evidence=RangeEvidence(
                None,
                ("RANGE_ANCHOR_UNREADABLE",),
            ),
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
        Image.new("RGB", (64, 48), (20 + index * 20, 40, 80)).save(
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
        execution_slot=JobExecutionSlot.IMAGE_SELECTION,
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


def test_range_recovery_rebuilds_only_preserved_candidates_into_derived_run(
    tmp_path: Path,
) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=3,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    source_run_id = uuid4()
    snapshot = "f" * 64
    source_root = import_root / "browser-selections" / str(store.run.source_selection_id)
    sources, _ = load_browser_selection_manifest(source_root / "_browser_manifest.json")
    selected = CandidateResult(
        source=sources[1],
        decision=CandidateDecision.SELECTED_AUTOMATIC,
        quality=ImageQualityMetrics(*(0.95 for _ in range(8))),
        recognized_range=None,
        reason_codes=("REPRESENTATIVE_RANGE_UNKNOWN",),
        width=64,
        height=48,
    )
    source_group = RecoverySourceGroup(
        origin_group_id=uuid4(),
        result=SelectionGroupResult(
            group_order=0,
            source_count=3,
            range=None,
            fingerprint_sha256="0" * 64,
            board_count_consensus=9,
            status=SelectionGroupStatus.RANGE_REQUIRED,
            selected_candidate=selected,
            top_candidates=(selected,),
        ),
        sources=sources,
    )
    store.run = replace(
        store.run,
        first_sequence_number=1,
        execution_mode=ImageSelectionExecutionMode.RANGE_RECOVERY,
        source_run_id=source_run_id,
        source_snapshot_sha256=snapshot,
    )
    store.recovery_source_run_id = source_run_id
    store.recovery_snapshot = snapshot
    store.recovery_source_groups = (source_group,)
    calls: list[int] = []
    context = _Context(job)
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=calls),
            _Verifier(),
        ),
    )

    handler(context, job)  # type: ignore[arg-type]

    assert calls == [0, 1, 2]
    assert store.recovery_source_groups == (source_group,)
    assert set(store.recovery_origins.values()) == {source_group.origin_group_id}
    selected_groups = [
        group for group in store.groups if group.status is SelectionGroupStatus.AUTO_SELECTED
    ]
    assert len(selected_groups) == 1
    assert selected_groups[0].range == SequenceRange(1, 9, 0.98)
    selected_orders = [
        group.selected_candidate.source.order_index
        for group in store.groups
        if group.selected_candidate is not None
    ]
    assert len(selected_orders) == len(set(selected_orders))
    assert store.published is not None
    assert any(
        checkpoint["checkpoint_payload"]["recovery_projection_complete"] is True
        for checkpoint in context.checkpoints
    )


def test_v10_4_job_fails_closed_without_first_sequence_number(tmp_path: Path) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=1,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (_Analyzer(), _Verifier()),
    )

    with pytest.raises(JobHandlerError) as raised:
        handler(_Context(job), job)  # type: ignore[arg-type]

    assert raised.value.code == "IMAGE_SELECTION_FIRST_SEQUENCE_REQUIRED"


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
    assert sorted(
        observation.source.order_index
        for sources in store.gallery_sources.values()
        for observation in sources
    ) == [0, 1, 2]
    assert store.published is not None
    final = context.checkpoints[-1]
    payload = final["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["error_count"] == 1
    assert payload["upload_duration_seconds"] == 12.5
    assert float(payload["processing_duration_seconds"]) > 0
    recent_window = payload["recent_window"]
    assert isinstance(recent_window, dict)
    assert recent_window["toProcessed"] == 3
    assert recent_window["fromProcessed"] in {0, 2}
    assert recent_window["elapsedSeconds"] >= 0
    assert recent_window["verifications"] >= 0
    stage_timing = payload["stage_timing"]
    assert isinstance(stage_timing, dict)
    assert stage_timing["stages"]["output"]["count"] == 1
    assert stage_timing["stages"]["persistence"]["count"] >= 1
    assert stage_timing["counters"]["persistenceWrites"] >= 1
    scan_cache = payload["scan_cache"]
    assert isinstance(scan_cache, dict)
    assert scan_cache["hitCount"] == 0
    assert scan_cache["missCount"] == 3
    assert scan_cache["writeCount"] == 3
    diagnostic = payload["diagnostic"]
    assert isinstance(diagnostic, dict)
    path = artifact_root / str(diagnostic["relativePath"])
    diagnostic_content = path.read_bytes()
    assert len(diagnostic_content) < 16 * 1024
    assert hashlib.sha256(diagnostic_content).hexdigest() == diagnostic["checksumSha256"]
    assert str(tmp_path).encode() not in diagnostic_content
    assert b"photo2.jpg" not in diagnostic_content


def test_job_enforces_declared_sequence_group_count_before_publication(
    tmp_path: Path,
) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=3,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    store.run = replace(
        store.run,
        first_sequence_number=1,
        last_sequence_number=9,
    )
    calls: list[int] = []
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=calls),
            _Verifier(),
        ),
    )

    handler(_Context(job), job)  # type: ignore[arg-type]

    logical_groups = tuple(
        group
        for group in store.groups
        if group.status is not SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    )
    assert calls == [0, 1, 2]
    assert len(logical_groups) == 1
    assert logical_groups[0].range == SequenceRange(1, 9, 1.0)
    assert store.reconciled_persist_count == 1
    assert store.published is not None


def test_job_partitions_false_merge_before_cardinality_reconciliation(
    tmp_path: Path,
) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=9,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    store.run = replace(
        store.run,
        first_sequence_number=1,
        last_sequence_number=27,
    )
    calls: list[int] = []
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=calls),
            _PartitionVerifier(sources_per_group=3),
        ),
    )

    handler(_Context(job), job)  # type: ignore[arg-type]

    logical_groups = tuple(
        group
        for group in store.groups
        if group.status is not SelectionGroupStatus.SKIPPED_EXISTING_RANGE
    )
    assert calls == list(range(9))
    assert len(logical_groups) == 3
    assert all(group.source_count >= 1 for group in logical_groups)
    assert [
        None if group.range is None else (group.range.start, group.range.end)
        for group in logical_groups
    ] == [(1, 9), (10, 18), (19, 27)]
    assert store.reconciled_persist_count == 1
    assert store.published is not None


def test_job_fails_closed_when_declared_groups_outnumber_sources(tmp_path: Path) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=2,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    store.run = replace(
        store.run,
        first_sequence_number=1,
        last_sequence_number=27,
    )
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (_Analyzer(), _Verifier()),
    )

    with pytest.raises(JobHandlerError) as raised:
        handler(_Context(job), job)  # type: ignore[arg-type]

    assert raised.value.code == "IMAGE_SELECTION_SOURCE_CARDINALITY_UNDERFLOW"
    assert store.reconciled_persist_count == 0
    assert store.published is None


def test_reconciled_projection_keeps_generic_job_counters_monotonic(
    tmp_path: Path,
) -> None:
    import_root, artifact_root, job, store = _fixture(
        tmp_path,
        file_count=3,
        manifest=DEFAULT_SELECTOR_MANIFEST,
    )
    store.run = replace(
        store.run,
        first_sequence_number=1,
        last_sequence_number=9,
    )
    resumed_job = replace(
        job,
        progress_current=3,
        progress_total=3,
        success_count=2,
        review_count=1,
    )
    context = _Context(resumed_job)
    handler = ImageSelectionJobHandler(
        store,
        browser_upload_root=import_root,
        artifact_root=artifact_root,
        repository_root=tmp_path,
        selector_manifest=DEFAULT_SELECTOR_MANIFEST,
        adapter_factory=lambda _root, _manifest: (
            _Analyzer(calls=[]),
            _Verifier(),
        ),
    )

    handler(context, resumed_job)  # type: ignore[arg-type]

    final = context.checkpoints[-1]
    payload = final["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["selected_count"] == 1
    assert payload["manual_count"] == 0
    assert final["success_count"] == 2
    assert final["review_count"] == 1


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

    assert resumed_calls == []
    assert len(store.groups) == 1
    assert store.published is not None
    resumed_payload = resumed_context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(resumed_payload, dict)
    resumed_cache = resumed_payload["scan_cache"]
    assert isinstance(resumed_cache, dict)
    assert resumed_cache["hitCount"] == 1
    assert resumed_cache["missCount"] == 0


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
