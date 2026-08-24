from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.remote_manual_selection_access import (
    REMOTE_SELECTION_COOKIE_NAME,
    REMOTE_SELECTION_PROXY_INTENT,
    RemoteManualSelectionLeaseConflictError,
)
from game_predictor_api.application.remote_manual_selection_control import (
    RemoteManualSelectionControlRateLimiter,
    RemoteManualSelectionControlService,
    RemoteManualSelectionRateLimitError,
    source_file,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionBatchMapping,
    RemoteManualSelectionPublishedFinalization,
)
from game_predictor_api.application.remote_manual_selection_path_safety import (
    ValidatedWindowsComponent,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
    RemoteSourceKind,
    RemoteSourceManifestEntryV1,
    build_remote_source_manifest,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
)

SESSION_ID = UUID("10000000-0000-4000-8000-000000000001")
COLLECTION_ID = UUID("20000000-0000-4000-8000-000000000002")
BATCH_ID = UUID("30000000-0000-4000-8000-000000000003")
CLIENT_ID = UUID("40000000-0000-4000-8000-000000000004")
FILE_IDS = (
    UUID("50000000-0000-4000-8000-000000000005"),
    UUID("50000000-0000-4000-8000-000000000006"),
)
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


class FakeAccess:
    writer = True

    def authorize_session(self, *, session_id, access_token, client_instance_id):
        assert access_token == "access-token"
        assert session_id == SESSION_ID
        assert client_instance_id == CLIENT_ID
        return SimpleNamespace(session_id=session_id)

    def context(self, *, access_token, client_instance_id):
        assert access_token == "access-token"
        assert client_instance_id == CLIENT_ID
        return SimpleNamespace(session_id=SESSION_ID)

    def authorize_writer(self, *, session_id, access_token, client_instance_id):
        self.authorize_session(
            session_id=session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        if not self.writer:
            raise RemoteManualSelectionLeaseConflictError(
                "REMOTE_SELECTION_WRITER_LEASE_LOST",
                "The client no longer owns an active writer lease.",
            )
        return SimpleNamespace(session_id=session_id, is_writer=True)


class FakeHost:
    def validate_mapping_component(self, repository, *, session_id, value):
        assert repository.get_host_binding_for_update(session_id) is not None
        return ValidatedWindowsComponent(value, value.casefold())

    def provision_batch_mapping(
        self,
        repository,
        *,
        session_id,
        collection,
        batch,
        total_file_count,
    ):
        existing = repository.get_batch(batch.id)
        if existing is None:
            binding = repository.get_host_binding_for_update(session_id)
            repository.add_batch(
                batch,
                base_binding_id=binding.base_binding_id,
                normalized_collection_name=collection.normalized_name,
                normalized_batch_name=batch.name.casefold(),
                total_file_count=total_file_count,
            )
        return RemoteManualSelectionBatchMapping(
            session_id=session_id,
            collection_id=collection.id,
            batch_id=batch.id,
            collection_name=collection.name,
            batch_name=batch.name,
            created=existing is None,
            resumed=existing is not None,
        )

    def publish_finalization_manifests(self, repository, **kwargs):
        assert repository is not None
        assert kwargs["session_id"] == SESSION_ID
        assert kwargs["batch_id"] == BATCH_ID
        return RemoteManualSelectionPublishedFinalization(
            final_manifest_checksum_sha256=kwargs["final_manifest_checksum_sha256"],
            output_checksum_sha256="b" * 64,
            trace_checksum_sha256="c" * 64,
            operational_checksum_sha256="d" * 64,
        )


def _fixture():
    repository = InMemoryRemoteManualSelectionRepository()
    repository.add_session(
        RemoteManualSelectionSessionV1(
            id=SESSION_ID,
            status=RemoteManualSelectionSessionStatus.ACTIVE,
            revision=0,
            created_at=NOW,
            updated_at=NOW,
            expires_at=NOW + timedelta(hours=8),
        ),
        base_binding_id=UUID(int=99),
        host_base_path=r"C:\private",
        display_name="private",
    )
    access = FakeAccess()
    service = RemoteManualSelectionControlService(
        repository,
        access,  # type: ignore[arg-type]
        FakeHost(),  # type: ignore[arg-type]
    )
    entries = tuple(
        RemoteSourceManifestEntryV1(
            ordinal=index,
            relative_path=f"{index + 1}.jpg",
            name=f"{index + 1}.jpg",
            size_bytes=100 + index,
            last_modified_ms=1_700_000_000_000 + index,
            mime_type="image/jpeg",
        )
        for index in range(2)
    )
    manifest = build_remote_source_manifest(
        entries,
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
    )
    return repository, access, service, entries, manifest


def _authorize() -> dict[str, object]:
    return {"access_token": "access-token", "client_instance_id": CLIENT_ID}


def _provision_active_batch():
    repository, access, service, entries, manifest = _fixture()
    created = service.create_collection(
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="777",
        **_authorize(),
    )
    replay = service.create_collection(
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="777",
        **_authorize(),
    )
    assert created.created is True
    assert replay.created is False
    first_batch = service.create_batch(
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        batch_id=BATCH_ID,
        name="1-18",
        source_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        total_file_count=2,
        **_authorize(),
    )
    replay_batch = service.create_batch(
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        batch_id=BATCH_ID,
        name="1-18",
        source_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        total_file_count=2,
        **_authorize(),
    )
    assert first_batch.mapping.created is True
    assert replay_batch.mapping.created is False
    files = tuple(
        source_file(
            file_id=FILE_IDS[index],
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            source_index=index,
            relative_path=entry.relative_path,
            size_bytes=entry.size_bytes,
            last_modified_ms=entry.last_modified_ms,
            mime_type=entry.mime_type,
        )
        for index, entry in enumerate(entries)
    )
    page_one = service.register_source_items(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        files=files[:1],
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
        complete=False,
        **_authorize(),
    )
    completed = service.register_source_items(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        files=files[1:],
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
        complete=True,
        **_authorize(),
    )
    assert page_one.batch.status is RemoteManualSelectionBatchStatus.INDEXING
    assert completed.batch.status is RemoteManualSelectionBatchStatus.ACTIVE
    return repository, access, service, files


def test_manifest_pages_activate_once_and_are_immutable_after_activation() -> None:
    repository, access, service, files = _provision_active_batch()

    access.writer = False
    exact_page_retry = service.register_source_items(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        files=files[:1],
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
        complete=False,
        **_authorize(),
    )
    assert exact_page_retry.created_count == 0
    assert len(repository.files) == 2

    with pytest.raises(RemoteManualSelectionConflictError) as error:
        service.register_source_items(
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            files=(
                source_file(
                    file_id=UUID(int=999),
                    session_id=SESSION_ID,
                    batch_id=BATCH_ID,
                    source_index=2,
                    relative_path="3.jpg",
                    size_bytes=102,
                    last_modified_ms=1_700_000_000_002,
                    mime_type="image/jpeg",
                ),
            ),
            source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
            complete=False,
            **_authorize(),
        )
    assert error.value.code == "REMOTE_SELECTION_SOURCE_MANIFEST_IMMUTABLE"


def test_operation_retry_survives_lease_loss_and_state_delta_is_ordered() -> None:
    _repository, access, service, files = _provision_active_batch()
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID("60000000-0000-4000-8000-000000000006"),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=1,
        expected_server_revision=0,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=1,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=files[0].id,
        image_path=files[0].relative_path,
        source_index=0,
        image_checksum_sha256="a" * 64,
        output_name="seq_1-9.jpg",
        visible_milliseconds=400,
        decoded=True,
    )
    first = service.apply_operation(command=command, **_authorize())
    access.writer = False
    exact_retry = service.apply_operation(command=command, **_authorize())

    assert first.batch.server_revision == 1
    assert exact_retry.exact_retry is True
    assert exact_retry.operation == first.operation
    delta = service.state_delta(
        batch_id=BATCH_ID,
        since_revision=0,
        limit=1,
        **_authorize(),
    )
    assert delta.next_revision == 1
    assert delta.has_more is False
    assert delta.files[0].file.id == files[0].id


def test_remote_deselect_rollback_flag_blocks_new_tombstone_but_not_select() -> None:
    repository, access, service, files = _provision_active_batch()
    select_command = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID(int=650),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=1,
        expected_server_revision=0,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=1,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=files[0].id,
        image_path=files[0].relative_path,
        source_index=0,
        image_checksum_sha256="a" * 64,
        output_name="seq_1-9.jpg",
    )
    service.apply_operation(command=select_command, **_authorize())
    disabled = RemoteManualSelectionControlService(
        repository,
        access,  # type: ignore[arg-type]
        FakeHost(),  # type: ignore[arg-type]
        deselect_enabled=False,
    )
    deselect = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID(int=651),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=2,
        expected_server_revision=1,
        operation_type=RemoteManualSelectionOperationType.DESELECT,
        selection_generation=2,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=files[0].id,
        target_operation_id=select_command.operation_id,
    )

    with pytest.raises(RemoteManualSelectionConflictError) as error:
        disabled.apply_operation(command=deselect, **_authorize())

    assert error.value.code == "REMOTE_SELECTION_DESELECT_DISABLED"
    assert repository.get_file(batch_id=BATCH_ID, file_id=files[0].id).desired_selected


def test_new_operation_without_writer_and_forged_revision_fail_closed() -> None:
    _repository, access, service, files = _provision_active_batch()
    access.writer = False
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID(int=700),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=1,
        expected_server_revision=0,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=1,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=files[0].id,
        image_path=files[0].relative_path,
        source_index=0,
        output_name="seq_1-9.jpg",
    )
    with pytest.raises(RemoteManualSelectionLeaseConflictError) as lease:
        service.apply_operation(command=command, **_authorize())
    assert lease.value.code == "REMOTE_SELECTION_WRITER_LEASE_LOST"

    with pytest.raises(RemoteManualSelectionConflictError) as revision:
        service.state_delta(
            batch_id=BATCH_ID,
            since_revision=99,
            limit=10,
            **_authorize(),
        )
    assert revision.value.code == "REMOTE_SELECTION_REVISION_CONFLICT"


def test_control_rate_limit_has_stable_error() -> None:
    limiter = RemoteManualSelectionControlRateLimiter(
        limit=1,
        now=lambda: NOW,
    )
    limiter.consume(SESSION_ID, CLIENT_ID)
    with pytest.raises(RemoteManualSelectionRateLimitError) as error:
        limiter.consume(SESSION_ID, UUID(int=CLIENT_ID.int + 1))
    assert error.value.code == "REMOTE_SELECTION_CONTROL_RATE_LIMITED"


def test_loopback_control_http_exact_retry_and_state_delta(tmp_path) -> None:
    _repository, access, service, entries, manifest = _fixture()
    app = create_app(
        ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}),
        remote_manual_selection_host_service_dependency=lambda: FakeHost(),
        remote_manual_selection_access_service_dependency=lambda: access,
        remote_manual_selection_control_service_dependency=lambda: service,
    )
    headers = {
        "Cookie": f"{REMOTE_SELECTION_COOKIE_NAME}=access-token",
        "X-Remote-Selection-Client": str(CLIENT_ID),
        "X-Remote-Selection-Proxy": REMOTE_SELECTION_PROXY_INTENT,
    }
    with TestClient(app, base_url="https://testserver") as client:
        collection = client.post(
            "/api/v1/remote-manual-selections/collections",
            headers=headers,
            json={
                "collectionId": str(COLLECTION_ID),
                "sessionId": str(SESSION_ID),
                "name": "777",
            },
        )
        assert collection.status_code == 201, collection.text
        assert collection.json()["created"] is True

        batch = client.post(
            f"/api/v1/remote-manual-selections/collections/{COLLECTION_ID}/batches",
            headers=headers,
            json={
                "batchId": str(BATCH_ID),
                "sessionId": str(SESSION_ID),
                "name": "1-18",
                "sourceManifestChecksumSha256": manifest.manifest_checksum_sha256,
                "firstLayout": 1,
                "direction": "ascending",
                "totalFileCount": 2,
            },
        )
        assert batch.status_code == 201, batch.text
        source = client.post(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/source-items",
            headers=headers,
            json={
                "sessionId": str(SESSION_ID),
                "sourceKind": "directory_handle",
                "complete": True,
                "items": [
                    {
                        "fileId": str(FILE_IDS[index]),
                        "sourceIndex": index,
                        "relativePath": entry.relative_path,
                        "sizeBytes": entry.size_bytes,
                        "lastModifiedMs": entry.last_modified_ms,
                        "mimeType": entry.mime_type,
                    }
                    for index, entry in enumerate(entries)
                ],
            },
        )
        assert source.status_code == 200, source.text
        assert source.json()["batch"]["status"] == "active"
        assert source.json()["acceptedFileIds"] == [str(value) for value in FILE_IDS]

        operation_payload = {
            "schemaVersion": "remote-manual-selection-operation-v1",
            "operationId": "60000000-0000-4000-8000-000000000006",
            "sessionId": str(SESSION_ID),
            "batchId": str(BATCH_ID),
            "clientInstanceId": str(CLIENT_ID),
            "clientSequence": 1,
            "expectedServerRevision": 0,
            "operationType": "select",
            "selectionGeneration": 1,
            "rangeStart": 1,
            "rangeEnd": 9,
            "recordedAt": NOW.isoformat(),
            "fileId": str(FILE_IDS[0]),
            "imagePath": entries[0].relative_path,
            "sourceIndex": 0,
            "imageChecksumSha256": "a" * 64,
            "outputName": "seq_1-9.jpg",
            "visibleMilliseconds": 400,
            "decoded": True,
            "targetOperationId": None,
        }
        first = client.post(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/operations",
            headers=headers,
            json=operation_payload,
        )
        replay = client.post(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/operations",
            headers=headers,
            json=operation_payload,
        )
        assert first.status_code == 200, first.text
        assert replay.status_code == 200, replay.text
        assert first.json()["exactRetry"] is False
        assert replay.json()["exactRetry"] is True
        assert replay.json()["operation"] == first.json()["operation"]

        skip_payload = {
            **operation_payload,
            "operationId": "60000000-0000-4000-8000-000000000007",
            "clientSequence": 2,
            "expectedServerRevision": 1,
            "operationType": "skip",
            "selectionGeneration": 0,
            "rangeStart": 10,
            "rangeEnd": 18,
            "fileId": None,
            "imagePath": None,
            "sourceIndex": None,
            "imageChecksumSha256": None,
            "outputName": None,
            "visibleMilliseconds": 0,
            "decoded": False,
        }
        skipped = client.post(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/operations",
            headers=headers,
            json=skip_payload,
        )
        assert skipped.status_code == 200, skipped.text
        assert skipped.json()["batch"]["serverRevision"] == 2

        undo_payload = {
            **operation_payload,
            "operationId": "60000000-0000-4000-8000-000000000008",
            "clientSequence": 3,
            "expectedServerRevision": 2,
            "operationType": "undo",
            "selectionGeneration": 2,
            "imageChecksumSha256": None,
            "outputName": None,
            "targetOperationId": operation_payload["operationId"],
        }
        undone = client.post(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/operations",
            headers=headers,
            json=undo_payload,
        )
        assert undone.status_code == 200, undone.text
        assert undone.json()["file"]["desiredSelected"] is False

        delta = client.get(
            f"/api/v1/remote-manual-selections/batches/{BATCH_ID}/state",
            headers=headers,
            params={"sinceRevision": 0, "limit": 100},
        )
        assert delta.status_code == 200, delta.text
        assert delta.json()["nextRevision"] == 3
        assert delta.json()["files"][0]["fileId"] == str(FILE_IDS[0])

    serialized = repr({collection.text, batch.text, source.text, first.text, delta.text})
    assert "C:\\private" not in serialized
    assert "access-token" not in serialized


def test_finalization_is_revision_bound_idempotent_and_reopen_is_host_only() -> None:
    repository, _access, service, _files = _provision_active_batch()

    preview = service.finalize_preview(
        batch_id=BATCH_ID,
        **_authorize(),
    )
    assert preview.ready is True
    assert preview.server_revision == 0

    finalized = service.finalize_batch(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=0,
        **_authorize(),
    )
    assert finalized.snapshot.batch.status is RemoteManualSelectionBatchStatus.COMPLETED
    assert finalized.snapshot.batch.server_revision == 1
    assert finalized.exact_retry is False

    replay = service.finalize_batch(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=0,
        **_authorize(),
    )
    assert replay.exact_retry is True
    assert replay.artifacts.final_manifest_checksum_sha256 == (
        finalized.artifacts.final_manifest_checksum_sha256
    )

    reopened = service.reopen_batch(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=1,
        expected_final_manifest_checksum_sha256=(
            finalized.artifacts.final_manifest_checksum_sha256
        ),
    )
    assert reopened.snapshot.batch.status is RemoteManualSelectionBatchStatus.ACTIVE
    assert reopened.snapshot.batch.server_revision == 2
    assert (
        repository.get_finalization_snapshot(batch_id=BATCH_ID).final_manifest_checksum_sha256
        is None
    )
