"""Bounded-memory generation and validation of the M3.5 benchmark dataset."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Callable, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast
from uuid import UUID

from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus

from game_predictor_worker.domain import (
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
    encode_signature,
    evaluate_payout,
)
from game_predictor_worker.payouts.readiness import (
    SUPPORTED_PAYOUT_ALGORITHM,
    PayoutCompletenessFacts,
)
from game_predictor_worker.snapshots import (
    ProductionSnapshotArtifactPublisher,
    ProductionSnapshotGenerator,
    ProductionSnapshotSpec,
    SnapshotArtifact,
    SnapshotGameSelection,
    SnapshotGameSource,
    SnapshotLayout,
    SnapshotSymbol,
    validate_snapshot_artifact,
)

BENCHMARK_MANIFEST_VERSION: Final = 1
BENCHMARK_GENERATOR_VERSION: Final = "m35-benchmark-v1"
BENCHMARK_RELEASE_VERSION: Final = "m35-benchmark.1"
BENCHMARK_CREATED_AT: Final = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
BENCHMARK_MANIFEST_FILE: Final = "benchmark-manifest.json"
BENCHMARK_GAME_ID: Final = UUID("35000000-0000-0000-0000-000000000001")
BENCHMARK_DATASET_VERSION_ID: Final = UUID("35000000-0000-0000-0000-000000000002")
BENCHMARK_RULES_VERSION_ID: Final = UUID("35000000-0000-0000-0000-000000000003")
BENCHMARK_DATASET_VERSION: Final = 1
BENCHMARK_RULES_VERSION: Final = 1
DEFAULT_BENCHMARK_LAYOUT_COUNT: Final = 500_000
DEFAULT_BENCHMARK_BATCH_SIZE: Final = 1_000
DEFAULT_BENCHMARK_SEED: Final = 350_027
DEFAULT_DUPLICATE_GROUP_COUNT: Final = 6
BENCHMARK_ROWS: Final = 3
BENCHMARK_COLUMNS: Final = 5
BENCHMARK_SPIN_COST: Final = 10
BENCHMARK_SIGNATURE_CELL_WIDTH: Final = 2
BENCHMARK_SYMBOL_COUNT: Final = 11

ProgressCallback = Callable[["BenchmarkProgress"], None]


class BenchmarkDatasetError(RuntimeError):
    """Stable failure raised by benchmark generation or verification."""


@dataclass(frozen=True, slots=True)
class BenchmarkProgress:
    phase: str
    processed_layout_count: int
    total_layout_count: int


@dataclass(frozen=True, slots=True)
class BenchmarkDatasetSpec:
    layout_count: int = DEFAULT_BENCHMARK_LAYOUT_COUNT
    seed: int = DEFAULT_BENCHMARK_SEED
    batch_size: int = DEFAULT_BENCHMARK_BATCH_SIZE
    duplicate_group_count: int = DEFAULT_DUPLICATE_GROUP_COUNT

    def __post_init__(self) -> None:
        if type(self.layout_count) is not int or self.layout_count < 2:
            raise ValueError("layout_count must be an integer greater than one.")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("seed must be a non-negative integer.")
        if type(self.batch_size) is not int or self.batch_size < 1:
            raise ValueError("batch_size must be a positive integer.")
        if (
            type(self.duplicate_group_count) is not int
            or self.duplicate_group_count < 5
            or self.duplicate_group_count > 10
        ):
            raise ValueError("duplicate_group_count must be between 5 and 10.")
        if self.layout_count < self.duplicate_group_count * 2:
            raise ValueError("layout_count must leave one unique source per duplicate group.")

    @property
    def duplicate_source_sequences(self) -> tuple[int, ...]:
        unique_count = self.layout_count - self.duplicate_group_count
        return tuple(
            (index * unique_count) // (self.duplicate_group_count + 1)
            for index in range(1, self.duplicate_group_count + 1)
        )

    @property
    def duplicate_destination_sequences(self) -> tuple[int, ...]:
        first_destination = self.layout_count - self.duplicate_group_count + 1
        return tuple(range(first_destination, self.layout_count + 1))

    @property
    def duplicate_pairs(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            zip(
                self.duplicate_source_sequences,
                self.duplicate_destination_sequences,
                strict=True,
            )
        )


@dataclass(frozen=True, slots=True)
class BenchmarkDatasetResult:
    output_directory: Path
    manifest_path: Path
    artifact: SnapshotArtifact


@dataclass(frozen=True, slots=True)
class BenchmarkDatasetValidationReport:
    layout_count: int
    duplicate_group_count: int
    logical_content_sha256: str
    snapshot_file_sha256: str
    snapshot_size_bytes: int
    maximum_validation_batch_size: int


def _symbols() -> tuple[SymbolDefinition, ...]:
    return tuple(
        SymbolDefinition(
            mobile_code=mobile_code,
            code="JOKER" if mobile_code == BENCHMARK_SYMBOL_COUNT else f"S{mobile_code:02d}",
            name=(
                "Joker" if mobile_code == BENCHMARK_SYMBOL_COUNT else f"Symbol {mobile_code:02d}"
            ),
            is_wildcard=mobile_code == BENCHMARK_SYMBOL_COUNT,
            display_order=mobile_code - 1,
        )
        for mobile_code in range(1, BENCHMARK_SYMBOL_COUNT + 1)
    )


def _game() -> GameConfig:
    return GameConfig(
        id=str(BENCHMARK_GAME_ID),
        code="m35-benchmark-game",
        name="M3.5 Benchmark Game",
        rows=BENCHMARK_ROWS,
        columns=BENCHMARK_COLUMNS,
        spin_cost=BENCHMARK_SPIN_COST,
        signature_cell_width=BENCHMARK_SIGNATURE_CELL_WIDTH,
        symbols=_symbols(),
    )


def _paylines() -> tuple[PaylineDefinition, ...]:
    return (
        PaylineDefinition(id="top", row_path=(0, 0, 0, 0, 0)),
        PaylineDefinition(id="middle", row_path=(1, 1, 1, 1, 1)),
        PaylineDefinition(id="bottom", row_path=(2, 2, 2, 2, 2)),
        PaylineDefinition(id="down-v", row_path=(0, 1, 2, 1, 0)),
        PaylineDefinition(id="up-v", row_path=(2, 1, 0, 1, 2)),
    )


def _payout_symbols() -> tuple[PayoutSymbolDefinition, ...]:
    return tuple(
        PayoutSymbolDefinition(
            symbol_mobile_code=mobile_code,
            minimum_match_length=2 if mobile_code <= 2 else 3,
        )
        for mobile_code in range(1, BENCHMARK_SYMBOL_COUNT)
    )


def _payout_rules() -> tuple[PayoutRuleDefinition, ...]:
    rules: list[PayoutRuleDefinition] = []
    for payout_symbol in _payout_symbols():
        base_payout = 50 + payout_symbol.symbol_mobile_code * 50
        for match_length in range(
            payout_symbol.minimum_match_length,
            BENCHMARK_COLUMNS + 1,
        ):
            payout_credits = (
                max(1, base_payout // 3)
                if match_length == 2
                else base_payout * 3 ** (match_length - 3)
            )
            rules.append(
                PayoutRuleDefinition(
                    symbol_mobile_code=payout_symbol.symbol_mobile_code,
                    match_length=match_length,
                    payout_credits=payout_credits,
                )
            )
    return tuple(rules)


def _derived_integer(seed: int, label: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{BENCHMARK_GENERATOR_VERSION}:{seed}:{label}".encode()).digest()
    return int.from_bytes(digest, "big") % modulus


@lru_cache(maxsize=32)
def _affine_parameters(seed: int) -> tuple[int, int, int]:
    modulus = BENCHMARK_SYMBOL_COUNT ** (BENCHMARK_ROWS * BENCHMARK_COLUMNS)
    multiplier = _derived_integer(seed, "multiplier", modulus)
    if multiplier == 0:
        multiplier = 1
    while math.gcd(multiplier, modulus) != 1:
        multiplier = (multiplier + 1) % modulus
        if multiplier == 0:
            multiplier = 1
    offset = _derived_integer(seed, "offset", modulus)
    return multiplier, offset, modulus


@lru_cache(maxsize=32)
def _duplicate_sources_by_destination(
    spec: BenchmarkDatasetSpec,
) -> dict[int, int]:
    return dict(
        zip(
            spec.duplicate_destination_sequences,
            spec.duplicate_source_sequences,
            strict=True,
        )
    )


def _logical_sequence_number(sequence_number: int, spec: BenchmarkDatasetSpec) -> int:
    return _duplicate_sources_by_destination(spec).get(
        sequence_number,
        sequence_number,
    )


def benchmark_cells(
    sequence_number: int,
    spec: BenchmarkDatasetSpec,
) -> tuple[int, ...]:
    """Return one deterministic row-major board without shared mutable state."""

    if sequence_number < 1 or sequence_number > spec.layout_count:
        raise ValueError("sequence_number is outside the benchmark dataset.")
    logical_sequence_number = _logical_sequence_number(sequence_number, spec)
    multiplier, offset, modulus = _affine_parameters(spec.seed)
    encoded = (multiplier * (logical_sequence_number - 1) + offset) % modulus
    cells: list[int] = []
    for _ in range(BENCHMARK_ROWS * BENCHMARK_COLUMNS):
        encoded, digit = divmod(encoded, BENCHMARK_SYMBOL_COUNT)
        cells.append(digit + 1)
    return tuple(cells)


class BenchmarkSnapshotRepository:
    """Generated-on-demand production snapshot source with bounded batches."""

    def __init__(
        self,
        spec: BenchmarkDatasetSpec,
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.spec = spec
        self.game = _game()
        self.paylines = _paylines()
        self.payout_symbols = _payout_symbols()
        self.payout_rules = _payout_rules()
        self.selection = SnapshotGameSelection(
            BENCHMARK_DATASET_VERSION_ID,
            BENCHMARK_RULES_VERSION_ID,
            SUPPORTED_PAYOUT_ALGORITHM,
        )
        self.maximum_generated_batch_size = 0
        self._progress = progress

    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None:
        if (
            dataset_version_id != self.selection.dataset_version_id
            or rules_version_id != self.selection.rules_version_id
            or algorithm_version != self.selection.algorithm_version
        ):
            return None
        return PayoutCompletenessFacts(
            dataset_version_id=dataset_version_id,
            rules_version_id=rules_version_id,
            algorithm_version=algorithm_version,
            dataset_game_id=BENCHMARK_GAME_ID,
            rules_game_id=BENCHMARK_GAME_ID,
            dataset_status=DatasetVersionStatus.PUBLISHED,
            rules_status=RulesVersionStatus.PUBLISHED,
            dataset_rows=BENCHMARK_ROWS,
            dataset_columns=BENCHMARK_COLUMNS,
            rules_rows=BENCHMARK_ROWS,
            rules_columns=BENCHMARK_COLUMNS,
            layout_count=self.spec.layout_count,
            payout_count=self.spec.layout_count,
            missing_payout_count=0,
            missing_sequence_numbers=(),
            missing_sequences_truncated=False,
            missing_audit_count=0,
        )

    def load_snapshot_game(
        self,
        selection: SnapshotGameSelection,
    ) -> SnapshotGameSource | None:
        if selection != self.selection:
            return None
        return SnapshotGameSource(
            game_id=BENCHMARK_GAME_ID,
            game_code=self.game.code,
            game_name=self.game.name,
            dataset_version_id=BENCHMARK_DATASET_VERSION_ID,
            dataset_version=BENCHMARK_DATASET_VERSION,
            rules_version_id=BENCHMARK_RULES_VERSION_ID,
            rules_version=BENCHMARK_RULES_VERSION,
            algorithm_version=SUPPORTED_PAYOUT_ALGORITHM,
            rows=BENCHMARK_ROWS,
            columns=BENCHMARK_COLUMNS,
            spin_cost=BENCHMARK_SPIN_COST,
            signature_cell_width=BENCHMARK_SIGNATURE_CELL_WIDTH,
            layout_count=self.spec.layout_count,
            symbols=tuple(
                SnapshotSymbol(
                    mobile_code=symbol.mobile_code,
                    code=symbol.code,
                    name=symbol.name,
                    is_wildcard=symbol.is_wildcard,
                    display_order=symbol.display_order,
                    image_asset_key=None,
                )
                for symbol in self.game.symbols
            ),
        )

    def list_snapshot_layout_batch(
        self,
        selection: SnapshotGameSelection,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[SnapshotLayout]:
        if selection != self.selection:
            return ()
        last_sequence_number = min(
            self.spec.layout_count,
            after_sequence_number + limit,
        )
        layouts = tuple(
            self._layout(sequence_number)
            for sequence_number in range(
                after_sequence_number + 1,
                last_sequence_number + 1,
            )
        )
        self.maximum_generated_batch_size = max(
            self.maximum_generated_batch_size,
            len(layouts),
        )
        if self._progress is not None and layouts:
            self._progress(
                BenchmarkProgress(
                    phase="generate",
                    processed_layout_count=layouts[-1].sequence_number,
                    total_layout_count=self.spec.layout_count,
                )
            )
        return layouts

    def _layout(self, sequence_number: int) -> SnapshotLayout:
        cells = benchmark_cells(sequence_number, self.spec)
        return SnapshotLayout(
            sequence_number=sequence_number,
            signature=encode_signature(cells, BENCHMARK_SIGNATURE_CELL_WIDTH),
            payout=evaluate_payout(
                self.game,
                cells,
                self.paylines,
                self.payout_symbols,
                self.payout_rules,
            ).total_payout,
        )


def _game_manifest(repository: BenchmarkSnapshotRepository) -> dict[str, object]:
    return {
        "algorithmVersion": SUPPORTED_PAYOUT_ALGORITHM,
        "columns": BENCHMARK_COLUMNS,
        "datasetVersion": BENCHMARK_DATASET_VERSION,
        "datasetVersionId": str(BENCHMARK_DATASET_VERSION_ID),
        "gameCode": repository.game.code,
        "gameId": str(BENCHMARK_GAME_ID),
        "paylines": [
            {"id": payline.id, "rowPath": list(payline.row_path)} for payline in repository.paylines
        ],
        "payoutRules": [
            {
                "matchLength": rule.match_length,
                "payoutCredits": rule.payout_credits,
                "symbolMobileCode": rule.symbol_mobile_code,
            }
            for rule in repository.payout_rules
        ],
        "payoutSymbols": [
            {
                "minimumMatchLength": symbol.minimum_match_length,
                "symbolMobileCode": symbol.symbol_mobile_code,
            }
            for symbol in repository.payout_symbols
        ],
        "rows": BENCHMARK_ROWS,
        "rulesVersion": BENCHMARK_RULES_VERSION,
        "rulesVersionId": str(BENCHMARK_RULES_VERSION_ID),
        "signatureCellWidth": BENCHMARK_SIGNATURE_CELL_WIDTH,
        "spinCost": BENCHMARK_SPIN_COST,
        "symbols": [
            {
                "code": symbol.code,
                "displayOrder": symbol.display_order,
                "isWildcard": symbol.is_wildcard,
                "mobileCode": symbol.mobile_code,
                "name": symbol.name,
            }
            for symbol in repository.game.symbols
        ],
    }


def _benchmark_manifest(
    spec: BenchmarkDatasetSpec,
    repository: BenchmarkSnapshotRepository,
    artifact: SnapshotArtifact,
    output_directory: Path,
) -> dict[str, object]:
    duplicate_groups = []
    for source, destination in spec.duplicate_pairs:
        duplicate_groups.append(
            {
                "sequenceNumbers": [source, destination],
                "signature": encode_signature(
                    benchmark_cells(source, spec),
                    BENCHMARK_SIGNATURE_CELL_WIDTH,
                ),
            }
        )
    return {
        "artifact": {
            "relativeDirectory": artifact.directory.relative_to(
                output_directory.resolve()
            ).as_posix(),
            "snapshotFileSha256": artifact.manifest.snapshot_file_sha256,
            "snapshotSizeBytes": artifact.database_path.stat().st_size,
        },
        "batchSize": spec.batch_size,
        "createdAt": BENCHMARK_CREATED_AT.isoformat().replace("+00:00", "Z"),
        "duplicateGroups": duplicate_groups,
        "game": _game_manifest(repository),
        "generatorVersion": BENCHMARK_GENERATOR_VERSION,
        "layoutCount": spec.layout_count,
        "logicalContentSha256": artifact.manifest.logical_content_sha256,
        "manifestVersion": BENCHMARK_MANIFEST_VERSION,
        "releaseVersion": BENCHMARK_RELEASE_VERSION,
        "seed": spec.seed,
    }


def _canonical_json(value: dict[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def generate_benchmark_dataset(
    output_directory: Path,
    spec: BenchmarkDatasetSpec | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> BenchmarkDatasetResult:
    """Generate and immutably publish a production-shaped benchmark snapshot."""

    if spec is None:
        spec = BenchmarkDatasetSpec()
    resolved_output = output_directory.resolve()
    repository = BenchmarkSnapshotRepository(spec, progress=progress)
    generator = ProductionSnapshotGenerator(
        repository,
        batch_size=spec.batch_size,
    )
    artifact = ProductionSnapshotArtifactPublisher(
        generator,
        resolved_output,
    ).publish(
        ProductionSnapshotSpec(
            release_version=BENCHMARK_RELEASE_VERSION,
            created_at=BENCHMARK_CREATED_AT,
            games=(repository.selection,),
        )
    )
    manifest = _benchmark_manifest(
        spec,
        repository,
        artifact,
        resolved_output,
    )
    manifest_path = resolved_output / BENCHMARK_MANIFEST_FILE
    manifest_bytes = _canonical_json(manifest)
    if manifest_path.exists():
        if manifest_path.read_bytes() != manifest_bytes:
            raise BenchmarkDatasetError("An existing benchmark manifest has different content.")
    else:
        try:
            with manifest_path.open("xb") as file:
                file.write(manifest_bytes)
        except OSError as error:
            raise BenchmarkDatasetError("The benchmark manifest could not be written.") from error
    return BenchmarkDatasetResult(
        output_directory=resolved_output,
        manifest_path=manifest_path,
        artifact=artifact,
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BenchmarkDatasetError(
            "The benchmark manifest is not readable canonical JSON."
        ) from error
    if not isinstance(value, dict):
        raise BenchmarkDatasetError("The benchmark manifest root must be an object.")
    canonical = _canonical_json(cast(dict[str, object], value))
    if path.read_bytes() != canonical:
        raise BenchmarkDatasetError("The benchmark manifest is not canonical.")
    return cast(dict[str, Any], value)


def _manifest_integer(manifest: dict[str, Any], key: str) -> int:
    value = manifest.get(key)
    if type(value) is not int:
        raise BenchmarkDatasetError(f"Benchmark manifest field {key} is invalid.")
    return value


def _manifest_artifact_directory(
    output_directory: Path,
    manifest: dict[str, Any],
) -> Path:
    artifact_value = manifest.get("artifact")
    if not isinstance(artifact_value, dict):
        raise BenchmarkDatasetError("Benchmark artifact metadata is invalid.")
    relative_value = artifact_value.get("relativeDirectory")
    if not isinstance(relative_value, str) or not relative_value:
        raise BenchmarkDatasetError("Benchmark artifact directory is invalid.")
    candidate = (output_directory / Path(relative_value)).resolve()
    resolved_output = output_directory.resolve()
    if candidate != resolved_output and resolved_output not in candidate.parents:
        raise BenchmarkDatasetError("Benchmark artifact directory escapes its root.")
    return candidate


def validate_benchmark_dataset(
    output_directory: Path,
    *,
    progress: ProgressCallback | None = None,
) -> BenchmarkDatasetValidationReport:
    """Independently validate the manifest and every generated layout."""

    resolved_output = output_directory.resolve()
    manifest_path = resolved_output / BENCHMARK_MANIFEST_FILE
    manifest = _load_manifest(manifest_path)
    if _manifest_integer(manifest, "manifestVersion") != BENCHMARK_MANIFEST_VERSION:
        raise BenchmarkDatasetError("Benchmark manifest version is unsupported.")
    if manifest.get("generatorVersion") != BENCHMARK_GENERATOR_VERSION:
        raise BenchmarkDatasetError("Benchmark generator version is unsupported.")
    duplicate_groups = manifest.get("duplicateGroups")
    if not isinstance(duplicate_groups, list):
        raise BenchmarkDatasetError("Benchmark duplicate groups are invalid.")
    spec = BenchmarkDatasetSpec(
        layout_count=_manifest_integer(manifest, "layoutCount"),
        seed=_manifest_integer(manifest, "seed"),
        batch_size=_manifest_integer(manifest, "batchSize"),
        duplicate_group_count=len(duplicate_groups),
    )
    artifact = validate_snapshot_artifact(_manifest_artifact_directory(resolved_output, manifest))
    repository = BenchmarkSnapshotRepository(spec)
    expected_manifest = _benchmark_manifest(
        spec,
        repository,
        artifact,
        resolved_output,
    )
    if manifest != expected_manifest:
        raise BenchmarkDatasetError(
            "Benchmark manifest does not match its deterministic specification."
        )

    maximum_batch_size = 0
    uri = f"{artifact.database_path.resolve().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        cursor = connection.execute(
            """
            SELECT sequence_number, signature, payout
            FROM layouts
            WHERE game_id = 1
            ORDER BY sequence_number
            """
        )
        expected_sequence_number = 1
        while True:
            batch = cursor.fetchmany(spec.batch_size)
            if not batch:
                break
            maximum_batch_size = max(maximum_batch_size, len(batch))
            for raw_sequence_number, raw_signature, raw_payout in batch:
                sequence_number = cast(int, raw_sequence_number)
                signature = cast(str, raw_signature)
                payout = cast(int, raw_payout)
                if sequence_number != expected_sequence_number:
                    raise BenchmarkDatasetError("Benchmark layout sequence is incomplete.")
                expected_layout = repository._layout(sequence_number)
                if signature != expected_layout.signature or payout != expected_layout.payout:
                    raise BenchmarkDatasetError(
                        f"Benchmark layout {sequence_number} is not reproducible."
                    )
                expected_sequence_number += 1
            if progress is not None:
                progress(
                    BenchmarkProgress(
                        phase="validate",
                        processed_layout_count=expected_sequence_number - 1,
                        total_layout_count=spec.layout_count,
                    )
                )
    if expected_sequence_number != spec.layout_count + 1:
        raise BenchmarkDatasetError("Benchmark layout count is incomplete.")

    return BenchmarkDatasetValidationReport(
        layout_count=spec.layout_count,
        duplicate_group_count=spec.duplicate_group_count,
        logical_content_sha256=artifact.manifest.logical_content_sha256,
        snapshot_file_sha256=artifact.manifest.snapshot_file_sha256,
        snapshot_size_bytes=artifact.database_path.stat().st_size,
        maximum_validation_batch_size=maximum_batch_size,
    )
