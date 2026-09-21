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
from .preflight import (
    SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION,
    SHAPE_GEOMETRY_V2_LOCAL_VERIFICATION_VERSION,
    SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION,
    SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION,
    ShapeGeometryV2LocalVerification,
    ShapeGeometryV2PreflightError,
    ShapeGeometryV2PreflightProfile,
    build_shape_geometry_v2_preflight_profile,
    parse_shape_geometry_v2_preflight_profile,
    verify_shape_geometry_v2_profile,
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
    "SHAPE_GEOMETRY_V2_LOCAL_POLICY_VERSION",
    "SHAPE_GEOMETRY_V2_LOCAL_VERIFICATION_VERSION",
    "SHAPE_GEOMETRY_V2_PREFLIGHT_POLICY_VERSION",
    "SHAPE_GEOMETRY_V2_PREFLIGHT_PROFILE_VERSION",
    "ShapeGeometryV2LocalVerification",
    "ShapeGeometryV2PreflightError",
    "ShapeGeometryV2PreflightProfile",
    "build_shape_geometry_v2_preflight_profile",
    "detect_shape_geometry_v2",
    "parse_shape_geometry_v2_preflight_profile",
    "verify_shape_geometry_v2_profile",
]
