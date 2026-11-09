"""Production raster observations in original source coordinates, never geometry proxies."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.canonical_source import CanonicalSourceFrame
from game_predictor_api.domain.grid_content_repeatability import bbox_diagonal, lattice_cell
from game_predictor_api.domain.grid_render_reference import REFERENCE_V2, require_reference_v2
from game_predictor_api.domain.grid_training_cohorts import digest
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
from game_predictor_api.domain.production_cell_evaluation import REFERENCE_VERSION
from game_predictor_api.domain.production_cell_geometry import (
    assess_content,
    coverage_matrix,
    intersect_support,
)

from ..geometry_core.metrics import hungarian, quad_iou
from .grid_cell_content_reference import frozen_content_reference
from .grid_rescue_strategy import slots
from .virtual_cell_extraction import (
    VirtualCellExtractionError,
    VirtualCellRender,
    VirtualCellRenderer,
)


def real_source_support(frame: CanonicalSourceFrame) -> list[list[float]]:
    # Managed crops are already restored onto the original-coordinate canvas.
    # The offset is represented by valid_box, never applied a second time.
    if frame.crop is None:
        left, top, right, bottom = 0, 0, frame.source.width, frame.source.height
    else:
        box = frame.crop.valid_box
        left, top, right, bottom = box.left, box.top, box.right, box.bottom
    return [[left, top], [right, top], [right, bottom], [left, bottom]]


def reference_context(target: Mapping[str, Any]) -> dict[str, Any] | None:
    pin = target.get("productionContentReference")
    if pin is None:
        return None
    if pin.get("version") == REFERENCE_V2:
        require_reference_v2(pin)
        if pin["measurement"] is not None:
            annotation = target.get("contentAnnotation", {})
            contract = pin["evaluationContract"]
            oracle = target.get("contentOracle") or {}
            if (
                annotation.get("sessionId") != pin["measurement"]["sessionId"]
                or oracle.get("contentReferenceSha256") != target.get("contentReferenceSha256")
                or oracle.get("sha256")
                != digest({k: v for k, v in oracle.items() if k != "sha256"})
                or oracle.get("renderConfiguration") != contract["renderConfiguration"]
                or oracle.get("classifierSnapshotSha256")
                != digest(
                    {
                        "classifier": contract["classifier"],
                        "renderConfiguration": contract["renderConfiguration"],
                    }
                )
            ):
                raise ValueError("CONTENT_ORACLE_CONTRACT_CHANGED")
        return (
            dict(pin["sourceContext"]) if pin["sourceContext"].get("state") == "available" else None
        )
    if (
        pin.get("version") != REFERENCE_VERSION
        or pin.get("sha256") != digest({k: v for k, v in pin.items() if k != "sha256"})
        or pin.get("sourceContextSha256") != digest(pin.get("sourceContext"))
    ):
        raise ValueError("CONTENT_PRODUCTION_REFERENCE_INVALID")
    context = pin["sourceContext"]
    return context if context.get("state") == "available" else None


def render_cells(
    frame: CanonicalSourceFrame,
    nodes: Any,
    target: Mapping[str, Any],
    context: Mapping[str, Any],
    *,
    raster_sink: Callable[[VirtualCellRender], None] | None = None,
) -> list[dict[str, Any]]:
    lattice = SourceLatticeNodes(tuple(SourcePoint(float(x), float(y)) for x, y in nodes))
    geometry = VirtualBoardGeometry(
        source=frame.source,
        source_occurrence=SourceOccurrence(
            UUID(context["importJobId"]), context["fileExecutionKey"]
        ),
        slot=ActiveBoardSlot(
            context["sequenceRangeStart"],
            context["sequenceRangeEnd"],
            target["positionIndex"],
            target["sequenceNumber"],
        ),
        topology=BoardTopology(3, 5),
        topology_rules_version_id=UUID(context["topologyRulesVersionId"]),
        geometry_revision=0,
        geometry_version="production-content-evaluation-geometry-v1",
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
    results = []
    for cell in derive_virtual_cells(geometry=geometry, configuration=configuration):
        try:
            rendered = VirtualCellRenderer().render(frame, (cell,))[0]
            # These are precisely the corners passed to OpenCV, not the ideal float64 quad.
            footprint = (
                np.asarray(
                    [(p.x, p.y) for p in rendered.padded_source_quad.corners], dtype=np.float32
                )
                .astype(np.float64)
                .tolist()
            )
            results.append(
                {
                    "support": intersect_support(footprint, real_source_support(frame)),
                    "float32Footprint": footprint,
                    "renderSpecSha256": rendered.render_spec_checksum_sha256,
                    "renderedPixelSha256": rendered.rendered_pixel_checksum_sha256,
                    "reason": None,
                }
            )
        except VirtualCellExtractionError as error:
            results.append({"support": None, "reason": error.code})
            continue
        # The default observer remains metadata-only. A file consumer can retain
        # these exact, validated RGB pixels, rather than approximating the warp.
        # Sink failures must propagate, never become a missing production cell.
        if raster_sink is not None:
            raster_sink(rendered)
    return results


def ambiguous_matching(labels: Any, predictions: Any, matches: Any) -> set[int]:
    """Identify alternative optimal bindings, rather than silently using iteration order."""
    from math import fsum

    if not labels or not predictions:
        return set()
    corners = [0, 5, 23, 18]
    iou = np.asarray(
        [
            [quad_iou(np.asarray(p)[corners], np.asarray(t)[corners]) for t in labels]
            for p in predictions
        ],
        dtype=np.float64,
    )
    cost = np.where(iou >= 0.5, 1.0 - iou, 1e9)
    chosen = hungarian(cost)

    def score(matrix: Any, pairs: list[tuple[int, int]]) -> tuple[int, int, float]:
        # Never add finite IoU costs to the sentinel magnitude: even fsum would
        # round that combined total at ~1e-7, above the uniqueness tolerance.
        return (
            sum(matrix[i, j] == 1e12 for i, j in pairs),
            sum(matrix[i, j] == 1e9 for i, j in pairs),
            fsum(float(matrix[i, j]) for i, j in pairs if matrix[i, j] < 1e9),
        )

    best = score(cost, chosen)
    affected: set[int] = set()
    for match in matches:
        alternate = cost.copy()
        alternate[match.prediction, match.label] = 1e12
        pairs = hungarian(alternate)
        alternative = score(alternate, pairs)
        # Only numerical accumulation tolerance, never a spatial or model threshold.
        if alternative[:2] == best[:2] and abs(alternative[2] - best[2]) <= (
            np.finfo(np.float64).eps * 16 * max(1, len(chosen))
        ):
            affected.update(j for i, j in set(chosen) ^ set(pairs) if iou[i, j] >= 0.5)
    return affected


class ProductionContentObserver:
    def __init__(
        self,
        snapshot: Any,
        role: str,
        *,
        u: float | None,
        input_reader: Any = None,
        sources: Mapping[str, Any] | None = None,
        render_configurations: Mapping[str, Mapping[str, Any]] | None = None,
        raster_sink: Callable[[str, int, VirtualCellRender], None] | None = None,
        physical_slots: Mapping[int, int] | None = None,
    ) -> None:
        from .grid_cohort_dataset import GridAssessmentDataset, GridBoardDataset

        self.snapshot, self.role, self.u = snapshot, role, u
        self.input_reader = input_reader
        self.render_configurations = render_configurations
        self.raster_sink = raster_sink
        self.physical_slots = physical_slots
        if sources is None:
            dataset = (
                GridAssessmentDataset(snapshot, "VALIDATION" if role == "B" else role)
                if role in ("REGRESSION", "B")
                else GridBoardDataset(snapshot, role)
            )
            self.sources = {source["sourceId"]: source for source, _ in dataset.indexed()}
        else:
            self.sources = dict(sources)

    def __call__(self, photo: Any, rgb: Any, observed: Mapping[str, Any]) -> dict[str, Any]:
        source = self.sources[photo.source_id]
        targets = sorted(source["targets"], key=lambda t: t["positionIndex"])
        frame = self.snapshot.frame(
            source,
            "VALIDATION" if self.role == "B" else self.role,
            **({"validation_purpose": "B"} if self.role == "B" else {}),
        )
        if not np.array_equal(frame.rgb, rgb):
            raise ValueError("CONTENT_SOURCE_RASTER_CHANGED")
        references = [
            frozen_content_reference(UUID(self.snapshot.manifest["gameId"]), source, t)
            for t in targets
        ]
        contexts = [reference_context(t) for t in targets]
        reasons = set()
        if self.u is None:
            reasons.add("CONTENT_UNCERTAINTY_MISSING")
        if any(c is None for c in contexts):
            reasons.add("CONTENT_RENDER_REFERENCE_MISSING")
        configurations = {digest(c["renderConfiguration"]) for c in contexts if c is not None}
        if len(configurations) != 1:
            reasons.add("CONTENT_SOURCE_RENDER_CONFIGURATION_AMBIGUOUS")
        rows = [
            {
                "positionIndex": t["positionIndex"],
                "referenceSha256": t.get("contentReferenceSha256"),
                "cells": [
                    {
                        "cellIndex": j,
                        "contentState": "unknown" if ref is None else ref.cells[j].state,
                    }
                    for j in range(15)
                ],
            }
            for t, ref in zip(targets, references, strict=True)
        ]
        visible = [
            (i, j, cell.quad)
            for i, ref in enumerate(references)
            if ref is not None
            for j, cell in enumerate(ref.cells)
            if cell.state == "visible" and cell.quad is not None
        ]
        for name in ("base", "candidate"):
            found, measured, engine = observed[name]
            usable = [d for d in found if d.nodes is not None]
            matches = {m.label: m for m in measured.matching.matches}
            ambiguous = ambiguous_matching(
                list(photo.labels), [d.nodes for d in usable], measured.matching.matches
            )
            binding = getattr(self, "physical_slots", None)
            if binding is None:
                binding = slots(found)
            ambiguous.update(
                i
                for i, match in matches.items()
                if binding is None
                or targets[i]["positionIndex"] not in binding
                or found[binding[targets[i]["positionIndex"]]] is not usable[match.prediction]
            )
            reverse = {m.prediction: i for i, m in matches.items()}
            crops: list[dict[str, Any]] = []
            for p, detection in enumerate(usable):
                index = reverse.get(p, 0)
                context = contexts[index]
                if context is None or len(configurations) != 1:
                    crops.extend(
                        [{"support": None, "reason": "CONTENT_RENDER_REFERENCE_MISSING"}] * 15
                    )
                    continue
                try:
                    configuration = (getattr(self, "render_configurations", None) or {}).get(name)
                    render_context = (
                        context
                        if configuration is None
                        else {**context, "renderConfiguration": dict(configuration)}
                    )
                    retained: list[VirtualCellRender] = []
                    crops.extend(
                        render_cells(
                            frame,
                            detection.nodes,
                            targets[index],
                            render_context,
                            raster_sink=retained.append
                            if getattr(self, "raster_sink", None)
                            else None,
                        )
                    )
                except (ValueError, TypeError):
                    crops.extend([{"support": None, "reason": "CONTENT_PREDICTION_INVALID"}] * 15)
                    continue
                # Consumer failures must not be disguised as missing geometry.
                sink = getattr(self, "raster_sink", None)
                if sink is not None:
                    for raster in retained:
                        sink(name, p, raster)
            proper: list[int | None] = [
                None if i not in matches or i in ambiguous else matches[i].prediction * 15 + j
                for i, j, _ in visible
            ]
            matrix = coverage_matrix(
                [q for _, _, q in visible], [c["support"] for c in crops], proper
            )
            for k, (i, j, quad) in enumerate(visible):
                crop_index = proper[k]
                crop = None if crop_index is None else crops[crop_index]
                radius = (self.u or 0.0) * bbox_diagonal(lattice_cell(photo.labels[i], j))
                assessment = assess_content(quad, None if crop is None else crop["support"], radius)
                rows[i]["cells"][j][name] = {
                    "finalContentState": assessment["state"],
                    "coverage": assessment["coverage"],
                    "reason": assessment["reason"],
                    **matrix["cells"][k],
                    "cropIndex": proper[k],
                }
            for i, row in enumerate(rows):
                from .production_cell_input import observe_input

                match = matches.get(i)
                input_proof = (
                    None
                    if match is None or i in ambiguous
                    else (self.input_reader or observe_input)(
                        frame,
                        source,
                        targets[i],
                        usable[match.prediction],
                        engine,
                        UUID(self.snapshot.manifest["gameId"]),
                    )
                )
                for j, cell in enumerate(row["cells"]):
                    if name in cell:
                        cell[name]["inputContentState"] = (
                            None if input_proof is None else input_proof["inputContentStates"][j]
                        )
                cell_results = [c.get(name) for c in row["cells"]]
                row[name] = {
                    "matchAmbiguous": i in ambiguous,
                    "inputEvidence": input_proof,
                    "matchedPrediction": None if i not in matches else matches[i].prediction,
                    "usable": i in matches
                    and matches[i].correct
                    and i not in ambiguous
                    and all(
                        c is not None
                        and c["finalContentState"] == "preserved"
                        and not any(c[f] for f in ("wrongCell", "tie", "foreignFullSymbol"))
                        for c in cell_results
                    ),
                }
            # Keep actual raster witnesses and the full source-wide matrix in durable detail.
            for row in rows:
                row[name]["usable"] = bool(row[name]["usable"])
            if name == "base":
                model_details = {}
            model_details[name] = {
                "crops": crops,
                "coverageMatrix": matrix["coverage"],
                "detections": [
                    {
                        "nodes": None
                        if d.nodes is None
                        else np.asarray(d.nodes, dtype=np.float64).tolist(),
                        "screenQuad": np.asarray(d.screen_quad, dtype=np.float64).tolist(),
                    }
                    for d in found
                ],
            }
        return {
            "version": "production-cell-photo-v1",
            "sourceId": source["sourceId"],
            "fullGeometry": photo.full_geometry,
            "reasonCodes": sorted(reasons),
            "referenceSha256": digest([t.get("productionContentReference") for t in targets]),
            "boards": rows,
            "models": model_details,
        }
