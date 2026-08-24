from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

from game_predictor_api.application.remote_manual_selection_finalization import (
    build_remote_selection_finalization_payloads,
    build_remote_selection_finalize_preview,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionCollectionV1,
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationStatus,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionFinalFileRecord,
    RemoteManualSelectionFinalizationSnapshot,
)

SESSION_ID = UUID("10000000-0000-4000-8000-000000000001")
COLLECTION_ID = UUID("20000000-0000-4000-8000-000000000002")
BATCH_ID = UUID("30000000-0000-4000-8000-000000000003")
CLIENT_ID = UUID("40000000-0000-4000-8000-000000000004")
FILE_IDS = (
    UUID("50000000-0000-4000-8000-000000000005"),
    UUID("50000000-0000-4000-8000-000000000006"),
)
NOW = datetime(2026, 8, 24, 16, tzinfo=UTC)


def _batch() -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="1-18",
        source_manifest_checksum_sha256="a" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=1,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=2,
        last_client_sequence=2,
    )


def _operation(
    operation_type: RemoteManualSelectionOperationType,
    *,
    sequence: int,
    recorded_at: datetime,
) -> RemoteManualSelectionOperationV1:
    selected = operation_type is RemoteManualSelectionOperationType.SELECT
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID(int=100 + sequence),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=sequence,
        expected_server_revision=sequence - 1,
        operation_type=operation_type,
        selection_generation=1 if selected else 0,
        range_start=1 if selected else 10,
        range_end=9 if selected else 18,
        recorded_at=recorded_at,
        file_id=FILE_IDS[0] if selected else None,
        image_path="source/1.jpg" if selected else None,
        source_index=0 if selected else 1,
        image_checksum_sha256="b" * 64 if selected else None,
        output_name="seq_1-9.jpg" if selected else None,
        visible_milliseconds=500,
    )
    return RemoteManualSelectionOperationV1(
        command=command,
        command_checksum_sha256=command.checksum_sha256,
        status=RemoteManualSelectionOperationStatus.APPLIED,
        applied_server_revision=sequence,
        outcome_code="REMOTE_SELECTION_OPERATION_APPLIED",
    )


def _snapshot(*, synced: bool = True) -> RemoteManualSelectionFinalizationSnapshot:
    selected = RemoteManualSelectionFileV1(
        id=FILE_IDS[0],
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="source/1.jpg",
        size_bytes=123,
        last_modified_ms=1_700_000_000_000,
        mime_type="image/jpeg",
        desired_selected=True,
        selection_generation=1,
        status=(
            RemoteManualSelectionFileStatus.SYNCED
            if synced
            else RemoteManualSelectionFileStatus.UPLOAD_QUEUED
        ),
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
        host_checksum_sha256="b" * 64 if synced else None,
    )
    unselected = RemoteManualSelectionFileV1(
        id=FILE_IDS[1],
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=1,
        relative_path="source/2.jpg",
        size_bytes=124,
        last_modified_ms=1_700_000_000_001,
        mime_type="image/jpeg",
        desired_selected=False,
        selection_generation=0,
        status=RemoteManualSelectionFileStatus.UNSELECTED,
    )
    operations = (
        _operation(
            RemoteManualSelectionOperationType.SELECT,
            sequence=1,
            recorded_at=NOW + timedelta(seconds=2),
        ),
        _operation(
            RemoteManualSelectionOperationType.SKIP,
            sequence=2,
            recorded_at=NOW + timedelta(seconds=1),
        ),
    )
    return RemoteManualSelectionFinalizationSnapshot(
        batch=_batch(),
        collection=RemoteManualSelectionCollectionV1(
            id=COLLECTION_ID,
            session_id=SESSION_ID,
            name="777",
            normalized_name="777",
            status=RemoteManualSelectionCollectionStatus.ACTIVE,
            revision=0,
        ),
        files=(
            RemoteManualSelectionFinalFileRecord(
                file=selected,
                final_relative_path="seq_1-9.jpg" if synced else None,
            ),
            RemoteManualSelectionFinalFileRecord(
                file=unselected,
                final_relative_path=None,
            ),
        ),
        operations=operations,
        transfers=(),
        host_actions=(),
        total_file_count=2,
        selected_file_count=1,
        transferred_file_count=1 if synced else 0,
        final_manifest_checksum_sha256=None,
        updated_at=NOW,
    )


def test_preview_blocks_an_unsynced_selected_file() -> None:
    preview = build_remote_selection_finalize_preview(_snapshot(synced=False))

    assert preview.ready is False
    assert [(item.code, item.count) for item in preview.blockers] == [
        ("REMOTE_SELECTION_SELECTED_FILE_NOT_SYNCED", 1)
    ]


def test_finalization_projects_unchanged_local_v1_manifests_deterministically() -> None:
    snapshot = _snapshot()

    first = build_remote_selection_finalization_payloads(
        snapshot,
        finalized_at=NOW,
    )
    second = build_remote_selection_finalization_payloads(
        snapshot,
        finalized_at=NOW,
    )

    assert first == second
    assert first.output_manifest["schemaVersion"] == 1
    assert first.trace_manifest["schemaVersion"] == 1
    assert first.operational_manifest["schemaVersion"] == (
        "remote-manual-image-selection-session-v1"
    )
    assert list(first.output_manifest) == [
        "schemaVersion",
        "direction",
        "firstLayout",
        "gameId",
        "items",
        "sessionKey",
        "sourceDirectoryName",
        "updatedAt",
    ]
    assert first.output_manifest["items"] == [
        {
            "outputName": "seq_1-9.jpg",
            "rangeStart": 1,
            "rangeEnd": 9,
            "imagePath": "source/1.jpg",
            "imageChecksum": "b" * 64,
        }
    ]
    trace = first.trace_manifest["events"]
    assert isinstance(trace, list)
    assert [item["kind"] for item in trace] == ["accepted", "skipped"]
    assert [item["eventIndex"] for item in trace] == [0, 1]
    assert list(trace[0]) == [
        "decoded",
        "decisionOrdinal",
        "eventIndex",
        "gameId",
        "imageChecksum",
        "imagePath",
        "kind",
        "outputName",
        "rangeEnd",
        "rangeStart",
        "recordedAt",
        "revertsDecisionOrdinal",
        "sessionKey",
        "sourceIndex",
        "visibleMilliseconds",
    ]


def test_completed_snapshot_is_ready_but_abandoned_snapshot_is_not() -> None:
    snapshot = _snapshot()
    completed = replace(
        snapshot,
        batch=replace(snapshot.batch, status=RemoteManualSelectionBatchStatus.COMPLETED),
    )
    abandoned = replace(
        snapshot,
        batch=replace(snapshot.batch, status=RemoteManualSelectionBatchStatus.ABANDONED),
    )

    assert build_remote_selection_finalize_preview(completed).ready is True
    assert build_remote_selection_finalize_preview(abandoned).blockers[0].code == (
        "REMOTE_SELECTION_BATCH_NOT_FINALIZABLE"
    )


def test_an_active_older_transfer_still_blocks_the_global_barrier() -> None:
    snapshot = _snapshot()
    active_old_transfer = RemoteManualSelectionTransferV1(
        id=UUID(int=800),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_IDS[0],
        generation=0,
        attempt=1,
        declared_bytes=123,
        received_bytes=12,
        status=RemoteManualSelectionTransferStatus.UPLOADING,
        declared_checksum_sha256="b" * 64,
    )

    preview = build_remote_selection_finalize_preview(
        replace(snapshot, transfers=(active_old_transfer,))
    )

    assert preview.ready is False
    assert preview.blockers[0].code == "REMOTE_SELECTION_TRANSFER_PENDING"
