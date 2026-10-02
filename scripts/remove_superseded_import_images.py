"""Preview or remove the dead source images of a superseded duplicate import.

TASK-0811. Only images of ``--import-job-id`` that are wholly replaced by
another import of the same game and carry no human work or live data are
removed; every other image of the import is kept whole and listed with its
reasons (rules: ``build_removal_plan`` in
``game_predictor_api.storage.superseded_import_image_removal_repository``).
Files on disk are never touched.

``--preview`` (default) runs in one ``REPEATABLE READ READ ONLY`` transaction
and writes only the report ``<report dir>/<stamp>-preview.json`` with the plan
digest ``planSha256``. ``--execute --confirm-plan-sha256 <digest>`` takes the
game's exclusive lifecycle fence, recomputes the plan in one ``REPEATABLE
READ`` transaction and refuses if the digest differs; it then writes a JSON
Lines backup of every row it deletes to ``<report dir>/<stamp>/``, deletes,
checks the invariants and commits only when they all hold (otherwise the
transaction is rolled back). The report of an execution is
``<report dir>/<stamp>/report.json``.

Run with the API, workers and Reviewer of every checkout stopped, on the
schema-owner connection (``GAME_PREDICTOR_OWNER_DATABASE_URL``).

Examples (repository root)::

    .venv\\Scripts\\python.exe scripts/remove_superseded_import_images.py \\
        --game-id <uuid> --import-job-id <uuid>
    .venv\\Scripts\\python.exe scripts/remove_superseded_import_images.py \\
        --game-id <uuid> --import-job-id <uuid> --execute --confirm-plan-sha256 <digest>

Exit codes: 0 success, 2 refused (nothing written to the database), 3 an
invariant failed and the transaction was rolled back.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_maintenance_database_engine
from game_predictor_api.storage.schema_readiness import (
    EXPECTED_ALEMBIC_HEAD,
    AlembicHeadMismatchError,
    database_alembic_revision,
)
from game_predictor_api.storage.superseded_import_image_removal_repository import (
    REMOVAL_SCHEMA,
    RemovalError,
    RemovalExecution,
    RemovalInvariantError,
    SupersededImportImageRemovalRepository,
    plan_report,
)
from sqlalchemy import Engine

REPORT_DIRECTORY = ("data", "exports", "remove-superseded-import-images")


def _arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", required=True, type=UUID)
    parser.add_argument("--import-job-id", required=True, type=UUID)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--preview", action="store_true", help="Read-only plan (default).")
    action.add_argument("--execute", action="store_true", help="Delete in one transaction.")
    parser.add_argument(
        "--confirm-plan-sha256",
        help="planSha256 of the preview the operator reviewed (required with --execute).",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        help="Directory of the reports and backups (default: <artifact root>/"
        "data/exports/remove-superseded-import-images/<game id>).",
    )
    arguments = parser.parse_args(argv)
    if arguments.execute and not arguments.confirm_plan_sha256:
        parser.error("--execute requires --confirm-plan-sha256 from a reviewed preview")
    return arguments


def _require_schema(engine: Engine) -> None:
    found = database_alembic_revision(engine)
    if found != EXPECTED_ALEMBIC_HEAD:
        raise AlembicHeadMismatchError(found)


def _report_dir(settings: ApiSettings, arguments: argparse.Namespace) -> Path:
    if arguments.report_dir is not None:
        return Path(arguments.report_dir).resolve()
    return settings.artifact_root.joinpath(*REPORT_DIRECTORY, str(arguments.game_id))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as target:
        target.write(json.dumps(payload, indent=2, sort_keys=True))


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    """Console view: the report without the per-image lists."""

    hidden = {
        "keptImages",
        "qualifyingImageIds",
        "foreignKeysChecked",
        "metricsBefore",
        "metricsAfter",
    }
    plan = {key: value for key, value in report.get("plan", {}).items() if key not in hidden}
    body = {key: value for key, value in report.items() if key not in hidden | {"plan"}}
    return {**body, **({"plan": plan} if plan else {})}


def _execution_report(execution: RemovalExecution) -> dict[str, Any]:
    return {
        "committed": execution.committed,
        "deletedCounts": dict(execution.deleted_counts),
        "backupDirectory": (
            None if execution.backup_directory is None else str(execution.backup_directory)
        ),
        "backupTables": (
            None if execution.backup_manifest is None else execution.backup_manifest["tables"]
        ),
        "metricsBefore": execution.metrics_before,
        "metricsAfter": execution.metrics_after,
    }


def main(argv: list[str] | None = None) -> int:
    arguments = _arguments(argv)
    settings = ApiSettings.from_environment()
    action = "execute" if arguments.execute else "preview"
    report_dir = _report_dir(settings, arguments)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    started = time.monotonic()
    report: dict[str, Any] = {
        "schema": REMOVAL_SCHEMA,
        "action": action,
        "gameId": str(arguments.game_id),
        "importJobId": str(arguments.import_job_id),
        "generatedAt": datetime.now(UTC).isoformat(),
    }
    engine = create_maintenance_database_engine(settings)
    exit_code = 0
    try:
        _require_schema(engine)
        repository = SupersededImportImageRemovalRepository(engine)
        if not arguments.execute:
            plan = repository.preview(arguments.game_id, arguments.import_job_id)
            report["plan"] = plan_report(plan)
            path = report_dir / f"{stamp}-preview.json"
        else:
            backup_root = report_dir
            try:
                execution = repository.execute(
                    arguments.game_id,
                    arguments.import_job_id,
                    confirm_plan_sha256=str(arguments.confirm_plan_sha256),
                    backup_root=backup_root,
                )
            except RemovalInvariantError as error:
                report["error"] = {"code": error.code, "details": error.details}
                report["committed"] = False
                exit_code = 3
                path = report_dir / f"{stamp}-execute-rolled-back.json"
            else:
                report["plan"] = plan_report(execution.plan)
                report.update(_execution_report(execution))
                path = (
                    execution.backup_directory / "report.json"
                    if execution.backup_directory is not None
                    else report_dir / f"{stamp}-execute-nothing-to-delete.json"
                )
    except RemovalError as error:
        report["error"] = {"code": error.code, "message": error.message, "details": error.details}
        report["committed"] = False
        exit_code = 2
        path = report_dir / f"{stamp}-{action}-refused.json"
    finally:
        engine.dispose()
    report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    _write(path, report)
    print(json.dumps({**_summary(report), "reportPath": str(path)}, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
