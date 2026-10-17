"""Pure completion extraction must preserve the worker's guarded write boundary."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain.source_canonical_metadata import SourceCanonicalMetadata
from game_predictor_worker.images import pipeline_store
from game_predictor_worker.images.pipeline_execution import StoredImageStageResult


def candidate(*, lease=True):
    return SimpleNamespace(
        job_id=uuid4(),
        lease_token=uuid4() if lease else None,
        executed_at=datetime.now(UTC),
        execution=SimpleNamespace(file_execution_key="own-execution"),
    )


def normalization(*, canonical=True):
    payload = {"sourceWidth": 40, "sourceHeight": 30, "width": 40, "height": 30}
    if canonical:
        payload["normalizedPixelChecksumSha256"] = "a" * 64
    return StoredImageStageResult(
        adapter_version="image-normalization-v2-in-memory-source-v1", payload=payload
    )


def session_factory():
    session = MagicMock()
    session.__enter__.return_value = session
    return session, lambda: session


EXPECTED = SourceCanonicalMetadata(
    raw_width=40,
    raw_height=30,
    oriented_width=40,
    oriented_height=30,
    exif_orientation=None,
    coordinate_space="exif-normalized-rgb-pixels-v1",
    normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    normalized_pixel_checksum_sha256="a" * 64,
).to_dict()


@pytest.mark.parametrize("initial", ["all_null", "complete_no_exif", "conflict"])
def test_projection_keeps_completion_equality_conflict_and_lease_order(monkeypatch, initial):
    current = SourceCanonicalMetadata().to_dict() if initial == "all_null" else dict(EXPECTED)
    if initial == "conflict":
        current["raw_width"] = 99
    source = SimpleNamespace(**current)
    events = []
    session, factory = session_factory()

    def require_lease(*args, **kwargs):
        events.append("lease")

    def locked_source(*args, **kwargs):
        assert events == ["lease"]
        events.append("source")
        return source

    monkeypatch.setattr(pipeline_store, "_require_candidate_lease", require_lease)
    monkeypatch.setattr(pipeline_store, "_locked_source", locked_source)
    store = pipeline_store.SqlAlchemyImagePipelineStore(factory)
    if initial == "conflict":
        with pytest.raises(pipeline_store.ImagePipelineStoreError) as failure:
            store.project_source_metadata(candidate(), normalization=normalization())
        assert failure.value.code == "IMAGE_SOURCE_COORDINATE_METADATA_CONFLICT"
        assert vars(source) == current
    else:
        store.project_source_metadata(candidate(), normalization=normalization())
        assert vars(source) == EXPECTED
    assert events == ["lease", "source"]
    session.begin.assert_called_once()


def test_missing_execution_lease_is_rejected_before_opening_session():
    factory = MagicMock()
    store = pipeline_store.SqlAlchemyImagePipelineStore(factory)
    with pytest.raises(pipeline_store.ImagePipelineStoreError) as failure:
        store.project_source_metadata(candidate(lease=False), normalization=normalization())
    assert failure.value.code == "IMAGE_PIPELINE_EXECUTION_CONTEXT_MISSING"
    factory.assert_not_called()


def test_actual_job_lease_guard_runs_before_source_access(monkeypatch):
    session, factory = session_factory()
    session.get.return_value = None
    source_lock = MagicMock(side_effect=AssertionError("Source reached before job lease"))
    monkeypatch.setattr(pipeline_store, "_locked_source", source_lock)
    with pytest.raises(pipeline_store.ImagePipelineStoreError) as failure:
        pipeline_store.SqlAlchemyImagePipelineStore(factory).project_source_metadata(
            candidate(), normalization=normalization()
        )
    assert failure.value.code == "IMAGE_PIPELINE_JOB_NOT_FOUND"
    source_lock.assert_not_called()


def test_legacy_normalization_payload_still_does_not_start_metadata_projection():
    factory = MagicMock()
    pipeline_store.SqlAlchemyImagePipelineStore(factory).project_source_metadata(
        candidate(lease=False), normalization=normalization(canonical=False)
    )
    factory.assert_not_called()
