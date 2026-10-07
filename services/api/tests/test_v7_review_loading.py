"""Public V7 run responses must not ship the full private scan to the viewer."""

from copy import deepcopy
from dataclasses import replace
from unittest.mock import MagicMock, Mock

import pytest
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionWorkflowMode,
)
from game_predictor_api.domain.v7_selection_delivery import V7DeliveryConflict, V7OutputDecision
from game_predictor_api.schemas.semi_automatic_image_selections import to_run_response
from game_predictor_api.storage.job_repository import job_record_from_domain
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
    _run_record,
)
from sqlalchemy.dialects import postgresql
from test_v7_selection_delivery_api import decision_body, delivery_fixture


@pytest.mark.parametrize("phase", ["scanning", "paused", "finalized"])
def test_v7_response_keeps_private_checkpoint_unchanged(tmp_path, phase):
    _, repository, _, run, _ = delivery_fixture(tmp_path)
    checkpoint = {
        "schemaVersion": "v7-api-checkpoint-v3" if phase == "scanning" else "v7-api-checkpoint-v2",
        "runtimeVersion": "runtime-v1",
        "calibrationFingerprint": "a" * 64,
        "scanState": {
            "schemaVersion": "v7-scan-v2",
            "phase": phase,
            "sourceManifest": {"sources": ["private-source.jpg"]},
            "observations": [{"private": "diagnostics"}],
            "tracker": {"occurrences": ["private-history"]},
        },
        "pilotSnapshot": {"private": "source-binding"},
        "resumeBase": {"relativePath": "private-recovery.json"},
    }
    original = deepcopy(checkpoint)
    run = replace(run, checkpoint=checkpoint)
    repository.runs[run.id] = run
    response = to_run_response(run)
    assert response.checkpoint == {
        "schemaVersion": checkpoint["schemaVersion"],
        "runtimeVersion": "runtime-v1",
        "calibrationFingerprint": "a" * 64,
        "scanState": {"schemaVersion": "v7-scan-v2", "phase": phase},
    }
    assert run.checkpoint == original
    assert repository.runs[run.id].checkpoint == original
    assert response.status == run.status
    assert response.counters == run.counters


def test_historical_checkpoint_response_is_preserved(tmp_path):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    checkpoint = {"grouping": {"sources": ["history.jpg"]}, "phase": "review"}
    run = replace(
        run,
        workflow_mode=SemiAutomaticSelectionWorkflowMode.SELECTION,
        checkpoint=checkpoint,
        v7_configuration=None,
    )
    assert to_run_response(run).checkpoint == checkpoint


def test_v7_unexpected_checkpoint_values_are_not_public(tmp_path):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    run = replace(run, checkpoint={"schemaVersion": ["private"], "scanState": None})
    assert to_run_response(run).checkpoint == {}


@pytest.mark.parametrize("include_checkpoint", [False, True])
def test_display_sql_never_selects_raw_private_checkpoint(tmp_path, include_checkpoint):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    record = _run_record(run, identity_key="a" * 64)
    private = deepcopy(record.checkpoint)
    summary = {"scanState": {"phase": "finalized"}} if include_checkpoint else {}
    session = Mock()
    session.execute.return_value.one_or_none.return_value = (
        record,
        job_record_from_domain(run.job),
        summary,
    )
    result = SqlAlchemySemiAutomaticSelectionRepository(session).get_for_display(
        run.id, include_checkpoint=include_checkpoint
    )
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "semi_automatic_image_selection_runs.checkpoint," not in sql
    assert ("jsonb_build_object" in sql) == include_checkpoint
    if not include_checkpoint:
        assert "semi_automatic_image_selection_runs.checkpoint" not in sql
    assert result.checkpoint == summary
    assert record.checkpoint == private
    session.flush.assert_not_called()


def test_review_reads_use_display_adapter_but_mutations_keep_full_read(tmp_path):
    client, repository, service, run, _ = delivery_fixture(tmp_path)
    full = repository.get
    display = Mock(side_effect=lambda run_id, **_: replace(full(run_id), checkpoint={}))
    repository.get_for_display = display
    repository.get = Mock(side_effect=full)
    assert client.get(f"/admin/semi-automatic-image-selections/{run.id}").status_code == 200
    assert service.list_ranges(run.id, after_expected_index=None, limit=1)
    assert service.list_sources(run.id, after_source_index=None, limit=1)
    assert service.v7_source_diagnostics(run.id, [0])
    assert display.call_count == 4
    repository.get.assert_not_called()
    service.get(run.id)
    repository.get.assert_called_once_with(run.id)


@pytest.mark.parametrize(
    "roots,expected",
    [
        ([], None),
        ([None], ""),
        (["C:/output"], "C:/output"),
        (["C:/output", "C:/output"], "C:/output"),
    ],
)
def test_output_pin_read_is_bounded_and_preserves_legacy_root(tmp_path, roots, expected):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    session = Mock()
    session.scalars.return_value.all.return_value = roots
    assert (
        SqlAlchemySemiAutomaticSelectionRepository(session).get_v7_output_root(run.id) == expected
    )
    sql = str(session.scalars.call_args.args[0].compile(dialect=postgresql.dialect())).lower()
    assert sql.count("limit ") == 2
    assert "union all" in sql
    assert "distinct" not in sql


def test_conflicting_pending_and_committed_root_blocks_publication(tmp_path):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    session = Mock()
    session.scalars.return_value.all.return_value = ["C:/one", "C:/two"]
    with pytest.raises(V7DeliveryConflict) as failed:
        SqlAlchemySemiAutomaticSelectionRepository(session).get_v7_output_root(run.id)
    assert failed.value.code == "V7_OUTPUT_ROOT_CONFLICT"


def test_review_reservation_and_retry_preserve_private_checkpoint(tmp_path):
    _, repository, service, run, manifest = delivery_fixture(tmp_path)
    private = {"scanState": {"phase": "finalized", "observations": ["private-history"]}}
    run = replace(run, checkpoint=private)
    repository.runs[run.id] = run
    repository.get_for_v7_review = Mock(
        side_effect=lambda run_id, **_: replace(
            repository.runs[run_id], checkpoint={"scanState": {"phase": "finalized"}}
        )
    )
    repository.get = Mock(side_effect=AssertionError("Review must not load private scan history"))
    repository.save = Mock(side_effect=AssertionError("Review must not rewrite scan recovery"))
    decision = V7OutputDecision.from_payload(decision_body(run, manifest))
    reserved = service.acknowledge_v7_output(run.id, 1, decision)
    assert reserved.output_operation["state"] == "reserved"
    assert repository.runs[run.id].checkpoint == private
    current = repository.runs[run.id]
    repository.runs[run.id] = replace(current, job=replace(current.job, status=JobStatus.FAILED))
    replayed = service.acknowledge_v7_output(run.id, 1, decision)
    assert replayed.output_operation["operationId"] == str(decision.operation_id)
    assert len(repository.operations) == 1
    assert repository.runs[run.id].job.status is JobStatus.CREATED
    assert repository.runs[run.id].checkpoint == private
    repository.get.assert_not_called()
    repository.save.assert_not_called()


@pytest.mark.parametrize(
    "control",
    [
        {"blockedReason": "DRIFT", "scanState": {"phase": "finalized"}},
        {"scanState": {"phase": "scanning"}},
        {"scanState": None},
    ],
)
def test_review_control_keeps_finalization_and_block_guards(tmp_path, control):
    _, repository, service, run, manifest = delivery_fixture(tmp_path)
    repository.get_for_v7_review = Mock(return_value=replace(run, checkpoint=control))
    with pytest.raises(V7DeliveryConflict) as failed:
        service.acknowledge_v7_output(
            run.id, 1, V7OutputDecision.from_payload(decision_body(run, manifest))
        )
    assert failed.value.code == "V7_SCAN_FINALIZATION_REQUIRED"
    assert not repository.operations


def test_review_control_sql_is_compact_and_does_not_change_recovery(tmp_path):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    record = _run_record(run, identity_key="a" * 64)
    private = deepcopy(record.checkpoint)
    control = {
        "blockedReason": None,
        "v7ProjectionFingerprint": "a" * 64,
        "scanState": {"phase": "finalized"},
    }
    session = Mock()
    session.execute.return_value.one_or_none.return_value = (
        record,
        job_record_from_domain(run.job),
        control,
    )
    result = SqlAlchemySemiAutomaticSelectionRepository(session).get_for_v7_review(run.id)
    sql = str(session.execute.call_args.args[0].compile(dialect=postgresql.dialect()))
    assert "semi_automatic_image_selection_runs.checkpoint," not in sql
    assert "jsonb_build_object" in sql
    assert result.checkpoint == control
    assert record.checkpoint == private
    session.flush.assert_not_called()


def test_review_metadata_save_never_replaces_checkpoint(tmp_path):
    _, _, _, run, _ = delivery_fixture(tmp_path)
    record = _run_record(run, identity_key="a" * 64)
    private = deepcopy(record.checkpoint)
    session = Mock()
    session.get.side_effect = [record, job_record_from_domain(run.job)]
    repo = SqlAlchemySemiAutomaticSelectionRepository(session)
    updated = replace(
        run, checkpoint={"scanState": {"phase": "finalized"}}, revision=run.revision + 1
    )
    assert repo.save_v7_review_state(updated) == updated
    assert record.checkpoint == private
    assert record.revision == updated.revision
    session.execute.assert_not_called()
    session.flush.assert_called_once()


@pytest.mark.parametrize(
    "workflow,status,compact",
    [
        ("v7_selection", "syncing_output", True),
        ("v7_selection", "analysis_complete", True),
        ("v7_selection", "review_mode", True),
        ("v7_selection", "running", False),
        ("v7_selection", "paused", False),
        ("selection", "analysis_complete", False),
    ],
)
def test_worker_dispatch_preserves_full_scan_reads_and_bounds_review(
    tmp_path, monkeypatch, workflow, status, compact
):
    from game_predictor_worker.semi_automatic_selection import job as job_module

    _, _, _, run, _ = delivery_fixture(tmp_path)
    run = replace(run, checkpoint={"v7ProjectionFingerprint": "a" * 64})
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute.return_value.one_or_none.return_value = (run.id, workflow, status)
    repository = Mock()
    repository.get.return_value = run
    repository.get_for_v7_review.return_value = run
    monkeypatch.setattr(
        job_module, "SqlAlchemySemiAutomaticSelectionRepository", lambda _: repository
    )
    assert (
        job_module.SemiAutomaticSelectionJobStore(lambda: session).get_run_for_job(run.job.id)
        == run
    )
    if compact:
        repository.get.assert_not_called()
        repository.get_for_v7_review.assert_called_once_with(run.id)
    else:
        repository.get.assert_called_once_with(run.id)
        repository.get_for_v7_review.assert_not_called()


def test_worker_keeps_full_recovery_when_finalization_has_no_projection(tmp_path, monkeypatch):
    from game_predictor_worker.semi_automatic_selection import job as job_module

    _, _, _, run, _ = delivery_fixture(tmp_path)
    session = MagicMock()
    session.__enter__.return_value = session
    session.execute.return_value.one_or_none.return_value = (
        run.id,
        "v7_selection",
        "analysis_complete",
    )
    repository = Mock()
    repository.get_for_v7_review.return_value = replace(
        run, checkpoint={"v7ProjectionFingerprint": None}
    )
    repository.get.return_value = run
    monkeypatch.setattr(
        job_module, "SqlAlchemySemiAutomaticSelectionRepository", lambda _: repository
    )
    assert (
        job_module.SemiAutomaticSelectionJobStore(lambda: session).get_run_for_job(run.job.id)
        == run
    )
    repository.get.assert_called_once_with(run.id)
