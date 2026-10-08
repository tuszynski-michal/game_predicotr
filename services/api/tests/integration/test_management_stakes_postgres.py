"""Real application-role persistence, coherent results and concurrent UUID/CAS writes."""

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from _application_role_database import application_role_database
from game_predictor_api.domain.management import (
    ManagementAssignmentCommand,
    ManagementDeleteCommand,
    ManagementDeletePreviewCommand,
    ManagementError,
    ManagementMachineCommand,
    ManagementPointCommand,
)
from game_predictor_api.domain.management_stakes import (
    ManagementClearCommand,
    ManagementCorrectionCommand,
    ManagementRefreshCommand,
    ManagementSaveCommand,
    ManagementSearchCommand,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.management_game_adapter import SqlAlchemyManagementGameAdapter
from game_predictor_api.storage.management_models import (
    ManagementJournalModel,
    ManagementOperationModel,
)
from game_predictor_api.storage.management_repository import SqlAlchemyManagementRepository
from game_predictor_api.storage.management_stake_models import ManagementStakeSlotModel
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
from game_predictor_api.storage.models import (
    GameModel,
    PaylineModel,
    PayoutRuleModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from test_verified_cell_search_projection import _seed_pending_board

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires disposable PostgreSQL.",
)


def _rules(engine, game_id):
    with Session(engine) as session, session.begin():
        game = session.get(GameModel, game_id)
        game.expected_layout_count = 8
        rules = RulesVersionModel(
            game_id=game_id,
            version=2,
            rows=3,
            columns=5,
            spin_cost=20,
            status="published",
            published_at=datetime.now(UTC),
        )
        session.add(rules)
        session.flush()
        symbols = session.scalars(select(SymbolModel).where(SymbolModel.game_id == game_id)).all()
        session.add_all(
            RulesVersionSymbolModel(
                rules_version_id=rules.id,
                symbol_id=symbol.id,
                minimum_match_length=2,
                is_active=True,
            )
            for symbol in symbols
        )
        session.flush()
        session.add(
            PaylineModel(
                rules_version_id=rules.id,
                code="top",
                name="Top",
                row_path=[0] * 5,
                display_order=0,
                is_active=True,
            )
        )
        session.add_all(
            PayoutRuleModel(
                rules_version_id=rules.id,
                symbol_id=symbol.id,
                match_length=length,
                payout_credits=amount,
            )
            for symbol in symbols
            for length, amount in ((2, 5), (3, 10), (4, 25), (5, 50))
        )
        return rules.id


def test_complete_saved_stake_flow_app_role_retry_cas_history_and_new_process(
    tmp_path: Path, monkeypatch
):
    with application_role_database("t0922", ()) as db:
        seed = _seed_pending_board(
            create_session_factory(db.owner_engine), datetime.now(UTC), sibling_positions=(1, 2)
        )
        game = seed.game_id
        rules_id = _rules(db.owner_engine, game)
        with Session(db.app_engine) as session, session.begin():
            meta = SqlAlchemyManagementRepository(session)
            point = meta.point(
                None,
                ManagementPointCommand(
                    operation_id=uuid4(), expected_revision=0, name="P", city="C", street="S"
                ),
                "local-owner",
            )
            machine = meta.machine(
                point.id,
                None,
                ManagementMachineCommand(operation_id=uuid4(), expected_revision=0, name="M"),
                "local-owner",
            )
            meta.assignments(
                machine.id,
                ManagementAssignmentCommand(
                    operation_id=uuid4(), expected_revision=1, game_ids=[game]
                ),
                "local-owner",
            )
        factory = create_session_factory(db.app_engine)
        commands = {}

        def invoke(method, *args, actor="local-owner"):
            with factory() as session, session.begin():
                session.connection().exec_driver_sql("SET LOCAL statement_timeout='20s'")
                repo = SqlAlchemyManagementStakeRepository(session)
                response = getattr(repo, method)(machine.id, game, *args, actor)
                repo.before_commit()
                return response

        # Zero-hit searches are reproducible, journaled and never mutate a slot.
        empty_search = invoke(
            "search",
            ManagementSearchCommand(
                operation_id=uuid4(),
                stake_grosze=2000,
                cells=({"cellIndex": 0, "symbolCode": "second"},),
                scope="approved_only",
                limit=100,
            ),
        )
        assert not empty_search.search.results
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            event = repo.journal(machine.id, game_id=game, stake=2000).entries[0]
            assert event.action == "search" and event.after["resultCount"] == 0
            assert repo.slot(machine.id, game, 2000).empty

        # Auxiliary reads stay coherent while current symbol metadata changes.
        # Ambient game scope must not turn transaction setup into WRITE routing.
        original_snapshot = SqlAlchemyManagementGameAdapter._snapshot

        def concurrent_symbol_change(boards, game_id, start, count):
            configuration = boards.latest_published_rules(game_id)
            assert configuration.spin_cost == 20
            with db.owner_engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE public.symbols SET code='renamed' "
                        "WHERE game_id=:game AND code='first'"
                    ),
                    {"game": game_id},
                )
            return original_snapshot(boards, game_id, start, count)

        with monkeypatch.context() as patch:
            patch.setattr(
                SqlAlchemyManagementGameAdapter,
                "_snapshot",
                staticmethod(concurrent_symbol_change),
            )
            with factory() as session, game_storage_scope(game):
                _, payload, _ = SqlAlchemyManagementGameAdapter(session).snapshot(game, 1, 7)
                assert payload["startSymbolCodes"] == ["first"] * 15
        with db.owner_engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE public.symbols SET code='first' WHERE game_id=:game AND code='renamed'"
                ),
                {"game": game},
            )

        for stake in (2000, 1000, 600, 400, 200, 120):
            search = invoke(
                "search",
                ManagementSearchCommand(
                    operation_id=uuid4(),
                    stake_grosze=stake,
                    cells=(
                        {"cellIndex": 0, "symbolCode": "first"},
                        {"cellIndex": 1, "symbolCode": "?"},
                    ),
                    limit=100,
                ),
            )
            command = ManagementSaveCommand(
                operation_id=uuid4(),
                expected_revision=0,
                search_context_id=search.search_context_id,
                start_sequence_number=1,
                spin_count=7,
                pinned_spin_positions=(0, 3, 7),
            )
            commands[stake] = command
            if stake == 2000:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    first, second = [
                        f.result(timeout=30)
                        for f in [
                            pool.submit(invoke, "save", stake, command),
                            pool.submit(invoke, "save", stake, command),
                        ]
                    ]
                assert first == second
            else:
                invoke("save", stake, command)
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            slots = repo.list_slots(machine.id, game).slots
            assert all(slot.revision == 1 and not slot.empty for slot in slots)
            assert len({slot.result_version_id for slot in slots}) == 1
            initial = repo.result(machine.id, game, slots[0].result_version_id)
            assert initial.calculation.summary.recognized_payout_credits == 100
            assert initial.start_symbol_codes == ("first",) * 15
            assert initial.rules_snapshot["spin_cost"] == 20
            assert slots[0].pinned_points[-1].balance_credits == -40
        # Old pins are filled from the frozen result only, without a GET write.
        # The bounded list reads at most one payload for each of its six slots.
        with factory() as session, session.begin():
            stored = session.scalars(
                select(ManagementStakeSlotModel).where(
                    ManagementStakeSlotModel.machine_id == machine.id
                )
            ).all()
            for slot in stored:
                slot.pinned_points = [
                    {
                        key: value
                        for key, value in pin.items()
                        if key not in {"requiredStakeCredits", "machineCashCredits"}
                    }
                    for pin in slot.pinned_points
                ]
        reads, writes = [], []

        def observe_sql(_conn, _cursor, statement, *_args):
            lowered = statement.lower().lstrip()
            if lowered.startswith("select") and "management_result_versions.payload" in lowered:
                reads.append(statement)
            if lowered.startswith(("insert", "update", "delete")):
                writes.append(statement)

        sqlalchemy_event.listen(db.app_engine, "before_cursor_execute", observe_sql)
        try:
            with factory() as session:
                recovered = (
                    SqlAlchemyManagementStakeRepository(session).list_slots(machine.id, game).slots
                )
                assert len(reads) == 6 and not writes
                assert all(
                    slot.pinned_points[0].required_stake_credits == 0
                    and slot.pinned_points[0].machine_cash_credits == 0
                    for slot in recovered
                )
                assert all(
                    slot.pinned_points[-1].required_stake_credits is not None for slot in recovered
                )
            with factory() as session:
                stored = session.scalars(
                    select(ManagementStakeSlotModel).where(
                        ManagementStakeSlotModel.machine_id == machine.id
                    )
                ).all()
                assert all("requiredStakeCredits" not in slot.pinned_points[0] for slot in stored)
        finally:
            sqlalchemy_event.remove(db.app_engine, "before_cursor_execute", observe_sql)
        assert invoke("save", 2000, commands[2000]).revision == 1
        with pytest.raises(ManagementError, match="already used"):
            invoke("save", 2000, commands[2000].model_copy(update={"spin_count": 6}))
        with pytest.raises(ManagementError, match="already used"):
            invoke("save", 2000, commands[2000], actor="other")
        refreshed = invoke(
            "refresh", 2000, ManagementRefreshCommand(operation_id=uuid4(), expected_revision=1)
        )
        assert not refreshed.changed and refreshed.slot.result_version_id == initial.id

        # A restored saved selection can be edited by another authorized actor.
        replacement = commands[2000].model_copy(
            update={
                "operation_id": uuid4(),
                "expected_revision": 1,
                "pinned_spin_positions": (0, 2, 7),
            }
        )
        assert invoke("save", 2000, replacement, actor="management-share:recipient").revision == 2
        with pytest.raises(ManagementError, match="validated search context"):
            invoke(
                "save",
                600,
                commands[600].model_copy(
                    update={
                        "operation_id": uuid4(),
                        "expected_revision": 1,
                        "start_sequence_number": 2,
                    }
                ),
                actor="management-share:recipient",
            )

        def compete():
            try:
                return invoke(
                    "save",
                    2000,
                    replacement.model_copy(
                        update={"operation_id": uuid4(), "expected_revision": 2}
                    ),
                    actor="management-share:recipient",
                ).revision
            except ManagementError as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = [
                future.result(timeout=30) for future in [pool.submit(compete), pool.submit(compete)]
            ]
        assert sorted(map(str, outcomes)) == ["3", "MANAGEMENT_REVISION_CONFLICT"]

        # Current correction delegates the human writer; snapshots stay immutable.
        with factory() as session:
            detail = SqlAlchemyManagementStakeRepository(session).detail(machine.id, game, 1)
            cell = detail.cells[0]
        correction = ManagementCorrectionCommand(
            operation_id=uuid4(),
            expected_cell_version=cell.cell_version,
            action="reassign",
            target_symbol_code="second",
            search_context_id=commands[2000].search_context_id,
            start_sequence_number=1,
            spin_count=7,
        )

        # A revoked/expired public session guard rolls back the actual human
        # correction, its receipt and audit together after they were flushed.
        def reject_after_write(session):
            def guard():
                if session.get(ManagementOperationModel, correction.operation_id) is not None:
                    raise ManagementError("GUARD_REVOKED", "Session was revoked.")

            return guard

        with (
            pytest.raises(ManagementError, match="revoked"),
            factory() as session,
            session.begin(),
        ):
            repo = SqlAlchemyManagementStakeRepository(
                session, revalidate=reject_after_write(session)
            )
            repo.correct(machine.id, game, 2000, 1, 0, correction, "local-owner")
            repo.before_commit()
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            assert repo.detail(machine.id, game, 1).cells[0].cell_version == cell.cell_version
            assert session.get(ManagementOperationModel, correction.operation_id) is None
            assert (
                session.scalar(
                    select(ManagementJournalModel.id).where(
                        ManagementJournalModel.operation_id == correction.operation_id
                    )
                )
                is None
            )
        result = invoke("correct", 2000, 1, 0, correction)
        assert result.changed and invoke("correct", 2000, 1, 0, correction) == result
        changed = invoke(
            "refresh", 2000, ManagementRefreshCommand(operation_id=uuid4(), expected_revision=3)
        )
        assert changed.changed and changed.slot.start_sequence_number == 1
        assert changed.slot.pinned_spin_positions == (0, 2, 7)
        assert changed.slot.start_symbol_codes[0] == "second"
        # Reopen/save keeps the original server-approved start and pattern even
        # after current corrections stop matching the saved search pattern.
        restored = invoke(
            "save",
            1000,
            commands[1000].model_copy(
                update={
                    "operation_id": uuid4(),
                    "expected_revision": 1,
                    "pinned_spin_positions": (0, 6),
                }
            ),
            actor="management-share:recipient",
        )
        assert restored.start_sequence_number == 1
        assert restored.query["cells"][0]["symbolCode"] == "first"
        assert restored.start_symbol_codes[0] == "second"
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            assert repo.result(machine.id, game, initial.id).start_symbol_codes[0] == "first"
            events = repo.journal(machine.id, game_id=game, stake=2000, limit=100).entries
            assert any(
                event.action == "symbol.correct"
                and event.before["symbolCode"] == "first"
                and event.after["symbolCode"] == "second"
                for event in events
            )
            assert any(
                event.action == "stake.recalculate"
                and event.before_result_id == initial.id
                and event.after_result_id == changed.slot.result_version_id
                for event in events
            )
            with pytest.raises(DBAPIError, match="immutable"):
                session.execute(text("UPDATE public.management_result_versions SET summary='{}'"))
            session.rollback()

        # Missing rules are stale, with no replacement numeric zeros or revision bump.
        with db.owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE public.rules_versions SET status='draft' WHERE id=:id"),
                {"id": rules_id},
            )
        stale = invoke(
            "refresh", 2000, ManagementRefreshCommand(operation_id=uuid4(), expected_revision=4)
        )
        assert (
            stale.status == "stale"
            and stale.slot.result_version_id == changed.slot.result_version_id
            and stale.slot.revision == 4
        )
        with db.owner_engine.begin() as conn:
            conn.execute(
                text("UPDATE public.rules_versions SET status='published' WHERE id=:id"),
                {"id": rules_id},
            )
            conn.execute(
                text("UPDATE public.games SET expected_layout_count=4 WHERE id=:id"), {"id": game}
            )
        shrink = invoke(
            "refresh", 2000, ManagementRefreshCommand(operation_id=uuid4(), expected_revision=4)
        )
        assert shrink.changed and shrink.slot.unavailable_pin_positions == (7,)
        assert not shrink.slot.pinned_points[-1].available
        clear_command = ManagementClearCommand(
            operation_id=uuid4(), expected_revision=5, confirmed=True
        )
        clear = invoke(
            "clear",
            2000,
            clear_command,
        )
        assert clear.empty and clear.revision == 6
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            assert not repo.slot(machine.id, game, 1000).empty
            assert repo.result(machine.id, game, initial.id).calculation == initial.calculation
            page = repo.journal(machine.id, limit=2)
            assert page.next_cursor and len(page.entries) == 2
            second = repo.journal(machine.id, before=page.next_cursor, limit=2)
            assert not {event.id for event in page.entries} & {event.id for event in second.entries}

        # A fresh process sees saved selection and immutable original chart.
        env = db.subprocess_environment(
            MANAGEMENT_TEST_URL=db.app_url.render_as_string(hide_password=False),
            MANAGEMENT_MACHINE=str(machine.id),
            MANAGEMENT_GAME=str(game),
            MANAGEMENT_VERSION=str(initial.id),
        )
        process = subprocess.run(
            [
                sys.executable,
                "-c",
                """
import os
from uuid import UUID
from sqlalchemy import create_engine
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.management_stake_repository import (
    SqlAlchemyManagementStakeRepository,
)
engine=create_engine(os.environ['MANAGEMENT_TEST_URL'])
with create_session_factory(engine)() as session:
    repo=SqlAlchemyManagementStakeRepository(session)
    machine=UUID(os.environ['MANAGEMENT_MACHINE']); game=UUID(os.environ['MANAGEMENT_GAME'])
    assert repo.slot(machine,game,2000).empty
    assert not repo.slot(machine,game,1000).empty
    result=repo.result(machine,game,UUID(os.environ['MANAGEMENT_VERSION']))
    assert result.start_symbol_codes[0]=='first'
engine.dispose()
""",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=25,
        )
        assert process.returncode == 0, process.stderr

        # Detaching/archive keeps history reachable; new writes fail.
        with db.owner_engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE public.management_assignments SET attached=false "
                    "WHERE machine_id=:machine"
                ),
                {"machine": machine.id},
            )
            conn.execute(
                text("UPDATE public.games SET status='archived' WHERE id=:game"), {"game": game}
            )
            conn.execute(
                text("DELETE FROM public.game_storage_locations WHERE game_id=:game"),
                {"game": game},
            )
        with factory() as session:
            repo = SqlAlchemyManagementStakeRepository(session)
            assert not repo.slot(machine.id, game, 1000).empty
            assert repo.result(machine.id, game, initial.id).id == initial.id
            assert repo.journal(machine.id, game_id=game).entries
        with pytest.raises(ManagementError, match="active and attached"):
            invoke(
                "save",
                1000,
                commands[1000].model_copy(update={"operation_id": uuid4(), "expected_revision": 1}),
            )
        # Structural purge redacts ALL historical retries, including a cleared slot
        # and an ordinary machine update, while keeping the actual game catalog.
        with factory() as session, session.begin():
            meta = SqlAlchemyManagementRepository(session)
            _, current = meta.lock_machine(machine.id)
            rename = ManagementMachineCommand(
                operation_id=uuid4(), expected_revision=current.revision, name="Before deletion"
            )
            renamed = meta.machine(point.id, machine.id, rename, "local-owner")
            preview = meta.delete_preview(
                point.id,
                machine.id,
                ManagementDeletePreviewCommand(expected_revision=renamed.revision),
                "local-owner",
            )
            meta.delete_scope(
                point.id,
                machine.id,
                ManagementDeleteCommand(
                    operation_id=uuid4(),
                    expected_revision=renamed.revision,
                    preview_token=preview.preview_token,
                    confirmed=True,
                ),
                "local-owner",
            )
            with pytest.raises(ManagementError) as deleted:
                meta.machine(point.id, machine.id, rename, "local-owner")
            assert deleted.value.code == "MANAGEMENT_TARGET_DELETED"
            assert session.get(GameModel, game) is not None
        for method, stake, old_command in (
            ("save", 1000, commands[1000]),
            ("clear", 2000, clear_command),
        ):
            with pytest.raises(ManagementError) as deleted:
                invoke(method, stake, old_command)
            assert deleted.value.code == "MANAGEMENT_TARGET_DELETED"
