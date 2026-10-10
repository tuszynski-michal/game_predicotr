"""Export a bounded immutable V7 preference snapshot without updating the database.

PowerShell: set GAME_PREDICTOR_DATABASE_URL to the selected application DB;
root Python scripts/export_v7_selection_feedback.py --run-id UUID --output DIRECTORY
Run under an external timeout <=120 seconds. This does not train or activate a model.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
for directory in ("services/worker/src", "services/api/src"):
    sys.path.insert(0, str(ROOT / directory))

from game_predictor_api.config import ApiSettings  # noqa: E402
from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint  # noqa: E402
from game_predictor_api.storage.v7_selection_feedback import read_feedback_manifest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402


def publish_feedback_manifest(directory: Path, manifest: dict[str, object]) -> Path:
    """Crash-safe content-addressed publication; a conflicting existing file is never replaced."""
    fingerprint = payload_fingerprint(manifest)
    content = (
        json.dumps(
            {"fingerprint": fingerprint, "manifest": manifest},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"v7-feedback-{fingerprint}.json"
    descriptor, name = tempfile.mkstemp(dir=directory, prefix=".v7-feedback-")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != content:
                raise ValueError(
                    "Existing feedback artifact differs from its fingerprint."
                ) from None
        if target.read_bytes() != content:
            raise ValueError("Feedback artifact read-back failed.")
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", type=UUID, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-operations", type=int, default=10_000)
    args = parser.parse_args()
    settings = ApiSettings.from_environment()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
    try:
        with Session(engine) as session, session.begin():
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            session.execute(text("SET LOCAL statement_timeout = '10s'"))
            manifest = read_feedback_manifest(
                session, args.run_id, maximum_operations=args.maximum_operations
            )
        target = publish_feedback_manifest(args.output, manifest)
        print(json.dumps({"artifact": str(target), "report": manifest["report"]}))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
