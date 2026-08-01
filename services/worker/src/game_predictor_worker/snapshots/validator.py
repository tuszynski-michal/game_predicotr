"""Independent read-only verification of a completed snapshot artifact."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from game_predictor_worker.domain import DomainValidationError, decode_signature
from game_predictor_worker.snapshots.generator import (
    PRODUCTION_SNAPSHOT_SCHEMA_VERSION,
    SIGNATURE_INDEX_NAME,
    SQLITE_APPLICATION_ID,
)
from game_predictor_worker.snapshots.integrity import (
    GameRow,
    LayoutRow,
    LogicalSnapshotChecksum,
    SymbolRow,
    file_sha256,
)
from game_predictor_worker.snapshots.manifest import (
    SNAPSHOT_DATABASE_FILE,
    SNAPSHOT_MANIFEST_FILE,
    SnapshotArtifactError,
    SnapshotArtifactManifest,
    load_snapshot_manifest,
)

_EXPECTED_TABLES = {"metadata", "games", "symbols", "layouts"}
_EXPECTED_COLUMNS = {
    "metadata": (
        ("key", "TEXT", 1),
        ("value", "TEXT", 0),
    ),
    "games": (
        ("id", "INTEGER", 1),
        ("code", "TEXT", 0),
        ("name", "TEXT", 0),
        ("rows", "INTEGER", 0),
        ("columns", "INTEGER", 0),
        ("spin_cost", "INTEGER", 0),
        ("signature_cell_width", "INTEGER", 0),
        ("layout_count", "INTEGER", 0),
        ("dataset_version", "INTEGER", 0),
        ("rules_version", "INTEGER", 0),
    ),
    "symbols": (
        ("game_id", "INTEGER", 1),
        ("mobile_code", "INTEGER", 2),
        ("code", "TEXT", 0),
        ("name", "TEXT", 0),
        ("name_pl", "TEXT", 0),
        ("name_en", "TEXT", 0),
        ("is_wildcard", "INTEGER", 0),
        ("display_order", "INTEGER", 0),
        ("image_asset_key", "TEXT", 0),
    ),
    "layouts": (
        ("game_id", "INTEGER", 1),
        ("sequence_number", "INTEGER", 2),
        ("signature", "TEXT", 0),
        ("payout", "INTEGER", 0),
    ),
}
_EXPECTED_METADATA_KEYS = {
    "algorithm_version",
    "content_checksum",
    "created_at",
    "game_count",
    "layout_count",
    "release_version",
    "snapshot_schema_version",
}


@dataclass(frozen=True, slots=True)
class SnapshotArtifact:
    directory: Path
    database_path: Path
    manifest_path: Path
    manifest: SnapshotArtifactManifest


def validate_snapshot_artifact(
    directory: Path,
    *,
    enforce_final_layout: bool = True,
) -> SnapshotArtifact:
    if directory.is_symlink():
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_LAYOUT_INVALID",
            "The snapshot artifact must not be a symbolic link.",
        )
    try:
        resolved_directory = directory.resolve(strict=True)
    except OSError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_NOT_FOUND",
            "The snapshot artifact directory does not exist.",
        ) from error
    if not resolved_directory.is_dir() or resolved_directory.is_symlink():
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_LAYOUT_INVALID",
            "The snapshot artifact must be a real directory.",
        )
    try:
        entries = {entry.name: entry for entry in resolved_directory.iterdir()}
    except OSError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_UNREADABLE",
            "The snapshot artifact directory cannot be read.",
        ) from error
    if set(entries) != {SNAPSHOT_DATABASE_FILE, SNAPSHOT_MANIFEST_FILE}:
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_LAYOUT_INVALID",
            "The snapshot artifact must contain only snapshot.db and manifest.json.",
        )
    if any(not entry.is_file() or entry.is_symlink() for entry in entries.values()):
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_LAYOUT_INVALID",
            "Snapshot artifact entries must be regular files.",
        )

    database_path = entries[SNAPSHOT_DATABASE_FILE]
    manifest_path = entries[SNAPSHOT_MANIFEST_FILE]
    manifest = load_snapshot_manifest(manifest_path)
    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_UNREADABLE",
            "The snapshot manifest cannot be read.",
        ) from error
    if manifest_bytes != manifest.to_bytes():
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_NOT_CANONICAL",
            "The snapshot manifest is not in canonical form.",
        )
    if enforce_final_layout and (
        resolved_directory.name != manifest.logical_content_sha256
        or resolved_directory.parent.name != manifest.release_version
        or resolved_directory.parent.parent.name != "snapshots"
    ):
        raise SnapshotArtifactError(
            "SNAPSHOT_ARTIFACT_LAYOUT_INVALID",
            "The artifact path does not match releaseVersion and logical checksum.",
        )
    try:
        observed_file_sha256 = file_sha256(database_path)
    except OSError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_DATABASE_UNREADABLE",
            "The SQLite snapshot cannot be read.",
        ) from error
    if observed_file_sha256 != manifest.snapshot_file_sha256:
        raise SnapshotArtifactError(
            "SNAPSHOT_FILE_CHECKSUM_MISMATCH",
            "The SQLite file checksum does not match the manifest.",
        )

    _validate_database(database_path, manifest)
    return SnapshotArtifact(
        directory=resolved_directory,
        database_path=database_path,
        manifest_path=manifest_path,
        manifest=manifest,
    )


def _validate_database(
    database_path: Path,
    manifest: SnapshotArtifactManifest,
) -> None:
    uri = f"{database_path.resolve().as_uri()}?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            _validate_pragmas_and_schema(connection, manifest)
            metadata = _read_metadata(connection)
            _validate_metadata(metadata, manifest)
            game_rows = tuple(
                cast(
                    list[GameRow],
                    connection.execute(
                        """
                        SELECT
                            id, code, name, rows, columns, spin_cost,
                            signature_cell_width, layout_count,
                            dataset_version, rules_version
                        FROM games
                        ORDER BY id
                        """
                    ).fetchall(),
                )
            )
            symbol_rows = tuple(
                cast(
                    list[SymbolRow],
                    connection.execute(
                        """
                        SELECT
                            game_id, mobile_code, code, name, name_pl, name_en,
                            is_wildcard, display_order, image_asset_key
                        FROM symbols
                        ORDER BY game_id, mobile_code
                        """
                    ).fetchall(),
                )
            )
            _validate_catalog(game_rows, symbol_rows, manifest)
            logical_checksum = LogicalSnapshotChecksum(
                release_version=metadata["release_version"],
                created_at=metadata["created_at"],
                schema_version=int(metadata["snapshot_schema_version"]),
                algorithm_version=metadata["algorithm_version"],
                game_count=len(game_rows),
                symbol_count=len(symbol_rows),
                layout_count=int(metadata["layout_count"]),
            )
            for game_row in game_rows:
                logical_checksum.add_game(game_row)
            for symbol_row in symbol_rows:
                logical_checksum.add_symbol(symbol_row)
            _validate_layouts(
                connection,
                game_rows,
                symbol_rows,
                manifest,
                logical_checksum,
            )
    except SnapshotArtifactError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_DATABASE_INVALID",
            "The SQLite snapshot cannot be validated.",
        ) from error

    observed_logical_checksum = logical_checksum.hexdigest()
    if (
        observed_logical_checksum != metadata["content_checksum"]
        or observed_logical_checksum != manifest.logical_content_sha256
    ):
        raise SnapshotArtifactError(
            "SNAPSHOT_LOGICAL_CHECKSUM_MISMATCH",
            "The reconstructed logical checksum does not match the artifact.",
        )


def _validate_pragmas_and_schema(
    connection: sqlite3.Connection,
    manifest: SnapshotArtifactManifest,
) -> None:
    quick_check = connection.execute("PRAGMA quick_check").fetchall()
    if quick_check != [("ok",)]:
        raise SnapshotArtifactError(
            "SNAPSHOT_DATABASE_CORRUPT",
            "SQLite quick_check did not pass.",
        )
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise SnapshotArtifactError(
            "SNAPSHOT_FOREIGN_KEY_INVALID",
            "The SQLite snapshot contains a foreign-key violation.",
        )
    user_version = connection.execute("PRAGMA user_version").fetchone()
    application_id = connection.execute("PRAGMA application_id").fetchone()
    if (
        user_version != (PRODUCTION_SNAPSHOT_SCHEMA_VERSION,)
        or user_version != (manifest.snapshot_schema_version,)
        or application_id != (SQLITE_APPLICATION_ID,)
    ):
        raise SnapshotArtifactError(
            "SNAPSHOT_SCHEMA_UNSUPPORTED",
            "The SQLite schema or application id is not supported.",
        )
    tables = {
        name
        for (name,) in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        )
    }
    if tables != _EXPECTED_TABLES:
        raise SnapshotArtifactError(
            "SNAPSHOT_SCHEMA_INVALID",
            "The SQLite table set is invalid.",
        )
    for table, expected_columns in _EXPECTED_COLUMNS.items():
        columns = tuple(
            (name, column_type, primary_key)
            for _, name, column_type, _, _, primary_key in connection.execute(
                f"PRAGMA table_info('{table}')"
            )
        )
        if columns != expected_columns:
            raise SnapshotArtifactError(
                "SNAPSHOT_SCHEMA_INVALID",
                f"The SQLite {table} columns are invalid.",
            )
    index_columns = tuple(
        name for _, _, name in connection.execute(f"PRAGMA index_info('{SIGNATURE_INDEX_NAME}')")
    )
    if index_columns != ("game_id", "signature"):
        raise SnapshotArtifactError(
            "SNAPSHOT_SIGNATURE_INDEX_INVALID",
            "The required game/signature index is missing or invalid.",
        )


def _read_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute("SELECT key, value FROM metadata ORDER BY key").fetchall()
    if any(not isinstance(key, str) or not isinstance(value, str) for key, value in rows):
        raise SnapshotArtifactError(
            "SNAPSHOT_METADATA_INVALID",
            "SQLite metadata must contain text keys and values.",
        )
    metadata = dict(cast(list[tuple[str, str]], rows))
    if len(metadata) != len(rows) or set(metadata) != _EXPECTED_METADATA_KEYS:
        raise SnapshotArtifactError(
            "SNAPSHOT_METADATA_INVALID",
            "SQLite metadata fields are incomplete or unexpected.",
        )
    return metadata


def _validate_metadata(
    metadata: dict[str, str],
    manifest: SnapshotArtifactManifest,
) -> None:
    expected = {
        "algorithm_version": manifest.algorithm_version,
        "content_checksum": manifest.logical_content_sha256,
        "created_at": manifest.created_at,
        "game_count": str(manifest.game_count),
        "layout_count": str(manifest.layout_count),
        "release_version": manifest.release_version,
        "snapshot_schema_version": str(manifest.snapshot_schema_version),
    }
    if metadata != expected:
        raise SnapshotArtifactError(
            "SNAPSHOT_METADATA_MISMATCH",
            "SQLite metadata does not match the manifest.",
        )


def _validate_catalog(
    game_rows: tuple[GameRow, ...],
    symbol_rows: tuple[SymbolRow, ...],
    manifest: SnapshotArtifactManifest,
) -> None:
    if len(game_rows) != manifest.game_count or len(symbol_rows) != manifest.symbol_count:
        raise SnapshotArtifactError(
            "SNAPSHOT_COUNT_MISMATCH",
            "SQLite catalog counts do not match the manifest.",
        )
    symbol_counts: defaultdict[int, int] = defaultdict(int)
    for (
        game_id,
        mobile_code,
        code,
        name,
        name_pl,
        name_en,
        is_wildcard,
        display_order,
        image_asset_key,
    ) in symbol_rows:
        if (
            mobile_code < 1
            or mobile_code > 32767
            or not code
            or not name
            or (name_pl is not None and not name_pl.strip())
            or (name_en is not None and not name_en.strip())
            or is_wildcard not in (0, 1)
            or display_order < 0
            or (image_asset_key is not None and not image_asset_key)
        ):
            raise SnapshotArtifactError(
                "SNAPSHOT_SYMBOL_INVALID",
                "A SQLite symbol record is invalid.",
            )
        symbol_counts[game_id] += 1

    expected_ids = tuple(range(1, len(game_rows) + 1))
    if tuple(row[0] for row in game_rows) != expected_ids or tuple(
        row[1] for row in game_rows
    ) != tuple(sorted(row[1] for row in game_rows)):
        raise SnapshotArtifactError(
            "SNAPSHOT_GAME_ORDER_INVALID",
            "SQLite games must use continuous ids ordered by stable code.",
        )
    for game_row, manifest_game in zip(game_rows, manifest.games, strict=True):
        (
            game_id,
            code,
            name,
            rows,
            columns,
            spin_cost,
            signature_cell_width,
            layout_count,
            dataset_version,
            rules_version,
        ) = game_row
        if (
            not name
            or rows < 1
            or columns < 1
            or spin_cost < 0
            or not 1 <= signature_cell_width <= 5
            or (
                game_id,
                code,
                rows,
                columns,
                signature_cell_width,
                layout_count,
                dataset_version,
                rules_version,
                symbol_counts[game_id],
            )
            != (
                manifest_game.mobile_game_id,
                manifest_game.game_code,
                manifest_game.rows,
                manifest_game.columns,
                manifest_game.signature_cell_width,
                manifest_game.layout_count,
                manifest_game.dataset_version,
                manifest_game.rules_version,
                manifest_game.symbol_count,
            )
        ):
            raise SnapshotArtifactError(
                "SNAPSHOT_GAME_MISMATCH",
                "A SQLite game record does not match the manifest.",
            )


def _validate_layouts(
    connection: sqlite3.Connection,
    game_rows: tuple[GameRow, ...],
    symbol_rows: tuple[SymbolRow, ...],
    manifest: SnapshotArtifactManifest,
    logical_checksum: LogicalSnapshotChecksum,
) -> None:
    games = {row[0]: row for row in game_rows}
    symbol_codes: defaultdict[int, set[int]] = defaultdict(set)
    for game_id, mobile_code, *_ in symbol_rows:
        symbol_codes[game_id].add(mobile_code)
    observed_counts: defaultdict[int, int] = defaultdict(int)
    expected_sequence: defaultdict[int, int] = defaultdict(lambda: 1)
    cursor = connection.execute(
        """
        SELECT game_id, sequence_number, signature, payout
        FROM layouts
        ORDER BY game_id, sequence_number
        """
    )
    while True:
        batch = cursor.fetchmany(1000)
        if not batch:
            break
        for raw_row in batch:
            game_id, sequence_number, signature, payout = cast(LayoutRow, raw_row)
            if (
                type(game_id) is not int
                or type(sequence_number) is not int
                or not isinstance(signature, str)
                or type(payout) is not int
            ):
                raise SnapshotArtifactError(
                    "SNAPSHOT_LAYOUT_INVALID",
                    "A SQLite layout record has invalid types.",
                )
            game = games.get(game_id)
            if game is None or sequence_number != expected_sequence[game_id]:
                raise SnapshotArtifactError(
                    "SNAPSHOT_SEQUENCE_INVALID",
                    "SQLite layout sequences are incomplete or unordered.",
                )
            if payout < 0:
                raise SnapshotArtifactError(
                    "SNAPSHOT_LAYOUT_INVALID",
                    "A SQLite layout signature or payout is invalid.",
                )
            try:
                cells = decode_signature(
                    signature,
                    game[6],
                    expected_cell_count=game[3] * game[4],
                )
            except DomainValidationError as error:
                raise SnapshotArtifactError(
                    "SNAPSHOT_SIGNATURE_INVALID",
                    "A SQLite layout signature is invalid.",
                ) from error
            if any(cell not in symbol_codes[game_id] for cell in cells):
                raise SnapshotArtifactError(
                    "SNAPSHOT_SYMBOL_REFERENCE_INVALID",
                    "A SQLite layout signature references an unknown symbol.",
                )
            logical_checksum.add_layout((game_id, sequence_number, signature, payout))
            expected_sequence[game_id] += 1
            observed_counts[game_id] += 1

    if sum(observed_counts.values()) != manifest.layout_count:
        raise SnapshotArtifactError(
            "SNAPSHOT_COUNT_MISMATCH",
            "SQLite layout count does not match the manifest.",
        )
    for game in game_rows:
        if observed_counts[game[0]] != game[7]:
            raise SnapshotArtifactError(
                "SNAPSHOT_SEQUENCE_INVALID",
                "A SQLite game layout count does not match its continuous sequence.",
            )
