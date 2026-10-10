"""Preview binding, atomic command and exact legacy retry regressions."""

import hashlib
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementError,
    ManagementMachineCommand,
)
from game_predictor_api.storage.management_models import (
    ManagementJournalModel,
    ManagementMutationPreviewModel,
    ManagementOperationModel,
    now,
)
from game_predictor_api.storage.management_mutation_repository import (
    ManagementMutationRepository,
    digest,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_stake_models import ManagementStakeSlotModel
from game_predictor_api.storage.models import GameModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_management import database as management_database
from test_management import point_command

# Register the shared fixture locally; pytest_plugins loses this fixture when
# its defining test module is also collected in the same invocation.
database = management_database


def test_atomic_create_games_single_journal_and_omitted_games_unchanged(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        game = GameModel(code="atomic", name="Atomic", status=GameStatus.ACTIVE)
        session.add(game)
        session.flush()
        command = ManagementMachineCommand(
            operation_id=uuid4(), expected_revision=0, name="Machine", game_ids=[game.id]
        )
        machine = repo.machine(point.id, None, command, "local-owner")
        assert [row.game_id for row in machine.assignments] == [game.id]
        assert repo.machine(point.id, None, command, "local-owner") == machine
        assert session.scalar(select(func.count()).select_from(ManagementJournalModel)) == 2
        updated = repo.machine(
            point.id,
            machine.id,
            ManagementMachineCommand(
                operation_id=uuid4(),
                expected_revision=machine.revision,
                name="Renamed",
            ),
            "local-owner",
        )
        assert updated.name == "Renamed" and updated.assignments == machine.assignments


def test_atomic_create_invalid_game_rolls_back_everything(database):
    with Session(database) as session:
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        session.commit()
        with pytest.raises(ManagementError) as denied:
            repo.machine(
                point.id,
                None,
                ManagementMachineCommand(
                    operation_id=uuid4(),
                    expected_revision=0,
                    name="Invalid",
                    game_ids=[uuid4()],
                ),
                "local-owner",
            )
        assert denied.value.code == "MANAGEMENT_GAME_NOT_ACTIVE"
        session.rollback()
        assert repo.snapshot().points[0].machines == []
        assert session.scalar(select(func.count()).select_from(ManagementOperationModel)) == 1


def test_preview_actor_expiry_and_changed_scope_fail_closed(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        preview = repo.delete_preview(
            point.id,
            None,
            ManagementDeletePreviewCommand(
                expected_revision=point.revision,
            ),
            "local-owner",
        )
        row = session.scalar(select(ManagementMutationPreviewModel))
        assert row.token_sha256 == hashlib.sha256(preview.preview_token.encode()).hexdigest()
        assert row.token_sha256 != preview.preview_token
        assert preview.counts.points == 1 and preview.counts.journal_entries == 1
        mutations = ManagementMutationRepository(repo)
        with pytest.raises(ManagementError) as denied:
            mutations.lock_preview(preview.preview_token, "session:other")
        assert denied.value.code == "MANAGEMENT_PREVIEW_INVALID"
        locked = mutations.lock_preview(preview.preview_token, "local-owner")
        repo.machine(
            point.id,
            None,
            ManagementMachineCommand(
                operation_id=uuid4(),
                expected_revision=0,
                name="Added in another window",
            ),
            "local-owner",
        )
        with pytest.raises(ManagementError) as stale:
            mutations.confirm(
                locked,
                "local-owner",
                "point.delete",
                point.id,
                None,
                None,
                digest({"expected_revision": point.revision}),
            )
        assert stale.value.code == "MANAGEMENT_PREVIEW_STALE"
        row.expires_at = now() - timedelta(seconds=1)
        session.flush()
        with pytest.raises(ManagementError) as expired:
            mutations.lock_preview(preview.preview_token, "local-owner")
        assert expired.value.code == "MANAGEMENT_PREVIEW_EXPIRED"
        assert len(repo.snapshot().points[0].machines) == 1


def test_old_machine_checksum_survives_optional_contract_fields(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        command = ManagementMachineCommand(
            operation_id=uuid4(),
            expected_revision=0,
            name="Legacy",
        )
        response = repo.machine(point.id, None, command, "local-owner")
        old_body = command.model_dump(mode="json", exclude={"game_ids", "preview_token"})
        checksum = hashlib.sha256(
            json.dumps(
                {
                    "actor": "local-owner",
                    "action": "machine.write",
                    "target": f"{point.id}/None",
                    "body": old_body,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        assert (
            session.get(ManagementOperationModel, command.operation_id).request_checksum == checksum
        )
        assert repo.machine(point.id, None, command, "local-owner") == response


def test_deleted_marker_fails_after_identity_check_and_delete_receipt_survives(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        command = ManagementAssignmentCommand(
            operation_id=uuid4(), expected_revision=1, game_ids=[]
        )
        machine_id = uuid4()
        checksum, _ = repo.begin_operation(
            command, "local-owner", "assignments.write", str(machine_id)
        )
        session.add(
            ManagementOperationModel(
                operation_id=command.operation_id,
                actor="local-owner",
                request_checksum=checksum,
                response={"managementReceiptState": "target_deleted"},
            )
        )
        session.flush()
        with pytest.raises(ManagementError) as deleted:
            repo.begin_operation(command, "local-owner", "assignments.write", str(machine_id))
        assert deleted.value.code == "MANAGEMENT_TARGET_DELETED"
        with pytest.raises(ManagementError) as wrong_actor:
            repo.begin_operation(command, "other", "assignments.write", str(machine_id))
        assert wrong_actor.value.code == "MANAGEMENT_OPERATION_CONFLICT"


def test_delete_requires_confirmation():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ManagementDeleteCommand(
            operation_id=uuid4(),
            expected_revision=1,
            preview_token="x" * 43,
            confirmed=False,
        )


def test_preview_cleanup_is_bounded_and_actor_scoped(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        for index in range(106):
            session.add(
                ManagementMutationPreviewModel(
                    token_sha256=f"{index:064x}",
                    actor="local-owner" if index < 103 else "other",
                    action="point.delete",
                    point_id=point.id,
                    body_sha256="a" * 64,
                    fingerprint="b" * 64,
                    counts={},
                    expires_at=now() - timedelta(minutes=1),
                )
            )
        session.flush()
        repo.delete_preview(
            point.id,
            None,
            ManagementDeletePreviewCommand(expected_revision=point.revision),
            "local-owner",
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ManagementMutationPreviewModel)
                .where(ManagementMutationPreviewModel.actor == "local-owner")
            )
            == 4
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(ManagementMutationPreviewModel)
                .where(ManagementMutationPreviewModel.actor == "other")
            )
            == 3
        )


def test_preview_binds_body_scope_and_saved_slot_revision(database):
    with Session(database) as session, session.begin():
        repo = SqlAlchemyManagementRepository(session)
        point = repo.point(None, point_command(), "local-owner")
        game = GameModel(code="slot-preview", name="Slot", status=GameStatus.ACTIVE)
        session.add(game)
        session.flush()
        machine = repo.machine(
            point.id,
            None,
            ManagementMachineCommand(
                operation_id=uuid4(), expected_revision=0, name="Machine", game_ids=[game.id]
            ),
            "local-owner",
        )
        slot = ManagementStakeSlotModel(machine_id=machine.id, game_id=game.id, stake_grosze=2000)
        session.add(slot)
        session.flush()
        preview = repo.delete_preview(
            point.id,
            machine.id,
            ManagementDeletePreviewCommand(expected_revision=machine.revision),
            "local-owner",
        )
        mutations = ManagementMutationRepository(repo)
        locked = mutations.lock_preview(preview.preview_token, "local-owner")
        for wrong_machine, body in (
            (machine.id, "wrong-body"),
            (uuid4(), digest({"expected_revision": machine.revision})),
        ):
            with pytest.raises(ManagementError) as denied:
                mutations.confirm(
                    locked, "local-owner", "machine.delete", point.id, wrong_machine, None, body
                )
            assert denied.value.code == "MANAGEMENT_PREVIEW_INVALID"
        slot.revision += 1
        session.flush()
        with pytest.raises(ManagementError) as stale:
            mutations.confirm(
                locked,
                "local-owner",
                "machine.delete",
                point.id,
                machine.id,
                None,
                digest({"expected_revision": machine.revision}),
            )
        assert stale.value.code == "MANAGEMENT_PREVIEW_STALE"
