"""Actual production rendering exposes classifier inset independently of model quality."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import numpy as np
import pytest
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.grid_cell_content import ContentError, ContentRevision, ContentSource
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.grid_visibility_contract import (
    BoardContentReference,
    CellContentReference,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ActiveBoardSlot,
    DirectCellRenderConfiguration,
    GeometryEngineKind,
    NormalizedSourceImage,
    SourceLatticeNodes,
    SourceOccurrence,
    SourcePoint,
    VirtualBoardGeometry,
    derive_virtual_cells,
)
from game_predictor_worker.images.grid_cell_content_reference import (
    content_oracle,
    frozen_content_reference,
)
from game_predictor_worker.images.normalization import (
    CanonicalSourceFrame,
    rgb_pixel_checksum_sha256,
)
from game_predictor_worker.images.virtual_cell_extraction import (
    VIRTUAL_CELL_INTERPOLATION_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
)


def oracle_fixture(inset=0.1, content_inset=5.0, state="visible"):
    pixels = np.arange(200 * 120 * 3, dtype=np.uint8).reshape(120, 200, 3)
    source = NormalizedSourceImage(
        source_checksum_sha256="a" * 64,
        normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(pixels),
        width=200,
        height=120,
        exif_orientation=None,
        normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    )
    frame = CanonicalSourceFrame(
        source=source,
        raw_width=200,
        raw_height=120,
        source_mode="RGB",
        orientation_action="none",
        rgb=pixels,
    )
    nodes = tuple((float(x * 20 + 10), float(y * 20 + 10)) for y in range(4) for x in range(6))
    lattice = SourceLatticeNodes(tuple(SourcePoint(x, y) for x, y in nodes))
    geometry = VirtualBoardGeometry(
        source=source,
        source_occurrence=SourceOccurrence(UUID(int=3), "b" * 64),
        slot=ActiveBoardSlot(1, 1, 0, 1),
        topology=BoardTopology(3, 5),
        topology_rules_version_id=UUID(int=4),
        geometry_revision=7,
        geometry_version="human-content-oracle-v1",
        engine_kind=GeometryEngineKind.MANUAL_V1,
        symbol_grid_quad=lattice.outer_quad,
        lattice_nodes=lattice,
    )
    configuration = DirectCellRenderConfiguration(
        extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version="spatial-symbol-cnn-rgb-input-v1",
        interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
        output_width=64,
        output_height=64,
        padding_fraction=inset,
    )
    cells = derive_virtual_cells(geometry=geometry, configuration=configuration)
    content = []
    for index in range(15):
        y, x = divmod(index, 5)
        left, top = x * 20 + 10 + content_inset, y * 20 + 10 + content_inset
        right, bottom = (x + 1) * 20 + 10 - content_inset, (y + 1) * 20 + 10 - content_inset
        content.append(
            CellContentReference(
                state=state, quad=((left, top), (right, top), (right, bottom), (left, bottom))
            )
        )
    now = datetime(2026, 11, 8, tzinfo=UTC)
    annotation = ContentRevision(
        source=ContentSource(
            sourceId=UUID(int=5),
            sourceSha256="a" * 64,
            sourceRepresentativeSha256=frame.pixel_checksum_sha256,
            width=200,
            height=120,
        ),
        reference=BoardContentReference(
            gameId=UUID(int=6),
            sourceRepresentativeSha256=frame.pixel_checksum_sha256,
            positionIndex=0,
            revision=1,
            humanApproved=True,
            cells=tuple(content),
        ),
        sequenceNumber=1,
        origin="manual",
        actor="local-owner",
        approvedBy="local-owner",
        approvedAt=now,
        recordedAt=now,
    )
    snapshot = {
        "classifierVersion": "frozen-fixture-classifier",
        "renderConfiguration": configuration.to_dict(),
    }
    return frame, cells, annotation, nodes, snapshot


def run_oracle(values):
    frame, cells, annotation, nodes, snapshot = values
    return content_oracle(
        frame,
        cells,
        annotation,
        human_nodes=nodes,
        human_geometry_sha256=digest(list(nodes)),
        classifier_snapshot=snapshot,
        classifier_snapshot_sha256=digest(snapshot),
    )


def test_real_renderer_inset_can_clip_even_perfect_human_geometry():
    okay = run_oracle(oracle_fixture(content_inset=5))
    assert okay["state"] == "checked"
    assert len(okay["cells"]) == 15 and all(c["state"] == "preserved" for c in okay["cells"])
    clipped = run_oracle(oracle_fixture(content_inset=1))
    assert clipped["state"] == "render_contract_blocked"
    assert all(c["state"] == "clipped" and c["renderedPixelSha256"] for c in clipped["cells"])
    # No silent classifier crop change was used to achieve a pass.
    assert clipped["renderConfiguration"]["paddingFraction"] == 0.1


def test_nonvisible_observed_fragment_is_never_full_symbol_preservation():
    for state in ("occluded", "out_of_frame", "unknown"):
        result = run_oracle(oracle_fixture(state=state))
        assert all(c["state"] == "not_evaluable" for c in result["cells"])


def test_oracle_rejects_classifier_drift_and_unapproved_geometry_substitution():
    frame, cells, annotation, nodes, snapshot = oracle_fixture()
    with pytest.raises(ContentError, match="configuration differs"):
        run_oracle((frame, cells, annotation, nodes, {**snapshot, "renderConfiguration": {}}))
    changed = tuple(
        replace(cell, geometry=replace(cell.geometry, lattice_nodes=None)) for cell in cells
    )
    with pytest.raises(ContentError, match="Renderer input differs"):
        run_oracle((frame, changed, annotation, nodes, snapshot))


def test_frozen_reader_has_no_geometry_fallback_and_checks_exact_sha_slot_game():
    _, _, annotation, _, _ = oracle_fixture()
    source = {
        "sourceId": str(annotation.source.sourceId),
        "sourceIdentity": {
            "normalized_pixel_checksum_sha256": annotation.source.sourceRepresentativeSha256,
            "checksum_sha256": annotation.source.sourceSha256,
            "oriented_width": annotation.source.width,
            "oriented_height": annotation.source.height,
            "coordinate_space": annotation.source.coordinateSpace,
            "normalization_adapter_version": annotation.source.normalizationAdapterVersion,
            "exif_orientation": annotation.source.exifOrientation,
        },
    }
    target = {"positionIndex": 0, "sequenceNumber": 1}
    assert frozen_content_reference(annotation.reference.gameId, source, target) is None
    target.update(
        contentAnnotation=annotation.model_dump(mode="json"),
        contentReferenceSha256=annotation.sha256,
        contentReferenceRevision=1,
    )
    assert (
        frozen_content_reference(annotation.reference.gameId, source, target)
        == annotation.reference
    )
    with pytest.raises(ContentError, match="identity differs"):
        frozen_content_reference(UUID(int=99), source, target)
    with pytest.raises(ContentError, match="identity differs"):
        frozen_content_reference(
            annotation.reference.gameId, source, {**target, "contentReferenceRevision": 2}
        )


def test_alias_binding_preserves_original_annotation_and_checks_target_frame():
    from copy import deepcopy

    _, _, annotation, _, _ = oracle_fixture()
    alias = annotation.source.model_copy(
        update={"sourceId": UUID(int=88), "sourceSha256": "c" * 64, "exifOrientation": 1}
    )
    source = {
        "sourceId": str(alias.sourceId),
        "sourceIdentity": {
            "normalized_pixel_checksum_sha256": alias.sourceRepresentativeSha256,
            "checksum_sha256": alias.sourceSha256,
            "oriented_width": alias.width,
            "oriented_height": alias.height,
            "coordinate_space": alias.coordinateSpace,
            "normalization_adapter_version": alias.normalizationAdapterVersion,
            "exif_orientation": alias.exifOrientation,
        },
    }
    target = {
        "positionIndex": 0,
        "sequenceNumber": 1,
        "contentAnnotation": annotation.model_dump(mode="json"),
        "contentReferenceSha256": annotation.sha256,
        "contentReferenceRevision": 1,
        "contentTargetSource": alias.model_dump(mode="json"),
    }
    game = annotation.reference.gameId
    assert frozen_content_reference(game, source, target) == annotation.reference
    assert target["contentAnnotation"]["source"]["sourceId"] == str(annotation.source.sourceId)
    assert target["contentReferenceSha256"] == annotation.sha256
    with pytest.raises(ContentError):
        frozen_content_reference(
            game, source, {k: v for k, v in target.items() if k != "contentTargetSource"}
        )
    for key, value in (
        ("checksum_sha256", "d" * 64),
        ("oriented_width", 201),
        ("normalized_pixel_checksum_sha256", "e" * 64),
        ("exif_orientation", 8),
    ):
        changed = deepcopy(source)
        changed["sourceIdentity"][key] = value
        with pytest.raises(ContentError):
            frozen_content_reference(game, changed, target)
    # An attacker cannot make incompatible pixels/frame valid by modifying both pins.
    changed = deepcopy(target)
    changed["contentTargetSource"]["width"] = 201
    with pytest.raises(ContentError):
        frozen_content_reference(
            game,
            {**source, "sourceIdentity": {**source["sourceIdentity"], "oriented_width": 201}},
            changed,
        )
