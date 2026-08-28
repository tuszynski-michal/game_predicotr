from pathlib import Path

MIGRATION = (
    Path(__file__).parents[1]
    / "alembic"
    / "versions"
    / "0075_remove_obsolete_board_search_storage.py"
)


def test_cleanup_migration_removes_only_rebuildable_legacy_storage() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str | Sequence[str] | None = "0074_unknown_layout_cells"' in source
    assert 'op.drop_table("image_board_search_documents")' in source
    assert 'op.drop_column("image_symbol_review_cells", "has_grid_issue")' in source
    assert "UPDATE image_symbol_review_cells SET quality_issue = 'grid_issue'" in source
    assert "image_board_search_fast_documents" in source
    assert "image_board_search_candidates" in source
    assert "VACUUM FULL" not in source


def test_cleanup_downgrade_restores_structure_and_deterministic_data() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert 'op.create_table(\n        "image_board_search_documents"' in source
    assert "_primary_token_rebuild_sql" in source
    assert "_alternative_token_rebuild_sql" in source
    assert "INSERT INTO image_board_search_documents" in source
    assert "alternative.alternative_rank = {rank}" in source
    assert "image_sequence_canonical" in source
    assert "previous_has_grid_issue = (previous_quality_issue = 'grid_issue')" in source
