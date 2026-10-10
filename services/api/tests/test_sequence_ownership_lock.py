"""TASK-0950 (P0-5): re-entrancy and the no-upgrade rule of the ownership lock."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from game_predictor_api.domain.image_reviews import ImageReviewConflictError
from game_predictor_api.storage.sequence_ownership_lock import (
    SEQUENCE_OWNERSHIP_LOCK_UPGRADE,
    SequenceOwnershipLockMode,
    acquire_sequence_ownership_lock,
    ensure_sequence_ownership_lock,
    held_sequence_ownership_lock,
    require_exclusive_sequence_ownership,
)
from sqlalchemy.dialects import postgresql


class _Session:
    """The surface the protocol uses: ``info``, the root transaction, ``execute``."""

    def __init__(self) -> None:
        self.info: dict[str, Any] = {}
        self.transaction = object()
        self.statements: list[str] = []

    def connection(self) -> None:
        return None

    def get_transaction(self) -> object:
        return self.transaction

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))


def test_a_nested_request_of_the_same_or_a_weaker_mode_takes_no_second_lock() -> None:
    session = _Session()
    game_id = uuid4()
    acquire_sequence_ownership_lock(session, game_id=game_id)  # type: ignore[arg-type]
    acquire_sequence_ownership_lock(session, game_id=game_id)  # type: ignore[arg-type]
    acquire_sequence_ownership_lock(
        session,  # type: ignore[arg-type]
        game_id=game_id,
        mode=SequenceOwnershipLockMode.SHARED,
    )
    ensure_sequence_ownership_lock(session, game_id=game_id)  # type: ignore[arg-type]
    require_exclusive_sequence_ownership(session, game_id=game_id)  # type: ignore[arg-type]
    assert len(session.statements) == 1
    assert "pg_advisory_xact_lock(" in session.statements[0]
    assert held_sequence_ownership_lock(session, game_id=game_id) is (  # type: ignore[arg-type]
        SequenceOwnershipLockMode.EXCLUSIVE
    )


def test_shared_is_never_upgraded_to_exclusive() -> None:
    session = _Session()
    game_id = uuid4()
    acquire_sequence_ownership_lock(
        session,  # type: ignore[arg-type]
        game_id=game_id,
        mode=SequenceOwnershipLockMode.SHARED,
    )
    # A nested participant keeps the shared lock of the enclosing decision.
    ensure_sequence_ownership_lock(session, game_id=game_id)  # type: ignore[arg-type]
    for request in (
        lambda: acquire_sequence_ownership_lock(session, game_id=game_id),  # type: ignore[arg-type]
        lambda: require_exclusive_sequence_ownership(session, game_id=game_id),  # type: ignore[arg-type]
    ):
        with pytest.raises(ImageReviewConflictError) as error:
            request()
        assert error.value.code == SEQUENCE_OWNERSHIP_LOCK_UPGRADE
    assert len(session.statements) == 1
    assert "pg_advisory_xact_lock_shared(" in session.statements[0]


def test_the_registry_is_bound_to_the_transaction_and_the_game() -> None:
    session = _Session()
    game_id, other_game = uuid4(), uuid4()
    acquire_sequence_ownership_lock(
        session,  # type: ignore[arg-type]
        game_id=game_id,
        mode=SequenceOwnershipLockMode.SHARED,
    )
    # Another game has its own lock.
    acquire_sequence_ownership_lock(session, game_id=other_game)  # type: ignore[arg-type]
    # A new transaction (the previous one ended and released its locks) starts empty.
    session.transaction = object()
    assert held_sequence_ownership_lock(session, game_id=game_id) is None  # type: ignore[arg-type]
    acquire_sequence_ownership_lock(session, game_id=game_id)  # type: ignore[arg-type]
    assert len(session.statements) == 3
