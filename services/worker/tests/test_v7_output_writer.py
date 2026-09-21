from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from threading import Thread
from uuid import UUID

import pytest
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    LocalSourceManifest,
    build_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_output_writer import (
    V7FirstOutputRequest,
    V7ManualOutputRequest,
    V7OutputDecisionKind,
    V7OutputOperationState,
    V7OutputWriter,
    V7OutputWriterError,
    _is_supported_local_ntfs,
)

SELECTION_ID = UUID("00000000-0000-0000-0000-000000000702")
OPERATION_ID = UUID("00000000-0000-0000-0000-000000000703")
MANUAL_OPERATION_ID = UUID("00000000-0000-0000-0000-000000000704")
REPLACEMENT_OPERATION_ID = UUID("00000000-0000-0000-0000-000000000705")
SECOND_REPLACEMENT_OPERATION_ID = UUID("00000000-0000-0000-0000-000000000706")


def _manifest(source: Path) -> LocalSourceManifest:
    return build_local_source_manifest(
        source,
        selection_id=SELECTION_ID,
        display_name="V7 output fixture",
    )


def _fixture(tmp_path: Path) -> tuple[Path, LocalSourceManifest, V7FirstOutputRequest]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "frame.jpg").write_bytes(b"original-v7-jpeg-bytes")
    manifest = _manifest(source)
    entry = manifest.sources[0]
    request = V7FirstOutputRequest(
        operation_id=OPERATION_ID,
        sequence_range=SemiAutomaticSelectionRange(1, 9),
        source_index=entry.source_index,
        source_relative_path=entry.relative_path,
        source_size_bytes=entry.size_bytes,
        source_checksum_sha256=entry.checksum_sha256,
    )
    return source, manifest, request


def _writer(
    source: Path,
    manifest: LocalSourceManifest,
    **kwargs: object,
) -> V7OutputWriter:
    return V7OutputWriter(manifest, refresh_manifest=lambda: _manifest(source), **kwargs)


def _request_for_source(
    manifest: LocalSourceManifest,
    relative_path: str,
    *,
    operation_id: UUID,
    sequence_range: SemiAutomaticSelectionRange | None = None,
    decision_kind: V7OutputDecisionKind = V7OutputDecisionKind.MANUAL_FIRST,
    decision_generation: int = 0,
    operator_confirmed_range: bool = False,
    expected_previous_checksum_sha256: str | None = None,
    expected_previous_owner_operation_id: UUID | None = None,
) -> V7ManualOutputRequest:
    source = next(item for item in manifest.sources if item.relative_path == relative_path)
    return V7ManualOutputRequest(
        operation_id=operation_id,
        sequence_range=sequence_range or SemiAutomaticSelectionRange(1, 9),
        source_index=source.source_index,
        source_relative_path=source.relative_path,
        source_size_bytes=source.size_bytes,
        source_checksum_sha256=source.checksum_sha256,
        decision_kind=decision_kind,
        decision_generation=decision_generation,
        operator_confirmed_range=operator_confirmed_range,
        expected_previous_checksum_sha256=expected_previous_checksum_sha256,
        expected_previous_owner_operation_id=expected_previous_owner_operation_id,
    )


def _replacement_fixture(
    tmp_path: Path,
) -> tuple[Path, LocalSourceManifest, V7FirstOutputRequest, V7ManualOutputRequest]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.jpg").write_bytes(b"first-original-jpeg-bytes")
    (source / "replacement.jpg").write_bytes(b"replacement-original-jpeg-bytes")
    (source / "second-replacement.jpg").write_bytes(b"second-replacement-original-jpeg-bytes")
    manifest = _manifest(source)
    first = next(item for item in manifest.sources if item.relative_path == "first.jpg")
    automatic = V7FirstOutputRequest(
        operation_id=OPERATION_ID,
        sequence_range=SemiAutomaticSelectionRange(1, 9),
        source_index=first.source_index,
        source_relative_path=first.relative_path,
        source_size_bytes=first.size_bytes,
        source_checksum_sha256=first.checksum_sha256,
    )
    replacement = _request_for_source(
        manifest,
        "replacement.jpg",
        operation_id=REPLACEMENT_OPERATION_ID,
        decision_kind=V7OutputDecisionKind.MANUAL_REPLACE,
        decision_generation=1,
        operator_confirmed_range=True,
        expected_previous_checksum_sha256=first.checksum_sha256,
        expected_previous_owner_operation_id=automatic.operation_id,
    )
    return source, manifest, automatic, replacement


def test_first_output_is_byte_identical_committed_and_idempotent(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)

    first = writer.write_first(request)
    second = writer.write_first(request)
    journal = writer.recover()

    target = writer.output_root / "seq_1-9.jpg"
    assert first == second
    assert first.state is V7OutputOperationState.COMMITTED
    assert target.read_bytes() == (source / "frame.jpg").read_bytes()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == request.source_checksum_sha256
    assert journal.owners[0].operation_id == request.operation_id


def test_existing_foreign_target_is_never_overwritten(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    output = source.with_name("source cut")
    output.mkdir()
    target = output / request.target_name
    target.write_bytes(b"foreign")

    with pytest.raises(V7OutputWriterError) as error:
        _writer(source, manifest).write_first(request)

    assert error.value.code == "V7_OUTPUT_TARGET_CONFLICT"
    assert target.read_bytes() == b"foreign"


@pytest.mark.parametrize("crash_phase", ["prepared", "temp_written", "published"])
def test_recovery_after_each_persistent_phase_commits_exactly_one_output(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    source, manifest, request = _fixture(tmp_path)

    def crash(phase: str, _operation: object) -> None:
        if phase == crash_phase:
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash).write_first(request)

    restored = _writer(source, manifest)
    journal = restored.recover()
    operation = restored.write_first(request)

    assert operation.state is V7OutputOperationState.COMMITTED
    if crash_phase == "published":
        assert journal.operations[0].state is V7OutputOperationState.COMMITTED
    assert (restored.output_root / request.target_name).read_bytes() == (
        source / "frame.jpg"
    ).read_bytes()
    assert len(restored.recover().operations) == 1


def test_same_idempotency_key_cannot_change_the_command(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.write_first(request)
    contradictory = V7FirstOutputRequest(
        operation_id=request.operation_id,
        sequence_range=SemiAutomaticSelectionRange(10, 18),
        source_index=request.source_index,
        source_relative_path=request.source_relative_path,
        source_size_bytes=request.source_size_bytes,
        source_checksum_sha256=request.source_checksum_sha256,
    )

    with pytest.raises(V7OutputWriterError) as error:
        writer.write_first(contradictory)

    assert error.value.code == "V7_OUTPUT_IDEMPOTENCY_CONFLICT"


def test_stale_generation_is_superseded_before_it_can_publish(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)

    def crash(phase: str, _operation: object) -> None:
        if phase == "prepared":
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError):
        _writer(source, manifest, fault_hook=crash).write_first(request)
    writer = _writer(source, manifest)
    superseded = writer.supersede_pending(request.operation_id, next_generation=1)

    assert superseded.state is V7OutputOperationState.SUPERSEDED
    assert writer.write_first(request).state is V7OutputOperationState.SUPERSEDED
    assert not (writer.output_root / request.target_name).exists()


def test_generation_validator_blocks_a_writer_after_its_last_pre_publish_check(
    tmp_path: Path,
) -> None:
    source, manifest, request = _fixture(tmp_path)
    allowed = {"value": True}

    def invalidate(phase: str, _operation: object) -> None:
        if phase == "before_publish":
            allowed["value"] = False

    operation = _writer(
        source,
        manifest,
        generation_validator=lambda _operation: allowed["value"],
        fault_hook=invalidate,
    ).write_first(request)

    assert operation.state is V7OutputOperationState.CONFLICT
    assert operation.conflict_code == "V7_OUTPUT_STALE_GENERATION"
    assert not (source.with_name("source cut") / request.target_name).exists()


def test_directory_lock_blocks_a_newer_decision_after_generation_check(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    concurrent_result: dict[str, str] = {}
    contender = _writer(source, manifest)

    def attempt_supersede() -> None:
        try:
            contender.supersede_pending(request.operation_id, next_generation=1)
        except V7OutputWriterError as error:
            concurrent_result["code"] = error.code

    def pause_after_generation(phase: str, _operation: object) -> None:
        if phase == "after_generation_validation":
            thread = Thread(target=attempt_supersede)
            thread.start()
            thread.join(timeout=3)
            assert not thread.is_alive()

    operation = _writer(source, manifest, fault_hook=pause_after_generation).write_first(request)

    assert concurrent_result == {"code": "V7_OUTPUT_LOCK_BUSY"}
    assert operation.state is V7OutputOperationState.COMMITTED
    journal = _writer(source, manifest).recover()
    assert journal.owners[0].operation_id == OPERATION_ID


@pytest.mark.parametrize("crash_phase", ["target_linked", "published"])
def test_supersede_reconciles_visible_target_before_rejecting_a_pending_command(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    source, manifest, request = _fixture(tmp_path)

    def crash(phase: str, _operation: object) -> None:
        if phase == crash_phase:
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash).write_first(request)

    restored = _writer(source, manifest)
    with pytest.raises(V7OutputWriterError) as error:
        restored.supersede_pending(request.operation_id, next_generation=1)

    assert error.value.code == "V7_OUTPUT_GENERATION_INVALID"
    journal = restored.recover()
    assert journal.operations[0].state is V7OutputOperationState.COMMITTED
    assert journal.owners[0].operation_id == request.operation_id


@pytest.mark.parametrize("crash_phase", ["temp_written", "published"])
def test_recovery_marks_changed_temp_or_target_as_a_conflict(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    source, manifest, request = _fixture(tmp_path)

    def crash(phase: str, _operation: object) -> None:
        if phase == crash_phase:
            raise RuntimeError("TEST_CRASH")

    writer = _writer(source, manifest, fault_hook=crash)
    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        writer.write_first(request)
    if crash_phase == "temp_written":
        temp = writer.output_root / ".v7-selection-output" / f"output-{OPERATION_ID.hex}.part"
        temp.write_bytes(b"foreign-temp")
    else:
        (writer.output_root / request.target_name).write_bytes(b"foreign-target")

    journal = _writer(source, manifest).recover()

    assert journal.operations[0].state is V7OutputOperationState.CONFLICT
    assert journal.operations[0].conflict_code in {
        "V7_OUTPUT_TEMP_CHECKSUM_MISMATCH",
        "V7_OUTPUT_TARGET_CHECKSUM_MISMATCH",
    }


def test_manifest_drift_blocks_recovery_even_for_a_nonselected_source(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    (source / "unselected.jpg").write_bytes(b"unselected-original")
    manifest = _manifest(source)
    selected = manifest.sources[0]
    request = V7FirstOutputRequest(
        operation_id=request.operation_id,
        sequence_range=request.sequence_range,
        source_index=selected.source_index,
        source_relative_path=selected.relative_path,
        source_size_bytes=selected.size_bytes,
        source_checksum_sha256=selected.checksum_sha256,
    )

    def crash(phase: str, _operation: object) -> None:
        if phase == "prepared":
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash).write_first(request)
    (source / "unselected.jpg").write_bytes(b"unselected-changed")

    with pytest.raises(V7OutputWriterError) as error:
        _writer(source, manifest).recover()

    assert error.value.code == "V7_OUTPUT_SOURCE_MANIFEST_DRIFT"


def test_recovery_rejects_an_owner_that_does_not_match_a_committed_operation(
    tmp_path: Path,
) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.write_first(request)
    journal_path = writer.output_root / ".v7-selection-output" / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    journal["owners"][0]["operationId"] = "00000000-0000-0000-0000-000000000799"
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    with pytest.raises(V7OutputWriterError) as error:
        _writer(source, manifest).recover()

    assert error.value.code == "V7_OUTPUT_JOURNAL_INVALID"


def test_t08_journal_without_manual_fields_keeps_automatic_idempotency(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.write_first(request)
    journal_path = writer.output_root / ".v7-selection-output" / "journal.json"
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    for field in {
        "decisionKind",
        "expectedPreviousChecksumSha256",
        "expectedPreviousOwnerOperationId",
        "operatorConfirmedRange",
    }:
        del journal["operations"][0][field]
    journal_path.write_text(json.dumps(journal), encoding="utf-8")

    retried = _writer(source, manifest).write_first(request)

    assert retried.state is V7OutputOperationState.COMMITTED
    assert retried.operation_id == request.operation_id


@pytest.mark.parametrize("mutate", ["remove", "replace"])
def test_recovery_preserves_a_readable_conflict_for_a_damaged_committed_target(
    tmp_path: Path,
    mutate: str,
) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.write_first(request)
    target = writer.output_root / request.target_name
    if mutate == "remove":
        target.unlink()
    else:
        target.write_bytes(b"external-change")

    first = _writer(source, manifest).recover()
    second = _writer(source, manifest).recover()

    assert first == second
    assert first.operations[0].state is V7OutputOperationState.CONFLICT
    assert first.owners[0].operation_id == request.operation_id


def test_writer_rejects_unsupported_volume_before_creating_output(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)

    with pytest.raises(V7OutputWriterError) as error:
        _writer(source, manifest, filesystem_validator=lambda _path: False).write_first(request)

    assert error.value.code == "V7_OUTPUT_FILESYSTEM_UNSUPPORTED"
    assert not source.with_name("source cut").exists()


def test_local_ntfs_validator_rejects_unc_path_without_following_it() -> None:
    assert not _is_supported_local_ntfs(Path(r"\\server\share\source"))


def test_recovery_rejects_partial_journal_and_foreign_temp(tmp_path: Path) -> None:
    source, manifest, request = _fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.output_root.mkdir()
    state = writer.output_root / ".v7-selection-output"
    state.mkdir()
    (state / "journal.json").write_text("{", encoding="utf-8")

    with pytest.raises(V7OutputWriterError) as invalid:
        writer.recover()
    assert invalid.value.code == "V7_OUTPUT_JOURNAL_INVALID"

    (state / "journal.json").unlink()
    journal = writer.recover()
    assert journal.operations == ()
    (state / f"output-{request.operation_id.hex}.part").write_bytes(b"foreign")
    with pytest.raises(V7OutputWriterError) as orphan:
        writer.write_first(request)
    assert orphan.value.code == "V7_OUTPUT_ORPHAN_TEMP"


def test_manual_first_is_idempotent_after_a_lost_response(tmp_path: Path) -> None:
    source, manifest, _ = _fixture(tmp_path)
    request = _request_for_source(
        manifest,
        "frame.jpg",
        operation_id=MANUAL_OPERATION_ID,
    )
    writer = _writer(source, manifest)

    first = writer.write_manual_first(request)
    second = writer.write_manual_first(request)

    assert first == second
    assert first.state is V7OutputOperationState.COMMITTED
    assert first.decision_kind is V7OutputDecisionKind.MANUAL_FIRST
    assert (writer.output_root / request.target_name).read_bytes() == (
        source / "frame.jpg"
    ).read_bytes()


def test_manual_no_ocr_requires_operator_confirmation_and_remains_manual(tmp_path: Path) -> None:
    source, manifest, _ = _fixture(tmp_path)
    entry = manifest.sources[0]
    with pytest.raises(V7OutputWriterError) as missing_confirmation:
        V7ManualOutputRequest(
            operation_id=MANUAL_OPERATION_ID,
            sequence_range=SemiAutomaticSelectionRange(1, 9),
            source_index=entry.source_index,
            source_relative_path=entry.relative_path,
            source_size_bytes=entry.size_bytes,
            source_checksum_sha256=entry.checksum_sha256,
            decision_kind=V7OutputDecisionKind.MANUAL_NO_OCR,
        )
    assert missing_confirmation.value.code == "V7_OUTPUT_REQUEST_INVALID"

    confirmed = _request_for_source(
        manifest,
        "frame.jpg",
        operation_id=MANUAL_OPERATION_ID,
        decision_kind=V7OutputDecisionKind.MANUAL_NO_OCR,
        operator_confirmed_range=True,
    )
    operation = _writer(source, manifest).write_manual_no_ocr(confirmed)

    assert operation.state is V7OutputOperationState.COMMITTED
    assert operation.decision_kind is V7OutputDecisionKind.MANUAL_NO_OCR
    assert operation.operator_confirmed_range is True


def test_manual_final_partial_page_writes_seq_1_8_but_automatic_refuses_it(tmp_path: Path) -> None:
    source, manifest, automatic = _fixture(tmp_path)
    entry = manifest.sources[0]
    with pytest.raises(V7OutputWriterError) as automatic_error:
        V7FirstOutputRequest(
            operation_id=automatic.operation_id,
            sequence_range=SemiAutomaticSelectionRange(1, 8),
            source_index=entry.source_index,
            source_relative_path=entry.relative_path,
            source_size_bytes=entry.size_bytes,
            source_checksum_sha256=entry.checksum_sha256,
        )
    assert automatic_error.value.code == "V7_OUTPUT_REQUEST_INVALID"

    manual = _request_for_source(
        manifest,
        "frame.jpg",
        operation_id=MANUAL_OPERATION_ID,
        sequence_range=SemiAutomaticSelectionRange(1, 8),
    )
    operation = _writer(source, manifest).write_manual_first(manual)

    assert operation.state is V7OutputOperationState.COMMITTED
    assert (source.with_name("source cut") / "seq_1-8.jpg").read_bytes() == (
        source / "frame.jpg"
    ).read_bytes()


def test_manual_replace_keeps_history_and_installs_a_new_current_owner(tmp_path: Path) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    writer = _writer(source, manifest)
    first = writer.write_first(automatic)
    second = writer.manual_replace(replacement)
    journal = _writer(source, manifest).recover()

    assert first.state is V7OutputOperationState.COMMITTED
    assert second.state is V7OutputOperationState.COMMITTED
    assert (writer.output_root / replacement.target_name).read_bytes() == (
        source / "replacement.jpg"
    ).read_bytes()
    assert journal.owners[0].operation_id == replacement.operation_id
    assert journal.owners[0].checksum_sha256 == replacement.source_checksum_sha256
    assert journal.operations[0].operation_id == automatic.operation_id
    assert journal.operations[0].state is V7OutputOperationState.COMMITTED
    assert journal.operations[1].operation_id == replacement.operation_id


def test_manual_replace_requires_range_confirmation(tmp_path: Path) -> None:
    _, _, _, replacement = _replacement_fixture(tmp_path)

    with pytest.raises(V7OutputWriterError) as error:
        replace(replacement, operator_confirmed_range=False)

    assert error.value.code == "V7_OUTPUT_REQUEST_INVALID"


@pytest.mark.parametrize("crash_phase", ["target_replaced", "published"])
def test_manual_replace_recovery_commits_after_publication_before_acknowledgement(
    tmp_path: Path,
    crash_phase: str,
) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    _writer(source, manifest).write_first(automatic)

    def crash(phase: str, _operation: object) -> None:
        if phase == crash_phase:
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash).manual_replace(replacement)

    journal = _writer(source, manifest).recover()

    assert journal.owners[0].operation_id == replacement.operation_id
    assert journal.operations[0].state is V7OutputOperationState.COMMITTED
    assert journal.operations[1].state is V7OutputOperationState.COMMITTED
    assert (source.with_name("source cut") / replacement.target_name).read_bytes() == (
        source / "replacement.jpg"
    ).read_bytes()
    assert (
        _writer(source, manifest).write_first(automatic).state is V7OutputOperationState.COMMITTED
    )
    second_restart = _writer(source, manifest).recover()
    assert second_restart.operations[0].state is V7OutputOperationState.COMMITTED


def test_second_manual_replace_crash_keeps_every_historical_owner_committed(
    tmp_path: Path,
) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    writer = _writer(source, manifest)
    writer.write_first(automatic)
    writer.manual_replace(replacement)
    next_replacement = _request_for_source(
        manifest,
        "second-replacement.jpg",
        operation_id=SECOND_REPLACEMENT_OPERATION_ID,
        decision_kind=V7OutputDecisionKind.MANUAL_REPLACE,
        decision_generation=2,
        operator_confirmed_range=True,
        expected_previous_checksum_sha256=replacement.source_checksum_sha256,
        expected_previous_owner_operation_id=replacement.operation_id,
    )

    def crash(phase: str, _operation: object) -> None:
        if phase == "target_replaced":
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash).manual_replace(next_replacement)

    first_restart = _writer(source, manifest).recover()
    second_restart = _writer(source, manifest).recover()

    assert [operation.state for operation in first_restart.operations] == [
        V7OutputOperationState.COMMITTED,
        V7OutputOperationState.COMMITTED,
        V7OutputOperationState.COMMITTED,
    ]
    assert second_restart == first_restart
    assert first_restart.owners[0].operation_id == next_replacement.operation_id
    assert (source.with_name("source cut") / next_replacement.target_name).read_bytes() == (
        source / "second-replacement.jpg"
    ).read_bytes()


def test_manual_replace_refuses_changed_target_without_overwriting_it(tmp_path: Path) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    _writer(source, manifest).write_first(automatic)
    target = source.with_name("source cut") / replacement.target_name

    def mutate_target(phase: str, _operation: object) -> None:
        if phase == "before_publish":
            target.write_bytes(b"external-target")

    with pytest.raises(V7OutputWriterError) as error:
        _writer(source, manifest, fault_hook=mutate_target).manual_replace(replacement)

    assert error.value.code == "V7_OUTPUT_REPLACE_STALE_TARGET"
    assert target.read_bytes() == b"external-target"


def test_stale_manual_replace_cannot_pass_the_shared_directory_lock(tmp_path: Path) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    _writer(source, manifest).write_first(automatic)
    contender_result: dict[str, str] = {}
    stale = V7ManualOutputRequest(
        operation_id=MANUAL_OPERATION_ID,
        sequence_range=replacement.sequence_range,
        source_index=replacement.source_index,
        source_relative_path=replacement.source_relative_path,
        source_size_bytes=replacement.source_size_bytes,
        source_checksum_sha256=replacement.source_checksum_sha256,
        decision_kind=V7OutputDecisionKind.MANUAL_REPLACE,
        decision_generation=2,
        operator_confirmed_range=True,
        expected_previous_checksum_sha256=automatic.source_checksum_sha256,
        expected_previous_owner_operation_id=automatic.operation_id,
    )

    def attempt_stale_replace() -> None:
        try:
            _writer(source, manifest).manual_replace(stale)
        except V7OutputWriterError as error:
            contender_result["code"] = error.code

    def pause_after_generation(phase: str, _operation: object) -> None:
        if phase == "after_generation_validation":
            thread = Thread(target=attempt_stale_replace)
            thread.start()
            thread.join(timeout=3)
            assert not thread.is_alive()

    committed = _writer(source, manifest, fault_hook=pause_after_generation).manual_replace(
        replacement
    )
    with pytest.raises(V7OutputWriterError) as stale_error:
        _writer(source, manifest).manual_replace(stale)

    assert contender_result == {"code": "V7_OUTPUT_LOCK_BUSY"}
    assert committed.state is V7OutputOperationState.COMMITTED
    assert stale_error.value.code == "V7_OUTPUT_REPLACE_STALE_TARGET"


@pytest.mark.parametrize("action", ["cancel", "supersede"])
def test_cancelled_or_superseded_pending_manual_replace_cannot_resume_after_restart(
    tmp_path: Path,
    action: str,
) -> None:
    source, manifest, automatic, replacement = _replacement_fixture(tmp_path)
    _writer(source, manifest).write_first(automatic)

    def crash_after_temp(phase: str, _operation: object) -> None:
        if phase == "temp_written":
            raise RuntimeError("TEST_CRASH")

    with pytest.raises(RuntimeError, match="TEST_CRASH"):
        _writer(source, manifest, fault_hook=crash_after_temp).manual_replace(replacement)
    writer = _writer(source, manifest)
    operation = (
        writer.cancel_pending(replacement.operation_id)
        if action == "cancel"
        else writer.supersede_pending(replacement.operation_id, next_generation=2)
    )
    journal = _writer(source, manifest).recover()

    assert (
        operation.state
        is {
            "cancel": V7OutputOperationState.CANCELLED,
            "supersede": V7OutputOperationState.SUPERSEDED,
        }[action]
    )
    assert journal.operations[1].state is operation.state
    assert (source.with_name("source cut") / replacement.target_name).read_bytes() == (
        source / "first.jpg"
    ).read_bytes()
