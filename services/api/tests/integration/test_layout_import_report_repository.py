import os
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.layout_import_reports import (
    LayoutImportReportService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.jobs import (
    JobConflictError,
    JobStatus,
    JobType,
    create_job,
)
from game_predictor_api.domain.layout_import_reports import (
    LayoutImportRowStatus,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.job_repository import (
    SqlAlchemyJobRepository,
)
from game_predictor_api.storage.layout_import_report_repository import (
    SqlAlchemyLayoutImportReportRepository,
)
from game_predictor_api.storage.models import (
    DatasetVersionModel,
    JobModel,
    LayoutImportNormalizedRowModel,
    LayoutImportRowModel,
    LayoutModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
)
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TEST_DATABASE_NAME = "game_predictor_import_report_test"

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)


def _database_url(database_name: str) -> URL:
    return make_url(ApiSettings.from_environment().database_url).set(database=database_name)


def _migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    rendered_url = database_url.render_as_string(hide_password=False).replace(
        "%",
        "%%",
    )
    config.set_main_option("sqlalchemy.url", rendered_url)
    return config


@pytest.fixture
def isolated_import_report_database() -> Iterator[URL]:
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


def test_postgres_report_has_exact_counts_bounded_groups_and_filtered_rows(
    isolated_import_report_database: URL,
) -> None:
    command.upgrade(
        _migration_config(isolated_import_report_database),
        "head",
    )
    engine = create_engine(
        isolated_import_report_database,
        pool_pre_ping=True,
    )
    now = datetime.now(UTC)
    try:
        with Session(engine, expire_on_commit=False) as session:
            catalog = CatalogService(SqlAlchemyCatalogRepository(session))
            game = catalog.create_game(
                code="import-report-game",
                name="Import report game",
                status=GameStatus.ACTIVE,
            )
            first_symbol = catalog.create_symbol(
                game.id,
                mobile_code=1,
                code="S1",
                name="S1",
                image_path=None,
                is_wildcard=False,
                display_order=1,
                status=SymbolStatus.ACTIVE,
            )
            second_symbol = catalog.create_symbol(
                game.id,
                mobile_code=2,
                code="S2",
                name="S2",
                image_path=None,
                is_wildcard=False,
                display_order=2,
                status=SymbolStatus.ACTIVE,
            )
            rules = RulesVersionModel(
                game_id=game.id,
                version=1,
                rows=1,
                columns=2,
                spin_cost=10,
                status=RulesVersionStatus.PUBLISHED,
                published_at=now,
            )
            session.add(rules)
            session.flush()
            session.add_all(
                [
                    RulesVersionSymbolModel(
                        rules_version_id=rules.id,
                        symbol_id=first_symbol.id,
                        minimum_match_length=2,
                        is_active=True,
                    ),
                    RulesVersionSymbolModel(
                        rules_version_id=rules.id,
                        symbol_id=second_symbol.id,
                        minimum_match_length=2,
                        is_active=True,
                    ),
                ]
            )
            import_job = replace(
                create_job(
                    JobType.IMPORT,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "import_kind": "layout_file",
                        "source_path": "report.jsonl",
                        "source_checksum": "c" * 64,
                        "source_size_bytes": 600,
                        "file_format": "jsonl",
                        "contract_version": 1,
                    },
                ),
                status=JobStatus.COMPLETED,
                progress_current=600,
                progress_total=600,
                success_count=5,
                failure_count=1,
                stage="staged_import_rows",
                finished_at=now,
            )
            validation_job = replace(
                create_job(
                    JobType.VALIDATE,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "validation_kind": "layout_import",
                        "import_job_id": str(import_job.id),
                        "rules_version_id": str(rules.id),
                    },
                ),
                status=JobStatus.COMPLETED,
                progress_current=6,
                progress_total=6,
                success_count=4,
                failure_count=2,
                stage="validated_import_rows",
                finished_at=now,
            )
            jobs = SqlAlchemyJobRepository(session)
            jobs.add_job(import_job)
            jobs.add_job(validation_job)
            session.add_all(
                [
                    LayoutImportRowModel(
                        job_id=import_job.id,
                        line_number=line_number,
                        byte_offset_end=line_number * 100,
                        sequence_number=sequence_number,
                        cells=cells,
                        error_code=error_code,
                        error_message=error_message,
                    )
                    for (
                        line_number,
                        sequence_number,
                        cells,
                        error_code,
                        error_message,
                    ) in (
                        (1, 1, [1, 2], None, None),
                        (2, 2, [2, 1], None, None),
                        (3, 2, [2, 1], None, None),
                        (4, 4, [1, 2], None, None),
                        (5, 3, [1, 99], None, None),
                        (
                            6,
                            None,
                            None,
                            "import_record_invalid",
                            "Line 6 is invalid.",
                        ),
                    )
                ]
            )
            session.flush()
            session.add_all(
                [
                    LayoutImportNormalizedRowModel(
                        validation_job_id=validation_job.id,
                        import_job_id=import_job.id,
                        rules_version_id=rules.id,
                        line_number=line_number,
                        sequence_number=sequence_number,
                        cells=cells,
                        signature=signature,
                        error_code=error_code,
                        error_message=error_message,
                    )
                    for (
                        line_number,
                        sequence_number,
                        cells,
                        signature,
                        error_code,
                        error_message,
                    ) in (
                        (1, 1, [1, 2], "12", None, None),
                        (2, 2, [2, 1], "21", None, None),
                        (3, 2, [2, 1], "21", None, None),
                        (4, 4, [1, 2], "12", None, None),
                        (
                            5,
                            3,
                            [1, 99],
                            None,
                            "import_symbol_not_in_rules",
                            "Line 5 contains a foreign symbol.",
                        ),
                        (
                            6,
                            None,
                            None,
                            None,
                            "import_record_invalid",
                            "Line 6 is invalid.",
                        ),
                    )
                ]
            )
            session.commit()

            service = LayoutImportReportService(SqlAlchemyLayoutImportReportRepository(session))
            report = service.get_integrity_report(validation_job.id)
            page = service.list_normalized_rows(
                validation_job.id,
                after_line_number=0,
                limit=1,
                row_status=LayoutImportRowStatus.INVALID,
                error_code="import_symbol_not_in_rules",
            )

            assert report.actual_row_count == 6
            assert report.valid_row_count == 4
            assert report.invalid_row_count == 2
            assert report.missing_sequence_count == 1
            assert report.missing_sequence_numbers == (3,)
            assert report.duplicate_sequence_group_count == 1
            assert report.duplicate_sequence_affected_row_count == 2
            assert report.duplicate_sequences[0].line_numbers == (2, 3)
            assert report.duplicate_signature_group_count == 2
            assert {
                group.signature: group.sequence_numbers for group in report.duplicate_signatures
            } == {"12": (1, 4), "21": (2, 2)}
            assert report.ready_for_publication is False
            assert [(item.code, item.count) for item in report.error_code_counts] == [
                ("import_record_invalid", 1),
                ("import_symbol_not_in_rules", 1),
            ]
            assert len(page.items) == 1
            assert page.items[0].line_number == 5
            assert page.next_after_line_number is None

            with pytest.raises(JobConflictError) as publication_error:
                service.publish_dataset(validation_job.id)
            assert publication_error.value.code == "LAYOUT_IMPORT_NOT_READY_FOR_PUBLICATION"
            assert session.scalar(select(func.count()).select_from(DatasetVersionModel)) == 0

            active_validation_job = replace(
                create_job(
                    JobType.VALIDATE,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "validation_kind": "layout_import",
                        "import_job_id": str(import_job.id),
                        "rules_version_id": str(rules.id),
                    },
                ),
                input_key="active-layout-import-validation".ljust(64, "0"),
            )
            jobs.add_job(active_validation_job)
            session.commit()

            with pytest.raises(JobConflictError) as active_validation_error:
                service.reject_staging(validation_job.id)
            assert active_validation_error.value.code == "LAYOUT_IMPORT_STAGING_VALIDATION_ACTIVE"

            active_validation_model = session.get(JobModel, active_validation_job.id)
            assert active_validation_model is not None
            active_validation_model.status = JobStatus.CANCELLED
            session.commit()

            dataset = DatasetVersionModel(
                game_id=game.id,
                version=1,
                rows=1,
                columns=2,
                signature_cell_width=1,
                layout_count=4,
                status=DatasetVersionStatus.STAGING,
                generation_seed=1,
                generator_version="import-report-test",
                source_job_id=validation_job.id,
            )
            session.add(dataset)
            session.commit()

            with pytest.raises(JobConflictError) as dataset_error:
                service.reject_staging(validation_job.id)
            assert dataset_error.value.code == "LAYOUT_IMPORT_STAGING_IN_USE"

            session.delete(dataset)
            session.commit()

            rejection = service.reject_staging(validation_job.id)
            session.commit()

            assert rejection.import_job_id == import_job.id
            assert rejection.deleted_normalized_row_count == 6
            assert rejection.deleted_raw_row_count == 6
            assert (
                session.scalar(select(func.count()).select_from(LayoutImportNormalizedRowModel))
                == 0
            )
            assert session.scalar(select(func.count()).select_from(LayoutImportRowModel)) == 0

            clean_import_job = replace(
                create_job(
                    JobType.IMPORT,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "import_kind": "layout_file",
                        "source_path": "clean-report.jsonl",
                        "source_checksum": "d" * 64,
                        "source_size_bytes": 400,
                        "file_format": "jsonl",
                        "contract_version": 1,
                    },
                ),
                status=JobStatus.COMPLETED,
                progress_current=400,
                progress_total=400,
                success_count=4,
                stage="staged_import_rows",
                finished_at=now,
            )
            clean_validation_job = replace(
                create_job(
                    JobType.VALIDATE,
                    game_id=game.id,
                    input_payload={
                        "schema_version": 1,
                        "validation_kind": "layout_import",
                        "import_job_id": str(clean_import_job.id),
                        "rules_version_id": str(rules.id),
                    },
                ),
                status=JobStatus.COMPLETED,
                progress_current=4,
                progress_total=4,
                success_count=4,
                stage="validated_import_rows",
                finished_at=now,
            )
            jobs.add_job(clean_import_job)
            jobs.add_job(clean_validation_job)
            clean_rows = (
                (1, [1, 2], "12"),
                (2, [2, 1], "21"),
                (3, [1, 2], "12"),
                (4, [2, 2], "22"),
            )
            session.add_all(
                [
                    LayoutImportRowModel(
                        job_id=clean_import_job.id,
                        line_number=sequence_number,
                        byte_offset_end=sequence_number * 100,
                        sequence_number=sequence_number,
                        cells=cells,
                    )
                    for sequence_number, cells, _signature in clean_rows
                ]
            )
            session.flush()
            session.add_all(
                [
                    LayoutImportNormalizedRowModel(
                        validation_job_id=clean_validation_job.id,
                        import_job_id=clean_import_job.id,
                        rules_version_id=rules.id,
                        line_number=sequence_number,
                        sequence_number=sequence_number,
                        cells=cells,
                        signature=signature,
                    )
                    for sequence_number, cells, signature in clean_rows
                ]
            )
            session.commit()

            published = service.publish_dataset(clean_validation_job.id)
            session.commit()
            retried = service.publish_dataset(clean_validation_job.id)
            session.commit()

            assert retried.id == published.id
            assert published.status is DatasetVersionStatus.PUBLISHED
            assert published.source_job_id == clean_validation_job.id
            assert published.generator_version == "layout-import-v1"
            assert published.generation_seed == 0
            assert published.layout_count == 4
            assert published.published_at is not None
            published_layouts = tuple(
                session.scalars(
                    select(LayoutModel)
                    .where(LayoutModel.dataset_version_id == published.id)
                    .order_by(LayoutModel.sequence_number)
                )
            )
            assert [item.sequence_number for item in published_layouts] == [
                1,
                2,
                3,
                4,
            ]
            assert [item.signature for item in published_layouts] == [
                "12",
                "21",
                "12",
                "22",
            ]
            assert session.scalar(select(func.count()).select_from(DatasetVersionModel)) == 1

            with pytest.raises(JobConflictError) as published_rejection_error:
                service.reject_staging(clean_validation_job.id)
            assert published_rejection_error.value.code == "LAYOUT_IMPORT_STAGING_IN_USE"
    finally:
        engine.dispose()
