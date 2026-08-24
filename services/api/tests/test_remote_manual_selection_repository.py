from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

import pytest
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionError,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionHostActionType,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionSessionV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.storage.models import (
    RemoteManualSelectionBatchModel,
    RemoteManualSelectionFileModel,
    RemoteManualSelectionHostActionModel,
    RemoteManualSelectionOperationModel,
    RemoteManualSelectionSessionModel,
    RemoteManualSelectionTransferModel,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
    _batch_from_record,
    _file_from_record,
    _file_record_from_domain,
    _host_binding_from_record,
    _map_integrity_error,
    _operation_from_record,
    _operation_record_from_domain,
    _session_from_record,
)
from sqlalchemy import LargeBinary
from sqlalchemy.exc import IntegrityError

SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
COLLECTION_ID = UUID("20000000-0000-0000-0000-000000000002")
BATCH_ID = UUID("30000000-0000-0000-0000-000000000003")
FILE_ID = UUID("40000000-0000-0000-0000-000000000004")
CLIENT_ID = UUID("50000000-0000-0000-0000-000000000005")
OPERATION_ID = UUID("60000000-0000-0000-0000-000000000006")
BINDING_ID = UUID("70000000-0000-0000-0000-000000000007")
NOW = datetime(2026, 8, 23, 18, tzinfo=UTC)


def _session(
    session_id: UUID = SESSION_ID,
) -> RemoteManualSelectionSessionV1:
    return RemoteManualSelectionSessionV1(
        id=session_id,
        status=RemoteManualSelectionSessionStatus.ACTIVE,
        revision=0,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )


def _collection(
    session_id: UUID = SESSION_ID,
    collection_id: UUID = COLLECTION_ID,
) -> RemoteManualSelectionCollectionV1:
    return RemoteManualSelectionCollectionV1(
        id=collection_id,
        session_id=session_id,
        name="777",
        normalized_name="777",
        status=RemoteManualSelectionCollectionStatus.ACTIVE,
        revision=0,
    )


def _batch(
    session_id: UUID = SESSION_ID,
    collection_id: UUID = COLLECTION_ID,
    batch_id: UUID = BATCH_ID,
) -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=batch_id,
        session_id=session_id,
        collection_id=collection_id,
        name="1-19809",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=0,
        last_client_sequence=0,
    )


def _file(
    session_id: UUID = SESSION_ID,
    batch_id: UUID = BATCH_ID,
    file_id: UUID = FILE_ID,
) -> RemoteManualSelectionFileV1:
    return RemoteManualSelectionFileV1(
        id=file_id,
        session_id=session_id,
        batch_id=batch_id,
        source_index=0,
        relative_path="source/1.jpg",
        size_bytes=1024,
        last_modified_ms=1_700_000_000_000,
        mime_type="image/jpeg",
        desired_selected=False,
        selection_generation=0,
        status=RemoteManualSelectionFileStatus.UNSELECTED,
    )


def _command(
    *,
    operation_id: UUID = OPERATION_ID,
    client_sequence: int = 1,
    expected_revision: int = 0,
    generation: int = 1,
) -> RemoteManualSelectionOperationCommandV1:
    return RemoteManualSelectionOperationCommandV1(
        operation_id=operation_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=client_sequence,
        expected_server_revision=expected_revision,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=generation,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=FILE_ID,
        image_path="source/1.jpg",
        source_index=0,
        image_checksum_sha256="b" * 64,
        output_name="seq_1-9.jpg",
        visible_milliseconds=400,
        decoded=True,
    )


def _seed(repository: InMemoryRemoteManualSelectionRepository) -> None:
    repository.add_session(
        _session(),
        base_binding_id=BINDING_ID,
        host_base_path=r"C:\Users\user\Documents",
        display_name="Documents",
    )
    repository.add_collection(_collection())
    repository.add_batch(
        _batch(),
        base_binding_id=BINDING_ID,
        normalized_collection_name="777",
        normalized_batch_name="1-19809",
        total_file_count=1,
    )
    repository.add_files((_file(),))


def test_in_memory_repository_preserves_operation_revision_and_exact_retry() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)

    first = repository.apply_operation(_command())
    replay = repository.apply_operation(_command())

    assert first.batch.server_revision == 1
    assert first.file is not None and first.file.desired_selected is True
    assert replay.exact_retry is True
    assert replay.batch.server_revision == 1
    assert repository.get_batch(BATCH_ID) == first.batch
    assert repository.list_file_delta(batch_id=BATCH_ID, after_revision=0, limit=10) == (
        first.file,
    )
    assert repository.list_file_delta(batch_id=BATCH_ID, after_revision=1, limit=10) == ()
    assert repository.list_operations_after_sequence(
        batch_id=BATCH_ID,
        after_client_sequence=0,
        limit=10,
    ) == (first.operation,)


def test_in_memory_repository_rejects_duplicate_base_mapping_across_sessions() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)
    second_session_id = UUID(int=20)
    second_collection_id = UUID(int=21)
    repository.add_session(
        _session(second_session_id),
        base_binding_id=BINDING_ID,
        host_base_path=r"C:\Users\user\Documents",
        display_name="Documents",
    )
    repository.add_collection(_collection(second_session_id, second_collection_id))

    with pytest.raises(RemoteManualSelectionConflictError) as error:
        repository.add_batch(
            _batch(second_session_id, second_collection_id, UUID(int=22)),
            base_binding_id=BINDING_ID,
            normalized_collection_name="777",
            normalized_batch_name="1-19809",
            total_file_count=1,
        )
    assert error.value.code == "REMOTE_SELECTION_BASE_MAPPING_CONFLICT"


def test_public_session_projection_does_not_expose_host_or_secret_values() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)

    public_session = repository.get_session(SESSION_ID)
    host_binding = repository.get_host_binding_for_update(SESSION_ID)

    assert public_session is not None
    assert host_binding is not None
    public_keys = {key.replace("_", "").lower() for key in asdict(public_session)}
    assert public_keys.isdisjoint(
        {"hostbasepath", "codesalt", "codehash", "tokenhash", "leasetoken"}
    )
    assert host_binding.host_base_path == r"C:\Users\user\Documents"


def test_audit_payload_rejects_sensitive_keys_at_any_depth() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)

    with pytest.raises(RemoteManualSelectionError) as error:
        repository.append_audit_event(
            event_id=UUID(int=30),
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            event_type="security_reject",
            actor="local-owner",
            outcome_code="rejected",
            payload={"details": {"leaseToken": "secret"}},
            created_at=NOW,
        )
    assert error.value.code == "REMOTE_SELECTION_AUDIT_PAYLOAD_SENSITIVE"


def test_transfer_and_host_action_keep_only_metadata() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)
    transfer = RemoteManualSelectionTransferV1(
        id=UUID(int=31),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
        attempt=1,
        declared_bytes=1024,
        received_bytes=0,
        status=RemoteManualSelectionTransferStatus.QUEUED,
    )
    action = RemoteManualSelectionHostActionV1(
        id=UUID(int=32),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=transfer.id,
        generation=1,
        action_type=RemoteManualSelectionHostActionType.VERIFY,
        status=RemoteManualSelectionHostActionStatus.QUEUED,
        attempt=0,
    )

    assert repository.add_transfer(transfer) == transfer
    assert repository.add_host_action(action) == action


def test_in_memory_transfer_and_host_action_enforce_database_scope_and_uniqueness() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)
    transfer = RemoteManualSelectionTransferV1(
        id=UUID(int=33),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
        attempt=1,
        declared_bytes=1024,
        received_bytes=0,
        status=RemoteManualSelectionTransferStatus.QUEUED,
    )
    repository.add_transfer(transfer)

    with pytest.raises(RemoteManualSelectionConflictError):
        repository.add_transfer(
            RemoteManualSelectionTransferV1(
                id=UUID(int=34),
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                attempt=1,
                declared_bytes=1024,
                received_bytes=0,
                status=RemoteManualSelectionTransferStatus.QUEUED,
            )
        )

    with pytest.raises(RemoteManualSelectionError) as transfer_scope_error:
        repository.add_transfer(
            RemoteManualSelectionTransferV1(
                id=UUID(int=35),
                session_id=UUID(int=99),
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                generation=1,
                attempt=2,
                declared_bytes=1024,
                received_bytes=0,
                status=RemoteManualSelectionTransferStatus.QUEUED,
            )
        )
    assert transfer_scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"

    active_action = RemoteManualSelectionHostActionV1(
        id=UUID(int=36),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=transfer.id,
        generation=1,
        action_type=RemoteManualSelectionHostActionType.VERIFY,
        status=RemoteManualSelectionHostActionStatus.QUEUED,
        attempt=0,
    )
    repository.add_host_action(active_action)

    with pytest.raises(RemoteManualSelectionConflictError):
        repository.add_host_action(
            RemoteManualSelectionHostActionV1(
                id=UUID(int=37),
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                transfer_id=transfer.id,
                generation=1,
                action_type=RemoteManualSelectionHostActionType.VERIFY,
                status=RemoteManualSelectionHostActionStatus.PROCESSING,
                attempt=1,
            )
        )

    with pytest.raises(RemoteManualSelectionError) as action_scope_error:
        repository.add_host_action(
            RemoteManualSelectionHostActionV1(
                id=UUID(int=38),
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                file_id=FILE_ID,
                transfer_id=UUID(int=999),
                generation=2,
                action_type=RemoteManualSelectionHostActionType.VERIFY,
                status=RemoteManualSelectionHostActionStatus.QUEUED,
                attempt=0,
            )
        )
    assert action_scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"


def test_orm_mappers_roundtrip_without_host_only_values_in_domain_contracts() -> None:
    session_record = RemoteManualSelectionSessionModel(
        id=SESSION_ID,
        base_binding_id=BINDING_ID,
        host_base_path=r"C:\private",
        display_name="private",
        status="active",
        revision=0,
        failed_attempts=0,
        created_at=NOW,
        updated_at=NOW,
        expires_at=NOW + timedelta(hours=8),
    )
    batch_record = RemoteManualSelectionBatchModel(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        base_binding_id=BINDING_ID,
        normalized_collection_name="777",
        name="1-19809",
        normalized_name="1-19809",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction="ascending",
        cursor_index=0,
        status="active",
        server_revision=0,
        last_client_sequence=0,
        total_file_count=1,
        selected_file_count=0,
        transferred_file_count=0,
    )
    file_record = _file_record_from_domain(_file())
    application = InMemoryRemoteManualSelectionRepository()
    _seed(application)
    operation = application.apply_operation(_command()).operation
    operation_record = _operation_record_from_domain(operation)

    assert _session_from_record(session_record) == _session()
    assert _host_binding_from_record(session_record).host_base_path == r"C:\private"
    assert _batch_from_record(batch_record) == _batch()
    assert _file_from_record(file_record) == _file()
    assert _operation_from_record(operation_record) == operation


def test_image_state_tables_have_no_binary_image_column() -> None:
    for model in (
        RemoteManualSelectionFileModel,
        RemoteManualSelectionOperationModel,
        RemoteManualSelectionTransferModel,
        RemoteManualSelectionHostActionModel,
    ):
        assert not any(isinstance(column.type, LargeBinary) for column in model.__table__.columns)
        assert "content" not in model.__table__.columns
        assert "image_blob" not in model.__table__.columns


@pytest.mark.parametrize(
    ("constraint", "code"),
    [
        ("uq_rms_batches_base_mapping", "REMOTE_SELECTION_BASE_MAPPING_CONFLICT"),
        ("uq_rms_operations_client_sequence", "REMOTE_SELECTION_CLIENT_SEQUENCE_CONFLICT"),
        ("fk_rms_operations_file_scope", "REMOTE_SELECTION_SCOPE_MISMATCH"),
        ("ck_rms_files_range", "REMOTE_SELECTION_PERSISTENCE_CONFLICT"),
    ],
)
def test_constraint_errors_have_stable_domain_codes(constraint: str, code: str) -> None:
    original = RuntimeError("constraint")
    original.diag = SimpleNamespace(constraint_name=constraint)  # type: ignore[attr-defined]
    error = IntegrityError("insert", {}, original)

    assert _map_integrity_error(error).code == code


def test_page_limits_are_fail_closed() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)

    with pytest.raises(RemoteManualSelectionError) as error:
        repository.list_operations_after_sequence(
            batch_id=BATCH_ID,
            after_client_sequence=0,
            limit=1001,
        )
    assert error.value.code == "REMOTE_SELECTION_PAGE_LIMIT_INVALID"


def test_finalization_state_and_host_reopen_are_revision_and_checksum_bound() -> None:
    repository = InMemoryRemoteManualSelectionRepository()
    _seed(repository)

    finalizing = repository.mark_batch_finalizing(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=0,
        changed_at=NOW + timedelta(minutes=1),
    )
    assert finalizing.status is RemoteManualSelectionBatchStatus.FINALIZING
    assert finalizing.server_revision == 0

    completed = repository.complete_batch_finalization(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=0,
        final_manifest_checksum_sha256="f" * 64,
        completed_at=NOW + timedelta(minutes=2),
        actor="remote-operator:test",
    )
    assert completed.batch.status is RemoteManualSelectionBatchStatus.COMPLETED
    assert completed.batch.server_revision == 1
    assert completed.final_manifest_checksum_sha256 == "f" * 64

    with pytest.raises(RemoteManualSelectionConflictError):
        repository.reopen_completed_batch(
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            expected_server_revision=1,
            expected_final_manifest_checksum_sha256="e" * 64,
            reopened_at=NOW + timedelta(minutes=3),
        )

    reopened = repository.reopen_completed_batch(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        expected_server_revision=1,
        expected_final_manifest_checksum_sha256="f" * 64,
        reopened_at=NOW + timedelta(minutes=3),
    )
    assert reopened.batch.status is RemoteManualSelectionBatchStatus.ACTIVE
    assert reopened.batch.server_revision == 2
    assert reopened.final_manifest_checksum_sha256 is None
