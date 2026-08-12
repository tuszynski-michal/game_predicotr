from pathlib import Path


def test_curated_image_import_migration_has_cursor_and_non_overlapping_batches() -> None:
    path = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0038_curated_image_import_batches.py"
    )
    content = path.read_text(encoding="utf-8")

    assert '"curated_image_import_sources"' in content
    assert '"curated_image_import_batches"' in content
    assert "ck_curated_image_import_sources_cursor" in content
    assert "uq_curated_image_import_sources_selection_run" in content
    assert "uq_curated_image_import_batches_number" in content
    assert "uq_curated_image_import_batches_start" in content
    assert "uq_curated_image_import_batches_job" in content
    assert 'down_revision: str | Sequence[str] | None = "0037_symbol_model_registry"' in content
