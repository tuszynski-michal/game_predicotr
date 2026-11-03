"""Quarantine recovery keeps newly referenced files and holds the deletion fence."""

import json
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from game_predictor_api.application import cleanup
from game_predictor_api.application.cleanup import CleanupService, ManagedCleanupArtifactStore
from game_predictor_api.domain.cleanup import CleanupConflictError

KEY = "a" * 64
PATHS = ("data/a/photo.jpg", "data/b/crop.jpg")


class Guard:
    def __init__(self, protected):
        self.protected = protected
        self.active = False
        self.calls = []

    @contextmanager
    def __call__(self, paths):
        assert not self.active
        self.calls.append(paths)
        self.active = True
        try:
            yield self.protected
        finally:
            self.active = False


def seeded(tmp_path, guard=None):
    root = tmp_path.resolve()
    for path in PATHS:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.encode())
    store = ManagedCleanupArtifactStore(root, retention_guard=guard)
    store.quarantine(KEY, PATHS)
    return root, store, root / "cleanup-quarantine" / KEY


def test_completed_recovery_retains_new_manifest_reference_and_retries_after_restart(
    tmp_path, caplog, monkeypatch
):
    guard = Guard(True)
    root, store, quarantine = seeded(tmp_path, guard)
    receipt = (quarantine / "receipt.json").read_bytes()
    assert store.recover({KEY}) == (KEY,)
    assert store.retained_operation_keys == frozenset({KEY})
    assert (quarantine / "receipt.json").read_bytes() == receipt
    assert all((quarantine / path).read_bytes() == path.encode() for path in PATHS)
    assert all(not (root / path).exists() for path in PATHS)
    assert "SOURCE_REPLACEMENT_REFERENCED" in caplog.text
    assert "physical deletion deferred" in caplog.text
    assert guard.calls == [PATHS]
    assert not guard.active

    # A new process has only the durable receipt and must obtain a fresh proof.
    retry_guard = Guard(False)
    restarted = ManagedCleanupArtifactStore(root, retention_guard=retry_guard)
    original_rmtree = cleanup.shutil.rmtree
    removed = []

    def checked_rmtree(path, *args, **kwargs):
        assert retry_guard.active  # no check-release-delete window
        removed.append(path)
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(cleanup.shutil, "rmtree", checked_rmtree)
    assert restarted.recover({KEY}) == ()
    assert retry_guard.calls == [PATHS]
    assert len(removed) == 1 and not quarantine.exists()
    assert not retry_guard.active and not restarted.retained_operation_keys
    assert restarted.recover({KEY}) == ()


@pytest.mark.parametrize("failure", ["exception", "no_proof"])
def test_guard_failure_never_deletes_quarantine(tmp_path, monkeypatch, failure):
    @contextmanager
    def unavailable(paths):
        assert paths == PATHS
        if failure == "exception":
            raise RuntimeError("retention database unavailable")
        yield None

    _, store, quarantine = seeded(tmp_path, unavailable)
    delete = Mock(side_effect=AssertionError("must not delete without proof"))
    monkeypatch.setattr(cleanup.shutil, "rmtree", delete)
    expected = RuntimeError if failure == "exception" else CleanupConflictError
    with pytest.raises(expected):
        store.recover({KEY})
    delete.assert_not_called()
    assert all((quarantine / path).exists() for path in PATHS)


@pytest.mark.parametrize(
    "receipt",
    [
        [],
        {"operationKey": "b" * 64, "movedPaths": list(PATHS)},
        {"operationKey": KEY, "movedPaths": "data/a/photo.jpg"},
        {"operationKey": KEY, "movedPaths": [42]},
        {"operationKey": KEY, "movedPaths": ["../outside"]},
        {"operationKey": KEY, "movedPaths": [PATHS[0], PATHS[0], PATHS[1]]},
        {"operationKey": KEY, "movedPaths": []},
        {"operationKey": KEY, "movedPaths": [PATHS[0]]},
        {"operationKey": KEY, "movedPaths": ["data/a/../a/photo.jpg", PATHS[1]]},
    ],
)
def test_malformed_or_incomplete_receipt_cannot_bypass_path_retention(
    tmp_path, monkeypatch, receipt
):
    guard = Guard(False)
    _, store, quarantine = seeded(tmp_path, guard)
    (quarantine / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
    delete = Mock(side_effect=AssertionError("invalid receipt cannot authorize deletion"))
    monkeypatch.setattr(cleanup.shutil, "rmtree", delete)
    with pytest.raises(CleanupConflictError):
        store.recover({KEY})
    assert guard.calls == []
    delete.assert_not_called()
    assert all((quarantine / path).exists() for path in PATHS)


def test_missing_receipt_and_unrecorded_file_fail_closed(tmp_path, monkeypatch):
    guard = Guard(False)
    _, store, quarantine = seeded(tmp_path, guard)
    (quarantine / "unexpected.bin").write_bytes(b"unrecorded")
    with pytest.raises(CleanupConflictError):
        store.finalize(KEY)
    assert guard.calls == [] and (quarantine / "unexpected.bin").exists()
    (quarantine / "receipt.json").unlink()
    with pytest.raises(CleanupConflictError):
        store.finalize(KEY)
    assert all((quarantine / path).exists() for path in PATHS)


def test_incomplete_recovery_restores_without_guard_and_never_overwrites(tmp_path):
    guard = Mock(side_effect=AssertionError("restore must not need a deletion proof"))
    root, store, quarantine = seeded(tmp_path, guard)
    assert store.recover(set()) == ()
    assert all((root / path).read_bytes() == path.encode() for path in PATHS)
    assert not quarantine.exists()
    store.quarantine(KEY, PATHS)
    current = root / PATHS[0]
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_bytes(b"new current file")
    with pytest.raises(CleanupConflictError):
        store.recover(set())
    assert current.read_bytes() == b"new current file"
    assert (quarantine / PATHS[0]).read_bytes() == PATHS[0].encode()
    guard.assert_not_called()


def test_legacy_filesystem_store_still_finalizes_and_service_keeps_deferred_keys(tmp_path):
    root, store, quarantine = seeded(tmp_path)
    assert store.finalize(KEY) is True
    assert not quarantine.exists()
    guard = Guard(True)
    _, store, quarantine = seeded(root, guard)
    service = CleanupService(Mock(), store)
    service._pending_quarantines.add(KEY)
    service.finalize_committed_artifacts()
    assert service._pending_quarantines == {KEY} and quarantine.exists()
    guard.protected = False
    service.finalize_committed_artifacts()
    assert not service._pending_quarantines and not quarantine.exists()
