from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.verified_training_cohorts import (
    VerifiedTrainingCohortArtifactStore,
    VerifiedTrainingCohortRepository,
    VerifiedTrainingCohortService,
    VerifiedTrainingCohortSourceRepository,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_reviews import (
    ImageReviewAlternative,
    ImageReviewCell,
    ImageReviewConflictError,
    ImageReviewItem,
    canonical_image_review_bytes,
)
from game_predictor_api.domain.verified_training_cohorts import (
    CumulativeVerifiedTrainingSnapshot,
    VerifiedTrainingCohort,
    VerifiedTrainingCohortSnapshot,
    VerifiedTrainingCohortSource,
    VerifiedTrainingReviewState,
    build_model_quality_summary,
    build_verified_training_cohort_source,
    require_pending_model_prediction_target,
)
from game_predictor_api.main import create_app


def test_v2_quality_delta_uses_persisted_cell_sample_checksums() -> None:
    game_id = uuid4()
    cell = {
        "cellReviewId": str(uuid4()),
        "cropChecksumSha256": "a" * 64,
        "symbolCode": "lemon",
    }
    source = VerifiedTrainingCohortSource(
        game_id=game_id,
        manifest={"cells": [cell]},
        manifest_bytes=b"{}\n",
        manifest_checksum_sha256=hashlib.sha256(b"{}\n").hexdigest(),
        boards=(),
        resolved_layout_count=1,
        cell_sample_count=1,
        source_image_count=1,
        pending_item_count=0,
        rejected_item_count=0,
        incomplete_item_count=0,
        warnings=(),
        dataset_kind="verified-symbol-cell-training-cohort-v2",
        manifest_schema_version=2,
        cells=(cell,),
    )
    cohort = VerifiedTrainingCohort(
        id=uuid4(),
        game_id=game_id,
        iteration_number=1,
        manifest_schema_version=2,
        manifest_checksum_sha256=source.manifest_checksum_sha256,
        resolved_layout_count=1,
        cell_sample_count=1,
        source_image_count=1,
        pending_item_count=0,
        rejected_item_count=0,
        incomplete_item_count=0,
        artifact_relative_path="training/cohort.json",
        created_by="owner",
        created_at=datetime.now(UTC),
    )
    checksum = hashlib.sha256(canonical_image_review_bytes(cell)).hexdigest()

    summary = build_model_quality_summary(
        source=source,
        active_symbol_codes=("lemon",),
        latest_snapshot=VerifiedTrainingCohortSnapshot(
            cohort=cohort,
            item_checksums=frozenset({checksum}),
        ),
        active_heavy_job=False,
    )

    assert summary.new_verified_layout_count == 0
    assert summary.symbol_coverage[0].sample_count == 1


class MemorySourceRepository(VerifiedTrainingCohortSourceRepository):
    def __init__(self, game_id: UUID, items: Sequence[ImageReviewItem]) -> None:
        self.game_id = game_id
        self.items = list(items)
        self.heavy_job_active = False
        self.read_snapshot_count = 0
        self.lock_snapshot_count = 0

    def active_symbol_codes(self, game_id: UUID) -> Sequence[str]:
        if game_id != self.game_id:
            raise ImageReviewConflictError("GAME_NOT_FOUND", "Unknown game.")
        return ("lemon", "seven")

    def has_active_heavy_job(self, *, game_id: UUID) -> bool:
        if game_id != self.game_id:
            raise ImageReviewConflictError("GAME_NOT_FOUND", "Unknown game.")
        return self.heavy_job_active

    def lock_cumulative_verified_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> CumulativeVerifiedTrainingSnapshot:
        self.lock_snapshot_count += 1
        if game_id != self.game_id:
            raise ImageReviewConflictError("GAME_NOT_FOUND", "Unknown game.")
        return CumulativeVerifiedTrainingSnapshot(
            review_states=tuple(_review_state(item) for item in self.items),
            resolved_items=tuple(
                item for item in self.items if item.status in {"accepted", "corrected"}
            ),
        )

    def cumulative_verified_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> CumulativeVerifiedTrainingSnapshot:
        self.read_snapshot_count += 1
        if game_id != self.game_id:
            raise ImageReviewConflictError("GAME_NOT_FOUND", "Unknown game.")
        return CumulativeVerifiedTrainingSnapshot(
            review_states=tuple(_review_state(item) for item in self.items),
            resolved_items=tuple(
                item for item in self.items if item.status in {"accepted", "corrected"}
            ),
        )

    def lock_model_prediction_target(
        self,
        *,
        review_item_id: UUID,
        expected_resolution_revision: int,
        expected_geometry_revision: int,
    ) -> None:
        item = next(value for value in self.items if value.id == review_item_id)
        require_pending_model_prediction_target(
            status=item.status,
            resolution_revision=item.resolution_revision,
            expected_resolution_revision=expected_resolution_revision,
            geometry_revision=item.geometry_revision,
            expected_geometry_revision=expected_geometry_revision,
        )


class MemoryCohortRepository(VerifiedTrainingCohortRepository):
    def __init__(self) -> None:
        self.values: list[tuple[VerifiedTrainingCohort, str, UUID]] = []
        self.item_checksums: dict[UUID, frozenset[str]] = {}

    def latest_snapshot(
        self,
        *,
        game_id: UUID,
    ) -> VerifiedTrainingCohortSnapshot | None:
        values = [cohort for cohort, _command, _key in self.values if cohort.game_id == game_id]
        if not values:
            return None
        latest = max(values, key=lambda cohort: cohort.iteration_number)
        return VerifiedTrainingCohortSnapshot(
            cohort=latest,
            item_checksums=self.item_checksums[latest.id],
        )

    def find_by_idempotency(
        self,
        *,
        game_id: UUID,
        idempotency_key: UUID,
    ) -> tuple[VerifiedTrainingCohort, str] | None:
        return next(
            (
                (cohort, command)
                for cohort, command, key in self.values
                if cohort.game_id == game_id and key == idempotency_key
            ),
            None,
        )

    def find_by_manifest(
        self,
        *,
        game_id: UUID,
        manifest_checksum_sha256: str,
    ) -> VerifiedTrainingCohort | None:
        return next(
            (
                cohort
                for cohort, _command, _key in self.values
                if cohort.game_id == game_id
                and cohort.manifest_checksum_sha256 == manifest_checksum_sha256
            ),
            None,
        )

    def next_iteration(self, *, game_id: UUID) -> int:
        return (
            max(
                (
                    cohort.iteration_number
                    for cohort, _command, _key in self.values
                    if cohort.game_id == game_id
                ),
                default=0,
            )
            + 1
        )

    def save(
        self,
        *,
        source: VerifiedTrainingCohortSource,
        iteration_number: int,
        idempotency_key: UUID,
        command_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> VerifiedTrainingCohort:
        cohort = VerifiedTrainingCohort(
            id=uuid4(),
            game_id=source.game_id,
            iteration_number=iteration_number,
            manifest_schema_version=1,
            manifest_checksum_sha256=source.manifest_checksum_sha256,
            resolved_layout_count=source.resolved_layout_count,
            cell_sample_count=source.cell_sample_count,
            source_image_count=source.source_image_count,
            pending_item_count=source.pending_item_count,
            rejected_item_count=source.rejected_item_count,
            incomplete_item_count=source.incomplete_item_count,
            artifact_relative_path=artifact_relative_path,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.values.append((cohort, command_sha256, idempotency_key))
        self.item_checksums[cohort.id] = frozenset(
            hashlib.sha256(
                json.dumps(
                    dict(board),
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode("utf-8")
            ).hexdigest()
            for board in source.boards
        )
        return cohort


def _item(
    game_id: UUID,
    *,
    sequence_number: int,
    status: str = "accepted",
    symbol_code: str = "lemon",
) -> ImageReviewItem:
    item_id = uuid4()
    board_id = uuid4()
    cells = tuple(
        ImageReviewCell(
            observation_id=uuid4(),
            cell_index=index,
            row_index=index // 5,
            column_index=index % 5,
            crop_sample_id=hashlib.sha256(f"{item_id}:{index}:sample".encode()).hexdigest(),
            crop_relative_path=f"crops/{item_id}/{index}.png",
            crop_checksum_sha256=hashlib.sha256(f"{item_id}:{index}:bytes".encode()).hexdigest(),
            predicted_symbol_code="lemon",
            confidence=0.9,
            alternatives=(ImageReviewAlternative(symbol_code="lemon", confidence=0.9),),
            current_symbol_code=symbol_code,
        )
        for index in range(15)
    )
    resolved_at = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    resolved = {
        "action": status,
        "sequenceNumber": sequence_number,
        "geometryRevision": 0,
        "symbolCodes": [symbol_code] * 15,
        "cells": [
            {
                "cellIndex": cell.cell_index,
                "cropSampleId": cell.crop_sample_id,
                "symbolCode": symbol_code,
            }
            for cell in cells
        ],
    }
    return ImageReviewItem(
        id=item_id,
        game_id=game_id,
        import_job_id=uuid4(),
        source_image_id=uuid4(),
        recognized_board_id=board_id,
        status=status,
        source_order_index=sequence_number,
        position_index=(sequence_number - 1) % 9,
        queue_sequence_number=sequence_number,
        suggested_sequence_number=sequence_number,
        source_relative_path=f"sources/{item_id}.jpg",
        source_checksum_sha256="2" * 64,
        board_relative_path=f"boards/{item_id}.png",
        board_checksum_sha256="3" * 64,
        geometry_revision=0,
        geometry={"corners": [[0, 0], [500, 0], [500, 300], [0, 300]]},
        pipeline_fingerprint="4" * 64,
        cells=cells,
        resolved_value=resolved,
        resolved_by="owner",
        resolved_at=resolved_at,
        resolution_revision=1,
        created_at=resolved_at,
    )


def _review_state(item: ImageReviewItem) -> VerifiedTrainingReviewState:
    return VerifiedTrainingReviewState(
        game_id=item.game_id,
        review_item_id=item.id,
        recognized_board_id=item.recognized_board_id,
        source_image_id=item.source_image_id,
        import_job_id=item.import_job_id,
        source_order_index=item.source_order_index,
        position_index=item.position_index,
        status=item.status,
        resolution_revision=item.resolution_revision,
        geometry_revision=item.geometry_revision,
        source_checksum_sha256=item.source_checksum_sha256,
        board_checksum_sha256=item.board_checksum_sha256,
        pipeline_fingerprint=item.pipeline_fingerprint,
    )


def _service(
    tmp_path: Path,
) -> tuple[
    VerifiedTrainingCohortService,
    MemorySourceRepository,
    MemoryCohortRepository,
    UUID,
]:
    game_id = uuid4()
    accepted = _item(game_id, sequence_number=1)
    corrected = _item(game_id, sequence_number=2, status="corrected")
    pending = replace(
        _item(game_id, sequence_number=3),
        status="pending",
        queue_sequence_number=None,
        resolved_value=None,
        resolved_by=None,
        resolved_at=None,
        resolution_revision=0,
    )
    rejected = replace(
        _item(game_id, sequence_number=4),
        status="rejected",
        queue_sequence_number=None,
        resolved_value={"action": "rejected", "geometryRevision": 0, "reason": "blur"},
    )
    stale = _item(game_id, sequence_number=5)
    stale = replace(stale, cells=stale.cells[:-1])
    source = MemorySourceRepository(game_id, [accepted, corrected, pending, rejected, stale])
    cohorts = MemoryCohortRepository()
    return (
        VerifiedTrainingCohortService(
            source,
            cohorts,
            VerifiedTrainingCohortArtifactStore(tmp_path),
        ),
        source,
        cohorts,
        game_id,
    )


def test_preview_uses_only_complete_human_verified_items(tmp_path: Path) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)

    preview = service.preview(game_id=game_id)

    assert preview.resolved_layout_count == 2
    assert preview.cell_sample_count == 30
    assert preview.source_image_count == 2
    assert preview.pending_item_count == 1
    assert preview.rejected_item_count == 1
    assert preview.incomplete_item_count == 1
    assert "INCOMPLETE_HUMAN_DECISIONS_EXCLUDED" in preview.warnings
    assert {board["decisionStatus"] for board in preview.boards} == {
        "accepted",
        "corrected",
    }
    assert all(len(board["cells"]) == 15 for board in preview.boards)
    assert source.read_snapshot_count == 1
    assert source.lock_snapshot_count == 0


def test_compact_read_snapshot_preserves_full_manifest_and_checksum(tmp_path: Path) -> None:
    _service_value, source, _cohorts, game_id = _service(tmp_path)
    full = build_verified_training_cohort_source(game_id=game_id, items=source.items)
    compact = source.cumulative_verified_snapshot(game_id=game_id)

    optimized = build_verified_training_cohort_source(
        game_id=game_id,
        items=compact.resolved_items,
        review_states=compact.review_states,
    )

    assert optimized.manifest == full.manifest
    assert optimized.manifest_checksum_sha256 == full.manifest_checksum_sha256


def test_freeze_uses_a_locked_snapshot_after_read_only_preview(tmp_path: Path) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)
    preview = service.preview(game_id=game_id)

    service.freeze(
        game_id=game_id,
        idempotency_key=uuid4(),
        created_by="owner",
        expected_manifest_checksum_sha256=preview.manifest_checksum_sha256,
    )

    assert source.read_snapshot_count == 1
    assert source.lock_snapshot_count == 1


def test_freeze_is_idempotent_and_changed_human_label_creates_next_iteration(
    tmp_path: Path,
) -> None:
    service, source, cohorts, game_id = _service(tmp_path)
    first_preview = service.preview(game_id=game_id)
    first, created = service.freeze(
        game_id=game_id,
        idempotency_key=uuid4(),
        created_by="owner",
        expected_manifest_checksum_sha256=first_preview.manifest_checksum_sha256,
    )
    same, same_created = service.freeze(
        game_id=game_id,
        idempotency_key=uuid4(),
        created_by="owner",
        expected_manifest_checksum_sha256=first_preview.manifest_checksum_sha256,
    )
    artifact = tmp_path / "data" / Path(first.artifact_relative_path)

    assert created is True
    assert same_created is False
    assert same == first
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == first.manifest_checksum_sha256
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["datasetKind"] == "verified-training-cohort-v1"
    assert len(payload["boards"]) == 2

    source.items[0] = _item(game_id, sequence_number=1, symbol_code="seven")
    second_preview = service.preview(game_id=game_id)
    second, second_created = service.freeze(
        game_id=game_id,
        idempotency_key=uuid4(),
        created_by="owner",
        expected_manifest_checksum_sha256=second_preview.manifest_checksum_sha256,
    )
    assert second_created is True
    assert second.iteration_number == 2
    assert second.manifest_checksum_sha256 != first.manifest_checksum_sha256
    assert len(cohorts.values) == 2
    assert artifact.is_file()


@pytest.mark.parametrize("status", ["accepted", "corrected", "rejected"])
def test_automatic_prediction_write_cannot_target_human_resolved_item(
    tmp_path: Path,
    status: str,
) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)
    protected = _item(game_id, sequence_number=20, status=status)
    if status == "rejected":
        protected = replace(
            protected,
            queue_sequence_number=None,
            resolved_value={"action": "rejected", "geometryRevision": 0},
        )
    source.items.append(protected)

    with pytest.raises(
        ImageReviewConflictError,
        match="currently pending",
    ):
        service.authorize_model_prediction_write(
            review_item_id=protected.id,
            expected_resolution_revision=protected.resolution_revision,
            expected_geometry_revision=protected.geometry_revision,
        )


def test_pending_prediction_write_requires_current_revisions(tmp_path: Path) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)
    pending = next(item for item in source.items if item.status == "pending")
    service.authorize_model_prediction_write(
        review_item_id=pending.id,
        expected_resolution_revision=0,
        expected_geometry_revision=0,
    )
    with pytest.raises(ImageReviewConflictError, match="revision changed"):
        service.authorize_model_prediction_write(
            review_item_id=pending.id,
            expected_resolution_revision=1,
            expected_geometry_revision=0,
        )


def test_verified_training_cohort_api_exposes_preview_and_freeze(tmp_path: Path) -> None:
    service, _source, _cohorts, game_id = _service(tmp_path)
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": (
                    "postgresql+psycopg://unused:unused@localhost:5432/unused"
                ),
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
            }
        ),
        verified_training_cohort_service_dependency=lambda: service,
    )
    with TestClient(app) as client:
        quality = client.get(f"/api/v1/admin/games/{game_id}/model-quality")
        preview = client.get(f"/api/v1/admin/games/{game_id}/verified-training-cohorts/preview")
        freeze = client.post(
            f"/api/v1/admin/games/{game_id}/verified-training-cohorts",
            json={
                "idempotencyKey": str(uuid4()),
                "createdBy": "owner",
                "expectedManifestChecksumSha256": preview.json()["manifestChecksumSha256"],
            },
        )

    assert quality.status_code == 200
    assert quality.json()["newVerifiedLayoutCount"] == 2
    assert quality.json()["activeModel"] is None
    assert preview.status_code == 200
    assert preview.json()["resolvedLayoutCount"] == 2
    assert preview.json()["trainingExclusions"] == {
        "changedCrop": 0,
        "gridIssue": 0,
        "missingAsset": 0,
        "unknown": 0,
        "unreadable": 0,
    }
    assert quality.json()["manifestSchemaVersion"] == 1
    assert freeze.status_code == 200
    assert freeze.json()["created"] is True
    assert freeze.json()["cohort"]["iterationNumber"] == 1


def test_model_quality_reports_delta_symbols_thresholds_and_protected_items(
    tmp_path: Path,
) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)

    initial = service.model_quality(game_id=game_id)

    assert initial.active_model_version is None
    assert initial.new_verified_layout_count == 2
    assert initial.protected_item_count == 4
    assert [(item.symbol_code, item.sample_count) for item in initial.symbol_coverage] == [
        ("lemon", 30),
        ("seven", 0),
    ]
    assert [threshold.layout_count for threshold in initial.advisory_thresholds] == [
        100,
        1000,
    ]
    assert initial.can_freeze is True

    service.freeze(
        game_id=game_id,
        idempotency_key=uuid4(),
        created_by="owner",
        expected_manifest_checksum_sha256=initial.manifest_checksum_sha256,
    )
    after_freeze = service.model_quality(game_id=game_id)
    assert after_freeze.new_verified_layout_count == 0
    assert after_freeze.latest_cohort is not None

    source.items[0] = _item(game_id, sequence_number=1, symbol_code="seven")
    changed = service.model_quality(game_id=game_id)
    assert changed.new_verified_layout_count == 1


def test_freeze_rejects_stale_preview_and_active_heavy_job(tmp_path: Path) -> None:
    service, source, _cohorts, game_id = _service(tmp_path)
    preview = service.preview(game_id=game_id)
    source.items[0] = _item(game_id, sequence_number=1, symbol_code="seven")

    with pytest.raises(ImageReviewConflictError, match="changed after the preview"):
        service.freeze(
            game_id=game_id,
            idempotency_key=uuid4(),
            created_by="owner",
            expected_manifest_checksum_sha256=preview.manifest_checksum_sha256,
        )

    current = service.preview(game_id=game_id)
    source.heavy_job_active = True
    with pytest.raises(ImageReviewConflictError, match="heavy operation"):
        service.freeze(
            game_id=game_id,
            idempotency_key=uuid4(),
            created_by="owner",
            expected_manifest_checksum_sha256=current.manifest_checksum_sha256,
        )
