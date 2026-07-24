from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest
from game_predictor_worker.snapshot import (
    LOCAL_DATA_ERROR_CODE,
    SCHEMA_VERSION,
    SNAPSHOT_FILE,
    SQLITE_APPLICATION_ID,
    SnapshotValidationError,
    generate_snapshot,
    validate_snapshot,
)


def _paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / SNAPSHOT_FILE, tmp_path / "manifest.json"


def _load_manifest(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def _write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_generate_and_validate_complete_snapshot(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)

    generated = generate_snapshot(database_path, manifest_path)
    validated = validate_snapshot(database_path, manifest_path)

    assert validated == generated
    assert generated["schemaVersion"] == 2
    assert generated["gameCount"] == 3
    assert generated["layoutCount"] == 3_000
    assert generated["fixtureFingerprint"] == (
        "f349dcbeec49f4627d330ad4a63d1f1f09480ec1d60443b462debd6a1df69f88"
    )
    assert len(generated["snapshotFileSha256"]) == 64
    assert len(generated["logicalContentSha256"]) == 64
    assert [game["symbolCount"] for game in generated["games"]] == [10, 12, 11]


def test_database_contains_final_schema_counts_and_signature_index(
    tmp_path: Path,
) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)

    with closing(sqlite3.connect(database_path)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        index_sql = connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE name = 'idx_layouts_game_signature'
            """
        ).fetchone()
        user_version = connection.execute("PRAGMA user_version").fetchone()
        application_id = connection.execute("PRAGMA application_id").fetchone()
        game_count = connection.execute("SELECT COUNT(*) FROM games").fetchone()
        symbol_count = connection.execute("SELECT COUNT(*) FROM symbols").fetchone()
        layout_count = connection.execute("SELECT COUNT(*) FROM layouts").fetchone()

    assert tables == {"metadata", "games", "symbols", "layouts"}
    assert index_sql is not None
    assert "ON layouts(game_id, signature)" in index_sql[0]
    assert user_version == (SCHEMA_VERSION,)
    assert application_id == (SQLITE_APPLICATION_ID,)
    assert game_count == (3,)
    assert symbol_count == (33,)
    assert layout_count == (3_000,)


def test_sequences_and_controlled_duplicates_survive_persistence(
    tmp_path: Path,
) -> None:
    database_path, manifest_path = _paths(tmp_path)
    manifest = generate_snapshot(database_path, manifest_path)

    with closing(sqlite3.connect(database_path)) as connection:
        for game in manifest["games"]:
            sequence_summary = connection.execute(
                """
                SELECT COUNT(*), MIN(sequence_number), MAX(sequence_number)
                FROM layouts
                WHERE game_id = ?
                """,
                (game["id"],),
            ).fetchone()
            duplicate_groups = connection.execute(
                """
                SELECT signature, GROUP_CONCAT(sequence_number)
                FROM layouts
                WHERE game_id = ?
                GROUP BY signature
                HAVING COUNT(*) > 1
                ORDER BY signature
                """,
                (game["id"],),
            ).fetchall()

            assert sequence_summary == (1_000, 1, 1_000)
            expected_duplicates = sorted(
                (
                    duplicate["signature"],
                    ",".join(str(number) for number in duplicate["sequenceNumbers"]),
                )
                for duplicate in game["duplicateFixtures"]
            )
            assert duplicate_groups == expected_duplicates


def test_manifest_contains_full_cycle_golden_report(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)

    manifest = generate_snapshot(database_path, manifest_path)

    assert [
        (
            case["gameCode"],
            case["code"],
            case["startSequenceNumber"],
            len(case["expectedPositiveLocalPeaks"]),
        )
        for case in manifest["targetGoldenCases"]
    ] == [
        ("game-1", "multiple-peaks-later-lower-and-plateau", 99, 2),
        ("game-2", "single-positive-peak", 199, 1),
        ("game-2", "no-positive-peak", 200, 0),
    ]


def test_generation_is_byte_deterministic(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)

    first = generate_snapshot(database_path, manifest_path)
    first_database_bytes = database_path.read_bytes()
    first_manifest_bytes = manifest_path.read_bytes()
    second = generate_snapshot(database_path, manifest_path)

    assert database_path.read_bytes() == first_database_bytes
    assert manifest_path.read_bytes() == first_manifest_bytes
    assert second == first


def test_validation_rejects_changed_file(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)

    with database_path.open("ab") as file:
        file.write(b"changed")

    with pytest.raises(SnapshotValidationError, match="checksum") as error:
        validate_snapshot(database_path, manifest_path)

    assert error.value.code == LOCAL_DATA_ERROR_CODE


def test_validation_rejects_missing_manifest_field(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)
    manifest = _load_manifest(manifest_path)
    del manifest["fixtureFingerprint"]
    _write_manifest(manifest_path, manifest)

    with pytest.raises(SnapshotValidationError, match="fields"):
        validate_snapshot(database_path, manifest_path)


def test_validation_rejects_malformed_nested_manifest(tmp_path: Path) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)
    manifest = _load_manifest(manifest_path)
    manifest["games"][0]["duplicateFixtures"][0]["sequenceNumbers"] = [101]
    _write_manifest(manifest_path, manifest)

    with pytest.raises(SnapshotValidationError, match="duplicate fixture"):
        validate_snapshot(database_path, manifest_path)


def test_validation_rejects_content_change_even_with_updated_file_checksum(
    tmp_path: Path,
) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute(
            """
            UPDATE layouts
            SET payout = payout + 1
            WHERE game_id = 3 AND sequence_number = 1
            """
        )
    manifest = _load_manifest(manifest_path)
    manifest["snapshotFileSha256"] = _file_sha256(database_path)
    _write_manifest(manifest_path, manifest)

    with pytest.raises(SnapshotValidationError, match="Logical content checksum"):
        validate_snapshot(database_path, manifest_path)


def test_validation_rejects_sequence_gap_even_with_updated_file_checksum(
    tmp_path: Path,
) -> None:
    database_path, manifest_path = _paths(tmp_path)
    generate_snapshot(database_path, manifest_path)
    with closing(sqlite3.connect(database_path)) as connection, connection:
        connection.execute("DELETE FROM layouts WHERE game_id = 1 AND sequence_number = 500")
    manifest = _load_manifest(manifest_path)
    manifest["snapshotFileSha256"] = _file_sha256(database_path)
    _write_manifest(manifest_path, manifest)

    with pytest.raises(SnapshotValidationError, match="counts|continuous"):
        validate_snapshot(database_path, manifest_path)


def test_generation_requires_release_snapshot_filename(tmp_path: Path) -> None:
    with pytest.raises(SnapshotValidationError, match=SNAPSHOT_FILE):
        generate_snapshot(tmp_path / "wrong.db", tmp_path / "manifest.json")
