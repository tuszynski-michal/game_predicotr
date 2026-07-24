from __future__ import annotations

import random
from dataclasses import replace

import pytest
from game_predictor_worker.fixtures import (
    FixtureErrorCode,
    FixtureValidationError,
    fixture_fingerprint,
    generate_m1_fixture,
    validate_m1_fixture,
)


def test_generator_creates_complete_valid_m1_fixture() -> None:
    fixture = generate_m1_fixture()

    report = validate_m1_fixture(fixture)

    assert report.game_count == 3
    assert report.layout_count == 3_000
    assert [game.game.code for game in fixture.games] == [
        "game-1",
        "game-2",
        "game-3",
    ]
    assert [len(game.game.symbols) for game in fixture.games] == [10, 12, 11]
    assert [sum(symbol.is_wildcard for symbol in game.game.symbols) for game in fixture.games] == [
        0,
        0,
        1,
    ]
    assert all(game.layout_count == 1_000 for game in report.games)
    assert all(game.duplicate_group_count == 6 for game in report.games)
    assert all(1 <= game.unique_prefix_cell_count < 15 for game in report.games)


def test_generator_is_deterministic_and_does_not_use_global_random_state() -> None:
    random.seed(1)
    first = generate_m1_fixture()
    random.seed(2)
    second = generate_m1_fixture()

    assert first == second
    assert fixture_fingerprint(first) == fixture_fingerprint(second)
    assert (
        fixture_fingerprint(first)
        == "f349dcbeec49f4627d330ad4a63d1f1f09480ec1d60443b462debd6a1df69f88"
    )


def test_fixture_contains_only_the_controlled_nonzero_payouts() -> None:
    fixture = generate_m1_fixture()

    actual = [
        {
            layout.sequence_number: layout.payout_credits
            for layout in game.layouts
            if layout.payout_credits > 0
        }
        for game in fixture.games
    ]

    assert actual == [
        {100: 200, 111: 100, 112: 10},
        {200: 100},
        {},
    ]


def test_target_golden_metadata_covers_required_full_cycle_scenarios() -> None:
    fixture = generate_m1_fixture()

    game_one_golden = fixture.games[0].target_golden_fixtures[0]
    assert game_one_golden.code == "multiple-peaks-later-lower-and-plateau"
    assert game_one_golden.start_sequence_number == 99
    assert [
        (
            peak.spin_number,
            peak.sequence_number,
            peak.net_credits,
        )
        for peak in game_one_golden.expected_positive_local_peaks
    ] == [(1, 100, 190), (12, 111, 180)]
    assert game_one_golden.expected_final_net_credits == -9_680

    game_two_golden = fixture.games[1].target_golden_fixtures
    assert [
        (
            golden.code,
            golden.start_sequence_number,
            len(golden.expected_positive_local_peaks),
        )
        for golden in game_two_golden
    ] == [
        ("single-positive-peak", 199, 1),
        ("no-positive-peak", 200, 0),
    ]


def test_controlled_duplicates_have_identical_content_and_payout() -> None:
    fixture = generate_m1_fixture()

    for game_fixture in fixture.games:
        for duplicate in game_fixture.duplicate_fixtures:
            first_number, second_number = duplicate.sequence_numbers
            first = game_fixture.layouts[first_number - 1]
            second = game_fixture.layouts[second_number - 1]
            assert first.signature == duplicate.signature
            assert second.signature == duplicate.signature
            assert first.cells == second.cells
            assert first.payout_credits == second.payout_credits


def test_declared_incomplete_prefix_resolves_to_one_layout() -> None:
    fixture = generate_m1_fixture()

    for game_fixture in fixture.games:
        reference = game_fixture.unique_prefix_fixture
        matches = [
            layout.sequence_number
            for layout in game_fixture.layouts
            if layout.signature.startswith(reference.signature_prefix)
        ]
        assert matches == [reference.sequence_number]
        assert reference.cell_count < game_fixture.game.rows * game_fixture.game.columns


def test_validator_rejects_sequence_gap() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    corrupt_layout = replace(game.layouts[9], sequence_number=11)
    corrupt_game = replace(
        game,
        layouts=(*game.layouts[:9], corrupt_layout, *game.layouts[10:]),
    )

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.SEQUENCE_INTEGRITY_ERROR


def test_validator_rejects_signature_not_matching_cells() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    corrupt_layout = replace(game.layouts[0], signature="99" * 15)
    corrupt_game = replace(game, layouts=(corrupt_layout, *game.layouts[1:]))

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.SIGNATURE_INTEGRITY_ERROR


def test_validator_rejects_symbol_outside_game() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    corrupt_layout = replace(
        game.layouts[0],
        cells=(99, *game.layouts[0].cells[1:]),
        signature=f"99{game.layouts[0].signature[2:]}",
    )
    corrupt_game = replace(game, layouts=(corrupt_layout, *game.layouts[1:]))

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.LAYOUT_INTEGRITY_ERROR


def test_validator_rejects_stale_precomputed_payout() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    corrupt_layout = replace(
        game.layouts[0],
        payout_credits=game.layouts[0].payout_credits + 1,
    )
    corrupt_game = replace(game, layouts=(corrupt_layout, *game.layouts[1:]))

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.PAYOUT_INTEGRITY_ERROR


def test_validator_rejects_incomplete_duplicate_declaration() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    corrupt_game = replace(
        game,
        duplicate_fixtures=game.duplicate_fixtures[:-1],
    )

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.DUPLICATE_INTEGRITY_ERROR


def test_validator_rejects_non_unique_declared_prefix() -> None:
    fixture = generate_m1_fixture()
    game = fixture.games[0]
    duplicate = game.duplicate_fixtures[0]
    duplicate_layout = game.layouts[duplicate.sequence_numbers[0] - 1]
    corrupt_reference = replace(
        game.unique_prefix_fixture,
        sequence_number=duplicate_layout.sequence_number,
        cell_count=14,
        signature_prefix=duplicate_layout.signature[:28],
    )
    corrupt_game = replace(game, unique_prefix_fixture=corrupt_reference)

    with pytest.raises(FixtureValidationError) as error:
        validate_m1_fixture(replace(fixture, games=(corrupt_game, *fixture.games[1:])))

    assert error.value.code == FixtureErrorCode.PREFIX_INTEGRITY_ERROR
