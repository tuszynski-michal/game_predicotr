from __future__ import annotations

import importlib.util
from pathlib import Path

from game_predictor_api.domain.jobs import JobType
from game_predictor_api.storage.models import (
    FilenameRangeVerificationReviewModel,
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MIGRATION_PATH = (
    REPOSITORY_ROOT
    / "services"
    / "api"
    / "alembic"
    / "versions"
    / "0087_semi_automatic_image_selection.py"
)


def test_migration_0087_is_additive_and_has_a_bounded_downgrade() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "0086_partial_page_geometry_overrides" in source
    assert "autocommit_block" in source
    assert "semi_automatic_image_selection_runs" in source
    assert "semi_automatic_image_selection_ranges" in source
    assert 'ondelete="CASCADE"' in source
    assert 'op.drop_table("semi_automatic_image_selection_ranges")' in source
    assert 'op.drop_table("semi_automatic_image_selection_runs")' in source
    assert "DROP TYPE job_type" not in source


def test_migration_module_can_be_loaded_without_executing_ddl() -> None:
    spec = importlib.util.spec_from_file_location("migration_0087", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "0087_semi_automatic_image_selection"
    assert module.down_revision == "0086_partial_page_geometry_overrides"


def test_orm_and_job_contract_expose_global_run_tables() -> None:
    assert JobType.SEMI_AUTOMATIC_IMAGE_SELECTION.value == "semi_automatic_image_selection"
    assert SemiAutomaticImageSelectionRunModel.__tablename__ == (
        "semi_automatic_image_selection_runs"
    )
    assert SemiAutomaticImageSelectionRangeModel.__tablename__ == (
        "semi_automatic_image_selection_ranges"
    )


def test_migration_0091_adds_filename_verification_history_without_changing_job_type() -> None:
    path = (
        REPOSITORY_ROOT
        / "services"
        / "api"
        / "alembic"
        / "versions"
        / "0091_filename_range_verification_history.py"
    )
    source = path.read_text(encoding="utf-8")

    assert "0090_symbol_reference_individual_cell_provenance" in source
    assert "workflow_mode" in source
    assert "filename_verification" in source
    assert "semi_automatic_filename_verification_reviews" in source
    assert "JobType" not in source
    assert FilenameRangeVerificationReviewModel.__tablename__ == (
        "semi_automatic_filename_verification_reviews"
    )
