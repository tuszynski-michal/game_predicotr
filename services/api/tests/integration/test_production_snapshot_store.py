import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing
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
    RulesVersionModel,
    RulesVersionSymbolModel,
    SymbolModel,
)
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    ProductionSnapshotSpec,
    SnapshotGameSelection,
    SqlAlchemyProductionSnapshotStore,
    validate_snapshot_artifact,
)
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_production_snapshot_test"

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
def isolated_snapshot_database() -> Iterator[URL]:
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


def test_postgres_source_generates_exact_version_production_snapshot(
    isolated_snapshot_database: URL,
    tmp_path: Path,
) -> None:
    command.upgrade(_migration_config(isolated_snapshot_database), "head")
    engine = create_engine(isolated_snapshot_database, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    store = SqlAlchemyProductionSnapshotStore(session_factory)
    game_id = uuid4()
    rules_id = uuid4()
    dataset_id = uuid4()
    ordinary_id = uuid4()
    wildcard_id = uuid4()
    created_at = datetime(2026, 7, 27, 22, tzinfo=UTC)
    selection = SnapshotGameSelection(dataset_id, rules_id, "payout-v2")

    try:
        with Session(engine) as session, session.begin():
            session.add(
                GameModel(
                    id=game_id,
                    code="production-game",
                    name="Production game",
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
                        image_path="symbols/ordinary.png",
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
                        image_path=None,
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
                    version=7,
                    rows=1,
                    columns=2,
                    spin_cost=10,
                    status=RulesVersionStatus.PUBLISHED,
                    published_at=created_at,
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
                ]
            )
            session.add(
                DatasetVersionModel(
                    id=dataset_id,
                    game_id=game_id,
                    version=9,
                    rows=1,
                    columns=2,
                    signature_cell_width=2,
                    layout_count=2,
                    status=DatasetVersionStatus.PUBLISHED,
                    generation_seed=123,
                    generator_version="integration-v1",
                    published_at=created_at,
                )
            )
            session.flush()
            session.add_all(
                [
                    LayoutModel(
                        dataset_version_id=dataset_id,
                        sequence_number=1,
                        signature="0109",
                        cells=[1, 9],
                    ),
                    LayoutModel(
                        dataset_version_id=dataset_id,
                        sequence_number=2,
                        signature="0101",
                        cells=[1, 1],
                    ),
                ]
            )
            session.flush()
            session.add_all(
                [
                    LayoutPayoutModel(
                        dataset_version_id=dataset_id,
                        rules_version_id=rules_id,
                        sequence_number=1,
                        algorithm_version="payout-v1",
                        total_payout=999,
                        audit_path="payout-audits/historical.jsonl",
                        calculated_at=created_at,
                    ),
                    LayoutPayoutModel(
                        dataset_version_id=dataset_id,
                        rules_version_id=rules_id,
                        sequence_number=1,
                        algorithm_version="payout-v2",
                        total_payout=20,
                        audit_path="payout-audits/current-1.jsonl",
                        calculated_at=created_at,
                    ),
                    LayoutPayoutModel(
                        dataset_version_id=dataset_id,
                        rules_version_id=rules_id,
                        sequence_number=2,
                        algorithm_version="payout-v2",
                        total_payout=30,
                        audit_path="payout-audits/current-2.jsonl",
                        calculated_at=created_at,
                    ),
                ]
            )

        source = store.load_snapshot_game(selection)
        assert source is not None
        assert source.dataset_version == 9
        assert source.rules_version == 7
        assert [symbol.mobile_code for symbol in source.symbols] == [1, 9]
        assert [
            (layout.sequence_number, layout.payout)
            for layout in store.list_snapshot_layout_batch(
                selection,
                after_sequence_number=0,
                limit=1,
            )
        ] == [(1, 20)]

        database_path = tmp_path / "production.db"
        result = ProductionSnapshotGenerator(store, batch_size=1).generate(
            database_path,
            ProductionSnapshotSpec(
                release_version="integration.1",
                created_at=created_at,
                games=(selection,),
            ),
        )

        with closing(sqlite3.connect(database_path)) as connection:
            game = connection.execute(
                """
                SELECT
                    code, rows, columns, spin_cost, signature_cell_width,
                    layout_count, dataset_version, rules_version
                FROM games
                """
            ).fetchone()
            symbols = connection.execute(
                """
                SELECT mobile_code, image_asset_key
                FROM symbols
                ORDER BY mobile_code
                """
            ).fetchall()
            layouts = connection.execute(
                """
                SELECT sequence_number, signature, payout
                FROM layouts
                ORDER BY sequence_number
                """
            ).fetchall()
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))

        assert result.game_count == 1
        assert result.layout_count == 2
        assert game == ("production-game", 1, 2, 10, 2, 2, 9, 7)
        assert symbols == [(1, "symbols/ordinary.png"), (9, None)]
        assert layouts == [(1, "0109", 20), (2, "0101", 30)]
        assert metadata["algorithm_version"] == "payout-v2"
        assert metadata["content_checksum"] == result.logical_content_sha256

        artifact = ProductionSnapshotArtifactPublisher(
            ProductionSnapshotGenerator(store, batch_size=1),
            tmp_path / "artifacts",
        ).publish(
            ProductionSnapshotSpec(
                release_version="integration.1",
                created_at=created_at,
                games=(selection,),
            )
        )
        validated_artifact = validate_snapshot_artifact(artifact.directory)
        assert validated_artifact.manifest.games[0].game_id == game_id
        assert validated_artifact.manifest.games[0].dataset_version_id == dataset_id
        assert validated_artifact.manifest.games[0].rules_version_id == rules_id
        assert validated_artifact.manifest.snapshot_file_sha256 == (result.snapshot_file_sha256)
    finally:
        engine.dispose()
