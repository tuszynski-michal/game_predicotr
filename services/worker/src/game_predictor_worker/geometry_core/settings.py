"""Frozen inference settings shared by the laboratory and CPU worker."""

from __future__ import annotations

from typing import Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field


class Contract(BaseModel):
    model_config = ConfigDict(
        extra="forbid", allow_inf_nan=False, json_schema_serialization_defaults_required=True
    )


MODEL_VERSION: Final = "neural-grid-v1"
METRIC_DEFINITION: Final[dict[str, Any]] = {
    "version": "neural-grid-metrics-v1",
    "matching": "hungarian-max-quad-iou; pairs below min IoU are not matched",
    "match_min_iou": 0.5,
    "quad": "corner nodes 0, 5, 23, 18 (TL, TR, BR, BL)",
    "normalization": "euclidean distance of label nodes 0 and 23 (TL-BR diagonal, as T05)",
    "board_correct_max_nme": 0.02,
    "board_correct_max_node_error": 0.05,
    "false_board": "prediction whose quad IoU with every label is below 0.5",
    "photo_complete_correct": "every label board matched and correct and no false board",
    "image_macro": "T05: per label min(1, NME), missing or invalid = 1, mean per photo, "
    "mean over photos",
    "selection": "max photo_complete_correct_rate on development; tie -> lower image_macro; "
    "tie -> earlier round",
}


class ScreenPreset(Contract):
    long_side: Literal[768] = 768
    train_canvas: tuple[int, int] = (768, 576)
    stride: Literal[4] = 4
    pad_multiple: Literal[32] = 32
    heat_sigma_fraction: float = Field(gt=0, le=0.5)
    min_heat_sigma: float = Field(gt=0, le=4)
    offset_scale: float = Field(gt=0)
    positive_radius: float = Field(gt=0, le=1)
    offset_loss_weight: float = Field(gt=0)
    decode_threshold: float = Field(gt=0, lt=1)
    nms_iou: float = Field(gt=0, lt=1)
    top_k: int = Field(ge=1, le=256)


class BoardPreset(Contract):
    canvas: tuple[int, int] = (320, 192)
    margin: float = Field(ge=0, le=0.5)
    stride: Literal[4] = 4
    corner_jitter: float = Field(ge=0, le=0.2)
    shift_jitter: float = Field(ge=0, le=0.2)
    scale_jitter: float = Field(ge=0, le=0.3)
    rotation_jitter_degrees: float = Field(ge=0, le=10)
    boards_per_image: int = Field(ge=1, le=16)
    coordinate_loss_weight: float = Field(gt=0)
    heatmap_loss_weight: float = Field(ge=0)
    heatmap_sigma: float = Field(gt=0)
    visibility_loss_weight: float = Field(ge=0)


class FitPreset(Contract):
    method: Literal["opencv-ransac-homography-then-least-squares-on-inliers"] = (
        "opencv-ransac-homography-then-least-squares-on-inliers"
    )
    inlier_threshold: float = Field(gt=0, le=0.2)
    min_inliers: int = Field(ge=4, le=24)
