"""Keep orphan working reviews excluded after active reservations are released."""

from alembic import op
from sqlalchemy import text

revision = "0176_source_replacement_closed"
down_revision = "0175_source_replacement_guards"
branch_labels = None
depends_on = None

CURRENT_SQL = """
CREATE OR REPLACE FUNCTION public.source_replacement_current_v1(
g uuid,s uuid,h text,n bigint,i uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 SELECT public.source_replacement_source_current_v1(g,s,h)
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s AND p.state='reserved')
 AND (NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s)
 OR EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots p
 WHERE p.game_id=g AND p.new_source_id=s AND p.sequence_number=n AND p.bound_review_id=i))
 AND NOT EXISTS(
 SELECT 1 FROM game_data_v2.source_replacement_slots r WHERE r.game_id=g
 AND r.sequence_number=n AND NOT COALESCE(r.state='pending_bound'
 AND r.new_source_id=s AND r.new_sha256=h AND r.bound_review_id=i,false))
 /* closed-admission-fence */
$$;
"""

EXCLUDED_SQL = """
CREATE OR REPLACE FUNCTION public.source_replacement_excluded_reviews_v1(g uuid)
RETURNS SETOF uuid LANGUAGE sql STABLE SECURITY INVOKER SET search_path=pg_catalog AS $$
 WITH affected_sources AS (
 SELECT r.source_id AS id FROM game_data_v2.source_replacement_retired r WHERE r.game_id=g
 UNION SELECT s.id FROM game_data_v2.source_replacement_retired r
 JOIN game_data_v2.source_images s ON s.game_id=r.game_id AND s.checksum_sha256=r.source_sha256
 WHERE r.game_id=g
 UNION SELECT p.new_source_id FROM game_data_v2.source_replacement_slots p WHERE p.game_id=g
 UNION SELECT s.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.source_images s ON s.game_id=p.game_id AND s.checksum_sha256=p.new_sha256
 WHERE p.game_id=g AND p.state='reserved'
 /* closed-admission-sources */
 ), affected_reviews AS (
 SELECT i.id FROM affected_sources a JOIN game_data_v2.recognized_boards b
 ON b.game_id=g AND b.source_image_id=a.id
 JOIN game_data_v2.image_review_items i ON i.game_id=g AND i.recognized_board_id=b.id
 UNION SELECT i.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.image_review_items i ON i.game_id=p.game_id
 AND i.sequence_number=p.sequence_number WHERE p.game_id=g
 UNION SELECT i.id FROM game_data_v2.source_replacement_slots p
 JOIN game_data_v2.recognized_boards b ON b.game_id=p.game_id
 AND b.sequence_number=p.sequence_number
 JOIN game_data_v2.image_review_items i ON i.game_id=g AND i.recognized_board_id=b.id
 WHERE p.game_id=g AND i.sequence_number IS NULL
 )
 SELECT i.id FROM affected_reviews a JOIN game_data_v2.image_review_items i ON i.id=a.id
 JOIN game_data_v2.recognized_boards b ON b.game_id=i.game_id AND b.id=i.recognized_board_id
 JOIN game_data_v2.source_images s ON s.game_id=b.game_id AND s.id=b.source_image_id
 WHERE i.game_id=g
 AND NOT public.source_replacement_current_v1(g,s.id,s.checksum_sha256,
 COALESCE(i.sequence_number,b.sequence_number),i.id)
$$;
"""


def upgrade() -> None:
    op.execute(
        "CREATE INDEX source_replacement_entries_closed_source_idx ON "
        "game_data_v2.source_replacement_entries(game_id, "
        "(document #>> '{replacementAdmission,sourceId}')) WHERE phase='restored'"
    )
    op.execute(
        CURRENT_SQL.replace(
            "/* closed-admission-fence */",
            """
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_entries e
 WHERE e.game_id=g AND e.phase='restored'
 AND e.document #>> '{replacementAdmission,sourceId}'=s::text
 AND NOT (COALESCE((e.document #> '{restoration,canonicalReviewIds}')
 @> jsonb_build_array(i::text),false)
 AND EXISTS(SELECT 1 FROM game_data_v2.source_images src WHERE src.game_id=g AND src.id=s
 AND src.import_job_id::text=e.document #>> '{replacementAdmission,importJobId}')))
""",
        )
    )
    op.execute(
        EXCLUDED_SQL.replace(
            "/* closed-admission-sources */",
            """
 UNION SELECT s.id FROM game_data_v2.source_replacement_entries e
 JOIN game_data_v2.source_images s ON s.game_id=e.game_id
 AND s.id=(e.document #>> '{replacementAdmission,sourceId}')::uuid
 WHERE e.game_id=g AND e.phase='restored'
""",
        )
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        text(
            "SELECT EXISTS(SELECT 1 FROM "
            "game_data_v2.source_replacement_entries WHERE phase='restored')"
        )
    ):
        raise RuntimeError("SOURCE_REPLACEMENT_RESTORED_DOWNGRADE_BLOCKED")
    op.execute(CURRENT_SQL)
    op.execute(EXCLUDED_SQL)
    op.execute("DROP INDEX game_data_v2.source_replacement_entries_closed_source_idx")
