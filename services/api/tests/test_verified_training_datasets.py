from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from game_predictor_api.application import verified_training_datasets as module
from game_predictor_api.application.verified_training_datasets import (
    TrainingDatasetCatalog,
    VerifiedTrainingDatasetService,
)
from game_predictor_api.domain.verified_training_cohorts import VerifiedTrainingCohort
from game_predictor_worker.symbols import (
    TrainingDatasetArtifact,
    TrainingDatasetBuildError,
    TrainingSymbol,
)


class MemoryCohorts:
    def __init__(self, cohort: VerifiedTrainingCohort | None) -> None:
        self.cohort = cohort

    def get(self, *, cohort_id: UUID) -> VerifiedTrainingCohort | None:
        if self.cohort is None or self.cohort.id != cohort_id:
            return None
        return self.cohort


class MemoryCatalogs:
    def __init__(self, catalog: TrainingDatasetCatalog | None) -> None:
        self.catalog = catalog

    def get(self, *, game_id: UUID) -> TrainingDatasetCatalog | None:
        return self.catalog


def _cohort(*, artifact_relative_path: str = "training/game/cohort.json") -> VerifiedTrainingCohort:
    return VerifiedTrainingCohort(
        id=uuid4(),
        game_id=uuid4(),
        iteration_number=1,
        manifest_schema_version=1,
        manifest_checksum_sha256="a" * 64,
        resolved_layout_count=1,
        cell_sample_count=15,
        source_image_count=1,
        pending_item_count=0,
        rejected_item_count=0,
        incomplete_item_count=0,
        artifact_relative_path=artifact_relative_path,
        created_by="owner",
        created_at=datetime(2026, 8, 8, tzinfo=UTC),
    )


def test_service_resolves_persisted_cohort_and_active_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _cohort()
    catalog = TrainingDatasetCatalog(
        game_code="fixture-game",
        symbols=(TrainingSymbol(id="symbol-a", code="A"),),
    )
    captured: dict[str, Any] = {}

    def fake_build(**kwargs: object) -> TrainingDatasetArtifact:
        captured.update(kwargs)
        return TrainingDatasetArtifact(
            game_id=str(cohort.game_id),
            cohort_checksum_sha256=cohort.manifest_checksum_sha256,
            manifest_checksum_sha256="b" * 64,
            manifest_relative_path="training/fixture/manifest.json",
            sample_count=15,
            source_family_count=1,
            reused=False,
            manifest={"status": "ready"},
        )

    monkeypatch.setattr(module, "build_cumulative_training_dataset", fake_build)
    result = VerifiedTrainingDatasetService(
        MemoryCohorts(cohort),
        MemoryCatalogs(catalog),
        artifact_root=tmp_path,
    ).build(cohort_id=cohort.id)

    assert result.sample_count == 15
    assert captured["cohort_path"] == (tmp_path / "data" / "training" / "game" / "cohort.json")
    assert captured["expected_cohort_checksum_sha256"] == "a" * 64
    assert captured["game_code"] == "fixture-game"
    assert captured["symbols"] == catalog.symbols
    assert captured["expected_game_id"] == str(cohort.game_id)


def test_service_rejects_missing_or_unsafe_persisted_cohort(tmp_path: Path) -> None:
    missing_id = uuid4()
    service = VerifiedTrainingDatasetService(
        MemoryCohorts(None),
        MemoryCatalogs(None),
        artifact_root=tmp_path,
    )
    with pytest.raises(TrainingDatasetBuildError) as missing:
        service.build(cohort_id=missing_id)
    assert missing.value.code == "TRAINING_DATASET_COHORT_NOT_FOUND"

    unsafe = _cohort(artifact_relative_path="../outside.json")
    service = VerifiedTrainingDatasetService(
        MemoryCohorts(unsafe),
        MemoryCatalogs(
            TrainingDatasetCatalog(
                game_code="fixture-game",
                symbols=(TrainingSymbol(id="symbol-a", code="A"),),
            )
        ),
        artifact_root=tmp_path,
    )
    with pytest.raises(TrainingDatasetBuildError) as invalid:
        service.build(cohort_id=unsafe.id)
    assert invalid.value.code == "TRAINING_DATASET_COHORT_PATH_UNSAFE"
