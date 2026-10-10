"""Management service and stable control-plane errors."""

from typing import Protocol
from uuid import UUID

from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementDeleteResponse,
    ManagementMachineCommand,
    ManagementMachineResponse,
    ManagementMutationPreviewResponse,
    ManagementPointCommand,
    ManagementPointResponse,
    ManagementSnapshotResponse,
)
from game_predictor_api.domain.management import (
    ManagementError as ManagementError,
)


class ManagementRepository(Protocol):
    def delete_preview(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeletePreviewCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse: ...

    def update_preview(
        self,
        machine_id: UUID,
        command: ManagementMachineCommand | ManagementAssignmentCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse: ...

    def delete_scope(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeleteCommand,
        actor: str,
    ) -> ManagementDeleteResponse: ...

    def snapshot(self) -> ManagementSnapshotResponse: ...

    def point(
        self, point_id: UUID | None, command: ManagementPointCommand, actor: str
    ) -> ManagementPointResponse: ...

    def machine(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementMachineCommand,
        actor: str,
    ) -> ManagementMachineResponse: ...

    def assignments(
        self,
        machine_id: UUID,
        command: ManagementAssignmentCommand,
        actor: str,
    ) -> ManagementMachineResponse: ...


class ManagementService:
    def __init__(self, repository: ManagementRepository, actor: str = "local-owner") -> None:
        self.repository = repository
        self.actor = actor

    def delete_preview(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeletePreviewCommand,
    ) -> ManagementMutationPreviewResponse:
        return self.repository.delete_preview(point_id, machine_id, command, self.actor)

    def update_preview(
        self,
        machine_id: UUID,
        command: ManagementMachineCommand | ManagementAssignmentCommand,
    ) -> ManagementMutationPreviewResponse:
        return self.repository.update_preview(machine_id, command, self.actor)

    def delete_scope(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeleteCommand,
    ) -> ManagementDeleteResponse:
        return self.repository.delete_scope(point_id, machine_id, command, self.actor)

    def snapshot(self) -> ManagementSnapshotResponse:
        return self.repository.snapshot()

    def point(
        self, point_id: UUID | None, command: ManagementPointCommand
    ) -> ManagementPointResponse:
        return self.repository.point(point_id, command, self.actor)

    def machine(
        self, point_id: UUID, machine_id: UUID | None, command: ManagementMachineCommand
    ) -> ManagementMachineResponse:
        return self.repository.machine(point_id, machine_id, command, self.actor)

    def assignments(
        self, machine_id: UUID, command: ManagementAssignmentCommand
    ) -> ManagementMachineResponse:
        return self.repository.assignments(machine_id, command, self.actor)
