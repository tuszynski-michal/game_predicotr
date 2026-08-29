from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_api.application.image_storage import (
    MANAGED_STORAGE_NAMESPACES,
    ImageStorageNamespace,
    ImageStorageVolume,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.jobs.runtime import JobHandlerError
from game_predictor_worker.storage_inventory import StorageInventoryHandler

NOW = datetime(2026, 8, 29, 12, tzinfo=UTC)


class _Session:
    def scalar(self, _statement: object) -> int:
        return 123

    def execute(self, _statement: object) -> None:
        return None

    def add(self, _model: object) -> None:
        return None

    def __enter__(self) -> "_Session":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _SessionFactory:
    def __call__(self) -> _Session:
        return _Session()

    @contextmanager
    def begin(self):  # type: ignore[no-untyped-def]
        yield _Session()


class _Store:
    def __init__(self) -> None:
        self.scanned: list[str] = []

    def volumes(self) -> tuple[ImageStorageVolume, ...]:
        return (ImageStorageVolume("c:", ("artifacts", "imports"), 10_000, 5_000),)

    def namespace_inventory(self, name: str) -> ImageStorageNamespace:
        self.scanned.append(name)
        return ImageStorageNamespace(name, "preserve", True, True, 1, 10, 0)


class _Context:
    def __init__(self, *, stop_after_first: bool = False) -> None:
        self.stop_after_first = stop_after_first
        self.checkpoints: list[dict[str, object]] = []

    def now(self) -> datetime:
        return NOW

    def checkpoint(self, **values: object) -> None:
        self.checkpoints.append(values)
        if self.stop_after_first and len(self.checkpoints) == 1:
            raise RuntimeError("simulated worker stop")


def _job():  # type: ignore[no-untyped-def]
    return create_job(
        JobType.STORAGE_INVENTORY,
        game_id=None,
        input_payload={"schema_version": 1, "inventory_kind": "managed_image_storage"},
        created_at=NOW,
    )


def test_inventory_resumes_after_last_persisted_namespace(tmp_path: Path) -> None:
    handler = StorageInventoryHandler(
        cast(Any, _SessionFactory()), tmp_path / "artifacts", tmp_path / "imports"
    )
    store = _Store()
    handler._store = cast(Any, store)  # noqa: SLF001
    handler._save_namespace = cast(Any, lambda item, **_kwargs: None)  # noqa: SLF001
    first_context = _Context(stop_after_first=True)

    with pytest.raises(RuntimeError, match="simulated worker stop"):
        handler(cast(Any, first_context), _job())

    checkpoint = first_context.checkpoints[-1]["checkpoint_payload"]
    assert checkpoint["schema_version"] == 1
    assert store.scanned == [MANAGED_STORAGE_NAMESPACES[0]]
    resumed = replace(_job(), checkpoint_payload=cast(dict[str, object], checkpoint))
    second_context = _Context()
    handler(cast(Any, second_context), resumed)

    assert store.scanned == list(MANAGED_STORAGE_NAMESPACES)
    assert second_context.checkpoints[-1]["stage"] == "storage_inventory_completed"
    assert second_context.checkpoints[-1]["current"] == len(MANAGED_STORAGE_NAMESPACES) + 1


def test_inventory_rejects_out_of_range_checkpoint(tmp_path: Path) -> None:
    handler = StorageInventoryHandler(
        cast(Any, _SessionFactory()), tmp_path / "artifacts", tmp_path / "imports"
    )
    handler._store = cast(Any, _Store())  # noqa: SLF001
    job = replace(
        _job(),
        checkpoint_payload={
            "checkpoint_kind": "storage-inventory-v2",
            "measured_at": NOW.isoformat(),
            "next_namespace_index": len(MANAGED_STORAGE_NAMESPACES) + 1,
            "schema_version": 1,
        },
    )

    with pytest.raises(JobHandlerError) as error:
        handler(cast(Any, _Context()), job)

    assert error.value.code == "STORAGE_INVENTORY_CHECKPOINT_INVALID"
