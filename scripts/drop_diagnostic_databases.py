"""Preview and drop the leftover diagnostic databases of the local PostgreSQL (D-467, S1).

The list of databases is frozen. Without ``--execute`` the script only prints a
preview with sizes and a checksum; ``--execute`` requires the confirmation
phrase built from that checksum, refuses databases with open connections and
never touches a database outside the list.

Usage (repository root, PowerShell):

    .venv\\Scripts\\python.exe scripts/drop_diagnostic_databases.py
    .venv\\Scripts\\python.exe scripts/drop_diagnostic_databases.py --execute --confirm <phrase>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Sequence
from typing import Any

from game_predictor_api.config import ApiSettings
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

DIAGNOSTIC_DATABASES: tuple[str, ...] = (
    "diag_raw_test",
    "diag_search_path_test",
    "diag_search_path_test2",
)
PROTECTED_DATABASES: frozenset[str] = frozenset({"postgres", "template0", "template1"})


class DropRefused(RuntimeError):
    pass


def _preview(connection: Any) -> dict[str, Any]:
    rows = connection.execute(
        text(
            """
            SELECT d.datname,
                   pg_database_size(d.datname) AS bytes,
                   (SELECT count(*) FROM pg_stat_activity a WHERE a.datname = d.datname) AS sessions
            FROM pg_database d
            WHERE d.datname = ANY(:names)
            ORDER BY d.datname
            """
        ),
        {"names": list(DIAGNOSTIC_DATABASES)},
    ).all()
    databases = [
        {"name": row.datname, "bytes": int(row.bytes), "sessions": int(row.sessions)}
        for row in rows
    ]
    payload = {"databases": databases, "frozenList": list(DIAGNOSTIC_DATABASES)}
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {**payload, "previewSha256": digest}


def _required_confirmation(preview_sha256: str) -> str:
    return f"DROP-DIAGNOSTIC-DATABASES {preview_sha256[:16]}"


def _drop(connection: Any, preview: dict[str, Any]) -> list[str]:
    dropped: list[str] = []
    for database in preview["databases"]:
        name = str(database["name"])
        if name not in DIAGNOSTIC_DATABASES or name in PROTECTED_DATABASES:
            raise DropRefused(f"DIAGNOSTIC_DATABASE_NOT_LISTED: {name}")
        if database["sessions"]:
            raise DropRefused(f"DIAGNOSTIC_DATABASE_IN_USE: {name}")
        connection.execute(text(f'DROP DATABASE "{name}"'))
        dropped.append(name)
    return dropped


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--confirm", default="")
    arguments = parser.parse_args(argv)
    url = make_url(ApiSettings.from_environment().database_url).set(database="postgres")
    engine = create_engine(
        url,
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=30000"},
    )
    try:
        with engine.connect() as connection:
            preview = _preview(connection)
            print(json.dumps(preview, indent=2, sort_keys=True))
            if not arguments.execute:
                print(f"confirmation phrase: {_required_confirmation(preview['previewSha256'])}")
                return 0
            if arguments.confirm != _required_confirmation(preview["previewSha256"]):
                print("DIAGNOSTIC_DATABASE_CONFIRMATION_MISMATCH", file=sys.stderr)
                return 2
            if not preview["databases"]:
                print("nothing to drop")
                return 0
            try:
                dropped = _drop(connection, preview)
            except DropRefused as error:
                print(str(error), file=sys.stderr)
                return 2
            print(f"dropped: {', '.join(dropped)}")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
