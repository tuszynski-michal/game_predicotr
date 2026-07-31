from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_api.domain.jobs import JobType, create_job
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
    assert checkpoint["contractVersion"] == SOURCE_INGESTION_CONTRACT

    (source / "a.jpg").unlink()
    (source / "b.jpeg").unlink()
    source.rmdir()
    resumed = RecordingContext()

    handler(resumed, job)  # type: ignore[arg-type]

    assert resumed.checkpoints[-1]["current"] == 1
    assert len(list((artifact_root / "data" / "originals").glob("??/*.jpg"))) == 1


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
