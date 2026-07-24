from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest

ROOT = Path(__file__).resolve().parents[3]
SNAPSHOT_DIR = ROOT / "apps" / "mobile" / "assets" / "snapshot"
DATABASE_PATH = SNAPSHOT_DIR / "m1-snapshot.db"
MANIFEST_PATH = SNAPSHOT_DIR / "manifest.json"

EXACT_QUERY = """
    SELECT sequence_number, signature
    FROM layouts INDEXED BY idx_layouts_game_signature
    WHERE game_id = ? AND signature = ?
    ORDER BY sequence_number
"""
PREFIX_QUERY = """
    SELECT sequence_number, signature
    FROM layouts INDEXED BY idx_layouts_game_signature
    WHERE game_id = ? AND signature >= ? AND signature < ?
    ORDER BY signature, sequence_number
"""
CYCLIC_QUERY = """
    SELECT sequence_number, payout, cycle_segment
    FROM (
        SELECT sequence_number, payout, 0 AS cycle_segment
        FROM layouts
        WHERE game_id = ? AND sequence_number > ?

        UNION ALL

        SELECT sequence_number, payout, 1 AS cycle_segment
        FROM layouts
        WHERE game_id = ? AND sequence_number < ?
    )
    ORDER BY cycle_segment, sequence_number
"""


def _load_manifest() -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


@pytest.fixture
def connection() -> Iterator[sqlite3.Connection]:
    uri = f"{DATABASE_PATH.resolve().as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as database:
        yield database


def test_catalog_contains_complete_game_and_symbol_configuration(
    connection: sqlite3.Connection,
) -> None:
    manifest = _load_manifest()
    games = connection.execute(
        """
        SELECT
            id, code, rows, columns, spin_cost, signature_cell_width,
            layout_count, dataset_version, rules_version
        FROM games
        ORDER BY id
        """
    ).fetchall()
    symbol_counts = dict(
        connection.execute(
            """
            SELECT game_id, COUNT(*)
            FROM symbols
            GROUP BY game_id
            ORDER BY game_id
            """
        )
    )

    assert len(games) == manifest["gameCount"] == 3
    assert [row[6] for row in games] == [1_000, 1_000, 1_000]
    assert [symbol_counts[row[0]] for row in games] == [
        game["symbolCount"] for game in manifest["games"]
    ]


def test_exact_lookup_reproduces_unique_duplicate_and_not_found_cases(
    connection: sqlite3.Connection,
) -> None:
    game = _load_manifest()["games"][0]
    game_id = game["id"]
    unique_reference = game["uniquePrefixFixture"]
    unique_row = connection.execute(
        """
        SELECT signature
        FROM layouts
        WHERE game_id = ? AND sequence_number = ?
        """,
        (game_id, unique_reference["sequenceNumber"]),
    ).fetchone()
    assert unique_row is not None

    unique_matches = connection.execute(
        EXACT_QUERY,
        (game_id, unique_row[0]),
    ).fetchall()
    duplicate_reference = game["duplicateFixtures"][0]
    duplicate_matches = connection.execute(
        EXACT_QUERY,
        (game_id, duplicate_reference["signature"]),
    ).fetchall()
    missing_matches = connection.execute(
        EXACT_QUERY,
        (game_id, "99" * 15),
    ).fetchall()

    assert unique_matches == [(unique_reference["sequenceNumber"], unique_row[0])]
    assert [row[0] for row in duplicate_matches] == duplicate_reference["sequenceNumbers"]
    assert missing_matches == []


def test_prefix_lookup_reproduces_empty_unique_ambiguous_and_missing_cases(
    connection: sqlite3.Connection,
) -> None:
    game = _load_manifest()["games"][0]
    game_id = game["id"]
    unique_reference = game["uniquePrefixFixture"]
    unique_prefix = unique_reference["signaturePrefix"]

    empty_matches = connection.execute(
        PREFIX_QUERY,
        (game_id, "", ":"),
    ).fetchall()
    unique_matches = connection.execute(
        PREFIX_QUERY,
        (game_id, unique_prefix, f"{unique_prefix}:"),
    ).fetchall()
    ambiguous_prefix = unique_matches[0][1][:2]
    ambiguous_matches = connection.execute(
        PREFIX_QUERY,
        (game_id, ambiguous_prefix, f"{ambiguous_prefix}:"),
    ).fetchall()
    missing_matches = connection.execute(
        PREFIX_QUERY,
        (game_id, "99", "99:"),
    ).fetchall()

    assert len(empty_matches) == game["layoutCount"]
    assert len(unique_matches) == 1
    assert unique_matches[0][0] == unique_reference["sequenceNumber"]
    assert len(ambiguous_matches) > 1
    assert missing_matches == []


def test_cyclic_query_returns_exactly_n_minus_one_rows_in_domain_order(
    connection: sqlite3.Connection,
) -> None:
    game = _load_manifest()["games"][0]
    game_id = game["id"]
    layout_count = game["layoutCount"]
    start_sequence = 99

    rows = connection.execute(
        CYCLIC_QUERY,
        (game_id, start_sequence, game_id, start_sequence),
    ).fetchall()

    expected_sequences = list(range(100, layout_count + 1)) + list(range(1, 99))
    assert len(rows) == layout_count - 1
    assert [row[0] for row in rows] == expected_sequences
    assert rows[901][0] == 1
    assert sum(row[1] for row in rows) == 310


def test_repository_queries_use_signature_index_and_sequence_primary_key(
    connection: sqlite3.Connection,
) -> None:
    exact_plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT COUNT(*)
        FROM layouts INDEXED BY idx_layouts_game_signature
        WHERE game_id = ? AND signature = ?
        """,
        (1, "020508"),
    ).fetchall()
    prefix_plan = connection.execute(
        """
        EXPLAIN QUERY PLAN
        SELECT COUNT(*)
        FROM layouts INDEXED BY idx_layouts_game_signature
        WHERE game_id = ? AND signature >= ? AND signature < ?
        """,
        (1, "02", "02:"),
    ).fetchall()
    cyclic_plan = connection.execute(
        f"EXPLAIN QUERY PLAN {CYCLIC_QUERY}",
        (1, 99, 1, 99),
    ).fetchall()

    exact_details = " ".join(row[3] for row in exact_plan)
    prefix_details = " ".join(row[3] for row in prefix_plan)
    cyclic_details = " ".join(row[3] for row in cyclic_plan)
    assert "COVERING INDEX idx_layouts_game_signature" in exact_details
    assert "COVERING INDEX idx_layouts_game_signature" in prefix_details
    assert cyclic_details.count("USING PRIMARY KEY") == 2
