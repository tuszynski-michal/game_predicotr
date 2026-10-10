"""Preview-bound structural mutations; SQL purge is the only immutable DML port."""

import hashlib
import json
import secrets
from datetime import UTC, timedelta
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import delete, func, select, text

from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementCommand,
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementDeleteResponse,
    ManagementError,
    ManagementMachineCommand,
    ManagementMutationCounts,
    ManagementMutationPreviewResponse,
)
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementMutationPreviewModel,
    ManagementOperationModel,
    now,
)
from game_predictor_api.storage.management_stake_models import (
    ManagementSearchContextModel,
    ManagementStakeSlotModel,
)

if TYPE_CHECKING:
    from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def preview_body(command: ManagementCommand) -> str:
    return digest(command.model_dump(mode="json", exclude={"preview_token"}))


class ManagementMutationRepository:
    def __init__(self, metadata: "SqlAlchemyManagementRepository") -> None:
        self.metadata = metadata
        self.session = metadata.session

    def lock_preview(self, token: str | None, actor: str) -> ManagementMutationPreviewModel | None:
        if token is None:
            return None
        preview = self.session.scalar(
            select(ManagementMutationPreviewModel)
            .where(
                ManagementMutationPreviewModel.token_sha256
                == hashlib.sha256(token.encode()).hexdigest()
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if preview is None or preview.actor != actor:
            raise ManagementError(
                "MANAGEMENT_PREVIEW_INVALID", "Preview does not match this actor."
            )
        expiry = preview.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= now():
            raise ManagementError("MANAGEMENT_PREVIEW_EXPIRED", "Create a new deletion preview.")
        return preview

    def _state(
        self, point_id: UUID, machine_id: UUID | None, game_ids: list[UUID] | None
    ) -> tuple[str, ManagementMutationCounts]:
        point = self.metadata.lock_point(point_id)
        machines = self.session.scalars(
            select(ManagementMachineModel)
            .where(
                ManagementMachineModel.point_id == point_id,
                *([ManagementMachineModel.id == machine_id] if machine_id else []),
            )
            .order_by(ManagementMachineModel.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
        if machine_id and not machines:
            raise ManagementError(
                "MANAGEMENT_MACHINE_NOT_FOUND", "Machine is not in this point.", 404
            )
        ids = [machine.id for machine in machines]
        assignments = self.session.execute(
            select(
                ManagementAssignmentModel.machine_id,
                ManagementAssignmentModel.game_id,
                ManagementAssignmentModel.attached,
                ManagementAssignmentModel.updated_at,
            )
            .where(
                ManagementAssignmentModel.machine_id.in_(ids),
                *(
                    [ManagementAssignmentModel.game_id.in_(game_ids)]
                    if game_ids is not None
                    else []
                ),
            )
            .order_by(ManagementAssignmentModel.machine_id, ManagementAssignmentModel.game_id)
        ).all()
        slots = self.session.execute(
            select(
                ManagementStakeSlotModel.machine_id,
                ManagementStakeSlotModel.game_id,
                ManagementStakeSlotModel.stake_grosze,
                ManagementStakeSlotModel.revision,
            )
            .where(
                ManagementStakeSlotModel.machine_id.in_(ids),
                *([ManagementStakeSlotModel.game_id.in_(game_ids)] if game_ids is not None else []),
            )
            .order_by(
                ManagementStakeSlotModel.machine_id,
                ManagementStakeSlotModel.game_id,
                ManagementStakeSlotModel.stake_grosze,
            )
        ).all()
        journal_filter = (
            ManagementJournalModel.point_id == point_id
            if machine_id is None
            else ManagementJournalModel.machine_id == machine_id
        )
        journal = self.session.execute(
            select(func.count(), func.max(ManagementJournalModel.created_at))
            .select_from(ManagementJournalModel)
            .where(
                journal_filter,
                *([ManagementJournalModel.game_id.in_(game_ids)] if game_ids is not None else []),
            )
        ).one()
        contexts = self.session.execute(
            select(func.count(), func.max(ManagementSearchContextModel.created_at))
            .select_from(ManagementSearchContextModel)
            .where(
                ManagementSearchContextModel.machine_id.in_(ids),
                *(
                    [ManagementSearchContextModel.game_id.in_(game_ids)]
                    if game_ids is not None
                    else []
                ),
            )
        ).one()
        counts = ManagementMutationCounts(
            points=int(machine_id is None),
            machines=len(machines) if game_ids is None else 0,
            assignments=len(assignments),
            slots=len(slots),
            search_contexts=contexts[0],
            journal_entries=journal[0],
        )
        fingerprint = digest(
            {
                "point": (point.id, point.revision),
                "machines": [(m.id, m.revision) for m in machines],
                "assignments": [tuple(row) for row in assignments],
                "slots": [tuple(row) for row in slots],
                "journal": tuple(journal),
                "contexts": tuple(contexts),
            }
        )
        return fingerprint, counts

    def _cleanup(self, actor: str) -> None:
        oldest = (
            select(ManagementMutationPreviewModel.token_sha256)
            .where(
                ManagementMutationPreviewModel.actor == actor,
                ManagementMutationPreviewModel.expires_at <= now(),
            )
            .order_by(
                ManagementMutationPreviewModel.expires_at,
                ManagementMutationPreviewModel.token_sha256,
            )
            .limit(100)
        )
        self.session.execute(
            delete(ManagementMutationPreviewModel).where(
                ManagementMutationPreviewModel.token_sha256.in_(oldest)
            )
        )

    def _create(
        self,
        actor: str,
        action: str,
        point_id: UUID,
        machine_id: UUID | None,
        games: list[UUID] | None,
        body_hash: str,
    ) -> ManagementMutationPreviewResponse:
        fingerprint, counts = self._state(point_id, machine_id, games)
        token = secrets.token_urlsafe(32)
        expiry = now() + timedelta(minutes=10)
        self.session.add(
            ManagementMutationPreviewModel(
                token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                actor=actor,
                action=action,
                point_id=point_id,
                machine_id=machine_id,
                game_ids=[str(game) for game in games] if games is not None else None,
                body_sha256=body_hash,
                fingerprint=fingerprint,
                counts=counts.model_dump(mode="json", by_alias=True),
                expires_at=expiry,
            )
        )
        self.session.flush()
        return ManagementMutationPreviewResponse(
            preview_token=token, expires_at=expiry, counts=counts
        )

    def delete_preview(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeletePreviewCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse:
        self._cleanup(actor)
        if machine_id is None:
            actual = self.metadata.lock_point(point_id).revision
        else:
            point, machine = self.metadata.lock_machine(machine_id)
            if point.id != point_id:
                raise ManagementError(
                    "MANAGEMENT_MACHINE_NOT_FOUND", "Machine is not in this point.", 404
                )
            actual = machine.revision
        self.metadata.require_revision(actual, command.expected_revision)
        return self._create(
            actor,
            "point.delete" if machine_id is None else "machine.delete",
            point_id,
            machine_id,
            None,
            digest(command.model_dump(mode="json")),
        )

    def update_preview(
        self,
        machine_id: UUID,
        command: ManagementMachineCommand | ManagementAssignmentCommand,
        actor: str,
    ) -> ManagementMutationPreviewResponse:
        self._cleanup(actor)
        # Use the intended mutation UUID lock so multiple previews and retries
        # cannot cross an already-completed command.
        action = (
            "machine.write"
            if isinstance(command, ManagementMachineCommand)
            else "assignments.write"
        )
        point_id = self.session.scalar(
            select(ManagementMachineModel.point_id).where(ManagementMachineModel.id == machine_id)
        )
        if point_id is None:
            raise ManagementError("MANAGEMENT_MACHINE_NOT_FOUND", "Machine does not exist.", 404)
        target = f"{point_id}/{machine_id}" if action == "machine.write" else str(machine_id)
        _, receipt = self.metadata.begin_operation(command, actor, action, target)
        if receipt is not None:
            raise ManagementError(
                "MANAGEMENT_OPERATION_CONFLICT", "Operation was already completed."
            )
        point, machine = self.metadata.lock_machine(machine_id)
        self.metadata.require_available(point, machine)
        self.metadata.require_revision(machine.revision, command.expected_revision)
        if command.game_ids is None:
            raise ManagementError(
                "MANAGEMENT_PREVIEW_INVALID", "Specify the final game assignments.", 422
            )
        existing = self.session.scalars(
            select(ManagementAssignmentModel.game_id).where(
                ManagementAssignmentModel.machine_id == machine_id
            )
        ).all()
        removed = sorted(set(existing) - set(command.game_ids), key=str)
        return self._create(actor, action, point.id, machine.id, removed, preview_body(command))

    def confirm(
        self,
        preview: ManagementMutationPreviewModel | None,
        actor: str,
        action: str,
        point_id: UUID,
        machine_id: UUID | None,
        games: list[UUID] | None,
        body_hash: str,
    ) -> ManagementMutationCounts:
        if preview is None:
            raise ManagementError("MANAGEMENT_PREVIEW_REQUIRED", "Review the deletion scope first.")
        expiry = preview.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry <= now():
            raise ManagementError("MANAGEMENT_PREVIEW_EXPIRED", "Create a new deletion preview.")
        if (
            preview.actor != actor
            or preview.action != action
            or preview.point_id != point_id
            or preview.machine_id != machine_id
            or preview.game_ids != ([str(game) for game in games] if games is not None else None)
            or preview.body_sha256 != body_hash
        ):
            raise ManagementError(
                "MANAGEMENT_PREVIEW_INVALID", "Preview does not match the command."
            )
        fingerprint, counts = self._state(point_id, machine_id, games)
        if preview.fingerprint != fingerprint:
            raise ManagementError("MANAGEMENT_PREVIEW_STALE", "The scope changed; review it again.")
        return counts

    def purge(self, point_id: UUID, machine_id: UUID | None, games: list[UUID] | None) -> None:
        if self.session.get_bind().dialect.name != "postgresql":
            raise ManagementError(
                "MANAGEMENT_PURGE_REQUIRES_POSTGRESQL",
                "Immutable history purge requires the controlled PostgreSQL procedure.",
                503,
            )
        self.session.execute(
            text("SELECT public.management_purge_scope(:point, :machine, CAST(:games AS uuid[]))"),
            {
                "point": point_id,
                "machine": machine_id,
                "games": [str(game) for game in games] if games is not None else None,
            },
        )
        self.session.expire_all()

    def delete_scope(
        self,
        point_id: UUID,
        machine_id: UUID | None,
        command: ManagementDeleteCommand,
        actor: str,
    ) -> ManagementDeleteResponse:
        action = "point.delete" if machine_id is None else "machine.delete"
        checksum, receipt = self.metadata.begin_operation(
            command, actor, action, f"{point_id}/{machine_id}"
        )
        if receipt is not None:
            return ManagementDeleteResponse.model_validate(receipt)
        preview = self.lock_preview(command.preview_token, actor)
        point = self.metadata.lock_point(point_id)
        actual = point.revision
        if machine_id is not None:
            parent, machine = self.metadata.lock_machine(machine_id)
            if parent.id != point_id:
                raise ManagementError(
                    "MANAGEMENT_MACHINE_NOT_FOUND", "Machine is not in this point.", 404
                )
            actual = machine.revision
        self.metadata.require_revision(actual, command.expected_revision)
        counts = self.confirm(
            preview,
            actor,
            action,
            point_id,
            machine_id,
            None,
            digest({"expected_revision": command.expected_revision}),
        )
        self.purge(point_id, machine_id, None)
        response = ManagementDeleteResponse(
            operation_id=command.operation_id,
            point_id=point_id,
            machine_id=machine_id,
            counts=counts,
        )
        self.session.add(
            ManagementOperationModel(
                operation_id=command.operation_id,
                actor=actor,
                request_checksum=checksum,
                action=action,
                point_id=point_id,
                machine_id=machine_id,
                response=response.model_dump(mode="json", by_alias=True),
            )
        )
        self.session.flush()
        return response
