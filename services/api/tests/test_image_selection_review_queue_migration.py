from pathlib import Path


def test_review_queue_migration_adds_reversible_group_states() -> None:
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "0041_image_selection_review_queues.py"
    )
    content = path.read_text(encoding="utf-8")

    assert "rejection_origin_status" in content
    assert "'range_required', 'range_confirmed', 'skipped_unreadable'" in content
    assert "'rejected_by_user'" in content
    assert "status <> 'rejected_by_user' AND rejection_origin_status IS NULL" in content
    assert "'range_confirmed', 'rejected_group', 'restored_group'" in content
    assert "ck_image_selection_groups_rejection_origin" in content
    assert (
        'down_revision: str | Sequence[str] | None = '
        '"0040_image_selection_duplicate_range_decisions"'
    ) in content
