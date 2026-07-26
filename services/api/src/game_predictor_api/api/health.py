"""Health endpoint exposed outside the future admin resource prefix."""

from fastapi import APIRouter

from game_predictor_api.schemas.health import HealthResponse


def create_health_router(version: str) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get(
        "/health",
        response_model=HealthResponse,
        operation_id="getHealth",
        summary="Get API health",
    )
    def health() -> HealthResponse:
        return HealthResponse(status="ok", version=version)

    return router
