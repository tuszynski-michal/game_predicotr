from pathlib import Path


def test_grid_calibration_migration_has_immutable_registry_tables() -> None:
    path = Path(__file__).parents[1] / "alembic" / "versions" / "0039_grid_calibration_profiles.py"
    content = path.read_text(encoding="utf-8")

    assert '"grid_geometry_cohorts"' in content
    assert '"grid_calibration_profiles"' in content
    assert '"game_grid_profile_activations"' in content
    assert "uq_grid_geometry_cohorts_manifest" in content
    assert "uq_grid_calibration_profiles_cohort" in content
    assert "uq_game_grid_profile_activations_idempotency" in content
    assert (
        'down_revision: str | Sequence[str] | None = "0038_curated_image_import_batches"' in content
    )
