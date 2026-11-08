"""Recorded runtime input transform, independently bound by the source proposal.

The checksum binds configuration and transform identity, not an attestation of
neural inference or a checksum of the input tensor.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal

from pydantic import Field, model_validator

from .full_board_variant_context import ClosedVariant, Point, Sha, VariantContext
from .grid_model_registry import descriptor_sha256 as digest


class InputVariant(ClosedVariant):
    version: Literal["full-board-input-variant-v1"]
    variantKey: Sha
    sourceSha256: Sha
    modelManifestSha256: Sha
    operationPinSha256: Sha
    detectionId: str = Field(min_length=1, max_length=128)
    nodesSha256: Sha
    screenQuad: tuple[Point, Point, Point, Point]
    boardInputSupport: tuple[Point, Point, Point, Point]
    availableSourceBox: tuple[
        Annotated[int, Field(strict=True)],
        Annotated[int, Field(strict=True)],
        Annotated[int, Field(strict=True)],
        Annotated[int, Field(strict=True)],
    ]
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> InputVariant:
        if self.sha256 != digest(self.model_dump(mode="json", exclude={"sha256"})):
            raise ValueError("INPUT_VARIANT_CHECKSUM")
        left, top, right, bottom = self.availableSourceBox
        if not (0 <= left < right and 0 <= top < bottom):
            raise ValueError("INPUT_VARIANT_SOURCE_BOX")
        for quad in (self.screenQuad, self.boardInputSupport):
            cross = [
                (quad[(i + 1) % 4][0] - quad[i][0]) * (quad[(i + 2) % 4][1] - quad[(i + 1) % 4][1])
                - (quad[(i + 1) % 4][1] - quad[i][1])
                * (quad[(i + 2) % 4][0] - quad[(i + 1) % 4][0])
                for i in range(4)
            ]
            if not all(math.isfinite(c) for c in cross) or not (
                all(c > 0 for c in cross) or all(c < 0 for c in cross)
            ):
                raise ValueError("INPUT_VARIANT_DEGENERATE_QUAD")
        return self


def require_input_variant_binding(
    value: object,
    *,
    proposal: Mapping[str, Any],
    detection: Mapping[str, Any],
    model_sha256: str,
) -> InputVariant:
    stamp = InputVariant.model_validate(value)
    if (
        stamp.sourceSha256 != proposal["sourceChecksumSha256"]
        or stamp.modelManifestSha256 != model_sha256
        or stamp.detectionId != detection["detectionId"]
        or stamp.nodesSha256 != digest(detection["latticeNodes"])
        or stamp.availableSourceBox[2] > proposal["sourceWidth"]
        or stamp.availableSourceBox[3] > proposal["sourceHeight"]
    ):
        raise ValueError("INPUT_VARIANT_BINDING_CHANGED")
    return stamp


def require_runtime_input_variant(
    value: object,
    *,
    pin: Mapping[str, Any],
    proposal: Mapping[str, Any],
    detection: Mapping[str, Any],
    available_source_box: Sequence[int] | None = None,
) -> InputVariant:
    import numpy as np
    from game_predictor_worker.geometry_core.preprocessing import board_rectifier, transform_points
    from game_predictor_worker.geometry_core.rescue import BoardCropGeometryV2
    from game_predictor_worker.geometry_core.settings import BoardPreset

    stamp = require_input_variant_binding(
        value, proposal=proposal, detection=detection, model_sha256=pin["catalogueManifestSha256"]
    )
    if stamp.operationPinSha256 != pin["pinSha256"] or (
        available_source_box is not None and tuple(available_source_box) != stamp.availableSourceBox
    ):
        raise ValueError("INPUT_VARIANT_SOURCE_OR_OPERATION_CHANGED")
    contexts = pin["automaticQualification"]["profile"]["allowedVariants"]
    matches = [c for c in contexts if c["sha256"] == stamp.variantKey]
    if len(matches) != 1:
        raise ValueError("INPUT_VARIANT_CONTEXT_CHANGED")
    context = VariantContext.model_validate(matches[0])
    if context.candidateManifestSha256 != stamp.modelManifestSha256:
        raise ValueError("INPUT_VARIANT_CONTEXT_CHANGED")
    board = BoardPreset.model_validate(context.boardPreset)
    geometry = (
        None
        if context.boardGeometry is None
        else BoardCropGeometryV2.model_validate(context.boardGeometry)
    )
    matrix = board_rectifier(
        np.asarray(stamp.screenQuad, dtype=np.float32), board, geometry=geometry
    )
    width, height = board.canvas if geometry is None else geometry.canvas
    expected = transform_points(
        np.array([[0, 0], [width, 0], [width, height], [0, height]], np.float32),
        np.asarray(np.linalg.inv(matrix), dtype=np.float64),
    )
    if not np.allclose(expected, stamp.boardInputSupport, rtol=0, atol=1e-6):
        raise ValueError("INPUT_VARIANT_TRANSFORM_CHANGED")
    return stamp
