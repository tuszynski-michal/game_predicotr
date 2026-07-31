from __future__ import annotations

import os
from pathlib import Path

from game_predictor_worker.releases.representative_v01 import (
    V01_COLUMNS,
    V01_LAYOUT_COUNT,
    ApprovedBoard,
    RepresentativeSnapshotRepository,
    RepresentativeSymbolAsset,
    select_representative_symbol_assets,
    v01_paylines,
    v01_payout_rules,
    v01_payout_symbols,
    v01_symbols,
)
from game_predictor_worker.snapshots.integrity import file_sha256
from PIL import Image


def _approved_boards(count: int = 100) -> tuple[ApprovedBoard, ...]:
    codes = tuple(symbol.code for symbol in v01_symbols())
    return tuple(
        ApprovedBoard(
            sequence_number=sequence,
            symbol_codes=tuple(
                codes[(sequence + cell_index) % len(codes)] for cell_index in range(15)
            ),
            status="accepted" if sequence % 2 else "corrected",
            resolution_revision=1,
            board_checksum_sha256=f"{sequence:064x}",
            crop_sample_ids=tuple(
                f"{sequence * 100 + cell_index:064x}" for cell_index in range(15)
            ),
        )
        for sequence in range(1, count + 1)
    )


def _assets() -> tuple[RepresentativeSymbolAsset, ...]:
    return tuple(
        RepresentativeSymbolAsset(
            symbol_code=symbol.code,
            source_sequence_number=1,
            source_cell_index=symbol.mobile_code - 1,
            source_crop_sample_id=f"{symbol.mobile_code:064x}",
            source_relative_path=f"seq-001/r00-c{symbol.mobile_code - 1:02d}.png",
            source_sha256=f"{symbol.mobile_code:064x}",
            quality_score=100.0 + symbol.mobile_code,
            package_relative_path=f"symbols/{symbol.code}.png",
            mobile_asset_key=f"symbols/v01/{symbol.code}.png",
        )
        for symbol in v01_symbols()
    )


def test_rules_define_ten_unique_complete_paylines_and_increasing_payouts() -> None:
    paylines = v01_paylines()
    assert len(paylines) == 10
    assert len({payline.row_path for payline in paylines}) == 10
    assert all(len(payline.row_path) == V01_COLUMNS for payline in paylines)
    assert {payline.id for payline in paylines} >= {
        "top",
        "middle",
        "bottom",
        "down-v",
        "up-v",
        "cross",
    }

    minimums = {item.symbol_mobile_code: item.minimum_match_length for item in v01_payout_symbols()}
    assert minimums[1] == 2
    assert minimums[6] == 2
    assert all(minimums[code] == 3 for code in (2, 3, 4, 5, 7, 8))
    grouped: dict[int, list[int]] = {}
    for rule in v01_payout_rules():
        grouped.setdefault(rule.symbol_mobile_code, []).append(rule.payout_credits)
    assert all(values == sorted(set(values)) for values in grouped.values())


def test_repository_preserves_approved_boards_and_creates_explicit_duplicates() -> None:
    boards = _approved_boards()
    repository = RepresentativeSnapshotRepository(boards, _assets())
    mobile_by_code = {symbol.code: symbol.mobile_code for symbol in v01_symbols()}
    assert repository.cells(1) == tuple(mobile_by_code[code] for code in boards[0].symbol_codes)
    assert repository.cells(100) == tuple(mobile_by_code[code] for code in boards[-1].symbol_codes)
    assert repository.cells(101) == repository.cells(101)
    assert repository.cells(101) != repository.cells(102)

    for source, destination in repository.duplicate_pairs:
        assert destination <= V01_LAYOUT_COUNT
        assert repository.layout(source).signature == repository.layout(destination).signature
        assert repository.layout(source).payout == repository.layout(destination).payout


def test_representative_asset_selection_is_deterministic_and_copies_exact_pngs(
    tmp_path: Path,
) -> None:
    boards = _approved_boards()
    cell_root = tmp_path / "cells"
    source_by_code: dict[str, Path] = {}
    for symbol in v01_symbols():
        source = tmp_path / f"source-{symbol.code}.png"
        Image.new(
            "RGB",
            (40, 40),
            color=(symbol.mobile_code * 20, 40, 255 - symbol.mobile_code * 20),
        ).save(source)
        source_by_code[symbol.code] = source

    for board in boards:
        sequence_root = cell_root / f"seq-{board.sequence_number:03d}"
        sequence_root.mkdir(parents=True)
        for cell_index, code in enumerate(board.symbol_codes):
            row, column = divmod(cell_index, V01_COLUMNS)
            os.link(
                source_by_code[code],
                sequence_root / f"r{row:02d}-c{column:02d}.png",
            )

    package_root = tmp_path / "package-symbols"
    mobile_root = tmp_path / "mobile-symbols"
    first = select_representative_symbol_assets(
        boards,
        cell_root=cell_root,
        package_symbol_root=package_root,
        mobile_symbol_root=mobile_root,
    )
    second = select_representative_symbol_assets(
        boards,
        cell_root=cell_root,
        package_symbol_root=package_root,
        mobile_symbol_root=mobile_root,
    )
    assert first == second
    assert {asset.symbol_code for asset in first} == {symbol.code for symbol in v01_symbols()}
    for asset in first:
        assert file_sha256(package_root / f"{asset.symbol_code}.png") == asset.source_sha256
        assert file_sha256(mobile_root / f"{asset.symbol_code}.png") == asset.source_sha256
