"""Deterministic datasets built from immutable verified-training cohorts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast

from game_predictor_worker.filesystem import long_path_aware

TRAINING_DATASET_SCHEMA_VERSION = 1
TRAINING_DATASET_VERSION = "verified-symbol-training-dataset-v1"
TRAINING_SPLIT_POLICY_VERSION = "source-family-balanced-split-v2"
DEFAULT_SPLIT_SEED = "game-predictor-m6.6-symbol-split-v1"
MIN_RECOMMENDED_SAMPLES_PER_SYMBOL = 10

SplitName = Literal["train", "validation", "test", "regression"]
SPLIT_ORDER: tuple[SplitName, ...] = ("train", "validation", "test", "regression")
_SAFE_GAME_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TrainingDatasetBuildError(ValueError):
    """Stable failure raised before model training can start."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class TrainingSymbol:
    id: str
    code: str


@dataclass(frozen=True, slots=True)
class TrainingDatasetConfig:
    seed: str = DEFAULT_SPLIT_SEED
    train_basis_points: int = 6500
    validation_basis_points: int = 1500
    test_basis_points: int = 1000
    regression_basis_points: int = 1000
    transformation_version: str = "immutable-reviewed-crop-v1"
    split_policy_version: str = TRAINING_SPLIT_POLICY_VERSION
    # Persisted assignments make the split stable when a later cohort adds sources.
    # The tuple is used instead of a dict so the configuration remains canonical JSON.
    source_assignments: tuple[tuple[str, SplitName], ...] = ()

    def split_ratios(self) -> tuple[tuple[SplitName, int], ...]:
        values: tuple[tuple[SplitName, int], ...] = (
            ("train", self.train_basis_points),
            ("validation", self.validation_basis_points),
            ("test", self.test_basis_points),
            ("regression", self.regression_basis_points),
        )
        if (
            not self.seed
            or not self.transformation_version
            or not self.split_policy_version
            or any(value <= 0 for _, value in values)
            or sum(value for _, value in values) != 10_000
        ):
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_CONFIG_INVALID",
                "The dataset seed, versions, and positive split ratios must be valid.",
            )
        return values

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "splitPolicyVersion": self.split_policy_version,
            "splitRatiosBasisPoints": dict(self.split_ratios()),
            "transformationVersion": self.transformation_version,
            "sourceAssignments": {source: split for source, split in self.source_assignments},
        }


DEFAULT_TRAINING_DATASET_CONFIG = TrainingDatasetConfig()


@dataclass(frozen=True, slots=True)
class TrainingDatasetArtifact:
    game_id: str
    cohort_checksum_sha256: str
    manifest_checksum_sha256: str
    manifest_relative_path: str
    sample_count: int
    source_family_count: int
    reused: bool
    manifest: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _Sample:
    sample_id: str
    crop_checksum: str
    crop_source_path: Path
    asset_relative_path: str
    symbol_id: str
    symbol_code: str
    source_family: str
    source_image_id: str
    source_checksum: str
    source_relative_path: str
    import_job_id: str
    review_item_id: str
    sequence_number: int
    cell_index: int

    def to_dict(self, split: SplitName) -> dict[str, object]:
        return {
            "assetRelativePath": self.asset_relative_path,
            "cellIndex": self.cell_index,
            "cropChecksumSha256": self.crop_checksum,
            "cropSampleId": self.sample_id,
            "importJobId": self.import_job_id,
            "reviewItemId": self.review_item_id,
            "sequenceNumber": self.sequence_number,
            "sourceFamily": self.source_family,
            "sourceImageChecksumSha256": self.source_checksum,
            "sourceImageId": self.source_image_id,
            "sourceImageRelativePath": self.source_relative_path,
            "split": split,
            "symbolCode": self.symbol_code,
            "symbolId": self.symbol_id,
        }


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            f"{label} must be an object.",
        )
    return cast(Mapping[str, object], value)


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            f"{label} must be an array.",
        )
    return cast(Sequence[object], value)


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value.strip()


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if _SHA256.fullmatch(text) is None:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            f"{label} must be a lowercase SHA-256.",
        )
    return text


def _safe_relative_path(value: object, label: str) -> str:
    text = _text(value, label)
    relative = PurePosixPath(text)
    if relative.is_absolute() or ".." in relative.parts or "\\" in text:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_PATH_UNSAFE",
            f"{label} must be a managed relative POSIX path.",
        )
    return relative.as_posix()


def _read_cohort(path: Path, expected_checksum: str) -> Mapping[str, object]:
    if _SHA256.fullmatch(expected_checksum) is None:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_CHECKSUM_INVALID",
            "The expected cohort checksum must be a lowercase SHA-256.",
        )
    try:
        content = path.read_bytes()
    except OSError as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_MISSING",
            "The immutable verified-training cohort cannot be read.",
        ) from error
    if hashlib.sha256(content).hexdigest() != expected_checksum:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_CHECKSUM_MISMATCH",
            "The verified-training cohort differs from its persisted checksum.",
        )
    try:
        value: Any = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_INVALID",
            "The verified-training cohort is not valid UTF-8 JSON.",
        ) from error
    cohort = _mapping(value, "cohort")
    identity = (cohort.get("schemaVersion"), cohort.get("datasetKind"))
    if identity not in {
        (1, "verified-training-cohort-v1"),
        (2, "verified-symbol-cell-training-cohort-v2"),
    }:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_UNSUPPORTED",
            "The verified-training cohort schema is not supported.",
        )
    return cohort


def _catalog(symbols: Sequence[TrainingSymbol]) -> dict[str, str]:
    result: dict[str, str] = {}
    ids: set[str] = set()
    for symbol in sorted(symbols, key=lambda item: (item.code, item.id)):
        if not symbol.code or not symbol.id or symbol.code in result or symbol.id in ids:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_SYMBOL_CATALOG_INVALID",
                "The active game symbol catalog contains missing or duplicate identities.",
            )
        result[symbol.code] = symbol.id
        ids.add(symbol.id)
    if not result:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_SYMBOL_CATALOG_EMPTY",
            "At least one active game symbol is required.",
        )
    return result


def _validate_declared_counts(cohort: Mapping[str, object]) -> None:
    if cohort.get("datasetKind") == "verified-symbol-cell-training-cohort-v2":
        cells = _sequence(cohort.get("cells"), "cells")
        counts = _mapping(cohort.get("counts"), "counts")
        source_ids = {
            _text(_mapping(cell, "cell").get("sourceImageId"), "sourceImageId")
            for cell in cells
        }
        expected = {
            "cellSamples": len(cells),
            "sourceImages": len(source_ids),
        }
        if any(
            _integer(counts.get(key), f"counts.{key}") != value
            for key, value in expected.items()
        ):
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_COHORT_COUNTS_MISMATCH",
                "The cohort manifest counts do not match its immutable cell content.",
            )
        return
    boards = _sequence(cohort.get("boards"), "boards")
    counts = _mapping(cohort.get("counts"), "counts")
    source_ids = {
        _text(_mapping(board, "board").get("sourceImageId"), "sourceImageId") for board in boards
    }
    expected = {
        "resolvedLayouts": len(boards),
        "cellSamples": sum(
            len(_sequence(_mapping(board, "board").get("cells"), "cells")) for board in boards
        ),
        "sourceImages": len(source_ids),
    }
    if any(_integer(counts.get(key), f"counts.{key}") != value for key, value in expected.items()):
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_COHORT_COUNTS_MISMATCH",
            "The cohort manifest counts do not match its immutable board content.",
        )


def _managed_crop(data_root: Path, relative_path: str, checksum: str) -> Path:
    unresolved = data_root.joinpath(*PurePosixPath(relative_path).parts)
    if unresolved.is_symlink():
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_PATH_UNSAFE",
            "A crop cannot be read through a symbolic link.",
        )
    try:
        resolved = unresolved.resolve(strict=True)
    except OSError as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_MISSING",
            f"The immutable crop {relative_path} is unavailable.",
        ) from error
    if not resolved.is_relative_to(data_root) or not resolved.is_file():
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_PATH_UNSAFE",
            "A crop resolves outside managed artifact storage.",
        )
    digest = hashlib.sha256()
    try:
        with resolved.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    except OSError as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_MISSING",
            f"The immutable crop {relative_path} cannot be read.",
        ) from error
    if digest.hexdigest() != checksum:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_CROP_CHECKSUM_MISMATCH",
            f"The immutable crop {relative_path} differs from its cohort checksum.",
        )
    return resolved


def build_balanced_source_assignments(
    sources: Sequence[str],
    *,
    seed: str = DEFAULT_SPLIT_SEED,
    existing: Mapping[str, SplitName] | None = None,
) -> tuple[tuple[str, SplitName], ...]:
    """Build a deterministic, source-disjoint split with independent evaluation sets.

    Existing assignments are never changed. New sources are assigned by a seeded
    hash order to the currently smallest split, which keeps additions stable while
    yielding 4/1/1/1 for the seven-source cohort used by the first training run.
    """
    unique = sorted(set(sources))
    assignments: dict[str, SplitName] = dict(existing or {})
    assignments = {
        source: split
        for source, split in assignments.items()
        if source in unique and split in SPLIT_ORDER
    }
    pending = [source for source in unique if source not in assignments]
    # For a fresh cohort reserve one source for each independent split, then put
    # the remaining sources in train. This is intentionally explicit rather than
    # ratio-based so small cohorts never silently get an empty validation set.
    target_order: tuple[SplitName, ...] = ("validation", "test", "regression")
    fresh_balanced = not assignments and len(pending) >= 4
    if fresh_balanced:
        ranked = sorted(
            pending,
            key=lambda source: hashlib.sha256(f"{seed}\0{source}".encode()).hexdigest(),
        )
        for source, split in zip(ranked[:3], target_order, strict=True):
            assignments[source] = split
        pending = [source for source in pending if source not in assignments]
    counts = Counter(assignments.values())
    for source in sorted(
        pending,
        key=lambda value: hashlib.sha256(f"{seed}\0{value}".encode()).hexdigest(),
    ):
        if fresh_balanced:
            split = "train"
        else:
            split = min(
                SPLIT_ORDER,
                key=lambda candidate: (counts[candidate], SPLIT_ORDER.index(candidate)),
            )
        assignments[source] = split
        counts[split] += 1
    return tuple((source, assignments[source]) for source in unique)


def _source_split(
    source_family: str,
    config: TrainingDatasetConfig,
) -> SplitName:
    for source, split in config.source_assignments:
        if source == source_family:
            return split
    bucket = (
        int.from_bytes(
            hashlib.sha256(
                f"{config.split_policy_version}\0{config.seed}\0{source_family}".encode()
            ).digest(),
            "big",
        )
        % 10_000
    )
    boundary = 0
    for split, ratio in config.split_ratios():
        boundary += ratio
        if bucket < boundary:
            return split
    raise AssertionError("Validated split ratios must cover every hash bucket.")


def _parse_samples(
    cohort: Mapping[str, object],
    *,
    catalog: Mapping[str, str],
    data_root: Path,
) -> tuple[_Sample, ...]:
    if cohort.get("datasetKind") == "verified-symbol-cell-training-cohort-v2":
        return _parse_cell_samples(cohort, catalog=catalog, data_root=data_root)
    samples: list[_Sample] = []
    sample_ids: set[str] = set()
    crop_labels: dict[str, str] = {}
    for board_index, raw_board in enumerate(_sequence(cohort.get("boards"), "boards")):
        board = _mapping(raw_board, f"boards[{board_index}]")
        status = _text(board.get("decisionStatus"), "decisionStatus")
        if status not in {"accepted", "corrected"}:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_DECISION_NOT_VERIFIED",
                "A training cohort board is not an accepted or corrected human decision.",
            )
        source = _mapping(board.get("source"), "source")
        source_checksum = _sha256(source.get("checksumSha256"), "source.checksumSha256")
        source_path = _safe_relative_path(source.get("relativePath"), "source.relativePath")
        source_image_id = _text(board.get("sourceImageId"), "sourceImageId")
        cells = _sequence(board.get("cells"), "cells")
        if len(cells) != 15:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_BOARD_INCOMPLETE",
                "Every verified board must contain exactly 15 human-labeled cells.",
            )
        observed_indexes: set[int] = set()
        for raw_cell in cells:
            cell = _mapping(raw_cell, "cell")
            cell_index = _integer(cell.get("cellIndex"), "cell.cellIndex")
            if cell_index in observed_indexes or not 0 <= cell_index < 15:
                raise TrainingDatasetBuildError(
                    "TRAINING_DATASET_BOARD_INCOMPLETE",
                    "Verified board cells must be unique row-major indexes 0..14.",
                )
            observed_indexes.add(cell_index)
            symbol_code = _text(cell.get("symbolCode"), "cell.symbolCode")
            symbol_id = catalog.get(symbol_code)
            if symbol_id is None:
                raise TrainingDatasetBuildError(
                    "TRAINING_DATASET_SYMBOL_UNKNOWN",
                    f"Human label {symbol_code!r} is absent from the active symbol catalog.",
                )
            crop_checksum = _sha256(
                cell.get("cropChecksumSha256"),
                "cell.cropChecksumSha256",
            )
            previous_label = crop_labels.setdefault(crop_checksum, symbol_code)
            if previous_label != symbol_code:
                raise TrainingDatasetBuildError(
                    "TRAINING_DATASET_CROP_LABEL_CONFLICT",
                    "Identical crop bytes have conflicting human labels.",
                )
            crop_relative_path = _safe_relative_path(
                cell.get("cropRelativePath"),
                "cell.cropRelativePath",
            )
            crop_path = _managed_crop(data_root, crop_relative_path, crop_checksum)
            sample_id = _sha256(cell.get("cropSampleId"), "cell.cropSampleId")
            if sample_id in sample_ids:
                raise TrainingDatasetBuildError(
                    "TRAINING_DATASET_SAMPLE_DUPLICATE",
                    "The cohort contains a duplicate crop sample identity.",
                )
            sample_ids.add(sample_id)
            samples.append(
                _Sample(
                    sample_id=sample_id,
                    crop_checksum=crop_checksum,
                    crop_source_path=crop_path,
                    asset_relative_path=PurePosixPath(
                        "assets", crop_checksum[:2], f"{crop_checksum}.png"
                    ).as_posix(),
                    symbol_id=symbol_id,
                    symbol_code=symbol_code,
                    source_family=source_checksum,
                    source_image_id=source_image_id,
                    source_checksum=source_checksum,
                    source_relative_path=source_path,
                    import_job_id=_text(board.get("importJobId"), "importJobId"),
                    review_item_id=_text(board.get("reviewItemId"), "reviewItemId"),
                    sequence_number=_integer(board.get("sequenceNumber"), "sequenceNumber"),
                    cell_index=cell_index,
                )
            )
        if observed_indexes != set(range(15)):
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_BOARD_INCOMPLETE",
                "Verified board cells must cover row-major indexes 0..14.",
            )
    if not samples:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_EMPTY",
            "The frozen cohort does not contain training samples.",
        )
    return tuple(
        sorted(
            samples,
            key=lambda item: (
                item.source_family,
                item.sequence_number,
                item.review_item_id,
                item.cell_index,
                item.sample_id,
            ),
        )
    )


def _parse_cell_samples(
    cohort: Mapping[str, object],
    *,
    catalog: Mapping[str, str],
    data_root: Path,
) -> tuple[_Sample, ...]:
    samples: list[_Sample] = []
    sample_ids: set[str] = set()
    crop_labels: dict[str, str] = {}
    for index, raw_cell in enumerate(_sequence(cohort.get("cells"), "cells")):
        cell = _mapping(raw_cell, f"cells[{index}]")
        symbol_code = _text(cell.get("symbolCode"), "cell.symbolCode")
        symbol_id = catalog.get(symbol_code)
        if symbol_id is None:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_SYMBOL_UNKNOWN",
                f"Human label {symbol_code!r} is absent from the active symbol catalog.",
            )
        cell_index = _integer(cell.get("cellIndex"), "cell.cellIndex")
        if not 0 <= cell_index < 15:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_CELL_POSITION_INVALID",
                "A verified symbol cell must use a row-major index from 0 to 14.",
            )
        crop_checksum = _sha256(
            cell.get("cropChecksumSha256"), "cell.cropChecksumSha256"
        )
        previous_label = crop_labels.setdefault(crop_checksum, symbol_code)
        if previous_label != symbol_code:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_CROP_LABEL_CONFLICT",
                "Identical crop bytes have conflicting human labels.",
            )
        crop_relative_path = _safe_relative_path(
            cell.get("cropRelativePath"), "cell.cropRelativePath"
        )
        sample_id = _sha256(cell.get("cropSampleId"), "cell.cropSampleId")
        if sample_id in sample_ids:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_SAMPLE_DUPLICATE",
                "The cohort contains a duplicate crop sample identity.",
            )
        sample_ids.add(sample_id)
        source = _mapping(cell.get("source"), "cell.source")
        source_checksum = _sha256(
            source.get("checksumSha256"), "cell.source.checksumSha256"
        )
        source_path = _safe_relative_path(
            source.get("relativePath"), "cell.source.relativePath"
        )
        samples.append(
            _Sample(
                sample_id=sample_id,
                crop_checksum=crop_checksum,
                crop_source_path=_managed_crop(
                    data_root, crop_relative_path, crop_checksum
                ),
                asset_relative_path=PurePosixPath(
                    "assets", crop_checksum[:2], f"{crop_checksum}.png"
                ).as_posix(),
                symbol_id=symbol_id,
                symbol_code=symbol_code,
                source_family=source_checksum,
                source_image_id=_text(cell.get("sourceImageId"), "cell.sourceImageId"),
                source_checksum=source_checksum,
                source_relative_path=source_path,
                import_job_id=_text(cell.get("importJobId"), "cell.importJobId"),
                review_item_id=_text(cell.get("reviewItemId"), "cell.reviewItemId"),
                sequence_number=_integer(
                    cell.get("sequenceNumber"), "cell.sequenceNumber"
                ),
                cell_index=cell_index,
            )
        )
    if not samples:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_EMPTY",
            "The frozen cohort does not contain training samples.",
        )
    return tuple(
        sorted(
            samples,
            key=lambda item: (
                item.source_family,
                item.sequence_number,
                item.review_item_id,
                item.cell_index,
                item.sample_id,
            ),
        )
    )


def _manifest(
    *,
    cohort: Mapping[str, object],
    cohort_checksum: str,
    game_code: str,
    catalog: Mapping[str, str],
    samples: Sequence[_Sample],
    config: TrainingDatasetConfig,
) -> dict[str, object]:
    split_by_source = {
        source: _source_split(source, config)
        for source in sorted({sample.source_family for sample in samples})
    }
    split_samples: dict[SplitName, list[_Sample]] = {split: [] for split in SPLIT_ORDER}
    for sample in samples:
        split_samples[split_by_source[sample.source_family]].append(sample)

    symbol_stats: list[dict[str, object]] = []
    advisories: list[dict[str, object]] = []
    for code in sorted(catalog):
        current = [sample for sample in samples if sample.symbol_code == code]
        split_counts = {
            split: sum(sample.symbol_code == code for sample in split_samples[split])
            for split in SPLIT_ORDER
        }
        source_count = len({sample.source_family for sample in current})
        symbol_stats.append(
            {
                "sampleCount": len(current),
                "sourceFamilyCount": source_count,
                "splitSampleCounts": split_counts,
                "symbolCode": code,
                "symbolId": catalog[code],
            }
        )
        if len(current) < MIN_RECOMMENDED_SAMPLES_PER_SYMBOL:
            advisories.append(
                {
                    "code": "TRAINING_DATASET_SYMBOL_UNDERREPRESENTED",
                    "sampleCount": len(current),
                    "symbolCode": code,
                }
            )
        missing_splits = [split for split, count in split_counts.items() if count == 0]
        if current and missing_splits:
            advisories.append(
                {
                    "code": "TRAINING_DATASET_SYMBOL_SPLIT_COVERAGE_LOW",
                    "missingSplits": missing_splits,
                    "symbolCode": code,
                }
            )

    split_reports: list[dict[str, object]] = []
    for split in SPLIT_ORDER:
        current = split_samples[split]
        sources = sorted({sample.source_family for sample in current})
        split_reports.append(
            {
                "assetCount": len({sample.crop_checksum for sample in current}),
                "name": split,
                "sampleCount": len(current),
                "sourceFamilies": sources,
                "sourceFamilyCount": len(sources),
            }
        )

    review_state = _sequence(cohort.get("reviewState", ()), "reviewState")
    exclusions: Counter[str] = Counter()
    for raw_item in review_state:
        item = _mapping(raw_item, "reviewState item")
        if item.get("included") is False:
            reason = item.get("exclusionReason")
            exclusions[str(reason) if reason is not None else "unknown"] += 1

    game_id = _text(cohort.get("gameId"), "gameId")
    asset_paths = {
        sample.sample_id: _asset_relative_path(sample, config) for sample in samples
    }
    sample_rows = []
    for sample in samples:
        row = sample.to_dict(split_by_source[sample.source_family])
        row["assetRelativePath"] = asset_paths[sample.sample_id]
        sample_rows.append(row)
    return {
        "advisories": advisories,
        "artifactBaseRelativePath": PurePosixPath(
            "training", game_code, cohort_checksum
        ).as_posix(),
        "catalog": [{"symbolCode": code, "symbolId": catalog[code]} for code in sorted(catalog)],
        "cohortChecksumSha256": cohort_checksum,
        "configuration": config.to_dict(),
        "datasetVersion": TRAINING_DATASET_VERSION,
        "exclusions": [
            {"count": count, "reason": reason} for reason, count in sorted(exclusions.items())
        ],
        "gameCode": game_code,
        "gameId": game_id,
        "qualityGate": {
            "regressionSamplesInTrain": 0,
            "sourceFamilyLeakageCount": 0,
            "status": "passed",
        },
        "sampleCount": len(samples),
        "samples": sample_rows,
        "schemaVersion": TRAINING_DATASET_SCHEMA_VERSION,
        "sourceFamilyCount": len(split_by_source),
        "splits": split_reports,
        "status": "ready",
        "symbols": symbol_stats,
}


def _asset_relative_path(sample: _Sample, config: TrainingDatasetConfig) -> str:
    """Keep assets from incompatible dataset policies physically separate."""
    if config.split_policy_version == "source-family-balanced-split-v2":
        fingerprint = hashlib.sha256(_canonical_bytes(config.to_dict())).hexdigest()[:16]
        return PurePosixPath(
            "assets", f"{config.split_policy_version}-{fingerprint}", sample.crop_checksum[:2],
            f"{sample.crop_checksum}.png",
        ).as_posix()
    return sample.asset_relative_path


def _copy_asset(source: Path, destination: Path) -> None:
    filesystem_source = long_path_aware(source)
    filesystem_destination = long_path_aware(destination)
    filesystem_destination.parent.mkdir(parents=True, exist_ok=True)
    if filesystem_destination.exists():
        if hashlib.sha256(filesystem_destination.read_bytes()).hexdigest() != source.stem:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_ASSET_COLLISION",
                "An existing content-addressed asset has different bytes.",
            )
        return
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=filesystem_destination.parent,
            prefix=".tmp-",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        assert temporary is not None
        shutil.copyfile(filesystem_source, temporary)
        os.replace(temporary, filesystem_destination)
        temporary = None
    except OSError as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_WRITE_FAILED",
            "A training dataset asset could not be written.",
        ) from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _verify_existing(
    artifact_directory: Path,
    manifest_path: Path,
    manifest_bytes: bytes,
    samples: Sequence[_Sample],
    config: TrainingDatasetConfig,
    progress_callback: Callable[[int, int], None] | None = None,
) -> None:
    try:
        if manifest_path.read_bytes() != manifest_bytes:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_ARTIFACT_COLLISION",
                "An existing dataset directory contains another manifest.",
            )
    except OSError as error:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_ARTIFACT_INCOMPLETE",
            "An existing dataset artifact is incomplete.",
        ) from error
    unique_samples = {sample.crop_checksum: sample for sample in samples}
    total = len(unique_samples)
    for current, sample in enumerate(unique_samples.values(), start=1):
        asset = artifact_directory.joinpath(
            *PurePosixPath(_asset_relative_path(sample, config)).parts
        )
        try:
            observed = hashlib.sha256(long_path_aware(asset).read_bytes()).hexdigest()
        except OSError as error:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_ARTIFACT_INCOMPLETE",
                "An existing dataset artifact is missing an immutable crop.",
            ) from error
        if observed != sample.crop_checksum:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_ARTIFACT_CHANGED",
                "An existing dataset crop checksum changed.",
            )
        if progress_callback is not None:
            progress_callback(current, total)


def build_cumulative_training_dataset(
    *,
    cohort_path: Path,
    expected_cohort_checksum_sha256: str,
    artifact_root: Path,
    game_code: str,
    symbols: Sequence[TrainingSymbol],
    expected_game_id: str | None = None,
    config: TrainingDatasetConfig = DEFAULT_TRAINING_DATASET_CONFIG,
    progress_callback: Callable[[int, int], None] | None = None,
) -> TrainingDatasetArtifact:
    """Validate one immutable cohort and materialize a source-disjoint dataset."""

    config.split_ratios()
    if _SAFE_GAME_CODE.fullmatch(game_code) is None:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_GAME_CODE_INVALID",
            "The game code cannot be used in managed artifact storage.",
        )
    managed_root = artifact_root.resolve()
    data_root = managed_root / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    cohort = _read_cohort(cohort_path, expected_cohort_checksum_sha256)
    cohort_game_id = _text(cohort.get("gameId"), "gameId")
    if expected_game_id is not None and cohort_game_id != expected_game_id:
        raise TrainingDatasetBuildError(
            "TRAINING_DATASET_GAME_MISMATCH",
            "The persisted cohort manifest belongs to another game.",
        )
    _validate_declared_counts(cohort)
    catalog = _catalog(symbols)
    samples = _parse_samples(cohort, catalog=catalog, data_root=data_root)
    manifest = _manifest(
        cohort=cohort,
        cohort_checksum=expected_cohort_checksum_sha256,
        game_code=game_code,
        catalog=catalog,
        samples=samples,
        config=config,
    )
    manifest_bytes = _canonical_bytes(manifest)
    manifest_checksum = hashlib.sha256(manifest_bytes).hexdigest()
    relative_directory = PurePosixPath(
        "training",
        game_code,
        expected_cohort_checksum_sha256,
    )
    artifact_directory = data_root.joinpath(*relative_directory.parts)
    manifest_relative_path = relative_directory / "manifests" / f"{manifest_checksum}.json"
    manifest_path = data_root.joinpath(*manifest_relative_path.parts)
    reused = manifest_path.exists()
    if reused:
        _verify_existing(
            artifact_directory,
            manifest_path,
            manifest_bytes,
            samples,
            config,
            progress_callback,
        )
    else:
        artifact_directory.mkdir(parents=True, exist_ok=True)
        temporary_manifest: Path | None = None
        try:
            copied: set[str] = set()
            total_assets = len({sample.crop_checksum for sample in samples})
            for sample in samples:
                if sample.crop_checksum in copied:
                    continue
                copied.add(sample.crop_checksum)
                _copy_asset(
                    sample.crop_source_path,
                    artifact_directory.joinpath(
                        *PurePosixPath(_asset_relative_path(sample, config)).parts
                    ),
                )
                if progress_callback is not None:
                    progress_callback(len(copied), total_assets)
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=manifest_path.parent,
                prefix=".tmp-",
                delete=False,
            ) as handle:
                temporary_manifest = Path(handle.name)
                handle.write(manifest_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_manifest, manifest_path)
            temporary_manifest = None
            _verify_existing(
                artifact_directory,
                manifest_path,
                manifest_bytes,
                samples,
                config,
                progress_callback,
            )
        except TrainingDatasetBuildError:
            raise
        except OSError as error:
            raise TrainingDatasetBuildError(
                "TRAINING_DATASET_WRITE_FAILED",
                "The content-addressed training dataset could not be committed.",
            ) from error
        finally:
            if temporary_manifest is not None:
                temporary_manifest.unlink(missing_ok=True)

    return TrainingDatasetArtifact(
        game_id=cohort_game_id,
        cohort_checksum_sha256=expected_cohort_checksum_sha256,
        manifest_checksum_sha256=manifest_checksum,
        manifest_relative_path=manifest_relative_path.as_posix(),
        sample_count=len(samples),
        source_family_count=len({sample.source_family for sample in samples}),
        reused=reused,
        manifest=manifest,
    )


__all__ = [
    "DEFAULT_TRAINING_DATASET_CONFIG",
    "TRAINING_DATASET_SCHEMA_VERSION",
    "TRAINING_DATASET_VERSION",
    "TRAINING_SPLIT_POLICY_VERSION",
    "build_balanced_source_assignments",
    "TrainingDatasetArtifact",
    "TrainingDatasetBuildError",
    "TrainingDatasetConfig",
    "TrainingSymbol",
    "build_cumulative_training_dataset",
]
