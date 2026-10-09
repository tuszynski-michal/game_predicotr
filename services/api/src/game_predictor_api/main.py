"""FastAPI application factory for the local Admin API."""

import json
import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any, Final
from urllib.parse import urlparse
from uuid import UUID

from fastapi import Cookie, Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from game_predictor_worker.images.manual_board_cell_symbol_prediction import (
    ManualBoardCellSymbolPredictor,
)
from game_predictor_worker.semi_automatic_selection.v7_pilot_configuration import V7PilotArtifacts
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from game_predictor_api.api.image_selections import MANUAL_FILE_NAME_HEADER
from game_predictor_api.api.management import create_management_router
from game_predictor_api.api.management_public import (
    create_management_public_router,
    require_management_proxy,
)
from game_predictor_api.api.management_public_stakes import create_management_public_stake_router
from game_predictor_api.api.management_public_structure import (
    create_management_public_structure_router,
)
from game_predictor_api.api.management_sessions import create_management_sessions_router
from game_predictor_api.api.management_stakes import create_management_stake_router
from game_predictor_api.api.router import create_api_router
from game_predictor_api.api.super_game_series import create_super_game_series_router
from game_predictor_api.application.board_cell_geometry_pending import (
    BoardCellGeometryPendingService,
    ManagedBoardCellProcessingManifestStore,
)
from game_predictor_api.application.board_search import BoardSearchService
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardDetailService,
    BoardSearchBoardViewCache,
    BoardSearchBoardViewService,
)
from game_predictor_api.application.board_search_share_access import (
    BoardSearchShareAccessService,
    assert_board_search_share_ready,
)
from game_predictor_api.application.board_search_share_corrections import (
    BoardSearchShareCorrectionService,
)
from game_predictor_api.application.board_search_share_queries import (
    BoardSearchShareQueryLog,
    BoardSearchShareQueryLogService,
    BoardSearchShareRateLimiter,
)
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.cleanup import (
    CleanupService,
    ManagedCleanupArtifactStore,
)
from game_predictor_api.application.controlled_folder_picker import WindowsFolderPicker
from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.application.grid_audit_proposals import (
    FileGridAuditProposalStore,
    GridAuditProposalService,
)
from game_predictor_api.application.grid_audit_symbol_suggestions import (
    FileGridAuditSymbolSuggestionStore,
)
from game_predictor_api.application.grid_calibration import GridCalibrationService
from game_predictor_api.application.grid_shadow import GridShadowService
from game_predictor_api.application.image_geometry_rollout import ImageGeometryRolloutService
from game_predictor_api.application.image_grid_reviews import ImageGridReviewService
from game_predictor_api.application.image_import_geometry_guard import (
    ImageImportGeometryGuardService,
)
from game_predictor_api.application.image_imports import (
    IMAGE_RELATIVE_PATH_HEADER,
    BrowserImageSelectionService,
    ImageFolderSelectionService,
)
from game_predictor_api.application.image_jobs import ImageJobOperationsService
from game_predictor_api.application.image_review_cohorts import (
    VerifiedCohortArtifactStore,
    VerifiedCohortService,
)
from game_predictor_api.application.image_reviews import (
    OperationalImageReviewService,
)
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.image_storage import (
    ImageArtifactStore,
    ImageStorageService,
)
from game_predictor_api.application.image_symbol_review_backfill import (
    SymbolCellReviewBackfillService,
)
from game_predictor_api.application.image_symbol_review_bulk_operations import (
    SymbolCellReviewBulkOperationService,
)
from game_predictor_api.application.image_symbol_review_mutations import (
    SymbolCellReviewMutationService,
)
from game_predictor_api.application.image_symbol_reviews import SymbolCellReviewQueryService
from game_predictor_api.application.iterative_image_imports import IterativeImageImportService
from game_predictor_api.application.jobs import (
    JobService,
    ManagedImageSelectionDeletionArtifactStore,
)
from game_predictor_api.application.lab_symbol_candidate_import import (
    LabSymbolCandidateImportService,
)
from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportService,
)
from game_predictor_api.application.layout_imports import (
    LayoutImportSourceInspector,
)
from game_predictor_api.application.management import ManagementError, ManagementService
from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.application.management_ingress import stop_unused_shared_ingress
from game_predictor_api.application.management_public import ManagementPublicGuard
from game_predictor_api.application.management_stakes import ManagementStakeService
from game_predictor_api.application.mobile_releases import (
    MobileReleaseService,
)
from game_predictor_api.application.page_geometry_overrides import (
    PageGeometryOverrideService,
)
from game_predictor_api.application.remote_manual_selection_access import (
    RemoteManualSelectionAccessError,
    RemoteManualSelectionAccessNotFoundError,
    RemoteManualSelectionAccessService,
    RemoteManualSelectionAuthenticationError,
    RemoteManualSelectionAuthorizationError,
    RemoteManualSelectionLeaseConflictError,
)
from game_predictor_api.application.remote_manual_selection_control import (
    RemoteManualSelectionControlRateLimiter,
    RemoteManualSelectionControlService,
    RemoteManualSelectionRateLimitError,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.application.remote_manual_selection_recovery import (
    RemoteManualSelectionRecoveryRunner,
    RemoteManualSelectionRecoveryService,
)
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferGate,
    RemoteManualSelectionTransferLimitError,
    RemoteManualSelectionTransferLimits,
    RemoteManualSelectionTransferRateLimitError,
    RemoteManualSelectionTransferService,
    RemoteManualSelectionTransferTimeoutError,
)
from game_predictor_api.application.reviewer_access import (
    ReviewerAccessError,
    ReviewerAccessService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
)
from game_predictor_api.application.reviewer_work_assignments import (
    ReviewerWorkAssignmentService,
)
from game_predictor_api.application.reviewer_work_lifecycle import (
    ReviewerWorkLifecycleService,
)
from game_predictor_api.application.reviews import ReviewService
from game_predictor_api.application.rules import RulesService
from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.application.storage_capacity import StorageCapacityGuard
from game_predictor_api.application.storage_gc import StorageGcArtifactStore, StorageGcService
from game_predictor_api.application.super_game_series import SuperGameSeriesService
from game_predictor_api.application.symbol_model_iterations import SymbolModelIterationService
from game_predictor_api.application.symbol_model_registry import SymbolModelRegistryService
from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceService,
    ManagedSymbolReferenceArtifactStore,
)
from game_predictor_api.application.unreadable_board_reviews import UnreadableBoardReviewService
from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationApiError,
    V7LabelGeometryCalibrationService,
)
from game_predictor_api.application.verified_training_cohorts import (
    VerifiedTrainingCohortArtifactStore,
    VerifiedTrainingCohortService,
)
from game_predictor_api.application.virtual_cell_previews import VirtualCellPreviewService
from game_predictor_api.application.virtual_grid_geometry import VirtualGridGeometryService
from game_predictor_api.application.worker_lanes import WorkerLaneStatusService
from game_predictor_api.config import ApiSettings, get_settings
from game_predictor_api.domain.board_search import BoardSearchError
from game_predictor_api.domain.board_search_shares import (
    BoardSearchShareAuthenticationError,
    BoardSearchShareAuthorizationError,
    BoardSearchShareConflictError,
    BoardSearchShareError,
    BoardSearchShareNotFoundError,
    BoardSearchShareRateLimitError,
    BoardSearchShareUnavailableError,
)
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogError,
    CatalogNotFoundError,
)
from game_predictor_api.domain.cleanup import (
    CleanupConflictError,
    CleanupError,
    CleanupNotFoundError,
)
from game_predictor_api.domain.datasets import (
    DatasetConflictError,
    DatasetError,
    DatasetNotFoundError,
)
from game_predictor_api.domain.grid_shadow import GridShadowError
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.domain.image_import_engine_policy import (
    LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewError,
    ImageReviewNotFoundError,
)
from game_predictor_api.domain.image_selections import (
    ImageSelectionConflictError,
    ImageSelectionError,
    ImageSelectionNotFoundError,
)
from game_predictor_api.domain.image_sequence_canonical import ImageSequenceCanonicalService
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewError
from game_predictor_api.domain.iterative_image_imports import (
    IterativeImageImportConflictError,
    IterativeImageImportError,
    IterativeImageImportNotFoundError,
)
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobError,
    JobNotFoundError,
)
from game_predictor_api.domain.management_sessions import (
    MANAGEMENT_COOKIE,
    MANAGEMENT_EXPECTED_SESSION_HEADER,
    ManagementAccessError,
    invalid_access,
)
from game_predictor_api.domain.mobile_releases import (
    MobileReleaseConflictError,
    MobileReleaseError,
    MobileReleaseNotFoundError,
)
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
    RemoteManualSelectionError,
)
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignment,
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentError,
)
from game_predictor_api.domain.reviews import (
    ReviewConflictError,
    ReviewError,
    ReviewNotFoundError,
)
from game_predictor_api.domain.rules import (
    RulesConflictError,
    RulesError,
    RulesNotFoundError,
)
from game_predictor_api.domain.storage_capacity import GIB, StorageCapacityPolicy
from game_predictor_api.domain.storage_retention import StorageRetentionPolicy
from game_predictor_api.domain.super_game_series import (
    SuperGameSeriesConflictError,
    SuperGameSeriesError,
    SuperGameSeriesNotFoundError,
)
from game_predictor_api.security.local_admin import (
    ADMIN_CONFIRMATION_HEADER,
    ADMIN_INTENT_HEADER,
    ADMIN_TARGET_HEADER,
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
    augment_admin_security_openapi,
    loopback_origin_aliases,
)
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    SqlAlchemyBoardCellGeometryPendingRepository,
)
from game_predictor_api.storage.board_import_coverage_repository import (
    SqlAlchemyBoardImportCoverageRepository,
)
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.board_search_share_correction_repository import (
    SqlAlchemyBoardSearchShareCorrectionRepository,
)
from game_predictor_api.storage.board_search_share_query_repository import (
    SqlAlchemyBoardSearchShareQueryLog,
    SqlAlchemyBoardSearchShareQueryRepository,
)
from game_predictor_api.storage.board_search_share_repository import (
    SqlAlchemyBoardSearchShareRepository,
)
from game_predictor_api.storage.browser_staging_retention_repository import (
    SqlAlchemyBrowserStagingRetentionRepository,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import (
    create_cross_game_owner_session_factory,
    create_database_engine,
    create_owner_database_engine,
    create_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.dataset_repository import (
    SqlAlchemyDatasetRepository,
)
from game_predictor_api.storage.game_entity_locator import (
    GameEntityLocator,
    bind_located_game,
)
from game_predictor_api.storage.game_partition_lifecycle import GamePartitionLifecycleError
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRouter,
    GameStorageRoutingError,
    game_id_from_request,
    game_storage_scope,
)
from game_predictor_api.storage.global_geometry_library_repository import (
    SqlAlchemyGlobalGeometryLibraryRepository,
)
from game_predictor_api.storage.global_geometry_profile_snapshot_resolver import (
    SqlAlchemyGlobalGeometryProfileSnapshotResolver,
)
from game_predictor_api.storage.global_shape_geometry_readiness import (
    GlobalShapeGeometryReadinessResolver,
)
from game_predictor_api.storage.grid_audit_board_reader import SqlAlchemyGridAuditBoardReader
from game_predictor_api.storage.grid_calibration_repository import (
    SqlAlchemyGridCalibrationRepository,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_profile_snapshot_resolver import (
    SqlAlchemyGridProfileSnapshotResolver,
)
from game_predictor_api.storage.grid_shadow import SqlAlchemyGridShadowRepository
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)
from game_predictor_api.storage.image_geometry_completeness_state_repository import (
    SqlAlchemyImageGeometryCompletenessStateRepository,
)
from game_predictor_api.storage.image_geometry_rollout_backfill_repository import (
    SqlAlchemyImageGeometryRolloutBackfillRepository,
)
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)
from game_predictor_api.storage.image_import_geometry_guard_repository import (
    SqlAlchemyImageImportGeometryGuardRepository,
)
from game_predictor_api.storage.image_job_repository import (
    SqlAlchemyImageJobOperationsRepository,
)
from game_predictor_api.storage.image_review_cohort_repository import (
    SqlAlchemyVerifiedCohortExportRepository,
)
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.image_selection_repository import (
    SqlAlchemyImageSelectionRepository,
)
from game_predictor_api.storage.image_sequence_canonical_repository import (
    SqlAlchemyImageSequenceCanonicalRepository,
)
from game_predictor_api.storage.image_symbol_review_backfill_repository import (
    SqlAlchemySymbolCellReviewBackfillRepository,
)
from game_predictor_api.storage.image_symbol_review_bulk_operation_repository import (
    SqlAlchemySymbolCellReviewBulkOperationRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewMutationRepository,
    SqlAlchemySymbolCellReviewQueryRepository,
    SqlAlchemyUnreadableBoardReviewRepository,
)
from game_predictor_api.storage.iterative_image_import_repository import (
    SqlAlchemyIterativeImageImportRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.lab_symbol_candidate_import_repository import (
    SqlAlchemyLabSymbolCandidateImportRepository,
)
from game_predictor_api.storage.layout_import_report_repository import (
    SqlAlchemyLayoutImportReportRepository,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_session_repository import (
    SqlAlchemyManagementSessionRepository,
)
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
from game_predictor_api.storage.mobile_release_repository import (
    SqlAlchemyMobileReleaseRepository,
)
from game_predictor_api.storage.page_geometry_override_repository import (
    SqlAlchemyPageGeometryOverrideRepository,
)
from game_predictor_api.storage.remote_manual_selection_access_repository import (
    SqlAlchemyRemoteManualSelectionAccessRepository,
)
from game_predictor_api.storage.remote_manual_selection_repository import (
    SqlAlchemyRemoteManualSelectionRepository,
)
from game_predictor_api.storage.review_repository import (
    SqlAlchemyReviewRepository,
)
from game_predictor_api.storage.reviewer_access_repository import (
    SqlAlchemyReviewerAccessRepository,
)
from game_predictor_api.storage.reviewer_work_assignment_repository import (
    OtherGamesOnlineAssignments,
    SqlAlchemyReviewerWorkAssignmentRepository,
)
from game_predictor_api.storage.rules_repository import SqlAlchemyRulesRepository
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from game_predictor_api.storage.storage_gc_repository import SqlAlchemyStorageGcRepository
from game_predictor_api.storage.super_game_marker_repository import (
    SqlAlchemySuperGameMarkerRepository,
)
from game_predictor_api.storage.super_game_series_repository import (
    SqlAlchemySuperGameSeriesRepository,
)
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
)
from game_predictor_api.storage.symbol_model_iteration_repository import (
    SqlAlchemySymbolModelIterationRepository,
)
from game_predictor_api.storage.symbol_model_registry_repository import (
    SqlAlchemySymbolModelRegistryRepository,
)
from game_predictor_api.storage.symbol_model_snapshot_resolver import (
    SqlAlchemySymbolModelSnapshotResolver,
)
from game_predictor_api.storage.symbol_references_repository import (
    SqlAlchemyApprovedSymbolReferenceRepository,
)
from game_predictor_api.storage.verified_training_cohort_repository import (
    SqlAlchemyVerifiedTrainingCohortRepository,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from game_predictor_api.storage.worker_lane_repository import (
    SqlAlchemyWorkerLaneRepository,
)

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _GameEntityRoute:
    """A route that names a game-owned row only by its global id (TASK-0797)."""

    path_prefix: str
    path_parameter: str
    table: str
    column: str
    # False: the row may legitimately not exist yet (browser staging that has
    # no retention record); the request then continues unscoped.
    required: bool = True


_GAME_ENTITY_ROUTES: Final = (
    _GameEntityRoute(
        "/api/v1/admin/dataset-versions/", "dataset_version_id", "dataset_versions", "id"
    ),
    _GameEntityRoute("/api/v1/admin/image-selections/", "run_id", "image_selection_runs", "id"),
    _GameEntityRoute(
        "/api/v1/admin/image-imports/curated-sources/",
        "source_id",
        "curated_image_import_sources",
        "id",
    ),
    _GameEntityRoute(
        "/api/v1/admin/image-imports/browser-selections/",
        "upload_id",
        "browser_selection_retention_states",
        "upload_id",
        required=False,
    ),
    _GameEntityRoute("/api/v1/admin/review-batches/", "review_batch_id", "review_batches", "id"),
    _GameEntityRoute("/api/v1/admin/review-items/", "review_item_id", "review_items", "id"),
    _GameEntityRoute(
        "/api/v1/admin/review-feedback-exports/",
        "feedback_export_id",
        "review_feedback_exports",
        "id",
    ),
)


def _assign_request_entity_game(
    session: Session, request: Request, locator: GameEntityLocator
) -> None:
    """Route ``session`` to the game that owns the row named by the request path.

    A request already scoped to a game (path or ``gameId``) keeps that game: a
    row of another game is then invisible and reported as not found.
    """

    for route in _GAME_ENTITY_ROUTES:
        raw = request.path_params.get(route.path_parameter)
        if raw is None or not request.url.path.startswith(route.path_prefix):
            continue
        try:
            value = raw if isinstance(raw, UUID) else UUID(str(raw))
        except ValueError:
            return
        if bind_located_game(session, locator, route.table, route.column, value):
            return
        if route.required:
            raise GameStorageRoutingError(
                "GAME_SCOPED_RESOURCE_NOT_FOUND",
                "The requested resource does not exist in any game.",
                details={route.path_parameter: str(value)},
            )
        return


def _loopback_api_origin(host: str, port: int) -> str:
    """`http://host:port` with an IPv6 loopback in brackets."""

    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def create_app(
    settings: ApiSettings | None = None,
    *,
    local_source_picker: Callable[[], Path | None] | None = None,
    management_access_service_dependency: Callable[..., object] | None = None,
    management_service_dependency: Callable[..., object] | None = None,
    management_stake_service_dependency: Callable[..., object] | None = None,
    catalog_service_dependency: Callable[..., object] | None = None,
    board_search_service_dependency: Callable[..., object] | None = None,
    board_search_approximate_win_service_dependency: Callable[..., object] | None = None,
    board_search_board_detail_service_dependency: Callable[..., object] | None = None,
    board_search_board_view_service_dependency: Callable[..., object] | None = None,
    board_search_share_access_service_dependency: Callable[..., object] | None = None,
    board_search_share_query_log: BoardSearchShareQueryLog | None = None,
    board_search_share_query_log_service_dependency: Callable[..., object] | None = None,
    board_search_share_correction_service_dependency: Callable[..., object] | None = None,
    board_search_share_rate_limiter: BoardSearchShareRateLimiter | None = None,
    cleanup_service_dependency: Callable[..., object] | None = None,
    rules_service_dependency: Callable[..., object] | None = None,
    dataset_service_dependency: Callable[..., object] | None = None,
    job_service_dependency: Callable[..., object] | None = None,
    image_selection_service_dependency: Callable[..., object] | None = None,
    semi_automatic_image_selection_service_dependency: Callable[..., object] | None = None,
    v7_label_geometry_calibration_service_dependency: Callable[..., object] | None = None,
    image_job_service_dependency: Callable[..., object] | None = None,
    image_folder_selection_service_dependency: Callable[..., object] | None = None,
    browser_image_selection_service_dependency: Callable[..., object] | None = None,
    image_sequence_canonical_service_dependency: Callable[..., object] | None = None,
    iterative_image_import_service_dependency: Callable[..., object] | None = None,
    image_storage_service_dependency: Callable[..., object] | None = None,
    image_review_service_dependency: Callable[..., object] | None = None,
    image_grid_review_service_dependency: Callable[..., object] | None = None,
    grid_shadow_service_dependency: Callable[..., object] | None = None,
    image_geometry_rollout_service_dependency: Callable[..., object] | None = None,
    virtual_grid_geometry_service_dependency: Callable[..., object] | None = None,
    image_review_cohort_service_dependency: Callable[..., object] | None = None,
    layout_import_report_service_dependency: Callable[..., object] | None = None,
    mobile_release_service_dependency: Callable[..., object] | None = None,
    review_service_dependency: Callable[..., object] | None = None,
    reviewer_access_service_dependency: Callable[..., object] | None = None,
    reviewer_ingress_service_dependency: Callable[..., object] | None = None,
    reviewer_work_lifecycle_service_dependency: Callable[..., object] | None = None,
    symbol_reference_service_dependency: Callable[..., object] | None = None,
    symbol_cell_review_query_service_dependency: Callable[..., object] | None = None,
    virtual_cell_preview_service_dependency: Callable[..., object] | None = None,
    symbol_cell_review_mutation_service_dependency: Callable[..., object] | None = None,
    symbol_cell_review_bulk_operation_service_dependency: Callable[..., object] | None = None,
    symbol_cell_review_backfill_service_dependency: Callable[..., object] | None = None,
    unreadable_board_review_service_dependency: Callable[..., object] | None = None,
    worker_lane_status_service_dependency: Callable[..., object] | None = None,
    verified_training_cohort_service_dependency: Callable[..., object] | None = None,
    symbol_model_iteration_service_dependency: Callable[..., object] | None = None,
    lab_symbol_candidate_import_service_dependency: Callable[..., object] | None = None,
    symbol_model_registry_service_dependency: Callable[..., object] | None = None,
    grid_calibration_service_dependency: Callable[..., object] | None = None,
    page_geometry_override_service_dependency: Callable[..., object] | None = None,
    image_import_geometry_guard_service_dependency: Callable[..., object] | None = None,
    board_cell_geometry_pending_service_dependency: Callable[..., object] | None = None,
    remote_manual_selection_host_service_dependency: Callable[..., object] | None = None,
    remote_manual_selection_access_service_dependency: Callable[..., object] | None = None,
    remote_manual_selection_control_service_dependency: Callable[..., object] | None = None,
    remote_manual_selection_transfer_service_dependency: Callable[..., object] | None = None,
    remote_manual_selection_recovery_service_dependency: Callable[..., object] | None = None,
    super_game_series_service_dependency: Callable[..., object] | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    custom_service_dependency_supplied = any(
        dependency is not None
        for dependency in (
            management_access_service_dependency,
            catalog_service_dependency,
            board_search_service_dependency,
            board_search_approximate_win_service_dependency,
            board_search_board_detail_service_dependency,
            board_search_board_view_service_dependency,
            board_search_share_access_service_dependency,
            board_search_share_correction_service_dependency,
            cleanup_service_dependency,
            rules_service_dependency,
            dataset_service_dependency,
            job_service_dependency,
            image_selection_service_dependency,
            semi_automatic_image_selection_service_dependency,
            v7_label_geometry_calibration_service_dependency,
            image_job_service_dependency,
            image_folder_selection_service_dependency,
            browser_image_selection_service_dependency,
            image_sequence_canonical_service_dependency,
            iterative_image_import_service_dependency,
            image_storage_service_dependency,
            image_review_service_dependency,
            image_grid_review_service_dependency,
            grid_shadow_service_dependency,
            image_geometry_rollout_service_dependency,
            virtual_grid_geometry_service_dependency,
            image_review_cohort_service_dependency,
            layout_import_report_service_dependency,
            mobile_release_service_dependency,
            review_service_dependency,
            reviewer_access_service_dependency,
            reviewer_ingress_service_dependency,
            reviewer_work_lifecycle_service_dependency,
            symbol_reference_service_dependency,
            symbol_cell_review_query_service_dependency,
            virtual_cell_preview_service_dependency,
            symbol_cell_review_mutation_service_dependency,
            symbol_cell_review_bulk_operation_service_dependency,
            symbol_cell_review_backfill_service_dependency,
            unreadable_board_review_service_dependency,
            worker_lane_status_service_dependency,
            verified_training_cohort_service_dependency,
            symbol_model_iteration_service_dependency,
            lab_symbol_candidate_import_service_dependency,
            symbol_model_registry_service_dependency,
            grid_calibration_service_dependency,
            page_geometry_override_service_dependency,
            image_import_geometry_guard_service_dependency,
            board_cell_geometry_pending_service_dependency,
            remote_manual_selection_host_service_dependency,
            remote_manual_selection_access_service_dependency,
            remote_manual_selection_control_service_dependency,
            remote_manual_selection_transfer_service_dependency,
            remote_manual_selection_recovery_service_dependency,
            super_game_series_service_dependency,
        )
    )
    database_engine = create_database_engine(resolved_settings)
    session_factory = create_session_factory(database_engine)
    # TASK-0797: routes that name only a game-owned row id find its game here.
    game_entity_locator = GameEntityLocator(session_factory)
    # TASK-0795: schema-owner sessions only for partition DDL of a new game.
    # NullPool: no owner connection stays open between requests.
    owner_engine = create_owner_database_engine(resolved_settings)
    owner_session_factory = create_owner_session_factory(owner_engine)
    # TASK-0797: mobile releases span games (see CrossGameOwnerSession).
    cross_game_owner_session_factory = create_cross_game_owner_session_factory(owner_engine)

    def default_catalog_service_dependency() -> Iterator[CatalogService]:
        with session_factory() as session:
            try:
                yield CatalogService(
                    SqlAlchemyCatalogRepository(
                        session,
                        GameStorageRouter(),
                        partition_ddl_session_factory=owner_session_factory,
                    ),
                    shape_geometry_readiness_resolver=GlobalShapeGeometryReadinessResolver(
                        SqlAlchemyGlobalGeometryLibraryRepository(session)
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_catalog_dependency = catalog_service_dependency or default_catalog_service_dependency

    def default_board_search_service_dependency() -> Iterator[BoardSearchService]:
        with session_factory() as session:
            try:
                yield BoardSearchService(
                    SqlAlchemyBoardSearchProjectionRepository(session),
                    SqlAlchemySuperGameMarkerRepository(session),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_dependency = (
        board_search_service_dependency or default_board_search_service_dependency
    )

    def default_board_search_approximate_win_service_dependency() -> Iterator[
        BoardSearchApproximateWinService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchApproximateWinService(
                    SqlAlchemyBoardSearchApproximateWinRepository(session),
                    SqlAlchemySuperGameMarkerRepository(session),
                    read_snapshot=True,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_approximate_win_dependency = (
        board_search_approximate_win_service_dependency
        or default_board_search_approximate_win_service_dependency
    )

    def default_board_search_board_detail_service_dependency() -> Iterator[
        BoardSearchBoardDetailService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchBoardDetailService(
                    SqlAlchemyBoardSearchApproximateWinRepository(session),
                    SqlAlchemySuperGameMarkerRepository(session),
                    read_snapshot=True,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_board_detail_dependency = (
        board_search_board_detail_service_dependency
        or default_board_search_board_detail_service_dependency
    )
    board_search_board_view_cache = BoardSearchBoardViewCache(resolved_settings.artifact_root)

    def board_search_share_readiness(game_id: UUID) -> None:
        # Its own session: the readiness read binds game data routing, which
        # must not leak into the control-plane session that writes the share.
        with session_factory() as readiness_session:
            try:
                assert_board_search_share_ready(
                    SqlAlchemyBoardSearchApproximateWinRepository(readiness_session), game_id
                )
            finally:
                readiness_session.rollback()

    def default_board_search_share_access_service_dependency() -> Iterator[
        BoardSearchShareAccessService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchShareAccessService(
                    SqlAlchemyBoardSearchShareRepository(session),
                    readiness=board_search_share_readiness,
                    enabled=resolved_settings.board_search_share_enabled,
                )
                session.commit()
            except BoardSearchShareError:
                # Failed codes and lockouts are security state and must
                # survive the error response.
                session.commit()
                raise
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_share_access_dependency = (
        board_search_share_access_service_dependency
        or default_board_search_share_access_service_dependency
    )

    def default_board_search_share_query_log_service_dependency() -> Iterator[
        BoardSearchShareQueryLogService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchShareQueryLogService(
                    SqlAlchemyBoardSearchShareQueryRepository(session)
                )
            finally:
                session.rollback()

    resolved_board_search_share_query_log_service_dependency = (
        board_search_share_query_log_service_dependency
        or default_board_search_share_query_log_service_dependency
    )
    resolved_board_search_share_query_log = (
        board_search_share_query_log or SqlAlchemyBoardSearchShareQueryLog(session_factory)
    )
    resolved_board_search_share_rate_limiter = (
        board_search_share_rate_limiter or BoardSearchShareRateLimiter()
    )

    def default_board_search_share_correction_service_dependency() -> Iterator[
        BoardSearchShareCorrectionService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchShareCorrectionService(
                    SqlAlchemyBoardSearchShareCorrectionRepository(session)
                )
                session.commit()
            except SQLAlchemyError as error:
                session.rollback()
                raise BoardSearchShareUnavailableError(
                    "BOARD_SEARCH_SHARE_CORRECTION_UNAVAILABLE",
                    "The correction could not be committed; retry the same operation.",
                ) from error
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_share_correction_dependency = (
        board_search_share_correction_service_dependency
        or default_board_search_share_correction_service_dependency
    )

    def default_board_search_board_view_service_dependency() -> Iterator[
        BoardSearchBoardViewService
    ]:
        with session_factory() as session:
            try:
                yield BoardSearchBoardViewService(
                    SqlAlchemyBoardSearchApproximateWinRepository(session),
                    board_search_board_view_cache,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_board_search_board_view_dependency = (
        board_search_board_view_service_dependency
        or default_board_search_board_view_service_dependency
    )

    def default_cleanup_service_dependency(request: Request) -> Iterator[CleanupService]:
        # A mobile release references several games; its cleanup runs on the
        # cross-game owner session, game cleanups stay game-bound (TASK-0797).
        factory = (
            cross_game_owner_session_factory
            if request.url.path.startswith("/api/v1/admin/mobile-releases/")
            else session_factory
        )
        with factory() as session:
            repository = SqlAlchemyCleanupRepository(session, cross_game_owner_session_factory)
            artifact_store = ManagedCleanupArtifactStore(resolved_settings.artifact_root)
            service = CleanupService(repository, artifact_store)
            committed = False
            try:
                artifact_store.recover(repository.completed_board_source_quarantine_keys())
                yield service
                session.commit()
                committed = True
                service.finalize_committed_artifacts()
            except BaseException:
                if not committed:
                    session.rollback()
                    service.restore_uncommitted_artifacts()
                raise

    resolved_cleanup_dependency = cleanup_service_dependency or default_cleanup_service_dependency

    def default_symbol_reference_service_dependency() -> Iterator[ApprovedSymbolReferenceService]:
        with session_factory() as session:
            try:
                yield ApprovedSymbolReferenceService(
                    SqlAlchemyApprovedSymbolReferenceRepository(session),
                    ManagedSymbolReferenceArtifactStore(resolved_settings.artifact_root),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_reference_dependency = (
        symbol_reference_service_dependency or default_symbol_reference_service_dependency
    )

    def default_symbol_cell_review_query_service_dependency() -> Iterator[
        SymbolCellReviewQueryService
    ]:
        with session_factory() as session:
            try:
                yield SymbolCellReviewQueryService(
                    SqlAlchemySymbolCellReviewQueryRepository(session),
                    page_statement_timeout_ms=(
                        resolved_settings.symbol_review_page_statement_timeout_ms
                    ),
                    counts_statement_timeout_ms=(
                        resolved_settings.symbol_review_counts_statement_timeout_ms
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_cell_review_query_dependency = (
        symbol_cell_review_query_service_dependency
        or default_symbol_cell_review_query_service_dependency
    )

    virtual_cell_preview_service = VirtualCellPreviewService(resolved_settings.artifact_root)

    def default_virtual_cell_preview_service_dependency() -> Iterator[VirtualCellPreviewService]:
        yield virtual_cell_preview_service

    resolved_virtual_cell_preview_dependency = (
        virtual_cell_preview_service_dependency or default_virtual_cell_preview_service_dependency
    )

    def default_symbol_cell_review_bulk_operation_service_dependency() -> Iterator[
        SymbolCellReviewBulkOperationService
    ]:
        with session_factory() as session:
            try:
                yield SymbolCellReviewBulkOperationService(
                    SqlAlchemySymbolCellReviewBulkOperationRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_cell_review_bulk_operation_dependency = (
        symbol_cell_review_bulk_operation_service_dependency
        or default_symbol_cell_review_bulk_operation_service_dependency
    )

    def default_symbol_cell_review_mutation_service_dependency() -> Iterator[
        SymbolCellReviewMutationService
    ]:
        with session_factory() as session:
            try:
                yield SymbolCellReviewMutationService(
                    SqlAlchemySymbolCellReviewMutationRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_cell_review_mutation_dependency = (
        symbol_cell_review_mutation_service_dependency
        or default_symbol_cell_review_mutation_service_dependency
    )

    def default_symbol_cell_review_backfill_service_dependency() -> Iterator[
        SymbolCellReviewBackfillService
    ]:
        with session_factory() as session:
            try:
                yield SymbolCellReviewBackfillService(
                    SqlAlchemySymbolCellReviewBackfillRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_cell_review_backfill_dependency = (
        symbol_cell_review_backfill_service_dependency
        or default_symbol_cell_review_backfill_service_dependency
    )

    def default_unreadable_board_review_service_dependency() -> Iterator[
        UnreadableBoardReviewService
    ]:
        with session_factory() as session:
            try:
                yield UnreadableBoardReviewService(
                    SqlAlchemyUnreadableBoardReviewRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_unreadable_board_review_dependency = (
        unreadable_board_review_service_dependency
        or default_unreadable_board_review_service_dependency
    )

    def default_rules_service_dependency() -> Iterator[RulesService]:
        with session_factory() as session:
            try:
                yield RulesService(SqlAlchemyRulesRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_rules_dependency = rules_service_dependency or default_rules_service_dependency

    def default_dataset_service_dependency(request: Request) -> Iterator[DatasetService]:
        with session_factory() as session:
            try:
                _assign_request_entity_game(session, request, game_entity_locator)
                yield DatasetService(SqlAlchemyDatasetRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_dataset_dependency = dataset_service_dependency or default_dataset_service_dependency

    def default_job_service_dependency() -> Iterator[JobService]:
        with session_factory() as session:
            service = JobService(
                SqlAlchemyJobRepository(session),
                LayoutImportSourceInspector(
                    resolved_settings.import_root,
                    max_bytes=resolved_settings.import_max_bytes,
                ),
                SqlAlchemySymbolModelSnapshotResolver(
                    session,
                    artifact_root=resolved_settings.artifact_root,
                ),
                SqlAlchemyGridProfileSnapshotResolver(
                    session, artifact_root=resolved_settings.artifact_root
                ),
                artifact_root=resolved_settings.artifact_root,
                page_geometry_override_snapshot_resolver=PageGeometryOverrideService(
                    SqlAlchemyPageGeometryOverrideRepository(session)
                ),
                shape_geometry_v2_profile_snapshot_resolver=(
                    SqlAlchemyGlobalGeometryProfileSnapshotResolver(
                        SqlAlchemyGlobalGeometryLibraryRepository(session)
                    )
                ),
                deletion_artifact_store=ManagedImageSelectionDeletionArtifactStore(
                    artifact_root=resolved_settings.artifact_root,
                    import_root=resolved_settings.import_root,
                ),
            )
            try:
                yield service
                session.commit()
                service.finalize_pending_deletions()
            except BaseException:
                session.rollback()
                service.restore_pending_deletions()
                raise

    resolved_job_dependency = job_service_dependency or default_job_service_dependency

    def default_worker_lane_status_service_dependency() -> Iterator[WorkerLaneStatusService]:
        yield WorkerLaneStatusService(SqlAlchemyWorkerLaneRepository(session_factory))

    resolved_worker_lane_status_dependency = (
        worker_lane_status_service_dependency or default_worker_lane_status_service_dependency
    )

    def default_image_selection_service_dependency(
        request: Request,
    ) -> Iterator[ImageSelectionService]:
        with session_factory() as session:
            try:
                _assign_request_entity_game(session, request, game_entity_locator)
                yield ImageSelectionService(
                    SqlAlchemyImageSelectionRepository(session),
                    artifact_root=resolved_settings.artifact_root,
                    browser_upload_root=resolved_settings.import_root,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_selection_dependency = (
        image_selection_service_dependency or default_image_selection_service_dependency
    )

    controlled_folder_picker = WindowsFolderPicker(
        Path.cwd() / "scripts" / "select_local_image_folder.ps1"
    )
    default_image_folder_selection_service = ImageFolderSelectionService(
        local_source_picker or controlled_folder_picker
    )
    resolved_image_folder_selection_dependency = image_folder_selection_service_dependency or (
        lambda: default_image_folder_selection_service
    )
    storage_capacity_policy = StorageCapacityPolicy(
        warning_bytes=resolved_settings.storage_warning_gib * GIB,
        automatic_gc_bytes=resolved_settings.storage_automatic_gc_gib * GIB,
        target_bytes=resolved_settings.storage_target_gib * GIB,
        hard_reserve_bytes=resolved_settings.storage_hard_reserve_gib * GIB,
    )
    storage_retention_policy = StorageRetentionPolicy(
        warning_free_bytes=resolved_settings.storage_warning_gib * GIB,
        automatic_gc_free_bytes=resolved_settings.storage_automatic_gc_gib * GIB,
        target_free_bytes=resolved_settings.storage_target_gib * GIB,
        hard_reserve_bytes=resolved_settings.storage_hard_reserve_gib * GIB,
    )
    automatic_storage_gc_service = StorageGcService(
        SqlAlchemyStorageGcRepository(session_factory),
        StorageGcArtifactStore(
            resolved_settings.artifact_root,
            resolved_settings.import_root,
        ),
        policy=storage_retention_policy,
    )
    storage_capacity_guard = StorageCapacityGuard(
        {
            "artifact": resolved_settings.artifact_root,
            "import": resolved_settings.import_root,
        },
        policy=storage_capacity_policy,
        ensure_automatic_gc=(
            None
            if resolved_settings.storage_gc_observe_only
            else automatic_storage_gc_service.ensure_automatic_run
        ),
    )
    default_browser_image_selection_service = BrowserImageSelectionService(
        default_image_folder_selection_service,
        resolved_settings.import_root,
        max_bytes=resolved_settings.browser_layout_import_max_bytes,
        photo_selection_max_bytes=resolved_settings.image_selection_max_bytes,
        retention=SqlAlchemyBrowserStagingRetentionRepository(session_factory),
        capacity_guard=storage_capacity_guard,
    )
    resolved_browser_image_selection_dependency = browser_image_selection_service_dependency or (
        lambda: default_browser_image_selection_service
    )

    def default_semi_automatic_image_selection_service_dependency() -> Iterator[
        SemiAutomaticImageSelectionService
    ]:
        with session_factory() as session:
            try:
                yield SemiAutomaticImageSelectionService(
                    SqlAlchemySemiAutomaticSelectionRepository(session),
                    default_browser_image_selection_service,
                    enabled=resolved_settings.semi_automatic_image_selection_enabled,
                    artifact_root=resolved_settings.artifact_root,
                    folder_selection=default_image_folder_selection_service,
                    v7_output_base=resolved_settings.v7_review_output_base,
                    output_picker=controlled_folder_picker.choose,
                    v7_artifacts=V7PilotArtifacts(
                        resolved_settings.v7_label_geometry_runtime_root,
                        resolved_settings.v7_selection_ocr_model_root,
                        acceptance_scope=resolved_settings.v7_pilot_acceptance_scope,
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_semi_automatic_image_selection_dependency = (
        semi_automatic_image_selection_service_dependency
        or default_semi_automatic_image_selection_service_dependency
    )
    default_v7_label_geometry_calibration_service = V7LabelGeometryCalibrationService(
        runtime_root=resolved_settings.v7_label_geometry_runtime_root,
        corpus_manifest_path=resolved_settings.v7_label_geometry_corpus_manifest,
        read_only=resolved_settings.v7_label_geometry_read_only,
    )
    resolved_v7_label_geometry_calibration_dependency = (
        v7_label_geometry_calibration_service_dependency
        or (lambda: default_v7_label_geometry_calibration_service)
    )
    default_remote_manual_selection_host_service = RemoteManualSelectionHostService(
        controlled_folder_picker,
        operator_local_control_root=(
            resolved_settings.artifact_root / "remote-manual-selection-access"
        ),
    )
    resolved_remote_manual_selection_host_dependency = (
        remote_manual_selection_host_service_dependency
        or (lambda: default_remote_manual_selection_host_service)
    )

    remote_manual_selection_host_parameter = Depends(
        resolved_remote_manual_selection_host_dependency
    )

    def default_remote_manual_selection_access_service_dependency(
        host_service: Annotated[
            RemoteManualSelectionHostService,
            remote_manual_selection_host_parameter,
        ],
    ) -> Iterator[RemoteManualSelectionAccessService]:
        with session_factory() as session:
            try:
                yield RemoteManualSelectionAccessService(
                    SqlAlchemyRemoteManualSelectionAccessRepository(session),
                    host_service,
                )
                session.commit()
            except RemoteManualSelectionAccessError:
                # Failed access attempts, lockout and successful lease mutations
                # are security state and must survive the HTTP error response.
                session.commit()
                raise
            except BaseException:
                session.rollback()
                raise

    resolved_remote_manual_selection_access_dependency = (
        remote_manual_selection_access_service_dependency
        or default_remote_manual_selection_access_service_dependency
    )
    remote_manual_selection_control_rate_limiter = RemoteManualSelectionControlRateLimiter()

    def default_remote_manual_selection_control_service_dependency(
        host_service: Annotated[
            RemoteManualSelectionHostService,
            remote_manual_selection_host_parameter,
        ],
    ) -> Iterator[RemoteManualSelectionControlService]:
        with session_factory() as session:
            try:
                yield RemoteManualSelectionControlService(
                    SqlAlchemyRemoteManualSelectionRepository(session),
                    RemoteManualSelectionAccessService(
                        SqlAlchemyRemoteManualSelectionAccessRepository(session),
                        host_service,
                    ),
                    host_service,
                    rate_limiter=remote_manual_selection_control_rate_limiter,
                    deselect_enabled=resolved_settings.remote_selection_deselect_enabled,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_remote_manual_selection_control_dependency = (
        remote_manual_selection_control_service_dependency
        or default_remote_manual_selection_control_service_dependency
    )
    remote_manual_selection_transfer_limits = RemoteManualSelectionTransferLimits(
        max_file_bytes=resolved_settings.remote_selection_max_file_bytes,
        max_session_bytes=resolved_settings.remote_selection_max_session_bytes,
        max_active_session_transfers=(
            resolved_settings.remote_selection_max_active_session_transfers
        ),
        max_active_global_transfers=(
            resolved_settings.remote_selection_max_active_global_transfers
        ),
        upload_timeout_seconds=resolved_settings.remote_selection_upload_timeout_seconds,
    )
    remote_manual_selection_transfer_gate = RemoteManualSelectionTransferGate(
        remote_manual_selection_transfer_limits
    )

    def default_remote_manual_selection_transfer_service_dependency(
        host_service: Annotated[
            RemoteManualSelectionHostService,
            remote_manual_selection_host_parameter,
        ],
    ) -> Iterator[RemoteManualSelectionTransferService]:
        with session_factory() as session:
            try:
                yield RemoteManualSelectionTransferService(
                    SqlAlchemyRemoteManualSelectionRepository(session),
                    RemoteManualSelectionAccessService(
                        SqlAlchemyRemoteManualSelectionAccessRepository(session),
                        host_service,
                    ),
                    host_service,
                    limits=remote_manual_selection_transfer_limits,
                    gate=remote_manual_selection_transfer_gate,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_remote_manual_selection_transfer_dependency = (
        remote_manual_selection_transfer_service_dependency
        or default_remote_manual_selection_transfer_service_dependency
    )

    def default_remote_manual_selection_recovery_service_dependency(
        host_service: Annotated[
            RemoteManualSelectionHostService,
            remote_manual_selection_host_parameter,
        ],
    ) -> Iterator[RemoteManualSelectionRecoveryService]:
        with session_factory() as session:
            try:
                yield RemoteManualSelectionRecoveryService(
                    SqlAlchemyRemoteManualSelectionRepository(session),
                    host_service,
                    upload_timeout=timedelta(
                        seconds=resolved_settings.remote_selection_upload_timeout_seconds
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_remote_manual_selection_recovery_dependency = (
        remote_manual_selection_recovery_service_dependency
        or default_remote_manual_selection_recovery_service_dependency
    )

    def default_image_sequence_canonical_service_dependency() -> Iterator[
        ImageSequenceCanonicalService
    ]:
        with session_factory() as session:
            try:
                yield ImageSequenceCanonicalService(
                    SqlAlchemyImageSequenceCanonicalRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_sequence_canonical_dependency = (
        image_sequence_canonical_service_dependency
        or default_image_sequence_canonical_service_dependency
    )

    def default_iterative_image_import_service_dependency(
        request: Request,
    ) -> Iterator[IterativeImageImportService]:
        with session_factory() as session:
            try:
                _assign_request_entity_game(session, request, game_entity_locator)
                image_selection_service = ImageSelectionService(
                    SqlAlchemyImageSelectionRepository(session),
                    artifact_root=resolved_settings.artifact_root,
                    browser_upload_root=resolved_settings.import_root,
                )
                job_service = JobService(
                    SqlAlchemyJobRepository(session),
                    None,
                    SqlAlchemySymbolModelSnapshotResolver(
                        session,
                        artifact_root=resolved_settings.artifact_root,
                    ),
                    SqlAlchemyGridProfileSnapshotResolver(
                        session, artifact_root=resolved_settings.artifact_root
                    ),
                    artifact_root=resolved_settings.artifact_root,
                    shape_geometry_v2_profile_snapshot_resolver=(
                        SqlAlchemyGlobalGeometryProfileSnapshotResolver(
                            SqlAlchemyGlobalGeometryLibraryRepository(session)
                        )
                    ),
                )
                yield IterativeImageImportService(
                    SqlAlchemyIterativeImageImportRepository(session),
                    image_selection_service,
                    job_service,
                    artifact_root=resolved_settings.artifact_root,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_iterative_image_import_dependency = (
        iterative_image_import_service_dependency
        or default_iterative_image_import_service_dependency
    )

    def default_image_job_service_dependency() -> Iterator[ImageJobOperationsService]:
        with session_factory() as session:
            try:
                yield ImageJobOperationsService(SqlAlchemyImageJobOperationsRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_job_dependency = (
        image_job_service_dependency or default_image_job_service_dependency
    )

    def default_image_storage_service_dependency() -> Iterator[ImageStorageService]:
        with session_factory() as session:
            try:
                yield ImageStorageService(
                    SqlAlchemyImageJobOperationsRepository(session),
                    ImageArtifactStore(
                        resolved_settings.artifact_root,
                        resolved_settings.import_root,
                    ),
                    StorageGcService(
                        SqlAlchemyStorageGcRepository(session_factory),
                        StorageGcArtifactStore(
                            resolved_settings.artifact_root,
                            resolved_settings.import_root,
                        ),
                        policy=storage_retention_policy,
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_storage_dependency = (
        image_storage_service_dependency or default_image_storage_service_dependency
    )

    def default_image_review_service_dependency() -> Iterator[OperationalImageReviewService]:
        with session_factory() as session:
            try:
                # D-467 S6 (TASK-0796): the Reviewer's board geometry
                # correction delegates to the virtual path in this session.
                yield OperationalImageReviewService(
                    SqlAlchemyOperationalImageReviewRepository(session),
                    virtual_geometry=VirtualGridGeometryService(
                        SqlAlchemyVirtualGridGeometryRepository(session),
                        resolved_settings.artifact_root,
                    ),
                    board_import_coverage_repository=SqlAlchemyBoardImportCoverageRepository(
                        session
                    ),
                    geometry_completeness_repository=(
                        SqlAlchemyImageGeometryCompletenessRepository(session)
                    ),
                    geometry_completeness_state_repository=(
                        SqlAlchemyImageGeometryCompletenessStateRepository(session)
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_review_dependency = (
        image_review_service_dependency or default_image_review_service_dependency
    )

    def default_image_grid_review_service_dependency() -> Iterator[ImageGridReviewService]:
        with session_factory() as session:
            try:
                yield ImageGridReviewService(SqlAlchemyImageGridReviewRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_grid_review_dependency = (
        image_grid_review_service_dependency or default_image_grid_review_service_dependency
    )
    grid_audit_proposal_store = FileGridAuditProposalStore(resolved_settings.artifact_root)
    grid_audit_symbol_store = FileGridAuditSymbolSuggestionStore(resolved_settings.artifact_root)

    def default_grid_shadow_service_dependency() -> Iterator[GridShadowService]:
        with session_factory() as session:
            try:
                yield GridShadowService(
                    SqlAlchemyGridShadowRepository(session),
                    ManagedGridEngineModelStore(resolved_settings.artifact_root),
                    enabled=resolved_settings.grid_shadow_enabled,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_grid_shadow_dependency = (
        grid_shadow_service_dependency or default_grid_shadow_service_dependency
    )

    def default_grid_audit_proposal_service_dependency() -> Iterator[GridAuditProposalService]:
        # TASK-0840: read-only; the session is rolled back, never committed.
        with session_factory() as session:
            try:
                yield GridAuditProposalService(
                    grid_audit_proposal_store,
                    SqlAlchemyGridAuditBoardReader(session),
                    grid_audit_symbol_store,
                )
            finally:
                session.rollback()

    def default_image_geometry_rollout_service_dependency() -> Iterator[
        ImageGeometryRolloutService
    ]:
        with session_factory() as session:
            try:
                yield ImageGeometryRolloutService(
                    SqlAlchemyImageGeometryRolloutBackfillRepository(session)
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_geometry_rollout_dependency = (
        image_geometry_rollout_service_dependency
        or default_image_geometry_rollout_service_dependency
    )

    manual_board_cell_symbol_predictor = ManualBoardCellSymbolPredictor(
        Path(__file__).resolve().parents[4],
        resolved_settings.artifact_root,
    )

    def default_virtual_grid_geometry_service_dependency() -> Iterator[VirtualGridGeometryService]:
        with session_factory() as session:
            try:
                yield VirtualGridGeometryService(
                    SqlAlchemyVirtualGridGeometryRepository(session),
                    resolved_settings.artifact_root,
                    symbol_predictor=manual_board_cell_symbol_predictor,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_virtual_grid_geometry_dependency = (
        virtual_grid_geometry_service_dependency or default_virtual_grid_geometry_service_dependency
    )

    def default_image_review_cohort_service_dependency() -> Iterator[VerifiedCohortService]:
        with session_factory() as session:
            try:
                yield VerifiedCohortService(
                    SqlAlchemyOperationalImageReviewRepository(session),
                    SqlAlchemyVerifiedCohortExportRepository(session),
                    VerifiedCohortArtifactStore(resolved_settings.artifact_root),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_review_cohort_dependency = (
        image_review_cohort_service_dependency or default_image_review_cohort_service_dependency
    )

    def default_verified_training_cohort_service_dependency() -> Iterator[
        VerifiedTrainingCohortService
    ]:
        with session_factory() as session:
            try:
                yield VerifiedTrainingCohortService(
                    SqlAlchemyOperationalImageReviewRepository(session),
                    SqlAlchemyVerifiedTrainingCohortRepository(session),
                    VerifiedTrainingCohortArtifactStore(resolved_settings.artifact_root),
                    SqlAlchemySymbolCellTrainingSourceRepository(
                        session, resolved_settings.artifact_root
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_verified_training_cohort_dependency = (
        verified_training_cohort_service_dependency
        or default_verified_training_cohort_service_dependency
    )

    def default_symbol_model_iteration_service_dependency() -> Iterator[
        SymbolModelIterationService
    ]:
        with session_factory() as session:
            try:
                yield SymbolModelIterationService(
                    SqlAlchemySymbolModelIterationRepository(
                        session, resolved_settings.artifact_root
                    )
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_model_iteration_dependency = (
        symbol_model_iteration_service_dependency
        or default_symbol_model_iteration_service_dependency
    )

    def default_symbol_model_registry_service_dependency() -> Iterator[SymbolModelRegistryService]:
        with session_factory() as session:
            try:
                yield SymbolModelRegistryService(
                    SqlAlchemySymbolModelRegistryRepository(
                        session,
                        artifact_root=resolved_settings.artifact_root,
                    )
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_symbol_model_registry_dependency = (
        symbol_model_registry_service_dependency or default_symbol_model_registry_service_dependency
    )

    def default_lab_symbol_candidate_import_dependency() -> Iterator[
        LabSymbolCandidateImportService
    ]:
        with session_factory() as session:
            try:
                yield LabSymbolCandidateImportService(
                    SqlAlchemyLabSymbolCandidateImportRepository(session),
                    resolved_settings.artifact_root,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_lab_symbol_candidate_import_dependency = (
        lab_symbol_candidate_import_service_dependency
        or default_lab_symbol_candidate_import_dependency
    )

    def default_grid_calibration_service_dependency() -> Iterator[GridCalibrationService]:
        with session_factory() as session:
            try:
                yield GridCalibrationService(SqlAlchemyGridCalibrationRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_grid_calibration_dependency = (
        grid_calibration_service_dependency or default_grid_calibration_service_dependency
    )

    def default_page_geometry_override_service_dependency() -> Iterator[
        PageGeometryOverrideService
    ]:
        with session_factory() as session:
            try:
                yield PageGeometryOverrideService(SqlAlchemyPageGeometryOverrideRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_page_geometry_override_dependency = (
        page_geometry_override_service_dependency
        or default_page_geometry_override_service_dependency
    )

    def default_image_import_geometry_guard_service_dependency(
        request: Request,
    ) -> Iterator[ImageImportGeometryGuardService]:
        with session_factory() as session:
            try:
                _assign_request_entity_game(session, request, game_entity_locator)
                yield ImageImportGeometryGuardService(
                    SqlAlchemyImageImportGeometryGuardRepository(session),
                    resolved_settings.artifact_root,
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_image_import_geometry_guard_dependency = (
        image_import_geometry_guard_service_dependency
        or default_image_import_geometry_guard_service_dependency
    )

    def default_board_cell_geometry_pending_service_dependency() -> Iterator[
        BoardCellGeometryPendingService
    ]:
        with session_factory() as session:
            try:
                # D-467 (TASK-0790): the Reviewer's manual resolution delegates
                # to the virtual source path in the same transaction.
                yield BoardCellGeometryPendingService(
                    SqlAlchemyBoardCellGeometryPendingRepository(session),
                    ManagedBoardCellProcessingManifestStore(resolved_settings.artifact_root),
                    virtual_geometry=VirtualGridGeometryService(
                        SqlAlchemyVirtualGridGeometryRepository(session),
                        resolved_settings.artifact_root,
                        symbol_predictor=manual_board_cell_symbol_predictor,
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_board_cell_geometry_pending_dependency = (
        board_cell_geometry_pending_service_dependency
        or default_board_cell_geometry_pending_service_dependency
    )

    def default_layout_import_report_service_dependency() -> Iterator[LayoutImportReportService]:
        with session_factory() as session:
            try:
                yield LayoutImportReportService(SqlAlchemyLayoutImportReportRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_layout_import_report_dependency = (
        layout_import_report_service_dependency or default_layout_import_report_service_dependency
    )

    def default_mobile_release_service_dependency() -> Iterator[MobileReleaseService]:
        with cross_game_owner_session_factory() as session:
            try:
                yield MobileReleaseService(SqlAlchemyMobileReleaseRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_mobile_release_dependency = (
        mobile_release_service_dependency or default_mobile_release_service_dependency
    )

    def default_review_service_dependency(request: Request) -> Iterator[ReviewService]:
        with session_factory() as session:
            try:
                _assign_request_entity_game(session, request, game_entity_locator)
                yield ReviewService(SqlAlchemyReviewRepository(session, session_factory))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_review_dependency = review_service_dependency or default_review_service_dependency

    def reviewer_access_service(session: Session) -> ReviewerAccessService:
        return ReviewerAccessService(
            lambda: _active_reviewer_origin(
                resolved_settings.reviewer_origin,
            ),
            SqlAlchemyReviewerAccessRepository(session, game_entity_locator),
        )

    def default_reviewer_access_service_dependency() -> Iterator[ReviewerAccessService]:
        with session_factory() as session:
            try:
                yield reviewer_access_service(session)
                session.commit()
            except ReviewerAccessError:
                # Failed unlock attempts and the fifth-attempt lock are
                # security events that must survive the HTTP error response.
                session.commit()
                raise
            except BaseException:
                session.rollback()
                raise

    resolved_reviewer_access_dependency = (
        reviewer_access_service_dependency or default_reviewer_access_service_dependency
    )
    project_root = Path(__file__).resolve().parents[4]
    reviewer_ingress_service = ReviewerIngressService(
        project_root,
        # The Reviewer it starts must proxy to this API, whatever its port.
        api_origin=_loopback_api_origin(resolved_settings.host, resolved_settings.port),
    )
    resolved_reviewer_ingress_dependency = reviewer_ingress_service_dependency or (
        lambda: reviewer_ingress_service
    )

    other_games_online = OtherGamesOnlineAssignments(session_factory, game_entity_locator)

    def recover_other_games_online(current_game_id: UUID | None) -> None:
        # TASK-0797: one transaction reads one game; each other game's expired
        # online leases are recovered (and their access sessions revoked) in
        # that game's own short transaction.
        for game_id in game_entity_locator.registered_games():
            if game_id == current_game_id:
                continue
            with game_storage_scope(game_id), session_factory() as side_session:
                try:
                    access = reviewer_access_service(side_session)

                    def revoke(
                        assignment: ReviewerWorkAssignment,
                        access: ReviewerAccessService = access,
                    ) -> None:
                        if assignment.reviewer_access_session_id is not None:
                            access.revoke(assignment.reviewer_access_session_id)

                    ReviewerWorkAssignmentService(
                        SqlAlchemyReviewerWorkAssignmentRepository(
                            side_session, game_entity_locator
                        )
                    ).recover_expired_online(before_expire=revoke)
                    side_session.commit()
                except GameStorageRoutingError as error:
                    # A game under storage maintenance is read-only; its
                    # expired leases are recovered on a later request. Its
                    # unexpired leases still count for the cap and the tunnel.
                    side_session.rollback()
                    LOGGER.warning(
                        "Skipped Reviewer lease recovery of game %s: %s", game_id, error.code
                    )
                except BaseException:
                    side_session.rollback()
                    raise

    def default_reviewer_work_lifecycle_service_dependency() -> Iterator[
        ReviewerWorkLifecycleService
    ]:
        with session_factory() as session:
            try:
                yield ReviewerWorkLifecycleService(
                    ReviewerWorkAssignmentService(
                        SqlAlchemyReviewerWorkAssignmentRepository(
                            session,
                            game_entity_locator,
                            other_games_online=other_games_online,
                        )
                    ),
                    reviewer_access_service(session),
                    reviewer_ingress_service,
                    recover_other_games=recover_other_games_online,
                    stop_shared_ingress=lambda: stop_unused_shared_ingress(
                        database_engine, reviewer_ingress_service
                    ),
                )
                session.commit()
            except BaseException:
                session.rollback()
                raise

    resolved_reviewer_work_lifecycle_dependency = (
        reviewer_work_lifecycle_service_dependency
        or default_reviewer_work_lifecycle_service_dependency
    )
    api_host = (
        f"[{resolved_settings.host}]" if resolved_settings.host == "::1" else resolved_settings.host
    )
    application = FastAPI(
        title=resolved_settings.application_name,
        version=resolved_settings.version,
        servers=[
            {
                "url": f"http://{api_host}:{resolved_settings.port}",
                "description": "Local Admin API",
            }
        ],
    )

    @application.middleware("http")
    async def bind_game_storage_request(
        request: Request, call_next: Callable[[Request], Any]
    ) -> Any:
        game_id = game_id_from_request(request.url.path, request.query_params)
        if game_id is None:
            return await call_next(request)
        with game_storage_scope(game_id):
            return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(
            loopback_origin_aliases(resolved_settings.admin_origin)
            | loopback_origin_aliases(resolved_settings.reviewer_origin)
        ),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=[
            "Accept",
            "Authorization",
            "Content-Type",
            IMAGE_RELATIVE_PATH_HEADER,
            MANUAL_FILE_NAME_HEADER,
            ADMIN_INTENT_HEADER,
            ADMIN_CONFIRMATION_HEADER,
            ADMIN_TARGET_HEADER,
            "X-Game-Id",
            "X-Source-Checksum-Sha256",
            "X-Source-Relative-Path",
            "X-Geometry-Manifest-Checksum-Sha256",
        ],
    )
    application.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin=resolved_settings.admin_origin,
        reviewer_origin=resolved_settings.reviewer_origin,
        audit_log=AppendOnlyAdminAuditLog(resolved_settings.artifact_root),
    )

    def default_management_service_dependency() -> Iterator[ManagementService]:
        # Control-plane metadata spans games; deliberately no game-store session.
        with Session(database_engine) as session:
            try:
                yield ManagementService(SqlAlchemyManagementRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    @application.exception_handler(ManagementError)
    async def management_error_handler(request: Request, error: ManagementError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={
                "code": error.code,
                "message": str(error),
                "details": {},
            },
        )

    application.include_router(
        create_management_router(
            management_service_dependency or default_management_service_dependency
        )
    )

    def default_management_stake_service_dependency() -> Iterator[ManagementStakeService]:
        with session_factory() as session:
            service = ManagementStakeService(SqlAlchemyManagementStakeRepository(session))
            try:
                yield service
                service.before_commit()
                session.commit()
            except BaseException:
                session.rollback()
                raise

    application.include_router(
        create_management_stake_router(
            management_stake_service_dependency or default_management_stake_service_dependency
        )
    )

    def default_management_access_dependency() -> Iterator[ManagementAccessService]:
        with Session(database_engine) as session:
            try:
                yield ManagementAccessService(
                    SqlAlchemyManagementSessionRepository(session),
                    enabled=resolved_settings.management_share_enabled,
                )
                session.commit()
            except ManagementAccessError as error:
                if error.code in {"MANAGEMENT_CODE_INVALID", "MANAGEMENT_CODE_LOCKED"}:
                    session.commit()  # Persist failed codes only, never a failed domain mutation.
                else:
                    session.rollback()
                raise
            except BaseException:
                session.rollback()
                raise

    @application.exception_handler(ManagementAccessError)
    async def management_access_error_handler(
        request: Request, error: ManagementAccessError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=error.status,
            content={"code": error.code, "message": str(error), "details": {}},
        )

    def public_management_guard_dependency(
        request: Request,
        expected: Annotated[UUID | None, Header(alias=MANAGEMENT_EXPECTED_SESSION_HEADER)] = None,
        expected_asset: Annotated[UUID | None, Query(alias="expectedSessionId")] = None,
        token: Annotated[str | None, Cookie(alias=MANAGEMENT_COOKIE)] = None,
        _proxy: None = Depends(require_management_proxy),
    ) -> Iterator[ManagementPublicGuard]:
        asset = request.url.path.endswith(("/image", "/view"))
        identity = expected_asset if asset else expected
        if (
            identity is None
            or token is None
            or (expected is not None and expected_asset is not None and expected != expected_asset)
        ):
            raise invalid_access()

        # Plain metadata sessions never implicitly bind all assigned games.
        def plain_session() -> Session:
            return Session(database_engine)

        factory: Callable[[], Session] = (
            session_factory
            if "/game/" in request.url.path
            and not (
                "/results/" in request.url.path
                or "/stakes" in request.url.path
                and request.method == "GET"
            )
            else plain_session
        )
        with factory() as session:
            try:
                guard = ManagementPublicGuard(
                    session,
                    ManagementAccessService(
                        SqlAlchemyManagementSessionRepository(session),
                        enabled=resolved_settings.management_share_enabled,
                    ),
                    token,
                    identity,
                )
                machine = request.path_params.get("machine_id")
                game = request.path_params.get("game_id") or request.query_params.get("gameId")
                if machine and game:
                    historical = (
                        "/results/" in request.url.path
                        or request.url.path.endswith("/journal")
                        or "/stakes" in request.url.path
                        and request.method == "GET"
                    )
                    guard.game(UUID(str(machine)), UUID(str(game)), live=not historical)
                yield guard
                guard.before_commit()  # flush structural writes, then check fresh expiry/token.
                session.commit()
            except BaseException:
                session.rollback()
                raise

    def public_management_structure_dependency(
        guard: Annotated[
            ManagementPublicGuard, Depends(public_management_guard_dependency, scope="function")
        ],
    ) -> ManagementService:
        return ManagementService(
            SqlAlchemyManagementRepository(guard.session), actor=guard.context.actor
        )

    def public_management_stake_dependency(
        guard: Annotated[
            ManagementPublicGuard, Depends(public_management_guard_dependency, scope="function")
        ],
    ) -> Iterator[ManagementStakeService]:
        service = ManagementStakeService(
            SqlAlchemyManagementStakeRepository(guard.session, revalidate=guard.revalidate),
            actor=guard.context.actor,
        )
        yield service
        service.before_commit()

    application.include_router(
        create_management_sessions_router(
            management_access_service_dependency or default_management_access_dependency,
            resolved_reviewer_ingress_dependency,
        )
    )
    application.include_router(
        create_management_public_structure_router(public_management_structure_dependency)
    )
    application.include_router(
        create_management_public_stake_router(public_management_stake_dependency)
    )
    application.include_router(
        create_management_public_router(
            access_dependency=management_access_service_dependency
            or default_management_access_dependency,
            guard_dependency=public_management_guard_dependency,
            catalog_dependency=resolved_catalog_dependency,
            reference_dependency=resolved_symbol_reference_dependency,
            view_dependency=resolved_board_search_board_view_dependency,
            artifact_root=resolved_settings.artifact_root,
        )
    )

    def default_super_game_series_service_dependency() -> Iterator[SuperGameSeriesService]:
        with session_factory() as session:
            try:
                yield SuperGameSeriesService(SqlAlchemySuperGameSeriesRepository(session))
                session.commit()
            except BaseException:
                session.rollback()
                raise

    @application.exception_handler(SuperGameSeriesError)
    async def handle_super_game_series_error(
        _request: Request, error: SuperGameSeriesError
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, SuperGameSeriesNotFoundError):
            status_code = 404
        elif isinstance(error, SuperGameSeriesConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    application.include_router(
        create_super_game_series_router(
            super_game_series_service_dependency or default_super_game_series_service_dependency
        ),
        prefix="/api/v1",
    )

    application.state.database_engine = database_engine
    application.include_router(
        create_api_router(
            resolved_settings,
            resolved_catalog_dependency,
            resolved_board_search_dependency,
            resolved_board_search_approximate_win_dependency,
            resolved_cleanup_dependency,
            resolved_rules_dependency,
            resolved_dataset_dependency,
            resolved_job_dependency,
            resolved_image_selection_dependency,
            resolved_semi_automatic_image_selection_dependency,
            resolved_v7_label_geometry_calibration_dependency,
            resolved_image_job_dependency,
            resolved_image_folder_selection_dependency,
            resolved_browser_image_selection_dependency,
            resolved_iterative_image_import_dependency,
            resolved_image_sequence_canonical_dependency,
            resolved_image_storage_dependency,
            resolved_image_review_dependency,
            resolved_image_grid_review_dependency,
            resolved_image_geometry_rollout_dependency,
            resolved_virtual_grid_geometry_dependency,
            resolved_image_review_cohort_dependency,
            resolved_layout_import_report_dependency,
            resolved_mobile_release_dependency,
            resolved_review_dependency,
            resolved_reviewer_access_dependency,
            resolved_reviewer_ingress_dependency,
            resolved_reviewer_work_lifecycle_dependency,
            resolved_symbol_reference_dependency,
            resolved_symbol_cell_review_query_dependency,
            resolved_virtual_cell_preview_dependency,
            resolved_symbol_cell_review_mutation_dependency,
            resolved_symbol_cell_review_bulk_operation_dependency,
            resolved_symbol_cell_review_backfill_dependency,
            resolved_unreadable_board_review_dependency,
            resolved_worker_lane_status_dependency,
            resolved_verified_training_cohort_dependency,
            resolved_symbol_model_iteration_dependency,
            resolved_symbol_model_registry_dependency,
            resolved_grid_calibration_dependency,
            resolved_page_geometry_override_dependency,
            resolved_image_import_geometry_guard_dependency,
            resolved_board_cell_geometry_pending_dependency,
            resolved_remote_manual_selection_host_dependency,
            resolved_remote_manual_selection_access_dependency,
            resolved_remote_manual_selection_control_dependency,
            resolved_remote_manual_selection_transfer_dependency,
            resolved_remote_manual_selection_recovery_dependency,
            resolved_settings.artifact_root,
            board_search_board_detail_service_dependency=(
                resolved_board_search_board_detail_dependency
            ),
            board_search_board_view_service_dependency=resolved_board_search_board_view_dependency,
            board_search_share_access_service_dependency=(
                resolved_board_search_share_access_dependency
            ),
            board_search_share_query_log_service_dependency=(
                resolved_board_search_share_query_log_service_dependency
            ),
            board_search_share_correction_service_dependency=(
                resolved_board_search_share_correction_dependency
            ),
            board_search_share_query_log=resolved_board_search_share_query_log,
            board_search_share_rate_limiter=resolved_board_search_share_rate_limiter,
            grid_audit_proposal_service_dependency=(default_grid_audit_proposal_service_dependency),
            grid_shadow_service_dependency=resolved_grid_shadow_dependency,
            lab_symbol_candidate_import_service_dependency=resolved_lab_symbol_candidate_import_dependency,
        )
    )
    if not custom_service_dependency_supplied:
        startup_recovery = RemoteManualSelectionRecoveryRunner(
            session_factory,
            default_remote_manual_selection_host_service,
            enabled=resolved_settings.remote_selection_recovery_enabled,
            upload_timeout=timedelta(
                seconds=resolved_settings.remote_selection_upload_timeout_seconds
            ),
            limit=resolved_settings.remote_selection_recovery_limit,
        )

        def reconcile_remote_manual_selection_on_startup() -> None:
            try:
                application.state.remote_selection_startup_recovery = (
                    startup_recovery.run_bounded_cycle()
                )
            except Exception:  # noqa: BLE001 - startup recovery is best-effort and bounded.
                application.state.remote_selection_startup_recovery = None
                LOGGER.warning(
                    "remote_selection_startup_recovery_failed code=%s",
                    "REMOTE_SELECTION_RECOVERY_STARTUP_FAILED",
                )

        application.router.add_event_handler(
            "startup",
            reconcile_remote_manual_selection_on_startup,
        )

    @application.exception_handler(CatalogError)
    async def handle_catalog_error(
        _request: Request,
        error: CatalogError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, CatalogNotFoundError):
            status_code = 404
        elif isinstance(error, CatalogConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(GameStorageRoutingError)
    async def handle_game_storage_routing_error(
        _request: Request,
        error: GameStorageRoutingError,
    ) -> JSONResponse:
        status_code = 409
        if error.code in {"GAME_NOT_FOUND", "GAME_SCOPED_RESOURCE_NOT_FOUND"}:
            status_code = 404
        elif error.code in {
            "GAME_STORAGE_LOCATION_INVALID",
            "GAME_STORAGE_SESSION_SCOPE_CONFLICT",
            "GAME_STORAGE_TABLE_NOT_OWNED",
            "GAME_SCOPED_RESOURCE_AMBIGUOUS",
        }:
            status_code = 500
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    @application.exception_handler(GamePartitionLifecycleError)
    async def handle_game_partition_lifecycle_error(
        _request: Request,
        error: GamePartitionLifecycleError,
    ) -> JSONResponse:
        status_code = 404 if error.code == "GAME_NOT_FOUND" else 409
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    @application.exception_handler(BoardSearchError)
    async def handle_board_search_error(
        _request: Request,
        error: BoardSearchError,
    ) -> JSONResponse:
        status_code = 422
        if error.code == "GAME_NOT_FOUND":
            status_code = 404
        elif error.code in {
            "BOARD_SEARCH_PROJECTION_INCOMPLETE",
            # TASK-0652 approximate-win range calculator: the starting board
            # is out of the game's sequence, or the range cannot be
            # calculated from the current data/rules state. Never a client
            # input-shape error, so 409 rather than 422.
            "APPROXIMATE_WIN_START_OUT_OF_RANGE",
            "APPROXIMATE_WIN_RULES_NOT_PUBLISHED",
            "APPROXIMATE_WIN_RULES_INVALID",
            "APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES",
            # D-470 board detail and view: the board changed since the search
            # document was written, or its source image no longer matches.
            "BOARD_SEARCH_BOARD_REVISION_CONFLICT",
            "BOARD_SEARCH_BOARD_REFRESH_UNSUPPORTED",
            "BOARD_SEARCH_BOARD_VIEW_CACHE_UNSAFE",
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_PATH_UNSAFE",
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_MEDIA_TYPE_UNSUPPORTED",
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_CHECKSUM_DRIFT",
        }:
            status_code = 409
        elif error.code in {
            "BOARD_SEARCH_BOARD_NOT_FOUND",
            "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_NOT_FOUND",
            # TASK-0932 Admin draft preview: the selected rules version is not
            # a draft or published version of this game.
            "APPROXIMATE_WIN_RULES_VERSION_NOT_FOUND",
        }:
            status_code = 404
        # "APPROXIMATE_WIN_SPIN_COUNT_INVALID" and any other/unknown code
        # fall through to the 422 default (malformed query parameters).
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(SymbolCellReviewError)
    async def handle_symbol_cell_review_error(
        _request: Request,
        error: SymbolCellReviewError,
    ) -> JSONResponse:
        status_code = 422
        if error.code in {
            "GAME_NOT_FOUND",
            "SYMBOL_CELL_REVIEW_CELL_NOT_FOUND",
            "SYMBOL_CELL_REVIEW_ASSET_NOT_FOUND",
            "SYMBOL_CELL_REVIEW_BULK_OPERATION_NOT_FOUND",
        }:
            status_code = 404
        elif error.code in {
            "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
            "SYMBOL_CELL_REVIEW_CATALOG_REVISION_STALE",
            "SYMBOL_CELL_REVIEW_CURSOR_SCOPE_INVALID",
            "SYMBOL_CELL_REVIEW_CURSOR_DIRECTION_CONFLICT",
            "SYMBOL_CELL_REVIEW_CURRENT_OWNER_CONFLICT",
            "SYMBOL_CELL_REVIEW_REVISION_CONFLICT",
            "SYMBOL_CELL_REVIEW_CROP_DRIFT",
            "SYMBOL_CELL_REVIEW_ASSET_CHECKSUM_MISMATCH",
            "SYMBOL_CELL_REVIEW_BULK_IDEMPOTENCY_CONFLICT",
            "SYMBOL_CELL_REVIEW_BULK_FILTER_STALE",
            "SYMBOL_CELL_REVIEW_BULK_TARGET_NOT_CURRENT",
            "SYMBOL_CELL_REVIEW_BULK_TARGET_STALE",
        }:
            status_code = 409
        elif error.code in {
            "SYMBOL_CELL_REVIEW_QUERY_TIMEOUT",
            "SYMBOL_CELL_REVIEW_QUERY_CANCELLED",
        }:
            status_code = 503
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    @application.exception_handler(GridShadowError)
    async def handle_grid_shadow_error(request: Request, error: GridShadowError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    @application.exception_handler(ImageGridReviewError)
    async def handle_image_grid_review_error(
        _request: Request,
        error: ImageGridReviewError,
    ) -> JSONResponse:
        status_code = 422
        if error.code in {
            "GAME_NOT_FOUND",
            "IMAGE_GRID_REVIEW_ITEM_NOT_FOUND",
            "GRID_AUDIT_PROPOSALS_NOT_FOUND",
            "GRID_AUDIT_PROPOSAL_ITEM_NOT_FOUND",
        }:
            status_code = 404
        elif error.code in {
            "IMAGE_GRID_REVIEW_PROJECTION_INCOMPLETE",
            "IMAGE_GRID_REVIEW_CURSOR_SCOPE_INVALID",
            "IMAGE_GRID_REVIEW_CURSOR_DIRECTION_CONFLICT",
            "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
            "IMAGE_GRID_REVIEW_GEOMETRY_REVISION_CONFLICT",
            "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
            "IMAGE_GRID_REVIEW_SOURCE_DRIFT",
            "IMAGE_GRID_REVIEW_TOPOLOGY_CONFLICT",
            "IMAGE_GRID_REVIEW_CURRENT_OWNER_CONFLICT",
            "IMAGE_GRID_REVIEW_CORRECTION_REQUIRED",
            "GRID_AUDIT_PROPOSALS_CHECKSUM_MISMATCH",
            "GRID_AUDIT_SYMBOL_SUGGESTIONS_CHECKSUM_MISMATCH",
            # The Reviewer's operational geometry contract (409 before the
            # delegation to the virtual path, D-467 S6 / TASK-0796).
            "IMAGE_REVIEW_GEOMETRY_IDEMPOTENCY_CONFLICT",
            "IMAGE_REVIEW_SUPERSEDED",
        }:
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(CleanupError)
    async def handle_cleanup_error(
        _request: Request,
        error: CleanupError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, CleanupNotFoundError):
            status_code = 404
        elif isinstance(error, CleanupConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ImageReviewError)
    async def handle_image_review_error(
        _request: Request,
        error: ImageReviewError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, ImageReviewNotFoundError):
            status_code = 404
        elif isinstance(error, ImageReviewConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ImageSelectionError)
    async def handle_image_selection_error(
        _request: Request,
        error: ImageSelectionError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, ImageSelectionNotFoundError):
            status_code = 404
        elif isinstance(error, ImageSelectionConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(IterativeImageImportError)
    async def handle_iterative_image_import_error(
        _request: Request,
        error: IterativeImageImportError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, IterativeImageImportNotFoundError):
            status_code = 404
        elif isinstance(error, IterativeImageImportConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(RulesError)
    async def handle_rules_error(
        _request: Request,
        error: RulesError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, RulesNotFoundError):
            status_code = 404
        elif isinstance(error, RulesConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(DatasetError)
    async def handle_dataset_error(
        _request: Request,
        error: DatasetError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, DatasetNotFoundError):
            status_code = 404
        elif isinstance(error, DatasetConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(V7LabelGeometryCalibrationApiError)
    async def handle_v7_label_geometry_calibration_error(
        _request: Request,
        error: V7LabelGeometryCalibrationApiError,
    ) -> JSONResponse:
        status_code = 422
        if error.code in {
            "V7_CALIBRATION_SESSION_NOT_FOUND",
            "V7_CALIBRATION_SOURCE_NOT_FOUND",
            "V7_CALIBRATION_PROFILE_NOT_FOUND",
            "V7_VALIDATION_REPORT_NOT_FOUND",
            "V7_VALIDATION_ADOPTION_NOT_FOUND",
        }:
            status_code = 404
        elif error.code in {
            "V7_CALIBRATION_READ_ONLY",
            "V7_CALIBRATION_SESSION_RECOVERY_REQUIRED",
            "V7_CALIBRATION_SESSION_EXISTS",
            "V7_CALIBRATION_SESSION_BLOCKED",
            "V7_CALIBRATION_SESSION_SOURCE_DRIFT",
            "V7_CALIBRATION_SESSION_REVISION_CONFLICT",
            "V7_CALIBRATION_SESSION_OPERATION_ID_CONFLICT",
            "V7_CALIBRATION_SESSION_RECOVERY_CONFLICT",
            "V7_CALIBRATION_SOURCE_CHECKSUM_CONFLICT",
            "V7_CALIBRATION_SOURCE_DUPLICATE",
            "V7_CALIBRATION_PROFILE_CONFLICT",
            "V7_VALIDATION_OPERATION_ID_CONFLICT",
            "V7_VALIDATION_REPORT_CONFLICT",
            "V7_VALIDATION_CORPUS_DRIFT",
            "V7_VALIDATION_ADOPTION_OPERATION_ID_CONFLICT",
            "V7_VALIDATION_ADOPTION_CONFLICT",
            "V7_VALIDATION_ADOPTION_IDENTITY_CONFLICT",
            "V7_VALIDATION_ADOPTION_OBSERVER_CONFLICT",
            "V7_VALIDATION_ADOPTION_CORPUS_DRIFT",
        }:
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": str(error), "details": {}},
        )

    @application.exception_handler(JobError)
    async def handle_job_error(
        _request: Request,
        error: JobError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, JobNotFoundError):
            status_code = 404
        elif isinstance(error, JobConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(BoardSearchShareError)
    async def handle_board_search_share_error(
        _request: Request,
        error: BoardSearchShareError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, BoardSearchShareNotFoundError):
            status_code = 404
        elif isinstance(error, BoardSearchShareAuthenticationError):
            status_code = 401
        elif isinstance(error, BoardSearchShareAuthorizationError):
            status_code = 403
        elif isinstance(error, BoardSearchShareConflictError):
            status_code = 409
        elif isinstance(error, BoardSearchShareRateLimitError):
            status_code = 429
        elif isinstance(error, BoardSearchShareUnavailableError):
            status_code = 503
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": error.details},
        )

    @application.exception_handler(RemoteManualSelectionError)
    async def handle_remote_manual_selection_error(
        _request: Request,
        error: RemoteManualSelectionError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, RemoteManualSelectionAccessNotFoundError):
            status_code = 404
        elif isinstance(error, RemoteManualSelectionAuthenticationError):
            status_code = 401
        elif isinstance(error, RemoteManualSelectionAuthorizationError):
            status_code = 403
        elif isinstance(
            error,
            RemoteManualSelectionRateLimitError | RemoteManualSelectionTransferRateLimitError,
        ):
            status_code = 429
        elif isinstance(error, RemoteManualSelectionTransferLimitError):
            status_code = 413
        elif isinstance(error, RemoteManualSelectionTransferTimeoutError):
            status_code = 408
        elif error.code == "REMOTE_SELECTION_TRANSFER_CONTENT_TYPE_INVALID":
            status_code = 415
        elif isinstance(
            error,
            RemoteManualSelectionConflictError | RemoteManualSelectionLeaseConflictError,
        ):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(MobileReleaseError)
    async def handle_mobile_release_error(
        _request: Request,
        error: MobileReleaseError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, MobileReleaseNotFoundError):
            status_code = 404
        elif isinstance(error, MobileReleaseConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ReviewError)
    async def handle_review_error(
        _request: Request,
        error: ReviewError,
    ) -> JSONResponse:
        status_code = 422
        if isinstance(error, ReviewNotFoundError):
            status_code = 404
        elif isinstance(error, ReviewConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(ReviewerAccessError)
    async def handle_reviewer_access_error(
        _request: Request,
        error: ReviewerAccessError,
    ) -> JSONResponse:
        status_code = {
            "REVIEWER_ACCESS_CODE_INVALID": 401,
            "REVIEWER_SESSION_LOCKED": 401,
            "REVIEWER_SESSION_REVOKED": 401,
            "REVIEWER_TOKEN_INVALID": 401,
            "REVIEWER_TOKEN_REQUIRED": 401,
            "REVIEWER_SCOPE_FORBIDDEN": 403,
            "REVIEWER_SESSION_NOT_FOUND": 404,
            "REVIEWER_SCOPE_INVALID": 422,
            "REVIEWER_SESSION_LIFETIME_INVALID": 422,
        }.get(error.code, 422)
        return JSONResponse(
            status_code=status_code,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(ReviewerIngressError)
    async def handle_reviewer_ingress_error(
        _request: Request,
        error: ReviewerIngressError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content={"code": error.code, "message": error.message, "details": {}},
        )

    @application.exception_handler(ReviewerWorkAssignmentError)
    async def handle_reviewer_work_assignment_error(
        _request: Request,
        error: ReviewerWorkAssignmentError,
    ) -> JSONResponse:
        status_code = 422
        if error.code == "REVIEWER_ASSIGNMENT_NOT_FOUND":
            status_code = 404
        elif isinstance(error, ReviewerWorkAssignmentConflictError):
            status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={
                "code": error.code,
                "message": error.message,
                "details": error.details,
            },
        )

    @application.exception_handler(RequestValidationError)
    async def handle_request_validation_error(
        _request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        error_types = {str(item["type"]) for item in error.errors()}
        # An explicit domain refusal raised inside request validation keeps its
        # own code (D-467: a removed legacy image engine policy).
        explicit_codes = error_types & _EXPLICIT_VALIDATION_ERROR_CODES
        return JSONResponse(
            status_code=422,
            content={
                "code": (
                    next(iter(explicit_codes)) if len(explicit_codes) == 1 else "VALIDATION_ERROR"
                ),
                "message": "Request data is invalid.",
                "details": {
                    "errors": [
                        {
                            "location": [str(part) for part in item["loc"]],
                            "message": item["msg"],
                            "type": item["type"],
                        }
                        for item in error.errors()
                    ]
                },
            },
        )

    generated_openapi = application.openapi

    def local_admin_openapi() -> dict[str, Any]:
        schema = generated_openapi()
        augment_admin_security_openapi(schema)
        return schema

    application.openapi = local_admin_openapi  # type: ignore[method-assign]

    return application


_EXPLICIT_VALIDATION_ERROR_CODES = frozenset({LEGACY_IMAGE_IMPORT_ENGINE_POLICY_ERROR})


def _active_reviewer_origin(local_origin: str) -> str:
    state_path = Path(__file__).resolve().parents[4] / ".runtime" / "remote-reviewer.json"
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        public_origin = str(payload.get("publicOrigin", "")).rstrip("/")
        parsed = urlparse(public_origin)
        if (
            parsed.scheme == "https"
            and parsed.hostname is not None
            and parsed.hostname.endswith(".trycloudflare.com")
            and parsed.path in {"", "/"}
        ):
            return public_origin
    except (OSError, ValueError, TypeError):
        pass
    return local_origin.rstrip("/")


app = create_app()
