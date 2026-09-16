"""Stage one JPEG directory and start its immutable v20/v19 layout import.

The script mirrors the Admin browser-import contract.  It is deliberately
limited to the verified v19 mode, so it cannot accidentally start a current
virtual-geometry rollout while backfilling the historical image directories.
"""

from __future__ import annotations

import argparse
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
GEOMETRY_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
JPEG_SUFFIXES = frozenset({".jpg", ".jpeg"})
NATURAL_PART = re.compile(r"(\d+)")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _natural_key(value: str) -> tuple[tuple[int, object], ...]:
    return tuple(
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in NATURAL_PART.split(value)
        if part
    )


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".tmp-", delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _request_json(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, Any]:
    # Finalization can coincide with another large import.  The API call is
    # idempotent, so a bounded retry on a transport timeout is safer than
    # leaving a fully uploaded staging stranded before geometry preflight.
    last_error: httpx.TransportError | None = None
    for attempt in range(1, 4):
        try:
            response = client.request(method, path, json=payload)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise RuntimeError(f"Unexpected JSON response for {method} {path}.")
            return value
        except httpx.TransportError as error:
            last_error = error
            if attempt < 3:
                time.sleep(float(attempt))
    assert last_error is not None
    raise last_error


def _upload_one(
    client: httpx.Client,
    *,
    upload_id: str,
    index: int,
    source_root: Path,
    source: Path,
) -> int:
    relative_path = f"{source_root.name}/{source.relative_to(source_root).as_posix()}"
    error: Exception | None = None
    for attempt in range(1, 4):
        try:
            with source.open("rb") as handle:
                response = client.put(
                    f"/api/v1/admin/image-imports/browser-selections/{upload_id}/files/{index}",
                    content=handle,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "X-Image-Relative-Path": relative_path,
                    },
                )
            response.raise_for_status()
            return source.stat().st_size
        except (OSError, httpx.HTTPError) as current:
            error = current
            if attempt < 3:
                time.sleep(float(attempt))
    assert error is not None
    raise RuntimeError(f"Upload failed for index {index}: {relative_path}") from error


def _files(source_root: Path) -> list[Path]:
    files = [
        path
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix.casefold() in JPEG_SUFFIXES
    ]
    return sorted(files, key=lambda item: _natural_key(item.relative_to(source_root).as_posix()))


def _job_progress(job: dict[str, Any]) -> dict[str, object]:
    progress = job.get("progress")
    if not isinstance(progress, dict):
        return {"stage": None, "current": 0, "total": None, "review": 0}
    return {
        "stage": progress.get("stage"),
        "current": progress.get("current"),
        "total": progress.get("total"),
        "review": progress.get("review"),
    }


def _parse_options() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--upload-workers", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    return parser.parse_args()


def _load_or_create_upload(
    client: httpx.Client,
    *,
    options: argparse.Namespace,
    source_root: Path,
    files: list[Path],
    total_bytes: int,
    report: dict[str, object],
) -> tuple[str, set[int], int]:
    previous_upload_id = report.get("uploadId")
    if isinstance(previous_upload_id, str):
        restored = _request_json(
            client,
            "GET",
            f"/api/v1/admin/image-imports/browser-selections/{previous_upload_id}",
        )
        expected = {
            "expectedFileCount": len(files),
            "expectedTotalBytes": total_bytes,
            "gameId": options.game_id,
            "purpose": "layout_import",
        }
        mismatches = [key for key, value in expected.items() if restored.get(key) != value]
        if mismatches:
            raise RuntimeError("Existing staging contract mismatch: " + ", ".join(mismatches))
        indexes = restored.get("uploadedFileIndexes")
        if not isinstance(indexes, list) or not all(
            isinstance(value, int) and 0 <= value < len(files) for value in indexes
        ):
            raise RuntimeError("Existing staging has invalid uploaded file indexes.")
        return previous_upload_id, set(indexes), int(restored.get("uploadedBytes", 0))

    created = _request_json(
        client,
        "POST",
        "/api/v1/admin/image-imports/browser-selections",
        payload={
            "displayName": source_root.name,
            "expectedFileCount": len(files),
            "expectedTotalBytes": total_bytes,
            "purpose": "layout_import",
            "gameId": options.game_id,
        },
    )
    upload_id = created.get("uploadId")
    if not isinstance(upload_id, str):
        raise RuntimeError("Staging creation response is missing uploadId.")
    report["uploadId"] = upload_id
    return upload_id, set(), 0


def _wait_for_geometry(
    client: httpx.Client,
    *,
    geometry_job_id: str,
    report: dict[str, object],
    report_path: Path,
    poll_seconds: float,
) -> dict[str, Any]:
    # The geometry endpoint returns after persisting the job in its request
    # transaction.  A subsequent local HTTP request can race that commit for a
    # few milliseconds, so wait boundedly instead of treating the transient
    # 404 as a failed staging.
    visibility_deadline = time.monotonic() + 15.0
    while True:
        try:
            job = _request_json(client, "GET", f"/api/v1/admin/jobs/{geometry_job_id}")
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404 and time.monotonic() < visibility_deadline:
                time.sleep(0.5)
                continue
            raise
        status = job.get("status")
        if not isinstance(status, str):
            raise RuntimeError("Geometry job response is missing status.")
        progress = _job_progress(job)
        report.update(
            {
                "status": "geometry_preflight",
                "geometryJobStatus": status,
                "geometryProgress": progress,
                "updatedAt": _utc_now(),
            }
        )
        _write_report(report_path, report)
        if status in GEOMETRY_TERMINAL_STATUSES:
            if status != "completed":
                job_error = job.get("error")
                raise RuntimeError(f"Geometry preflight ended as {status}: {job_error}")
            return job
        time.sleep(poll_seconds)


def _geometry_checksum(job: dict[str, Any]) -> str:
    progress = job.get("progress")
    checkpoint = progress.get("pageGeometryPreflight") if isinstance(progress, dict) else None
    checksum = (
        checkpoint.get("geometryManifestChecksumSha256") if isinstance(checkpoint, dict) else None
    )
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise RuntimeError(
            "Completed geometry preflight is missing its immutable manifest checksum."
        )
    return checksum


def run(options: argparse.Namespace) -> None:
    source_root = options.source.resolve(strict=True)
    if not source_root.is_dir():
        raise RuntimeError("--source must name a directory.")
    files = _files(source_root)
    if not files:
        raise RuntimeError("Source directory contains no JPEG files.")
    total_bytes = sum(path.stat().st_size for path in files)
    report_path = options.report.resolve()
    report = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.is_file()
        else {
            "schemaVersion": 1,
            "status": "starting",
            "sourceDirectory": str(source_root),
            "displayName": source_root.name,
            "gameId": options.game_id,
            "fileCount": len(files),
            "totalBytes": total_bytes,
            "startedAt": _utc_now(),
        }
    )
    if report.get("sourceDirectory") != str(source_root) or report.get("gameId") != options.game_id:
        raise RuntimeError("Existing report belongs to a different source or game.")

    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(90.0, connect=10.0),
    ) as client:
        upload_id, uploaded_indexes, uploaded_bytes = _load_or_create_upload(
            client,
            options=options,
            source_root=source_root,
            files=files,
            total_bytes=total_bytes,
            report=report,
        )
        report.update(
            {
                "status": "uploading",
                "uploadId": upload_id,
                "uploadedFiles": len(uploaded_indexes),
                "uploadedBytes": uploaded_bytes,
                "updatedAt": _utc_now(),
            }
        )
        _write_report(report_path, report)
        with ThreadPoolExecutor(max_workers=options.upload_workers) as executor:
            pending = {
                executor.submit(
                    _upload_one,
                    client,
                    upload_id=upload_id,
                    index=index,
                    source_root=source_root,
                    source=source,
                ): index
                for index, source in enumerate(files)
                if index not in uploaded_indexes
            }
            for future in as_completed(pending):
                uploaded_bytes += future.result()
                uploaded_indexes.add(pending[future])
                if len(uploaded_indexes) % 20 == 0 or len(uploaded_indexes) == len(files):
                    report.update(
                        {
                            "uploadedFiles": len(uploaded_indexes),
                            "uploadedBytes": uploaded_bytes,
                            "updatedAt": _utc_now(),
                        }
                    )
                    _write_report(report_path, report)

        finalized = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/finalize",
        )
        selection_token = finalized.get("selectionToken")
        if not isinstance(selection_token, str):
            raise RuntimeError("Finalized staging response is missing selectionToken.")
        report.update({"status": "finalized", "finalizedAt": _utc_now()})
        _write_report(report_path, report)

        preflight = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/preflight",
            payload={"gameId": options.game_id},
        )
        geometry = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/geometry-preflight",
            payload={"gameId": options.game_id},
        )
        geometry_job = geometry.get("job")
        geometry_job_id = geometry_job.get("id") if isinstance(geometry_job, dict) else None
        if not isinstance(geometry_job_id, str):
            raise RuntimeError("Geometry preflight response is missing job id.")
        report.update(
            {
                "status": "geometry_preflight",
                "geometryJobId": geometry_job_id,
                "geometryCreated": geometry.get("created"),
                "updatedAt": _utc_now(),
            }
        )
        _write_report(report_path, report)
        completed_geometry = _wait_for_geometry(
            client,
            geometry_job_id=geometry_job_id,
            report=report,
            report_path=report_path,
            poll_seconds=options.poll_seconds,
        )
        started = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{upload_id}/start",
            payload={
                "gameId": options.game_id,
                "manifestChecksumSha256": preflight["manifestChecksumSha256"],
                "preflightChecksumSha256": preflight["preflightChecksumSha256"],
                "symbolModelInferenceFingerprint": preflight["symbolModelInferenceFingerprint"],
                "gridProfileInferenceFingerprint": preflight["gridProfileInferenceFingerprint"],
                "geometryPreflightJobId": geometry_job_id,
                "geometryManifestChecksumSha256": _geometry_checksum(completed_geometry),
                "boardCellProcessingMode": "verified_v19",
            },
        )
        import_job = started.get("job")
        import_job_id = import_job.get("id") if isinstance(import_job, dict) else None
        if not isinstance(import_job_id, str):
            raise RuntimeError("Import start response is missing job id.")
        report.update(
            {
                "status": "import_created",
                "importJobId": import_job_id,
                "importCreated": started.get("created"),
                "engine": "board-cell-processing-v20-verified-v19-v1",
                "finishedAt": _utc_now(),
            }
        )
        _write_report(report_path, report)
        print(json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)


if __name__ == "__main__":
    try:
        run(_parse_options())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr, flush=True)
        raise
