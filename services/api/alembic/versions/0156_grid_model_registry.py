"""Add immutable public geometry catalogue; preserve all game data and formats.

Historical descriptors below are frozen migration data, not a live registry import.
"""

import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision = "0156_grid_model_registry"
down_revision = "0155_historical_grid_acceptance"
branch_labels = depends_on = None
V8, V9 = "game-data-v2-manifest-v8", "game-data-v2-manifest-v9"
BASELINES_PATH = Path(__file__).resolve().parents[1] / "data/grid_model_baselines_v1.json"
BASELINES = json.loads(BASELINES_PATH.read_text(encoding="utf-8"))
BASELINES_CANONICAL = json.dumps(
    BASELINES, ensure_ascii=True, sort_keys=True, separators=(",", ":")
)
if hashlib.sha256(BASELINES_CANONICAL.encode("utf-8")).hexdigest() != (
    "e0816dfc9aff709eb1529306da45443393df5e62fa6ed7618076a49ee6aad76d"
):
    raise RuntimeError("GRID_MODEL_BASELINES_CORRUPT")

_NAMESPACE = UUID("1ab40b36-a4a2-4a30-a80d-f3ef16f2bbcc")


def _canonical(payload: object) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout='5s'")
    op.execute("SET LOCAL statement_timeout='120s'")
    op.execute("LOCK TABLE public.game_storage_locations IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$ BEGIN
        IF EXISTS (SELECT 1 FROM public.game_storage_lifecycle_operations WHERE status <> 'done')
        THEN
            RAISE EXCEPTION 'GAME_STORAGE_LIFECYCLE_IN_PROGRESS'; END IF;
        IF EXISTS (SELECT 1 FROM public.game_storage_locations WHERE manifest_version <> '{V8}'
            OR store_schema <> 'game_data_v2') THEN
            RAISE EXCEPTION 'GAME_STORAGE_MANIFEST_UNEXPECTED'; END IF;
    END $guard$""")
    op.drop_constraint("ck_games_shape_geometry_configuration", "games", schema="public")
    op.create_check_constraint(
        "ck_games_shape_geometry_configuration",
        "games",
        "shape_geometry_configuration IS NULL OR shape_geometry_configuration IN "
        "('framed_full_page_v2', 'requires_clarification', 'grid_profile_777_v2', "
        "'grid_profile_mumie_v1', 'neural_grid_v3')",
        schema="public",
    )
    statements = (
        """CREATE TABLE public.grid_model_families (id UUID PRIMARY KEY, code VARCHAR(64) NOT NULL
UNIQUE CHECK(code ~ '^[a-z][a-z0-9_]{0,63}$'), descriptor_json TEXT NOT NULL)""",
        """CREATE TABLE public.grid_model_versions (id UUID PRIMARY KEY, family_id UUID NOT NULL
REFERENCES public.grid_model_families(id) ON DELETE RESTRICT, version VARCHAR(64) NOT
NULL, base_version_id UUID REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT
CHECK(base_version_id <> id), manifest_json TEXT NOT NULL, manifest_sha256 VARCHAR(64)
NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'), created_at TIMESTAMPTZ NOT NULL
DEFAULT now(), UNIQUE(family_id,version))""",
        """CREATE TABLE public.grid_model_registration_receipts (idempotency_key UUID PRIMARY KEY,
command_sha256 VARCHAR(64) NOT NULL CHECK(command_sha256 ~ '^[0-9a-f]{64}$'), version_id
UUID NOT NULL REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT)""",
        """CREATE TABLE public.grid_model_version_events (id UUID PRIMARY KEY, version_id UUID NOT
NULL REFERENCES public.grid_model_versions(id) ON DELETE RESTRICT, kind VARCHAR(64) NOT
NULL CHECK(kind IN ('registered','historical_registration')), created_at TIMESTAMPTZ NOT
NULL DEFAULT now(), UNIQUE(version_id,kind))""",
        """CREATE TABLE public.game_grid_model_assignments (game_id UUID PRIMARY KEY REFERENCES
public.games(id) ON DELETE CASCADE, version_id UUID NOT NULL REFERENCES
public.grid_model_versions(id) ON DELETE RESTRICT, revision INTEGER NOT NULL
CHECK(revision>0), UNIQUE(game_id,revision))""",
        """CREATE TABLE public.game_grid_model_assignment_events (game_id UUID NOT NULL REFERENCES
public.game_grid_model_assignments(game_id) ON DELETE CASCADE, id UUID NOT NULL,
idempotency_key UUID NOT NULL, version_id UUID NOT NULL REFERENCES
public.grid_model_versions(id) ON DELETE RESTRICT, revision INTEGER NOT NULL
CHECK(revision>0), kind VARCHAR(64) NOT NULL CHECK(kind='historical_assignment'),
created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(game_id,id),
UNIQUE(game_id,idempotency_key))""",
    )
    for statement in statements:
        op.execute(statement)
    connection = op.get_bind()
    for payload in BASELINES:
        identity = {
            key: payload[key] for key in ("familyCode", "familyLabel", "topology", "capabilities")
        }
        canonical = _canonical(payload)
        checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        parameters = {
            "family": UUID(payload["familyId"]),
            "code": payload["familyCode"],
            "descriptor": _canonical(identity),
            "version_id": UUID(payload["versionId"]),
            "version": payload["version"],
            "manifest": canonical,
            "checksum": checksum,
        }
        connection.execute(
            sa.text("""INSERT INTO public.grid_model_families(id,code,descriptor_json)
VALUES(:family,:code,:descriptor)"""),
            parameters,
        )
        connection.execute(
            sa.text("""INSERT INTO
public.grid_model_versions(id,family_id,version,manifest_json,manifest_sha256)
VALUES(:version_id,:family,:version,:manifest,:checksum)"""),
            parameters,
        )
        parameters["key"] = uuid5(_NAMESPACE, payload["familyCode"] + ":historical-registration")
        connection.execute(
            sa.text("""INSERT INTO
public.grid_model_registration_receipts(idempotency_key,command_sha256,version_id)
VALUES(:key,:checksum,:version_id)"""),
            parameters,
        )
        connection.execute(
            sa.text("""INSERT INTO public.grid_model_version_events(id,version_id,kind)
VALUES(:key,:version_id,'historical_registration')"""),
            parameters,
        )
        connection.execute(
            sa.text("""INSERT INTO public.game_grid_model_assignments(game_id,version_id,revision)
SELECT
id,:version_id,1 FROM public.games WHERE shape_geometry_configuration=:code AND code <>
'7'"""),
            parameters,
        )
    op.execute("""INSERT INTO
public.game_grid_model_assignment_events(game_id,id,idempotency_key,version_id,revision,kind)
SELECT game_id,game_id,game_id,version_id,revision,'historical_assignment' FROM
public.game_grid_model_assignments""")
    op.execute("""CREATE FUNCTION public.grid_model_immutable_v1() RETURNS trigger LANGUAGE plpgsql
AS $body$ BEGIN
        IF TG_OP='DELETE' AND TG_TABLE_NAME='game_grid_model_assignment_events' THEN
            IF NOT EXISTS(SELECT 1 FROM public.games WHERE id=OLD.game_id) THEN RETURN OLD; END IF;
        END IF;
        RAISE EXCEPTION 'GRID_MODEL_IMMUTABLE';
    END $body$""")
    for table in (
        "grid_model_families",
        "grid_model_versions",
        "grid_model_registration_receipts",
        "grid_model_version_events",
        "game_grid_model_assignment_events",
    ):
        op.execute(
            f"CREATE TRIGGER grid_model_immutable BEFORE UPDATE OR DELETE ON public.{table} "
            "FOR EACH ROW EXECUTE FUNCTION public.grid_model_immutable_v1()"
        )
    op.execute(
        f"INSERT INTO public.game_storage_table_manifest SELECT '{V9}',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        f"WHERE manifest_version='{V8}'"
    )
    for table, ownership in (
        ("grid_model_families", "shared"),
        ("grid_model_versions", "shared"),
        ("grid_model_registration_receipts", "shared"),
        ("grid_model_version_events", "shared"),
        ("game_grid_model_assignments", "catalog"),
        ("game_grid_model_assignment_events", "catalog"),
    ):
        connection.execute(
            sa.text("""INSERT INTO
public.game_storage_table_manifest(manifest_version,table_name,ownership,partitioned)
VALUES(:version,:table,:ownership,FALSE)"""),
            {"version": V9, "table": table, "ownership": ownership},
        )
    op.drop_constraint(
        "ck_game_storage_locations_manifest_version_v8", "game_storage_locations", schema="public"
    )
    op.execute(
        f"UPDATE public.game_storage_locations SET manifest_version='{V9}',"
        f"revision=revision+1,updated_at=now() WHERE manifest_version='{V8}'"
    )
    op.create_check_constraint(
        "ck_game_storage_locations_manifest_version_v9",
        "game_storage_locations",
        f"manifest_version='{V9}'",
        schema="public",
    )


def downgrade() -> None:
    raise RuntimeError(
        "GRID_MODEL_REGISTRY_DOWNGRADE_REFUSED: immutable model and assignment history "
        "cannot be removed losslessly"
    )
