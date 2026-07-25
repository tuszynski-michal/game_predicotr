"""Deterministic M1 fixture generation without persistence dependencies."""

from __future__ import annotations

import random
from collections import Counter

from game_predictor_worker.domain import (
    ForecastPeak,
    GameConfig,
    PaylineDefinition,
    PayoutRuleDefinition,
    PayoutSymbolDefinition,
    SymbolDefinition,
    encode_signature,
    evaluate_payout,
)
from game_predictor_worker.fixtures.contracts import (
    DuplicateFixture,
    GeneratedGameFixture,
    GeneratedLayout,
    M1Fixture,
    TargetGoldenFixture,
    UniquePrefixFixture,
)

M1_FIXTURE_VERSION = "m1-fixture-v2"
M1_DATASET_VERSION = 2
M1_RULES_VERSION = 2
M1_ALGORITHM_VERSION = "payout-v2"
M1_LAYOUT_COUNT = 1_000
M1_DUPLICATE_GROUP_COUNT = 6

_GAME_SEEDS = (71_401, 71_402, 71_403)
_SYMBOL_COUNTS = (10, 12, 11)
_DUPLICATE_SOURCE_SEQUENCES = (101, 102, 103, 104, 105, 106)
_CONTROLLED_PAYOUTS: tuple[dict[int, int], ...] = (
    {100: 200, 111: 100, 112: 10},
    {200: 100},
    {},
)

_PAYLINES = (
    PaylineDefinition(id="top", row_path=(0, 0, 0, 0, 0)),
    PaylineDefinition(id="middle", row_path=(1, 1, 1, 1, 1)),
    PaylineDefinition(id="bottom", row_path=(2, 2, 2, 2, 2)),
    PaylineDefinition(id="down-v", row_path=(0, 1, 2, 1, 0)),
    PaylineDefinition(id="up-v", row_path=(2, 1, 0, 1, 2)),
)


def _symbols(game_number: int, symbol_count: int) -> tuple[SymbolDefinition, ...]:
    wildcard_code = symbol_count if game_number == 3 else None
    return tuple(
        SymbolDefinition(
            mobile_code=mobile_code,
            code="JOKER" if mobile_code == wildcard_code else f"S{mobile_code}",
            name="Joker" if mobile_code == wildcard_code else f"Symbol {mobile_code}",
            is_wildcard=mobile_code == wildcard_code,
            display_order=mobile_code - 1,
        )
        for mobile_code in range(1, symbol_count + 1)
    )


def _game_config(game_number: int, symbol_count: int) -> GameConfig:
    return GameConfig(
        id=f"game-{game_number}",
        code=f"game-{game_number}",
        name=f"Mock Game {game_number}",
        rows=3,
        columns=5,
        spin_cost=10,
        signature_cell_width=2,
        symbols=_symbols(game_number, symbol_count),
    )


def _payout_symbols(game: GameConfig) -> tuple[PayoutSymbolDefinition, ...]:
    ordinary_symbols = tuple(symbol for symbol in game.symbols if not symbol.is_wildcard)
    return tuple(
        PayoutSymbolDefinition(
            symbol_mobile_code=symbol.mobile_code,
            minimum_match_length=2 if index < 2 else 3,
        )
        for index, symbol in enumerate(ordinary_symbols)
    )


def _payout_rules(
    game: GameConfig,
    payout_symbols: tuple[PayoutSymbolDefinition, ...],
) -> tuple[PayoutRuleDefinition, ...]:
    rules: list[PayoutRuleDefinition] = []
    ordinary_symbols = tuple(symbol for symbol in game.symbols if not symbol.is_wildcard)
    plateau_symbol_code = ordinary_symbols[-1].mobile_code
    for payout_symbol in payout_symbols:
        base_payout = (
            10
            if payout_symbol.symbol_mobile_code == plateau_symbol_code
            else 50 + payout_symbol.symbol_mobile_code * 50
        )
        for match_length in range(
            payout_symbol.minimum_match_length,
            game.columns + 1,
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


def _random_cells(
    *,
    random_source: random.Random,
    symbol_codes: tuple[int, ...],
    cell_count: int,
) -> tuple[int, ...]:
    return tuple(random_source.choice(symbol_codes) for _ in range(cell_count))


def _unique_cells_with_payout(
    *,
    random_source: random.Random,
    game: GameConfig,
    payout_symbols: tuple[PayoutSymbolDefinition, ...],
    payout_rules: tuple[PayoutRuleDefinition, ...],
    desired_payout: int,
    used_signatures: set[str],
) -> tuple[int, ...]:
    symbol_codes = tuple(symbol.mobile_code for symbol in game.symbols)
    forced_symbol = next(
        (
            rule.symbol_mobile_code
            for rule in payout_rules
            if rule.match_length == 3 and rule.payout_credits == desired_payout
        ),
        None,
    )

    while True:
        cells = _random_cells(
            random_source=random_source,
            symbol_codes=symbol_codes,
            cell_count=game.rows * game.columns,
        )
        if desired_payout > 0:
            if forced_symbol is None:
                raise RuntimeError(
                    f"No length-three payout rule produces {desired_payout} credits."
                )
            replacement_codes = tuple(code for code in symbol_codes if code != forced_symbol)
            cells = (
                forced_symbol,
                forced_symbol,
                forced_symbol,
                random_source.choice(replacement_codes),
                random_source.choice(replacement_codes),
                *cells[5:],
            )
        signature = encode_signature(cells, game.signature_cell_width)
        if signature in used_signatures:
            continue
        actual_payout = evaluate_payout(
            game,
            cells,
            _PAYLINES,
            payout_symbols,
            payout_rules,
        ).total_payout
        if actual_payout == desired_payout:
            used_signatures.add(signature)
            return cells


def _unique_prefix_fixture(
    layouts: tuple[GeneratedLayout, ...],
    cell_width: int,
) -> UniquePrefixFixture:
    full_counts = Counter(layout.signature for layout in layouts)
    for prefix_cell_count in range(1, len(layouts[0].cells)):
        prefix_length = prefix_cell_count * cell_width
        prefix_counts = Counter(layout.signature[:prefix_length] for layout in layouts)
        for layout in layouts:
            if (
                full_counts[layout.signature] == 1
                and prefix_counts[layout.signature[:prefix_length]] == 1
            ):
                return UniquePrefixFixture(
                    sequence_number=layout.sequence_number,
                    cell_count=prefix_cell_count,
                    signature_prefix=layout.signature[:prefix_length],
                )
    raise RuntimeError("Generated fixture does not contain an incomplete unique prefix.")


def _target_golden_fixtures(
    game_number: int,
) -> tuple[TargetGoldenFixture, ...]:
    if game_number == 1:
        return (
            TargetGoldenFixture(
                code="multiple-peaks-later-lower-and-plateau",
                start_sequence_number=99,
                expected_final_cumulative_payout=310,
                expected_final_cumulative_cost=9_990,
                expected_final_net_credits=-9_680,
                expected_positive_local_peaks=(
                    ForecastPeak(
                        spin_number=1,
                        sequence_number=100,
                        spin_payout=200,
                        cumulative_payout=200,
                        cumulative_cost=10,
                        net_credits=190,
                    ),
                    ForecastPeak(
                        spin_number=12,
                        sequence_number=111,
                        spin_payout=100,
                        cumulative_payout=300,
                        cumulative_cost=120,
                        net_credits=180,
                    ),
                ),
            ),
        )
    if game_number == 2:
        return (
            TargetGoldenFixture(
                code="single-positive-peak",
                start_sequence_number=199,
                expected_final_cumulative_payout=100,
                expected_final_cumulative_cost=9_990,
                expected_final_net_credits=-9_890,
                expected_positive_local_peaks=(
                    ForecastPeak(
                        spin_number=1,
                        sequence_number=200,
                        spin_payout=100,
                        cumulative_payout=100,
                        cumulative_cost=10,
                        net_credits=90,
                    ),
                ),
            ),
            TargetGoldenFixture(
                code="no-positive-peak",
                start_sequence_number=200,
                expected_final_cumulative_payout=0,
                expected_final_cumulative_cost=9_990,
                expected_final_net_credits=-9_990,
                expected_positive_local_peaks=(),
            ),
        )
    return ()


def _generate_game_fixture(
    game_number: int,
    seed: int,
    symbol_count: int,
    controlled_payouts: dict[int, int],
) -> GeneratedGameFixture:
    game = _game_config(game_number, symbol_count)
    payout_symbols = _payout_symbols(game)
    payout_rules = _payout_rules(game, payout_symbols)
    random_source = random.Random(seed)
    unique_layout_count = M1_LAYOUT_COUNT - M1_DUPLICATE_GROUP_COUNT
    used_signatures: set[str] = set()
    unique_cells = tuple(
        _unique_cells_with_payout(
            random_source=random_source,
            game=game,
            payout_symbols=payout_symbols,
            payout_rules=payout_rules,
            desired_payout=controlled_payouts.get(sequence_number, 0),
            used_signatures=used_signatures,
        )
        for sequence_number in range(1, unique_layout_count + 1)
    )

    all_cells = unique_cells + tuple(
        unique_cells[source_sequence - 1] for source_sequence in _DUPLICATE_SOURCE_SEQUENCES
    )
    layouts = tuple(
        GeneratedLayout(
            sequence_number=sequence_number,
            cells=cells,
            signature=encode_signature(cells, game.signature_cell_width),
            payout_credits=evaluate_payout(
                game,
                cells,
                _PAYLINES,
                payout_symbols,
                payout_rules,
            ).total_payout,
        )
        for sequence_number, cells in enumerate(all_cells, start=1)
    )
    duplicate_fixtures = tuple(
        DuplicateFixture(
            signature=layouts[source_sequence - 1].signature,
            sequence_numbers=(
                source_sequence,
                unique_layout_count + duplicate_index,
            ),
        )
        for duplicate_index, source_sequence in enumerate(
            _DUPLICATE_SOURCE_SEQUENCES,
            start=1,
        )
    )

    return GeneratedGameFixture(
        seed=seed,
        game=game,
        paylines=_PAYLINES,
        payout_symbols=payout_symbols,
        payout_rules=payout_rules,
        layouts=layouts,
        duplicate_fixtures=duplicate_fixtures,
        unique_prefix_fixture=_unique_prefix_fixture(
            layouts,
            game.signature_cell_width,
        ),
        target_golden_fixtures=_target_golden_fixtures(game_number),
    )


def generate_m1_fixture() -> M1Fixture:
    """Generate the complete, deterministic logical fixture consumed by M1.3."""

    games = tuple(
        _generate_game_fixture(
            game_number,
            seed,
            symbol_count,
            controlled_payouts,
        )
        for game_number, (seed, symbol_count, controlled_payouts) in enumerate(
            zip(
                _GAME_SEEDS,
                _SYMBOL_COUNTS,
                _CONTROLLED_PAYOUTS,
                strict=True,
            ),
            start=1,
        )
    )
    return M1Fixture(
        fixture_version=M1_FIXTURE_VERSION,
        dataset_version=M1_DATASET_VERSION,
        rules_version=M1_RULES_VERSION,
        algorithm_version=M1_ALGORITHM_VERSION,
        games=games,
    )
