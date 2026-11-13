"""D-610: raise the per-population source limit of recording functions from 5000 to 20 000.

Only the two exact limit predicates change; every other byte of each live function
definition, its owner, grants and security settings stay as they were.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import text
from sqlalchemy.engine import Connection

PREVIOUS_LIMIT: Final = 5000
SOURCE_LIMIT: Final = 20_000
COHORT_FUNCTIONS: Final = tuple(
    f"public.recording_photo_cohort_v{version}(uuid,jsonb,text)" for version in (1, 2, 3, 4)
)
CONTEXT_FUNCTIONS: Final = tuple(
    f"public.recording_photo_context_data_v{version}(uuid,uuid[],boolean)" for version in (2, 3)
)


def _predicate(signature: str, limit: int) -> str:
    if signature in COHORT_FUNCTIONS:
        return f"jsonb_array_length(plan->'sources')>{limit}"
    return f"cardinality(next_bytes)>{limit} OR cardinality(next_pixels)>{limit}"


def _rewrite(connection: Connection, before: int, after: int) -> None:
    for signature in (*COHORT_FUNCTIONS, *CONTEXT_FUNCTIONS):
        definition = connection.scalar(
            text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
            {"signature": signature},
        )
        old, new = _predicate(signature, before), _predicate(signature, after)
        if not isinstance(definition, str) or definition.count(old) != 1:
            raise RuntimeError(f"{signature} does not carry exactly one {before} limit.")
        connection.exec_driver_sql(definition.replace(old, new))


def raise_source_limit(connection: Connection) -> None:
    _rewrite(connection, PREVIOUS_LIMIT, SOURCE_LIMIT)


def restore_source_limit(connection: Connection) -> None:
    largest = connection.scalar(
        text("""SELECT COALESCE(max(n),0) FROM (SELECT count(*) n
      FROM game_data_v2.grid_training_cohort_members GROUP BY game_id,cohort_id) sizes""")
    )
    if int(largest or 0) > PREVIOUS_LIMIT:
        raise RuntimeError("A cohort above 5000 sources prevents downgrade.")
    _rewrite(connection, SOURCE_LIMIT, PREVIOUS_LIMIT)
