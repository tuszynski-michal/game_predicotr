"""PostgreSQL read model for human-approved symbol reference candidates."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import String, and_, case, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceRepository,
)
from game_predictor_api.domain.catalog import (
    CatalogConflictError,
    CatalogNotFoundError,
    Symbol,
    SymbolStatus,
)
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAsset
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
    SymbolReferenceImage,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardSearchFastDocumentModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
    SymbolReferenceImageModel,
)


class SqlAlchemyApprovedSymbolReferenceRepository(ApprovedSymbolReferenceRepository):
    """Reads the current canonical, human-resolved representation only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def game_exists(self, game_id: UUID) -> bool:
        return self._session.get(GameModel, game_id) is not None

    def list_candidates(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        after_key: tuple[int, int, int, str] | None,
        limit: int,
    ) -> Sequence[ApprovedSymbolReferenceCandidate]:
        self._symbol_code(game_id, symbol_id)
        query = self._candidate_query(game_id=game_id, symbol_id=symbol_id)
        geometry_priority, sequence_number, cell_index, observation_id = _order_columns()
        if after_key is not None:
            query = query.where(
                or_(
                    geometry_priority > after_key[0],
                    and_(geometry_priority == after_key[0], sequence_number > after_key[1]),
                    and_(
                        geometry_priority == after_key[0],
                        sequence_number == after_key[1],
                        cell_index > after_key[2],
                    ),
                    and_(
                        geometry_priority == after_key[0],
                        sequence_number == after_key[1],
                        cell_index == after_key[2],
                        observation_id > after_key[3],
                    ),
                )
            )
        rows = self._session.execute(
            query.order_by(
                geometry_priority,
                sequence_number,
                cell_index,
                observation_id,
            ).limit(limit)
        ).all()
        return self._to_candidates(rows)

    def get_candidate(
        self, *, game_id: UUID, symbol_id: UUID, observation_id: UUID
    ) -> ApprovedSymbolReferenceCandidate | None:
        self._symbol_code(game_id, symbol_id)
        row = self._session.execute(
            self._candidate_query(game_id=game_id, symbol_id=symbol_id).where(
                CellObservationModel.id == observation_id
            )
        ).one_or_none()
        if row is None:
            return None
        return self._to_candidates((row,))[0]

    def get_reference(self, *, game_id: UUID, symbol_id: UUID) -> SymbolReferenceImage | None:
        row = self._session.execute(
            select(SymbolReferenceImageModel)
            .join(
                SymbolModel,
                SymbolModel.id == SymbolReferenceImageModel.symbol_id,
            )
            .where(
                SymbolReferenceImageModel.symbol_id == symbol_id,
                SymbolReferenceImageModel.game_id == game_id,
                SymbolModel.game_id == game_id,
            )
        ).scalar_one_or_none()
        if row is None:
            self._symbol_code(game_id, symbol_id)
            return None
        return _to_reference(row)

    def select_reference(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        candidate: ApprovedSymbolReferenceCandidate,
        expected_checksum_sha256: str,
        selected_by: str,
        image_relative_path: str,
        image_checksum_sha256: str,
    ) -> Symbol:
        current = self._locked_current_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            observation_id=candidate.observation_id,
        )
        if (
            current is None
            or current != candidate
            or (current.crop_checksum_sha256 != expected_checksum_sha256)
        ):
            raise CatalogConflictError(
                "SYMBOL_REFERENCE_CANDIDATE_STALE",
                "The approved symbol reference candidate changed after it was loaded.",
            )
        symbol = self._session.execute(
            select(SymbolModel)
            .where(SymbolModel.id == symbol_id, SymbolModel.game_id == game_id)
            .with_for_update()
        ).scalar_one_or_none()
        if symbol is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
                details={"gameId": str(game_id), "symbolId": str(symbol_id)},
            )
        reference = self._session.get(SymbolReferenceImageModel, symbol_id)
        if reference is None:
            reference = SymbolReferenceImageModel(
                symbol_id=symbol.id,
                game_id=game_id,
                source_review_item_id=current.review_item_id,
                source_recognized_board_id=current.recognized_board_id,
                source_observation_id=current.observation_id,
                sequence_number=current.sequence_number,
                cell_index=current.cell_index,
                resolution_revision=current.resolution_revision,
                geometry_revision=current.geometry_revision,
                image_relative_path=image_relative_path,
                image_checksum_sha256=image_checksum_sha256,
                selected_by=selected_by,
            )
            self._session.add(reference)
        else:
            reference.game_id = game_id
            reference.source_review_item_id = current.review_item_id
            reference.source_recognized_board_id = current.recognized_board_id
            reference.source_observation_id = current.observation_id
            reference.sequence_number = current.sequence_number
            reference.cell_index = current.cell_index
            reference.resolution_revision = current.resolution_revision
            reference.geometry_revision = current.geometry_revision
            reference.image_relative_path = image_relative_path
            reference.image_checksum_sha256 = image_checksum_sha256
            reference.selected_by = selected_by
        # The column remains an internal pointer for existing storage cleanup.
        # Catalog reads expose it only when the provenance row exists.
        symbol.image_path = image_relative_path
        self._session.flush()
        return Symbol(
            id=symbol.id,
            game_id=symbol.game_id,
            mobile_code=symbol.mobile_code,
            code=symbol.code,
            name=symbol.name,
            image_path=image_relative_path,
            is_wildcard=symbol.is_wildcard,
            display_order=symbol.display_order,
            status=symbol.status,
            name_pl=symbol.name_pl,
            name_en=symbol.name_en,
        )

    def _locked_current_candidate(
        self,
        *,
        game_id: UUID,
        symbol_id: UUID,
        observation_id: UUID,
    ) -> ApprovedSymbolReferenceCandidate | None:
        self._symbol_code(game_id, symbol_id)
        row = self._session.execute(
            self._candidate_query(game_id=game_id, symbol_id=symbol_id)
            .where(CellObservationModel.id == observation_id)
            .with_for_update()
        ).one_or_none()
        return None if row is None else self._to_candidates((row,))[0]

    def _symbol_code(self, game_id: UUID, symbol_id: UUID) -> str:
        code = self._session.scalar(
            select(SymbolModel.code).where(
                SymbolModel.id == symbol_id,
                SymbolModel.game_id == game_id,
            )
        )
        if code is None:
            raise CatalogNotFoundError(
                "SYMBOL_NOT_FOUND",
                "Symbol does not exist in this game.",
                details={"gameId": str(game_id), "symbolId": str(symbol_id)},
            )
        return str(code)

    def _candidate_query(self, *, game_id: UUID, symbol_id: UUID) -> Any:
        review_cell = ImageSymbolReviewCellModel
        return (
            select(
                review_cell,
                CellObservationModel,
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel.checksum_sha256,
                ImageSourceGeometryRevisionModel.normalized_pixel_checksum_sha256,
                ImageSourceGeometryRevisionModel.geometry_checksum_sha256,
            )
            .join(
                CellObservationModel,
                and_(
                    CellObservationModel.recognized_board_id == review_cell.recognized_board_id,
                    CellObservationModel.row_index == review_cell.row_index,
                    CellObservationModel.column_index == review_cell.column_index,
                ),
            )
            .join(ImageReviewItemModel, ImageReviewItemModel.id == review_cell.review_item_id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == review_cell.recognized_board_id,
            )
            .join(
                ImageBoardSearchFastDocumentModel,
                and_(
                    ImageBoardSearchFastDocumentModel.game_id == review_cell.game_id,
                    ImageBoardSearchFastDocumentModel.sequence_number
                    == review_cell.sequence_number,
                    ImageBoardSearchFastDocumentModel.review_item_id == review_cell.review_item_id,
                    ImageBoardSearchFastDocumentModel.recognized_board_id
                    == review_cell.recognized_board_id,
                    ImageBoardSearchFastDocumentModel.import_job_id == review_cell.import_job_id,
                ),
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .outerjoin(
                ImageSourceGeometryRevisionModel,
                ImageSourceGeometryRevisionModel.id == review_cell.source_geometry_revision_id,
            )
            .join(SymbolModel, SymbolModel.id == review_cell.assigned_symbol_id)
            .where(
                review_cell.game_id == game_id,
                review_cell.assigned_symbol_id == symbol_id,
                review_cell.review_state == "approved",
                review_cell.quality_issue.is_(None),
                review_cell.approved_crop_sample_id == review_cell.crop_sample_id,
                review_cell.approved_crop_checksum_sha256 == review_cell.crop_checksum_sha256,
                review_cell.approved_geometry_revision == review_cell.geometry_revision,
                review_cell.geometry_revision == RecognizedBoardModel.geometry_revision,
                SymbolModel.game_id == game_id,
                SymbolModel.status == SymbolStatus.ACTIVE,
                or_(
                    review_cell.asset_mode == "legacy_file",
                    and_(
                        review_cell.asset_mode == "virtual_source",
                        review_cell.approved_asset_mode == "virtual_source",
                        review_cell.approved_source_geometry_revision_id
                        == review_cell.source_geometry_revision_id,
                        review_cell.approved_render_spec_checksum_sha256
                        == review_cell.render_spec_checksum_sha256,
                        review_cell.approved_rendered_pixel_checksum_sha256
                        == review_cell.rendered_pixel_checksum_sha256,
                        review_cell.source_geometry_revision_id
                        == RecognizedBoardModel.source_geometry_revision_id,
                    ),
                ),
            )
        )

    def _to_candidates(self, rows: Sequence[Any]) -> tuple[ApprovedSymbolReferenceCandidate, ...]:
        candidates: list[ApprovedSymbolReferenceCandidate] = []
        for (
            review_cell,
            observation,
            item,
            board,
            source_checksum,
            normalized_pixel_checksum,
            geometry_checksum,
        ) in rows:
            virtual_asset = (
                None
                if review_cell.asset_mode != "virtual_source"
                else SymbolCellReviewAsset(
                    cell_review_id=review_cell.id,
                    crop_relative_path=None,
                    crop_checksum_sha256=review_cell.crop_checksum_sha256,
                    geometry_revision=review_cell.geometry_revision,
                    current_geometry_revision=board.geometry_revision,
                    revision=review_cell.revision,
                    asset_mode="virtual_source",
                    source_checksum_sha256=source_checksum,
                    normalized_pixel_checksum_sha256=normalized_pixel_checksum,
                    source_geometry_revision_id=review_cell.source_geometry_revision_id,
                    current_source_geometry_revision_id=board.source_geometry_revision_id,
                    geometry_checksum_sha256=geometry_checksum,
                    logical_cell_key=review_cell.logical_cell_key,
                    render_spec=review_cell.render_spec,
                    render_spec_checksum_sha256=review_cell.render_spec_checksum_sha256,
                    rendered_pixel_checksum_sha256=review_cell.rendered_pixel_checksum_sha256,
                    extractor_version=review_cell.extractor_version,
                )
            )
            candidates.append(
                ApprovedSymbolReferenceCandidate(
                    observation_id=observation.id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
                    sequence_number=int(review_cell.sequence_number),
                    cell_index=review_cell.cell_index,
                    resolution_revision=item.resolution_revision,
                    geometry_revision=review_cell.geometry_revision,
                    crop_relative_path=review_cell.crop_relative_path,
                    crop_checksum_sha256=review_cell.crop_checksum_sha256,
                    status=review_cell.review_state,
                    asset_mode=review_cell.asset_mode,
                    virtual_asset=virtual_asset,
                )
            )
        return tuple(candidates)


def _order_columns() -> tuple[Any, Any, Any, Any]:
    geometry_priority = case((ImageSymbolReviewCellModel.geometry_revision > 0, 0), else_=1)
    sequence_number = ImageSymbolReviewCellModel.sequence_number
    cell_index = ImageSymbolReviewCellModel.cell_index
    observation_id = CellObservationModel.id.cast(String)
    return geometry_priority, sequence_number, cell_index, observation_id


def _to_reference(record: SymbolReferenceImageModel) -> SymbolReferenceImage:
    return SymbolReferenceImage(
        symbol_id=record.symbol_id,
        source_review_item_id=record.source_review_item_id,
        source_recognized_board_id=record.source_recognized_board_id,
        source_observation_id=record.source_observation_id,
        sequence_number=int(record.sequence_number),
        cell_index=record.cell_index,
        resolution_revision=record.resolution_revision,
        geometry_revision=record.geometry_revision,
        image_relative_path=record.image_relative_path,
        image_checksum_sha256=record.image_checksum_sha256,
        selected_by=record.selected_by,
        selected_at=record.selected_at,
    )


__all__ = ["SqlAlchemyApprovedSymbolReferenceRepository"]
