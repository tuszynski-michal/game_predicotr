"""Add explicit model controls, immutable evaluation references and command history.

No model is published, admitted, activated or selected as default by this revision.
Game partition definitions and payloads are unchanged. Only schema-owner execution
on a separately authorized database is supported.
"""

import sqlalchemy as sa
from alembic import op

revision = "0157_grid_model_publication"
down_revision = "0156_grid_model_registry"
branch_labels = depends_on = None
V9, V10 = "game-data-v2-manifest-v9", "game-data-v2-manifest-v10"
SHARED = (
    "grid_model_evaluation_reports",
    "grid_model_evaluation_invalidations",
    "grid_model_publications",
    "grid_model_control_events",
    "grid_model_default",
)


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <> 'done')
        THEN RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations WHERE manifest_version <> '{V9}'
          OR store_schema <> 'game_data_v2')
        THEN RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")
    statements = (
        """CREATE TABLE public.grid_model_evaluation_reports (
id UUID PRIMARY KEY, version_id UUID NOT NULL REFERENCES public.grid_model_versions(id)
ON DELETE RESTRICT, producer VARCHAR(64) NOT NULL, report_json TEXT NOT NULL,
report_sha256 VARCHAR(64) NOT NULL CHECK(report_sha256 ~ '^[0-9a-f]{64}$'),
created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE public.grid_model_evaluation_invalidations (
id UUID PRIMARY KEY, report_id UUID NOT NULL REFERENCES public.grid_model_evaluation_reports(id)
ON DELETE RESTRICT, reason TEXT NOT NULL, actor VARCHAR(64) NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE INDEX ix_grid_model_evaluation_invalidations_report_id
ON public.grid_model_evaluation_invalidations(report_id)""",
        """CREATE TABLE public.grid_model_publications (
version_id UUID PRIMARY KEY REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT,
evaluation_id UUID REFERENCES public.grid_model_evaluation_reports(id) ON DELETE RESTRICT,
evidence_json TEXT NOT NULL, evidence_sha256 VARCHAR(64) NOT NULL
CHECK(evidence_sha256 ~ '^[0-9a-f]{64}$'), created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE TABLE public.grid_model_control_events (
idempotency_key UUID PRIMARY KEY, version_id UUID NOT NULL REFERENCES public.grid_model_versions(id)
ON DELETE RESTRICT, kind VARCHAR(32) NOT NULL CHECK(kind IN ('publish','set_default')),
revision INTEGER NOT NULL CHECK(revision>0), expected_revision INTEGER NOT NULL
CHECK(expected_revision>=0 AND revision=expected_revision+1), command_sha256 VARCHAR(64)
NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{64}$'), command_json TEXT NOT NULL,
receipt_json TEXT NOT NULL, actor VARCHAR(64) NOT NULL, evidence_sha256 VARCHAR(64)
NOT NULL CHECK(evidence_sha256 ~ '^[0-9a-f]{64}$'),
created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
        """CREATE UNIQUE INDEX uq_grid_model_control_default_revision
ON public.grid_model_control_events(revision) WHERE kind='set_default'""",
        """CREATE UNIQUE INDEX uq_grid_model_control_publication
ON public.grid_model_control_events(version_id) WHERE kind='publish'""",
        """CREATE TABLE public.grid_model_default (
id VARCHAR(32) PRIMARY KEY CHECK(id='geometry-v3'), version_id UUID NOT NULL
REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT,
revision INTEGER NOT NULL CHECK(revision>0))""",
    )
    for statement in statements:
        op.execute(statement)
    for name, type_ in (
        ("expected_revision", sa.Integer()),
        ("command_sha256", sa.String(64)),
        ("command_json", sa.Text()),
        ("receipt_json", sa.Text()),
        ("actor", sa.String(64)),
        ("evidence_sha256", sa.String(64)),
    ):
        op.add_column("game_grid_model_assignment_events", sa.Column(name, type_), schema="public")
    op.drop_constraint(
        "game_grid_model_assignment_events_kind_check",
        "game_grid_model_assignment_events",
        schema="public",
    )
    op.create_check_constraint(
        "ck_grid_assignment_event_command",
        "game_grid_model_assignment_events",
        "kind='historical_assignment' OR (kind IN ('activate','rollback') AND "
        "expected_revision IS NOT NULL AND expected_revision>=0 AND revision=expected_revision+1 "
        "AND command_sha256 IS NOT NULL AND command_sha256 ~ '^[0-9a-f]{64}$' "
        "AND command_json IS NOT NULL AND receipt_json IS NOT NULL AND actor IS NOT NULL "
        "AND evidence_sha256 IS NOT NULL AND evidence_sha256 ~ '^[0-9a-f]{64}$')",
        schema="public",
    )
    op.create_unique_constraint(
        "uq_grid_assignment_event_revision",
        "game_grid_model_assignment_events",
        ["game_id", "revision"],
        schema="public",
    )
    for table in SHARED:
        if table != "grid_model_default":
            op.execute(
                f"CREATE TRIGGER grid_model_immutable BEFORE UPDATE OR DELETE ON public.{table} "
                "FOR EACH ROW EXECUTE FUNCTION public.grid_model_immutable_v1()"
            )
    # Shared control reports can contain game IDs for coverage, never game data.
    op.execute(
        f"INSERT INTO public.game_storage_table_manifest SELECT '{V10}',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        f"WHERE manifest_version='{V9}'"
    )
    for table in SHARED:
        op.get_bind().execute(
            sa.text("""INSERT INTO
public.game_storage_table_manifest(manifest_version,table_name,ownership,partitioned)
VALUES(:version,:table,'shared',FALSE)"""),
            {"version": V10, "table": table},
        )
    op.drop_constraint(
        "ck_game_storage_locations_manifest_version_v9", "game_storage_locations", schema="public"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version='{V10}',"
        f"revision=revision+1,updated_at=now() WHERE manifest_version='{V9}'"
    )
    op.create_check_constraint(
        "ck_game_storage_locations_manifest_version_v10",
        "game_storage_locations",
        f"manifest_version='{V10}'",
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError(
        "GRID_MODEL_PUBLICATION_DOWNGRADE_REFUSED: immutable control history must remain"
    )
