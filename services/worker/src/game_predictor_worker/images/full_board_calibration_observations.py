"""Observe already executed model results once; GT establishes each result's truth."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

import numpy as np
from game_predictor_api.domain.full_board_calibration import (
    AXES,
    AXES_V2,
    AssessedTarget,
    FeatureVector,
)
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.input_edge_clearance import InputEdgeReference
from game_predictor_api.domain.neural_crop_policy import NEURAL_AUTO_CROP_BLOCKING_REASONS

from ..geometry_core.lattice import structurally_valid
from ..training_core.grid_correction_metrics import CorrectionControlPhoto
from .full_board_completeness import (
    features,
    gt_cropped,
    input_support,
    perspective_neighbor_deviation,
)
from .grid_rescue_strategy import completeness_suspicious, slots


class CalibrationObserver:
    def __init__(
        self,
        *,
        game_id: str,
        sources: Mapping[str, dict[str, Any]],
        game_aspect: float | None,
        routing: Mapping[str, Any] | None,
        role: str | None = None,
        routing_sha: str | None = None,
    ) -> None:
        self.game_id, self.sources = game_id, sources
        self.game_aspect, self.routing = game_aspect, routing
        self.role, self.routing_sha = role, routing_sha

    def __call__(
        self, photo: CorrectionControlPhoto, rgb: Any, observed: Mapping[str, Any]
    ) -> list[dict[str, Any]]:
        source = self.sources[photo.source_id]
        targets = sorted(source["targets"], key=lambda target: target["positionIndex"])
        width, height = rgb.shape[1], rgb.shape[0]
        evaluated: dict[tuple[str, int], tuple[bool, bool | None, bool, bool, FeatureVector]] = {}
        edges: dict[int, InputEdgeReference] = {}
        for name in ("base", "candidate"):
            found, measured, engine = observed[name]
            usable = [detection for detection in found if detection.nodes is not None]
            matching = {match.label: match for match in measured.matching.matches}
            binding = slots(found)
            neighbors = perspective_neighbor_deviation(found, binding or {})
            settings = getattr(getattr(engine, "engine", engine), "settings", None)
            contract = getattr(getattr(engine, "engine", engine), "output_contract", None)
            available = None
            if contract is not None and photo.available_source_box is not None:
                left, top, right, bottom = photo.available_source_box
                if 0 <= left < right <= width and 0 <= top < bottom <= height:
                    available = np.array(
                        [[left, top], [right, top], [right, bottom], [left, bottom]]
                    )
            for index, target in enumerate(targets):
                position = target["positionIndex"]
                match = matching.get(index)
                detection = None if match is None else usable[match.prediction]
                if detection is None:
                    evaluated[name, index] = (
                        False,
                        None,
                        False,
                        False,
                        FeatureVector(
                            version="full-board-completeness-features-v2"
                            if contract is not None
                            else "full-board-completeness-features-v1",
                            values=dict.fromkeys(AXES_V2 if contract is not None else AXES),
                            hardReasons=("COMPLETENESS_DETECTION_MISSING",),
                        ),
                    )
                    continue
                bound = (
                    binding is not None
                    and position in binding
                    and found[binding[position]] is detection
                )
                result = getattr(engine, "last_result", None)
                primary_found = getattr(engine, "last_baseline", found)
                primary_binding = slots(primary_found)
                primary = (
                    primary_found[primary_binding[position]]
                    if primary_binding and position in primary_binding
                    else None
                )
                completed = (
                    result is not None
                    and position in result.crop_calls
                    and primary is not detection
                )
                geometry = (
                    engine.variant.board
                    if completed and engine.path in ("board_only", "combined")
                    else None
                )
                support = (
                    input_support(detection.screen_quad, settings.board, geometry)
                    if settings is not None
                    else None
                )
                crop = gt_cropped(
                    photo.labels[index],
                    detection.nodes,
                    real_input_support=support,
                    width=width,
                    height=height,
                )
                good = bool(match is not None and match.correct and crop is False)
                pre_t0 = bool(
                    bound
                    and structurally_valid(detection.nodes)
                    and np.isfinite(detection.nodes).all()
                    and np.all(detection.nodes >= 0)
                    and np.all(detection.nodes[:, 0] <= width)
                    and np.all(detection.nodes[:, 1] <= height)
                )
                post_t0 = pre_t0 and not bool(
                    set(detection.reasons) & NEURAL_AUTO_CROP_BLOCKING_REASONS
                )
                required = (
                    self.routing is not None
                    and primary is not None
                    and completeness_suspicious(primary, width, height, self.routing)
                )
                vector = features(
                    detection,
                    width=width,
                    height=height,
                    real_input_support=support,
                    game_log_aspect_reference=self.game_aspect,
                    neighbor_deviation=neighbors.get(position),
                    neighbor_applicable=len(found) > 1,
                    primary=primary,
                    rescue_required=required,
                    rescue_completed=completed,
                    output_contract=contract,
                    board=None if settings is None else settings.board,
                    geometry=geometry,
                    available_source_support=available,
                )
                if name == "candidate" and contract is not None and self.role == "VALIDATION-A":
                    if self.routing_sha is None:
                        raise ValueError("INPUT_EDGE_ROUTING_REQUIRED")
                    edges[index] = InputEdgeReference(
                        referenceKind="geometry_proxy",
                        sourceRepresentativeSha256=source["sourceIdentity"][
                            "normalized_pixel_checksum_sha256"
                        ],
                        positionIndex=position,
                        variantSha256=self.routing_sha,
                        clearance=vector.values["inputEdgeClearance"],
                        inputCropped=gt_cropped(
                            photo.labels[index],
                            photo.labels[index],
                            real_input_support=support,
                            width=width,
                            height=height,
                        ),
                    )
                if not bound:
                    vector = vector.model_copy(
                        update={
                            "hardReasons": (
                                *vector.hardReasons,
                                "COMPLETENESS_SLOT_BINDING_REQUIRED",
                            )
                        }
                    )
                evaluated[name, index] = good, crop, pre_t0, post_t0, vector
        result = []
        for index, target in enumerate(targets):
            base, candidate = evaluated["base", index], evaluated["candidate", index]
            result.append(
                AssessedTarget(
                    gameId=UUID(self.game_id),
                    sourceId=UUID(source["sourceId"]),
                    sourceRepresentativeSha256=source["sourceIdentity"][
                        "normalized_pixel_checksum_sha256"
                    ],
                    positionIndex=target["positionIndex"],
                    groundTruthSha256=digest(target),
                    baselineGood=base[0],
                    candidateGood=candidate[0],
                    candidateCropped=candidate[1],
                    baselinePreT0Accepted=base[2],
                    baselineT0Accepted=base[3],
                    candidateFeatures=candidate[4],
                    synthetic=False,
                    inputEdgeReference=edges.get(index),
                ).model_dump(mode="json")
            )
        return result
