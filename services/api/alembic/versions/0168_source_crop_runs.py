"""Durable crop and original-deletion runs for managed originals (TASK-1047, D-562).

Revision ID: 0168_source_crop_runs
Revises: 0167_source_image_crops
Create Date: 2026-10-17

Adds the job types ``source_crop`` and ``source_original_deletion`` and the shared
table ``public.source_crop_runs`` (manifest v19). A run is planned by a worker
job, reviewed through an immutable manifest and token, and only then executed by
a second job. The table holds counters, paths and checksums; no image bytes and no
game payload. No run is created by this revision.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0168_source_crop_runs"
down_revision: str | Sequence[str] | None = "0167_source_image_crops"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "source_crop_runs"
SHA = "~ '^[0-9a-f]{64}$'"


def _guard(version: int) -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='30s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
      IF EXISTS(SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status<>'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
      IF EXISTS(SELECT 1 FROM public.game_storage_locations WHERE
        manifest_version<>'game-data-v2-manifest-v{version}' OR store_schema<>'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")


def _manifest(previous: int, current: int) -> None:
    op.execute(
        "ALTER TABLE public.game_storage_locations DROP CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{previous}"
    )
    op.execute(
        "UPDATE public.game_storage_locations SET "
        f"manifest_version='game-data-v2-manifest-v{current}',revision=revision+1,updated_at=now()"
    )
    op.execute(
        "ALTER TABLE public.game_storage_locations ADD CONSTRAINT "
        f"ck_game_storage_locations_manifest_version_v{current} "
        f"CHECK(manifest_version='game-data-v2-manifest-v{current}')"
    )


def upgrade() -> None:
    # As in 0165/0166: enum labels are committed before anything mentions them.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'source_crop'")
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'source_original_deletion'")
    _guard(18)
    op.execute(f"""CREATE TABLE public.{TABLE} (
      id uuid PRIMARY KEY,
      kind varchar(24) NOT NULL CHECK(kind IN ('crop','original_deletion')),
      status varchar(16) NOT NULL CHECK(status IN
        ('planning','previewed','created','processing','completed','failed','cancelled')),
      scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
      plan_job_id uuid NOT NULL REFERENCES public.jobs(id) ON DELETE RESTRICT,
      job_id uuid REFERENCES public.jobs(id) ON DELETE RESTRICT,
      manifest_relative_path varchar(1000),
      manifest_checksum_sha256 varchar(64) CHECK(manifest_checksum_sha256 {SHA}),
      preview_token varchar(64) CHECK(preview_token {SHA}),
      eligible_count integer NOT NULL DEFAULT 0 CHECK(eligible_count>=0),
      excluded_count integer NOT NULL DEFAULT 0 CHECK(excluded_count>=0),
      exclusion_counts jsonb NOT NULL DEFAULT '{{}}'::jsonb
        CHECK(jsonb_typeof(exclusion_counts)='object'),
      candidate_bytes bigint NOT NULL DEFAULT 0 CHECK(candidate_bytes>=0),
      estimated_saved_bytes bigint NOT NULL DEFAULT 0 CHECK(estimated_saved_bytes>=0),
      processed_count integer NOT NULL DEFAULT 0 CHECK(processed_count>=0),
      succeeded_count integer NOT NULL DEFAULT 0 CHECK(succeeded_count>=0),
      skipped_count integer NOT NULL DEFAULT 0 CHECK(skipped_count>=0),
      failed_count integer NOT NULL DEFAULT 0 CHECK(failed_count>=0),
      saved_bytes bigint NOT NULL DEFAULT 0 CHECK(saved_bytes>=0),
      checkpoint_index integer NOT NULL DEFAULT 0 CHECK(checkpoint_index>=0),
      outcome_counts jsonb NOT NULL DEFAULT '{{}}'::jsonb
        CHECK(jsonb_typeof(outcome_counts)='object'),
      failures jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK(jsonb_typeof(failures)='array' AND jsonb_array_length(failures)<=100),
      error_code varchar(100),
      error_message text,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now(),
      started_at timestamptz,
      finished_at timestamptz,
      CONSTRAINT ck_{TABLE}_preview CHECK(
        (status='planning' AND manifest_checksum_sha256 IS NULL AND preview_token IS NULL
          AND job_id IS NULL)
        OR (status<>'planning' AND status<>'failed' AND status<>'cancelled'
          AND manifest_relative_path IS NOT NULL
          AND manifest_checksum_sha256 IS NOT NULL AND preview_token IS NOT NULL)
        OR status IN ('failed','cancelled')),
      CONSTRAINT ck_{TABLE}_execution CHECK(
        status NOT IN ('created','processing','completed') OR job_id IS NOT NULL),
      CONSTRAINT ck_{TABLE}_progress CHECK(
        processed_count=succeeded_count+skipped_count+failed_count
        AND checkpoint_index>=processed_count))""")
    # At most one run is planned, previewed or executing at any time.
    op.execute(
        f"CREATE UNIQUE INDEX uq_{TABLE}_active ON public.{TABLE}((true)) "
        "WHERE status IN ('planning','previewed','created','processing')"
    )
    op.execute(f"CREATE INDEX ix_{TABLE}_created ON public.{TABLE}(created_at)")
    # The API writes runs on the application role. Owner default privileges cover
    # current installations; copy the ACL of public.storage_gc_runs (the same kind
    # of run table) for earlier ones, as 0159 does. Never create cluster roles.
    op.execute(f"""DO $grants$ DECLARE grant_row record; BEGIN
        FOR grant_row IN
            SELECT DISTINCT r.rolname,a.privilege_type FROM pg_class c
            JOIN pg_namespace n ON n.oid=c.relnamespace
            CROSS JOIN LATERAL aclexplode(c.relacl) a
            JOIN pg_roles r ON r.oid=a.grantee
            WHERE n.nspname='public' AND c.relname='storage_gc_runs'
              AND a.privilege_type IN ('SELECT','INSERT','UPDATE','DELETE')
              AND NOT r.rolsuper AND NOT r.rolbypassrls AND r.oid <> c.relowner
        LOOP
            EXECUTE format('GRANT %s ON public.{TABLE} TO %I',
                grant_row.privilege_type,grant_row.rolname);
        END LOOP;
    END $grants$""")
    # TASK-1048: the deletion job that removed an original, so a restart after
    # the state write and before the run checkpoint counts it exactly once.
    op.execute(
        "ALTER TABLE public.source_image_crops ADD COLUMN deletion_job_id uuid "
        "REFERENCES public.jobs(id) ON DELETE RESTRICT"
    )
    op.execute(
        "ALTER TABLE public.source_image_crops ADD CONSTRAINT "
        "ck_source_image_crops_deletion_job CHECK(state='original_deleted' "
        "OR deletion_job_id IS NULL)"
    )
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v19',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v18'"
    )
    op.execute(
        "INSERT INTO public.game_storage_table_manifest "
        f"VALUES('game-data-v2-manifest-v19','{TABLE}','shared',FALSE)"
    )
    _manifest(18, 19)


def downgrade() -> None:
    # PostgreSQL cannot drop an enum label; any run or job history blocks the downgrade.
    _guard(19)
    op.execute(f"LOCK TABLE public.{TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $history$ BEGIN
      IF EXISTS(SELECT 1 FROM public.{TABLE})
      OR EXISTS(SELECT 1 FROM public.jobs
        WHERE job_type::text IN ('source_crop','source_original_deletion'))
        THEN RAISE EXCEPTION 'SOURCE_CROP_RUNS_DOWNGRADE_HAS_HISTORY'; END IF;
    END $history$""")
    op.execute(f"DROP TABLE public.{TABLE}")
    op.execute("ALTER TABLE public.source_image_crops DROP COLUMN deletion_job_id")
    _manifest(19, 18)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v19'"
    )
