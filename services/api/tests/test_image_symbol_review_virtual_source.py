from __future__ import annotations

import dataclasses
import hashlib
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.board_render_manifests import (
    ObservedRenderCell,
    build_observation_render_manifest,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellAssignmentSource,
    approve_symbol_cell_review,
    map_current_symbol_cell_reviews,
)
from game_predictor_api.storage.board_render_manifest_reader import (
    CurrentBoardRenderManifest,
    current_render_manifest_from_record,
)
from game_predictor_api.storage.current_board_cell_sources import CurrentBoardCellSources
from game_predictor_api.storage.image_review_repository import (
    _current_board_identity_checksum,
    _item_from_records,
    materialize_current_image_review_cells,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewBackfillError,
    _apply_symbol_cell_review_transition,
    _asset_provenance_values,
    _current_cropper_version,
    _geometry_review_event_board_checksum,
)
from game_predictor_api.storage.models import BoardRenderManifestModel, ImageSymbolReviewCellModel


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


def _cells_prediction(observations) -> dict[str, object]:
    """D-467: one import prediction per imported cell, beside the manifest."""

    return {
        "cells": [
            {
                "rowIndex": observation.row_index,
                "columnIndex": observation.column_index,
                **observation.prediction,
            }
            for observation in observations
        ],
        "modelVersion": "test-model",
    }


def _manifest_sources(
    board_id: UUID, observations, source_geometry_revision_id: UUID
) -> CurrentBoardCellSources:
    """The revision-0 manifest the import writer builds from the same cells."""

    manifest = build_observation_render_manifest(
        recognized_board_id=board_id,
        cells=[
            ObservedRenderCell(
                cell_index=observation.row_index * 5 + observation.column_index,
                render_spec=observation.render_spec,
                render_spec_checksum_sha256=observation.render_spec_checksum_sha256,
                rendered_pixel_checksum_sha256=observation.rendered_pixel_checksum_sha256,
                logical_cell_key=observation.logical_cell_key,
                logical_cell_key_v2=observation.logical_cell_key_v2,
                render_identity_v2_sha256=observation.render_identity_v2_sha256,
            )
            for observation in observations
        ],
    )
    record = BoardRenderManifestModel(
        game_id=uuid4(),
        recognized_board_id=board_id,
        geometry_revision=0,
        asset_mode="virtual_source",
        source_geometry_revision_id=source_geometry_revision_id,
        extractor_version="direct-perspective-cell-v2",
        cells=dict(manifest.document),
        manifest_checksum_sha256=manifest.checksum_sha256,
    )
    return CurrentBoardCellSources(render_manifest=current_render_manifest_from_record(record))


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
            cells_prediction=_cells_prediction(observations),
        ),
        source=SimpleNamespace(),
        queue_item=SimpleNamespace(),
        job=SimpleNamespace(),
        cell_sources=_manifest_sources(board_id, observations, source_geometry_revision_id),
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
        # D-467 S7 (TASK-0793): the cell persists only the checksum; the
        # specification stays in the board render manifest.
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


def test_partial_virtual_source_materializes_only_available_cells() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    unavailable = (2, 7, 12, 13, 14)
    observations = tuple(
        value
        for index, value in enumerate(_virtual_observations(board_id, source_geometry_revision_id))
        if index not in unavailable
    )

    cells = materialize_current_image_review_cells(
        item=SimpleNamespace(resolved_value=None),
        board=SimpleNamespace(
            id=board_id,
            asset_mode="virtual_source",
            grid_rows=3,
            grid_columns=5,
            geometry_revision=0,
            completeness_status="pending_partial",
            unavailable_cell_indices=list(unavailable),
            cells_prediction=_cells_prediction(observations),
        ),
        source=SimpleNamespace(),
        queue_item=SimpleNamespace(),
        job=SimpleNamespace(),
        cell_sources=_manifest_sources(board_id, observations, source_geometry_revision_id),
        geometry_revision=None,
    )

    assert [cell.cell_index for cell in cells] == [
        index for index in range(15) if index not in unavailable
    ]


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
            cells_prediction=_cells_prediction(observations),
        ),
        SimpleNamespace(
            id=source_id,
            import_job_id=import_job_id,
            relative_path="originals/source.jpg",
            checksum_sha256=_sha(10_001),
        ),
        SimpleNamespace(source_order_index=3, position_index=2),
        SimpleNamespace(game_id=game_id),
        # The revision > 0 manifest is a verbatim copy of virtual_render_spec.
        CurrentBoardCellSources(
            render_manifest=CurrentBoardRenderManifest(
                recognized_board_id=board_id,
                geometry_revision=1,
                source_geometry_revision_id=source_geometry_revision_id,
                extractor_version="structured-board-cells-v0.10-manual",
                manifest_checksum_sha256=_sha(12_000),
                cells=tuple(revision_cells),
            )
        ),
        None,
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
    assert _current_board_identity_checksum(
        SimpleNamespace(
            asset_mode="virtual_source",
            geometry_checksum_sha256=_sha(11_000),
            board_checksum_sha256=None,
        )
    ) == _sha(11_000)


def test_approving_virtual_source_cell_persists_approved_render_provenance() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    observations = _virtual_observations(board_id, source_geometry_revision_id)
    cell = materialize_current_image_review_cells(
        item=SimpleNamespace(resolved_value=None),
        board=SimpleNamespace(
            id=board_id,
            asset_mode="virtual_source",
            grid_rows=3,
            grid_columns=5,
            geometry_revision=0,
            cells_prediction=_cells_prediction(observations),
        ),
        source=SimpleNamespace(),
        queue_item=SimpleNamespace(),
        job=SimpleNamespace(),
        cell_sources=_manifest_sources(board_id, observations, source_geometry_revision_id),
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
                    cells_prediction=_cells_prediction(observations),
                ),
                source=SimpleNamespace(),
                queue_item=SimpleNamespace(),
                job=SimpleNamespace(),
                cell_sources=_manifest_sources(board_id, observations, source_geometry_revision_id),
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


def test_geometry_approval_event_identifies_virtual_board_by_geometry_checksum() -> None:
    virtual_board = SimpleNamespace(board_checksum_sha256=None, geometry_checksum_sha256=_sha(7))
    crop_board = SimpleNamespace(board_checksum_sha256=_sha(8), geometry_checksum_sha256=None)

    assert _geometry_review_event_board_checksum(virtual_board) == _sha(7)  # type: ignore[arg-type]
    assert _geometry_review_event_board_checksum(crop_board) == _sha(8)  # type: ignore[arg-type]


def _all_outside_board(board_id: UUID, *, geometry_revision: int) -> SimpleNamespace:
    every = tuple(range(15))
    return SimpleNamespace(
        id=board_id,
        asset_mode="virtual_source",
        grid_rows=3,
        grid_columns=5,
        geometry_revision=geometry_revision,
        completeness_status="pending_partial",
        unavailable_cell_indices=list(every),
        geometry_qualification=GeometryQualification(
            "pending_partial",
            every,
            True,
            "missing_pixels",
            version="manual-geometry-qualification-v3",
            fully_unavailable_cell_indices=every,
        ).to_dict(),
        cells_prediction={"cells": [], "modelVersion": "test-model"},
    )


def test_board_without_renderable_cells_has_no_manifest_and_no_cells() -> None:
    """TASK-0757 rule read side: no manifest row <=> no renderable cells."""

    board_id = uuid4()
    for geometry_revision in (0, 1):
        assert (
            materialize_current_image_review_cells(
                item=SimpleNamespace(resolved_value=None),
                board=_all_outside_board(board_id, geometry_revision=geometry_revision),
                source=SimpleNamespace(),
                queue_item=SimpleNamespace(),
                job=SimpleNamespace(),
                cell_sources=CurrentBoardCellSources(),
                geometry_revision=None,
            )
            == ()
        )
    # The revision-0 base cropper of such a board is the fixed placeholder.
    assert (
        _current_cropper_version(
            board=_all_outside_board(board_id, geometry_revision=0),
            cell_sources=CurrentBoardCellSources(),
            geometry=None,
        )
        == "manual-geometry-no-source-cells-v1"
    )


def test_revision_zero_legacy_board_has_no_cell_source_after_s5() -> None:
    """D-467 S5 (TASK-0759): its base crops lived only in the dropped records."""

    board = SimpleNamespace(
        id=uuid4(),
        asset_mode="legacy_file",
        geometry_revision=0,
        geometry_qualification=None,
        completeness_status="complete",
        unavailable_cell_indices=[],
        cells_prediction=_cells_prediction(_virtual_observations(uuid4(), uuid4())),
    )
    with pytest.raises(ImageReviewConflictError) as error:
        materialize_current_image_review_cells(
            item=SimpleNamespace(resolved_value=None),
            board=board,
            source=SimpleNamespace(),
            queue_item=SimpleNamespace(),
            job=SimpleNamespace(),
            cell_sources=CurrentBoardCellSources(),
            geometry_revision=None,
        )
    assert error.value.code == "IMAGE_REVIEW_CELL_COUNT_INVALID"
    with pytest.raises(SymbolCellReviewBackfillError):
        _current_cropper_version(board=board, cell_sources=CurrentBoardCellSources(), geometry=None)


def test_missing_manifest_of_a_board_with_cells_fails_closed() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    observations = _virtual_observations(board_id, source_geometry_revision_id)
    board = SimpleNamespace(
        id=board_id,
        asset_mode="virtual_source",
        grid_rows=3,
        grid_columns=5,
        geometry_revision=0,
        cells_prediction=_cells_prediction(observations),
    )
    with pytest.raises(ImageReviewConflictError) as error:
        materialize_current_image_review_cells(
            item=SimpleNamespace(resolved_value=None),
            board=board,
            source=SimpleNamespace(),
            queue_item=SimpleNamespace(),
            job=SimpleNamespace(),
            cell_sources=CurrentBoardCellSources(),
            geometry_revision=None,
        )
    assert error.value.code == "IMAGE_REVIEW_RENDER_MANIFEST_MISSING"
    with pytest.raises(SymbolCellReviewBackfillError):
        _current_cropper_version(board=board, cell_sources=CurrentBoardCellSources(), geometry=None)
    # With its manifest the base cropper is the manifest extractor.
    assert (
        _current_cropper_version(
            board=board,
            cell_sources=_manifest_sources(board_id, observations, source_geometry_revision_id),
            geometry=None,
        )
        == "direct-perspective-cell-v2"
    )


def test_manifest_of_another_revision_or_cell_set_is_rejected() -> None:
    board_id = uuid4()
    source_geometry_revision_id = uuid4()
    observations = _virtual_observations(board_id, source_geometry_revision_id)
    sources = _manifest_sources(board_id, observations, source_geometry_revision_id)
    assert sources.render_manifest is not None

    def materialize(board: SimpleNamespace, cell_sources: CurrentBoardCellSources) -> object:
        return materialize_current_image_review_cells(
            item=SimpleNamespace(resolved_value=None),
            board=board,
            source=SimpleNamespace(),
            queue_item=SimpleNamespace(),
            job=SimpleNamespace(),
            cell_sources=cell_sources,
            geometry_revision=None,
        )

    stale_revision = SimpleNamespace(
        id=board_id,
        asset_mode="virtual_source",
        grid_rows=3,
        grid_columns=5,
        geometry_revision=1,
        cells_prediction=_cells_prediction(observations),
    )
    with pytest.raises(ImageReviewConflictError) as error:
        materialize(stale_revision, sources)
    assert error.value.code == "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID"
    missing_cell = CurrentBoardCellSources(
        render_manifest=dataclasses.replace(
            sources.render_manifest, cells=sources.render_manifest.cells[1:]
        )
    )
    current = SimpleNamespace(**{**vars(stale_revision), "geometry_revision": 0})
    with pytest.raises(ImageReviewConflictError) as error:
        materialize(current, missing_cell)
    assert error.value.code == "IMAGE_REVIEW_GEOMETRY_PROJECTION_INVALID"
