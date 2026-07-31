"""Deterministic representative 0.1 release built from human-approved boards."""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from PIL import Image
from sqlalchemy import Engine, text

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
from game_predictor_worker.snapshots.integrity import file_sha256

V01_MANIFEST_VERSION: Final = 1
V01_GENERATOR_VERSION: Final = "v01-representative-generator-v1"
V01_RELEASE_VERSION: Final = "0.1.5"
V01_CREATED_AT: Final = datetime(2026, 7, 31, 18, 0, tzinfo=UTC)
V01_MANIFEST_FILE: Final = "representative-release-manifest.json"
V01_GAME_ID: Final = UUID("11000000-0000-0000-0000-000000000001")
V01_DATASET_VERSION_ID: Final = UUID("11000000-0000-0000-0000-000000000002")
V01_RULES_VERSION_ID: Final = UUID("11000000-0000-0000-0000-000000000003")
V01_SOURCE_GAME_ID: Final = UUID("5e6ef52f-59bc-4059-943e-fcec5362a331")
V01_IMPORT_JOB_ID: Final = UUID("8188e320-dbfe-4bc8-beb1-f90d71ebfb21")
V01_GAME_CODE: Final = "blazing-hot-7-deluxe"
V01_GAME_NAME: Final = "Blazing Hot 7 Deluxe"
V01_DATASET_VERSION: Final = 1
V01_RULES_VERSION: Final = 1
V01_LAYOUT_COUNT: Final = 500_000
V01_BATCH_SIZE: Final = 1_000
V01_ASSET_CANDIDATE_SAMPLE_SIZE: Final = 32
V01_SEED: Final = 118_500_031
V01_ROWS: Final = 3
V01_COLUMNS: Final = 5
V01_SPIN_COST: Final = 10
V01_SIGNATURE_CELL_WIDTH: Final = 2
V01_DUPLICATE_GROUP_COUNT: Final = 6
V01_MINIMUM_APPROVED_COUNT: Final = 100

ProgressCallback = Callable[[str, int, int], None]


class RepresentativeReleaseError(RuntimeError):
    """Stable failure for the representative release workflow."""


@dataclass(frozen=True, slots=True)
class ApprovedBoard:
    sequence_number: int
    symbol_codes: tuple[str, ...]
    status: str
    resolution_revision: int
    board_checksum_sha256: str
    crop_sample_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RepresentativeSymbolAsset:
    symbol_code: str
    source_sequence_number: int
    source_cell_index: int
    source_crop_sample_id: str
    source_relative_path: str
    source_sha256: str
    quality_score: float
    package_relative_path: str
    mobile_asset_key: str


@dataclass(frozen=True, slots=True)
class RepresentativeReleaseResult:
    output_directory: Path
    manifest_path: Path
    artifact: SnapshotArtifact
    approved_board_count: int
    symbol_assets: tuple[RepresentativeSymbolAsset, ...]


@dataclass(frozen=True, slots=True)
class RepresentativeValidationReport:
    layout_count: int
    approved_board_count: int
    symbol_count: int
    duplicate_group_count: int
    logical_content_sha256: str
    snapshot_file_sha256: str
    snapshot_size_bytes: int
    maximum_validation_batch_size: int
    unique_fixture_sequence_number: int


def v01_symbols() -> tuple[SymbolDefinition, ...]:
    definitions = (
        (1, "cherries", "Cherries"),
        (2, "grapes", "Grapes"),
        (3, "lemon", "Lemon"),
        (4, "orange", "Orange"),
        (5, "plum", "Plum"),
        (6, "seven", "Seven"),
        (7, "star", "Star"),
        (8, "watermelon", "Watermelon"),
    )
    return tuple(
        SymbolDefinition(
            mobile_code=mobile_code,
            code=code,
            name=name,
            is_wildcard=False,
            display_order=mobile_code - 1,
        )
        for mobile_code, code, name in definitions
    )


def v01_paylines() -> tuple[PaylineDefinition, ...]:
    return (
        PaylineDefinition(id="top", row_path=(0, 0, 0, 0, 0)),
        PaylineDefinition(id="middle", row_path=(1, 1, 1, 1, 1)),
        PaylineDefinition(id="bottom", row_path=(2, 2, 2, 2, 2)),
        PaylineDefinition(id="down-v", row_path=(0, 1, 2, 1, 0)),
        PaylineDefinition(id="up-v", row_path=(2, 1, 0, 1, 2)),
        PaylineDefinition(id="down-step", row_path=(0, 0, 1, 2, 2)),
        PaylineDefinition(id="up-step", row_path=(2, 2, 1, 0, 0)),
        PaylineDefinition(id="top-zigzag", row_path=(0, 1, 0, 1, 0)),
        PaylineDefinition(id="bottom-zigzag", row_path=(2, 1, 2, 1, 2)),
        PaylineDefinition(id="cross", row_path=(0, 2, 1, 2, 0)),
    )


def v01_payout_symbols() -> tuple[PayoutSymbolDefinition, ...]:
    return tuple(
        PayoutSymbolDefinition(
            symbol_mobile_code=symbol.mobile_code,
            minimum_match_length=2 if symbol.code in {"cherries", "seven"} else 3,
        )
        for symbol in v01_symbols()
    )


def v01_payout_rules() -> tuple[PayoutRuleDefinition, ...]:
    rules: list[PayoutRuleDefinition] = []
    for payout_symbol in v01_payout_symbols():
        code = v01_symbols()[payout_symbol.symbol_mobile_code - 1].code
        base = 24 + _derived_integer(V01_SEED, f"payout:{code}", 57)
        previous = 0
        for match_length in range(payout_symbol.minimum_match_length, V01_COLUMNS + 1):
            factor = 1 if match_length == 2 else 3 ** (match_length - 3)
            payout = max(previous + 10, base * factor)
            rules.append(
                PayoutRuleDefinition(
                    symbol_mobile_code=payout_symbol.symbol_mobile_code,
                    match_length=match_length,
                    payout_credits=payout,
                )
            )
            previous = payout
    return tuple(rules)


def load_approved_boards(
    engine: Engine,
    *,
    import_job_id: UUID = V01_IMPORT_JOB_ID,
) -> tuple[ApprovedBoard, ...]:
    query = text(
        """
        SELECT
            rb.sequence_number,
            iri.status,
            iri.resolution_revision,
            rb.board_checksum_sha256,
            iri.resolved_value
        FROM image_review_items AS iri
        JOIN recognized_boards AS rb ON rb.id = iri.recognized_board_id
        JOIN source_images AS si ON si.id = rb.source_image_id
        WHERE si.import_job_id = :import_job_id
          AND iri.status IN ('accepted', 'corrected')
        ORDER BY rb.sequence_number, iri.id
        """
    )
    with engine.connect() as connection:
        rows = tuple(connection.execute(query, {"import_job_id": import_job_id}).mappings())
    boards = tuple(_approved_board_from_row(cast(Mapping[str, object], row)) for row in rows)
    _validate_approved_boards(boards)
    return boards


def _approved_board_from_row(row: Mapping[str, object]) -> ApprovedBoard:
    sequence_number = _integer(row.get("sequence_number"), "sequence_number")
    status = _string(row.get("status"), "status")
    if status not in {"accepted", "corrected"}:
        raise RepresentativeReleaseError("Only accepted/corrected boards are allowed.")
    resolution_revision = _integer(row.get("resolution_revision"), "resolution_revision", minimum=1)
    board_checksum = _sha256(row.get("board_checksum_sha256"), "board checksum")
    resolved = row.get("resolved_value")
    if not isinstance(resolved, Mapping):
        raise RepresentativeReleaseError("Resolved board payload is invalid.")
    symbol_codes_value = resolved.get("symbolCodes")
    cells_value = resolved.get("cells")
    if not isinstance(symbol_codes_value, list) or len(symbol_codes_value) != 15:
        raise RepresentativeReleaseError("Resolved board must contain 15 symbol codes.")
    if not isinstance(cells_value, list) or len(cells_value) != 15:
        raise RepresentativeReleaseError("Resolved board must contain 15 cell records.")
    symbol_codes = tuple(_string(value, "symbolCode") for value in symbol_codes_value)
    crop_ids: list[str] = []
    for expected_index, cell in enumerate(cells_value):
        if not isinstance(cell, Mapping):
            raise RepresentativeReleaseError("Resolved cell payload is invalid.")
        if _integer(cell.get("cellIndex"), "cellIndex", minimum=0) != expected_index:
            raise RepresentativeReleaseError("Resolved cells are not row-major.")
        if _string(cell.get("symbolCode"), "cell symbol") != symbol_codes[expected_index]:
            raise RepresentativeReleaseError("Resolved cell and board symbols differ.")
        crop_ids.append(_sha256(cell.get("cropSampleId"), "cropSampleId"))
    return ApprovedBoard(
        sequence_number=sequence_number,
        symbol_codes=symbol_codes,
        status=status,
        resolution_revision=resolution_revision,
        board_checksum_sha256=board_checksum,
        crop_sample_ids=tuple(crop_ids),
    )


def _validate_approved_boards(boards: Sequence[ApprovedBoard]) -> None:
    if len(boards) < V01_MINIMUM_APPROVED_COUNT:
        raise RepresentativeReleaseError(
            f"At least {V01_MINIMUM_APPROVED_COUNT} approved boards are required."
        )
    sequences = tuple(board.sequence_number for board in boards)
    if len(set(sequences)) != len(sequences) or sequences != tuple(sorted(sequences)):
        raise RepresentativeReleaseError("Approved sequence numbers must be unique and sorted.")
    if sequences[0] < 1 or sequences[-1] > V01_LAYOUT_COUNT:
        raise RepresentativeReleaseError("Approved sequence number is outside 1..500000.")
    allowed_codes = {symbol.code for symbol in v01_symbols()}
    for board in boards:
        if len(board.symbol_codes) != V01_ROWS * V01_COLUMNS:
            raise RepresentativeReleaseError("Approved board must contain 15 symbols.")
        if not set(board.symbol_codes).issubset(allowed_codes):
            raise RepresentativeReleaseError("Approved board contains an unknown symbol.")


def select_representative_symbol_assets(
    boards: Sequence[ApprovedBoard],
    *,
    cell_root: Path,
    package_symbol_root: Path,
    mobile_symbol_root: Path,
) -> tuple[RepresentativeSymbolAsset, ...]:
    _validate_approved_boards(boards)
    resolved_cell_root = cell_root.resolve(strict=True)
    package_symbol_root.mkdir(parents=True, exist_ok=True)
    mobile_symbol_root.mkdir(parents=True, exist_ok=True)
    candidates: dict[str, list[tuple[int, int, Path, str]]] = {
        symbol.code: [] for symbol in v01_symbols()
    }
    for board in boards:
        for cell_index, (symbol_code, crop_sample_id) in enumerate(
            zip(board.symbol_codes, board.crop_sample_ids, strict=True)
        ):
            row, column = divmod(cell_index, V01_COLUMNS)
            crop_path = (
                resolved_cell_root
                / f"seq-{board.sequence_number:03d}"
                / f"r{row:02d}-c{column:02d}.png"
            )
            if not crop_path.is_file() or crop_path.is_symlink():
                raise RepresentativeReleaseError(f"Approved crop is missing: {crop_path}")
            candidates[symbol_code].append(
                (board.sequence_number, cell_index, crop_path, crop_sample_id)
            )

    selected: list[RepresentativeSymbolAsset] = []
    for symbol in v01_symbols():
        symbol_candidates = candidates[symbol.code]
        if not symbol_candidates:
            raise RepresentativeReleaseError(f"No approved crop exists for symbol {symbol.code}.")
        sample_count = min(V01_ASSET_CANDIDATE_SAMPLE_SIZE, len(symbol_candidates))
        sample_indexes = {
            round(index * (len(symbol_candidates) - 1) / max(sample_count - 1, 1))
            for index in range(sample_count)
        }
        ranked = sorted(
            (
                (
                    _image_quality_score(symbol_candidates[index][2]),
                    *symbol_candidates[index],
                )
                for index in sorted(sample_indexes)
            ),
            key=lambda item: (-item[0], item[1], item[2], item[4]),
        )
        score, sequence_number, cell_index, source, crop_sample_id = ranked[0]
        source_checksum = file_sha256(source)
        package_relative_path = f"symbols/{symbol.code}.png"
        package_target = package_symbol_root / f"{symbol.code}.png"
        mobile_target = mobile_symbol_root / f"{symbol.code}.png"
        _copy_exact(source, package_target, source_checksum)
        _copy_exact(source, mobile_target, source_checksum)
        selected.append(
            RepresentativeSymbolAsset(
                symbol_code=symbol.code,
                source_sequence_number=sequence_number,
                source_cell_index=cell_index,
                source_crop_sample_id=crop_sample_id,
                source_relative_path=source.relative_to(resolved_cell_root).as_posix(),
                source_sha256=source_checksum,
                quality_score=round(score, 6),
                package_relative_path=package_relative_path,
                mobile_asset_key=f"symbols/v01/{symbol.code}.png",
            )
        )
    return tuple(selected)


def _image_quality_score(path: Path) -> float:
    try:
        with Image.open(path) as image:
            image.load()
            if image.format != "PNG" or image.width < 32 or image.height < 32:
                raise RepresentativeReleaseError("Representative crop must be a valid PNG.")
            rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    except (OSError, ValueError) as error:
        raise RepresentativeReleaseError(f"Could not inspect crop {path}.") from error
    gray = rgb.mean(axis=2)
    sharpness = float(np.var(np.diff(gray, axis=0)) + np.var(np.diff(gray, axis=1)))
    contrast = float(np.std(gray))
    clipped = float(np.mean((gray < 8.0) | (gray > 247.0)))
    return sharpness + contrast * 4.0 - clipped * 300.0


def _copy_exact(source: Path, target: Path, expected_sha256: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and file_sha256(target) == expected_sha256:
        return
    temporary = target.with_name(f".{target.name}.tmp")
    try:
        shutil.copyfile(source, temporary)
        if file_sha256(temporary) != expected_sha256:
            raise RepresentativeReleaseError("Copied symbol asset checksum changed.")
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


class RepresentativeSnapshotRepository:
    """Generated-on-demand source preserving approved boards at their sequence."""

    def __init__(
        self,
        approved_boards: Sequence[ApprovedBoard],
        symbol_assets: Sequence[RepresentativeSymbolAsset],
        *,
        progress: ProgressCallback | None = None,
    ) -> None:
        _validate_approved_boards(approved_boards)
        if {asset.symbol_code for asset in symbol_assets} != {
            symbol.code for symbol in v01_symbols()
        }:
            raise RepresentativeReleaseError("Representative symbol assets are incomplete.")
        self.approved_boards = tuple(approved_boards)
        self.approved_by_sequence = {board.sequence_number: board for board in self.approved_boards}
        self.assets_by_code = {asset.symbol_code: asset for asset in symbol_assets}
        self.symbols = v01_symbols()
        self.symbol_codes = {symbol.code: symbol.mobile_code for symbol in self.symbols}
        self.game = GameConfig(
            id=str(V01_GAME_ID),
            code=V01_GAME_CODE,
            name=V01_GAME_NAME,
            rows=V01_ROWS,
            columns=V01_COLUMNS,
            spin_cost=V01_SPIN_COST,
            signature_cell_width=V01_SIGNATURE_CELL_WIDTH,
            symbols=self.symbols,
        )
        self.paylines = v01_paylines()
        self.payout_symbols = v01_payout_symbols()
        self.payout_rules = v01_payout_rules()
        self.selection = SnapshotGameSelection(
            V01_DATASET_VERSION_ID,
            V01_RULES_VERSION_ID,
            SUPPORTED_PAYOUT_ALGORITHM,
        )
        self.maximum_generated_batch_size = 0
        self._progress = progress
        approved_sources = tuple(board.sequence_number for board in self.approved_boards[:6])
        first_destination = V01_LAYOUT_COUNT - V01_DUPLICATE_GROUP_COUNT + 1
        self.duplicate_pairs = tuple(
            zip(
                approved_sources,
                range(first_destination, V01_LAYOUT_COUNT + 1),
                strict=True,
            )
        )
        self.duplicate_sources = dict(
            (destination, source) for source, destination in self.duplicate_pairs
        )

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
            dataset_game_id=V01_GAME_ID,
            rules_game_id=V01_GAME_ID,
            dataset_status=DatasetVersionStatus.PUBLISHED,
            rules_status=RulesVersionStatus.PUBLISHED,
            dataset_rows=V01_ROWS,
            dataset_columns=V01_COLUMNS,
            rules_rows=V01_ROWS,
            rules_columns=V01_COLUMNS,
            layout_count=V01_LAYOUT_COUNT,
            payout_count=V01_LAYOUT_COUNT,
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
            game_id=V01_GAME_ID,
            game_code=V01_GAME_CODE,
            game_name=V01_GAME_NAME,
            dataset_version_id=V01_DATASET_VERSION_ID,
            dataset_version=V01_DATASET_VERSION,
            rules_version_id=V01_RULES_VERSION_ID,
            rules_version=V01_RULES_VERSION,
            algorithm_version=SUPPORTED_PAYOUT_ALGORITHM,
            rows=V01_ROWS,
            columns=V01_COLUMNS,
            spin_cost=V01_SPIN_COST,
            signature_cell_width=V01_SIGNATURE_CELL_WIDTH,
            layout_count=V01_LAYOUT_COUNT,
            symbols=tuple(
                SnapshotSymbol(
                    mobile_code=symbol.mobile_code,
                    code=symbol.code,
                    name=symbol.name,
                    is_wildcard=symbol.is_wildcard,
                    display_order=symbol.display_order,
                    image_asset_key=self.assets_by_code[symbol.code].mobile_asset_key,
                )
                for symbol in self.symbols
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
        last = min(V01_LAYOUT_COUNT, after_sequence_number + limit)
        layouts = tuple(
            self.layout(sequence_number)
            for sequence_number in range(after_sequence_number + 1, last + 1)
        )
        self.maximum_generated_batch_size = max(self.maximum_generated_batch_size, len(layouts))
        if layouts and self._progress is not None:
            self._progress("generate", layouts[-1].sequence_number, V01_LAYOUT_COUNT)
        return layouts

    def cells(self, sequence_number: int) -> tuple[int, ...]:
        if sequence_number < 1 or sequence_number > V01_LAYOUT_COUNT:
            raise ValueError("sequence_number is outside the representative dataset.")
        source = self.duplicate_sources.get(sequence_number, sequence_number)
        approved = self.approved_by_sequence.get(source)
        if approved is not None:
            return tuple(self.symbol_codes[code] for code in approved.symbol_codes)
        return _synthetic_cells(source)

    def layout(self, sequence_number: int) -> SnapshotLayout:
        cells = self.cells(sequence_number)
        return SnapshotLayout(
            sequence_number=sequence_number,
            signature=encode_signature(cells, V01_SIGNATURE_CELL_WIDTH),
            payout=evaluate_payout(
                self.game,
                cells,
                self.paylines,
                self.payout_symbols,
                self.payout_rules,
            ).total_payout,
        )


def generate_representative_release(
    output_directory: Path,
    approved_boards: Sequence[ApprovedBoard],
    symbol_assets: Sequence[RepresentativeSymbolAsset],
    *,
    progress: ProgressCallback | None = None,
) -> RepresentativeReleaseResult:
    resolved_output = output_directory.resolve()
    repository = RepresentativeSnapshotRepository(
        approved_boards,
        symbol_assets,
        progress=progress,
    )
    artifact = ProductionSnapshotArtifactPublisher(
        ProductionSnapshotGenerator(repository, batch_size=V01_BATCH_SIZE),
        resolved_output,
    ).publish(
        ProductionSnapshotSpec(
            release_version=V01_RELEASE_VERSION,
            created_at=V01_CREATED_AT,
            games=(repository.selection,),
        )
    )
    manifest = _release_manifest(repository, artifact, resolved_output)
    manifest_path = resolved_output / V01_MANIFEST_FILE
    manifest_bytes = _canonical_json(manifest)
    if manifest_path.exists():
        if manifest_path.read_bytes() != manifest_bytes:
            raise RepresentativeReleaseError(
                "Existing representative release manifest has different content."
            )
    else:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_bytes(manifest_bytes)
    return RepresentativeReleaseResult(
        output_directory=resolved_output,
        manifest_path=manifest_path,
        artifact=artifact,
        approved_board_count=len(approved_boards),
        symbol_assets=tuple(symbol_assets),
    )


def validate_representative_release(
    output_directory: Path,
    *,
    progress: ProgressCallback | None = None,
) -> RepresentativeValidationReport:
    resolved_output = output_directory.resolve(strict=True)
    manifest_path = resolved_output / V01_MANIFEST_FILE
    manifest = _load_canonical_manifest(manifest_path)
    _require_manifest_identity(manifest)
    artifact = validate_snapshot_artifact(resolved_output / _manifest_artifact_directory(manifest))
    approved_boards = _approved_boards_from_manifest(manifest)
    symbol_assets = _symbol_assets_from_manifest(manifest)
    _validate_symbol_asset_files(resolved_output, symbol_assets)
    repository = RepresentativeSnapshotRepository(approved_boards, symbol_assets)
    expected_manifest = _release_manifest(repository, artifact, resolved_output)
    if manifest != expected_manifest:
        raise RepresentativeReleaseError(
            "Representative manifest does not match deterministic inputs."
        )

    maximum_batch_size = 0
    unique_fixture = 0
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
        expected_sequence = 1
        while True:
            batch = cursor.fetchmany(V01_BATCH_SIZE)
            if not batch:
                break
            maximum_batch_size = max(maximum_batch_size, len(batch))
            for raw_sequence, raw_signature, raw_payout in batch:
                sequence = cast(int, raw_sequence)
                signature = cast(str, raw_signature)
                payout = cast(int, raw_payout)
                if sequence != expected_sequence:
                    raise RepresentativeReleaseError("Snapshot sequence is incomplete.")
                expected = repository.layout(sequence)
                if signature != expected.signature or payout != expected.payout:
                    raise RepresentativeReleaseError(
                        f"Snapshot layout {sequence} is not reproducible."
                    )
                expected_sequence += 1
            if progress is not None:
                progress("validate", expected_sequence - 1, V01_LAYOUT_COUNT)
        if expected_sequence != V01_LAYOUT_COUNT + 1:
            raise RepresentativeReleaseError("Snapshot does not contain 500000 layouts.")
        for candidate in range(max(board.sequence_number for board in approved_boards) + 1, 10_000):
            signature = repository.layout(candidate).signature
            count = cast(
                int,
                connection.execute(
                    "SELECT COUNT(*) FROM layouts WHERE game_id = 1 AND signature = ?",
                    (signature,),
                ).fetchone()[0],
            )
            if count == 1:
                unique_fixture = candidate
                break
        for source, destination in repository.duplicate_pairs:
            signature = repository.layout(source).signature
            duplicate_count = cast(
                int,
                connection.execute(
                    "SELECT COUNT(*) FROM layouts WHERE game_id = 1 AND signature = ?",
                    (signature,),
                ).fetchone()[0],
            )
            if repository.layout(destination).signature != signature or duplicate_count < 2:
                raise RepresentativeReleaseError("Duplicate fixture is not ambiguous.")
    if unique_fixture == 0:
        raise RepresentativeReleaseError("No deterministic unique fixture was found.")

    expected_unique = _integer(manifest.get("uniqueFixtureSequenceNumber"), "unique fixture")
    if expected_unique != unique_fixture:
        raise RepresentativeReleaseError("Unique fixture sequence changed.")
    return RepresentativeValidationReport(
        layout_count=V01_LAYOUT_COUNT,
        approved_board_count=len(approved_boards),
        symbol_count=len(v01_symbols()),
        duplicate_group_count=len(repository.duplicate_pairs),
        logical_content_sha256=artifact.manifest.logical_content_sha256,
        snapshot_file_sha256=artifact.manifest.snapshot_file_sha256,
        snapshot_size_bytes=artifact.database_path.stat().st_size,
        maximum_validation_batch_size=maximum_batch_size,
        unique_fixture_sequence_number=unique_fixture,
    )


def load_representative_snapshot_artifact(output_directory: Path) -> SnapshotArtifact:
    """Load and statically validate the immutable snapshot selected by the manifest."""

    resolved_output = output_directory.resolve(strict=True)
    manifest = _load_canonical_manifest(resolved_output / V01_MANIFEST_FILE)
    _require_manifest_identity(manifest)
    return validate_snapshot_artifact(resolved_output / _manifest_artifact_directory(manifest))


def _release_manifest(
    repository: RepresentativeSnapshotRepository,
    artifact: SnapshotArtifact,
    output_directory: Path,
) -> dict[str, object]:
    unique_fixture = _find_unique_fixture(artifact, repository)
    return {
        "algorithmVersion": SUPPORTED_PAYOUT_ALGORITHM,
        "approvedBoards": [
            {
                "boardChecksumSha256": board.board_checksum_sha256,
                "resolutionRevision": board.resolution_revision,
                "sequenceNumber": board.sequence_number,
                "signature": repository.layout(board.sequence_number).signature,
                "status": board.status,
            }
            for board in repository.approved_boards
        ],
        "artifact": {
            "relativeDirectory": artifact.directory.relative_to(output_directory).as_posix(),
            "snapshotFileSha256": artifact.manifest.snapshot_file_sha256,
            "snapshotSizeBytes": artifact.database_path.stat().st_size,
        },
        "batchSize": V01_BATCH_SIZE,
        "createdAt": V01_CREATED_AT.isoformat().replace("+00:00", "Z"),
        "datasetKind": "human-approved-prefix-with-deterministic-synthetic-fill",
        "datasetVersionId": str(V01_DATASET_VERSION_ID),
        "duplicateGroups": [
            {
                "sequenceNumbers": [source, destination],
                "signature": repository.layout(source).signature,
            }
            for source, destination in repository.duplicate_pairs
        ],
        "game": {
            "code": V01_GAME_CODE,
            "columns": V01_COLUMNS,
            "id": str(V01_GAME_ID),
            "name": V01_GAME_NAME,
            "paylines": [
                {"id": payline.id, "rowPath": list(payline.row_path)}
                for payline in repository.paylines
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
                    "minimumMatchLength": item.minimum_match_length,
                    "symbolMobileCode": item.symbol_mobile_code,
                }
                for item in repository.payout_symbols
            ],
            "rows": V01_ROWS,
            "spinCost": V01_SPIN_COST,
            "symbols": [
                {
                    "code": symbol.code,
                    "displayOrder": symbol.display_order,
                    "isWildcard": symbol.is_wildcard,
                    "mobileCode": symbol.mobile_code,
                    "name": symbol.name,
                }
                for symbol in repository.symbols
            ],
        },
        "generatorVersion": V01_GENERATOR_VERSION,
        "layoutCount": V01_LAYOUT_COUNT,
        "logicalContentSha256": artifact.manifest.logical_content_sha256,
        "manifestVersion": V01_MANIFEST_VERSION,
        "releaseVersion": V01_RELEASE_VERSION,
        "rulesVersionId": str(V01_RULES_VERSION_ID),
        "seed": V01_SEED,
        "source": {
            "approvedBoardCount": len(repository.approved_boards),
            "gameId": str(V01_SOURCE_GAME_ID),
            "importJobId": str(V01_IMPORT_JOB_ID),
        },
        "symbolAssets": [
            {
                "mobileAssetKey": asset.mobile_asset_key,
                "packageRelativePath": asset.package_relative_path,
                "qualityScore": asset.quality_score,
                "sourceCellIndex": asset.source_cell_index,
                "sourceCropSampleId": asset.source_crop_sample_id,
                "sourceRelativePath": asset.source_relative_path,
                "sourceSequenceNumber": asset.source_sequence_number,
                "sourceSha256": asset.source_sha256,
                "symbolCode": asset.symbol_code,
            }
            for asset in sorted(
                repository.assets_by_code.values(), key=lambda item: item.symbol_code
            )
        ],
        "uniqueFixtureSequenceNumber": unique_fixture,
    }


def _find_unique_fixture(
    artifact: SnapshotArtifact,
    repository: RepresentativeSnapshotRepository,
) -> int:
    start = max(board.sequence_number for board in repository.approved_boards) + 1
    uri = f"{artifact.database_path.resolve().as_uri()}?mode=ro&immutable=1"
    with closing(sqlite3.connect(uri, uri=True)) as connection:
        for sequence_number in range(start, 10_000):
            signature = repository.layout(sequence_number).signature
            row = connection.execute(
                "SELECT COUNT(*) FROM layouts WHERE game_id = 1 AND signature = ?",
                (signature,),
            ).fetchone()
            if row is not None and cast(int, row[0]) == 1:
                return sequence_number
    raise RepresentativeReleaseError("No deterministic unique fixture was found.")


def _approved_boards_from_manifest(manifest: Mapping[str, object]) -> tuple[ApprovedBoard, ...]:
    values = manifest.get("approvedBoards")
    if not isinstance(values, list):
        raise RepresentativeReleaseError("approvedBoards is invalid.")
    symbols_by_mobile = {symbol.mobile_code: symbol.code for symbol in v01_symbols()}
    boards: list[ApprovedBoard] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise RepresentativeReleaseError("approvedBoards entry is invalid.")
        signature = _string(value.get("signature"), "approved signature")
        if len(signature) != V01_ROWS * V01_COLUMNS * V01_SIGNATURE_CELL_WIDTH:
            raise RepresentativeReleaseError("Approved signature width is invalid.")
        mobile_codes = tuple(
            int(signature[index : index + V01_SIGNATURE_CELL_WIDTH])
            for index in range(0, len(signature), V01_SIGNATURE_CELL_WIDTH)
        )
        try:
            symbol_codes = tuple(symbols_by_mobile[code] for code in mobile_codes)
        except KeyError as error:
            raise RepresentativeReleaseError("Approved signature has unknown symbol.") from error
        boards.append(
            ApprovedBoard(
                sequence_number=_integer(value.get("sequenceNumber"), "sequenceNumber"),
                symbol_codes=symbol_codes,
                status=_string(value.get("status"), "status"),
                resolution_revision=_integer(
                    value.get("resolutionRevision"), "resolutionRevision", minimum=1
                ),
                board_checksum_sha256=_sha256(
                    value.get("boardChecksumSha256"), "boardChecksumSha256"
                ),
                crop_sample_ids=tuple("0" * 64 for _ in range(15)),
            )
        )
    result = tuple(boards)
    _validate_approved_boards(result)
    return result


def _symbol_assets_from_manifest(
    manifest: Mapping[str, object],
) -> tuple[RepresentativeSymbolAsset, ...]:
    values = manifest.get("symbolAssets")
    if not isinstance(values, list):
        raise RepresentativeReleaseError("symbolAssets is invalid.")
    assets: list[RepresentativeSymbolAsset] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise RepresentativeReleaseError("symbolAssets entry is invalid.")
        quality = value.get("qualityScore")
        if not isinstance(quality, int | float) or isinstance(quality, bool):
            raise RepresentativeReleaseError("qualityScore is invalid.")
        assets.append(
            RepresentativeSymbolAsset(
                symbol_code=_string(value.get("symbolCode"), "symbolCode"),
                source_sequence_number=_integer(
                    value.get("sourceSequenceNumber"), "sourceSequenceNumber"
                ),
                source_cell_index=_integer(
                    value.get("sourceCellIndex"), "sourceCellIndex", minimum=0
                ),
                source_crop_sample_id=_sha256(
                    value.get("sourceCropSampleId"), "sourceCropSampleId"
                ),
                source_relative_path=_safe_relative_path(
                    value.get("sourceRelativePath"), "sourceRelativePath"
                ),
                source_sha256=_sha256(value.get("sourceSha256"), "sourceSha256"),
                quality_score=float(quality),
                package_relative_path=_safe_relative_path(
                    value.get("packageRelativePath"), "packageRelativePath"
                ),
                mobile_asset_key=_safe_relative_path(value.get("mobileAssetKey"), "mobileAssetKey"),
            )
        )
    return tuple(assets)


def _validate_symbol_asset_files(
    output_directory: Path,
    assets: Sequence[RepresentativeSymbolAsset],
) -> None:
    for asset in assets:
        path = (output_directory / asset.package_relative_path).resolve()
        if output_directory != path.parent and output_directory not in path.parents:
            raise RepresentativeReleaseError("Symbol asset escapes release directory.")
        if not path.is_file() or path.is_symlink() or file_sha256(path) != asset.source_sha256:
            raise RepresentativeReleaseError(f"Symbol asset is missing or changed: {path}")


def _require_manifest_identity(manifest: Mapping[str, object]) -> None:
    expected = {
        "manifestVersion": V01_MANIFEST_VERSION,
        "generatorVersion": V01_GENERATOR_VERSION,
        "releaseVersion": V01_RELEASE_VERSION,
        "layoutCount": V01_LAYOUT_COUNT,
        "seed": V01_SEED,
        "batchSize": V01_BATCH_SIZE,
        "algorithmVersion": SUPPORTED_PAYOUT_ALGORITHM,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RepresentativeReleaseError(f"Manifest field {key} is invalid.")


def _manifest_artifact_directory(manifest: Mapping[str, object]) -> Path:
    artifact = manifest.get("artifact")
    if not isinstance(artifact, Mapping):
        raise RepresentativeReleaseError("Manifest artifact is invalid.")
    return Path(_safe_relative_path(artifact.get("relativeDirectory"), "relativeDirectory"))


def _load_canonical_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RepresentativeReleaseError("Representative manifest is unreadable.") from error
    if not isinstance(value, dict) or path.read_bytes() != _canonical_json(value):
        raise RepresentativeReleaseError("Representative manifest is not canonical JSON.")
    return cast(dict[str, Any], value)


def _canonical_json(value: Mapping[str, object]) -> bytes:
    return (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _derived_integer(seed: int, label: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{V01_GENERATOR_VERSION}:{seed}:{label}".encode()).digest()
    return int.from_bytes(digest, "big") % modulus


@lru_cache(maxsize=1)
def _affine_parameters() -> tuple[int, int, int]:
    modulus = len(v01_symbols()) ** (V01_ROWS * V01_COLUMNS)
    multiplier = _derived_integer(V01_SEED, "multiplier", modulus) or 1
    while math.gcd(multiplier, modulus) != 1:
        multiplier = (multiplier + 1) % modulus or 1
    offset = _derived_integer(V01_SEED, "offset", modulus)
    return multiplier, offset, modulus


def _synthetic_cells(sequence_number: int) -> tuple[int, ...]:
    multiplier, offset, modulus = _affine_parameters()
    encoded = (multiplier * (sequence_number - 1) + offset) % modulus
    cells: list[int] = []
    symbol_count = len(v01_symbols())
    for _ in range(V01_ROWS * V01_COLUMNS):
        encoded, digit = divmod(encoded, symbol_count)
        cells.append(digit + 1)
    return tuple(cells)


def _integer(value: object, label: str, *, minimum: int = 1) -> int:
    if type(value) is not int or value < minimum:
        raise RepresentativeReleaseError(f"{label} is invalid.")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RepresentativeReleaseError(f"{label} is invalid.")
    return value.strip()


def _sha256(value: object, label: str) -> str:
    result = _string(value, label)
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise RepresentativeReleaseError(f"{label} is not SHA-256.")
    return result


def _safe_relative_path(value: object, label: str) -> str:
    result = _string(value, label).replace("\\", "/")
    path = Path(result)
    if path.is_absolute() or ".." in path.parts or result.startswith("/"):
        raise RepresentativeReleaseError(f"{label} is not a safe relative path.")
    return result
