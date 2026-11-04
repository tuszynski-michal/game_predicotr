"""Bounded JSON representation of neural stage results for durable rescue."""

import math
from typing import Any

import numpy as np

from .inference import BoardDetection


def detection_document(item: BoardDetection) -> dict[str, Any]:
    if not math.isfinite(item.score) or not np.isfinite(item.screen_quad).all():
        raise ValueError("GRID_RESCUE_RESULT_INVALID")
    return {
        "score": float(item.score),
        "screenQuad": item.screen_quad.tolist(),
        **{
            key: None if value is None or not np.isfinite(value).all() else value.tolist()
            for key, value in (
                ("rawNodes", item.raw_nodes),
                ("nodes", item.nodes),
                ("nodePeak", item.node_peak),
                ("visibility", item.visibility),
            )
        },
        "fitResidual": item.fit_residual
        if item.fit_residual is None or math.isfinite(item.fit_residual)
        else None,
        "fitMaxError": item.fit_max_error
        if item.fit_max_error is None or math.isfinite(item.fit_max_error)
        else None,
        "fitInliers": item.fit_inliers,
        "reasons": list(item.reasons),
    }


def detection_from_document(value: dict[str, Any]) -> BoardDetection:
    if set(value) != {
        "score",
        "screenQuad",
        "rawNodes",
        "nodes",
        "nodePeak",
        "visibility",
        "fitResidual",
        "fitMaxError",
        "fitInliers",
        "reasons",
    }:
        raise ValueError("GRID_RESCUE_RESULT_INVALID")
    arrays = {
        key: None if value[key] is None else np.asarray(value[key], dtype=np.float32)
        for key in ("rawNodes", "nodes", "nodePeak", "visibility")
    }
    quad = np.asarray(value["screenQuad"], dtype=np.float32)
    if (
        quad.shape != (4, 2)
        or not np.isfinite(quad).all()
        or type(value["score"]) not in (float, int)
        or not math.isfinite(value["score"])
        or not 0 <= value["score"] <= 1
        or any(
            item is not None
            and (
                item.shape != ((24, 2) if key in ("nodes", "rawNodes") else (24,))
                or not np.isfinite(item).all()
            )
            for key, item in arrays.items()
        )
        or any(
            value[key] is not None
            and (
                type(value[key]) not in (int, float)
                or not math.isfinite(value[key])
                or value[key] < 0
            )
            for key in ("fitResidual", "fitMaxError")
        )
        or type(value["fitInliers"]) is not int
        or not 0 <= value["fitInliers"] <= 24
        or not isinstance(value["reasons"], list)
        or any(not isinstance(reason, str) or len(reason) > 128 for reason in value["reasons"])
    ):
        raise ValueError("GRID_RESCUE_RESULT_INVALID")
    return BoardDetection(
        float(value["score"]),
        quad,
        arrays["rawNodes"],
        arrays["nodes"],
        arrays["nodePeak"],
        arrays["visibility"],
        value["fitResidual"],
        value["fitMaxError"],
        value["fitInliers"],
        list(value["reasons"]),
    )
