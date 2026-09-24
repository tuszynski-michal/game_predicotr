from __future__ import annotations

import hashlib
import json
import os
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any


def _load_script() -> Any:
    path = Path(__file__).parents[3] / "scripts" / "preview_legacy_game_managed_asset_gc.py"
    spec = spec_from_file_location("preview_legacy_game_managed_asset_gc", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


def test_managed_relative_normalizes_only_safe_managed_paths() -> None:
    assert SCRIPT._managed_relative("crops/source-direct-v19/a.png") == (
        "data/crops/source-direct-v19/a.png"
    )
    assert SCRIPT._managed_relative("data/originals/ab/source.jpg") == (
        "data/originals/ab/source.jpg"
    )
    assert SCRIPT._managed_relative("artifacts/data/models/777/model.onnx") == (
        "data/models/777/model.onnx"
    )
    assert SCRIPT._managed_relative("../outside.jpg") is None
    assert SCRIPT._managed_relative("C:/outside.jpg") is None


def test_path_values_only_returns_path_named_members() -> None:
    payload = {
        "checksum": "ignored",
        "source": {"relativePath": "originals/aa/source.jpg"},
        "cells": [
            {"cropRelativePath": "crops/runtime-v1/a.png", "label": "ignored"},
            {"nested": {"file_path": "data/models/new-siedem/model.onnx"}},
        ],
    }

    assert list(SCRIPT._path_values(payload)) == [
        "originals/aa/source.jpg",
        "crops/runtime-v1/a.png",
        "data/models/new-siedem/model.onnx",
    ]


def test_measure_tree_separates_live_file_and_has_stable_fingerprint(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    candidate_root = artifact_root / "data" / "originals"
    candidate_root.mkdir(parents=True)
    kept = candidate_root / "kept.jpg"
    removed = candidate_root / "removed.jpg"
    kept.write_bytes(b"kept")
    removed.write_bytes(b"removed")
    first_details = tmp_path / "first.jsonl"
    second_details = tmp_path / "second.jsonl"

    with first_details.open("w", encoding="utf-8", newline="\n") as handle:
        first = SCRIPT._measure_tree(
            artifact_root,
            "data/originals",
            {"data/originals/kept.jpg"},
            handle,
        )
    with second_details.open("w", encoding="utf-8", newline="\n") as handle:
        second = SCRIPT._measure_tree(
            artifact_root,
            "data/originals",
            {"data/originals/kept.jpg"},
            handle,
        )

    assert first == second
    assert first["candidateFiles"] == 1
    assert first["candidateBytes"] == len(b"removed")
    assert first["protectedFiles"] == 1
    assert "removed.jpg" in first_details.read_text(encoding="utf-8")
    assert "kept.jpg" not in first_details.read_text(encoding="utf-8")


def test_whole_tree_candidate_is_compact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    candidate_root = artifact_root / "data" / "crops" / "source-direct-v19"
    candidate_root.mkdir(parents=True)
    (candidate_root / "one.png").write_bytes(b"one")
    (candidate_root / "two.png").write_bytes(b"two")
    details = tmp_path / "details.jsonl"

    with details.open("w", encoding="utf-8", newline="\n") as handle:
        summary = SCRIPT._measure_tree(
            artifact_root,
            "data/crops/source-direct-v19",
            set(),
            handle,
        )

    lines = details.read_text(encoding="utf-8").splitlines()
    assert summary["wholeTreeCandidate"] is True
    assert summary["candidateFiles"] == 2
    assert len(lines) == 1
    assert '"wholeTreeCandidate":true' in lines[0]


def test_source_groups_preserve_entire_live_source_directory(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    root = artifact_root / "data" / "crops" / "source-direct-v19" / "aa"
    live_group = root / ("a" * 64)
    orphan_group = root / ("b" * 64)
    (live_group / "board-00").mkdir(parents=True)
    (orphan_group / "board-00").mkdir(parents=True)
    (live_group / "board-00" / "source-context.png").write_bytes(b"live")
    (orphan_group / "board-00" / "source-context.png").write_bytes(b"orphan")
    details = tmp_path / "details.jsonl"

    live_path = "data/crops/source-direct-v19/aa/" + "a" * 64 + "/board-00/source-context.png"
    with details.open("w", encoding="utf-8", newline="\n") as handle:
        summary = SCRIPT._measure_source_groups(
            artifact_root,
            "data/crops/source-direct-v19",
            {live_path},
            handle,
        )

    assert summary["candidateGroups"] == 1
    assert summary["protectedGroups"] == 1
    assert summary["candidateFiles"] == 1
    contents = details.read_text(encoding="utf-8")
    assert "b" * 64 in contents
    assert "a" * 64 not in contents


def test_execution_preview_requires_exact_confirmation_and_verified_details(
    tmp_path: Path,
) -> None:
    details = tmp_path / "preview.paths.jsonl"
    details.write_text('{"path":"data/originals/a.jpg","size":1,"mtimeNs":2}\n')
    payload = {
        "policy": SCRIPT.POLICY,
        "createdAtUnix": 1,
        "gameId": SCRIPT.LEGACY_ID,
        "protectedGameId": SCRIPT.PROTECTED_ID,
        "artifactRoot": str(tmp_path / "artifacts"),
        "operatorRootProtected": str(SCRIPT.PROTECTED_OPERATOR_ROOT),
        "details": {
            "path": str(details),
            "sha256": hashlib.sha256(details.read_bytes()).hexdigest(),
        },
        "deletionExecuted": False,
    }
    fingerprint = {key: value for key, value in payload.items() if key != "createdAtUnix"}
    payload["previewSha256"] = SCRIPT._canonical_sha(fingerprint)
    preview = tmp_path / "preview.json"
    preview.write_text(json.dumps(payload), encoding="utf-8")

    loaded, loaded_details = SCRIPT._load_execution_preview(
        preview,
        expected_preview_sha256=payload["previewSha256"],
        confirmation=SCRIPT._required_confirmation(payload["previewSha256"]),
    )

    assert loaded == payload
    assert loaded_details == details


def test_execution_preview_rejects_approximate_confirmation(tmp_path: Path) -> None:
    details = tmp_path / "preview.paths.jsonl"
    details.write_text("", encoding="utf-8")
    payload = {
        "policy": SCRIPT.POLICY,
        "gameId": SCRIPT.LEGACY_ID,
        "protectedGameId": SCRIPT.PROTECTED_ID,
        "details": {
            "path": str(details),
            "sha256": hashlib.sha256(details.read_bytes()).hexdigest(),
        },
        "deletionExecuted": False,
    }
    payload["previewSha256"] = SCRIPT._canonical_sha(payload)
    preview = tmp_path / "preview.json"
    preview.write_text(json.dumps(payload), encoding="utf-8")

    try:
        SCRIPT._load_execution_preview(
            preview,
            expected_preview_sha256=payload["previewSha256"],
            confirmation="delete it",
        )
    except SCRIPT.PreviewBlocked as error:
        assert "exact" in str(error)
    else:
        raise AssertionError("approximate confirmation must be rejected")


def test_record_liveness_protects_entire_candidate_tree() -> None:
    record = {
        "root": "data/crops/source-direct-v19/aa/source",
        "wholeTreeCandidate": True,
    }

    assert SCRIPT._record_is_live(
        record,
        {"data/crops/source-direct-v19/aa/source/board-00/crop.png"},
    )
    assert not SCRIPT._record_is_live(
        record,
        {"data/crops/source-direct-v19/aa/other/board-00/crop.png"},
    )


def test_quarantine_delete_is_resumable_after_atomic_move(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    source = artifact_root / "data" / "models" / "777"
    source.mkdir(parents=True)
    (source / "model.bin").write_bytes(b"model")
    nested = source / "candidate"
    nested.mkdir()
    (nested / "weights.bin").write_bytes(b"weights")
    record = {
        "root": "data/models/777",
        "wholeTreeCandidate": True,
        "candidateFiles": 2,
        "candidateBytes": 12,
        "treeSha256": SCRIPT._tree_fingerprint(artifact_root, "data/models/777")[2],
    }
    SCRIPT._verify_record(artifact_root, record)
    quarantine_root = tmp_path / "quarantine"
    quarantine = SCRIPT._quarantine_target(quarantine_root, record["root"])
    quarantine.parent.mkdir(parents=True)
    source.rename(quarantine)

    SCRIPT._delete_quarantined(quarantine)
    SCRIPT._delete_quarantined(quarantine)

    assert not source.exists()
    assert not quarantine.exists()


def test_rmtree_handler_only_ignores_already_missing_entries() -> None:
    SCRIPT._handle_rmtree_error(None, "missing", FileNotFoundError())

    try:
        SCRIPT._handle_rmtree_error(None, "blocked", PermissionError())
    except PermissionError:
        pass
    else:
        raise AssertionError("permission failures must remain fatal")


def test_native_long_path_uses_windows_extended_prefix(tmp_path: Path) -> None:
    native = str(SCRIPT._native_long_path(tmp_path / "nested"))

    if os.name == "nt":
        assert native.startswith("\\\\?\\")
    else:
        assert native == str((tmp_path / "nested").resolve())


def test_detached_managed_root_preserves_logical_data_paths(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    active = artifact_root / "data"
    detached = artifact_root / "data.detached-test"
    active.mkdir(parents=True)
    target = detached / "models" / "777"
    target.mkdir(parents=True)
    (target / "model.bin").write_bytes(b"model")

    selected = SCRIPT._validate_managed_data_root(artifact_root, detached)
    resolved = SCRIPT._artifact_path(
        artifact_root,
        "data/models/777/model.bin",
        managed_data_root=selected,
    )

    assert selected == detached.resolve()
    assert resolved == (target / "model.bin").resolve()
    assert (
        SCRIPT._tree_fingerprint(
            artifact_root,
            "data/models/777",
            managed_data_root=selected,
        )[0]
        == 1
    )


def test_detached_managed_root_requires_empty_active_root(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    active = artifact_root / "data"
    detached = artifact_root / "data.detached-test"
    active.mkdir(parents=True)
    detached.mkdir()
    (active / "new-file.bin").write_bytes(b"new")

    try:
        SCRIPT._validate_managed_data_root(artifact_root, detached)
    except SCRIPT.PreviewBlocked as error:
        assert "must remain empty" in str(error)
    else:
        raise AssertionError("non-empty active data root must block detached GC")


def test_execution_root_binding_rejects_a_different_directory(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    active = artifact_root / "data"
    first = artifact_root / "data.detached-first"
    second = artifact_root / "data.detached-second"
    active.mkdir(parents=True)
    first.mkdir()
    second.mkdir()
    state_path = tmp_path / "execution.json"
    state = {
        "nextLine": 0,
        "pending": None,
        "managedDataRoot": SCRIPT._managed_root_descriptor(first),
    }

    try:
        SCRIPT._bind_execution_root(
            state_path,
            state,
            records=[],
            artifact_root=artifact_root,
            managed_data_root=second,
            quarantine_root=tmp_path / "quarantine",
        )
    except SCRIPT.PreviewBlocked as error:
        assert "another managed data root" in str(error)
    else:
        raise AssertionError("execution root binding must be immutable")


def test_stale_intention_before_detach_is_discarded(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    active = artifact_root / "data"
    detached = artifact_root / "data.detached-test"
    active.mkdir(parents=True)
    source = detached / "originals" / "a.jpg"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"a")
    record = {
        "path": "data/originals/a.jpg",
        "size": 1,
        "mtimeNs": source.stat().st_mtime_ns,
    }
    state_path = tmp_path / "preview.execution.json"
    state = {
        "policy": SCRIPT.EXECUTION_POLICY,
        "previewSha256": "sha",
        "nextLine": 0,
        "pending": None,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({**state, "pending": {"line": 0, "target": record["path"]}}),
        encoding="utf-8",
    )

    reconciled = SCRIPT._reconcile_interrupted_state_write(
        state_path,
        state,
        expected_preview_sha256="sha",
        records=[record],
        artifact_root=artifact_root,
        managed_data_root=detached,
        quarantine_root=tmp_path / "quarantine",
    )

    assert reconciled["pending"] is None
    assert source.exists()
    assert not temporary.exists()


def test_detached_target_is_promoted_to_pending_recovery(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    active = artifact_root / "data"
    detached = artifact_root / "data.detached-test"
    active.mkdir(parents=True)
    detached.mkdir()
    record = {"path": "data/originals/a.jpg", "size": 1, "mtimeNs": 1}
    state_path = tmp_path / "preview.execution.json"
    state = {
        "policy": SCRIPT.EXECUTION_POLICY,
        "previewSha256": "sha",
        "nextLine": 0,
        "pending": None,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    temporary.write_text(
        json.dumps({**state, "pending": {"line": 0, "target": record["path"]}}),
        encoding="utf-8",
    )
    quarantine_root = tmp_path / "quarantine"
    quarantine = SCRIPT._quarantine_target(quarantine_root, record["path"])
    quarantine.parent.mkdir(parents=True)
    quarantine.write_bytes(b"a")

    reconciled = SCRIPT._reconcile_interrupted_state_write(
        state_path,
        state,
        expected_preview_sha256="sha",
        records=[record],
        artifact_root=artifact_root,
        managed_data_root=detached,
        quarantine_root=quarantine_root,
    )

    assert reconciled["pending"] == {"line": 0, "target": record["path"]}
    assert json.loads(state_path.read_text(encoding="utf-8"))["pending"] == {
        "line": 0,
        "target": record["path"],
    }


def test_live_path_cache_requires_matching_wal_and_checksum(tmp_path: Path) -> None:
    cache = tmp_path / "preview.live-paths.txt"
    descriptor = SCRIPT._write_live_path_cache(
        cache,
        {"data/originals/b.jpg", "data/originals/a.jpg"},
    )
    descriptor["walLsn"] = "0/123"

    assert SCRIPT._load_live_path_cache(
        descriptor,
        cache_path=cache,
        expected_wal_lsn="0/123",
    ) == {"data/originals/a.jpg", "data/originals/b.jpg"}
    assert (
        SCRIPT._load_live_path_cache(
            descriptor,
            cache_path=cache,
            expected_wal_lsn="0/124",
        )
        is None
    )

    cache.write_text("data/originals/changed.jpg\n", encoding="utf-8")
    try:
        SCRIPT._load_live_path_cache(
            descriptor,
            cache_path=cache,
            expected_wal_lsn="0/123",
        )
    except SCRIPT.PreviewBlocked as error:
        assert "checksum" in str(error)
    else:
        raise AssertionError("changed live-path cache must be rejected")


class _FakeGuardConnection:
    """Fails any query beyond the per-game storage check, to prove ordering."""

    def __init__(self, per_game_storage_count: int) -> None:
        self._per_game_storage_count = per_game_storage_count
        self.scalar_calls: list[str] = []

    def scalar(self, statement: Any) -> int:
        text_value = str(statement)
        self.scalar_calls.append(text_value)
        if "game_storage_locations" in text_value:
            return self._per_game_storage_count
        raise AssertionError(f"unexpected scalar query reached the database: {text_value}")

    def execute(self, statement: Any, *_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError(f"unexpected execute query reached the database: {statement}")


def test_operation_guard_refuses_before_any_scan_when_per_game_storage_exists() -> None:
    connection = _FakeGuardConnection(per_game_storage_count=1)

    try:
        SCRIPT._operation_guard(connection)
    except SCRIPT.PreviewBlocked as error:
        assert "LEGACY_GC_REFUSED_PER_GAME_STORAGE_PRESENT" in str(error)
    else:
        raise AssertionError("a per-game (V2) storage row must refuse the scan")
    # Exactly the one guard query ran; no deletion-operation, identity or job
    # query (and no preview/detail file write, since none of those queries
    # ever run) happened before the refusal.
    assert len(connection.scalar_calls) == 1


def test_operation_guard_proceeds_past_the_new_check_when_every_game_is_legacy() -> None:
    connection = _FakeGuardConnection(per_game_storage_count=0)

    try:
        SCRIPT._operation_guard(connection)
    except AssertionError as error:
        # The fake raises AssertionError, not PreviewBlocked, once control
        # reaches the pre-existing deletion-operation query — proving the
        # new check does not block a database with only legacy storage.
        assert "unexpected execute query reached the database" in str(error)
    else:
        raise AssertionError(
            "the pre-existing deletion-operation guard must still run "
            "when no game uses per-game storage"
        )
