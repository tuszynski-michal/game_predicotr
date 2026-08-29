from pathlib import Path
from uuid import uuid4

import pytest
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.storage_gc import (
    MAX_BATCH_BYTES,
    _batch_end,
    _deleted_marker,
    _safe_root_path,
    _trash_path,
    _validate_managed_candidate_path,
    _write_deleted_marker,
)


def test_gc_batches_are_bounded_by_paths_and_bytes() -> None:
    entries = tuple({"sizeBytes": MAX_BATCH_BYTES // 2 + 1} for _ in range(3))

    assert _batch_end(entries, 0) == 1
    assert _batch_end(tuple({"sizeBytes": 1} for _ in range(300)), 0) == 250


@pytest.mark.parametrize(
    ("root_kind", "artifact_class", "relative_path"),
    [
        ("artifact", "normalization_working_bitmap", "data/originals/secret.jpg"),
        ("artifact", "temporary_file", "data/models/.tmp-model"),
        ("import", "browser_staging", "browser-selections/not-a-uuid"),
        (
            "artifact",
            "browser_staging",
            "browser-selections/00000000-0000-0000-0000-000000000000",
        ),
    ],
)
def test_gc_rejects_paths_outside_disposable_namespaces(
    root_kind: str, artifact_class: str, relative_path: str
) -> None:
    with pytest.raises(JobHandlerError) as error:
        _validate_managed_candidate_path(
            root_kind=root_kind,
            artifact_class=artifact_class,
            relative_path=relative_path,
        )
    assert error.value.code == "STORAGE_GC_PATH_UNSAFE"


def test_gc_trash_path_is_deterministic_and_inside_same_root(tmp_path: Path) -> None:
    run_id = uuid4()

    first = _trash_path(tmp_path, run_id, 3, "data/working/a/file.part")
    second = _trash_path(tmp_path, run_id, 3, "data/working/a/file.part")

    assert first == second
    assert first.is_relative_to(tmp_path)
    assert str(run_id) in first.parts

    marker = _deleted_marker(first)
    marker.parent.mkdir(parents=True)
    _write_deleted_marker(marker, 123)
    assert marker.read_text(encoding="ascii") == "123"


def test_safe_root_path_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(JobHandlerError) as error:
        _safe_root_path(tmp_path, "../outside")
    assert error.value.code == "STORAGE_GC_PATH_UNSAFE"
