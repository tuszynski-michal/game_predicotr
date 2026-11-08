"""Exact owned-capability cleanup/check for the explicit two-command T1167 fixture.

Only the maintenance connection resolves owner configuration. Application tests require
the separate disposable URL and independent expected database before engine creation.
No credential is printed, included in receipts, or retained after cleanup.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[4]
    journal = args.journal.resolve()
    assert journal.is_relative_to(root / "artifacts"), "Only owned artifact journals"
    row = json.loads(journal.read_text(encoding="utf-8"))
    name = row["databaseName"]
    assert re.fullmatch(r"game_predictor_t1167parent_[0-9a-f]{12}_test", name)
    assert row["schemaVersion"] == "recording-test-resource-receipt-v1"
    assert row["databaseCreatedHere"] is True
    from _recording_capability_fixture import (
        OwnedRecordingCapability,
        RecordingCapabilityReceipt,
        RuntimeRoleReceipt,
    )
    from game_predictor_api.config import ApiSettings
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    owner = make_url(ApiSettings.from_environment().owner_database_url)
    assert owner.host == row["clusterHost"] and owner.port == row["clusterPort"]
    capability = OwnedRecordingCapability(owner.set(database=name))
    capability.database_oid = row["databaseOid"]
    capability._journal_nonce = row["journalNonce"]
    capability.journal_root = journal.parent
    original = row["capabilityRole"]
    capability.receipt = RecordingCapabilityReceipt(
        original["name"],
        original["oid"],
        name,
        row["databaseOid"],
        original["marker"],
        original["createdHere"],
    )
    runtime = row["runtimeRole"]
    capability.runtime_role_receipt = RuntimeRoleReceipt(
        runtime["name"],
        runtime["oid"],
        runtime["createdHere"],
        runtime["marker"],
    )
    engine = create_engine(
        owner.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    try:
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_database()")) == "postgres"
            connection.execute(text("SET statement_timeout='10s'"))
            if args.cleanup:
                capability.drop_database(connection)
            counts = {
                "databases": connection.scalar(
                    text("SELECT count(*) FROM pg_database WHERE datname=:n"), {"n": name}
                ),
                "runtimeRoles": connection.scalar(
                    text("SELECT count(*) FROM pg_roles WHERE rolname=:n"), {"n": runtime["name"]}
                ),
                "capabilityRoles": connection.scalar(
                    text("SELECT count(*) FROM pg_roles WHERE rolname=:n"), {"n": original["name"]}
                ),
            }
            assert counts == {"databases": 0, "runtimeRoles": 0, "capabilityRoles": 0}, counts
    finally:
        engine.dispose()
    if args.cleanup:
        private = root / ".tmp" / "TASK1167-private-app.json"
        assert private.resolve().is_relative_to((root / ".tmp").resolve())
        private.unlink(missing_ok=True)
    receipt = args.receipt.resolve()
    assert receipt.is_relative_to(root / "artifacts")
    receipt.write_text(
        json.dumps({"database": name, "freshProcess": True, **counts}, indent=2), encoding="utf-8"
    )
    print(json.dumps(counts))


if __name__ == "__main__":
    main()
