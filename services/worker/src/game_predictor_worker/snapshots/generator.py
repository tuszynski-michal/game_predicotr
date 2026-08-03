"""Deterministic, bounded-memory SQLite generator for mobile releases."""

from __future__ import annotations

import os
import re
import sqlite3
import tempfile
from collections.abc import Sequence
from contextlib import closing
from datetime import UTC
from pathlib import Path
from typing import Final

from game_predictor_worker.payouts.readiness import PayoutReadinessService
from game_predictor_worker.snapshots.contracts import (
    ProductionSnapshotGameResult,
    ProductionSnapshotRepository,
    ProductionSnapshotResult,
    ProductionSnapshotSpec,
    SnapshotGameSelection,
    SnapshotGameSource,
    SnapshotLayout,
)
from game_predictor_worker.snapshots.integrity import (
    GameRow,
    LayoutRow,
    LogicalSnapshotChecksum,
    SymbolRow,
    file_sha256,
)

PRODUCTION_SNAPSHOT_SCHEMA_VERSION: Final = 3
SQLITE_APPLICATION_ID: Final = 0x47505244
DEFAULT_SNAPSHOT_BATCH_SIZE: Final = 1000
SIGNATURE_INDEX_NAME: Final = "idx_layouts_game_signature"

_RELEASE_VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")


class ProductionSnapshotError(RuntimeError):
    """Stable generation failure safe to expose to an operator."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class ProductionSnapshotGenerator:
    def __init__(
        self,
        repository: ProductionSnapshotRepository,
        *,
        batch_size: int = DEFAULT_SNAPSHOT_BATCH_SIZE,
    ) -> None:
        if batch_size <= 0:
            raise ValueError("Snapshot batch size must be positive.")
        self._repository = repository
        self._readiness = PayoutReadinessService(repository)
        self._batch_size = batch_size

    def generate(
        self,
        database_path: Path,
        spec: ProductionSnapshotSpec,
    ) -> ProductionSnapshotResult:
        normalized_release, normalized_created_at = _validate_spec(spec)
        if database_path.exists():
            raise ProductionSnapshotError(
                "SNAPSHOT_TARGET_EXISTS",
                "The target snapshot already exists and will not be overwritten.",
                details={"databasePath": str(database_path)},
            )

        sources = self._load_sources(spec.games)
        algorithm_version = sources[0][0].algorithm_version
        game_rows, symbol_rows = _catalog_rows(sources)
        layout_count = sum(source.layout_count for source, _ in sources)
        logical_checksum = LogicalSnapshotChecksum(
            release_version=normalized_release,
            created_at=normalized_created_at,
            schema_version=PRODUCTION_SNAPSHOT_SCHEMA_VERSION,
            algorithm_version=algorithm_version,
            game_count=len(game_rows),
            symbol_count=len(symbol_rows),
            layout_count=layout_count,
        )
        for game_row in game_rows:
            logical_checksum.add_game(game_row)
        for symbol_row in symbol_rows:
            logical_checksum.add_symbol(symbol_row)

        database_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = _temporary_path(database_path)
        try:
            self._write_database(
                temporary_path,
                sources=sources,
                game_rows=game_rows,
                symbol_rows=symbol_rows,
                release_version=normalized_release,
                created_at=normalized_created_at,
                algorithm_version=algorithm_version,
                layout_count=layout_count,
                logical_checksum=logical_checksum,
            )
            logical_content_sha256 = logical_checksum.hexdigest()
            _finalize_database_metadata(temporary_path, logical_content_sha256)
            snapshot_checksum = file_sha256(temporary_path)
            try:
                os.link(temporary_path, database_path)
            except FileExistsError as error:
                raise ProductionSnapshotError(
                    "SNAPSHOT_TARGET_EXISTS",
                    "The target snapshot already exists and will not be overwritten.",
                    details={"databasePath": str(database_path)},
                ) from error
            except OSError as error:
                raise ProductionSnapshotError(
                    "SNAPSHOT_PUBLISH_FAILED",
                    "The completed snapshot could not be published.",
                    details={"databasePath": str(database_path)},
                ) from error
        except ProductionSnapshotError:
            raise
        except (OSError, sqlite3.Error) as error:
            raise ProductionSnapshotError(
                "SNAPSHOT_GENERATION_FAILED",
                "The production SQLite snapshot could not be generated.",
            ) from error
        finally:
            temporary_path.unlink(missing_ok=True)

        return ProductionSnapshotResult(
            database_path=database_path,
            release_version=normalized_release,
            created_at=normalized_created_at,
            schema_version=PRODUCTION_SNAPSHOT_SCHEMA_VERSION,
            algorithm_version=algorithm_version,
            game_count=len(game_rows),
            symbol_count=len(symbol_rows),
            layout_count=layout_count,
            logical_content_sha256=logical_content_sha256,
            snapshot_file_sha256=snapshot_checksum,
            games=tuple(
                ProductionSnapshotGameResult(
                    mobile_game_id=mobile_game_id,
                    game_id=source.game_id,
                    game_code=source.game_code,
                    dataset_version_id=source.dataset_version_id,
                    dataset_version=source.dataset_version,
                    rules_version_id=source.rules_version_id,
                    rules_version=source.rules_version,
                    rows=source.rows,
                    columns=source.columns,
                    signature_cell_width=source.signature_cell_width,
                    symbol_count=len(source.symbols),
                    layout_count=source.layout_count,
                )
                for mobile_game_id, (source, _) in enumerate(sources, start=1)
            ),
        )

    def _load_sources(
        self,
        selections: Sequence[SnapshotGameSelection],
    ) -> list[tuple[SnapshotGameSource, SnapshotGameSelection]]:
        loaded: list[tuple[SnapshotGameSource, SnapshotGameSelection]] = []
        for selection in selections:
            self._readiness.require(
                selection.dataset_version_id,
                selection.rules_version_id,
                selection.algorithm_version,
            )
            source = self._repository.load_snapshot_game(selection)
            if source is None:
                raise ProductionSnapshotError(
                    "SNAPSHOT_SOURCE_NOT_FOUND",
                    "A selected snapshot game source does not exist.",
                )
            if (
                source.dataset_version_id != selection.dataset_version_id
                or source.rules_version_id != selection.rules_version_id
                or source.algorithm_version != selection.algorithm_version
            ):
                raise ProductionSnapshotError(
                    "SNAPSHOT_SOURCE_VERSION_MISMATCH",
                    "The loaded snapshot source does not match its selection.",
                )
            loaded.append((source, selection))

        loaded.sort(key=lambda item: (item[0].game_code, str(item[0].game_id)))
        game_ids = [source.game_id for source, _ in loaded]
        game_codes = [source.game_code for source, _ in loaded]
        if len(set(game_ids)) != len(game_ids) or len(set(game_codes)) != len(game_codes):
            raise ProductionSnapshotError(
                "DUPLICATE_SNAPSHOT_GAME",
                "A snapshot can contain each game exactly once.",
            )
        algorithms = {source.algorithm_version for source, _ in loaded}
        if len(algorithms) != 1:
            raise ProductionSnapshotError(
                "SNAPSHOT_ALGORITHM_MISMATCH",
                "All games in one snapshot must use the same algorithm.",
            )
        return loaded

    def _write_database(
        self,
        database_path: Path,
        *,
        sources: Sequence[tuple[SnapshotGameSource, SnapshotGameSelection]],
        game_rows: Sequence[GameRow],
        symbol_rows: Sequence[SymbolRow],
        release_version: str,
        created_at: str,
        algorithm_version: str,
        layout_count: int,
        logical_checksum: LogicalSnapshotChecksum,
    ) -> None:
        with closing(sqlite3.connect(database_path)) as connection:
            _create_schema(connection)
            with connection:
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
                        game_id, mobile_code, code, name, name_pl, name_en,
                        is_wildcard, display_order, image_asset_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    symbol_rows,
                )
                connection.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    sorted(
                        {
                            "algorithm_version": algorithm_version,
                            "content_checksum": "0" * 64,
                            "created_at": created_at,
                            "game_count": str(len(game_rows)),
                            "layout_count": str(layout_count),
                            "release_version": release_version,
                            "snapshot_schema_version": str(PRODUCTION_SNAPSHOT_SCHEMA_VERSION),
                        }.items()
                    ),
                )

            for game_id, (source, selection) in enumerate(sources, start=1):
                self._write_game_layouts(
                    connection,
                    game_id=game_id,
                    source=source,
                    selection=selection,
                    logical_checksum=logical_checksum,
                )

    def _write_game_layouts(
        self,
        connection: sqlite3.Connection,
        *,
        game_id: int,
        source: SnapshotGameSource,
        selection: SnapshotGameSelection,
        logical_checksum: LogicalSnapshotChecksum,
    ) -> None:
        after_sequence_number = 0
        while after_sequence_number < source.layout_count:
            batch = tuple(
                self._repository.list_snapshot_layout_batch(
                    selection,
                    after_sequence_number=after_sequence_number,
                    limit=self._batch_size,
                )
            )
            if not batch:
                raise ProductionSnapshotError(
                    "SNAPSHOT_SEQUENCE_INCOMPLETE",
                    "The snapshot layout stream ended before layout_count.",
                    details={
                        "gameCode": source.game_code,
                        "expectedSequenceNumber": after_sequence_number + 1,
                    },
                )
            rows = _layout_rows(
                game_id,
                source,
                batch,
                after_sequence_number=after_sequence_number,
            )
            with connection:
                connection.executemany(
                    """
                    INSERT INTO layouts(
                        game_id, sequence_number, signature, payout
                    ) VALUES (?, ?, ?, ?)
                    """,
                    rows,
                )
            for row in rows:
                logical_checksum.add_layout(row)
            after_sequence_number = batch[-1].sequence_number
        if after_sequence_number != source.layout_count:
            raise ProductionSnapshotError(
                "SNAPSHOT_SEQUENCE_INCOMPLETE",
                "The snapshot layout stream does not end at layout_count.",
                details={
                    "gameCode": source.game_code,
                    "layoutCount": source.layout_count,
                    "lastSequenceNumber": after_sequence_number,
                },
            )


def _validate_spec(spec: ProductionSnapshotSpec) -> tuple[str, str]:
    release_version = spec.release_version.strip()
    if not _RELEASE_VERSION.fullmatch(release_version):
        raise ProductionSnapshotError(
            "INVALID_SNAPSHOT_RELEASE_VERSION",
            "releaseVersion must be a safe identifier with at most 100 characters.",
        )
    if spec.created_at.tzinfo is None or spec.created_at.utcoffset() is None:
        raise ProductionSnapshotError(
            "INVALID_SNAPSHOT_CREATED_AT",
            "createdAt must include a timezone.",
        )
    if not spec.games:
        raise ProductionSnapshotError(
            "EMPTY_SNAPSHOT_SELECTION",
            "A production snapshot requires at least one selected game.",
        )
    for selection in spec.games:
        if not selection.algorithm_version.strip():
            raise ProductionSnapshotError(
                "INVALID_SNAPSHOT_ALGORITHM",
                "algorithmVersion must not be blank.",
            )
    created_at = (
        spec.created_at.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )
    return release_version, created_at


def _catalog_rows(
    sources: Sequence[tuple[SnapshotGameSource, SnapshotGameSelection]],
) -> tuple[tuple[GameRow, ...], tuple[SymbolRow, ...]]:
    games: list[GameRow] = []
    symbols: list[SymbolRow] = []
    for game_id, (source, _) in enumerate(sources, start=1):
        games.append(
            (
                game_id,
                source.game_code,
                source.game_name,
                source.rows,
                source.columns,
                source.spin_cost,
                source.signature_cell_width,
                source.layout_count,
                source.dataset_version,
                source.rules_version,
            )
        )
        symbols.extend(
            (
                game_id,
                symbol.mobile_code,
                symbol.code,
                symbol.name,
                symbol.name_pl,
                symbol.name_en,
                int(symbol.is_wildcard),
                symbol.display_order,
                symbol.image_asset_key,
            )
            for symbol in sorted(source.symbols, key=lambda item: item.mobile_code)
        )
    return tuple(games), tuple(symbols)


def _layout_rows(
    game_id: int,
    source: SnapshotGameSource,
    layouts: Sequence[SnapshotLayout],
    *,
    after_sequence_number: int,
) -> tuple[LayoutRow, ...]:
    expected = after_sequence_number + 1
    rows: list[LayoutRow] = []
    for layout in layouts:
        if layout.sequence_number != expected:
            raise ProductionSnapshotError(
                "SNAPSHOT_SEQUENCE_INCOMPLETE",
                "Snapshot layouts must be a continuous sequence.",
                details={
                    "gameCode": source.game_code,
                    "expectedSequenceNumber": expected,
                    "actualSequenceNumber": layout.sequence_number,
                },
            )
        if layout.payout < 0:
            raise ProductionSnapshotError(
                "SNAPSHOT_PAYOUT_INVALID",
                "Snapshot payouts must be non-negative.",
                details={
                    "gameCode": source.game_code,
                    "sequenceNumber": layout.sequence_number,
                },
            )
        rows.append(
            (
                game_id,
                layout.sequence_number,
                layout.signature,
                layout.payout,
            )
        )
        expected += 1
    return tuple(rows)


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA page_size = 4096")
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(f"PRAGMA application_id = {SQLITE_APPLICATION_ID}")
    connection.execute(f"PRAGMA user_version = {PRODUCTION_SNAPSHOT_SCHEMA_VERSION}")
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
                name_pl TEXT CHECK (name_pl IS NULL OR length(trim(name_pl)) > 0),
                name_en TEXT CHECK (name_en IS NULL OR length(trim(name_en)) > 0),
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

            CREATE INDEX {SIGNATURE_INDEX_NAME}
                ON layouts(game_id, signature);
            """
        )


def _finalize_database_metadata(database_path: Path, logical_checksum: str) -> None:
    with closing(sqlite3.connect(database_path)) as connection:
        with connection:
            connection.execute(
                "UPDATE metadata SET value = ? WHERE key = 'content_checksum'",
                (logical_checksum,),
            )
        connection.execute("VACUUM")


def _temporary_path(database_path: Path) -> Path:
    handle, name = tempfile.mkstemp(
        prefix=f".{database_path.name}.",
        suffix=".tmp",
        dir=database_path.parent,
    )
    os.close(handle)
    return Path(name)
