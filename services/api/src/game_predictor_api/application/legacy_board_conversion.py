"""Conversion of the remaining ``legacy_file`` boards to ``virtual_source`` (TASK-0791).

D-467 S6: every board and review cell ends in the single virtual data mode.
A legacy board keeps its current corners and qualification; its cells are
rendered through the same path as a manual virtual geometry save
(:meth:`VirtualGridGeometryService.prepare_legacy_conversion`) and persisted
as a new ``virtual_source`` revision numbered by the TASK-0702 rule.

Human decisions are preserved explicitly (the conversion does not change the
geometry, only its asset representation): ``assigned_symbol_id``,
``assignment_source``, ``review_state``, ``quality_issue``, the verification
outcome and ``last_reviewed_by``/``last_reviewed_at`` stay as they are, an
approval is rebound to the new render of the same corners, the review item is
neither reopened nor resolved, and an append-only ``geometry_invalidated``
event records the provenance change with both sides of every field.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from game_predictor_api.application.virtual_grid_geometry import (
    LegacyConversionTarget,
    PreparedVirtualGridGeometrySource,
    VirtualGridGeometryService,
)

LEGACY_BOARD_CONVERSION_ACTOR = "system:legacy-board-conversion-v1"

# Board-level reasons that keep a board out of ``--execute`` (preview reports
# them; the conversion of its source is skipped and the exit code is non-zero).
NO_SOURCE_CONTEXT_CODES = frozenset(
    {
        "LEGACY_CONVERSION_SOURCE_GEOMETRY_MISSING",
        "LEGACY_CONVERSION_SOURCE_METADATA_INCOMPLETE",
        "LEGACY_CONVERSION_SOURCE_GEOMETRY_INVALID",
        "LEGACY_CONVERSION_SOURCE_ASSET_UNAVAILABLE",
    }
)


@dataclass(frozen=True, slots=True)
class LegacyConversionBoardPlan:
    """Read-only facts about one ``legacy_file`` board before its conversion."""

    recognized_board_id: UUID
    review_item_id: UUID | None
    source_image_id: UUID
    item_status: str | None
    sequence_number: int | None
    geometry_revision: int
    sequence_geometry_revision: int | None
    owned_cell_count: int
    assigned_cell_count: int
    human_decision_cell_count: int
    approved_cell_count: int
    target: LegacyConversionTarget | None
    problems: tuple[str, ...] = ()

    @property
    def next_geometry_revision(self) -> int:
        floor = self.geometry_revision
        if self.sequence_geometry_revision is not None:
            floor = max(floor, self.sequence_geometry_revision)
        return floor + 1

    @property
    def has_source_context(self) -> bool:
        return not NO_SOURCE_CONTEXT_CODES.intersection(self.problems)


@dataclass(frozen=True, slots=True)
class LegacyConversionSourcePlan:
    game_id: UUID
    source_image_id: UUID
    boards: tuple[LegacyConversionBoardPlan, ...]

    @property
    def problems(self) -> tuple[str, ...]:
        return tuple(sorted({problem for board in self.boards for problem in board.problems}))


@dataclass(frozen=True, slots=True)
class LegacyConversionBoardResult:
    recognized_board_id: UUID
    review_item_id: UUID
    previous_geometry_revision: int
    geometry_revision: int
    converted_cell_count: int
    preserved_decision_cell_count: int
    render_manifest_written: bool


@dataclass(frozen=True, slots=True)
class LegacyConversionSourceResult:
    source_image_id: UUID
    source_geometry_revision_id: UUID | None
    boards: tuple[LegacyConversionBoardResult, ...] = field(default_factory=tuple)


class LegacyBoardConversionError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class LegacyBoardConversionRepository(Protocol):
    def legacy_conversion_source_ids(self, *, game_id: UUID) -> tuple[UUID, ...]: ...

    def legacy_conversion_plan(
        self, *, game_id: UUID, source_image_id: UUID, lock: bool
    ) -> LegacyConversionSourcePlan: ...

    def convert_legacy_source(
        self,
        *,
        plan: LegacyConversionSourcePlan,
        prepared: PreparedVirtualGridGeometrySource,
        actor: str,
        created_at: datetime,
    ) -> LegacyConversionSourceResult: ...


class LegacyBoardConversionService:
    """One source per call; the caller owns the transaction around it."""

    def __init__(
        self,
        repository: LegacyBoardConversionRepository,
        virtual_geometry: VirtualGridGeometryService,
    ) -> None:
        self._repository = repository
        self._virtual_geometry = virtual_geometry

    def source_ids(self, game_id: UUID) -> tuple[UUID, ...]:
        return self._repository.legacy_conversion_source_ids(game_id=game_id)

    def plan(self, *, game_id: UUID, source_image_id: UUID) -> LegacyConversionSourcePlan:
        return self._repository.legacy_conversion_plan(
            game_id=game_id, source_image_id=source_image_id, lock=False
        )

    def render_check(self, plan: LegacyConversionSourcePlan) -> PreparedVirtualGridGeometrySource:
        """Render the source in memory without any write (preview ``--render``)."""

        return self._virtual_geometry.prepare_legacy_conversion(
            _targets(plan), actor=LEGACY_BOARD_CONVERSION_ACTOR
        )

    def convert_source(
        self,
        *,
        game_id: UUID,
        source_image_id: UUID,
        created_at: datetime,
        actor: str = LEGACY_BOARD_CONVERSION_ACTOR,
    ) -> LegacyConversionSourceResult:
        """Lock, re-read, render and persist every legacy board of one source.

        Idempotent: a source without ``legacy_file`` boards returns an empty
        result.  A board with a problem aborts the whole source (nothing is
        written) so the operator sees it in the report.
        """

        plan = self._repository.legacy_conversion_plan(
            game_id=game_id, source_image_id=source_image_id, lock=True
        )
        if not plan.boards:
            return LegacyConversionSourceResult(
                source_image_id=source_image_id, source_geometry_revision_id=None
            )
        if plan.problems:
            raise LegacyBoardConversionError(
                plan.problems[0],
                "A legacy board of this source cannot be converted: " + ", ".join(plan.problems),
            )
        prepared = self._virtual_geometry.prepare_legacy_conversion(_targets(plan), actor=actor)
        return self._repository.convert_legacy_source(
            plan=plan, prepared=prepared, actor=actor, created_at=created_at
        )


def _targets(plan: LegacyConversionSourcePlan) -> Sequence[LegacyConversionTarget]:
    targets: list[LegacyConversionTarget] = []
    for board in plan.boards:
        if board.target is None:
            raise LegacyBoardConversionError(
                board.problems[0] if board.problems else "LEGACY_CONVERSION_CONTEXT_MISSING",
                "A legacy board has no renderable virtual context.",
            )
        targets.append(board.target)
    return tuple(targets)


__all__ = [
    "LEGACY_BOARD_CONVERSION_ACTOR",
    "NO_SOURCE_CONTEXT_CODES",
    "LegacyBoardConversionError",
    "LegacyBoardConversionRepository",
    "LegacyBoardConversionService",
    "LegacyConversionBoardPlan",
    "LegacyConversionBoardResult",
    "LegacyConversionSourcePlan",
    "LegacyConversionSourceResult",
]
