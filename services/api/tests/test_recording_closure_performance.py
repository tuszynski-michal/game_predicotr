"""Reversible, fail-closed rewrites leave the existing admission guards intact."""

from typing import Any, cast

import pytest
from game_predictor_api.storage.source_recording_closure_performance import (
    COHORT,
    CONTEXT,
    rewrite_closure_functions,
    rewrite_definition,
)
from game_predictor_api.storage.source_recording_sql_v8 import CONTEXT_SQL
from game_predictor_api.storage.source_recording_sql_v10 import PHOTO_SQL
from sqlalchemy.engine import Connection


def definitions():
    return {
        CONTEXT: CONTEXT_SQL.split("CREATE FUNCTION public.recording_photo_context_v3(")[0],
        COHORT: PHOTO_SQL,
    }


@pytest.mark.parametrize("signature", [CONTEXT, COHORT])
def test_upgrade_downgrade_restores_the_complete_original_definition(signature):
    original = definitions()[signature]
    improved = rewrite_definition(signature, original)
    assert "TASK-1235" in improved
    assert rewrite_definition(signature, improved, restore=True) == original
    with pytest.raises(RuntimeError):
        rewrite_definition(signature, improved)
    with pytest.raises(RuntimeError):
        rewrite_definition(signature, original, restore=True)


def test_context_keeps_the_original_connected_branch_and_guard_codes():
    original = definitions()[CONTEXT]
    improved = rewrite_definition(CONTEXT, original)
    start = original.index("  bytes:=ARRAY")
    end = original.index("  result:=result||")
    assert original[start:end] in improved
    assert improved.count("'RECORDING_PAGE_INVALID'") == original.count("'RECORDING_PAGE_INVALID'")
    assert "WHERE b IS NULL OR p IS NULL" in improved
    assert "u.game_id=wanted AND u.source_id=candidate.id" in improved


def test_cohort_keeps_every_guard_and_preview_modes_separate():
    original = definitions()[COHORT]
    improved = rewrite_definition(COHORT, original)
    import re

    assert re.findall(r"RAISE EXCEPTION\s+'([^']+)'", improved) == re.findall(
        r"RAISE EXCEPTION\s+'([^']+)'", original
    )
    for guard in (
        "source_replacement_source_current_v1",
        "registryProofSha256",
        "validationPurpose",
        "newUseExcluded",
        "pg_advisory_xact_lock",
    ):
        assert improved.count(guard) >= original.count(guard)
    assert "||':'||preview::text" in improved
    assert "closure_pos+199" in improved
    assert "WHERE preview IS TRUE" in improved and "WHERE preview IS NOT TRUE" in improved


class FakeConnection:
    def __init__(self, values):
        self.values, self.writes = values, []

    def scalar(self, statement: Any, parameters: Any):
        assert "pg_get_functiondef" in str(statement)
        return self.values[parameters["signature"]]

    def exec_driver_sql(self, definition):
        self.writes.append(definition)


@pytest.mark.parametrize("broken", [None, "unexpected function body"])
def test_both_functions_are_preflighted_before_any_write(broken):
    originals = definitions()
    connection = FakeConnection({**originals, COHORT: broken})
    with pytest.raises(RuntimeError):
        rewrite_closure_functions(cast(Connection, connection))
    assert not connection.writes


def test_rewrite_uses_complete_definitions_in_their_original_order():
    originals = definitions()
    connection = FakeConnection(originals)
    rewrite_closure_functions(cast(Connection, connection))
    assert connection.writes == [rewrite_definition(key, value) for key, value in originals.items()]
