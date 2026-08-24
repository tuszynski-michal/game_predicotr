"""Run the deterministic first checkpoint of remote manual-selection rollout."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import tracemalloc
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from time import perf_counter, process_time
from uuid import UUID

from game_predictor_api.application.remote_manual_selection_finalization import (
    build_remote_selection_finalization_payloads,
)
from game_predictor_api.application.remote_manual_selection_rollout import (
    RemoteSelectionRolloutReportError,
    build_rollout_report,
    canonical_report_bytes,
    rollout_stage,
    validate_rollout_report,
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
    apply_remote_manual_selection_operation,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionFinalFileRecord,
    RemoteManualSelectionFinalizationSnapshot,
)
from PIL import Image
from remote_manual_selection_rollout_stage_two import build_stage_two_local_report

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPOSITORY_ROOT / "artifacts" / "remote-manual-selection-rollout" / "stage-1.json"
DEFAULT_STAGE_ONE_REPORT = DEFAULT_OUTPUT
SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
COLLECTION_ID = UUID("22222222-2222-4222-8222-222222222222")
BATCH_ID = UUID("33333333-3333-4333-8333-333333333333")
CLIENT_ID = UUID("44444444-4444-4444-8444-444444444444")
NOW = datetime(2026, 8, 24, 20, tzinfo=UTC)


def _jpeg(index: int) -> bytes:
    output = BytesIO()
    Image.new("RGB", (16, 12), (index * 17 % 255, index * 31 % 255, index * 47 % 255)).save(
        output,
        format="JPEG",
    )
    return output.getvalue()


def _operation(
    *,
    sequence: int,
    kind: RemoteManualSelectionOperationType,
    file_id: UUID | None,
    source_index: int,
    checksum: str | None,
    selection_generation: int | None = None,
    target_operation_id: UUID | None = None,
) -> RemoteManualSelectionOperationV1:
    selected = kind is RemoteManualSelectionOperationType.SELECT
    start = source_index * 9 + 1
    command = RemoteManualSelectionOperationCommandV1(
        operation_id=UUID(int=100 + sequence),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        client_instance_id=CLIENT_ID,
        client_sequence=sequence,
        expected_server_revision=sequence - 1,
        operation_type=kind,
        selection_generation=(1 if selected else 0)
        if selection_generation is None
        else selection_generation,
        range_start=start,
        range_end=start + 8,
        recorded_at=NOW + timedelta(seconds=sequence),
        file_id=file_id,
        image_path=f"source/{source_index + 1}.jpg" if file_id is not None else None,
        source_index=source_index,
        image_checksum_sha256=checksum if selected else None,
        output_name=f"seq_{start}-{start + 8}.jpg" if selected else None,
        visible_milliseconds=500,
        target_operation_id=target_operation_id,
    )
    return RemoteManualSelectionOperationV1(
        command=command,
        command_checksum_sha256=command.checksum_sha256,
        status=RemoteManualSelectionOperationStatus.APPLIED,
        applied_server_revision=sequence,
        outcome_code="REMOTE_SELECTION_OPERATION_APPLIED",
    )


def build_stage_one_report() -> dict[str, object]:
    """Exercise deterministic file/manifest parity without opening a public route."""

    tracemalloc.start()
    wall_started = perf_counter()
    cpu_started = process_time()
    source_payloads = tuple(_jpeg(index) for index in range(10))
    checksums = tuple(hashlib.sha256(item).hexdigest() for item in source_payloads)
    file_ids = tuple(UUID(int=1_000 + index) for index in range(10))
    selected_indexes = frozenset({0, 1, 3, 4, 5, 6})
    operations = (
        _operation(
            sequence=1,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[0],
            source_index=0,
            checksum=checksums[0],
        ),
        _operation(
            sequence=2,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[1],
            source_index=1,
            checksum=checksums[1],
        ),
        _operation(
            sequence=3,
            kind=RemoteManualSelectionOperationType.DESELECT,
            file_id=file_ids[1],
            source_index=1,
            checksum=None,
            selection_generation=2,
            target_operation_id=UUID(int=102),
        ),
        _operation(
            sequence=4,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[1],
            source_index=1,
            checksum=checksums[1],
        ),
        _operation(
            sequence=5,
            kind=RemoteManualSelectionOperationType.SKIP,
            file_id=None,
            source_index=2,
            checksum=None,
        ),
        _operation(
            sequence=6,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[3],
            source_index=3,
            checksum=checksums[3],
        ),
        _operation(
            sequence=7,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[4],
            source_index=4,
            checksum=checksums[4],
        ),
        _operation(
            sequence=8,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[5],
            source_index=5,
            checksum=checksums[5],
        ),
        _operation(
            sequence=9,
            kind=RemoteManualSelectionOperationType.SELECT,
            file_id=file_ids[6],
            source_index=6,
            checksum=checksums[6],
        ),
        _operation(
            sequence=10,
            kind=RemoteManualSelectionOperationType.SKIP,
            file_id=None,
            source_index=7,
            checksum=None,
        ),
    )
    files = tuple(
        RemoteManualSelectionFileV1(
            id=file_id,
            session_id=SESSION_ID,
            batch_id=BATCH_ID,
            source_index=index,
            relative_path=f"source/{index + 1}.jpg",
            size_bytes=len(source_payloads[index]),
            last_modified_ms=1_700_000_000_000 + index,
            mime_type="image/jpeg",
            desired_selected=index in selected_indexes,
            selection_generation=1 if index in selected_indexes else 0,
            status=(
                RemoteManualSelectionFileStatus.SYNCED
                if index in selected_indexes
                else RemoteManualSelectionFileStatus.UNSELECTED
            ),
            range_start=index * 9 + 1 if index in selected_indexes else None,
            range_end=index * 9 + 9 if index in selected_indexes else None,
            output_name=f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg"
            if index in selected_indexes
            else None,
            host_checksum_sha256=checksums[index] if index in selected_indexes else None,
        )
        for index, file_id in enumerate(file_ids)
    )
    snapshot = RemoteManualSelectionFinalizationSnapshot(
        batch=RemoteManualSelectionBatchV1(
            id=BATCH_ID,
            session_id=SESSION_ID,
            collection_id=COLLECTION_ID,
            name="stage-1-fixture",
            source_manifest_checksum_sha256=hashlib.sha256(
                "".join(checksums).encode("ascii")
            ).hexdigest(),
            first_layout=1,
            direction=RemoteManualSelectionDirection.ASCENDING,
            cursor_index=8,
            status=RemoteManualSelectionBatchStatus.ACTIVE,
            server_revision=10,
            last_client_sequence=10,
        ),
        collection=RemoteManualSelectionCollectionV1(
            id=COLLECTION_ID,
            session_id=SESSION_ID,
            name="stage-1",
            normalized_name="stage-1",
            status=RemoteManualSelectionCollectionStatus.ACTIVE,
            revision=0,
        ),
        files=tuple(
            RemoteManualSelectionFinalFileRecord(
                file=item,
                final_relative_path=item.output_name if item.desired_selected else None,
            )
            for item in files
        ),
        operations=operations,
        transfers=(),
        host_actions=(),
        total_file_count=len(files),
        selected_file_count=len(selected_indexes),
        transferred_file_count=len(selected_indexes),
        final_manifest_checksum_sha256=None,
        updated_at=NOW,
    )
    started = perf_counter()
    first = build_remote_selection_finalization_payloads(snapshot, finalized_at=NOW)
    api_ms = (perf_counter() - started) * 1_000
    started = perf_counter()
    second = build_remote_selection_finalization_payloads(snapshot, finalized_at=NOW)
    restart_ms = (perf_counter() - started) * 1_000
    if first != second:
        raise RemoteSelectionRolloutReportError(
            "Stage-one finalization recovery is not deterministic."
        )
    output_items = first.output_manifest["items"]
    trace_events = first.trace_manifest["events"]
    if not isinstance(output_items, list) or not isinstance(trace_events, list):
        raise RemoteSelectionRolloutReportError("Stage-one manifests have an unexpected shape.")
    with tempfile.TemporaryDirectory(prefix="remote-selection-stage-1-") as temporary:
        output_directory = Path(temporary)
        for index in selected_indexes:
            target = output_directory / f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg"
            target.write_bytes(source_payloads[index])
        duplicate_replay = False
        try:
            (output_directory / "seq_1-9.jpg").open("xb").close()
        except FileExistsError:
            duplicate_replay = True
        host_files = tuple(output_directory.glob("seq_*.jpg"))
        parity = all(
            hashlib.sha256(path.read_bytes()).hexdigest()
            == checksums[(int(path.name.split("_")[1].split("-")[0]) - 1) // 9]
            for path in host_files
        )
    manifest_checksum = snapshot.batch.source_manifest_checksum_sha256
    command_faults_ok = _verify_stage_one_command_faults(source_payloads[1], checksums[1])
    _, peak_memory_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    duration_milliseconds = (perf_counter() - wall_started) * 1_000
    cpu_milliseconds = (process_time() - cpu_started) * 1_000
    transfer_throughputs = tuple(
        len(source_payloads[index]) * 1_000 / max(api_ms, 0.001) for index in selected_indexes
    )
    return build_rollout_report(
        stage_id="stage-1",
        environment={
            "executionMode": "deterministic_local_fixture",
            "transport": "no_public_route",
        },
        source_manifest_checksum_sha256=manifest_checksum,
        source_file_count=len(source_payloads),
        source_size_bytes=tuple(len(item) for item in source_payloads),
        operation_count=len(operations),
        selected_file_count=len(selected_indexes),
        host_output_file_count=len(host_files) if parity else 0,
        output_manifest_item_count=len(output_items),
        trace_event_count=len(trace_events),
        ui_latency_samples_ms=(api_ms, restart_ms),
        api_latency_samples_ms=(api_ms, restart_ms),
        transfer_latency_samples_ms=(api_ms, restart_ms),
        host_queue_latency_samples_ms=(api_ms, restart_ms),
        retry_count=1,
        conflict_count=0,
        duration_milliseconds=duration_milliseconds,
        throughput_bytes_per_second_samples=transfer_throughputs,
        process_cpu_milliseconds=cpu_milliseconds,
        peak_process_memory_bytes=max(peak_memory_bytes, 1),
        environment_gate_passed=True,
        fault_outcomes={
            "duplicate_replay": duplicate_replay and command_faults_ok["duplicate_replay"],
            "restart_recovery": first == second,
            "stale_generation": command_faults_ok["stale_generation"],
        },
    )


def _verify_stage_one_command_faults(
    payload: bytes,
    checksum: str,
) -> dict[str, bool]:
    """Exercise select, deselect, undo, exact retry and stale generation in the core."""

    initial_batch = RemoteManualSelectionBatchV1(
        id=BATCH_ID,
        session_id=SESSION_ID,
        collection_id=COLLECTION_ID,
        name="stage-1-command-fixture",
        source_manifest_checksum_sha256=hashlib.sha256(payload).hexdigest(),
        first_layout=1,
        direction=RemoteManualSelectionDirection.ASCENDING,
        cursor_index=0,
        status=RemoteManualSelectionBatchStatus.ACTIVE,
        server_revision=0,
        last_client_sequence=0,
    )
    initial_file = RemoteManualSelectionFileV1(
        id=UUID(int=1_001),
        session_id=SESSION_ID,
        batch_id=BATCH_ID,
        source_index=1,
        relative_path="source/2.jpg",
        size_bytes=len(payload),
        last_modified_ms=1_700_000_000_001,
        mime_type="image/jpeg",
        desired_selected=False,
        selection_generation=0,
        status=RemoteManualSelectionFileStatus.UNSELECTED,
    )
    select = _operation(
        sequence=1,
        kind=RemoteManualSelectionOperationType.SELECT,
        file_id=initial_file.id,
        source_index=1,
        checksum=checksum,
    ).command
    selected = apply_remote_manual_selection_operation(initial_batch, initial_file, select)
    assert selected.file is not None
    deselect = _operation(
        sequence=2,
        kind=RemoteManualSelectionOperationType.DESELECT,
        file_id=initial_file.id,
        source_index=1,
        checksum=None,
        selection_generation=2,
        target_operation_id=select.operation_id,
    ).command
    deselected = apply_remote_manual_selection_operation(
        selected.batch,
        selected.file,
        deselect,
        target_operation=selected.operation,
    )
    assert deselected.file is not None
    undo = _operation(
        sequence=3,
        kind=RemoteManualSelectionOperationType.UNDO,
        file_id=initial_file.id,
        source_index=1,
        checksum=None,
        selection_generation=3,
        target_operation_id=select.operation_id,
    ).command
    undone = apply_remote_manual_selection_operation(
        deselected.batch,
        deselected.file,
        undo,
        target_operation=selected.operation,
    )
    assert undone.file is not None
    reselect = _operation(
        sequence=4,
        kind=RemoteManualSelectionOperationType.SELECT,
        file_id=initial_file.id,
        source_index=1,
        checksum=checksum,
        selection_generation=4,
    ).command
    final = apply_remote_manual_selection_operation(undone.batch, undone.file, reselect)
    assert final.file is not None
    replay = apply_remote_manual_selection_operation(
        final.batch,
        final.file,
        reselect,
        existing_operation=final.operation,
    )
    stale = _operation(
        sequence=5,
        kind=RemoteManualSelectionOperationType.SELECT,
        file_id=initial_file.id,
        source_index=1,
        checksum=checksum,
        selection_generation=4,
    ).command
    stale_result = apply_remote_manual_selection_operation(final.batch, final.file, stale)
    return {
        "duplicate_replay": replay.exact_retry and replay.batch.server_revision == 4,
        "stale_generation": (
            stale_result.operation.status is RemoteManualSelectionOperationStatus.SUPERSEDED
            and stale_result.operation.outcome_code == "stale_generation"
            and stale_result.batch.server_revision == 4
            and stale_result.file == final.file
        ),
    }


def build_observation_report(
    observation: object,
    *,
    allow_large: bool,
    owner_approval: str | None,
) -> dict[str, object]:
    if not isinstance(observation, dict):
        raise RemoteSelectionRolloutReportError("The rollout observation must be an object.")
    stage_id = _string(observation.get("stageId"), "stageId")
    stage = rollout_stage(stage_id)
    approval = observation.get("explicitOwnerApproval")
    if stage.requires_owner_approval:
        if not allow_large:
            raise RemoteSelectionRolloutReportError(
                "Stages 4 and 5 require --allow-large after owner approval."
            )
        if not isinstance(approval, str) or approval != owner_approval:
            raise RemoteSelectionRolloutReportError(
                "The supplied --owner-approval does not match the observation."
            )
    return build_rollout_report(
        stage_id=stage_id,
        environment=_mapping(observation.get("environment"), "environment"),
        source_manifest_checksum_sha256=_string(
            observation.get("sourceManifestChecksumSha256"),
            "sourceManifestChecksumSha256",
        ),
        source_file_count=_integer(observation.get("sourceFileCount"), "sourceFileCount"),
        source_size_bytes=_integer_list(observation.get("sourceSizeBytes"), "sourceSizeBytes"),
        operation_count=_integer(observation.get("operationCount"), "operationCount"),
        selected_file_count=_integer(
            observation.get("selectedFileCount"),
            "selectedFileCount",
        ),
        host_output_file_count=_integer(
            observation.get("hostOutputFileCount"),
            "hostOutputFileCount",
        ),
        output_manifest_item_count=_integer(
            observation.get("outputManifestItemCount"),
            "outputManifestItemCount",
        ),
        trace_event_count=_integer(observation.get("traceEventCount"), "traceEventCount"),
        ui_latency_samples_ms=_number_list(
            observation.get("uiLatencySamplesMs"),
            "uiLatencySamplesMs",
        ),
        api_latency_samples_ms=_number_list(
            observation.get("apiLatencySamplesMs"),
            "apiLatencySamplesMs",
        ),
        transfer_latency_samples_ms=_number_list(
            observation.get("transferLatencySamplesMs"),
            "transferLatencySamplesMs",
        ),
        host_queue_latency_samples_ms=_number_list(
            observation.get("hostQueueLatencySamplesMs"),
            "hostQueueLatencySamplesMs",
        ),
        retry_count=_integer(observation.get("retryCount"), "retryCount"),
        conflict_count=_integer(observation.get("conflictCount"), "conflictCount"),
        fault_outcomes=_bool_mapping(observation.get("faultOutcomes"), "faultOutcomes"),
        duration_milliseconds=_number(
            observation.get("durationMilliseconds"), "durationMilliseconds"
        ),
        throughput_bytes_per_second_samples=_number_list(
            observation.get("throughputBytesPerSecondSamples"),
            "throughputBytesPerSecondSamples",
        ),
        process_cpu_milliseconds=_number(
            observation.get("processCpuMilliseconds"),
            "processCpuMilliseconds",
        ),
        peak_process_memory_bytes=_integer(
            observation.get("peakProcessMemoryBytes"),
            "peakProcessMemoryBytes",
        ),
        environment_gate_passed=_boolean(
            observation.get("environmentGatePassed"),
            "environmentGatePassed",
        ),
        queue_error_count=_integer(observation.get("queueErrorCount", 0), "queueErrorCount"),
        manifest_checksum_mismatch_count=_integer(
            observation.get("manifestChecksumMismatchCount", 0),
            "manifestChecksumMismatchCount",
        ),
        jpeg_checksum_mismatch_count=_integer(
            observation.get("jpegChecksumMismatchCount", 0),
            "jpegChecksumMismatchCount",
        ),
        json_parity_mismatch_count=_integer(
            observation.get("jsonParityMismatchCount", 0),
            "jsonParityMismatchCount",
        ),
        missing_final_file_count=_integer(
            observation.get("missingFinalFileCount", 0),
            "missingFinalFileCount",
        ),
        duplicate_final_file_count=_integer(
            observation.get("duplicateFinalFileCount", 0),
            "duplicateFinalFileCount",
        ),
        foreign_file_overwrite_count=_integer(
            observation.get("foreignFileOverwriteCount", 0),
            "foreignFileOverwriteCount",
        ),
        lost_decision_count=_integer(
            observation.get("lostDecisionCount", 0),
            "lostDecisionCount",
        ),
        verified_resend_count=_integer(
            observation.get("verifiedResendCount", 0),
            "verifiedResendCount",
        ),
        prior_stage_checksums=_string_mapping(
            observation.get("priorStageChecksums", {}),
            "priorStageChecksums",
        ),
        explicit_owner_approval=approval if isinstance(approval, str) else None,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--stage", choices=("stage-1", "stage-2-local"), default="stage-1")
    parser.add_argument("--stage-one-report", type=Path, default=DEFAULT_STAGE_ONE_REPORT)
    parser.add_argument("--observation", type=Path)
    parser.add_argument("--allow-large", action="store_true")
    parser.add_argument("--owner-approval")
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    try:
        if arguments.check:
            payload = json.loads(output.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise RemoteSelectionRolloutReportError("Rollout report must be an object.")
            validate_rollout_report(payload)
            if output.read_bytes() != canonical_report_bytes(payload):
                raise RemoteSelectionRolloutReportError("Rollout report is not canonical JSON.")
        else:
            if arguments.observation is not None:
                payload = build_observation_report(
                    json.loads(arguments.observation.read_text(encoding="utf-8")),
                    allow_large=arguments.allow_large,
                    owner_approval=arguments.owner_approval,
                )
            elif arguments.stage == "stage-2-local":
                stage_one = json.loads(arguments.stage_one_report.read_text(encoding="utf-8"))
                if not isinstance(stage_one, dict):
                    raise RemoteSelectionRolloutReportError(
                        "The stage-one report must be an object."
                    )
                validate_rollout_report(stage_one)
                if stage_one.get("decision") != {"status": "passed"}:
                    raise RemoteSelectionRolloutReportError(
                        "Stage one must pass before the stage-two local sub-gate."
                    )
                payload = build_stage_two_local_report(
                    prior_stage_checksum_sha256=_string(
                        stage_one.get("contentChecksumSha256"),
                        "stageOne.contentChecksumSha256",
                    )
                )
            else:
                payload = build_stage_one_report()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(canonical_report_bytes(payload))
        print(f"Remote-selection rollout report: {output}")
        print(f"SHA-256: {hashlib.sha256(output.read_bytes()).hexdigest()}")
        return 0
    except (OSError, RuntimeError, ValueError, RemoteSelectionRolloutReportError) as error:
        print(f"Remote-selection rollout benchmark failed: {error}")
        return 1


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise RemoteSelectionRolloutReportError(f"{field} must be an object.")
    return value


def _string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise RemoteSelectionRolloutReportError(f"{field} must be a non-empty string.")
    return value


def _integer(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise RemoteSelectionRolloutReportError(f"{field} must be a non-negative integer.")
    return value


def _integer_list(value: object, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise RemoteSelectionRolloutReportError(f"{field} must be a list.")
    return tuple(_integer(item, f"{field}[]") for item in value)


def _number_list(value: object, field: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise RemoteSelectionRolloutReportError(f"{field} must be a list.")
    result: list[float] = []
    for item in value:
        if not isinstance(item, int | float) or isinstance(item, bool):
            raise RemoteSelectionRolloutReportError(f"{field}[] must be a number.")
        result.append(float(item))
    return tuple(result)


def _number(value: object, field: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise RemoteSelectionRolloutReportError(f"{field} must be a number.")
    return float(value)


def _bool_mapping(value: object, field: str) -> dict[str, bool]:
    mapping = _mapping(value, field)
    result: dict[str, bool] = {}
    for key, item in mapping.items():
        if not isinstance(item, bool):
            raise RemoteSelectionRolloutReportError(f"{field}.{key} must be boolean.")
        result[key] = item
    return result


def _boolean(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise RemoteSelectionRolloutReportError(f"{field} must be boolean.")
    return value


def _string_mapping(value: object, field: str) -> dict[str, str]:
    mapping = _mapping(value, field)
    return {str(key): _string(item, f"{field}.{key}") for key, item in mapping.items()}


if __name__ == "__main__":
    raise SystemExit(main())
