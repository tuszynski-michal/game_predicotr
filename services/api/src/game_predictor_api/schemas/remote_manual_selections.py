"""Local Admin schemas for host-bound remote manual selection setup."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import UUID

from pydantic import Field

from game_predictor_api.application.remote_manual_selection_access import (
    CreatedRemoteManualSelectionAccess,
    RemoteManualSelectionAccessView,
    RemoteManualSelectionBatchMonitorView,
    RemoteManualSelectionContext,
    RemoteManualSelectionSessionMonitorView,
)
from game_predictor_api.application.remote_manual_selection_control import (
    CreatedRemoteManualSelectionBatch,
    CreatedRemoteManualSelectionCollection,
    FinalizedRemoteManualSelectionBatch,
    RemoteManualSelectionStateDelta,
    ReopenedRemoteManualSelectionBatch,
    source_file,
)
from game_predictor_api.application.remote_manual_selection_finalization import (
    RemoteSelectionFinalizePreview,
)
from game_predictor_api.application.remote_manual_selection_host import (
    RemoteManualSelectionBaseCapability,
)
from game_predictor_api.application.remote_manual_selection_recovery import (
    RemoteSelectionRecoveryStatus,
)
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressStatus,
    is_ready_online_reviewer_ingress,
)
from game_predictor_api.domain.remote_manual_selections import (
    REMOTE_OPERATION_SCHEMA,
    RemoteManualSelectionBatchV1,
    RemoteManualSelectionDirection,
    RemoteManualSelectionFileV1,
    RemoteManualSelectionOperationCommandV1,
    RemoteManualSelectionOperationType,
    RemoteManualSelectionOperationV1,
    RemoteManualSelectionTransferStatus,
    RemoteSourceKind,
)
from game_predictor_api.schemas.catalog import ApiModel
from game_predictor_api.storage.remote_manual_selection_repository import (
    RemoteManualSelectionQueueSnapshot,
    RemoteManualSelectionTransferRecord,
)


class RemoteManualSelectionBaseCapabilityResponse(ApiModel):
    status: Literal["selected", "cancelled"]
    base_capability: str | None = None
    display_name: str | None = None
    expires_at: datetime | None = None

    @classmethod
    def selected(
        cls,
        value: RemoteManualSelectionBaseCapability,
    ) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(
            status="selected",
            base_capability=value.capability,
            display_name=value.display_name,
            expires_at=value.expires_at,
        )

    @classmethod
    def cancelled(cls) -> RemoteManualSelectionBaseCapabilityResponse:
        return cls(status="cancelled")


class RemoteManualSelectionSessionCreate(ApiModel):
    base_capability: str | None = Field(default=None, min_length=32, max_length=200)
    lifetime_minutes: int = Field(default=480, ge=5, le=1440)
    label: str | None = Field(default=None, min_length=1, max_length=100)


class RemoteManualSelectionSessionResponse(ApiModel):
    session_id: UUID
    status: Literal["draft", "active", "completed", "expired", "revoked"]
    revision: int
    display_name: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    locked_at: datetime | None
    revoked_at: datetime | None
    writer_active: bool
    writer_lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None
    ready: bool
    review_url: str | None

    @classmethod
    def from_view(
        cls,
        value: RemoteManualSelectionAccessView,
        ingress: ReviewerIngressStatus | None,
    ) -> RemoteManualSelectionSessionResponse:
        ready = (
            value.status.value == "active"
            and ingress is not None
            and is_ready_online_reviewer_ingress(ingress)
        )
        return cls(
            session_id=value.session_id,
            status=value.status.value,
            revision=value.revision,
            display_name=value.display_name,
            created_at=value.created_at,
            updated_at=value.updated_at,
            expires_at=value.expires_at,
            locked_at=value.locked_at,
            revoked_at=value.revoked_at,
            writer_active=value.writer_active,
            writer_lease_expires_at=value.writer_lease_expires_at,
            last_heartbeat_at=value.last_heartbeat_at,
            ready=ready,
            review_url=(
                _manual_selection_url(ingress.public_origin, value.session_id)
                if ready and ingress is not None and ingress.public_origin is not None
                else None
            ),
        )


class RemoteManualSelectionSessionCreatedResponse(ApiModel):
    session: RemoteManualSelectionSessionResponse
    access_code: str

    @classmethod
    def from_created(
        cls,
        value: CreatedRemoteManualSelectionAccess,
        ingress: ReviewerIngressStatus,
    ) -> RemoteManualSelectionSessionCreatedResponse:
        return cls(
            session=RemoteManualSelectionSessionResponse.from_view(
                value.session,
                ingress,
            ),
            access_code=value.access_code,
        )


class RemoteManualSelectionSessionListResponse(ApiModel):
    sessions: list[RemoteManualSelectionSessionResponse]


class RemoteManualSelectionBatchMonitorResponse(ApiModel):
    batch_id: UUID
    name: str
    status: str
    total_file_count: int
    selected_file_count: int
    synced_file_count: int
    failed_file_count: int
    pending_host_action_count: int
    last_error_codes: list[str]
    server_revision: int
    final_manifest_checksum_sha256: str | None
    updated_at: datetime

    @classmethod
    def from_view(
        cls,
        value: RemoteManualSelectionBatchMonitorView,
    ) -> RemoteManualSelectionBatchMonitorResponse:
        return cls(
            batch_id=value.batch_id,
            name=value.name,
            status=value.status,
            total_file_count=value.total_file_count,
            selected_file_count=value.selected_file_count,
            synced_file_count=value.synced_file_count,
            failed_file_count=value.failed_file_count,
            pending_host_action_count=value.pending_host_action_count,
            last_error_codes=list(value.last_error_codes),
            server_revision=value.server_revision,
            final_manifest_checksum_sha256=(value.final_manifest_checksum_sha256),
            updated_at=value.updated_at,
        )


class RemoteManualSelectionSessionMonitorResponse(ApiModel):
    session: RemoteManualSelectionSessionResponse
    batches: list[RemoteManualSelectionBatchMonitorResponse]
    has_more_batches: bool
    disk_total_bytes: int | None
    disk_free_bytes: int | None
    disk_error_code: str | None

    @classmethod
    def from_view(
        cls,
        value: RemoteManualSelectionSessionMonitorView,
        ingress: ReviewerIngressStatus | None,
    ) -> RemoteManualSelectionSessionMonitorResponse:
        return cls(
            session=RemoteManualSelectionSessionResponse.from_view(
                value.session,
                ingress,
            ),
            batches=[
                RemoteManualSelectionBatchMonitorResponse.from_view(batch)
                for batch in value.batches
            ],
            has_more_batches=value.has_more_batches,
            disk_total_bytes=value.disk_total_bytes,
            disk_free_bytes=value.disk_free_bytes,
            disk_error_code=value.disk_error_code,
        )


class RemoteManualSelectionUnlock(ApiModel):
    access_code: str = Field(min_length=1, max_length=64)
    client_instance_id: UUID


class RemoteManualSelectionWriterLeaseCommand(ApiModel):
    client_instance_id: UUID


class RemoteManualSelectionContextResponse(ApiModel):
    session_id: UUID
    status: Literal["active"]
    revision: int
    expires_at: datetime
    is_writer: bool
    writer_active: bool
    writer_lease_expires_at: datetime | None
    last_heartbeat_at: datetime | None

    @classmethod
    def from_context(
        cls,
        value: RemoteManualSelectionContext,
    ) -> RemoteManualSelectionContextResponse:
        if value.status.value != "active":
            raise ValueError("Only an active remote selection session has public context.")
        return cls(
            session_id=value.session_id,
            status="active",
            revision=value.revision,
            expires_at=value.expires_at,
            is_writer=value.is_writer,
            writer_active=value.writer_active,
            writer_lease_expires_at=value.writer_lease_expires_at,
            last_heartbeat_at=value.last_heartbeat_at,
        )


class RemoteManualSelectionCollectionCreate(ApiModel):
    collection_id: UUID
    session_id: UUID
    name: str = Field(min_length=1, max_length=200)


class RemoteManualSelectionCollectionResponse(ApiModel):
    collection_id: UUID
    session_id: UUID
    name: str
    normalized_name: str
    status: str
    revision: int
    created: bool

    @classmethod
    def from_created(
        cls, value: CreatedRemoteManualSelectionCollection
    ) -> RemoteManualSelectionCollectionResponse:
        collection = value.collection
        return cls(
            collection_id=collection.id,
            session_id=collection.session_id,
            name=collection.name,
            normalized_name=collection.normalized_name,
            status=collection.status.value,
            revision=collection.revision,
            created=value.created,
        )


class RemoteManualSelectionBatchCreate(ApiModel):
    batch_id: UUID
    session_id: UUID
    name: str = Field(min_length=1, max_length=200)
    source_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    first_layout: int = Field(ge=1)
    direction: RemoteManualSelectionDirection
    total_file_count: int = Field(ge=1, le=100_000)


class RemoteManualSelectionBatchResponse(ApiModel):
    batch_id: UUID
    session_id: UUID
    collection_id: UUID
    name: str
    source_manifest_checksum_sha256: str
    first_layout: int
    direction: str
    cursor_index: int
    status: str
    server_revision: int
    last_client_sequence: int

    @classmethod
    def from_domain(cls, value: RemoteManualSelectionBatchV1) -> RemoteManualSelectionBatchResponse:
        return cls(
            batch_id=value.id,
            session_id=value.session_id,
            collection_id=value.collection_id,
            name=value.name,
            source_manifest_checksum_sha256=value.source_manifest_checksum_sha256,
            first_layout=value.first_layout,
            direction=value.direction.value,
            cursor_index=value.cursor_index,
            status=value.status.value,
            server_revision=value.server_revision,
            last_client_sequence=value.last_client_sequence,
        )


class RemoteManualSelectionBatchCreatedResponse(ApiModel):
    batch: RemoteManualSelectionBatchResponse
    created: bool
    resumed: bool

    @classmethod
    def from_created(
        cls, value: CreatedRemoteManualSelectionBatch
    ) -> RemoteManualSelectionBatchCreatedResponse:
        return cls(
            batch=RemoteManualSelectionBatchResponse.from_domain(value.batch),
            created=value.mapping.created,
            resumed=value.mapping.resumed,
        )


class RemoteManualSelectionSourceItem(ApiModel):
    file_id: UUID
    source_index: int = Field(ge=0)
    relative_path: str = Field(min_length=1, max_length=2_048)
    size_bytes: int = Field(ge=0)
    last_modified_ms: int = Field(ge=0)
    mime_type: str = Field(min_length=1, max_length=100)

    def to_domain(self, *, session_id: UUID, batch_id: UUID) -> RemoteManualSelectionFileV1:
        return source_file(
            file_id=self.file_id,
            session_id=session_id,
            batch_id=batch_id,
            source_index=self.source_index,
            relative_path=self.relative_path,
            size_bytes=self.size_bytes,
            last_modified_ms=self.last_modified_ms,
            mime_type=self.mime_type,
        )


class RemoteManualSelectionSourceItemsCreate(ApiModel):
    session_id: UUID
    source_kind: RemoteSourceKind
    complete: bool = False
    items: list[RemoteManualSelectionSourceItem] = Field(min_length=1, max_length=500)


class RemoteManualSelectionFileResponse(ApiModel):
    file_id: UUID
    session_id: UUID
    batch_id: UUID
    source_index: int
    relative_path: str
    size_bytes: int
    last_modified_ms: int
    mime_type: str
    desired_selected: bool
    selection_generation: int
    status: str
    range_start: int | None
    range_end: int | None
    output_name: str | None
    host_checksum_sha256: str | None
    last_server_revision: int | None = None

    @classmethod
    def from_domain(
        cls,
        value: RemoteManualSelectionFileV1,
        *,
        last_server_revision: int | None = None,
    ) -> RemoteManualSelectionFileResponse:
        return cls(
            file_id=value.id,
            session_id=value.session_id,
            batch_id=value.batch_id,
            source_index=value.source_index,
            relative_path=value.relative_path,
            size_bytes=value.size_bytes,
            last_modified_ms=value.last_modified_ms,
            mime_type=value.mime_type,
            desired_selected=value.desired_selected,
            selection_generation=value.selection_generation,
            status=value.status.value,
            range_start=value.range_start,
            range_end=value.range_end,
            output_name=value.output_name,
            host_checksum_sha256=value.host_checksum_sha256,
            last_server_revision=last_server_revision,
        )


class RemoteManualSelectionSourceItemsResponse(ApiModel):
    batch: RemoteManualSelectionBatchResponse
    accepted_file_ids: list[UUID]
    created_count: int
    total_file_count: int


class RemoteManualSelectionOperationCreate(ApiModel):
    schema_version: Literal["remote-manual-selection-operation-v1"] = REMOTE_OPERATION_SCHEMA
    operation_id: UUID
    session_id: UUID
    batch_id: UUID
    client_instance_id: UUID
    client_sequence: int = Field(ge=1)
    expected_server_revision: int = Field(ge=0)
    operation_type: RemoteManualSelectionOperationType
    selection_generation: int = Field(ge=0)
    range_start: int = Field(ge=1)
    range_end: int = Field(ge=1)
    recorded_at: datetime
    file_id: UUID | None = None
    image_path: str | None = Field(default=None, max_length=2_048)
    source_index: int | None = Field(default=None, ge=0)
    image_checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    output_name: str | None = Field(default=None, max_length=255)
    visible_milliseconds: int = Field(default=0, ge=0)
    decoded: bool = True
    target_operation_id: UUID | None = None

    def to_domain(self) -> RemoteManualSelectionOperationCommandV1:
        return RemoteManualSelectionOperationCommandV1(
            operation_id=self.operation_id,
            session_id=self.session_id,
            batch_id=self.batch_id,
            client_instance_id=self.client_instance_id,
            client_sequence=self.client_sequence,
            expected_server_revision=self.expected_server_revision,
            operation_type=self.operation_type,
            selection_generation=self.selection_generation,
            range_start=self.range_start,
            range_end=self.range_end,
            recorded_at=self.recorded_at,
            file_id=self.file_id,
            image_path=self.image_path,
            source_index=self.source_index,
            image_checksum_sha256=self.image_checksum_sha256,
            output_name=self.output_name,
            visible_milliseconds=self.visible_milliseconds,
            decoded=self.decoded,
            target_operation_id=self.target_operation_id,
        )


class RemoteManualSelectionOperationResponse(ApiModel):
    operation_id: UUID
    command_checksum_sha256: str
    status: str
    applied_server_revision: int
    outcome_code: str

    @classmethod
    def from_domain(
        cls, value: RemoteManualSelectionOperationV1
    ) -> RemoteManualSelectionOperationResponse:
        return cls(
            operation_id=value.command.operation_id,
            command_checksum_sha256=value.command_checksum_sha256,
            status=value.status.value,
            applied_server_revision=value.applied_server_revision,
            outcome_code=value.outcome_code,
        )


class RemoteManualSelectionOperationAppliedResponse(ApiModel):
    operation: RemoteManualSelectionOperationResponse
    batch: RemoteManualSelectionBatchResponse
    file: RemoteManualSelectionFileResponse | None
    exact_retry: bool


class RemoteManualSelectionTransferResponse(ApiModel):
    transfer_id: UUID | None
    batch_id: UUID
    file_id: UUID
    generation: int
    attempt: int
    declared_bytes: int
    received_bytes: int
    status: str
    declared_checksum_sha256: str | None
    verified_checksum_sha256: str | None

    @classmethod
    def from_record(
        cls,
        value: RemoteManualSelectionTransferRecord,
    ) -> RemoteManualSelectionTransferResponse:
        transfer = value.transfer
        public_status = (
            "synced"
            if transfer.status is RemoteManualSelectionTransferStatus.MATERIALIZED
            else transfer.status.value
        )
        return cls(
            transfer_id=transfer.id,
            batch_id=transfer.batch_id,
            file_id=transfer.file_id,
            generation=transfer.generation,
            attempt=transfer.attempt,
            declared_bytes=transfer.declared_bytes,
            received_bytes=transfer.received_bytes,
            status=public_status,
            declared_checksum_sha256=transfer.declared_checksum_sha256,
            verified_checksum_sha256=transfer.verified_checksum_sha256,
        )

    @classmethod
    def not_started(
        cls,
        *,
        batch_id: UUID,
        file_id: UUID,
        generation: int,
    ) -> RemoteManualSelectionTransferResponse:
        return cls(
            transfer_id=None,
            batch_id=batch_id,
            file_id=file_id,
            generation=generation,
            attempt=0,
            declared_bytes=0,
            received_bytes=0,
            status="not_started",
            declared_checksum_sha256=None,
            verified_checksum_sha256=None,
        )


class RemoteManualSelectionStateDeltaResponse(ApiModel):
    batch: RemoteManualSelectionBatchResponse
    files: list[RemoteManualSelectionFileResponse]
    next_revision: int
    has_more: bool
    queue: RemoteSelectionQueueStatusResponse
    last_heartbeat_at: datetime | None

    @classmethod
    def from_delta(
        cls, value: RemoteManualSelectionStateDelta
    ) -> RemoteManualSelectionStateDeltaResponse:
        return cls(
            batch=RemoteManualSelectionBatchResponse.from_domain(value.batch),
            files=[
                RemoteManualSelectionFileResponse.from_domain(
                    item.file,
                    last_server_revision=item.server_revision,
                )
                for item in value.files
            ],
            next_revision=value.next_revision,
            has_more=value.has_more,
            queue=RemoteSelectionQueueStatusResponse.from_snapshot(value.queue),
            last_heartbeat_at=value.last_heartbeat_at,
        )


class RemoteSelectionRecoveryFindingResponse(ApiModel):
    code: str
    count: int


class RemoteSelectionQueueStatusResponse(ApiModel):
    pending_operation_count: int
    uploading_transfer_count: int
    pending_transfer_bytes: int
    materializing_action_count: int
    pending_host_action_count: int
    synced_file_count: int
    conflict_file_count: int
    recovery_findings: list[RemoteSelectionRecoveryFindingResponse]

    @classmethod
    def from_snapshot(
        cls,
        value: RemoteManualSelectionQueueSnapshot,
    ) -> RemoteSelectionQueueStatusResponse:
        return cls(
            pending_operation_count=value.pending_operation_count,
            uploading_transfer_count=value.uploading_transfer_count,
            pending_transfer_bytes=value.pending_transfer_bytes,
            materializing_action_count=value.materializing_action_count,
            pending_host_action_count=value.pending_host_action_count,
            synced_file_count=value.synced_file_count,
            conflict_file_count=value.conflict_file_count,
            recovery_findings=[
                RemoteSelectionRecoveryFindingResponse(code=code, count=count)
                for code, count in value.recovery_findings
            ],
        )


class RemoteSelectionGcCategoryResponse(ApiModel):
    code: str
    artifact_count: int
    total_bytes: int


class RemoteSelectionGcPreviewResponse(ApiModel):
    deletion_enabled: Literal[False]
    scanned_artifact_count: int
    scanned_bytes: int
    categories: list[RemoteSelectionGcCategoryResponse]
    findings: list[str]


class RemoteSelectionRecoveryStatusResponse(ApiModel):
    batch_id: UUID
    queue: RemoteSelectionQueueStatusResponse
    gc_preview: RemoteSelectionGcPreviewResponse

    @classmethod
    def from_status(
        cls,
        value: RemoteSelectionRecoveryStatus,
    ) -> RemoteSelectionRecoveryStatusResponse:
        return cls(
            batch_id=value.batch_id,
            queue=RemoteSelectionQueueStatusResponse.from_snapshot(value.queue),
            gc_preview=RemoteSelectionGcPreviewResponse(
                deletion_enabled=False,
                scanned_artifact_count=value.gc_preview.scanned_artifact_count,
                scanned_bytes=value.gc_preview.scanned_bytes,
                categories=[
                    RemoteSelectionGcCategoryResponse(
                        code=item.code,
                        artifact_count=item.artifact_count,
                        total_bytes=item.total_bytes,
                    )
                    for item in value.gc_preview.categories
                ],
                findings=list(value.gc_preview.findings),
            ),
        )


class RemoteSelectionFinalizeBlockerResponse(ApiModel):
    code: str
    count: int


class RemoteSelectionFinalizePreviewResponse(ApiModel):
    batch_id: UUID
    status: str
    server_revision: int
    ready: bool
    total_file_count: int
    selected_file_count: int
    synced_file_count: int
    operation_count: int
    blockers: list[RemoteSelectionFinalizeBlockerResponse]

    @classmethod
    def from_view(
        cls,
        value: RemoteSelectionFinalizePreview,
    ) -> RemoteSelectionFinalizePreviewResponse:
        return cls(
            batch_id=UUID(value.batch_id),
            status=value.status,
            server_revision=value.server_revision,
            ready=value.ready,
            total_file_count=value.total_file_count,
            selected_file_count=value.selected_file_count,
            synced_file_count=value.synced_file_count,
            operation_count=value.operation_count,
            blockers=[
                RemoteSelectionFinalizeBlockerResponse(
                    code=item.code,
                    count=item.count,
                )
                for item in value.blockers
            ],
        )


class RemoteSelectionFinalizeCommand(ApiModel):
    session_id: UUID
    expected_server_revision: int = Field(ge=0)


class RemoteSelectionFinalizedResponse(ApiModel):
    batch: RemoteManualSelectionBatchResponse
    finalized_at: datetime
    final_manifest_checksum_sha256: str
    exact_retry: bool

    @classmethod
    def from_result(
        cls,
        value: FinalizedRemoteManualSelectionBatch,
    ) -> RemoteSelectionFinalizedResponse:
        return cls(
            batch=RemoteManualSelectionBatchResponse.from_domain(value.snapshot.batch),
            finalized_at=value.finalized_at,
            final_manifest_checksum_sha256=(value.artifacts.final_manifest_checksum_sha256),
            exact_retry=value.exact_retry,
        )


class RemoteSelectionReopenCommand(ApiModel):
    batch_id: UUID
    expected_server_revision: int = Field(ge=0)
    expected_final_manifest_checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RemoteSelectionReopenedResponse(ApiModel):
    batch: RemoteManualSelectionBatchResponse
    reopened_at: datetime

    @classmethod
    def from_result(
        cls,
        value: ReopenedRemoteManualSelectionBatch,
    ) -> RemoteSelectionReopenedResponse:
        return cls(
            batch=RemoteManualSelectionBatchResponse.from_domain(value.snapshot.batch),
            reopened_at=value.reopened_at,
        )


def _manual_selection_url(public_origin: str, session_id: UUID) -> str:
    parsed = urlparse(public_origin)
    return urlunparse(
        parsed._replace(
            path="/manual-selection",
            query=urlencode({"session": str(session_id)}),
        )
    )


__all__ = [
    "RemoteManualSelectionBaseCapabilityResponse",
    "RemoteManualSelectionContextResponse",
    "RemoteManualSelectionSessionCreate",
    "RemoteManualSelectionSessionCreatedResponse",
    "RemoteManualSelectionSessionListResponse",
    "RemoteManualSelectionSessionResponse",
    "RemoteManualSelectionUnlock",
    "RemoteManualSelectionWriterLeaseCommand",
    "RemoteManualSelectionBatchCreate",
    "RemoteManualSelectionBatchCreatedResponse",
    "RemoteManualSelectionBatchResponse",
    "RemoteManualSelectionCollectionCreate",
    "RemoteManualSelectionCollectionResponse",
    "RemoteManualSelectionFileResponse",
    "RemoteManualSelectionOperationAppliedResponse",
    "RemoteManualSelectionOperationCreate",
    "RemoteManualSelectionOperationResponse",
    "RemoteManualSelectionSourceItemsCreate",
    "RemoteManualSelectionSourceItemsResponse",
    "RemoteManualSelectionStateDeltaResponse",
    "RemoteManualSelectionTransferResponse",
    "RemoteSelectionFinalizeBlockerResponse",
    "RemoteSelectionFinalizeCommand",
    "RemoteSelectionFinalizedResponse",
    "RemoteSelectionFinalizePreviewResponse",
    "RemoteSelectionReopenCommand",
    "RemoteSelectionReopenedResponse",
]
