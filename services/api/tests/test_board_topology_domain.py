from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from game_predictor_api.domain.board_topology import (
    BoardTopology,
    BoardTopologyError,
    ensure_rules_version_matches_topology,
    pin_board_topology,
)
from game_predictor_api.domain.rules import RulesVersion, RulesVersionStatus


def _rules_version(*, rows: int = 3, columns: int = 5) -> RulesVersion:
    return RulesVersion(
        id=UUID(int=2),
        game_id=UUID(int=1),
        version=1,
        rows=rows,
        columns=columns,
        spin_cost=10,
        status=RulesVersionStatus.DRAFT,
        created_at=datetime(2026, 8, 28, tzinfo=UTC),
        published_at=None,
    )


def test_topology_exposes_row_major_coordinates() -> None:
    topology = BoardTopology(rows=2, columns=4)

    assert topology.cell_count == 8
    assert topology.coordinates(6) == (1, 2)
    topology.validate_coordinates(cell_index=7, row_index=1, column_index=3)

    with pytest.raises(BoardTopologyError) as error:
        topology.validate_coordinates(cell_index=7, row_index=0, column_index=3)

    assert error.value.code == "GAME_BOARD_TOPOLOGY_CELL_COORDINATES_INVALID"


def test_topology_must_be_defined_by_rules_before_import() -> None:
    with pytest.raises(BoardTopologyError) as error:
        pin_board_topology(None)

    assert error.value.code == "GAME_BOARD_TOPOLOGY_REQUIRED"


def test_pinned_topology_allows_new_rules_only_with_the_same_dimensions() -> None:
    source = _rules_version()
    pinned = pin_board_topology(source)

    ensure_rules_version_matches_topology(
        replace(source, id=UUID(int=3), version=2),
        pinned=pinned,
    )

    with pytest.raises(BoardTopologyError) as error:
        ensure_rules_version_matches_topology(
            replace(source, id=UUID(int=4), version=2, columns=4),
            pinned=pinned,
        )

    assert error.value.code == "GAME_BOARD_TOPOLOGY_LOCKED"
    assert error.value.details["rows"] == 3
    assert error.value.details["columns"] == 5
