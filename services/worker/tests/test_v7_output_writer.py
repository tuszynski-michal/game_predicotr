from __future__ import annotations

import hashlib
import json
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
    V7OutputOperationState,
    V7OutputWriter,
    V7OutputWriterError,
    _is_supported_local_ntfs,
)

SELECTION_ID = UUID("00000000-0000-0000-0000-000000000702")
OPERATION_ID = UUID("00000000-0000-0000-0000-000000000703")


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
