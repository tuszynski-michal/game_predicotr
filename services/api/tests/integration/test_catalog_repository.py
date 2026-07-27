import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.datasets import DatasetService
from game_predictor_api.application.rules import RulesService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    GameStatus,
    SymbolStatus,
)
from game_predictor_api.domain.rules import (
    RulesConflictError,
    RulesVersionStatus,
)
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.dataset_repository import (
    SqlAlchemyDatasetRepository,
)
from game_predictor_api.storage.models import LayoutModel
from game_predictor_api.storage.rules_repository import SqlAlchemyRulesRepository
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_catalog_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_catalog_database() -> Iterator[URL]:
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


def test_catalog_repository_uses_real_constraints(
    isolated_catalog_database: URL,
) -> None:
    command.upgrade(_migration_config(isolated_catalog_database), "head")
    engine = create_engine(isolated_catalog_database, pool_pre_ping=True)

    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "dataset_versions",
            "games",
            "layouts",
            "paylines",
            "payout_rules",
            "rules_versions",
            "rules_version_symbols",
            "symbols",
        }

        with Session(engine, expire_on_commit=False) as session:
            service = CatalogService(SqlAlchemyCatalogRepository(session))
            game = service.create_game(
                code="game-1",
                name="Game 1",
                status=GameStatus.ACTIVE,
            )
            first = service.create_symbol(
                game.id,
                mobile_code=1,
                code="S1",
                name="Symbol 1",
                image_path="symbols/game-1/s1.png",
                is_wildcard=False,
                display_order=20,
                status=SymbolStatus.ACTIVE,
            )
            second = service.create_symbol(
                game.id,
                mobile_code=2,
                code="WILD",
                name="Wildcard",
                image_path=None,
                is_wildcard=True,
                display_order=10,
                status=SymbolStatus.ACTIVE,
            )
            session.commit()

            assert [symbol.id for symbol in service.list_symbols(game.id)] == [
                second.id,
                first.id,
            ]
            assert service.archive_symbol(game.id, first.id).status is SymbolStatus.ARCHIVED
            session.commit()

            rules_service = RulesService(SqlAlchemyRulesRepository(session))
            first_rules = rules_service.create_rules_version(
                game.id,
                rows=3,
                columns=5,
                spin_cost=10,
            )
            second_rules = rules_service.create_rules_version(
                game.id,
                rows=4,
                columns=6,
                spin_cost=20,
            )
            assert [item.version for item in rules_service.list_rules_versions(game.id)] == [2, 1]
            assert first_rules.version == 1
            assert second_rules.version == 2
            assert (
                rules_service.update_rules_version(
                    second_rules.id,
                    spin_cost=25,
                ).spin_cost
                == 25
            )
            first_payline = rules_service.create_payline(
                first_rules.id,
                code="line-v",
                name="V",
                row_path=[0, 1, 2, 1, 0],
                display_order=20,
                is_active=True,
            )
            second_payline = rules_service.create_payline(
                first_rules.id,
                code="line-top",
                name="Top",
                row_path=[0, 0, 0, 0, 0],
                display_order=10,
                is_active=True,
            )
            assert [payline.id for payline in rules_service.list_paylines(first_rules.id)] == [
                second_payline.id,
                first_payline.id,
            ]
            assert (
                rules_service.archive_payline(
                    first_rules.id,
                    first_payline.id,
                ).is_active
                is False
            )
            with pytest.raises(RulesConflictError) as error:
                rules_service.update_rules_version(first_rules.id, columns=6)
            assert error.value.code == "RULES_DIMENSIONS_IN_USE"
            session.commit()

            with pytest.raises(RulesConflictError) as error:
                rules_service.create_payline(
                    first_rules.id,
                    code="line-copy",
                    name="Copy",
                    row_path=[0, 1, 2, 1, 0],
                    display_order=30,
                    is_active=True,
                )
            assert error.value.code == "DUPLICATE_PAYLINE"
            session.rollback()

            symbol_config = rules_service.update_rules_version_symbol(
                first_rules.id,
                first.id,
                minimum_match_length=2,
                is_active=True,
            )
            payout_two = rules_service.create_payout_rule(
                first_rules.id,
                symbol_id=first.id,
                match_length=2,
                payout_credits=10,
                is_active=True,
            )
            payout_five = rules_service.create_payout_rule(
                first_rules.id,
                symbol_id=first.id,
                match_length=5,
                payout_credits=100,
                is_active=True,
            )
            assert symbol_config.minimum_match_length == 2
            assert [
                item.match_length
                for item in rules_service.list_payout_rules(first_rules.id)
            ] == [2, 5]
            rules_service.update_rules_version_symbol(
                first_rules.id,
                first.id,
                minimum_match_length=3,
                is_active=True,
            )
            assert (
                rules_service.get_payout_rule(
                    first_rules.id,
                    payout_two.id,
                ).is_active
                is False
            )
            assert (
                rules_service.get_payout_rule(
                    first_rules.id,
                    payout_five.id,
                ).is_active
                is True
            )
            wildcard_config = rules_service.update_rules_version_symbol(
                first_rules.id,
                second.id,
                minimum_match_length=None,
                is_active=True,
            )
            assert wildcard_config.minimum_match_length is None
            session.commit()

            with pytest.raises(CatalogConflictError) as identity_error:
                service.update_symbol(
                    game.id,
                    first.id,
                    is_wildcard=True,
                )
            assert identity_error.value.code == "SYMBOL_RULES_IDENTITY_IN_USE"
            session.rollback()

            with pytest.raises(RulesConflictError) as error:
                rules_service.create_payout_rule(
                    first_rules.id,
                    symbol_id=first.id,
                    match_length=5,
                    payout_credits=200,
                    is_active=True,
                )
            assert error.value.code == "PAYOUT_RULE_ALREADY_EXISTS"
            session.rollback()

            for match_length, payout_credits in ((3, 20), (4, 50)):
                rules_service.create_payout_rule(
                    first_rules.id,
                    symbol_id=first.id,
                    match_length=match_length,
                    payout_credits=payout_credits,
                    is_active=True,
                )
            assert rules_service.get_publication_readiness(first_rules.id).ready
            published = rules_service.publish_rules_version(first_rules.id)
            assert published.status is RulesVersionStatus.PUBLISHED
            assert published.published_at is not None
            session.commit()

            with pytest.raises(RulesConflictError) as immutable_error:
                rules_service.update_payout_rule(
                    first_rules.id,
                    payout_five.id,
                    payout_credits=200,
                )
            assert immutable_error.value.code == "RULES_VERSION_IMMUTABLE"
            session.rollback()

            dataset_service = DatasetService(
                SqlAlchemyDatasetRepository(session)
            )
            first_dataset = dataset_service.generate_mock_dataset(
                game.id,
                rules_version_id=first_rules.id,
                seed=71401,
            )
            second_dataset = dataset_service.generate_mock_dataset(
                game.id,
                rules_version_id=first_rules.id,
                seed=71401,
            )
            assert first_dataset.version == 1
            assert second_dataset.version == 2
            assert first_dataset.layout_count == 1000
            first_layouts = list(
                session.scalars(
                    select(LayoutModel)
                    .where(
                        LayoutModel.dataset_version_id == first_dataset.id
                    )
                    .order_by(LayoutModel.sequence_number)
                )
            )
            second_layouts = list(
                session.scalars(
                    select(LayoutModel)
                    .where(
                        LayoutModel.dataset_version_id == second_dataset.id
                    )
                    .order_by(LayoutModel.sequence_number)
                )
            )
            assert [item.sequence_number for item in first_layouts] == list(
                range(1, 1001)
            )
            assert [
                (item.signature, item.cells) for item in first_layouts
            ] == [
                (item.signature, item.cells) for item in second_layouts
            ]
            assert len({item.signature for item in first_layouts}) == 994
            session.commit()

            archived = rules_service.archive_rules_version(first_rules.id)
            assert archived.status is RulesVersionStatus.ARCHIVED
            assert archived.published_at == published.published_at
            session.commit()

        with Session(engine, expire_on_commit=False) as session:
            service = CatalogService(SqlAlchemyCatalogRepository(session))
            with pytest.raises(CatalogConflictError) as error:
                service.create_game(
                    code="game-1",
                    name="Duplicate",
                    status=GameStatus.DRAFT,
                )
            assert error.value.code == "GAME_CODE_ALREADY_EXISTS"
            session.rollback()

            with pytest.raises(CatalogConflictError) as error:
                service.create_symbol(
                    game.id,
                    mobile_code=3,
                    code="S1",
                    name="Duplicate code",
                    image_path=None,
                    is_wildcard=False,
                    display_order=30,
                    status=SymbolStatus.ACTIVE,
                )
            assert error.value.code == "SYMBOL_CODE_ALREADY_EXISTS"
            session.rollback()

            with pytest.raises(CatalogConflictError) as error:
                service.create_symbol(
                    game.id,
                    mobile_code=2,
                    code="S2",
                    name="Duplicate mobile code",
                    image_path=None,
                    is_wildcard=False,
                    display_order=30,
                    status=SymbolStatus.ACTIVE,
                )
            assert error.value.code == "SYMBOL_MOBILE_CODE_ALREADY_EXISTS"
    finally:
        engine.dispose()
