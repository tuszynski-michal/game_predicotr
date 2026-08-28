import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from game_predictor_api.application.storage_gc import (
    BrowserStagingGcSource,
    StorageGcArtifactStore,
)
from game_predictor_api.domain.storage_retention import (
    StorageArtifactClass,
    StorageRetentionPolicy,
    StorageRootKind,
)

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)
OLD = NOW - timedelta(hours=25)


class GcSourceRepository:
    def __init__(self) -> None:
        self.statuses: dict[str, tuple[str, ...]] = {}
        self.staging: tuple[BrowserStagingGcSource, ...] = ()

    def normalization_dependency_statuses(self, execution_keys):  # type: ignore[no-untyped-def]
        return {key: self.statuses.get(key, ()) for key in execution_keys}

    def browser_staging_sources(self):  # type: ignore[no-untyped-def]
        return self.staging


def _old(path: Path) -> None:
    timestamp = OLD.timestamp()
    os.utime(path, (timestamp, timestamp))


def test_preview_includes_only_terminal_old_normalization_bitmaps(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts"
    imports = tmp_path / "imports"
    imports.mkdir()
    terminal_key = "a" * 64
    active_key = "b" * 64
    terminal = (
        artifact
        / "data"
        / "working"
        / "image-normalization-v1"
        / "aa"
        / terminal_key
        / "normalized.png"
    )
    active = terminal.parents[1] / active_key / "normalized.png"
    terminal.parent.mkdir(parents=True)
    active.parent.mkdir(parents=True)
    terminal.write_bytes(b"terminal")
    active.write_bytes(b"active")
    _old(terminal)
    _old(active)
    repository = GcSourceRepository()
    repository.statuses = {terminal_key: ("completed",), active_key: ("processing",)}

    scan = StorageGcArtifactStore(artifact, imports).scan(
        repository, policy=StorageRetentionPolicy(), now=NOW
    )

    assert [entry.relative_path for entry in scan.entries] == [
        terminal.relative_to(artifact).as_posix()
    ]
    assert scan.entries[0].artifact_class is StorageArtifactClass.NORMALIZATION_WORKING_BITMAP
    assert scan.entries[0].root_kind is StorageRootKind.ARTIFACT
    assert len(scan.protected) == 1


def test_staging_requires_a_verified_complete_managed_manifest(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts"
    imports = tmp_path / "imports"
    upload_id = uuid4()
    staging = imports / "browser-selections" / str(upload_id)
    staging.mkdir(parents=True)
    (staging / "00000001.jpg").write_bytes(b"staged")
    _old(staging / "00000001.jpg")
    _old(staging)
    original = artifact / "data" / "originals" / "aa" / ("a" * 64 + ".jpg")
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    original_checksum = hashlib.sha256(b"original").hexdigest()
    manifest = {
        "originals": [
            {
                "managedRelativePath": original.relative_to(artifact).as_posix(),
                "sizeBytes": len(b"original"),
                "checksumSha256": original_checksum,
            }
        ]
    }
    content = json.dumps(manifest).encode()
    manifest_path = artifact / "data" / "originals" / "manifests" / "job.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(content)
    repository = GcSourceRepository()
    repository.staging = (
        BrowserStagingGcSource(
            upload_id=upload_id,
            relative_path=f"browser-selections/{upload_id}",
            finalized_at=OLD,
            last_dependency_at=OLD,
            linked_import_exists=True,
            managed_originals_verified=True,
            dependency_job_statuses=("completed",),
            managed_manifest_relative_path=manifest_path.relative_to(artifact).as_posix(),
            managed_manifest_checksum_sha256=hashlib.sha256(content).hexdigest(),
        ),
    )
    store = StorageGcArtifactStore(artifact, imports)

    eligible = store.scan(repository, policy=StorageRetentionPolicy(), now=NOW)
    original.write_bytes(b"changed")
    blocked = store.scan(repository, policy=StorageRetentionPolicy(), now=NOW)

    assert len(eligible.entries) == 1
    assert eligible.entries[0].artifact_class is StorageArtifactClass.BROWSER_STAGING
    assert eligible.entries[0].root_kind is StorageRootKind.IMPORT
    assert len(blocked.entries) == 0
    assert len(blocked.protected) == 1


def test_gc_manifest_is_immutable_and_contains_observation_identity(tmp_path: Path) -> None:
    artifact = tmp_path / "artifacts"
    imports = tmp_path / "imports"
    imports.mkdir()
    key = "c" * 64
    normalized = (
        artifact
        / "data"
        / "working"
        / "image-normalization-v1"
        / "cc"
        / key
        / "normalized.png"
    )
    normalized.parent.mkdir(parents=True)
    normalized.write_bytes(b"pixels")
    _old(normalized)
    repository = GcSourceRepository()
    repository.statuses[key] = ("completed",)
    store = StorageGcArtifactStore(artifact, imports)
    scan = store.scan(repository, policy=StorageRetentionPolicy(), now=NOW)

    relative, checksum, token = store.persist_manifest(
        scan.entries, policy=StorageRetentionPolicy(), run_id=uuid4()
    )
    content = (artifact / Path(*relative.split("/"))).read_bytes()
    payload = json.loads(content)

    assert hashlib.sha256(content).hexdigest() == checksum
    assert len(token) == 64
    assert payload["candidates"][0]["observationChecksumSha256"]
    assert payload["candidates"][0]["rootKind"] == "artifact"
