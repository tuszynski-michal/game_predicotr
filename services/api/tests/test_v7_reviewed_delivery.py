from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRangeStatus,
)
from game_predictor_api.domain.v7_selection_delivery import V7OutputDecision
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.semi_automatic_selection import job as job_module
from game_predictor_worker.semi_automatic_selection import v7_delivery as delivery_module
from game_predictor_worker.semi_automatic_selection.v7_output_writer import (
    V7OutputWriter,
    V7OutputWriterError,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import V7PinnedSourceManifest
from test_v7_selection_delivery_api import decision_body, delivery_fixture


class TransactionFixture:
    """Transaction/row-lock unit double; journal and output use the actual filesystem."""

    def __init__(self, repository, run, operation):
        self.repository = repository
        self.run = run
        item = repository.ranges[(run.id, 1)]
        self.state = SimpleNamespace(
            run=SimpleNamespace(
                **{
                    "id": run.id,
                    "status": "syncing_output",
                    "checkpoint": run.checkpoint,
                    "v7_configuration": run.v7_configuration.as_payload(),
                    "revision": run.revision,
                    "counters": {"missing": 2, "proposed": 0, "autoSelected": 0, "outputSynced": 0},
                    "updated_at": run.updated_at,
                }
            ),
            item=SimpleNamespace(**item.__dict__)
            if hasattr(item, "__dict__")
            else SimpleNamespace(
                **{name: getattr(item, name) for name in item.__dataclass_fields__}
            ),
            operations={operation.operation_id: operation},
        )
        self.lease = uuid4()

    def __call__(self):
        owner = self

        class Session:
            def __enter__(self):
                self.state = deepcopy(owner.state)
                self.owner = owner
                return self

            def __exit__(self, *_args):
                return False

            @contextmanager
            def begin(self):
                yield
                owner.state = self.state

            def scalar(self, _statement):
                return self.state.item

        return Session()


class FixtureRepository:
    def __init__(self, session):
        self.session = session

    def get_v7_pilot_gate(self, **_kwargs):
        return self.session.owner.repository.gate

    def get_v7_output_operation(self, operation_id, **_kwargs):
        return self.session.state.operations.get(operation_id)

    def get_pending_v7_output(self, run_id):
        return next(
            (
                op
                for op in self.session.state.operations.values()
                if op.state in ("reserved", "recovery_required")
            ),
            None,
        )

    def save_v7_output_operation(self, operation):
        self.session.state.operations[operation.operation_id] = operation
        return operation

    def get_for_v7_review(self, run_id, **_kwargs):
        return replace(self.session.owner.run, checkpoint=self.session.state.run.checkpoint)


def prepared_delivery(tmp_path, monkeypatch, *, source_policy="exact_sources"):
    _client, repository, service, run, manifest = delivery_fixture(
        tmp_path, source_policy=source_policy
    )
    run = replace(
        run,
        checkpoint={
            "scanState": {
                "phase": "finalized",
                "sourceManifest": V7PinnedSourceManifest.from_local_manifest(manifest).as_dict(),
            }
        },
    )
    repository.runs[run.id] = run
    decision = V7OutputDecision.from_payload(
        {
            **decision_body(run, manifest),
            "expectedTargetChecksumSha256": None,
            "expectedOwnerOperationId": None,
        }
    )
    service.acknowledge_v7_output(run.id, 1, decision)
    operation = repository.operations[decision.operation_id]
    fixture = TransactionFixture(repository, run, operation)
    monkeypatch.setattr(
        delivery_module, "SqlAlchemySemiAutomaticSelectionRepository", FixtureRepository
    )
    monkeypatch.setattr(
        job_module, "_locked_run", lambda session, _run_id, **_kwargs: session.state.run
    )

    def assert_fence(session, _job_id, token, _now):
        if token != fixture.lease:
            raise JobConflictError("JOB_LEASE_LOST", "Lost fixture lease.")

    monkeypatch.setattr(job_module, "_assert_fence", assert_fence)
    context = SimpleNamespace(lease_token=fixture.lease, now=lambda: datetime.now(UTC))
    return fixture, context, run, manifest, operation


@pytest.mark.parametrize(
    "control",
    [
        {"blockedReason": "DRIFT", "scanState": {"phase": "finalized"}},
        {"scanState": {"phase": "scanning"}},
        {"scanState": None},
    ],
)
def test_compact_publication_control_still_blocks_invalid_scan(tmp_path, monkeypatch, control):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    fixture.state.run.checkpoint = control
    with pytest.raises(JobHandlerError) as failed:
        delivery_module.V7ReviewedDelivery(
            fixture,
            SimpleNamespace(validate=lambda _gate: None),
            filesystem_validator=lambda _: True,
        ).execute(context, run, manifest)
    assert failed.value.code == "V7_OUTPUT_STALE_GENERATION"
    assert fixture.state.operations[operation.operation_id].state != "committed"
    assert not (manifest.source_root.with_name("source cut") / "seq_10-18.jpg").exists()


def test_publication_and_receipt_do_not_load_locked_run_checkpoint(tmp_path, monkeypatch):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    locks = []

    def lock_without_recovery(session, _run_id, *, include_checkpoint=True):
        locks.append(include_checkpoint)
        assert include_checkpoint is False
        return session.state.run

    monkeypatch.setattr(job_module, "_locked_run", lock_without_recovery)
    delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _: True,
    ).execute(context, run, manifest)
    assert locks and not any(locks)
    assert fixture.state.operations[operation.operation_id].state == "committed"


@pytest.mark.parametrize("phase", ["target_linked", "journal_committed"])
def test_pinned_other_output_volume_recovers_without_rehashing_catalog(
    tmp_path, monkeypatch, phase
):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    output = tmp_path / "other-volume" / str(run.id)
    operation = replace(
        operation, context_payload={**operation.context_payload, "outputRoot": str(output)}
    )
    fixture.state.operations[operation.operation_id] = operation

    def unexpected_catalog_scan(*_args, **_kwargs):
        raise AssertionError("A manual decision must not rehash all unrelated sources")

    monkeypatch.setattr(delivery_module, "build_local_source_manifest", unexpected_catalog_scan)

    def crash(at, _operation):
        if at == phase:
            raise RuntimeError("Process loss after publication")

    delivery = delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda path: path != manifest.source_root,
        fault_hook=crash,
    )
    with pytest.raises(JobHandlerError):
        delivery.execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "recovery_required"
    fixture.lease = uuid4()
    context = SimpleNamespace(lease_token=fixture.lease, now=lambda: datetime.now(UTC))
    delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda path: path != manifest.source_root,
    ).execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "committed"
    assert (output / "seq_10-18.jpg").read_bytes() == b"selected-jpeg-fixture"
    assert not (manifest.source_root.with_name("source cut")).exists()


def test_selected_source_changed_still_blocks_pinned_manual_publication(tmp_path, monkeypatch):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    (manifest.source_root / manifest.sources[0].relative_path).write_bytes(b"changed-jpeg")
    with pytest.raises(JobHandlerError) as failed:
        delivery_module.V7ReviewedDelivery(
            fixture,
            SimpleNamespace(validate=lambda _gate: None),
            filesystem_validator=lambda _path: True,
        ).execute(context, run, manifest)
    assert failed.value.code == "V7_OUTPUT_SOURCE_CHANGED"
    assert not (manifest.source_root.with_name("source cut") / "seq_10-18.jpg").exists()


@pytest.mark.parametrize("phase", ["target_linked", "journal_committed"])
@pytest.mark.parametrize("source_policy", ["exact_sources", "operator_selected_local_folder"])
def test_current_new_claim_recovers_publication_before_sql_receipt(
    tmp_path, monkeypatch, phase, source_policy
):
    fixture, context, run, manifest, operation = prepared_delivery(
        tmp_path, monkeypatch, source_policy=source_policy
    )

    def crash(at, _operation):
        if at == phase:
            raise RuntimeError("Simulated process loss before SQL commit.")

    delivery = delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        fault_hook=crash,
        filesystem_validator=lambda _path: True,
    )
    with pytest.raises(JobHandlerError):
        delivery.execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "recovery_required"
    assert fixture.state.item.output_checksum_sha256 is None
    fixture.lease = uuid4()
    context = SimpleNamespace(lease_token=fixture.lease, now=lambda: datetime.now(UTC))
    # New adapter and lease; no in-memory generation whitelist survives recovery.
    delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _path: True,
    ).execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "committed"
    assert fixture.state.item.status == SemiAutomaticSelectionRangeStatus.OUTPUT_SYNCED.value
    assert (
        fixture.state.run.counters["outputSynced"]
        == fixture.state.run.counters["manualSelected"]
        == 1
    )
    assert (tmp_path / "source cut" / "seq_10-18.jpg").read_bytes() == b"selected-jpeg-fixture"


@pytest.mark.parametrize(
    "method,code",
    [
        ("_write_temp", "V7_OUTPUT_WRITE_FAILED"),
        ("_save_journal", "V7_OUTPUT_JOURNAL_WRITE_FAILED"),
    ],
)
def test_transient_before_publication_keeps_same_operation_retryable(
    tmp_path, monkeypatch, method, code
):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    original = getattr(V7OutputWriter, method)
    calls = 0

    def fail_once(writer, *args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise V7OutputWriterError(code, "One sharing violation.")
        return original(writer, *args)

    monkeypatch.setattr(V7OutputWriter, method, fail_once)
    delivery = delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _path: True,
    )
    with pytest.raises(JobHandlerError):
        delivery.execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "recovery_required"
    assert fixture.state.operations[operation.operation_id].error_code == code
    fixture.lease = uuid4()
    context.lease_token = fixture.lease
    delivery.execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "committed"


def test_model_error_before_journal_is_terminal_with_reason(tmp_path, monkeypatch):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)

    def fail(_gate):
        raise delivery_module.V7DeliveryConflict("V7_PILOT_ARTIFACT_MISMATCH", "Changed model.")

    with pytest.raises(JobHandlerError):
        delivery_module.V7ReviewedDelivery(fixture, SimpleNamespace(validate=fail)).execute(
            context, run, manifest
        )
    assert fixture.state.operations[operation.operation_id].state == "failed"
    assert (
        fixture.state.operations[operation.operation_id].receipt["errorCode"]
        == "V7_PILOT_ARTIFACT_MISMATCH"
    )
    assert not (tmp_path / "source cut").exists()


def test_partial_temp_after_io_becomes_explicit_terminal_conflict(tmp_path, monkeypatch):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    original = V7OutputWriter._write_temp

    def partial_temp(writer, _source, journal_operation):
        writer._temp_path(journal_operation).write_bytes(b"incomplete-copy")
        raise V7OutputWriterError("V7_OUTPUT_WRITE_FAILED", "Interrupted partial temp.")

    monkeypatch.setattr(V7OutputWriter, "_write_temp", partial_temp)
    delivery = delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _path: True,
    )
    with pytest.raises(JobHandlerError):
        delivery.execute(context, run, manifest)
    monkeypatch.setattr(V7OutputWriter, "_write_temp", original)
    fixture.lease = uuid4()
    context.lease_token = fixture.lease
    delivery.execute(context, run, manifest)
    outcome = fixture.state.operations[operation.operation_id]
    assert outcome.state == "conflict"
    assert outcome.receipt["errorCode"] == "V7_OUTPUT_TEMP_CHECKSUM_MISMATCH"
    assert not (tmp_path / "source cut" / "seq_10-18.jpg").exists()


@pytest.mark.parametrize("phase", ["prepared", "temp_written"])
def test_same_sha_foreign_file_never_becomes_owned_after_crash(tmp_path, monkeypatch, phase):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    target = tmp_path / "source cut" / "seq_10-18.jpg"

    def foreign_target(at, _operation):
        if at == phase:
            target.write_bytes(b"selected-jpeg-fixture")
            raise RuntimeError("Crash before own hardlink publication.")

    with pytest.raises(JobHandlerError):
        delivery_module.V7ReviewedDelivery(
            fixture,
            SimpleNamespace(validate=lambda _gate: None),
            fault_hook=foreign_target,
            filesystem_validator=lambda _path: True,
        ).execute(context, run, manifest)
    fixture.lease = uuid4()
    context.lease_token = fixture.lease
    delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _path: True,
    ).execute(context, run, manifest)
    assert fixture.state.operations[operation.operation_id].state == "conflict"
    assert fixture.state.item.v7_output_owner_operation_id is None
    assert target.read_bytes() == b"selected-jpeg-fixture"


@pytest.mark.parametrize("published", [False, True])
def test_dispatch_validation_failure_resolves_or_explains_pending_command(
    tmp_path, monkeypatch, published
):
    fixture, context, run, manifest, operation = prepared_delivery(tmp_path, monkeypatch)
    delivery = delivery_module.V7ReviewedDelivery(
        fixture,
        SimpleNamespace(validate=lambda _gate: None),
        filesystem_validator=lambda _path: True,
    )
    if published:

        def crash(at, _operation):
            if at == "target_linked":
                raise RuntimeError("Crash before SQL receipt.")

        with pytest.raises(JobHandlerError):
            delivery_module.V7ReviewedDelivery(
                fixture,
                SimpleNamespace(validate=lambda _gate: None),
                fault_hook=crash,
                filesystem_validator=lambda _path: True,
            ).execute(context, run, manifest)
        fixture.lease = uuid4()
        context.lease_token = fixture.lease
    delivery.dispatch_failure(context, run, "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", None)
    outcome = fixture.state.operations[operation.operation_id]
    assert outcome.error_code == "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED"
    assert outcome.state == ("recovery_required" if published else "failed")
    if published:
        delivery.execute(context, run, manifest)
        assert fixture.state.operations[operation.operation_id].state == "committed"
    else:
        assert outcome.receipt["errorCode"] == "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED"
        assert not (tmp_path / "source cut").exists()
