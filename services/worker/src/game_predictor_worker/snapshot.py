"""Build and validate the deterministic SQLite spike snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import closing
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final, TypedDict, cast

RELEASE_VERSION: Final = "m1-spike.1"
SCHEMA_VERSION: Final = 1
ALGORITHM_VERSION: Final = "m1-spike.1"
SNAPSHOT_FILE: Final = "m1-spike.db"


@dataclass(frozen=True)
class DiagnosticRecord:
    sequence_number: int
    label: str


DIAGNOSTIC_RECORDS: Final[tuple[DiagnosticRecord, ...]] = (
    DiagnosticRecord(sequence_number=1, label="offline-ready"),
    DiagnosticRecord(sequence_number=2, label="schema-validated"),
    DiagnosticRecord(sequence_number=3, label="checksum-versioned"),
)


class SnapshotManifest(TypedDict):
    algorithmVersion: str
    logicalContentSha256: str
    recordCount: int
    releaseVersion: str
    schemaVersion: int
    snapshotFile: str
    snapshotFileSha256: str


class SnapshotValidationError(RuntimeError):
    """Raised when a generated snapshot does not satisfy its manifest."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _logical_content_sha256(records: Sequence[DiagnosticRecord]) -> str:
    content = {
        "algorithm_version": ALGORITHM_VERSION,
        "records": [asdict(record) for record in records],
        "release_version": RELEASE_VERSION,
        "schema_version": SCHEMA_VERSION,
    }
    return hashlib.sha256(_canonical_json(content)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _metadata(logical_content_sha256: str) -> Mapping[str, str]:
    return {
        "algorithm_version": ALGORITHM_VERSION,
        "logical_content_sha256": logical_content_sha256,
        "release_version": RELEASE_VERSION,
        "schema_version": str(SCHEMA_VERSION),
    }


def generate_snapshot(database_path: Path, manifest_path: Path) -> SnapshotManifest:
    """Create a deterministic SQLite database and matching external manifest."""

    database_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    logical_checksum = _logical_content_sha256(DIAGNOSTIC_RECORDS)

    temporary_handle, temporary_name = tempfile.mkstemp(
        prefix=f"{database_path.stem}-",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(temporary_handle)
    temporary_path = Path(temporary_name)

    try:
        with closing(sqlite3.connect(temporary_path)) as connection:
            with connection:
                connection.execute("PRAGMA page_size = 4096")
                connection.execute("PRAGMA journal_mode = DELETE")
                connection.execute("PRAGMA foreign_keys = ON")
                connection.executescript(
                    """
                    CREATE TABLE metadata (
                        key TEXT PRIMARY KEY NOT NULL,
                        value TEXT NOT NULL
                    ) WITHOUT ROWID;

                    CREATE TABLE diagnostic_record (
                        sequence_number INTEGER PRIMARY KEY,
                        label TEXT NOT NULL
                    );
                    """
                )
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    sorted(_metadata(logical_checksum).items()),
                )
                connection.executemany(
                    """
                    INSERT INTO diagnostic_record(sequence_number, label)
                    VALUES (?, ?)
                    """,
                    (
                        (record.sequence_number, record.label)
                        for record in DIAGNOSTIC_RECORDS
                    ),
                )
            connection.execute("VACUUM")

        temporary_path.replace(database_path)
    finally:
        temporary_path.unlink(missing_ok=True)

    manifest: SnapshotManifest = {
        "algorithmVersion": ALGORITHM_VERSION,
        "logicalContentSha256": logical_checksum,
        "recordCount": len(DIAGNOSTIC_RECORDS),
        "releaseVersion": RELEASE_VERSION,
        "schemaVersion": SCHEMA_VERSION,
        "snapshotFile": SNAPSHOT_FILE,
        "snapshotFileSha256": _file_sha256(database_path),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validate_snapshot(database_path, manifest_path)
    return manifest


def _load_manifest(path: Path) -> SnapshotManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotValidationError(f"Cannot read snapshot manifest: {error}") from error

    if not isinstance(value, dict):
        raise SnapshotValidationError("Snapshot manifest must be a JSON object.")
    return cast(SnapshotManifest, value)


def validate_snapshot(database_path: Path, manifest_path: Path) -> SnapshotManifest:
    """Validate the file checksum, SQLite integrity, metadata and record content."""

    manifest = _load_manifest(manifest_path)
    required_keys = {
        "algorithmVersion",
        "logicalContentSha256",
        "recordCount",
        "releaseVersion",
        "schemaVersion",
        "snapshotFile",
        "snapshotFileSha256",
    }
    if set(manifest) != required_keys:
        raise SnapshotValidationError("Snapshot manifest fields do not match the contract.")

    actual_file_checksum = _file_sha256(database_path)
    if manifest["snapshotFileSha256"] != actual_file_checksum:
        raise SnapshotValidationError("Snapshot file checksum does not match the manifest.")

    try:
        with closing(
            sqlite3.connect(f"file:{database_path}?mode=ro", uri=True)
        ) as connection:
            integrity_result = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity_result != ("ok",):
                raise SnapshotValidationError("SQLite integrity check failed.")

            database_metadata = dict(
                connection.execute("SELECT key, value FROM metadata").fetchall()
            )
            records = tuple(
                DiagnosticRecord(sequence_number=row[0], label=row[1])
                for row in connection.execute(
                    """
                    SELECT sequence_number, label
                    FROM diagnostic_record
                    ORDER BY sequence_number
                    """
                )
            )
    except sqlite3.Error as error:
        raise SnapshotValidationError(f"Cannot validate SQLite snapshot: {error}") from error

    expected_logical_checksum = _logical_content_sha256(records)
    expected_metadata = _metadata(expected_logical_checksum)

    if database_metadata != expected_metadata:
        raise SnapshotValidationError("SQLite metadata does not match its content.")
    if manifest["logicalContentSha256"] != expected_logical_checksum:
        raise SnapshotValidationError("Logical content checksum does not match the manifest.")
    if manifest["recordCount"] != len(records):
        raise SnapshotValidationError("Diagnostic record count does not match the manifest.")
    if manifest["releaseVersion"] != RELEASE_VERSION:
        raise SnapshotValidationError("Release version does not match the generator.")
    if manifest["schemaVersion"] != SCHEMA_VERSION:
        raise SnapshotValidationError("Schema version does not match the generator.")
    if manifest["algorithmVersion"] != ALGORITHM_VERSION:
        raise SnapshotValidationError("Algorithm version does not match the generator.")
    if manifest["snapshotFile"] != database_path.name:
        raise SnapshotValidationError("Snapshot filename does not match the manifest.")

    return manifest
