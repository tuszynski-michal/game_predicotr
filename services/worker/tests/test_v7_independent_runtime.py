from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace

import pytest
from game_predictor_worker.semi_automatic_selection.v7_observation_codec import (
    advance_observation_digest,
    deserialize_scan_observation,
    serialize_scan_observation,
)
from game_predictor_worker.semi_automatic_selection.v7_quality import V7CropEdge
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)
from game_predictor_worker.semi_automatic_selection.v7_review_projection import (
    build_review_projections,
    source_diagnostics,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7RunStateError,
    V7RunStatePhase,
    V7ScanObservation,
    V7ScanRunState,
)
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7CheckpointPolicy,
    V7WorkerRuntime,
    V7WorkerRuntimeError,
)
from test_v7_checkpoint_batching import ProofObserver, manifest_with_sources
from test_v7_worker_runtime import _configuration, _Factory, _SourceErrorObserver
from v7_run_state_support import quality as _quality


def test_independent_flush_never_builds_full_state_before_finalized(tmp_path, monkeypatch):
    manifest = manifest_with_sources(tmp_path, 7)
    baseline = V7WorkerRuntime(_Factory((ProofObserver(manifest),))).run(
        manifest=manifest, configuration=_configuration(), checkpoint={}, persist=lambda _: None
    )
    original = V7ScanRunState.checkpoint
    calls = []

    def only_finalized(state):
        assert state.phase is V7RunStatePhase.FINALIZED
        calls.append(state.phase)
        return original(state)

    monkeypatch.setattr(V7ScanRunState, "checkpoint", only_finalized)
    progress = []
    runtime = V7WorkerRuntime(
        _Factory((ProofObserver(manifest),)),
        checkpoint_policy=V7CheckpointPolicy(max_sources=2),
        independent_progress=True,
        clock=lambda: 0.0,
    )
    result = runtime.run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=progress.append,
        resume_reference={
            "fixture": "base",
            "checksumSha256": "a" * 64,
            "observationsDigest": "a" * 64,
        },
    )
    assert runtime.independent_progress
    assert calls == [V7RunStatePhase.FINALIZED]
    assert result == baseline
    assert build_review_projections(result.checkpoint["scanState"], result.finalization) == (
        build_review_projections(baseline.checkpoint["scanState"], baseline.finalization)
    )
    assert [p.source_indexes for p in progress] == [(0, 1), (2, 3), (4, 5), (6,), ()]
    diagnostics = {}
    digest = "a" * 64
    for item in progress:
        for observation in item.observations:
            digest = advance_observation_digest(digest, observation)
        assert tuple(o.source_index for o in item.observations) == item.source_indexes
        assert len(item.diagnostic_scan_state["sourceDiagnostics"]) == len(item.source_indexes)
        diagnostics.update(
            source_diagnostics(
                item.diagnostic_scan_state,
                source_indexes=item.source_indexes,
                pinned_manifest=item.pinned_manifest,
            )
        )
        if item.phase is not V7RunStatePhase.FINALIZED:
            assert item.checkpoint["resumeBase"]["observationsDigest"] == digest
            assert item.checkpoint["runtimeVersion"] == "v7-worker-runtime-v3"
            assert "sources" not in item.checkpoint["scanState"]["sourceManifest"]
            assert len(json.dumps(item.checkpoint)) < 1500
    assert diagnostics == source_diagnostics(baseline.checkpoint["scanState"])


def test_diagnostic_delta_does_not_iterate_prior_results(tmp_path):
    manifest = manifest_with_sources(tmp_path, 5)
    observer = ProofObserver(manifest)
    state = observer.state
    for source in state.source_manifest.sources:
        from types import SimpleNamespace

        state.consume(observer.observe(SimpleNamespace(source=source)))

    class LookupOnly(dict):
        def __iter__(self):
            raise AssertionError("Previous results were traversed")

        def items(self):
            raise AssertionError("Previous results were traversed")

        def values(self):
            raise AssertionError("Previous results were traversed")

        def keys(self):
            raise AssertionError("Previous results were traversed")

        def __getitem__(self, index):
            assert index == 4
            return super().__getitem__(index)

    state._qualities = LookupOnly(state._qualities)
    state._diagnostics = LookupOnly(state._diagnostics)
    state._source_errors = LookupOnly(state._source_errors)
    delta = state.diagnostic_checkpoint((4,))
    assert [row["sourceIndex"] for row in delta["frameQualities"]] == [4]


def weak_observation(state, index, *, second=False):
    labels = tuple(V7LabelEvidence(i, i + 1, 0.99, 0.99) for i in range(3))
    quality = _quality(state, index)
    quality = replace(
        quality,
        boards=(
            replace(quality.boards[0], cropped_edges=frozenset({V7CropEdge.TOP})),
            *quality.boards[1:],
        ),
    )
    return V7ScanObservation(
        source_index=index,
        proof=V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("WEAK",)),
        quality=quality,
        weak_evidence=V7WeakFrameEvidence(
            state.source_manifest.sources[index].source_id,
            labels,
            2**64 - 1 if second else 0,
            bytes([7 if second else 0] * 64),
        ),
        labels=labels,
        observed_position_indices=(0, 1, 2, 4),
    )


def test_lossless_weak_replay_across_checkpoint_retains_quality_and_pair(tmp_path):
    manifest = manifest_with_sources(tmp_path, 2)
    config = _configuration()
    state = V7ScanRunState(
        manifest, expected_ranges=config.expected_ranges, border_style=config.border_style
    )
    observations = (weak_observation(state, 0), weak_observation(state, 1, second=True))
    first, second = (
        deserialize_scan_observation(json.loads(json.dumps(serialize_scan_observation(o))))
        for o in observations
    )
    assert (first, second) == observations
    state.consume(first)
    restored = V7ScanRunState(
        manifest,
        expected_ranges=config.expected_ranges,
        border_style=config.border_style,
        checkpoint=state.checkpoint(),
    )
    state.consume(second)
    restored.consume(second)
    state.complete_scan()
    restored.complete_scan()
    assert state.finalize(manifest) == restored.finalize(manifest)
    assert state.checkpoint() == restored.checkpoint()
    assert state.finalization.selections[0].proof_kinds == (
        V7RangeProofKind.MULTI_FRAME_THREE_PLUS_THREE,
    )


@pytest.mark.parametrize(
    "mutation", ["missing_weak", "wrong_version", "bad_signature", "bool_index"]
)
def test_codec_rejects_corrupt_payload(tmp_path, mutation):
    manifest = manifest_with_sources(tmp_path, 1)
    observation = weak_observation(ProofObserver(manifest).state, 0)
    raw = deepcopy(serialize_scan_observation(observation))
    if mutation == "missing_weak":
        del raw["weakEvidence"]
    elif mutation == "wrong_version":
        raw["version"] = "unknown"
    elif mutation == "bad_signature":
        raw["weakEvidence"]["visualSignature"] = "00"
    else:
        raw["sourceIndex"] = False
    with pytest.raises(V7RunStateError, match="resume observation"):
        deserialize_scan_observation(raw)


def test_independent_mode_requires_explicit_policy_and_base(tmp_path):
    with pytest.raises(ValueError, match="bounded checkpoint"):
        V7WorkerRuntime(independent_progress=True)
    runtime = V7WorkerRuntime(independent_progress=True, checkpoint_policy=V7CheckpointPolicy())
    with pytest.raises(V7WorkerRuntimeError, match="resume base"):
        runtime.run(
            manifest=manifest_with_sources(tmp_path, 1),
            configuration=_configuration(),
            checkpoint={},
            persist=lambda _: None,
        )


def test_source_errors_replay_and_progress_count_survive_independent_batches(tmp_path):
    manifest = manifest_with_sources(tmp_path, 3)
    progress = []
    result = V7WorkerRuntime(
        _Factory((_SourceErrorObserver(),)),
        checkpoint_policy=V7CheckpointPolicy(max_sources=2),
        independent_progress=True,
        clock=lambda: 0.0,
    ).run(
        manifest=manifest,
        configuration=_configuration(),
        checkpoint={},
        persist=progress.append,
        resume_reference={
            "fixture": "base",
            "checksumSha256": "a" * 64,
            "observationsDigest": "a" * 64,
        },
    )
    assert [item.source_error_count for item in progress] == [2, 3, 3]
    for item in progress:
        for observation in item.observations:
            assert (
                deserialize_scan_observation(serialize_scan_observation(observation)) == observation
            )
    assert len(result.checkpoint["scanState"]["sourceErrors"]) == 3
