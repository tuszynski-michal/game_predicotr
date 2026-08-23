from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_api.application.remote_manual_selection_host import (
    OWNERSHIP_DIRECTORY,
    OWNERSHIP_MARKER_NAME,
    OWNERSHIP_VERSION_DIRECTORY,
    RemoteManualSelectionBatchMapping,
    RemoteManualSelectionHostService,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionError,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
)

SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
COLLECTION_ID = UUID("20000000-0000-0000-0000-000000000002")
BATCH_ID = UUID("30000000-0000-0000-0000-000000000003")
BINDING_ID = UUID("70000000-0000-0000-0000-000000000007")
NOW = datetime(2026, 8, 23, 20, tzinfo=UTC)
pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows host path boundary")


def _session() -> RemoteManualSelectionSessionV1:
    return RemoteManualSelectionSessionV1(
        id=SESSION_ID,
        status=RemoteManualSelectionSessionStatus.ACTIVE,
        revision=0,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )


def _collection(name: str = "777") -> RemoteManualSelectionCollectionV1:
    return RemoteManualSelectionCollectionV1(
        id=COLLECTION_ID,
        session_id=SESSION_ID,
        name=name,
        normalized_name=name.casefold(),
        status=RemoteManualSelectionCollectionStatus.ACTIVE,
        revision=0,
    )


def _batch(name: str = "1-19809") -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name=name,
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=0,
        last_client_sequence=0,
    )


def _repository(base: Path) -> InMemoryRemoteManualSelectionRepository:
    repository = InMemoryRemoteManualSelectionRepository()
    repository.add_session(
        _session(),
        base_binding_id=BINDING_ID,
        host_base_path=str(base),
        display_name=base.name,
    )
    return repository


def test_base_capability_is_path_free_single_use_and_expires(tmp_path: Path) -> None:
    base = tmp_path / "private-base"
    base.mkdir()
    clock = [NOW]
    service = RemoteManualSelectionHostService(
        lambda: base,
        clock=lambda: clock[0],
    )

    capability = service.select_base()

    assert capability is not None
    assert capability.display_name == "private-base"
    public_keys = {key.replace("_", "").lower() for key in asdict(capability)}
    assert public_keys.isdisjoint({"path", "hostbasepath", "basepath"})
    consumed = service.consume_base_capability(capability.capability)
    assert consumed.host_base_path == base
    with pytest.raises(RemoteManualSelectionError) as replay:
        service.consume_base_capability(capability.capability)
    assert replay.value.code == "REMOTE_SELECTION_BASE_CAPABILITY_INVALID"

    expiring = service.select_base()
    assert expiring is not None
    clock[0] += timedelta(minutes=6)
    with pytest.raises(RemoteManualSelectionError) as expired:
        service.consume_base_capability(expiring.capability)
    assert expired.value.code == "REMOTE_SELECTION_BASE_CAPABILITY_INVALID"


def test_mapping_creates_marker_and_resumes_after_service_restart(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    repository = _repository(base)
    first_service = RemoteManualSelectionHostService(lambda: None)

    created = first_service.provision_batch_mapping(
        repository,
        session_id=SESSION_ID,
        collection=_collection(),
        batch=_batch(),
        total_file_count=2201,
    )
    marker = (
        base
        / "777"
        / "1-19809"
        / OWNERSHIP_DIRECTORY
        / OWNERSHIP_VERSION_DIRECTORY
        / OWNERSHIP_MARKER_NAME
    )
    marker_bytes = marker.read_bytes()

    restarted_service = RemoteManualSelectionHostService(lambda: None)
    resumed = restarted_service.provision_batch_mapping(
        repository,
        session_id=SESSION_ID,
        collection=_collection(),
        batch=_batch(),
        total_file_count=2201,
    )

    assert created.created is True and created.resumed is False
    assert resumed.created is False and resumed.resumed is True
    assert marker.read_bytes() == marker_bytes
    assert "base" not in {key.lower() for key in asdict(resumed)}


def test_existing_unmarked_or_foreign_batch_is_blocked(tmp_path: Path) -> None:
    base = tmp_path / "base"
    batch_path = base / "777" / "1-19809"
    batch_path.mkdir(parents=True)
    repository = _repository(base)
    service = RemoteManualSelectionHostService(lambda: None)

    with pytest.raises(RemoteManualSelectionConflictError) as unmarked:
        service.provision_batch_mapping(
            repository,
            session_id=SESSION_ID,
            collection=_collection(),
            batch=_batch(),
            total_file_count=2201,
        )
    assert unmarked.value.code == "REMOTE_SELECTION_PATH_COLLISION"

    marker = batch_path / OWNERSHIP_DIRECTORY / OWNERSHIP_VERSION_DIRECTORY / OWNERSHIP_MARKER_NAME
    marker.parent.mkdir(parents=True)
    marker.write_text('{"foreign":true}\n', encoding="utf-8")
    with pytest.raises(RemoteManualSelectionConflictError) as foreign:
        service.provision_batch_mapping(
            repository,
            session_id=SESSION_ID,
            collection=_collection(),
            batch=_batch(),
            total_file_count=2201,
        )
    assert foreign.value.code == "REMOTE_SELECTION_PATH_COLLISION"


def test_parallel_exact_mapping_creation_is_idempotent(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    repository = _repository(base)
    service = RemoteManualSelectionHostService(lambda: None)

    def create() -> RemoteManualSelectionBatchMapping:
        return service.provision_batch_mapping(
            repository,
            session_id=SESSION_ID,
            collection=_collection(),
            batch=_batch(),
            total_file_count=2201,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _value: create(), range(2)))

    assert sorted(result.created for result in results) == [False, True]
    assert sorted(result.resumed for result in results) == [False, True]


def test_mapping_rejects_scope_and_normalization_mismatch(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    repository = _repository(base)
    service = RemoteManualSelectionHostService(lambda: None)
    invalid_collection = RemoteManualSelectionCollectionV1(
        id=COLLECTION_ID,
        session_id=SESSION_ID,
        name="Collection",
        normalized_name="not-the-windows-key",
        status=RemoteManualSelectionCollectionStatus.ACTIVE,
        revision=0,
    )

    with pytest.raises(RemoteManualSelectionError) as mismatch:
        service.provision_batch_mapping(
            repository,
            session_id=SESSION_ID,
            collection=invalid_collection,
            batch=_batch(),
            total_file_count=1,
        )

    assert mismatch.value.code == "REMOTE_SELECTION_PATH_NORMALIZATION_MISMATCH"
