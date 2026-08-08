"""Run and time one real browser-contract image-selection acceptance flow.

The script mirrors the Admin workspace protocol while remaining suitable for a
long, unattended local run: bounded HTTP upload, durable job creation, polling,
and progressive collision-safe writes to the owner-selected output directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ADMIN_HEADERS = {"X-Admin-Intent": "local-owner"}
SUPPORTED_SUFFIXES = frozenset({".jpg", ".jpeg"})
TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled", "waiting_for_review"})
_NATURAL_PART = re.compile(r"(\d+)")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _natural_key(value: str) -> tuple[tuple[int, object], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in _NATURAL_PART.split(value)
        if part
    )


def _duration(started: float) -> float:
    return round(time.monotonic() - started, 3)


def _job_progress(job: dict[str, Any]) -> dict[str, object]:
    progress = job.get("progress")
    if not isinstance(progress, dict):
        raise RuntimeError("Image-selection job response is missing progress.")
    selection = progress.get("imageSelection")
    selection_progress = selection if isinstance(selection, dict) else {}
    return {
        "stage": progress.get("stage"),
        "current": progress.get("current"),
        "total": progress.get("total"),
        "groups": selection_progress.get("groups", 0),
        "selected": selection_progress.get("selected", 0),
        "manual": selection_progress.get("manual", 0),
        "skipped": selection_progress.get("skipped", 0),
        "errors": selection_progress.get("errors", 0),
        "verifications": selection_progress.get("verifications", 0),
    }


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        for attempt in range(8):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(0.05 * (attempt + 1))
    finally:
        temporary.unlink(missing_ok=True)


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    json_body: dict[str, object] | None = None,
    params: dict[str, str | int | float | bool | None] | None = None,
) -> dict[str, Any]:
    response = client.request(method, path, json=json_body, params=params)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"Unexpected JSON response for {method} {path}.")
    return payload


def _upload_one(
    client: httpx.Client,
    upload_id: str,
    index: int,
    source_root: Path,
    path: Path,
) -> int:
    relative = f"{source_root.name}/{path.relative_to(source_root).as_posix()}"
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with path.open("rb") as source:
                response = client.put(
                    f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/{index}",
                    content=source,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Image-Relative-Path": relative,
                    },
                )
            response.raise_for_status()
            return path.stat().st_size
        except (OSError, httpx.HTTPError) as error:
            last_error = error
            if attempt < 3:
                time.sleep(float(attempt))
    assert last_error is not None
    raise RuntimeError(f"Upload failed for file {index + 1}: {relative}") from last_error


def _all_groups(client: httpx.Client, run_id: str) -> list[dict[str, Any]]:
    after = -1
    result: list[dict[str, Any]] = []
    while True:
        page = _request_json(
            client,
            "GET",
            f"/api/v1/admin/image-selections/{run_id}/groups",
            params={"afterGroupOrder": after, "limit": 100},
        )
        items = page.get("items")
        if not isinstance(items, list):
            raise RuntimeError("Image-selection group page is invalid.")
        result.extend(item for item in items if isinstance(item, dict))
        next_after = page.get("nextAfterGroupOrder")
        if next_after is None:
            return result
        after = int(next_after)


def _save_ready_groups(
    client: httpx.Client,
    run_id: str,
    output_root: Path,
    saved_orders: set[int],
) -> tuple[int, int]:
    saved_now = 0
    groups = _all_groups(client, run_id)
    for group in sorted(groups, key=lambda item: int(item["groupOrder"])):
        group_order = int(group["groupOrder"])
        if group_order in saved_orders:
            continue
        if group.get("status") not in {"auto_selected", "manually_selected"}:
            continue
        range_start = group.get("rangeStart")
        range_end = group.get("rangeEnd")
        group_id = group.get("id")
        if range_start is None or range_end is None or not isinstance(group_id, str):
            continue
        file_name = f"seq_{int(range_start)}-{int(range_end)}.jpg"
        response = client.get(
            f"/api/v1/admin/image-selections/{run_id}/groups/{group_id}/selected-file"
        )
        response.raise_for_status()
        content = response.content
        destination = output_root / file_name
        if destination.exists():
            if (
                hashlib.sha256(destination.read_bytes()).digest()
                != hashlib.sha256(content).digest()
            ):
                raise RuntimeError(f"Output collision with different bytes: {destination}")
            saved_orders.add(group_order)
            continue
        with tempfile.NamedTemporaryFile(dir=output_root, prefix=".tmp-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        saved_orders.add(group_order)
        saved_now += 1
    return saved_now, len(groups)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--upload-workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument(
        "--resume-existing",
        action="store_true",
        help="Resume polling and progressive export from IDs stored in --report.",
    )
    return parser.parse_args()


def _resume_existing(options: argparse.Namespace) -> int:
    report = json.loads(options.report.read_text(encoding="utf-8"))
    run_id = str(report["runId"])
    selection_started_at = datetime.fromisoformat(str(report["selectionStartedAt"]))
    output_root = options.output.resolve(strict=True)
    saved_orders: set[int] = set()
    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(60.0, connect=10.0),
    ) as client:
        last_log = 0.0
        while True:
            current_run = _request_json(client, "GET", f"/api/v1/admin/image-selections/{run_id}")
            job = current_run["job"]
            progress = _job_progress(job)
            saved_now, group_count = _save_ready_groups(client, run_id, output_root, saved_orders)
            elapsed = round((datetime.now(UTC) - selection_started_at).total_seconds(), 3)
            report.update(
                {
                    "jobStatus": job["status"],
                    "jobStage": progress["stage"],
                    "progressCurrent": progress["current"],
                    "progressTotal": progress["total"],
                    "selectionCounters": {
                        key: progress[key]
                        for key in (
                            "groups",
                            "selected",
                            "manual",
                            "skipped",
                            "errors",
                            "verifications",
                        )
                    },
                    "groupCount": group_count,
                    "savedOutputFiles": len(saved_orders),
                    "selectionElapsedSeconds": elapsed,
                }
            )
            if saved_now or time.monotonic() - last_log >= 10:
                _write_report(options.report, report)
                print(
                    f"selection status={job['status']} stage={progress['stage']} "
                    f"progress={progress['current']}/{progress['total']} "
                    f"groups={group_count} saved={len(saved_orders)} elapsed={elapsed}s",
                    flush=True,
                )
                last_log = time.monotonic()
            if job["status"] in TERMINAL_STATUSES:
                report.update(
                    {
                        "status": "finished" if job["status"] == "completed" else job["status"],
                        "selectionFinishedAt": _utc_now(),
                        "selectionElapsedSeconds": elapsed,
                        "finishedAt": _utc_now(),
                        "errorCode": job.get("errorCode"),
                        "errorMessage": job.get("errorMessage"),
                    }
                )
                _write_report(options.report, report)
                return 0 if job["status"] in {"completed", "waiting_for_review"} else 1
            time.sleep(options.poll_seconds)


def main() -> int:
    options = _parse_args()
    if options.resume_existing:
        return _resume_existing(options)
    source_root = options.source.resolve(strict=True)
    output_root = options.output.resolve(strict=True)
    if source_root == output_root or source_root in output_root.parents:
        raise RuntimeError("Output directory must be separate from the source directory.")
    if any(output_root.iterdir()):
        raise RuntimeError("Output directory must be empty before the acceptance run.")
    files = sorted(
        (
            path
            for path in source_root.rglob("*")
            if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
        ),
        key=lambda path: _natural_key(path.relative_to(source_root).as_posix()),
    )
    if not files:
        raise RuntimeError("Source directory contains no JPEG files.")
    total_bytes = sum(path.stat().st_size for path in files)
    report: dict[str, object] = {
        "schemaVersion": 1,
        "status": "starting",
        "sourceDirectory": str(source_root),
        "outputDirectory": str(output_root),
        "gameId": options.game_id,
        "fileCount": len(files),
        "totalBytes": total_bytes,
        "uploadWorkers": options.upload_workers,
        "startedAt": _utc_now(),
        "uploadedFiles": 0,
        "uploadedBytes": 0,
        "savedOutputFiles": 0,
    }
    _write_report(options.report, report)
    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(60.0, connect=10.0),
    ) as client:
        upload_started = time.monotonic()
        report.update({"status": "uploading", "uploadStartedAt": _utc_now()})
        created = _request_json(
            client,
            "POST",
            "/api/v1/admin/image-imports/browser-selections",
            json_body={
                "displayName": source_root.name,
                "expectedFileCount": len(files),
                "expectedTotalBytes": total_bytes,
                "purpose": "photo_selection",
                "gameId": options.game_id,
            },
        )
        upload_id = str(created["uploadId"])
        report["uploadId"] = upload_id
        _write_report(options.report, report)
        last_log = time.monotonic()
        uploaded_files = 0
        uploaded_bytes = 0
        with ThreadPoolExecutor(max_workers=options.upload_workers) as executor:
            futures = {
                executor.submit(_upload_one, client, upload_id, index, source_root, path): index
                for index, path in enumerate(files)
            }
            for future in as_completed(futures):
                uploaded = future.result()
                uploaded_files += 1
                uploaded_bytes += uploaded
                report["uploadedFiles"] = uploaded_files
                report["uploadedBytes"] = uploaded_bytes
                if time.monotonic() - last_log >= 10:
                    report["uploadElapsedSeconds"] = _duration(upload_started)
                    _write_report(options.report, report)
                    print(
                        f"upload {report['uploadedFiles']}/{len(files)} "
                        f"elapsed={report['uploadElapsedSeconds']}s",
                        flush=True,
                    )
                    last_log = time.monotonic()
        finalized = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize",
        )
        upload_finished_at = _utc_now()
        report.update(
            {
                "uploadFinishedAt": upload_finished_at,
                "uploadElapsedSeconds": _duration(upload_started),
                "status": "creating_selection",
            }
        )
        _write_report(options.report, report)
        selection_started = time.monotonic()
        selection = _request_json(
            client,
            "POST",
            "/api/v1/admin/image-selections",
            json_body={
                "contractVersion": 1,
                "firstSequenceNumber": None,
                "gameId": options.game_id,
                "sequenceDirection": "ascending",
                "selectionToken": finalized["selectionToken"],
            },
        )
        run = selection["run"]
        run_id = str(run["id"])
        job_id = str(run["job"]["id"])
        report.update(
            {
                "status": "selecting",
                "selectionStartedAt": _utc_now(),
                "runId": run_id,
                "jobId": job_id,
            }
        )
        _write_report(options.report, report)
        saved_orders: set[int] = set()
        last_log = 0.0
        while True:
            current_run = _request_json(client, "GET", f"/api/v1/admin/image-selections/{run_id}")
            job = current_run["job"]
            progress = _job_progress(job)
            saved_now, group_count = _save_ready_groups(client, run_id, output_root, saved_orders)
            report.update(
                {
                    "jobStatus": job["status"],
                    "jobStage": progress["stage"],
                    "progressCurrent": progress["current"],
                    "progressTotal": progress["total"],
                    "selectionCounters": {
                        key: progress[key]
                        for key in (
                            "groups",
                            "selected",
                            "manual",
                            "skipped",
                            "errors",
                            "verifications",
                        )
                    },
                    "groupCount": group_count,
                    "savedOutputFiles": len(saved_orders),
                    "selectionElapsedSeconds": _duration(selection_started),
                }
            )
            if saved_now or time.monotonic() - last_log >= 10:
                _write_report(options.report, report)
                print(
                    f"selection status={job['status']} stage={progress['stage']} "
                    f"progress={progress['current']}/{progress['total']} "
                    f"groups={group_count} saved={len(saved_orders)} "
                    f"elapsed={report['selectionElapsedSeconds']}s",
                    flush=True,
                )
                last_log = time.monotonic()
            if job["status"] in TERMINAL_STATUSES:
                report.update(
                    {
                        "status": "finished" if job["status"] == "completed" else job["status"],
                        "selectionFinishedAt": _utc_now(),
                        "selectionElapsedSeconds": _duration(selection_started),
                        "finishedAt": _utc_now(),
                        "errorCode": job.get("errorCode"),
                        "errorMessage": job.get("errorMessage"),
                    }
                )
                _write_report(options.report, report)
                return 0 if job["status"] in {"completed", "waiting_for_review"} else 1
            time.sleep(options.poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"live image-selection acceptance failed: {error}", file=sys.stderr, flush=True)
        raise
