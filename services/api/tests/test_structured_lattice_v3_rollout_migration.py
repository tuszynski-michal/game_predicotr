from pathlib import Path


def test_structured_lattice_v3_rollout_migration_is_reversible() -> None:
    path = (
        Path(__file__).parents[1] / "alembic" / "versions" / "0095_structured_lattice_v3_rollout.py"
    )
    content = path.read_text(encoding="utf-8")

    assert (
        'down_revision: str | Sequence[str] | None = "0094_grid_profile_gate_revisions"' in content
    )
    assert "'structured_lattice_v3'" in content
    assert "SET geometry_mode = 'structured_default'" in content
    assert content.count("ck_image_geometry_rollout_states_geometry_mode") == 4
