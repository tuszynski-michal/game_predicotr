"""Deterministic source-aware splits for reviewed symbol datasets."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

DATASET_VERSION = "labeled-symbol-dataset-v1"
DATASET_SPLIT_VERSION = "source-aware-symbol-dataset-split-v1"
DEFAULT_SPLIT_SEED = "game-predictor-m6-split-v1"
BOOTSTRAP_TARGET_PER_SYMBOL = 100
MINIMUM_SOURCES_PER_SPLIT = 2

SplitName = Literal["train", "validation", "test"]

SPLIT_RATIOS: tuple[tuple[SplitName, float], ...] = (
    ("train", 0.70),
    ("validation", 0.15),
    ("test", 0.15),
)


class SymbolDatasetSplitError(ValueError):
    """Stable failure raised while validating or splitting a symbol dataset."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class _Sample:
    sample_id: str
    crop_checksum: str
    source_checksum: str
    source_id: str
    source_group: str
    source_relative_path: str
    symbol_code: str
    symbol_id: str


@dataclass(frozen=True, slots=True)
class _Source:
    checksum: str
    source_id: str
    source_group: str
    source_relative_path: str
    samples: tuple[_Sample, ...]

    @property
    def symbol_counts(self) -> Counter[str]:
        return Counter(sample.symbol_code for sample in self.samples)


@dataclass(frozen=True, slots=True)
class SymbolDatasetSplitReport:
    """Auditable split assignment and quality evidence."""

    value: Mapping[str, object]

    @property
    def status(self) -> str:
        return str(self.value["status"])

    def to_dict(self) -> dict[str, object]:
        return dict(self.value)

    def to_json_bytes(self) -> bytes:
        return _json_bytes(self.value)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be an object.",
        )
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be an array.",
        )
    return value


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be a non-empty string.",
        )
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be an integer.",
        )
    return value


def _sha256(value: object, label: str) -> str:
    text = _text(value, label)
    if len(text) != 64:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        )
    try:
        int(text, 16)
    except ValueError as error:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_CONTRACT_INVALID",
            f"{label} must be a SHA-256 value.",
        ) from error
    return text.lower()


def _load_dataset(path: Path) -> tuple[bytes, Mapping[str, object]]:
    try:
        content = path.read_bytes()
        value: Any = json.loads(content)
    except (OSError, json.JSONDecodeError) as error:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_INPUT_INVALID",
            "The labeled dataset export cannot be read.",
        ) from error
    return content, _mapping(value, path.name)


def _parse_symbols(dataset: Mapping[str, object]) -> dict[str, str]:
    symbols: dict[str, str] = {}
    symbol_ids: set[str] = set()
    for index, raw_symbol in enumerate(_sequence(dataset.get("symbols"), "symbols")):
        symbol = _mapping(raw_symbol, f"symbols[{index}]")
        code = _text(symbol.get("symbolCode"), f"symbols[{index}].symbolCode")
        symbol_id = _text(symbol.get("symbolId"), f"symbols[{index}].symbolId")
        if code in symbols or symbol_id in symbol_ids:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_SYMBOL_DUPLICATE",
                "The symbol catalog contains a duplicate code or identifier.",
            )
        symbols[code] = symbol_id
        symbol_ids.add(symbol_id)
    if not symbols:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_SYMBOLS_MISSING",
            "The labeled dataset does not contain a symbol catalog.",
        )
    return symbols


def _parse_samples(
    dataset: Mapping[str, object],
    symbols: Mapping[str, str],
) -> tuple[_Sample, ...]:
    samples: list[_Sample] = []
    sample_ids: set[str] = set()
    crop_sources: dict[str, str] = {}
    for index, raw_sample in enumerate(_sequence(dataset.get("samples"), "samples")):
        sample = _mapping(raw_sample, f"samples[{index}]")
        symbol_code = _text(sample.get("symbolCode"), f"samples[{index}].symbolCode")
        symbol_id = _text(sample.get("symbolId"), f"samples[{index}].symbolId")
        if symbols.get(symbol_code) != symbol_id:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_SYMBOL_MISMATCH",
                "A sample does not reference the stable dataset symbol catalog.",
            )
        parsed = _Sample(
            sample_id=_sha256(sample.get("sampleId"), f"samples[{index}].sampleId"),
            crop_checksum=_sha256(
                sample.get("cropChecksumSha256"),
                f"samples[{index}].cropChecksumSha256",
            ),
            source_checksum=_sha256(
                sample.get("sourceImageChecksumSha256"),
                f"samples[{index}].sourceImageChecksumSha256",
            ),
            source_id=_text(
                sample.get("sourceImageId"),
                f"samples[{index}].sourceImageId",
            ),
            source_group=_text(
                sample.get("sourceGroup"),
                f"samples[{index}].sourceGroup",
            ),
            source_relative_path=_text(
                sample.get("sourceImageRelativePath"),
                f"samples[{index}].sourceImageRelativePath",
            ),
            symbol_code=symbol_code,
            symbol_id=symbol_id,
        )
        if parsed.sample_id in sample_ids:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_SAMPLE_DUPLICATE",
                "The labeled dataset contains a duplicate sample identifier.",
            )
        existing_source = crop_sources.setdefault(
            parsed.crop_checksum,
            parsed.source_checksum,
        )
        if existing_source != parsed.source_checksum:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_ASSET_SOURCE_CONFLICT",
                "Identical crop bytes occur in multiple source images.",
            )
        sample_ids.add(parsed.sample_id)
        samples.append(parsed)

    declared_count = _integer(dataset.get("sampleCount"), "sampleCount")
    if declared_count != len(samples) or not samples:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_SAMPLE_COUNT_INVALID",
            "The declared sample count does not match a non-empty sample list.",
        )
    return tuple(samples)


def _group_sources(samples: Sequence[_Sample]) -> tuple[_Source, ...]:
    grouped: dict[str, list[_Sample]] = defaultdict(list)
    identity: dict[str, tuple[str, str, str]] = {}
    for sample in samples:
        current_identity = (
            sample.source_id,
            sample.source_group,
            sample.source_relative_path,
        )
        previous_identity = identity.setdefault(sample.source_checksum, current_identity)
        if previous_identity != current_identity:
            raise SymbolDatasetSplitError(
                "SYMBOL_DATASET_SPLIT_SOURCE_IDENTITY_CONFLICT",
                "One source checksum has conflicting source-image metadata.",
            )
        grouped[sample.source_checksum].append(sample)
    return tuple(
        _Source(
            checksum=checksum,
            source_id=identity[checksum][0],
            source_group=identity[checksum][1],
            source_relative_path=identity[checksum][2],
            samples=tuple(grouped[checksum]),
        )
        for checksum in sorted(grouped)
    )


def _assignment_score(
    assignment: Mapping[str, SplitName],
    sources: Sequence[_Source],
    symbol_codes: Sequence[str],
) -> float:
    total_samples = sum(len(source.samples) for source in sources)
    total_sources = len(sources)
    total_symbols = Counter(
        sample.symbol_code for source in sources for sample in source.samples
    )
    split_samples: Counter[SplitName] = Counter()
    split_sources: Counter[SplitName] = Counter()
    split_symbols: dict[SplitName, Counter[str]] = {
        name: Counter() for name, _ in SPLIT_RATIOS
    }
    for source in sources:
        split = assignment[source.checksum]
        split_samples[split] += len(source.samples)
        split_sources[split] += 1
        split_symbols[split].update(source.symbol_counts)

    score = 0.0
    for split, ratio in SPLIT_RATIOS:
        sample_target = total_samples * ratio
        source_target = total_sources * ratio
        score += ((split_samples[split] - sample_target) / max(sample_target, 1.0)) ** 2
        score += 0.25 * (
            (split_sources[split] - source_target) / max(source_target, 1.0)
        ) ** 2
        for code in symbol_codes:
            symbol_target = total_symbols[code] * ratio
            score += 0.08 * (
                (split_symbols[split][code] - symbol_target)
                / max(symbol_target, 1.0)
            ) ** 2
    return score


def _candidate_assignment(
    sources: Sequence[_Source],
    symbol_codes: Sequence[str],
    seed: str,
    attempt: int,
) -> dict[str, SplitName] | None:
    split_names = tuple(name for name, _ in SPLIT_RATIOS)
    ratios = dict(SPLIT_RATIOS)
    order = sorted(
        sources,
        key=lambda source: hashlib.sha256(
            f"{seed}:{attempt}:{source.checksum}".encode()
        ).hexdigest(),
    )
    assignment: dict[str, SplitName] = {}
    counts: Counter[SplitName] = Counter()
    source_counts: Counter[SplitName] = Counter()
    symbol_counts: dict[SplitName, Counter[str]] = {
        split: Counter() for split in split_names
    }
    total_samples = sum(len(source.samples) for source in sources)
    total_symbols = Counter(
        sample.symbol_code for source in sources for sample in source.samples
    )

    for index, source in enumerate(order):
        remaining_after = len(order) - index - 1
        choices: list[tuple[float, str, SplitName]] = []
        for split in split_names:
            projected_source_counts = source_counts.copy()
            projected_source_counts[split] += 1
            required_sources = sum(
                max(0, MINIMUM_SOURCES_PER_SPLIT - projected_source_counts[name])
                for name in split_names
            )
            if required_sources > remaining_after:
                continue

            projected_count = counts[split] + len(source.samples)
            target_count = total_samples * ratios[split]
            score = ((projected_count - target_count) / max(target_count, 1.0)) ** 2
            target_sources = len(sources) * ratios[split]
            score += 0.25 * (
                (projected_source_counts[split] - target_sources)
                / max(target_sources, 1.0)
            ) ** 2
            source_symbol_counts = source.symbol_counts
            for code in symbol_codes:
                projected_symbol_count = (
                    symbol_counts[split][code] + source_symbol_counts[code]
                )
                target_symbol_count = total_symbols[code] * ratios[split]
                score += 0.08 * (
                    (projected_symbol_count - target_symbol_count)
                    / max(target_symbol_count, 1.0)
                ) ** 2
                if symbol_counts[split][code] == 0 and source_symbol_counts[code] > 0:
                    score -= 0.15
            tie_break = hashlib.sha256(
                f"{seed}:{attempt}:{source.checksum}:{split}".encode()
            ).hexdigest()
            choices.append((score, tie_break, split))

        if not choices:
            return None
        _, _, chosen = min(choices)
        assignment[source.checksum] = chosen
        counts[chosen] += len(source.samples)
        source_counts[chosen] += 1
        symbol_counts[chosen].update(source.symbol_counts)

    if any(source_counts[split] < MINIMUM_SOURCES_PER_SPLIT for split in split_names):
        return None
    if any(
        symbol_counts[split][code] == 0
        for split in split_names
        for code in symbol_codes
    ):
        return None
    return assignment


def _choose_assignment(
    sources: Sequence[_Source],
    symbol_codes: Sequence[str],
    seed: str,
) -> dict[str, SplitName]:
    if len(sources) < MINIMUM_SOURCES_PER_SPLIT * len(SPLIT_RATIOS):
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_SOURCES_INSUFFICIENT",
            "There are too few distinct source images for the required split.",
        )
    candidates: list[tuple[float, str, dict[str, SplitName]]] = []
    attempt_count = max(512, len(sources) * 64)
    for attempt in range(attempt_count):
        assignment = _candidate_assignment(sources, symbol_codes, seed, attempt)
        if assignment is None:
            continue
        signature = "|".join(
            f"{checksum}:{assignment[checksum]}" for checksum in sorted(assignment)
        )
        candidates.append(
            (
                _assignment_score(assignment, sources, symbol_codes),
                signature,
                assignment,
            )
        )
    if not candidates:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_COVERAGE_INSUFFICIENT",
            "No source-disjoint split can cover every symbol in all subsets.",
        )
    return min(candidates, key=lambda item: (item[0], item[1]))[2]


def _build_report_value(
    dataset: Mapping[str, object],
    dataset_sha256: str,
    samples: Sequence[_Sample],
    sources: Sequence[_Source],
    symbols: Mapping[str, str],
    assignment: Mapping[str, SplitName],
    seed: str,
) -> dict[str, object]:
    split_names = tuple(name for name, _ in SPLIT_RATIOS)
    split_samples: dict[SplitName, list[_Sample]] = {
        split: [] for split in split_names
    }
    split_sources: dict[SplitName, list[_Source]] = {
        split: [] for split in split_names
    }
    for source in sources:
        split = assignment[source.checksum]
        split_sources[split].append(source)
    for sample in samples:
        split_samples[assignment[sample.source_checksum]].append(sample)

    symbol_reports: list[dict[str, object]] = []
    all_targets_met = True
    for code in sorted(symbols):
        total_samples = [sample for sample in samples if sample.symbol_code == code]
        target_met = len(total_samples) >= BOOTSTRAP_TARGET_PER_SYMBOL
        all_targets_met = all_targets_met and target_met
        symbol_reports.append(
            {
                "bootstrapTargetMet": target_met,
                "sampleCount": len(total_samples),
                "sourceImageCount": len(
                    {sample.source_checksum for sample in total_samples}
                ),
                "splits": {
                    split: {
                        "sampleCount": sum(
                            sample.symbol_code == code for sample in split_samples[split]
                        ),
                        "sourceImageCount": len(
                            {
                                sample.source_checksum
                                for sample in split_samples[split]
                                if sample.symbol_code == code
                            }
                        ),
                    }
                    for split in split_names
                },
                "symbolCode": code,
                "symbolId": symbols[code],
            }
        )

    split_reports: list[dict[str, object]] = []
    for split in split_names:
        current_samples = split_samples[split]
        current_sources = sorted(split_sources[split], key=lambda source: source.checksum)
        split_reports.append(
            {
                "assetCount": len(
                    {sample.crop_checksum for sample in current_samples}
                ),
                "name": split,
                "ratio": dict(SPLIT_RATIOS)[split],
                "sampleCount": len(current_samples),
                "sampleIds": [sample.sample_id for sample in current_samples],
                "sourceImageCount": len(current_sources),
                "sources": [
                    {
                        "sampleCount": len(source.samples),
                        "sourceGroup": source.source_group,
                        "sourceImageChecksumSha256": source.checksum,
                        "sourceImageId": source.source_id,
                        "sourceImageRelativePath": source.source_relative_path,
                    }
                    for source in current_sources
                ],
            }
        )

    advisories: list[dict[str, object]] = []
    if not all_targets_met:
        advisories.append(
            {
                "code": "SYMBOL_DATASET_BOOTSTRAP_TARGET_NOT_MET",
                "message": (
                    "At least one symbol has fewer than the approximate "
                    f"{BOOTSTRAP_TARGET_PER_SYMBOL} reviewed samples."
                ),
                "symbolCodes": [
                    str(report["symbolCode"])
                    for report in symbol_reports
                    if not report["bootstrapTargetMet"]
                ],
            }
        )

    return {
        "advisories": advisories,
        "bootstrapTargetMet": all_targets_met,
        "bootstrapTargetSamplesPerSymbol": BOOTSTRAP_TARGET_PER_SYMBOL,
        "corpusId": _text(dataset.get("corpusId"), "corpusId"),
        "datasetSha256": dataset_sha256,
        "datasetSplitVersion": DATASET_SPLIT_VERSION,
        "datasetVersion": DATASET_VERSION,
        "gameCode": _text(dataset.get("gameCode"), "gameCode"),
        "gameId": _text(dataset.get("gameId"), "gameId"),
        "qualityGate": {
            "assetLeakageCount": 0,
            "minimumSourcesPerSplit": MINIMUM_SOURCES_PER_SPLIT,
            "missingSymbolsBySplit": {
                split: [] for split in split_names
            },
            "sourceImageLeakageCount": 0,
            "status": "passed",
        },
        "ratios": {name: ratio for name, ratio in SPLIT_RATIOS},
        "sampleCount": len(samples),
        "schemaVersion": 1,
        "seed": seed,
        "sourceImageCount": len(sources),
        "splits": split_reports,
        "status": "ready",
        "symbols": symbol_reports,
    }


def build_symbol_dataset_split(
    dataset_path: Path,
    *,
    seed: str = DEFAULT_SPLIT_SEED,
) -> SymbolDatasetSplitReport:
    """Validate and split an exported symbol dataset by source image."""

    if not seed:
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_SEED_INVALID",
            "The split seed must be a non-empty string.",
        )
    content, dataset = _load_dataset(dataset_path)
    if dataset.get("datasetVersion") != DATASET_VERSION or dataset.get("status") != "ready":
        raise SymbolDatasetSplitError(
            "SYMBOL_DATASET_SPLIT_DATASET_NOT_READY",
            "A ready labeled-symbol-dataset-v1 export is required.",
        )
    symbols = _parse_symbols(dataset)
    samples = _parse_samples(dataset, symbols)
    sources = _group_sources(samples)
    assignment = _choose_assignment(sources, tuple(sorted(symbols)), seed)
    value = _build_report_value(
        dataset,
        hashlib.sha256(content).hexdigest(),
        samples,
        sources,
        symbols,
        assignment,
        seed,
    )
    return SymbolDatasetSplitReport(value=value)
