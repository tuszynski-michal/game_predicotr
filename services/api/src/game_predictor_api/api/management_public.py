"""Authenticated context and game-bound assets without internal review identities."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Response

from game_predictor_api.api.symbol_references import resolve_symbol_reference_asset
from game_predictor_api.application.board_search_board_detail import BoardSearchBoardViewService
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.application.management_public import ManagementPublicGuard
from game_predictor_api.application.symbol_references import ApprovedSymbolReferenceService
from game_predictor_api.domain.catalog import CatalogNotFoundError
from game_predictor_api.domain.management import ManagementError
from game_predictor_api.domain.management_sessions import (
    MANAGEMENT_COOKIE,
    MANAGEMENT_COOKIE_PATH,
    MANAGEMENT_PROXY_HEADER,
    MANAGEMENT_PROXY_INTENT,
    ManagementAccessError,
)
from game_predictor_api.schemas.board_search_shares import BoardSearchSharePublicSymbolResponse
from game_predictor_api.schemas.management_sessions import (
    ManagementSessionContext,
    ManagementSessionUnlock,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope


def require_management_proxy(
    intent: Annotated[str | None, Header(alias=MANAGEMENT_PROXY_HEADER)] = None,
) -> None:
    if intent != MANAGEMENT_PROXY_INTENT:
        raise ManagementAccessError(
            "MANAGEMENT_PROXY_REQUIRED", "Use the Reviewer application.", 403
        )


def create_management_public_router(
    *,
    access_dependency: Callable[..., object],
    guard_dependency: Callable[..., object],
    catalog_dependency: Callable[..., object],
    reference_dependency: Callable[..., object],
    view_dependency: Callable[..., object],
    artifact_root: Path,
) -> APIRouter:
    router = APIRouter(
        prefix="/api/v1/management-public",
        tags=["management-public"],
        dependencies=[Depends(require_management_proxy)],
    )
    access, guard = (
        Depends(access_dependency, scope="function"),
        Depends(guard_dependency, scope="function"),
    )
    catalog, references, views = (
        Depends(catalog_dependency),
        Depends(reference_dependency),
        Depends(view_dependency),
    )
    base = "/machines/{machine_id}/game/{game_id}"

    @router.post(
        "/sessions/{session_id}/unlock",
        response_model=ManagementSessionContext,
        operation_id="unlockManagementSession",
    )
    def unlock(
        session_id: UUID,
        payload: ManagementSessionUnlock,
        response: Response,
        service: Annotated[ManagementAccessService, access],
    ) -> ManagementSessionContext:
        record, token = service.unlock(session_id, payload.access_code)
        response.set_cookie(
            key=MANAGEMENT_COOKIE,
            value=token,
            max_age=max(0, int((record.expires_at - datetime.now(UTC)).total_seconds())),
            expires=record.expires_at,
            path=MANAGEMENT_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return ManagementSessionContext.from_record(record)

    @router.get(
        "/context",
        response_model=ManagementSessionContext,
        operation_id="getManagementSessionContext",
    )
    def context(auth: Annotated[ManagementPublicGuard, guard]) -> ManagementSessionContext:
        return ManagementSessionContext.from_record(auth.context)

    @router.get(
        base + "/symbols",
        response_model=list[BoardSearchSharePublicSymbolResponse],
        operation_id="listPublicManagementSymbols",
    )
    def symbols(
        machine_id: UUID,
        game_id: UUID,
        auth: Annotated[ManagementPublicGuard, guard],
        service: Annotated[CatalogService, catalog],
        refs: Annotated[ApprovedSymbolReferenceService, references],
    ) -> list[BoardSearchSharePublicSymbolResponse]:
        auth.game(machine_id, game_id, live=True)
        with game_storage_scope(game_id):
            result = []
            for symbol in service.list_symbols(game_id):
                try:
                    revision = (
                        refs.reference(game_id, symbol.id).image_checksum_sha256
                        if symbol.image_path
                        else None
                    )
                except CatalogNotFoundError:
                    revision = None
                result.append(
                    BoardSearchSharePublicSymbolResponse(
                        id=symbol.id,
                        mobile_code=symbol.mobile_code,
                        code=symbol.code,
                        name=symbol.name,
                        name_pl=symbol.name_pl,
                        name_en=symbol.name_en,
                        is_wildcard=symbol.is_wildcard,
                        display_order=symbol.display_order,
                        status=str(symbol.status),
                        image_revision=revision,
                    )
                )
            return result

    @router.get(
        base + "/symbols/{symbol_id}/image",
        response_class=Response,
        operation_id="getPublicManagementSymbolImage",
    )
    def symbol_image(
        machine_id: UUID,
        game_id: UUID,
        symbol_id: UUID,
        revision: Annotated[str, Query(pattern=r"^[a-f0-9]{64}$")],
        auth: Annotated[ManagementPublicGuard, guard],
        refs: Annotated[ApprovedSymbolReferenceService, references],
    ) -> Response:
        auth.game(machine_id, game_id, live=True)
        with game_storage_scope(game_id):
            reference = refs.reference(game_id, symbol_id)
        if reference.image_checksum_sha256 != revision:
            raise ManagementError("MANAGEMENT_SYMBOL_IMAGE_CHANGED", "Reload the symbol image.")
        path = resolve_symbol_reference_asset(
            artifact_root, reference.image_relative_path, reference.image_checksum_sha256
        )
        return Response(
            content=path.read_bytes(),
            media_type="image/png" if path.suffix.lower() == ".png" else "image/jpeg",
            headers={"Cache-Control": "private, no-cache"},
        )

    @router.get(
        base + "/boards/{sequence}/view",
        response_class=Response,
        operation_id="getPublicManagementBoardView",
    )
    def board_view(
        machine_id: UUID,
        game_id: UUID,
        sequence: int,
        checksum: Annotated[
            str, Query(alias="expectedBoardChecksumSha256", pattern=r"^[a-f0-9]{64}$")
        ],
        auth: Annotated[ManagementPublicGuard, guard],
        service: Annotated[BoardSearchBoardViewService, views],
        view_revision: Annotated[
            str | None, Query(alias="viewRevision", pattern=r"^[a-f0-9]{64}$")
        ] = None,
        if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    ) -> Response:
        auth.game(machine_id, game_id, live=True)
        with game_storage_scope(game_id):
            asset = service.view(
                game_id=game_id,
                sequence_number=sequence,
                expected_board_checksum_sha256=checksum,
                expected_view_revision=view_revision,
            )
        headers = {"Cache-Control": "private, no-cache", "ETag": f'"{asset.revision}"'}
        if if_none_match == headers["ETag"]:
            return Response(status_code=304, headers=headers)
        return Response(content=asset.content, media_type=asset.media_type, headers=headers)

    return router
