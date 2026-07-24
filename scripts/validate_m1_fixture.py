"""Generate and validate the deterministic logical fixture for M1."""

from __future__ import annotations

import json

from game_predictor_worker.fixtures import generate_m1_fixture, validate_m1_fixture


def main() -> None:
    fixture = generate_m1_fixture()
    report = validate_m1_fixture(fixture)
    print(
        json.dumps(
            {
                "status": "ok",
                "fixtureFingerprint": report.fixture_fingerprint,
                "gameCount": report.game_count,
                "layoutCount": report.layout_count,
                "games": [
                    {
                        "gameCode": game.game_code,
                        "layoutCount": game.layout_count,
                        "duplicateGroupCount": game.duplicate_group_count,
                        "uniquePrefixCellCount": game.unique_prefix_cell_count,
                        "targetGoldenCases": [
                            {
                                "code": golden.code,
                                "startSequenceNumber": golden.start_sequence_number,
                            }
                            for golden in fixture_game.target_golden_fixtures
                        ],
                    }
                    for game, fixture_game in zip(
                        report.games,
                        fixture.games,
                        strict=True,
                    )
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
