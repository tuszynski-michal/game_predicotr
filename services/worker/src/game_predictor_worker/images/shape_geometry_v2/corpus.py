"""Checksum-bound, non-production corpus and v1.1 baseline contracts.

The module deliberately has no database, HTTP, job, import, or artifact-store
dependency.  It is used only by offline quality tools before a future geometry
variant is allowed to enter the production preflight path.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any, NoReturn, cast

SHAPE_GEOMETRY_V2_CORPUS_SCHEMA_VERSION = 1
SHAPE_GEOMETRY_V2_ANNOTATION_SCHEMA_VERSION = 1
SHAPE_GEOMETRY_V2_INVENTORY_VERSION = "shape-geometry-v2-inventory-v1"
SHAPE_GEOMETRY_V2_ANCHOR_SELECTION_VERSION = "shape-geometry-v2-anchor-selection-v1"
SHAPE_GEOMETRY_V2_V11_BASELINE_VERSION = "shape-geometry-v2-v11-baseline-v1"
V11_ENGINE_VARIANT = "selective_board_review_v1_1"
SUPPORTED_GAME_IDS = frozenset({"777", "blazing", "gang", "reels", "mummies"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}")
_SOURCE_ID = re.compile(r"[a-z0-9][a-z0-9_./-]{0,191}")
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_EXCLUDED_V7_DATASET_IDS = frozenset({"reels_test", "rells_big"})


class ShapeGeometryCorpusError(ValueError):
    """A stable, fail-closed corpus or baseline error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CorpusVisibility(StrEnum):
    EXECUTOR = "executor"
    ACCEPTANCE = "acceptance"


class CorpusSplit(StrEnum):
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    ACCEPTANCE = "acceptance"


class CorpusRole(StrEnum):
    MEASUREMENT = "measurement"
    ANCHOR_POOL = "anchor_pool"


class ManualPageState(StrEnum):
    COMPLETE = "complete"
    SIDE_PARTIAL = "side_partial"
    VERTICAL_CROP = "vertical_crop"
    OCCLUDED = "occluded"
    NOT_A_PAGE = "not_a_page"


def _fail(code: str, message: str) -> NoReturn:
    raise ShapeGeometryCorpusError(code, message)


def canonical_json_bytes(payload: object) -> bytes:
    """Return stable bytes for fingerprints and report equality checks."""

    return json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(payload: object) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _require_mapping(raw: object, name: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping):
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} must be an object.")
    return cast(Mapping[str, object], raw)


def _require_sequence(raw: object, name: str) -> Sequence[object]:
    if not isinstance(raw, Sequence) or isinstance(raw, str | bytes):
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} must be an array.")
    return cast(Sequence[object], raw)


def _require_exact_keys(raw: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(raw) != expected:
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} fields are incomplete or unknown.")


def _require_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} is invalid.")
    return value


def _require_sha256(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} must be a lowercase SHA-256.")
    return value


def _safe_relative_path(value: object, name: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} must be a non-empty relative path.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.suffix.casefold() not in {".jpg", ".jpeg"}
    ):
        _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", f"{name} is not a safe JPEG path.")
    return path


def _is_link_or_reparse(path: Path) -> bool:
    try:
        return path.is_symlink() or bool(
            getattr(path.stat(), "st_file_attributes", 0) & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        )
    except OSError as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE",
            "Corpus path cannot be inspected.",
        ) from error


def _resolved_directory(path: Path) -> Path:
    absolute = path.absolute()
    ancestors = tuple(reversed((absolute, *absolute.parents)))
    if any(_is_link_or_reparse(item) for item in ancestors if item.exists()):
        _fail(
            "SHAPE_GEOMETRY_V2_CORPUS_PATH_UNSAFE",
            "Corpus root or one of its ancestors is a link or junction.",
        )
    try:
        resolved = absolute.resolve(strict=True)
    except OSError as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE",
            "Corpus root is unavailable.",
        ) from error
    if not resolved.is_dir():
        _fail("SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE", "Corpus root is not a directory.")
    return resolved


@dataclass(frozen=True, slots=True)
class ShapeGeometryTopology:
    """Explicit page and cell topology; neither dimension is inferred."""

    page_board_rows: int
    page_board_columns: int
    cell_rows: int
    cell_columns: int
    active_board_slots: tuple[int, ...]

    def __post_init__(self) -> None:
        if (
            self.page_board_rows != 3
            or self.page_board_columns != 3
            or self.cell_rows != 3
            or self.cell_columns != 5
            or self.active_board_slots != tuple(range(9))
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_TOPOLOGY_UNSUPPORTED",
                "Shape geometry v2 corpus requires a full 3x3 page of 3x5 boards.",
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryTopology:
        expected = {
            "pageBoardRows",
            "pageBoardColumns",
            "cellRows",
            "cellColumns",
            "activeBoardSlots",
        }
        _require_exact_keys(raw, expected, "game topology")
        slots = _require_sequence(raw["activeBoardSlots"], "activeBoardSlots")
        if any(type(value) is not int for value in slots):
            _fail("SHAPE_GEOMETRY_V2_TOPOLOGY_UNSUPPORTED", "Active board slots must be integers.")
        return cls(
            page_board_rows=cast(int, raw["pageBoardRows"]),
            page_board_columns=cast(int, raw["pageBoardColumns"]),
            cell_rows=cast(int, raw["cellRows"]),
            cell_columns=cast(int, raw["cellColumns"]),
            active_board_slots=tuple(cast(int, value) for value in slots),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "activeBoardSlots": list(self.active_board_slots),
            "cellColumns": self.cell_columns,
            "cellRows": self.cell_rows,
            "pageBoardColumns": self.page_board_columns,
            "pageBoardRows": self.page_board_rows,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryGame:
    game_id: str
    topology: ShapeGeometryTopology
    v11_profile: Mapping[str, object] | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryGame:
        _require_exact_keys(
            raw,
            {
                "gameId",
                "pageBoardRows",
                "pageBoardColumns",
                "cellRows",
                "cellColumns",
                "activeBoardSlots",
                "v11Profile",
            },
            "game",
        )
        game_id = _require_identifier(raw["gameId"], "gameId")
        if game_id not in SUPPORTED_GAME_IDS:
            _fail(
                "SHAPE_GEOMETRY_V2_GAME_UNSUPPORTED",
                "Corpus game is outside the approved scope.",
            )
        profile = raw["v11Profile"]
        if profile is not None and not isinstance(profile, Mapping):
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "v11Profile must be an object or null.")
        return cls(
            game_id=game_id,
            topology=ShapeGeometryTopology.from_mapping(
                {
                    "pageBoardRows": raw["pageBoardRows"],
                    "pageBoardColumns": raw["pageBoardColumns"],
                    "cellRows": raw["cellRows"],
                    "cellColumns": raw["cellColumns"],
                    "activeBoardSlots": raw["activeBoardSlots"],
                }
            ),
            v11_profile=(None if profile is None else cast(Mapping[str, object], profile)),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "gameId": self.game_id,
            **self.topology.as_dict(),
            "v11Profile": None if self.v11_profile is None else dict(self.v11_profile),
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryCorpusSource:
    source_id: str
    game_id: str
    relative_path: PurePosixPath
    source_checksum_sha256: str
    split: CorpusSplit
    corpus_role: CorpusRole
    capture_family_id: str
    source_ordinal: int
    scenarios: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryCorpusSource:
        _require_exact_keys(
            raw,
            {
                "sourceId",
                "gameId",
                "relativePath",
                "sourceChecksumSha256",
                "split",
                "corpusRole",
                "captureFamilyId",
                "sourceOrdinal",
                "scenarios",
            },
            "source",
        )
        source_id = raw["sourceId"]
        if not isinstance(source_id, str) or _SOURCE_ID.fullmatch(source_id) is None:
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "sourceId is invalid.")
        game_id = _require_identifier(raw["gameId"], "source.gameId")
        if game_id not in SUPPORTED_GAME_IDS:
            _fail(
                "SHAPE_GEOMETRY_V2_GAME_UNSUPPORTED",
                "Source game is outside the approved scope.",
            )
        try:
            split = CorpusSplit(cast(str, raw["split"]))
            corpus_role = CorpusRole(cast(str, raw["corpusRole"]))
        except ValueError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_CORPUS_INVALID",
                "Source split or corpus role is invalid.",
            ) from error
        capture_family_id = _require_identifier(raw["captureFamilyId"], "captureFamilyId")
        if capture_family_id in _EXCLUDED_V7_DATASET_IDS:
            _fail(
                "SHAPE_GEOMETRY_V2_CORPUS_EXCLUDED_DATASET",
                "Reserved V7 or non-independent Reels data cannot enter shape geometry v2.",
            )
        relative_path = _safe_relative_path(raw["relativePath"], "relativePath")
        if any(part.casefold() in _EXCLUDED_V7_DATASET_IDS for part in relative_path.parts):
            _fail(
                "SHAPE_GEOMETRY_V2_CORPUS_EXCLUDED_DATASET",
                "Reserved V7 or non-independent Reels data cannot enter shape geometry v2.",
            )
        source_ordinal = raw["sourceOrdinal"]
        if type(source_ordinal) is not int or source_ordinal < 1:
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "sourceOrdinal must be positive.")
        raw_scenarios = _require_sequence(raw["scenarios"], "scenarios")
        scenarios = tuple(_require_identifier(value, "scenario") for value in raw_scenarios)
        if not scenarios or len(set(scenarios)) != len(scenarios):
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "Scenarios must be non-empty and unique.")
        return cls(
            source_id=source_id,
            game_id=game_id,
            relative_path=relative_path,
            source_checksum_sha256=_require_sha256(
                raw["sourceChecksumSha256"], "sourceChecksumSha256"
            ),
            split=split,
            corpus_role=corpus_role,
            capture_family_id=capture_family_id,
            source_ordinal=source_ordinal,
            scenarios=scenarios,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "captureFamilyId": self.capture_family_id,
            "corpusRole": self.corpus_role.value,
            "gameId": self.game_id,
            "relativePath": self.relative_path.as_posix(),
            "scenarios": list(self.scenarios),
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
            "sourceOrdinal": self.source_ordinal,
            "split": self.split.value,
        }

    def public_inventory_dict(self, *, size_bytes: int) -> dict[str, object]:
        return {
            "captureFamilyId": self.capture_family_id,
            "corpusRole": self.corpus_role.value,
            "gameId": self.game_id,
            "scenarios": list(self.scenarios),
            "sizeBytes": size_bytes,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
            "sourceOrdinal": self.source_ordinal,
            "split": self.split.value,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryCorpusManifest:
    corpus_root: Path
    visibility: CorpusVisibility
    games: tuple[ShapeGeometryGame, ...]
    sources: tuple[ShapeGeometryCorpusSource, ...]

    def __post_init__(self) -> None:
        games_by_id = {game.game_id: game for game in self.games}
        if len(games_by_id) != len(self.games) or set(games_by_id) != SUPPORTED_GAME_IDS:
            _fail(
                "SHAPE_GEOMETRY_V2_GAME_SET_INVALID",
                "Corpus must declare exactly 777, Blazing, Gang, Reels, and Mummies.",
            )
        source_ids = tuple(source.source_id for source in self.sources)
        relative_paths = tuple(source.relative_path.as_posix() for source in self.sources)
        source_occurrences = tuple(
            (source.game_id, source.capture_family_id, source.source_ordinal)
            for source in self.sources
        )
        if (
            len(set(source_ids)) != len(source_ids)
            or len(set(relative_paths)) != len(relative_paths)
            or len(set(source_occurrences)) != len(source_occurrences)
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_CORPUS_IDENTITY_CONFLICT",
                "Source ID, path, and family ordinal must each be unique.",
            )
        family_splits: dict[tuple[str, str], CorpusSplit] = {}
        checksum_splits: dict[str, CorpusSplit] = {}
        checksum_roles: dict[str, set[CorpusRole]] = defaultdict(set)
        for source in self.sources:
            if source.game_id not in games_by_id:
                _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "Source references an undeclared game.")
            existing_split = family_splits.setdefault(
                (source.game_id, source.capture_family_id), source.split
            )
            if existing_split is not source.split:
                _fail(
                    "SHAPE_GEOMETRY_V2_CAPTURE_FAMILY_SPLIT_LEAKAGE",
                    "One capture family cannot be divided between corpus splits.",
                )
            existing_checksum_split = checksum_splits.setdefault(
                source.source_checksum_sha256, source.split
            )
            if existing_checksum_split is not source.split:
                _fail(
                    "SHAPE_GEOMETRY_V2_CHECKSUM_SPLIT_LEAKAGE",
                    "A byte-identical source cannot be divided between corpus splits.",
                )
            checksum_roles[source.source_checksum_sha256].add(source.corpus_role)
            if self.visibility is CorpusVisibility.EXECUTOR:
                if source.split is CorpusSplit.ACCEPTANCE:
                    _fail(
                        "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
                        "Executor corpus cannot contain acceptance sources.",
                    )
            elif source.split is not CorpusSplit.ACCEPTANCE:
                _fail(
                    "SHAPE_GEOMETRY_V2_EXECUTOR_VISIBILITY_FORBIDDEN",
                    "Acceptance corpus cannot contain development or calibration sources.",
                )
            if source.corpus_role is CorpusRole.ANCHOR_POOL and (
                self.visibility is not CorpusVisibility.EXECUTOR
                or source.split is not CorpusSplit.DEVELOPMENT
            ):
                _fail(
                    "SHAPE_GEOMETRY_V2_ANCHOR_POOL_INVALID",
                    "Anchor pool sources must be development-only executor sources.",
                )
        if any(
            CorpusRole.ANCHOR_POOL in roles and CorpusRole.MEASUREMENT in roles
            for roles in checksum_roles.values()
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_ANCHOR_MEASUREMENT_DUPLICATE",
                "A byte-identical source cannot be both a v2 anchor and measurement evidence.",
            )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryCorpusManifest:
        _require_exact_keys(
            raw,
            {"schemaVersion", "visibility", "corpusRoot", "games", "sources"},
            "manifest",
        )
        if raw["schemaVersion"] != SHAPE_GEOMETRY_V2_CORPUS_SCHEMA_VERSION:
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "Corpus manifest version is unsupported.")
        try:
            visibility = CorpusVisibility(cast(str, raw["visibility"]))
        except ValueError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_CORPUS_INVALID", "Corpus visibility is invalid."
            ) from error
        root = raw["corpusRoot"]
        if not isinstance(root, str) or not root.strip():
            _fail("SHAPE_GEOMETRY_V2_CORPUS_INVALID", "corpusRoot is required.")
        games = tuple(
            ShapeGeometryGame.from_mapping(_require_mapping(item, "game"))
            for item in _require_sequence(raw["games"], "games")
        )
        sources = tuple(
            ShapeGeometryCorpusSource.from_mapping(_require_mapping(item, "source"))
            for item in _require_sequence(raw["sources"], "sources")
        )
        return cls(corpus_root=Path(root), visibility=visibility, games=games, sources=sources)

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "games": [
                    game.as_dict() for game in sorted(self.games, key=lambda value: value.game_id)
                ],
                "schemaVersion": SHAPE_GEOMETRY_V2_CORPUS_SCHEMA_VERSION,
                "sources": [
                    source.as_dict()
                    for source in sorted(self.sources, key=lambda value: value.source_id)
                ],
                "visibility": self.visibility.value,
            }
        )

    def game(self, game_id: str) -> ShapeGeometryGame:
        for game in self.games:
            if game.game_id == game_id:
                return game
        _fail("SHAPE_GEOMETRY_V2_GAME_UNSUPPORTED", "Corpus game is unavailable.")

    def resolved_corpus_root(self) -> Path:
        return _resolved_directory(self.corpus_root)

    def resolve_source_path(self, source: ShapeGeometryCorpusSource) -> Path:
        root = self.resolved_corpus_root()
        candidate = root.joinpath(*source.relative_path.parts)
        inspected = root
        for part in source.relative_path.parts:
            inspected = inspected / part
            if _is_link_or_reparse(inspected):
                _fail(
                    "SHAPE_GEOMETRY_V2_CORPUS_PATH_UNSAFE",
                    "A corpus source traverses a link or junction.",
                )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE",
                "A declared corpus source is unavailable.",
            ) from error
        if not resolved.is_relative_to(root) or not resolved.is_file():
            _fail(
                "SHAPE_GEOMETRY_V2_CORPUS_PATH_UNSAFE",
                "A declared corpus source escapes the corpus root.",
            )
        return resolved

    def freeze_inventory(self) -> ShapeGeometryFrozenInventory:
        entries: list[dict[str, object]] = []
        for source in sorted(self.sources, key=lambda value: value.source_id):
            path = self.resolve_source_path(source)
            try:
                size_bytes = path.stat().st_size
                checksum = _sha256_file(path)
            except OSError as error:
                raise ShapeGeometryCorpusError(
                    "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE",
                    "A declared corpus source cannot be read.",
                ) from error
            if checksum != source.source_checksum_sha256:
                _fail(
                    "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_DRIFT",
                    "A corpus source no longer matches its declared SHA-256.",
                )
            entries.append(source.public_inventory_dict(size_bytes=size_bytes))
        return ShapeGeometryFrozenInventory(
            manifest_fingerprint=self.fingerprint(),
            visibility=self.visibility,
            sources=tuple(entries),
        )


@dataclass(frozen=True, slots=True)
class ShapeGeometryFrozenInventory:
    manifest_fingerprint: str
    visibility: CorpusVisibility
    sources: tuple[dict[str, object], ...]

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "manifestFingerprint": self.manifest_fingerprint,
                "sources": list(self.sources),
                "visibility": self.visibility.value,
            }
        )

    def as_dict(self) -> dict[str, object]:
        duplicates: list[dict[str, object]] = []
        by_checksum: dict[str, list[dict[str, object]]] = defaultdict(list)
        for source in self.sources:
            by_checksum[cast(str, source["sourceChecksumSha256"])].append(source)
        for checksum, occurrences in sorted(by_checksum.items()):
            if len(occurrences) > 1:
                duplicates.append(
                    {
                        "gameIds": sorted({cast(str, value["gameId"]) for value in occurrences}),
                        "occurrenceCount": len(occurrences),
                        "sourceChecksumSha256": checksum,
                        "sourceIds": sorted(cast(str, value["sourceId"]) for value in occurrences),
                    }
                )
        per_game: list[dict[str, object]] = []
        for game_id in sorted(SUPPORTED_GAME_IDS):
            game_sources = [value for value in self.sources if value["gameId"] == game_id]
            per_game.append(
                {
                    "captureFamilyCount": len(
                        {cast(str, value["captureFamilyId"]) for value in game_sources}
                    ),
                    "gameId": game_id,
                    "sourceCount": len(game_sources),
                    "uniqueSourceChecksumCount": len(
                        {cast(str, value["sourceChecksumSha256"]) for value in game_sources}
                    ),
                }
            )
        return {
            "duplicates": duplicates,
            "inventoryFingerprint": self.fingerprint(),
            "manifestFingerprint": self.manifest_fingerprint,
            "perGame": per_game,
            "schemaVersion": SHAPE_GEOMETRY_V2_INVENTORY_VERSION,
            "sources": list(self.sources),
            "visibility": self.visibility.value,
        }


def load_shape_geometry_corpus_manifest(path: Path) -> ShapeGeometryCorpusManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_CORPUS_MANIFEST_UNREADABLE",
            "Corpus manifest cannot be read.",
        ) from error
    return ShapeGeometryCorpusManifest.from_mapping(_require_mapping(raw, "manifest"))


def load_inventory_report(path: Path) -> Mapping[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_INVENTORY_UNREADABLE",
            "Frozen corpus inventory cannot be read.",
        ) from error
    return _require_mapping(raw, "inventory report")


def require_current_inventory(
    manifest: ShapeGeometryCorpusManifest, saved_report: Mapping[str, object]
) -> ShapeGeometryFrozenInventory:
    current = manifest.freeze_inventory()
    expected = current.as_dict()
    required_keys = {
        "duplicates",
        "inventoryFingerprint",
        "manifestFingerprint",
        "perGame",
        "schemaVersion",
        "sources",
        "visibility",
    }
    if (
        set(saved_report) != required_keys
        or saved_report.get("schemaVersion") != SHAPE_GEOMETRY_V2_INVENTORY_VERSION
        or canonical_json_bytes(saved_report) != canonical_json_bytes(expected)
    ):
        _fail(
            "SHAPE_GEOMETRY_V2_INVENTORY_DRIFT",
            "Frozen corpus inventory differs from the current manifest or sources.",
        )
    return current


def verify_split_boundary(
    executor_manifest: ShapeGeometryCorpusManifest,
    acceptance_manifest: ShapeGeometryCorpusManifest,
) -> dict[str, object]:
    """Check both frozen corpora without exposing acceptance source paths in output."""

    if executor_manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail("SHAPE_GEOMETRY_V2_BOUNDARY_INVALID", "Executor manifest visibility is required.")
    if acceptance_manifest.visibility is not CorpusVisibility.ACCEPTANCE:
        _fail("SHAPE_GEOMETRY_V2_BOUNDARY_INVALID", "Acceptance manifest visibility is required.")
    executor = executor_manifest.freeze_inventory()
    acceptance = acceptance_manifest.freeze_inventory()
    executor_hashes = {
        cast(str, source["sourceChecksumSha256"]) for source in executor.sources
    }
    acceptance_hashes = {
        cast(str, source["sourceChecksumSha256"]) for source in acceptance.sources
    }
    if executor_hashes & acceptance_hashes:
        _fail(
            "SHAPE_GEOMETRY_V2_CHECKSUM_SPLIT_LEAKAGE",
            "A byte-identical source crosses the executor and acceptance boundary.",
        )
    executor_families = {
        (cast(str, source["gameId"]), cast(str, source["captureFamilyId"]))
        for source in executor.sources
    }
    acceptance_families = {
        (cast(str, source["gameId"]), cast(str, source["captureFamilyId"]))
        for source in acceptance.sources
    }
    if executor_families & acceptance_families:
        _fail(
            "SHAPE_GEOMETRY_V2_CAPTURE_FAMILY_SPLIT_LEAKAGE",
            "A capture family crosses the executor and acceptance boundary.",
        )
    return {
        "acceptanceInventoryFingerprint": acceptance.fingerprint(),
        "acceptanceSourceCount": len(acceptance.sources),
        "executorInventoryFingerprint": executor.fingerprint(),
        "executorSourceCount": len(executor.sources),
        "status": "passed",
        "version": "shape-geometry-v2-split-boundary-v1",
    }


@dataclass(frozen=True, slots=True)
class ShapeGeometryManualAnnotation:
    source_id: str
    source_checksum_sha256: str
    page_state: ManualPageState
    topology_confirmed: bool
    visible_grid: bool
    anchor_candidate: bool
    active_operator_seconds: int

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryManualAnnotation:
        _require_exact_keys(
            raw,
            {
                "sourceId",
                "sourceChecksumSha256",
                "pageState",
                "topologyConfirmed",
                "visibleGrid",
                "anchorCandidate",
                "activeOperatorSeconds",
            },
            "manual annotation",
        )
        source_id = raw["sourceId"]
        if not isinstance(source_id, str) or _SOURCE_ID.fullmatch(source_id) is None:
            _fail("SHAPE_GEOMETRY_V2_ANNOTATION_INVALID", "Annotation sourceId is invalid.")
        try:
            page_state = ManualPageState(cast(str, raw["pageState"]))
        except ValueError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_ANNOTATION_INVALID", "Annotation pageState is invalid."
            ) from error
        bool_fields = ("topologyConfirmed", "visibleGrid", "anchorCandidate")
        if any(type(raw[field]) is not bool for field in bool_fields):
            _fail("SHAPE_GEOMETRY_V2_ANNOTATION_INVALID", "Annotation boolean fields are invalid.")
        active_seconds = raw["activeOperatorSeconds"]
        if type(active_seconds) is not int or active_seconds < 0:
            _fail(
                "SHAPE_GEOMETRY_V2_ANNOTATION_INVALID",
                "activeOperatorSeconds must be a non-negative integer.",
            )
        return cls(
            source_id=source_id,
            source_checksum_sha256=_require_sha256(
                raw["sourceChecksumSha256"], "annotation.sourceChecksumSha256"
            ),
            page_state=page_state,
            topology_confirmed=cast(bool, raw["topologyConfirmed"]),
            visible_grid=cast(bool, raw["visibleGrid"]),
            anchor_candidate=cast(bool, raw["anchorCandidate"]),
            active_operator_seconds=active_seconds,
        )


@dataclass(frozen=True, slots=True)
class ShapeGeometryManualAnnotations:
    corpus_manifest_fingerprint: str
    annotations: tuple[ShapeGeometryManualAnnotation, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryManualAnnotations:
        _require_exact_keys(
            raw,
            {"schemaVersion", "corpusManifestFingerprint", "annotations"},
            "annotation document",
        )
        if raw["schemaVersion"] != SHAPE_GEOMETRY_V2_ANNOTATION_SCHEMA_VERSION:
            _fail("SHAPE_GEOMETRY_V2_ANNOTATION_INVALID", "Annotation version is unsupported.")
        annotations = tuple(
            ShapeGeometryManualAnnotation.from_mapping(_require_mapping(item, "manual annotation"))
            for item in _require_sequence(raw["annotations"], "annotations")
        )
        source_ids = tuple(annotation.source_id for annotation in annotations)
        if len(set(source_ids)) != len(source_ids):
            _fail(
                "SHAPE_GEOMETRY_V2_ANNOTATION_INVALID",
                "Manual annotation source IDs are duplicated.",
            )
        return cls(
            corpus_manifest_fingerprint=_require_sha256(
                raw["corpusManifestFingerprint"], "corpusManifestFingerprint"
            ),
            annotations=annotations,
        )

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "annotations": [
                    {
                        "activeOperatorSeconds": value.active_operator_seconds,
                        "anchorCandidate": value.anchor_candidate,
                        "pageState": value.page_state.value,
                        "sourceChecksumSha256": value.source_checksum_sha256,
                        "sourceId": value.source_id,
                        "topologyConfirmed": value.topology_confirmed,
                        "visibleGrid": value.visible_grid,
                    }
                    for value in sorted(self.annotations, key=lambda value: value.source_id)
                ],
                "corpusManifestFingerprint": self.corpus_manifest_fingerprint,
                "schemaVersion": SHAPE_GEOMETRY_V2_ANNOTATION_SCHEMA_VERSION,
            }
        )


def load_manual_annotations(
    path: Path, manifest: ShapeGeometryCorpusManifest
) -> ShapeGeometryManualAnnotations:
    if manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
            "Anchor annotations are unavailable for an acceptance corpus.",
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_ANNOTATION_UNREADABLE",
            "Manual annotations cannot be read.",
        ) from error
    document = ShapeGeometryManualAnnotations.from_mapping(
        _require_mapping(raw, "annotation document")
    )
    if document.corpus_manifest_fingerprint != manifest.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_ANNOTATION_DRIFT",
            "Manual annotations reference a different executor corpus manifest.",
        )
    sources_by_id = {source.source_id: source for source in manifest.sources}
    for annotation in document.annotations:
        source = sources_by_id.get(annotation.source_id)
        if source is None or source.source_checksum_sha256 != annotation.source_checksum_sha256:
            _fail(
                "SHAPE_GEOMETRY_V2_ANNOTATION_DRIFT",
                "Manual annotation source identity differs from the corpus manifest.",
            )
    return document


def select_v2_anchors(
    manifest: ShapeGeometryCorpusManifest, annotations: ShapeGeometryManualAnnotations
) -> dict[str, object]:
    """Select exactly one pre-prediction v2 anchor per game, or report its absence."""

    if manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
            "Acceptance sources cannot participate in v2 anchor selection.",
        )
    if annotations.corpus_manifest_fingerprint != manifest.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_ANNOTATION_DRIFT",
            "Annotations do not belong to this executor corpus.",
        )
    sources_by_id = {source.source_id: source for source in manifest.sources}
    for annotation in annotations.annotations:
        source = sources_by_id.get(annotation.source_id)
        if source is None or source.source_checksum_sha256 != annotation.source_checksum_sha256:
            _fail(
                "SHAPE_GEOMETRY_V2_ANNOTATION_DRIFT",
                "Anchor annotation source identity differs from the corpus manifest.",
            )
    annotations_by_source = {value.source_id: value for value in annotations.annotations}
    games: list[dict[str, object]] = []
    for game_id in sorted(SUPPORTED_GAME_IDS):
        candidates = sorted(
            (
                source
                for source in manifest.sources
                if source.game_id == game_id and source.corpus_role is CorpusRole.ANCHOR_POOL
            ),
            key=lambda value: (
                value.capture_family_id,
                value.source_ordinal,
                value.source_checksum_sha256,
                value.source_id,
            ),
        )
        decisions: list[dict[str, object]] = []
        selected: ShapeGeometryCorpusSource | None = None
        for source in candidates:
            candidate_annotation = annotations_by_source.get(source.source_id)
            reasons: list[str] = []
            if source.split is not CorpusSplit.DEVELOPMENT:
                reasons.append("NOT_DEVELOPMENT")
            if candidate_annotation is None:
                reasons.append("ANNOTATION_MISSING")
            else:
                if candidate_annotation.page_state is not ManualPageState.COMPLETE:
                    reasons.append("PAGE_NOT_COMPLETE")
                if not candidate_annotation.topology_confirmed:
                    reasons.append("TOPOLOGY_UNCONFIRMED")
                if not candidate_annotation.visible_grid:
                    reasons.append("GRID_NOT_VISIBLE")
                if not candidate_annotation.anchor_candidate:
                    reasons.append("NOT_MARKED_ANCHOR_CANDIDATE")
            eligible = not reasons and selected is None
            if eligible:
                selected = source
            decisions.append(
                {
                    "eligible": eligible,
                    "reasons": (
                        reasons if reasons else (["SELECTED"] if eligible else ["LATER_CANDIDATE"])
                    ),
                    "sourceChecksumSha256": source.source_checksum_sha256,
                    "sourceId": source.source_id,
                }
            )
        games.append(
            {
                "anchor": (
                    None
                    if selected is None
                    else {
                        "sourceChecksumSha256": selected.source_checksum_sha256,
                        "sourceId": selected.source_id,
                    }
                ),
                "candidateCount": len(candidates),
                "candidates": decisions,
                "gameId": game_id,
                "status": "selected" if selected is not None else "not_evaluable",
            }
        )
    return {
        "annotationFingerprint": annotations.fingerprint(),
        "corpusManifestFingerprint": manifest.fingerprint(),
        "games": games,
        "schemaVersion": SHAPE_GEOMETRY_V2_ANCHOR_SELECTION_VERSION,
    }


def run_v11_baseline(
    manifest: ShapeGeometryCorpusManifest,
    inventory: ShapeGeometryFrozenInventory,
    *,
    max_sources_per_game: int = 10,
) -> dict[str, object]:
    """Evaluate the existing v1.1 registrar without a job, database, or write."""

    if manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
            "Baseline cannot read an acceptance corpus.",
        )
    if not 1 <= max_sources_per_game <= 10:
        _fail(
            "SHAPE_GEOMETRY_V2_BASELINE_LIMIT_INVALID",
            "Baseline may process from one to ten sources per game.",
        )
    current = manifest.freeze_inventory()
    if current.fingerprint() != inventory.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_INVENTORY_DRIFT",
            "Baseline requires the current checksum-bound executor inventory.",
        )
    games: list[dict[str, object]] = []
    for game_id in sorted(SUPPORTED_GAME_IDS):
        game = manifest.game(game_id)
        selected = tuple(
            sorted(
                (
                    source
                    for source in manifest.sources
                    if source.game_id == game_id
                    and source.corpus_role is CorpusRole.MEASUREMENT
                    and source.split in {CorpusSplit.DEVELOPMENT, CorpusSplit.CALIBRATION}
                ),
                key=lambda value: (
                    value.capture_family_id,
                    value.source_ordinal,
                    value.source_checksum_sha256,
                    value.source_id,
                ),
            )[:max_sources_per_game]
        )
        if not selected:
            games.append(
                {
                    "gameId": game_id,
                    "results": [],
                    "selectedSourceCount": 0,
                    "status": "not_evaluable",
                    "v11ProfileFingerprint": None,
                }
            )
            continue
        if not _is_usable_v11_profile(game.v11_profile):
            games.append(
                {
                    "gameId": game_id,
                    "results": [
                        _baseline_source_result(source, "not_configured") for source in selected
                    ],
                    "selectedSourceCount": len(selected),
                    "status": "not_configured",
                    "v11ProfileFingerprint": None,
                }
            )
            continue
        game_sources_by_checksum: dict[str, ShapeGeometryCorpusSource] = {}
        for source in sorted(
            (value for value in manifest.sources if value.game_id == game_id),
            key=lambda value: value.source_id,
        ):
            game_sources_by_checksum.setdefault(source.source_checksum_sha256, source)
        registrar = _build_v11_registrar(
            manifest,
            game.v11_profile,
            game_sources_by_checksum,
        )
        source_results = [
            _evaluate_v11_source(manifest, source, registrar) for source in selected
        ]
        games.append(
            {
                "gameId": game_id,
                "results": source_results,
                "selectedSourceCount": len(selected),
                "status": "measured",
                "v11ProfileFingerprint": _fingerprint(game.v11_profile),
            }
        )
    return {
        "corpusInventoryFingerprint": inventory.fingerprint(),
        "corpusManifestFingerprint": manifest.fingerprint(),
        "engineVariant": V11_ENGINE_VARIANT,
        "games": games,
        "maximumSourcesPerGame": max_sources_per_game,
        "schemaVersion": SHAPE_GEOMETRY_V2_V11_BASELINE_VERSION,
    }


def require_matching_baseline(
    saved_report: Mapping[str, object], current_report: Mapping[str, object]
) -> None:
    if canonical_json_bytes(saved_report) != canonical_json_bytes(current_report):
        _fail(
            "SHAPE_GEOMETRY_V2_V11_BASELINE_DRIFT",
            "Baseline output differs from the checksum-bound saved report.",
        )


def _is_usable_v11_profile(profile: Mapping[str, object] | None) -> bool:
    if profile is None:
        return False
    anchors = profile.get("anchors")
    return isinstance(anchors, Sequence) and not isinstance(anchors, str | bytes) and bool(anchors)


def _pinned_v11_anchor_checksums(profile: Mapping[str, object] | None) -> tuple[str, ...]:
    if profile is None:
        _fail("SHAPE_GEOMETRY_V2_V11_PROFILE_INVALID", "Pinned v1.1 profile is missing.")
    anchors = profile.get("anchors")
    if not isinstance(anchors, Sequence) or isinstance(anchors, str | bytes) or not anchors:
        _fail("SHAPE_GEOMETRY_V2_V11_PROFILE_INVALID", "Pinned v1.1 profile has no anchors.")
    checksums: list[str] = []
    for raw_anchor in anchors:
        anchor = _require_mapping(raw_anchor, "v1.1 profile anchor")
        checksum = _require_sha256(
            anchor.get("sourceChecksumSha256"),
            "v1.1 profile anchor.sourceChecksumSha256",
        )
        checksums.append(checksum)
    if len(set(checksums)) != len(checksums):
        _fail(
            "SHAPE_GEOMETRY_V2_V11_PROFILE_INVALID",
            "Pinned v1.1 profile anchor checksums are duplicated.",
        )
    return tuple(checksums)


def _build_v11_registrar(
    manifest: ShapeGeometryCorpusManifest,
    profile: Mapping[str, object] | None,
    sources_by_checksum: Mapping[str, ShapeGeometryCorpusSource],
) -> Any:
    from game_predictor_worker.images.page_geometry_registration import VerifiedPageRegistrar

    anchor_images: dict[str, Any] = {}
    for checksum in _pinned_v11_anchor_checksums(profile):
        source = sources_by_checksum.get(checksum)
        if source is None:
            _fail(
                "SHAPE_GEOMETRY_V2_V11_PROFILE_ANCHOR_MISSING",
                "Pinned v1.1 profile refers to a source outside the evaluated game.",
            )
        anchor_images[checksum] = _load_exif_normalized_rgb(manifest, source)

    def load_anchor_rgb(checksum: str) -> Any:
        return anchor_images[checksum]

    registrar = VerifiedPageRegistrar(profile, load_anchor_rgb=load_anchor_rgb)
    registrar.prepare()
    if not registrar.available:
        _fail(
            "SHAPE_GEOMETRY_V2_V11_PROFILE_INVALID",
            "Pinned v1.1 profile has no usable executor-corpus anchor.",
        )
    return registrar


def _evaluate_v11_source(
    manifest: ShapeGeometryCorpusManifest, source: ShapeGeometryCorpusSource, registrar: Any
) -> dict[str, object]:
    try:
        rgb = _load_exif_normalized_rgb(manifest, source)
    except ShapeGeometryCorpusError:
        raise
    except (OSError, ValueError):
        return _baseline_source_result(
            source,
            "source_error",
            reason_code="IMAGE_DECODE_UNAVAILABLE",
        )
    evaluation = registrar.evaluate(rgb)
    if evaluation.result is not None:
        return _baseline_source_result(
            source,
            "registered",
            geometry=cast(Mapping[str, object], evaluation.result.to_payload()),
        )
    return _baseline_source_result(
        source,
        "review_required",
        diagnostics=cast(Mapping[str, object], evaluation.failure_payload()),
    )


def _load_exif_normalized_rgb(
    manifest: ShapeGeometryCorpusManifest, source: ShapeGeometryCorpusSource
) -> Any:
    """Decode only one already-attested corpus JPEG into the canonical RGB space."""

    from io import BytesIO

    import numpy as np
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        encoded = manifest.resolve_source_path(source).read_bytes()
        if hashlib.sha256(encoded).hexdigest() != source.source_checksum_sha256:
            _fail(
                "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_DRIFT",
                "A corpus source changed after its inventory was frozen.",
            )
        with Image.open(BytesIO(encoded)) as image:
            image.load()
            return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)
    except (OSError, UnidentifiedImageError) as error:
        raise ValueError("Corpus JPEG cannot be decoded.") from error


def _baseline_source_result(
    source: ShapeGeometryCorpusSource,
    status: str,
    *,
    geometry: Mapping[str, object] | None = None,
    diagnostics: Mapping[str, object] | None = None,
    reason_code: str | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "sourceChecksumSha256": source.source_checksum_sha256,
        "sourceId": source.source_id,
        "status": status,
    }
    if geometry is not None:
        payload["geometry"] = dict(geometry)
    if diagnostics is not None:
        payload["diagnostics"] = dict(diagnostics)
    if reason_code is not None:
        payload["reasonCode"] = reason_code
    return payload


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


__all__ = [
    "CorpusRole",
    "CorpusSplit",
    "CorpusVisibility",
    "ManualPageState",
    "SHAPE_GEOMETRY_V2_ANCHOR_SELECTION_VERSION",
    "SHAPE_GEOMETRY_V2_ANNOTATION_SCHEMA_VERSION",
    "SHAPE_GEOMETRY_V2_CORPUS_SCHEMA_VERSION",
    "SHAPE_GEOMETRY_V2_INVENTORY_VERSION",
    "SHAPE_GEOMETRY_V2_V11_BASELINE_VERSION",
    "ShapeGeometryCorpusError",
    "ShapeGeometryCorpusManifest",
    "ShapeGeometryFrozenInventory",
    "ShapeGeometryManualAnnotations",
    "canonical_json_bytes",
    "load_inventory_report",
    "load_manual_annotations",
    "load_shape_geometry_corpus_manifest",
    "require_current_inventory",
    "require_matching_baseline",
    "run_v11_baseline",
    "select_v2_anchors",
    "verify_split_boundary",
]
