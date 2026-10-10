"""Record the lock acquisitions of each transaction and check the global order.

TASK-0950 (audit round 4): a lightweight test helper. It listens to the SQL an
engine sends, classifies every lock (advisory locks by their key, row locks by
the locked tables) and keeps one list per database transaction. ``violations``
reports the inversions that produced the audited deadlocks:

* a job row locked after the ownership lock (P0-6);
* the ownership lock taken after a sequence, source, row, state or cell lock
  (P0-5);
* a new sequence lock after a source row lock;
* a source row locked after the counters state (P0-7);
* a source row and the counters state locked without the ownership lock
  (a non-participant, P0-7).

Re-locking something the transaction already holds never waits, so only the
first acquisition of each advisory key counts.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from game_predictor_api.storage.image_review_repository import _sequence_advisory_lock_key
from game_predictor_api.storage.sequence_ownership_lock import sequence_ownership_lock_key
from sqlalchemy import event
from sqlalchemy.engine import Engine

_TABLE_CATEGORIES = {
    "jobs": "job",
    "games": "game",
    "source_images": "source",
    "image_symbol_review_states": "state",
    "image_symbol_review_cells": "cells",
    # Control-plane routing lock of every game transaction, not part of the order.
    "game_storage_locations": "",
}
_FROM = re.compile(r"\b(?:FROM|JOIN)\s+(?:\w+\.)?(\w+)", re.IGNORECASE)
_OF = re.compile(r"FOR\s+UPDATE\s+OF\s+([\w\s,\.]+)", re.IGNORECASE)


@dataclass
class _Transaction:
    locks: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    advisory_keys: set[int] = field(default_factory=set)


@dataclass
class LockOrderLog:
    game_id: UUID
    sequence_keys: set[int]
    transactions: list[_Transaction] = field(default_factory=list)
    _open: dict[int, _Transaction] = field(default_factory=dict)
    _mutex: threading.Lock = field(default_factory=threading.Lock)

    def violations(self) -> list[str]:
        found: list[str] = []
        for index, transaction in enumerate(self.transactions):
            seen: set[str] = set()
            for lock in transaction.locks:
                if lock == "job" and "ownership" in seen:
                    found.append(f"tx{index}: job row after ownership {transaction.locks}")
                if lock == "ownership" and seen & {"sequence", "source", "rows", "state", "cells"}:
                    found.append(
                        f"tx{index}: ownership after {sorted(seen)} {transaction.locks} "
                        f"{transaction.tables}"
                    )
                if lock == "sequence" and "source" in seen:
                    found.append(f"tx{index}: new sequence after source {transaction.locks}")
                if lock == "source" and "state" in seen:
                    found.append(f"tx{index}: source after state {transaction.locks}")
                seen.add(lock)
            if {"source", "state"} <= seen and "ownership" not in seen:
                found.append(f"tx{index}: source and state without ownership {transaction.locks}")
        return found

    def categories(self) -> list[list[str]]:
        return [transaction.locks for transaction in self.transactions if transaction.locks]


def _locked_tables(statement: str) -> list[str]:
    match = _OF.search(statement)
    if match:
        return [name.strip().split(".")[-1] for name in match.group(1).split(",") if name.strip()]
    head = re.split(r"FOR\s+(?:UPDATE|SHARE|NO KEY UPDATE|KEY SHARE)", statement, flags=re.I)[0]
    return [name for name in _FROM.findall(head)]


def _row_categories(tables: list[str]) -> list[str]:
    categories = {_TABLE_CATEGORIES.get(table, "rows") for table in tables if table} - {""}
    order = ("job", "game", "source", "rows", "state", "cells")
    return [category for category in order if category in categories]


@contextmanager
def lock_order_probe(
    engine: Engine, *, game_id: UUID, sequence_numbers: Iterable[int] = ()
) -> Iterator[LockOrderLog]:
    log = LockOrderLog(
        game_id=game_id,
        sequence_keys={_sequence_advisory_lock_key(game_id, number) for number in sequence_numbers},
    )
    ownership_key = sequence_ownership_lock_key(game_id)

    def transaction_of(connection: Any) -> _Transaction:
        key = id(connection.connection.dbapi_connection)
        with log._mutex:
            current = log._open.get(key)
            if current is None:
                current = _Transaction()
                log._open[key] = current
                log.transactions.append(current)
            return current

    def close(connection: Any) -> None:
        key = id(connection.connection.dbapi_connection)
        with log._mutex:
            log._open.pop(key, None)

    def before(connection: Any, _cursor: Any, statement: str, parameters: Any, *_: Any) -> None:
        upper = statement.upper()
        if "PG_ADVISORY_XACT_LOCK" in upper:
            values = parameters.values() if isinstance(parameters, dict) else parameters or ()
            transaction = transaction_of(connection)
            for value in values:
                if not isinstance(value, int) or value in transaction.advisory_keys:
                    continue
                transaction.advisory_keys.add(value)
                if value == ownership_key:
                    transaction.locks.append("ownership")
                elif value in log.sequence_keys:
                    transaction.locks.append("sequence")
            return
        if "FOR UPDATE" in upper or "FOR SHARE" in upper:
            tables = _locked_tables(statement)
            transaction = transaction_of(connection)
            transaction.locks.extend(_row_categories(tables))
            transaction.tables.append(",".join(tables))

    event.listen(engine, "before_cursor_execute", before)
    event.listen(engine, "commit", close)
    event.listen(engine, "rollback", close)
    try:
        yield log
    finally:
        event.remove(engine, "before_cursor_execute", before)
        event.remove(engine, "commit", close)
        event.remove(engine, "rollback", close)


__all__ = ["LockOrderLog", "lock_order_probe"]
