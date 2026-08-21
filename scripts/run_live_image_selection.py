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
READY_GROUP_STATUSES = frozenset({"auto_selected", "manually_selected", "range_confirmed"})
GROUP_STATUSES = (
    "collecting",
    "auto_selected",
    "manual_required",
    "manually_selected",
    "missing_image",
    "skipped_existing_range",
    "range_required",
    "range_confirmed",
    "skipped_unreadable",
    "rejected_by_user",
)
_NATURAL_PART = re.compile(r"(\d+)")
_SEQUENCE_OUTPUT = re.compile(r"^seq_([1-9][0-9]*)-([1-9][0-9]*)\.jpg$")


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
        "rangeRequired": selection_progress.get("rangeRequired", 0),
        "skipped": selection_progress.get("skipped", 0),
        "errors": selection_progress.get("errors", 0),
        "verifications": selection_progress.get("verifications", 0),
    }


def _job_error(job: dict[str, Any]) -> tuple[object | None, object | None]:
    error = job.get("error")
    if not isinstance(error, dict):
        return None, None
    return error.get("code"), error.get("message")


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


def _groups_after(
    client: httpx.Client,
    run_id: str,
    *,
    after_group_order: int,
) -> tuple[list[dict[str, Any]], int]:
    # Read exactly one bounded page per polling cycle. During a fast run the
    # worker can append groups quicker than an unbounded pagination loop can
    # reach the moving end, which would starve progressive file export.
    page = _request_json(
        client,
        "GET",
        f"/api/v1/admin/image-selections/{run_id}/groups",
        params={"afterGroupOrder": after_group_order, "limit": 100},
    )
    items = page.get("items")
    if not isinstance(items, list):
        raise RuntimeError("Image-selection group page is invalid.")
    page_items = [item for item in items if isinstance(item, dict)]
    export_cursor = after_group_order
    if page_items:
        export_cursor = max(
            export_cursor,
            *(int(item["groupOrder"]) for item in page_items),
        )
    return page_items, export_cursor


def _save_ready_groups(
    client: httpx.Client,
    run_id: str,
    output_root: Path,
    saved_orders: set[int],
    *,
    after_group_order: int,
) -> tuple[int, int]:
    saved_now = 0
    groups, export_cursor = _groups_after(
        client,
        run_id,
        after_group_order=after_group_order,
    )
    for group in sorted(groups, key=lambda item: int(item["groupOrder"])):
        group_order = int(group["groupOrder"])
        if group_order in saved_orders:
            continue
        if group.get("status") not in READY_GROUP_STATUSES:
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
    return saved_now, export_cursor


def _drain_ready_groups(
    client: httpx.Client,
    run_id: str,
    output_root: Path,
    saved_orders: set[int],
    *,
    after_group_order: int,
) -> tuple[int, int]:
    """Reconcile every remaining page after the run becomes terminal."""

    saved_total = 0
    export_cursor = after_group_order
    while True:
        saved_now, next_cursor = _save_ready_groups(
            client,
            run_id,
            output_root,
            saved_orders,
            after_group_order=export_cursor,
        )
        saved_total += saved_now
        if next_cursor == export_cursor:
            return saved_total, export_cursor
        export_cursor = next_cursor


def _all_groups(
    client: httpx.Client,
    run_id: str,
) -> tuple[list[dict[str, Any]], int]:
    groups: list[dict[str, Any]] = []
    cursor = -1
    while True:
        page, next_cursor = _groups_after(
            client,
            run_id,
            after_group_order=cursor,
        )
        groups.extend(page)
        if next_cursor == cursor:
            return groups, cursor
        cursor = next_cursor


def _expected_ranges(run: dict[str, Any]) -> list[tuple[int, int]] | None:
    first = run.get("firstSequenceNumber")
    last = run.get("lastSequenceNumber")
    direction = run.get("sequenceDirection")
    if not isinstance(first, int) or not isinstance(last, int):
        return None
    if direction == "ascending" and last >= first:
        return [(start, min(last, start + 8)) for start in range(first, last + 1, 9)]
    if direction == "descending" and first >= last:
        return [(max(last, end - 8), end) for end in range(first, last - 1, -9)]
    return None


def _selection_coverage(
    run: dict[str, Any],
    groups: list[dict[str, Any]],
) -> dict[str, object]:
    status_counts = {status: 0 for status in GROUP_STATUSES}
    for group in groups:
        status = group.get("status")
        if isinstance(status, str):
            status_counts[status] = status_counts.get(status, 0) + 1

    owners = [group for group in groups if group.get("status") != "skipped_existing_range"]
    duplicates = len(groups) - len(owners)
    proof_first = run.get("selectorVersion") in {
        "fast-image-selector-v10.19",
        "fast-image-selector-v10.20",
    }
    expected_ranges = _expected_ranges(run)
    expected_count = run.get("expectedGroupCount")
    if not isinstance(expected_count, int) and expected_ranges is not None:
        expected_count = len(expected_ranges)

    owner_ranges = [
        (int(group["rangeStart"]), int(group["rangeEnd"]))
        for group in owners
        if isinstance(group.get("rangeStart"), int) and isinstance(group.get("rangeEnd"), int)
    ]
    range_counts: dict[tuple[int, int], int] = {}
    for item in owner_ranges:
        range_counts[item] = range_counts.get(item, 0) + 1
    expected_set = set(expected_ranges or ())
    missing = [item for item in expected_ranges or () if range_counts.get(item, 0) == 0]
    duplicate_ranges = sorted(item for item, count in range_counts.items() if count > 1)
    off_grid = sorted(item for item in range_counts if item not in expected_set)
    ordered_ranges_match = expected_ranges is not None and owner_ranges == expected_ranges
    automatic_groups = [group for group in owners if group.get("status") == "auto_selected"]
    automatic_ranges_present = all(
        isinstance(group.get("rangeStart"), int) and isinstance(group.get("rangeEnd"), int)
        for group in automatic_groups
    )
    range_projection_conflict_free = bool(
        expected_ranges is not None
        and automatic_ranges_present
        and not duplicate_ranges
        and not off_grid
    )
    logical_coverage_valid = bool(
        isinstance(expected_count, int)
        and len(owners) == expected_count
        and duplicates == len(groups) - expected_count
        and len(owner_ranges) == len(owners)
        and not missing
        and not duplicate_ranges
        and not off_grid
        and ordered_ranges_match
    )
    return {
        "physicalGroups": len(groups),
        "expectedLogicalGroups": expected_count,
        "logicalGroups": len(owners),
        "resolvedRangeGroups": len(owner_ranges),
        "duplicateGroups": duplicates,
        "provenAutomaticGroups": len(automatic_groups),
        "manuallyConfirmedGroups": sum(
            status_counts.get(status, 0) for status in ("manually_selected", "range_confirmed")
        ),
        "unresolvedRangeGroups": sum(
            1
            for group in owners
            if not isinstance(group.get("rangeStart"), int)
            or not isinstance(group.get("rangeEnd"), int)
        ),
        "unreadableOrRejectedGroups": sum(
            status_counts.get(status, 0)
            for status in ("missing_image", "skipped_unreadable", "rejected_by_user")
        ),
        "groupStatusCounts": status_counts,
        "missingRanges": [{"rangeStart": start, "rangeEnd": end} for start, end in missing],
        "duplicateRanges": [
            {"rangeStart": start, "rangeEnd": end} for start, end in duplicate_ranges
        ],
        "offGridRanges": [{"rangeStart": start, "rangeEnd": end} for start, end in off_grid],
        "logicalCoverageValid": logical_coverage_valid,
        "rangeProjectionConflictFree": range_projection_conflict_free,
        "proofFirstRun": proof_first,
    }


def _ready_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        group
        for group in groups
        if group.get("status") in READY_GROUP_STATUSES
        and isinstance(group.get("id"), str)
        and isinstance(group.get("rangeStart"), int)
        and isinstance(group.get("rangeEnd"), int)
    ]


def _owned_output_files(output_root: Path) -> set[Path]:
    return {
        path
        for path in output_root.iterdir()
        if path.is_file() and _SEQUENCE_OUTPUT.fullmatch(path.name)
    }


def _output_coverage(
    output_root: Path,
    groups: list[dict[str, Any]],
) -> dict[str, object]:
    ready = _ready_groups(groups)
    desired_names = [
        f"seq_{int(group['rangeStart'])}-{int(group['rangeEnd'])}.jpg" for group in ready
    ]
    actual_names = {path.name for path in _owned_output_files(output_root)}
    desired_set = set(desired_names)
    return {
        "readyOutputGroups": len(ready),
        "savedOutputFiles": len(actual_names),
        "outputCoverageValid": (
            len(desired_names) == len(desired_set) and actual_names == desired_set
        ),
    }


def _reconcile_terminal_output(
    client: httpx.Client,
    run_id: str,
    output_root: Path,
    groups: list[dict[str, Any]],
    saved_orders: set[int],
) -> int:
    ready = _ready_groups(groups)
    desired_names = {
        f"seq_{int(group['rangeStart'])}-{int(group['rangeEnd'])}.jpg" for group in ready
    }
    if len(desired_names) != len(ready):
        raise RuntimeError("Ready groups contain duplicate output ranges.")

    saved_now = 0
    for group in sorted(ready, key=lambda item: int(item["groupOrder"])):
        group_order = int(group["groupOrder"])
        file_name = f"seq_{int(group['rangeStart'])}-{int(group['rangeEnd'])}.jpg"
        response = client.get(
            f"/api/v1/admin/image-selections/{run_id}/groups/{group['id']}/selected-file"
        )
        response.raise_for_status()
        content = response.content
        destination = output_root / file_name
        if (
            destination.exists()
            and hashlib.sha256(destination.read_bytes()).digest()
            == hashlib.sha256(content).digest()
        ):
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

    for stale in _owned_output_files(output_root):
        if stale.name not in desired_names:
            stale.unlink()
    saved_orders.intersection_update(int(group["groupOrder"]) for group in ready)
    return saved_now


def _finalize_terminal_run(
    client: httpx.Client,
    run_id: str,
    run: dict[str, Any],
    output_root: Path,
    saved_orders: set[int],
) -> tuple[dict[str, object], int, int]:
    groups, cursor = _all_groups(client, run_id)
    coverage = _selection_coverage(run, groups)
    saved_now = 0
    job = run.get("job")
    job_status = job.get("status") if isinstance(job, dict) else None
    may_reconcile_ready_output = bool(
        coverage["logicalCoverageValid"]
        or (coverage["proofFirstRun"] and coverage["rangeProjectionConflictFree"])
    )
    if job_status in {"completed", "waiting_for_review"} and may_reconcile_ready_output:
        saved_now = _reconcile_terminal_output(
            client,
            run_id,
            output_root,
            groups,
            saved_orders,
        )
    output_coverage = _output_coverage(output_root, groups)
    if job_status in {"failed", "cancelled"}:
        output_coverage["outputCoverageValid"] = False
    coverage.update(output_coverage)
    return coverage, saved_now, cursor


def _terminal_report_is_success(job_status: object, report: dict[str, object]) -> bool:
    if job_status == "completed":
        return bool(report["logicalCoverageValid"] and report["outputCoverageValid"])
    if job_status != "waiting_for_review":
        return False
    if report.get("proofFirstRun") is True:
        return bool(
            report.get("rangeProjectionConflictFree") is True and report["outputCoverageValid"]
        )
    return bool(report["logicalCoverageValid"] and report["outputCoverageValid"])


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--source", type=Path)
    source.add_argument(
        "--rerun-id",
        help="Reuse immutable browser staging from an existing image-selection run.",
    )
    configured_output = os.environ.get("GAME_PREDICTOR_SELECTION_OUTPUT")
    parser.add_argument(
        "--output",
        type=Path,
        default=None if configured_output is None else Path(configured_output),
        help=(
            "Selected JPEG output directory. May also be supplied through "
            "GAME_PREDICTOR_SELECTION_OUTPUT."
        ),
    )
    parser.add_argument("--game-id")
    parser.add_argument(
        "--resume-upload-id",
        help="Resume one incomplete browser upload after validating its immutable contract.",
    )
    parser.add_argument(
        "--first-sequence-number",
        type=int,
        help="First layout number visible in the first source-image group.",
    )
    parser.add_argument(
        "--last-sequence-number",
        type=int,
        help="Last layout number in an existing staging rerun.",
    )
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--upload-workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument(
        "--expected-total-bytes",
        type=int,
        help="Precomputed source JPEG byte count from the controlled launcher.",
    )
    parser.add_argument("--poll-seconds", type=float, default=3.0)
    parser.add_argument(
        "--resume-existing",
        action="store_true",
        help="Resume polling and progressive export from IDs stored in --report.",
    )
    return parser.parse_args()


def _start_existing_rerun(options: argparse.Namespace) -> int:
    output_root = options.output.resolve(strict=True)
    if any(output_root.iterdir()):
        raise RuntimeError("Output directory must be empty before the acceptance run.")
    started_at = _utc_now()
    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(60.0, connect=10.0),
    ) as client:
        first_sequence_number = getattr(options, "first_sequence_number", None)
        last_sequence_number = getattr(options, "last_sequence_number", None)
        rerun_body = {
            key: value
            for key, value in {
                "firstSequenceNumber": first_sequence_number,
                "lastSequenceNumber": last_sequence_number,
            }.items()
            if value is not None
        }
        created = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-selections/{options.rerun_id}/rerun",
            json_body=rerun_body or None,
        )
    run = created.get("run")
    if not isinstance(run, dict):
        raise RuntimeError("Image-selection rerun response is missing the run.")
    job = run.get("job")
    if not isinstance(job, dict):
        raise RuntimeError("Image-selection rerun response is missing the job.")
    run_id = run.get("id")
    job_id = job.get("id")
    if not isinstance(run_id, str) or not isinstance(job_id, str):
        raise RuntimeError("Image-selection rerun response contains invalid identifiers.")
    report: dict[str, object] = {
        "schemaVersion": 3,
        "status": "selecting",
        "sourceRunId": options.rerun_id,
        "outputDirectory": str(output_root),
        "selectionStartedAt": started_at,
        "startedAt": started_at,
        "runId": run_id,
        "jobId": job_id,
        "savedOutputFiles": 0,
        "exportCursor": -1,
        "rerunCreated": bool(created.get("created")),
        "firstSequenceNumber": run.get("firstSequenceNumber"),
        "lastSequenceNumber": run.get("lastSequenceNumber"),
    }
    _write_report(options.report, report)
    return _resume_existing(options)


def _resume_existing(options: argparse.Namespace) -> int:
    report = json.loads(options.report.read_text(encoding="utf-8"))
    report["schemaVersion"] = 3
    run_id = str(report["runId"])
    selection_started_at = datetime.fromisoformat(str(report["selectionStartedAt"]))
    output_root = options.output.resolve(strict=True)
    saved_orders: set[int] = set()
    # A resumed monitor performs one complete reconciliation against the output
    # directory. Every later poll advances monotonically from this cursor.
    export_cursor = -1
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
                            "rangeRequired",
                            "skipped",
                            "errors",
                            "verifications",
                        )
                    },
                    "groupCount": progress["groups"],
                    "selectionElapsedSeconds": elapsed,
                }
            )
            if job["status"] in TERMINAL_STATUSES:
                error_code, error_message = _job_error(job)
                coverage, saved_terminal, export_cursor = _finalize_terminal_run(
                    client,
                    run_id,
                    current_run,
                    output_root,
                    saved_orders,
                )
                report.update(coverage)
                report.update(
                    {
                        "exportCursor": export_cursor,
                        "status": ("finished" if job["status"] == "completed" else job["status"]),
                        "selectionFinishedAt": _utc_now(),
                        "selectionElapsedSeconds": elapsed,
                        "finishedAt": _utc_now(),
                        "errorCode": error_code,
                        "errorMessage": error_message,
                    }
                )
                if saved_terminal:
                    print(
                        "terminal reconciliation "
                        f"saved={saved_terminal} total={report['savedOutputFiles']}",
                        flush=True,
                    )
                _write_report(options.report, report)
                return 0 if _terminal_report_is_success(job["status"], report) else 1
            saved_now, export_cursor = _save_ready_groups(
                client,
                run_id,
                output_root,
                saved_orders,
                after_group_order=export_cursor,
            )
            report.update(
                {
                    "savedOutputFiles": len(saved_orders),
                    "exportCursor": export_cursor,
                }
            )
            if saved_now or time.monotonic() - last_log >= 10:
                _write_report(options.report, report)
                print(
                    f"selection status={job['status']} stage={progress['stage']} "
                    f"progress={progress['current']}/{progress['total']} "
                    f"groups={progress['groups']} saved={len(saved_orders)} elapsed={elapsed}s",
                    flush=True,
                )
                last_log = time.monotonic()
            time.sleep(options.poll_seconds)


def main() -> int:
    options = _parse_args()
    if options.output is None:
        raise RuntimeError("--output or GAME_PREDICTOR_SELECTION_OUTPUT is required.")
    if options.resume_existing:
        return _resume_existing(options)
    if options.first_sequence_number is not None and options.first_sequence_number < 1:
        raise RuntimeError("--first-sequence-number must be positive.")
    if options.last_sequence_number is not None and options.last_sequence_number < 1:
        raise RuntimeError("--last-sequence-number must be positive.")
    if options.last_sequence_number is not None and options.rerun_id is None:
        raise RuntimeError("--last-sequence-number is supported only with --rerun-id.")
    if options.rerun_id is not None:
        return _start_existing_rerun(options)
    if not options.resume_existing and options.first_sequence_number is None:
        raise RuntimeError("--first-sequence-number is required for a new anchored selector run.")
    if options.source is None or options.game_id is None:
        raise RuntimeError("--source and --game-id are required for a new upload.")
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
    total_bytes = options.expected_total_bytes
    if total_bytes is None:
        total_bytes = sum(path.stat().st_size for path in files)
    if total_bytes < 1:
        raise RuntimeError("--expected-total-bytes must be positive.")
    report: dict[str, object] = {
        "schemaVersion": 3,
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
        "exportCursor": -1,
    }
    _write_report(options.report, report)
    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(60.0, connect=10.0),
    ) as client:
        upload_started = time.monotonic()
        report.update({"status": "uploading", "uploadStartedAt": _utc_now()})
        if options.resume_upload_id is None:
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
            uploaded_indexes: set[int] = set()
            uploaded_files = 0
            uploaded_bytes = 0
        else:
            upload_id = options.resume_upload_id
            upload = _request_json(
                client,
                "GET",
                f"/api/v1/admin/image-imports/browser-selections/{upload_id}",
            )
            expected_contract = {
                "expectedFileCount": len(files),
                "expectedTotalBytes": total_bytes,
                "gameId": options.game_id,
                "purpose": "photo_selection",
            }
            mismatches = [
                key for key, expected in expected_contract.items() if upload.get(key) != expected
            ]
            if mismatches:
                raise RuntimeError("Resume upload contract mismatch: " + ", ".join(mismatches))
            raw_indexes = upload.get("uploadedFileIndexes")
            if not isinstance(raw_indexes, list) or not all(
                isinstance(index, int) and 0 <= index < len(files) for index in raw_indexes
            ):
                raise RuntimeError("Resume upload contains invalid file indexes.")
            uploaded_indexes = set(raw_indexes)
            uploaded_files = len(uploaded_indexes)
            uploaded_bytes = int(upload.get("uploadedBytes", 0))
            report.update(
                {
                    "resumedUpload": True,
                    "resumedUploadedFiles": uploaded_files,
                    "resumedUploadedBytes": uploaded_bytes,
                }
            )
        report["uploadId"] = upload_id
        report["uploadedFiles"] = uploaded_files
        report["uploadedBytes"] = uploaded_bytes
        _write_report(options.report, report)
        last_log = time.monotonic()
        with ThreadPoolExecutor(max_workers=options.upload_workers) as executor:
            futures = {
                executor.submit(_upload_one, client, upload_id, index, source_root, path): index
                for index, path in enumerate(files)
                if index not in uploaded_indexes
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
                "firstSequenceNumber": options.first_sequence_number,
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
        export_cursor = -1
        last_log = 0.0
        while True:
            current_run = _request_json(client, "GET", f"/api/v1/admin/image-selections/{run_id}")
            job = current_run["job"]
            progress = _job_progress(job)
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
                            "rangeRequired",
                            "skipped",
                            "errors",
                            "verifications",
                        )
                    },
                    "groupCount": progress["groups"],
                    "selectionElapsedSeconds": _duration(selection_started),
                }
            )
            if job["status"] in TERMINAL_STATUSES:
                error_code, error_message = _job_error(job)
                coverage, saved_terminal, export_cursor = _finalize_terminal_run(
                    client,
                    run_id,
                    current_run,
                    output_root,
                    saved_orders,
                )
                report.update(coverage)
                report.update(
                    {
                        "exportCursor": export_cursor,
                        "status": ("finished" if job["status"] == "completed" else job["status"]),
                        "selectionFinishedAt": _utc_now(),
                        "selectionElapsedSeconds": _duration(selection_started),
                        "finishedAt": _utc_now(),
                        "errorCode": error_code,
                        "errorMessage": error_message,
                    }
                )
                if saved_terminal:
                    print(
                        "terminal reconciliation "
                        f"saved={saved_terminal} total={report['savedOutputFiles']}",
                        flush=True,
                    )
                _write_report(options.report, report)
                return 0 if _terminal_report_is_success(job["status"], report) else 1
            saved_now, export_cursor = _save_ready_groups(
                client,
                run_id,
                output_root,
                saved_orders,
                after_group_order=export_cursor,
            )
            report.update(
                {
                    "savedOutputFiles": len(saved_orders),
                    "exportCursor": export_cursor,
                }
            )
            if saved_now or time.monotonic() - last_log >= 10:
                _write_report(options.report, report)
                print(
                    f"selection status={job['status']} stage={progress['stage']} "
                    f"progress={progress['current']}/{progress['total']} "
                    f"groups={progress['groups']} saved={len(saved_orders)} "
                    f"elapsed={report['selectionElapsedSeconds']}s",
                    flush=True,
                )
                last_log = time.monotonic()
            time.sleep(options.poll_seconds)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"live image-selection acceptance failed: {error}", file=sys.stderr, flush=True)
        raise
