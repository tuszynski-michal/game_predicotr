"""Preview-bound structural purge and scoped, redactable retry receipts."""

from alembic import op
from game_predictor_api.storage.management_receipt_backfill import RECEIPT_SCOPE_SQL

revision = "0152_management_compact_panel"
down_revision = "0151_super_game_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
ALTER TABLE public.management_operations
  ADD COLUMN action varchar(80), ADD COLUMN point_id uuid,
  ADD COLUMN machine_id uuid, ADD COLUMN game_id uuid;
CREATE INDEX ix_public_management_operations_point_id
  ON public.management_operations(point_id);
CREATE INDEX ix_public_management_operations_machine_id
  ON public.management_operations(machine_id);
CREATE INDEX ix_public_management_operations_game_id
  ON public.management_operations(game_id);
CREATE TABLE public.management_mutation_previews (
  token_sha256 varchar(64) PRIMARY KEY, actor varchar(200) NOT NULL,
  action varchar(80) NOT NULL, point_id uuid NOT NULL, machine_id uuid,
  game_ids json, body_sha256 varchar(64) NOT NULL, fingerprint varchar(64) NOT NULL,
  counts json NOT NULL, created_at timestamptz NOT NULL, expires_at timestamptz NOT NULL
);
CREATE INDEX ix_public_management_mutation_previews_actor
  ON public.management_mutation_previews(actor);
CREATE INDEX ix_public_management_mutation_previews_expires_at
  ON public.management_mutation_previews(expires_at);
CREATE INDEX ix_management_search_contexts_scope_created
  ON public.management_search_contexts(machine_id, game_id, created_at);
CREATE INDEX ix_management_journal_scope_created
  ON public.management_journal(machine_id, game_id, created_at);
""")
    op.execute("""
CREATE OR REPLACE FUNCTION public.management_history_immutable() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog, public AS $$
DECLARE mode text := current_setting('management.maintenance_mode', true);
        owner_name text;
BEGIN
  SELECT r.rolname INTO owner_name FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_roles r ON r.oid=c.relowner WHERE c.oid=TG_RELID;
  IF current_user=owner_name THEN
    IF mode='purge' AND TG_OP='DELETE'
       AND TG_TABLE_SCHEMA='public' AND TG_TABLE_NAME IN
       ('management_journal','management_search_contexts','management_result_versions')
    THEN RETURN OLD; END IF;
    IF mode IN ('purge','migration-backfill') AND TG_OP='UPDATE'
       AND TG_TABLE_SCHEMA='public' AND TG_TABLE_NAME='management_operations'
    THEN
      IF NEW.operation_id IS DISTINCT FROM OLD.operation_id
         OR NEW.actor IS DISTINCT FROM OLD.actor
         OR NEW.request_checksum IS DISTINCT FROM OLD.request_checksum
         OR NEW.created_at IS DISTINCT FROM OLD.created_at
      THEN RAISE EXCEPTION 'Management receipt identity is immutable'; END IF;
      IF mode='purge' AND (
         NEW.action IS DISTINCT FROM OLD.action OR NEW.point_id IS DISTINCT FROM OLD.point_id
         OR NEW.machine_id IS DISTINCT FROM OLD.machine_id
         OR NEW.game_id IS DISTINCT FROM OLD.game_id
         OR NEW.response::jsonb <> '{"managementReceiptState":"target_deleted"}'::jsonb)
      THEN RAISE EXCEPTION 'Management purge only redacts receipt responses'; END IF;
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION 'Management history is immutable';
END $$;
""")
    op.execute("SELECT set_config('management.maintenance_mode','migration-backfill',true)")
    op.execute(
        RECEIPT_SCOPE_SQL
        + """
UPDATE public.management_operations o SET
 action=c.action, point_id=c.point_id, machine_id=c.machine_id, game_id=c.game_id,
 response=CASE WHEN c.category='legacy_redacted'
   THEN '{"managementReceiptState":"legacy_redacted"}'::json ELSE o.response END
FROM classified c WHERE c.operation_id=o.operation_id
"""
    )
    op.execute("SELECT set_config('management.maintenance_mode','',true)")
    op.execute("""
CREATE FUNCTION public.management_purge_scope(p_point uuid, p_machine uuid, p_games uuid[])
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog, public AS $$
DECLARE machines uuid[]; versions uuid[]; key bigint;
        old_mode text := current_setting('management.maintenance_mode', true);
BEGIN
  IF p_games IS NOT NULL AND p_machine IS NULL THEN
    RAISE EXCEPTION 'Game purge requires a machine'; END IF;
  PERFORM id FROM public.management_points WHERE id=p_point FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Management point not found'; END IF;
  PERFORM id FROM public.management_machines
    WHERE point_id=p_point AND (p_machine IS NULL OR id=p_machine)
    ORDER BY id FOR UPDATE;
  IF p_machine IS NOT NULL AND NOT FOUND THEN
    RAISE EXCEPTION 'Management machine is not in point'; END IF;
  SELECT COALESCE(array_agg(id ORDER BY id), '{}'::uuid[]) INTO machines
    FROM public.management_machines
    WHERE point_id=p_point AND (p_machine IS NULL OR id=p_machine);
  PERFORM g.id FROM public.games g JOIN public.management_assignments a ON a.game_id=g.id
    WHERE a.machine_id=ANY(machines) AND (p_games IS NULL OR a.game_id=ANY(p_games))
    ORDER BY g.id FOR SHARE OF g;
  SELECT COALESCE(array_agg(DISTINCT id), '{}'::uuid[]) INTO versions FROM (
    SELECT before_result_id AS id FROM public.management_journal
      WHERE (CASE WHEN p_machine IS NULL THEN point_id=p_point ELSE machine_id=p_machine END)
        AND (p_games IS NULL OR game_id=ANY(p_games))
    UNION SELECT after_result_id FROM public.management_journal
      WHERE (CASE WHEN p_machine IS NULL THEN point_id=p_point ELSE machine_id=p_machine END)
        AND (p_games IS NULL OR game_id=ANY(p_games))
    UNION SELECT result_version_id FROM public.management_stake_slots
      WHERE machine_id=ANY(machines) AND (p_games IS NULL OR game_id=ANY(p_games))
  ) candidates WHERE id IS NOT NULL;
  FOR key IN SELECT ('x'||substr(content_sha256,1,16))::bit(64)::bigint
      FROM (SELECT DISTINCT content_sha256 FROM public.management_result_versions
            WHERE id=ANY(versions) ORDER BY content_sha256) ordered_digests
  LOOP PERFORM pg_advisory_xact_lock(key); END LOOP;
  PERFORM set_config('management.maintenance_mode','purge',true);
  UPDATE public.management_operations
    SET response='{"managementReceiptState":"target_deleted"}'::json
    WHERE (CASE WHEN p_machine IS NULL THEN point_id=p_point ELSE machine_id=p_machine END)
      AND (p_games IS NULL OR game_id IS NULL OR game_id=ANY(p_games))
      AND action NOT IN ('point.delete','machine.delete');
  DELETE FROM public.management_journal
    WHERE (CASE WHEN p_machine IS NULL THEN point_id=p_point ELSE machine_id=p_machine END)
      AND (p_games IS NULL OR game_id=ANY(p_games));
  DELETE FROM public.management_stake_slots
    WHERE machine_id=ANY(machines) AND (p_games IS NULL OR game_id=ANY(p_games));
  DELETE FROM public.management_search_contexts
    WHERE machine_id=ANY(machines) AND (p_games IS NULL OR game_id=ANY(p_games));
  DELETE FROM public.management_result_versions v WHERE v.id=ANY(versions)
    AND NOT EXISTS (SELECT 1 FROM public.management_stake_slots s WHERE s.result_version_id=v.id)
    AND NOT EXISTS (SELECT 1 FROM public.management_journal j
                    WHERE j.before_result_id=v.id OR j.after_result_id=v.id);
  DELETE FROM public.management_assignments
    WHERE machine_id=ANY(machines) AND (p_games IS NULL OR game_id=ANY(p_games));
  IF p_games IS NULL THEN
    DELETE FROM public.management_machines WHERE id=ANY(machines);
    IF p_machine IS NULL THEN
      DELETE FROM public.management_points WHERE id=p_point;
    END IF;
  END IF;
  PERFORM set_config('management.maintenance_mode',COALESCE(old_mode,''),true);
END $$;
REVOKE ALL ON FUNCTION public.management_purge_scope(uuid,uuid,uuid[]) FROM PUBLIC;
""")


def downgrade() -> None:
    raise RuntimeError(
        "Structural purge and receipt redaction require backup restore, not downgrade."
    )
