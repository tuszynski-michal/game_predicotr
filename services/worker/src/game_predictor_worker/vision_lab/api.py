"""Standalone loopback API, deliberately independent of production storage."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .catalog import Catalog, InvalidImageError
from .contracts import DetectRequest, GeometryResult, SourcePage

HOSTS = {"127.0.0.1:8102", "localhost:8102"}
ORIGINS = {"http://127.0.0.1:3102", "http://localhost:3102"}


class LocalBoundary(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("host") not in HOSTS:
            return Response("HOST_FORBIDDEN", 403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in ORIGINS:
            return Response("ORIGIN_FORBIDDEN", 403)
        if request.method not in {"GET", "HEAD"}:
            if origin not in ORIGINS:
                return Response("ORIGIN_REQUIRED", 403)
            if (
                request.headers.get("content-type", "").split(";", 1)[0].strip()
                != "application/json"
            ):
                return Response("JSON_REQUIRED", 415)
        return await call_next(request)


def create_app(catalog: Catalog | None = None) -> FastAPI:
    application = FastAPI(title="Vision Lab API", version="1.0.0", docs_url=None, redoc_url=None)
    application.add_middleware(LocalBoundary)
    registry = catalog

    def current() -> Catalog:
        nonlocal registry
        if registry is None:
            configured = os.environ.get("VISION_LAB_SNAPSHOT")
            registry = Catalog(Path(configured) if configured else None)
        return registry

    @application.get("/sources", response_model=SourcePage, operation_id="list_sources")
    def sources(
        offset: int = Query(0, ge=0), limit: int = Query(24, ge=1, le=100), game: str | None = None
    ) -> SourcePage:
        items = [s for s in current().sources.values() if game is None or s.game_id == game]
        return SourcePage(
            sources=items[offset : offset + limit],
            total=len(items),
            games={s.game_id: s.game_name for s in current().sources.values()},
        )

    @application.post("/geometry", response_model=GeometryResult, operation_id="detect_geometry")
    def geometry(body: DetectRequest) -> GeometryResult:
        try:
            return current().detect(body.source_id, body.topology)
        except KeyError as error:
            raise HTTPException(404, "SOURCE_NOT_FOUND") from error
        except ValueError as error:
            raise HTTPException(409, "SNAPSHOT_INTEGRITY_ERROR") from error

    @application.get(
        "/assets/{asset_id}",
        operation_id="get_asset",
        responses={200: {"content": {"image/jpeg": {}}}},
    )
    def asset(asset_id: str) -> Response:
        if len(asset_id) != 64 or any(c not in "0123456789abcdef" for c in asset_id):
            raise HTTPException(404, "ASSET_NOT_FOUND")
        try:
            return Response(
                current().asset(asset_id),
                media_type="image/jpeg",
                headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"},
            )
        except KeyError as error:
            raise HTTPException(404, "ASSET_NOT_FOUND") from error
        except InvalidImageError as error:
            raise HTTPException(422, "IMAGE_DECODE_FAILED") from error
        except ValueError as error:
            raise HTTPException(409, "SNAPSHOT_INTEGRITY_ERROR") from error

    return application


app = create_app()
