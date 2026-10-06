from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    SourceLatticeNodes,
    SourcePoint,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.schemas.source_lattice_geometry import lattice_nodes_payload
from game_predictor_api.storage.virtual_grid_geometry_repository import _revision_from_model
from test_virtual_grid_geometry import _corners, _fixture


def _lattice() -> SourceLatticeNodes:
    points = [
        SourcePoint(5 + 109 * column / 5, 5 + 69 * row / 3)
        for row in range(4)
        for column in range(6)
    ]
    points[8] = SourcePoint(points[8].x + 1.125, points[8].y + 0.325)
    return SourceLatticeNodes(tuple(points))


def _command(context, lattice):
    return dict(
        game_id=context.game_id,
        import_job_id=context.import_job_id,
        review_item_id=context.review_item_id,
        expected_geometry_revision=0,
        expected_resolution_revision=0,
        expected_source_checksum_sha256=context.source_checksum_sha256,
        expected_source_width=context.oriented_width,
        expected_source_height=context.oriented_height,
        expected_grid_rows=3,
        expected_grid_columns=5,
        corners=_corners(),
        lattice_nodes=lattice,
    )


def test_exact_interior_node_controls_all_four_adjacent_cells(tmp_path):
    service, context = _fixture(tmp_path)
    lattice = _lattice()
    preview = service.preview(**_command(context, lattice))
    assert len(preview.cells) == 15
    for cell in preview.cells:
        assert (
            cell.render_spec["sourceQuad"]
            == lattice.cell_quad(
                topology=BoardTopology(3, 5),
                row_index=cell.row_index,
                column_index=cell.column_index,
            ).to_dict()
        )
    assert lattice.cell_quad(topology=BoardTopology(3, 5), row_index=0, column_index=1) != (
        lattice.outer_quad.cell_quad(topology=BoardTopology(3, 5), row_index=0, column_index=1)
    )


def test_lattice_save_read_and_lost_reply_preserve_exact_nodes(tmp_path):
    service, context = _fixture(tmp_path)
    command = _command(context, _lattice())
    key = uuid4()
    service.save(**command, idempotency_key=key, actor="operator", created_at=datetime.now(UTC))
    prepared = service._repository.saved[0]
    assert prepared.board_geometries[0]["latticeNodes"] == command["lattice_nodes"].to_dict()
    assert prepared.board_geometry["latticeNodes"] == command["lattice_nodes"].to_dict()
    record = SimpleNamespace(
        id=uuid4(),
        review_item_id=context.review_item_id,
        recognized_board_id=context.recognized_board_id,
        revision=1,
        idempotency_key=key,
        command_sha256=prepared.command.command_sha256,
        corners=[point.to_dict() for point in command["lattice_nodes"].outer_quad.corners],
        asset_mode="virtual_source",
        source_geometry_revision_id=context.source_geometry_revision_id,
        geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
        virtual_render_spec_checksum_sha256=prepared.virtual_render_spec_checksum_sha256,
        virtual_render_spec=prepared.virtual_render_spec,
        geometry=prepared.board_geometry,
        cropper_version=prepared.cropper_version,
        corrected_by="operator",
        created_at=datetime.now(UTC),
    )
    # Corners use the compatible integer transport; full nodes remain floats.
    record.corners = [{"x": p.x, "y": p.y} for p in _corners()]
    read = _revision_from_model(record)
    assert read.lattice_nodes == command["lattice_nodes"]
    service._repository.replays[(context.target_id, key)] = read
    replay = service.save(
        **command, idempotency_key=key, actor="operator", created_at=datetime.now(UTC)
    )
    assert not replay.created
    assert replay.revision.lattice_nodes == read.lattice_nodes
    assert len(service._repository.saved) == 1
    changed = list(command["lattice_nodes"].nodes)
    changed[8] = SourcePoint(changed[8].x + 0.01, changed[8].y)
    with pytest.raises(ImageGridReviewError, match="another command"):
        service.save(
            **{**command, "lattice_nodes": SourceLatticeNodes(tuple(changed))},
            idempotency_key=key,
            actor="operator",
            created_at=datetime.now(UTC),
        )


def test_stale_proposal_pin_rejects_before_render(tmp_path):
    service, context = _fixture(tmp_path)
    with pytest.raises(ImageGridReviewError) as caught:
        service.preview(**_command(context, _lattice()), expected_proposal_checksum_sha256="a" * 64)
    assert caught.value.code == "IMAGE_GRID_REVIEW_PROPOSAL_STALE"
    assert not service._repository.saved


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), True])
def test_nonfinite_lattice_nodes_are_rejected(bad):
    with pytest.raises(ImageGeometryContractError):
        SourcePoint(bad, 1)


@pytest.mark.parametrize("bad", [True, "1.125", float("nan"), float("inf")])
def test_lattice_dto_does_not_coerce_non_numeric_json(bad):
    nodes = _lattice().to_dict()
    nodes[0]["x"] = bad
    with pytest.raises(ValueError):
        lattice_nodes_payload(nodes)


def test_lattice_fold_is_rejected():
    points = list(_lattice().nodes)
    points[8] = points[7]
    with pytest.raises(ImageGeometryContractError):
        SourceLatticeNodes(tuple(points))


def test_partial_lattice_keeps_visible_pixels_but_emits_no_outside_crop(tmp_path):
    service, context = _fixture(tmp_path)
    lattice = SourceLatticeNodes(
        tuple(SourcePoint(point.x - 30, point.y) for point in _lattice().nodes)
    )
    command = _command(context, lattice)
    command["geometry_qualification"] = GeometryQualification(
        "pending_partial",
        (0, 1, 5, 6, 10, 11),
        True,
        "missing_pixels",
    )
    preview = service.preview(**command)
    assert [cell.cell_index for cell in preview.cells] == [
        index for index in range(15) if index not in {0, 5, 10}
    ]
    assert preview.contact_sheet_png.startswith(b"\x89PNG")
    service.save(
        **command,
        idempotency_key=uuid4(),
        actor="operator",
        created_at=datetime.now(UTC),
    )
    prepared = service._repository.saved[0]
    assert prepared.board_geometry["geometryQualification"]["unavailableCellIndices"] == [
        0,
        1,
        5,
        6,
        10,
        11,
    ]
    assert len(prepared.cells) == 12


@pytest.mark.parametrize("tamper", ["point", "remove_render_nodes", "remove_geometry_nodes"])
def test_persisted_lattice_render_checksum_tampering_fails_closed(tmp_path, tamper):
    service, context = _fixture(tmp_path)
    service.save(
        **_command(context, _lattice()),
        idempotency_key=uuid4(),
        actor="operator",
        created_at=datetime.now(UTC),
    )
    prepared = service._repository.saved[0]
    record = SimpleNamespace(
        asset_mode="virtual_source",
        source_geometry_revision_id=context.source_geometry_revision_id,
        geometry_checksum_sha256=prepared.source_geometry_checksum_sha256,
        virtual_render_spec_checksum_sha256=prepared.virtual_render_spec_checksum_sha256,
        virtual_render_spec=prepared.virtual_render_spec,
        geometry=prepared.board_geometry,
    )
    if tamper == "point":
        record.virtual_render_spec["latticeNodes"][8]["x"] += 0.125
    elif tamper == "remove_render_nodes":
        record.virtual_render_spec.pop("latticeNodes")
    else:
        record.geometry.pop("latticeNodes")
    with pytest.raises(ImageGridReviewError) as caught:
        _revision_from_model(record)
    assert caught.value.code == "IMAGE_GRID_REVIEW_VIRTUAL_REVISION_INVALID"
