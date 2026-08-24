"""Bounded streaming transfer for selected remote-manual-selection JPEGs."""

from __future__ import annotations

import asyncio
import hashlib
import os
from collections.abc import AsyncIterable, Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessService,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostRepository,
    RemoteManualSelectionHostService,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionTransferRecord,
)

JPEG_MIME_TYPES = frozenset({"image/jpeg", "image/jpg"})
TRANSFER_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True, slots=True)
class RemoteManualSelectionTransferLimits:
    max_file_bytes: int = 32 * 1024 * 1024
    max_session_bytes: int = 20 * 1024 * 1024 * 1024
    max_active_session_transfers: int = 4
    max_active_global_transfers: int = 8
    upload_timeout_seconds: int = 120

    def __post_init__(self) -> None:
        if (
            min(
                self.max_file_bytes,
                self.max_session_bytes,
                self.max_active_session_transfers,
                self.max_active_global_transfers,
                self.upload_timeout_seconds,
            )
            < 1
        ):
            raise ValueError("Remote selection transfer limits must be positive.")


class RemoteManualSelectionTransferLimitError(RemoteManualSelectionError):
    """The declared transfer cannot fit within an immutable size quota."""


class RemoteManualSelectionTransferRateLimitError(RemoteManualSelectionError):
    """The bounded concurrent transfer budget is exhausted."""


class RemoteManualSelectionTransferTimeoutError(RemoteManualSelectionError):
    """The streaming body exceeded the bounded wall-clock budget."""


class RemoteManualSelectionTransferRepository(RemoteManualSelectionHostRepository, Protocol):
    def get_file(self, *, batch_id: UUID, file_id: UUID) -> RemoteManualSelectionFileV1 | None: ...

    def get_applied_select_operation(
        self, *, batch_id: UUID, file_id: UUID, generation: int
    ) -> RemoteManualSelectionOperationV1 | None: ...

    def get_transfer_record(
        self, *, batch_id: UUID, file_id: UUID, transfer_id: UUID
    ) -> RemoteManualSelectionTransferRecord | None: ...

    def get_verified_transfer_record(
        self, *, batch_id: UUID, file_id: UUID, generation: int
    ) -> RemoteManualSelectionTransferRecord | None: ...

    def next_transfer_attempt(self, *, file_id: UUID, generation: int) -> int: ...

    def session_reserved_transfer_bytes(self, session_id: UUID) -> int: ...

    def add_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None = None,
        retry_at: datetime | None = None,
    ) -> RemoteManualSelectionTransferV1: ...

    def update_transfer(
        self,
        value: RemoteManualSelectionTransferV1,
        *,
        temp_relative_path: str | None,
    ) -> RemoteManualSelectionTransferV1: ...

    def update_file_transfer_status(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        status: RemoteManualSelectionFileStatus,
        temp_relative_path: str | None = None,
        host_checksum_sha256: str | None = None,
    ) -> RemoteManualSelectionFileV1: ...

    def ensure_materialization_action(
        self,
        *,
        session_id: UUID,
        batch_id: UUID,
        file_id: UUID,
        transfer_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionHostActionV1: ...


class RemoteManualSelectionTransferGate:
    """Process-local admission control; database invariants remain authoritative."""

    def __init__(self, limits: RemoteManualSelectionTransferLimits) -> None:
        self._limits = limits
        self._active: set[tuple[UUID, UUID, int]] = set()
        self._session_counts: dict[UUID, int] = {}
        self._lock = Lock()

    def acquire(self, session_id: UUID, file_id: UUID, generation: int) -> Callable[[], None]:
        key = (session_id, file_id, generation)
        with self._lock:
            if key in self._active:
                raise RemoteManualSelectionTransferRateLimitError(
                    "REMOTE_SELECTION_TRANSFER_ALREADY_ACTIVE",
                    "This selected file generation is already uploading.",
                )
            session_count = self._session_counts.get(session_id, 0)
            if (
                session_count >= self._limits.max_active_session_transfers
                or len(self._active) >= self._limits.max_active_global_transfers
            ):
                raise RemoteManualSelectionTransferRateLimitError(
                    "REMOTE_SELECTION_TRANSFER_RATE_LIMITED",
                    "The concurrent remote selection transfer limit is exhausted.",
                )
            self._active.add(key)
            self._session_counts[session_id] = session_count + 1

        released = False

        def release() -> None:
            nonlocal released
            with self._lock:
                if released:
                    return
                released = True
                self._active.discard(key)
                remaining = self._session_counts.get(session_id, 1) - 1
                if remaining > 0:
                    self._session_counts[session_id] = remaining
                else:
                    self._session_counts.pop(session_id, None)

        return release


class RemoteManualSelectionTransferService:
    def __init__(
        self,
        repository: RemoteManualSelectionTransferRepository,
        access_service: RemoteManualSelectionAccessService,
        host_service: RemoteManualSelectionHostService,
        *,
        limits: RemoteManualSelectionTransferLimits | None = None,
        gate: RemoteManualSelectionTransferGate | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._access = access_service
        self._host = host_service
        self._limits = limits or RemoteManualSelectionTransferLimits()
        self._gate = gate or RemoteManualSelectionTransferGate(self._limits)
        self._clock = clock or (lambda: datetime.now(UTC))

    def status(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        transfer_id: UUID | None,
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionTransferRecord | None:
        context = self._access.context(
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        self._selected_file(
            batch_id,
            file_id,
            generation,
            session_id=context.session_id,
        )
        if transfer_id is not None:
            record = self._repository.get_transfer_record(
                batch_id=batch_id,
                file_id=file_id,
                transfer_id=transfer_id,
            )
            if record is not None and record.transfer.generation != generation:
                raise _transfer_conflict("The transfer ID belongs to another generation.")
            if (
                record is not None
                and record.transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
            ):
                self._ensure_materialization(record.transfer)
            return record
        record = self._repository.get_verified_transfer_record(
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
        )
        if (
            record is not None
            and record.transfer.status is RemoteManualSelectionTransferStatus.VERIFIED
        ):
            self._ensure_materialization(record.transfer)
        return record

    async def upload(
        self,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        transfer_id: UUID,
        declared_bytes: int,
        declared_last_modified_ms: int,
        declared_checksum_sha256: str,
        content_type: str,
        chunks: AsyncIterable[bytes],
        access_token: str,
        client_instance_id: UUID,
    ) -> RemoteManualSelectionTransferRecord:
        context = self._access.context(
            access_token=access_token,
            client_instance_id=client_instance_id,
        )
        file = self._selected_file(
            batch_id,
            file_id,
            generation,
            session_id=context.session_id,
        )
        self._validate_declaration(
            file,
            declared_bytes=declared_bytes,
            declared_last_modified_ms=declared_last_modified_ms,
            declared_checksum_sha256=declared_checksum_sha256,
            content_type=content_type,
        )
        operation = self._repository.get_applied_select_operation(
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
        )
        if operation is None or operation.command.image_checksum_sha256 is None:
            raise _transfer_conflict(
                "The selected generation has no checksum-bound confirmed SELECT operation."
            )
        if operation.command.image_checksum_sha256 != declared_checksum_sha256:
            raise _transfer_conflict("The upload checksum differs from the confirmed selection.")

        existing_verified = self._repository.get_verified_transfer_record(
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
        )
        if existing_verified is not None:
            self._assert_exact_metadata(
                existing_verified.transfer,
                declared_bytes,
                declared_checksum_sha256,
            )
            self._ensure_materialization(existing_verified.transfer)
            return existing_verified
        existing = self._repository.get_transfer_record(
            batch_id=batch_id,
            file_id=file_id,
            transfer_id=transfer_id,
        )
        if existing is not None:
            self._assert_exact_metadata(existing.transfer, declared_bytes, declared_checksum_sha256)
            if existing.transfer.generation != generation:
                raise _transfer_conflict("The transfer ID belongs to another generation.")
            if existing.transfer.status in {
                RemoteManualSelectionTransferStatus.VERIFIED,
                RemoteManualSelectionTransferStatus.MATERIALIZED,
            }:
                self._ensure_materialization(existing.transfer)
                return existing
            raise _transfer_conflict("The transfer request ID is already in progress or terminal.")

        self._access.authorize_writer(
            session_id=file.session_id,
            access_token=access_token,
            client_instance_id=client_instance_id,
        )

        reserved = self._repository.session_reserved_transfer_bytes(file.session_id)
        if reserved + declared_bytes > self._limits.max_session_bytes:
            raise RemoteManualSelectionTransferLimitError(
                "REMOTE_SELECTION_SESSION_QUOTA_EXCEEDED",
                "The remote selection session temporary storage quota would be exceeded.",
            )
        release = self._gate.acquire(file.session_id, file.id, generation)
        try:
            return await self._upload_exclusive(
                file=file,
                transfer_id=transfer_id,
                generation=generation,
                declared_bytes=declared_bytes,
                declared_checksum_sha256=declared_checksum_sha256,
                chunks=chunks,
            )
        finally:
            release()

    async def _upload_exclusive(
        self,
        *,
        file: RemoteManualSelectionFileV1,
        transfer_id: UUID,
        generation: int,
        declared_bytes: int,
        declared_checksum_sha256: str,
        chunks: AsyncIterable[bytes],
    ) -> RemoteManualSelectionTransferRecord:
        transfer = RemoteManualSelectionTransferV1(
            id=transfer_id,
            session_id=file.session_id,
            batch_id=file.batch_id,
            file_id=file.id,
            generation=generation,
            attempt=self._repository.next_transfer_attempt(
                file_id=file.id,
                generation=generation,
            ),
            declared_bytes=declared_bytes,
            received_bytes=0,
            status=RemoteManualSelectionTransferStatus.QUEUED,
            declared_checksum_sha256=declared_checksum_sha256,
        )
        self._repository.add_transfer(transfer)
        transfer = replace(transfer, status=RemoteManualSelectionTransferStatus.UPLOADING)
        self._repository.update_transfer(transfer, temp_relative_path=None)
        self._advance_file_to_uploading(file)

        part_path: Path | None = None
        try:
            with self._host.open_transfer_directory(
                self._repository,
                session_id=file.session_id,
                batch_id=file.batch_id,
                file_id=file.id,
                generation=generation,
            ) as directory:
                part_name = f"{transfer_id}.part"
                verified_name = f"{transfer_id}.verified"
                part_path = directory.path / part_name
                verified_path = directory.path / verified_name
                if verified_path.exists():
                    checksum = await asyncio.to_thread(_checksum_regular_file, verified_path)
                    if (
                        verified_path.stat().st_size != declared_bytes
                        or checksum != declared_checksum_sha256
                    ):
                        raise _transfer_conflict(
                            "The recovered verified artifact differs from this request."
                        )
                    await asyncio.to_thread(_validate_jpeg, verified_path)
                    verified_relative_path = f"{directory.relative_path}/{verified_name}"
                    transfer = replace(
                        transfer,
                        received_bytes=declared_bytes,
                        status=RemoteManualSelectionTransferStatus.STORED_TEMP,
                    )
                    self._repository.update_transfer(
                        transfer,
                        temp_relative_path=verified_relative_path,
                    )
                    transfer = replace(
                        transfer,
                        status=RemoteManualSelectionTransferStatus.VERIFIED,
                        verified_checksum_sha256=checksum,
                    )
                    self._repository.update_transfer(
                        transfer,
                        temp_relative_path=verified_relative_path,
                    )
                    self._advance_file_from_uploading_to_verified(
                        file,
                        verified_relative_path,
                        checksum,
                    )
                    self._ensure_materialization(transfer)
                    return RemoteManualSelectionTransferRecord(
                        transfer,
                        verified_relative_path,
                    )
                with suppress(FileNotFoundError):
                    part_path.unlink()
                received, checksum = await self._stream_to_part(
                    part_path,
                    chunks,
                    declared_bytes=declared_bytes,
                )
                part_relative_path = f"{directory.relative_path}/{part_name}"
                transfer = replace(
                    transfer,
                    received_bytes=received,
                    status=RemoteManualSelectionTransferStatus.STORED_TEMP,
                )
                self._repository.update_transfer(
                    transfer,
                    temp_relative_path=part_relative_path,
                )
                if checksum != declared_checksum_sha256:
                    raise RemoteManualSelectionError(
                        "REMOTE_SELECTION_TRANSFER_CHECKSUM_MISMATCH",
                        "The streamed JPEG checksum does not match the selected image.",
                    )
                await asyncio.to_thread(_validate_jpeg, part_path)
                if verified_path.exists():
                    raise _transfer_conflict("A verified artifact already exists for this request.")
                os.rename(part_path, verified_path)
                part_path = None
                verified_relative_path = f"{directory.relative_path}/{verified_name}"
                transfer = replace(
                    transfer,
                    status=RemoteManualSelectionTransferStatus.VERIFIED,
                    verified_checksum_sha256=checksum,
                )
                self._repository.update_transfer(
                    transfer,
                    temp_relative_path=verified_relative_path,
                )
                self._advance_file_from_uploading_to_verified(
                    file,
                    verified_relative_path,
                    checksum,
                )
                self._ensure_materialization(transfer)
                return RemoteManualSelectionTransferRecord(transfer, verified_relative_path)
        except BaseException:
            if part_path is not None:
                with suppress(OSError):
                    part_path.unlink(missing_ok=True)
            self._mark_failed_best_effort(file, transfer)
            raise

    async def _stream_to_part(
        self,
        path: Path,
        chunks: AsyncIterable[bytes],
        *,
        declared_bytes: int,
    ) -> tuple[int, str]:
        received = 0
        digest = hashlib.sha256()
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as stream:
                descriptor = -1
                try:
                    async with asyncio.timeout(self._limits.upload_timeout_seconds):
                        async for source_chunk in chunks:
                            if not source_chunk:
                                continue
                            view = memoryview(source_chunk)
                            for offset in range(0, len(view), TRANSFER_CHUNK_BYTES):
                                chunk = view[offset : offset + TRANSFER_CHUNK_BYTES]
                                received += len(chunk)
                                if received > declared_bytes:
                                    raise RemoteManualSelectionTransferLimitError(
                                        "REMOTE_SELECTION_TRANSFER_TOO_LARGE",
                                        "The streamed body exceeds its declared size.",
                                    )
                                stream.write(chunk)
                                digest.update(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                except TimeoutError as error:
                    raise RemoteManualSelectionTransferTimeoutError(
                        "REMOTE_SELECTION_TRANSFER_TIMEOUT",
                        "The selected JPEG transfer exceeded its time limit.",
                    ) from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)
        if received != declared_bytes:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_TRANSFER_SIZE_MISMATCH",
                "The streamed body length does not match its declaration.",
            )
        return received, digest.hexdigest()

    def _selected_file(
        self,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
        *,
        session_id: UUID,
    ) -> RemoteManualSelectionFileV1:
        file = self._repository.get_file(batch_id=batch_id, file_id=file_id)
        if (
            file is None
            or file.session_id != session_id
            or not file.desired_selected
            or file.selection_generation != generation
        ):
            raise RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_TRANSFER_GENERATION_CONFLICT",
                "Only the confirmed current selected file generation can be transferred.",
            )
        return file

    def _validate_declaration(
        self,
        file: RemoteManualSelectionFileV1,
        *,
        declared_bytes: int,
        declared_last_modified_ms: int,
        declared_checksum_sha256: str,
        content_type: str,
    ) -> None:
        if declared_bytes < 1 or declared_bytes > self._limits.max_file_bytes:
            raise RemoteManualSelectionTransferLimitError(
                "REMOTE_SELECTION_TRANSFER_TOO_LARGE",
                "The selected JPEG exceeds the per-file transfer limit.",
            )
        if declared_bytes != file.size_bytes or declared_last_modified_ms != file.last_modified_ms:
            raise _transfer_conflict("The upload metadata differs from the immutable source item.")
        if file.mime_type.lower() not in JPEG_MIME_TYPES:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_TRANSFER_SOURCE_TYPE_INVALID",
                "The canonical source item is not a JPEG.",
            )
        if content_type.lower() != "application/octet-stream":
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_TRANSFER_CONTENT_TYPE_INVALID",
                "JPEG transfers must use application/octet-stream.",
            )
        if len(declared_checksum_sha256) != 64 or any(
            value not in "0123456789abcdef" for value in declared_checksum_sha256
        ):
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_TRANSFER_CHECKSUM_INVALID",
                "The declared SHA-256 checksum is invalid.",
            )

    @staticmethod
    def _assert_exact_metadata(
        transfer: RemoteManualSelectionTransferV1,
        declared_bytes: int,
        declared_checksum_sha256: str,
    ) -> None:
        if (
            transfer.declared_bytes != declared_bytes
            or transfer.declared_checksum_sha256 != declared_checksum_sha256
        ):
            raise _transfer_conflict("The transfer request was reused with different content.")

    def _advance_file_to_uploading(self, file: RemoteManualSelectionFileV1) -> None:
        status = file.status
        if status is RemoteManualSelectionFileStatus.FAILED:
            self._repository.update_file_transfer_status(
                batch_id=file.batch_id,
                file_id=file.id,
                generation=file.selection_generation,
                status=RemoteManualSelectionFileStatus.RETRYING,
            )
            status = RemoteManualSelectionFileStatus.RETRYING
        if status in {
            RemoteManualSelectionFileStatus.SELECTION_QUEUED,
            RemoteManualSelectionFileStatus.RETRYING,
        }:
            self._repository.update_file_transfer_status(
                batch_id=file.batch_id,
                file_id=file.id,
                generation=file.selection_generation,
                status=RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
            )
            status = RemoteManualSelectionFileStatus.UPLOAD_QUEUED
        if status is RemoteManualSelectionFileStatus.UPLOAD_QUEUED:
            self._repository.update_file_transfer_status(
                batch_id=file.batch_id,
                file_id=file.id,
                generation=file.selection_generation,
                status=RemoteManualSelectionFileStatus.UPLOADING,
            )
            return
        if status is not RemoteManualSelectionFileStatus.UPLOADING:
            raise _transfer_conflict("The selected file is not ready for upload.")

    def _mark_failed_best_effort(
        self,
        file: RemoteManualSelectionFileV1,
        transfer: RemoteManualSelectionTransferV1,
    ) -> None:
        with suppress(RemoteManualSelectionError):
            current = self._repository.get_transfer_record(
                batch_id=file.batch_id,
                file_id=file.id,
                transfer_id=transfer.id,
            )
            if current is not None and current.transfer.status in {
                RemoteManualSelectionTransferStatus.UPLOADING,
                RemoteManualSelectionTransferStatus.STORED_TEMP,
            }:
                self._repository.update_transfer(
                    replace(
                        current.transfer,
                        status=RemoteManualSelectionTransferStatus.FAILED,
                    ),
                    temp_relative_path=None,
                )
        with suppress(RemoteManualSelectionError):
            current_file = self._repository.get_file(batch_id=file.batch_id, file_id=file.id)
            if current_file is not None and current_file.status in {
                RemoteManualSelectionFileStatus.SELECTION_QUEUED,
                RemoteManualSelectionFileStatus.UPLOAD_QUEUED,
                RemoteManualSelectionFileStatus.UPLOADING,
                RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
            }:
                self._repository.update_file_transfer_status(
                    batch_id=file.batch_id,
                    file_id=file.id,
                    generation=file.selection_generation,
                    status=RemoteManualSelectionFileStatus.FAILED,
                )

    def _advance_file_from_uploading_to_verified(
        self,
        file: RemoteManualSelectionFileV1,
        verified_relative_path: str,
        checksum: str,
    ) -> None:
        self._repository.update_file_transfer_status(
            batch_id=file.batch_id,
            file_id=file.id,
            generation=file.selection_generation,
            status=RemoteManualSelectionFileStatus.STORED_TEMPORARILY,
            temp_relative_path=verified_relative_path,
        )
        self._repository.update_file_transfer_status(
            batch_id=file.batch_id,
            file_id=file.id,
            generation=file.selection_generation,
            status=RemoteManualSelectionFileStatus.VERIFIED,
            temp_relative_path=verified_relative_path,
            host_checksum_sha256=checksum,
        )

    def _ensure_materialization(self, transfer: RemoteManualSelectionTransferV1) -> None:
        self._repository.ensure_materialization_action(
            session_id=transfer.session_id,
            batch_id=transfer.batch_id,
            file_id=transfer.file_id,
            transfer_id=transfer.id,
            generation=transfer.generation,
        )


def _validate_jpeg(path: Path) -> None:
    try:
        with path.open("rb") as stream:
            if stream.read(3) != b"\xff\xd8\xff":
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_TRANSFER_JPEG_INVALID",
                    "The uploaded content has no JPEG signature.",
                )
        with Image.open(path) as image:
            if image.format != "JPEG":
                raise RemoteManualSelectionError(
                    "REMOTE_SELECTION_TRANSFER_JPEG_INVALID",
                    "The uploaded content is not a JPEG image.",
                )
            image.verify()
        with Image.open(path) as image:
            image.load()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise RemoteManualSelectionError(
            "REMOTE_SELECTION_TRANSFER_JPEG_INVALID",
            "The uploaded JPEG cannot be decoded safely.",
        ) from error


def _checksum_regular_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(TRANSFER_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _transfer_conflict(message: str) -> RemoteManualSelectionConflictError:
    return RemoteManualSelectionConflictError(
        "REMOTE_SELECTION_TRANSFER_CONFLICT",
        message,
    )


__all__ = [
    "RemoteManualSelectionTransferGate",
    "RemoteManualSelectionTransferLimitError",
    "RemoteManualSelectionTransferLimits",
    "RemoteManualSelectionTransferRateLimitError",
    "RemoteManualSelectionTransferService",
    "RemoteManualSelectionTransferTimeoutError",
]
