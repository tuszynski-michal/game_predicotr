from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_worker.images import geometry_guard_report_reconstruction as module
from game_predictor_worker.images.large_import_geometry_guard import (
    ReconstructedLargeImportGeometryGuardReport,
)
from game_predictor_worker.images.source_ingestion import (
    ManagedOriginal,
    ManagedSourceManifest,
)
from game_predictor_worker.imports.validation_dispatch import ValidationJobDispatchHandler

GAME_ID = UUID("11111111-1111-1111-1111-111111111111")
SOURCE_JOB_ID = UUID("22222222-2222-2222-2222-222222222222")
SELECTION_ID = UUID("33333333-3333-3333-3333-333333333333")


class _Context:
    def __init__(self) -> None:
        self.values: dict[str, object] | None = None

    def checkpoint(self, **values: object) -> None:
        self.values = values


def test_reconstruction_uses_source_snapshots_and_records_a_separate_checkpoint(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source = replace(
        create_job(
            JobType.IMPORT,
            game_id=GAME_ID,
            input_payload={
                "schema_version": 5,
                "import_kind": "image_directory",
                "source_selection_id": str(SELECTION_ID),
                "source_manifest_sha256": "b" * 64,
            },
        ),
        id=SOURCE_JOB_ID,
        status=JobStatus.FAILED,
    )
    reconstruction = create_job(
        JobType.VALIDATE,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 1,
            "validation_kind": "image_geometry_guard_report_reconstruction",
            "source_selection_id": str(SELECTION_ID),
            "source_guard_job_id": str(SOURCE_JOB_ID),
            "legacy_report_checksum_sha256": "a" * 64,
            "source_manifest_checksum_sha256": "b" * 64,
            "page_geometry_manifest_checksum_sha256": "d" * 64,
        },
    )
    original = ManagedOriginal(
        checksum_sha256="1" * 64,
        source_relative_path="seq_1_9.jpg",
        managed_relative_path="data/originals/11/source.jpg",
        size_bytes=100,
        sequence_range_start=1,
        sequence_range_end=9,
        sequence_range_source="filename",
    )
    manifest = ManagedSourceManifest(
        source_directory=tmp_path,
        originals=(original,),
        content=b"manifest",
        relative_path=f"data/originals/manifests/{SOURCE_JOB_ID}.json",
        checksum_sha256="c" * 64,
    )
    legacy = {
        "jobId": str(SOURCE_JOB_ID),
        "sourceManifestChecksumSha256": "c" * 64,
        "pageGeometryManifestChecksumSha256": "d" * 64,
        "selectedSourceChecksums": [original.checksum_sha256],
    }
    handler = module.GeometryGuardReportReconstructionHandler.__new__(
        module.GeometryGuardReportReconstructionHandler
    )
    handler._artifact_root = tmp_path
    handler._repository_root = tmp_path
    handler._original_store = SimpleNamespace(load_existing_manifest=lambda _job: manifest)
    monkeypatch.setattr(handler, "_source_job", lambda _job: source)
    monkeypatch.setattr(handler, "_legacy_report", lambda _source, _job: (legacy, "a" * 64))
    monkeypatch.setattr(module, "_page_geometry_manifest_checksum", lambda _job: "d" * 64)
    monkeypatch.setattr(module, "_page_geometry_manifest", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(module, "_filter_canonical_originals", lambda values, _job: values)
    monkeypatch.setattr(
        module, "_filter_registered_geometry_originals", lambda values, _geometry: values
    )
    monkeypatch.setattr(module, "_board_cell_processing_snapshot", lambda _job: {"ok": True})
    monkeypatch.setattr(module, "_symbol_model_snapshot", lambda _job: object())
    monkeypatch.setattr(module, "_grid_profile_snapshot", lambda _job: {})
    monkeypatch.setattr(module, "_page_registration_profile_snapshot", lambda _job: {})
    monkeypatch.setattr(module, "_image_selection_run_id", lambda _job: None)
    monkeypatch.setattr(module, "_geometry_rollout_snapshot", lambda _job: object())
    monkeypatch.setattr(module, "_normalization_adapter_version", lambda _job: "v1")
    monkeypatch.setattr(module, "_pipeline_fingerprint", lambda _job: "e" * 64)
    monkeypatch.setattr(
        module, "ProductionImageStageAdapterSuite", lambda *_args, **_kwargs: object()
    )
    monkeypatch.setattr(
        module,
        "reconstruct_board_level_guard_report_from_legacy",
        lambda **_kwargs: ReconstructedLargeImportGeometryGuardReport(
            report_checksum_sha256="f" * 64,
            report_relative_path="data/image-geometry-guards/derived/ff/report.json",
            source_count=1,
            board_count=9,
        ),
    )
    context = _Context()

    handler(context, reconstruction)

    assert context.values is not None
    assert context.values["stage"] == "image_geometry_guard_report_reconstruction"
    checkpoint = context.values["checkpoint_payload"]
    assert isinstance(checkpoint, dict)
    descriptor = checkpoint["geometry_guard_report_reconstruction"]
    assert descriptor["sourceGuardJobId"] == str(SOURCE_JOB_ID)
    assert descriptor["legacyReportChecksumSha256"] == "a" * 64
    assert descriptor["reportChecksumSha256"] == "f" * 64
    assert source.status is JobStatus.FAILED


def test_validation_dispatch_routes_reconstruction_without_running_other_handlers() -> None:
    calls: list[str] = []
    dispatch = ValidationJobDispatchHandler(
        lambda _context, _job: calls.append("layout"),
        lambda _context, _job: calls.append("page"),
        lambda _context, _job: calls.append("guard"),
    )
    job = create_job(
        JobType.VALIDATE,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 1,
            "validation_kind": "image_geometry_guard_report_reconstruction",
            "source_selection_id": str(SELECTION_ID),
            "source_guard_job_id": str(SOURCE_JOB_ID),
            "legacy_report_checksum_sha256": "a" * 64,
            "source_manifest_checksum_sha256": "b" * 64,
            "page_geometry_manifest_checksum_sha256": "c" * 64,
        },
    )

    dispatch(_Context(), job)

    assert calls == ["guard"]
