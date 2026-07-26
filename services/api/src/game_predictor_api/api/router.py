"""Composition root for versioned HTTP routes."""

from fastapi import APIRouter

from game_predictor_api.api.health import create_health_router
from game_predictor_api.config import ApiSettings


def create_api_router(settings: ApiSettings) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    router.include_router(create_health_router(settings.version))
    return router
