"""Read side of per-board render manifests (D-467, TASK-0758).

Every runtime reader of a virtual board's current cell render identities
(Reviewer mapper, symbol-review projection, re-inference, manual geometry)
reads ``board_render_manifests`` for the board's *current* geometry revision.
The manifest has the ``virtual_render_spec`` shape: ``cells[]`` entries carry
``cellIndex``, ``cropSampleId``, ``renderSpec``, the render/pixel checksums and
the logical v1/v2 keys; the row carries ``extractor_version`` and
``source_geometry_revision_id``.

Rule (TASK-0757): no manifest row <=> the board has no renderable cells.  A
reader must therefore treat a missing row as zero cells and fail closed when
the board declares available cells.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.storage.models import BoardRenderManifestModel, RecognizedBoardModel


class BoardRenderManifestReadError(ValueError):
    """A persisted manifest does not have the shared cells shape."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class CurrentBoardRenderManifest:
    """The render manifest of one board at its current geometry revision."""

    recognized_board_id: UUID
    geometry_revision: int
    source_geometry_revision_id: UUID
    extractor_version: str
    manifest_checksum_sha256: str
    cells: tuple[Mapping[str, object], ...]

    @property
    def cell_indices(self) -> tuple[int, ...]:
        return tuple(cast(int, cell["cellIndex"]) for cell in self.cells)

    def cells_by_index(self) -> dict[int, Mapping[str, object]]:
        return {cast(int, cell["cellIndex"]): cell for cell in self.cells}


def current_render_manifest_from_record(
    record: BoardRenderManifestModel,
) -> CurrentBoardRenderManifest:
    """Validate the stored shape; cells are returned sorted by ``cellIndex``.

    Checksums were verified when the manifest was written (writer or
    backfill) and the row is immutable, so reads only check the shape.
    """

    document = record.cells
    raw_cells = document.get("cells") if isinstance(document, Mapping) else None
    if not isinstance(raw_cells, list) or not raw_cells:
        raise BoardRenderManifestReadError(
            "BOARD_RENDER_MANIFEST_SHAPE_INVALID",
            "A board render manifest needs a non-empty cells array.",
        )
    by_index: dict[int, Mapping[str, object]] = {}
    for raw in raw_cells:
        index = raw.get("cellIndex") if isinstance(raw, Mapping) else None
        if (
            not isinstance(raw, Mapping)
            or not isinstance(index, int)
            or isinstance(index, bool)
            or index < 0
            or index in by_index
            or not isinstance(raw.get("renderSpec"), Mapping)
        ):
            raise BoardRenderManifestReadError(
                "BOARD_RENDER_MANIFEST_SHAPE_INVALID",
                "A board render manifest cell is invalid or duplicated.",
            )
        by_index[index] = cast(Mapping[str, object], raw)
    return CurrentBoardRenderManifest(
        recognized_board_id=record.recognized_board_id,
        geometry_revision=record.geometry_revision,
        source_geometry_revision_id=record.source_geometry_revision_id,
        extractor_version=record.extractor_version,
        manifest_checksum_sha256=record.manifest_checksum_sha256,
        cells=tuple(by_index[index] for index in sorted(by_index)),
    )


def load_current_render_manifests(
    session: Session,
    *,
    game_id: UUID,
    boards: Iterable[RecognizedBoardModel],
) -> dict[UUID, CurrentBoardRenderManifest]:
    """Load the current-revision manifests of the given virtual boards.

    ``game_id`` keeps the read on the primary key and one partition.  Legacy
    boards never have a manifest and are skipped.
    """

    revisions_by_board: dict[UUID, int] = {
        board.id: board.geometry_revision
        for board in boards
        if board.asset_mode == "virtual_source"
    }
    if not revisions_by_board:
        return {}
    board_ids_by_revision: dict[int, list[UUID]] = defaultdict(list)
    for board_id, revision in revisions_by_board.items():
        board_ids_by_revision[revision].append(board_id)
    manifests: dict[UUID, CurrentBoardRenderManifest] = {}
    for revision, board_ids in sorted(board_ids_by_revision.items()):
        for record in session.scalars(
            select(BoardRenderManifestModel).where(
                BoardRenderManifestModel.game_id == game_id,
                BoardRenderManifestModel.recognized_board_id.in_(board_ids),
                BoardRenderManifestModel.geometry_revision == revision,
            )
        ):
            manifests[record.recognized_board_id] = current_render_manifest_from_record(record)
    return manifests


def load_current_render_manifest(
    session: Session,
    *,
    game_id: UUID,
    board: RecognizedBoardModel,
) -> CurrentBoardRenderManifest | None:
    return load_current_render_manifests(session, game_id=game_id, boards=(board,)).get(board.id)


__all__ = [
    "BoardRenderManifestReadError",
    "CurrentBoardRenderManifest",
    "current_render_manifest_from_record",
    "load_current_render_manifest",
    "load_current_render_manifests",
]
