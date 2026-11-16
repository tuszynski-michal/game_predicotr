"""Bounded context pages and equivalent empty closures for unlinked photos."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

CONTEXT = "public.recording_photo_context_data_v3(uuid,uuid[],boolean)"
COHORT = "public.recording_photo_cohort_v4(uuid,jsonb,text)"

_CONTEXT_LOOP = """ FOR s IN SELECT id,checksum_sha256,normalized_pixel_checksum_sha256
 FROM game_data_v2.source_images WHERE game_id=wanted AND id=ANY(ids) ORDER BY id LOOP
"""
_CONTEXT_PAGE = (
    """ -- TASK-1235: classify only this bounded page in the statement snapshot.
 WITH selected AS MATERIALIZED (
  SELECT id,checksum_sha256 b,normalized_pixel_checksum_sha256 p
  FROM game_data_v2.source_images WHERE game_id=wanted AND id=ANY(ids)
 ), linked AS (
  SELECT candidate.id FROM selected candidate JOIN public.recording_photo_uses u
   ON u.source_sha256=candidate.b
  UNION SELECT candidate.id FROM selected candidate JOIN public.recording_photo_uses u
   ON u.pixel_sha256=candidate.p
  UNION SELECT candidate.id FROM selected candidate JOIN public.recording_photo_uses u
   ON u.game_id=wanted AND u.source_id=candidate.id
  UNION SELECT candidate.id FROM selected candidate JOIN public.recording_occurrences o
   ON o.source_sha256=candidate.b
  UNION SELECT candidate.id FROM selected candidate JOIN public.recording_occurrences o
   ON o.pixel_sha256=candidate.p
  UNION SELECT id FROM selected WHERE b IS NULL OR p IS NULL
 ) SELECT COALESCE(array_agg(id),'{}') INTO closure_linked FROM linked;
 WITH selected AS MATERIALIZED (
  SELECT id,checksum_sha256 b,normalized_pixel_checksum_sha256 p
  FROM game_data_v2.source_images WHERE game_id=wanted AND id=ANY(ids)
 ), diagnostic AS (
  SELECT candidate.id,COALESCE(jsonb_agg(jsonb_build_object('id',e.id,'sha256',e.payload_sha256)
   ORDER BY e.id) FILTER(WHERE e.id IS NOT NULL),'[]'::jsonb) evidence
  FROM selected candidate LEFT JOIN public.recording_evidence e ON e.kind='use'
   AND e.payload->>'purpose'='diagnostic_comparison'
   AND (e.payload->>'sourceSha256'=candidate.b OR e.payload->>'pixelSha256'=candidate.p)
  GROUP BY candidate.id
 ) SELECT COALESCE(jsonb_object_agg(id::text,evidence),'{}')
 INTO closure_diagnostics FROM diagnostic;
 closure_empty_proof:=public.recording_proof_v1('{}'::uuid[]);
"""
    + _CONTEXT_LOOP
    + "  IF s.id=ANY(closure_linked) THEN\n"
)

_RESULT = "  result:=result||jsonb_build_array(jsonb_build_object('sourceId',s.id,"
_EMPTY_CLOSURE = (
    """  ELSE
   -- No registry seed means no transitive edges. Own uses/nullable identities
   -- took the original branch, so label arrays are also exactly empty here.
   groups:='{}'; bytes:=ARRAY[s.checksum_sha256];
   pixels:=ARRAY[s.normalized_pixel_checksum_sha256];
   uses:='[]'; released:='[]'; releases:='[]'; labels:='[]'; alias_labels:='[]';
   roles:='{}'; photo_roles:='{}'; external_roles:='{}'; purposes:='{}';
   allowed:=ARRAY['TRAIN','VALIDATION','REGRESSION'];
   protected:=false; external_protection:=false; unspecified_protection:=false;
   exposed:=false;
   diagnostic:=COALESCE(closure_diagnostics->(s.id::text),'[]'::jsonb);
  END IF;
"""
    + _RESULT
)

_COHORT_LOOP = " FOR item IN SELECT p FROM jsonb_array_elements(plan->'sources') p LOOP\n"
_COHORT_PAGE = (
    """ -- TASK-1235: IDs/preview flags retain the original plan order.
 SELECT array_agg((p->>'sourceId')::uuid ORDER BY ord),
  array_agg(COALESCE(incremental AND (kind='register_cohort_use'
   OR COALESCE(p->'newUseExcluded'='true'::jsonb,false)),false) ORDER BY ord)
 INTO closure_ids,closure_previews
 FROM jsonb_array_elements(plan->'sources') WITH ORDINALITY AS planned(p,ord);
"""
    + _COHORT_LOOP
    + "  closure_pos:=closure_pos+1;\n"
)

_CONTEXT_CALL = """  context:=public.recording_photo_context_data_v3(wanted,ARRAY[source.id],
   incremental AND (kind='register_cohort_use'
    OR COALESCE(item->'newUseExcluded'='true'::jsonb,false)))->0;"""
_PAGED_CALL = """  IF mod(closure_pos-1,200)=0 THEN
   SELECT COALESCE(jsonb_object_agg((value->>'sourceId')||':'||preview::text,value),'{}')
   INTO closure_page FROM (
    SELECT value,true AS preview FROM jsonb_array_elements(
     public.recording_photo_context_data_v3(wanted,ARRAY(
      SELECT id FROM unnest(closure_ids[closure_pos:closure_pos+199],
       closure_previews[closure_pos:closure_pos+199]) AS page(id,preview)
      WHERE preview IS TRUE),true)) AS contexts(value)
    UNION ALL
    SELECT value,false AS preview FROM jsonb_array_elements(
     public.recording_photo_context_data_v3(wanted,ARRAY(
      SELECT id FROM unnest(closure_ids[closure_pos:closure_pos+199],
       closure_previews[closure_pos:closure_pos+199]) AS page(id,preview)
      WHERE preview IS NOT TRUE),false)) AS contexts(value)
   ) cached;
  END IF;
  context:=closure_page->(source.id::text||':'||closure_previews[closure_pos]::text);"""

_REPLACEMENTS = {
    CONTEXT: (
        (
            " iteration integer; BEGIN",
            " iteration integer; closure_linked uuid[]; closure_diagnostics jsonb; "
            "closure_empty_proof text; BEGIN",
        ),
        (_CONTEXT_LOOP, _CONTEXT_PAGE),
        (_RESULT, _EMPTY_CLOSURE),
        (
            "public.recording_proof_v1(groups)",
            "(CASE WHEN cardinality(groups)=0 THEN closure_empty_proof "
            "ELSE public.recording_proof_v1(groups) END)",
        ),
    ),
    COHORT: (
        (
            "incremental boolean; BEGIN",
            "incremental boolean; closure_ids uuid[]; closure_previews boolean[]; "
            "closure_pos integer:=0; closure_page jsonb; BEGIN",
        ),
        (_COHORT_LOOP, _COHORT_PAGE),
        (_CONTEXT_CALL, _PAGED_CALL),
    ),
}


def rewrite_definition(signature: str, definition: str, *, restore: bool = False) -> str:
    """Reject unexpected live definitions instead of partially patching SQL."""
    replacements = _REPLACEMENTS[signature]
    if restore:
        replacements = tuple((new, old) for old, new in reversed(replacements))
    for before, after in replacements:
        if definition.count(before) != 1:
            raise RuntimeError(f"{signature} does not carry exactly one expected closure fragment.")
        definition = definition.replace(before, after)
    return definition


def rewrite_closure_functions(connection: Connection, *, restore: bool = False) -> None:
    """Preflight both definitions; CREATE OR REPLACE retains OIDs and ACLs."""
    replacements: list[str] = []
    for signature in (CONTEXT, COHORT):
        definition = connection.scalar(
            text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
            {"signature": signature},
        )
        if not isinstance(definition, str):
            raise RuntimeError(f"Missing closure function: {signature}.")
        replacements.append(rewrite_definition(signature, definition, restore=restore))
    for definition in replacements:
        connection.exec_driver_sql(definition)


_HEADER_SELECT = " SELECT c.revision,c.status,c.document,c.manifest_sha256 INTO header"
_HEADER_PROJECTED = """ -- TASK-1235: project once to avoid repeated document detoasting.
 SELECT c.revision,c.status,c.document->>'policyVersion' AS policy_version,
  c.document->>'mode' AS cohort_mode,c.document->>'familyId' AS family_id,
  c.document->'photoSplit'->'contentSampling'->>'policy' AS sampling_policy,
  c.document->'photoSplit' AS photo_split,c.manifest_sha256 INTO header"""
_HEADER_REPLACEMENTS = (
    (_HEADER_SELECT, _HEADER_PROJECTED, 1),
    ("header.document->>'policyVersion'", "header.policy_version", 1),
    ("header.document->>'mode'", "header.cohort_mode", 3),
    ("header.document->>'familyId'", "header.family_id", 1),
    (
        "header.document->'photoSplit'->'contentSampling'->>'policy'",
        "header.sampling_policy",
        1,
    ),
    ("header.document->'photoSplit'", "header.photo_split", 1),
)


def rewrite_header_definition(definition: str, *, restore: bool = False) -> str:
    """Cache immutable header fields without changing admission or cast timing."""
    replacements: tuple[tuple[str, str, int], ...] = _HEADER_REPLACEMENTS
    if restore:
        replacements = tuple((new, old, count) for old, new, count in reversed(replacements))
    for before, after, count in replacements:
        if definition.count(before) != count:
            raise RuntimeError(f"{COHORT} does not carry the expected header fragments.")
        definition = definition.replace(before, after)
    if not restore and "header.document" in definition:
        raise RuntimeError(f"{COHORT} has an unexpected large-header access.")
    return definition


def rewrite_header_function(connection: Connection, *, restore: bool = False) -> None:
    """Preserve the existing function identity, privileges and security settings."""
    definition = connection.scalar(
        text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
        {"signature": COHORT},
    )
    if not isinstance(definition, str):
        raise RuntimeError(f"Missing closure function: {COHORT}.")
    connection.exec_driver_sql(rewrite_header_definition(definition, restore=restore))
