"""Remove cardinality admission caps, retaining all other SQL guards and grants."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from game_predictor_api.storage.source_recording_source_limit import (
    COHORT_FUNCTIONS,
    CONTEXT_FUNCTIONS,
    SOURCE_LIMIT,
)


def _predicates(signature: str) -> tuple[str, str]:
    if signature in COHORT_FUNCTIONS:
        return (
            f"jsonb_array_length(plan->'sources')>{SOURCE_LIMIT}",
            "false /* source count uncapped */",
        )
    return (
        f"cardinality(next_bytes)>{SOURCE_LIMIT} OR cardinality(next_pixels)>{SOURCE_LIMIT}",
        "false /* identity count uncapped */",
    )


def _rewrite(connection: Connection, *, restore: bool) -> None:
    # Validate every definition before replacing any, including in test connections.
    replacements: list[str] = []
    for signature in (*COHORT_FUNCTIONS, *CONTEXT_FUNCTIONS):
        definition = connection.scalar(
            text("SELECT pg_get_functiondef(to_regprocedure(:signature))"),
            {"signature": signature},
        )
        capped, uncapped = _predicates(signature)
        before, after = (uncapped, capped) if restore else (capped, uncapped)
        if not isinstance(definition, str) or definition.count(before) != 1:
            raise RuntimeError(f"{signature} does not carry exactly one expected source predicate.")
        replacements.append(definition.replace(before, after))
    for definition in replacements:
        connection.exec_driver_sql(definition)


def remove_source_cap(connection: Connection) -> None:
    _rewrite(connection, restore=False)


def restore_source_cap(connection: Connection) -> None:
    largest = connection.scalar(
        text("""SELECT COALESCE(max(n),0) FROM (SELECT count(*) n
      FROM game_data_v2.grid_training_cohort_members GROUP BY game_id,cohort_id) sizes""")
    )
    if int(largest or 0) > SOURCE_LIMIT:
        raise RuntimeError("A cohort above 20000 sources prevents downgrade.")
    _rewrite(connection, restore=True)
