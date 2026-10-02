"""TASK-0818: route boards with unknown search cells to grid correction."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import UUID, uuid4

from game_predictor_api.domain.image_symbol_reviews import (
    SymbolCellReviewAction,
    SymbolCellReviewError,
)

GAME_ID = UUID("bfc4f949-5c14-4850-b02a-db99610bcfa5")


def _script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "route_partial_boards_to_grid_correction.py"
    spec = spec_from_file_location("route_partial_boards_to_grid_correction", path)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    # The script defines a dataclass, which resolves its module by name.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _cells(script: ModuleType) -> tuple[Any, ...]:
    first, second = uuid4(), uuid4()

    def cell(item: UUID, sequence: int, index: int, issue: str) -> Any:
        return script.TargetCell(
            sequence_number=sequence,
            review_item_id=item,
            cell_review_id=uuid4(),
            cell_index=index,
            revision=3,
            geometry_revision=1,
            crop_sample_id="a" * 64,
            crop_checksum_sha256="b" * 64,
            quality_issue=issue,
        )

    return (
        cell(first, 10, 2, "unreadable"),
        cell(first, 10, 7, "unreadable"),
        cell(second, 11, 4, "partial_visibility"),
    )


def test_summary_counts_boards_and_cells_per_quality_issue() -> None:
    script = _script()

    report = script.summary(GAME_ID, _cells(script))

    assert (report["boardCount"], report["cellCount"]) == (2, 3)
    assert report["boardCountByQualityIssue"] == {"partial_visibility": 1, "unreadable": 1}
    assert report["sequenceSample"] == [10, 11]


def test_apply_marks_each_board_once_and_skips_a_board_that_changed() -> None:
    script = _script()
    cells = _cells(script)
    log: list[str] = []
    applied: list[tuple[Any, ...]] = []

    class _Session:
        def commit(self) -> None:
            log.append("commit")

    @contextmanager
    def sessions() -> Any:
        yield _Session()

    def apply_board(_session: Any, commands: tuple[Any, ...]) -> None:
        if len(commands) == 1:
            raise SymbolCellReviewError("SYMBOL_CELL_REVIEW_REVISION_CONFLICT", "changed")
        applied.append(commands)

    report = script.apply(sessions, GAME_ID, cells, apply_board=apply_board)

    assert report["routedBoardCount"] == 1
    assert report["skipped"] == [
        {"sequenceNumber": 11, "code": "SYMBOL_CELL_REVIEW_REVISION_CONFLICT"}
    ]
    assert log == ["commit"]
    (commands,) = applied
    assert [command.cell_review_id for command in commands] == [
        cells[0].cell_review_id,
        cells[1].cell_review_id,
    ]
    assert all(
        command.action is SymbolCellReviewAction.MARK_GRID_ISSUE
        and command.expected_revision == 3
        and command.expected_geometry_revision == 1
        and command.actor == script.ACTOR
        for command in commands
    )
