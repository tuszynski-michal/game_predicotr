"""Standalone loopback API, deliberately independent of production storage."""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from .annotation_contracts import (
    AnnotationRequest,
    AnnotationState,
    BackupRequest,
    BackupResult,
    FamilyRequest,
    SplitRequest,
    TimingReport,
)
from .annotations import AnnotationStore
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
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response


def create_app(catalog: Catalog | None = None, annotation_root: Path | None = None) -> FastAPI:
    application = FastAPI(title="Vision Lab API", version="1.0.0", docs_url=None, redoc_url=None)
    application.add_middleware(LocalBoundary)
    registry = catalog

    def annotations() -> AnnotationStore:
        configured = os.environ.get("VISION_LAB_ANNOTATIONS")
        root = annotation_root or (Path(configured) if configured else None)
        if root is None:
            raise HTTPException(503, "ANNOTATION_DIRECTORY_NOT_CONFIGURED")
        return AnnotationStore(root, current())

    @application.get("/annotations", response_model=AnnotationState, operation_id="get_annotations")
    def get_annotations() -> AnnotationState:
        try:
            return annotations().read()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.post(
        "/annotations", response_model=AnnotationState, operation_id="save_annotation"
    )
    def save_annotation(body: AnnotationRequest) -> AnnotationState:
        try:
            return annotations().mutate(body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.post("/families", response_model=AnnotationState, operation_id="save_family")
    def save_family(body: FamilyRequest) -> AnnotationState:
        try:
            return annotations().mutate(body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.post("/splits", response_model=AnnotationState, operation_id="freeze_split")
    def freeze_split(body: SplitRequest) -> AnnotationState:
        try:
            return annotations().mutate(body)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.post("/backups", response_model=BackupResult, operation_id="create_backup")
    def create_backup(body: BackupRequest) -> BackupResult:
        try:
            return annotations().backup()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

    @application.get("/timings", response_model=list[TimingReport], operation_id="get_timings")
    def get_timings() -> list[TimingReport]:
        try:
            return annotations().timing_report()
        except ValueError as error:
            raise HTTPException(409, str(error)) from error

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
            return current().detect(body.source_id, body.topology, body.preview_board)
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
