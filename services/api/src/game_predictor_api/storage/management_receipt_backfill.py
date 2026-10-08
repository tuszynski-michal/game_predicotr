"""Read-only legacy receipt classification shared by migration and operator preview."""

RECEIPT_SCOPE_SQL = """
WITH raw AS (
  SELECT o.operation_id, o.response::jsonb AS body,
         j.action, j.point_id AS journal_point, j.machine_id AS journal_machine,
         j.game_id AS journal_game, c.machine_id AS context_machine,
         c.game_id AS context_game
  FROM public.management_operations o
  LEFT JOIN LATERAL (
    SELECT action, point_id, machine_id, game_id
    FROM public.management_journal WHERE operation_id=o.operation_id
    ORDER BY created_at, id LIMIT 1
  ) j ON true
  LEFT JOIN public.management_search_contexts c ON c.id=o.operation_id
), decoded AS (
  SELECT *,
    CASE WHEN COALESCE(body->>'machineId', body->'slot'->>'machineId',
      CASE WHEN body ? 'pointId' THEN body->>'id' END)
      ~* '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
    THEN COALESCE(body->>'machineId', body->'slot'->>'machineId',
      CASE WHEN body ? 'pointId' THEN body->>'id' END)::uuid END AS response_machine,
    CASE WHEN COALESCE(body->>'pointId',
      CASE WHEN body ? 'city' AND body ? 'street' THEN body->>'id' END)
      ~* '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
    THEN COALESCE(body->>'pointId',
      CASE WHEN body ? 'city' AND body ? 'street' THEN body->>'id' END)::uuid END AS response_point,
    CASE WHEN COALESCE(body->>'gameId', body->'slot'->>'gameId')
      ~* '^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$'
    THEN COALESCE(body->>'gameId', body->'slot'->>'gameId')::uuid END AS response_game
  FROM raw
), classified AS (
  SELECT d.operation_id, COALESCE(d.action, 'legacy.write') AS action,
    COALESCE(d.journal_point, d.response_point, m.point_id) AS point_id,
    COALESCE(d.journal_machine, d.context_machine, d.response_machine) AS machine_id,
    COALESCE(d.journal_game, d.context_game, d.response_game) AS game_id,
    CASE WHEN d.journal_point IS NOT NULL THEN 'journal'
         WHEN d.context_machine IS NOT NULL THEN 'context'
         WHEN COALESCE(d.response_point, m.point_id) IS NOT NULL THEN 'response'
         ELSE 'legacy_redacted' END AS category
  FROM decoded d LEFT JOIN public.management_machines m
    ON m.id=COALESCE(d.journal_machine, d.context_machine, d.response_machine)
)
"""
