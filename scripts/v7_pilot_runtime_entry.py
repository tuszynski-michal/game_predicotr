"""Background entry for one recorded, isolated R3 process; launched hidden by PowerShell."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".claude" / "v7-pilot-runtime"


def _runtime_lock(role: str) -> BinaryIO:
    """Hold a kernel file lock for the process lifetime, including direct entry starts."""
    import msvcrt

    lock = (RUNTIME / f"process-{role}.live.lock").open("a+b")
    if lock.tell() == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        lock.close()
        raise ValueError("This role already has a live task-owned process.") from None
    return lock


def api_factory(scope: str) -> str:
    if scope not in ("real_pilot", "technical_fixture"):
        raise ValueError("Unknown pilot composition.")
    function = "create_fixture_app" if scope == "technical_fixture" else "create_operator_app"
    return f"scripts.v7_pilot_fixture_app:{function}"


def check_ready(role: str, token: UUID | None = None) -> dict[str, object]:
    """Actual runtime identity/head and optional own-worker heartbeat, without inference."""
    from game_predictor_api.domain.worker_lanes import WorkerLaneName
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from scripts.prepare_v7_reviewed_pilot import DATABASE, HEAD, ROLE, _engine, _load

    settings = _load()
    engine = _engine(make_url(str(settings["databaseUrl"])))
    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()
            head = connection.scalar(text("SELECT version_num FROM public.alembic_version"))
            ready = (
                settings["phase"] == "ready"
                and tuple(identity) == (DATABASE, ROLE)
                and head == HEAD
            )
            if role == "worker":
                ready = ready and bool(
                    connection.scalar(
                        text(
                            "SELECT EXISTS(SELECT 1 FROM public.worker_lane_runtime "
                            "WHERE lane=:lane AND instance_token=:token "
                            "AND stopped_at IS NULL "
                            "AND heartbeat_at >= now() - interval '10 seconds')"
                        ),
                        {"lane": WorkerLaneName.IMAGE_SELECTION.value, "token": token},
                    )
                )
            return {"ready": ready, "database": DATABASE, "head": head, "role": role}
    finally:
        engine.dispose()


def check_stop(role: str) -> dict[str, object]:
    """Read-only safety proof before stopping a verified task-owned process."""
    from sqlalchemy import text
    from sqlalchemy.engine import make_url

    from scripts.prepare_v7_reviewed_pilot import DATABASE, ROLE, _engine, _load
    from scripts.v7_pilot_fixture_app import fixture_environment

    settings = _load()
    environment = fixture_environment()
    if (
        settings["phase"] != "ready"
        or environment["GAME_PREDICTOR_V7_LABEL_GEOMETRY_READ_ONLY"] != "true"
    ):
        raise ValueError("Stop requires the isolated read-only calibration composition.")
    engine = _engine(make_url(str(settings["databaseUrl"])))
    try:
        with engine.connect() as connection:
            identity = connection.execute(text("SELECT current_database(), current_user")).one()
            processing = connection.scalar(
                text("SELECT count(*) FROM public.jobs WHERE status='processing'")
            )
            if tuple(identity) != (DATABASE, ROLE) or (role == "worker" and processing != 0):
                raise ValueError("Stop refused: identity differs or the worker owns active work.")
            return {
                "status": "safe_to_stop",
                "role": role,
                "database": DATABASE,
                "calibrationReadOnly": True,
                "processingJobs": processing,
                "pendingOutputsRemainDurable": True,
            }
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", choices=("api", "worker", "admin"), required=True)
    parser.add_argument("--launch-token", type=UUID)
    parser.add_argument("--check-stop", action="store_true")
    parser.add_argument("--check-ready", action="store_true")
    parser.add_argument(
        "--scope", choices=("real_pilot", "technical_fixture"), default="real_pilot"
    )
    args = parser.parse_args()
    sys.path.insert(0, str(ROOT))
    if args.check_stop:
        print(json.dumps(check_stop(args.role)))
        return 0
    if args.check_ready:
        print(json.dumps(check_ready(args.role, args.launch_token)))
        return 0
    if args.launch_token is None:
        parser.error("--launch-token is required for a process launch")
    with _runtime_lock(args.role):
        return run_process(args.role, args.launch_token, args.scope)


def run_process(role: str, launch_token: UUID, scope: str) -> int:
    from scripts.prepare_v7_reviewed_pilot import _load
    from scripts.v7_pilot_fixture_app import fixture_environment

    settings = _load()
    if settings["phase"] != "ready":
        raise ValueError("Isolated role/schema readiness is required before runtime launch.")
    os.environ.update(fixture_environment(scope))
    if not check_ready("api")["ready"]:
        raise ValueError("Actual isolated database identity/head readiness failed.")
    registry = RUNTIME / f"process-{role}.json"
    record = {
        "task": "TASK-0853",
        "role": role,
        "scope": scope,
        "pid": os.getpid(),
        "launchToken": str(launch_token),
        "worktree": str(ROOT),
        "entryPath": str(Path(__file__).resolve()),
        "startedAtUtc": datetime.now(UTC).isoformat(),
        "databaseName": "game_predictor_v7_pilot",
        "runtimeRole": "game_predictor_v7_pilot_app",
        "status": "starting",
    }
    temporary = registry.with_suffix(".tmp")
    temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
    temporary.replace(registry)
    print(
        json.dumps(
            {
                "role": role,
                "scope": scope,
                "pid": os.getpid(),
                "databaseName": record["databaseName"],
            }
        ),
        flush=True,
    )
    if role == "api":
        import uvicorn

        uvicorn.run(
            api_factory(scope),
            factory=True,
            host="127.0.0.1",
            port=8020,
        )
        return 0
    if role == "worker":
        from game_predictor_worker.cli import main as worker_main

        return worker_main(
            [
                "--poll",
                "--lane",
                "image-selection",
                "--poll-interval",
                "0.5",
                "--cpu-thread-budget",
                "1",
                "--lane-instance-token",
                str(launch_token),
                "--worker-id",
                f"TASK-0853-{launch_token}",
                "--artifact-root",
                str(RUNTIME / "artifacts"),
            ]
        )
    node = shutil.which("node")
    if node is None:
        raise ValueError("Configured Node runtime is unavailable.")
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GAME_PREDICTOR_")
    }
    # The isolated Next server forwards the same /api/v1 contract to API 8020.
    environment["NEXT_PUBLIC_ADMIN_API_BASE_URL"] = "http://127.0.0.1:3020"
    environment["GAME_PREDICTOR_ADMIN_WORKSPACE_ROOT"] = str(ROOT)
    # This child is a long-lived server under the parent's PID/token registry.
    return subprocess.run(
        [
            node,
            str(ROOT / "node_modules" / "next" / "dist" / "bin" / "next"),
            "dev",
            "--hostname",
            "127.0.0.1",
            "--port",
            "3020",
        ],
        cwd=ROOT / "apps" / "admin",
        env=environment,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
