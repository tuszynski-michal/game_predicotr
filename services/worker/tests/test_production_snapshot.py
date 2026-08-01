from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from contextlib import closing
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_worker.payouts.readiness import (
    PayoutCompletenessFacts,
    PayoutReadinessError,
)
from game_predictor_worker.snapshots import (
    PRODUCTION_SNAPSHOT_SCHEMA_VERSION,
    SQLITE_APPLICATION_ID,
    ProductionSnapshotError,
    ProductionSnapshotGenerator,
    ProductionSnapshotSpec,
    SnapshotGameSelection,
    SnapshotGameSource,
    SnapshotLayout,
    SnapshotSymbol,
)

DATASET_ALPHA = UUID("10000000-0000-0000-0000-000000000001")
RULES_ALPHA = UUID("20000000-0000-0000-0000-000000000001")
GAME_ALPHA = UUID("30000000-0000-0000-0000-000000000001")
DATASET_ZETA = UUID("10000000-0000-0000-0000-000000000002")
RULES_ZETA = UUID("20000000-0000-0000-0000-000000000002")
GAME_ZETA = UUID("30000000-0000-0000-0000-000000000002")

ALPHA_SELECTION = SnapshotGameSelection(DATASET_ALPHA, RULES_ALPHA, "payout-v2")
ZETA_SELECTION = SnapshotGameSelection(DATASET_ZETA, RULES_ZETA, "payout-v2")
CREATED_AT = datetime(2026, 7, 27, 12, 30, tzinfo=UTC)


def _source(
    selection: SnapshotGameSelection,
    *,
    game_id: UUID,
    game_code: str,
    dataset_version: int,
    rules_version: int,
    layout_count: int,
) -> SnapshotGameSource:
    return SnapshotGameSource(
        game_id=game_id,
        game_code=game_code,
        game_name=f"{game_code.title()} Game",
        dataset_version_id=selection.dataset_version_id,
        dataset_version=dataset_version,
        rules_version_id=selection.rules_version_id,
        rules_version=rules_version,
        algorithm_version=selection.algorithm_version,
        rows=1,
        columns=2,
        spin_cost=10,
        signature_cell_width=2,
        layout_count=layout_count,
        symbols=(
            SnapshotSymbol(
                2,
                "S2",
                "Symbol 2",
                False,
                2,
                "symbols/s2.png",
                name_pl="Dwójka",
                name_en="Two",
            ),
            SnapshotSymbol(1, "S1", "Symbol 1", False, 1, None),
        ),
    )


ALPHA_SOURCE = _source(
    ALPHA_SELECTION,
    game_id=GAME_ALPHA,
    game_code="alpha",
    dataset_version=11,
    rules_version=21,
    layout_count=3,
)
ZETA_SOURCE = _source(
    ZETA_SELECTION,
    game_id=GAME_ZETA,
    game_code="zeta",
    dataset_version=12,
    rules_version=22,
    layout_count=2,
)

ALPHA_LAYOUTS = (
    SnapshotLayout(1, "0102", 0),
    SnapshotLayout(2, "0102", 30),
    SnapshotLayout(3, "0201", 5),
)
ZETA_LAYOUTS = (
    SnapshotLayout(1, "0202", 7),
    SnapshotLayout(2, "0101", 0),
)


class FakeSnapshotRepository:
    def __init__(
        self,
        *,
        sources: dict[SnapshotGameSelection, SnapshotGameSource] | None = None,
        layouts: dict[SnapshotGameSelection, tuple[SnapshotLayout, ...]] | None = None,
        facts: dict[SnapshotGameSelection, PayoutCompletenessFacts] | None = None,
    ) -> None:
        self.sources = sources or {
            ALPHA_SELECTION: ALPHA_SOURCE,
            ZETA_SELECTION: ZETA_SOURCE,
        }
        self.layouts = layouts or {
            ALPHA_SELECTION: ALPHA_LAYOUTS,
            ZETA_SELECTION: ZETA_LAYOUTS,
        }
        self.facts = facts or {
            selection: _complete_facts(source) for selection, source in self.sources.items()
        }
        self.batch_calls: list[tuple[SnapshotGameSelection, int, int]] = []

    def get_completeness_facts(
        self,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> PayoutCompletenessFacts | None:
        return self.facts.get(
            SnapshotGameSelection(
                dataset_version_id,
                rules_version_id,
                algorithm_version,
            )
        )

    def load_snapshot_game(
        self,
        selection: SnapshotGameSelection,
    ) -> SnapshotGameSource | None:
        return self.sources.get(selection)

    def list_snapshot_layout_batch(
        self,
        selection: SnapshotGameSelection,
        *,
        after_sequence_number: int,
        limit: int,
    ) -> Sequence[SnapshotLayout]:
        self.batch_calls.append((selection, after_sequence_number, limit))
        return tuple(
            layout
            for layout in self.layouts.get(selection, ())
            if layout.sequence_number > after_sequence_number
        )[:limit]


def _complete_facts(source: SnapshotGameSource) -> PayoutCompletenessFacts:
    return PayoutCompletenessFacts(
        dataset_version_id=source.dataset_version_id,
        rules_version_id=source.rules_version_id,
        algorithm_version=source.algorithm_version,
        dataset_game_id=source.game_id,
        rules_game_id=source.game_id,
        dataset_status=DatasetVersionStatus.PUBLISHED,
        rules_status=RulesVersionStatus.PUBLISHED,
        dataset_rows=source.rows,
        dataset_columns=source.columns,
        rules_rows=source.rows,
        rules_columns=source.columns,
        layout_count=source.layout_count,
        payout_count=source.layout_count,
        missing_payout_count=0,
        missing_sequence_numbers=(),
        missing_sequences_truncated=False,
        missing_audit_count=0,
    )


def _spec(
    games: tuple[SnapshotGameSelection, ...] = (
        ZETA_SELECTION,
        ALPHA_SELECTION,
    ),
) -> ProductionSnapshotSpec:
    return ProductionSnapshotSpec(
        release_version="release-2026.07.27",
        created_at=CREATED_AT,
        games=games,
    )


def test_generator_writes_production_schema_and_bounded_ordered_content(
    tmp_path: Path,
) -> None:
    repository = FakeSnapshotRepository()
    database_path = tmp_path / "production.db"

    result = ProductionSnapshotGenerator(repository, batch_size=2).generate(
        database_path,
        _spec(),
    )

    with closing(sqlite3.connect(database_path)) as connection:
        tables = {
            name
            for (name,) in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            )
        }
        metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        games = connection.execute(
            """
            SELECT
                id, code, dataset_version, rules_version, layout_count
            FROM games
            ORDER BY id
            """
        ).fetchall()
        symbols = connection.execute(
            """
            SELECT game_id, mobile_code, name_pl, name_en, image_asset_key
            FROM symbols
            ORDER BY game_id, mobile_code
            """
        ).fetchall()
        alpha_duplicates = connection.execute(
            """
            SELECT sequence_number
            FROM layouts
            WHERE game_id = 1 AND signature = '0102'
            ORDER BY sequence_number
            """
        ).fetchall()
        alpha_prefix = connection.execute(
            """
            SELECT sequence_number
            FROM layouts
            WHERE game_id = 1 AND signature >= '01' AND signature < '01:'
            ORDER BY sequence_number
            """
        ).fetchall()
        alpha_cycle = connection.execute(
            """
            SELECT sequence_number, payout
            FROM (
                SELECT sequence_number, payout
                FROM layouts
                WHERE game_id = 1 AND sequence_number > 2
                ORDER BY sequence_number
            )
            UNION ALL
            SELECT sequence_number, payout
            FROM (
                SELECT sequence_number, payout
                FROM layouts
                WHERE game_id = 1 AND sequence_number < 2
                ORDER BY sequence_number
            )
            """
        ).fetchall()
        index_sql = connection.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE name = 'idx_layouts_game_signature'
            """
        ).fetchone()
        user_version = connection.execute("PRAGMA user_version").fetchone()
        application_id = connection.execute("PRAGMA application_id").fetchone()

    assert result.game_count == 2
    assert result.symbol_count == 4
    assert result.layout_count == 5
    assert len(result.logical_content_sha256) == 64
    assert len(result.snapshot_file_sha256) == 64
    assert tables == {"metadata", "games", "symbols", "layouts"}
    assert metadata == {
        "algorithm_version": "payout-v2",
        "content_checksum": result.logical_content_sha256,
        "created_at": "2026-07-27T12:30:00.000000Z",
        "game_count": "2",
        "layout_count": "5",
        "release_version": "release-2026.07.27",
        "snapshot_schema_version": "3",
    }
    assert not any(key.startswith("fixture_") for key in metadata)
    assert games == [(1, "alpha", 11, 21, 3), (2, "zeta", 12, 22, 2)]
    assert symbols == [
        (1, 1, None, None, None),
        (1, 2, "Dwójka", "Two", "symbols/s2.png"),
        (2, 1, None, None, None),
        (2, 2, "Dwójka", "Two", "symbols/s2.png"),
    ]
    assert alpha_duplicates == [(1,), (2,)]
    assert alpha_prefix == [(1,), (2,)]
    assert alpha_cycle == [(3, 5), (1, 0)]
    assert index_sql is not None
    assert "ON layouts(game_id, signature)" in index_sql[0]
    assert user_version == (PRODUCTION_SNAPSHOT_SCHEMA_VERSION,)
    assert application_id == (SQLITE_APPLICATION_ID,)
    assert all(call[2] == 2 for call in repository.batch_calls)


def test_generation_is_byte_deterministic_and_input_order_independent(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.db"
    second_path = tmp_path / "second.db"

    first = ProductionSnapshotGenerator(FakeSnapshotRepository()).generate(
        first_path,
        _spec((ZETA_SELECTION, ALPHA_SELECTION)),
    )
    second = ProductionSnapshotGenerator(FakeSnapshotRepository()).generate(
        second_path,
        _spec((ALPHA_SELECTION, ZETA_SELECTION)),
    )

    assert first_path.read_bytes() == second_path.read_bytes()
    assert first.logical_content_sha256 == second.logical_content_sha256
    assert first.snapshot_file_sha256 == second.snapshot_file_sha256


def test_readiness_blocks_incomplete_exact_version_before_file_creation(
    tmp_path: Path,
) -> None:
    repository = FakeSnapshotRepository()
    repository.facts[ALPHA_SELECTION] = replace(
        repository.facts[ALPHA_SELECTION],
        payout_count=2,
        missing_payout_count=1,
        missing_sequence_numbers=(3,),
    )
    database_path = tmp_path / "blocked.db"

    with pytest.raises(PayoutReadinessError) as error:
        ProductionSnapshotGenerator(repository).generate(
            database_path,
            _spec((ALPHA_SELECTION,)),
        )

    assert error.value.code == "PAYOUTS_NOT_READY"
    assert database_path.exists() is False
    assert repository.batch_calls == []


def test_sequence_failure_leaves_no_partial_target(tmp_path: Path) -> None:
    repository = FakeSnapshotRepository(
        sources={ALPHA_SELECTION: ALPHA_SOURCE},
        layouts={
            ALPHA_SELECTION: (
                SnapshotLayout(1, "0102", 0),
                SnapshotLayout(3, "0201", 5),
            )
        },
    )
    database_path = tmp_path / "partial.db"

    with pytest.raises(ProductionSnapshotError) as error:
        ProductionSnapshotGenerator(repository, batch_size=2).generate(
            database_path,
            _spec((ALPHA_SELECTION,)),
        )

    assert error.value.code == "SNAPSHOT_SEQUENCE_INCOMPLETE"
    assert database_path.exists() is False
    assert list(tmp_path.iterdir()) == []


def test_existing_target_is_never_overwritten(tmp_path: Path) -> None:
    database_path = tmp_path / "existing.db"
    database_path.write_bytes(b"keep-me")

    with pytest.raises(ProductionSnapshotError) as error:
        ProductionSnapshotGenerator(FakeSnapshotRepository()).generate(
            database_path,
            _spec(),
        )

    assert error.value.code == "SNAPSHOT_TARGET_EXISTS"
    assert database_path.read_bytes() == b"keep-me"


def test_duplicate_game_selection_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ProductionSnapshotError) as error:
        ProductionSnapshotGenerator(FakeSnapshotRepository()).generate(
            tmp_path / "duplicate.db",
            _spec((ALPHA_SELECTION, ALPHA_SELECTION)),
        )

    assert error.value.code == "DUPLICATE_SNAPSHOT_GAME"


@pytest.mark.parametrize(
    ("spec", "code"),
    [
        (
            ProductionSnapshotSpec("", CREATED_AT, (ALPHA_SELECTION,)),
            "INVALID_SNAPSHOT_RELEASE_VERSION",
        ),
        (
            ProductionSnapshotSpec(
                "release-1",
                datetime(2026, 7, 27, 12, 30),
                (ALPHA_SELECTION,),
            ),
            "INVALID_SNAPSHOT_CREATED_AT",
        ),
        (
            ProductionSnapshotSpec("release-1", CREATED_AT, ()),
            "EMPTY_SNAPSHOT_SELECTION",
        ),
    ],
)
def test_invalid_build_spec_is_rejected_before_repository_access(
    tmp_path: Path,
    spec: ProductionSnapshotSpec,
    code: str,
) -> None:
    repository = FakeSnapshotRepository()

    with pytest.raises(ProductionSnapshotError) as error:
        ProductionSnapshotGenerator(repository).generate(
            tmp_path / "invalid.db",
            spec,
        )

    assert error.value.code == code
    assert repository.batch_calls == []
