"""Equality lookup of cohort membership for the currentness trigger (TASK-1191, D-605)."""

from game_predictor_api.storage.grid_cohort_member_refs_migration import downgrade, upgrade

revision = "0186_grid_cohort_member_refs"
down_revision = "0185_grid_gate_noise_tolerance"
branch_labels = depends_on = None

__all__ = ["downgrade", "upgrade"]
