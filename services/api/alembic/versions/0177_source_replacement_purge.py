"""Keep frozen identities independent of purged operational image records."""

from alembic import op

revision = "0177_source_replacement_purge"
down_revision = "0176_source_replacement_closed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE game_data_v2.source_images ADD COLUMN purged_at timestamptz")
    # UUID provenance stays immutable; only its live-parent FK is detached.
    op.execute("""DO $$ DECLARE r record; BEGIN
      FOR r IN SELECT c.conname,t.relname FROM pg_constraint c
        JOIN pg_class t ON t.oid=c.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
        JOIN pg_class parent ON parent.oid=c.confrelid
        WHERE n.nspname='game_data_v2' AND c.contype='f' AND c.conparentid=0
          AND t.relname IN ('verified_training_cohort_items','verified_training_cohort_cells',
                           'symbol_reference_images')
          AND parent.relname IN ('recognized_boards','image_review_items',
             'image_symbol_review_cells','image_source_geometry_revisions')
      LOOP EXECUTE format('ALTER TABLE game_data_v2.%I DROP CONSTRAINT %I',r.relname,r.conname);
      END LOOP;
    END $$""")
    op.execute("""CREATE FUNCTION game_data_v2.frozen_image_parent_guard_v1()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    DECLARE d jsonb := to_jsonb(NEW); previous jsonb; r record; value uuid; ok boolean;
    BEGIN
      PERFORM pg_advisory_xact_lock_shared(
        ('x'||substr(encode(sha256(convert_to(NEW.game_id::text||chr(58)||'sequence-ownership','UTF8')),
         'hex'),1,16))::bit(64)::bigint);
      IF TG_OP='UPDATE' THEN previous:=to_jsonb(OLD); END IF;
      FOR r IN SELECT * FROM (VALUES
       ('review_item_id','image_review_items'),('source_review_item_id','image_review_items'),
       ('recognized_board_id','recognized_boards'),
       ('source_recognized_board_id','recognized_boards'),
       ('cell_review_id','image_symbol_review_cells'),
       ('source_geometry_revision_id','image_source_geometry_revisions')) AS refs(field,tab)
      LOOP
        IF NOT d ? r.field OR d->r.field='null'::jsonb THEN CONTINUE; END IF;
        IF TG_OP='UPDATE' AND d->r.field IS NOT DISTINCT FROM previous->r.field THEN
          CONTINUE;
        END IF;
        value:=(d->>r.field)::uuid;
        EXECUTE format('SELECT EXISTS(SELECT 1 FROM game_data_v2.%I '
          'WHERE game_id=$1 AND id=$2)',r.tab) INTO ok USING NEW.game_id,value;
        IF NOT ok THEN RAISE EXCEPTION 'SOURCE_REPLACEMENT_FROZEN_PARENT_MISSING'; END IF;
      END LOOP;
      value:=COALESCE((d->>'review_item_id')::uuid,(d->>'source_review_item_id')::uuid);
      IF value IS NOT NULL AND (TG_OP='INSERT' OR
        d->'review_item_id' IS DISTINCT FROM previous->'review_item_id' OR
        d->'source_review_item_id' IS DISTINCT FROM previous->'source_review_item_id') THEN
        SELECT public.source_replacement_current_v1(s.game_id,s.id,s.checksum_sha256,
          b.sequence_number,i.id) INTO ok FROM game_data_v2.image_review_items i
          JOIN game_data_v2.recognized_boards b ON b.game_id=i.game_id AND
          b.id=i.recognized_board_id
          JOIN game_data_v2.source_images s ON s.game_id=b.game_id AND s.id=b.source_image_id
          WHERE i.game_id=NEW.game_id AND i.id=value;
        IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'SOURCE_REPLACEMENT_RETIRED'; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    for table in (
        "verified_training_cohort_items",
        "verified_training_cohort_cells",
        "symbol_reference_images",
    ):
        op.execute(
            f"CREATE TRIGGER frozen_image_parent_guard BEFORE INSERT OR UPDATE ON "
            f"game_data_v2.{table} FOR EACH ROW EXECUTE FUNCTION "
            "game_data_v2.frozen_image_parent_guard_v1()"
        )


def downgrade() -> None:
    # Restoring FKs cannot resurrect deleted parents or pixels.
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM game_data_v2.source_images
      WHERE purged_at IS NOT NULL) THEN RAISE EXCEPTION 'SOURCE_PURGE_IRREVERSIBLE';
      END IF; END $$""")
    for table in (
        "verified_training_cohort_items",
        "verified_training_cohort_cells",
        "symbol_reference_images",
    ):
        op.execute(f"DROP TRIGGER frozen_image_parent_guard ON game_data_v2.{table}")
    op.execute("DROP FUNCTION game_data_v2.frozen_image_parent_guard_v1()")
    refs = {
        "verified_training_cohort_items": {
            "review_item_id": "image_review_items",
            "recognized_board_id": "recognized_boards",
        },
        "verified_training_cohort_cells": {
            "review_item_id": "image_review_items",
            "recognized_board_id": "recognized_boards",
            "cell_review_id": "image_symbol_review_cells",
            "source_geometry_revision_id": "image_source_geometry_revisions",
        },
        "symbol_reference_images": {
            "source_review_item_id": "image_review_items",
            "source_recognized_board_id": "recognized_boards",
        },
    }
    for table, columns in refs.items():
        for column, parent in columns.items():
            op.execute(
                f"ALTER TABLE game_data_v2.{table} ADD FOREIGN KEY(game_id,{column}) "
                f"REFERENCES game_data_v2.{parent}(game_id,id) ON DELETE RESTRICT"
            )
    op.execute("ALTER TABLE game_data_v2.source_images DROP COLUMN purged_at")
