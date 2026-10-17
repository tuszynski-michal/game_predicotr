"""Grid model evaluation job and the cross-game cohort currentness bridge (TASK-0997, D-559).

Revision ID: 0166_grid_model_evaluation
Revises: 0165_grid_training_lane
Create Date: 2026-10-16

A ``currentness_notice`` row in any game partition appends one identity-only mark to a
shared watermark through a SECURITY DEFINER trigger; the application role may only read
it. Evaluation cohort proofs are append-only server records that also pin the game's
storage generation; deleting a game removes its storage location, which the barrier
reads, so its proof can never stay current. No history is backfilled: a proof compares
the watermark with the count it read itself, so only later notices matter. No report,
binding, proof or publication is created by this revision.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0166_grid_model_evaluation"
down_revision: str | Sequence[str] | None = "0165_grid_training_lane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

MARKS = "grid_model_cohort_notice_marks"
PROOFS = "grid_model_evaluation_cohort_proofs"
SHA = "~ '^[0-9a-f]{64}$'"

MARK_SQL = r"""
CREATE FUNCTION public.grid_cohort_notice_mark_v1() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$ BEGIN
 INSERT INTO public.grid_model_cohort_notice_marks(game_id,cohort_id)
 VALUES(NEW.game_id,NEW.cohort_id);
 RETURN NULL;
END $$;
REVOKE ALL ON FUNCTION public.grid_cohort_notice_mark_v1() FROM PUBLIC;
"""


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
    # As in 0165: the label is committed before anything mentions it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE job_type ADD VALUE IF NOT EXISTS 'grid_model_evaluation'")
    _guard(16)
    op.execute(f"""CREATE TABLE public.{MARKS} (
      id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,game_id uuid NOT NULL,
      cohort_id uuid NOT NULL,created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute(f"CREATE INDEX ix_{MARKS}_cohort ON public.{MARKS}(game_id,cohort_id)")
    op.execute(f"""CREATE TABLE public.{PROOFS} (
      id uuid PRIMARY KEY,report_id uuid NOT NULL
        REFERENCES public.grid_model_evaluation_reports(id) ON DELETE RESTRICT,
      game_id uuid NOT NULL,cohort_id uuid NOT NULL,
      manifest_sha256 varchar(64) NOT NULL CHECK(manifest_sha256 {SHA}),
      notice_count bigint NOT NULL CHECK(notice_count>=0),
      storage_generation integer NOT NULL CHECK(storage_generation>=1),
      bind_receipt_sha256 varchar(64) NOT NULL CHECK(bind_receipt_sha256 {SHA}),
      eligibility_sha256 varchar(64) NOT NULL CHECK(eligibility_sha256 {SHA}),
      actor varchar(64) NOT NULL CHECK(length(actor) BETWEEN 1 AND 64),
      created_at timestamptz NOT NULL DEFAULT now())""")
    op.execute(f"CREATE INDEX ix_{PROOFS}_report ON public.{PROOFS}(report_id,game_id,created_at)")
    for table in (MARKS, PROOFS):
        op.execute(
            f"CREATE TRIGGER grid_model_immutable BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.grid_model_immutable_v1()"
        )
    op.execute(MARK_SQL)
    # A row trigger on the partitioned parent is cloned to every current and future
    # game partition; only notices count, other cohort history does not.
    op.execute(
        "CREATE TRIGGER grid_cohort_notice_mark AFTER INSERT "
        "ON game_data_v2.grid_training_cohort_events FOR EACH ROW "
        "WHEN (NEW.kind='currentness_notice') "
        "EXECUTE FUNCTION public.grid_cohort_notice_mark_v1()"
    )
    # Default privileges granted DML on the new table to every application role.
    op.execute(f"REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON public.{MARKS} FROM PUBLIC")
    op.execute(f"""DO $revoke$ DECLARE grantee record; BEGIN
      FOR grantee IN SELECT DISTINCT r.rolname FROM pg_class c
      JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL aclexplode(c.relacl) a
      JOIN pg_roles r ON r.oid=a.grantee WHERE n.nspname='public' AND c.relname='{MARKS}'
      AND r.oid<>c.relowner LOOP
        EXECUTE format('REVOKE INSERT,UPDATE,DELETE,TRUNCATE ON public.{MARKS} FROM %I',
          grantee.rolname);
      END LOOP;
    END $revoke$""")
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v17',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v16'"
    )
    for table in (MARKS, PROOFS):
        op.execute(
            "INSERT INTO public.game_storage_table_manifest "
            f"VALUES('game-data-v2-manifest-v17','{table}','shared',FALSE)"
        )
    _manifest(16, 17)


def downgrade() -> None:
    # PostgreSQL cannot drop an enum label; any evaluation history blocks the downgrade.
    _guard(17)
    op.execute(f"LOCK TABLE public.{MARKS},public.{PROOFS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $history$ BEGIN
      IF EXISTS(SELECT 1 FROM public.{MARKS}) OR EXISTS(SELECT 1 FROM public.{PROOFS})
      OR EXISTS(SELECT 1 FROM public.jobs WHERE job_type::text='grid_model_evaluation')
      OR EXISTS(SELECT 1 FROM public.grid_model_evaluation_reports
        WHERE report_json::jsonb->>'schemaVersion'='grid-model-evaluation-read-v2')
        THEN RAISE EXCEPTION 'GRID_MODEL_EVALUATION_DOWNGRADE_HAS_HISTORY'; END IF;
    END $history$""")
    op.execute("DROP TRIGGER grid_cohort_notice_mark ON game_data_v2.grid_training_cohort_events")
    op.execute("DROP FUNCTION public.grid_cohort_notice_mark_v1()")
    op.execute(f"DROP TABLE public.{PROOFS}")
    op.execute(f"DROP TABLE public.{MARKS}")
    _manifest(17, 16)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v17'"
    )
