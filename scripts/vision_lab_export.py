"""Read-only, manifest-scoped export of vision evidence from the local database.

The command never creates a database row. All output is staged beside the final
snapshot directory and becomes visible only after every row and file is checked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import time
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID, uuid4

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageBoardSearchFastDocumentModel,
    ImagePageGeometryOverrideModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    ImageSymbolReviewEventModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    RulesVersionSymbolModel,
    SourceImageModel,
    SymbolModel,
)
from sqlalchemy import Connection, Engine, Table, create_engine, select, text, tuple_
from sqlalchemy.orm import Session

EXPORTER_VERSION = "vision-lab-export-v1"
_V11_POLICY_VERSION = "structured-lattice-v4-selective-frame-v1"
_BATCH_SIZE = 100
_STATEMENT_TIMEOUT_MS = 10_000
_TRANSACTION_TIMEOUT_MS = 30_000
_TABLES: dict[str, Table] = {
    table.name: table
    for table in (
        cast(Table, model.__table__)
        for model in (
            GameModel,
            JobModel,
            RulesVersionModel,
            SymbolModel,
            RulesVersionSymbolModel,
            SourceImageModel,
            ImageSourceGeometryRevisionModel,
            ImagePageGeometryOverrideModel,
            RecognizedBoardModel,
            ImageReviewItemModel,
            ImageBoardGeometryRevisionModel,
            ImageBoardGeometryReviewEventModel,
            ImageBoardSearchFastDocumentModel,
            ImageSymbolReviewCellModel,
            ImageSymbolReviewEventModel,
        )
    )
}


class ExportIntegrityError(RuntimeError):
    """The requested snapshot cannot be published without losing evidence."""


def _plain(value: Any) -> Any:
    if isinstance(value, UUID | datetime | date):
        return value.isoformat() if not isinstance(value, UUID) else str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value


def _json(value: Any) -> bytes:
    return json.dumps(
        _plain(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _check_sha(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{field} must be a lowercase SHA-256 digest")
    return value


def _safe_relative_parts(value: object) -> tuple[str, ...]:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ExportIntegrityError("Snapshot contains an invalid relative path")
    path = PurePosixPath(value)
    parts = path.parts
    if (
        path.is_absolute()
        or path.as_posix() != value
        or not parts
        or ".." in parts
        or any(":" in part for part in parts)
    ):
        raise ExportIntegrityError("Snapshot relative path escapes its root")
    return parts


def _uuid(value: object, field: str) -> UUID:
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be a UUID") from error


def validate_input(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "datasetName", "entries"}:
        raise ValueError("Manifest requires schemaVersion, datasetName and entries")
    if value["schemaVersion"] != 1:
        raise ValueError("Unsupported manifest schemaVersion")
    name = value["datasetName"]
    if not isinstance(name, str) or not name.strip() or len(name) > 200:
        raise ValueError("datasetName must be a nonempty name of at most 200 characters")
    entries = value["entries"]
    if not isinstance(entries, list) or not entries or len(entries) > 1_000:
        raise ValueError("entries must contain 1 to 1000 sources")
    normalized: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict) or set(raw) != {
            "gameId",
            "sourceImageId",
            "expectedSourceSha256",
            "sourceFamilyId",
            "role",
        }:
            raise ValueError(f"entries[{index}] has invalid fields")
        game_id = str(_uuid(raw["gameId"], "gameId"))
        source_id = str(_uuid(raw["sourceImageId"], "sourceImageId"))
        if source_id in seen:
            raise ValueError("Duplicate sourceImageId")
        seen.add(source_id)
        family = raw["sourceFamilyId"]
        if not isinstance(family, str) or not family.strip() or len(family) > 200:
            raise ValueError("sourceFamilyId must be a nonempty value of at most 200 characters")
        role = raw["role"]
        if role not in ("data", "comparison_only", "777_v2_declared"):
            raise ValueError("role must be data, comparison_only or 777_v2_declared")
        normalized.append(
            {
                "gameId": game_id,
                "sourceImageId": source_id,
                "expectedSourceSha256": _check_sha(
                    raw["expectedSourceSha256"], "expectedSourceSha256"
                ),
                "sourceFamilyId": family,
                "role": role,
            }
        )
    normalized.sort(key=lambda entry: (entry["gameId"], entry["sourceImageId"]))
    return {"schemaVersion": 1, "datasetName": name.strip(), "entries": normalized}


@dataclass(frozen=True)
class FrozenRow:
    game_id: UUID
    table: str
    key: tuple[str, ...]
    fingerprint: str
    storage_generation: int = 1


def _key(table: Table, row: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(str(row[column.name]) for column in table.primary_key.columns)


def _where_keys(table: Table, keys: Sequence[tuple[str, ...]]) -> Any:
    columns = list(table.primary_key.columns)
    typed = [
        tuple(
            UUID(value) if column.type.python_type is UUID else value
            for column, value in zip(columns, key, strict=True)
        )
        for key in keys
    ]
    if len(columns) == 1:
        return columns[0].in_([key[0] for key in typed])
    return tuple_(*columns).in_(typed)


@contextmanager
def _read_transaction(
    engine: Engine, game_id: UUID, expected_generation: int | None = None
) -> Iterator[Connection]:
    with engine.connect() as connection:
        _configure_read_only(connection)
        with Session(bind=connection) as session:
            _bind_game(session, connection, game_id, expected_generation)
            yield connection
        connection.rollback()


def _configure_read_only(connection: Connection) -> None:
    connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    connection.execute(
        text("SELECT set_config('statement_timeout', :timeout, true)"),
        {"timeout": str(_STATEMENT_TIMEOUT_MS)},
    )
    connection.execute(
        text("SELECT set_config('idle_in_transaction_session_timeout', :timeout, true)"),
        {"timeout": str(_TRANSACTION_TIMEOUT_MS)},
    )
    connection.info["vision_export_deadline"] = time.monotonic() + _TRANSACTION_TIMEOUT_MS / 1000


def _bind_game(
    session: Session, connection: Connection, game_id: UUID, expected_generation: int | None
) -> None:
    location = GameStorageRouter().bind(
        session,
        game_id,
        intent=GameStorageIntent.READ,
        expected_generation=expected_generation,
    )
    if location.status.value != "active":
        raise ExportIntegrityError(f"Game {game_id} storage is not active")
    connection.info["vision_export_generation"] = location.generation


def _rows(connection: Connection, table_name: str, condition: Any) -> list[dict[str, Any]]:
    if time.monotonic() > connection.info["vision_export_deadline"]:
        raise ExportIntegrityError("Read-only transaction exceeded its time limit")
    table = _TABLES[table_name]
    rows = [dict(row) for row in connection.execute(select(table).where(condition)).mappings()]
    if time.monotonic() > connection.info["vision_export_deadline"]:
        raise ExportIntegrityError("Read-only transaction exceeded its time limit")
    return rows


def _identities(rows: Sequence[Mapping[str, Any]], field: str = "id") -> list[Any]:
    return [row[field] for row in rows]


def _freeze_game(
    connection: Connection, game_id: UUID, entries: Sequence[dict[str, str]]
) -> dict[str, list[dict[str, Any]]]:
    source_ids = [UUID(entry["sourceImageId"]) for entry in entries]
    selected: dict[str, list[dict[str, Any]]] = {}

    def take(name: str, condition: Any) -> list[dict[str, Any]]:
        selected[name] = _rows(connection, name, condition)
        return selected[name]

    game = take("games", _TABLES["games"].c.id == game_id)
    if len(game) != 1:
        raise ExportIntegrityError(f"Game {game_id} is unavailable")
    sources = take("source_images", _TABLES["source_images"].c.id.in_(source_ids))
    if len(sources) != len(source_ids):
        raise ExportIntegrityError(f"A source for game {game_id} is unavailable")
    jobs = take("jobs", _TABLES["jobs"].c.id.in_(_identities(sources, "import_job_id")))
    if len(jobs) != len(set(_identities(sources, "import_job_id"))):
        raise ExportIntegrityError("A source import job is unavailable")
    job_game = {row["id"]: row["game_id"] for row in jobs}
    expected = {UUID(entry["sourceImageId"]): entry for entry in entries}
    for source in sources:
        entry = expected[source["id"]]
        if job_game[source["import_job_id"]] != game_id:
            raise ExportIntegrityError("Source belongs to a different game")
        if source["checksum_sha256"] != entry["expectedSourceSha256"]:
            raise ExportIntegrityError("Source checksum differs from input manifest")
    take(
        "image_source_geometry_revisions",
        _TABLES["image_source_geometry_revisions"].c.source_image_id.in_(source_ids),
    )
    take(
        "image_page_geometry_overrides",
        (_TABLES["image_page_geometry_overrides"].c.game_id == game_id)
        & _TABLES["image_page_geometry_overrides"].c.source_checksum_sha256.in_(
            [entry["expectedSourceSha256"] for entry in entries]
        ),
    )
    boards = take(
        "recognized_boards", _TABLES["recognized_boards"].c.source_image_id.in_(source_ids)
    )
    board_ids = _identities(boards)
    review_items = take(
        "image_review_items", _TABLES["image_review_items"].c.recognized_board_id.in_(board_ids)
    )
    review_ids = _identities(review_items)
    take(
        "image_board_geometry_revisions",
        _TABLES["image_board_geometry_revisions"].c.recognized_board_id.in_(board_ids),
    )
    take(
        "image_board_geometry_review_events",
        _TABLES["image_board_geometry_review_events"].c.recognized_board_id.in_(board_ids),
    )
    cells = take(
        "image_symbol_review_cells",
        _TABLES["image_symbol_review_cells"].c.review_item_id.in_(review_ids),
    )
    take(
        "image_board_search_fast_documents",
        (_TABLES["image_board_search_fast_documents"].c.game_id == game_id)
        & _TABLES["image_board_search_fast_documents"].c.sequence_number.in_(
            _identities(cells, "sequence_number")
        ),
    )
    take(
        "image_symbol_review_events",
        _TABLES["image_symbol_review_events"].c.cell_review_id.in_(_identities(cells)),
    )
    symbols = take("symbols", _TABLES["symbols"].c.game_id == game_id)
    rules = take("rules_versions", _TABLES["rules_versions"].c.game_id == game_id)
    take(
        "rules_version_symbols",
        _TABLES["rules_version_symbols"].c.rules_version_id.in_(_identities(rules)),
    )
    symbol_ids = set(_identities(symbols))
    if any(row["symbol_id"] not in symbol_ids for row in selected["rules_version_symbols"]):
        raise ExportIntegrityError("Rules version references a symbol outside the game")
    return selected


def freeze_export_identity(
    engine: Engine, manifest: Mapping[str, Any]
) -> tuple[str, list[FrozenRow]]:
    frozen: list[FrozenRow] = []
    by_game: dict[UUID, list[dict[str, str]]] = defaultdict(list)
    for entry in manifest["entries"]:
        by_game[UUID(entry["gameId"])].append(entry)
    with engine.connect() as connection:
        _configure_read_only(connection)
        with Session(bind=connection) as session:
            router = GameStorageRouter()
            for game_id in sorted(by_game, key=str):
                router.clear_session_binding(session)
                _bind_game(session, connection, game_id, None)
                generation = int(connection.info["vision_export_generation"])
                for table_name, rows in _freeze_game(connection, game_id, by_game[game_id]).items():
                    table = _TABLES[table_name]
                    for row in rows:
                        frozen.append(
                            FrozenRow(
                                game_id, table_name, _key(table, row), _sha(_json(row)), generation
                            )
                        )
        connection.rollback()
    frozen.sort(key=lambda row: (str(row.game_id), row.table, row.key))
    identity = {
        "input": manifest,
        "exporterVersion": EXPORTER_VERSION,
        "rows": [
            [str(row.game_id), row.table, list(row.key), row.fingerprint, row.storage_generation]
            for row in frozen
        ],
    }
    return _sha(_json(identity)), frozen


def _export_rows(engine: Engine, frozen: Sequence[FrozenRow], stage: Path) -> dict[str, str]:
    grouped: dict[tuple[UUID, str], list[FrozenRow]] = defaultdict(list)
    for row in frozen:
        grouped[row.game_id, row.table].append(row)
    checksums: dict[str, str] = {}
    for (game_id, table_name), references in sorted(
        grouped.items(), key=lambda item: (str(item[0][0]), item[0][1])
    ):
        table = _TABLES[table_name]
        file_path = stage / "records" / str(game_id) / f"{table_name}.jsonl"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with file_path.open("wb") as output:
            for offset in range(0, len(references), _BATCH_SIZE):
                batch = references[offset : offset + _BATCH_SIZE]
                with _read_transaction(engine, game_id, batch[0].storage_generation) as connection:
                    found = _rows(
                        connection, table_name, _where_keys(table, [row.key for row in batch])
                    )
                by_key = {_key(table, row): row for row in found}
                if len(by_key) != len(batch):
                    raise ExportIntegrityError(f"Missing {table_name} row after freeze")
                for reference in batch:
                    value = by_key[reference.key]
                    encoded = _json(value)
                    if _sha(encoded) != reference.fingerprint:
                        raise ExportIntegrityError(f"{table_name} row drifted after freeze")
                    line = encoded + b"\n"
                    output.write(line)
                    digest.update(line)
            output.flush()
            os.fsync(output.fileno())
        checksums[file_path.relative_to(stage).as_posix()] = digest.hexdigest()
    return checksums


def _managed_source(root: Path, checksum: str) -> Path:
    relative = PurePosixPath("data", "originals", checksum[:2], f"{checksum}.jpg")
    path = (root / Path(*relative.parts)).resolve(strict=True)
    if not path.is_relative_to(root.resolve(strict=True)) or not path.is_file():
        raise ExportIntegrityError("Managed source path escapes artifact root")
    return path


def _copy_sources(manifest: Mapping[str, Any], artifact_root: Path, stage: Path) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for checksum in sorted({entry["expectedSourceSha256"] for entry in manifest["entries"]}):
        source = _managed_source(artifact_root, checksum)
        target = stage / "images" / checksum[:2] / f"{checksum}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open("rb") as original, target.open("wb") as copy:
            while block := original.read(1024 * 1024):
                copy.write(block)
                digest.update(block)
            copy.flush()
            os.fsync(copy.fileno())
        if digest.hexdigest() != checksum:
            raise ExportIntegrityError(f"Managed source {checksum} changed or is corrupt")
        checksums[target.relative_to(stage).as_posix()] = checksum
    return checksums


def _copy_referenced_artifacts(
    manifest: Mapping[str, Any], artifact_root: Path, stage: Path
) -> dict[str, str]:
    """Preserve immutable legacy boards and exact cell crops referenced by revisions."""
    referenced: dict[str, str] = {}

    def register(relative: object, checksum: object) -> None:
        if relative is None and checksum is None:
            return
        if not isinstance(relative, str):
            raise ExportIntegrityError("Managed artifact has an invalid path")
        _safe_relative_parts(relative)
        expected = _check_sha(checksum, "artifact checksum")
        previous = referenced.setdefault(relative, expected)
        if previous != expected:
            raise ExportIntegrityError("One managed artifact path has conflicting checksums")

    for game_id in sorted({entry["gameId"] for entry in manifest["entries"]}):
        for board in _read_record_file(stage, game_id, "recognized_boards"):
            register(board["board_relative_path"], board["board_checksum_sha256"])
        for revision in _read_record_file(stage, game_id, "image_board_geometry_revisions"):
            register(revision["board_relative_path"], revision["board_checksum_sha256"])
            for crop in revision["crop_artifacts"] or []:
                register(crop["cropRelativePath"], crop["cropChecksumSha256"])
        for cell in _read_record_file(stage, game_id, "image_symbol_review_cells"):
            register(
                cell["crop_relative_path"],
                cell["crop_checksum_sha256"] if cell["crop_relative_path"] is not None else None,
            )

    checksums: dict[str, str] = {}
    root = artifact_root.resolve(strict=True)
    for relative, checksum in sorted(referenced.items()):
        parts = _safe_relative_parts(relative)
        source = (root / Path(*parts)).resolve(strict=True)
        if not source.is_relative_to(root) or not source.is_file():
            raise ExportIntegrityError("Managed artifact path escapes artifact root")
        target = stage / "assets" / Path(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        with source.open("rb") as original, target.open("wb") as copy:
            while block := original.read(1024 * 1024):
                copy.write(block)
                digest.update(block)
            copy.flush()
            os.fsync(copy.fileno())
        if digest.hexdigest() != checksum:
            raise ExportIntegrityError(f"Managed artifact {relative} changed or is corrupt")
        checksums[target.relative_to(stage).as_posix()] = checksum
    return checksums


def _read_record_file(stage: Path, game_id: str, table_name: str) -> list[dict[str, Any]]:
    path = stage / "records" / game_id / f"{table_name}.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _write_projection(stage: Path, relative: str, value: Any) -> str:
    target = stage / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = _json(value) + b"\n"
    with target.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    return _sha(encoded)


def _eligible_legacy_label(
    cell: Mapping[str, Any],
    board: Mapping[str, Any],
    symbol: Mapping[str, Any] | None,
    owner: Mapping[str, Any] | None,
    game_id: str,
) -> bool:
    """Conservative projection of the production training gate for copied crops."""
    return (
        cell["game_id"] == game_id
        and cell["source_available"] is True
        and cell["geometry_revision"] == board["geometry_revision"]
        and cell["review_state"] == "approved"
        and cell["quality_issue"] is None
        and cell["approved_crop_sample_id"] == cell["crop_sample_id"]
        and cell["approved_crop_checksum_sha256"] == cell["crop_checksum_sha256"]
        and cell["approved_geometry_revision"] == cell["geometry_revision"]
        and cell["asset_mode"] == "legacy_file"
        and cell["approved_asset_mode"] in (None, "legacy_file")
        and cell["crop_relative_path"] is not None
        and symbol is not None
        and symbol["game_id"] == game_id
        and symbol["status"] == "active"
        and owner is not None
        and owner["review_item_id"] == cell["review_item_id"]
        and owner["recognized_board_id"] == board["id"]
    )


def _build_projections(stage: Path, manifest: Mapping[str, Any]) -> dict[str, str]:
    """Expose conservative label and historical-comparison views over raw evidence."""
    approved: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    game_ids = sorted({entry["gameId"] for entry in manifest["entries"]})
    for game_id in game_ids:
        boards = _read_record_file(stage, game_id, "recognized_boards")
        board_by_id = {row["id"]: row for row in boards}
        jobs = {row["id"]: row for row in _read_record_file(stage, game_id, "jobs")}
        sources = {row["id"]: row for row in _read_record_file(stage, game_id, "source_images")}
        symbols = {row["id"]: row for row in _read_record_file(stage, game_id, "symbols")}
        owners = {
            row["sequence_number"]: row
            for row in _read_record_file(stage, game_id, "image_board_search_fast_documents")
        }
        source_revisions = _read_record_file(stage, game_id, "image_source_geometry_revisions")
        source_revisions_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in source_revisions:
            source_revisions_by_source[row["source_image_id"]].append(row)
        revisions = _read_record_file(stage, game_id, "image_board_geometry_revisions")
        by_board: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in revisions:
            by_board[row["recognized_board_id"]].append(row)
        for cell in _read_record_file(stage, game_id, "image_symbol_review_cells"):
            board = board_by_id.get(cell["recognized_board_id"])
            if board is None:
                raise ExportIntegrityError("Approved cell references an absent board")
            symbol = symbols.get(cell["assigned_symbol_id"])
            owner = owners.get(cell["sequence_number"])
            if _eligible_legacy_label(cell, board, symbol, owner, game_id):
                approved.append(
                    {
                        "gameId": game_id,
                        "sourceImageId": board["source_image_id"],
                        "boardId": board["id"],
                        "cellIndex": cell["cell_index"],
                        "geometryRevision": cell["geometry_revision"],
                        "cropSampleId": cell["crop_sample_id"],
                        "cropSha256": cell["crop_checksum_sha256"],
                        "symbolId": cell["assigned_symbol_id"],
                        "reviewRevision": cell["revision"],
                        "reviewedAt": cell["last_reviewed_at"],
                    }
                )
        for entry in manifest["entries"]:
            if entry["gameId"] != game_id or entry["role"] != "comparison_only":
                continue
            source = sources[entry["sourceImageId"]]
            job = jobs[source["import_job_id"]]
            policy = job["input_payload"].get("lateral_partial_geometry")
            variant = policy.get("variant") if isinstance(policy, dict) else None
            for board in boards:
                if board["source_image_id"] != entry["sourceImageId"]:
                    continue
                history = sorted(by_board[board["id"]], key=lambda row: row["revision"])
                initial_candidates = []
                for row in source_revisions_by_source[entry["sourceImageId"]]:
                    slot = board["position_index"]
                    slots = row["active_board_slots"]
                    if (
                        row["game_id"] != game_id
                        or row["engine_kind"] != "structured_opencv_v1"
                        or row["engine_version"] != _V11_POLICY_VERSION
                        or row["geometry_source"] != "auto"
                        or row["source_checksum_sha256"] != entry["expectedSourceSha256"]
                        or slot not in slots
                        or len(slots) != len(row["board_geometries"])
                    ):
                        continue
                    geometry = row["board_geometries"][slots.index(slot)]
                    if (
                        isinstance(geometry, dict)
                        and isinstance(row["revision"], int)
                        and row["revision"] >= 0
                        and isinstance(row["sequence_range_start"], int)
                        and geometry.get("positionIndex") == slot
                        and geometry.get("sequenceNumber") == board["sequence_number"]
                        and board["sequence_number"] == row["sequence_range_start"] + slot
                    ):
                        initial_candidates.append(row)
                revisions_by_number = {row["revision"]: row for row in initial_candidates}
                initial = (
                    min(initial_candidates, key=lambda row: row["revision"])
                    if len(revisions_by_number) == len(initial_candidates) and initial_candidates
                    else None
                )
                geometry_index = (
                    None
                    if initial is None
                    else initial["active_board_slots"].index(board["position_index"])
                )
                comparisons.append(
                    {
                        "gameId": game_id,
                        "sourceImageId": entry["sourceImageId"],
                        "boardId": board["id"],
                        "v11EngineVariant": "selective_board_review_v1_1",
                        "comparisonAvailable": (
                            variant == "selective_board_review_v1_1" and initial is not None
                        ),
                        "initialV11Revision": (
                            None
                            if variant != "selective_board_review_v1_1" or initial is None
                            else {
                                "sourceGeometryRevisionId": initial["id"],
                                "revision": initial["revision"],
                                "boardPositionIndex": board["position_index"],
                                "boardGeometrySha256": _sha(
                                    _json(initial["board_geometries"][geometry_index])
                                ),
                            }
                        ),
                        "laterGeometryRevisions": [
                            {"id": row["id"], "revision": row["revision"]} for row in history
                        ],
                    }
                )
    approved.sort(
        key=lambda row: (row["gameId"], row["sourceImageId"], row["boardId"], row["cellIndex"])
    )
    comparisons.sort(key=lambda row: (row["gameId"], row["sourceImageId"], row["boardId"]))
    return {
        "approved_labels.json": _write_projection(stage, "approved_labels.json", approved),
        "historical_comparisons.json": _write_projection(
            stage, "historical_comparisons.json", comparisons
        ),
    }


def _verify_published(path: Path, expected: Mapping[str, Any]) -> None:
    _reject_reparse(path)
    if not path.is_dir():
        raise ExportIntegrityError("Existing snapshot is not a directory")
    manifest_path = _snapshot_file(path, "manifest.json")
    try:
        published = json.loads(manifest_path.read_bytes())
    except (OSError, ValueError) as error:
        raise ExportIntegrityError("Existing snapshot manifest is unavailable") from error
    if published != expected:
        raise ExportIntegrityError("Existing snapshot conflicts with frozen identity")
    files = published.get("files")
    if not isinstance(files, dict):
        raise ExportIntegrityError("Existing snapshot has no file inventory")
    expected_files = {"manifest.json"}
    for relative, checksum in files.items():
        if not isinstance(relative, str) or not isinstance(checksum, str):
            raise ExportIntegrityError("Existing snapshot inventory is invalid")
        file_path = _snapshot_file(path, relative)
        expected_files.add(relative)
        if _sha(file_path.read_bytes()) != checksum:
            raise ExportIntegrityError(f"Existing snapshot file {relative} differs")
    for directory, subdirectories, filenames in os.walk(path, followlinks=False):
        for name in (*subdirectories, *filenames):
            member = Path(directory) / name
            _reject_reparse(member)
            if member.is_file() and member.relative_to(path).as_posix() not in expected_files:
                raise ExportIntegrityError("Existing snapshot contains an unlisted file")


def _reject_reparse(path: Path) -> None:
    try:
        info = path.lstat()
    except OSError as error:
        raise ExportIntegrityError(f"Snapshot path {path} is unavailable") from error
    if stat.S_ISLNK(info.st_mode) or (
        getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        raise ExportIntegrityError(f"Snapshot path {path} is a link or reparse point")


def _snapshot_file(root: Path, relative: str) -> Path:
    parts = _safe_relative_parts(relative)
    resolved_root = root.resolve(strict=True)
    candidate = root
    for part in parts:
        candidate = candidate / part
        _reject_reparse(candidate)
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(resolved_root) or not candidate.is_file():
        raise ExportIntegrityError("Snapshot file escapes its root or is not a file")
    return candidate


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":
        return
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_snapshot(stage: Path, destination: Path, payload: Mapping[str, Any]) -> Path:
    manifest_path = stage / "manifest.json"
    with manifest_path.open("wb") as output:
        output.write(_json(payload) + b"\n")
        output.flush()
        os.fsync(output.fileno())
    for directory in sorted((item for item in stage.rglob("*") if item.is_dir()), reverse=True):
        _fsync_directory(directory)
    _fsync_directory(stage)
    _verify_published(stage, payload)
    if os.path.lexists(destination):
        _verify_published(destination, payload)
        return destination
    try:
        stage.rename(destination)
    except FileExistsError:
        _verify_published(destination, payload)
        return destination
    _fsync_directory(destination.parent)
    _verify_published(destination, payload)
    return destination


def export_snapshot(
    engine: Engine, manifest_value: object, artifact_root: Path, output_root: Path
) -> Path:
    manifest = validate_input(manifest_value)
    snapshot_id, frozen = freeze_export_identity(engine, manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / snapshot_id
    stage = output_root / f".stage-{uuid4().hex}"
    stage.mkdir(exist_ok=False)
    try:
        files = _export_rows(engine, frozen, stage)
        files.update(_copy_sources(manifest, artifact_root, stage))
        files.update(_copy_referenced_artifacts(manifest, artifact_root, stage))
        files.update(_build_projections(stage, manifest))
        files["frozen_identity.json"] = _write_projection(
            stage,
            "frozen_identity.json",
            {
                "snapshotId": snapshot_id,
                "exporterVersion": EXPORTER_VERSION,
                "rows": [
                    {
                        "gameId": str(row.game_id),
                        "table": row.table,
                        "key": list(row.key),
                        "fingerprint": row.fingerprint,
                        "storageGeneration": row.storage_generation,
                    }
                    for row in frozen
                ],
            },
        )
        payload = {
            "schemaVersion": 1,
            "snapshotId": snapshot_id,
            "exporterVersion": EXPORTER_VERSION,
            "input": manifest,
            "frozenRows": len(frozen),
            "files": dict(sorted(files.items())),
        }
        return publish_snapshot(stage, destination, payload)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, required=True)
    arguments = parser.parse_args()
    settings = ApiSettings.from_environment()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 5})
    try:
        result = export_snapshot(
            engine,
            json.loads(arguments.manifest.read_text(encoding="utf-8")),
            arguments.artifact_root or settings.artifact_root,
            arguments.output_root,
        )
    finally:
        engine.dispose()
    print(result)


if __name__ == "__main__":
    main()
