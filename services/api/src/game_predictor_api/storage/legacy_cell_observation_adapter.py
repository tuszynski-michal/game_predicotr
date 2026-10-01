"""The only runtime reader of ``cell_observations`` (D-467, TASK-0758).

After TASK-0758 virtual boards read render identities from
``board_render_manifests`` and predictions from
``recognized_boards.cells_prediction``; legacy boards with a geometry revision
read their crops from ``image_board_geometry_revisions.crop_artifacts``.  One
case still has no other source: a ``legacy_file`` board at geometry revision 0
whose base crops (path, checksum, cropper version) and per-cell predictions
exist only as cell observations.  The operator database has none of them
(2026-10-01: all 461 legacy boards of game 777 are at revision 1 or 2); they
are produced by the legacy import engine policy and by the benchmark fixtures.

This adapter isolates that read so S5 can drop the table: S5 deletes this
module after TASK-0760 stops creating legacy revision-0 boards, and the
callers then fail closed for such a board.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardSearchFastDocumentModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
)

LEGACY_ASSET_MODE = "legacy_file"


@dataclass(frozen=True, slots=True)
class LegacyBaseCell:
    """One legacy base crop of a revision-0 board, with its import prediction."""

    row_index: int
    column_index: int
    crop_relative_path: str | None
    crop_checksum_sha256: str
    cropper_version: str
    prediction: Mapping[str, object]


def legacy_base_cells(
    session: Session, board_ids: Sequence[UUID]
) -> dict[UUID, tuple[LegacyBaseCell, ...]]:
    """Row-major legacy base cells for each board (only ``legacy_file`` rows)."""

    cells_by_board: dict[UUID, list[LegacyBaseCell]] = defaultdict(list)
    if not board_ids:
        return {}
    for observation in session.scalars(
        select(CellObservationModel)
        .where(
            CellObservationModel.recognized_board_id.in_(list(board_ids)),
            CellObservationModel.asset_mode == LEGACY_ASSET_MODE,
        )
        .order_by(
            CellObservationModel.recognized_board_id,
            CellObservationModel.row_index,
            CellObservationModel.column_index,
        )
    ):
        cells_by_board[observation.recognized_board_id].append(
            LegacyBaseCell(
                row_index=observation.row_index,
                column_index=observation.column_index,
                crop_relative_path=observation.crop_relative_path,
                crop_checksum_sha256=observation.crop_checksum_sha256,
                cropper_version=observation.cropper_version,
                prediction=cast(Mapping[str, object], observation.prediction),
            )
        )
    return {board_id: tuple(cells) for board_id, cells in cells_by_board.items()}


def legacy_base_cells_for_board(session: Session, board_id: UUID) -> tuple[LegacyBaseCell, ...]:
    return legacy_base_cells(session, (board_id,)).get(board_id, ())


def legacy_review_items_with_stale_base_crop(session: Session, game_id: UUID) -> tuple[UUID, ...]:
    """Selected legacy revision-0 review cells whose base observation changed.

    The legacy half of the former stale-base-crop check; the virtual half
    compares the revision-0 render manifest instead.
    """

    statement = (
        select(ImageSymbolReviewCellModel.review_item_id)
        .join(
            ImageBoardSearchFastDocumentModel,
            ImageBoardSearchFastDocumentModel.review_item_id
            == ImageSymbolReviewCellModel.review_item_id,
        )
        .join(
            RecognizedBoardModel,
            RecognizedBoardModel.id == ImageSymbolReviewCellModel.recognized_board_id,
        )
        .outerjoin(
            CellObservationModel,
            and_(
                CellObservationModel.recognized_board_id
                == ImageSymbolReviewCellModel.recognized_board_id,
                CellObservationModel.row_index == ImageSymbolReviewCellModel.row_index,
                CellObservationModel.column_index == ImageSymbolReviewCellModel.column_index,
            ),
        )
        .where(
            ImageBoardSearchFastDocumentModel.game_id == game_id,
            # Explicit partition key: the session role bypasses RLS.
            ImageSymbolReviewCellModel.game_id == game_id,
            RecognizedBoardModel.geometry_revision == 0,
            RecognizedBoardModel.asset_mode == LEGACY_ASSET_MODE,
            ImageSymbolReviewCellModel.source_available.is_(True),
            or_(
                CellObservationModel.id.is_(None),
                CellObservationModel.crop_checksum_sha256
                != ImageSymbolReviewCellModel.crop_checksum_sha256,
                CellObservationModel.crop_relative_path
                != ImageSymbolReviewCellModel.crop_relative_path,
                CellObservationModel.cropper_version != ImageSymbolReviewCellModel.cropper_version,
                CellObservationModel.asset_mode != ImageSymbolReviewCellModel.asset_mode,
                CellObservationModel.source_geometry_revision_id
                != ImageSymbolReviewCellModel.source_geometry_revision_id,
                CellObservationModel.logical_cell_key
                != ImageSymbolReviewCellModel.logical_cell_key,
                CellObservationModel.render_spec_checksum_sha256
                != ImageSymbolReviewCellModel.render_spec_checksum_sha256,
                CellObservationModel.rendered_pixel_checksum_sha256
                != ImageSymbolReviewCellModel.rendered_pixel_checksum_sha256,
            ),
        )
        .distinct()
        .order_by(ImageSymbolReviewCellModel.review_item_id)
    )
    return tuple(session.scalars(statement))


__all__ = [
    "LegacyBaseCell",
    "legacy_base_cells",
    "legacy_base_cells_for_board",
    "legacy_review_items_with_stale_base_crop",
]
