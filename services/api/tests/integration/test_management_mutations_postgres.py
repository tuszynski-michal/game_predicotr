"""Real owner/app-role purge, shared results, retries and transaction rollback."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.application.management_access import ManagementAccessService
from game_predictor_api.domain.management import (
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementError,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.storage.database_roles import describe_application_role
from game_predictor_api.storage.management_models import (
    ManagementAssignmentModel,
    ManagementJournalModel,
    ManagementMachineModel,
    ManagementMutationPreviewModel,
    ManagementOperationModel,
    ManagementPointModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_session_models import ManagementSessionAuditModel
from game_predictor_api.storage.management_session_repository import (
    SqlAlchemyManagementSessionRepository,
)
from game_predictor_api.storage.management_stake_models import (
    ManagementResultVersionModel,
    ManagementSearchContextModel,
    ManagementStakeSlotModel,
)
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
from game_predictor_api.storage.models import GameModel
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires a disposable PostgreSQL database and application role.",
)


def _point(repo, name):
    return repo.point(
        None,
        ManagementPointCommand(
            operation_id=uuid4(),
            expected_revision=0,
            name=name,
            city="City",
            street="Street",
        ),
        "local-owner",
    )


def _machine(repo, point, game, name="Machine"):
    command = ManagementMachineCommand(
        operation_id=uuid4(),
        expected_revision=0,
        name=name,
        game_ids=[game],
    )
    return repo.machine(point.id, None, command, "local-owner"), command


def _save_fixture(session, point, machine, game, version):
    """Valid relational fixture for storage purge; numeric content is opaque here."""
    operation = uuid4()
    session.add(
        ManagementOperationModel(
            operation_id=operation,
            actor="local-owner",
            request_checksum="b" * 64,
            response={"searchContextId": str(operation)},
            action="search",
            point_id=point.id,
            machine_id=machine.id,
            game_id=game,
        )
    )
    session.flush()
    session.add(
        ManagementSearchContextModel(
            id=operation,
            machine_id=machine.id,
            game_id=game,
            stake_grosze=2000,
            actor="local-owner",
            query={},
            sequence_numbers=[1],
        )
    )
    session.flush()
    session.add(
        ManagementStakeSlotModel(
            machine_id=machine.id,
            game_id=game,
            stake_grosze=2000,
            search_context_id=operation,
            start_sequence_number=1,
            spin_count=1,
            result_version_id=version,
            pinned_spin_positions=[],
            pinned_points=[],
        )
    )
    session.add(
        ManagementJournalModel(
            operation_id=operation,
            actor="local-owner",
            action="save",
            point_id=point.id,
            machine_id=machine.id,
            game_id=game,
            before={},
            after={},
            after_result_id=version,
        )
    )
    session.flush()
    return operation


def test_purge_roles_preview_shared_version_retry_and_rollback():
    with application_role_database("t0940purge", ("purge",)) as db:
        game = db.games["purge"]
        with db.owner_engine.begin() as conn:
            conn.execute(text("UPDATE public.games SET status='active' WHERE id=:id"), {"id": game})
            assert describe_application_role(conn, db.role).compliant
        for statement in (
            "GRANT EXECUTE ON FUNCTION public.management_purge_scope(uuid,uuid,uuid[]) TO PUBLIC",
            "ALTER FUNCTION public.management_purge_scope(uuid,uuid,uuid[]) SECURITY INVOKER",
            "ALTER FUNCTION public.management_purge_scope(uuid,uuid,uuid[]) SET search_path=public",
        ):
            with db.owner_engine.connect() as conn:
                conn.execute(text(statement))
                assert describe_application_role(conn, db.role).management_function_errors
                conn.rollback()
                assert describe_application_role(conn, db.role).compliant
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            point = _point(repo, "Deleted point")
            survivor = _point(repo, "Surviving point")
            first, first_create = _machine(repo, point, game)
            second, second_create = _machine(repo, point, game, "Second")
            other, _ = _machine(repo, survivor, game, "Other point")
            ManagementAccessService(SqlAlchemyManagementSessionRepository(session)).create(
                "Security audit survives purge", 480
            )
            version = ManagementResultVersionModel(
                game_id=game,
                content_sha256="a" * 64,
                payload={"fixture": "opaque"},
                summary={"fixture": "opaque"},
            )
            session.add(version)
            session.flush()
            version_id = version.id
            old_search = _save_fixture(session, point, first, game, version_id)
            _save_fixture(session, point, second, game, version_id)
            _save_fixture(session, survivor, other, game, version_id)

        # Neither application-controlled flags nor owner identity alone can
        # modify history. The transaction is rolled back after each probe.
        for engine, statement in (
            (db.app_engine, "SELECT set_config('management.maintenance_mode','purge',true)"),
            (db.owner_engine, "SELECT set_config('management.maintenance_mode','',true)"),
        ):
            with engine.connect() as conn:
                conn.execute(text(statement))
                with pytest.raises(DBAPIError, match="immutable"):
                    conn.execute(text("DELETE FROM public.management_journal"))
                conn.rollback()
                conn.execute(text("SELECT set_config('management.maintenance_mode','purge',true)"))
                with pytest.raises(DBAPIError, match="immutable"):
                    conn.execute(text("UPDATE public.management_operations SET actor='forged'"))
                conn.rollback()
                conn.execute(text("SELECT set_config('management.maintenance_mode','purge',true)"))
                with pytest.raises(DBAPIError, match="immutable"):
                    conn.execute(text("DELETE FROM public.management_session_audit"))
                conn.rollback()

        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            preview = repo.delete_preview(
                point.id,
                first.id,
                ManagementDeletePreviewCommand(
                    expected_revision=first.revision,
                ),
                "local-owner",
            )
            assert preview.counts.slots == 1 and preview.counts.search_contexts == 1
            delete_first = ManagementDeleteCommand(
                operation_id=uuid4(),
                expected_revision=first.revision,
                preview_token=preview.preview_token,
                confirmed=True,
            )
            deleted_first = repo.delete_scope(point.id, first.id, delete_first, "local-owner")
            assert deleted_first.deleted and deleted_first.counts.machines == 1
            assert session.get(ManagementResultVersionModel, version_id) is not None
            assert session.get(GameModel, game) is not None
            assert session.get(ManagementOperationModel, old_search).response == {
                "managementReceiptState": "target_deleted"
            }
            with pytest.raises(ManagementError) as denied:
                repo.machine(point.id, None, first_create, "local-owner")
            assert denied.value.code == "MANAGEMENT_TARGET_DELETED"

        # An exact retry uses its own receipt before checking the missing row.
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            assert (
                repo.delete_scope(point.id, first.id, delete_first, "local-owner") == deleted_first
            )
            detach = ManagementMachineCommand(
                operation_id=uuid4(),
                expected_revision=second.revision,
                name="Renamed and detached atomically",
                game_ids=[],
            )
            preview = repo.update_preview(second.id, detach, "local-owner")
            confirmed_detach = detach.model_copy(update={"preview_token": preview.preview_token})
            updated = repo.machine(
                point.id,
                second.id,
                confirmed_detach,
                "local-owner",
            )
            assert updated.name == detach.name and updated.revision == second.revision + 1
            assert updated.assignments == []
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ManagementJournalModel)
                    .where(ManagementJournalModel.operation_id == detach.operation_id)
                )
                == 1
            )
            assert session.get(ManagementAssignmentModel, (second.id, game)) is None
            assert session.get(ManagementResultVersionModel, version_id) is not None

        # A purge performed inside a failed transaction leaves no success receipt
        # and restores the entire scope and its immutable journal.
        with Session(db.app_engine) as session:
            repo = SqlAlchemyManagementRepository(session)
            preview = repo.delete_preview(
                survivor.id,
                other.id,
                ManagementDeletePreviewCommand(
                    expected_revision=other.revision,
                ),
                "local-owner",
            )
            session.commit()
            failed = ManagementDeleteCommand(
                operation_id=uuid4(),
                expected_revision=other.revision,
                preview_token=preview.preview_token,
                confirmed=True,
            )
            repo.delete_scope(survivor.id, other.id, failed, "local-owner")
            session.rollback()
            assert session.get(ManagementMachineModel, other.id) is not None
            assert session.get(ManagementOperationModel, failed.operation_id) is None
            assert session.get(ManagementStakeSlotModel, (other.id, game, 2000)) is not None
            assert session.get(ManagementResultVersionModel, version_id) is not None

        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            preview = repo.delete_preview(
                point.id,
                None,
                ManagementDeletePreviewCommand(
                    expected_revision=point.revision,
                ),
                "local-owner",
            )
            delete_point = ManagementDeleteCommand(
                operation_id=uuid4(),
                expected_revision=point.revision,
                preview_token=preview.preview_token,
                confirmed=True,
            )
            repo.delete_scope(point.id, None, delete_point, "local-owner")
            assert session.get(ManagementPointModel, point.id) is None
            assert session.get(ManagementMachineModel, second.id) is None
            assert session.get(ManagementResultVersionModel, version_id) is not None
            # Parent purge never redacts the successful child delete receipt.
            assert (
                repo.delete_scope(point.id, first.id, delete_first, "local-owner") == deleted_first
            )
            with pytest.raises(ManagementError) as denied:
                repo.machine(point.id, None, second_create, "local-owner")
            assert denied.value.code == "MANAGEMENT_TARGET_DELETED"
            with pytest.raises(ManagementError) as denied:
                repo.machine(point.id, second.id, confirmed_detach, "local-owner")
            assert denied.value.code == "MANAGEMENT_TARGET_DELETED"
            assert (
                session.scalar(select(func.count()).select_from(ManagementMutationPreviewModel)) > 0
            )

        # A writer holds the SAME digest advisory lock used by the SQL purge.
        # The purge waits, then sees the committed new reference in another point.
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            new_point = _point(repo, "Concurrent writer")
            new_machine, _ = _machine(repo, new_point, game)
        locked, release = Event(), Event()

        def write_reference():
            with Session(db.app_engine) as session, session.begin():
                meta = SqlAlchemyManagementRepository(session)
                meta.lock_machine(new_machine.id)
                adapter = SimpleNamespace(
                    snapshot=lambda *_: ("a" * 64, {"fixture": "opaque"}, {"fixture": "opaque"})
                )
                version = SqlAlchemyManagementStakeRepository(session, adapter=adapter)._version(
                    game, 1, 1
                )
                assert version.id == version_id
                locked.set()
                assert release.wait(5)
                _save_fixture(session, new_point, new_machine, game, version.id)

        def delete_final_old_scope():
            with Session(db.app_engine) as session, session.begin():
                SqlAlchemyManagementRepository(session).delete_scope(
                    survivor.id, other.id, failed, "local-owner"
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            writing = pool.submit(write_reference)
            assert locked.wait(5)
            deleting = pool.submit(delete_final_old_scope)
            try:
                deadline = time.monotonic() + 3
                with db.app_engine.connect() as conn:
                    while not conn.scalar(
                        text(
                            "SELECT count(*) FROM pg_locks "
                            "WHERE locktype='advisory' AND NOT granted"
                        )
                    ):
                        assert time.monotonic() < deadline, "purge must wait for the dedup writer"
                        time.sleep(0.01)
            finally:
                release.set()
            writing.result(10)
            deleting.result(10)
        # Once the final referencing scope is deleted, its frozen result can go.
        with Session(db.app_engine) as session, session.begin():
            repo = SqlAlchemyManagementRepository(session)
            assert session.get(ManagementResultVersionModel, version_id) is not None
            preview = repo.delete_preview(
                new_point.id,
                new_machine.id,
                ManagementDeletePreviewCommand(expected_revision=new_machine.revision),
                "local-owner",
            )
            repo.delete_scope(
                new_point.id,
                new_machine.id,
                ManagementDeleteCommand(
                    operation_id=uuid4(),
                    expected_revision=new_machine.revision,
                    preview_token=preview.preview_token,
                    confirmed=True,
                ),
                "local-owner",
            )
            assert session.get(ManagementResultVersionModel, version_id) is None
            assert session.get(GameModel, game) is not None
            assert (
                session.scalar(select(func.count()).select_from(ManagementSessionAuditModel)) == 1
            )
        # Response loss and restart preserve a child deletion receipt even after
        # the entire parent scope and all shared results have disappeared.
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import json, os
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.domain.management import ManagementDeleteCommand
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
engine = create_engine(os.environ['MANAGEMENT_TEST_URL'])
with Session(engine) as session, session.begin():
    receipt = SqlAlchemyManagementRepository(session).delete_scope(
        UUID(os.environ['MANAGEMENT_POINT']), UUID(os.environ['MANAGEMENT_MACHINE']),
        ManagementDeleteCommand.model_validate_json(os.environ['MANAGEMENT_DELETE']), 'local-owner')
    expected = json.loads(os.environ['MANAGEMENT_RECEIPT'])
    assert receipt.model_dump(mode='json', by_alias=True) == expected
engine.dispose()
""",
            ],
            env=db.subprocess_environment(
                MANAGEMENT_TEST_URL=db.app_url.render_as_string(hide_password=False),
                MANAGEMENT_POINT=str(point.id),
                MANAGEMENT_MACHINE=str(first.id),
                MANAGEMENT_DELETE=delete_first.model_dump_json(by_alias=True),
                MANAGEMENT_RECEIPT=deleted_first.model_dump_json(by_alias=True),
            ),
            capture_output=True,
            text=True,
            timeout=25,
        )
        assert process.returncode == 0, process.stderr
