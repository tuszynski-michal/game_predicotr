"""Durable symbol-state and artifact boundaries."""

import os
import subprocess
import sys

import pytest
from game_predictor_worker.vision_lab.annotations import exclusive
from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore
from test_vision_lab_symbol_labels import label, symbols


def test_backup_restore_and_fresh_process(tmp_path):
    store, source = symbols(tmp_path)
    store.mutate(label(store, source))
    backup = store.backup()
    assert store.backup() == backup
    target = tmp_path / "restored"
    restored = store.restore(backup.backup_id, target)
    assert restored.list_labels().items == store.list_labels().items
    store.restore(backup.backup_id, target)
    code = (
        "from pathlib import Path; "
        "from game_predictor_worker.vision_lab.catalog import Catalog; "
        "from game_predictor_worker.vision_lab.annotations import AnnotationStore; "
        "from game_predictor_worker.vision_lab.symbol_store import SymbolLabelStore; import sys; "
        "print(SymbolLabelStore(Path(sys.argv[1]),AnnotationStore(Path(sys.argv[2]),"
        "Catalog(Path(sys.argv[3])))).list_labels().total)"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            code,
            str(target),
            str(store.annotations.root),
            str(store.catalog.root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        env=os.environ.copy(),
        check=True,
    )
    assert result.stdout.strip() == "1"


def test_cas_conflict_and_atomic_failed_state_write(tmp_path, monkeypatch):
    store, source = symbols(tmp_path)
    request = label(store, source)
    before = (store.root / "state.json").read_bytes()
    import game_predictor_worker.vision_lab.symbol_store as module

    original = module.write_atomic
    monkeypatch.setattr(module, "write_atomic", lambda *a: (_ for _ in ()).throw(OSError("crash")))
    with pytest.raises(OSError, match="crash"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before
    monkeypatch.setattr(module, "write_atomic", original)
    assert store.mutate(request).label_valid
    request.symbol_id = "other"
    with pytest.raises(ValueError, match="REQUEST_ID_CONFLICT"):
        store.mutate(request)


def test_geometry_lock_blocks_symbol_writer(tmp_path):
    store, source = symbols(tmp_path)
    request = label(store, source)
    with exclusive(store.annotations.root), pytest.raises(ValueError, match="BUSY"):
        store.mutate(request)
    assert store.mutate(request).label_valid


def test_overlap_and_tampered_backup(tmp_path):
    store, source = symbols(tmp_path)
    with pytest.raises(ValueError, match="OVERLAP"):
        SymbolLabelStore(store.annotations.root / "nested", store.annotations)
    store.mutate(label(store, source))
    backup = store.backup()
    (store.root / "backups" / backup.backup_id / "state.json").write_text("{}")
    with pytest.raises(ValueError, match="INTEGRITY"):
        store.restore(backup.backup_id, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_bundle_crash_before_publication_can_retry(tmp_path, monkeypatch, operation):
    from pathlib import Path

    store, source = symbols(tmp_path)
    store.mutate(label(store, source))
    backup = store.backup() if operation == "restore" else None
    original = Path.rename

    def crash(path, target):
        if path.name.startswith(".symbol-bundle-"):
            raise OSError("publication crash")
        return original(path, target)

    monkeypatch.setattr(Path, "rename", crash)
    with pytest.raises(OSError, match="publication crash"):
        if operation == "backup":
            store.backup()
        else:
            store.restore(backup.backup_id, tmp_path / "restored")
    assert not (tmp_path / "restored").exists()
    monkeypatch.setattr(Path, "rename", original)
    if operation == "backup":
        assert store.backup().revision == 3
    else:
        assert store.restore(backup.backup_id, tmp_path / "restored").list_labels().total == 1


def test_crop_publication_crash_has_no_approval(tmp_path, monkeypatch):
    import game_predictor_worker.vision_lab.symbol_store as module

    store, source = symbols(tmp_path)
    request = label(store, source)
    before = (store.root / "state.json").read_bytes()
    original = module.os.link
    monkeypatch.setattr(module.os, "link", lambda *a: (_ for _ in ()).throw(OSError("crop crash")))
    with pytest.raises(OSError, match="crop crash"):
        store.mutate(request)
    assert (store.root / "state.json").read_bytes() == before
    monkeypatch.setattr(module.os, "link", original)
    assert store.mutate(request).label_valid


def test_real_geometry_writer_fences_symbol_write(tmp_path):
    store, source = symbols(tmp_path)
    request = label(store, source)
    ready = tmp_path / "ready"
    release = tmp_path / "release"
    code = """
import sys, time
from pathlib import Path
from game_predictor_worker.vision_lab.annotations import exclusive
with exclusive(Path(sys.argv[1])):
    Path(sys.argv[2]).touch()
    deadline=time.monotonic()+10
    while not Path(sys.argv[3]).exists() and time.monotonic()<deadline:
        time.sleep(.02)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", code, str(store.annotations.root), str(ready), str(release)]
    )
    import time

    try:
        deadline = time.monotonic() + 8
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists()
        with pytest.raises(ValueError, match="BUSY"):
            store.mutate(request)
    finally:
        release.touch()
        process.wait(timeout=12)
    assert process.returncode == 0
    assert store.mutate(request).label_valid
