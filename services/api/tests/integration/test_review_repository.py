from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.reviews import ReviewService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.reviews import (
    ReviewItemStatus,
    ReviewResolutionAction,
)
from game_predictor_api.storage.models import (
    GameModel,
    ReviewBatchModel,
    ReviewFeedbackExportModel,
    ReviewItemModel,
    ReviewResolutionModel,
    SymbolModel,
)
from game_predictor_api.storage.review_repository import (
    SqlAlchemyReviewRepository,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
REPORT_PATH = REPOSITORY_ROOT / "ai_docs" / "quality" / "m6-symbol-active-learning-selection.json"
TEST_DATABASE_NAME = "game_predictor_review_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason=("Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests."),
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_review_database() -> Iterator[URL]:
    maintenance_engine = create_engine(
        _database_url("postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    test_database_url = _database_url(TEST_DATABASE_NAME)
    identifier = f'"{TEST_DATABASE_NAME}"'

    try:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        yield test_database_url
    finally:
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _report() -> tuple[dict[str, object], str]:
    content = REPORT_PATH.read_bytes()
    value: Any = json.loads(content)
    assert isinstance(value, dict)
    return value, hashlib.sha256(content).hexdigest()


def test_review_repository_persists_idempotent_immutable_batch(
    isolated_review_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_review_database), "head")
    engine = create_engine(isolated_review_database, pool_pre_ping=True)
    report, report_sha256 = _report()
    symbol_codes = tuple(str(value) for value in cast(Sequence[object], report["classes"]))

    try:
        with Session(engine, expire_on_commit=False) as session:
            game = GameModel(
                code="review-game",
                name="Review game",
                status=GameStatus.ACTIVE,
            )
            session.add(game)
            session.flush()
            session.add_all(
                [
                    SymbolModel(
                        game_id=game.id,
                        mobile_code=index,
                        code=code,
                        name=code,
                        display_order=index - 1,
                        status=SymbolStatus.ACTIVE,
                    )
                    for index, code in enumerate(symbol_codes, start=1)
                ]
            )
            session.commit()

            service = ReviewService(SqlAlchemyReviewRepository(session))
            imported, created = service.import_review_batch(
                game_id=game.id,
                source_report_sha256=report_sha256,
                report=report,
            )
            session.commit()
            retried, created_on_retry = service.import_review_batch(
                game_id=game.id,
                source_report_sha256=report_sha256,
                report=report,
            )

            assert created is True
            assert created_on_retry is False
            assert retried.id == imported.id
            assert imported.item_count == 30
            assert session.scalar(select(func.count()).select_from(ReviewBatchModel)) == 1
            assert session.scalar(select(func.count()).select_from(ReviewItemModel)) == 30
            page = service.list_review_items(
                review_batch_id=imported.id,
                status=ReviewItemStatus.PENDING,
                after_selection_rank=0,
                limit=7,
            )
            assert [item.selection_rank for item in page.items] == list(range(1, 8))
            assert page.next_after_selection_rank == 7
            cells = cast(
                Sequence[object],
                page.items[0].prediction_snapshot["cells"],
            )
            assert len(cells) == 15
            all_items = service.list_review_items(
                review_batch_id=imported.id,
                status=None,
                after_selection_rank=0,
                limit=100,
            ).items
            first_key = uuid4()
            for item in all_items:
                snapshot_cells = cast(
                    Sequence[Mapping[str, object]],
                    item.prediction_snapshot["cells"],
                )
                resolution_command = {
                    "review_item_id": item.id,
                    "idempotency_key": first_key
                    if item.id == all_items[0].id
                    else uuid4(),
                    "expected_revision": 0,
                    "action": ReviewResolutionAction.ACCEPT,
                    "geometry_accepted": True,
                    "labels": tuple(
                        {
                            "cellIndex": cell["cellIndex"],
                            "sampleId": cell["sampleId"],
                            "symbolCode": cell["predictedSymbolCode"],
                        }
                        for cell in snapshot_cells
                    ),
                    "rejection_reason": None,
                    "resolved_by": "integration-admin",
                }
                resolved, event, event_created = service.resolve_review_item(
                    **resolution_command
                )
                assert resolved.resolution_revision == 1
                assert event.revision == 1
                assert event_created is True
                if item.id == all_items[0].id:
                    _, retried_event, created_on_resolution_retry = (
                        service.resolve_review_item(**resolution_command)
                    )
                    assert retried_event.id == event.id
                    assert created_on_resolution_retry is False
            session.commit()
            feedback_export, export_created = service.create_feedback_export(
                review_batch_id=imported.id,
                created_by="integration-admin",
            )
            retried_export, export_created_on_retry = service.create_feedback_export(
                review_batch_id=imported.id,
                created_by="integration-admin",
            )
            session.commit()

            assert export_created is True
            assert export_created_on_retry is False
            assert retried_export.id == feedback_export.id
            assert feedback_export.sample_count == 30 * 15
            assert session.scalar(
                select(func.count()).select_from(ReviewResolutionModel)
            ) == 30
            assert session.scalar(
                select(func.count()).select_from(ReviewFeedbackExportModel)
            ) == 1
    finally:
        engine.dispose()
