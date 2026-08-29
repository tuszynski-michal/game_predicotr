"""Allow server-digested terminal pipeline manifests.

Revision ID: 0081_pipeline_terminal_manifest_v2
Revises: 0080_pipeline_state_digest
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0081_pipeline_terminal_manifest_v2"
down_revision: str | Sequence[str] | None = "0080_pipeline_state_digest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_image_pipeline_terminal_manifest_schema",
        "image_pipeline_terminal_manifests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_pipeline_terminal_manifest_schema",
        "image_pipeline_terminal_manifests",
        "schema_version IN (1, 2)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_image_pipeline_terminal_manifest_schema",
        "image_pipeline_terminal_manifests",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_pipeline_terminal_manifest_schema",
        "image_pipeline_terminal_manifests",
        "schema_version = 1",
    )
