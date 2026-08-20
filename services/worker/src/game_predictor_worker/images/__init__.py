"""Image corpus contracts used before algorithm implementation."""

from .board_cell_geometry_audit import (
    BoardCellGeometryAudit,
    BoardCellGeometryAuditError,
    render_audit_contact_sheets,
    render_audit_overlays,
    run_board_cell_geometry_audit,
    select_audit_pages,
    write_content_addressed_audit,
)
from .board_cell_geometry_contract import (
    BOARD_CELL_GEOMETRY_MANIFEST_VERSION,
    BOARD_CELL_GEOMETRY_VERSION,
    BoardCellGeometryContractError,
    BoardCellGeometryManifestV1,
    derive_board_cell_quads,
    load_board_cell_geometry_manifest,
    load_real_board_cell_geometry_corpus,
    parse_board_cell_geometry_manifest,
    write_content_addressed_manifest,
)
from .board_cell_geometry_crops import (
    CROPPER_VERSION as BOARD_CELL_GEOMETRY_CROPPER_VERSION,
)
from .board_cell_geometry_crops import (
    BoardCellGeometryCropError,
    BoardCellGeometryCropResult,
    BoardCellGeometrySourceCrop,
    BoardCellGeometrySourceDirectCropper,
    cropper_fingerprint_sha256,
)
from .board_cell_geometry_estimator import (
    BoardCellGeometryEstimate,
    estimate_board_cell_geometry,
    estimator_thresholds,
)
from .calibrated_symbol_inventory import build_calibrated_symbol_crop_inventory
from .cell_grid_golden import (
    CellGridGoldenError,
    CellGridGoldenReview,
    baseline_report_bytes,
    build_v1_baseline_report,
)
from .cell_grid_review_http import (
    CellGridReviewHttpError,
    create_cell_grid_review_server,
)
from .cell_grid_v2_quality import (
    CALIBRATED_QUALITY_REPORT_VERSION,
    CellGridV2QualityError,
    build_calibrated_quality_report,
    build_v2_quality_report,
    calibrated_quality_report_bytes,
    v2_quality_report_bytes,
)
from .corpus import (
    CorpusValidationError,
    CorpusValidationReport,
    validate_corpus,
)
from .grid_calibration import (
    INTERPOLATION_VERSION,
    PROFILE_SET_VERSION,
    GridCalibrationError,
    GridCalibrationProfiles,
    build_profile_document,
    profile_document_bytes,
)
from .manual_board_cell_geometry_preview import (
    MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION,
    MANUAL_BOARD_CELL_GEOMETRY_VERSION,
    ManualBoardCellGeometryArtifacts,
    ManualBoardCellGeometryPreview,
    ManualBoardCellGeometryPreviewer,
    ManualBoardCellGeometryPreviewError,
    manual_board_cell_geometry_decision_checksum,
)
from .rectification import (
    CALIBRATED_CROPPER_VERSION,
    V2_CROPPER_VERSION,
    V2_GRID_CONTRACT,
    PerspectiveBoardCellCropperV2,
    PerspectiveBoardCellCropperV2Calibrated,
)
from .symbol_dataset import (
    CALIBRATED_INVENTORY_VERSION,
    SymbolDatasetError,
    build_symbol_crop_inventory,
    export_reviewed_symbol_dataset,
    load_reviewed_label_source,
    load_symbol_crop_inventory,
)
from .symbol_review import BootstrapSymbolReview, SymbolReviewError
from .symbol_review_http import SymbolReviewHttpError, create_review_server

__all__ = [
    "BOARD_CELL_GEOMETRY_MANIFEST_VERSION",
    "BOARD_CELL_GEOMETRY_VERSION",
    "BoardCellGeometryContractError",
    "BoardCellGeometryCropError",
    "BoardCellGeometryCropResult",
    "BoardCellGeometryEstimate",
    "BoardCellGeometryAudit",
    "BoardCellGeometryAuditError",
    "BoardCellGeometryManifestV1",
    "BoardCellGeometrySourceCrop",
    "BoardCellGeometrySourceDirectCropper",
    "BOARD_CELL_GEOMETRY_CROPPER_VERSION",
    "CorpusValidationError",
    "CorpusValidationReport",
    "CellGridGoldenError",
    "CellGridGoldenReview",
    "CellGridReviewHttpError",
    "CellGridV2QualityError",
    "CALIBRATED_CROPPER_VERSION",
    "CALIBRATED_INVENTORY_VERSION",
    "CALIBRATED_QUALITY_REPORT_VERSION",
    "SymbolDatasetError",
    "SymbolReviewError",
    "SymbolReviewHttpError",
    "BootstrapSymbolReview",
    "build_symbol_crop_inventory",
    "build_calibrated_symbol_crop_inventory",
    "build_calibrated_quality_report",
    "build_profile_document",
    "baseline_report_bytes",
    "build_v1_baseline_report",
    "build_v2_quality_report",
    "calibrated_quality_report_bytes",
    "create_cell_grid_review_server",
    "cropper_fingerprint_sha256",
    "derive_board_cell_quads",
    "estimate_board_cell_geometry",
    "estimator_thresholds",
    "export_reviewed_symbol_dataset",
    "load_reviewed_label_source",
    "load_symbol_crop_inventory",
    "load_board_cell_geometry_manifest",
    "load_real_board_cell_geometry_corpus",
    "parse_board_cell_geometry_manifest",
    "render_audit_overlays",
    "render_audit_contact_sheets",
    "run_board_cell_geometry_audit",
    "select_audit_pages",
    "create_review_server",
    "GridCalibrationError",
    "GridCalibrationProfiles",
    "INTERPOLATION_VERSION",
    "MANUAL_BOARD_CELL_GEOMETRY_VERSION",
    "MANUAL_BOARD_CELL_GEOMETRY_PREVIEW_VERSION",
    "ManualBoardCellGeometryArtifacts",
    "ManualBoardCellGeometryPreview",
    "ManualBoardCellGeometryPreviewError",
    "ManualBoardCellGeometryPreviewer",
    "manual_board_cell_geometry_decision_checksum",
    "PerspectiveBoardCellCropperV2",
    "PerspectiveBoardCellCropperV2Calibrated",
    "PROFILE_SET_VERSION",
    "V2_CROPPER_VERSION",
    "V2_GRID_CONTRACT",
    "profile_document_bytes",
    "v2_quality_report_bytes",
    "validate_corpus",
    "write_content_addressed_manifest",
    "write_content_addressed_audit",
]
