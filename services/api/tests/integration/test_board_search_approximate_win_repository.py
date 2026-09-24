"""Isolated PostgreSQL coverage for the approximate-win range calculator.

Builds a minimal-but-real board-search fixture chain (job, source,
recognized board, review item -> `rebuild_game()`, the same production sync
used by the search endpoint) for a game routed to `game_data_v2`, then
exercises `SqlAlchemyBoardSearchApproximateWinRepository` and
`BoardSearchApproximateWinService` end to end against a live database.
Confirms: payout parity with the shared `payout-v3` evaluator for a complete
board, the confirmed-minimum lower bound for a partial board, a missing
position, `game_data_v2` routing, and that the whole calculation performs no
writes.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.board_search_approximate_win import (
    BoardSearchApproximateWinService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_search_approximate_win_repository import (
    SqlAlchemyBoardSearchApproximateWinRepository,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.game_data_v2_manifest_v1 import VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardSearchCandidateModel,
    ImageBoardSearchFastDocumentModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    JobModel,
    PaylineModel,
    PayoutRuleModel,
    RecognizedBoardModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SourceImageModel,
    SymbolModel,
)
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0652_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {_quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


# Board-search projection tables are game-owned (game_deletion_policy_v1),
# in addition to the core review chain tables every board needs.
_V2_PARTITIONED_TABLES = (
    "source_images",
    "recognized_boards",
    "cell_observations",
    "image_review_items",
    "image_sequence_canonical",
    "image_import_job_files",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_board_search_candidates",
    "image_board_search_fast_documents",
    "image_board_search_projection_states",
)


def _provision_v2_storage_location(session: Session, *, game_id: UUID) -> None:
    """Route a game to game_data_v2 and create its partitions for this test.

    Mirrors `test_board_import_coverage_repository.py`'s fixture: a real
    cutover also runs storage_generation-tracking migration steps this
    fixture skips, but the routing behavior under test only needs the
    registry row, live partitions for the tables this scenario touches, and
    GameStorageRouter.bind() to establish the session's search_path/RLS
    scope before any insert.
    """

    session.execute(
        text(
            "INSERT INTO public.game_storage_locations "
            "(game_id, store_schema, generation, manifest_version, status, revision) "
            "VALUES (:game_id, 'game_data_v2', 2, :version, 'active', 0)"
        ),
        {"game_id": game_id, "version": VERSION},
    )
    for table in _V2_PARTITIONED_TABLES:
        session.execute(
            text(
                f"CREATE TABLE game_data_v2.{table}_g_{game_id.hex} "
                f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game_id}')"
            )
        )
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)


def _import_job(session: Session, *, game_id: UUID) -> JobModel:
    job = JobModel(
        game_id=game_id,
        job_type="import",
        status="waiting_for_review",
        input_payload={"import_kind": "image_directory"},
        input_key=uuid4().hex,
    )
    session.add(job)
    session.flush()
    return job


def _source(session: Session, *, job: JobModel, relative_path: str) -> SourceImageModel:
    checksum = uuid4().hex * 2
    session.add(
        ImageFileExecutionModel(
            file_execution_key=checksum,
            source_checksum_sha256=checksum,
            pipeline_fingerprint="b" * 64,
            checkpoint_payload={},
            status="waiting_for_review",
            review_required=True,
        )
    )
    session.flush()
    session.add(
        ImageImportJobFileModel(
            job_id=job.id,
            file_execution_key=checksum,
            order_index=0,
            source_relative_path=relative_path,
            workflow_checkpoint_payload={},
            workflow_status="waiting_for_review",
            review_required=True,
        )
    )
    source = SourceImageModel(
        import_job_id=job.id,
        file_execution_key=checksum,
        relative_path=relative_path,
        checksum_sha256=checksum,
        width=100,
        height=100,
        status="waiting_for_review",
    )
    session.add(source)
    session.flush()
    return source


def _resolved_review_item(
    session: Session,
    *,
    game_id: UUID,
    job: JobModel,
    source: SourceImageModel,
    position: int,
    sequence_number: int,
    symbol_codes: tuple[str | None, ...],
    status: str = "accepted",
) -> ImageReviewItemModel:
    """One board resolved by a human decision, with `symbol_codes` exactly as
    `resolved_value.symbolCodes` — `None` entries are logical `?`, allowed
    even for an accepted/corrected board (a confirmed partial reading)."""

    assert len(symbol_codes) == 15
    board = RecognizedBoardModel(
        source_image_id=source.id,
        position_index=position,
        sequence_number_raw=str(sequence_number),
        sequence_number=sequence_number,
        sequence_confidence=1,
        board_geometry={},
        board_relative_path=f"boards/{sequence_number}.jpg",
        board_checksum_sha256="b" * 64,
        cells_prediction={},
        completeness_status="complete",
        board_confidence=1,
        pipeline_fingerprint="b" * 64,
        status="pending_review",
    )
    session.add(board)
    session.flush()
    session.add_all(
        CellObservationModel(
            recognized_board_id=board.id,
            row_index=n // 5,
            column_index=n % 5,
            crop_relative_path=f"cells/{sequence_number}_{n}.jpg",
            crop_checksum_sha256="c" * 64,
            cropper_version="fixture",
            prediction={},
        )
        for n in range(15)
    )
    item = ImageReviewItemModel(
        game_id=game_id,
        import_job_id=job.id,
        recognized_board_id=board.id,
        sequence_number=sequence_number,
        status=status,
        snapshot={},
        resolved_value={"sequenceNumber": sequence_number, "symbolCodes": list(symbol_codes)},
        resolved_by="fixture",
        resolved_at=datetime.now(UTC),
        resolution_revision=1,
    )
    session.add(item)
    session.flush()
    # `_rebuild_fast_documents` only selects a candidate whose review item
    # owns the sequence's canonical row (or a still-waiting pending
    # candidate); a resolved accepted/corrected decision is only reachable
    # through this table in production, via the resolve-review-item use
    # case that this fixture bypasses.
    session.add(
        ImageSequenceCanonicalModel(
            game_id=game_id,
            sequence_number=sequence_number,
            review_item_id=item.id,
            recognized_board_id=board.id,
            import_job_id=job.id,
            source_image_id=source.id,
            source_checksum_sha256=source.checksum_sha256,
            board_checksum_sha256=board.board_checksum_sha256,
            status=status,
            resolution_revision=1,
            geometry_revision=0,
        )
    )
    session.flush()
    return item


def _known(*, first: int = 0) -> tuple[str | None, ...]:
    """15 cells, all `None` except a leading run of `"A"` of the given length."""

    return ("A",) * first + (None,) * (15 - first)


def test_calculates_payout_range_across_complete_partial_and_missing_boards(
    database: Engine,
) -> None:
    game_id = uuid4()
    rules_version_id = uuid4()
    symbol_id = uuid4()

    with Session(database, expire_on_commit=False) as session, session.begin():
        session.add(
            GameModel(
                id=game_id,
                code="v2-app-win",
                name="V2 Approximate Win",
                expected_layout_count=50,
            )
        )
        session.flush()
        _provision_v2_storage_location(session, game_id=game_id)

        # Catalog rows (symbols/rules/paylines/payout_rules) are not
        # per-game-partitioned (game_data_v2_manifest_v1.CATALOG); ordinary
        # public-schema inserts. Flushed one at a time, matching the fixture
        # convention in test_board_import_coverage_repository.py, so each
        # insert's foreign key target already exists in the database.
        session.add(
            SymbolModel(
                id=symbol_id,
                game_id=game_id,
                mobile_code=1,
                code="A",
                name="Symbol A",
                is_wildcard=False,
                display_order=0,
                status=SymbolStatus.ACTIVE,
            )
        )
        session.flush()
        session.add(
            RulesVersionModel(
                id=rules_version_id,
                game_id=game_id,
                version=1,
                rows=3,
                columns=5,
                spin_cost=20,
                status=RulesVersionStatus.PUBLISHED,
                published_at=datetime.now(UTC),
            )
        )
        session.flush()
        session.add(
            RulesVersionSymbolModel(
                rules_version_id=rules_version_id,
                symbol_id=symbol_id,
                minimum_match_length=2,
                is_active=True,
            )
        )
        session.flush()
        session.add(
            PaylineModel(
                rules_version_id=rules_version_id,
                code="top",
                name="top",
                row_path=[0, 0, 0, 0, 0],
                display_order=0,
                is_active=True,
            )
        )
        session.add_all(
            PayoutRuleModel(
                rules_version_id=rules_version_id,
                symbol_id=symbol_id,
                match_length=length,
                payout_credits=credits,
            )
            for length, credits in ((2, 5), (3, 10), (4, 25), (5, 50))
        )
        session.flush()

        job = _import_job(session, game_id=game_id)
        source = _source(session, job=job, relative_path="page_1.jpg")

        # sequence 2: fully known, 5-in-a-row on "top" -> length-5 payout (50)
        _resolved_review_item(
            session,
            game_id=game_id,
            job=job,
            source=source,
            position=0,
            sequence_number=2,
            symbol_codes=_known(first=15),
        )
        # sequence 3: only the first two "top" cells known -> confirmed
        # length-2 payout (5); the rest of the board is unknown
        _resolved_review_item(
            session,
            game_id=game_id,
            job=job,
            source=source,
            position=1,
            sequence_number=3,
            symbol_codes=_known(first=2),
            status="corrected",
        )
        # sequence 4 is intentionally left without any review item (missing)

        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game_id)

    # A fresh, unscoped session/transaction: the calculation itself must be
    # read-only, so nothing it does may depend on the fixture's own
    # transaction or write anything back.
    with Session(database, expire_on_commit=False) as session:
        before_counts = _game_owned_row_counts(session, game_id)

        repository = SqlAlchemyBoardSearchApproximateWinRepository(session)
        service = BoardSearchApproximateWinService(repository)
        calculation = service.calculate(
            game_id=game_id,
            start_sequence_number=1,
            requested_spin_count=4,
        )

        after_counts = _game_owned_row_counts(session, game_id)

    assert before_counts == after_counts, "approximate-win calculation must not write anything"

    result = calculation.result
    assert calculation.data_source.value == "operational_review"
    assert calculation.rules_version_id == rules_version_id
    assert calculation.spin_cost == 20
    assert result.evaluated_spin_count == 4
    assert result.sequence_length == 50
    assert result.wrapped_at_sequence_end is False

    assert result.completeness.complete_board_count == 1
    assert result.completeness.partial_board_count == 1
    assert result.completeness.missing_board_count == 2  # sequences 4 and 5

    assert result.summary.recognized_payout_credits == 55  # 50 + 5
    assert result.summary.spin_cost_credits == 80  # 4 spins * 20
    assert result.summary.balance_credits == 55 - 80

    rows_by_sequence = {row.sequence_number: row for row in result.rows}
    assert set(rows_by_sequence) == {2, 3}
    assert rows_by_sequence[2].spin_number == 1
    assert rows_by_sequence[2].payout_credits == 50
    assert rows_by_sequence[2].payout_kind == "exact"
    assert rows_by_sequence[2].cumulative_cost_credits == 20
    assert rows_by_sequence[3].spin_number == 2
    assert rows_by_sequence[3].payout_credits == 5
    assert rows_by_sequence[3].payout_kind == "confirmed_minimum"
    assert rows_by_sequence[3].cumulative_cost_credits == 40
    assert rows_by_sequence[3].cumulative_payout_credits == 55
    assert rows_by_sequence[3].cumulative_balance_credits == 55 - 40


def _game_owned_row_counts(session: Session, game_id: UUID) -> dict[str, int]:
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    return {
        "recognized_boards": int(
            session.scalar(select(func.count()).select_from(RecognizedBoardModel)) or 0
        ),
        "image_review_items": int(
            session.scalar(
                select(func.count())
                .select_from(ImageReviewItemModel)
                .where(ImageReviewItemModel.game_id == game_id)
            )
            or 0
        ),
        "image_board_search_candidates": int(
            session.scalar(
                select(func.count())
                .select_from(ImageBoardSearchCandidateModel)
                .where(ImageBoardSearchCandidateModel.game_id == game_id)
            )
            or 0
        ),
        "image_board_search_fast_documents": int(
            session.scalar(
                select(func.count())
                .select_from(ImageBoardSearchFastDocumentModel)
                .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            )
            or 0
        ),
    }
