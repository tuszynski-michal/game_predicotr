"""PostgreSQL read model for human-approved symbol reference candidates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast
from uuid import UUID

from sqlalchemy import String, and_, case, or_, select
from sqlalchemy.orm import Session

from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceRepository,
)
from game_predictor_api.domain.catalog import CatalogConflictError, CatalogNotFoundError, Symbol
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
    SymbolReferenceImage,
)
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    RecognizedBoardModel,
    SymbolModel,
    SymbolReferenceImageModel,
)

_APPROVED_STATUSES = ("accepted", "corrected")


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
        symbol_code = self._symbol_code(game_id, symbol_id)
        query = self._candidate_query(game_id=game_id, symbol_code=symbol_code)
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
        symbol_code = self._symbol_code(game_id, symbol_id)
        row = self._session.execute(
            self._candidate_query(game_id=game_id, symbol_code=symbol_code).where(
                CellObservationModel.id == observation_id
            )
        ).one_or_none()
        if row is None:
            return None
        return self._to_candidates((row,))[0]

    def get_reference(self, *, game_id: UUID, symbol_id: UUID) -> SymbolReferenceImage | None:
        row = self._session.execute(
            select(SymbolReferenceImageModel).join(
                SymbolModel,
                SymbolModel.id == SymbolReferenceImageModel.symbol_id,
            ).where(
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
    ) -> Symbol:
        current = self._locked_current_candidate(
            game_id=game_id,
            symbol_id=symbol_id,
            observation_id=candidate.observation_id,
        )
        if current is None or current != candidate or (
            current.crop_checksum_sha256 != expected_checksum_sha256
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
                image_checksum_sha256=expected_checksum_sha256,
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
            reference.image_checksum_sha256 = expected_checksum_sha256
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
        symbol_code = self._symbol_code(game_id, symbol_id)
        row = self._session.execute(
            self._candidate_query(game_id=game_id, symbol_code=symbol_code)
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

    def _candidate_query(self, *, game_id: UUID, symbol_code: str) -> Any:
        cell_index = CellObservationModel.row_index * 5 + CellObservationModel.column_index
        resolved_symbol = ImageReviewItemModel.resolved_value["symbolCodes"][
            cell_index
        ].as_string()
        return (
            select(
                CellObservationModel,
                ImageReviewItemModel,
                RecognizedBoardModel,
                ImageSequenceCanonicalModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == CellObservationModel.recognized_board_id,
            )
            .join(
                ImageReviewItemModel,
                ImageReviewItemModel.recognized_board_id == RecognizedBoardModel.id,
            )
            .join(
                ImageSequenceCanonicalModel,
                and_(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.review_item_id == ImageReviewItemModel.id,
                    ImageSequenceCanonicalModel.recognized_board_id == RecognizedBoardModel.id,
                ),
            )
            .where(
                ImageSequenceCanonicalModel.status.in_(_APPROVED_STATUSES),
                ImageReviewItemModel.status.in_(_APPROVED_STATUSES),
                RecognizedBoardModel.status.in_(_APPROVED_STATUSES),
                ImageReviewItemModel.resolved_value["symbolCodes"].contains([symbol_code]),
                resolved_symbol == symbol_code,
            )
        )

    def _to_candidates(self, rows: Sequence[Any]) -> tuple[ApprovedSymbolReferenceCandidate, ...]:
        board_ids = [cast(RecognizedBoardModel, row[2]).id for row in rows]
        revisions = {
            (revision.recognized_board_id, revision.revision): revision
            for revision in self._session.scalars(
                select(ImageBoardGeometryRevisionModel).where(
                    ImageBoardGeometryRevisionModel.recognized_board_id.in_(board_ids)
                )
            )
        } if board_ids else {}
        candidates: list[ApprovedSymbolReferenceCandidate] = []
        for observation, item, board, canonical in rows:
            observation = cast(CellObservationModel, observation)
            item = cast(ImageReviewItemModel, item)
            board = cast(RecognizedBoardModel, board)
            canonical = cast(ImageSequenceCanonicalModel, canonical)
            index = observation.row_index * 5 + observation.column_index
            crop_relative_path = observation.crop_relative_path
            crop_checksum_sha256 = observation.crop_checksum_sha256
            if board.geometry_revision > 0:
                revision = revisions.get((board.id, board.geometry_revision))
                if revision is None or revision.crop_artifacts is None:
                    raise CatalogNotFoundError(
                        "SYMBOL_REFERENCE_GEOMETRY_MISSING",
                        "The approved board geometry revision is unavailable.",
                    )
                artifact = _crop_artifact(revision.crop_artifacts, index)
                crop_relative_path = artifact["cropRelativePath"]
                crop_checksum_sha256 = artifact["cropChecksumSha256"]
            if crop_relative_path is None:
                raise CatalogNotFoundError(
                    "SYMBOL_REFERENCE_VIRTUAL_ASSET_UNAVAILABLE",
                    "Virtual symbol assets are not active in the approved-reference picker.",
                )
            candidates.append(
                ApprovedSymbolReferenceCandidate(
                    observation_id=observation.id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
                    sequence_number=int(canonical.sequence_number),
                    cell_index=index,
                    resolution_revision=item.resolution_revision,
                    geometry_revision=board.geometry_revision,
                    crop_relative_path=crop_relative_path,
                    crop_checksum_sha256=crop_checksum_sha256,
                    status=str(item.status),
                )
            )
        return tuple(candidates)


def _order_columns() -> tuple[Any, Any, Any, Any]:
    geometry_priority = case((RecognizedBoardModel.geometry_revision > 0, 0), else_=1)
    sequence_number = ImageSequenceCanonicalModel.sequence_number
    cell_index = CellObservationModel.row_index * 5 + CellObservationModel.column_index
    observation_id = CellObservationModel.id.cast(String)
    return geometry_priority, sequence_number, cell_index, observation_id


def _crop_artifact(
    artifacts: Sequence[Mapping[str, object]], cell_index: int
) -> dict[str, str]:
    match = next(
        (
            value
            for value in artifacts
            if value.get("rowIndex") == cell_index // 5
            and value.get("columnIndex") == cell_index % 5
        ),
        None,
    )
    if (
        match is None
        or not isinstance(match.get("cropRelativePath"), str)
        or not isinstance(match.get("cropChecksumSha256"), str)
    ):
        raise CatalogNotFoundError(
            "SYMBOL_REFERENCE_GEOMETRY_INVALID",
            "The approved board geometry crop is incomplete.",
        )
    return {
        "cropRelativePath": cast(str, match["cropRelativePath"]),
        "cropChecksumSha256": cast(str, match["cropChecksumSha256"]),
    }


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
