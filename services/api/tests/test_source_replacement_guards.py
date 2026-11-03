"""Replacement restrictions precede legacy ownership without changing its fallback."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from game_predictor_api.domain.sequence_takeover import (
    ImportOrder,
    ReplacementClaimBinding,
    SequenceClaimOutcome,
    SequenceReservation,
    decide_sequence_claim,
)
from game_predictor_api.domain.source_crop_eligibility import CropExclusion, classify_blob
from test_source_crop_eligibility import SHA, _facts, _quads


@pytest.mark.parametrize("canonical", [False, True])
@pytest.mark.parametrize(
    "field", ["game_id", "batch_id", "entry_id", "source_id", "source_sha256", "review_id"]
)
def test_reservation_rejects_every_foreign_binding_before_canonical(canonical, field):
    binding = ReplacementClaimBinding("game", "batch", "entry", "source", "a" * 64, "review")
    slot = SequenceReservation("game", "batch", "entry", "source", "a" * 64, "review")
    result = decide_sequence_claim(
        canonical_exists=canonical,
        incumbent=None,
        incoming_source_checksum_sha256="a" * 64,
        incoming_order=ImportOrder(datetime.now(UTC), "job"),
        reservation=slot,
        replacement_binding=replace(binding, **{field: "foreign"}),
    )
    assert result.outcome is SequenceClaimOutcome.KEEP_RESERVED
    assert not result.incoming_owns


@pytest.mark.parametrize("provisional", [False, True])
def test_exact_proof_can_prepare_review_before_fk_binding(provisional):
    binding = ReplacementClaimBinding("game", "batch", "entry", "source", "a" * 64, "review")
    slot = SequenceReservation(
        "game",
        "batch",
        "entry",
        "source",
        "a" * 64,
        None if provisional else "review",
        "review" if provisional else None,
    )
    result = decide_sequence_claim(
        canonical_exists=True,
        incumbent=None,
        incoming_source_checksum_sha256="a" * 64,
        incoming_order=ImportOrder(datetime.now(UTC), "job"),
        reservation=slot,
        replacement_binding=binding,
    )
    assert result.outcome is SequenceClaimOutcome.CLAIM_RESERVED
    assert result.incoming_owns


def test_crop_reference_is_an_independent_retention_blocker():
    source = _facts(replacement_referenced=True)
    result = classify_blob(SHA, [source], _quads(source))
    assert not result.eligible
    assert CropExclusion.SOURCE_REPLACEMENT_REFERENCED in result.exclusions


@pytest.mark.parametrize("operation", ["delete_release", "reset_game", "delete_board_sources"])
def test_cleanup_preview_and_execute_refuse_before_files_or_rows(operation):
    from game_predictor_api.application.cleanup import CleanupService
    from game_predictor_api.domain.cleanup import (
        BoardSourceCleanupSelection,
        CleanupCommand,
        CleanupConflictError,
    )
    from test_cleanup_domain import FakeArtifacts, FakeCleanupRepository, _snapshot

    snapshot = _snapshot(blockers=("SOURCE_REPLACEMENT_REFERENCED",))
    repository, artifacts = FakeCleanupRepository(snapshot), FakeArtifacts()
    service = CleanupService(repository, artifacts)
    selection = BoardSourceCleanupSelection((1,))
    preview = (
        service.preview_board_sources(snapshot.target_id, selection)
        if operation == "delete_board_sources"
        else service.preview_game_reset(snapshot.target_id)
    )
    assert "SOURCE_REPLACEMENT_REFERENCED" in preview.snapshot.blockers
    command = CleanupCommand(preview.preview_token, snapshot.confirmation_target, True)
    args = (
        (snapshot.target_id, command)
        if operation != "delete_board_sources"
        else (snapshot.target_id, BoardSourceCleanupSelection((1,)), command)
    )
    with pytest.raises(CleanupConflictError) as blocked:
        getattr(service, operation)(*args)
    assert blocked.value.code == "SOURCE_REPLACEMENT_REFERENCED"
    assert not repository.deleted
    assert not artifacts.deleted and not artifacts.quarantined


def test_resume_rechecks_retired_cohort_without_rewriting_saved_job():
    from game_predictor_api.application.grid_training_runs import GridTrainingRunService
    from game_predictor_api.domain.grid_training_cohorts import GridCohortError
    from game_predictor_api.domain.jobs import JobStatus
    from test_grid_training_runs import GAME, Cohorts, Jobs, command

    cohorts, jobs = Cohorts(), Jobs()
    service = GridTrainingRunService(cohorts, jobs)
    result = service.create(GAME, command())
    job_id = next(iter(jobs.rows))
    original = replace(jobs.rows[job_id], status=JobStatus.FAILED)
    jobs.rows[job_id] = original
    cohorts.blockers = ["SOURCE_REPLACEMENT_RETIRED"]
    with pytest.raises(GridCohortError) as blocked:
        service.resume(GAME, job_id)
    assert blocked.value.code == "SOURCE_REPLACEMENT_RETIRED"
    assert jobs.rows[job_id] is original
    assert service.get(GAME, job_id)["runId"] == result["runId"]


@pytest.mark.parametrize(
    "relative",
    [
        "data/models/inactive/model.onnx",
        "data/symbol-readability/models/frozen/model.json",
        "data/datasets/history/dataset.json",
    ],
)
def test_gc_model_and_dataset_artifacts_are_outside_deletable_namespaces(tmp_path, relative):
    from game_predictor_api.application.storage_gc import StorageGcArtifactStore
    from game_predictor_api.domain.storage_retention import StorageRetentionPolicy
    from game_predictor_worker.jobs.runtime import JobHandlerError
    from game_predictor_worker.storage_gc import _validate_managed_candidate_path
    from test_storage_gc import GcSourceRepository

    path = tmp_path / "artifacts" / relative
    path.parent.mkdir(parents=True)
    path.write_bytes(b"retained historical artifact")
    imports = tmp_path / "imports"
    imports.mkdir()
    scan = StorageGcArtifactStore(tmp_path / "artifacts", imports).scan(
        GcSourceRepository(), policy=StorageRetentionPolicy(), now=datetime.now(UTC)
    )
    assert not scan.entries
    for kind in ("temporary_file", "normalization_working_bitmap", "grid_cohort_asset"):
        with pytest.raises(JobHandlerError):
            _validate_managed_candidate_path(
                root_kind="artifact", artifact_class=kind, relative_path=relative
            )
    assert path.read_bytes() == b"retained historical artifact"
