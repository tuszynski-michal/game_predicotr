"""Shared registry of verified lossless crops of managed originals (TASK-1044, D-562).

Revision ID: 0167_source_image_crops
Revises: 0166_grid_model_evaluation
Create Date: 2026-10-17

One row per content-addressed original (its SHA-256), not per game: a managed
original may be shared by sources of several games. The row mirrors the crop
attestation stored next to the crop file and carries the job state
(``verified`` -> ``original_deleted``). It holds paths, checksums and boxes
only, never image bytes or game payload, so it is a ``shared`` table of
manifest v18. No crop is created and no original is touched by this revision.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0167_source_image_crops"
down_revision: str | Sequence[str] | None = "0166_grid_model_evaluation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "source_image_crops"
SHA = "~ '^[0-9a-f]{64}$'"
SAFE_PATH = r"!~ '(^/|(^|/)\.\.(/|$)|\\)'"


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
    _guard(17)
    op.execute(f"""CREATE TABLE public.{TABLE} (
      original_checksum_sha256 varchar(64) PRIMARY KEY
        CHECK(original_checksum_sha256 {SHA}),
      original_relative_path varchar(1000) NOT NULL,
      original_size_bytes bigint NOT NULL CHECK(original_size_bytes>0),
      original_normalized_pixel_checksum_sha256 varchar(64) NOT NULL
        CHECK(original_normalized_pixel_checksum_sha256 {SHA}),
      original_width integer NOT NULL CHECK(original_width>0),
      original_height integer NOT NULL CHECK(original_height>0),
      original_exif_orientation smallint
        CHECK(original_exif_orientation IS NULL OR original_exif_orientation IN (1,3,6,8)),
      crop_relative_path varchar(1000) NOT NULL,
      attestation_relative_path varchar(1000) NOT NULL,
      crop_checksum_sha256 varchar(64) NOT NULL CHECK(crop_checksum_sha256 {SHA}),
      crop_size_bytes bigint NOT NULL CHECK(crop_size_bytes>0),
      crop_normalized_pixel_checksum_sha256 varchar(64) NOT NULL
        CHECK(crop_normalized_pixel_checksum_sha256 {SHA}),
      canvas_pixel_checksum_sha256 varchar(64) NOT NULL
        CHECK(canvas_pixel_checksum_sha256 {SHA}),
      attestation_sha256 varchar(64) NOT NULL CHECK(attestation_sha256 {SHA}),
      crop_box integer[] NOT NULL,
      raw_crop_box integer[] NOT NULL,
      protected_box double precision[] NOT NULL,
      margin_px smallint NOT NULL CHECK(margin_px>=0),
      imcu_width smallint NOT NULL CHECK(imcu_width IN (8,16)),
      imcu_height smallint NOT NULL CHECK(imcu_height IN (8,16)),
      edge_mismatch_pixels integer NOT NULL CHECK(edge_mismatch_pixels>=0),
      tool_version varchar(200) NOT NULL CHECK(length(btrim(tool_version))>0),
      policy_version varchar(40) NOT NULL CHECK(policy_version='source-crop-v1'),
      state varchar(20) NOT NULL,
      job_id uuid REFERENCES public.jobs(id) ON DELETE RESTRICT,
      verified_at timestamptz NOT NULL DEFAULT now(),
      original_deleted_at timestamptz,
      CONSTRAINT ck_{TABLE}_paths CHECK(
        original_relative_path = 'originals/' || substr(original_checksum_sha256,1,2)
          || '/' || original_checksum_sha256 || '.jpg'
        AND crop_relative_path = 'originals-cropped/' || substr(original_checksum_sha256,1,2)
          || '/' || original_checksum_sha256 || '.jpg'
        AND attestation_relative_path = 'originals-cropped/'
          || substr(original_checksum_sha256,1,2) || '/' || original_checksum_sha256 || '.json'
        AND crop_relative_path {SAFE_PATH}),
      CONSTRAINT ck_{TABLE}_smaller CHECK(crop_size_bytes<original_size_bytes),
      CONSTRAINT ck_{TABLE}_boxes CHECK(
        cardinality(crop_box)=4 AND cardinality(raw_crop_box)=4
        AND cardinality(protected_box)=4
        AND array_ndims(crop_box)=1 AND array_ndims(raw_crop_box)=1
        AND array_ndims(protected_box)=1
        AND array_lower(crop_box,1)=1 AND array_lower(raw_crop_box,1)=1
        AND array_lower(protected_box,1)=1
        AND array_position(crop_box,NULL) IS NULL
        AND array_position(raw_crop_box,NULL) IS NULL
        AND array_position(protected_box,NULL) IS NULL
        AND raw_crop_box[1]>=0 AND raw_crop_box[2]>=0
        AND raw_crop_box[3]>raw_crop_box[1] AND raw_crop_box[4]>raw_crop_box[2]
        AND (raw_crop_box[3]-raw_crop_box[1])*(raw_crop_box[4]-raw_crop_box[2])
          =(crop_box[3]-crop_box[1])*(crop_box[4]-crop_box[2])
        AND protected_box[3]>=protected_box[1] AND protected_box[4]>=protected_box[2]
        AND crop_box[1]>=0 AND crop_box[2]>=0
        AND crop_box[3]>crop_box[1] AND crop_box[4]>crop_box[2]
        AND crop_box[3]<=original_width AND crop_box[4]<=original_height
        AND protected_box[1]>=crop_box[1] AND protected_box[2]>=crop_box[2]
        AND protected_box[3]<=crop_box[3] AND protected_box[4]<=crop_box[4]),
      CONSTRAINT ck_{TABLE}_state CHECK(
        (state='verified' AND original_deleted_at IS NULL)
        OR (state='original_deleted' AND original_deleted_at IS NOT NULL
          AND original_deleted_at>=verified_at)))""")
    op.execute(f"CREATE INDEX ix_{TABLE}_state ON public.{TABLE}(state,verified_at)")
    op.execute(f"CREATE INDEX ix_{TABLE}_job ON public.{TABLE}(job_id)")
    op.execute(
        "INSERT INTO public.game_storage_table_manifest SELECT 'game-data-v2-manifest-v18',"
        "table_name,ownership,partitioned FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v17'"
    )
    op.execute(
        "INSERT INTO public.game_storage_table_manifest "
        f"VALUES('game-data-v2-manifest-v18','{TABLE}','shared',FALSE)"
    )
    _manifest(17, 18)


def downgrade() -> None:
    # A crop whose original was deleted is the only copy of that image region:
    # dropping its registry would orphan the attested files, so it blocks.
    _guard(18)
    op.execute(f"LOCK TABLE public.{TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute(f"""DO $history$ BEGIN
      IF EXISTS(SELECT 1 FROM public.{TABLE})
        THEN RAISE EXCEPTION 'SOURCE_IMAGE_CROPS_DOWNGRADE_HAS_HISTORY'; END IF;
    END $history$""")
    op.execute(f"DROP TABLE public.{TABLE}")
    _manifest(18, 17)
    op.execute(
        "DELETE FROM public.game_storage_table_manifest "
        "WHERE manifest_version='game-data-v2-manifest-v18'"
    )
