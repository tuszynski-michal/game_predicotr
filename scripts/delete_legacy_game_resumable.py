"""Preview/resume the pinned legacy game deletion; never touch operator JPEGs.

Preview is the default and prints JSON. Execution needs the exact preview SHA
and confirmation. A bounded invocation yields after --max-steps (default 100).
Run the same command again to resume committed progress.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine
from game_predictor_api.storage.game_deletion_policy_v1 import (
    DEFAULT_ARCHIVE,
    LEGACY_ID,
    SELF_LINKS,
    DeletionError,
    deletion_order,
    digest,
)
from game_predictor_api.storage.game_deletion_repository import (
    GameDeletionRepository,
    load_schema,
    transaction_limits,
)
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


def archive_fingerprint(path: Path) -> dict[str, Any]:
    """Verify the existing small SQLite archive, read-only and within 30 s."""
    deadline = time.monotonic() + 30
    resolved = path.resolve(strict=True)
    before = resolved.stat()
    if resolved.suffix.lower() != ".sqlite3":
        raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "SQLite archive required")
    sha = hashlib.sha256()
    with resolved.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            if time.monotonic() > deadline:
                raise DeletionError("GAME_DELETE_ARCHIVE_TIMEOUT", str(resolved))
            sha.update(chunk)
    with sqlite3.connect(resolved.as_uri() + "?mode=ro", uri=True, timeout=5) as connection:
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        metadata = {
            k: json.loads(v) for k, v in connection.execute("SELECT key,value FROM metadata")
        }
        if metadata.get("archiveVersion") != 1 or metadata.get("sourceGameId") != LEGACY_ID:
            raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Archive owner/version mismatch")
        if metadata.get("topology") != {"rows": 3, "columns": 5} or metadata.get("cellCount") != 15:
            raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Expected canonical 3x5 topology")
        symbols = list(
            connection.execute(
                "SELECT mobile_code,code,display_name FROM symbols ORDER BY mobile_code"
            )
        )
        known_codes = {row[0] for row in symbols} | {0}
        layout_sha = hashlib.sha256()
        for sequence, status, blob in connection.execute(
            "SELECT sequence_number,status,primary_mobile_codes FROM layouts "
            "ORDER BY sequence_number"
        ):
            if time.monotonic() > deadline:
                raise DeletionError("GAME_DELETE_ARCHIVE_TIMEOUT", "Archive content verification")
            if len(blob) != 30 or not set(struct.unpack("<15h", blob)) <= known_codes:
                raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Invalid symbol layout")
            layout_sha.update(f"{int(sequence)}:{status}:".encode())
            layout_sha.update(blob)
        if layout_sha.hexdigest() != metadata.get("layoutFingerprint"):
            raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Layout fingerprint mismatch")
        count = connection.execute("SELECT count(*) FROM layouts").fetchone()[0]
        if count <= 0 or count != metadata.get("layoutCount"):
            raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Archive count mismatch")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DeletionError("GAME_DELETE_ARCHIVE_INVALID", "Archive integrity check failed")
    after = resolved.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ino,
    ):
        raise DeletionError("GAME_DELETE_ARCHIVE_CHANGED", "Archive changed while verifying")
    return {
        "sha256": sha.hexdigest(),
        "path": str(resolved),
        "layoutCount": count,
        "layoutFingerprint": layout_sha.hexdigest(),
        "symbolsSha256": digest(symbols),
    }


def progress(state: dict[str, Any], stages: tuple[str, ...] = ()) -> None:
    print(
        json.dumps(
            {
                "status": state["status"],
                "stageIndex": state["stage_index"],
                "stage": stages[state["stage_index"]]
                if state["stage_index"] < len(stages)
                else "database_done",
                "committedBatches": state["batch_sequence"],
                "deletedCounts": state["deleted_counts"],
                "totalRows": None,
                "lastError": state["failure_code"],
            }
        ),
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path(DEFAULT_ARCHIVE))
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-preview-sha256")
    parser.add_argument("--confirmation")
    parser.add_argument("--max-steps", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.max_steps <= 1000:
        parser.error("--max-steps must be between 1 and 1000")
    engine = create_database_engine(ApiSettings.from_environment())
    try:
        archive = archive_fingerprint(args.archive)
        repo = GameDeletionRepository(engine)
        report = repo.preview(archive)
        if not args.execute:
            print(json.dumps(report, indent=2))
            return 0 if report["ready"] else 2
        if args.expected_preview_sha256 != report["sha256"]:
            raise DeletionError("GAME_DELETE_PREVIEW_DRIFT", "Review the current preview first")
        repo.start(report, args.confirmation)
        with engine.begin() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            transaction_limits(connection)
            schema = load_schema(connection)
        stages = (
            ("unlink:games",)
            + tuple(f"unlink:{t}" for t in sorted(SELF_LINKS))
            + deletion_order(schema.foreign_keys)
        )
        repo.run(
            schema, max_steps=args.max_steps, on_progress=lambda state: progress(state, stages)
        )
        return 0
    except (DeletionError, DBAPIError, OSError, sqlite3.Error) as error:
        # DB driver messages can include payload values; report stable SQLSTATE only.
        code = (
            str(getattr(error.orig, "sqlstate", "DATABASE_ERROR"))
            if isinstance(error, DBAPIError)
            else str(error)
        )
        print(json.dumps({"status": "blocked", "error": code}), flush=True)
        return 2
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
