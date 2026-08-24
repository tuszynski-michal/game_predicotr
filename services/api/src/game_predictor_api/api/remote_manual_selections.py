"""Purpose-scoped access routes for remote manual image selection."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, Query, Request, Response

from game_predictor_api.application.remote_manual_selection_access import (
    REMOTE_SELECTION_COOKIE_NAME,
    REMOTE_SELECTION_COOKIE_PATH,
    REMOTE_SELECTION_PROXY_INTENT,
    RemoteManualSelectionAccessService,
    RemoteManualSelectionAuthenticationError,
    RemoteManualSelectionAuthorizationError,
)
from game_predictor_api.application.remote_manual_selection_control import (
    RemoteManualSelectionControlService,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionHostService,
)
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferService,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressService,
    ensure_online_reviewer_ingress,
)
from game_predictor_api.domain.remote_manual_selections import RemoteManualSelectionError
from game_predictor_api.schemas.catalog import ErrorResponse
from game_predictor_api.schemas.remote_manual_selections import (
    RemoteManualSelectionBaseCapabilityResponse,
    RemoteManualSelectionBatchCreate,
    RemoteManualSelectionBatchCreatedResponse,
    RemoteManualSelectionBatchResponse,
    RemoteManualSelectionCollectionCreate,
    RemoteManualSelectionCollectionResponse,
    RemoteManualSelectionContextResponse,
    RemoteManualSelectionFileResponse,
    RemoteManualSelectionOperationAppliedResponse,
    RemoteManualSelectionOperationCreate,
    RemoteManualSelectionOperationResponse,
    RemoteManualSelectionSessionCreate,
    RemoteManualSelectionSessionCreatedResponse,
    RemoteManualSelectionSessionListResponse,
    RemoteManualSelectionSessionResponse,
    RemoteManualSelectionSourceItemsCreate,
    RemoteManualSelectionSourceItemsResponse,
    RemoteManualSelectionStateDeltaResponse,
    RemoteManualSelectionTransferResponse,
    RemoteManualSelectionUnlock,
    RemoteManualSelectionWriterLeaseCommand,
)


def create_remote_manual_selections_admin_router(
    host_service_dependency: Callable[..., object],
    access_service_dependency: Callable[..., object],
    ingress_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(prefix="/admin/remote-manual-selections")
    host_service_parameter = Depends(host_service_dependency)
    access_service_parameter = Depends(access_service_dependency)
    ingress_service_parameter = Depends(ingress_service_dependency)

    @router.post(
        "/base-capabilities",
        response_model=RemoteManualSelectionBaseCapabilityResponse,
        operation_id="selectRemoteManualSelectionHostBase",
        summary="Select a local host base for remote manual image selection",
        tags=["remote-manual-selections"],
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def select_host_base(
        service: Annotated[RemoteManualSelectionHostService, host_service_parameter],
    ) -> RemoteManualSelectionBaseCapabilityResponse:
        selected = service.select_base()
        return (
            RemoteManualSelectionBaseCapabilityResponse.cancelled()
            if selected is None
            else RemoteManualSelectionBaseCapabilityResponse.selected(selected)
        )

    @router.post(
        "/sessions",
        response_model=RemoteManualSelectionSessionCreatedResponse,
        status_code=201,
        operation_id="createRemoteManualSelectionSession",
        summary="Create one purpose-scoped remote manual selection session",
        tags=["remote-manual-selections"],
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def create_session(
        payload: RemoteManualSelectionSessionCreate,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_service_parameter],
    ) -> RemoteManualSelectionSessionCreatedResponse:
        ingress_status = ensure_online_reviewer_ingress(ingress)
        return RemoteManualSelectionSessionCreatedResponse.from_created(
            service.create(
                base_capability=payload.base_capability,
                lifetime_minutes=payload.lifetime_minutes,
            ),
            ingress_status,
        )

    @router.get(
        "/sessions",
        response_model=RemoteManualSelectionSessionListResponse,
        operation_id="listRemoteManualSelectionSessions",
        summary="List remote manual selection sessions without secrets",
        tags=["remote-manual-selections"],
    )
    def list_sessions(
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_service_parameter],
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
    ) -> RemoteManualSelectionSessionListResponse:
        ingress_status = ingress.status()
        return RemoteManualSelectionSessionListResponse(
            sessions=[
                RemoteManualSelectionSessionResponse.from_view(item, ingress_status)
                for item in service.list_sessions(limit=limit)
            ]
        )

    @router.get(
        "/sessions/{session_id}",
        response_model=RemoteManualSelectionSessionResponse,
        operation_id="getRemoteManualSelectionSession",
        summary="Read one remote manual selection session without secrets",
        tags=["remote-manual-selections"],
        responses={404: {"model": ErrorResponse}},
    )
    def get_session(
        session_id: UUID,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        ingress: Annotated[ReviewerIngressService, ingress_service_parameter],
    ) -> RemoteManualSelectionSessionResponse:
        return RemoteManualSelectionSessionResponse.from_view(
            service.get_session(session_id),
            ingress.status(),
        )

    @router.post(
        "/sessions/{session_id}/revoke",
        response_model=RemoteManualSelectionSessionResponse,
        operation_id="revokeRemoteManualSelectionSession",
        summary="Immediately revoke one remote manual selection session",
        tags=["remote-manual-selections"],
        responses={404: {"model": ErrorResponse}},
    )
    def revoke_session(
        session_id: UUID,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
    ) -> RemoteManualSelectionSessionResponse:
        # Revocation is a safety operation and must not depend on the optional
        # public ingress process being healthy. A later read projects the current
        # shared ingress URL again if it is available.
        return RemoteManualSelectionSessionResponse.from_view(
            service.revoke(session_id),
            None,
        )

    return router


def create_remote_manual_selections_public_router(
    access_service_dependency: Callable[..., object],
    control_service_dependency: Callable[..., object],
    transfer_service_dependency: Callable[..., object],
) -> APIRouter:
    router = APIRouter(
        prefix="/remote-manual-selections",
        dependencies=[Depends(_require_remote_selection_proxy)],
    )
    access_service_parameter = Depends(access_service_dependency)
    control_service_parameter = Depends(control_service_dependency)
    transfer_service_parameter = Depends(transfer_service_dependency)
    client_header_parameter = Header(alias="X-Remote-Selection-Client")

    @router.post(
        "/sessions/{session_id}/unlock",
        response_model=RemoteManualSelectionContextResponse,
        operation_id="unlockRemoteManualSelectionSession",
        summary="Unlock one purpose-scoped remote manual selection session",
        tags=["remote-manual-selections"],
        responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def unlock_session(
        session_id: UUID,
        payload: RemoteManualSelectionUnlock,
        response: Response,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
    ) -> RemoteManualSelectionContextResponse:
        unlocked = service.unlock(
            session_id=session_id,
            access_code=payload.access_code,
            client_instance_id=payload.client_instance_id,
        )
        max_age = max(0, int((unlocked.context.expires_at - _utc_now()).total_seconds()))
        response.set_cookie(
            key=REMOTE_SELECTION_COOKIE_NAME,
            value=unlocked.access_token,
            max_age=max_age,
            expires=unlocked.context.expires_at,
            path=REMOTE_SELECTION_COOKIE_PATH,
            secure=True,
            httponly=True,
            samesite="strict",
        )
        return RemoteManualSelectionContextResponse.from_context(unlocked.context)

    @router.get(
        "/context",
        response_model=RemoteManualSelectionContextResponse,
        operation_id="getRemoteManualSelectionContext",
        summary="Read the authenticated remote manual selection context",
        tags=["remote-manual-selections"],
        responses={401: {"model": ErrorResponse}},
    )
    def get_context(
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionContextResponse:
        return RemoteManualSelectionContextResponse.from_context(
            service.context(
                access_token=_require_cookie(access_token),
                client_instance_id=client_instance_id,
            )
        )

    @router.post(
        "/sessions/{session_id}/writer-lease/heartbeat",
        response_model=RemoteManualSelectionContextResponse,
        operation_id="heartbeatRemoteManualSelectionWriterLease",
        summary="Renew the currently owned remote selection writer lease",
        tags=["remote-manual-selections"],
        responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def heartbeat_writer_lease(
        session_id: UUID,
        payload: RemoteManualSelectionWriterLeaseCommand,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionContextResponse:
        return RemoteManualSelectionContextResponse.from_context(
            service.heartbeat(
                session_id=session_id,
                access_token=_require_cookie(access_token),
                client_instance_id=payload.client_instance_id,
            )
        )

    @router.post(
        "/sessions/{session_id}/writer-lease/takeover",
        response_model=RemoteManualSelectionContextResponse,
        operation_id="takeoverRemoteManualSelectionWriterLease",
        summary="Take over an expired remote selection writer lease",
        tags=["remote-manual-selections"],
        responses={401: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def takeover_writer_lease(
        session_id: UUID,
        payload: RemoteManualSelectionWriterLeaseCommand,
        service: Annotated[RemoteManualSelectionAccessService, access_service_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionContextResponse:
        return RemoteManualSelectionContextResponse.from_context(
            service.takeover(
                session_id=session_id,
                access_token=_require_cookie(access_token),
                client_instance_id=payload.client_instance_id,
            )
        )

    @router.post(
        "/collections",
        response_model=RemoteManualSelectionCollectionResponse,
        status_code=201,
        operation_id="createRemoteManualSelectionCollection",
        summary="Create an idempotent remote selection collection",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def create_collection(
        payload: RemoteManualSelectionCollectionCreate,
        service: Annotated[RemoteManualSelectionControlService, control_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionCollectionResponse:
        return RemoteManualSelectionCollectionResponse.from_created(
            service.create_collection(
                session_id=payload.session_id,
                collection_id=payload.collection_id,
                name=payload.name,
                access_token=_require_cookie(access_token),
                client_instance_id=client_instance_id,
            )
        )

    @router.post(
        "/collections/{collection_id}/batches",
        response_model=RemoteManualSelectionBatchCreatedResponse,
        status_code=201,
        operation_id="createRemoteManualSelectionBatch",
        summary="Create an idempotent remote selection batch mapping",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def create_batch(
        collection_id: UUID,
        payload: RemoteManualSelectionBatchCreate,
        service: Annotated[RemoteManualSelectionControlService, control_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionBatchCreatedResponse:
        return RemoteManualSelectionBatchCreatedResponse.from_created(
            service.create_batch(
                session_id=payload.session_id,
                collection_id=collection_id,
                batch_id=payload.batch_id,
                name=payload.name,
                source_manifest_checksum_sha256=(payload.source_manifest_checksum_sha256),
                first_layout=payload.first_layout,
                direction=payload.direction,
                total_file_count=payload.total_file_count,
                access_token=_require_cookie(access_token),
                client_instance_id=client_instance_id,
            )
        )

    @router.post(
        "/batches/{batch_id}/source-items",
        response_model=RemoteManualSelectionSourceItemsResponse,
        operation_id="registerRemoteManualSelectionSourceItems",
        summary="Register one bounded page of immutable source metadata",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def register_source_items(
        batch_id: UUID,
        payload: RemoteManualSelectionSourceItemsCreate,
        service: Annotated[RemoteManualSelectionControlService, control_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionSourceItemsResponse:
        result = service.register_source_items(
            session_id=payload.session_id,
            batch_id=batch_id,
            files=tuple(
                item.to_domain(session_id=payload.session_id, batch_id=batch_id)
                for item in payload.items
            ),
            source_kind=payload.source_kind,
            complete=payload.complete,
            access_token=_require_cookie(access_token),
            client_instance_id=client_instance_id,
        )
        return RemoteManualSelectionSourceItemsResponse(
            batch=RemoteManualSelectionBatchResponse.from_domain(result.batch),
            accepted_file_ids=[item.id for item in result.files],
            created_count=result.created_count,
            total_file_count=result.total_file_count,
        )

    @router.get(
        "/batches/{batch_id}/state",
        response_model=RemoteManualSelectionStateDeltaResponse,
        operation_id="getRemoteManualSelectionStateDelta",
        summary="Read one bounded canonical state delta",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def get_state_delta(
        batch_id: UUID,
        service: Annotated[RemoteManualSelectionControlService, control_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        since_revision: Annotated[int, Query(alias="sinceRevision", ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionStateDeltaResponse:
        return RemoteManualSelectionStateDeltaResponse.from_delta(
            service.state_delta(
                batch_id=batch_id,
                since_revision=since_revision,
                limit=limit,
                access_token=_require_cookie(access_token),
                client_instance_id=client_instance_id,
            )
        )

    @router.post(
        "/batches/{batch_id}/operations",
        response_model=RemoteManualSelectionOperationAppliedResponse,
        operation_id="applyRemoteManualSelectionOperation",
        summary="Apply one strictly ordered idempotent selection operation",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def apply_operation(
        batch_id: UUID,
        payload: RemoteManualSelectionOperationCreate,
        service: Annotated[RemoteManualSelectionControlService, control_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionOperationAppliedResponse:
        command = payload.to_domain()
        if command.batch_id != batch_id:
            raise RemoteManualSelectionError(
                "REMOTE_SELECTION_SCOPE_MISMATCH",
                "The operation does not belong to the requested batch.",
            )
        result = service.apply_operation(
            command=command,
            access_token=_require_cookie(access_token),
            client_instance_id=client_instance_id,
        )
        return RemoteManualSelectionOperationAppliedResponse(
            operation=RemoteManualSelectionOperationResponse.from_domain(result.operation),
            batch=RemoteManualSelectionBatchResponse.from_domain(result.batch),
            file=(
                None
                if result.file is None
                else RemoteManualSelectionFileResponse.from_domain(result.file)
            ),
            exact_retry=result.exact_retry,
        )

    @router.get(
        "/batches/{batch_id}/files/{file_id}/transfer",
        response_model=RemoteManualSelectionTransferResponse,
        operation_id="getRemoteManualSelectionFileTransfer",
        summary="Read the resumable status of one selected JPEG transfer",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def get_file_transfer(
        batch_id: UUID,
        file_id: UUID,
        service: Annotated[RemoteManualSelectionTransferService, transfer_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        generation: Annotated[int, Query(ge=1)],
        transfer_id: Annotated[UUID | None, Query(alias="transferId")] = None,
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionTransferResponse:
        record = service.status(
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
            transfer_id=transfer_id,
            access_token=_require_cookie(access_token),
            client_instance_id=client_instance_id,
        )
        return (
            RemoteManualSelectionTransferResponse.not_started(
                batch_id=batch_id,
                file_id=file_id,
                generation=generation,
            )
            if record is None
            else RemoteManualSelectionTransferResponse.from_record(record)
        )

    @router.put(
        "/batches/{batch_id}/files/{file_id}/content",
        response_model=RemoteManualSelectionTransferResponse,
        operation_id="putRemoteManualSelectionFileContent",
        summary="Stream one checksum-bound selected JPEG to host temporary storage",
        tags=["remote-manual-selections"],
        responses={
            401: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            415: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
                },
            }
        },
    )
    async def put_file_content(
        batch_id: UUID,
        file_id: UUID,
        request: Request,
        service: Annotated[RemoteManualSelectionTransferService, transfer_service_parameter],
        client_instance_id: Annotated[UUID, client_header_parameter],
        transfer_id: Annotated[UUID, Header(alias="X-Remote-Selection-Transfer-Id")],
        generation: Annotated[int, Header(alias="X-Remote-Selection-Generation", ge=1)],
        source_last_modified_ms: Annotated[
            int,
            Header(alias="X-Remote-Selection-Source-Mtime", ge=0),
        ],
        checksum_sha256: Annotated[
            str,
            Header(alias="X-Remote-Selection-Checksum-Sha256", pattern=r"^[0-9a-f]{64}$"),
        ],
        content_length: Annotated[int, Header(alias="Content-Length", ge=1)],
        content_type: Annotated[str, Header(alias="Content-Type")],
        access_token: Annotated[
            str | None,
            Cookie(alias=REMOTE_SELECTION_COOKIE_NAME),
        ] = None,
    ) -> RemoteManualSelectionTransferResponse:
        result = await service.upload(
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
            transfer_id=transfer_id,
            declared_bytes=content_length,
            declared_last_modified_ms=source_last_modified_ms,
            declared_checksum_sha256=checksum_sha256,
            content_type=content_type,
            chunks=request.stream(),
            access_token=_require_cookie(access_token),
            client_instance_id=client_instance_id,
        )
        return RemoteManualSelectionTransferResponse.from_record(result)

    return router


def _require_cookie(access_token: str | None) -> str:
    if access_token is None or not access_token.strip():
        raise RemoteManualSelectionAuthenticationError(
            "REMOTE_SELECTION_TOKEN_REQUIRED",
            "Remote selection access token is required.",
        )
    return access_token


def _require_remote_selection_proxy(
    proxy_intent: Annotated[
        str | None,
        Header(alias="X-Remote-Selection-Proxy"),
    ] = None,
) -> None:
    if proxy_intent != REMOTE_SELECTION_PROXY_INTENT:
        raise RemoteManualSelectionAuthorizationError(
            "REMOTE_SELECTION_PROXY_REQUIRED",
            "Remote selection access is available only through the Reviewer proxy.",
        )


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "create_remote_manual_selections_admin_router",
    "create_remote_manual_selections_public_router",
]
