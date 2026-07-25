"""Generate and validate the immutable M1 SQLite snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections import defaultdict
from collections.abc import Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Final, TypedDict, TypeGuard, cast

from game_predictor_worker.domain import DomainValidationError, decode_signature
from game_predictor_worker.fixtures import (
    GeneratedGameFixture,
    M1Fixture,
    generate_m1_fixture,
    validate_m1_fixture,
)

RELEASE_VERSION: Final = "m1-fixture.2"
SCHEMA_VERSION: Final = 2
CREATED_AT: Final = "2026-07-24T00:00:00Z"
SNAPSHOT_FILE: Final = "m1-snapshot.db"
SQLITE_APPLICATION_ID: Final = 0x47505244
LOCAL_DATA_ERROR_CODE: Final = "local_data_error"

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_REQUIRED_TABLES = frozenset({"metadata", "games", "symbols", "layouts"})
_SIGNATURE_INDEX = "idx_layouts_game_signature"

GameRow = tuple[int, str, str, int, int, int, int, int, int, int]
SymbolRow = tuple[int, int, str, str, int, int, str | None]
LayoutRow = tuple[int, int, str, int]


class ManifestDuplicateFixture(TypedDict):
    sequenceNumbers: list[int]
    signature: str


class ManifestUniquePrefixFixture(TypedDict):
    cellCount: int
    sequenceNumber: int
    signaturePrefix: str


class ManifestGame(TypedDict):
    code: str
    datasetVersion: int
    duplicateFixtures: list[ManifestDuplicateFixture]
    id: int
    layoutCount: int
    rulesVersion: int
    seed: int
    symbolCount: int
    uniquePrefixFixture: ManifestUniquePrefixFixture


class ManifestTargetPeak(TypedDict):
    cumulativeCost: int
    cumulativePayout: int
    netCredits: int
    sequenceNumber: int
    spinNumber: int
    spinPayout: int


class ManifestTargetGoldenCase(TypedDict):
    code: str
    expectedFinalCumulativeCost: int
    expectedFinalCumulativePayout: int
    expectedFinalNetCredits: int
    expectedPositiveLocalPeaks: list[ManifestTargetPeak]
    gameCode: str
    startSequenceNumber: int


class SnapshotManifest(TypedDict):
    algorithmVersion: str
    createdAt: str
    datasetVersion: int
    fixtureFingerprint: str
    fixtureVersion: str
    gameCount: int
    games: list[ManifestGame]
    layoutCount: int
    logicalContentSha256: str
    releaseVersion: str
    rulesVersion: int
    schemaVersion: int
    snapshotFile: str
    snapshotFileSha256: str
    targetGoldenCases: list[ManifestTargetGoldenCase]


class SnapshotValidationError(RuntimeError):
    """A stable local snapshot integrity failure."""

    code = LOCAL_DATA_ERROR_CODE


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise SnapshotValidationError(f"Cannot read SQLite snapshot: {error}") from error
    return digest.hexdigest()


def _database_rows(
    fixture: M1Fixture,
) -> tuple[tuple[GameRow, ...], tuple[SymbolRow, ...], tuple[LayoutRow, ...]]:
    game_rows: list[GameRow] = []
    symbol_rows: list[SymbolRow] = []
    layout_rows: list[LayoutRow] = []
    for game_id, game_fixture in enumerate(fixture.games, start=1):
        game = game_fixture.game
        game_rows.append(
            (
                game_id,
                game.code,
                game.name,
                game.rows,
                game.columns,
                game.spin_cost,
                game.signature_cell_width,
                len(game_fixture.layouts),
                fixture.dataset_version,
                fixture.rules_version,
            )
        )
        symbol_rows.extend(
            (
                game_id,
                symbol.mobile_code,
                symbol.code,
                symbol.name,
                int(symbol.is_wildcard),
                symbol.display_order,
                None,
            )
            for symbol in game.symbols
        )
        layout_rows.extend(
            (
                game_id,
                layout.sequence_number,
                layout.signature,
                layout.payout_credits,
            )
            for layout in game_fixture.layouts
        )
    return tuple(game_rows), tuple(symbol_rows), tuple(layout_rows)


def _logical_content_sha256(
    *,
    release_version: str,
    schema_version: int,
    created_at: str,
    fixture_version: str,
    fixture_fingerprint: str,
    algorithm_version: str,
    dataset_version: int,
    rules_version: int,
    game_rows: Sequence[GameRow],
    symbol_rows: Sequence[SymbolRow],
    layout_rows: Sequence[LayoutRow],
) -> str:
    content = {
        "algorithm_version": algorithm_version,
        "created_at": created_at,
        "dataset_version": dataset_version,
        "fixture_fingerprint": fixture_fingerprint,
        "fixture_version": fixture_version,
        "games": list(game_rows),
        "layouts": list(layout_rows),
        "release_version": release_version,
        "rules_version": rules_version,
        "schema_version": schema_version,
        "symbols": list(symbol_rows),
    }
    return hashlib.sha256(_canonical_json(content)).hexdigest()


def _manifest_game(
    game_id: int,
    fixture: M1Fixture,
    game_fixture: GeneratedGameFixture,
) -> ManifestGame:
    prefix = game_fixture.unique_prefix_fixture
    return {
        "code": game_fixture.game.code,
        "datasetVersion": fixture.dataset_version,
        "duplicateFixtures": [
            {
                "sequenceNumbers": list(duplicate.sequence_numbers),
                "signature": duplicate.signature,
            }
            for duplicate in game_fixture.duplicate_fixtures
        ],
        "id": game_id,
        "layoutCount": len(game_fixture.layouts),
        "rulesVersion": fixture.rules_version,
        "seed": game_fixture.seed,
        "symbolCount": len(game_fixture.game.symbols),
        "uniquePrefixFixture": {
            "cellCount": prefix.cell_count,
            "sequenceNumber": prefix.sequence_number,
            "signaturePrefix": prefix.signature_prefix,
        },
    }


def _manifest_target_cases(fixture: M1Fixture) -> list[ManifestTargetGoldenCase]:
    return [
        {
            "code": golden.code,
            "expectedFinalCumulativeCost": golden.expected_final_cumulative_cost,
            "expectedFinalCumulativePayout": golden.expected_final_cumulative_payout,
            "expectedFinalNetCredits": golden.expected_final_net_credits,
            "expectedPositiveLocalPeaks": [
                {
                    "cumulativeCost": peak.cumulative_cost,
                    "cumulativePayout": peak.cumulative_payout,
                    "netCredits": peak.net_credits,
                    "sequenceNumber": peak.sequence_number,
                    "spinNumber": peak.spin_number,
                    "spinPayout": peak.spin_payout,
                }
                for peak in golden.expected_positive_local_peaks
            ],
            "gameCode": game_fixture.game.code,
            "startSequenceNumber": golden.start_sequence_number,
        }
        for game_fixture in fixture.games
        for golden in game_fixture.target_golden_fixtures
    ]


def _build_manifest(
    fixture: M1Fixture,
    *,
    fixture_fingerprint: str,
    logical_content_sha256: str,
    snapshot_file_sha256: str,
) -> SnapshotManifest:
    return {
        "algorithmVersion": fixture.algorithm_version,
        "createdAt": CREATED_AT,
        "datasetVersion": fixture.dataset_version,
        "fixtureFingerprint": fixture_fingerprint,
        "fixtureVersion": fixture.fixture_version,
        "gameCount": len(fixture.games),
        "games": [
            _manifest_game(game_id, fixture, game_fixture)
            for game_id, game_fixture in enumerate(fixture.games, start=1)
        ],
        "layoutCount": sum(len(game.layouts) for game in fixture.games),
        "logicalContentSha256": logical_content_sha256,
        "releaseVersion": RELEASE_VERSION,
        "rulesVersion": fixture.rules_version,
        "schemaVersion": SCHEMA_VERSION,
        "snapshotFile": SNAPSHOT_FILE,
        "snapshotFileSha256": snapshot_file_sha256,
        "targetGoldenCases": _manifest_target_cases(fixture),
    }


def _metadata(manifest: SnapshotManifest) -> Mapping[str, str]:
    return {
        "algorithm_version": manifest["algorithmVersion"],
        "content_checksum": manifest["logicalContentSha256"],
        "created_at": manifest["createdAt"],
        "dataset_version": str(manifest["datasetVersion"]),
        "fixture_fingerprint": manifest["fixtureFingerprint"],
        "fixture_version": manifest["fixtureVersion"],
        "game_count": str(manifest["gameCount"]),
        "layout_count": str(manifest["layoutCount"]),
        "release_version": manifest["releaseVersion"],
        "rules_version": str(manifest["rulesVersion"]),
        "snapshot_schema_version": str(manifest["schemaVersion"]),
    }


def _create_database(
    database_path: Path,
    manifest: SnapshotManifest,
    game_rows: Sequence[GameRow],
    symbol_rows: Sequence[SymbolRow],
    layout_rows: Sequence[LayoutRow],
) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        connection.execute("PRAGMA page_size = 4096")
        connection.execute("PRAGMA journal_mode = DELETE")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        with connection:
            connection.executescript(
                f"""
                CREATE TABLE metadata (
                    key TEXT PRIMARY KEY NOT NULL,
                    value TEXT NOT NULL
                ) WITHOUT ROWID;

                CREATE TABLE games (
                    id INTEGER PRIMARY KEY,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    rows INTEGER NOT NULL CHECK (rows > 0),
                    columns INTEGER NOT NULL CHECK (columns > 0),
                    spin_cost INTEGER NOT NULL CHECK (spin_cost >= 0),
                    signature_cell_width INTEGER NOT NULL
                        CHECK (signature_cell_width BETWEEN 1 AND 5),
                    layout_count INTEGER NOT NULL CHECK (layout_count > 0),
                    dataset_version INTEGER NOT NULL CHECK (dataset_version > 0),
                    rules_version INTEGER NOT NULL CHECK (rules_version > 0)
                );

                CREATE TABLE symbols (
                    game_id INTEGER NOT NULL,
                    mobile_code INTEGER NOT NULL
                        CHECK (mobile_code BETWEEN 1 AND 32767),
                    code TEXT NOT NULL,
                    name TEXT NOT NULL,
                    is_wildcard INTEGER NOT NULL CHECK (is_wildcard IN (0, 1)),
                    display_order INTEGER NOT NULL CHECK (display_order >= 0),
                    image_asset_key TEXT,
                    PRIMARY KEY (game_id, mobile_code),
                    UNIQUE (game_id, code),
                    FOREIGN KEY (game_id) REFERENCES games(id)
                ) WITHOUT ROWID;

                CREATE TABLE layouts (
                    game_id INTEGER NOT NULL,
                    sequence_number INTEGER NOT NULL CHECK (sequence_number > 0),
                    signature TEXT NOT NULL,
                    payout INTEGER NOT NULL CHECK (payout >= 0),
                    PRIMARY KEY (game_id, sequence_number),
                    FOREIGN KEY (game_id) REFERENCES games(id)
                ) WITHOUT ROWID;

                CREATE INDEX {_SIGNATURE_INDEX}
                    ON layouts(game_id, signature);
                """
            )
            connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(_metadata(manifest).items()),
            )
            connection.executemany(
                """
                INSERT INTO games(
                    id, code, name, rows, columns, spin_cost,
                    signature_cell_width, layout_count,
                    dataset_version, rules_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                game_rows,
            )
            connection.executemany(
                """
                INSERT INTO symbols(
                    game_id, mobile_code, code, name, is_wildcard,
                    display_order, image_asset_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                symbol_rows,
            )
            connection.executemany(
                """
                INSERT INTO layouts(
                    game_id, sequence_number, signature, payout
                ) VALUES (?, ?, ?, ?)
                """,
                layout_rows,
            )
        connection.execute("VACUUM")


def _write_manifest(path: Path, manifest: SnapshotManifest) -> None:
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _temporary_path(parent: Path, stem: str, suffix: str) -> Path:
    handle, name = tempfile.mkstemp(prefix=f"{stem}-", suffix=suffix, dir=parent)
    os.close(handle)
    return Path(name)


def generate_snapshot(
    database_path: Path,
    manifest_path: Path,
    fixture: M1Fixture | None = None,
) -> SnapshotManifest:
    """Atomically replace snapshot artifacts after validating temporary output."""

    if database_path.name != SNAPSHOT_FILE:
        raise SnapshotValidationError(f"Snapshot database must be named {SNAPSHOT_FILE}.")
    fixture = generate_m1_fixture() if fixture is None else fixture
    fixture_report = validate_m1_fixture(fixture)
    game_rows, symbol_rows, layout_rows = _database_rows(fixture)
    logical_checksum = _logical_content_sha256(
        release_version=RELEASE_VERSION,
        schema_version=SCHEMA_VERSION,
        created_at=CREATED_AT,
        fixture_version=fixture.fixture_version,
        fixture_fingerprint=fixture_report.fixture_fingerprint,
        algorithm_version=fixture.algorithm_version,
        dataset_version=fixture.dataset_version,
        rules_version=fixture.rules_version,
        game_rows=game_rows,
        symbol_rows=symbol_rows,
        layout_rows=layout_rows,
    )

    database_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_database = _temporary_path(
        database_path.parent,
        database_path.stem,
        ".db.tmp",
    )
    temporary_manifest = _temporary_path(
        manifest_path.parent,
        manifest_path.stem,
        ".json.tmp",
    )
    try:
        incomplete_manifest = _build_manifest(
            fixture,
            fixture_fingerprint=fixture_report.fixture_fingerprint,
            logical_content_sha256=logical_checksum,
            snapshot_file_sha256="0" * 64,
        )
        _create_database(
            temporary_database,
            incomplete_manifest,
            game_rows,
            symbol_rows,
            layout_rows,
        )
        manifest = _build_manifest(
            fixture,
            fixture_fingerprint=fixture_report.fixture_fingerprint,
            logical_content_sha256=logical_checksum,
            snapshot_file_sha256=_file_sha256(temporary_database),
        )
        _write_manifest(temporary_manifest, manifest)
        _validate_snapshot_content(
            temporary_database,
            manifest,
            expected_snapshot_file=database_path.name,
        )
        temporary_database.replace(database_path)
        temporary_manifest.replace(manifest_path)
    finally:
        temporary_database.unlink(missing_ok=True)
        temporary_manifest.unlink(missing_ok=True)

    return validate_snapshot(database_path, manifest_path)


def _load_manifest(path: Path) -> SnapshotManifest:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SnapshotValidationError(f"Cannot read snapshot manifest: {error}") from error
    if not isinstance(value, dict):
        raise SnapshotValidationError("Snapshot manifest must be a JSON object.")
    manifest = cast(SnapshotManifest, value)
    _validate_manifest_contract(manifest)
    return manifest


def _is_int(value: object) -> TypeGuard[int]:
    return type(value) is int


def _validate_manifest_game(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "code",
        "datasetVersion",
        "duplicateFixtures",
        "id",
        "layoutCount",
        "rulesVersion",
        "seed",
        "symbolCount",
        "uniquePrefixFixture",
    }:
        raise SnapshotValidationError("Snapshot game manifest is invalid.")
    if (
        not isinstance(value["code"], str)
        or not value["code"]
        or any(
            not _is_int(value[key])
            for key in (
                "datasetVersion",
                "id",
                "layoutCount",
                "rulesVersion",
                "seed",
                "symbolCount",
            )
        )
        or not isinstance(value["duplicateFixtures"], list)
        or not isinstance(value["uniquePrefixFixture"], dict)
    ):
        raise SnapshotValidationError("Snapshot game manifest types are invalid.")
    if any(
        cast(int, value[key]) < 1
        for key in (
            "datasetVersion",
            "id",
            "layoutCount",
            "rulesVersion",
            "seed",
            "symbolCount",
        )
    ):
        raise SnapshotValidationError("Snapshot game manifest values are invalid.")
    for duplicate in value["duplicateFixtures"]:
        if (
            not isinstance(duplicate, dict)
            or set(duplicate) != {"sequenceNumbers", "signature"}
            or not isinstance(duplicate["signature"], str)
            or not duplicate["signature"]
            or not isinstance(duplicate["sequenceNumbers"], list)
            or len(duplicate["sequenceNumbers"]) != 2
            or any(not _is_int(number) or number < 1 for number in duplicate["sequenceNumbers"])
        ):
            raise SnapshotValidationError("Snapshot duplicate fixture manifest is invalid.")
    prefix = value["uniquePrefixFixture"]
    if (
        set(prefix) != {"cellCount", "sequenceNumber", "signaturePrefix"}
        or not _is_int(prefix["cellCount"])
        or prefix["cellCount"] < 1
        or not _is_int(prefix["sequenceNumber"])
        or prefix["sequenceNumber"] < 1
        or not isinstance(prefix["signaturePrefix"], str)
        or not prefix["signaturePrefix"]
    ):
        raise SnapshotValidationError("Snapshot unique-prefix fixture manifest is invalid.")


def _validate_manifest_target_case(value: object) -> None:
    if not isinstance(value, dict) or set(value) != {
        "code",
        "expectedFinalCumulativeCost",
        "expectedFinalCumulativePayout",
        "expectedFinalNetCredits",
        "expectedPositiveLocalPeaks",
        "gameCode",
        "startSequenceNumber",
    }:
        raise SnapshotValidationError("Target golden case manifest is invalid.")
    if (
        not isinstance(value["code"], str)
        or not value["code"]
        or not isinstance(value["gameCode"], str)
        or not value["gameCode"]
        or any(
            not _is_int(value[key])
            for key in (
                "expectedFinalCumulativeCost",
                "expectedFinalCumulativePayout",
                "expectedFinalNetCredits",
                "startSequenceNumber",
            )
        )
        or not isinstance(value["expectedPositiveLocalPeaks"], list)
    ):
        raise SnapshotValidationError("Target golden case types are invalid.")
    for peak in value["expectedPositiveLocalPeaks"]:
        if (
            not isinstance(peak, dict)
            or set(peak)
            != {
                "cumulativeCost",
                "cumulativePayout",
                "netCredits",
                "sequenceNumber",
                "spinNumber",
                "spinPayout",
            }
            or any(not _is_int(peak[key]) for key in peak)
        ):
            raise SnapshotValidationError("Target golden peak manifest is invalid.")


def _validate_manifest_contract(manifest: SnapshotManifest) -> None:
    required_keys = {
        "algorithmVersion",
        "createdAt",
        "datasetVersion",
        "fixtureFingerprint",
        "fixtureVersion",
        "gameCount",
        "games",
        "layoutCount",
        "logicalContentSha256",
        "releaseVersion",
        "rulesVersion",
        "schemaVersion",
        "snapshotFile",
        "snapshotFileSha256",
        "targetGoldenCases",
    }
    if set(manifest) != required_keys:
        raise SnapshotValidationError("Snapshot manifest fields do not match the contract.")
    string_keys = (
        "algorithmVersion",
        "createdAt",
        "fixtureFingerprint",
        "fixtureVersion",
        "logicalContentSha256",
        "releaseVersion",
        "snapshotFile",
        "snapshotFileSha256",
    )
    integer_keys = (
        "datasetVersion",
        "gameCount",
        "layoutCount",
        "rulesVersion",
        "schemaVersion",
    )
    manifest_values = cast(Mapping[str, object], manifest)
    if any(
        not isinstance(manifest_values[key], str) or not manifest_values[key] for key in string_keys
    ) or any(not _is_int(manifest_values[key]) for key in integer_keys):
        raise SnapshotValidationError("Snapshot manifest contains invalid value types.")
    if (
        not _SHA256_PATTERN.fullmatch(manifest["fixtureFingerprint"])
        or not _SHA256_PATTERN.fullmatch(manifest["logicalContentSha256"])
        or not _SHA256_PATTERN.fullmatch(manifest["snapshotFileSha256"])
    ):
        raise SnapshotValidationError("Snapshot manifest contains an invalid SHA-256.")
    if not isinstance(manifest["games"], list) or not isinstance(
        manifest["targetGoldenCases"],
        list,
    ):
        raise SnapshotValidationError("Snapshot manifest collections are invalid.")
    for game in manifest["games"]:
        _validate_manifest_game(game)
    for target_case in manifest["targetGoldenCases"]:
        _validate_manifest_target_case(target_case)
    if (
        manifest["releaseVersion"] != RELEASE_VERSION
        or manifest["schemaVersion"] != SCHEMA_VERSION
        or manifest["createdAt"] != CREATED_AT
        or manifest["snapshotFile"] != SNAPSHOT_FILE
    ):
        raise SnapshotValidationError(
            "Snapshot manifest version does not match this application build."
        )


def _read_database(
    database_path: Path,
) -> tuple[
    dict[str, str],
    tuple[GameRow, ...],
    tuple[SymbolRow, ...],
    tuple[LayoutRow, ...],
]:
    try:
        uri = f"file:{database_path.resolve().as_posix()}?mode=ro&immutable=1"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                raise SnapshotValidationError("SQLite integrity check failed.")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise SnapshotValidationError("SQLite foreign key check failed.")
            user_version = connection.execute("PRAGMA user_version").fetchone()
            application_id = connection.execute("PRAGMA application_id").fetchone()
            if user_version != (SCHEMA_VERSION,):
                raise SnapshotValidationError("SQLite user_version is unsupported.")
            if application_id != (SQLITE_APPLICATION_ID,):
                raise SnapshotValidationError("SQLite application_id is invalid.")

            table_names = frozenset(
                row[0]
                for row in connection.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                )
            )
            if table_names != _REQUIRED_TABLES:
                raise SnapshotValidationError("SQLite tables do not match the schema.")
            index_row = connection.execute(
                """
                SELECT sql
                FROM sqlite_master
                WHERE type = 'index' AND name = ?
                """,
                (_SIGNATURE_INDEX,),
            ).fetchone()
            if index_row is None:
                raise SnapshotValidationError("SQLite signature index is missing.")

            metadata = dict(
                cast(
                    list[tuple[str, str]],
                    connection.execute("SELECT key, value FROM metadata ORDER BY key").fetchall(),
                )
            )
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
                            game_id, mobile_code, code, name, is_wildcard,
                            display_order, image_asset_key
                        FROM symbols
                        ORDER BY game_id, mobile_code
                        """
                    ).fetchall(),
                )
            )
            layout_rows = tuple(
                cast(
                    list[LayoutRow],
                    connection.execute(
                        """
                        SELECT game_id, sequence_number, signature, payout
                        FROM layouts
                        ORDER BY game_id, sequence_number
                        """
                    ).fetchall(),
                )
            )
    except sqlite3.Error as error:
        raise SnapshotValidationError(f"Cannot validate SQLite snapshot: {error}") from error
    return metadata, game_rows, symbol_rows, layout_rows


def _validate_game_rows(
    manifest: SnapshotManifest,
    game_rows: Sequence[GameRow],
    symbol_rows: Sequence[SymbolRow],
    layout_rows: Sequence[LayoutRow],
) -> None:
    if len(game_rows) != manifest["gameCount"] or len(layout_rows) != manifest["layoutCount"]:
        raise SnapshotValidationError("Snapshot counts do not match the manifest.")

    symbols_by_game: defaultdict[int, set[int]] = defaultdict(set)
    for game_id, mobile_code, *_rest in symbol_rows:
        symbols_by_game[game_id].add(mobile_code)
    layouts_by_game: defaultdict[int, list[LayoutRow]] = defaultdict(list)
    for layout in layout_rows:
        layouts_by_game[layout[0]].append(layout)

    manifest_games = {game["id"]: game for game in manifest["games"]}
    if len(manifest_games) != len(manifest["games"]):
        raise SnapshotValidationError("Snapshot manifest game ids are not unique.")

    for game_row in game_rows:
        (
            game_id,
            code,
            _name,
            rows,
            columns,
            _spin_cost,
            cell_width,
            layout_count,
            dataset_version,
            rules_version,
        ) = game_row
        manifest_game = manifest_games.get(game_id)
        if manifest_game is None or (
            manifest_game["code"],
            manifest_game["layoutCount"],
            manifest_game["datasetVersion"],
            manifest_game["rulesVersion"],
            manifest_game["symbolCount"],
        ) != (
            code,
            layout_count,
            dataset_version,
            rules_version,
            len(symbols_by_game[game_id]),
        ):
            raise SnapshotValidationError("Snapshot game rows do not match the manifest.")

        game_layouts = layouts_by_game[game_id]
        sequence_numbers = tuple(layout[1] for layout in game_layouts)
        if sequence_numbers != tuple(range(1, layout_count + 1)):
            raise SnapshotValidationError(f"Snapshot sequence for {code} is not continuous.")
        for _layout_game_id, sequence_number, signature, payout in game_layouts:
            if payout < 0:
                raise SnapshotValidationError(
                    f"Snapshot payout for {code}/{sequence_number} is negative."
                )
            try:
                cells = decode_signature(
                    signature,
                    cell_width,
                    expected_cell_count=rows * columns,
                )
            except DomainValidationError as error:
                raise SnapshotValidationError(
                    f"Snapshot signature for {code}/{sequence_number} is invalid."
                ) from error
            if any(cell not in symbols_by_game[game_id] for cell in cells):
                raise SnapshotValidationError(
                    f"Snapshot signature for {code}/{sequence_number} uses an unknown symbol."
                )

        signature_positions: defaultdict[str, list[int]] = defaultdict(list)
        for _layout_game_id, sequence_number, signature, _payout in game_layouts:
            signature_positions[signature].append(sequence_number)
        observed_duplicates = {
            signature: sequence_numbers
            for signature, sequence_numbers in signature_positions.items()
            if len(sequence_numbers) > 1
        }
        declared_duplicates = {
            duplicate["signature"]: duplicate["sequenceNumbers"]
            for duplicate in manifest_game["duplicateFixtures"]
        }
        if observed_duplicates != declared_duplicates or any(
            len(sequence_numbers) != 2 for sequence_numbers in observed_duplicates.values()
        ):
            raise SnapshotValidationError(
                f"Snapshot duplicate groups for {code} do not match the manifest."
            )

        prefix = manifest_game["uniquePrefixFixture"]
        prefix_matches = [
            layout for layout in game_layouts if layout[2].startswith(prefix["signaturePrefix"])
        ]
        if (
            len(prefix_matches) != 1
            or prefix_matches[0][1] != prefix["sequenceNumber"]
            or len(prefix["signaturePrefix"]) != prefix["cellCount"] * cell_width
            or prefix["cellCount"] >= rows * columns
        ):
            raise SnapshotValidationError(
                f"Snapshot unique prefix for {code} does not match the manifest."
            )


def _validate_target_cases(
    manifest: SnapshotManifest,
    game_rows: Sequence[GameRow],
    layout_rows: Sequence[LayoutRow],
) -> None:
    game_ids = {game_row[1]: game_row[0] for game_row in game_rows}
    layouts_by_game: defaultdict[int, list[LayoutRow]] = defaultdict(list)
    for layout in layout_rows:
        layouts_by_game[layout[0]].append(layout)
    for target_case in manifest["targetGoldenCases"]:
        if not isinstance(target_case, dict):
            raise SnapshotValidationError("Target golden case manifest is invalid.")
        game_code = target_case.get("gameCode")
        start_value = target_case.get("startSequenceNumber")
        if not isinstance(game_code, str) or not _is_int(start_value):
            raise SnapshotValidationError("Target golden case start is invalid.")
        start = start_value
        game_id = game_ids.get(game_code)
        if game_id is None:
            raise SnapshotValidationError("Target golden case game is invalid.")
        layouts = layouts_by_game[game_id]
        if start < 1 or start > len(layouts):
            raise SnapshotValidationError("Target golden case start is out of range.")
        ordered = layouts[start:] + layouts[: start - 1]
        final_payout = sum(layout[3] for layout in ordered)
        game_row = next(game for game in game_rows if game[0] == game_id)
        final_cost = len(ordered) * game_row[5]
        if (
            target_case.get("expectedFinalCumulativePayout") != final_payout
            or target_case.get("expectedFinalCumulativeCost") != final_cost
            or target_case.get("expectedFinalNetCredits") != final_payout - final_cost
        ):
            raise SnapshotValidationError("Target golden case totals are invalid.")


def _validate_snapshot_content(
    database_path: Path,
    manifest: SnapshotManifest,
    *,
    expected_snapshot_file: str,
) -> None:
    _validate_manifest_contract(manifest)
    if manifest["snapshotFile"] != expected_snapshot_file:
        raise SnapshotValidationError("Snapshot filename does not match the manifest.")
    if _file_sha256(database_path) != manifest["snapshotFileSha256"]:
        raise SnapshotValidationError("Snapshot file checksum does not match the manifest.")

    metadata, game_rows, symbol_rows, layout_rows = _read_database(database_path)
    if metadata != _metadata(manifest):
        raise SnapshotValidationError("SQLite metadata does not match the manifest.")
    _validate_game_rows(manifest, game_rows, symbol_rows, layout_rows)
    _validate_target_cases(manifest, game_rows, layout_rows)

    logical_checksum = _logical_content_sha256(
        release_version=metadata["release_version"],
        schema_version=int(metadata["snapshot_schema_version"]),
        created_at=metadata["created_at"],
        fixture_version=metadata["fixture_version"],
        fixture_fingerprint=metadata["fixture_fingerprint"],
        algorithm_version=metadata["algorithm_version"],
        dataset_version=int(metadata["dataset_version"]),
        rules_version=int(metadata["rules_version"]),
        game_rows=game_rows,
        symbol_rows=symbol_rows,
        layout_rows=layout_rows,
    )
    if logical_checksum != manifest["logicalContentSha256"]:
        raise SnapshotValidationError("Logical content checksum does not match the manifest.")


def validate_snapshot(
    database_path: Path,
    manifest_path: Path,
) -> SnapshotManifest:
    """Validate file checksum, schema, logical content and release metadata."""

    manifest = _load_manifest(manifest_path)
    _validate_snapshot_content(
        database_path,
        manifest,
        expected_snapshot_file=database_path.name,
    )
    return manifest
