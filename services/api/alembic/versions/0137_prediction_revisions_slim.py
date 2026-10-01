"""Prediction revisions keep the pre-slimming digest (D-467 S8, TASK-0794; D-466).

Since TASK-0794 ``image_symbol_prediction_revisions.predictions[].virtualCell``
carries only checksums and keys; the full ``renderSpec`` lives in the board
render manifest.  ``scripts/slim_prediction_revisions.py`` removes it from the
existing rows and, just before that, stores the v1 digest of the full list in
the new nullable ``legacy_predictions_sha256``, so reference-library apply
manifests written before TASK-0794 (v1 digests) still recognise their
revisions (``apply`` / ``apply-revert`` anchors).

Upgrade adds the column on the partitioned parent (catalog-only, no rewrite)
and a format CHECK, validated immediately (every value is NULL; the scan
reads only the small heap, not the TOAST of ``predictions``).

Downgrade drops the column, but refuses
(``PREDICTION_REVISION_LEGACY_DIGEST_PRESENT``) once the slimming stored any
legacy digest: dropping it would orphan the v1 manifests of finished runs.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0137_prediction_revisions_slim"
down_revision: str | Sequence[str] | None = "0136_drop_cell_render_spec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REVISIONS = "game_data_v2.image_symbol_prediction_revisions"
LEGACY_CHECK = "ck_image_symbol_prediction_revisions_legacy_digest"
LEGACY_CHECK_EXPRESSION = (
    "legacy_predictions_sha256 IS NULL OR legacy_predictions_sha256 ~ '^[0-9a-f]{64}$'"
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {REVISIONS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"ALTER TABLE {REVISIONS} ADD COLUMN legacy_predictions_sha256 varchar(64)")
    op.execute(
        f"ALTER TABLE {REVISIONS} ADD CONSTRAINT {LEGACY_CHECK} "
        f"CHECK ({LEGACY_CHECK_EXPRESSION}) NOT VALID"
    )
    op.execute(f"ALTER TABLE {REVISIONS} VALIDATE CONSTRAINT {LEGACY_CHECK}")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {REVISIONS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM {REVISIONS} WHERE legacy_predictions_sha256 IS NOT NULL) THEN
            RAISE EXCEPTION 'PREDICTION_REVISION_LEGACY_DIGEST_PRESENT: slimmed prediction '
                'revisions keep the v1 digests of finished reference-library runs';
        END IF;
    END $guard$""")
    op.execute(f"ALTER TABLE {REVISIONS} DROP CONSTRAINT {LEGACY_CHECK}")
    op.execute(f"ALTER TABLE {REVISIONS} DROP COLUMN legacy_predictions_sha256")
