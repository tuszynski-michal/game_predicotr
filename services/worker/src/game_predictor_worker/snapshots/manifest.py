"""Strict deterministic manifest contract for production snapshot artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID

from game_predictor_worker.snapshots.contracts import ProductionSnapshotResult

SNAPSHOT_MANIFEST_VERSION = 1
SNAPSHOT_DATABASE_FILE = "snapshot.db"
SNAPSHOT_MANIFEST_FILE = "manifest.json"
MAX_MANIFEST_BYTES = 1024 * 1024

_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_RELEASE_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_MANIFEST_KEYS = {
    "algorithmVersion",
    "createdAt",
    "gameCount",
    "games",
    "layoutCount",
    "logicalContentSha256",
    "manifestVersion",
    "releaseVersion",
    "snapshotFile",
    "snapshotFileSha256",
    "snapshotSchemaVersion",
    "symbolCount",
}
_GAME_KEYS = {
    "columns",
    "datasetVersion",
    "datasetVersionId",
    "gameCode",
    "gameId",
    "layoutCount",
    "mobileGameId",
    "rows",
    "rulesVersion",
    "rulesVersionId",
    "signatureCellWidth",
    "symbolCount",
}


class SnapshotArtifactError(RuntimeError):
    """Stable snapshot artifact or manifest integrity failure."""

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


@dataclass(frozen=True, slots=True)
class SnapshotManifestGame:
    mobile_game_id: int
    game_id: UUID
    game_code: str
    dataset_version_id: UUID
    dataset_version: int
    rules_version_id: UUID
    rules_version: int
    rows: int
    columns: int
    signature_cell_width: int
    symbol_count: int
    layout_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "columns": self.columns,
            "datasetVersion": self.dataset_version,
            "datasetVersionId": str(self.dataset_version_id),
            "gameCode": self.game_code,
            "gameId": str(self.game_id),
            "layoutCount": self.layout_count,
            "mobileGameId": self.mobile_game_id,
            "rows": self.rows,
            "rulesVersion": self.rules_version,
            "rulesVersionId": str(self.rules_version_id),
            "signatureCellWidth": self.signature_cell_width,
            "symbolCount": self.symbol_count,
        }


@dataclass(frozen=True, slots=True)
class SnapshotArtifactManifest:
    manifest_version: int
    release_version: str
    created_at: str
    snapshot_schema_version: int
    algorithm_version: str
    snapshot_file: str
    snapshot_file_sha256: str
    logical_content_sha256: str
    game_count: int
    symbol_count: int
    layout_count: int
    games: tuple[SnapshotManifestGame, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "algorithmVersion": self.algorithm_version,
            "createdAt": self.created_at,
            "gameCount": self.game_count,
            "games": [game.to_dict() for game in self.games],
            "layoutCount": self.layout_count,
            "logicalContentSha256": self.logical_content_sha256,
            "manifestVersion": self.manifest_version,
            "releaseVersion": self.release_version,
            "snapshotFile": self.snapshot_file,
            "snapshotFileSha256": self.snapshot_file_sha256,
            "snapshotSchemaVersion": self.snapshot_schema_version,
            "symbolCount": self.symbol_count,
        }

    def to_bytes(self) -> bytes:
        return (
            json.dumps(
                self.to_dict(),
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")


def build_snapshot_manifest(
    result: ProductionSnapshotResult,
) -> SnapshotArtifactManifest:
    return SnapshotArtifactManifest(
        manifest_version=SNAPSHOT_MANIFEST_VERSION,
        release_version=result.release_version,
        created_at=result.created_at,
        snapshot_schema_version=result.schema_version,
        algorithm_version=result.algorithm_version,
        snapshot_file=SNAPSHOT_DATABASE_FILE,
        snapshot_file_sha256=result.snapshot_file_sha256,
        logical_content_sha256=result.logical_content_sha256,
        game_count=result.game_count,
        symbol_count=result.symbol_count,
        layout_count=result.layout_count,
        games=tuple(
            SnapshotManifestGame(
                mobile_game_id=game.mobile_game_id,
                game_id=game.game_id,
                game_code=game.game_code,
                dataset_version_id=game.dataset_version_id,
                dataset_version=game.dataset_version,
                rules_version_id=game.rules_version_id,
                rules_version=game.rules_version,
                rows=game.rows,
                columns=game.columns,
                signature_cell_width=game.signature_cell_width,
                symbol_count=game.symbol_count,
                layout_count=game.layout_count,
            )
            for game in result.games
        ),
    )


def load_snapshot_manifest(path: Path) -> SnapshotArtifactManifest:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_UNREADABLE",
            "The snapshot manifest cannot be read.",
        ) from error
    if len(raw) > MAX_MANIFEST_BYTES:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_TOO_LARGE",
            "The snapshot manifest exceeds the supported size.",
        )
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_INVALID",
            "The snapshot manifest is not valid UTF-8 JSON.",
        ) from error
    if not isinstance(value, dict) or set(value) != _MANIFEST_KEYS:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_INVALID",
            "The snapshot manifest fields do not match version 1.",
        )
    return _parse_manifest(value)


def _parse_manifest(value: dict[str, Any]) -> SnapshotArtifactManifest:
    manifest_version = _positive_int(value, "manifestVersion")
    if manifest_version != SNAPSHOT_MANIFEST_VERSION:
        raise SnapshotArtifactError(
            "SNAPSHOT_MANIFEST_VERSION_UNSUPPORTED",
            "The snapshot manifest version is not supported.",
        )
    release_version = _string(value, "releaseVersion")
    if not _RELEASE_VERSION_PATTERN.fullmatch(release_version):
        _invalid_manifest("releaseVersion is invalid.")
    created_at = _string(value, "createdAt")
    try:
        parsed_created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        _invalid_manifest("createdAt is invalid.")
    if (
        not created_at.endswith("Z")
        or parsed_created_at.tzinfo is None
        or parsed_created_at.utcoffset() is None
    ):
        _invalid_manifest("createdAt must be a UTC timestamp.")

    games_value = value.get("games")
    if not isinstance(games_value, list) or not games_value:
        _invalid_manifest("games must be a non-empty array.")
    games = tuple(_parse_game(game) for game in games_value)
    mobile_ids = tuple(game.mobile_game_id for game in games)
    if mobile_ids != tuple(range(1, len(games) + 1)):
        _invalid_manifest("mobileGameId must be continuous from 1.")
    if tuple(game.game_code for game in games) != tuple(sorted(game.game_code for game in games)):
        _invalid_manifest("games must be ordered by gameCode.")
    if len({game.game_id for game in games}) != len(games) or len(
        {game.game_code for game in games}
    ) != len(games):
        _invalid_manifest("games must be unique.")
    if len({game.dataset_version_id for game in games}) != len(games) or len(
        {game.rules_version_id for game in games}
    ) != len(games):
        _invalid_manifest("dataset and rules version ids must be unique per game.")

    game_count = _positive_int(value, "gameCount")
    symbol_count = _positive_int(value, "symbolCount")
    layout_count = _positive_int(value, "layoutCount")
    if (
        game_count != len(games)
        or symbol_count != sum(game.symbol_count for game in games)
        or layout_count != sum(game.layout_count for game in games)
    ):
        _invalid_manifest("manifest counts do not match games.")

    snapshot_file_sha256 = _sha256(value, "snapshotFileSha256")
    logical_content_sha256 = _sha256(value, "logicalContentSha256")
    snapshot_file = _string(value, "snapshotFile")
    if snapshot_file != SNAPSHOT_DATABASE_FILE:
        _invalid_manifest("snapshotFile is invalid.")

    return SnapshotArtifactManifest(
        manifest_version=manifest_version,
        release_version=release_version,
        created_at=created_at,
        snapshot_schema_version=_positive_int(value, "snapshotSchemaVersion"),
        algorithm_version=_string(value, "algorithmVersion"),
        snapshot_file=snapshot_file,
        snapshot_file_sha256=snapshot_file_sha256,
        logical_content_sha256=logical_content_sha256,
        game_count=game_count,
        symbol_count=symbol_count,
        layout_count=layout_count,
        games=games,
    )


def _parse_game(value: object) -> SnapshotManifestGame:
    if not isinstance(value, dict) or set(value) != _GAME_KEYS:
        _invalid_manifest("A game manifest has invalid fields.")
    game = value
    try:
        game_id = UUID(_string(game, "gameId"))
        dataset_version_id = UUID(_string(game, "datasetVersionId"))
        rules_version_id = UUID(_string(game, "rulesVersionId"))
    except ValueError:
        _invalid_manifest("A game manifest UUID is invalid.")
    signature_cell_width = _positive_int(game, "signatureCellWidth")
    if signature_cell_width > 5:
        _invalid_manifest("signatureCellWidth is outside 1..5.")
    return SnapshotManifestGame(
        mobile_game_id=_positive_int(game, "mobileGameId"),
        game_id=game_id,
        game_code=_string(game, "gameCode"),
        dataset_version_id=dataset_version_id,
        dataset_version=_positive_int(game, "datasetVersion"),
        rules_version_id=rules_version_id,
        rules_version=_positive_int(game, "rulesVersion"),
        rows=_positive_int(game, "rows"),
        columns=_positive_int(game, "columns"),
        signature_cell_width=signature_cell_width,
        symbol_count=_positive_int(game, "symbolCount"),
        layout_count=_positive_int(game, "layoutCount"),
    )


def _string(value: dict[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        _invalid_manifest(f"{key} must be a non-empty string.")
    return item


def _positive_int(value: dict[str, Any], key: str) -> int:
    item = value.get(key)
    if type(item) is not int or item < 1:
        _invalid_manifest(f"{key} must be a positive integer.")
    return item


def _sha256(value: dict[str, Any], key: str) -> str:
    item = _string(value, key)
    if not _SHA256_PATTERN.fullmatch(item):
        _invalid_manifest(f"{key} must be a lowercase SHA-256.")
    return item


def _invalid_manifest(message: str) -> NoReturn:
    raise SnapshotArtifactError("SNAPSHOT_MANIFEST_INVALID", message)
