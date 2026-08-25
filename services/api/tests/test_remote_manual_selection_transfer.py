from __future__ import annotations

import asyncio
import hashlib
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionTransferDirectory,
)
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferGate,
    RemoteManualSelectionTransferLimitError,
    RemoteManualSelectionTransferLimits,
    RemoteManualSelectionTransferRateLimitError,
    RemoteManualSelectionTransferService,
    RemoteManualSelectionTransferTimeoutError,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationStatus,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionTransferStatus,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
)
from PIL import Image

SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
BATCH_ID = UUID("22222222-2222-4222-8222-222222222222")
FILE_ID = UUID("33333333-3333-4333-8333-333333333333")
CLIENT_ID = UUID("44444444-4444-4444-8444-444444444444")


class FakeAccess:
    def context(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(session_id=SESSION_ID)

    def authorize_session(self, *, session_id: UUID, **_kwargs: object) -> None:
        assert session_id == SESSION_ID

    def authorize_writer(self, *, session_id: UUID, **_kwargs: object) -> None:
        assert session_id == SESSION_ID


class ExpiredWriterAccess(FakeAccess):
    def authorize_writer(self, **_kwargs: object) -> None:
        raise AssertionError("an exact verified retry must not require the writer lease")


class FakeHost:
    def __init__(self, root: Path) -> None:
        self.root = root

    @contextmanager
    def open_transfer_directory(
        self, *_args: object, **_kwargs: object
    ) -> Iterator[RemoteManualSelectionTransferDirectory]:
        self.root.mkdir(parents=True, exist_ok=True)
        yield RemoteManualSelectionTransferDirectory(
            path=self.root,
            relative_path=".game-predictor/remote-selection-v1/transfers/file/1",
        )


def test_stream_upload_verifies_jpeg_and_exact_retry_does_not_read_body(tmp_path: Path) -> None:
    payload = _jpeg()
    service, repository = _service(tmp_path, payload)
    transfer_id = uuid4()

    first = asyncio.run(
        service.upload(
            **_request(payload, transfer_id),
            chunks=_chunks(payload, 17),
        )
    )
    assert first.transfer.status.value == "verified"
    assert first.transfer.verified_checksum_sha256 == hashlib.sha256(payload).hexdigest()
    assert first.temp_relative_path is not None
    assert list(tmp_path.glob("*.verified"))
    assert not list(tmp_path.glob("*.part"))
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.VERIFIED
    assert len(repository.host_actions) == 1

    consumed = False

    async def forbidden_body() -> AsyncIterator[bytes]:
        nonlocal consumed
        consumed = True
        yield payload

    retry_service = RemoteManualSelectionTransferService(
        repository,
        ExpiredWriterAccess(),  # type: ignore[arg-type]
        FakeHost(tmp_path),  # type: ignore[arg-type]
    )
    retried = asyncio.run(
        retry_service.upload(
            **_request(payload, transfer_id),
            chunks=forbidden_body(),
        )
    )
    assert retried.transfer.id == first.transfer.id
    assert consumed is False
    assert len(repository.transfers) == 1
    assert len(repository.host_actions) == 1


def test_status_reconciles_verified_transfer_missing_its_host_action(tmp_path: Path) -> None:
    payload = _jpeg()
    service, repository = _service(tmp_path, payload)
    transfer_id = uuid4()
    asyncio.run(
        service.upload(
            **_request(payload, transfer_id),
            chunks=_chunks(payload, 17),
        )
    )
    repository.host_actions.clear()
    repository.host_action_metadata.clear()

    record = service.status(
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        generation=1,
        transfer_id=transfer_id,
        access_token="token",
        client_instance_id=CLIENT_ID,
    )

    assert record is not None
    assert record.transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
    assert len(repository.host_actions) == 1


def test_interrupted_stream_and_invalid_jpeg_never_publish_verified_file(
    tmp_path: Path,
) -> None:
    payload = _jpeg()
    service, repository = _service(tmp_path, payload)

    async def interrupted() -> AsyncIterator[bytes]:
        yield payload[:10]
        raise ConnectionError("synthetic disconnect")

    with pytest.raises(ConnectionError):
        asyncio.run(
            service.upload(
                **_request(payload, uuid4()),
                chunks=interrupted(),
            )
        )
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.verified"))
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED

    invalid = b"not-a-jpeg" * 5
    service, repository = _service(tmp_path / "invalid", invalid)
    with pytest.raises(Exception, match="JPEG"):
        asyncio.run(
            service.upload(
                **_request(invalid, uuid4()),
                chunks=_chunks(invalid, 4),
            )
        )
    assert not list((tmp_path / "invalid").glob("*.verified"))
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED


def test_successful_retry_cancels_older_failed_attempt_for_same_generation(
    tmp_path: Path,
) -> None:
    payload = _jpeg()
    service, repository = _service(tmp_path, payload)
    failed_transfer_id = uuid4()

    async def interrupted() -> AsyncIterator[bytes]:
        yield payload[:10]
        raise ConnectionError("synthetic disconnect")

    with pytest.raises(ConnectionError):
        asyncio.run(
            service.upload(
                **_request(payload, failed_transfer_id),
                chunks=interrupted(),
            )
        )

    retry_transfer_id = uuid4()
    result = asyncio.run(
        service.upload(
            **_request(payload, retry_transfer_id),
            chunks=_chunks(payload, 17),
        )
    )

    assert result.transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
    assert result.transfer.attempt == 2
    assert (
        repository.transfers[failed_transfer_id].status
        is RemoteManualSelectionTransferStatus.CANCELLED
    )
    assert (
        repository.transfers[retry_transfer_id].status
        is RemoteManualSelectionTransferStatus.VERIFIED
    )
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.VERIFIED


def test_size_quota_and_concurrency_gate_fail_before_streaming(tmp_path: Path) -> None:
    payload = _jpeg()
    limits = RemoteManualSelectionTransferLimits(
        max_file_bytes=len(payload) - 1,
        max_session_bytes=10_000,
        max_active_session_transfers=1,
        max_active_global_transfers=1,
        upload_timeout_seconds=5,
    )
    service, _repository = _service(tmp_path, payload, limits=limits)
    with pytest.raises(RemoteManualSelectionTransferLimitError):
        asyncio.run(
            service.upload(
                **_request(payload, uuid4()),
                chunks=_chunks(payload, 10),
            )
        )

    gate = RemoteManualSelectionTransferGate(
        RemoteManualSelectionTransferLimits(
            max_file_bytes=100,
            max_session_bytes=100,
            max_active_session_transfers=1,
            max_active_global_transfers=1,
            upload_timeout_seconds=5,
        )
    )
    release = gate.acquire(SESSION_ID, FILE_ID, 1)
    with pytest.raises(RemoteManualSelectionTransferRateLimitError):
        gate.acquire(SESSION_ID, uuid4(), 1)
    release()
    release()


def test_restart_recovers_checksum_matching_verified_artifact_without_resend(
    tmp_path: Path,
) -> None:
    payload = _jpeg()
    service, repository = _service(tmp_path, payload)
    transfer_id = uuid4()
    (tmp_path / f"{transfer_id}.verified").write_bytes(payload)
    consumed = False

    async def forbidden_body() -> AsyncIterator[bytes]:
        nonlocal consumed
        consumed = True
        yield payload

    result = asyncio.run(
        service.upload(
            **_request(payload, transfer_id),
            chunks=forbidden_body(),
        )
    )
    assert result.transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
    assert consumed is False
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.VERIFIED


def test_streamed_checksum_mismatch_is_rejected_after_incremental_write(
    tmp_path: Path,
) -> None:
    payload = _jpeg()
    changed = bytearray(payload)
    changed[-3] ^= 1
    service, repository = _service(tmp_path, payload)
    arguments = _request(payload, uuid4())

    with pytest.raises(Exception, match="checksum"):
        asyncio.run(
            service.upload(
                **arguments,
                chunks=_chunks(bytes(changed), 7),
            )
        )
    assert not list(tmp_path.glob("*.verified"))
    assert not list(tmp_path.glob("*.part"))
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED


def test_slow_stream_hits_wall_clock_timeout_and_removes_part(tmp_path: Path) -> None:
    payload = _jpeg()
    service, repository = _service(
        tmp_path,
        payload,
        limits=RemoteManualSelectionTransferLimits(
            max_file_bytes=len(payload),
            max_session_bytes=len(payload) * 2,
            max_active_session_transfers=1,
            max_active_global_transfers=1,
            upload_timeout_seconds=1,
        ),
    )

    async def slow() -> AsyncIterator[bytes]:
        await asyncio.sleep(2)
        yield payload

    with pytest.raises(RemoteManualSelectionTransferTimeoutError):
        asyncio.run(
            service.upload(
                **_request(payload, uuid4()),
                chunks=slow(),
            )
        )
    assert not list(tmp_path.glob("*.part"))
    assert not list(tmp_path.glob("*.verified"))
    assert repository.files[FILE_ID].status is RemoteManualSelectionFileStatus.FAILED


def _service(
    root: Path,
    payload: bytes,
    *,
    limits: RemoteManualSelectionTransferLimits | None = None,
) -> tuple[RemoteManualSelectionTransferService, InMemoryRemoteManualSelectionRepository]:
    checksum = hashlib.sha256(payload).hexdigest()
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
    repository.files[FILE_ID] = RemoteManualSelectionFileV1(
        id=FILE_ID,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="image.jpg",
        size_bytes=len(payload),
        last_modified_ms=123,
        mime_type="image/jpeg",
        desired_selected=True,
        selection_generation=1,
        status=RemoteManualSelectionFileStatus.SELECTION_QUEUED,
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
    )
    repository.file_revisions[FILE_ID] = 1
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=uuid4(),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=1,
        expected_server_revision=0,
        operation_type=RemoteManualSelectionOperationType.SELECT,
        selection_generation=1,
        range_start=1,
        range_end=9,
        recorded_at=datetime(2026, 8, 24, tzinfo=UTC),
        file_id=FILE_ID,
        image_path="image.jpg",
        source_index=0,
        image_checksum_sha256=checksum,
        output_name="seq_1-9.jpg",
    )
    repository.operations[command.operation_id] = RemoteManualSelectionOperationV1(
        command=command,
        command_checksum_sha256=command.checksum_sha256,
        status=RemoteManualSelectionOperationStatus.APPLIED,
        applied_server_revision=1,
        outcome_code="applied",
    )
    return (
        RemoteManualSelectionTransferService(
            repository,
            FakeAccess(),  # type: ignore[arg-type]
            FakeHost(root),  # type: ignore[arg-type]
            limits=limits,
        ),
        repository,
    )


def _request(payload: bytes, transfer_id: UUID) -> dict[str, object]:
    return {
        "batch_id": BATCH_ID,
        "file_id": FILE_ID,
        "generation": 1,
        "transfer_id": transfer_id,
        "declared_bytes": len(payload),
        "declared_last_modified_ms": 123,
        "declared_checksum_sha256": hashlib.sha256(payload).hexdigest(),
        "content_type": "application/octet-stream",
        "access_token": "token",
        "client_instance_id": CLIENT_ID,
    }


async def _chunks(payload: bytes, size: int) -> AsyncIterator[bytes]:
    for offset in range(0, len(payload), size):
        await asyncio.sleep(0)
        yield payload[offset : offset + size]


def _jpeg() -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 12), (200, 20, 10)).save(output, format="JPEG")
    return output.getvalue()
