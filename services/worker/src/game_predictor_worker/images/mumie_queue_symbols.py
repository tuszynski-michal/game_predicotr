"""Commit classifier output for the exact newly rendered Mumie cells in the geometry transaction."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from game_predictor_api.application.virtual_grid_geometry import PreparedVirtualGridGeometry
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageBoardSearchFastDocumentModel,
    ImageSymbolPredictionRevisionModel,
    ImageSymbolReviewCellModel,
    SymbolModel,
)
from sqlalchemy import select
from sqlalchemy.orm import Session


def save_queue_symbols(
    session: Session,
    entries: Sequence[PreparedVirtualGridGeometry],
    written: Mapping[UUID, UUID],
    payload: dict[str, Any],
) -> None:
    model = SymbolModelJobSnapshot.from_payload(payload)
    for entry in entries:
        ctx = entry.context
        predicted = entry.slot_prediction
        if (
            predicted is None
            or ctx.review_item_id is None
            or ctx.recognized_board_id is None
            or written.get(ctx.target_id) != ctx.review_item_id
            or predicted.model_manifest_checksum_sha256 != model.manifest_checksum_sha256
            or len(predicted.cells) != 15
            or len(entry.cells) != 15
        ):
            raise ValueError("MUMIE_QUEUE_SYMBOLS_INCOMPLETE")
        observations = []
        checksums = []
        for index, (cell, pred) in enumerate(zip(entry.cells, predicted.cells, strict=True)):
            if (
                (cell.row_index, cell.column_index) != divmod(index, 5)
                or (pred["rowIndex"], pred["columnIndex"]) != divmod(index, 5)
                or pred["symbolCode"] not in model.class_codes
            ):
                raise ValueError("MUMIE_QUEUE_SYMBOL_POSITION_INVALID")
            checksums.append(cell.crop_checksum_sha256)
            observations.append(
                {
                    **pred,
                    "virtualCell": {
                        "cropChecksumSha256": cell.crop_checksum_sha256,
                        "extractorVersion": cell.extractor_version,
                        "logicalCellKeySha256": cell.logical_cell_key,
                        "logicalCellKeyV2Sha256": cell.logical_cell_key_v2,
                        "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
                        "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
                    },
                }
            )
        manifest = hashlib.sha256(json.dumps(checksums, separators=(",", ":")).encode()).hexdigest()
        existing = session.scalar(
            select(ImageSymbolPredictionRevisionModel).where(
                ImageSymbolPredictionRevisionModel.review_item_id == ctx.review_item_id,
                ImageSymbolPredictionRevisionModel.model_checksum_sha256
                == model.onnx_checksum_sha256,
                ImageSymbolPredictionRevisionModel.crop_manifest_checksum_sha256 == manifest,
            )
        )
        if existing is None:
            existing = ImageSymbolPredictionRevisionModel(
                game_id=ctx.game_id,
                review_item_id=ctx.review_item_id,
                recognized_board_id=ctx.recognized_board_id,
                source_job_id=ctx.import_job_id,
                model_iteration_id=model.iteration_id,
                model_version=model.model_version,
                model_checksum_sha256=model.onnx_checksum_sha256,
                crop_manifest_checksum_sha256=manifest,
                predictions=observations,
            )
            session.add(existing)
            session.flush()
        elif existing.predictions != observations:
            raise ValueError("MUMIE_QUEUE_SYMBOL_PROVENANCE_CHANGED")
        if not SymbolCellReviewWriteThroughCoordinator(
            session
        ).synchronize_after_prediction_refresh(
            game_id=ctx.game_id,
            review_item_id=ctx.review_item_id,
            actor="system:mumie-suspicious-queue",
        ):
            raise ValueError("MUMIE_QUEUE_SYMBOL_REVIEW_INCOMPLETE")
        session.flush()
        refreshed = session.execute(
            select(
                ImageSymbolReviewCellModel.cell_index,
                ImageSymbolReviewCellModel.prediction_symbol_code,
                ImageSymbolReviewCellModel.rendered_pixel_checksum_sha256,
                SymbolModel.code,
                SymbolModel.mobile_code,
            )
            .join(SymbolModel, SymbolModel.id == ImageSymbolReviewCellModel.assigned_symbol_id)
            .where(
                ImageSymbolReviewCellModel.review_item_id == ctx.review_item_id,
                ImageSymbolReviewCellModel.game_id == ctx.game_id,
                ImageSymbolReviewCellModel.prediction_revision_id == existing.id,
                ImageSymbolReviewCellModel.geometry_revision == ctx.next_geometry_revision,
            )
            .order_by(ImageSymbolReviewCellModel.cell_index)
        ).all()
        expected = [
            (index, pred["symbolCode"], cell.rendered_pixel_checksum_sha256, pred["symbolCode"])
            for index, (cell, pred) in enumerate(zip(entry.cells, predicted.cells, strict=True))
        ]
        if [row[:4] for row in refreshed] != expected:
            raise ValueError("MUMIE_QUEUE_SYMBOL_ASSIGNMENTS_INCOMPLETE")
        SqlAlchemyBoardSearchProjectionRepository(session).sync_review_item(ctx.review_item_id)
        projection = session.execute(
            select(
                ImageBoardSearchFastDocumentModel.review_item_id,
                ImageBoardSearchFastDocumentModel.primary_symbol_mobile_codes,
            ).where(
                ImageBoardSearchFastDocumentModel.game_id == ctx.game_id,
                ImageBoardSearchFastDocumentModel.sequence_number == ctx.sequence_number,
            )
        ).one_or_none()
        if projection != (ctx.review_item_id, [row[4] for row in refreshed]):
            raise ValueError("MUMIE_QUEUE_SEARCH_SYMBOLS_INCOMPLETE")
