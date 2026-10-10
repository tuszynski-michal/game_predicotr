"""Transactional management writes with retained history and exact retry receipts."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from game_predictor_api.application.management import ManagementError
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import (
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementDeleteResponse,
    ManagementMutationPreviewResponse,
)
from game_predictor_api.schemas.management import (
    ManagementAssignmentCommand,
    ManagementAssignmentResponse,
    ManagementCommand,
    ManagementGameResponse,
    ManagementMachineCommand,
    ManagementMachineResponse,
    ManagementPointCommand,
    ManagementPointResponse,
    ManagementSnapshotResponse,
)
from game_predictor_api.storage.game_storage_routing import GameStorageRouter
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementMutationPreviewModel,
    ManagementOperationModel,
    ManagementPointModel,
    now,
)
from game_predictor_api.storage.management_mutation_repository import (
    ManagementMutationRepository,
    preview_body,
)
from game_predictor_api.storage.models import GameModel


class SqlAlchemyManagementRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def snapshot(self) -> ManagementSnapshotResponse:
        # Bounded control-plane metadata only; no boards, images or charts.
        points = self.session.scalars(
            select(ManagementPointModel).order_by(
                ManagementPointModel.created_at, ManagementPointModel.id
            )
        ).all()
        machines = self.session.scalars(
            select(ManagementMachineModel).order_by(
                ManagementMachineModel.created_at, ManagementMachineModel.id
            )
        ).all()
        assignments = self._assignment_responses()
        responses = [self._point_response(point) for point in points]
        by_point = {point.id: point for point in responses}
        for machine in machines:
            response = ManagementMachineResponse.model_validate(
                {
                    **{
                        key: getattr(machine, key)
                        for key in ManagementMachineResponse.model_fields
                        if key != "assignments"
                    },
                    "assignments": [],
                }
            )
            response.assignments = assignments.get(machine.id, [])
            by_point[machine.point_id].machines.append(response)
        games = self.session.scalars(
            select(GameModel)
            .where(GameModel.status == GameStatus.ACTIVE)
            .order_by(GameModel.name, GameModel.id)
        ).all()
        return ManagementSnapshotResponse(
            points=responses,
            active_games=[ManagementGameResponse.model_validate(game) for game in games],
        )

    def _assignment_responses(
        self, machine_id: UUID | None = None
    ) -> dict[UUID, list[ManagementAssignmentResponse]]:
        statement = (
            select(ManagementAssignmentModel, GameModel)
            .join(GameModel, GameModel.id == ManagementAssignmentModel.game_id)
            .order_by(GameModel.name, GameModel.id)
        )
        if machine_id is not None:
            statement = statement.where(ManagementAssignmentModel.machine_id == machine_id)
        result: dict[UUID, list[ManagementAssignmentResponse]] = {}
        for assignment, game in self.session.execute(statement):
            result.setdefault(assignment.machine_id, []).append(
                ManagementAssignmentResponse(
                    game_id=game.id,
                    game_name=game.name,
                    game_status=game.status,
                    attached=assignment.attached,
                )
            )
        return result

    def _point_response(self, point: ManagementPointModel) -> ManagementPointResponse:
        return ManagementPointResponse.model_validate(
            {
                **{
                    key: getattr(point, key)
                    for key in ManagementPointResponse.model_fields
                    if key != "machines"
                },
                "machines": [],
            }
        )

    def _machine_response(self, machine: ManagementMachineModel) -> ManagementMachineResponse:
        response = ManagementMachineResponse.model_validate(
            {
                **{
                    key: getattr(machine, key)
                    for key in ManagementMachineResponse.model_fields
                    if key != "assignments"
                },
                "assignments": [],
            }
        )
        response.assignments = self._assignment_responses(machine.id).get(machine.id, [])
        return response

    def begin_operation(
        self,
        command: ManagementCommand,
        actor: str,
        action: str,
        target: str,
    ) -> tuple[str, dict[str, object] | None]:
        command_body = command.model_dump(mode="json")
        # New optional fields cannot alter checksums of previously saved
        # commands, whose exact retries remain valid after the schema upgrade.
        for optional_field in ("game_ids", "preview_token"):
            if command_body.get(optional_field) is None:
                command_body.pop(optional_field, None)
        body = {
            "actor": actor,
            "action": action,
            "target": target,
            "body": command_body,
        }
        checksum = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
        ).hexdigest()
        if self.session.get_bind().dialect.name == "postgresql":
            # Serialize even concurrent create retries before a target row exists.
            key = int.from_bytes(command.operation_id.bytes[:8], "big", signed=True)
            self.session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
        receipt = self.session.get(ManagementOperationModel, command.operation_id)
        if receipt is not None:
            if receipt.actor != actor or receipt.request_checksum != checksum:
                raise ManagementError(
                    "MANAGEMENT_OPERATION_CONFLICT", "Operation was already used."
                )
            marker = receipt.response.get("managementReceiptState")
            if marker in ("target_deleted", "legacy_redacted"):
                code = (
                    "MANAGEMENT_TARGET_DELETED"
                    if marker == "target_deleted"
                    else "MANAGEMENT_LEGACY_RECEIPT_REDACTED"
                )
                raise ManagementError(code, "The original target is no longer available.")
            return checksum, receipt.response
        return checksum, None

    def finish_operation(
        self,
        command: ManagementCommand,
        actor: str,
        checksum: str,
        action: str,
        point_id: UUID,
        machine_id: UUID | None,
        before: dict[str, object],
        response: ManagementPointResponse | ManagementMachineResponse,
    ) -> None:
        after = response.model_dump(mode="json", by_alias=True)
        self.session.add(
            ManagementOperationModel(
                operation_id=command.operation_id,
                actor=actor,
                request_checksum=checksum,
                response=after,
                action=action,
                point_id=point_id,
                machine_id=machine_id,
            )
        )
        self.session.flush()
        self.session.add(
            ManagementJournalModel(
                operation_id=command.operation_id,
                actor=actor,
                action=action,
                point_id=point_id,
                machine_id=machine_id,
                before=before,
                after=after,
            )
        )
        self.session.flush()

    def lock_point(self, point_id: UUID) -> ManagementPointModel:
        point = self.session.scalar(
            select(ManagementPointModel)
            .where(ManagementPointModel.id == point_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if point is None:
            raise ManagementError("MANAGEMENT_POINT_NOT_FOUND", "Point does not exist.", 404)
        return point

    def lock_machine(self, machine_id: UUID) -> tuple[ManagementPointModel, ManagementMachineModel]:
        point_id = self.session.scalar(
            select(ManagementMachineModel.point_id).where(ManagementMachineModel.id == machine_id)
        )
        if point_id is None:
            raise ManagementError("MANAGEMENT_MACHINE_NOT_FOUND", "Machine does not exist.", 404)
        point = self.lock_point(point_id)
        machine = self.session.scalar(
            select(ManagementMachineModel)
            .where(ManagementMachineModel.id == machine_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if machine is None:
            raise ManagementError("MANAGEMENT_MACHINE_NOT_FOUND", "Machine does not exist.", 404)
        return point, machine

    @staticmethod
    def require_revision(actual: int, expected: int) -> None:
        if actual != expected:
            raise ManagementError(
                "MANAGEMENT_REVISION_CONFLICT", "Refresh before editing this record."
            )

    @staticmethod
    def require_available(
        point: ManagementPointModel, machine: ManagementMachineModel | None = None
    ) -> None:
        if point.archived or (machine is not None and machine.archived):
            raise ManagementError(
                "MANAGEMENT_ARCHIVED", "Restore the archived point or machine first."
            )

    def point(
        self, point_id: UUID | None, command: ManagementPointCommand, actor: str
    ) -> ManagementPointResponse:
        checksum, receipt = self.begin_operation(command, actor, "point.write", str(point_id))
        if receipt is not None:
            return ManagementPointResponse.model_validate(receipt)
        before: dict[str, object] = {}
        if point_id is None:
            self.require_revision(0, command.expected_revision)
            point = ManagementPointModel()
            self.session.add(point)
        else:
            point = self.lock_point(point_id)
            self.require_revision(point.revision, command.expected_revision)
            before = self._point_response(point).model_dump(mode="json", by_alias=True)
            point.revision += 1
        point.name, point.city, point.street = command.name, command.city, command.street
        point.archived, point.updated_at = command.archived, now()
        self.session.flush()
        response = self._point_response(point)
        self.finish_operation(
            command, actor, checksum, "point.write", point.id, None, before, response
        )
        return response

    def machine(
        self, point_id: UUID, machine_id: UUID | None, command: ManagementMachineCommand, actor: str
    ) -> ManagementMachineResponse:
        target = f"{point_id}/{machine_id}"
        checksum, receipt = self.begin_operation(command, actor, "machine.write", target)
        if receipt is not None:
            return ManagementMachineResponse.model_validate(receipt)
        mutations = ManagementMutationRepository(self)
        preview = mutations.lock_preview(command.preview_token, actor)
        before: dict[str, object] = {}
        if machine_id is None:
            point = self.lock_point(point_id)
            self.require_available(point)
            self.require_revision(0, command.expected_revision)
            machine = ManagementMachineModel(point_id=point.id)
            self.session.add(machine)
        else:
            point, machine = self.lock_machine(machine_id)
            if point.id != point_id:
                raise ManagementError(
                    "MANAGEMENT_MACHINE_NOT_FOUND", "Machine is not in this point.", 404
                )
            self.require_available(point)
            self.require_revision(machine.revision, command.expected_revision)
            before = self._machine_response(machine).model_dump(mode="json", by_alias=True)
        if machine_id is None:
            machine.name = command.name
            self.session.flush()
        if command.game_ids is not None:
            self._apply_assignments(
                machine, command.game_ids, actor, "machine.write", command, preview
            )
        if machine_id is not None:
            machine.revision += 1
        machine.name, machine.archived, machine.updated_at = command.name, command.archived, now()
        self.session.flush()
        response = self._machine_response(machine)
        self.finish_operation(
            command, actor, checksum, "machine.write", point.id, machine.id, before, response
        )
        return response

    def assignments(
        self, machine_id: UUID, command: ManagementAssignmentCommand, actor: str
    ) -> ManagementMachineResponse:
        checksum, receipt = self.begin_operation(
            command, actor, "assignments.write", str(machine_id)
        )
        if receipt is not None:
            return ManagementMachineResponse.model_validate(receipt)
        preview = ManagementMutationRepository(self).lock_preview(command.preview_token, actor)
        point, machine = self.lock_machine(machine_id)
        self.require_available(point, machine)
        self.require_revision(machine.revision, command.expected_revision)
        before = self._machine_response(machine).model_dump(mode="json", by_alias=True)
        self._apply_assignments(
            machine, command.game_ids, actor, "assignments.write", command, preview
        )
        machine.revision += 1
        machine.updated_at = now()
        self.session.flush()
        response = self._machine_response(machine)
        self.finish_operation(
            command, actor, checksum, "assignments.write", point.id, machine.id, before, response
        )
        return response

    def delete_preview(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeletePreviewCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse:
        return ManagementMutationRepository(self).delete_preview(
            point_id, machine_id, command, actor
        )

    def update_preview(
        self,
        machine_id: UUID,
        command: ManagementMachineCommand | ManagementAssignmentCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse:
        return ManagementMutationRepository(self).update_preview(machine_id, command, actor)

    def delete_scope(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeleteCommand,
        actor: str,
    ) -> ManagementDeleteResponse:
        return ManagementMutationRepository(self).delete_scope(point_id, machine_id, command, actor)

    def _apply_assignments(
        self,
        machine: ManagementMachineModel,
        game_ids: list[UUID],
        actor: str,
        action: str,
        command: ManagementCommand,
        preview: ManagementMutationPreviewModel | None,
    ) -> None:
        existing = {
            row.game_id: row
            for row in self.session.scalars(
                select(ManagementAssignmentModel).where(
                    ManagementAssignmentModel.machine_id == machine.id
                )
            )
        }
        newly_attached = {
            game_id
            for game_id in game_ids
            if game_id not in existing or not existing[game_id].attached
        }
        removed = sorted(existing.keys() - set(game_ids), key=str)
        # Lock live and removed games in one deterministic order.
        games = self.session.scalars(
            select(GameModel)
            .where(GameModel.id.in_(set(game_ids) | set(removed)))
            .order_by(GameModel.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        ).all()
        if len(games) != len(set(game_ids) | set(removed)) or any(
            game.status != GameStatus.ACTIVE and game.id in newly_attached for game in games
        ):
            raise ManagementError(
                "MANAGEMENT_GAME_NOT_ACTIVE", "Only active games can be assigned."
            )
        if self.session.get_bind().dialect.name == "postgresql" and newly_attached:
            self.session.execute(
                text(
                    "SELECT game_id FROM public.game_storage_locations "
                    "WHERE game_id = ANY(CAST(:ids AS uuid[])) ORDER BY game_id FOR SHARE"
                ),
                {"ids": [str(game_id) for game_id in sorted(newly_attached, key=str)]},
            )
        locations = GameStorageRouter().describe_many(self.session, tuple(newly_attached))
        if any(not location.write_available for location in locations.values()):
            raise ManagementError("MANAGEMENT_GAME_UNAVAILABLE", "Game storage is unavailable.")
        if removed:
            mutations = ManagementMutationRepository(self)
            mutations.confirm(
                preview, actor, action, machine.point_id, machine.id, removed, preview_body(command)
            )
            mutations.purge(machine.point_id, machine.id, removed)
        wanted = set(game_ids)
        for game_id in wanted & existing.keys():
            row = existing[game_id]
            row.attached = True
            row.updated_at = now()
        for game_id in wanted - existing.keys():
            self.session.add(ManagementAssignmentModel(machine_id=machine.id, game_id=game_id))
        self.session.flush()
