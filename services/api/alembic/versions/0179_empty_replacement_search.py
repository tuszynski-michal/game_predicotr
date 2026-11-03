"""Skip exclusion joins when a game has no replacement visibility fences."""

from alembic import op

revision = "0179_empty_replacement_search"
down_revision = "0178_grid_correction_growth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute(
        "ALTER FUNCTION public.source_replacement_excluded_reviews_v1(uuid) "
        "RENAME TO source_replacement_excluded_reviews_impl_v1"
    )
    op.execute("""
CREATE FUNCTION public.source_replacement_excluded_reviews_v1(g uuid)
RETURNS SETOF uuid LANGUAGE plpgsql STABLE SECURITY INVOKER
SET search_path=pg_catalog AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_retired WHERE game_id=g)
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_slots WHERE game_id=g)
 AND NOT EXISTS(SELECT 1 FROM game_data_v2.source_replacement_entries
                WHERE game_id=g AND phase='restored') THEN
  RETURN;
 END IF;
 RETURN QUERY SELECT * FROM public.source_replacement_excluded_reviews_impl_v1(g);
END;
$$;
""")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("DROP FUNCTION public.source_replacement_excluded_reviews_v1(uuid)")
    op.execute(
        "ALTER FUNCTION public.source_replacement_excluded_reviews_impl_v1(uuid) "
        "RENAME TO source_replacement_excluded_reviews_v1"
    )
