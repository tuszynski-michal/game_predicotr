"""Wait for verified page geometry and start one already-staged v20 import."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx
from run_v20_layout_import import (
    ADMIN_HEADERS,
    _geometry_checksum,
    _request_json,
    _utc_now,
    _wait_for_geometry,
    _write_report,
)


def _parse_options() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-id", required=True)
    parser.add_argument("--game-id", required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    return parser.parse_args()


def run(options: argparse.Namespace) -> None:
    report_path = options.report.resolve()
    report: dict[str, object] = (
        json.loads(report_path.read_text(encoding="utf-8"))
        if report_path.is_file()
        else {
            "schemaVersion": 1,
            "status": "starting",
            "uploadId": options.upload_id,
            "gameId": options.game_id,
            "startedAt": _utc_now(),
        }
    )
    if report.get("uploadId") != options.upload_id or report.get("gameId") != options.game_id:
        raise RuntimeError("Existing report belongs to another staging or game.")
    with httpx.Client(
        base_url=options.api_base_url,
        headers=ADMIN_HEADERS,
        timeout=httpx.Timeout(90.0, connect=10.0),
    ) as client:
        preflight = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{options.upload_id}/preflight",
            payload={"gameId": options.game_id},
        )
        geometry = _request_json(
            client,
            "POST",
            f"/api/v1/admin/image-imports/browser-selections/{options.upload_id}/geometry-preflight",
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
            f"/api/v1/admin/image-imports/browser-selections/{options.upload_id}/start",
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
