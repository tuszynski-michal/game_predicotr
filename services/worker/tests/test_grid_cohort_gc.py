"""Tiny owned file GC preview/revalidation/quarantine; no operator cleanup."""

import os
import shutil
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from game_predictor_api.application.storage_gc import StorageGcArtifactStore
from game_predictor_api.domain.storage_retention import (
    CohortAssetReferenceState,
    StorageRetentionPolicy,
)
from game_predictor_worker import storage_gc as worker
from game_predictor_worker.filesystem import long_path_aware
from sqlalchemy.orm import sessionmaker

NOW = datetime(2026, 10, 16, tzinfo=UTC)
OLD = NOW - timedelta(hours=25)


@pytest.fixture(autouse=True)
def owned_long_path_cleanup(tmp_path):
    identity = tmp_path.stat().st_dev, tmp_path.stat().st_ino
    marker = str(uuid4())
    (tmp_path / "fixture-owner").write_text(marker, encoding="utf-8")
    yield
    assert identity == (tmp_path.stat().st_dev, tmp_path.stat().st_ino)
    assert (tmp_path / "fixture-owner").read_text(encoding="utf-8") == marker
    target = long_path_aware(tmp_path)
    assert all(not p.is_symlink() and not p.is_junction() for p in (target, *target.rglob("*")))
    shutil.rmtree(target)


class Repository:
    def __init__(self, state):
        self.state, self.active, self.entries = state, False, 0

    def normalization_dependency_statuses(self, keys):
        return {}

    def browser_staging_sources(self):
        return ()

    @contextmanager
    def cohort_asset_gc_guard(self, relative):
        assert not self.active
        self.active = True
        self.entries += 1
        try:
            yield self.state
        finally:
            self.active = False


def fixture(tmp_path, *, long=False):
    artifact = tmp_path / ("artifacts-" + "x" * 80 if long else "artifacts")
    imports = tmp_path / "imports"
    long_path_aware(artifact).mkdir(parents=True)
    imports.mkdir()
    relative = f"data/grid-training-cohorts/{uuid4()}/{uuid4()}/originals/{'b' * 64}.jpg"
    target = long_path_aware(artifact / relative)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"synthetic-only-not-a-jpeg")
    os.utime(target, (OLD.timestamp(), OLD.timestamp()))
    repo = Repository(CohortAssetReferenceState(False, OLD))
    handler = worker.StorageGcHandler(sessionmaker(), artifact, imports)
    handler._repository = repo
    scan = StorageGcArtifactStore(artifact, imports).scan(
        repo, policy=StorageRetentionPolicy(), now=NOW
    )
    entry = {
        "rootKind": "artifact",
        "relativePath": relative,
        "artifactClass": "grid_cohort_asset",
        "sizeBytes": scan.entries[0].size_bytes,
        "observationChecksumSha256": scan.entries[0].observation_checksum_sha256,
    }
    return artifact, imports, target, relative, repo, handler, entry


def test_preview_retained_reference_latest_receipt_and_unresolved_are_protected(tmp_path):
    artifact, imports, target, relative, repo, _, _ = fixture(tmp_path)
    store = StorageGcArtifactStore(artifact, imports)
    for state, reason in (
        (CohortAssetReferenceState(True, OLD), "retained_cohort_reference"),
        (CohortAssetReferenceState(False, NOW), "retention_not_elapsed"),
        (CohortAssetReferenceState(False, None, True), "cohort_reference_unresolved"),
    ):
        repo.state = state
        scan = store.scan(repo, policy=StorageRetentionPolicy(), now=NOW)
        assert scan.entries == ()
        assert reason in {value.value for value in scan.protected[0].protection_reasons}
    repo.state = CohortAssetReferenceState(False, OLD)
    scan = store.scan(repo, policy=StorageRetentionPolicy(), now=NOW)
    assert len(scan.entries) == 1 and target.exists() and scan.entries[0].relative_path == relative


def test_missing_optional_adapter_keeps_legacy_namespace_behavior(tmp_path):
    artifact, imports, target, _, _, handler, entry = fixture(tmp_path)

    class Legacy:
        def normalization_dependency_statuses(self, keys):
            return {}

        def browser_staging_sources(self):
            return ()

    repository = Legacy()
    assert (
        not StorageGcArtifactStore(artifact, imports)
        .scan(repository, policy=StorageRetentionPolicy(), now=NOW)
        .entries
    )
    handler._repository = repository
    assert handler._process_entry(
        uuid4(), 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW
    ) == ("protectedCount", 0)
    assert target.exists()


def test_fresh_reference_overrides_preview_and_batch_observation(tmp_path, monkeypatch):
    _, _, target, _, repo, handler, entry = fixture(tmp_path)
    repo.state = CohortAssetReferenceState(True, NOW)
    assert handler._current_observations([entry], NOW) == {}
    monkeypatch.setattr(
        worker.os, "replace", lambda *a: pytest.fail("Referenced file cannot enter quarantine")
    )
    assert handler._process_entry(
        uuid4(), 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW
    ) == ("protectedCount", 0)
    assert target.exists() and not repo.active


def test_long_path_orphan_quarantine_and_delete_hold_the_same_guard(tmp_path, monkeypatch):
    _, _, target, _, repo, handler, entry = fixture(tmp_path, long=True)
    assert len(str(target)) > 260
    original = worker._delete_trash

    def remove(path):
        assert repo.active
        original(path)

    monkeypatch.setattr(worker, "_delete_trash", remove)
    result = handler._process_entry(
        uuid4(), 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW
    )
    assert (
        result == ("deletedCount", entry["sizeBytes"]) and not target.exists() and not repo.active
    )


def test_quarantine_retry_revalidates_new_reference_and_latest_dependency(tmp_path, monkeypatch):
    artifact, _, target, relative, repo, handler, entry = fixture(tmp_path)
    run = uuid4()
    original = worker._delete_trash

    def crash(path):
        assert repo.active
        raise OSError("synthetic crash after quarantine")

    monkeypatch.setattr(worker, "_delete_trash", crash)
    with pytest.raises(worker.JobHandlerError):
        handler._process_entry(run, 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW)
    trash = worker._trash_path(artifact, run, 0, relative)
    assert not target.exists() and trash.exists() and not repo.active
    monkeypatch.setattr(worker, "_delete_trash", original)
    for state in (
        CohortAssetReferenceState(True, NOW),
        CohortAssetReferenceState(False, NOW),
        CohortAssetReferenceState(False, None, True),
    ):
        repo.state = state
        assert handler._process_entry(
            run, 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW
        ) == ("protectedCount", 0)
        assert trash.exists()
    repo.state = CohortAssetReferenceState(False, OLD)
    assert handler._process_entry(
        run, 0, entry, current={}, policy=StorageRetentionPolicy(), now=NOW
    ) == ("deletedCount", entry["sizeBytes"])
    assert not trash.exists()
