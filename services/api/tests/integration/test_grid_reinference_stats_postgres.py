"""Small owned PostgreSQL receipts and JSONB distinct-count regressions."""

import copy
import os
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
import test_grid_reinference_postgres as original
from game_predictor_api.application.grid_reinference_stats import STATS_POLICY, empty_scope
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_reinference import SqlAlchemyGridReinferenceRepository
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from sqlalchemy import select, text
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Owned disposable PostgreSQL only",
)


@pytest.fixture(scope="module")
def database():
    prefix = os.environ.get("GAME_PREDICTOR_STATS_TEST_ROUND", "TASK-1003_PG_R1")
    with patch.dict(os.environ, {"GAME_PREDICTOR_GRID_TEST_EVIDENCE_PREFIX": prefix}):
        yield from original.database.__wrapped__()


@pytest.mark.parametrize(
    "scenario",
    [
        "accepted",
        "unchanged",
        "grid_issue",
        "rollback_retry",
        "target_conflict",
        "deferred_stats",
        "cancel_between_sources",
    ],
)
def test_real_writer_stats_receipts_and_atomic_rollback(database, tmp_path, scenario):
    original.test_prepare_wait_freeze_start_real_write_and_lost_reply(database, tmp_path, scenario)


def test_inconsistent_partial_projection_rolls_back_geometry_and_receipts(database, tmp_path):
    original.test_prepare_wait_freeze_start_real_write_and_lost_reply(
        database, tmp_path, "inconsistent_partial_stats"
    )


def test_duplicate_frozen_id_across_pages_is_unique_and_legacy_skips_aggregation(database):
    # Existing frozen operations from the real workflow supply valid parents.
    with database.engine.connect() as connection:
        games = list(connection.scalars(text("SELECT id FROM public.games ORDER BY id")))
    found = None
    for game in games:
        with game_storage_scope(game), Session(database.engine) as session:
            repository = SqlAlchemyGridReinferenceRepository(session, Path.cwd())
            repository.bind(game, write=False)
            # Game ids are random: never pick the single-board deferred scenario by order
            # (TASK-1001). The expectation below needs an operation with two boards.
            boards: dict[object, set[str]] = {}
            first: dict[object, Target] = {}
            for candidate in session.scalars(
                select(Target)
                .where(Target.game_id == game)
                .order_by(Target.operation_id, Target.ordinal)
            ):
                if candidate.snapshot["board"] is None:
                    continue
                boards.setdefault(candidate.operation_id, set()).add(
                    candidate.snapshot["board"]["id"]
                )
                first.setdefault(candidate.operation_id, candidate)
            chosen = next((key for key, ids in boards.items() if len(ids) == 2), None)
            if chosen is not None:
                found = game, chosen, first[chosen].ordinal
                break
    assert found is not None
    game, operation_id, ordinal = found
    with game_storage_scope(game), Session(database.engine) as session, session.begin():
        repository = SqlAlchemyGridReinferenceRepository(session, Path.cwd())
        operation = repository.record(game, operation_id, lock=True)
        target = session.get(Target, (game, operation_id, ordinal))
        # A second frozen source can retain a board/cell ID moved since a prior
        # page. This is a JSONB-count input test, not a live board mutation.
        cloned_source_id = uuid4()
        from game_predictor_api.storage.grid_reinference_models import (
            GridReinferenceSourceModel as Source,
        )

        source = session.get(Source, (game, operation_id, target.source_ordinal))
        cloned_ordinal = target.source_ordinal + 100
        session.add(
            Source(
                game_id=game,
                operation_id=operation_id,
                ordinal=cloned_ordinal,
                source_image_id=cloned_source_id,
                live_source_image_id=None,
                document=copy.deepcopy(source.document),
            )
        )
        session.flush()
        session.add(
            Target(
                game_id=game,
                operation_id=operation_id,
                ordinal=cloned_ordinal * 10 + target.position_index + 1,
                source_ordinal=cloned_ordinal,
                source_image_id=cloned_source_id,
                position_index=target.position_index,
                target_result_id=uuid4(),
                snapshot=copy.deepcopy(target.snapshot),
                fingerprint_sha256=target.fingerprint_sha256,
            )
        )
        session.flush()
        operation.document = {
            **operation.document,
            "statsPolicy": STATS_POLICY,
            "scopeStats": empty_scope(),
        }
        repository.finalize_preparation(operation)
        total = operation.document["scopeStats"]
        assert total["existingBoardCount"] == 2
        assert total["existingCellCount"] == 30 and total["availableCellCount"] <= 30
        snapshot_before = copy.deepcopy(target.snapshot)
        manifest = operation.document["manifestSha256"]
        operation.document = {
            key: value
            for key, value in operation.document.items()
            if key not in {"statsPolicy", "scopeStats"}
        }
        execute = session.execute

        def forbid_stats(statement, *args, **kwargs):
            assert "count(DISTINCT" not in str(statement)
            return execute(statement, *args, **kwargs)

        with patch.object(session, "execute", forbid_stats):
            repository.finalize_preparation(operation)
        assert operation.document["manifestSha256"] == manifest
        assert target.snapshot == snapshot_before and "scopeStats" not in operation.document
        session.rollback()
