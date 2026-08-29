"""Preview or enqueue bounded compaction of reproducible pipeline payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobType, create_job, job_input_key
from game_predictor_api.storage.database import create_database_engine, create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.pipeline_state_compaction_repository import (
    SqlAlchemyPipelineStateCompactionRepository,
)

CONFIRMATION = "DELETE_REPRODUCIBLE_PIPELINE_PAYLOADS"


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preview = commands.add_parser("preview", help="Create an immutable, non-destructive report.")
    preview.add_argument("--retention-hours", type=int, default=24)
    start = commands.add_parser("start", help="Enqueue deletion from an approved preview.")
    start.add_argument("--manifest-relative-path", required=True)
    start.add_argument("--manifest-checksum-sha256", required=True)
    start.add_argument("--preview-token", required=True)
    start.add_argument("--confirm", required=True)
    return parser.parse_args()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(artifact_root: Path, relative_value: str) -> Path:
    relative = PurePosixPath(relative_value)
    if (
        relative.is_absolute()
        or relative.parts[:4] != ("data", "exports", "storage-gc", "pipeline-state")
        or relative.name != "manifest.jsonl"
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError("Unsafe pipeline compaction manifest path.")
    root = artifact_root.resolve()
    path = root.joinpath(*relative.parts).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Pipeline compaction manifest escapes managed storage.")
    return path


def _preview(settings: ApiSettings, retention_hours: int) -> dict[str, object]:
    if not 1 <= retention_hours <= 24 * 365:
        raise ValueError("--retention-hours must be between 1 and 8760")
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            report = SqlAlchemyPipelineStateCompactionRepository(
                session,
                settings.artifact_root,
            ).create_preview(cutoff_at=datetime.now(UTC) - timedelta(hours=retention_hours))
    finally:
        engine.dispose()
    return {
        "previewId": str(report.preview_id),
        "manifestRelativePath": report.manifest_relative_path,
        "manifestChecksumSha256": report.manifest_checksum_sha256,
        "previewToken": report.preview_token,
        "candidateCount": report.candidate_count,
        "stageResultCount": report.stage_result_count,
        "candidateBytes": report.candidate_bytes,
        "cutoffAt": report.cutoff_at.isoformat(),
        "destructive": False,
    }


def _start(settings: ApiSettings, arguments: argparse.Namespace) -> dict[str, object]:
    if arguments.confirm != CONFIRMATION:
        raise ValueError(f"--confirm must equal {CONFIRMATION}")
    manifest = _manifest_path(settings.artifact_root, arguments.manifest_relative_path)
    checksum = _file_sha256(manifest)
    if checksum != arguments.manifest_checksum_sha256:
        raise ValueError("Manifest checksum differs from the approved preview.")
    expected_token = hashlib.sha256(
        f"{checksum}:pipeline-compaction-confirmation-v2".encode("ascii")
    ).hexdigest()
    if arguments.preview_token != expected_token:
        raise ValueError("Preview token differs from the approved preview.")
    payload: dict[str, object] = {
        "schema_version": 1,
        "compaction_kind": "reproducible_image_pipeline_state",
        "manifest_relative_path": arguments.manifest_relative_path,
        "manifest_checksum_sha256": checksum,
        "preview_token": expected_token,
        "mode": "execute",
    }
    engine = create_database_engine(settings)
    factory = create_session_factory(engine)
    try:
        with factory.begin() as session:
            repository = SqlAlchemyJobRepository(session)
            input_key = job_input_key(
                JobType.STORAGE_PIPELINE_COMPACTION,
                game_id=None,
                input_payload=payload,
            )
            existing = repository.get_job_by_input_key(input_key)
            job = existing or repository.add_job(
                create_job(
                    JobType.STORAGE_PIPELINE_COMPACTION,
                    game_id=None,
                    input_payload=payload,
                )
            )
    finally:
        engine.dispose()
    return {
        "jobId": str(job.id),
        "status": job.status.value,
        "created": existing is None,
        "manifestChecksumSha256": checksum,
    }


def main() -> int:
    arguments = _arguments()
    settings = ApiSettings.from_environment()
    try:
        result = (
            _preview(settings, arguments.retention_hours)
            if arguments.command == "preview"
            else _start(settings, arguments)
        )
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
