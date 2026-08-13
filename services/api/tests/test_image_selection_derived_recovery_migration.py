from pathlib import Path


def test_derived_recovery_migration_is_reversible_and_keeps_full_identity() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0042_image_selection_derived_recovery.py"
    )
    content = path.read_text(encoding="utf-8")

    assert "execution_mode" in content
    assert "source_run_id" in content
    assert "source_snapshot_sha256" in content
    assert "origin_group_id" in content
    assert "uq_image_selection_runs_full_identity" in content
    assert "uq_image_selection_runs_recovery_identity" in content
    assert "execution_mode = 'full'" in content
    assert "execution_mode = 'range_recovery'" in content
    assert "DELETE FROM image_selection_runs" in content
    assert (
        'down_revision: str | Sequence[str] | None = '
        '"0041_image_selection_review_queues"'
    ) in content
