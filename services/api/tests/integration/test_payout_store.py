import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    GameModel,
    LayoutModel,
    LayoutPayoutModel,
    PaylineModel,
    PayoutRuleModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from game_predictor_worker.payouts.contracts import CalculatedLayoutPayout
from game_predictor_worker.payouts.store import SqlAlchemyPayoutStore
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_payout_store_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


@pytest.fixture
def isolated_payout_database() -> Iterator[URL]:
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


def test_payout_store_loads_versioned_source_and_upserts_without_duplicates(
    isolated_payout_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_payout_database), "head")
    engine = create_engine(isolated_payout_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    store = SqlAlchemyPayoutStore(session_factory)
    game_id = uuid4()
    rules_id = uuid4()
    dataset_id = uuid4()
    ordinary_id = uuid4()
    wildcard_id = uuid4()
    calculated_at = datetime(2026, 7, 27, 21, tzinfo=UTC)

    try:
        with Session(engine) as session, session.begin():
            session.add(
                GameModel(
                    id=game_id,
                    code="payout-game",
                    name="Payout game",
                    status=GameStatus.ACTIVE,
                )
            )
            session.flush()
            session.add_all(
                [
                    SymbolModel(
                        id=ordinary_id,
                        game_id=game_id,
                        mobile_code=1,
                        code="ordinary",
                        name="Ordinary",
                        is_wildcard=False,
                        display_order=0,
                        status=SymbolStatus.ACTIVE,
                    ),
                    SymbolModel(
                        id=wildcard_id,
                        game_id=game_id,
                        mobile_code=9,
                        code="wild",
                        name="Wild",
                        is_wildcard=True,
                        display_order=1,
                        status=SymbolStatus.ACTIVE,
                    ),
                ]
            )
            session.flush()
            session.add(
                RulesVersionModel(
                    id=rules_id,
                    game_id=game_id,
                    version=1,
                    rows=2,
                    columns=3,
                    spin_cost=10,
                    status=RulesVersionStatus.PUBLISHED,
                    published_at=calculated_at,
                )
            )
            session.flush()
            session.add_all(
                [
                    RulesVersionSymbolModel(
                        rules_version_id=rules_id,
                        symbol_id=ordinary_id,
                        minimum_match_length=2,
                        is_active=True,
                    ),
                    RulesVersionSymbolModel(
                        rules_version_id=rules_id,
                        symbol_id=wildcard_id,
                        minimum_match_length=None,
                        is_active=True,
                    ),
                    PaylineModel(
                        rules_version_id=rules_id,
                        code="top",
                        name="Top",
                        row_path=[0, 0, 0],
                        display_order=0,
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    PayoutRuleModel(
                        rules_version_id=rules_id,
                        symbol_id=ordinary_id,
                        match_length=2,
                        payout_credits=10,
                        is_active=True,
                    ),
                    PayoutRuleModel(
                        rules_version_id=rules_id,
                        symbol_id=ordinary_id,
                        match_length=3,
                        payout_credits=20,
                        is_active=True,
                    ),
                ]
            )
            session.flush()
            session.add(
                DatasetVersionModel(
                    id=dataset_id,
                    game_id=game_id,
                    version=1,
                    rows=2,
                    columns=3,
                    signature_cell_width=2,
                    layout_count=2,
                    status=DatasetVersionStatus.PUBLISHED,
                    generation_seed=1,
                    generator_version="test-v1",
                    published_at=calculated_at,
                )
            )
            session.flush()
            session.add_all(
                [
                    LayoutModel(
                        dataset_version_id=dataset_id,
                        sequence_number=1,
                        signature="010101010101",
                        cells=[1, 1, 1, 1, 1, 1],
                    ),
                    LayoutModel(
                        dataset_version_id=dataset_id,
                        sequence_number=2,
                        signature="010901010101",
                        cells=[1, 9, 1, 1, 1, 1],
                    ),
                ]
            )

        source = store.load_source(dataset_id, rules_id)
        assert source is not None
        assert source.game_id == game_id
        assert [symbol.mobile_code for symbol in source.game.symbols] == [1, 9]
        assert [rule.payout_credits for rule in source.payout_rules] == [10, 20]
        assert [
            layout.sequence_number
            for layout in store.list_layout_batch(
                dataset_id,
                after_sequence_number=0,
                limit=1,
            )
        ] == [1]

        first = CalculatedLayoutPayout(
            dataset_version_id=dataset_id,
            rules_version_id=rules_id,
            sequence_number=1,
            algorithm_version="payout-v2",
            total_payout=20,
            audit_path="payout-audits/batch.jsonl",
            calculated_at=calculated_at,
        )
        store.upsert_payouts((first,))
        store.upsert_payouts((first,))

        with Session(engine) as session:
            assert session.scalar(select(func.count()).select_from(LayoutPayoutModel)) == 1
            persisted = session.get(
                LayoutPayoutModel,
                (dataset_id, rules_id, 1, "payout-v2"),
            )
            assert persisted is not None
            assert persisted.total_payout == 20
            assert persisted.audit_path == "payout-audits/batch.jsonl"
    finally:
        engine.dispose()
