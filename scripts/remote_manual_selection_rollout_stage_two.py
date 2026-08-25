"""Local real-filesystem sub-gate for stage two of remote-selection rollout."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import tracemalloc
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from time import perf_counter, process_time
from typing import TypedDict
from uuid import UUID

from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessService,
    RemoteManualSelectionAuthenticationError,
)
from game_predictor_api.application.remote_manual_selection_control import (
    RemoteManualSelectionControlService,
    source_file,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.application.remote_manual_selection_materialization import (
    RemoteManualSelectionHostMaterializer,
)
from game_predictor_api.application.remote_manual_selection_rollout import build_rollout_report
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferService,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationType,
    RemoteSourceKind,
    RemoteSourceManifestEntryV1,
    build_remote_source_manifest,
)
from game_predictor_api.storage.remote_manual_selection_access_repository import (
    InMemoryRemoteManualSelectionAccessRepository,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    InMemoryRemoteManualSelectionRepository,
)
from PIL import Image

STAGE_TWO_FILE_COUNT = 100
CLIENT_ID = UUID("40000000-0000-4000-8000-000000000004")
COLLECTION_ID = UUID("20000000-0000-4000-8000-000000000002")
BATCH_ID = UUID("30000000-0000-4000-8000-000000000003")
NOW = datetime(2026, 8, 24, 21, tzinfo=UTC)


class _UploadArguments(TypedDict):
    batch_id: UUID
    file_id: UUID
    generation: int
    transfer_id: UUID
    declared_bytes: int
    declared_last_modified_ms: int
    declared_checksum_sha256: str
    content_type: str
    access_token: str
    client_instance_id: UUID


def _uuid(namespace: int, index: int) -> UUID:
    return UUID(f"{namespace:08x}-0000-4000-8000-{index:012x}")


def _jpeg(index: int) -> bytes:
    output = BytesIO()
    Image.new(
        "RGB",
        (32, 24),
        (index * 13 % 255, index * 29 % 255, index * 43 % 255),
    ).save(output, format="JPEG", quality=90)
    return output.getvalue()


async def _chunks(payload: bytes, chunk_bytes: int = 127) -> AsyncIterator[bytes]:
    for offset in range(0, len(payload), chunk_bytes):
        yield payload[offset : offset + chunk_bytes]


async def _offline_chunks(payload: bytes) -> AsyncIterator[bytes]:
    yield payload[:17]
    raise ConnectionError("synthetic host disconnect")


def build_stage_two_local_report(
    *,
    prior_stage_checksum_sha256: str,
) -> dict[str, object]:
    """Run 100 real JPEGs locally; keep the external UI/LAN gate explicitly blocked."""

    tracemalloc.start()
    wall_started = perf_counter()
    cpu_started = process_time()
    payloads = tuple(_jpeg(index) for index in range(STAGE_TWO_FILE_COUNT))
    checksums = tuple(hashlib.sha256(payload).hexdigest() for payload in payloads)
    source_sizes = tuple(len(payload) for payload in payloads)
    operation_latencies: list[float] = []
    transfer_latencies: list[float] = []
    host_latencies: list[float] = []
    throughput_samples: list[float] = []
    retry_count = 0
    api_retry_ok = False
    offline_operator_ok = False
    offline_host_ok = False
    revoke_ok = False

    with tempfile.TemporaryDirectory(prefix="remote-selection-stage-2-") as temporary:
        base = Path(temporary) / "base"
        base.mkdir()
        host = RemoteManualSelectionHostService(lambda: base, clock=lambda: NOW)
        capability = host.select_base()
        if capability is None:
            raise RuntimeError("Stage-two host base was not selected.")
        access_repository = InMemoryRemoteManualSelectionAccessRepository()
        access = RemoteManualSelectionAccessService(
            access_repository,
            host,
            now=lambda: NOW,
        )
        created = access.create(
            base_capability=capability.capability,
            lifetime_minutes=60,
            label="Stage 2 local",
        )
        session_id = created.session.session_id
        access_record = access_repository.records[session_id]
        repository = InMemoryRemoteManualSelectionRepository()
        repository.add_session(
            access_record.session,
            base_binding_id=access_record.base_binding_id,
            host_base_path=access_record.host_base_path,
            display_name=access_record.display_name,
        )
        unlocked = access.unlock(
            session_id=session_id,
            access_code=created.access_code,
            client_instance_id=CLIENT_ID,
        )
        token = unlocked.access_token
        control = RemoteManualSelectionControlService(
            repository,
            access,
            host,
            now=lambda: NOW,
        )
        entries = tuple(
            RemoteSourceManifestEntryV1(
                ordinal=index,
                relative_path=f"source/{index + 1}.jpg",
                name=f"{index + 1}.jpg",
                size_bytes=source_sizes[index],
                last_modified_ms=1_700_000_000_000 + index,
                mime_type="image/jpeg",
            )
            for index in range(STAGE_TWO_FILE_COUNT)
        )
        manifest = build_remote_source_manifest(
            entries,
            source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
        )
        control.create_collection(
            session_id=session_id,
            collection_id=COLLECTION_ID,
            name="rollout-stage-2",
            access_token=token,
            client_instance_id=CLIENT_ID,
        )
        control.create_batch(
            session_id=session_id,
            collection_id=COLLECTION_ID,
            batch_id=BATCH_ID,
            name="1-900",
            source_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
            first_layout=1,
            direction=RemoteManualSelectionDirection.ASCENDING,
            total_file_count=STAGE_TWO_FILE_COUNT,
            access_token=token,
            client_instance_id=CLIENT_ID,
        )
        files = tuple(
            source_file(
                file_id=_uuid(0x50000000, index + 1),
                session_id=session_id,
                batch_id=BATCH_ID,
                source_index=index,
                relative_path=entry.relative_path,
                size_bytes=entry.size_bytes,
                last_modified_ms=entry.last_modified_ms,
                mime_type=entry.mime_type,
            )
            for index, entry in enumerate(entries)
        )
        control.register_source_items(
            session_id=session_id,
            batch_id=BATCH_ID,
            files=files,
            source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
            complete=True,
            access_token=token,
            client_instance_id=CLIENT_ID,
        )

        for index, file in enumerate(files):
            start = index * 9 + 1
            command = RemoteManualSelectionOperationCommandV1(
                operation_id=_uuid(0x60000000, index + 1),
                session_id=session_id,
                batch_id=BATCH_ID,
                client_instance_id=CLIENT_ID,
                client_sequence=index + 1,
                expected_server_revision=index,
                operation_type=RemoteManualSelectionOperationType.SELECT,
                selection_generation=1,
                range_start=start,
                range_end=start + 8,
                recorded_at=NOW + timedelta(milliseconds=index),
                file_id=file.id,
                image_path=file.relative_path,
                source_index=index,
                image_checksum_sha256=checksums[index],
                output_name=f"seq_{start}-{start + 8}.jpg",
                visible_milliseconds=400,
                decoded=True,
            )
            measured = perf_counter()
            applied = control.apply_operation(
                command=command,
                access_token=token,
                client_instance_id=CLIENT_ID,
            )
            operation_latencies.append((perf_counter() - measured) * 1_000)
            if index == 0:
                retry_count += 1
                replay = control.apply_operation(
                    command=command,
                    access_token=token,
                    client_instance_id=CLIENT_ID,
                )
                api_retry_ok = (
                    replay.exact_retry
                    and replay.batch.server_revision == applied.batch.server_revision
                )
            if index == 49:
                control = RemoteManualSelectionControlService(
                    repository,
                    access,
                    RemoteManualSelectionHostService(lambda: None, clock=lambda: NOW),
                    now=lambda: NOW,
                )
                restored = control.state_delta(
                    batch_id=BATCH_ID,
                    since_revision=0,
                    limit=STAGE_TWO_FILE_COUNT,
                    access_token=token,
                    client_instance_id=CLIENT_ID,
                )
                offline_operator_ok = (
                    restored.batch.server_revision == 50
                    and len(restored.files) == 50
                    and not restored.has_more
                )

        transfer = RemoteManualSelectionTransferService(
            repository,
            access,
            host,
            clock=lambda: NOW,
        )
        materializer = RemoteManualSelectionHostMaterializer(host)
        for index, file in enumerate(files):
            if index == 1:
                retry_count += 1
                try:
                    asyncio.run(
                        transfer.upload(
                            **_upload_arguments(
                                session_token=token,
                                file=file,
                                transfer_id=_uuid(0x70000000, 1),
                                payload=payloads[index],
                                checksum=checksums[index],
                            ),
                            chunks=_offline_chunks(payloads[index]),
                        )
                    )
                except ConnectionError:
                    offline_host_ok = True
                transfer = RemoteManualSelectionTransferService(
                    repository,
                    access,
                    RemoteManualSelectionHostService(lambda: None, clock=lambda: NOW),
                    clock=lambda: NOW,
                )
            measured = perf_counter()
            asyncio.run(
                transfer.upload(
                    **_upload_arguments(
                        session_token=token,
                        file=file,
                        transfer_id=_uuid(0x71000000, index + 1),
                        payload=payloads[index],
                        checksum=checksums[index],
                    ),
                    chunks=_chunks(payloads[index]),
                )
            )
            elapsed = max((perf_counter() - measured) * 1_000, 0.001)
            transfer_latencies.append(elapsed)
            throughput_samples.append(len(payloads[index]) * 1_000 / elapsed)
            measured = perf_counter()
            _materialize_one(repository, materializer)
            host_latencies.append((perf_counter() - measured) * 1_000)

        preview = control.finalize_preview(
            batch_id=BATCH_ID,
            access_token=token,
            client_instance_id=CLIENT_ID,
        )
        if not preview.ready:
            blockers = ", ".join(f"{item.code}={item.count}" for item in preview.blockers)
            raise RuntimeError(f"Stage-two batch did not become finalizable: {blockers}.")
        finalized = control.finalize_batch(
            session_id=session_id,
            batch_id=BATCH_ID,
            expected_server_revision=preview.server_revision,
            access_token=token,
            client_instance_id=CLIENT_ID,
        )
        final_directory = base / "rollout-stage-2" / "1-900"
        output_manifest = json.loads(
            (final_directory / "manual-image-selection-output-v1.json").read_text(encoding="utf-8")
        )
        trace_manifest = json.loads(
            (final_directory / "manual-image-selection-trace-v1.json").read_text(encoding="utf-8")
        )
        output_items = output_manifest.get("items", [])
        trace_events = trace_manifest.get("events", [])
        host_files = tuple(final_directory.glob("seq_*.jpg"))
        jpeg_mismatches = sum(
            hashlib.sha256(path.read_bytes()).hexdigest()
            != checksums[(int(path.stem.split("_")[1].split("-")[0]) - 1) // 9]
            for path in host_files
        )
        access.revoke(session_id)
        try:
            access.context(access_token=token, client_instance_id=CLIENT_ID)
        except RemoteManualSelectionAuthenticationError:
            revoke_ok = True

        _, peak_memory_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        duration_ms = (perf_counter() - wall_started) * 1_000
        cpu_ms = (process_time() - cpu_started) * 1_000
        return build_rollout_report(
            stage_id="stage-2",
            environment={
                "executionMode": "local_real_filesystem_subgate",
                "externalUiEvidence": "pending",
                "transport": "in_process_no_public_route",
            },
            environment_gate_passed=False,
            source_manifest_checksum_sha256=manifest.manifest_checksum_sha256,
            source_file_count=STAGE_TWO_FILE_COUNT,
            source_size_bytes=source_sizes,
            operation_count=STAGE_TWO_FILE_COUNT,
            selected_file_count=STAGE_TWO_FILE_COUNT,
            host_output_file_count=len(host_files),
            output_manifest_item_count=len(output_items),
            trace_event_count=len(trace_events),
            ui_latency_samples_ms=operation_latencies,
            api_latency_samples_ms=operation_latencies,
            transfer_latency_samples_ms=transfer_latencies,
            host_queue_latency_samples_ms=host_latencies,
            duration_milliseconds=duration_ms,
            throughput_bytes_per_second_samples=throughput_samples,
            process_cpu_milliseconds=cpu_ms,
            peak_process_memory_bytes=max(peak_memory_bytes, 1),
            retry_count=retry_count,
            conflict_count=0,
            jpeg_checksum_mismatch_count=jpeg_mismatches,
            json_parity_mismatch_count=(
                0
                if finalized.snapshot.selected_file_count == len(host_files) == len(output_items)
                else 1
            ),
            fault_outcomes={
                "api_5xx_retry": api_retry_ok,
                "offline_host": offline_host_ok,
                "offline_operator": offline_operator_ok,
                "revoke": revoke_ok,
            },
            prior_stage_checksums={"stage-1": prior_stage_checksum_sha256},
        )


def _upload_arguments(
    *,
    session_token: str,
    file: RemoteManualSelectionFileV1,
    transfer_id: UUID,
    payload: bytes,
    checksum: str,
) -> _UploadArguments:
    return {
        "batch_id": BATCH_ID,
        "file_id": file.id,
        "generation": 1,
        "transfer_id": transfer_id,
        "declared_bytes": len(payload),
        "declared_last_modified_ms": file.last_modified_ms,
        "declared_checksum_sha256": checksum,
        "content_type": "application/octet-stream",
        "access_token": session_token,
        "client_instance_id": CLIENT_ID,
    }


def _materialize_one(
    repository: InMemoryRemoteManualSelectionRepository,
    materializer: RemoteManualSelectionHostMaterializer,
) -> None:
    claim = repository.claim_next_materialization_action(
        lease_owner="stage-2-worker",
        lease_duration=timedelta(seconds=30),
        claimed_at=NOW,
    )
    if claim is None or claim.lease_token is None:
        raise RuntimeError("Stage-two materialization action was not queued.")
    lease_token = claim.lease_token
    context = repository.lock_materialization_context(
        action_id=claim.action.id,
        lease_token=lease_token,
        locked_at=NOW,
    )
    if context is None:
        raise RuntimeError("Stage-two materialization was superseded unexpectedly.")

    def complete(relative_path: str) -> None:
        repository.complete_materialization_action(
            context,
            lease_token=lease_token,
            final_relative_path=relative_path,
            completed_at=NOW,
        )

    materializer.materialize(repository, context, on_published=complete)


__all__ = ["STAGE_TWO_FILE_COUNT", "build_stage_two_local_report"]
