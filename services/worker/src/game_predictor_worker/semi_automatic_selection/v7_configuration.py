"""Pure configuration and corpus contracts for v7 representative selection."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NoReturn

from .contracts import SemiAutomaticSelectionDirection, SemiAutomaticSelectionRange

V7_CONFIGURATION_VERSION = "v7-selection-configuration-v1"
V7_CORPUS_MANIFEST_VERSION = 2
V7_FULL_PAGE_BOARD_COUNT = 9
_RANGE_INPUT = re.compile(r"(?P<start>[1-9]\d*)(?:\s*-\s*(?P<end>[1-9]\d*))?")
_CASE_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
_GEOMETRY_FAMILY_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT = 0x0400
_MUMMIES_REFERENCE_DIRECTORY = "wybrane mumie"


class V7SelectionConfigurationError(ValueError):
    """A deliberately reason-coded invalid v7 setup."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class V7SelectionMode(StrEnum):
    AUTOMATIC = "automatic"
    SEMI_AUTOMATIC = "semi_automatic"


class V7BorderStyle(StrEnum):
    TOP_AND_SIDES = "top_and_sides"
    FULL_FRAME = "full_frame"
    IRREGULAR_OR_NONE = "irregular_or_none"


class V7CorpusSplit(StrEnum):
    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    VALIDATION = "validation"
    HOLDOUT = "holdout"
    REFERENCE_ONLY = "reference_only"


@dataclass(frozen=True, slots=True)
class V7SelectionConfiguration:
    """Validated full-page configuration before any source is scanned."""

    source_root: Path
    output_root: Path
    mode: V7SelectionMode
    direction: SemiAutomaticSelectionDirection
    first_range: SemiAutomaticSelectionRange
    last_range: SemiAutomaticSelectionRange
    border_style: V7BorderStyle
    expected_ranges: tuple[SemiAutomaticSelectionRange, ...]

    @property
    def expected_group_count(self) -> int:
        return len(self.expected_ranges)

    def as_dict(self) -> dict[str, object]:
        return {
            "borderStyle": self.border_style.value,
            "direction": self.direction.value,
            "expectedGroupCount": self.expected_group_count,
            "expectedRanges": [value.as_dict() for value in self.expected_ranges],
            "firstRange": self.first_range.as_dict(),
            "lastRange": self.last_range.as_dict(),
            "mode": self.mode.value,
            "outputRoot": str(self.output_root),
            "sourceRoot": str(self.source_root),
            "version": V7_CONFIGURATION_VERSION,
        }


@dataclass(frozen=True, slots=True)
class V7CorpusCase:
    """One named, non-production corpus directory and its annotation role."""

    case_id: str
    directory_name: str
    split: V7CorpusSplit
    border_style: V7BorderStyle | None
    scenarios: tuple[str, ...]
    expected_direction: SemiAutomaticSelectionDirection | None
    geometry_family_id: str | None = None
    source_game_ref: str | None = None

    def __post_init__(self) -> None:
        if not _CASE_ID.fullmatch(self.case_id):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus case ID is invalid.")
        if self.geometry_family_id is not None and not _GEOMETRY_FAMILY_ID.fullmatch(
            self.geometry_family_id
        ):
            _fail("V7_CORPUS_CASE_INVALID", "Geometry family ID is invalid.")
        if self.source_game_ref is not None and (
            not self.source_game_ref.strip() or len(self.source_game_ref) > 128
        ):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus source game reference is invalid.")
        directory = Path(self.directory_name)
        if (
            not self.directory_name
            or directory.name != self.directory_name
            or directory.is_absolute()
            or self.directory_name in {".", ".."}
        ):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus directory must be one direct child.")
        if not self.scenarios or len(set(self.scenarios)) != len(self.scenarios):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus scenarios must be non-empty and unique.")
        if self.directory_name.casefold() == _MUMMIES_REFERENCE_DIRECTORY and (
            self.split is not V7CorpusSplit.REFERENCE_ONLY
            or "quality_reference" not in self.scenarios
        ):
            _fail(
                "V7_CORPUS_MUMMIES_ROLE_INVALID",
                "Selected mummies are a quality-only reference and cannot score grouping.",
            )
        if self.split is V7CorpusSplit.REFERENCE_ONLY:
            if "quality_reference" not in self.scenarios:
                _fail(
                    "V7_CORPUS_REFERENCE_INVALID",
                    "A reference-only case must declare quality_reference.",
                )
        elif "quality_reference" in self.scenarios:
            _fail(
                "V7_CORPUS_REFERENCE_INVALID",
                "Only a reference-only case may declare quality_reference.",
            )

    def as_dict(self, *, schema_version: int = V7_CORPUS_MANIFEST_VERSION) -> dict[str, object]:
        value: dict[str, object] = {
            "borderStyle": None if self.border_style is None else self.border_style.value,
            "caseId": self.case_id,
            "directoryName": self.directory_name,
            "expectedDirection": (
                None if self.expected_direction is None else self.expected_direction.value
            ),
            "scenarios": list(self.scenarios),
            "split": self.split.value,
        }
        if schema_version >= 2:
            value["geometryFamilyId"] = self.geometry_family_id
            value["sourceGameRef"] = self.source_game_ref
        return value


@dataclass(frozen=True, slots=True)
class V7CorpusCaseInventory:
    """Frozen identity of the direct JPEG files in one annotated corpus case."""

    case_id: str
    jpeg_count: int
    fingerprint: str

    def as_dict(self) -> dict[str, object]:
        return {
            "caseId": self.case_id,
            "fingerprint": self.fingerprint,
            "jpegCount": self.jpeg_count,
        }


@dataclass(frozen=True, slots=True)
class V7CorpusSourceFile:
    """One direct JPEG resolved only from a validated corpus case."""

    case_id: str
    path: Path
    source_checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class V7CorpusManifest:
    """A filesystem-validated, split-safe corpus manifest for v7 evaluation."""

    corpus_root: Path
    cases: tuple[V7CorpusCase, ...]
    schema_version: int = V7_CORPUS_MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.schema_version not in {1, V7_CORPUS_MANIFEST_VERSION}:
            _fail("V7_CORPUS_MANIFEST_INVALID", "Corpus manifest version is unsupported.")
        if self.schema_version == 1 and any(
            item.geometry_family_id is not None or item.source_game_ref is not None
            for item in self.cases
        ):
            _fail(
                "V7_CORPUS_MANIFEST_INVALID",
                "Corpus manifest V1 cannot declare V2 geometry fields.",
            )
        case_ids = tuple(item.case_id for item in self.cases)
        directories = tuple(item.directory_name for item in self.cases)
        if (
            not self.cases
            or len(set(case_ids)) != len(case_ids)
            or len(set(directories)) != len(directories)
        ):
            _fail(
                "V7_CORPUS_MANIFEST_INVALID",
                "Corpus cases must have unique IDs and directories.",
            )
        splits = {item.split for item in self.cases}
        required = {
            V7CorpusSplit.DEVELOPMENT,
            V7CorpusSplit.CALIBRATION,
            V7CorpusSplit.VALIDATION,
            V7CorpusSplit.HOLDOUT,
        }
        if not required.issubset(splits):
            _fail("V7_CORPUS_SPLITS_INCOMPLETE", "Corpus lacks one of the four scored splits.")

    def freeze_inventory(self) -> tuple[V7CorpusCaseInventory, ...]:
        root = self.resolved_corpus_root()
        direct_entries = tuple(root.iterdir())
        if any(item.is_dir() and _is_link_or_reparse(item) for item in direct_entries):
            _fail(
                "V7_CORPUS_PATH_UNSAFE",
                "Corpus cannot contain a linked or junction case directory.",
            )
        actual_directories = {item.name for item in direct_entries if item.is_dir()}
        declared_directories = {item.directory_name for item in self.cases}
        if actual_directories != declared_directories:
            _fail(
                "V7_CORPUS_DIRECTORY_DRIFT",
                "Corpus direct directories differ from the frozen manifest configuration.",
            )
        inventory: list[V7CorpusCaseInventory] = []
        for case in self.cases:
            directory = root / case.directory_name
            inventory.append(
                V7CorpusCaseInventory(
                    case_id=case.case_id,
                    jpeg_count=len(_direct_jpegs(directory)),
                    fingerprint=_directory_fingerprint(directory),
                )
            )
        if any(item.jpeg_count == 0 for item in inventory):
            _fail("V7_CORPUS_SPLIT_EMPTY", "Every declared corpus case must contain a JPEG.")
        return tuple(inventory)

    def fingerprint(self) -> str:
        return _fingerprint(
            {"cases": [item.as_dict(schema_version=self.schema_version) for item in self.cases]}
        )

    def resolved_corpus_root(self) -> Path:
        """Return the physical corpus root after rejecting every linked ancestor."""

        return _resolve_directory(self.corpus_root, "V7_CORPUS_ROOT_UNAVAILABLE")

    def resolve_case_sources(
        self,
        case_ids: tuple[str, ...],
    ) -> tuple[V7CorpusSourceFile, ...]:
        """Resolve direct JPEGs only after validating the whole corpus topology.

        Paths returned by this method are intentionally server-side values. HTTP
        callers must expose only a session source identity derived from their
        checksum, never this path or its file name.
        """

        if not case_ids or len(set(case_ids)) != len(case_ids):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus source cases must be unique and non-empty.")
        cases_by_id = {case.case_id: case for case in self.cases}
        if any(case_id not in cases_by_id for case_id in case_ids):
            _fail("V7_CORPUS_CASE_INVALID", "Corpus source case is not declared.")
        self.freeze_inventory()
        root = self.resolved_corpus_root()
        result: list[V7CorpusSourceFile] = []
        for case_id in case_ids:
            directory = _resolve_directory(
                root / cases_by_id[case_id].directory_name,
                "V7_CORPUS_SOURCE_UNAVAILABLE",
            )
            if not directory.is_relative_to(root):
                _fail("V7_CORPUS_PATH_UNSAFE", "Corpus source directory escapes its root.")
            for path in _direct_jpegs(directory):
                try:
                    result.append(
                        V7CorpusSourceFile(
                            case_id=case_id,
                            path=path,
                            source_checksum_sha256=_sha256_file(path),
                            size_bytes=path.stat().st_size,
                        )
                    )
                except OSError as error:
                    raise V7SelectionConfigurationError(
                        "V7_CORPUS_SOURCE_UNAVAILABLE", "Corpus JPEG cannot be read."
                    ) from error
        return tuple(result)


def parse_v7_full_range(value: str) -> SemiAutomaticSelectionRange:
    """Normalize `10` and `10–18` into exactly one complete 3×3 page."""

    match = _RANGE_INPUT.fullmatch(value.strip().replace("–", "-"))
    if match is None:
        _fail("V7_RANGE_INPUT_INVALID", "A range must be a positive number or start-end.")
    start = int(match.group("start"))
    end_text = match.group("end")
    end = start + V7_FULL_PAGE_BOARD_COUNT - 1 if end_text is None else int(end_text)
    try:
        value_range = SemiAutomaticSelectionRange(start=start, end=end)
    except ValueError as error:
        raise V7SelectionConfigurationError(
            "V7_RANGE_INPUT_INVALID", "Range end must not be before its start."
        ) from error
    if value_range.board_count != V7_FULL_PAGE_BOARD_COUNT:
        _fail("V7_FULL_PAGE_REQUIRED", "Automatic v7 configuration requires exactly nine boards.")
    return value_range


def build_v7_selection_configuration(
    *,
    source_root: Path,
    first_range_input: str,
    last_range_input: str,
    direction: SemiAutomaticSelectionDirection = SemiAutomaticSelectionDirection.ASCENDING,
    mode: V7SelectionMode = V7SelectionMode.SEMI_AUTOMATIC,
    border_style: V7BorderStyle = V7BorderStyle.TOP_AND_SIDES,
) -> V7SelectionConfiguration:
    """Build expected full pages without inferring any number from source order."""

    first_range = parse_v7_full_range(first_range_input)
    last_range = parse_v7_full_range(last_range_input)
    if direction is SemiAutomaticSelectionDirection.ASCENDING:
        first_number, last_number = first_range.start, last_range.end
    else:
        first_number, last_number = first_range.end, last_range.start
    try:
        from .contracts import SemiAutomaticSequenceBounds

        bounds = SemiAutomaticSequenceBounds(
            first_sequence_number=first_number,
            last_sequence_number=last_number,
            direction=direction,
            full_range_size=V7_FULL_PAGE_BOARD_COUNT,
        )
    except ValueError as error:
        raise V7SelectionConfigurationError(
            "V7_RANGE_DIRECTION_INVALID", "The first and last pages contradict the direction."
        ) from error
    expected_ranges = bounds.expected_ranges()
    if expected_ranges[0] != first_range or expected_ranges[-1] != last_range:
        _fail("V7_RANGE_ALIGNMENT_INVALID", "First and last values must delimit whole pages.")
    source_path = Path(source_root)
    if not source_path.name:
        _fail("V7_SOURCE_ROOT_INVALID", "The source folder must not be a filesystem root.")
    return V7SelectionConfiguration(
        source_root=source_path,
        output_root=source_path.with_name(f"{source_path.name} cut"),
        mode=mode,
        direction=direction,
        first_range=first_range,
        last_range=last_range,
        border_style=border_style,
        expected_ranges=expected_ranges,
    )


def load_v7_corpus_manifest(path: Path) -> V7CorpusManifest:
    """Load explicit non-production corpus metadata; production never calls this."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise V7SelectionConfigurationError(
            "V7_CORPUS_MANIFEST_UNREADABLE", "Corpus manifest cannot be read."
        ) from error
    if not isinstance(payload, dict) or payload.get("schemaVersion") not in {
        1,
        V7_CORPUS_MANIFEST_VERSION,
    }:
        _fail("V7_CORPUS_MANIFEST_INVALID", "Corpus manifest version is unsupported.")
    root = payload.get("corpusRoot")
    raw_cases = payload.get("cases")
    if not isinstance(root, str) or not isinstance(raw_cases, list):
        _fail("V7_CORPUS_MANIFEST_INVALID", "Corpus root and cases are required.")
    cases: list[V7CorpusCase] = []
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            _fail("V7_CORPUS_MANIFEST_INVALID", "Corpus case must be an object.")
        if payload["schemaVersion"] == 1 and any(
            raw_case.get(field) is not None for field in ("geometryFamilyId", "sourceGameRef")
        ):
            _fail(
                "V7_CORPUS_MANIFEST_INVALID",
                "Corpus manifest V1 cannot declare V2 geometry fields.",
            )
        try:
            raw_border = raw_case.get("borderStyle")
            raw_direction = raw_case.get("expectedDirection")
            scenarios = raw_case["scenarios"]
            if not isinstance(scenarios, list) or not all(
                isinstance(value, str) for value in scenarios
            ):
                _fail("V7_CORPUS_MANIFEST_INVALID", "Corpus scenarios must be a list of strings.")
            cases.append(
                V7CorpusCase(
                    case_id=str(raw_case["caseId"]),
                    directory_name=str(raw_case["directoryName"]),
                    split=V7CorpusSplit(str(raw_case["split"])),
                    border_style=None if raw_border is None else V7BorderStyle(str(raw_border)),
                    scenarios=tuple(scenarios),
                    expected_direction=(
                        None
                        if raw_direction is None
                        else SemiAutomaticSelectionDirection(str(raw_direction))
                    ),
                    geometry_family_id=(
                        None
                        if raw_case.get("geometryFamilyId") is None
                        else str(raw_case["geometryFamilyId"])
                    ),
                    source_game_ref=(
                        None
                        if raw_case.get("sourceGameRef") is None
                        else str(raw_case["sourceGameRef"])
                    ),
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise V7SelectionConfigurationError(
                "V7_CORPUS_MANIFEST_INVALID", "Corpus case is invalid."
            ) from error
    return V7CorpusManifest(
        corpus_root=Path(root),
        cases=tuple(cases),
        schema_version=int(payload["schemaVersion"]),
    )


def _direct_jpegs(directory: Path) -> tuple[Path, ...]:
    entries = tuple(directory.iterdir())
    if any(_is_link_or_reparse(item) for item in entries):
        _fail("V7_CORPUS_PATH_UNSAFE", "Corpus case cannot contain linked or junction entries.")
    return tuple(
        sorted(
            (
                item
                for item in entries
                if item.is_file() and item.suffix.casefold() in {".jpg", ".jpeg"}
            ),
            key=lambda item: (_natural_key(item.name), item.name),
        )
    )


def _directory_fingerprint(directory: Path) -> str:
    files = _direct_jpegs(directory)
    entries = []
    for file_path in files:
        try:
            entries.append(
                {
                    "name": file_path.name,
                    "sha256": _sha256_file(file_path),
                    "sizeBytes": file_path.stat().st_size,
                }
            )
        except OSError as error:
            raise V7SelectionConfigurationError(
                "V7_CORPUS_SOURCE_UNAVAILABLE", "Corpus JPEG cannot be read."
            ) from error
    return _fingerprint({"directory": directory.name, "files": entries})


def _resolve_directory(path: Path, code: str) -> Path:
    if _has_link_or_reparse_ancestor(path):
        _fail("V7_CORPUS_PATH_UNSAFE", "Corpus root cannot be a link or junction.")
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise V7SelectionConfigurationError(code, "Corpus root is unavailable.") from error
    if not resolved.is_dir() or resolved.is_symlink():
        _fail(code, "Corpus root must be a real directory.")
    return resolved


def _has_link_or_reparse_ancestor(path: Path) -> bool:
    """Reject a link or Windows junction in the path before resolving it."""

    try:
        absolute = path.absolute()
    except OSError:
        return True
    return any(_is_link_or_reparse(component) for component in (absolute, *absolute.parents))


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return _has_windows_reparse_attribute(path.lstat())
    except OSError:
        return False


def _has_windows_reparse_attribute(stat_result: object) -> bool:
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return isinstance(attributes, int) and bool(attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT)


def _natural_key(value: str) -> tuple[tuple[int, int | str], ...]:
    return tuple(
        (0, int(part)) if part.isdecimal() else (1, part.casefold())
        for part in re.split(r"(\d+)", value)
        if part
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _fail(code: str, message: str) -> NoReturn:
    raise V7SelectionConfigurationError(code, message)
