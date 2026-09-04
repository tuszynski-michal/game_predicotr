from __future__ import annotations

import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    approve_symbol_cell_review,
    map_current_symbol_cell_reviews,
)
from game_predictor_api.storage.image_review_repository import (
    _current_board_identity_checksum,
    _item_from_records,
    materialize_current_image_review_cells,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    _apply_symbol_cell_review_transition,
    _asset_provenance_values,
)
from game_predictor_api.storage.models import ImageSymbolReviewCellModel


def _sha(seed: int) -> str:
    return f"{seed:064x}"


def _virtual_observations(board_id: UUID, source_geometry_revision_id: UUID):
    observations = []
    for cell_index in range(15):
        render_spec = {
            "cellIndex": cell_index,
            "columnIndex": cell_index % 5,
            "rowIndex": cell_index // 5,
            "schemaVersion": "virtual-cell-render-spec-v1",
        }
        render_spec_checksum = hashlib.sha256(canonical_json_bytes(render_spec)).hexdigest()
        observations.append(
            SimpleNamespace(
                id=uuid4(),
                row_index=cell_index // 5,
                column_index=cell_index % 5,
                asset_mode="virtual_source",
                crop_relative_path=None,
                crop_checksum_sha256=_sha(1_000 + cell_index),
                cropper_version="structured-board-cells-v0.10",
                source_geometry_revision_id=source_geometry_revision_id,
                logical_cell_key=_sha(2_000 + cell_index),
                logical_cell_key_v2=_sha(3_000 + cell_index),
                render_identity_v2_sha256=_sha(4_000 + cell_index),
                render_spec=render_spec,
                render_spec_checksum_sha256=render_spec_checksum,
                rendered_pixel_checksum_sha256=_sha(1_000 + cell_index),
                extractor_version="direct-perspective-cell-v2",
                prediction={
                    "symbolCode": "cherry",
                    "confidence": 0.9,
                    "alternatives": [{"symbolCode": "cherry", "confidence": 0.9}],
                },
            )
        )
    return tuple(observations)


def test_virtual_source_materializer_keeps_current_render_provenance() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    observations = _virtual_observations(board_id, source_geometry_revision_id)

    cells = materialize_current_image_review_cells(
        item=SimpleNamespace(resolved_value=None),
        board=SimpleNamespace(
            id=board_id,
            asset_mode="virtual_source",
            grid_rows=3,
            grid_columns=5,
            geometry_revision=0,
        ),
        source=SimpleNamespace(),
        queue_item=SimpleNamespace(),
        job=SimpleNamespace(),
        observations=observations,
        geometry_revision=None,
    )

    assert len(cells) == 15
    assert all(cell.asset_mode == "virtual_source" for cell in cells)
    assert all(cell.crop_relative_path is None for cell in cells)
    assert all(cell.source_geometry_revision_id == source_geometry_revision_id for cell in cells)
    assert _asset_provenance_values(cells[0]) == {
        "asset_mode": "virtual_source",
        "source_geometry_revision_id": source_geometry_revision_id,
        "logical_cell_key": _sha(2_000),
        "logical_cell_key_v2": _sha(3_000),
        "render_identity_v2_sha256": _sha(4_000),
        "render_spec": {
            "cellIndex": 0,
            "columnIndex": 0,
            "rowIndex": 0,
            "schemaVersion": "virtual-cell-render-spec-v1",
        },
        "render_spec_checksum_sha256": hashlib.sha256(
            canonical_json_bytes(
                {
                    "cellIndex": 0,
                    "columnIndex": 0,
                    "rowIndex": 0,
                    "schemaVersion": "virtual-cell-render-spec-v1",
                }
            )
        ).hexdigest(),
        "rendered_pixel_checksum_sha256": _sha(1_000),
        "extractor_version": "direct-perspective-cell-v2",
    }


def test_operational_item_uses_complete_manual_virtual_geometry_revision() -> None:
    board_id = uuid4()
    game_id = uuid4()
    import_job_id = uuid4()
    source_geometry_revision_id = uuid4()
    observations = _virtual_observations(board_id, source_geometry_revision_id)
    revision_cells = []
    for cell_index, observation in enumerate(observations):
        revision_cells.append(
            {
                "cellIndex": cell_index,
                "cropSampleId": _sha(5_000 + cell_index),
                "logicalCellKeySha256": _sha(6_000 + cell_index),
                "logicalCellKeyV2Sha256": _sha(7_000 + cell_index),
                "renderIdentityV2Sha256": _sha(8_000 + cell_index),
                "renderSpec": observation.render_spec,
                "renderSpecChecksumSha256": observation.render_spec_checksum_sha256,
                "renderedPixelChecksumSha256": _sha(9_000 + cell_index),
            }
        )
    item_id = uuid4()
    source_id = uuid4()
    item = _item_from_records(
        SimpleNamespace(
            id=item_id,
            status="pending",
            resolved_value=None,
            resolved_by=None,
            resolved_at=None,
            resolution_revision=0,
            created_at=None,
        ),
        SimpleNamespace(
            id=board_id,
            asset_mode="virtual_source",
            grid_rows=3,
            grid_columns=5,
            geometry_revision=1,
            sequence_number=42,
            board_geometry={"displayAssetKind": "source_context"},
            pipeline_fingerprint=_sha(10_000),
        ),
        SimpleNamespace(
            id=source_id,
            import_job_id=import_job_id,
            relative_path="originals/source.jpg",
            checksum_sha256=_sha(10_001),
        ),
        SimpleNamespace(source_order_index=3, position_index=2),
        SimpleNamespace(game_id=game_id),
        observations,
        SimpleNamespace(
            revision=1,
            asset_mode="virtual_source",
            source_geometry_revision_id=source_geometry_revision_id,
            virtual_render_spec={"cells": revision_cells},
            cropper_version="structured-board-cells-v0.10-manual",
        ),
    )

    assert item.id == item_id
    assert item.board_relative_path == "originals/source.jpg"
    assert item.board_checksum_sha256 == _sha(10_001)
    assert len(item.cells) == 15
    assert [cell.crop_sample_id for cell in item.cells] == [
        _sha(5_000 + index) for index in range(15)
    ]
    assert all(cell.asset_mode == "virtual_source" for cell in item.cells)


def test_virtual_board_identity_uses_geometry_checksum() -> None:
    assert (
        _current_board_identity_checksum(
            SimpleNamespace(
                asset_mode="virtual_source",
                geometry_checksum_sha256=_sha(11_000),
                board_checksum_sha256=None,
            )
        )
        == _sha(11_000)
    )


def test_approving_virtual_source_cell_persists_approved_render_provenance() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    cell = materialize_current_image_review_cells(
        item=SimpleNamespace(resolved_value=None),
        board=SimpleNamespace(
            id=board_id,
            asset_mode="virtual_source",
            grid_rows=3,
            grid_columns=5,
            geometry_revision=0,
        ),
        source=SimpleNamespace(),
        queue_item=SimpleNamespace(),
        job=SimpleNamespace(),
        observations=_virtual_observations(board_id, source_geometry_revision_id),
        geometry_revision=None,
    )[0]
    review = map_current_symbol_cell_reviews(
        cells=(
            *materialize_current_image_review_cells(
                item=SimpleNamespace(resolved_value=None),
                board=SimpleNamespace(
                    id=board_id,
                    asset_mode="virtual_source",
                    grid_rows=3,
                    grid_columns=5,
                    geometry_revision=0,
                ),
                source=SimpleNamespace(),
                queue_item=SimpleNamespace(),
                job=SimpleNamespace(),
                observations=_virtual_observations(board_id, source_geometry_revision_id),
                geometry_revision=None,
            ),
        ),
        geometry_revision=0,
        cropper_version="structured-board-cells-v0.10",
        assignment_source=SymbolCellAssignmentSource.MODEL,
    )[0]
    approved = approve_symbol_cell_review(review, active_symbol_codes=("cherry",)).review
    model = ImageSymbolReviewCellModel(
        asset_mode="virtual_source",
        source_geometry_revision_id=cell.source_geometry_revision_id,
        render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
        rendered_pixel_checksum_sha256=cell.rendered_pixel_checksum_sha256,
    )

    _apply_symbol_cell_review_transition(
        model,
        review=approved,
        symbol_id_by_code={"cherry": uuid4()},
        actor="test",
    )

    assert model.approved_asset_mode == "virtual_source"
    assert model.approved_source_geometry_revision_id == source_geometry_revision_id
    assert model.approved_render_spec_checksum_sha256 == cell.render_spec_checksum_sha256
    assert model.approved_rendered_pixel_checksum_sha256 == cell.rendered_pixel_checksum_sha256
