"""TASK-1191 / D-605: equality membership lookup of the cohort currentness trigger.

The v1 trigger (array containment on member rows) stays installed but unused, so
the same evidence writes are replayed against v1 and v2 on probe tables and the
resulting notices must be identical, row for row, under the application role.
"""

from __future__ import annotations

import os
from collections import Counter
from uuid import UUID, uuid4

import pytest
from _application_role_database import ALEMBIC_INI, application_role_database
from alembic import command
from alembic.config import Config
from game_predictor_api.storage.game_partition_lifecycle import partition_name
from game_predictor_api.storage.grid_cohort_member_refs_migration import LOOKUP_SQL
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit disposable PostgreSQL only",
)
REFS = "game_data_v2.grid_training_cohort_member_refs"
PROBE_COLUMNS = (
    "id",
    "source_image_id",
    "recognized_board_id",
    "canonical_board_id",
    "review_item_id",
    "image_review_item_id",
    "cell_id",
    "symbol_review_cell_id",
    "quality_issue",
    "source_geometry_revision_id",
    "approved_source_geometry_revision_id",
    "note",
)
CLASSIFICATIONS = (
    "source",
    "source_revision",
    "board",
    "board_evidence",
    "review",
    "review_evidence",
    "owner",
    "cell",
    "cell_evidence",
)


def _config(db) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url", db.owner_url.render_as_string(hide_password=False).replace("%", "%%")
    )
    return config


def _scope(connection: Connection, game: UUID) -> None:
    connection.execute(
        text("SELECT set_config('game_predictor.game_id', :g, true)"), {"g": str(game)}
    )
    connection.execute(text("SELECT set_config('search_path', 'game_data_v2, public', true)"))


def _cohort(connection: Connection, game: UUID, status: str = "preparing") -> UUID:
    cohort = uuid4()
    manifest = None if status == "preparing" else "a" * 64
    connection.execute(
        text(
            "INSERT INTO game_data_v2.grid_training_cohorts"
            "(game_id,id,status,document,manifest_path,manifest_sha256,created_by) "
            "VALUES(:g,:c,:s,'{}'::jsonb,:p,:m,'fixture:1190')"
        ),
        {"g": game, "c": cohort, "s": status, "p": manifest and "fixture.json", "m": manifest},
    )
    return cohort


def _member(
    connection: Connection,
    game: UUID,
    cohort: UUID,
    source: UUID,
    ordinal: int,
    boards: list[UUID],
    reviews: list[UUID],
    cells: list[UUID],
) -> None:
    connection.execute(
        text(
            "INSERT INTO game_data_v2.grid_training_cohort_members"
            "(game_id,cohort_id,source_id,ordinal) VALUES(:g,:c,:s,:o)"
        ),
        {"g": game, "c": cohort, "s": source, "o": ordinal},
    )
    # Capture: the only array write the immutability trigger admits (preparing).
    connection.execute(
        text(
            "UPDATE game_data_v2.grid_training_cohort_members SET role='TRAIN',"
            "frozen=jsonb_build_object('captured','yes'),board_ids=CAST(:b AS uuid[]),"
            "review_ids=CAST(:r AS uuid[]),cell_ids=CAST(:x AS uuid[]) "
            "WHERE game_id=:g AND cohort_id=:c AND source_id=:s"
        ),
        {
            "g": game,
            "c": cohort,
            "s": source,
            "b": [str(v) for v in boards],
            "r": [str(v) for v in reviews],
            "x": [str(v) for v in cells],
        },
    )


def _pairs(connection: Connection, table: str, game: UUID) -> set[tuple[str, ...]]:
    if table == "refs":
        rows = connection.execute(
            text(f"SELECT cohort_id,member_source_id,ref_kind,ref_id FROM {REFS} WHERE game_id=:g"),
            {"g": game},
        )
    else:
        rows = connection.execute(
            text(
                "SELECT m.cohort_id,m.source_id,p.k,p.v FROM "
                "game_data_v2.grid_training_cohort_members m CROSS JOIN LATERAL ("
                "SELECT 'source' k,m.source_id v UNION SELECT 'board',unnest(m.board_ids) "
                "UNION SELECT 'review',unnest(m.review_ids) "
                "UNION SELECT 'cell',unnest(m.cell_ids)) p WHERE m.game_id=:g"
            ),
            {"g": game},
        )
    return {tuple(str(value) for value in row) for row in rows}


def _install_probes(connection: Connection, role: str) -> None:
    columns = ",".join(
        f"{name} {'text' if name in ('quality_issue', 'note') else 'uuid'}"
        for name in PROBE_COLUMNS
    )
    for classification in CLASSIFICATIONS:
        for version in ("v1", "v2"):
            table = f"probe_{classification}_{version}"
            connection.execute(
                text(f"CREATE TABLE public.{table}(game_id uuid NOT NULL,{columns})")
            )
            connection.execute(text(f'GRANT ALL ON public.{table} TO "{role}"'))
            connection.execute(
                text(
                    f"CREATE TRIGGER notice BEFORE INSERT OR UPDATE OR DELETE ON public.{table} "
                    f"FOR EACH ROW EXECUTE FUNCTION game_data_v2.grid_cohort_notice_{version}"
                    f"('{classification}','{classification}')"
                )
            )


def _notices(connection: Connection, game: UUID) -> Counter[tuple[str, ...]]:
    rows = connection.execute(
        text(
            "SELECT cohort_id,kind,source_id,board_id,review_id,cell_id,document "
            "FROM game_data_v2.grid_training_cohort_events WHERE game_id=:g "
            "AND kind='currentness_notice'"
        ),
        {"g": game},
    )
    return Counter(tuple(str(value) for value in row) for row in rows)


def _replay(db, game: UUID, version: str, steps) -> Counter[tuple[str, ...]]:
    with db.app_engine.begin() as connection:
        _scope(connection, game)
        before = _notices(connection, game)
        for classification, statement, params in steps:
            connection.execute(
                text(statement.format(table=f"public.probe_{classification}_{version}")),
                {"g": game, **params},
            )
        after = _notices(connection, game)
    after.subtract(before)
    return +after


def test_v2_notices_equal_v1_and_lookup_uses_the_index_under_rls() -> None:
    with application_role_database("t1190refs", ("refs-a", "refs-b")) as db:
        game, other = db.games["refs-a"], db.games["refs-b"]
        s1, s2, s3 = uuid4(), uuid4(), uuid4()
        b1, b2, r1, r2 = uuid4(), uuid4(), uuid4(), uuid4()
        c1, c2, c3 = uuid4(), uuid4(), uuid4()
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            first, second = _cohort(connection, game), _cohort(connection, game)
            _member(connection, game, first, s1, 0, [b1], [r1], [c1, c2])
            _member(connection, game, first, s2, 1, [b2], [r2], [c3])
            # A dependency cell shared by two members still yields one notice per member.
            _member(connection, game, first, s3, 2, [], [], [c1])
            _member(connection, game, second, s1, 0, [b1], [r1], [c1])
            assert _pairs(connection, "refs", game) == _pairs(connection, "members", game)
            assert len(_pairs(connection, "refs", game)) == 15
        with db.app_engine.begin() as connection:
            _scope(connection, other)
            # RLS: another game's scope sees no lookup pair of this game, neither
            # through the parent nor directly through the game's own partition
            # (created by the partition lifecycle after the migration).
            assert connection.scalar(text(f"SELECT count(*) FROM {REFS}")) == 0
            child = partition_name(game, "grid_training_cohort_member_refs")
            assert connection.scalar(text(f"SELECT count(*) FROM game_data_v2.{child}")) == 0
        with db.owner_engine.connect() as connection:
            for code in ("refs-a", "refs-b"):
                child = partition_name(db.games[code], "grid_training_cohort_member_refs")
                flags = connection.execute(
                    text(
                        "SELECT c.relrowsecurity,c.relforcerowsecurity,"
                        "(SELECT count(*) FROM pg_policy p WHERE p.polrelid=c.oid "
                        "AND p.polname='game_scope_v1') FROM pg_class c "
                        "JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE n.nspname='game_data_v2' AND c.relname=:t"
                    ),
                    {"t": child},
                ).one()
                assert tuple(flags) == (True, True, 1), (child, flags)
        with db.owner_engine.begin() as connection:
            _install_probes(connection, db.role)
        ids = {
            "source": ("id", s1, s2),
            "source_revision": ("source_image_id", s1, s3),
            "board": ("id", b1, b2),
            "board_evidence": ("recognized_board_id", b1, uuid4()),
            "review": ("id", r1, r2),
            "review_evidence": ("image_review_item_id", r2, r1),
            "owner": ("canonical_board_id", b2, b1),
            "cell": ("id", c1, c3),
            "cell_evidence": ("symbol_review_cell_id", c1, c2),
        }
        steps = []
        for classification, (column, hit, moved) in ids.items():
            note = "grid_issue" if classification == "cell_evidence" else "x"
            steps += [
                (
                    classification,
                    f"INSERT INTO {{table}}(game_id,{column},quality_issue,note) "
                    "VALUES(:g,:hit,'grid_issue',:note)",
                    {"hit": hit, "note": note},
                ),
                # Evidence change on the same row (cell: revision pointer).
                (
                    classification,
                    "UPDATE {table} SET source_geometry_revision_id=:rev,note=:note2 "
                    f"WHERE {column}=:hit",
                    {"hit": hit, "rev": uuid4(), "note2": note + "-2"},
                ),
                # Identity move: old and new identifiers both notify.
                (
                    classification,
                    f"UPDATE {{table}} SET {column}=:moved WHERE {column}=:hit",
                    {"hit": hit, "moved": moved},
                ),
                (classification, f"DELETE FROM {{table}} WHERE {column}=:moved", {"moved": moved}),
                # Unrelated identifiers notify nobody.
                (
                    classification,
                    f"INSERT INTO {{table}}(game_id,{column},quality_issue,note) "
                    "VALUES(:g,:hit,'grid_issue',:note)",
                    {"hit": uuid4(), "note": note},
                ),
            ]
        # Symbol-only cell change and non-grid cell insert stay silent in both.
        steps += [
            (
                "cell",
                "INSERT INTO {table}(game_id,id,quality_issue,note) VALUES(:g,:c,NULL,'a')",
                {"c": c2},
            ),
            ("cell", "UPDATE {table} SET note='b' WHERE id=:c", {"c": c2}),
        ]
        v1 = _replay(db, game, "v1", steps)
        v2 = _replay(db, game, "v2", steps)
        assert sum(v1.values()) > 30
        normalized = {
            version: Counter(
                {
                    (*key[:6], key[6].replace(f'"{version}"', "")): count
                    for key, count in counts.items()
                }
            )
            for version, counts in (("v1", v1), ("v2", v2))
        }
        assert normalized["v1"] == normalized["v2"]
        # A realistic share of pairs (2000 members, 10 cells each) so the planner
        # chooses by selectivity; the lookup is the trigger's own SQL.
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            bulk = _cohort(connection, game)
            connection.execute(
                text(
                    "INSERT INTO game_data_v2.grid_training_cohort_members"
                    "(game_id,cohort_id,source_id,ordinal) "
                    "SELECT :g,:c,gen_random_uuid(),n FROM generate_series(0,1999) n"
                ),
                {"g": game, "c": bulk},
            )
            connection.execute(
                text(
                    "UPDATE game_data_v2.grid_training_cohort_members SET role='TRAIN',"
                    "frozen=jsonb_build_object('captured','yes'),"
                    "cell_ids=ARRAY(SELECT gen_random_uuid() FROM generate_series(1,10+0*ordinal)) "
                    "WHERE game_id=:g AND cohort_id=:c"
                ),
                {"g": game, "c": bulk},
            )
        with db.owner_engine.begin() as connection:
            connection.execute(text(f"ANALYZE {REFS}"))
            connection.execute(text("ANALYZE game_data_v2.grid_training_cohort_members"))
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            statement = (
                LOOKUP_SQL.replace("r.game_id=gid", "r.game_id=:g")
                .replace("IN (sid,oldsid)", "IN (:s,NULL)")
                .replace("IN (bid,oldbid)", "IN (:b,NULL)")
                .replace("IN (rid,oldrid)", "IN (:r,NULL)")
                .replace("IN (cid,oldcid)", "IN (:c,:c2)")
            )
            plan = "\n".join(
                connection.scalars(
                    text(
                        "EXPLAIN SELECT DISTINCT u.cohort_id,u.member_source_id FROM ("
                        + statement
                        + ") u"
                    ),
                    {"g": game, "s": s1, "b": b1, "r": r1, "c": c1, "c2": c3},
                )
            )
            assert "Seq Scan" not in plan, plan
            conditions = [line for line in plan.splitlines() if "Index Cond" in line]
            assert len(conditions) == 4, plan
            assert all("ref_kind" in line and "ref_id" in line for line in conditions), plan
            legacy = "\n".join(
                connection.scalars(
                    text(
                        "EXPLAIN SELECT 1 FROM game_data_v2.grid_training_cohort_members m "
                        "WHERE m.game_id=:g AND (m.cell_ids @> ARRAY[CAST(:c AS uuid)] "
                        "OR m.board_ids @> ARRAY[CAST(:b AS uuid)])"
                    ),
                    {"g": game, "c": c1, "b": b1},
                )
            )
            # The cause this task removes: under RLS containment is only a filter over
            # every member row of the game; the GIN indexes are never index conditions.
            assert "@>" in "\n".join(line for line in legacy.splitlines() if "Filter:" in line), (
                legacy
            )
            assert not any("@>" in line for line in legacy.splitlines() if "Index Cond" in line), (
                legacy
            )


def test_refs_are_derived_only_and_retired_toggles_frozen() -> None:
    with application_role_database("t1190guard", ("guard",)) as db:
        game = db.games["guard"]
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            cohort = _cohort(connection, game)
            _member(connection, game, cohort, uuid4(), 0, [uuid4()], [uuid4()], [uuid4()])
        for statement in (
            f"INSERT INTO {REFS}(game_id,cohort_id,member_source_id,ref_kind,ref_id) "
            "VALUES(:g,:c,gen_random_uuid(),'cell',gen_random_uuid())",
            f"DELETE FROM {REFS} WHERE game_id=:g",
            f"UPDATE {REFS} SET ref_id=gen_random_uuid() WHERE game_id=:g",
        ):
            with (
                db.app_engine.begin() as connection,
                pytest.raises(DBAPIError, match="GRID_COHORT_REFS_DERIVED_ONLY"),
            ):
                _scope(connection, game)
                connection.execute(text(statement), {"g": game, "c": cohort})
        # Out of retired only retired -> frozen exists (no failed/canceled, no edits).
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            parked = _cohort(connection, game, status="frozen")
            connection.execute(
                text(
                    "UPDATE game_data_v2.grid_training_cohorts SET status='retired',revision=2 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": parked},
            )
        for assignments in (
            "status='failed',revision=3",
            "status='canceled',revision=3",
            "status='retired',revision=3",
            "status='retired',revision=3,summary=jsonb_build_object('x','y')",
            "status='preparing',revision=3",
        ):
            with (
                db.app_engine.begin() as connection,
                pytest.raises(DBAPIError, match="GRID_COHORT_IMMUTABLE_HISTORY"),
            ):
                _scope(connection, game)
                connection.execute(
                    text(
                        f"UPDATE game_data_v2.grid_training_cohorts SET {assignments} "
                        "WHERE game_id=:g AND id=:c"
                    ),
                    {"g": game, "c": parked},
                )
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            frozen = _cohort(connection, game, status="frozen")
            for status, revision in (("retired", 2), ("frozen", 3)):
                connection.execute(
                    text(
                        "UPDATE game_data_v2.grid_training_cohorts SET status=:s,revision=:r "
                        "WHERE game_id=:g AND id=:c"
                    ),
                    {"s": status, "r": revision, "g": game, "c": frozen},
                )
        for assignments in (
            "status='preparing',revision=4",
            "status='retired',revision=4,document=jsonb_build_object('x','y')",
            "status='retired',revision=5",
            "status='retired',revision=4,summary=jsonb_build_object('x','y')",
        ):
            with (
                db.app_engine.begin() as connection,
                pytest.raises(DBAPIError, match="GRID_COHORT_IMMUTABLE_HISTORY"),
            ):
                _scope(connection, game)
                connection.execute(
                    text(
                        f"UPDATE game_data_v2.grid_training_cohorts SET {assignments} "
                        "WHERE game_id=:g AND id=:c"
                    ),
                    {"g": game, "c": frozen},
                )
        # The widened CHECK admits retired and still rejects unknown statuses.
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            _cohort(connection, game, status="retired")
        with (
            db.app_engine.begin() as connection,
            pytest.raises(DBAPIError, match="ck_grid_training_cohorts_status"),
        ):
            _scope(connection, game)
            connection.execute(
                text(
                    "INSERT INTO game_data_v2.grid_training_cohorts"
                    "(game_id,id,status,document,created_by) "
                    "VALUES(:g,gen_random_uuid(),'bogus','{}'::jsonb,'fixture:1190')"
                ),
                {"g": game},
            )


def test_backfill_from_existing_members_and_reversible_downgrade() -> None:
    with application_role_database("t1190fill", ("fill",)) as db:
        game = db.games["fill"]
        config = _config(db)
        command.downgrade(config, "0185_grid_gate_noise_tolerance")
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            cohort = _cohort(connection, game)
            for ordinal in range(3):
                _member(
                    connection,
                    game,
                    cohort,
                    uuid4(),
                    ordinal,
                    [uuid4()],
                    [uuid4()],
                    [uuid4() for _ in range(15)],
                )
        command.upgrade(config, "0186_grid_cohort_member_refs")
        with db.owner_engine.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT manifest_version FROM public.game_storage_locations")
                )
                == "game-data-v2-manifest-v23"
            )
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            assert _pairs(connection, "refs", game) == _pairs(connection, "members", game)
            assert len(_pairs(connection, "refs", game)) == 3 * (1 + 1 + 1 + 15)
            retired = _cohort(connection, game, status="frozen")
            connection.execute(
                text(
                    "UPDATE game_data_v2.grid_training_cohorts SET status='retired',revision=2 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": retired},
            )
        with pytest.raises(RuntimeError, match="retired grid cohort"):
            command.downgrade(config, "0185_grid_gate_noise_tolerance")
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            connection.execute(
                text(
                    "UPDATE game_data_v2.grid_training_cohorts SET status='frozen',revision=3 "
                    "WHERE game_id=:g AND id=:c"
                ),
                {"g": game, "c": retired},
            )
        command.downgrade(config, "0185_grid_gate_noise_tolerance")
        with db.owner_engine.connect() as connection:
            assert connection.scalar(text(f"SELECT to_regclass('{REFS}')")) is None
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid "
                        "WHERE t.tgname='grid_cohort_currentness' AND t.tgparentid=0 "
                        "AND p.proname='grid_cohort_notice_v1'"
                    )
                )
                == 14
            )
        command.upgrade(config, "head")
        with db.app_engine.begin() as connection:
            _scope(connection, game)
            assert _pairs(connection, "refs", game) == _pairs(connection, "members", game)
