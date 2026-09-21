from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from game_predictor_worker.semi_automatic_selection import v7_calibration_sessions
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7_STANDARD_GEOMETRY_FAMILY_ID,
    V7AnnotationState,
    V7CropAssessment,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration_sessions import (
    V7CalibrationSessionError,
    V7CalibrationSessionOperation,
    V7CalibrationSessionOperationKind,
    V7CalibrationSessionSource,
    V7CalibrationSessionStatus,
    V7CalibrationSessionStore,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7CorpusSplit

FINGERPRINT = "a" * 64
SESSION_ID = "00000000-0000-0000-0000-000000000001"


def _sources(
    *, split: V7CorpusSplit = V7CorpusSplit.CALIBRATION
) -> tuple[V7CalibrationSessionSource, ...]:
    return tuple(
        V7CalibrationSessionSource(
            source_id=f"777/source-{index}.jpg",
            source_checksum_sha256=f"{index + 1:064x}",
            corpus_case_id="small_777",
            split=split,
            geometry_family_id=V7_STANDARD_GEOMETRY_FAMILY_ID,
        )
        for index in range(5)
    )


def _store(tmp_path: Path) -> V7CalibrationSessionStore:
    return V7CalibrationSessionStore(tmp_path / ".runtime")


def _create(store: V7CalibrationSessionStore):
    return store.create(
        manifest_fingerprint=FINGERPRINT,
        geometry_family_id=V7_STANDARD_GEOMETRY_FAMILY_ID,
        sources=_sources(),
        session_id=SESSION_ID,
    )


def _operation(
    operation_id: str,
    *,
    expected_revision: int = 0,
    center_x: float = 0.2,
) -> V7CalibrationSessionOperation:
    return V7CalibrationSessionOperation(
        operation_id=operation_id,
        expected_revision=expected_revision,
        kind=V7CalibrationSessionOperationKind.ANNOTATED,
        source_id="777/source-0.jpg",
        position_index=0,
        center_x=center_x,
        center_y=0.3,
        crop_assessment=V7CropAssessment.CONTAINED,
    )


def test_session_creation_pins_calibration_sources_and_explicit_slots(tmp_path: Path) -> None:
    session = _create(_store(tmp_path))

    assert session.revision == 0
    assert len(session.sources) == 5
    assert len(session.slots) == 45
    assert all(item.state is V7AnnotationState.UNREVIEWED for item in session.slots)


@pytest.mark.parametrize("split", [V7CorpusSplit.HOLDOUT, V7CorpusSplit.REFERENCE_ONLY])
def test_session_creation_rejects_holdout_and_reference_sources(
    tmp_path: Path, split: V7CorpusSplit
) -> None:
    store = _store(tmp_path)

    with pytest.raises(V7CalibrationSessionError) as error:
        store.create(
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=V7_STANDARD_GEOMETRY_FAMILY_ID,
            sources=_sources(split=split),
            session_id=SESSION_ID,
        )

    assert error.value.code == "V7_CALIBRATION_SESSION_SOURCE_INVALID"


def test_session_creation_rejects_byte_identical_source_aliases(tmp_path: Path) -> None:
    store = _store(tmp_path)
    duplicate = list(_sources())
    duplicate[1] = V7CalibrationSessionSource(
        source_id="777/copied-source.jpg",
        source_checksum_sha256=duplicate[0].source_checksum_sha256,
        corpus_case_id=duplicate[1].corpus_case_id,
        split=duplicate[1].split,
        geometry_family_id=duplicate[1].geometry_family_id,
    )

    with pytest.raises(V7CalibrationSessionError) as error:
        store.create(
            manifest_fingerprint=FINGERPRINT,
            geometry_family_id=V7_STANDARD_GEOMETRY_FAMILY_ID,
            sources=duplicate,
            session_id=SESSION_ID,
        )

    assert error.value.code == "V7_CALIBRATION_SESSION_SOURCE_INVALID"


def test_operation_replay_precedes_revision_check_and_rejects_changed_payload(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    _create(store)
    operation = _operation("00000000-0000-0000-0000-000000000011")

    updated, first_receipt = store.apply(SESSION_ID, operation, current_sources=_sources())
    replayed, replay_receipt = store.apply(SESSION_ID, operation, current_sources=_sources())

    assert (
        updated.revision
        == replayed.revision
        == first_receipt.revision
        == replay_receipt.revision
        == 1
    )
    assert len(replayed.receipts) == 1
    with pytest.raises(V7CalibrationSessionError) as error:
        store.apply(
            SESSION_ID,
            _operation(operation.operation_id, center_x=0.21),
            current_sources=_sources(),
        )
    assert error.value.code == "V7_CALIBRATION_SESSION_OPERATION_ID_CONFLICT"


def test_concurrent_stale_revision_allows_one_mutation(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    operations = (
        _operation("00000000-0000-0000-0000-000000000021"),
        _operation("00000000-0000-0000-0000-000000000022", center_x=0.21),
    )

    def apply(operation: V7CalibrationSessionOperation) -> str:
        try:
            return str(store.apply(SESSION_ID, operation, current_sources=_sources())[1].revision)
        except V7CalibrationSessionError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = set(executor.map(apply, operations))

    assert outcomes == {"1", "V7_CALIBRATION_SESSION_REVISION_CONFLICT"}
    assert store.read(SESSION_ID).revision == 1


def test_restart_temp_recovery_and_invalid_temp_fail_closed(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    store.apply(
        SESSION_ID,
        _operation("00000000-0000-0000-0000-000000000031"),
        current_sources=_sources(),
    )
    state_path = store._state_path(SESSION_ID)
    temporary_path = state_path.with_suffix(".json.tmp")
    state_path.replace(temporary_path)

    restored = _store(tmp_path).read(SESSION_ID)

    assert restored.revision == 1
    assert state_path.exists()
    temporary_path.write_text("{", encoding="utf-8")
    with pytest.raises(V7CalibrationSessionError) as error:
        _store(tmp_path).read(SESSION_ID)
    assert error.value.code == "V7_CALIBRATION_SESSION_CORRUPT"

    temporary_path.unlink()
    state_path.write_text("{", encoding="utf-8")
    with pytest.raises(V7CalibrationSessionError) as state_error:
        _store(tmp_path).read(SESSION_ID)
    assert state_error.value.code == "V7_CALIBRATION_SESSION_CORRUPT"


def test_recovery_commits_fsynced_successor_after_interrupted_publish(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    _create(store)
    operation = _operation("00000000-0000-0000-0000-000000000035")
    state_path = store._state_path(SESSION_ID)
    original_replace = v7_calibration_sessions.os.replace

    def interrupt_publish(source: Path, destination: Path) -> None:
        if Path(destination) == state_path:
            raise OSError("simulated interruption")
        original_replace(source, destination)

    monkeypatch.setattr(v7_calibration_sessions.os, "replace", interrupt_publish)
    with pytest.raises(OSError, match="simulated interruption"):
        store.apply(SESSION_ID, operation, current_sources=_sources())

    monkeypatch.setattr(v7_calibration_sessions.os, "replace", original_replace)
    recovered = _store(tmp_path).read(SESSION_ID)
    replayed, receipt = _store(tmp_path).apply(SESSION_ID, operation, current_sources=_sources())

    assert recovered.revision == replayed.revision == receipt.revision == 1


def test_recovery_rejects_successor_that_discards_idempotency_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    _create(store)
    operation = _operation("00000000-0000-0000-0000-000000000036")
    state_path = store._state_path(SESSION_ID)
    temporary_path = state_path.with_suffix(".json.tmp")
    original_replace = v7_calibration_sessions.os.replace

    def interrupt_publish(source: Path, destination: Path) -> None:
        if Path(destination) == state_path:
            raise OSError("simulated interruption")
        original_replace(source, destination)

    monkeypatch.setattr(v7_calibration_sessions.os, "replace", interrupt_publish)
    with pytest.raises(OSError, match="simulated interruption"):
        store.apply(SESSION_ID, operation, current_sources=_sources())
    monkeypatch.setattr(v7_calibration_sessions.os, "replace", original_replace)

    tampered = json.loads(temporary_path.read_text(encoding="utf-8"))
    tampered["session"]["receipts"] = []
    temporary_path.write_text(json.dumps(tampered), encoding="utf-8")
    with pytest.raises(V7CalibrationSessionError) as error:
        _store(tmp_path).read(SESSION_ID)

    assert error.value.code == "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT"


def test_recovery_rejects_blocked_snapshot_that_changes_annotation_state(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    state_path = store._state_path(SESSION_ID)
    temporary_path = state_path.with_suffix(".json.tmp")
    tampered = json.loads(state_path.read_text(encoding="utf-8"))
    tampered["session"]["status"] = "blocked_source_drift"
    tampered["session"]["slots"][0]["state"] = "unavailable"
    temporary_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(V7CalibrationSessionError) as error:
        _store(tmp_path).read(SESSION_ID)

    assert error.value.code == "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT"


def test_session_recovery_rejects_snapshot_from_another_session(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    other_id = "00000000-0000-0000-0000-000000000002"
    store.create(
        manifest_fingerprint=FINGERPRINT,
        geometry_family_id=V7_STANDARD_GEOMETRY_FAMILY_ID,
        sources=_sources(),
        session_id=other_id,
    )
    first_path = store._state_path(SESSION_ID)
    other_path = store._state_path(other_id)
    other_content = other_path.read_bytes()
    first_path.write_bytes(other_content)

    with pytest.raises(V7CalibrationSessionError) as error:
        store.read(SESSION_ID)

    assert error.value.code == "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT"
    assert other_path.read_bytes() == other_content


def test_drift_blocks_session_before_mutation_and_persists_the_block(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    drifted = list(_sources())
    drifted[0] = V7CalibrationSessionSource(
        source_id=drifted[0].source_id,
        source_checksum_sha256="f" * 64,
        corpus_case_id=drifted[0].corpus_case_id,
        split=drifted[0].split,
        geometry_family_id=drifted[0].geometry_family_id,
    )

    with pytest.raises(V7CalibrationSessionError) as error:
        store.apply(
            SESSION_ID,
            _operation("00000000-0000-0000-0000-000000000041"),
            current_sources=drifted,
        )

    assert error.value.code == "V7_CALIBRATION_SESSION_SOURCE_DRIFT"
    blocked_session = _store(tmp_path).read(SESSION_ID)
    assert blocked_session.status is V7CalibrationSessionStatus.BLOCKED_SOURCE_DRIFT


def test_capture_group_unavailable_and_immutable_export(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _create(store)
    session, _ = store.apply(
        SESSION_ID,
        V7CalibrationSessionOperation(
            operation_id="00000000-0000-0000-0000-000000000051",
            expected_revision=0,
            kind=V7CalibrationSessionOperationKind.SET_CAPTURE_GROUP,
            source_id="777/source-0.jpg",
            capture_group_id="take-a",
        ),
        current_sources=_sources(),
    )
    session, _ = store.apply(
        SESSION_ID,
        V7CalibrationSessionOperation(
            operation_id="00000000-0000-0000-0000-000000000052",
            expected_revision=session.revision,
            kind=V7CalibrationSessionOperationKind.UNAVAILABLE,
            source_id="777/source-0.jpg",
            position_index=8,
        ),
        current_sources=_sources(),
    )

    first = store.export(SESSION_ID, expected_revision=session.revision, current_sources=_sources())
    second = store.export(
        SESSION_ID, expected_revision=session.revision, current_sources=_sources()
    )

    assert first.path == second.path
    assert first.export_checksum_sha256 == second.export_checksum_sha256
    assert first.path.read_text(encoding="utf-8")
    loaded = store.read(SESSION_ID)
    unavailable = next(
        item
        for item in loaded.slots
        if item.source_id == "777/source-0.jpg" and item.position_index == 8
    )
    assert unavailable.state is V7AnnotationState.UNAVAILABLE
    assert loaded.capture_groups == (("777/source-0.jpg", "take-a"),)


def test_export_recovers_from_interruption_before_atomic_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    session = _create(store)
    original_link = v7_calibration_sessions.os.link

    def interrupt_link(_source: Path, _destination: Path) -> None:
        raise OSError("simulated export interruption")

    monkeypatch.setattr(v7_calibration_sessions.os, "link", interrupt_link)
    with pytest.raises(OSError, match="simulated export interruption"):
        store.export(SESSION_ID, expected_revision=session.revision, current_sources=_sources())

    monkeypatch.setattr(v7_calibration_sessions.os, "link", original_link)
    current_sources = _sources()
    exported = store.export(
        SESSION_ID,
        expected_revision=session.revision,
        current_sources=current_sources,
    )

    assert exported.path.exists()
    assert list(exported.path.parent.glob("*.json")) == [exported.path]


@pytest.mark.skipif(
    v7_calibration_sessions.os.name != "nt",
    reason="extended-length paths are specific to Windows",
)
def test_windows_export_uses_extended_root_before_descendant_exceeds_max_path(
    tmp_path: Path,
) -> None:
    runtime_root = tmp_path / ("runtime-" + "x" * 80)
    plain_sessions_root = runtime_root / "v7-label-geometry" / "sessions"
    temporary_name = "." + "a" * 24 + "." + "b" * 32 + ".tmp"
    assert len(str(plain_sessions_root)) < 240
    assert len(str(plain_sessions_root / SESSION_ID / "exports" / temporary_name)) > 260

    store = V7CalibrationSessionStore(runtime_root)
    assert str(store._sessions_root).startswith("\\\\?\\")
    session = _create(store)
    exported = store.export(
        SESSION_ID,
        expected_revision=session.revision,
        current_sources=_sources(),
    )

    assert exported.path.exists()
    assert V7CalibrationSessionStore(runtime_root).read(SESSION_ID).revision == session.revision


def test_lock_open_failure_releases_the_process_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = _store(tmp_path)
    original_open = Path.open
    failed = False

    def fail_once(path: Path, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        nonlocal failed
        if path.name == "session.lock" and not failed:
            failed = True
            raise PermissionError("simulated lock access failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_once)
    with pytest.raises(PermissionError, match="simulated lock access failure"):
        _create(store)

    session = _create(store)

    assert session.session_id == SESSION_ID
