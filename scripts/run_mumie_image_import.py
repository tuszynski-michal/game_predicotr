"""Upload Mumie using supported virtual geometry and durable, bounded API steps.

The operator's source seq_* ranges remain unchanged. This tool never accepts
geometries, labels symbols, publishes rules or activates a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import httpx
from game_predictor_worker.vision_lab.annotations import exclusive_bounded
from run_v20_layout_import import (
    ADMIN_HEADERS,
    _files,
    _geometry_checksum,
    _load_or_create_upload,
    _request_json,
    _upload_one,
    _write_report,
)

BASE = "/api/v1/admin"
PROFILE = "grid_profile_mumie_v1"


def bind_input(source: Path, report: dict[str, Any]) -> list[Path]:
    files: list[Path] = _files(source)
    if not files:
        raise ValueError("NO_SOURCE_PHOTOS")
    rows: list[dict[str, Any]] = []
    for path in files:
        if path.is_symlink():
            raise ValueError("SOURCE_LINK_FORBIDDEN")
        with path.open("rb") as handle:
            sha = hashlib.file_digest(handle, "sha256").hexdigest()
        rows.append(
            {
                "path": path.relative_to(source).as_posix(),
                "sha256": sha,
                "size": path.stat().st_size,
            }
        )
    fingerprint = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    if report.get("inputFingerprint", fingerprint) != fingerprint:
        raise ValueError("IMPORT_INPUT_CHANGED")
    if report.get("sourceDirectory", str(source)) != str(source):
        raise ValueError("IMPORT_SOURCE_CHANGED")
    report.update(
        inputFingerprint=fingerprint,
        sourceDirectory=str(source),
        inputFiles=rows,
        fileCount=len(files),
        totalBytes=sum(r["size"] for r in rows),
    )
    return files


def ensure_game(client: httpx.Client, report: dict[str, Any]) -> str:
    response = client.get(f"{BASE}/games")
    response.raise_for_status()
    games = [g for g in response.json() if g["code"].casefold() == "mumie"]
    if len(games) > 1:
        raise ValueError("MUMIE_GAME_AMBIGUOUS")
    game = (
        games[0]
        if games
        else _request_json(
            client,
            "POST",
            f"{BASE}/games",
            payload={
                "code": "mumie",
                "name": "Mumie",
                "status": "draft",
                "shapeGeometryConfiguration": PROFILE,
            },
        )
    )
    if game["shapeGeometryConfiguration"] != PROFILE:
        raise ValueError("MUMIE_GAME_PROFILE_CONFLICT")
    if report.get("gameId", game["id"]) != game["id"]:
        raise ValueError("MUMIE_GAME_ID_CONFLICT")
    report.update(gameId=game["id"], gridProfile=PROFILE)
    return str(game["id"])


def upload(client: httpx.Client, source: Path, path: Path, report: dict[str, Any]) -> None:
    files = bind_input(source, report)
    game_id = ensure_game(client, report)
    client.params = {"gameId": game_id}
    _write_report(path, report)
    if "uploadId" not in report:
        if report.get("uploadCreationPending"):
            raise ValueError("UPLOAD_CREATION_OUTCOME_UNKNOWN")
        # Creating a staging is not idempotent. Never automatically repeat it
        # after a lost response; known upload IDs resume through GET below.
        report["uploadCreationPending"] = True
        _write_report(path, report)
        response = client.post(
            f"{BASE}/image-imports/browser-selections",
            json={
                "displayName": source.name,
                "expectedFileCount": len(files),
                "expectedTotalBytes": report["totalBytes"],
                "purpose": "layout_import",
                "gameId": game_id,
            },
        )
        response.raise_for_status()
        report.update(uploadId=response.json()["uploadId"], uploadCreationPending=False)
        _write_report(path, report)
    upload_id, uploaded, uploaded_bytes = _load_or_create_upload(
        client,
        options=argparse.Namespace(game_id=game_id),
        source_root=source,
        files=files,
        total_bytes=report["totalBytes"],
        report=report,
    )
    report.update(uploadId=upload_id, status="uploading")
    _write_report(path, report)
    with ThreadPoolExecutor(max_workers=4) as executor:
        pending = {
            executor.submit(
                _upload_one,
                client,
                upload_id=upload_id,
                index=index,
                source_root=source,
                source=item,
            ): index
            for index, item in enumerate(files)
            if index not in uploaded
        }
        for future in as_completed(pending):
            uploaded_bytes += future.result()
            uploaded.add(pending[future])
            if len(uploaded) % 20 == 0 or len(uploaded) == len(files):
                report.update(uploadedFiles=len(uploaded), uploadedBytes=uploaded_bytes)
                _write_report(path, report)
                print(f"Uploaded {len(uploaded)}/{len(files)}", flush=True)
    finalized = _request_json(
        client, "POST", f"{BASE}/image-imports/browser-selections/{upload_id}/finalize"
    )
    report.update(
        status="uploaded",
        uploadedFiles=len(uploaded),
        uploadedBytes=uploaded_bytes,
        manifestChecksumSha256=finalized.get("inputManifestSha256"),
    )
    _write_report(path, report)


def start_payload(
    report: dict[str, Any], preflight: dict[str, Any], job: dict[str, Any]
) -> dict[str, Any]:
    checkpoint = job.get("progress", {}).get("pageGeometryPreflight", {})
    if checkpoint.get("reviewRequiredSourceCount", 0) or job.get("progress", {}).get("review", 0):
        raise ValueError("GEOMETRY_REVIEW_REQUIRED")
    return {
        "gameId": report["gameId"],
        "manifestChecksumSha256": preflight["manifestChecksumSha256"],
        "preflightChecksumSha256": preflight["preflightChecksumSha256"],
        "symbolModelInferenceFingerprint": preflight.get("symbolModelInferenceFingerprint"),
        "symbolModelSnapshotFingerprint": preflight.get("symbolModelSnapshotFingerprint"),
        "gridProfileInferenceFingerprint": preflight.get("gridProfileInferenceFingerprint"),
        "geometryPreflightJobId": report["geometryJobId"],
        "geometryManifestChecksumSha256": _geometry_checksum(job),
        "boardCellProcessingMode": "structured_lattice_v3",
    }


def advance(client: httpx.Client, path: Path, report: dict[str, Any]) -> None:
    client.params = {"gameId": report["gameId"]}
    if "uploadId" not in report:
        raise ValueError("UPLOAD_REQUIRED")
    prefix = f"{BASE}/image-imports/browser-selections/{report['uploadId']}"
    if "geometryJobId" not in report:
        response = _request_json(
            client, "POST", prefix + "/geometry-preflight", payload={"gameId": report["gameId"]}
        )
        report.update(geometryJobId=response["job"]["id"], status="geometry_preflight")
        _write_report(path, report)
    job = _request_json(client, "GET", f"{BASE}/jobs/{report['geometryJobId']}")
    report.update(geometryJobStatus=job["status"], geometryProgress=job.get("progress"))
    _write_report(path, report)
    if job["status"] != "completed":
        if job["status"] in {"failed", "cancelled"}:
            raise ValueError(f"GEOMETRY_JOB_{job['status'].upper()}: {job.get('error')}")
        return
    preflight = _request_json(
        client, "POST", prefix + "/preflight", payload={"gameId": report["gameId"]}
    )
    if preflight.get("geometryPreflightRequired") and not preflight.get(
        "geometryPreflightArtifactReady"
    ):
        report.update(status="geometry_review_required", preflight=preflight)
        _write_report(path, report)
        return
    try:
        payload = start_payload(report, preflight, job)
    except ValueError as error:
        if str(error) != "GEOMETRY_REVIEW_REQUIRED":
            raise
        report.update(status="geometry_review_required", preflight=preflight)
        _write_report(path, report)
        return
    started = _request_json(client, "POST", prefix + "/start", payload=payload)
    existing = report.get("importJobId")
    if existing is not None and existing != started["job"]["id"]:
        raise ValueError("IMPORT_JOB_ID_CHANGED")
    report.update(
        status="import_created",
        importJobId=started["job"]["id"],
        importCreated=started["created"],
        preflight=preflight,
    )
    _write_report(path, report)


def status(client: httpx.Client, path: Path, report: dict[str, Any]) -> None:
    if "gameId" in report:
        client.params = {"gameId": report["gameId"]}
    if "gameId" in report:
        report["game"] = _request_json(client, "GET", f"{BASE}/games/{report['gameId']}")
    if "uploadId" in report:
        report["upload"] = _request_json(
            client, "GET", f"{BASE}/image-imports/browser-selections/{report['uploadId']}"
        )
    if "geometryJobId" in report:
        report["geometryJob"] = _request_json(
            client, "GET", f"{BASE}/jobs/{report['geometryJobId']}"
        )
    if "importJobId" in report:
        report["importJob"] = _request_json(client, "GET", f"{BASE}/jobs/{report['importJobId']}")
    _write_report(path, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", required=True, choices=("upload", "advance", "status"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    path = args.report.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with exclusive_bounded(path.parent, 3):
        report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        with httpx.Client(
            base_url=args.api, headers=ADMIN_HEADERS, timeout=httpx.Timeout(20, connect=3)
        ) as client:
            if args.step == "upload":
                upload(client, args.source.resolve(), path, report)
            elif args.step == "advance":
                bind_input(args.source.resolve(), report)
                advance(client, path, report)
            else:
                status(client, path, report)
        print(
            json.dumps(
                {
                    k: v
                    for k, v in report.items()
                    if k
                    not in {
                        "inputFiles",
                        "game",
                        "upload",
                        "geometryJob",
                        "importJob",
                        "preflight",
                        "geometryProgress",
                    }
                },
                ensure_ascii=False,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
