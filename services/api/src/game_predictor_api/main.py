"""FastAPI application factory for the local Admin API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from game_predictor_api.api.router import create_api_router
from game_predictor_api.config import ApiSettings, get_settings


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    api_host = (
        f"[{resolved_settings.host}]"
        if resolved_settings.host == "::1"
        else resolved_settings.host
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
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[resolved_settings.admin_origin],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["Accept", "Content-Type"],
    )
    application.include_router(create_api_router(resolved_settings))
    return application


app = create_app()
