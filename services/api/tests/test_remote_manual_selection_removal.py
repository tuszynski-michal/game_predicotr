from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionRemovalScope,
)
from game_predictor_api.application.remote_manual_selection_removal import (
    RemoteManualSelectionHostRemover,
    RemoteManualSelectionRemovalResult,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionDirection,
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
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
    RemoteManualSelectionRemovalContext,
)

SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
COLLECTION_ID = UUID("22222222-2222-4222-8222-222222222222")
BATCH_ID = UUID("33333333-3333-4333-8333-333333333333")
FILE_ID = UUID("44444444-4444-4444-8444-444444444444")
CLIENT_ID = UUID("55555555-5555-4555-8555-555555555555")
SELECT_ID = UUID("66666666-6666-4666-8666-666666666666")
TRANSFER_ID = UUID("77777777-7777-4777-8777-777777777777")
MATERIALIZATION_ID = UUID("88888888-8888-4888-8888-888888888888")
REMOVAL_ID = UUID("99999999-9999-4999-8999-999999999999")
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)
PAYLOAD = b"owned-final-jpeg"
CHECKSUM = hashlib.sha256(PAYLOAD).hexdigest()


class SyntheticCrash(BaseException):
    pass


class FakeRemovalHost:
    def __init__(self, root: Path, context: RemoteManualSelectionRemovalContext) -> None:
        self.root = root
        self.context = context

    @contextmanager
    def open_removal_scope(self, _repository: object, **_kwargs: object) -> Iterator[object]:
        internal = self.root / ".internal"
        internal.mkdir(parents=True, exist_ok=True)
        materialization_journal = internal / "materialization.json"
        if not materialization_journal.exists():
            materialization_journal.write_text(
                json.dumps(
                    {
                        "actionId": str(self.context.materialization_action_id),
                        "batchId": str(BATCH_ID),
                        "checksumSha256": CHECKSUM,
                        "fileId": str(FILE_ID),
                        "generation": 1,
                        "outputName": "seq_1-9.jpg",
                        "schemaVersion": "remote-manual-selection-materialization-v1",
                        "sessionId": str(SESSION_ID),
                        "state": "published",
                        "transferId": str(TRANSFER_ID),
                    }
                ),
                encoding="utf-8",
            )
        quarantine = internal / "quarantine.jpg"

        def quarantine_target(expected_checksum: str) -> None:
            source = self.root / "seq_1-9.jpg"
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected_checksum
            os.replace(source, quarantine)

        yield RemoteManualSelectionRemovalScope(
            target_path=self.root / "seq_1-9.jpg",
            quarantine_path=quarantine,
            removal_journal_path=internal / "removal.json",
            materialization_journal_path=materialization_journal,
            quarantine_relative_path=".internal/quarantine.jpg",
            quarantine_target=quarantine_target,
        )


@pytest.mark.parametrize(
    "crash_point",
    (
        "before_removal_journal",
        "after_removal_journal",
        "after_quarantine",
        "after_quarantined_journal",
    ),
)
def test_removal_crash_windows_recover_one_reversible_quarantine(
    tmp_path: Path,
    crash_point: str,
) -> None:
    context = _removal_context()
    target = tmp_path / context.output_name
    target.write_bytes(PAYLOAD)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SyntheticCrash(point)

    with pytest.raises(SyntheticCrash):
        RemoteManualSelectionHostRemover(
            FakeRemovalHost(tmp_path, context),
            fault=crash,
        ).remove(object(), context)

    completed: list[bool] = []
    result = RemoteManualSelectionHostRemover(FakeRemovalHost(tmp_path, context)).remove(
        object(), context, on_quarantined=lambda: completed.append(True)
    )

    assert result is RemoteManualSelectionRemovalResult.QUARANTINED
    assert completed == [True]
    assert not target.exists()
    assert (tmp_path / ".internal" / "quarantine.jpg").read_bytes() == PAYLOAD


def test_foreign_or_changed_final_target_is_never_removed(tmp_path: Path) -> None:
    context = _removal_context()
    host = FakeRemovalHost(tmp_path, context)
    target = tmp_path / context.output_name
    target.write_bytes(PAYLOAD)
    with host.open_removal_scope(object()) as scope:
        assert isinstance(scope, RemoteManualSelectionRemovalScope)
        scope.materialization_journal_path.unlink()
        scope.materialization_journal_path.write_text("{}", encoding="utf-8")
        with pytest.raises(Exception) as foreign:
            RemoteManualSelectionHostRemover(host).remove(object(), context)
    assert foreign.value.code == "REMOTE_SELECTION_REMOVAL_TARGET_FOREIGN"
    assert target.read_bytes() == PAYLOAD

    target.write_bytes(b"changed")
    (tmp_path / ".internal" / "materialization.json").unlink()
    with pytest.raises(AssertionError):
        RemoteManualSelectionHostRemover(FakeRemovalHost(tmp_path, context)).remove(
            object(), context
        )
    assert target.read_bytes() == b"changed"


def test_deselect_cancels_old_generation_and_queues_remove_idempotently() -> None:
    repository = _repository(synced=True)
    deselect = _command(
        operation_id=uuid4(),
        client_sequence=2,
        expected_revision=1,
        generation=2,
        operation_type=RemoteManualSelectionOperationType.DESELECT,
        target_operation_id=SELECT_ID,
    )

    applied = repository.apply_operation(deselect)
    replay = repository.apply_operation(deselect)

    assert applied.file is not None
    assert applied.file.desired_selected is False
    assert applied.file.status is RemoteManualSelectionFileStatus.DESELECT_PENDING
    assert applied.operation.outcome_code == "tombstone_applied"
    assert replay.exact_retry is True
    removes = [
        action
        for action in repository.host_actions.values()
        if action.action_type is RemoteManualSelectionHostActionType.REMOVE
    ]
    assert len(removes) == 1
    assert removes[0].generation == 2


def test_deselect_before_materialization_finishes_removed_without_host_action() -> None:
    repository = _repository(synced=False)
    deselect = _command(
        operation_id=uuid4(),
        client_sequence=2,
        expected_revision=1,
        generation=2,
        operation_type=RemoteManualSelectionOperationType.UNDO,
        target_operation_id=SELECT_ID,
    )

    result = repository.apply_operation(deselect)

    assert result.file is not None
    assert result.file.status is RemoteManualSelectionFileStatus.REMOVED
    assert not repository.host_actions


def test_rapid_select_deselect_select_keeps_generation_three_and_removes_old_target() -> None:
    repository = _repository(synced=True)
    deselect = _command(
        operation_id=uuid4(),
        client_sequence=2,
        expected_revision=1,
        generation=2,
        operation_type=RemoteManualSelectionOperationType.DESELECT,
        target_operation_id=SELECT_ID,
    )
    repository.apply_operation(deselect)
    reselect = _command(
        operation_id=uuid4(),
        client_sequence=3,
        expected_revision=2,
        generation=3,
    )
    selected = repository.apply_operation(reselect)
    assert selected.file is not None and selected.file.desired_selected

    assert (
        repository.claim_next_materialization_action(
            lease_owner="materializer",
            lease_duration=timedelta(seconds=30),
            claimed_at=NOW,
        )
        is None
    )
    claim = repository.claim_next_removal_action(
        lease_owner="remover",
        lease_duration=timedelta(seconds=30),
        claimed_at=NOW,
    )
    assert claim is not None and claim.lease_token is not None
    context = repository.lock_removal_context(
        action_id=claim.action.id,
        lease_token=claim.lease_token,
        locked_at=NOW,
    )
    assert context is not None
    current = repository.complete_removal_action(
        context,
        lease_token=claim.lease_token,
        completed_at=NOW,
    )
    assert current.selection_generation == 3
    assert current.desired_selected is True
    assert current.status is RemoteManualSelectionFileStatus.SELECTION_QUEUED
    assert FILE_ID not in repository.file_final_paths


def _repository(*, synced: bool) -> InMemoryRemoteManualSelectionRepository:
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
        base_binding_id=UUID(int=10),
        host_base_path=r"C:\Users\user\Documents",
        display_name="Documents",
    )
    repository.add_collection(
        RemoteManualSelectionCollectionV1(
            id=COLLECTION_ID,
            session_id=SESSION_ID,
            name="777",
            normalized_name="777",
            status=RemoteManualSelectionCollectionStatus.ACTIVE,
            revision=0,
        )
    )
    repository.add_batch(
        RemoteManualSelectionBatchV1(
            id=BATCH_ID,
            session_id=SESSION_ID,
            collection_id=COLLECTION_ID,
            name="1-9",
            source_manifest_checksum_sha256="a" * 64,
            first_layout=1,
            direction=RemoteManualSelectionDirection.ASCENDING,
            cursor_index=0,
            status=RemoteManualSelectionBatchStatus.ACTIVE,
            server_revision=0,
            last_client_sequence=0,
        ),
        base_binding_id=UUID(int=10),
        normalized_collection_name="777",
        normalized_batch_name="1-9",
        total_file_count=1,
    )
    repository.add_files(
        (
            RemoteManualSelectionFileV1(
                id=FILE_ID,
                session_id=SESSION_ID,
                batch_id=BATCH_ID,
                source_index=0,
                relative_path="source.jpg",
                size_bytes=len(PAYLOAD),
                last_modified_ms=1,
                mime_type="image/jpeg",
                desired_selected=False,
                selection_generation=0,
                status=RemoteManualSelectionFileStatus.UNSELECTED,
            ),
        )
    )
    repository.apply_operation(_command())
    if not synced:
        return repository
    repository.files[FILE_ID] = replace(
        repository.files[FILE_ID],
        status=RemoteManualSelectionFileStatus.SYNCED,
        host_checksum_sha256=CHECKSUM,
    )
    repository.file_final_paths[FILE_ID] = "seq_1-9.jpg"
    repository.add_transfer(
        RemoteManualSelectionTransferV1(
            id=TRANSFER_ID,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            generation=1,
            attempt=1,
            declared_bytes=len(PAYLOAD),
            received_bytes=len(PAYLOAD),
            status=RemoteManualSelectionTransferStatus.MATERIALIZED,
            declared_checksum_sha256=CHECKSUM,
            verified_checksum_sha256=CHECKSUM,
        ),
        temp_relative_path="verified",
    )
    repository.add_host_action(
        RemoteManualSelectionHostActionV1(
            id=MATERIALIZATION_ID,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            transfer_id=TRANSFER_ID,
            generation=1,
            action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
            status=RemoteManualSelectionHostActionStatus.COMPLETED,
            attempt=1,
        )
    )
    return repository


def _command(
    *,
    operation_id: UUID = SELECT_ID,
    client_sequence: int = 1,
    expected_revision: int = 0,
    generation: int = 1,
    operation_type: RemoteManualSelectionOperationType = RemoteManualSelectionOperationType.SELECT,
    target_operation_id: UUID | None = None,
) -> RemoteManualSelectionOperationCommandV1:
    return RemoteManualSelectionOperationCommandV1(
        operation_id=operation_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=client_sequence,
        expected_server_revision=expected_revision,
        operation_type=operation_type,
        selection_generation=generation,
        range_start=1,
        range_end=9,
        recorded_at=NOW,
        file_id=FILE_ID,
        image_path=(
            "source.jpg" if operation_type is RemoteManualSelectionOperationType.SELECT else None
        ),
        source_index=0 if operation_type is RemoteManualSelectionOperationType.SELECT else None,
        image_checksum_sha256=CHECKSUM,
        output_name=(
            "seq_1-9.jpg" if operation_type is RemoteManualSelectionOperationType.SELECT else None
        ),
        target_operation_id=target_operation_id,
    )


def _removal_context() -> RemoteManualSelectionRemovalContext:
    file = RemoteManualSelectionFileV1(
        id=FILE_ID,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="source.jpg",
        size_bytes=len(PAYLOAD),
        last_modified_ms=1,
        mime_type="image/jpeg",
        desired_selected=False,
        selection_generation=2,
        status=RemoteManualSelectionFileStatus.DESELECT_PENDING,
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
    )
    transfer = RemoteManualSelectionTransferV1(
        id=TRANSFER_ID,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
        attempt=1,
        declared_bytes=len(PAYLOAD),
        received_bytes=len(PAYLOAD),
        status=RemoteManualSelectionTransferStatus.MATERIALIZED,
        declared_checksum_sha256=CHECKSUM,
        verified_checksum_sha256=CHECKSUM,
    )
    return RemoteManualSelectionRemovalContext(
        action=RemoteManualSelectionHostActionV1(
            id=REMOVAL_ID,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            transfer_id=TRANSFER_ID,
            generation=2,
            action_type=RemoteManualSelectionHostActionType.REMOVE,
            status=RemoteManualSelectionHostActionStatus.PROCESSING,
            attempt=1,
        ),
        file=file,
        transfer=transfer,
        materialization_action_id=MATERIALIZATION_ID,
        materialized_generation=1,
        output_name="seq_1-9.jpg",
        checksum_sha256=CHECKSUM,
    )
