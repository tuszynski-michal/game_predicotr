"""Pure domain rules for the board topology owned by a game's rules."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from game_predictor_api.domain.rules import RulesVersion, validate_dimensions


class BoardTopologyError(ValueError):
    """Stable topology failure translated by later application boundaries."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True, slots=True)
class BoardTopology:
    """Immutable row-major dimensions of one logical game board."""

    rows: int
    columns: int

    def __post_init__(self) -> None:
        try:
            validate_dimensions(self.rows, self.columns)
        except ValueError as error:
            raise BoardTopologyError(
                "GAME_BOARD_TOPOLOGY_INVALID",
                "Board topology rows and columns must be valid rules dimensions.",
                details={"rows": self.rows, "columns": self.columns},
            ) from error

    @property
    def cell_count(self) -> int:
        return self.rows * self.columns

    def coordinates(self, cell_index: int) -> tuple[int, int]:
        if not 0 <= cell_index < self.cell_count:
            raise BoardTopologyError(
                "GAME_BOARD_TOPOLOGY_CELL_INDEX_INVALID",
                "A cell index must belong to the configured board topology.",
                details={"cellIndex": cell_index, "cellCount": self.cell_count},
            )
        return divmod(cell_index, self.columns)

    def validate_coordinates(
        self,
        *,
        cell_index: int,
        row_index: int,
        column_index: int,
    ) -> None:
        expected_row, expected_column = self.coordinates(cell_index)
        if (row_index, column_index) != (expected_row, expected_column):
            raise BoardTopologyError(
                "GAME_BOARD_TOPOLOGY_CELL_COORDINATES_INVALID",
                "Cell coordinates must follow the configured row-major topology.",
                details={
                    "cellIndex": cell_index,
                    "rowIndex": row_index,
                    "columnIndex": column_index,
                    "expectedRowIndex": expected_row,
                    "expectedColumnIndex": expected_column,
                },
            )


LEGACY_IMAGE_BOARD_TOPOLOGY = BoardTopology(rows=3, columns=5)


@dataclass(frozen=True, slots=True)
class PinnedBoardTopology:
    """The rules version that permanently defines one game's board dimensions."""

    game_id: UUID
    rules_version_id: UUID
    topology: BoardTopology


def pin_board_topology(rules_version: RulesVersion | None) -> PinnedBoardTopology:
    """Create a topology pin from the rules selected before the first board import."""

    if rules_version is None:
        raise BoardTopologyError(
            "GAME_BOARD_TOPOLOGY_REQUIRED",
            "A rules version must define board dimensions before boards can be imported.",
        )
    return PinnedBoardTopology(
        game_id=rules_version.game_id,
        rules_version_id=rules_version.id,
        topology=BoardTopology(rows=rules_version.rows, columns=rules_version.columns),
    )


def ensure_rules_version_matches_topology(
    rules_version: RulesVersion,
    *,
    pinned: PinnedBoardTopology,
) -> None:
    """Reject changing a game's dimensions after its topology was pinned."""

    requested = BoardTopology(rows=rules_version.rows, columns=rules_version.columns)
    if rules_version.game_id != pinned.game_id or requested != pinned.topology:
        raise BoardTopologyError(
            "GAME_BOARD_TOPOLOGY_LOCKED",
            "Board dimensions cannot change after the game topology is pinned.",
            details={
                "gameId": str(pinned.game_id),
                "topologyRulesVersionId": str(pinned.rules_version_id),
                "rows": pinned.topology.rows,
                "columns": pinned.topology.columns,
                "requestedRulesVersionId": str(rules_version.id),
                "requestedRows": requested.rows,
                "requestedColumns": requested.columns,
            },
        )


__all__ = [
    "LEGACY_IMAGE_BOARD_TOPOLOGY",
    "BoardTopology",
    "BoardTopologyError",
    "PinnedBoardTopology",
    "ensure_rules_version_matches_topology",
    "pin_board_topology",
]
