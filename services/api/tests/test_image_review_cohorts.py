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
from game_predictor_api.application.image_review_cohorts import (
    VerifiedCohortArtifactStore,
    VerifiedCohortExportRepository,
    VerifiedCohortService,
    VerifiedCohortSourceRepository,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_review_cohorts import (
    ImageVerifiedCohortExport,
    VerifiedCohortSource,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewAlternative,
    ImageReviewCell,
    ImageReviewConflictError,
    ImageReviewCounts,
    ImageReviewItem,
)
from game_predictor_api.main import create_app


class MemorySourceRepository(VerifiedCohortSourceRepository):
    def __init__(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        items: Sequence[ImageReviewItem],
        counts: ImageReviewCounts,
    ) -> None:
        self.game_id = game_id
        self.import_job_id = import_job_id
        self.items = list(items)
        self.counts = counts

    def lock_verified_snapshot(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
    ) -> tuple[Sequence[ImageReviewItem], ImageReviewCounts]:
        if game_id != self.game_id or import_job_id != self.import_job_id:
            raise ImageReviewConflictError(
                "IMAGE_REVIEW_CONTEXT_INVALID",
                "Unknown review context.",
            )
        return tuple(self.items), self.counts


class MemoryExportRepository(VerifiedCohortExportRepository):
    def __init__(self) -> None:
        self.values: list[ImageVerifiedCohortExport] = []

    def find_by_state(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        input_state_sha256: str,
    ) -> ImageVerifiedCohortExport | None:
        return next(
            (
                value
                for value in self.values
                if value.game_id == game_id
                and value.import_job_id == import_job_id
                and value.input_state_sha256 == input_state_sha256
            ),
            None,
        )

    def next_version(self, *, game_id: UUID, import_job_id: UUID) -> int:
        return (
            max(
                (
                    value.version
                    for value in self.values
                    if value.game_id == game_id and value.import_job_id == import_job_id
                ),
                default=0,
            )
            + 1
        )

    def save(
        self,
        *,
        source: VerifiedCohortSource,
        version: int,
        payload_sha256: str,
        artifact_relative_path: str,
        created_by: str,
    ) -> ImageVerifiedCohortExport:
        value = ImageVerifiedCohortExport(
            id=uuid4(),
            game_id=source.game_id,
            import_job_id=source.import_job_id,
            version=version,
            input_state_sha256=source.input_state_sha256,
            payload_sha256=payload_sha256,
            artifact_relative_path=artifact_relative_path,
            board_count=source.board_count,
            sample_count=source.sample_count,
            pending_item_count=source.pending_item_count,
            rejected_item_count=source.rejected_item_count,
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.values.append(value)
        return value

    def list(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        limit: int,
    ) -> Sequence[ImageVerifiedCohortExport]:
        return tuple(
            sorted(
                (
                    value
                    for value in self.values
                    if value.game_id == game_id and value.import_job_id == import_job_id
                ),
                key=lambda value: value.version,
                reverse=True,
            )[:limit]
        )


def _verified_item(
    game_id: UUID,
    import_job_id: UUID,
    *,
    sequence_number: int,
    status: str = "accepted",
    symbol_code: str = "lemon",
    resolution_revision: int = 1,
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
            confidence=0.91,
            alternatives=(
                ImageReviewAlternative(symbol_code="lemon", confidence=0.91),
                ImageReviewAlternative(symbol_code="seven", confidence=0.09),
            ),
            current_symbol_code=symbol_code,
        )
        for index in range(15)
    )
    resolved_at = datetime(2026, 7, 29, 12, sequence_number, tzinfo=UTC)
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
        import_job_id=import_job_id,
        source_image_id=uuid4(),
        recognized_board_id=board_id,
        status=status,
        source_order_index=sequence_number - 1,
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
        resolution_revision=resolution_revision,
        created_at=resolved_at,
    )


def _service(
    tmp_path: Path,
) -> tuple[VerifiedCohortService, MemorySourceRepository, MemoryExportRepository, UUID, UUID]:
    game_id = uuid4()
    import_job_id = uuid4()
    pending = [
        replace(
            _verified_item(game_id, import_job_id, sequence_number=20 + index),
            status="pending",
            queue_sequence_number=None,
            resolved_value=None,
            resolved_by=None,
            resolved_at=None,
            resolution_revision=0,
        )
        for index in range(7)
    ]
    rejected = [
        replace(
            _verified_item(game_id, import_job_id, sequence_number=40 + index),
            status="rejected",
            queue_sequence_number=None,
            resolved_value={
                "action": "rejected",
                "geometryRevision": 0,
                "reason": "unusable",
            },
        )
        for index in range(3)
    ]
    source = MemorySourceRepository(
        game_id=game_id,
        import_job_id=import_job_id,
        items=[
            _verified_item(game_id, import_job_id, sequence_number=2, status="corrected"),
            _verified_item(game_id, import_job_id, sequence_number=1),
            *pending,
            *rejected,
        ],
        counts=ImageReviewCounts(pending=7, accepted=1, corrected=1, rejected=3),
    )
    exports = MemoryExportRepository()
    return (
        VerifiedCohortService(
            source,
            exports,
            VerifiedCohortArtifactStore(tmp_path),
        ),
        source,
        exports,
        game_id,
        import_job_id,
    )


def test_freeze_is_checksum_bound_complete_and_idempotent(tmp_path: Path) -> None:
    service, _source, exports, game_id, import_job_id = _service(tmp_path)

    first, first_created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by=" owner ",
    )
    second, second_created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by="another retry actor",
    )

    assert first_created is True
    assert second_created is False
    assert second == first
    assert len(exports.values) == 1
    assert first.board_count == 2
    assert first.sample_count == 30
    assert first.pending_item_count == 7
    assert first.rejected_item_count == 3
    assert not Path(first.artifact_relative_path).is_absolute()
    artifact = tmp_path / "data" / Path(first.artifact_relative_path)
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    assert payload["datasetKind"] == "verified-image-review-cohort-v1"
    assert [board["sequenceNumber"] for board in payload["boards"]] == [1, 2]
    assert all(len(board["cells"]) == 15 for board in payload["boards"])
    assert all(
        cell["symbolCode"] == "lemon" for board in payload["boards"] for cell in board["cells"]
    )
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == first.payload_sha256


def test_changed_human_revision_creates_new_version_without_mutating_prior(
    tmp_path: Path,
) -> None:
    service, source, exports, game_id, import_job_id = _service(tmp_path)
    first, _created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by="owner",
    )
    first_bytes = (tmp_path / "data" / Path(first.artifact_relative_path)).read_bytes()
    changed = _verified_item(
        game_id,
        import_job_id,
        sequence_number=2,
        status="corrected",
        symbol_code="seven",
        resolution_revision=2,
    )
    source.items[0] = changed

    second, created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by="owner",
    )

    assert created is True
    assert second.version == 2
    assert second.input_state_sha256 != first.input_state_sha256
    assert second.payload_sha256 != first.payload_sha256
    assert len(exports.values) == 2
    assert (tmp_path / "data" / Path(first.artifact_relative_path)).read_bytes() == first_bytes


def test_rejected_decision_changes_state_without_adding_samples(tmp_path: Path) -> None:
    service, source, _exports, game_id, import_job_id = _service(tmp_path)
    first, _created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by="owner",
    )
    pending_index = next(
        index for index, item in enumerate(source.items) if item.status == "pending"
    )
    pending = source.items[pending_index]
    source.items[pending_index] = replace(
        pending,
        status="rejected",
        resolved_value={
            "action": "rejected",
            "geometryRevision": pending.geometry_revision,
            "reason": "unusable",
        },
        resolved_by="owner",
        resolved_at=datetime.now(UTC),
        resolution_revision=1,
    )
    source.counts = ImageReviewCounts(pending=6, accepted=1, corrected=1, rejected=4)

    second, created = service.freeze(
        game_id=game_id,
        import_job_id=import_job_id,
        created_by="owner",
    )

    assert created is True
    assert second.version == 2
    assert second.input_state_sha256 != first.input_state_sha256
    assert second.sample_count == first.sample_count == 30
    assert second.rejected_item_count == 4


def test_freeze_rejects_empty_or_stale_human_labels(tmp_path: Path) -> None:
    service, source, _exports, game_id, import_job_id = _service(tmp_path)
    source.items = []
    source.counts = ImageReviewCounts(pending=0, accepted=0, corrected=0, rejected=0)
    with pytest.raises(ImageReviewConflictError, match="At least one"):
        service.freeze(
            game_id=game_id,
            import_job_id=import_job_id,
            created_by="owner",
        )

    stale = _verified_item(game_id, import_job_id, sequence_number=1)
    stale_cells = list(stale.cells)
    stale_cells[0] = replace(stale_cells[0], crop_sample_id="f" * 64)
    source.items = [replace(stale, cells=tuple(stale_cells))]
    source.counts = ImageReviewCounts(pending=0, accepted=1, corrected=0, rejected=0)
    with pytest.raises(ImageReviewConflictError, match="immutable crop"):
        service.freeze(
            game_id=game_id,
            import_job_id=import_job_id,
            created_by="owner",
        )


def test_verified_cohort_api_freezes_and_lists_versions(tmp_path: Path) -> None:
    service, _source, _exports, game_id, import_job_id = _service(tmp_path)
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": "postgresql+psycopg://unused:unused@localhost:5432/unused",
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path),
            }
        ),
        image_review_cohort_service_dependency=lambda: service,
    )
    with TestClient(app) as client:
        freeze = client.post(
            "/api/v1/admin/image-review-cohort-exports",
            params={"gameId": str(game_id), "importJobId": str(import_job_id)},
            json={"createdBy": "owner"},
        )
        listed = client.get(
            "/api/v1/admin/image-review-cohort-exports",
            params={"gameId": str(game_id), "importJobId": str(import_job_id)},
        )

    assert freeze.status_code == 200
    assert freeze.json()["created"] is True
    assert freeze.json()["export"]["boardCount"] == 2
    assert listed.status_code == 200
    assert [value["version"] for value in listed.json()] == [1]
