from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.storage.models import V7SourceObservationModel
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.semi_automatic_selection import job as job_module
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_delivery_store import (
    persist_v7_observations,
    verify_v7_observation_prefix,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7RangeProofKind,
    V7RangeProofResult,
)
from game_predictor_worker.semi_automatic_selection.v7_review_projection import source_diagnostics
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7RunStateError,
    V7ScanObservation,
    V7ScanRunState,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session


@pytest.fixture
def persistence_fixture(tmp_path):
    # Portable SQL round-trip fixture. Production PostgreSQL constraints/locks
    # are covered by the existing gate/lease/delivery integration regressions.
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE semi_automatic_selection_v7_source_observations ("
                "run_id CHAR(32) NOT NULL, source_index BIGINT NOT NULL, "
                "source_checksum_sha256 VARCHAR(64) NOT NULL, "
                "payload_fingerprint VARCHAR(64) NOT NULL, payload JSON NOT NULL, "
                "created_at DATETIME NOT NULL, PRIMARY KEY (run_id, source_index))"
            )
        )
    root = tmp_path / "sources"
    root.mkdir()
    for index in range(4):
        (root / f"{index}.jpg").write_bytes(f"fixture-{index}".encode())
    manifest = build_local_source_manifest(root, selection_id=uuid4(), display_name="fixture")
    state = V7ScanRunState(
        manifest,
        expected_ranges=(SemiAutomaticSelectionRange(1, 9),),
        border_style=V7BorderStyle.TOP_AND_SIDES,
    )
    for index in range(4):
        state.consume(
            V7ScanObservation(
                index,
                V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("TEST_NO_PROOF",)),
                None,
                "TEST_SOURCE_ERROR",
            )
        )
    yield engine, uuid4(), {"scanState": state.checkpoint()}, state.source_manifest
    engine.dispose()


def test_delta_is_canonical_and_bulk_sql_survives_fresh_session_retry(persistence_fixture):
    engine, run_id, checkpoint, manifest = persistence_fixture
    scan = checkpoint["scanState"]
    full = source_diagnostics(scan)
    delta = source_diagnostics(scan, source_indexes=(2, 3), pinned_manifest=manifest)
    assert delta == {index: full[index] for index in (2, 3)}
    with Session(engine) as session, session.begin():
        persist_v7_observations(session, run_id, checkpoint, datetime.now(UTC))
    selects = []

    def count_select(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().startswith("SELECT"):
            selects.append(statement)

    event.listen(engine, "before_cursor_execute", count_select)
    try:
        # SQL committed but caller lost the response: a new process/session
        # retries the same delta, without querying earlier observations.
        with Session(engine) as session, session.begin():
            persist_v7_observations(
                session,
                run_id,
                checkpoint,
                datetime.now(UTC),
                source_indexes=(2, 3),
                pinned_manifest=manifest,
            )
        assert len(selects) == 1
        assert "source_index IN" in selects[0]
        with Session(engine) as session, session.begin():
            verify_v7_observation_prefix(session, run_id, checkpoint)
        assert len(selects) == 2
    finally:
        event.remove(engine, "before_cursor_execute", count_select)


@pytest.mark.parametrize("mutation", ["payload", "fingerprint", "checksum", "missing", "extra"])
def test_fresh_claim_audits_old_prefix_fail_closed(persistence_fixture, mutation):
    engine, run_id, checkpoint, _manifest = persistence_fixture
    with Session(engine) as session, session.begin():
        persist_v7_observations(session, run_id, checkpoint, datetime.now(UTC))
    with Session(engine) as session, session.begin():
        row = session.get(V7SourceObservationModel, (run_id, 0))
        if mutation == "missing":
            session.delete(row)
        elif mutation == "extra":
            session.add(
                V7SourceObservationModel(
                    run_id=run_id,
                    source_index=4,
                    source_checksum_sha256=row.source_checksum_sha256,
                    payload_fingerprint=row.payload_fingerprint,
                    payload=row.payload,
                    created_at=datetime.now(UTC),
                )
            )
        elif mutation == "payload":
            row.payload = {**row.payload, "sourceErrorCode": "CHANGED"}
        elif mutation == "fingerprint":
            row.payload_fingerprint = "a" * 64
        else:
            row.source_checksum_sha256 = "a" * 64
    with Session(engine) as session, session.begin(), pytest.raises(JobHandlerError) as error:
        verify_v7_observation_prefix(session, run_id, checkpoint)
    assert error.value.code == "V7_SOURCE_OBSERVATION_CHANGED"


def test_delta_conflict_rolls_back_the_whole_new_batch(persistence_fixture):
    engine, run_id, checkpoint, manifest = persistence_fixture
    with Session(engine) as session, session.begin():
        persist_v7_observations(
            session,
            run_id,
            checkpoint,
            datetime.now(UTC),
            source_indexes=(3,),
            pinned_manifest=manifest,
        )
    changed = deepcopy(checkpoint)
    changed["scanState"]["sourceErrors"][3]["reasonCode"] = "CHANGED"
    with Session(engine) as session, pytest.raises(JobHandlerError), session.begin():
        persist_v7_observations(
            session,
            run_id,
            changed,
            datetime.now(UTC),
            source_indexes=(2, 3),
            pinned_manifest=manifest,
        )
    with Session(engine) as session:
        assert session.get(V7SourceObservationModel, (run_id, 2)) is None


def test_delta_rejects_missing_diagnostics_and_manifest_drift(persistence_fixture):
    _engine, _run_id, checkpoint, manifest = persistence_fixture
    changed = deepcopy(checkpoint["scanState"])
    changed["sourceDiagnostics"].pop()
    with pytest.raises(V7RunStateError):
        source_diagnostics(changed, source_indexes=(3,), pinned_manifest=manifest)
    changed = deepcopy(checkpoint["scanState"])
    changed["sourceManifest"]["sourceFingerprint"] = "a" * 64
    with pytest.raises(V7RunStateError) as error:
        source_diagnostics(changed, source_indexes=(3,), pinned_manifest=manifest)
    assert error.value.code == "V7_SOURCE_MANIFEST_DRIFT"


@pytest.mark.parametrize("blocked", ["gate", "lease", "cancel", "delta"])
def test_batch_transaction_keeps_gate_job_run_order_and_rolls_back(
    persistence_fixture, monkeypatch, blocked
):
    engine, run_id, checkpoint, manifest = persistence_fixture
    calls = []

    def gate(_session, _run_id):
        calls.append("gate")
        if blocked == "gate":
            raise JobHandlerError("V7_PILOT_GENERATION_MISMATCH", "Changed generation.")

    def fence(_session, _job_id, _token, _now):
        calls.append("job")
        if blocked == "lease":
            raise JobHandlerError("JOB_LEASE_LOST", "Lost lease.")

    def locked_run(_session, _run_id):
        calls.append("run")
        return SimpleNamespace(
            status="cancelled" if blocked == "cancel" else "running",
            workflow_mode="v7_selection",
            counters={"processedSources": 0},
        )

    monkeypatch.setattr(job_module, "_lock_v7_gate_for_run", gate)
    monkeypatch.setattr(job_module, "_assert_fence", fence)
    monkeypatch.setattr(job_module, "_locked_run", locked_run)
    store = job_module.SemiAutomaticSelectionJobStore(lambda: Session(engine))
    progress = SimpleNamespace(
        source_indexes=(1, 2, 3) if blocked == "delta" else (0, 1, 2, 3),
        pinned_manifest=manifest,
    )
    with pytest.raises(JobHandlerError):
        store.persist_checkpoint(
            job_id=uuid4(),
            run_id=run_id,
            lease_token=uuid4(),
            checkpoint=checkpoint,
            counters={"processedSources": 4},
            persisted_at=datetime.now(UTC),
            v7_progress=progress,
        )
    assert calls == (
        ["gate"]
        if blocked == "gate"
        else ["gate", "job"]
        if blocked == "lease"
        else ["gate", "job", "run"]
    )
    with Session(engine) as session:
        assert session.get(V7SourceObservationModel, (run_id, 0)) is None


def test_pause_commits_complete_batch_and_new_claim_audits_it(persistence_fixture, monkeypatch):
    engine, run_id, checkpoint, manifest = persistence_fixture
    calls = []
    record = SimpleNamespace(
        status="paused",
        workflow_mode="v7_selection",
        counters={"processedSources": 0},
        checkpoint={},
        revision=0,
    )
    monkeypatch.setattr(job_module, "_lock_v7_gate_for_run", lambda *_args: calls.append("gate"))
    monkeypatch.setattr(job_module, "_assert_fence", lambda *_args: calls.append("job"))

    def locked_run(*_args):
        calls.append("run")
        return record

    monkeypatch.setattr(job_module, "_locked_run", locked_run)
    store = job_module.SemiAutomaticSelectionJobStore(lambda: Session(engine))
    monkeypatch.setattr(store, "_get_run", lambda _id: record)
    progress = SimpleNamespace(source_indexes=(0, 1, 2, 3), pinned_manifest=manifest)
    store.persist_checkpoint(
        job_id=uuid4(),
        run_id=run_id,
        lease_token=uuid4(),
        checkpoint=checkpoint,
        counters={"processedSources": 4},
        persisted_at=datetime.now(UTC),
        v7_progress=progress,
    )
    assert record.status == "paused" and record.counters["processedSources"] == 4
    assert record.checkpoint == checkpoint
    assert calls == ["gate", "job", "run"]
    calls.clear()
    # A fresh SQL session/claim validates the committed prefix before observing.
    store.verify_v7_prefix(
        job_id=uuid4(),
        run_id=run_id,
        lease_token=uuid4(),
        persisted_at=datetime.now(UTC),
    )
    assert calls == ["gate", "job", "run"]
