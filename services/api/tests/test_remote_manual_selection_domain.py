from __future__ import annotations

import tracemalloc
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import UUID

import pytest
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionBatchStatus,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionCollectionStatus,
    RemoteManualSelectionConflictError,
    RemoteManualSelectionDirection,
    RemoteManualSelectionError,
    RemoteManualSelectionFileStatus,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionHostActionStatus,
    RemoteManualSelectionHostActionType,
    RemoteManualSelectionHostActionV1,
    RemoteManualSelectionManifestV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationStatus,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionSessionStatus,
    RemoteManualSelectionTransferStatus,
    RemoteManualSelectionTransferV1,
    RemoteSourceKind,
    RemoteSourceManifestEntryV1,
    apply_remote_manual_selection_operation,
    build_remote_source_manifest,
    canonical_remote_checksum_sha256,
    canonical_remote_json_bytes,
    parse_remote_operation_type,
    project_manual_selection_output_v1,
    project_manual_selection_trace_v1,
    transition_remote_batch_status,
    transition_remote_collection_status,
    transition_remote_file_status,
    transition_remote_host_action_status,
    transition_remote_operation_status,
    transition_remote_session_status,
    transition_remote_transfer_status,
)

SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
COLLECTION_ID = UUID("20000000-0000-0000-0000-000000000002")
BATCH_ID = UUID("30000000-0000-0000-0000-000000000003")
FILE_ID = UUID("40000000-0000-0000-0000-000000000004")
CLIENT_ID = UUID("50000000-0000-0000-0000-000000000005")
OPERATION_ID = UUID("60000000-0000-0000-0000-000000000006")
NOW = datetime(2026, 8, 23, 12, tzinfo=UTC)
CHECKSUM = "a" * 64


def _batch(
    *,
    status: RemoteManualSelectionBatchStatus = RemoteManualSelectionBatchStatus.ACTIVE,
    revision: int = 0,
    client_sequence: int = 0,
) -> RemoteManualSelectionBatchV1:
    return RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="1-19809",
        source_manifest_checksum_sha256="b" * 64,
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=status,
        server_revision=revision,
        last_client_sequence=client_sequence,
    )


def _file(
    *,
    file_id: UUID = FILE_ID,
    generation: int = 0,
    status: RemoteManualSelectionFileStatus = RemoteManualSelectionFileStatus.UNSELECTED,
    desired_selected: bool = False,
) -> RemoteManualSelectionFileV1:
    return RemoteManualSelectionFileV1(
        id=file_id,
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=0,
        relative_path="folder/image_1.jpg",
        size_bytes=1024,
        last_modified_ms=1_700_000_000_000,
        mime_type="image/jpeg",
        desired_selected=desired_selected,
        selection_generation=generation,
        status=status,
    )


def _command(
    *,
    operation_id: UUID = OPERATION_ID,
    operation_type: RemoteManualSelectionOperationType = (
        RemoteManualSelectionOperationType.SELECT
    ),
    client_sequence: int = 1,
    expected_revision: int = 0,
    generation: int = 1,
    file_id: UUID | None = FILE_ID,
) -> RemoteManualSelectionOperationCommandV1:
    is_select = operation_type is RemoteManualSelectionOperationType.SELECT
    is_file_operation = operation_type is not RemoteManualSelectionOperationType.SKIP
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
        file_id=file_id if is_file_operation else None,
        image_path="folder/image_1.jpg" if is_file_operation else None,
        source_index=0 if is_file_operation else None,
        image_checksum_sha256=CHECKSUM if is_select else None,
        output_name="seq_1-9.jpg" if is_select else None,
        target_operation_id=(
            OPERATION_ID
            if operation_type
            in {
                RemoteManualSelectionOperationType.DESELECT,
                RemoteManualSelectionOperationType.UNDO,
            }
            else None
        ),
    )


@pytest.mark.parametrize(
    ("transition", "current", "target"),
    [
        (
            transition_remote_session_status,
            RemoteManualSelectionSessionStatus.DRAFT,
            RemoteManualSelectionSessionStatus.ACTIVE,
        ),
        (
            transition_remote_collection_status,
            RemoteManualSelectionCollectionStatus.ACTIVE,
            RemoteManualSelectionCollectionStatus.COMPLETED,
        ),
        (
            transition_remote_batch_status,
            RemoteManualSelectionBatchStatus.ACTIVE,
            RemoteManualSelectionBatchStatus.FINALIZING,
        ),
        (
            transition_remote_file_status,
            RemoteManualSelectionFileStatus.VERIFIED,
            RemoteManualSelectionFileStatus.MATERIALIZED,
        ),
        (
            transition_remote_operation_status,
            RemoteManualSelectionOperationStatus.SENDING,
            RemoteManualSelectionOperationStatus.APPLIED,
        ),
        (
            transition_remote_transfer_status,
            RemoteManualSelectionTransferStatus.STORED_TEMP,
            RemoteManualSelectionTransferStatus.VERIFIED,
        ),
        (
            transition_remote_host_action_status,
            RemoteManualSelectionHostActionStatus.PROCESSING,
            RemoteManualSelectionHostActionStatus.COMPLETED,
        ),
    ],
)
def test_each_state_machine_accepts_a_legal_transition(transition, current, target) -> None:
    assert transition(current, target) is target
    assert transition(current, current) is current


@pytest.mark.parametrize(
    ("transition", "current", "target"),
    [
        (
            transition_remote_session_status,
            RemoteManualSelectionSessionStatus.COMPLETED,
            RemoteManualSelectionSessionStatus.ACTIVE,
        ),
        (
            transition_remote_collection_status,
            RemoteManualSelectionCollectionStatus.COMPLETED,
            RemoteManualSelectionCollectionStatus.ACTIVE,
        ),
        (
            transition_remote_batch_status,
            RemoteManualSelectionBatchStatus.COMPLETED,
            RemoteManualSelectionBatchStatus.ACTIVE,
        ),
        (
            transition_remote_file_status,
            RemoteManualSelectionFileStatus.UNSELECTED,
            RemoteManualSelectionFileStatus.SYNCED,
        ),
        (
            transition_remote_operation_status,
            RemoteManualSelectionOperationStatus.REJECTED,
            RemoteManualSelectionOperationStatus.SENDING,
        ),
        (
            transition_remote_transfer_status,
            RemoteManualSelectionTransferStatus.MATERIALIZED,
            RemoteManualSelectionTransferStatus.UPLOADING,
        ),
        (
            transition_remote_host_action_status,
            RemoteManualSelectionHostActionStatus.COMPLETED,
            RemoteManualSelectionHostActionStatus.PROCESSING,
        ),
    ],
)
def test_each_state_machine_rejects_an_illegal_transition(transition, current, target) -> None:
    with pytest.raises(RemoteManualSelectionConflictError) as error:
        transition(current, target)
    assert error.value.code == "REMOTE_SELECTION_INVALID_TRANSITION"


@pytest.mark.parametrize(
    ("statuses", "transition", "allowed"),
    [
        (
            RemoteManualSelectionSessionStatus,
            transition_remote_session_status,
            {
                "draft": {"active", "revoked"},
                "active": {"completed", "expired", "revoked"},
            },
        ),
        (
            RemoteManualSelectionCollectionStatus,
            transition_remote_collection_status,
            {"active": {"completed"}},
        ),
        (
            RemoteManualSelectionBatchStatus,
            transition_remote_batch_status,
            {
                "draft": {"indexing", "abandoned"},
                "indexing": {"active", "failed", "abandoned"},
                "active": {"finalizing", "failed", "abandoned"},
                "finalizing": {"completed", "failed"},
                "failed": {"indexing", "active", "finalizing", "abandoned"},
            },
        ),
        (
            RemoteManualSelectionFileStatus,
            transition_remote_file_status,
            {
                "discovered": {"unselected"},
                "unselected": {"selection_queued"},
                "selection_queued": {"upload_queued", "deselect_pending", "failed"},
                "upload_queued": {"uploading", "deselect_pending", "failed"},
                "uploading": {"stored_temporarily", "deselect_pending", "failed"},
                "stored_temporarily": {"verified", "deselect_pending", "failed"},
                "verified": {"materialized", "deselect_pending", "failed"},
                "materialized": {"synced", "deselect_pending", "failed"},
                "synced": {"deselect_pending"},
                "deselect_pending": {
                    "unselected",
                    "removed",
                    "selection_queued",
                    "failed",
                },
                "removed": {"selection_queued"},
                "failed": {"retrying", "deselect_pending"},
                "retrying": {"upload_queued", "unselected", "deselect_pending"},
            },
        ),
        (
            RemoteManualSelectionOperationStatus,
            transition_remote_operation_status,
            {
                "queued": {"sending"},
                "sending": {"applied", "retry", "superseded", "conflict", "rejected"},
                "retry": {"sending"},
                "applied": {"superseded"},
            },
        ),
        (
            RemoteManualSelectionTransferStatus,
            transition_remote_transfer_status,
            {
                "queued": {"uploading", "cancelled"},
                "uploading": {"stored_temp", "cancelled", "failed"},
                "stored_temp": {"verified", "failed"},
                "verified": {"materialized"},
                "failed": {"retrying"},
                "retrying": {"uploading", "cancelled"},
            },
        ),
        (
            RemoteManualSelectionHostActionStatus,
            transition_remote_host_action_status,
            {
                "queued": {"processing", "superseded"},
                "processing": {"completed", "retry", "failed", "superseded"},
                "retry": {"processing"},
            },
        ),
    ],
)
def test_state_machine_matrices_are_exhaustive(statuses, transition, allowed) -> None:
    for current in statuses:
        for target in statuses:
            if current is target or target.value in allowed.get(current.value, set()):
                assert transition(current, target) is target
                continue
            with pytest.raises(RemoteManualSelectionConflictError) as error:
                transition(current, target)
            assert error.value.code == "REMOTE_SELECTION_INVALID_TRANSITION"


def test_select_applies_one_revision_and_exact_retry_is_revision_neutral() -> None:
    command = _command()
    applied = apply_remote_manual_selection_operation(_batch(), _file(), command)

    assert applied.batch.server_revision == 1
    assert applied.batch.last_client_sequence == 1
    assert applied.file is not None
    assert applied.file.desired_selected is True
    assert applied.file.selection_generation == 1
    assert applied.file.status is RemoteManualSelectionFileStatus.SELECTION_QUEUED
    assert applied.operation.status is RemoteManualSelectionOperationStatus.APPLIED

    replay = apply_remote_manual_selection_operation(
        applied.batch,
        applied.file,
        command,
        existing_operation=applied.operation,
    )
    assert replay.exact_retry is True
    assert replay.batch is applied.batch
    assert replay.file is applied.file
    assert replay.operation is applied.operation
    assert replay.batch.server_revision == 1


def test_operation_id_cannot_be_reused_for_different_content() -> None:
    command = _command()
    applied = apply_remote_manual_selection_operation(_batch(), _file(), command)

    with pytest.raises(RemoteManualSelectionConflictError) as error:
        apply_remote_manual_selection_operation(
            applied.batch,
            applied.file,
            replace(command, visible_milliseconds=301),
            existing_operation=applied.operation,
        )
    assert error.value.code == "REMOTE_SELECTION_OPERATION_IDEMPOTENCY_CONFLICT"


def test_unknown_contract_version_and_tampered_command_checksum_are_rejected() -> None:
    with pytest.raises(RemoteManualSelectionError) as version_error:
        replace(_batch(), schema_version="remote-manual-selection-batch-v2")  # type: ignore[arg-type]
    assert version_error.value.code == "REMOTE_SELECTION_CONTRACT_INVALID"

    command = _command()
    with pytest.raises(RemoteManualSelectionError) as checksum_error:
        RemoteManualSelectionOperationV1(
            command=command,
            command_checksum_sha256="f" * 64,
            status=RemoteManualSelectionOperationStatus.APPLIED,
            applied_server_revision=1,
            outcome_code="applied",
        )
    assert checksum_error.value.code == "REMOTE_SELECTION_CONTRACT_INVALID"


def test_exact_retry_still_rejects_a_foreign_scope() -> None:
    command = _command()
    applied = apply_remote_manual_selection_operation(_batch(), _file(), command)

    with pytest.raises(RemoteManualSelectionError) as error:
        apply_remote_manual_selection_operation(
            applied.batch,
            applied.file,
            replace(command, session_id=UUID(int=99)),
            existing_operation=applied.operation,
        )
    assert error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"


def test_stale_generation_is_superseded_without_changing_desired_state_or_revision() -> None:
    canonical_file = replace(
        _file(generation=3),
        desired_selected=True,
        status=RemoteManualSelectionFileStatus.SELECTION_QUEUED,
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
    )
    batch = _batch(revision=7, client_sequence=10)
    stale = _command(client_sequence=11, expected_revision=7, generation=2)

    result = apply_remote_manual_selection_operation(batch, canonical_file, stale)

    assert result.operation.status is RemoteManualSelectionOperationStatus.SUPERSEDED
    assert result.operation.outcome_code == "stale_generation"
    assert result.batch.server_revision == 7
    assert result.batch.last_client_sequence == 11
    assert result.file is canonical_file


@pytest.mark.parametrize(
    ("command", "code"),
    [
        (_command(client_sequence=2), "REMOTE_SELECTION_CLIENT_SEQUENCE_GAP"),
        (
            _command(client_sequence=1, expected_revision=2),
            "REMOTE_SELECTION_REVISION_CONFLICT",
        ),
        (_command(generation=3), "REMOTE_SELECTION_GENERATION_GAP"),
    ],
)
def test_order_revision_and_generation_conflicts_are_fail_closed(command, code) -> None:
    with pytest.raises(RemoteManualSelectionConflictError) as error:
        apply_remote_manual_selection_operation(_batch(), _file(), command)
    assert error.value.code == code


def test_scope_and_unknown_operation_types_are_rejected() -> None:
    with pytest.raises(RemoteManualSelectionError) as scope_error:
        apply_remote_manual_selection_operation(
            _batch(),
            _file(),
            replace(_command(), session_id=UUID(int=99)),
        )
    assert scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"

    with pytest.raises(RemoteManualSelectionError) as file_error:
        apply_remote_manual_selection_operation(
            _batch(),
            _file(file_id=UUID(int=98)),
            _command(),
        )
    assert file_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"

    with pytest.raises(RemoteManualSelectionError) as type_error:
        parse_remote_operation_type("replace_all")
    assert type_error.value.code == "REMOTE_SELECTION_OPERATION_TYPE_INVALID"


def test_select_rejects_a_source_path_index_or_output_name_from_another_file() -> None:
    for command in (
        replace(_command(), image_path="folder/other.jpg"),
        replace(_command(), source_index=1),
        replace(_command(), output_name="seq_10-18.jpg"),
    ):
        with pytest.raises(RemoteManualSelectionError) as error:
            apply_remote_manual_selection_operation(_batch(), _file(), command)
        assert error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"


def test_source_manifest_is_natural_ordered_canonical_and_path_safe() -> None:
    entries = tuple(
        RemoteSourceManifestEntryV1(
            ordinal=index,
            relative_path=path,
            name=path,
            size_bytes=index + 1,
            last_modified_ms=100 + index,
            mime_type="image/jpeg",
        )
        for index, path in enumerate(("10.jpg", "2.jpg", "1.jpg"))
    )
    manifest = build_remote_source_manifest(
        entries,
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
    )
    replay = build_remote_source_manifest(
        entries[::-1],
        source_kind=RemoteSourceKind.DIRECTORY_HANDLE,
    )

    assert [item.relative_path for item in manifest.entries] == ["1.jpg", "2.jpg", "10.jpg"]
    assert manifest.manifest_checksum_sha256 == replay.manifest_checksum_sha256
    assert len(manifest.manifest_checksum_sha256) == 64

    with pytest.raises(RemoteManualSelectionError) as unsafe:
        RemoteSourceManifestEntryV1(
            ordinal=0,
            relative_path="../secret.jpg",
            name="secret.jpg",
            size_bytes=1,
            last_modified_ms=1,
            mime_type="image/jpeg",
        )
    assert unsafe.value.code == "REMOTE_SELECTION_SOURCE_MANIFEST_INVALID"


def test_canonical_json_and_remote_manifest_checksum_are_order_independent() -> None:
    assert canonical_remote_json_bytes({"z": 1, "a": {"b": 2, "a": 1}}) == (
        b'{"a":{"a":1,"b":2},"z":1}'
    )
    assert canonical_remote_checksum_sha256({"a": 1, "b": 2}) == (
        canonical_remote_checksum_sha256({"b": 2, "a": 1})
    )
    assert canonical_remote_checksum_sha256({"a": 1, "b": 2}) == (
        "43258cff783fe7036d8a43033f830adfc60ec037382473548ac742b888292777"
    )

    batch = _batch()
    file = _file()
    transfer = RemoteManualSelectionTransferV1(
        id=UUID(int=7),
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
        id=UUID(int=8),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        file_id=FILE_ID,
        transfer_id=transfer.id,
        generation=1,
        action_type=RemoteManualSelectionHostActionType.MATERIALIZE,
        status=RemoteManualSelectionHostActionStatus.QUEUED,
        attempt=0,
    )
    manifest = RemoteManualSelectionManifestV1(
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        batch=batch,
        files=(file,),
        operations=(),
        transfers=(transfer,),
        host_actions=(action,),
        generated_at=NOW,
    )

    assert manifest.payload()["schemaVersion"] == "remote-manual-image-selection-session-v1"
    assert len(manifest.checksum_sha256) == 64

    with pytest.raises(RemoteManualSelectionError) as scope_error:
        RemoteManualSelectionManifestV1(
            session_id=SESSION_ID,
            collection_id=COLLECTION_ID,
            batch=batch,
            files=(replace(file, batch_id=UUID(int=99)),),
            operations=(),
            transfers=(),
            host_actions=(),
            generated_at=NOW,
        )
    assert scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"

    foreign_transfer = replace(transfer, file_id=UUID(int=98))
    with pytest.raises(RemoteManualSelectionError) as transfer_scope_error:
        RemoteManualSelectionManifestV1(
            session_id=SESSION_ID,
            collection_id=COLLECTION_ID,
            batch=batch,
            files=(file,),
            operations=(),
            transfers=(foreign_transfer,),
            host_actions=(),
            generated_at=NOW,
        )
    assert transfer_scope_error.value.code == "REMOTE_SELECTION_SCOPE_MISMATCH"


def test_output_v1_projection_preserves_the_existing_snapshot() -> None:
    synced = replace(
        _file(),
        desired_selected=True,
        selection_generation=1,
        status=RemoteManualSelectionFileStatus.SYNCED,
        range_start=1,
        range_end=9,
        output_name="seq_1-9.jpg",
        host_checksum_sha256=CHECKSUM,
    )

    assert project_manual_selection_output_v1(
        workspace_id="remote-workspace-1",
        session_key="remote-session:batch-1",
        source_directory_name="1-19809",
        direction=RemoteManualSelectionDirection.ASCENDING,
        first_layout=1,
        files=(synced,),
        updated_at=NOW,
    ) == {
        "direction": "ascending",
        "firstLayout": 1,
        "gameId": "remote-workspace-1",
        "items": [
            {
                "imageChecksum": CHECKSUM,
                "imagePath": "folder/image_1.jpg",
                "outputName": "seq_1-9.jpg",
                "rangeEnd": 9,
                "rangeStart": 1,
            }
        ],
        "schemaVersion": 1,
        "sessionKey": "remote-session:batch-1",
        "sourceDirectoryName": "1-19809",
        "updatedAt": "2026-08-23T12:00:00.000Z",
    }

    with pytest.raises(RemoteManualSelectionError) as incomplete:
        project_manual_selection_output_v1(
            workspace_id="remote-workspace-1",
            session_key="remote-session:batch-1",
            source_directory_name="1-19809",
            direction=RemoteManualSelectionDirection.ASCENDING,
            first_layout=1,
            files=(replace(synced, status=RemoteManualSelectionFileStatus.MATERIALIZED),),
            updated_at=NOW,
        )
    assert incomplete.value.code == "REMOTE_SELECTION_PROJECTION_INCOMPLETE"


def test_trace_v1_projection_preserves_order_and_existing_fields() -> None:
    select_command = _command()
    skip_command = _command(
        operation_id=UUID(int=12),
        operation_type=RemoteManualSelectionOperationType.SKIP,
        client_sequence=2,
        expected_revision=1,
        generation=0,
        file_id=None,
    )
    operations = tuple(
        RemoteManualSelectionOperationV1(
            command=command,
            command_checksum_sha256=command.checksum_sha256,
            status=RemoteManualSelectionOperationStatus.APPLIED,
            applied_server_revision=index + 1,
            outcome_code="applied",
        )
        for index, command in enumerate((select_command, skip_command))
    )

    trace = project_manual_selection_trace_v1(
        workspace_id="remote-workspace-1",
        session_key="remote-session:batch-1",
        source_directory_name="1-19809",
        direction=RemoteManualSelectionDirection.ASCENDING,
        first_layout=1,
        operations=operations[::-1],
        exported_at=NOW + timedelta(minutes=1),
    )

    assert trace["schemaVersion"] == 1
    assert trace["exportedAt"] == "2026-08-23T12:01:00.000Z"
    assert [event["kind"] for event in trace["events"]] == ["accepted", "skipped"]
    assert [event["eventIndex"] for event in trace["events"]] == [0, 1]
    assert trace["events"][0]["outputName"] == "seq_1-9.jpg"


def test_trace_undo_references_its_explicit_decision() -> None:
    first = _command()
    second = replace(
        _command(operation_id=UUID(int=13)),
        client_sequence=2,
        expected_server_revision=1,
        range_start=10,
        range_end=18,
        output_name="seq_10-18.jpg",
    )
    undo = replace(
        _command(
            operation_id=UUID(int=14),
            operation_type=RemoteManualSelectionOperationType.UNDO,
            client_sequence=3,
            expected_revision=2,
            generation=2,
        ),
        target_operation_id=first.operation_id,
    )
    commands = (first, second, undo)
    operations = tuple(
        RemoteManualSelectionOperationV1(
            command=command,
            command_checksum_sha256=command.checksum_sha256,
            status=RemoteManualSelectionOperationStatus.APPLIED,
            applied_server_revision=index + 1,
            outcome_code="applied",
        )
        for index, command in enumerate(commands)
    )

    trace = project_manual_selection_trace_v1(
        workspace_id="remote-workspace-1",
        session_key="remote-session:batch-1",
        source_directory_name="1-19809",
        direction=RemoteManualSelectionDirection.ASCENDING,
        first_layout=1,
        operations=operations,
        exported_at=NOW,
    )

    assert trace["events"][2]["revertsDecisionOrdinal"] == 0


def test_output_projection_handles_fifteen_thousand_records_deterministically(
    record_property,
) -> None:
    files = tuple(
        RemoteManualSelectionFileV1(
            id=UUID(int=index + 1),
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            source_index=index,
            relative_path=f"source/{index + 1}.jpg",
            size_bytes=1024,
            last_modified_ms=index,
            mime_type="image/jpeg",
            desired_selected=True,
            selection_generation=1,
            status=RemoteManualSelectionFileStatus.SYNCED,
            range_start=index * 9 + 1,
            range_end=index * 9 + 9,
            output_name=f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg",
            host_checksum_sha256=f"{index:064x}",
        )
        for index in range(15_000)
    )

    tracemalloc.start()
    started_at = perf_counter()
    try:
        projection = project_manual_selection_output_v1(
            workspace_id="remote-workspace-1",
            session_key="remote-session:batch-scale",
            source_directory_name="scale",
            direction=RemoteManualSelectionDirection.ASCENDING,
            first_layout=1,
            files=files,
            updated_at=NOW,
        )
        elapsed_seconds = perf_counter() - started_at
        _current_bytes, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    record_property("projection_seconds", elapsed_seconds)
    record_property("projection_peak_bytes", peak_bytes)

    assert len(projection["items"]) == 15_000
    assert projection["items"][0]["rangeStart"] == 1
    assert projection["items"][-1]["rangeEnd"] == 135_000
