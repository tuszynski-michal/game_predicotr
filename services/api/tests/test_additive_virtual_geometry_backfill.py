from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from uuid import UUID

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.schemas.jobs import ImageGeometryRolloutBackfillJobPayload
from game_predictor_api.storage.image_geometry_rollout_backfill_repository import (
    ImageGeometryRolloutBackfillError,
    SqlAlchemyImageGeometryRolloutBackfillRepository,
)
from game_predictor_api.storage.models import VerifiedTrainingCohortCellModel
from sqlalchemy.orm import Session

GAME_ID = UUID("40000000-0000-0000-0000-000000000001")
SOURCE_ID = UUID("40000000-0000-0000-0000-000000000002")
IMPORT_ID = UUID("40000000-0000-0000-0000-000000000003")
RULES_ID = UUID("40000000-0000-0000-0000-000000000004")
SYMBOL_ID = UUID("40000000-0000-0000-0000-000000000005")


def _job_payload(schema_version: int) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "workflow": "image_geometry_rollout_backfill",
        "generation": 1,
        "rollout_revision": 1,
        "geometry_mode": "structured_review",
        "cell_asset_mode": "virtual_source",
    }
    if schema_version == 3:
        payload["contract_backfill_version"] = "additive-virtual-geometry-v2-backfill-v1"
    return payload


@pytest.mark.parametrize("schema_version", [1, 2, 3])
def test_rollout_job_payload_preserves_all_replayable_schema_versions(
    schema_version: int,
) -> None:
    parsed = ImageGeometryRolloutBackfillJobPayload.model_validate(_job_payload(schema_version))

    assert parsed.schema_version == schema_version


def test_rollout_job_payload_requires_contract_version_for_schema_v3() -> None:
    payload = _job_payload(3)
    payload.pop("contract_backfill_version")

    with pytest.raises(ValueError, match="requires contractBackfillVersion"):
        ImageGeometryRolloutBackfillJobPayload.model_validate(payload)


@pytest.mark.parametrize("limit", [0, 101])
def test_contract_backfill_rejects_batches_outside_the_bounded_limit(limit: int) -> None:
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(cast(Session, object()))

    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        repository.validate_next_batch(GAME_ID, limit=limit)


def _source() -> SimpleNamespace:
    return SimpleNamespace(
        id=SOURCE_ID,
        import_job_id=IMPORT_ID,
        file_execution_key="1" * 64,
    )


def _geometry() -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("40000000-0000-0000-0000-000000000006"),
        game_id=GAME_ID,
        source_image_id=SOURCE_ID,
        topology_rules_version_id=RULES_ID,
        sequence_range_start=10,
        sequence_range_end=18,
        active_board_slots=list(range(9)),
        topology_fingerprint_sha256=None,
        sequence_attestation_schema_version=None,
        sequence_attestation_checksum_sha256=None,
    )


def _render_spec() -> dict[str, object]:
    return {
        "boardSlot": 0,
        "cellIndex": 0,
        "columnIndex": 0,
        "configuration": {
            "extractorVersion": "virtual-cell-extractor-v1",
            "interpolation": "linear",
            "outputHeight": 96,
            "outputWidth": 96,
            "paddingFraction": 0.05,
            "preprocessingVersion": "rgb-v1",
        },
        "geometryFingerprintSha256": "2" * 64,
        "rowIndex": 0,
        "sourceQuad": [
            {"x": 0.0, "y": 0.0},
            {"x": 10.0, "y": 0.0},
            {"x": 10.0, "y": 10.0},
            {"x": 0.0, "y": 10.0},
        ],
    }


def test_render_identity_backfill_is_idempotent_and_conflicts_fail_closed() -> None:
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(cast(Session, object()))
    cell = SimpleNamespace(
        cell_index=0,
        row_index=0,
        column_index=0,
        render_spec=_render_spec(),
        logical_cell_key_v2=None,
        render_identity_v2_sha256=None,
    )

    first = repository._backfill_render_identity(
        source=_source(),
        geometry=_geometry(),
        topology=BoardTopology(rows=3, columns=5),
        board=SimpleNamespace(position_index=0),
        cell=cell,
    )
    second = repository._backfill_render_identity(
        source=_source(),
        geometry=_geometry(),
        topology=BoardTopology(rows=3, columns=5),
        board=SimpleNamespace(position_index=0),
        cell=cell,
    )

    assert first == 1
    assert second == 0
    assert len(cell.logical_cell_key_v2) == 64
    assert len(cell.render_identity_v2_sha256) == 64

    cell.logical_cell_key_v2 = "f" * 64
    with pytest.raises(ImageGeometryRolloutBackfillError) as raised:
        repository._backfill_render_identity(
            source=_source(),
            geometry=_geometry(),
            topology=BoardTopology(rows=3, columns=5),
            board=SimpleNamespace(position_index=0),
            cell=cell,
        )
    assert raised.value.code == "IMAGE_V2_RENDER_IDENTITY_PERSISTENCE_MISMATCH"


def test_frozen_training_cell_uses_its_explicit_historical_coordinates() -> None:
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(cast(Session, object()))
    cell = VerifiedTrainingCohortCellModel(
        cell_index=0,
        render_spec=_render_spec(),
        logical_cell_key_v2=None,
        render_identity_v2_sha256=None,
    )

    updated = repository._backfill_render_identity(
        source=_source(),
        geometry=_geometry(),
        topology=BoardTopology(rows=3, columns=5),
        board=SimpleNamespace(position_index=0),
        cell=cell,
        row_index=0,
        column_index=0,
    )

    assert updated == 1
    assert len(cell.logical_cell_key_v2 or "") == 64
    assert len(cell.render_identity_v2_sha256 or "") == 64


class _RowsSession:
    def __init__(self, rows: list[object]) -> None:
        self.rows = rows

    def scalars(self, _statement: object) -> list[object]:
        return self.rows


class _GeometrySession(_RowsSession):
    def scalar(self, _statement: object) -> object:
        return SimpleNamespace(id=RULES_ID, game_id=GAME_ID, rows=3, columns=5)


def test_source_contract_backfill_is_additive_and_exact() -> None:
    geometry = _geometry()
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(
        cast(Session, _GeometrySession([geometry]))
    )

    assert repository._backfill_source_revisions(game_id=GAME_ID, source=_source()) == 1
    assert repository._backfill_source_revisions(game_id=GAME_ID, source=_source()) == 0
    assert len(geometry.topology_fingerprint_sha256) == 64
    assert geometry.sequence_attestation_schema_version == "source-sequence-attestation-v2"
    assert len(geometry.sequence_attestation_checksum_sha256) == 64

    geometry.topology_fingerprint_sha256 = "f" * 64
    with pytest.raises(ImageGeometryRolloutBackfillError) as raised:
        repository._backfill_source_revisions(game_id=GAME_ID, source=_source())
    assert raised.value.code == "IMAGE_GEOMETRY_ROLLOUT_SOURCE_CONTRACT_V2_MISMATCH"


def test_review_outcome_backfill_never_promotes_a_model_suggestion() -> None:
    cell = SimpleNamespace(
        review_state="pending",
        quality_issue=None,
        assigned_symbol_id=SYMBOL_ID,
        prediction_symbol_code="cherry",
        assignment_source="model",
        verification_outcome=None,
        verified_symbol_id_v2=None,
    )
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(
        cast(Session, _RowsSession([cell]))
    )

    assert repository._backfill_review_outcomes_for_source(source=_source()) == 1
    assert cell.verification_outcome == "requires_review"
    assert cell.verified_symbol_id_v2 is None


def test_ambiguous_review_outcome_blocks_the_source_without_mutation() -> None:
    cell = SimpleNamespace(
        review_state="approved",
        quality_issue=None,
        assigned_symbol_id=None,
        prediction_symbol_code=None,
        assignment_source="human",
        verification_outcome=None,
        verified_symbol_id_v2=None,
    )
    repository = SqlAlchemyImageGeometryRolloutBackfillRepository(
        cast(Session, _RowsSession([cell]))
    )

    with pytest.raises(ImageGeometryRolloutBackfillError) as raised:
        repository._backfill_review_outcomes_for_source(source=_source())

    assert raised.value.code == "SYMBOL_VERIFICATION_LEGACY_APPROVED_NULL_AMBIGUOUS"
    assert cell.verification_outcome is None
    assert cell.verified_symbol_id_v2 is None
