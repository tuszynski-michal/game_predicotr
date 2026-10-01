"""RLS policy function is parallel safe; approved-cell CHECK without legacy_file (TASK-0797).

1. ``game_data_v2.current_game_id_v1()`` -- the function of every
   ``game_scope_v1`` policy -- was ``PARALLEL UNSAFE`` (plpgsql default) and
   caught the uuid cast error in an ``EXCEPTION`` block, which opens a
   subtransaction (forbidden in a parallel worker). Since the API and the
   worker run as the application role (TASK-0795), every policy-filtered
   query therefore ran without parallel workers (777: pending cells per symbol
   1.4 s -> 3.6 s). The function is replaced by a ``STABLE PARALLEL SAFE``
   plpgsql function without an exception block. Behaviour is unchanged: a
   missing or blank ``game_predictor.game_id`` raises
   ``GAME_STORAGE_SCOPE_REQUIRED``, a value that is not a uuid raises
   ``GAME_STORAGE_SCOPE_INVALID`` (both SQLSTATE 42501), never ``NULL``. The
   uuid shape is checked with the forms PostgreSQL's uuid input accepts
   (hyphens optional between 4-digit groups, optional braces). The policies
   themselves are not touched: ``CREATE OR REPLACE`` keeps the function oid.
   Custom GUCs are copied to parallel workers, and a ``SET search_path``
   clause is allowed there.

2. ``ck_image_symbol_review_cells_approved_provenance`` loses the historical
   file-crop approval branch (``approved_asset_mode IS NULL OR
   'legacy_file'`` with a crop sample). No writer produces it since
   TASK-0790/0796; the operator database had 0 such rows (2026-10-01,
   read-only). Preflight under ``ACCESS EXCLUSIVE`` (``lock_timeout`` 5 s,
   ``statement_timeout`` 120 s) refuses with
   ``CELL_APPROVED_LEGACY_PROVENANCE_PRESENT`` when any row still uses the
   branch; the new constraint is added ``NOT VALID`` like in ``0135``/``0136``
   and validated afterwards by the runbook (SHARE UPDATE EXCLUSIVE scan).

Downgrade restores the previous function and the wider constraint (every row
valid under the new constraint is valid under the old one).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0138_rls_policy_function_parallel_safe"
down_revision: str | Sequence[str] | None = "0137_prediction_revisions_slim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CELLS = "game_data_v2.image_symbol_review_cells"
APPROVED_CHECK = "ck_image_symbol_review_cells_approved_provenance"

_SHA256 = "'^[0-9a-f]{64}$'"
_UNAPPROVED = (
    "(approved_crop_sample_id IS NULL AND approved_crop_checksum_sha256 IS NULL "
    "AND approved_geometry_revision IS NULL AND approved_asset_mode IS NULL "
    "AND approved_source_geometry_revision_id IS NULL "
    "AND approved_render_spec_checksum_sha256 IS NULL "
    "AND approved_rendered_pixel_checksum_sha256 IS NULL)"
)
_LEGACY_FILE_APPROVAL = (
    f"(approved_crop_sample_id ~ {_SHA256} AND approved_crop_checksum_sha256 ~ {_SHA256} "
    "AND approved_geometry_revision >= 0 "
    "AND (approved_asset_mode IS NULL OR approved_asset_mode = 'legacy_file') "
    "AND approved_source_geometry_revision_id IS NULL "
    "AND approved_render_spec_checksum_sha256 IS NULL "
    "AND approved_rendered_pixel_checksum_sha256 IS NULL)"
)
_VIRTUAL_APPROVAL = (
    f"(approved_crop_sample_id ~ {_SHA256} AND approved_crop_checksum_sha256 ~ {_SHA256} "
    "AND approved_geometry_revision >= 0 AND approved_asset_mode = 'virtual_source' "
    "AND approved_source_geometry_revision_id IS NOT NULL "
    f"AND approved_render_spec_checksum_sha256 ~ {_SHA256} "
    f"AND approved_rendered_pixel_checksum_sha256 ~ {_SHA256})"
)
NEW_APPROVED_CHECK = f"{_UNAPPROVED} OR {_VIRTUAL_APPROVAL}"
OLD_APPROVED_CHECK = f"{_UNAPPROVED} OR {_LEGACY_FILE_APPROVAL} OR {_VIRTUAL_APPROVAL}"

# Accepted uuid text forms of PostgreSQL's uuid input (case-insensitive).
_UUID_TEXT = r"^(\{[0-9a-f]{4}(-?[0-9a-f]{4}){7}\}|[0-9a-f]{4}(-?[0-9a-f]{4}){7})$"

PARALLEL_SAFE_FUNCTION = f"""
CREATE OR REPLACE FUNCTION game_data_v2.current_game_id_v1()
RETURNS uuid
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $$
DECLARE raw_game_id text;
BEGIN
    raw_game_id := current_setting('game_predictor.game_id', true);
    IF raw_game_id IS NULL OR btrim(raw_game_id) = '' THEN
        RAISE EXCEPTION 'GAME_STORAGE_SCOPE_REQUIRED' USING ERRCODE = '42501';
    END IF;
    IF raw_game_id !~* '{_UUID_TEXT}' THEN
        RAISE EXCEPTION 'GAME_STORAGE_SCOPE_INVALID' USING ERRCODE = '42501';
    END IF;
    RETURN raw_game_id::uuid;
END
$$
"""

PREVIOUS_FUNCTION = """
CREATE OR REPLACE FUNCTION game_data_v2.current_game_id_v1()
RETURNS uuid
LANGUAGE plpgsql
STABLE
PARALLEL UNSAFE
SET search_path = pg_catalog
AS $$
DECLARE raw_game_id text;
BEGIN
    raw_game_id := current_setting('game_predictor.game_id', true);
    IF raw_game_id IS NULL OR btrim(raw_game_id) = '' THEN
        RAISE EXCEPTION 'GAME_STORAGE_SCOPE_REQUIRED' USING ERRCODE = '42501';
    END IF;
    RETURN raw_game_id::uuid;
EXCEPTION WHEN invalid_text_representation THEN
    RAISE EXCEPTION 'GAME_STORAGE_SCOPE_INVALID' USING ERRCODE = '42501';
END
$$
"""


def _swap_approved_check(expression: str) -> None:
    op.execute(f"ALTER TABLE {CELLS} DROP CONSTRAINT {APPROVED_CHECK}")
    op.execute(
        f"ALTER TABLE {CELLS} ADD CONSTRAINT {APPROVED_CHECK} CHECK ({expression}) NOT VALID"
    )


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(PARALLEL_SAFE_FUNCTION)
    op.execute(f"LOCK TABLE {CELLS} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $guard$
    DECLARE legacy bigint;
    BEGIN
        SELECT count(*) INTO legacy FROM {CELLS}
        WHERE approved_crop_sample_id IS NOT NULL
          AND approved_asset_mode IS DISTINCT FROM 'virtual_source';
        IF legacy > 0 THEN
            RAISE EXCEPTION 'CELL_APPROVED_LEGACY_PROVENANCE_PRESENT: % review cells keep a '
                'file-crop approval; convert them before narrowing the constraint', legacy;
        END IF;
    END $guard$""")
    _swap_approved_check(NEW_APPROVED_CHECK)


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '120s'")
    op.execute(f"LOCK TABLE {CELLS} IN ACCESS EXCLUSIVE MODE")
    _swap_approved_check(OLD_APPROVED_CHECK)
    op.execute(PREVIOUS_FUNCTION)
