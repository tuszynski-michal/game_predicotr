"""Additive recording membership lookup, installed by Alembic0162.

The frozen five-argument resolver and all v1 registry objects remain unchanged.
"""

INSTALL_SOURCE_RECORDING_V2_SQL = """
CREATE FUNCTION public.resolve_own_groups(wanted uuid, ids uuid[], family uuid,
    page_limit integer, after_id uuid, wanted_source uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE views jsonb; cursor uuid; BEGIN
 PERFORM public.recording_scope_v1(wanted);
 IF page_limit NOT BETWEEN 1 AND 100 OR COALESCE(pg_catalog.cardinality(ids),0)>200 THEN RAISE
    EXCEPTION 'RECORDING_PAGE_INVALID' USING ERRCODE='22023'; END IF;
 IF EXISTS(SELECT 1 FROM pg_catalog.unnest(ids) v WHERE NOT EXISTS(SELECT 1 FROM
    public.recording_groups g WHERE g.id=v AND g.game_id=wanted)) THEN RAISE EXCEPTION
    'RECORDING_NOT_FOUND' USING ERRCODE='42501'; END IF;
 SELECT COALESCE(pg_catalog.jsonb_agg(public.recording_group_view_v1(wanted,g.id,family) ORDER
    BY g.id),'[]') INTO views
 FROM (SELECT selected.id FROM public.recording_groups selected
    WHERE selected.game_id=wanted
    AND (wanted_source IS NULL OR EXISTS(SELECT 1 FROM public.recording_occurrences occurrence
        WHERE occurrence.group_id=selected.id AND occurrence.game_id=wanted
        AND occurrence.origin='MAIN' AND occurrence.source_id=wanted_source))
    AND (after_id IS NULL OR selected.id>after_id)
    AND (COALESCE(pg_catalog.cardinality(ids),0)=0 OR selected.id=ANY(ids))
    ORDER BY selected.id LIMIT page_limit) g;
 IF pg_catalog.jsonb_array_length(views)=page_limit THEN cursor:=(views->-1->>'id')::uuid; END IF;
 RETURN pg_catalog.jsonb_build_object('items',views,'nextCursor',cursor);
END $$;
"""

DROP_SOURCE_RECORDING_V2_SQL = """
DROP FUNCTION public.resolve_own_groups(uuid,uuid[],uuid,integer,uuid,uuid);
"""
