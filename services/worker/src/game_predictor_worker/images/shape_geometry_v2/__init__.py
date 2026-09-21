"""Offline contracts and shared proposal core for experimental shape geometry v2."""

from .core import (
    SHAPE_GEOMETRY_V2_CORE_VERSION,
    ShapeGeometryV2Board,
    ShapeGeometryV2ColorEvidence,
    ShapeGeometryV2Config,
    ShapeGeometryV2Error,
    ShapeGeometryV2GridEvidence,
    ShapeGeometryV2ReasonCode,
    ShapeGeometryV2Result,
    ShapeGeometryV2Status,
    detect_shape_geometry_v2,
)

__all__ = [
    "SHAPE_GEOMETRY_V2_CORE_VERSION",
    "ShapeGeometryV2Board",
    "ShapeGeometryV2ColorEvidence",
    "ShapeGeometryV2Config",
    "ShapeGeometryV2Error",
    "ShapeGeometryV2GridEvidence",
    "ShapeGeometryV2ReasonCode",
    "ShapeGeometryV2Result",
    "ShapeGeometryV2Status",
    "detect_shape_geometry_v2",
]
