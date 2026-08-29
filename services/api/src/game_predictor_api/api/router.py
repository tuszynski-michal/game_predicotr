"""Composition root for versioned HTTP routes."""

from collections.abc import Callable
from pathlib import Path

from fastapi import APIRouter

from game_predictor_api.api.board_cell_geometry_pending import (
    create_board_cell_geometry_pending_router,
)
from game_predictor_api.api.board_search import create_board_search_router
from game_predictor_api.api.catalog import create_catalog_router
from game_predictor_api.api.cleanup import create_cleanup_router
from game_predictor_api.api.datasets import create_datasets_router
from game_predictor_api.api.grid_calibration import create_grid_calibration_router
from game_predictor_api.api.health import create_health_router
from game_predictor_api.api.image_grid_reviews import create_image_grid_reviews_router
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.api.image_jobs import create_image_jobs_router
from game_predictor_api.api.image_review_cohorts import (
    create_image_review_cohort_router,
)
from game_predictor_api.api.image_reviews import create_image_reviews_router
from game_predictor_api.api.image_selections import create_image_selections_router
from game_predictor_api.api.image_storage import create_image_storage_router
from game_predictor_api.api.image_symbol_reviews import create_image_symbol_reviews_router
from game_predictor_api.api.jobs import create_jobs_router
from game_predictor_api.api.layout_import_reports import (
    create_layout_import_reports_router,
)
from game_predictor_api.api.mobile_releases import (
    create_mobile_releases_router,
)
from game_predictor_api.api.remote_manual_selections import (
    create_remote_manual_selections_admin_router,
    create_remote_manual_selections_public_router,
)
from game_predictor_api.api.reviewer_access import create_reviewer_access_router
from game_predictor_api.api.reviews import create_reviews_router
from game_predictor_api.api.rules import create_rules_router
from game_predictor_api.api.symbol_model_iterations import create_symbol_model_iteration_router
from game_predictor_api.api.symbol_references import create_symbol_references_router
from game_predictor_api.api.verified_training_cohorts import (
    create_verified_training_cohort_router,
)
from game_predictor_api.api.worker_lanes import create_worker_lanes_router
from game_predictor_api.config import ApiSettings


def create_api_router(
    settings: ApiSettings,
    catalog_service_dependency: Callable[..., object],
    board_search_service_dependency: Callable[..., object],
    cleanup_service_dependency: Callable[..., object],
    rules_service_dependency: Callable[..., object],
    dataset_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
    image_selection_service_dependency: Callable[..., object],
    image_job_service_dependency: Callable[..., object],
    image_folder_selection_service_dependency: Callable[..., object],
    browser_image_selection_service_dependency: Callable[..., object],
    iterative_image_import_service_dependency: Callable[..., object],
    image_sequence_canonical_service_dependency: Callable[..., object],
    image_storage_service_dependency: Callable[..., object],
    image_review_service_dependency: Callable[..., object],
    image_grid_review_service_dependency: Callable[..., object],
    image_review_cohort_service_dependency: Callable[..., object],
    layout_import_report_service_dependency: Callable[..., object],
    mobile_release_service_dependency: Callable[..., object],
    review_service_dependency: Callable[..., object],
    reviewer_access_service_dependency: Callable[..., object],
    reviewer_ingress_service_dependency: Callable[..., object],
    reviewer_work_lifecycle_service_dependency: Callable[..., object],
    symbol_reference_service_dependency: Callable[..., object],
    symbol_cell_review_query_service_dependency: Callable[..., object],
    virtual_cell_preview_service_dependency: Callable[..., object],
    symbol_cell_review_mutation_service_dependency: Callable[..., object],
    symbol_cell_review_bulk_operation_service_dependency: Callable[..., object],
    symbol_cell_review_backfill_service_dependency: Callable[..., object],
    unreadable_board_review_service_dependency: Callable[..., object],
    worker_lane_status_service_dependency: Callable[..., object],
    verified_training_cohort_service_dependency: Callable[..., object],
    symbol_model_iteration_service_dependency: Callable[..., object],
    symbol_model_registry_service_dependency: Callable[..., object],
    grid_calibration_service_dependency: Callable[..., object],
    page_geometry_override_service_dependency: Callable[..., object],
    board_cell_geometry_pending_service_dependency: Callable[..., object],
    remote_manual_selection_host_service_dependency: Callable[..., object],
    remote_manual_selection_access_service_dependency: Callable[..., object],
    remote_manual_selection_control_service_dependency: Callable[..., object],
    remote_manual_selection_transfer_service_dependency: Callable[..., object],
    remote_manual_selection_recovery_service_dependency: Callable[..., object],
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_health_router(settings.version))
    router.include_router(
        create_reviewer_access_router(
            reviewer_access_service_dependency,
            catalog_service_dependency,
            job_service_dependency,
            reviewer_ingress_service_dependency,
            reviewer_work_lifecycle_service_dependency,
        )
    )
    router.include_router(create_catalog_router(catalog_service_dependency))
    router.include_router(create_board_search_router(board_search_service_dependency))
    router.include_router(create_cleanup_router(cleanup_service_dependency))
    if settings.remote_manual_selection_host_mapping_enabled:
        router.include_router(
            create_remote_manual_selections_admin_router(
                remote_manual_selection_host_service_dependency,
                remote_manual_selection_access_service_dependency,
                remote_manual_selection_control_service_dependency,
                remote_manual_selection_recovery_service_dependency,
                reviewer_ingress_service_dependency,
            )
        )
        router.include_router(
            create_remote_manual_selections_public_router(
                remote_manual_selection_access_service_dependency,
                remote_manual_selection_control_service_dependency,
                remote_manual_selection_transfer_service_dependency,
            )
        )
    router.include_router(
        create_symbol_references_router(
            symbol_reference_service_dependency,
            settings.artifact_root,
        )
    )
    router.include_router(
        create_image_symbol_reviews_router(
            symbol_cell_review_query_service_dependency,
            virtual_cell_preview_service_dependency,
            symbol_cell_review_mutation_service_dependency,
            symbol_cell_review_bulk_operation_service_dependency,
            symbol_cell_review_backfill_service_dependency,
            unreadable_board_review_service_dependency,
            settings.artifact_root,
        )
    )
    router.include_router(create_rules_router(rules_service_dependency))
    router.include_router(create_datasets_router(dataset_service_dependency))
    router.include_router(create_jobs_router(job_service_dependency))
    router.include_router(create_worker_lanes_router(worker_lane_status_service_dependency))
    router.include_router(
        create_image_selections_router(
            image_selection_service_dependency,
            image_folder_selection_service_dependency,
        )
    )
    router.include_router(
        create_image_imports_router(
            image_folder_selection_service_dependency,
            browser_image_selection_service_dependency,
            job_service_dependency,
            iterative_image_import_service_dependency,
            image_sequence_canonical_service_dependency,
            page_geometry_override_service_dependency,
            artifact_root,
        )
    )
    router.include_router(
        create_image_jobs_router(
            image_job_service_dependency,
            image_storage_service_dependency,
        )
    )
    router.include_router(create_image_storage_router(image_storage_service_dependency))
    router.include_router(
        create_image_reviews_router(
            image_review_service_dependency,
            settings.artifact_root,
            reviewer_access_service_dependency,
            job_service_dependency,
        )
    )
    router.include_router(
        create_image_grid_reviews_router(
            image_grid_review_service_dependency,
            image_review_service_dependency,
            settings.artifact_root,
        )
    )
    router.include_router(create_image_review_cohort_router(image_review_cohort_service_dependency))
    router.include_router(
        create_verified_training_cohort_router(verified_training_cohort_service_dependency)
    )
    router.include_router(
        create_symbol_model_iteration_router(
            symbol_model_iteration_service_dependency,
            symbol_model_registry_service_dependency,
        )
    )
    router.include_router(create_grid_calibration_router(grid_calibration_service_dependency))
    router.include_router(
        create_board_cell_geometry_pending_router(
            board_cell_geometry_pending_service_dependency,
            reviewer_access_service_dependency,
            artifact_root,
        )
    )
    router.include_router(
        create_layout_import_reports_router(layout_import_report_service_dependency)
    )
    router.include_router(
        create_mobile_releases_router(
            mobile_release_service_dependency,
            settings.artifact_root,
        )
    )
    router.include_router(
        create_reviews_router(
            review_service_dependency,
            settings.review_crop_root,
            settings.review_source_root,
        )
    )
    return router
