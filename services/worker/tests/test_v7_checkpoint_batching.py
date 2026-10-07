from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_worker.semi_automatic_selection.job import _v7_job_checkpoint
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
)
from game_predictor_worker.semi_automatic_selection.v7_review_projection import (
    build_review_projections,
    source_diagnostics,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7ScanObservation,
    V7ScanRunState,
)
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7CheckpointPolicy,
    V7WorkerRuntime,
    V7WorkerRuntimeError,
)
from test_v7_run_state import _quality
from test_v7_worker_runtime import _configuration, _Factory, _jpeg_bytes, _SourceErrorObserver


def manifest_with_sources(tmp_path, count=5):
    root = tmp_path / "sources"
    root.mkdir()
    for index in range(count):
        (root / f"{index}.jpg").write_bytes(_jpeg_bytes(index))
    return build_local_source_manifest(root, selection_id=uuid4(), display_name="fixture")


class ProofObserver(_SourceErrorObserver):
    def __init__(self, manifest):
        super().__init__()
        configuration = _configuration()
        self.state = V7ScanRunState(
            manifest,
            expected_ranges=configuration.expected_ranges,
            border_style=configuration.border_style,
        )

    def observe(self, request):
        self.observed_indexes.append(request.source.source_index)
        return V7ScanObservation(
            request.source.source_index,
            V7RangeProofResult(
                V7RangeProofKind.STRONG_FIVE_LABEL,
                _configuration().expected_ranges[0],
                (request.source.source_id,),
                (),
            ),
            _quality(self.state, request.source.source_index),
            labels=tuple(V7LabelEvidence(i, i + 1, 0.99, 0.99) for i in range(9)),
            observed_position_indices=tuple(range(9)),
        )


def test_batching_preserves_final_checkpoint_diagnostics_proof_and_selection(tmp_path):
    manifest = manifest_with_sources(tmp_path)
    legacy_progress, batch_progress = [], []
    legacy = V7WorkerRuntime(_Factory((ProofObserver(manifest),))).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=legacy_progress.append,
    )
    batched = V7WorkerRuntime(
        _Factory((ProofObserver(manifest),)),
        checkpoint_policy=V7CheckpointPolicy(max_sources=2),
        clock=lambda: 0.0,
    ).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=batch_progress.append,
    )
    assert legacy.checkpoint == batched.checkpoint
    assert legacy.finalization == batched.finalization
    assert legacy.finalization.selections[0].source_index == 2
    assert build_review_projections(legacy.checkpoint["scanState"], legacy.finalization) == (
        build_review_projections(batched.checkpoint["scanState"], batched.finalization)
    )
    assert [p.processed_sources for p in legacy_progress] == [1, 2, 3, 4, 5, 5, 5]
    assert [p.source_indexes for p in batch_progress] == [(0, 1), (2, 3), (4,), ()]
    deltas = {}
    for progress in batch_progress:
        deltas.update(
            source_diagnostics(
                progress.checkpoint["scanState"],
                source_indexes=progress.source_indexes,
                pinned_manifest=progress.pinned_manifest,
            )
        )
    assert deltas == source_diagnostics(legacy.checkpoint["scanState"])


@pytest.mark.parametrize("committed", [False, True])
def test_process_loss_and_lost_response_resume_only_durable_prefix(tmp_path, committed):
    manifest = manifest_with_sources(tmp_path)
    durable = {}
    observed = _SourceErrorObserver()

    def persist(progress):
        nonlocal durable
        if committed:
            durable = progress.checkpoint
        raise RuntimeError("Process loss / response lost")

    with pytest.raises(RuntimeError):
        V7WorkerRuntime(
            _Factory((observed,)),
            checkpoint_policy=V7CheckpointPolicy(max_sources=2),
            clock=lambda: 0.0,
        ).run(manifest=manifest, configuration=_configuration(), checkpoint={}, persist=persist)
    resumed = _SourceErrorObserver()
    progress = []
    result = V7WorkerRuntime(
        _Factory((resumed,)),
        checkpoint_policy=V7CheckpointPolicy(max_sources=2),
        clock=lambda: 0.0,
    ).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint=durable,
        persist=progress.append,
    )
    assert observed.observed_indexes == [0, 1]
    assert resumed.observed_indexes == ([2, 3, 4] if committed else [0, 1, 2, 3, 4])
    assert result.checkpoint["scanState"]["tracker"]["cursors"]["nextSourceIndex"] == 5


def test_elapsed_time_flushes_before_source_count_limit(tmp_path):
    manifest = manifest_with_sources(tmp_path)
    elapsed = 0.0

    class TimedObserver(_SourceErrorObserver):
        def observe(self, request):
            nonlocal elapsed
            elapsed += 1.1
            return super().observe(request)

    progress = []
    V7WorkerRuntime(
        _Factory((TimedObserver(),)),
        checkpoint_policy=V7CheckpointPolicy(),
        clock=lambda: elapsed,
    ).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=progress.append,
    )
    assert [p.source_indexes for p in progress] == [(0, 1), (2, 3), (4,), ()]


def test_default_policy_flushes_at_sixteen_even_with_fast_observer(tmp_path):
    manifest = manifest_with_sources(tmp_path, count=17)
    progress = []
    V7WorkerRuntime(
        _Factory((_SourceErrorObserver(),)),
        checkpoint_policy=V7CheckpointPolicy(),
        clock=lambda: 0.0,
    ).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=progress.append,
    )
    assert [p.source_indexes for p in progress] == [tuple(range(16)), (16,), ()]


def test_drift_flushes_pending_prefix_then_blocks_fresh_resume(tmp_path):
    manifest = manifest_with_sources(tmp_path)

    class ChangingObserver(_SourceErrorObserver):
        def observe(self, request):
            if request.source.source_index == 1:
                (manifest.source_root / "2.jpg").write_bytes(b"changed")
            return super().observe(request)

    progress = []
    with pytest.raises(V7WorkerRuntimeError) as error:
        V7WorkerRuntime(
            _Factory((ChangingObserver(),)),
            checkpoint_policy=V7CheckpointPolicy(),
            clock=lambda: 0.0,
        ).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint={},
            persist=progress.append,
        )
    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"
    assert len(progress) == 1
    assert progress[0].source_indexes == (0, 1)
    assert progress[0].blocked_source_drift is True
    with pytest.raises(V7WorkerRuntimeError) as restart_error:
        V7WorkerRuntime(_Factory((_SourceErrorObserver(),))).run(
            manifest=manifest,
            configuration=_configuration(),
            checkpoint=progress[0].checkpoint,
            persist=lambda _progress: None,
        )
    assert restart_error.value.code == "V7_SOURCE_MANIFEST_DRIFT"


def test_job_checkpoint_is_a_small_reference_to_authoritative_run(tmp_path):
    manifest = manifest_with_sources(tmp_path)
    progress = []
    V7WorkerRuntime(_Factory((_SourceErrorObserver(),))).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=progress.append,
    )
    captured = []
    context = SimpleNamespace(checkpoint=lambda **kwargs: captured.append(kwargs))
    run = SimpleNamespace(
        id=uuid4(),
        counters={"missing": 1},
        source=SimpleNamespace(source_fingerprint=manifest.source_fingerprint),
    )
    _v7_job_checkpoint(context, run, progress[-1])
    payload = captured[0]["checkpoint_payload"]
    assert len(json.dumps(payload)) < 1500
    assert "scanState" not in payload["v7_semi_automatic_image_selection"]
    assert payload["v7_semi_automatic_image_selection"]["runId"] == str(run.id)
    assert captured[0]["current"] == 5


@pytest.mark.parametrize("kwargs", [{"max_sources": 17}, {"max_seconds": 3}, {"max_seconds": 0}])
def test_checkpoint_policy_cannot_weaken_recovery_bounds(kwargs):
    with pytest.raises(ValueError):
        V7CheckpointPolicy(**kwargs)
