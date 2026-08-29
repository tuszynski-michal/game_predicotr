from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.pipeline_state_compaction import (
    PipelineStateCompactionHandler,
    _manifest_entries,
)


def _handler(root: Path) -> PipelineStateCompactionHandler:
    return PipelineStateCompactionHandler(cast(Any, object()), root, cast(Any, object()))


def test_pipeline_compaction_manifest_path_stays_in_managed_exports(tmp_path: Path) -> None:
    relative = "data/exports/storage-gc/pipeline-state/run/manifest.jsonl"
    job = create_job(
        JobType.STORAGE_PIPELINE_COMPACTION,
        game_id=None,
        input_payload={"schema_version": 1, "manifest_relative_path": relative},
    )

    assert _handler(tmp_path)._manifest_path(job) == tmp_path / Path(relative)  # noqa: SLF001


@pytest.mark.parametrize(
    "relative",
    (
        "../manifest.jsonl",
        "data/originals/manifest.jsonl",
        "data/exports/storage-gc/pipeline-state/run/other.jsonl",
    ),
)
def test_pipeline_compaction_rejects_unsafe_manifest_paths(
    tmp_path: Path, relative: str
) -> None:
    job = create_job(
        JobType.STORAGE_PIPELINE_COMPACTION,
        game_id=None,
        input_payload={"schema_version": 1, "manifest_relative_path": relative},
    )

    with pytest.raises(JobHandlerError) as error:
        _handler(tmp_path)._manifest_path(job)  # noqa: SLF001
    assert error.value.code == "STORAGE_PIPELINE_COMPACTION_PATH_UNSAFE"


def test_pipeline_compaction_rejects_invalid_manifest_header(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text('{"schemaVersion":"wrong"}\n', encoding="utf-8")

    with pytest.raises(JobHandlerError) as error:
        _manifest_entries(manifest)
    assert error.value.code == "STORAGE_PIPELINE_COMPACTION_SOURCE_CHANGED"
