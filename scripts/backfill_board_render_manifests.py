"""Preview or execute the per-board render manifest backfill (D-467, TASK-0757).

``--preview`` is read-only: category counts plus an optional in-memory
validation sample (no writes).  ``--execute`` inserts manifests in committed
batches, resumable from a checkpoint under the artifact root; refused boards
are appended to a JSONL report next to the checkpoint.  A repeated run skips
existing manifests.

Examples (repository root)::

    .venv\\Scripts\\python.exe scripts/backfill_board_render_manifests.py \\
        --game-id <uuid> --preview --sample-boards 100
    .venv\\Scripts\\python.exe scripts/backfill_board_render_manifests.py \\
        --game-id <uuid> --execute --max-seconds 100
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.board_render_manifest_backfill import (
    DEFAULT_BATCH_SIZE,
    MAX_BATCH_SIZE,
    BackfillBatchResult,
    preview_counts,
    run_batch,
    run_game,
)
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.schema_readiness import require_alembic_head
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

CHECKPOINT_SCHEMA = "board-render-manifest-backfill-checkpoint-v1"
DEFAULT_MIN_FREE_GB = 10.0
# PostgreSQL runs in Docker Desktop; its data grows docker_data.vhdx on this disk.
_DOCKER_DISK = Path(os.environ.get("LOCALAPPDATA", "")) / "Docker" / "wsl" / "disk"


class DiskSpaceError(RuntimeError):
    code = "BOARD_RENDER_MANIFEST_DISK_SPACE_LOW"


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true", help="Read-only counts (no writes).")
    mode.add_argument("--execute", action="store_true", help="Insert manifests in batches.")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--sample-boards",
        type=int,
        default=0,
        help="Preview only: validate this many boards in memory (read-only).",
    )
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--max-seconds", type=float, default=None)
    parser.add_argument(
        "--min-free-gb",
        type=float,
        default=DEFAULT_MIN_FREE_GB,
        help="Execute only: refuse or stop when the database disk has less free space.",
    )
    parser.add_argument(
        "--disk-path",
        type=Path,
        default=None,
        help="Path on the database disk (default: Docker Desktop WSL disk, else artifact root).",
    )
    parser.add_argument(
        "--restart", action="store_true", help="Ignore the checkpoint and scan from the start."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Checkpoint path (default: <artifact root>/data/exports/"
        "board-render-manifest-backfill/<game id>/checkpoint.json).",
    )
    arguments = parser.parse_args(argv)
    if not 1 <= arguments.batch_size <= MAX_BATCH_SIZE:
        parser.error(f"--batch-size must be between 1 and {MAX_BATCH_SIZE}")
    if arguments.sample_boards < 0 or (arguments.execute and arguments.sample_boards):
        parser.error("--sample-boards is a non-negative preview-only option")
    return arguments


def _checkpoint_path(settings: ApiSettings, arguments: argparse.Namespace) -> Path:
    if arguments.checkpoint is not None:
        return Path(arguments.checkpoint).resolve()
    return (
        settings.artifact_root
        / "data"
        / "exports"
        / "board-render-manifest-backfill"
        / str(arguments.game_id)
        / "checkpoint.json"
    )


def _read_checkpoint(path: Path, game_id: UUID) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != CHECKPOINT_SCHEMA or payload.get("gameId") != str(game_id):
        raise ValueError(f"Checkpoint {path} belongs to another game or schema.")
    return dict(payload)


def _write_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def _free_gb(path: Path) -> float:
    return shutil.disk_usage(path).free / 1024**3


def _disk_path(settings: ApiSettings, arguments: argparse.Namespace) -> Path:
    if arguments.disk_path is not None:
        return Path(arguments.disk_path)
    return _DOCKER_DISK if _DOCKER_DISK.is_dir() else Path(settings.artifact_root.anchor)


def _require_free_space(path: Path, minimum_gb: float) -> float:
    free = _free_gb(path)
    if free < minimum_gb:
        raise DiskSpaceError(
            f"BOARD_RENDER_MANIFEST_DISK_SPACE_LOW: {free:.1f} GB free on {path}, "
            f"--min-free-gb is {minimum_gb:.1f}."
        )
    return free


def _preview(settings: ApiSettings, arguments: argparse.Namespace) -> dict[str, object]:
    engine = create_database_engine(settings)
    try:
        require_alembic_head(engine)
    except Exception:
        engine.dispose()
        raise
    # A plain session: the preview binds the game store for READ explicitly,
    # and every transaction is READ ONLY, so no statement can write.
    factory: sessionmaker[Session] = sessionmaker(bind=engine, expire_on_commit=False)
    started = time.monotonic()
    try:
        with factory() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            counts = preview_counts(session, arguments.game_id)
            session.rollback()
        counts_seconds = time.monotonic() - started
        sample: dict[str, object] | None = None
        if arguments.sample_boards:
            sample_started = time.monotonic()
            with factory() as session:
                session.execute(text("SET TRANSACTION READ ONLY"))
                result = run_batch(
                    session,
                    arguments.game_id,
                    after_board_id=None,
                    batch_size=arguments.sample_boards,
                    write=False,
                )
                session.rollback()
            built = result.counts["built_revision_zero"] + result.counts["copied"]
            sample = {
                "scanned": result.scanned,
                "counts": dict(result.counts),
                "refused": [board.to_dict() for board in result.refused[:20]],
                "averageManifestCanonicalJsonBytes": (
                    round(result.manifest_bytes / built) if built else None
                ),
                "elapsedSeconds": round(time.monotonic() - sample_started, 3),
            }
    finally:
        engine.dispose()
    return {
        "mode": "preview",
        "gameId": str(arguments.game_id),
        "counts": counts,
        "countsElapsedSeconds": round(counts_seconds, 3),
        "sample": sample,
    }


def _execute(settings: ApiSettings, arguments: argparse.Namespace) -> dict[str, object]:
    checkpoint_path = _checkpoint_path(settings, arguments)
    refused_path = checkpoint_path.with_name("refused.jsonl")
    checkpoint = None if arguments.restart else _read_checkpoint(checkpoint_path, arguments.game_id)
    totals: Counter[str] = Counter(dict(checkpoint.get("counts", {})) if checkpoint else {})
    after = (
        UUID(str(checkpoint["lastBoardId"]))
        if checkpoint is not None and checkpoint.get("lastBoardId")
        else None
    )
    run_counts: Counter[str] = Counter()
    disk_path = _disk_path(settings, arguments)
    free_at_start = _require_free_space(disk_path, arguments.min_free_gb)

    def persist(result: BackfillBatchResult, *, completed: bool = False) -> None:
        totals.update(result.counts)
        totals["scanned"] += result.scanned
        run_counts.update(result.counts)
        run_counts["scanned"] += result.scanned
        if result.refused:
            refused_path.parent.mkdir(parents=True, exist_ok=True)
            with refused_path.open("a", encoding="utf-8") as report:
                for board in result.refused:
                    report.write(json.dumps(board.to_dict(), sort_keys=True) + "\n")
        _write_checkpoint(
            checkpoint_path,
            {
                "schema": CHECKPOINT_SCHEMA,
                "gameId": str(arguments.game_id),
                "lastBoardId": None if result.last_board_id is None else str(result.last_board_id),
                "completed": completed,
                "counts": dict(totals),
                "updatedAt": datetime.now(UTC).isoformat(),
            },
        )
        if not completed:
            # Stop after the committed, checkpointed batch; a rerun resumes.
            _require_free_space(disk_path, arguments.min_free_gb)

    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    started = time.monotonic()
    try:
        require_alembic_head(engine)
        last, exhausted = run_game(
            factory,
            arguments.game_id,
            after_board_id=after,
            batch_size=arguments.batch_size,
            max_batches=arguments.max_batches,
            max_seconds=arguments.max_seconds,
            on_batch=persist,
        )
    finally:
        engine.dispose()
    if exhausted:
        persist(BackfillBatchResult(last_board_id=last), completed=True)
    return {
        "mode": "execute",
        "gameId": str(arguments.game_id),
        "completed": exhausted,
        "lastBoardId": None if last is None else str(last),
        "thisRun": dict(run_counts),
        "cumulative": dict(totals),
        "checkpoint": str(checkpoint_path),
        "refusedReport": str(refused_path),
        "freeGbAtStart": round(free_at_start, 1),
        "elapsedSeconds": round(time.monotonic() - started, 3),
    }


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    settings = ApiSettings.from_environment()
    report = _preview(settings, arguments) if arguments.preview else _execute(settings, arguments)
    json.dump(report, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
