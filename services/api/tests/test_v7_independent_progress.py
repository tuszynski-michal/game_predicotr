from __future__ import annotations

import json
import os
import subprocess
import sys
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint
from game_predictor_api.storage.models import (
    SemiAutomaticImageSelectionRunModel,
    V7SourceObservationModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from game_predictor_worker.filesystem import long_path_aware
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.semi_automatic_selection import job as job_module
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionSource,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import LocalSourceManifest
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_delivery_store import (
    persist_v7_observations,
    verify_v7_observation_prefix,
)
from game_predictor_worker.semi_automatic_selection.v7_independent_progress import (
    prepare_independent_progress,
)
from game_predictor_worker.semi_automatic_selection.v7_quality import V7CropEdge
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7LabelEvidence,
    V7RangeProofKind,
    V7RangeProofResult,
    V7WeakFrameEvidence,
)
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7PinnedSourceManifest,
    V7ScanObservation,
    V7ScanRunState,
)
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7WorkerConfiguration,
    _progress,
    _runtime_checkpoint,
)
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from test_v7_selection_delivery_api import delivery_fixture
from v7_run_state_support import manifest as _manifest
from v7_run_state_support import quality as _quality


@pytest.fixture
def independent_fixture(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'observations.sqlite'}")
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
    manifest = _manifest(b"frame-0", b"frame-1", b"frame-2", b"frame-3")
    config = V7WorkerConfiguration(
        1,
        18,
        SemiAutomaticSelectionDirection.ASCENDING,
        V7BorderStyle.TOP_AND_SIDES,
        "a" * 64,
        "b" * 64,
    )
    state = V7ScanRunState(
        manifest, expected_ranges=config.expected_ranges, border_style=config.border_style
    )
    run_id = uuid4()
    labels = tuple(V7LabelEvidence(i, i + 1, 0.99, 0.99) for i in (0, 4, 8))

    def observation(index):
        quality = _quality(state, index)
        quality = replace(
            quality,
            boards=(
                replace(quality.boards[0], cropped_edges=frozenset({V7CropEdge.TOP})),
                *quality.boards[1:],
            ),
        )
        return V7ScanObservation(
            index,
            V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("NO_LOCAL_PROOF",)),
            quality,
            weak_evidence=V7WeakFrameEvidence(
                state.source_manifest.sources[index].source_id,
                labels,
                0 if index % 2 == 0 else (2**64 - 1),
                bytes(64) if index % 2 == 0 else bytes([7]) * 64,
            ),
            labels=labels,
            observed_position_indices=(0, 4, 8),
        )

    # The legacy base ends with a pending weak hypothesis, not a resolved proof.
    state.consume(observation(0))
    base_checkpoint = _runtime_checkpoint(state, config)
    with Session(engine) as session, session.begin():
        persist_v7_observations(session, run_id, base_checkpoint, datetime.now(UTC))
        prepared = prepare_independent_progress(
            session,
            artifact_root=tmp_path,
            run_id=run_id,
            checkpoint=base_checkpoint,
            configuration=config,
            manifest=manifest,
        )
    pending = tuple(observation(i) for i in range(1, 4))
    for item in pending:
        state.consume(item)
    progress = _progress(
        state,
        config,
        source_indexes=(1, 2, 3),
        resume_reference=prepared.resume_reference,
        observations=pending,
    )
    yield engine, run_id, manifest, config, state, progress, tmp_path
    engine.dispose()


def commit_progress(fixture):
    engine, run_id, _manifest, _config, _state, progress, _root = fixture
    with Session(engine) as session, session.begin():
        persist_v7_observations(
            session,
            run_id,
            progress.checkpoint,
            datetime.now(UTC),
            source_indexes=progress.source_indexes,
            pinned_manifest=progress.pinned_manifest,
            diagnostic_scan_state=progress.diagnostic_scan_state,
            observations=progress.observations,
        )


def test_windows_long_artifact_path_can_publish_adopt_and_recover(independent_fixture):
    engine, run_id, manifest, config, state, _progress_record, root = independent_fixture
    commit_progress(independent_fixture)
    artifact_root = root.joinpath(*("nested-" + "a" * 30 for _ in range(5)))
    full_checkpoint = _runtime_checkpoint(state, config)
    with Session(engine) as session:
        prepared = prepare_independent_progress(
            session,
            artifact_root=artifact_root,
            run_id=run_id,
            checkpoint=full_checkpoint,
            configuration=config,
            manifest=manifest,
        )
        base_path = artifact_root / prepared.resume_reference["relativePath"]
        assert len(str(base_path.resolve())) > 260
        assert prepared == prepare_independent_progress(
            session,
            artifact_root=artifact_root,
            run_id=run_id,
            checkpoint=full_checkpoint,
            configuration=config,
            manifest=manifest,
        )
        control = _progress(
            state, config, resume_reference=prepared.resume_reference, observations=()
        )
        recovered = prepare_independent_progress(
            session,
            artifact_root=artifact_root,
            run_id=run_id,
            checkpoint=control.checkpoint,
            configuration=config,
            manifest=manifest,
        )
    assert recovered.checkpoint == full_checkpoint


def recover(fixture, checkpoint=None):
    engine, run_id, manifest, config, _state, progress, root = fixture
    with Session(engine) as session:
        return prepare_independent_progress(
            session,
            artifact_root=root,
            run_id=run_id,
            checkpoint=progress.checkpoint if checkpoint is None else checkpoint,
            configuration=config,
            manifest=manifest,
        )


def test_v2_adoption_fresh_session_recovery_preserves_weak_proofs_crop_and_canon(
    independent_fixture,
):
    commit_progress(independent_fixture)
    engine, run_id, _manifest, config, state, progress, root = independent_fixture
    prepared = recover(independent_fixture)
    assert prepared.checkpoint == _runtime_checkpoint(state, config)
    assert prepared.resume_reference == progress.checkpoint["resumeBase"]
    assert len(json.dumps(progress.checkpoint)) < 1500
    assert len(tuple((root / "exports").rglob("*.json"))) == 1
    with Session(engine) as session, session.begin():
        verify_v7_observation_prefix(session, run_id, prepared.checkpoint)
    # Same committed batch after a lost response remains immutable/idempotent.
    commit_progress(independent_fixture)
    assert recover(independent_fixture).checkpoint == prepared.checkpoint


def test_batch_reads_only_new_source_ids_and_rollback_leaves_no_partial_result(independent_fixture):
    engine, run_id, _manifest, _config, _state, progress, _root = independent_fixture
    statements = []

    def record(_conn, _cursor, statement, params, _context, _many):
        if statement.startswith("SELECT"):
            statements.append((statement, params))

    event.listen(engine, "before_cursor_execute", record)
    try:
        with pytest.raises(RuntimeError), Session(engine) as session, session.begin():
            persist_v7_observations(
                session,
                run_id,
                progress.checkpoint,
                datetime.now(UTC),
                source_indexes=progress.source_indexes,
                pinned_manifest=progress.pinned_manifest,
                diagnostic_scan_state=progress.diagnostic_scan_state,
                observations=progress.observations,
            )
            session.flush()
            raise RuntimeError("Lost process before commit")
        assert len(statements) == 1 and "source_index IN" in statements[0][0]
        assert tuple(statements[0][1][-3:]) == (1, 2, 3)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    with Session(engine) as session:
        assert session.get(V7SourceObservationModel, (run_id, 1)) is None
    with pytest.raises(JobHandlerError) as error:
        recover(independent_fixture)
    assert error.value.code == "V7_SOURCE_OBSERVATION_CHANGED"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "extra",
        "digest",
        "quality",
        "crop",
        "weak",
        "resume",
        "base",
        "path",
        "cursor",
        "manifest",
        "profile",
    ],
)
def test_independent_recovery_fails_closed_on_changed_base_prefix_or_pins(
    independent_fixture, mutation
):
    commit_progress(independent_fixture)
    engine, run_id, _manifest, _config, _state, progress, root = independent_fixture
    checkpoint = deepcopy(progress.checkpoint)
    if mutation in {"missing", "extra", "digest", "quality", "crop", "weak", "resume"}:
        with Session(engine) as session, session.begin():
            row = session.get(V7SourceObservationModel, (run_id, 1))
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
            else:
                body = deepcopy(row.payload)
                if mutation == "digest":
                    row.payload_fingerprint = "c" * 64
                elif mutation == "quality":
                    body["resumeObservation"]["quality"]["sourceId"] = "wrong-source"
                    row.payload = body
                    row.payload_fingerprint = payload_fingerprint(body)
                elif mutation == "crop":
                    body["resumeObservation"]["quality"]["boards"][0]["croppedEdges"] = []
                    row.payload = body
                    row.payload_fingerprint = payload_fingerprint(body)
                elif mutation == "weak":
                    body["resumeObservation"]["weakEvidence"]["visualHash"] = "0"
                    row.payload = body
                    row.payload_fingerprint = payload_fingerprint(body)
                else:
                    body.pop("resumeObservation")
                    row.payload = body
                    row.payload_fingerprint = payload_fingerprint(body)
    elif mutation == "base":
        long_path_aware(root / checkpoint["resumeBase"]["relativePath"]).write_bytes(b"changed")
    elif mutation == "path":
        checkpoint["resumeBase"]["relativePath"] = "../foreign.json"
    elif mutation == "cursor":
        checkpoint["scanState"]["tracker"]["cursors"]["sequenceCursorIndex"] += 1
    elif mutation == "manifest":
        checkpoint["scanState"]["sourceManifest"]["sourceFingerprint"] = "c" * 64
    else:
        checkpoint["calibrationFingerprint"] = "c" * 64
    with pytest.raises(JobHandlerError):
        recover(independent_fixture, checkpoint)


def test_finalization_pending_recovers_without_reinterpreting_or_ocr(independent_fixture):
    commit_progress(independent_fixture)
    _engine, _run_id, manifest, config, state, progress, _root = independent_fixture
    state.complete_scan()
    pending = _progress(
        state,
        config,
        source_indexes=(),
        observations=(),
        resume_reference=progress.checkpoint["resumeBase"],
    )
    prepared = recover(independent_fixture, pending.checkpoint)
    assert prepared.checkpoint == _runtime_checkpoint(state, config)
    restored = V7ScanRunState(
        manifest,
        expected_ranges=config.expected_ranges,
        border_style=config.border_style,
        checkpoint=prepared.checkpoint["scanState"],
    )
    assert restored.finalize(manifest) == state.finalize(manifest)


def test_public_diagnostics_excludes_private_recovery_fields(independent_fixture):
    commit_progress(independent_fixture)
    engine, run_id, _manifest, _config, _state, _progress, _root = independent_fixture
    with Session(engine) as session:
        private = session.get(V7SourceObservationModel, (run_id, 1)).payload
        public = SqlAlchemySemiAutomaticSelectionRepository(session).get_v7_source_observations(
            run_id, (1,)
        )[1]
    assert "resumeObservation" in private and "resumeObservation" not in public
    assert public == {key: value for key, value in private.items() if key != "resumeObservation"}


def test_recovery_from_a_new_python_process_uses_only_persisted_base_and_sql(independent_fixture):
    commit_progress(independent_fixture)
    _engine, run_id, manifest, config, state, progress, root = independent_fixture
    inputs = root / "fresh-process-input.json"
    inputs.write_text(
        json.dumps(
            {
                "runId": str(run_id),
                "checkpoint": progress.checkpoint,
                "manifest": state.source_manifest.as_dict(),
                "database": f"sqlite:///{root / 'observations.sqlite'}",
                "artifactRoot": str(root),
            }
        ),
        encoding="utf-8",
    )
    script = root / "recover.py"
    script.write_text(
        "import sys\n"
        "from test_v7_independent_progress import recover_persisted_fixture\n"
        "print(recover_persisted_fixture(sys.argv[1]))\n",
        encoding="utf-8",
    )
    process = subprocess.run(
        [sys.executable, str(script), str(inputs)],
        capture_output=True,
        text=True,
        timeout=25,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (
                    str(Path(__file__).resolve().parents[3] / "services" / "api" / "src"),
                    str(Path(__file__).resolve().parents[3] / "services" / "worker" / "src"),
                    str(Path(__file__).resolve().parent),
                    str(Path(__file__).resolve().parents[3] / "services" / "test_support"),
                )
            ),
        },
    )
    assert process.returncode == 0, process.stderr
    assert process.stdout.strip() == payload_fingerprint(_runtime_checkpoint(state, config))


def recover_persisted_fixture(input_path):
    data = json.loads(Path(input_path).read_text(encoding="utf-8"))
    pinned = V7PinnedSourceManifest.from_dict(data["manifest"])
    sources = tuple(
        SemiAutomaticSelectionSource(
            source.source_index, source.relative_path, source.size_bytes, source.checksum_sha256
        )
        for source in pinned.sources
    )
    manifest = LocalSourceManifest(
        pinned.selection_id,
        "fixture",
        pinned.source_root,
        sources,
        pinned.source_fingerprint,
        sum(source.size_bytes for source in sources),
        b"",
        pinned.manifest_checksum_sha256,
    )
    config = V7WorkerConfiguration(
        1,
        18,
        SemiAutomaticSelectionDirection.ASCENDING,
        V7BorderStyle.TOP_AND_SIDES,
        "a" * 64,
        "b" * 64,
    )
    engine = create_engine(data["database"])
    try:
        with Session(engine) as session:
            prepared = prepare_independent_progress(
                session,
                artifact_root=Path(data["artifactRoot"]),
                run_id=UUID(data["runId"]),
                checkpoint=data["checkpoint"],
                configuration=config,
                manifest=manifest,
            )
        return payload_fingerprint(prepared.checkpoint)
    finally:
        engine.dispose()


@pytest.mark.parametrize("status", ["running", "paused", "cancelled"])
def test_fenced_independent_store_never_reads_old_checkpoint_and_preserves_control(
    independent_fixture, monkeypatch, status
):
    engine, run_id, _manifest, _config, _state, progress, root = independent_fixture
    delivery_root = root / "delivery"
    delivery_root.mkdir()
    _client, _repo, _service, domain, _local_manifest = delivery_fixture(delivery_root)
    domain = replace(domain, id=run_id)
    # Poison the old JSON deliberately. A SELECT of that column would fail
    # decoding, proving that the real ORM query omits it rather than merely
    # ignoring its value after it has been loaded.
    columns = ", ".join(
        f'"{column.name}" ' + ("INTEGER" if column.name == "revision" else "TEXT")
        for column in SemiAutomaticImageSelectionRunModel.__table__.columns
    )
    with engine.begin() as connection:
        connection.execute(text(f"CREATE TABLE semi_automatic_image_selection_runs ({columns})"))
        connection.execute(
            text(
                "INSERT INTO semi_automatic_image_selection_runs "
                "(id,job_id,workflow_mode,status,checkpoint,counters,revision) "
                "VALUES (:id,:job_id,'v7_selection',:status,'not-json',:counters,0)"
            ),
            {
                "id": run_id.hex,
                "job_id": domain.job.id.hex,
                "status": status,
                "counters": json.dumps({"processedSources": 1}),
            },
        )
    calls = []
    monkeypatch.setattr(job_module, "_lock_v7_gate_for_run", lambda *_: calls.append("gate"))
    monkeypatch.setattr(job_module, "_assert_fence", lambda *_: calls.append("job"))
    store = job_module.SemiAutomaticSelectionJobStore(lambda: Session(engine))

    def forbidden_read(_id):
        raise AssertionError("Full run read after commit")

    monkeypatch.setattr(store, "_get_run", forbidden_read)
    request = dict(
        job_id=domain.job.id,
        run_id=run_id,
        lease_token=uuid4(),
        checkpoint=progress.checkpoint,
        counters={"processedSources": 4},
        persisted_at=datetime.now(UTC),
        v7_progress=progress,
        current_run=domain,
    )
    if status == "cancelled":
        with pytest.raises(JobHandlerError):
            store.persist_checkpoint(**request)
        with Session(engine) as session:
            assert session.get(V7SourceObservationModel, (run_id, 1)) is None
    else:
        result = store.persist_checkpoint(**request)
        assert result.status.value == status
        assert result.checkpoint == progress.checkpoint and result.counters["processedSources"] == 4
        assert result.revision == 1
    assert calls == ["gate", "job"]
