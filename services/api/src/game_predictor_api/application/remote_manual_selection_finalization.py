"""Deterministic finalization barrier and manifest projections."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionManifestV1,
    RemoteManualSelectionOperationStatus,
    RemoteManualSelectionTransferStatus,
    project_manual_selection_output_v1,
    project_manual_selection_trace_v1,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionFinalizationSnapshot,
)

REMOTE_WORKSPACE_PREFIX = "remote-manual-selection"


@dataclass(frozen=True, slots=True)
class RemoteSelectionFinalizeBlocker:
    code: str
    count: int


@dataclass(frozen=True, slots=True)
class RemoteSelectionFinalizePreview:
    batch_id: str
    status: str
    server_revision: int
    ready: bool
    total_file_count: int
    selected_file_count: int
    synced_file_count: int
    operation_count: int
    blockers: tuple[RemoteSelectionFinalizeBlocker, ...]


@dataclass(frozen=True, slots=True)
class RemoteSelectionFinalizationPayloads:
    output_manifest: dict[str, object]
    trace_manifest: dict[str, object]
    operational_manifest: dict[str, object]
    final_manifest_checksum_sha256: str


def build_remote_selection_finalize_preview(
    snapshot: RemoteManualSelectionFinalizationSnapshot,
) -> RemoteSelectionFinalizePreview:
    blockers: dict[str, int] = {}

    def block(code: str, count: int = 1) -> None:
        if count > 0:
            blockers[code] = blockers.get(code, 0) + count

    files = snapshot.files
    selected = tuple(item for item in files if item.file.desired_selected)
    synced = tuple(
        item
        for item in selected
        if item.file.status.value == "synced"
        and item.file.host_checksum_sha256 is not None
        and item.file.output_name is not None
        and item.final_relative_path == item.file.output_name
    )
    if len(files) != snapshot.total_file_count:
        block("REMOTE_SELECTION_SOURCE_COUNT_MISMATCH")
    if len(selected) != snapshot.selected_file_count:
        block("REMOTE_SELECTION_SELECTED_COUNTER_MISMATCH")
    if len(synced) != snapshot.transferred_file_count:
        block("REMOTE_SELECTION_SYNCED_COUNTER_MISMATCH")
    block("REMOTE_SELECTION_SELECTED_FILE_NOT_SYNCED", len(selected) - len(synced))

    pending_removals = sum(
        not item.file.desired_selected
        and item.file.status.value in {"deselect_pending", "failed", "retrying"}
        for item in files
    )
    block("REMOTE_SELECTION_REMOVAL_PENDING", pending_removals)

    active_operations = sum(
        item.status
        in {
            RemoteManualSelectionOperationStatus.QUEUED,
            RemoteManualSelectionOperationStatus.SENDING,
            RemoteManualSelectionOperationStatus.RETRY,
        }
        for item in snapshot.operations
    )
    block("REMOTE_SELECTION_OPERATION_PENDING", active_operations)

    current_generations = {item.file.id: item.file.selection_generation for item in files}
    active_transfers = sum(
        item.status
        in {
            RemoteManualSelectionTransferStatus.QUEUED,
            RemoteManualSelectionTransferStatus.UPLOADING,
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.VERIFIED,
            RemoteManualSelectionTransferStatus.RETRYING,
        }
        or (
            item.status is RemoteManualSelectionTransferStatus.FAILED
            and item.generation == current_generations.get(item.file_id)
        )
        for item in snapshot.transfers
    )
    block("REMOTE_SELECTION_TRANSFER_PENDING", active_transfers)

    active_actions = sum(
        item.status
        in {
            RemoteManualSelectionHostActionStatus.QUEUED,
            RemoteManualSelectionHostActionStatus.PROCESSING,
            RemoteManualSelectionHostActionStatus.RETRY,
        }
        or (
            item.status is RemoteManualSelectionHostActionStatus.FAILED
            and item.generation == current_generations.get(item.file_id)
        )
        for item in snapshot.host_actions
    )
    block("REMOTE_SELECTION_HOST_ACTION_PENDING", active_actions)

    ranges: set[tuple[int, int]] = set()
    output_names: set[str] = set()
    for item in selected:
        file = item.file
        if file.range_start is None or file.range_end is None or file.output_name is None:
            block("REMOTE_SELECTION_SELECTED_FILE_METADATA_INCOMPLETE")
            continue
        range_key = (file.range_start, file.range_end)
        if range_key in ranges:
            block("REMOTE_SELECTION_DUPLICATE_RANGE")
        ranges.add(range_key)
        if file.output_name in output_names:
            block("REMOTE_SELECTION_DUPLICATE_OUTPUT_NAME")
        output_names.add(file.output_name)

    if snapshot.batch.status not in {
        RemoteManualSelectionBatchStatus.ACTIVE,
        RemoteManualSelectionBatchStatus.FINALIZING,
        RemoteManualSelectionBatchStatus.COMPLETED,
    }:
        block("REMOTE_SELECTION_BATCH_NOT_FINALIZABLE")

    ordered = tuple(
        RemoteSelectionFinalizeBlocker(code=code, count=count)
        for code, count in sorted(blockers.items())
    )
    return RemoteSelectionFinalizePreview(
        batch_id=str(snapshot.batch.id),
        status=snapshot.batch.status.value,
        server_revision=snapshot.batch.server_revision,
        ready=not ordered,
        total_file_count=snapshot.total_file_count,
        selected_file_count=len(selected),
        synced_file_count=len(synced),
        operation_count=len(snapshot.operations),
        blockers=ordered,
    )


def build_remote_selection_finalization_payloads(
    snapshot: RemoteManualSelectionFinalizationSnapshot,
    *,
    finalized_at: datetime,
) -> RemoteSelectionFinalizationPayloads:
    preview = build_remote_selection_finalize_preview(snapshot)
    if not preview.ready:
        raise ValueError("A blocked remote selection snapshot cannot be projected.")
    workspace_id = f"{REMOTE_WORKSPACE_PREFIX}:{snapshot.batch.session_id}"
    session_key = f"remote:{snapshot.batch.session_id}:{snapshot.batch.id}"
    files = tuple(item.file for item in snapshot.files)
    output = project_manual_selection_output_v1(
        workspace_id=workspace_id,
        session_key=session_key,
        source_directory_name=snapshot.batch.name,
        direction=snapshot.batch.direction,
        first_layout=snapshot.batch.first_layout,
        files=files,
        updated_at=finalized_at,
    )
    trace = project_manual_selection_trace_v1(
        workspace_id=workspace_id,
        session_key=session_key,
        source_directory_name=snapshot.batch.name,
        direction=snapshot.batch.direction,
        first_layout=snapshot.batch.first_layout,
        operations=snapshot.operations,
        exported_at=finalized_at,
    )
    completed_batch = replace(
        snapshot.batch,
        status=RemoteManualSelectionBatchStatus.COMPLETED,
        server_revision=snapshot.batch.server_revision + 1,
    )
    operational = RemoteManualSelectionManifestV1(
        session_id=completed_batch.session_id,
        collection_id=completed_batch.collection_id,
        batch=completed_batch,
        files=files,
        operations=snapshot.operations,
        transfers=snapshot.transfers,
        host_actions=snapshot.host_actions,
        generated_at=finalized_at,
    )
    return RemoteSelectionFinalizationPayloads(
        output_manifest=output,
        trace_manifest=trace,
        operational_manifest=operational.payload(),
        final_manifest_checksum_sha256=operational.checksum_sha256,
    )


__all__ = [
    "RemoteSelectionFinalizationPayloads",
    "RemoteSelectionFinalizeBlocker",
    "RemoteSelectionFinalizePreview",
    "build_remote_selection_finalization_payloads",
    "build_remote_selection_finalize_preview",
]
