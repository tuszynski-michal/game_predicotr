"""Run one ranked campaign for the operator-approved Mumie A2 grid (TASK-1265)."""

# ruff: noqa: E402 -- local operator entry point resolves the checked-out packages.
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]
for source in ("services/api/src", "services/worker/src"):
    sys.path.insert(0, str(ROOT / source))

from game_predictor_api.application.grid_reinference import digest
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain import mumie_suspicious_batch as policy
from game_predictor_api.domain.image_grid_reviews import (
    ImageGridReviewListFilter,
    ImageGridReviewView,
)
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.grid_reinference import SqlAlchemyGridReinferenceRepository
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from game_predictor_api.storage.image_grid_review_repository import (
    SqlAlchemyImageGridReviewRepository,
)


def ledger(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS control(id INTEGER PRIMARY KEY CHECK(id=1), paused INTEGER NOT NULL,
      scanned INTEGER NOT NULL, cursor INTEGER NOT NULL, sealed INTEGER NOT NULL);
    INSERT OR IGNORE INTO control VALUES(1,0,0,0,0);
    CREATE TABLE IF NOT EXISTS boards(sequence INTEGER PRIMARY KEY,
      score REAL NOT NULL, pin TEXT NOT NULL,
      batch TEXT, outcome TEXT);
    CREATE INDEX IF NOT EXISTS queue_order ON boards(batch,score DESC,sequence);
    CREATE TABLE IF NOT EXISTS batches(id TEXT PRIMARY KEY, operation TEXT, report TEXT);
    CREATE UNIQUE INDEX IF NOT EXISTS one_open_batch ON batches((1)) WHERE report IS NULL;
    """)
    return db


@contextmanager
def driver_lock(path: Path) -> Iterator[None]:
    # A separate SQLite write lock is released by the OS on exit, including a crash.
    # The control ledger remains writable for pause and readable for status.
    with closing(sqlite3.connect(path, timeout=0)) as lock:
        try:
            lock.execute("BEGIN IMMEDIATE")
        except sqlite3.OperationalError as exc:
            raise RuntimeError("Inny proces steruje już tą kolejką.") from exc
        yield


def reserve(db: sqlite3.Connection) -> str | None:
    with db:
        db.execute("BEGIN IMMEDIATE")
        active = db.execute("SELECT id FROM batches WHERE report IS NULL").fetchone()
        if active:
            return str(active[0])
        control = db.execute("SELECT * FROM control").fetchone()
        if control["paused"] or not control["sealed"]:
            return None
        rows = db.execute(
            "SELECT sequence,pin FROM boards WHERE batch IS NULL "
            "ORDER BY score DESC,sequence LIMIT 100"
        ).fetchall()
        if not rows:
            return None
        key = str(uuid5(policy.VERSION, digest([json.loads(r["pin"]) for r in rows])))
        db.execute("INSERT INTO batches(id) VALUES(?)", (key,))
        db.executemany(
            "UPDATE boards SET batch=? WHERE sequence=? AND batch IS NULL",
            [(key, r["sequence"]) for r in rows],
        )
        return key


def status(db: sqlite3.Connection) -> dict[str, Any]:
    ctrl = dict(db.execute("SELECT paused,scanned,sealed FROM control").fetchone())
    counts = dict(
        db.execute(
            "SELECT coalesce(outcome,case when batch is null then 'waiting' else 'in_batch' end),"
            "count(*) FROM boards GROUP BY 1"
        )
    )
    active = db.execute("SELECT id,operation FROM batches WHERE report IS NULL").fetchone()
    return {
        **ctrl,
        "boards": counts,
        "active": dict(active) if active else None,
        "finished": bool(ctrl["sealed"] and not active and not counts.get("waiting")),
    }


def scan_page(db: sqlite3.Connection, sessions: sessionmaker[Session], root: Path) -> None:
    cursor = db.execute("SELECT cursor FROM control").fetchone()[0]
    with sessions.begin() as session:
        SqlAlchemyGridReinferenceRepository(session, root).bind(policy.GAME, write=False)
        page = SqlAlchemyImageGridReviewRepository(session).list_grid_reviews(
            review_filter=ImageGridReviewListFilter(
                policy.GAME, ImageGridReviewView.SUSPICIOUS, None
            ),
            after_key=(cursor, "") if cursor else None,
            before_key=None,
            limit=500,
        )
        pins = [policy.board_pin(item) for item in page.items]
    with db:
        db.executemany(
            "INSERT INTO boards(sequence,score,pin) VALUES(?,?,?)",
            [(p["sequence"], p["score"], json.dumps(p)) for p in pins],
        )
        db.execute(
            "UPDATE control SET cursor=?,scanned=scanned+?,sealed=? WHERE id=1",
            (
                page.last_scanned_key[0] if page.last_scanned_key else cursor,
                page.scanned_count,
                int(not page.has_next),
            ),
        )


def finish(
    db: sqlite3.Connection,
    batch: str,
    pins: list[dict[str, Any]],
    outcomes: dict[str, str],
    report: str,
) -> None:
    if not report or not set(outcomes).issubset(p["review"] for p in pins):
        raise ValueError("Wyniki wykraczają poza zarezerwowaną partię.")
    with db:
        db.executemany(
            "UPDATE boards SET outcome=? WHERE batch=? AND sequence=?",
            [(outcomes.get(p["review"], "protected_or_stale"), batch, p["sequence"]) for p in pins],
        )
        db.execute("UPDATE batches SET report=? WHERE id=?", (report, batch))


def advance(
    db: sqlite3.Connection,
    sessions: sessionmaker[Session],
    root: Path,
    batch: str,
    *,
    retry: bool = False,
) -> str:
    pins = [
        json.loads(r[0])
        for r in db.execute(
            "SELECT pin FROM boards WHERE batch=? ORDER BY score DESC,sequence", (batch,)
        )
    ]
    op = db.execute("SELECT operation FROM batches WHERE id=?", (batch,)).fetchone()[0]
    with sessions.begin() as session:
        repo = SqlAlchemyGridReinferenceRepository(session, root)
        if op is None:
            view = repo.prepare(
                policy.GAME,
                {
                    "idempotencyKey": batch,
                    "suspiciousBatch": pins,
                    "selector": {"categories": ["unconfirmed"]},
                    "modelVersionId": str(policy.VERSION),
                    "executionScope": "pilot",
                },
                "local-admin:mumie-suspicious",
            )
        else:
            view = repo.get(policy.GAME, UUID(op))
        op = view["operationId"]
        phase = view["state"]
        command = {
            "expectedRevision": view["revision"],
            "idempotencyKey": str(uuid5(UUID(batch), f"{phase}:{view['revision']}")),
        }
        if phase in {"prepared", "frozen"}:
            action = "freeze" if phase == "prepared" else "start"
            repo.execute(
                policy.GAME,
                UUID(op),
                action,
                {**command, "manifestSha256": view["manifestSha256"]},
                "local-admin:mumie-suspicious",
            )
        elif phase in {"failed", "cancelled"}:
            if not retry:
                raise RuntimeError(
                    f"Partia {batch}, operacja {op}: {phase}. Po sprawdzeniu przyczyny użyj resume."
                )
            repo.execute(
                policy.GAME,
                UUID(op),
                "resume",
                {**command, "expectedPhase": view["phase"]},
                "local-admin:mumie-suspicious",
            )
        elif phase == "completed":
            rows = session.scalars(
                select(Target).where(Target.game_id == policy.GAME, Target.operation_id == UUID(op))
            ).all()
            outcomes = {row.snapshot["review"]["id"]: row.outcome for row in rows if row.outcome}
            if len(outcomes) != len(rows) or len(rows) != view["targetCount"]:
                raise ValueError("Brak pełnego rozliczenia zapisanych celów.")
    with db:
        db.execute("UPDATE batches SET operation=? WHERE id=?", (op, batch))
    if phase == "completed":
        finish(db, batch, pins, outcomes, view["reportSha256"])
        print(
            json.dumps(
                {
                    "batch": batch,
                    "operation": op,
                    "selected": len(pins),
                    "outcomes": view["outcomes"],
                    "protected_or_stale": len(pins) - len(outcomes),
                }
            ),
            flush=True,
        )
    return str(phase)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "pause", "resume", "status"))
    action = parser.parse_args().action
    settings = ApiSettings.from_environment()
    root = settings.artifact_root.resolve()
    directory = root / "mumie-suspicious-queue" / str(policy.VERSION)
    directory.mkdir(parents=True, exist_ok=True)
    with closing(ledger(directory / "queue.sqlite3")) as db:
        if action == "pause":
            with db:
                db.execute("UPDATE control SET paused=1")
        if action in {"status", "pause"}:
            print(json.dumps(status(db)))
            return
        with driver_lock(directory / "driver.sqlite3"), game_storage_scope(policy.GAME):
            if action == "resume":
                with db:
                    db.execute("UPDATE control SET paused=0")
            engine = create_database_engine(settings)
            sessions = create_session_factory(engine)
            try:
                retry = action == "resume"
                while True:
                    control = db.execute("SELECT paused,sealed FROM control").fetchone()
                    if not control["sealed"] and not control["paused"]:
                        scan_page(db, sessions, root)
                        continue
                    batch = reserve(db)
                    if not batch:
                        break
                    try:
                        state = advance(db, sessions, root, batch, retry=retry)
                    except JobConflictError as error:
                        if error.code != "GAME_JOB_ADMISSION_CONFLICT":
                            raise
                        # Preserve the same reservation while another image job finishes.
                        if db.execute("SELECT paused FROM control").fetchone()[0]:
                            break
                        time.sleep(3)
                        continue
                    retry = False
                    if state in {"preparing", "queued", "running", "cancel_requested"}:
                        time.sleep(3)
                print(json.dumps(status(db)))
            finally:
                engine.dispose()


if __name__ == "__main__":
    main()
