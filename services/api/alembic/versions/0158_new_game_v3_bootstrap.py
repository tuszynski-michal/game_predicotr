"""Reserve new V3 games atomically with transfer provenance and family lineage.

No game, assignment, publication or default is created by this migration.
"""

import sqlalchemy as sa
from alembic import op

revision = "0158_new_game_v3_bootstrap"
down_revision = "0157_grid_model_publication"
branch_labels = depends_on = None
V10, V11 = "game-data-v2-manifest-v10", "game-data-v2-manifest-v11"


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <> 'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations WHERE manifest_version <> '{V10}'
          OR store_schema <> 'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")
    op.execute("""CREATE TABLE public.game_create_receipts (
idempotency_key UUID PRIMARY KEY, game_id UUID UNIQUE NOT NULL,
command_json TEXT NOT NULL, command_sha256 VARCHAR(64) NOT NULL
CHECK(command_sha256 ~ '^[0-9a-f]{64}$'), reservation_json TEXT NOT NULL,
reservation_sha256 VARCHAR(64) NOT NULL CHECK(reservation_sha256 ~ '^[0-9a-f]{64}$'),
actor VARCHAR(64) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.execute("""CREATE TABLE public.grid_model_family_forks (
family_id UUID PRIMARY KEY REFERENCES public.grid_model_families(id) ON DELETE RESTRICT,
base_version_id UUID NOT NULL REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT,
base_manifest_sha256 VARCHAR(64) NOT NULL CHECK(base_manifest_sha256 ~ '^[0-9a-f]{64}$'),
lineage_json TEXT NOT NULL, lineage_sha256 VARCHAR(64) NOT NULL
CHECK(lineage_sha256 ~ '^[0-9a-f]{64}$'), actor VARCHAR(64) NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")
    op.add_column(
        "game_grid_model_assignments",
        sa.Column(
            "training_family_id",
            sa.Uuid(),
            sa.ForeignKey("public.grid_model_families.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        schema="public",
    )
    op.drop_constraint(
        "ck_grid_assignment_event_command", "game_grid_model_assignment_events", schema="public"
    )
    op.create_check_constraint(
        "ck_grid_assignment_event_command",
        "game_grid_model_assignment_events",
        "kind='historical_assignment' OR (kind IN ('activate','rollback','bootstrap') AND "
        "expected_revision IS NOT NULL AND expected_revision>=0 AND revision=expected_revision+1 "
        "AND command_sha256 IS NOT NULL AND command_sha256 ~ '^[0-9a-f]{64}$' "
        "AND command_json IS NOT NULL AND receipt_json IS NOT NULL AND actor IS NOT NULL "
        "AND evidence_sha256 IS NOT NULL AND evidence_sha256 ~ '^[0-9a-f]{64}$' "
        "AND (kind<>'bootstrap' OR expected_revision=0))",
        schema="public",
    )
    for table in ("game_create_receipts", "grid_model_family_forks"):
        op.execute(
            f"CREATE TRIGGER grid_model_immutable BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.grid_model_immutable_v1()"
        )
    op.execute(f"""INSERT INTO public.game_storage_table_manifest
SELECT '{V11}',table_name,ownership,partitioned FROM public.game_storage_table_manifest
WHERE manifest_version='{V10}'""")
    for table, ownership in (
        ("game_create_receipts", "catalog"),
        ("grid_model_family_forks", "shared"),
    ):
        op.get_bind().execute(
            sa.text("""INSERT INTO
public.game_storage_table_manifest(manifest_version,table_name,ownership,partitioned)
VALUES(:version,:table,:ownership,FALSE)"""),
            {"version": V11, "table": table, "ownership": ownership},
        )
    op.drop_constraint(
        "ck_game_storage_locations_manifest_version_v10", "game_storage_locations", schema="public"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version='{V11}',"
        f"revision=revision+1,updated_at=now() WHERE manifest_version='{V10}'"
    )
    op.create_check_constraint(
        "ck_game_storage_locations_manifest_version_v11",
        "game_storage_locations",
        f"manifest_version='{V11}'",
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError("GAME_CREATE_DOWNGRADE_REFUSED: immutable creation history must remain")
