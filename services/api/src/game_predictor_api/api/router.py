"""Composition root for versioned HTTP routes."""

from collections.abc import Callable

from fastapi import APIRouter

from game_predictor_api.api.catalog import create_catalog_router
from game_predictor_api.api.cleanup import create_cleanup_router
from game_predictor_api.api.datasets import create_datasets_router
from game_predictor_api.api.health import create_health_router
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.api.image_jobs import create_image_jobs_router
from game_predictor_api.api.image_review_cohorts import (
    create_image_review_cohort_router,
)
from game_predictor_api.api.image_reviews import create_image_reviews_router
from game_predictor_api.api.image_storage import create_image_storage_router
from game_predictor_api.api.jobs import create_jobs_router
from game_predictor_api.api.layout_import_reports import (
    create_layout_import_reports_router,
)
from game_predictor_api.api.mobile_releases import (
    create_mobile_releases_router,
)
from game_predictor_api.api.reviewer_access import create_reviewer_access_router
from game_predictor_api.api.reviews import create_reviews_router
from game_predictor_api.api.rules import create_rules_router
from game_predictor_api.api.symbol_bootstrap import create_symbol_bootstrap_router
from game_predictor_api.config import ApiSettings


def create_api_router(
    settings: ApiSettings,
    catalog_service_dependency: Callable[..., object],
    cleanup_service_dependency: Callable[..., object],
    rules_service_dependency: Callable[..., object],
    dataset_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
    image_job_service_dependency: Callable[..., object],
    image_folder_selection_service_dependency: Callable[..., object],
    image_storage_service_dependency: Callable[..., object],
    image_review_service_dependency: Callable[..., object],
    image_review_cohort_service_dependency: Callable[..., object],
    layout_import_report_service_dependency: Callable[..., object],
    mobile_release_service_dependency: Callable[..., object],
    review_service_dependency: Callable[..., object],
    reviewer_access_service_dependency: Callable[..., object],
    reviewer_ingress_service_dependency: Callable[..., object],
    symbol_bootstrap_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_health_router(settings.version))
    router.include_router(
        create_reviewer_access_router(
            reviewer_access_service_dependency,
            catalog_service_dependency,
            job_service_dependency,
            reviewer_ingress_service_dependency,
        )
    )
    router.include_router(create_catalog_router(catalog_service_dependency))
    router.include_router(create_cleanup_router(cleanup_service_dependency))
    router.include_router(
        create_symbol_bootstrap_router(
            symbol_bootstrap_service_dependency,
            settings.artifact_root,
        )
    )
    router.include_router(create_rules_router(rules_service_dependency))
    router.include_router(create_datasets_router(dataset_service_dependency))
    router.include_router(create_jobs_router(job_service_dependency))
    router.include_router(
        create_image_imports_router(
            image_folder_selection_service_dependency,
            job_service_dependency,
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
        )
    )
    router.include_router(create_image_review_cohort_router(image_review_cohort_service_dependency))
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
