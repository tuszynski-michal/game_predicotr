from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_api.application.layout_imports import (
    LayoutImportSourceInspector,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_worker.imports.contracts import StagedLayoutImportRow
from game_predictor_worker.imports.handler import LayoutImportStagingHandler
from game_predictor_worker.jobs.runtime import JobHandlerError

GAME_ID = UUID("11111111-1111-4111-8111-111111111111")


class FakeStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[UUID, int], StagedLayoutImportRow] = {}
        self.upsert_calls: list[tuple[int, ...]] = []
        self.delete_calls: list[int] = []

    def upsert_rows(
        self,
        job_id: UUID,
        rows: tuple[StagedLayoutImportRow, ...],
    ) -> None:
        self.upsert_calls.append(tuple(row.line_number for row in rows))
        for row in rows:
            self.rows[(job_id, row.line_number)] = row

    def delete_rows_after(
        self,
        job_id: UUID,
        *,
        line_number: int,
    ) -> None:
        self.delete_calls.append(line_number)
        self.rows = {
            key: row for key, row in self.rows.items() if key[0] != job_id or key[1] <= line_number
        }


class FakeContext:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)


class StopAfterFirstCheckpoint(FakeContext):
    def checkpoint(self, **values: object) -> None:
        super().checkpoint(**values)
        if len(self.checkpoints) == 1:
            raise RuntimeError("simulated process crash after staging upsert")


class MutatingAttestor:
    def __init__(
        self,
        inspector: LayoutImportSourceInspector,
        source_path: Path,
    ) -> None:
        self._inspector = inspector
        self._source_path = source_path
        self.calls = 0

    def inspect(self, source_path: str, *, contract_version: int):
        self.calls += 1
        if self.calls == 2:
            self._source_path.write_bytes(b'{"schemaVersion":1,"sequenceNumber":9,"cells":[9]}\n')
        return self._inspector.inspect(
            source_path,
            contract_version=contract_version,
        )


def _write_jsonl(path: Path) -> bytes:
    content = (
        b'{"schemaVersion":1,"sequenceNumber":1,"cells":[1,2]}\n'
        b'{"schemaVersion":1,"sequenceNumber":"bad","cells":[2,1]}\n'
        b'{"schemaVersion":1,"sequenceNumber":3,"cells":[2,2]}\n'
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _job(source_path: str, content: bytes) -> Job:
    return create_job(
        JobType.IMPORT,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 1,
            "import_kind": "layout_file",
            "source_path": source_path,
            "source_checksum": hashlib.sha256(content).hexdigest(),
            "source_size_bytes": len(content),
            "file_format": "jsonl",
            "contract_version": 1,
        },
    )


def _required_int(value: object) -> int:
    assert isinstance(value, int) and not isinstance(value, bool)
    return value


def _resumed_job(job: Job, checkpoint_call: dict[str, object]) -> Job:
    payload = checkpoint_call["checkpoint_payload"]
    assert isinstance(payload, dict)
    return replace(
        job,
        checkpoint_payload=payload,
        stage=str(checkpoint_call["stage"]),
        progress_current=_required_int(checkpoint_call["current"]),
        progress_total=_required_int(checkpoint_call["total"]),
        success_count=_required_int(checkpoint_call["success_count"]),
        failure_count=_required_int(checkpoint_call["failure_count"]),
        review_count=_required_int(checkpoint_call["review_count"]),
    )


def test_handler_stages_valid_and_invalid_rows_with_final_checkpoint(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = _write_jsonl(import_root / "layouts.jsonl")
    store = FakeStore()
    context = FakeContext()
    handler = LayoutImportStagingHandler(
        store,
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
        batch_size=2,
    )
    job = _job("layouts.jsonl", content)

    handler(context, job)  # type: ignore[arg-type]

    assert len(store.rows) == 3
    assert store.rows[(job.id, 1)].sequence_number == 1
    assert store.rows[(job.id, 2)].error_code == "import_sequence_number_invalid"
    assert store.rows[(job.id, 3)].sequence_number == 3
    assert context.checkpoints[-1]["stage"] == "staged_import_rows"
    final = context.checkpoints[-1]["checkpoint_payload"]
    assert isinstance(final, dict)
    assert final["stream_complete"] is True
    assert final["byte_offset"] == len(content)
    assert context.checkpoints[-1]["success_count"] == 2
    assert context.checkpoints[-1]["failure_count"] == 1


def test_crash_after_upsert_replays_same_batch_without_duplicates(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = _write_jsonl(import_root / "layouts.jsonl")
    store = FakeStore()
    handler = LayoutImportStagingHandler(
        store,
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
        batch_size=2,
    )
    job = _job("layouts.jsonl", content)

    with pytest.raises(RuntimeError, match="simulated process crash"):
        handler(StopAfterFirstCheckpoint(), job)  # type: ignore[arg-type]
    assert len(store.rows) == 2

    retry = FakeContext()
    handler(retry, job)  # type: ignore[arg-type]

    assert len(store.rows) == 3
    assert store.upsert_calls[:2] == [(1, 2), (1, 2)]
    assert retry.checkpoints[-1]["stage"] == "staged_import_rows"


def test_resume_from_durable_checkpoint_matches_single_pass(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = _write_jsonl(import_root / "layouts.jsonl")
    job = _job("layouts.jsonl", content)
    inspector = LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024)
    resumed_store = FakeStore()
    handler = LayoutImportStagingHandler(
        resumed_store,
        inspector,
        batch_size=2,
    )
    interrupted = StopAfterFirstCheckpoint()

    with pytest.raises(RuntimeError):
        handler(interrupted, job)  # type: ignore[arg-type]
    resumed_store.upsert_rows(
        job.id,
        (
            StagedLayoutImportRow(
                line_number=99,
                byte_offset_end=len(content) + 10,
                sequence_number=99,
                cells=(9, 9),
                error_code=None,
                error_message=None,
            ),
        ),
    )
    resumed_context = FakeContext()
    handler(
        resumed_context,
        _resumed_job(job, interrupted.checkpoints[0]),
    )  # type: ignore[arg-type]

    single_store = FakeStore()
    LayoutImportStagingHandler(
        single_store,
        inspector,
        batch_size=10,
    )(FakeContext(), job)  # type: ignore[arg-type]

    assert resumed_store.rows == single_store.rows
    assert (job.id, 99) not in resumed_store.rows
    assert resumed_store.upsert_calls == [(1, 2), (99,), (3,)]


def test_source_changed_before_staging_is_rejected_without_rows(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    source = import_root / "layouts.jsonl"
    content = _write_jsonl(source)
    job = _job("layouts.jsonl", content)
    source.write_bytes(b'{"schemaVersion":1,"sequenceNumber":9,"cells":[9]}\n')
    store = FakeStore()
    handler = LayoutImportStagingHandler(
        store,
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
    )

    with pytest.raises(JobHandlerError) as captured:
        handler(FakeContext(), job)  # type: ignore[arg-type]

    assert captured.value.code == "IMPORT_SOURCE_ATTESTATION_MISMATCH"
    assert store.rows == {}


def test_prefix_chain_mismatch_clears_staging_and_replays_from_start(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = _write_jsonl(import_root / "layouts.jsonl")
    job = _job("layouts.jsonl", content)
    store = FakeStore()
    inspector = LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024)
    handler = LayoutImportStagingHandler(store, inspector, batch_size=2)
    interrupted = StopAfterFirstCheckpoint()
    with pytest.raises(RuntimeError):
        handler(interrupted, job)  # type: ignore[arg-type]
    checkpoint_call = dict(interrupted.checkpoints[0])
    checkpoint_payload = checkpoint_call["checkpoint_payload"]
    assert isinstance(checkpoint_payload, dict)
    checkpoint_call["checkpoint_payload"] = {
        **checkpoint_payload,
        "prefix_chain": "0" * 64,
    }

    context = FakeContext()
    handler(
        context,
        _resumed_job(job, checkpoint_call),
    )  # type: ignore[arg-type]

    reset_payload = context.checkpoints[0]["checkpoint_payload"]
    assert isinstance(reset_payload, dict)
    assert reset_payload["byte_offset"] == 0
    assert len(store.rows) == 3
    assert context.checkpoints[-1]["stage"] == "staged_import_rows"


def test_final_source_change_resets_checkpoint_for_safe_full_replay(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    source = import_root / "layouts.jsonl"
    content = _write_jsonl(source)
    job = _job("layouts.jsonl", content)
    store = FakeStore()
    inspector = LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024)
    context = FakeContext()
    handler = LayoutImportStagingHandler(
        store,
        MutatingAttestor(inspector, source),
        batch_size=10,
    )

    with pytest.raises(JobHandlerError) as captured:
        handler(context, job)  # type: ignore[arg-type]

    assert captured.value.code == "IMPORT_SOURCE_ATTESTATION_MISMATCH"
    reset = context.checkpoints[-1]
    reset_payload = reset["checkpoint_payload"]
    assert isinstance(reset_payload, dict)
    assert reset_payload["byte_offset"] == 0
    assert reset_payload["processed_count"] == 0
    assert reset["success_count"] == 0
    assert reset["failure_count"] == 0
    assert store.rows == {}

    source.write_bytes(content)
    retry = FakeContext()
    LayoutImportStagingHandler(
        store,
        inspector,
        batch_size=10,
    )(retry, _resumed_job(job, reset))  # type: ignore[arg-type]

    assert retry.checkpoints[-1]["stage"] == "staged_import_rows"
    assert len(store.rows) == 3


def test_handler_rejects_wrong_type_and_unattested_payload(
    tmp_path: Path,
) -> None:
    import_root = tmp_path / "imports"
    content = _write_jsonl(import_root / "layouts.jsonl")
    handler = LayoutImportStagingHandler(
        FakeStore(),
        LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024),
    )
    import_job = _job("layouts.jsonl", content)

    with pytest.raises(JobHandlerError) as wrong_type:
        handler(
            FakeContext(),  # type: ignore[arg-type]
            replace(import_job, job_type=JobType.VALIDATE),
        )
    with pytest.raises(JobHandlerError) as bad_payload:
        handler(
            FakeContext(),  # type: ignore[arg-type]
            replace(
                import_job,
                input_payload={
                    **import_job.input_payload,
                    "client_checksum": "untrusted",
                },
            ),
        )

    assert wrong_type.value.code == "INVALID_LAYOUT_IMPORT_JOB_TYPE"
    assert bad_payload.value.code == "INVALID_LAYOUT_IMPORT_PAYLOAD"
