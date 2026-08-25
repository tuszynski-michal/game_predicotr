from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.application.remote_manual_selection_recovery import (
    RemoteManualSelectionRecoveryService,
    redact_remote_selection_diagnostic,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
)

NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
SESSION_ID = UUID("10000000-0000-4000-8000-000000000001")
COLLECTION_ID = UUID("20000000-0000-4000-8000-000000000002")
BATCH_ID = UUID("30000000-0000-4000-8000-000000000003")
FILE_ID = UUID("40000000-0000-4000-8000-000000000004")
TRANSFER_ID = UUID("50000000-0000-4000-8000-000000000005")
BINDING_ID = UUID("60000000-0000-4000-8000-000000000006")
PAYLOAD = b"verified-jpeg-payload"
CHECKSUM = hashlib.sha256(PAYLOAD).hexdigest()


def test_reconciler_recovers_only_exact_verified_artifact_and_is_idempotent(
    tmp_path: Path,
) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.UPLOADING,
    )
    with host.open_transfer_directory(
        repository,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
    ) as directory:
        (directory.path / f"{TRANSFER_ID}.verified").write_bytes(PAYLOAD)

    service = RemoteManualSelectionRecoveryService(repository, host, now=lambda: NOW)
    first = service.reconcile()
    second = service.reconcile()

    assert first.inspected_transfer_count == 1
    assert first.recovered_transfer_count == 1
    assert first.failed_transfer_count == 0
    assert repository.transfers[TRANSFER_ID].status is RemoteManualSelectionTransferStatus.VERIFIED
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.VERIFIED
    assert repository.files[FILE_ID].host_checksum_sha256 == CHECKSUM
    assert len(repository.host_actions) == 1
    assert second.inspected_transfer_count == 0
    assert second.recovered_transfer_count == 0
    assert len(repository.host_actions) == 1


def test_reconciler_never_confirms_partial_artifact_and_reports_retained_bytes(
    tmp_path: Path,
) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.UPLOADING,
    )
    with host.open_transfer_directory(
        repository,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
    ) as directory:
        partial = directory.path / f"{TRANSFER_ID}.part"
        partial.write_bytes(PAYLOAD[:7])

    service = RemoteManualSelectionRecoveryService(repository, host, now=lambda: NOW)
    report = service.reconcile()
    status = service.status(session_id=SESSION_ID, batch_id=BATCH_ID)

    assert report.recovered_transfer_count == 0
    assert report.failed_transfer_count == 1
    assert repository.transfers[TRANSFER_ID].status is RemoteManualSelectionTransferStatus.FAILED
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED
    assert partial.read_bytes() == PAYLOAD[:7]
    assert status.gc_preview.deletion_enabled is False
    assert any(
        item.code == "REMOTE_SELECTION_GC_INCOMPLETE_TRANSFER"
        and item.artifact_count == 1
        and item.total_bytes == 7
        for item in status.gc_preview.categories
    )
    assert dict(status.queue.recovery_findings) == {
        "REMOTE_SELECTION_CONFLICT_REQUIRES_ATTENTION": 1
    }


def test_reconciler_fails_closed_for_conflicting_verified_artifact(
    tmp_path: Path,
) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.STORED_TEMP,
        file_status=RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
    )
    with host.open_transfer_directory(
        repository,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
    ) as directory:
        conflicting = directory.path / f"{TRANSFER_ID}.verified"
        conflicting.write_bytes(b"different-content")

    report = RemoteManualSelectionRecoveryService(
        repository,
        host,
        now=lambda: NOW,
    ).reconcile()

    assert report.recovered_transfer_count == 0
    assert report.failed_transfer_count == 1
    assert repository.transfers[TRANSFER_ID].status is RemoteManualSelectionTransferStatus.FAILED
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED
    assert conflicting.read_bytes() == b"different-content"
    assert report.findings[0].code == "REMOTE_SELECTION_TRANSFER_ARTIFACT_CONFLICT"


def test_reconciler_restores_missing_materialization_action_without_reupload(
    tmp_path: Path,
) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.VERIFIED,
        file_status=RemoteManualSelectionFileStatus.VERIFIED,
        received_bytes=len(PAYLOAD),
        verified_checksum=CHECKSUM,
        file_checksum=CHECKSUM,
    )

    report = RemoteManualSelectionRecoveryService(
        repository,
        host,
        now=lambda: NOW,
    ).reconcile()

    assert report.inspected_transfer_count == 0
    assert report.queued_materialization_count == 1
    assert len(repository.host_actions) == 1
    assert repository.transfers[TRANSFER_ID].status is RemoteManualSelectionTransferStatus.VERIFIED


def test_diagnostics_redact_credentials_and_host_paths() -> None:
    raw = {
        "accessToken": "top-secret",
        "lease_token": "lease-secret",
        "message": (
            r"failed at C:\Users\owner\private\image.jpg and "
            "C:/Users/owner/private/second.jpg"
        ),
        "nested": [{"outputPath": r"D:\results\seq_1-9.jpg", "count": 2}],
    }

    redacted = redact_remote_selection_diagnostic(raw)
    serialized = json.dumps(redacted)

    assert "top-secret" not in serialized
    assert "lease-secret" not in serialized
    assert "Users\\owner" not in serialized
    assert "Users/owner" not in serialized
    assert "results\\seq" not in serialized
    assert serialized.count("[REDACTED]") == 3
    assert "[REDACTED_PATH]" in serialized


def test_recovery_status_contains_only_aggregate_diagnostics(tmp_path: Path) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.UPLOADING,
    )

    status = RemoteManualSelectionRecoveryService(
        repository,
        host,
        now=lambda: NOW,
    ).status(session_id=SESSION_ID, batch_id=BATCH_ID)
    serialized = json.dumps(asdict(status), default=str)

    assert str(tmp_path) not in serialized
    assert status.queue.uploading_transfer_count == 1
    assert status.queue.pending_transfer_bytes == len(PAYLOAD)
    assert dict(status.queue.recovery_findings) == {"REMOTE_SELECTION_STALE_TRANSFER": 1}


def test_admin_recovery_endpoint_is_bounded_and_path_free(tmp_path: Path) -> None:
    repository, host = _fixture(
        tmp_path,
        transfer_status=RemoteManualSelectionTransferStatus.UPLOADING,
    )
    recovery = RemoteManualSelectionRecoveryService(repository, host, now=lambda: NOW)
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}
        ),
        remote_manual_selection_recovery_service_dependency=lambda: recovery,
    )

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/admin/remote-manual-selections/"
            f"sessions/{SESSION_ID}/batches/{BATCH_ID}/recovery"
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["batchId"] == str(BATCH_ID)
    assert payload["queue"]["uploadingTransferCount"] == 1
    assert payload["gcPreview"]["deletionEnabled"] is False
    assert str(tmp_path).lower() not in response.text.lower()


def _fixture(
    tmp_path: Path,
    *,
    transfer_status: RemoteManualSelectionTransferStatus,
    file_status: RemoteManualSelectionFileStatus = RemoteManualSelectionFileStatus.UPLOADING,
    received_bytes: int = 0,
    verified_checksum: str | None = None,
    file_checksum: str | None = None,
) -> tuple[InMemoryRemoteManualSelectionRepository, RemoteManualSelectionHostService]:
    base = tmp_path / "private-host-base"
    base.mkdir()
    repository = InMemoryRemoteManualSelectionRepository()
    repository.add_session(
        RemoteManualSelectionSessionV1(
            id=SESSION_ID,
            status=RemoteManualSelectionSessionStatus.ACTIVE,
            revision=0,
            created_at=NOW - timedelta(hours=1),
            updated_at=NOW - timedelta(minutes=5),
            expires_at=NOW + timedelta(hours=7),
        ),
        base_binding_id=BINDING_ID,
        host_base_path=str(base),
        display_name="private-host-base",
    )
    collection = RemoteManualSelectionCollectionV1(
        id=COLLECTION_ID,
        session_id=SESSION_ID,
        name="777",
        normalized_name="777",
        status=RemoteManualSelectionCollectionStatus.ACTIVE,
        revision=0,
    )
    repository.add_collection(collection)
    batch = RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="1-19809",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=1,
        last_client_sequence=1,
    )
    host = RemoteManualSelectionHostService(lambda: None)
    host.provision_batch_mapping(
        repository,
        session_id=SESSION_ID,
        collection=collection,
        batch=batch,
        total_file_count=1,
    )
    repository.files[FILE_ID] = RemoteManualSelectionFileV1(
        id=FILE_ID,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="image.jpg",
        size_bytes=len(PAYLOAD),
        last_modified_ms=1,
        mime_type="image/jpeg",
        desired_selected=True,
        selection_generation=1,
        status=file_status,
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
        host_checksum_sha256=file_checksum,
    )
    repository.file_revisions[FILE_ID] = 1
    repository.add_transfer(
        RemoteManualSelectionTransferV1(
            id=TRANSFER_ID,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            generation=1,
            attempt=1,
            declared_bytes=len(PAYLOAD),
            received_bytes=received_bytes,
            status=transfer_status,
            declared_checksum_sha256=CHECKSUM,
            verified_checksum_sha256=verified_checksum,
        ),
        temp_relative_path=(
            f".game-predictor/remote-selection-v1/transfers/{FILE_ID}/1/"
            f"{TRANSFER_ID}.verified"
            if transfer_status is RemoteManualSelectionTransferStatus.VERIFIED
            else None
        ),
    )
    repository.transfer_updated_at[TRANSFER_ID] = NOW - timedelta(minutes=5)
    return repository, host
