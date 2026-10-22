"""Preview/apply only the reviewed source-directory relocation (no schema changes).

Preview uses a read-only transaction. Apply requires the exact preview SHA,
complete preservation receipts, unchanged input files, inactive jobs and the
relocation-aware worker code. It locks/rechecks every row before the first
update and commits all paths atomically. It never changes manifests, sessions,
job statuses, input keys, checkpoints or game data.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any
from uuid import UUID

import psycopg
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_worker.images.source_ingestion import ManagedOriginalStore
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_legacy_copy_retirement import (  # noqa: E402
    checksum,
    fingerprint,
    legacy_values,
    ordinary_target,
)

CONTRACT = "legacy-job-path-relocation-v1"
SELECT_JOBS = (
    "select id::text,game_id::text,job_type::text,status::text,input_payload,"
    "checkpoint_payload,updated_at::text from public.jobs order by id"
)


def connect(*, readonly: bool) -> Any:
    url = make_url(ApiSettings.from_environment().owner_database_url)
    options = "-c statement_timeout=10000 -c lock_timeout=2000"
    if readonly:
        options += " -c default_transaction_read_only=on"
    return psycopg.connect(
        host=url.host,
        port=url.port or 5432,
        dbname=url.database,
        user=url.username,
        password=url.password,
        connect_timeout=5,
        options=options,
        row_factory=dict_row,
    )


def target_directory(value: str, source: str, destination: str) -> str:
    relative = PureWindowsPath(value).relative_to(PureWindowsPath(source))
    if ".." in relative.parts:
        raise ValueError("Parent traversal in source directory")
    return str(Path(destination).joinpath(*relative.parts))


def validate_current_row(before: dict[str, Any], current: dict[str, Any]) -> None:
    if current != before or current["status"] in {"created", "processing"}:
        raise ValueError(f"Job changed or can be claimed: {before['id']}")


def verify_input_receipts(plan: dict[str, Any]) -> None:
    summary_path = Path(plan["files_summary"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if not summary["complete"]:
        raise ValueError("File preservation is incomplete")
    if summary["source"] != plan["source"] or summary["destination"] != plan["destination"]:
        raise ValueError("File preservation roots differ from the preview")
    receipt_path = summary_path.parent / "files.sqlite"
    root = Path(plan["destination"])
    directories = sorted({item["after"] for item in plan["jobs"]})
    with sqlite3.connect(f"{receipt_path.as_uri()}?mode=ro", uri=True) as receipt:
        for index, directory in enumerate(directories, 1):
            relative = Path(directory).relative_to(root).as_posix().rstrip("/") + "/"
            records = receipt.execute(
                "select relative,size,copy_path,copy_mtime,kind,sha256 from files "
                "where relative>=? and relative<?",
                (relative, relative + "\uffff"),
            ).fetchall()
            if not records:
                raise ValueError(f"No verified source inventory: {directory}")

            def verify_record(record: tuple[Any, ...]) -> None:
                path, size, copy_path, mtime, kind, expected_sha = record
                candidate = ordinary_target(root, path)
                if kind != "active_copy" or candidate != Path(copy_path):
                    raise ValueError(f"Source requires recovery before relocation: {path}")
                if fingerprint(candidate) != (size, int(mtime)):
                    raise ValueError(f"Input changed since preservation: {path}")
                if checksum(candidate) != expected_sha:
                    raise ValueError(f"Input checksum changed since preservation: {path}")

            with ThreadPoolExecutor(max_workers=16) as pool:
                for offset in range(0, len(records), 64):
                    futures = [
                        pool.submit(verify_record, record)
                        for record in records[offset : offset + 64]
                    ]
                    for future in futures:
                        future.result()
            print(f"verified_input_directory={index}/{len(directories)}", flush=True)


def verify_worker(plan: dict[str, Any]) -> None:
    store = ManagedOriginalStore(Path(plan["destination"]) / "artifacts")
    for item in plan["jobs"]:
        before = item["before"]
        job = create_job(
            JobType(before["job_type"]),
            game_id=UUID(before["game_id"]),
            input_payload=item["after_payload"],
            created_at=datetime.now(UTC),
        )
        job = replace(job, id=UUID(before["id"]))
        manifest_path = (
            Path(plan["destination"]) / "artifacts/data/originals/manifests" / f"{job.id}.json"
        )
        if manifest_path.is_file():
            loaded = store.load_existing_manifest(job)
            if loaded.source_directory != Path(item["after"]):
                raise ValueError("Deploy the relocation-aware worker before migrating job paths")


def preview(source: Path, destination: Path, files_summary: Path) -> dict[str, Any]:
    jobs: list[dict[str, Any]] = []
    blockers: list[str] = []
    with connect(readonly=True) as connection:
        connection.execute("set transaction isolation level repeatable read")
        for row in connection.execute(SELECT_JOBS).fetchall():
            paths = list(legacy_values(row["input_payload"], str(source), "input_payload"))
            paths += list(legacy_values(row["checkpoint_payload"], str(source), "checkpoint"))
            if not paths:
                continue
            if [key for key, _value in paths] != ["input_payload.source_directory"]:
                blockers.append(f"Unhandled nested source path in {row['id']}")
                continue
            if row["status"] in {"created", "processing"}:
                blockers.append(f"Active job {row['id']}")
            after = target_directory(paths[0][1], str(source), str(destination))
            after_payload = {**row["input_payload"], "source_directory": after}
            if "source_directory_relocation" in row["input_payload"]:
                blockers.append(f"Job already has a relocation receipt: {row['id']}")
            after_payload["source_directory_relocation"] = {
                "contract_version": 1,
                "previous": paths[0][1],
                "current": after,
            }
            jobs.append({"before": row, "after": after, "after_payload": after_payload})
        sessions = []
        for row in connection.execute(
            "select id::text,status,host_base_path,expires_at::text "
            "from public.remote_manual_selection_sessions order by id"
        ).fetchall():
            if not list(legacy_values(row["host_base_path"], str(source))):
                continue
            counts = {}
            for table in (
                "collections",
                "batches",
                "files",
                "operations",
                "transfers",
                "host_actions",
            ):
                counts[table] = connection.execute(
                    "select count(*) as n from public.remote_manual_selection_"
                    + table
                    + " where session_id=%s::uuid",
                    (row["id"],),
                ).fetchone()["n"]
            expired = datetime.fromisoformat(row["expires_at"]) <= datetime.now(UTC)
            if any(counts.values()) or (row["status"] in {"draft", "active"} and not expired):
                blockers.append(f"Live or nonempty remote-selection binding {row['id']}")
            sessions.append({**row, "expired": expired, "counts": counts})
    plan: dict[str, Any] = {
        "contract": CONTRACT,
        "source": str(source),
        "destination": str(destination),
        "files_summary": str(files_summary),
        "jobs": jobs,
        "sessions_unchanged": sessions,
        "blockers": blockers,
        "counts": dict(Counter(item["before"]["status"] for item in jobs)),
    }
    try:
        verify_input_receipts(plan)
        plan["files_ready"] = True
    except (OSError, ValueError, sqlite3.Error) as error:
        plan["files_ready"] = False
        blockers.append(str(error))
    return plan


def apply(plan_path: Path, expected_sha256: str) -> int:
    content = plan_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise ValueError("Preview SHA-256 differs from the approved preview")
    plan = json.loads(content)
    if plan["contract"] != CONTRACT or plan["blockers"] or not plan["files_ready"]:
        raise ValueError("Preview has unresolved blockers")
    verify_input_receipts(plan)
    verify_worker(plan)
    before_by_id = {item["before"]["id"]: item["before"] for item in plan["jobs"]}
    with connect(readonly=False) as connection:
        # All row locks and comparisons precede the first UPDATE. NOWAIT avoids
        # waiting for an operator/worker operation and then using stale evidence.
        rows = connection.execute(
            SELECT_JOBS.replace(
                "order by id", "where id=any(%s::uuid[]) order by id for update nowait"
            ),
            (list(before_by_id),),
        ).fetchall()
        if len(rows) != len(before_by_id):
            raise ValueError("A previewed job disappeared")
        for row in rows:
            validate_current_row(before_by_id[row["id"]], row)
        # A lost API/CLI response is safe: a second invocation fails closed on
        # the changed before-values; the caller can inspect the committed rows.
        for item in plan["jobs"]:
            connection.execute(
                "update public.jobs set input_payload=%s::json,updated_at=now() where id=%s::uuid",
                (json.dumps(item["after_payload"]), item["before"]["id"]),
            )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("preview")
    prepare.add_argument("--source", type=Path, required=True)
    prepare.add_argument("--destination", type=Path, required=True)
    prepare.add_argument("--files-summary", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    execute = commands.add_parser("apply")
    execute.add_argument("--plan", type=Path, required=True)
    execute.add_argument("--approve-sha256", required=True)
    args = parser.parse_args()
    if args.command == "apply":
        print(f"updated_jobs={apply(args.plan, args.approve_sha256)}")
    else:
        plan = preview(args.source, args.destination, args.files_summary)
        content = json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8")
        args.output.write_bytes(content)
        print(json.dumps({"counts": plan["counts"], "blockers": plan["blockers"]}))
        print("preview_sha256=" + hashlib.sha256(content).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
