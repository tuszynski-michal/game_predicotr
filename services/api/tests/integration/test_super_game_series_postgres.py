"""Super game series on PostgreSQL with the real application role (TASK-0933).

Fixture boards are seeded as the schema owner with foreign-key triggers off
(``session_replication_role = replica``): the derivation reads only cells,
review items and boards, so the full import graph is not needed.  Every read
and write under test runs as the application role through RLS.
"""

from __future__ import annotations

import os
import threading
import time
import tracemalloc
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from _application_role_database import ApplicationRoleDatabase, application_role_database
from _virtual_board_fixtures import save_manual_virtual_geometry
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.cleanup import CleanupService
from game_predictor_api.application.super_game_series import (
    DerivationStart,
    PublicationOutcome,
    PublicationStatus,
    SeriesBoardDocument,
    SuperGameSeriesDerivation,
    SuperGameSeriesRecord,
    SuperGameSeriesService,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.cleanup import BoardSourceCleanupSelection, CleanupCommand
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.super_game_series import (
    BoardTrigger,
    DerivedSuperGameSeries,
    RunVerification,
    SeriesCompleteness,
    SuperGameSeriesConflictError,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.cleanup_repository import SqlAlchemyCleanupRepository
from game_predictor_api.storage.database import (
    create_cross_game_owner_session_factory,
    create_session_factory,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyGridCorrectionSymbolRepository,
    SqlAlchemyImageSymbolReviewRepository,
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageSourceGeometryRevisionModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
)
from game_predictor_api.storage.rules_repository import SqlAlchemyRulesRepository
from game_predictor_api.storage.super_game_input_version import (
    SUPER_GAME_INPUT_SOURCES,
    record_super_game_input_change,
)
from game_predictor_api.storage.super_game_series_repository import (
    SqlAlchemySuperGameSeriesDerivationStore,
    SqlAlchemySuperGameSeriesRepository,
)
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import Engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from test_image_batch_store import (  # type: ignore[import-not-found]
    PIPELINE,
    _add_review_projection_source,
    _image_job,
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Requires the disposable PostgreSQL integration database.",
)

HEX = "a" * 64


@dataclass(frozen=True)
class Board:
    sequence_number: int
    trigger_cells: int = 0
    human_cells: int = 0
    cut_cells: int = 15


@dataclass
class Fixture:
    database: ApplicationRoleDatabase
    game_id: UUID
    trigger_symbol: UUID
    ordinary_symbol: UUID
    wild_symbol: UUID
    factory: sessionmaker[Session]


def _symbols(owner: Engine, game_id: UUID) -> tuple[UUID, UUID, UUID]:
    trigger, ordinary, wild = uuid4(), uuid4(), uuid4()
    with owner.begin() as connection:
        connection.execute(
            text("UPDATE public.games SET super_game_kind = 'wild_super_spins' WHERE id = :g"),
            {"g": game_id},
        )
        for symbol_id, code, mobile, is_wild, count in (
            (trigger, "MUMIA", 1, True, 3),
            (ordinary, "K", 2, False, None),
            (wild, "W", 3, True, None),
        ):
            connection.execute(
                text(
                    """INSERT INTO public.symbols (id, game_id, mobile_code, code, name,
                    is_wildcard, display_order, status, super_game_trigger_count)
                    VALUES (:id, :g, :m, :code, :code, :w, :m, 'active', :count)"""
                ),
                {
                    "id": symbol_id,
                    "g": game_id,
                    "m": mobile,
                    "code": code,
                    "w": is_wild,
                    "count": count,
                },
            )
    return trigger, ordinary, wild


def _seed(fixture: Fixture, boards: Iterable[Board]) -> None:
    rows = list(boards)
    if not rows:
        return
    items = [uuid4() for _ in rows]
    boards_ids = [uuid4() for _ in rows]
    job_id, geometry_id = uuid4(), uuid4()
    with fixture.database.owner_engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL session_replication_role = replica")
        parameters = {
            "g": fixture.game_id,
            "job": job_id,
            "geometry": geometry_id,
            "items": items,
            "boards": boards_ids,
            "seqs": [row.sequence_number for row in rows],
            "triggers": [row.trigger_cells for row in rows],
            "humans": [row.human_cells for row in rows],
            "cuts": [row.cut_cells for row in rows],
            "trigger": fixture.trigger_symbol,
            "ordinary": fixture.ordinary_symbol,
            "hex": HEX,
        }
        connection.execute(
            text(
                """INSERT INTO game_data_v2.recognized_boards (
                    game_id, id, source_image_id, position_index, sequence_number_raw,
                    sequence_number, sequence_confidence, board_geometry, asset_mode,
                    source_geometry_revision_id, geometry_engine_name, geometry_engine_version,
                    geometry_checksum_sha256, cells_prediction, completeness_status,
                    unavailable_cell_indices, board_confidence, pipeline_fingerprint,
                    geometry_revision, status)
                SELECT :g, b.board, gen_random_uuid(), 0, b.seq::text, b.seq, 1, '{}',
                    'virtual_source', :geometry, 'fixture', 'fixture', :hex, '{}', 'complete',
                    '{}', 1, :hex, 0, 'pending_review'
                FROM unnest(CAST(:boards AS uuid[]), CAST(:seqs AS bigint[])) AS b(board, seq)"""
            ),
            parameters,
        )
        connection.execute(
            text(
                """INSERT INTO game_data_v2.image_review_items (
                    game_id, id, import_job_id, sequence_number, recognized_board_id, status,
                    snapshot, resolution_revision)
                SELECT :g, b.item, :job, b.seq, b.board, 'pending', '{}', 0
                FROM unnest(CAST(:items AS uuid[]), CAST(:boards AS uuid[]),
                            CAST(:seqs AS bigint[])) AS b(item, board, seq)"""
            ),
            parameters,
        )
        connection.execute(
            text(
                """INSERT INTO game_data_v2.image_symbol_review_cells (
                    game_id, id, import_job_id, review_item_id, recognized_board_id,
                    sequence_number, cell_index, row_index, column_index, asset_mode,
                    source_geometry_revision_id, logical_cell_key, render_spec_checksum_sha256,
                    rendered_pixel_checksum_sha256, extractor_version, crop_sample_id,
                    crop_checksum_sha256, geometry_revision, cropper_version,
                    assigned_symbol_id, review_state, assignment_source, revision,
                    last_reviewed_by)
                SELECT :g, gen_random_uuid(), :job, b.item, b.board, b.seq, ci, ci / 5, ci % 5,
                    'virtual_source', :geometry, :hex, :hex, :hex, 'fixture', :hex, :hex, 0,
                    'fixture',
                    CASE WHEN ci < b.trigger_cells THEN CAST(:trigger AS uuid)
                         ELSE CAST(:ordinary AS uuid) END,
                    CASE WHEN ci < b.human_cells THEN 'approved' ELSE 'pending' END,
                    CASE WHEN ci < b.human_cells THEN 'human' ELSE 'model' END,
                    0, 'fixture'
                FROM unnest(CAST(:items AS uuid[]), CAST(:boards AS uuid[]),
                            CAST(:seqs AS bigint[]), CAST(:triggers AS integer[]),
                            CAST(:humans AS integer[]), CAST(:cuts AS integer[]))
                     AS b(item, board, seq, trigger_cells, human_cells, cut_cells)
                CROSS JOIN generate_series(0, 14) AS ci
                WHERE ci < b.cut_cells"""
            ),
            parameters,
        )


def _set_trigger_cells(
    fixture: Fixture, sequence_number: int, count: int, *, bump: bool = True
) -> None:
    """A correction through the application role: cells and input version in one transaction."""

    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        session.execute(
            text(
                """UPDATE image_symbol_review_cells
                    SET assigned_symbol_id = CASE WHEN cell_index < :count
                        THEN CAST(:trigger AS uuid) ELSE CAST(:ordinary AS uuid) END,
                        review_state = 'approved', assignment_source = 'human'
                    WHERE game_id = :game_id AND sequence_number = :seq"""
            ),
            {
                "game_id": fixture.game_id,
                "seq": sequence_number,
                "count": count,
                "trigger": fixture.trigger_symbol,
                "ordinary": fixture.ordinary_symbol,
            },
        )
        if bump:
            record_super_game_input_change(session, fixture.game_id, source="symbol_cells")


@pytest.fixture
def fixture() -> Iterable[Fixture]:
    with application_role_database("t0933", ("mumie",)) as database:
        game_id = database.games["mumie"]
        trigger, ordinary, wild = _symbols(database.owner_engine, game_id)
        yield Fixture(
            database=database,
            game_id=game_id,
            trigger_symbol=trigger,
            ordinary_symbol=ordinary,
            wild_symbol=wild,
            factory=create_session_factory(database.app_engine),
        )


def _derive(
    fixture: Fixture, store: SqlAlchemySuperGameSeriesDerivationStore | None = None, **kwargs: int
):
    with game_storage_scope(fixture.game_id):
        return SuperGameSeriesDerivation(
            store or SqlAlchemySuperGameSeriesDerivationStore(fixture.factory), **kwargs
        ).derive(fixture.game_id)


def _series(
    fixture: Fixture,
) -> list[tuple[int, int, int, tuple[int, ...], str, str, UUID | None, int, UUID]]:
    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        service = SuperGameSeriesService(SqlAlchemySuperGameSeriesRepository(session))
        page = service.list(fixture.game_id, limit=200)
        return [
            (
                item.trigger_sequence_number,
                item.start_sequence_number,
                item.end_sequence_number,
                item.retrigger_sequence_numbers,
                item.completeness.value,
                item.run_verification.value,
                item.super_symbol_id,
                item.revision,
                item.id,
            )
            for item in page.items
        ]


def _state(fixture: Fixture):
    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        return SuperGameSeriesService(SqlAlchemySuperGameSeriesRepository(session)).state(
            fixture.game_id
        )


def _define(fixture: Fixture, series_id: UUID, symbol_id: UUID | None, revision: int):
    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        return SuperGameSeriesService(
            SqlAlchemySuperGameSeriesRepository(session)
        ).set_super_symbol(
            fixture.game_id, series_id, symbol_id=symbol_id, expected_revision=revision, actor="op"
        )


def _queued_jobs(fixture: Fixture) -> int:
    with fixture.database.owner_engine.connect() as connection:
        return int(
            connection.execute(
                select(func.count())
                .select_from(JobModel)
                .where(
                    JobModel.game_id == fixture.game_id,
                    JobModel.job_type == JobType.SUPER_GAME_SERIES_DERIVE,
                    JobModel.status == JobStatus.CREATED,
                )
            ).scalar_one()
        )


def _audit(fixture: Fixture) -> list[tuple[str, int, UUID | None]]:
    with fixture.database.owner_engine.connect() as connection:
        return [
            (str(row[0]), int(row[1]), row[2])
            for row in connection.execute(
                text(
                    """SELECT event_kind, trigger_sequence_number, previous_super_symbol_id
                    FROM game_data_v2.super_game_series_audit_events WHERE game_id = :g
                    ORDER BY created_at, trigger_sequence_number"""
                ),
                {"g": fixture.game_id},
            )
        ]


def _working_rows(fixture: Fixture) -> int:
    with fixture.database.owner_engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT count(*) FROM game_data_v2.super_game_series_generation_rows "
                    "WHERE game_id = :g"
                ),
                {"g": fixture.game_id},
            ).scalar_one()
        )


def _boards(last: int, special: dict[int, Board]) -> list[Board]:
    return [special.get(n, Board(n)) for n in range(1, last + 1)]


def test_chain_missing_board_incomplete_and_verification(fixture: Fixture) -> None:
    boards = _boards(
        130,
        {
            100: Board(100, trigger_cells=3, human_cells=3),
            105: Board(105, trigger_cells=4, human_cells=2),  # retrigger on a prediction
            110: Board(110, trigger_cells=3, human_cells=3),
            50: Board(50, trigger_cells=3, human_cells=3, cut_cells=14),  # not cut: no trigger
        },
    )
    _seed(fixture, [board for board in boards if board.sequence_number != 103])
    report = _derive(fixture, position_batch_size=40)
    assert report.status is PublicationStatus.PUBLISHED
    ((trigger, start, end, retriggers, completeness, verification, *_),) = _series(fixture)
    assert (trigger, start, end) == (100, 101, 130)
    assert retriggers == (105, 110)
    assert completeness == "complete" and verification == "unverified"
    assert _state(fixture).fresh

    # The last known board is 130; a series ending at 140 is incomplete.
    _seed(fixture, [Board(131, trigger_cells=3, human_cells=3)])
    _set_trigger_cells(fixture, 131, 3)
    _derive(fixture)
    rows = _series(fixture)
    assert [row[0] for row in rows] == [100, 131]
    assert rows[1][4] == SeriesCompleteness.INCOMPLETE.value
    assert rows[1][5] == RunVerification.VERIFIED.value


def test_generation_swap_keeps_identity_symbol_and_audits_removals(fixture: Fixture) -> None:
    _seed(
        fixture,
        _boards(
            200,
            {
                100: Board(100, trigger_cells=3, human_cells=3),
                115: Board(115, trigger_cells=3, human_cells=3),
                150: Board(150, trigger_cells=3, human_cells=3),
            },
        ),
    )
    _derive(fixture)
    first = {row[0]: row for row in _series(fixture)}
    assert set(first) == {100, 115, 150}
    for trigger in (100, 115, 150):
        _define(fixture, first[trigger][8], fixture.ordinary_symbol, 0)

    # Re-derivation without changes keeps revision and symbol.
    report = _derive(fixture)
    assert (report.inserted, report.updated, report.removed) == (0, 0, 0)
    again = {row[0]: row for row in _series(fixture)}
    assert all(again[t][6] == fixture.ordinary_symbol and again[t][7] == 1 for t in again)

    # A retrigger on 108 extends 100 to 120 and absorbs the trigger on 115
    # (now a retrigger, so the series ends at 130);
    # losing the trigger on 150 removes that series. Both removals are audited.
    _set_trigger_cells(fixture, 108, 3)
    _set_trigger_cells(fixture, 150, 0)
    _derive(fixture)
    rows = {row[0]: row for row in _series(fixture)}
    assert set(rows) == {100}
    assert rows[100][2] == 130 and rows[100][3] == (108, 115)
    assert rows[100][6] == fixture.ordinary_symbol and rows[100][7] == 1
    assert rows[100][8] == first[100][8]
    removed = [event for event in _audit(fixture) if event[0] == "series_removed"]
    assert sorted(event[1] for event in removed) == [115, 150]
    assert {event[2] for event in removed} == {fixture.ordinary_symbol}


def test_retrigger_above_smallint_round_trips(fixture: Fixture) -> None:
    _seed(
        fixture,
        [
            Board(39_995, trigger_cells=3, human_cells=3),
            Board(40_000, trigger_cells=3, human_cells=3),
            Board(40_010),
        ],
    )
    _derive(fixture, position_batch_size=100_000)
    ((trigger, _start, end, retriggers, completeness, *_),) = _series(fixture)
    assert (trigger, end, retriggers, completeness) == (39_995, 40_015, (40_000,), "incomplete")


class _CrashingStore(SqlAlchemySuperGameSeriesDerivationStore):
    def __init__(self, factory: sessionmaker[Session]) -> None:
        super().__init__(factory)
        self.writes = 0

    def write_generation_rows(
        self, start: DerivationStart, rows: Sequence[DerivedSuperGameSeries]
    ) -> None:
        super().write_generation_rows(start, rows)
        self.writes += 1
        raise RuntimeError("worker killed after the first batch")


def test_restart_in_the_middle_never_exposes_partial_state(fixture: Fixture) -> None:
    special = {n: Board(n, trigger_cells=3, human_cells=3) for n in range(20, 400, 25)}
    _seed(fixture, _boards(400, special))
    _derive(fixture)
    published = _series(fixture)
    _set_trigger_cells(fixture, 21, 0)  # no-op for the series, but the input version moves
    with pytest.raises(RuntimeError, match="killed"):
        _derive(fixture, _CrashingStore(fixture.factory), write_batch_size=2)
    assert _working_rows(fixture) > 0
    assert _series(fixture) == published  # the API serves the last published generation
    assert not _state(fixture).fresh
    report = _derive(fixture, write_batch_size=2)
    assert report.status is PublicationStatus.PUBLISHED
    assert _working_rows(fixture) == 0
    assert [row[:8] for row in _series(fixture)] == [row[:8] for row in published]
    assert _state(fixture).fresh


class _ConcurrentCorrectionStore(SqlAlchemySuperGameSeriesDerivationStore):
    def __init__(self, fixture: Fixture) -> None:
        super().__init__(fixture.factory)
        self._fixture = fixture
        self.corrected = False

    def last_known_sequence_number(self, start: DerivationStart, *, window: int) -> int | None:
        if not self.corrected:
            self.corrected = True
            _set_trigger_cells(self._fixture, 60, 3)  # a new trigger while the job runs
            assert not _state(self._fixture).fresh
        return super().last_known_sequence_number(start, window=window)


def test_concurrent_correction_rejects_candidate_and_queues_one_rerun(fixture: Fixture) -> None:
    _seed(fixture, _boards(120, {10: Board(10, trigger_cells=3, human_cells=3)}))
    _derive(fixture)
    before = _series(fixture)
    assert [row[0] for row in before] == [10]
    assert _queued_jobs(fixture) == 0

    report = _derive(fixture, _ConcurrentCorrectionStore(fixture))
    assert report.status is PublicationStatus.REJECTED
    assert report.current_input_version == report.expected_input_version + 1
    assert _series(fixture) == before
    assert _working_rows(fixture) == 0
    state = _state(fixture)
    assert not state.fresh and state.input_version == report.current_input_version
    assert _queued_jobs(fixture) == 1  # the correction's job; the rejection reused it

    rerun = _derive(fixture)
    assert rerun.status is PublicationStatus.PUBLISHED
    assert [row[0] for row in _series(fixture)] == [10, 60]
    assert _state(fixture).fresh


def test_input_version_bump_is_transactional_and_low_revision_change_detected(
    fixture: Fixture,
) -> None:
    _seed(fixture, _boards(30, {}))
    _derive(fixture)
    version = _state(fixture).input_version
    with fixture.factory() as session, game_storage_scope(fixture.game_id):
        with session.begin():
            assert record_super_game_input_change(session, fixture.game_id, source="symbol_cells")
            # Twice in one transaction counts once.
            assert not record_super_game_input_change(
                session, fixture.game_id, source="symbol_cells"
            )
        session.begin()
        record_super_game_input_change(session, fixture.game_id, source="rules_publication")
        session.rollback()  # the write failed: its bump disappears with it
    version += 1
    assert _state(fixture).input_version == version
    # Scenario 100 / 1->2: a change of a low-revision cell next to a cell with
    # a much higher revision is detected, because detection never looks at
    # revisions.
    with fixture.database.owner_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE game_data_v2.image_symbol_review_cells SET revision = 100 "
                "WHERE game_id = :g AND sequence_number = 1"
            ),
            {"g": fixture.game_id},
        )
    _set_trigger_cells(fixture, 2, 3)
    state = _state(fixture)
    assert state.input_version == version + 1 and not state.fresh
    assert _queued_jobs(fixture) == 1


def test_super_symbol_cas_conflict_writes_nothing(fixture: Fixture) -> None:
    _seed(fixture, _boards(40, {5: Board(5, trigger_cells=3, human_cells=3)}))
    _derive(fixture)
    ((*_, series_id),) = _series(fixture)
    saved = _define(fixture, series_id, fixture.ordinary_symbol, 0)
    assert saved.revision == 1 and saved.super_symbol_id == fixture.ordinary_symbol
    assert saved.defined_by == "op" and saved.defined_at is not None
    with pytest.raises(SuperGameSeriesConflictError):
        _define(fixture, series_id, None, 0)
    with pytest.raises(Exception, match="ordinary"):
        _define(fixture, series_id, fixture.wild_symbol, 1)
    ((*_, symbol, revision, _id),) = _series(fixture)
    assert symbol == fixture.ordinary_symbol and revision == 1
    assert [event[0] for event in _audit(fixture)] == ["super_symbol_defined"]


def test_none_kind_derives_zero_series_and_clears(fixture: Fixture) -> None:
    _seed(fixture, _boards(40, {5: Board(5, trigger_cells=3, human_cells=3)}))
    _derive(fixture)
    assert len(_series(fixture)) == 1
    with fixture.database.owner_engine.begin() as connection:
        connection.execute(
            text("UPDATE public.games SET super_game_kind = 'none' WHERE id = :g"),
            {"g": fixture.game_id},
        )
    report = _derive(fixture)
    assert report.series_count == 0 and report.removed == 1
    assert _series(fixture) == [] and _state(fixture).fresh


def test_two_thousand_positions_thirty_series_within_batches(fixture: Fixture) -> None:
    special = {n: Board(n, trigger_cells=3, human_cells=n % 2 * 3) for n in range(30, 2_000, 66)}
    assert len(special) == 30
    _seed(fixture, _boards(2_000, special))
    tracemalloc.start()
    started = time.perf_counter()
    report = _derive(fixture, position_batch_size=500, write_batch_size=8)
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert report.status is PublicationStatus.PUBLISHED
    assert report.series_count == 30 and report.position_batch_count <= 5
    assert len(_series(fixture)) == 30
    print(
        f"SUPER_GAME_DERIVATION_2000: seconds={elapsed:.3f} peak_bytes={peak} "
        f"batches={report.position_batch_count} series={report.series_count}"
    )
    assert elapsed < 30
    assert peak < 20 * 1024 * 1024


def test_rejection_outcome_type_is_public() -> None:
    outcome = PublicationOutcome(PublicationStatus.REJECTED, 3)
    assert outcome.inserted == 0 and BoardTrigger(1, True).sequence_number == 1


def test_migration_downgrade_refuses_decisions_and_round_trips() -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from game_predictor_api.storage.game_partition_lifecycle import partition_name

    with application_role_database("t0933m", ("mumie-migration",)) as database:
        game_id = database.games["mumie-migration"]
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            database.owner_url.render_as_string(hide_password=False).replace("%", "%%"),
        )
        trigger, ordinary, _wild = _symbols(database.owner_engine, game_id)
        fixture = Fixture(
            database, game_id, trigger, ordinary, _wild, create_session_factory(database.app_engine)
        )
        _seed(fixture, _boards(40, {5: Board(5, trigger_cells=3, human_cells=3)}))
        _derive(fixture)
        ((*_, series_id),) = _series(fixture)
        _define(fixture, series_id, ordinary, 0)
        with pytest.raises(Exception, match="SUPER_GAME_SERIES_DOWNGRADE_HAS_DECISIONS"):
            command.downgrade(config, "0151_super_game_roles")
        with database.owner_engine.begin() as connection:
            for table in ("super_game_series_audit_events", "super_game_series"):
                connection.execute(text(f"DELETE FROM game_data_v2.{table}"))
        command.downgrade(config, "0151_super_game_roles")
        with database.owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT manifest_version FROM public.game_storage_locations")
                ).scalar_one()
                == "game-data-v2-manifest-v5"
            )
            assert (
                connection.execute(
                    text("SELECT to_regclass('game_data_v2.super_game_series')")
                ).scalar_one()
                is None
            )
        command.upgrade(config, "head")
        with database.owner_engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT manifest_version FROM public.game_storage_locations")
                ).scalar_one()
                == "game-data-v2-manifest-v6"
            )
            for table in (
                "super_game_series",
                "super_game_series_generation_rows",
                "super_game_derivation_state",
                "super_game_series_audit_events",
            ):
                child = partition_name(game_id, table)
                assert connection.execute(
                    text(
                        "SELECT relrowsecurity AND relforcerowsecurity FROM pg_class "
                        "WHERE relname = :child"
                    ),
                    {"child": child},
                ).scalar_one()


# --- Audit P0-1: expected_layout_count is derivation input -----------------


def _catalog_update(fixture: Fixture, **changes: object) -> None:
    with fixture.factory() as session, session.begin(), game_storage_scope(fixture.game_id):
        CatalogService(SqlAlchemyCatalogRepository(session)).update_game(
            fixture.game_id,
            **changes,  # type: ignore[arg-type]
        )


class _LayoutChangeDuringJobStore(SqlAlchemySuperGameSeriesDerivationStore):
    def __init__(self, fixture: Fixture, layout_count: int) -> None:
        super().__init__(fixture.factory)
        self._fixture = fixture
        self._layout_count = layout_count

    def last_known_sequence_number(self, start: DerivationStart, *, window: int) -> int | None:
        _catalog_update(self._fixture, expected_layout_count=self._layout_count)
        return super().last_known_sequence_number(start, window=window)


def test_expected_layout_count_change_invalidates_and_rejects(fixture: Fixture) -> None:
    _catalog_update(fixture, expected_layout_count=1_000)
    _seed(
        fixture,
        _boards(
            800,
            {
                100: Board(100, trigger_cells=3, human_cells=3),
                700: Board(700, trigger_cells=3, human_cells=3),
            },
        ),
    )
    _derive(fixture)
    assert [row[0] for row in _series(fixture)] == [100, 700]
    assert _state(fixture).fresh

    # Shrinking 1000 -> 500 before a job: stale at once, one job queued.
    version = _state(fixture).input_version
    queued = _queued_jobs(fixture)
    _catalog_update(fixture, expected_layout_count=500)
    state = _state(fixture)
    assert state.input_version == version + 1 and not state.fresh
    assert _queued_jobs(fixture) == max(queued, 1)
    assert [row[0] for row in _series(fixture)] == [100, 700]  # last generation still served
    report = _derive(fixture)
    assert report.status is PublicationStatus.PUBLISHED and report.removed == 1
    assert [row[0] for row in _series(fixture)] == [100]
    assert ("series_removed", 700, None) in _audit(fixture)
    assert _state(fixture).fresh

    # A change while the job runs rejects the candidate.
    rejected = _derive(fixture, _LayoutChangeDuringJobStore(fixture, 900))
    assert rejected.status is PublicationStatus.REJECTED
    assert not _state(fixture).fresh and [row[0] for row in _series(fixture)] == [100]
    _derive(fixture)
    assert [row[0] for row in _series(fixture)] == [100, 700]
    assert _state(fixture).fresh


# --- Audit P1-1: real write operations bump the input version --------------


class _NoArtifacts:
    def delete(self, relative_paths: tuple[str, ...]) -> None:
        return None

    def quarantine(self, operation_key: str, relative_paths: tuple[str, ...]) -> None:
        return None

    def restore(self, operation_key: str) -> None:
        return None

    def finalize(self, operation_key: str) -> None:
        return None

    def recover(self, completed_operation_keys: set[str]) -> None:
        return None


@dataclass
class RealBoard:
    database: ApplicationRoleDatabase
    game_id: UUID
    job_id: UUID
    review_item_id: UUID
    board_id: UUID
    test_symbol: UUID
    other_symbol: UUID
    factory: sessionmaker[Session]


@pytest.fixture(scope="module")
def real_board() -> Iterable[RealBoard]:
    """One imported virtual board with real cells, built through production code."""

    if os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Requires the disposable PostgreSQL integration database.")
    now = datetime.now(UTC)
    with application_role_database("t0933w", ("mumie-writes",)) as database:
        game_id = database.games["mumie-writes"]
        factory = create_session_factory(database.app_engine)
        with factory() as session, game_storage_scope(game_id):
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            catalog.update_game(game_id, super_game_kind="wild_super_spins")
            symbols = {
                code: catalog.create_symbol(
                    game_id,
                    mobile_code=index + 1,
                    code=code,
                    name=code,
                    image_path=None,
                    is_wildcard=False,
                    display_order=index,
                    status=SymbolStatus.ACTIVE,
                ).id
                for index, code in enumerate(("test", "other"))
            }
            job = SqlAlchemyJobRepository(session).add_job(_image_job(game_id, PIPELINE, now))
            session.commit()
        execution = SqlAlchemyImageBatchStore(factory).register_file(
            job.id,
            source_checksum_sha256="7" * 64,
            pipeline_fingerprint=PIPELINE,
            source_relative_path="writes.jpg",
            order_index=0,
            registered_at=now,
        )
        with game_storage_scope(game_id), factory() as session:
            review_item_id, board_id = _add_review_projection_source(
                session,
                job_id=job.id,
                file_execution_key=execution.file_execution_key,
                source_checksum="7" * 64,
                source_name="writes.jpg",
                position_index=0,
                sequence_number=1,
                status="pending",
                created_at=now,
            )
            record = session.get(JobModel, job.id)
            assert record is not None
            record.status = JobStatus.WAITING_FOR_REVIEW
            SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game_id)
            session.commit()
        with game_storage_scope(game_id), factory() as session:
            backfill = SqlAlchemyImageSymbolReviewRepository(session)
            backfill.start_or_resume_backfill(game_id)
            while backfill.backfill_next_batch(
                game_id, batch_size=10, finalize_when_exhausted=False
            ).has_more:
                pass
            backfill.finalize_backfill(game_id)
            session.commit()
        yield RealBoard(
            database=database,
            game_id=game_id,
            job_id=job.id,
            review_item_id=review_item_id,
            board_id=board_id,
            test_symbol=symbols["test"],
            other_symbol=symbols["other"],
            factory=factory,
        )


def _prediction_refresh(board: RealBoard, session: Session, code: str) -> None:
    """Storage path of the inference handlers: a new revision, then the refresh."""

    session.add(
        ImageSymbolPredictionRevisionModel(
            game_id=board.game_id,
            review_item_id=board.review_item_id,
            recognized_board_id=board.board_id,
            source_job_id=board.job_id,
            model_iteration_id=None,
            model_version=f"super-game-{code}-{uuid4().hex[:8]}",
            model_checksum_sha256="a" * 64,
            crop_manifest_checksum_sha256="b" * 64,
            predictions=[
                {
                    "rowIndex": index // 5,
                    "columnIndex": index % 5,
                    "symbolCode": code,
                    "confidence": 0.6,
                    "alternatives": [{"symbolCode": code, "confidence": 0.6}],
                }
                for index in range(15)
            ],
        )
    )
    session.flush()
    SymbolCellReviewWriteThroughCoordinator(session).synchronize_after_prediction_refresh(
        game_id=board.game_id, review_item_id=board.review_item_id, actor="system:test"
    )


def _queued_derive_jobs(board: RealBoard) -> int:
    with board.database.owner_engine.connect() as connection:
        return int(
            connection.execute(
                text(
                    "SELECT count(*) FROM public.jobs WHERE game_id = :g "
                    "AND job_type = 'super_game_series_derive' AND status = 'created'"
                ),
                {"g": board.game_id},
            ).scalar_one()
        )


def _drain_derive_jobs(board: RealBoard) -> None:
    """The worker has run the queued derivations (cleanup waits for them)."""

    with board.database.owner_engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM public.jobs WHERE game_id = :g "
                "AND job_type = 'super_game_series_derive' AND status = 'created'"
            ),
            {"g": board.game_id},
        )


def _cleanup_service(board: RealBoard, session: Session) -> CleanupService:
    return CleanupService(
        SqlAlchemyCleanupRepository(
            session, create_cross_game_owner_session_factory(board.database.owner_engine)
        ),
        _NoArtifacts(),  # type: ignore[arg-type]
    )


def _operation(name: str, board: RealBoard, session: Session, attempt: int) -> None:
    catalog = CatalogService(SqlAlchemyCatalogRepository(session))
    if name == "prediction_write":
        _prediction_refresh(board, session, "other" if attempt == 0 else "test")
    elif name == "human_symbol_correction":
        SqlAlchemyGridCorrectionSymbolRepository(session).assign(
            game_id=board.game_id,
            review_item_id=board.review_item_id,
            symbol_id_by_cell_index={5 + attempt: board.other_symbol},
            actor="super-game-test",
        )
    elif name == "grid_correction":
        # Storage effects of a manual geometry save (the production render
        # path needs real source pixels): new revision, reopen, cell resync.
        save_manual_virtual_geometry(
            session,
            game_id=board.game_id,
            import_job_id=board.job_id,
            review_item_id=board.review_item_id,
            board_id=board.board_id,
            actor="super-game-test",
            variant=f"grid-{uuid4().hex[:8]}",
            created_at=datetime.now(UTC),
        )
    elif name == "symbol_cell_backfill":
        backfill = SqlAlchemyImageSymbolReviewRepository(session)
        backfill.start_or_resume_backfill(board.game_id)
        while backfill.backfill_next_batch(
            board.game_id, batch_size=10, finalize_when_exhausted=False
        ).has_more:
            pass
        backfill.finalize_backfill(board.game_id)
    elif name == "symbol_role":
        catalog.update_symbol(
            board.game_id,
            board.test_symbol,
            super_game_trigger_count=3 if attempt == 0 else 4,
            update_super_game_trigger_count=True,
        )
    elif name == "symbol_role_new_symbol":
        catalog.create_symbol(
            board.game_id,
            mobile_code=10 + attempt,
            code=f"trigger{attempt}",
            name=f"Trigger {attempt}",
            image_path=None,
            is_wildcard=True,
            display_order=10 + attempt,
            status=SymbolStatus.ACTIVE,
            super_game_trigger_count=3,
        )
    elif name == "symbol_role_manual_symbol":
        catalog.create_manual_symbol(
            board.game_id, name=f"Manual {attempt}", is_wildcard=False, super_game_trigger_count=5
        )
    elif name == "super_game_kind":
        catalog.update_game(board.game_id, super_game_kind="none")
        session.flush()
        # Back to the kind under test in the same transaction: still one bump.
        catalog.update_game(board.game_id, super_game_kind="wild_super_spins")
    elif name == "expected_layout_count":
        catalog.update_game(board.game_id, expected_layout_count=1_000 + attempt)
    elif name == "rules_publication":
        rules = SqlAlchemyRulesRepository(session)
        draft = rules.add_next_rules_version(
            game_id=board.game_id, rows=3, columns=5, spin_cost=100
        )
        assert draft is not None
        rules.save_rules_version(
            replace(draft, status=RulesVersionStatus.PUBLISHED, published_at=datetime.now(UTC))
        )
    elif name == "board_source_cleanup":
        _drain_derive_jobs(board)
        service = _cleanup_service(board, session)
        # A whole image-source range is removed together (cleanup rule).
        start, end = session.execute(
            select(
                ImageSourceGeometryRevisionModel.sequence_range_start,
                ImageSourceGeometryRevisionModel.sequence_range_end,
            )
            .where(ImageSourceGeometryRevisionModel.game_id == board.game_id)
            .limit(1)
        ).one()
        selection = BoardSourceCleanupSelection(
            sequence_numbers=tuple(range(int(start), int(end) + 1))
        )
        preview = service.preview_board_sources(board.game_id, selection)
        service.delete_board_sources(
            board.game_id,
            selection,
            CleanupCommand(
                preview_token=preview.preview_token,
                confirmation_target=preview.snapshot.confirmation_target,
                confirmed=True,
            ),
        )
    elif name == "game_layout_reset":
        _drain_derive_jobs(board)
        service = _cleanup_service(board, session)
        preview = service.preview_game_reset(board.game_id)
        service.reset_game(
            board.game_id,
            CleanupCommand(
                preview_token=preview.preview_token,
                confirmation_target=str(board.game_id),
                confirmed=True,
            ),
        )
    else:  # pragma: no cover - the parametrisation lists every name
        raise AssertionError(name)


def _real_state(board: RealBoard) -> tuple[int, int | None]:
    with board.database.owner_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT input_version, input_version_of_generation "
                "FROM game_data_v2.super_game_derivation_state WHERE game_id = :g"
            ),
            {"g": board.game_id},
        ).one_or_none()
    return (0, None) if row is None else (int(row[0]), None if row[1] is None else int(row[1]))


# Order matters: destructive operations run last. Each name drives one source
# of SUPER_GAME_INPUT_WRITE_POINTS through production code; the shared
# write-through choke point (``symbol_cells``) is driven by three operations.
REAL_OPERATIONS = (
    ("prediction_write", "symbol_cells"),
    ("human_symbol_correction", "symbol_cells"),
    ("symbol_cell_backfill", "symbol_cell_backfill"),
    ("grid_correction", "symbol_cells"),
    ("super_game_kind", "super_game_kind"),
    ("symbol_role", "symbol_role"),
    ("symbol_role_new_symbol", "symbol_role"),
    ("symbol_role_manual_symbol", "symbol_role"),
    ("expected_layout_count", "expected_layout_count"),
    ("rules_publication", "rules_publication"),
    ("board_source_cleanup", "board_source_cleanup"),
    ("game_layout_reset", "game_layout_reset"),
)


def test_real_operations_cover_every_write_point_source() -> None:
    assert {source for _name, source in REAL_OPERATIONS} == SUPER_GAME_INPUT_SOURCES


@pytest.mark.parametrize(("name", "source"), REAL_OPERATIONS, ids=[n for n, _ in REAL_OPERATIONS])
def test_real_write_operation_bumps_once_and_rolls_back(
    real_board: RealBoard, name: str, source: str
) -> None:
    del source
    board = real_board
    # Publish a generation first so that freshness is observable.
    with game_storage_scope(board.game_id):
        SuperGameSeriesDerivation(SqlAlchemySuperGameSeriesDerivationStore(board.factory)).derive(
            board.game_id
        )
    version, generation = _real_state(board)
    assert generation == version

    # A rolled-back write leaves the version untouched.
    with game_storage_scope(board.game_id), board.factory() as session:
        session.begin()
        _operation(name, board, session, attempt=0)
        session.rollback()
    assert _real_state(board) == (version, generation)

    # A committed write bumps exactly once, in the same transaction.
    with game_storage_scope(board.game_id), board.factory() as session, session.begin():
        _operation(name, board, session, attempt=1)
        in_transaction = session.execute(
            text("SELECT input_version FROM super_game_derivation_state WHERE game_id = :g"),
            {"g": board.game_id},
        ).scalar_one()
        assert in_transaction == version + 1
    assert _real_state(board) == (version + 1, generation)
    # The bump queued a derivation (for cleanups: after the drained ones).
    assert _queued_derive_jobs(board) == 1
    with board.factory() as session, session.begin(), game_storage_scope(board.game_id):
        state = SuperGameSeriesService(SqlAlchemySuperGameSeriesRepository(session)).state(
            board.game_id
        )
    assert not state.fresh


# --- Audit P0-3: input parameters are read under the state lock -----------


class _CatalogWriteBetweenLockAndReadStore(SqlAlchemySuperGameSeriesDerivationStore):
    """Commits a layout-count change while ``begin_generation`` holds the state lock.

    The catalog transaction locks the games row and then blocks on the state
    row; it can only commit after ``begin_generation`` commits, so the job
    sees the old parameters together with the old input version and the
    publication must reject the candidate.
    """

    def __init__(self, fixture: Fixture, layout_count: int) -> None:
        super().__init__(fixture.factory)
        self._fixture = fixture
        self._layout_count = layout_count
        self.thread: threading.Thread | None = None
        self.writer_was_blocked = False
        self.read_layout_count: int | None = None
        self.errors: list[BaseException] = []

    def _write(self) -> None:
        try:
            _catalog_update(self._fixture, expected_layout_count=self._layout_count)
        except BaseException as error:  # pragma: no cover - reported by the test
            self.errors.append(error)

    def _read_input_parameters(
        self, session: Session, game_id: UUID
    ) -> tuple[str, int, dict[UUID, int]]:
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()
        self.thread.join(timeout=2.0)
        self.writer_was_blocked = self.thread.is_alive()
        result = super()._read_input_parameters(session, game_id)
        self.read_layout_count = result[1]
        return result

    def begin_generation(self, game_id: UUID) -> DerivationStart:
        start = super().begin_generation(game_id)
        assert self.thread is not None
        self.thread.join(timeout=30.0)
        assert not self.thread.is_alive() and not self.errors
        return start


def test_catalog_write_during_begin_generation_rejects_the_candidate(fixture: Fixture) -> None:
    _catalog_update(fixture, expected_layout_count=1_000)
    _seed(
        fixture,
        _boards(800, {700: Board(700, trigger_cells=3, human_cells=3)}),
    )
    _derive(fixture)
    assert [row[0] for row in _series(fixture)] == [700]

    store = _CatalogWriteBetweenLockAndReadStore(fixture, 500)
    report = _derive(fixture, store)
    assert store.writer_was_blocked  # the catalog write waited for the state lock
    assert store.read_layout_count == 1_000  # old range with the old input version
    assert report.status is PublicationStatus.REJECTED
    assert report.current_input_version == report.expected_input_version + 1
    assert [row[0] for row in _series(fixture)] == [700] and not _state(fixture).fresh
    rerun = _derive(fixture)
    assert rerun.status is PublicationStatus.PUBLISHED
    assert _series(fixture) == [] and _state(fixture).fresh


# --- Audit P0-5: reads come from one consistent snapshot -------------------


class _PublishingDuringReadRepository(SqlAlchemySuperGameSeriesRepository):
    """Publishes a new generation in the middle of a list or boards read."""

    def __init__(self, session: Session, fixture: Fixture) -> None:
        super().__init__(session)
        self._fixture = fixture
        self.published = False

    def _publish_once(self) -> None:
        if not self.published:
            self.published = True
            report = _derive(self._fixture)
            assert report.status is PublicationStatus.PUBLISHED

    def list_series(self, game_id: UUID, **kwargs: Any) -> list[SuperGameSeriesRecord]:
        self._publish_once()
        return super().list_series(game_id, **kwargs)

    def board_documents(
        self, game_id: UUID, sequence_numbers: Sequence[int]
    ) -> dict[int, SeriesBoardDocument]:
        self._publish_once()
        return super().board_documents(game_id, sequence_numbers)


def test_list_and_boards_never_pair_old_series_with_a_new_fresh_state(fixture: Fixture) -> None:
    _seed(fixture, _boards(60, {10: Board(10, trigger_cells=3, human_cells=3)}))
    with fixture.database.owner_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO game_data_v2.image_board_search_projection_states "
                "(game_id, status, candidate_count, document_count, "
                "skipped_review_item_count) VALUES (:g, 'ready', 0, 0, 0)"
            ),
            {"g": fixture.game_id},
        )
    _derive(fixture)
    ((*_, series_id),) = _series(fixture)

    for call in ("boards", "list"):
        # A retrigger extends the series; the next generation has length 20/30.
        _set_trigger_cells(fixture, 15 if call == "boards" else 25, 3)
        expected_length = 20 if call == "boards" else 30
        with fixture.factory() as session, game_storage_scope(fixture.game_id):
            repository = _PublishingDuringReadRepository(session, fixture)
            service = SuperGameSeriesService(repository)
            if call == "boards":
                result = service.boards(fixture.game_id, series_id)
                lengths = [result.series.length]
                state = result.state
                assert [board.missing for board in result.boards] == [True] * len(result.boards)
            else:
                page = service.list(fixture.game_id)
                lengths = [item.length for item in page.items]
                state = page.state
            session.commit()
        assert repository.published
        # Fully new, or the old generation explicitly marked not fresh.
        assert lengths == [expected_length] or not state.fresh
        assert state.fresh is (state.generation_input_version == state.input_version)
        # Afterwards the new generation is served as fresh.
        assert [row[2] - row[1] + 1 for row in _series(fixture)] == [expected_length]
        assert _state(fixture).fresh


def test_read_snapshot_must_start_the_transaction(fixture: Fixture) -> None:
    with fixture.factory() as session, game_storage_scope(fixture.game_id):
        session.execute(text("SELECT 1"))
        with pytest.raises(RuntimeError, match="snapshot"):
            SqlAlchemySuperGameSeriesRepository(session).begin_read_snapshot()
        session.rollback()
