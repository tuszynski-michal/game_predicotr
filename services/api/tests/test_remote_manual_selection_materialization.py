from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionMaterializationScope,
)
from game_predictor_api.application.remote_manual_selection_materialization import (
    RemoteManualSelectionHostMaterializer,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionHostActionType,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
    RemoteManualSelectionMaterializationContext,
)

SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
BATCH_ID = UUID("22222222-2222-4222-8222-222222222222")
FILE_ID = UUID("33333333-3333-4333-8333-333333333333")
TRANSFER_ID = UUID("44444444-4444-4444-8444-444444444444")
ACTION_ID = UUID("55555555-5555-4555-8555-555555555555")
NOW = datetime(2026, 8, 24, 12, tzinfo=UTC)


class SyntheticCrash(BaseException):
    pass


class FakeMaterializationHost:
    def __init__(self, root: Path, source: bytes) -> None:
        self.root = root
        self.source = source

    @contextmanager
    def open_materialization_scope(
        self,
        _repository: object,
        *,
        action_id: UUID,
        output_name: str,
        **_kwargs: object,
    ) -> Iterator[RemoteManualSelectionMaterializationScope]:
        internal = self.root / ".internal" / str(action_id)
        internal.mkdir(parents=True, exist_ok=True)
        source_path = internal / "source.verified"
        if not source_path.exists():
            source_path.write_bytes(self.source)
        yield RemoteManualSelectionMaterializationScope(
            source_path=source_path,
            target_path=self.root / output_name,
            working_path=internal / f"{action_id}.materializing",
            journal_path=internal / f"{action_id}.json",
            final_relative_path=output_name,
            pin_target=lambda: None,
        )


@pytest.mark.parametrize(
    "crash_point",
    (
        "before_temp_copy",
        "after_temp_copy",
        "after_prepared_journal",
        "after_publish",
        "after_published_journal",
    ),
)
def test_every_filesystem_crash_window_recovers_one_owned_output(
    tmp_path: Path,
    crash_point: str,
) -> None:
    payload = b"verified-jpeg-bytes"
    context = _context(payload)
    host = FakeMaterializationHost(tmp_path, payload)

    def crash(point: str) -> None:
        if point == crash_point:
            raise SyntheticCrash(point)

    with pytest.raises(SyntheticCrash):
        RemoteManualSelectionHostMaterializer(host, fault=crash).materialize(
            object(),  # type: ignore[arg-type]
            context,
        )

    completed: list[str] = []
    result = RemoteManualSelectionHostMaterializer(host).materialize(
        object(),  # type: ignore[arg-type]
        context,
        on_published=completed.append,
    )

    assert result == "seq_1-9.jpg"
    assert completed == ["seq_1-9.jpg"]
    assert (tmp_path / result).read_bytes() == payload
    assert len(tuple(tmp_path.glob("seq_*.jpg"))) == 1


def test_foreign_and_changed_owned_targets_fail_closed(tmp_path: Path) -> None:
    payload = b"verified-jpeg-bytes"
    context = _context(payload)
    host = FakeMaterializationHost(tmp_path, payload)
    target = tmp_path / context.output_name
    target.write_bytes(b"foreign")

    with pytest.raises(Exception, match="ownership") as foreign:
        RemoteManualSelectionHostMaterializer(host).materialize(
            object(),  # type: ignore[arg-type]
            context,
        )
    assert foreign.value.code == "REMOTE_SELECTION_MATERIALIZATION_TARGET_FOREIGN"
    assert target.read_bytes() == b"foreign"

    target.unlink()
    RemoteManualSelectionHostMaterializer(host).materialize(
        object(),  # type: ignore[arg-type]
        context,
    )
    target.write_bytes(b"changed")
    with pytest.raises(Exception, match="checksum") as changed:
        RemoteManualSelectionHostMaterializer(host).materialize(
            object(),  # type: ignore[arg-type]
            context,
        )
    assert changed.value.code == "REMOTE_SELECTION_MATERIALIZATION_TARGET_CHANGED"
    assert target.read_bytes() == b"changed"


def test_reparse_working_file_is_blocked_without_touching_external_target(
    tmp_path: Path,
) -> None:
    payload = b"verified-jpeg-bytes"
    context = _context(payload)
    host = FakeMaterializationHost(tmp_path, payload)
    internal = tmp_path / ".internal" / str(ACTION_ID)
    internal.mkdir(parents=True)
    external = tmp_path / "external.jpg"
    external.write_bytes(b"foreign")
    working = internal / f"{ACTION_ID}.materializing"
    try:
        working.symlink_to(external)
    except OSError:
        pytest.skip("File symlinks are unavailable on this Windows host.")

    with pytest.raises(Exception) as blocked:
        RemoteManualSelectionHostMaterializer(host).materialize(
            object(),  # type: ignore[arg-type]
            context,
        )

    assert blocked.value.code == "REMOTE_SELECTION_PATH_UNSAFE"
    assert external.read_bytes() == b"foreign"
    assert not (tmp_path / context.output_name).exists()


def test_in_memory_queue_claims_once_reclaims_expired_and_fences_completion() -> None:
    payload = b"verified-jpeg-bytes"
    repository = _repository(payload)
    action = repository.ensure_materialization_action(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=TRANSFER_ID,
        generation=1,
    )
    assert (
        repository.ensure_materialization_action(
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            file_id=FILE_ID,
            transfer_id=TRANSFER_ID,
            generation=1,
        ).id
        == action.id
    )

    first = repository.claim_next_materialization_action(
        lease_owner="worker-a",
        lease_duration=timedelta(seconds=5),
        claimed_at=NOW,
    )
    assert first is not None and first.lease_token is not None
    assert (
        repository.claim_next_materialization_action(
            lease_owner="worker-b",
            lease_duration=timedelta(seconds=5),
            claimed_at=NOW,
        )
        is None
    )
    reclaimed = repository.claim_next_materialization_action(
        lease_owner="worker-b",
        lease_duration=timedelta(seconds=5),
        claimed_at=NOW + timedelta(seconds=6),
    )
    assert reclaimed is not None and reclaimed.lease_token is not None
    assert reclaimed.action.id == first.action.id
    assert reclaimed.lease_token != first.lease_token

    with pytest.raises(Exception) as fenced:
        repository.lock_materialization_context(
            action_id=action.id,
            lease_token=first.lease_token,
            locked_at=NOW + timedelta(seconds=6),
        )
    assert fenced.value.code == "REMOTE_SELECTION_HOST_ACTION_LEASE_LOST"
    context = repository.lock_materialization_context(
        action_id=action.id,
        lease_token=reclaimed.lease_token,
        locked_at=NOW + timedelta(seconds=6),
    )
    assert context is not None
    synced = repository.complete_materialization_action(
        context,
        lease_token=reclaimed.lease_token,
        final_relative_path=context.output_name,
        completed_at=NOW + timedelta(seconds=6),
    )
    assert synced.status is RemoteManualSelectionFileStatus.SYNCED
    assert (
        repository.transfers[TRANSFER_ID].status is RemoteManualSelectionTransferStatus.MATERIALIZED
    )
    assert (
        repository.host_actions[action.id].status is RemoteManualSelectionHostActionStatus.COMPLETED
    )


def test_stale_generation_is_superseded_before_filesystem_access() -> None:
    payload = b"verified-jpeg-bytes"
    repository = _repository(payload)
    action = repository.ensure_materialization_action(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=TRANSFER_ID,
        generation=1,
    )
    claim = repository.claim_next_materialization_action(
        lease_owner="worker",
        lease_duration=timedelta(seconds=30),
        claimed_at=NOW,
    )
    assert claim is not None and claim.lease_token is not None
    repository.files[FILE_ID] = replace(
        repository.files[FILE_ID],
        selection_generation=2,
    )
    assert (
        repository.lock_materialization_context(
            action_id=action.id,
            lease_token=claim.lease_token,
            locked_at=NOW,
        )
        is None
    )
    assert (
        repository.host_actions[action.id].status
        is RemoteManualSelectionHostActionStatus.SUPERSEDED
    )


def test_startup_reconciliation_restores_only_missing_verified_actions() -> None:
    repository = _repository(b"verified-jpeg-bytes")

    assert repository.enqueue_missing_materialization_actions(limit=4) == 1
    assert repository.enqueue_missing_materialization_actions(limit=4) == 0
    assert len(repository.host_actions) == 1


def test_retry_is_not_claimed_before_its_backoff_deadline() -> None:
    repository = _repository(b"verified-jpeg-bytes")
    action = repository.ensure_materialization_action(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=TRANSFER_ID,
        generation=1,
    )
    claim = repository.claim_next_materialization_action(
        lease_owner="worker-a",
        lease_duration=timedelta(seconds=30),
        claimed_at=NOW,
    )
    assert claim is not None and claim.lease_token is not None
    retry_at = NOW + timedelta(seconds=8)
    repository.finish_materialization_failure(
        action_id=action.id,
        lease_token=claim.lease_token,
        error_code="REMOTE_SELECTION_MATERIALIZATION_IO_FAILED",
        failed_at=NOW,
        retry_at=retry_at,
    )

    assert (
        repository.claim_next_materialization_action(
            lease_owner="worker-b",
            lease_duration=timedelta(seconds=30),
            claimed_at=retry_at - timedelta(microseconds=1),
        )
        is None
    )
    retried = repository.claim_next_materialization_action(
        lease_owner="worker-b",
        lease_duration=timedelta(seconds=30),
        claimed_at=retry_at,
    )
    assert retried is not None
    assert retried.action.id == action.id
    assert retried.action.attempt == 2


def test_database_completion_rejects_a_different_final_relative_name() -> None:
    repository = _repository(b"verified-jpeg-bytes")
    action = repository.ensure_materialization_action(
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=TRANSFER_ID,
        generation=1,
    )
    claim = repository.claim_next_materialization_action(
        lease_owner="worker",
        lease_duration=timedelta(seconds=30),
        claimed_at=NOW,
    )
    assert claim is not None and claim.lease_token is not None
    context = repository.lock_materialization_context(
        action_id=action.id,
        lease_token=claim.lease_token,
        locked_at=NOW,
    )
    assert context is not None

    with pytest.raises(Exception) as mismatch:
        repository.complete_materialization_action(
            context,
            lease_token=claim.lease_token,
            final_relative_path="seq_10-18.jpg",
            completed_at=NOW,
        )

    assert mismatch.value.code == "REMOTE_SELECTION_MATERIALIZATION_GENERATION_CONFLICT"
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.VERIFIED


def test_one_hundred_small_materializations_remain_bounded(tmp_path: Path) -> None:
    payload = b"verified-jpeg-bytes"
    started = perf_counter()
    for index in range(100):
        context = _context(
            payload,
            action_id=uuid4(),
            file_id=uuid4(),
            transfer_id=uuid4(),
            output_name=f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
        )
        RemoteManualSelectionHostMaterializer(
            FakeMaterializationHost(tmp_path, payload)
        ).materialize(object(), context)  # type: ignore[arg-type]
    assert len(tuple(tmp_path.glob("seq_*.jpg"))) == 100
    assert perf_counter() - started < 5.0


def _context(
    payload: bytes,
    *,
    action_id: UUID = ACTION_ID,
    file_id: UUID = FILE_ID,
    transfer_id: UUID = TRANSFER_ID,
    output_name: str = "seq_1-9.jpg",
) -> RemoteManualSelectionMaterializationContext:
    checksum = hashlib.sha256(payload).hexdigest()
    file = RemoteManualSelectionFileV1(
        id=file_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="image.jpg",
        size_bytes=len(payload),
        last_modified_ms=123,
        mime_type="image/jpeg",
        desired_selected=True,
        selection_generation=1,
        status=RemoteManualSelectionFileStatus.VERIFIED,
        range_start=1,
        range_end=9,
        output_name=output_name,
        host_checksum_sha256=checksum,
    )
    transfer = RemoteManualSelectionTransferV1(
        id=transfer_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=file_id,
        generation=1,
        attempt=1,
        declared_bytes=len(payload),
        received_bytes=len(payload),
        status=RemoteManualSelectionTransferStatus.VERIFIED,
        declared_checksum_sha256=checksum,
        verified_checksum_sha256=checksum,
    )
    action = RemoteManualSelectionHostActionV1(
        id=action_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=file_id,
        transfer_id=transfer_id,
        generation=1,
        action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
        status=RemoteManualSelectionHostActionStatus.PROCESSING,
        attempt=1,
    )
    return RemoteManualSelectionMaterializationContext(
        action=action,
        file=file,
        transfer=transfer,
        verified_relative_path=(
            f".game-predictor/remote-selection-v1/transfers/{file_id}/1/{transfer_id}.verified"
        ),
        output_name=output_name,
        checksum_sha256=checksum,
    )


def _repository(payload: bytes) -> InMemoryRemoteManualSelectionRepository:
    context = _context(payload)
    repository = InMemoryRemoteManualSelectionRepository()
    repository.batches[BATCH_ID] = RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=uuid4(),
        name="batch",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=1,
        last_client_sequence=1,
    )
    repository.files[FILE_ID] = context.file
    repository.file_revisions[FILE_ID] = 1
    repository.transfers[TRANSFER_ID] = context.transfer
    repository.transfer_paths[TRANSFER_ID] = context.verified_relative_path
    return repository
