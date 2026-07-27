"""Composition root for versioned HTTP routes."""

from collections.abc import Callable

from fastapi import APIRouter

from game_predictor_api.api.catalog import create_catalog_router
from game_predictor_api.api.datasets import create_datasets_router
from game_predictor_api.api.health import create_health_router
from game_predictor_api.api.jobs import create_jobs_router
from game_predictor_api.api.rules import create_rules_router
from game_predictor_api.config import ApiSettings


def create_api_router(
    settings: ApiSettings,
    catalog_service_dependency: Callable[..., object],
    rules_service_dependency: Callable[..., object],
    dataset_service_dependency: Callable[..., object],
    job_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_health_router(settings.version))
    router.include_router(create_catalog_router(catalog_service_dependency))
    router.include_router(create_rules_router(rules_service_dependency))
    router.include_router(create_datasets_router(dataset_service_dependency))
    router.include_router(create_jobs_router(job_service_dependency))
    return router
