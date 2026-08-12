from datetime import UTC, datetime
from uuid import uuid4

import pytest
from game_predictor_api.domain.iterative_image_imports import (
    IterativeImageImportConflictError,
    batch_allows_following_reservation,
    create_curated_source,
    reserve_source_entries,
)
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job

NOW = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)


def _job():
    return create_job(
        JobType.IMPORT,
        game_id=uuid4(),
        input_payload={
            "schema_version": 3,
            "import_kind": "image_directory",
        },
        created_at=NOW,
    )


def test_reservations_are_contiguous_and_final_batch_is_bounded() -> None:
    source = create_curated_source(
        game_id=uuid4(),
        image_selection_run_id=uuid4(),
        manifest_relative_path="data/exports/run/manifest.json",
        manifest_checksum_sha256="a" * 64,
        total_entries=25,
        created_at=NOW,
    )
    first_source, first = reserve_source_entries(
        source,
        requested_count=10,
        batch_number=1,
        batch_id=uuid4(),
        job=_job(),
        created_at=NOW,
    )
    final_source, second = reserve_source_entries(
        first_source,
        requested_count=20,
        batch_number=2,
        batch_id=uuid4(),
        job=_job(),
        created_at=NOW,
    )

    assert (first.start_index, first.end_index) == (0, 10)
    assert (second.start_index, second.end_index) == (10, 25)
    assert final_source.next_entry_index == 25
    with pytest.raises(IterativeImageImportConflictError) as caught:
        reserve_source_entries(
            final_source,
            requested_count=1,
            batch_number=3,
            batch_id=uuid4(),
            job=_job(),
            created_at=NOW,
        )
    assert caught.value.code == "CURATED_IMAGE_IMPORT_COMPLETE"


def test_only_completed_pipeline_allows_the_next_reservation() -> None:
    source = create_curated_source(
        game_id=uuid4(),
        image_selection_run_id=uuid4(),
        manifest_relative_path="data/exports/run/manifest.json",
        manifest_checksum_sha256="a" * 64,
        total_entries=10,
        created_at=NOW,
    )
    _updated, batch = reserve_source_entries(
        source,
        requested_count=5,
        batch_number=1,
        batch_id=uuid4(),
        job=_job(),
        created_at=NOW,
    )

    assert not batch_allows_following_reservation(batch)
    assert batch.job.status is JobStatus.CREATED
