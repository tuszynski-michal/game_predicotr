"""TASK-1041: a V3 import records the sources it skips without a slot binding."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.images.neural_unbound_sources import (
    NEURAL_UNBOUND_SOURCES_SAMPLE_LIMIT,
    record_neural_unbound_sources,
    unbound_neural_sources,
)
from game_predictor_worker.images.pipeline_contract import CellAssetRolloutMode
from game_predictor_worker.images.production_workflow import ProductionImageImportWorkflow
from game_predictor_worker.images.source_ingestion import ManagedOriginal, ManagedSourceManifest
from game_predictor_worker.jobs.runtime import JobHandlerError

MANIFEST_SHA = "c" * 64


def _original(index: int) -> ManagedOriginal:
    start = index * 9 + 1
    return ManagedOriginal(
        checksum_sha256=f"{index + 1:064x}",
        source_relative_path=f"seq_{start}-{start + 8}.jpg",
        managed_relative_path=f"data/originals/{index + 1:064x}.jpg",
        size_bytes=100,
        sequence_range_start=start,
        sequence_range_end=start + 8,
        sequence_range_source="filename",
    )


def _entries(originals: tuple[ManagedOriginal, ...], statuses: list[str]) -> dict[str, object]:
    reasons = {
        "slot_binding_required": "NEURAL_GRID_SLOT_BINDING_REQUIRED",
        "review_required": "NEURAL_GRID_REVIEW_REQUIRED",
    }
    return {
        original.checksum_sha256: {
            "sourceRelativePath": original.source_relative_path,
            "status": status,
            **({"reasonCode": reasons[status]} if status in reasons else {}),
        }
        for original, status in zip(originals, statuses, strict=True)
    }


def test_only_slot_binding_required_sources_are_reported_with_their_reason() -> None:
    originals = tuple(_original(index) for index in range(4))
    entries = _entries(
        originals,
        ["slot_binding_required", "review_required", "skipped_human_resolved", "x"],
    )
    entries[originals[3].checksum_sha256] = {
        "status": "slot_binding_required",
        "reasonCode": "NEURAL_GRID_SOURCE_TIME_LIMIT",
    }

    assert unbound_neural_sources(originals, entries) == (
        {
            "sourceChecksumSha256": originals[0].checksum_sha256,
            "sourceRelativePath": "seq_1-9.jpg",
            "sequenceRangeStart": 1,
            "sequenceRangeEnd": 9,
            "reasonCode": "NEURAL_GRID_SLOT_BINDING_REQUIRED",
        },
        {
            "sourceChecksumSha256": originals[3].checksum_sha256,
            "sourceRelativePath": "seq_28-36.jpg",
            "sequenceRangeStart": 28,
            "sequenceRangeEnd": 36,
            "reasonCode": "NEURAL_GRID_SOURCE_TIME_LIMIT",
        },
    )


def test_report_keeps_the_full_list_while_the_summary_keeps_a_bounded_sample(
    tmp_path: Path,
) -> None:
    originals = tuple(_original(index) for index in range(25))
    entries = _entries(originals, ["slot_binding_required"] * 24 + ["review_required"])
    job_id = uuid4()

    summary = record_neural_unbound_sources(
        tmp_path,
        job_id=job_id,
        page_geometry_manifest_checksum_sha256=MANIFEST_SHA,
        originals=originals,
        entries=entries,
    )

    assert summary is not None
    assert summary["sourceCount"] == 24
    assert summary["attestedBoardCount"] == 24 * 9
    assert summary["reasonCounts"] == {"NEURAL_GRID_SLOT_BINDING_REQUIRED": 24}
    assert summary["reportRelativePath"] == f"data/image-import-unbound-sources/{job_id}.json"
    sample = summary["sample"]
    assert isinstance(sample, list) and len(sample) == NEURAL_UNBOUND_SOURCES_SAMPLE_LIMIT
    assert sample[0] == {
        "sourceRelativePath": "seq_1-9.jpg",
        "sequenceRangeStart": 1,
        "sequenceRangeEnd": 9,
        "reasonCode": "NEURAL_GRID_SLOT_BINDING_REQUIRED",
    }
    report_path = tmp_path / str(summary["reportRelativePath"])
    content = report_path.read_bytes()
    assert hashlib.sha256(content).hexdigest() == summary["reportChecksumSha256"]
    report = json.loads(content)
    assert report["jobId"] == str(job_id)
    assert report["pageGeometryManifestChecksumSha256"] == MANIFEST_SHA
    assert [item["sourceChecksumSha256"] for item in report["sources"]] == [
        original.checksum_sha256 for original in originals[:24]
    ]

    # A resumed run rewrites identical bytes; a different list is a collision.
    assert (
        record_neural_unbound_sources(
            tmp_path,
            job_id=job_id,
            page_geometry_manifest_checksum_sha256=MANIFEST_SHA,
            originals=originals,
            entries=entries,
        )
        == summary
    )
    with pytest.raises(JobHandlerError) as caught:
        record_neural_unbound_sources(
            tmp_path,
            job_id=job_id,
            page_geometry_manifest_checksum_sha256=MANIFEST_SHA,
            originals=originals[:3],
            entries=entries,
        )
    assert caught.value.code == "NEURAL_GRID_UNBOUND_SOURCES_REPORT_COLLISION"


def test_fully_bound_import_writes_no_report(tmp_path: Path) -> None:
    originals = tuple(_original(index) for index in range(2))
    summary = record_neural_unbound_sources(
        tmp_path,
        job_id=uuid4(),
        page_geometry_manifest_checksum_sha256=MANIFEST_SHA,
        originals=originals,
        entries=_entries(originals, ["review_required", "skipped_human_resolved"]),
    )

    assert summary is None
    assert not (tmp_path / "data").exists()


class _Context:
    def __init__(self, job: object) -> None:
        self.job = job
        self.values: list[dict[str, object]] = []

    def now(self):  # type: ignore[no-untyped-def]
        return self.job.created_at  # type: ignore[attr-defined]

    def heartbeat(self) -> None:
        return None

    def checkpoint(self, **values: object) -> None:
        self.values.append(values)
        self.job = replace(  # type: ignore[type-var]
            self.job,
            progress_current=int(values["current"]),  # type: ignore[call-overload]
            progress_total=int(values["total"]),  # type: ignore[call-overload]
            success_count=int(values["success_count"]),  # type: ignore[call-overload]
            failure_count=int(values["failure_count"]),  # type: ignore[call-overload]
            review_count=int(values["review_count"]),  # type: ignore[call-overload]
        )


def _workflow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: tuple[ManagedOriginal, ...],
    entries: dict[str, object],
) -> tuple[ProductionImageImportWorkflow, _Context]:
    manifest = ManagedSourceManifest(
        source_directory=tmp_path,
        originals=originals,
        content=b"manifest",
        relative_path="data/originals/manifests/test.json",
        checksum_sha256=hashlib.sha256(b"manifest").hexdigest(),
    )
    workflow = ProductionImageImportWorkflow.__new__(ProductionImageImportWorkflow)
    workflow._artifact_root = tmp_path  # type: ignore[attr-defined]
    workflow._repository_root = tmp_path  # type: ignore[attr-defined]
    workflow._original_store = SimpleNamespace(  # type: ignore[attr-defined]
        load_or_create_manifest=lambda *_args, **_kwargs: manifest
    )
    workflow._source_handler = SimpleNamespace(  # type: ignore[attr-defined]
        ingest=lambda *_args, **_kwargs: manifest
    )
    workflow._batch_store = SimpleNamespace(  # type: ignore[attr-defined]
        register_files=lambda *_args, **_kwargs: None
    )
    workflow._projection_store = None  # type: ignore[attr-defined]
    workflow._board_cell_geometry_deferred_writer = None  # type: ignore[attr-defined]
    workflow._hard_reserve_bytes = 1  # type: ignore[attr-defined]
    workflow._record_browser_staging_handoff = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    module = "game_predictor_worker.images.production_workflow"
    monkeypatch.setattr(f"{module}._page_geometry_manifest", lambda *_a, **_k: entries)
    monkeypatch.setattr(f"{module}._page_geometry_manifest_checksum", lambda _job: MANIFEST_SHA)
    monkeypatch.setattr(
        f"{module}._geometry_rollout_snapshot",
        lambda _job: SimpleNamespace(cell_asset_mode=CellAssetRolloutMode.VIRTUAL_DEFAULT),
    )
    # Bound sources are admitted without re-validating the stub proposal.
    monkeypatch.setattr(
        "game_predictor_worker.images.neural_pending_geometry.bound_neural_originals",
        lambda items, values: tuple(
            item
            for item in items
            if values[item.checksum_sha256]["status"] == "review_required"  # type: ignore[index]
        ),
    )
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 5,
            "import_kind": "image_directory",
            "source_directory": str(tmp_path),
            "pipeline_fingerprint": "a" * 64,
        },
    )
    job = replace(job, input_payload={**job.input_payload, "neural_grid_proposal": {}})
    return workflow, _Context(job)


def test_import_without_any_bound_source_records_the_skip_in_its_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = tuple(_original(index) for index in range(3))
    entries = _entries(originals, ["slot_binding_required"] * 3)
    workflow, context = _workflow(tmp_path, monkeypatch, originals, entries)

    workflow(context, context.job)  # type: ignore[arg-type]

    final = context.values[-1]
    assert final["stage"] == "image_deferred_geometry_skip"
    payload = final["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["deferred_geometry_source_count"] == 3
    summary = payload["neural_unbound_sources"]
    assert summary["sourceCount"] == 3
    assert summary["attestedBoardCount"] == 27
    assert [item["sourceRelativePath"] for item in summary["sample"]] == [
        "seq_1-9.jpg",
        "seq_10-18.jpg",
        "seq_19-27.jpg",
    ]
    assert (tmp_path / summary["reportRelativePath"]).is_file()


def test_partial_import_keeps_the_skip_summary_in_pipeline_checkpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    originals = tuple(_original(index) for index in range(3))
    entries = _entries(
        originals, ["review_required", "slot_binding_required", "slot_binding_required"]
    )
    workflow, context = _workflow(tmp_path, monkeypatch, originals, entries)
    module = "game_predictor_worker.images.production_workflow"
    monkeypatch.setattr(
        f"{module}.ProductionImageStageAdapterSuite",
        lambda *_a, **_k: SimpleNamespace(adapters=lambda: None),
    )
    monkeypatch.setattr(f"{module}.ImagePipelineStageExecutor", lambda *_a, **_k: None)
    for helper_name in (
        "_symbol_model_snapshot",
        "_grid_profile_snapshot",
        "_page_registration_profile_snapshot",
    ):
        monkeypatch.setattr(f"{module}.{helper_name}", lambda _job: None)
    registered: list[object] = []

    class _Pipeline:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            return None

        def __call__(self, pipeline_context: object, _job: object) -> None:
            pipeline_context.checkpoint(  # type: ignore[attr-defined]
                checkpoint_payload={"checkpoint_kind": "fake"},
                stage="done",
                current=1,
                total=1,
                success_count=1,
                failure_count=0,
                review_count=0,
            )

    monkeypatch.setattr(f"{module}.ImageBatchHandler", _Pipeline)
    workflow._batch_store = SimpleNamespace(  # type: ignore[attr-defined]
        register_files=lambda *_args, **kwargs: registered.append(kwargs["registrations"])
    )

    workflow(context, context.job)  # type: ignore[arg-type]

    assert [item.source_checksum_sha256 for item in registered[0]] == [  # type: ignore[attr-defined]
        originals[0].checksum_sha256
    ]
    payload = context.values[-1]["checkpoint_payload"]
    assert isinstance(payload, dict)
    assert payload["checkpoint_kind"] == "fake"
    assert payload["neural_unbound_sources"]["sourceCount"] == 2
    assert payload["neural_unbound_sources"]["reasonCounts"] == {
        "NEURAL_GRID_SLOT_BINDING_REQUIRED": 2
    }
