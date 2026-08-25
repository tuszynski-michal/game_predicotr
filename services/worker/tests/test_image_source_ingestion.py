import hashlib
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    ImageFolderSelectionService,
)
from game_predictor_api.domain.jobs import (
    JobType,
    checkpoint_job,
    create_job,
    start_job,
)
from game_predictor_worker.images.selection.output import (
    OUTPUT_MANIFEST_FILE,
    CuratedImageEntry,
    CuratedImageManifest,
)
from game_predictor_worker.images.source_ingestion import (
    SOURCE_INGESTION_CONTRACT,
    ImageSourceIngestionHandler,
    ManagedOriginalStore,
)
from game_predictor_worker.jobs.runtime import JobHandlerError
from PIL import Image

NOW = datetime(2026, 7, 31, 12, 0, tzinfo=UTC)
FINGERPRINT = "a" * 64


class RecordingContext:
    def __init__(self) -> None:
        self.checkpoints: list[dict[str, object]] = []

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(dict(values))


def _job(source: Path):
    return create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 1,
            "import_kind": "image_directory",
            "source_selection_id": str(uuid4()),
            "source_directory": str(source.resolve()),
            "source_display_name": source.name,
            "pipeline_fingerprint": FINGERPRINT,
        },
        created_at=NOW,
    )


def test_ingestion_deduplicates_bytes_and_survives_removed_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "a.jpg", "JPEG")
    (source / "b.jpeg").write_bytes((source / "a.jpg").read_bytes())
    artifact_root = tmp_path / "artifacts"
    job = _job(source)
    handler = ImageSourceIngestionHandler(ManagedOriginalStore(artifact_root))
    first = RecordingContext()

    handler(first, job)  # type: ignore[arg-type]

    originals = list((artifact_root / "data" / "originals").glob("??/*.jpg"))
    manifests = list((artifact_root / "data" / "originals" / "manifests").glob("*.json"))
    assert len(originals) == 1
    assert len(manifests) == 1
    final = first.checkpoints[-1]
    assert final["stage"] == "image_originals_copied"
    assert final["current"] == 1
    checkpoint = final["checkpoint_payload"]
    assert isinstance(checkpoint, dict)
    assert checkpoint["schema_version"] == 1
    assert checkpoint["contractVersion"] == SOURCE_INGESTION_CONTRACT

    lease_token = uuid4()
    claimed = start_job(
        job,
        worker_version="worker-test",
        worker_id="source-ingestion-test",
        lease_token=lease_token,
        lease_expires_at=NOW + timedelta(seconds=60),
        started_at=NOW,
    )
    persisted = checkpoint_job(
        claimed,
        lease_token=lease_token,
        checkpoint_payload=checkpoint,
        stage=str(final["stage"]),
        current=int(final["current"]),
        total=int(final["total"]),
        success_count=int(final["success_count"]),
        failure_count=int(final["failure_count"]),
        review_count=int(final["review_count"]),
        updated_at=NOW,
    )
    assert persisted.progress_current == 1
    assert persisted.checkpoint_payload == checkpoint

    (source / "a.jpg").unlink()
    (source / "b.jpeg").unlink()
    source.rmdir()
    resumed = RecordingContext()

    handler(resumed, job)  # type: ignore[arg-type]

    assert resumed.checkpoints[-1]["current"] == 1
    assert len(list((artifact_root / "data" / "originals").glob("??/*.jpg"))) == 1


def test_ingestion_copies_only_the_preflight_selected_originals(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "a.jpg", "JPEG")
    Image.new("RGB", (32, 24), (0, 255, 0)).save(source / "b.jpg", "JPEG")
    artifact_root = tmp_path / "artifacts"
    job = _job(source)
    store = ManagedOriginalStore(artifact_root)
    manifest = store.load_or_create_manifest(job, source_directory=source)
    selected = manifest.originals[:1]

    returned = ImageSourceIngestionHandler(store).ingest(
        RecordingContext(),  # type: ignore[arg-type]
        job,
        originals=selected,
    )

    assert returned.originals == manifest.originals
    copied = list((artifact_root / "data" / "originals").glob("??/*.jpg"))
    assert len(copied) == 1
    assert copied[0].stem == selected[0].checksum_sha256


def test_ingestion_rejects_source_changed_after_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    path = source / "layout.jpg"
    Image.new("RGB", (32, 24), (255, 0, 0)).save(path, "JPEG")
    artifact_root = tmp_path / "artifacts"
    job = _job(source)
    store = ManagedOriginalStore(artifact_root)
    store.load_or_create_manifest(job, source_directory=source)
    Image.new("RGB", (32, 24), (0, 255, 0)).save(path, "JPEG")

    with pytest.raises(JobHandlerError) as caught:
        ImageSourceIngestionHandler(store)(RecordingContext(), job)  # type: ignore[arg-type]

    assert caught.value.code == "IMAGE_SOURCE_CHANGED"


def test_seq_filenames_are_attested_and_sorted_by_numeric_range(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "seq_10-18.jpg", "JPEG")
    Image.new("RGB", (32, 24), (0, 255, 0)).save(source / "seq_1-9.jpg", "JPEG")

    manifest = ManagedOriginalStore(tmp_path / "artifacts").load_or_create_manifest(
        _job(source),
        source_directory=source,
    )

    assert [
        (item.sequence_range_start, item.sequence_range_end) for item in manifest.originals
    ] == [(1, 9), (10, 18)]
    assert all(item.sequence_range_source == "filename" for item in manifest.originals)


def test_seq_filenames_reject_invalid_or_overlapping_ranges(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "seq_1-9.jpg", "JPEG")
    Image.new("RGB", (32, 24), (0, 255, 0)).save(source / "seq_9-17.jpg", "JPEG")

    with pytest.raises(JobHandlerError) as caught:
        ManagedOriginalStore(tmp_path / "artifacts").load_or_create_manifest(
            _job(source),
            source_directory=source,
        )

    assert caught.value.code == "IMAGE_SEQUENCE_FILENAME_CONFLICT"


def test_browser_manifest_preserves_seq_name_while_copying_physical_file(
    tmp_path: Path,
) -> None:
    upload_root = tmp_path / "imports"
    selection_service = ImageFolderSelectionService(lambda: None, clock=lambda: NOW)
    browser_service = BrowserImageSelectionService(
        selection_service,
        upload_root,
        max_bytes=1024 * 1024,
        clock=lambda: NOW,
    )
    stream = BytesIO()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(stream, "JPEG")
    content = stream.getvalue()
    upload = browser_service.begin(
        display_name="1-9",
        expected_file_count=1,
        expected_total_bytes=len(content),
    )
    browser_service.upload_file(
        upload.upload_id,
        0,
        relative_path="1-9/seq_1-9.jpg",
        content=content,
    )
    browser_service.finalize(upload.upload_id)
    source = upload.path
    game_id = uuid4()
    job = create_job(
        JobType.IMPORT,
        game_id=game_id,
        input_payload={
            "schema_version": 2,
            "import_kind": "image_directory",
            "source_selection_id": str(upload.upload_id),
            "source_directory": str(source.resolve()),
            "source_display_name": "1-9",
            "pipeline_fingerprint": FINGERPRINT,
        },
        created_at=NOW,
    )

    store = ManagedOriginalStore(tmp_path / "artifacts")
    manifest = store.load_or_create_manifest(job, source_directory=source)

    assert manifest.originals[0].source_relative_path == "1-9/seq_1-9.jpg"
    assert manifest.originals[0].source_storage_relative_path == "00000001.jpg"
    assert manifest.originals[0].sequence_range_start == 1
    assert manifest.originals[0].sequence_range_end == 9
    assert store.ensure_original(manifest, manifest.originals[0]) is True
    managed_path = tmp_path / "artifacts" / manifest.originals[0].managed_relative_path
    assert managed_path.read_bytes() == content


def test_managed_reprocess_clones_manifest_after_original_folder_was_removed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "layout.jpg", "JPEG")
    artifact_root = tmp_path / "artifacts"
    source_job = _job(source)
    store = ManagedOriginalStore(artifact_root)
    ImageSourceIngestionHandler(store)(RecordingContext(), source_job)  # type: ignore[arg-type]
    (source / "layout.jpg").unlink()
    source.rmdir()
    reprocess_job = create_job(
        JobType.IMPORT,
        game_id=source_job.game_id,
        input_payload={
            "schema_version": 4,
            "import_kind": "image_directory",
            "source_directory": str(source),
            "source_display_name": "reprocess",
            "pipeline_fingerprint": "b" * 64,
            "source_pipeline_fingerprint": "c" * 64,
            "managed_source_job_id": str(source_job.id),
            "symbol_model": {},
            "grid_profile": {},
        },
        created_at=NOW,
    )

    manifest = ImageSourceIngestionHandler(store).ingest(  # type: ignore[arg-type]
        RecordingContext(),
        reprocess_job,
    )

    assert len(manifest.originals) == 1
    assert manifest.originals[0].managed_relative_path.startswith("data/originals/")
    assert len(list((artifact_root / "data" / "originals").glob("??/*.jpg"))) == 1


def test_ingestion_rejects_unsupported_image_issue(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    Image.new("RGB", (32, 24), (255, 0, 0)).save(source / "layout.png", "PNG")
    job = _job(source)

    with pytest.raises(JobHandlerError) as caught:
        ImageSourceIngestionHandler(ManagedOriginalStore(tmp_path / "artifacts"))(
            RecordingContext(),  # type: ignore[arg-type]
            job,
        )

    assert caught.value.code == "IMAGE_DISCOVERY_REQUIRES_REVIEW"


def test_curated_ingestion_uses_only_the_pinned_manifest_slice(tmp_path: Path) -> None:
    source = tmp_path / "curated"
    images = source / "images"
    images.mkdir(parents=True)
    run_id = uuid4()
    entries: list[CuratedImageEntry] = []
    for index, color in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
        path = images / f"seq_{index * 9 + 1}-{index * 9 + 9}.jpg"
        Image.new("RGB", (32, 24), color).save(path, "JPEG")
        content = path.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        entries.append(
            CuratedImageEntry(
                group_order=index,
                range_start=index * 9 + 1,
                range_end=index * 9 + 9,
                source_order_index=index * 10,
                source_relative_path=f"raw/{index}.jpg",
                source_checksum_sha256=checksum,
                output_relative_path=f"images/{path.name}",
                output_checksum_sha256=checksum,
                size_bytes=len(content),
                width=32,
                height=24,
                quality_metrics={},
                reason_codes=("test",),
                selection_method="automatic",
            )
        )
    curated = CuratedImageManifest(
        run_id=run_id,
        input_manifest_sha256="b" * 64,
        selector_version="test-selector",
        selector_fingerprint="c" * 64,
        entries=tuple(entries),
    )
    (source / OUTPUT_MANIFEST_FILE).write_bytes(curated.canonical_bytes)
    job = create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 3,
            "import_kind": "image_directory",
            "source_selection_id": str(uuid4()),
            "source_directory": str(source.resolve()),
            "source_display_name": "curated test",
            "pipeline_fingerprint": FINGERPRINT,
            "source_pipeline_fingerprint": "d" * 64,
            "image_selection_run_id": str(run_id),
            "curated_image_import_source_id": str(uuid4()),
            "curated_image_import_batch_id": str(uuid4()),
            "curated_manifest_relative_path": "data/exports/test/manifest.json",
            "curated_manifest_checksum_sha256": curated.checksum_sha256,
            "curated_manifest_entry_start": 1,
            "curated_manifest_entry_count": 2,
            "symbol_model": {},
            "grid_profile": {},
        },
        created_at=NOW,
    )

    manifest = ManagedOriginalStore(tmp_path / "artifacts").load_or_create_manifest(
        job,
        source_directory=source,
    )

    assert [item.source_relative_path for item in manifest.originals] == [
        "images/seq_10-18.jpg",
        "images/seq_19-27.jpg",
    ]
