"""TASK-0971 (D-543): the worker import writer uses the shared ownership rule.

The PostgreSQL scenarios of the rule run the worker writer itself
(``services/api/tests/integration/test_replacement_photo_takeover_postgres.py``);
these tests pin that the worker has no second copy of the rule.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from game_predictor_api.domain import sequence_takeover
from game_predictor_api.storage import pending_sequence_ownership
from game_predictor_worker.images import pipeline_store


def test_a_new_review_item_is_created_by_the_shared_ownership_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    created = SimpleNamespace(id=uuid4(), status="superseded")

    def create(session: object, **kwargs: Any) -> tuple[object, tuple[object, ...]]:
        calls.append(kwargs)
        return created, (created.id,)

    monkeypatch.setattr(pipeline_store, "create_owned_pending_review_item", create)
    session = MagicMock()
    session.scalar.return_value = None
    board = SimpleNamespace(
        id=uuid4(),
        board_geometry={"quad": []},
        pipeline_fingerprint="b" * 64,
        position_index=0,
        completeness_status="complete",
        unavailable_cell_indices=[],
    )
    source = SimpleNamespace(checksum_sha256="a" * 64, relative_path="originals/b.jpg")
    job = SimpleNamespace(id=uuid4(), game_id=uuid4())
    now = datetime.now(UTC)

    item, changed = pipeline_store._upsert_review_item(
        cast(Any, session),
        cast(Any, board),
        cast(Any, source),
        cast(Any, job),
        {"normalizedNumber": 100},
        {"confidence": 0.9},
        {"assetMode": "virtual_source"},
        {"cells": []},
        created_at=now,
    )

    assert item is created and changed == (created.id,)
    [call] = calls
    assert call["board"] is board and call["import_job"] is job
    assert call["game_id"] == job.game_id and call["created_at"] == now


def test_the_worker_writer_has_no_copy_of_the_pending_ownership_rule() -> None:
    source = inspect.getsource(pipeline_store)
    for reason in (
        sequence_takeover.EXISTING_OWNER_KEPT_REASON,
        sequence_takeover.NEWER_SAME_SOURCE_OWNER_KEPT_REASON,
        sequence_takeover.OLDER_SAME_SOURCE_OWNER_REPLACED_REASON,
    ):
        assert reason not in source
    assert pipeline_store.create_owned_pending_review_item is (
        pending_sequence_ownership.create_owned_pending_review_item
    )
    ownership = inspect.getsource(pending_sequence_ownership)
    assert "decide_sequence_claim(" in ownership
