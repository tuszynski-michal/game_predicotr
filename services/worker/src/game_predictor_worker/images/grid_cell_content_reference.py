"""Strict frozen content reader and oracle using the production cell renderer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.grid_cell_content import (
    ContentError,
    ContentRevision,
    ContentSource,
    content_source_identity,
    same_content_frame,
)
from game_predictor_api.domain.grid_content_repeatability import point_to_filled_quad
from game_predictor_api.domain.grid_training_cohorts import digest, exact_lattice
from game_predictor_api.domain.grid_visibility_contract import BoardContentReference
from game_predictor_api.domain.image_geometry_v2 import VirtualCell

from .normalization import CanonicalSourceFrame
from .virtual_cell_extraction import VirtualCellExtractionError, VirtualCellRenderer

ORACLE_VERSION = "production-cell-content-oracle-v1"
SOURCE_EPSILON = 1e-6


def run_blind_content_oracle(
    frame: CanonicalSourceFrame,
    annotation: ContentRevision,
    context: Mapping[str, Any],
) -> dict[str, Any]:
    """Bounded one-board adapter for a second-pass write, using its actual manual nodes."""
    from game_predictor_api.domain.board_topology import BoardTopology
    from game_predictor_api.domain.image_geometry_v2 import (
        ActiveBoardSlot,
        DirectCellRenderConfiguration,
        GeometryEngineKind,
        SourceLatticeNodes,
        SourceOccurrence,
        SourcePoint,
        VirtualBoardGeometry,
        derive_virtual_cells,
    )

    if context.get("state") != "available":
        body = {
            "version": ORACLE_VERSION,
            "state": "render_contract_blocked",
            "reasonCode": context.get("reasonCode", "CONTENT_ORACLE_PROVENANCE_MISSING"),
            "contentReferenceSha256": annotation.sha256,
        }
        return {**body, "sha256": digest(body)}
    if annotation.measuredNodes is None or annotation.origin != "manual_blind":
        raise ContentError(
            "CONTENT_ORACLE_BLIND_NODES_REQUIRED", "Blind manual geometry is required."
        )
    lattice = SourceLatticeNodes(tuple(SourcePoint(x, y) for x, y in annotation.measuredNodes))
    geometry = VirtualBoardGeometry(
        source=frame.source,
        source_occurrence=SourceOccurrence(
            UUID(context["importJobId"]), context["fileExecutionKey"]
        ),
        slot=ActiveBoardSlot(
            context["sequenceRangeStart"],
            context["sequenceRangeEnd"],
            annotation.reference.positionIndex,
            annotation.sequenceNumber,
        ),
        topology=BoardTopology(3, 5),
        topology_rules_version_id=UUID(context["topologyRulesVersionId"]),
        geometry_revision=0,
        geometry_version="blind-content-oracle-geometry-v1",
        engine_kind=GeometryEngineKind.MANUAL_V1,
        symbol_grid_quad=lattice.outer_quad,
        lattice_nodes=lattice,
    )
    raw = context["renderConfiguration"]
    configuration = DirectCellRenderConfiguration(
        extractor_version=raw["extractorVersion"],
        preprocessing_version=raw["preprocessingVersion"],
        interpolation=raw["interpolation"],
        output_width=raw["outputWidth"],
        output_height=raw["outputHeight"],
        padding_fraction=raw["paddingFraction"],
    )
    snapshot = {"classifier": context["classifier"], "renderConfiguration": configuration.to_dict()}
    return content_oracle(
        frame,
        derive_virtual_cells(geometry=geometry, configuration=configuration),
        annotation,
        human_nodes=annotation.measuredNodes,
        human_geometry_sha256=digest(list(annotation.measuredNodes)),
        classifier_snapshot=snapshot,
        classifier_snapshot_sha256=digest(snapshot),
    )


def frozen_content_reference(
    game: UUID,
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> BoardContentReference | None:
    """No live fallback or geometry-derived visibility; absence remains unknown."""
    fields = ("contentReferenceSha256", "contentReferenceRevision", "contentAnnotation")
    present = [field in target for field in fields]
    if not any(present):
        return None
    if not all(present):
        raise ContentError(
            "CONTENT_FROZEN_PIN_INCOMPLETE", "The frozen annotation pin is incomplete."
        )
    annotation = ContentRevision.model_validate(target["contentAnnotation"])
    ref = annotation.reference
    actual_source = content_source_identity({**source["sourceIdentity"], "id": source["sourceId"]})
    # Original annotation/source stays immutable; a separate manifest pin binds an alias.
    # Legacy same-source pins remain readable, but cannot silently acquire an alias.
    target_source = (
        ContentSource.model_validate(target["contentTargetSource"])
        if "contentTargetSource" in target
        else annotation.source
    )
    if (
        annotation.sha256 != target["contentReferenceSha256"]
        or ref.revision != target["contentReferenceRevision"]
        or ref.gameId != game
        or ref.sourceRepresentativeSha256
        != source["sourceIdentity"]["normalized_pixel_checksum_sha256"]
        or target_source != actual_source
        or not same_content_frame(annotation.source, target_source)
        or ref.positionIndex != target["positionIndex"]
        or annotation.sequenceNumber != target["sequenceNumber"]
        or not ref.humanApproved
        or type(target["contentReferenceRevision"]) is not int
    ):
        raise ContentError("CONTENT_FROZEN_PIN_CONFLICT", "The frozen annotation identity differs.")
    if "blindGeometry" in target:
        blind = target["blindGeometry"]
        nodes = (
            None
            if annotation.measuredNodes is None
            else [{"x": x, "y": y} for x, y in annotation.measuredNodes]
        )
        if (
            annotation.origin != "manual_blind"
            or annotation.passNumber != 2
            or not isinstance(blind, dict)
            or blind.get("version") != "blind-content-geometry-reference-v1"
            or blind.get("sessionId") != str(annotation.sessionId)
            or blind.get("contentRevision") != ref.revision
            or blind.get("contentReferenceSha256") != annotation.sha256
            or blind.get("nodesSha256") != digest(nodes)
            or target.get("nodes") != nodes
        ):
            raise ContentError(
                "CONTENT_BLIND_GEOMETRY_CONFLICT", "A geometry differs from its blind pass."
            )
        _, quads = exact_lattice(
            {"latticeNodes": nodes}, annotation.source.width, annotation.source.height
        )
        if target.get("render", {}).get("cellQuads") != quads:
            raise ContentError(
                "CONTENT_BLIND_GEOMETRY_CONFLICT", "A cell quads differ from its blind pass."
            )
    return ref


def content_oracle(
    frame: CanonicalSourceFrame,
    cells: tuple[VirtualCell, ...],
    annotation: ContentRevision,
    *,
    human_nodes: Sequence[tuple[float, float]],
    human_geometry_sha256: str,
    classifier_snapshot: Mapping[str, Any],
    classifier_snapshot_sha256: str,
) -> dict[str, Any]:
    """The caller resolves approved geometry/configuration from trusted frozen evidence.

    Non-visible annotations never establish full-symbol preservation. Actual rendered
    pixels and padded support are recorded; the configuration is never adjusted here.
    """
    ref = annotation.reference
    if (
        not ref.humanApproved
        or len(cells) != 15
        or {cell.cell_index for cell in cells} != set(range(15))
    ):
        raise ContentError(
            "CONTENT_ORACLE_EVIDENCE_REQUIRED", "Fifteen exact cells and human labels are required."
        )
    if digest(list(human_nodes)) != human_geometry_sha256:
        raise ContentError("CONTENT_ORACLE_GEOMETRY_PIN", "Approved geometry pin differs.")
    if digest(dict(classifier_snapshot)) != classifier_snapshot_sha256:
        raise ContentError("CONTENT_ORACLE_CLASSIFIER_PIN", "Classifier snapshot pin differs.")
    configuration = cells[0].configuration.to_dict()
    if classifier_snapshot.get("renderConfiguration") != configuration:
        raise ContentError(
            "CONTENT_ORACLE_RENDER_PIN", "The classifier render configuration differs."
        )
    for cell in cells:
        geometry = cell.geometry
        nodes = geometry.lattice_nodes
        if (
            nodes is None
            or [(p.x, p.y) for p in nodes.nodes] != list(human_nodes)
            or geometry.slot.position_index != ref.positionIndex
            or geometry.slot.sequence_number != annotation.sequenceNumber
            or geometry.source != frame.source
            or cell.configuration.to_dict() != configuration
            or frame.source.normalized_pixel_checksum_sha256 != ref.sourceRepresentativeSha256
            or frame.source.source_checksum_sha256 != annotation.source.sourceSha256
        ):
            raise ContentError(
                "CONTENT_ORACLE_IDENTITY_CONFLICT",
                "Renderer input differs from approved source evidence.",
            )
    outcomes: list[dict[str, Any]] = []
    for cell in sorted(cells, key=lambda c: c.cell_index):
        content = ref.cells[cell.cell_index]
        try:
            rendered = VirtualCellRenderer().render(frame, (cell,))[0]
        except VirtualCellExtractionError as error:
            outcomes.append(
                {
                    "cellIndex": cell.cell_index,
                    "contentState": content.state,
                    "state": "render_unavailable",
                    "reasonCode": error.code,
                }
            )
            continue
        # source_direct_warp_rgb passes float32 corners into OpenCV. Evaluate
        # those exact corners in float64, rather than a more generous ideal quad.
        actual_quad = np.asarray(
            [(p.x, p.y) for p in rendered.padded_source_quad.corners], dtype=np.float32
        ).astype(np.float64)
        support = tuple((float(x), float(y)) for x, y in actual_quad)
        state = "not_evaluable"
        if content.state == "visible":
            assert content.quad is not None
            state = (
                "preserved"
                if all(point_to_filled_quad(p, support) <= SOURCE_EPSILON for p in content.quad)
                else "clipped"
            )
        outcomes.append(
            {
                "cellIndex": cell.cell_index,
                "contentState": content.state,
                "state": state,
                "renderSpecSha256": rendered.render_spec_checksum_sha256,
                "renderedPixelSha256": rendered.rendered_pixel_checksum_sha256,
                "support": support,
            }
        )
    blocked = any(row["state"] in {"clipped", "render_unavailable"} for row in outcomes)
    body = {
        "version": ORACLE_VERSION,
        "state": "render_contract_blocked"
        if blocked
        else "checked"
        if any(row["state"] == "preserved" for row in outcomes)
        else "not_evaluable",
        "contentReferenceSha256": annotation.sha256,
        "contentReferenceRevision": ref.revision,
        "humanGeometrySha256": human_geometry_sha256,
        "classifierSnapshotSha256": classifier_snapshot_sha256,
        "renderConfiguration": configuration,
        "cells": outcomes,
    }
    return {**body, "sha256": digest(body)}
