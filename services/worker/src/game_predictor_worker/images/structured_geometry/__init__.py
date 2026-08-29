"""Structured OpenCV geometry stages kept separate from legacy v20."""

from .global_initialization import (
    STRUCTURED_GEOMETRY_ENGINE_ID,
    STRUCTURED_GEOMETRY_GLOBAL_INITIALIZATION_VERSION,
    ActiveSlotInitialization,
    GlobalInitializationMethod,
    GlobalInitializationResult,
    GlobalInitializationStatus,
    StructuredGeometryInitializationError,
    StructuredGeometryInitializationRequest,
    StructuredGeometryInitializationThresholds,
    StructuredOpenCvGeometryEngine,
)

__all__ = [
    "STRUCTURED_GEOMETRY_ENGINE_ID",
    "STRUCTURED_GEOMETRY_GLOBAL_INITIALIZATION_VERSION",
    "ActiveSlotInitialization",
    "GlobalInitializationMethod",
    "GlobalInitializationResult",
    "GlobalInitializationStatus",
    "StructuredGeometryInitializationError",
    "StructuredGeometryInitializationRequest",
    "StructuredGeometryInitializationThresholds",
    "StructuredOpenCvGeometryEngine",
]
