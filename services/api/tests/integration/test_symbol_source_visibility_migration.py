"""Exercise migration 0126 on an isolated database, including real writes."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 for isolated PostgreSQL tests.",
)


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    """Only this uniquely named database is changed or removed."""
    name = "game_predictor_task0708_" + uuid4().hex[:12]
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "0125_remove_legacy_public_game_store")
        with engine.begin() as connection:
            game_id = uuid4()
            for table in (
                "image_symbol_review_cells",
                "image_symbol_review_events",
                "image_symbol_review_bulk_targets",
            ):
                connection.execute(
                    text(
                        f"CREATE TABLE game_data_v2.task0708_{table} PARTITION OF "
                        f"game_data_v2.{table} FOR VALUES IN ('{game_id}')"
                    )
                )
        command.upgrade(config, "0126_symbol_cell_source_visibility")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text("SET statement_timeout='10s'"))
            connection.execute(text(f'DROP DATABASE "{name}"'))
        maintenance.dispose()


def test_outside_constraints_accept_no_asset_and_reject_inconsistent_rows(
    database: Engine,
) -> None:
    values = {
        "id": uuid4(),
        "game_id": uuid4(),
        "import_job_id": uuid4(),
        "review_item_id": uuid4(),
        "recognized_board_id": uuid4(),
        "sequence_number": 62287,
        "cell_index": 0,
        "row_index": 0,
        "column_index": 0,
        "geometry_revision": 1,
        "cropper_version": "test",
        "review_state": "pending",
        "assignment_source": "geometry_partial",
        "last_reviewed_by": "migration-test",
        "asset_mode": "none",
        "source_available": False,
        "source_visibility": "outside",
    }
    with database.begin() as connection:
        # LIKE copies checks and nullability but intentionally omits unrelated FKs.
        connection.execute(
            text(
                "CREATE TEMP TABLE visibility_probe (LIKE "
                "game_data_v2.image_symbol_review_cells INCLUDING DEFAULTS "
                "INCLUDING CONSTRAINTS) ON COMMIT DROP"
            )
        )
        connection.execute(
            text(
                "INSERT INTO visibility_probe ("
                + ", ".join(values)
                + ") VALUES ("
                + ", ".join(":" + key for key in values)
                + ")"
            ),
            values,
        )
        assert connection.scalar(text("SELECT count(*) FROM visibility_probe")) == 1
        for mutation in (
            "source_visibility = NULL",
            "source_visibility = 'full'",
            "source_available = true",
            "crop_sample_id = repeat('a',64)",
            "prediction_confidence = 0",
            "render_spec = '{}'::jsonb",
            "crop_relative_path = 'fake.png'",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text("UPDATE visibility_probe SET " + mutation))


def test_nullable_identities_and_partition_inheritance(database: Engine) -> None:
    with database.begin() as connection:
        columns = connection.execute(
            text(
                "SELECT table_name, column_name, is_nullable FROM information_schema.columns "
                "WHERE table_schema = 'game_data_v2' AND table_name IN "
                "('image_symbol_review_cells','image_symbol_review_events',"
                "'image_symbol_review_bulk_targets') AND column_name IN "
                "('crop_sample_id','crop_checksum_sha256','expected_crop_sample_id',"
                "'expected_crop_checksum_sha256')"
            )
        ).all()
        assert len(columns) == 6
        assert all(nullable == "YES" for _, _, nullable in columns)
        existing_columns = (
            connection.execute(
                text(
                    "SELECT is_nullable FROM information_schema.columns "
                    "WHERE table_schema = 'game_data_v2' AND table_name LIKE 'task0708_%' "
                    "AND column_name IN ('crop_sample_id','crop_checksum_sha256',"
                    "'expected_crop_sample_id','expected_crop_checksum_sha256')"
                )
            )
            .scalars()
            .all()
        )
        assert existing_columns == ["YES"] * 6
        existing_check = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
                "conrelid = 'game_data_v2.task0708_image_symbol_review_cells'::regclass "
                "AND conname = 'ck_image_symbol_review_cells_source_asset'"
            )
        )
        assert existing_check is not None and "outside" in existing_check
        game_id = uuid4()
        child = "visibility_test_" + game_id.hex
        connection.execute(
            text(
                f"CREATE TABLE game_data_v2.{child} PARTITION OF "
                f"game_data_v2.image_symbol_review_cells FOR VALUES IN ('{game_id}')"
            )
        )
        definition = connection.scalar(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE "
                "conrelid = CAST(:relation AS regclass) AND "
                "conname = 'ck_image_symbol_review_cells_source_asset'"
            ).bindparams(relation="game_data_v2." + child)
        )
        assert definition is not None and "outside" in definition
