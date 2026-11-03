"""Bounded Windows sharing retries retain the atomic trainer-file protocol."""

from __future__ import annotations

import ctypes
import errno
import json
import os
from pathlib import Path

import pytest
from game_predictor_worker.images import grid_training_child as child


def _sharing_error(code: int | None) -> OSError:
    error = PermissionError(errno.EACCES, "blocked destination")
    if code is not None:
        error.winerror = code
    return error


def test_uncontended_write_fsyncs_once_then_atomically_replaces_without_sleep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "progress.json"
    old = b'{"step": 487}'
    destination.write_bytes(old)
    value = {"format": child.PROGRESS_FORMAT, "step": 488, "label": "postęp"}
    events = []
    replace, fsync = child.os.replace, child.os.fsync

    def synced(descriptor: int) -> None:
        fsync(descriptor)
        events.append("fsync")

    def replaced(source: str, target: Path) -> None:
        assert events == ["fsync"]
        assert target == destination
        assert destination.read_bytes() == old
        assert json.loads(Path(source).read_text(encoding="utf-8")) == value
        events.append("replace")
        replace(source, target)

    def no_sleep(_seconds: float) -> None:
        pytest.fail("an uncontended atomic write must not wait")

    monkeypatch.setattr(child.os, "fsync", synced)
    monkeypatch.setattr(child.os, "replace", replaced)
    monkeypatch.setattr(child.time, "sleep", no_sleep)
    child.write_json_atomic(destination, value)
    assert events == ["fsync", "replace"]
    assert json.loads(destination.read_text(encoding="utf-8")) == value
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("code", [5, 32, 33])
def test_transient_sharing_retries_the_same_complete_temp_without_touching_old_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    destination = tmp_path / "progress.json"
    old = b'{"step": 487}'
    destination.write_bytes(old)
    value = {"format": child.PROGRESS_FORMAT, "step": 488}
    sources: list[str] = []
    delays: list[float] = []
    syncs: list[int] = []
    replace, fsync = child.os.replace, child.os.fsync

    def synced(descriptor: int) -> None:
        fsync(descriptor)
        syncs.append(descriptor)

    def blocked(source: str, target: Path) -> None:
        sources.append(source)
        assert target == destination
        assert destination.read_bytes() == old
        assert json.loads(Path(source).read_text(encoding="utf-8")) == value
        if len(sources) < 3:
            raise _sharing_error(code)
        replace(source, target)

    monkeypatch.setattr(child.os, "fsync", synced)
    monkeypatch.setattr(child.os, "replace", blocked)
    monkeypatch.setattr(child.time, "sleep", delays.append)
    child.write_json_atomic(destination, value)
    assert len(sources) == 3 and len(set(sources)) == 1
    assert len(syncs) == 1
    assert delays == [0.01, 0.02]
    assert json.loads(destination.read_text(encoding="utf-8")) == value
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("code", [5, 32, 33])
def test_permanent_sharing_stops_at_seven_attempts_and_cleans_only_its_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    destination = tmp_path / "progress.json"
    old = b'{"step":487,"budget":{"remainingSteps":7512}}'
    destination.write_bytes(old)
    sources: list[str] = []
    delays: list[float] = []
    removed: list[Path] = []
    error = _sharing_error(code)
    unlink = Path.unlink

    def blocked(source: str, target: Path) -> None:
        sources.append(source)
        assert target == destination
        assert destination.read_bytes() == old
        assert json.loads(Path(source).read_text(encoding="utf-8")) == {"step": 488}
        raise error

    def cleanup(path: Path, *, missing_ok: bool = False) -> None:
        removed.append(path)
        assert path != destination
        unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(child.os, "replace", blocked)
    monkeypatch.setattr(child.time, "sleep", delays.append)
    monkeypatch.setattr(Path, "unlink", cleanup)
    with pytest.raises(PermissionError) as caught:
        child.write_json_atomic(destination, {"step": 488})
    assert caught.value is error
    assert len(sources) == 7 and len(set(sources)) == 1
    assert delays == [0.01, 0.02, 0.04, 0.08, 0.16, 0.16]
    assert sum(delays) == pytest.approx(0.47)
    assert removed == [Path(sources[0])]
    assert destination.read_bytes() == old
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.parametrize("code", [None, 2, 80, 87])
def test_errno_only_access_denial_and_other_windows_errors_propagate_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: int | None
) -> None:
    destination = tmp_path / "progress.json"
    destination.write_text('{"step":487}', encoding="utf-8")
    error = _sharing_error(code)
    sources: list[str] = []
    delays: list[float] = []

    def blocked(source: str, _target: Path) -> None:
        sources.append(source)
        raise error

    monkeypatch.setattr(child.os, "replace", blocked)
    monkeypatch.setattr(child.time, "sleep", delays.append)
    with pytest.raises(PermissionError) as caught:
        child.write_json_atomic(destination, {"step": 488})
    assert caught.value is error
    assert len(sources) == 1 and not delays
    assert json.loads(destination.read_text(encoding="utf-8")) == {"step": 487}
    assert list(tmp_path.iterdir()) == [destination]


@pytest.mark.skipif(os.name != "nt", reason="requires an actual Windows file-sharing handle")
def test_real_windows_reader_without_share_delete_releases_before_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ctypes import wintypes

    destination = tmp_path / "progress.json"
    old = b'{"step":487}'
    destination.write_bytes(old)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create = kernel.CreateFileW
    create.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    create.restype = wintypes.HANDLE
    close = kernel.CloseHandle
    close.argtypes = [wintypes.HANDLE]
    close.restype = wintypes.BOOL
    # GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE (no FILE_SHARE_DELETE),
    # OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL. This is a real OS sharing constraint.
    handle = create(str(destination), 0x80000000, 0x1 | 0x2, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    released = False
    failures: list[int] = []
    delays: list[float] = []
    replace, sleep = child.os.replace, child.time.sleep

    def observed_replace(source: str, target: Path) -> None:
        try:
            replace(source, target)
        except OSError as error:
            failures.append(error.winerror)
            assert destination.read_bytes() == old
            raise

    def release_reader(seconds: float) -> None:
        nonlocal released
        delays.append(seconds)
        if not released:
            assert close(handle), ctypes.get_last_error()
            released = True
        sleep(seconds)

    try:
        monkeypatch.setattr(child.os, "replace", observed_replace)
        monkeypatch.setattr(child.time, "sleep", release_reader)
        value = {"format": child.PROGRESS_FORMAT, "attempt": 1, "step": 488}
        child.write_json_atomic(destination, value)
        assert released and len(failures) == 1 and failures[0] in (5, 32, 33)
        assert delays == [0.01]
        assert json.loads(destination.read_text(encoding="utf-8")) == value
        assert list(tmp_path.iterdir()) == [destination]
    finally:
        if not released:
            assert close(handle), ctypes.get_last_error()
