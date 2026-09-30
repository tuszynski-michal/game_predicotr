"""Write reference-library predictions for pending symbol cells (D-466).

One board is written per transaction through the existing prediction-revision
mechanism, so the current human-decision rules of the symbol-cell projection
apply unchanged. Nothing here approves a cell.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
    SymbolModel,
)
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

MODEL_VERSION = "symbol-reference-library-v1"
LIBRARY_CONFIDENCE = 0.99
ACTOR = "system:symbol-reference-library"


class ReferenceLibraryWriteError(RuntimeError):
    """A board could not be written consistently; its transaction must roll back."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class TargetCell:
    cell_review_id: UUID
    cell_index: int
    rendered_pixel_checksum_sha256: str
    old_symbol: str
    new_symbol: str
    shape_votes: int
    combined_votes: int


@dataclass(frozen=True, slots=True)
class BoardPlan:
    review_item_id: UUID
    recognized_board_id: UUID
    prediction_revision_id: UUID
    predictions_sha256: str
    targets: tuple[TargetCell, ...]


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def predictions_digest(predictions: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(canonical_json(list(predictions))).hexdigest()


def _cell_index(entry: Mapping[str, Any], columns: int) -> int:
    row, column = entry.get("rowIndex"), entry.get("columnIndex")
    if not isinstance(row, int) or not isinstance(column, int):
        raise ReferenceLibraryWriteError(
            "SYMBOL_REFERENCE_PREDICTION_INVALID", "A prediction entry has no cell position."
        )
    return row * columns + column


def rewrite_predictions(
    predictions: Sequence[Mapping[str, Any]],
    targets: Sequence[TargetCell],
    *,
    columns: int = 5,
) -> list[dict[str, Any]]:
    """Return a copy of a board's predictions with only the target cells replaced."""

    rewritten = [copy.deepcopy(dict(entry)) for entry in predictions]
    by_index: dict[int, dict[str, Any]] = {}
    for entry in rewritten:
        index = _cell_index(entry, columns)
        if index in by_index:
            raise ReferenceLibraryWriteError(
                "SYMBOL_REFERENCE_PREDICTION_INVALID", f"Cell {index} is predicted twice."
            )
        by_index[index] = entry
    for target in targets:
        found = by_index.get(target.cell_index)
        if found is None:
            raise ReferenceLibraryWriteError(
                "SYMBOL_REFERENCE_PREDICTION_INVALID",
                f"Cell {target.cell_index} has no current prediction.",
            )
        entry = found
        if entry.get("symbolCode") != target.old_symbol:
            raise ReferenceLibraryWriteError(
                "SYMBOL_REFERENCE_PREDICTION_DRIFT",
                f"Cell {target.cell_index} no longer predicts {target.old_symbol}.",
            )
        entry["symbolCode"] = target.new_symbol
        entry["confidence"] = LIBRARY_CONFIDENCE
        entry["alternatives"] = [
            {"symbolCode": target.new_symbol, "confidence": LIBRARY_CONFIDENCE}
        ]
        entry["referenceLibrary"] = {
            "version": MODEL_VERSION,
            "previousSymbolCode": target.old_symbol,
            "shapeVotes": target.shape_votes,
            "combinedVotes": target.combined_votes,
        }
    return rewritten


@dataclass(frozen=True, slots=True)
class _CellState:
    review_state: str
    assigned_symbol_id: UUID | None
    assignment_source: str | None
    quality_issue: str | None

    @classmethod
    def of(cls, cell: ImageSymbolReviewCellModel) -> _CellState:
        return cls(
            cell.review_state, cell.assigned_symbol_id, cell.assignment_source, cell.quality_issue
        )


def revert_checksum(library_checksum_sha256: str) -> str:
    """Checksum of the revision that restores the predictions a library run replaced."""

    return hashlib.sha256(f"revert:{library_checksum_sha256}".encode()).hexdigest()


def _lock_board(session: Session, plan: BoardPlan) -> ImageSymbolPredictionRevisionModel | str:
    item = session.scalar(
        select(ImageReviewItemModel)
        .where(ImageReviewItemModel.id == plan.review_item_id)
        .with_for_update()
    )
    board = session.scalar(
        select(RecognizedBoardModel)
        .where(RecognizedBoardModel.id == plan.recognized_board_id)
        .with_for_update()
    )
    if item is None or board is None:
        return "stale:board_missing"
    latest = session.scalar(
        select(ImageSymbolPredictionRevisionModel)
        .where(ImageSymbolPredictionRevisionModel.review_item_id == plan.review_item_id)
        .order_by(
            ImageSymbolPredictionRevisionModel.created_at.desc(),
            ImageSymbolPredictionRevisionModel.id.desc(),
        )
        .limit(1)
    )
    return "stale:no_prediction_revision" if latest is None else latest


def _lock_cells(
    session: Session, *, game_id: UUID, plan: BoardPlan
) -> dict[UUID, ImageSymbolReviewCellModel]:
    return {
        cell.id: cell
        for cell in session.scalars(
            select(ImageSymbolReviewCellModel)
            .where(
                ImageSymbolReviewCellModel.game_id == game_id,
                ImageSymbolReviewCellModel.review_item_id == plan.review_item_id,
            )
            .with_for_update()
        )
    }


def _snapshot_exists(
    session: Session, *, plan: BoardPlan, checksum: str, crop_manifest_checksum: str
) -> bool:
    return (
        session.scalar(
            select(ImageSymbolPredictionRevisionModel.id).where(
                ImageSymbolPredictionRevisionModel.review_item_id == plan.review_item_id,
                ImageSymbolPredictionRevisionModel.model_checksum_sha256 == checksum,
                ImageSymbolPredictionRevisionModel.crop_manifest_checksum_sha256
                == crop_manifest_checksum,
            )
        )
        is not None
    )


def _write_revision(
    session: Session,
    *,
    game_id: UUID,
    plan: BoardPlan,
    cells: Mapping[UUID, ImageSymbolReviewCellModel],
    revision: ImageSymbolPredictionRevisionModel,
    expected_symbols: Mapping[UUID, str],
) -> None:
    """Add a revision, refresh the projection and check that only expected cells changed.

    ``expected_symbols`` maps the cells that must show the new revision to their symbol;
    every other cell of the board, and any cell sharing its sequence, must keep its state.
    """

    before = {cell_id: _CellState.of(cell) for cell_id, cell in cells.items()}
    sequence_numbers = {cell.sequence_number for cell in cells.values()}
    session.add(revision)
    session.flush()
    SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(plan.review_item_id)
    if not SymbolCellReviewWriteThroughCoordinator(session).synchronize_after_prediction_refresh(
        game_id=game_id,
        review_item_id=plan.review_item_id,
        actor=ACTOR,
    ):
        raise ReferenceLibraryWriteError(
            "SYMBOL_CELL_REVIEW_PROJECTION_INCOMPLETE",
            "The symbol-cell projection rejected the prediction refresh.",
        )
    session.flush()

    symbol_ids = {
        code: symbol_id
        for symbol_id, code in session.execute(
            select(SymbolModel.id, SymbolModel.code).where(SymbolModel.game_id == game_id)
        )
    }
    after = list(
        session.scalars(
            select(ImageSymbolReviewCellModel).where(
                ImageSymbolReviewCellModel.game_id == game_id,
                or_(
                    ImageSymbolReviewCellModel.review_item_id == plan.review_item_id,
                    ImageSymbolReviewCellModel.sequence_number.in_(sequence_numbers),
                ),
            )
        )
    )
    # Logical cells are keyed by sequence; the refresh must not move cells between owners.
    if {cell.id for cell in after} != set(before):
        raise ReferenceLibraryWriteError(
            "SYMBOL_REFERENCE_WRITE_SIDE_EFFECT",
            "The prediction refresh changed which cells belong to the board.",
        )
    for cell in after:
        session.refresh(cell)
        symbol = expected_symbols.get(cell.id)
        if symbol is not None:
            if (
                cell.review_state != "pending"
                or cell.prediction_revision_id != revision.id
                or cell.prediction_symbol_code != symbol
                or cell.assigned_symbol_id != symbol_ids.get(symbol)
            ):
                raise ReferenceLibraryWriteError(
                    "SYMBOL_REFERENCE_WRITE_UNVERIFIED",
                    f"Cell {cell.id} does not show the expected prediction.",
                )
        elif _CellState.of(cell) != before[cell.id]:
            raise ReferenceLibraryWriteError(
                "SYMBOL_REFERENCE_WRITE_SIDE_EFFECT",
                f"Non-target cell {cell.id} changed its decision or assignment.",
            )


def apply_board(
    session: Session,
    *,
    game_id: UUID,
    plan: BoardPlan,
    library_checksum_sha256: str,
) -> str:
    """Write one board inside the caller's transaction.

    Returns ``applied`` or ``already_applied``, or ``stale:<reason>`` without
    writing anything. Raises when the write itself is inconsistent.
    """

    latest = _lock_board(session, plan)
    if isinstance(latest, str):
        return latest
    if (
        latest.model_version == MODEL_VERSION
        and latest.model_checksum_sha256 == library_checksum_sha256
    ):
        return "already_applied"
    if latest.id != plan.prediction_revision_id:
        return "stale:prediction_revision_changed"
    if predictions_digest(latest.predictions) != plan.predictions_sha256:
        return "stale:predictions_changed"
    if _snapshot_exists(
        session,
        plan=plan,
        checksum=library_checksum_sha256,
        crop_manifest_checksum=latest.crop_manifest_checksum_sha256,
    ):
        # This run was written earlier and later superseded; it is not written twice.
        return "stale:library_revision_exists"

    cells = _lock_cells(session, game_id=game_id, plan=plan)
    for target in plan.targets:
        cell = cells.get(target.cell_review_id)
        if (
            cell is None
            or cell.cell_index != target.cell_index
            or cell.review_state != "pending"
            or cell.assignment_source != "model"
            or cell.quality_issue is not None
            or cell.rendered_pixel_checksum_sha256 != target.rendered_pixel_checksum_sha256
            or cell.prediction_revision_id != plan.prediction_revision_id
            or cell.prediction_symbol_code != target.old_symbol
        ):
            return "stale:cell_changed"

    _write_revision(
        session,
        game_id=game_id,
        plan=plan,
        cells=cells,
        revision=ImageSymbolPredictionRevisionModel(
            game_id=game_id,
            review_item_id=plan.review_item_id,
            recognized_board_id=plan.recognized_board_id,
            source_job_id=latest.source_job_id,
            model_iteration_id=None,
            model_version=MODEL_VERSION,
            model_checksum_sha256=library_checksum_sha256,
            crop_manifest_checksum_sha256=latest.crop_manifest_checksum_sha256,
            predictions=rewrite_predictions(latest.predictions, plan.targets),
        ),
        expected_symbols={target.cell_review_id: target.new_symbol for target in plan.targets},
    )
    return "applied"


def revert_board(
    session: Session,
    *,
    game_id: UUID,
    plan: BoardPlan,
    library_checksum_sha256: str,
) -> str:
    """Restore the predictions a library run replaced on one board.

    The previous revision is copied into a new current revision under the previous
    model version, so the old model is the prediction source again. Only a board whose
    current revision is still this run's library revision is reverted; target cells an
    operator has decided meanwhile keep that decision.
    """

    latest = _lock_board(session, plan)
    if isinstance(latest, str):
        return latest
    checksum = revert_checksum(library_checksum_sha256)
    if latest.model_checksum_sha256 == checksum:
        return "already_reverted"
    if (
        latest.model_version != MODEL_VERSION
        or latest.model_checksum_sha256 != library_checksum_sha256
    ):
        return "stale:not_current_library_revision"
    previous = session.get(ImageSymbolPredictionRevisionModel, plan.prediction_revision_id)
    if previous is None or predictions_digest(previous.predictions) != plan.predictions_sha256:
        return "stale:previous_revision_changed"
    if _snapshot_exists(
        session,
        plan=plan,
        checksum=checksum,
        crop_manifest_checksum=latest.crop_manifest_checksum_sha256,
    ):
        return "stale:revert_revision_exists"

    cells = _lock_cells(session, game_id=game_id, plan=plan)
    expected_symbols: dict[UUID, str] = {}
    for target in plan.targets:
        cell = cells.get(target.cell_review_id)
        if (
            cell is not None
            and cell.review_state == "pending"
            and cell.assignment_source == "model"
            and cell.prediction_revision_id == latest.id
        ):
            expected_symbols[cell.id] = target.old_symbol

    _write_revision(
        session,
        game_id=game_id,
        plan=plan,
        cells=cells,
        revision=ImageSymbolPredictionRevisionModel(
            game_id=game_id,
            review_item_id=plan.review_item_id,
            recognized_board_id=plan.recognized_board_id,
            source_job_id=previous.source_job_id,
            model_iteration_id=previous.model_iteration_id,
            model_version=previous.model_version,
            model_checksum_sha256=checksum,
            crop_manifest_checksum_sha256=latest.crop_manifest_checksum_sha256,
            predictions=copy.deepcopy(previous.predictions),
        ),
        expected_symbols=expected_symbols,
    )
    return "reverted"
