"""Persistence and backfill for the compact partial-board search projection."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import cast
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_search import (
    BOARD_SEARCH_CELL_COUNT,
    BoardSearchCandidate,
    BoardSearchProjectionPayload,
    select_board_search_document,
)
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardSearchCandidateModel,
    ImageBoardSearchDocumentModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)

_SEARCHABLE_STATUSES = frozenset({"pending", "accepted", "corrected"})
_REBUILD_BATCH_SIZE = 400


@dataclass(frozen=True, slots=True)
class BoardSearchProjectionRebuildResult:
    candidate_count: int
    document_count: int
    skipped_review_item_count: int


ReviewProjectionRow = tuple[
    ImageReviewItemModel,
    RecognizedBoardModel,
    SourceImageModel,
    JobModel,
]


class SqlAlchemyBoardSearchProjectionRepository:
    """Maintains only compact data; board crop bytes stay in the artifact root."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_candidate(self, payload: BoardSearchProjectionPayload) -> None:
        values = _candidate_values(payload)
        insert_statement = postgresql_insert(ImageBoardSearchCandidateModel).values(**values)
        update_statement = insert_statement.on_conflict_do_update(
            index_elements=[ImageBoardSearchCandidateModel.review_item_id],
            set_={
                key: value
                for key, value in values.items()
                if key not in {"review_item_id", "created_at"}
            }
            | {"updated_at": func.now()},
        )
        self._session.execute(update_statement)

    def remove_candidate(self, review_item_id: UUID) -> None:
        self._session.execute(
            delete(ImageBoardSearchCandidateModel).where(
                ImageBoardSearchCandidateModel.review_item_id == review_item_id
            )
        )

    def reconcile_review_item(self, review_item_id: UUID) -> None:
        candidate = self._session.get(ImageBoardSearchCandidateModel, review_item_id)
        if candidate is None:
            return
        self.reconcile_sequence(candidate.game_id, candidate.sequence_number)

    def reconcile_sequence(self, game_id: UUID, sequence_number: int) -> None:
        rows = self._session.execute(
            select(ImageBoardSearchCandidateModel, JobModel)
            .join(JobModel, JobModel.id == ImageBoardSearchCandidateModel.import_job_id)
            .where(
                ImageBoardSearchCandidateModel.game_id == game_id,
                ImageBoardSearchCandidateModel.sequence_number == sequence_number,
            )
        ).all()
        payloads = tuple(_payload_from_candidate(record) for record, _job in rows)
        canonical_review_item_id = self._session.scalar(
            select(ImageSequenceCanonicalModel.review_item_id).where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == sequence_number,
            )
        )
        waiting_pending_review_item_ids = tuple(
            candidate.review_item_id
            for candidate, job in rows
            if candidate.status == "pending" and job.status is JobStatus.WAITING_FOR_REVIEW
        )
        selection = select_board_search_document(
            sequence_number=sequence_number,
            candidates=payloads,
            canonical_review_item_id=canonical_review_item_id,
            waiting_pending_review_item_ids=waiting_pending_review_item_ids,
        )
        if selection is None:
            self._session.execute(
                delete(ImageBoardSearchDocumentModel).where(
                    ImageBoardSearchDocumentModel.game_id == game_id,
                    ImageBoardSearchDocumentModel.sequence_number == sequence_number,
                )
            )
            return
        values = {
            "game_id": game_id,
            "sequence_number": sequence_number,
            "review_item_id": selection.review_item_id,
            "selection_kind": selection.selection_kind,
        }
        self._session.execute(
            delete(ImageBoardSearchDocumentModel).where(
                ImageBoardSearchDocumentModel.review_item_id == selection.review_item_id,
                ImageBoardSearchDocumentModel.sequence_number != sequence_number,
            )
        )
        insert_statement = postgresql_insert(ImageBoardSearchDocumentModel).values(**values)
        self._session.execute(
            insert_statement.on_conflict_do_update(
                index_elements=[
                    ImageBoardSearchDocumentModel.game_id,
                    ImageBoardSearchDocumentModel.sequence_number,
                ],
                set_={
                    "review_item_id": selection.review_item_id,
                    "selection_kind": selection.selection_kind,
                    "updated_at": func.now(),
                },
            )
        )

    def rebuild_game(self, game_id: UUID) -> BoardSearchProjectionRebuildResult:
        """Rebuild one game atomically from review records in bounded batches."""

        self._session.execute(
            delete(ImageBoardSearchDocumentModel).where(
                ImageBoardSearchDocumentModel.game_id == game_id
            )
        )
        self._session.execute(
            delete(ImageBoardSearchCandidateModel).where(
                ImageBoardSearchCandidateModel.game_id == game_id
            )
        )
        self._session.flush()

        candidate_count = 0
        skipped_count = 0
        sequences: set[int] = set()
        rows_result = self._session.execute(
            select(
                ImageReviewItemModel,
                RecognizedBoardModel,
                SourceImageModel,
                JobModel,
            )
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
            .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
            .where(JobModel.game_id == game_id)
            .order_by(ImageReviewItemModel.id)
        )
        for rows in rows_result.partitions(_REBUILD_BATCH_SIZE):
            batch = tuple(cast(ReviewProjectionRow, row) for row in rows)
            payloads = _payloads_from_rows(self._session, batch)
            candidate_count += len(payloads)
            skipped_count += len(batch) - len(payloads)
            for payload in payloads:
                self.upsert_candidate(payload)
                sequences.add(payload.candidate.sequence_number)
            self._session.flush()

        for sequence_number in sorted(sequences):
            self.reconcile_sequence(game_id, sequence_number)
        self._session.flush()
        document_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(ImageBoardSearchDocumentModel)
                .where(ImageBoardSearchDocumentModel.game_id == game_id)
            )
            or 0
        )
        return BoardSearchProjectionRebuildResult(
            candidate_count=candidate_count,
            document_count=document_count,
            skipped_review_item_count=skipped_count,
        )


def _payloads_from_rows(
    session: Session,
    rows: Sequence[ReviewProjectionRow],
) -> tuple[BoardSearchProjectionPayload, ...]:
    if not rows:
        return ()
    review_item_ids = [item.id for item, _board, _source, _job in rows]
    board_ids = [board.id for _item, board, _source, _job in rows]
    observations_by_board: dict[UUID, list[CellObservationModel]] = defaultdict(list)
    for observation in session.scalars(
        select(CellObservationModel)
        .where(CellObservationModel.recognized_board_id.in_(board_ids))
        .order_by(
            CellObservationModel.recognized_board_id,
            CellObservationModel.row_index,
            CellObservationModel.column_index,
        )
    ):
        observations_by_board[observation.recognized_board_id].append(observation)

    latest_predictions: dict[UUID, list[dict[str, object]]] = {}
    for revision in session.scalars(
        select(ImageSymbolPredictionRevisionModel)
        .where(ImageSymbolPredictionRevisionModel.review_item_id.in_(review_item_ids))
        .order_by(
            ImageSymbolPredictionRevisionModel.review_item_id,
            ImageSymbolPredictionRevisionModel.created_at,
            ImageSymbolPredictionRevisionModel.id,
        )
    ):
        latest_predictions[revision.review_item_id] = list(revision.predictions)

    payloads: list[BoardSearchProjectionPayload] = []
    for item, board, source, job in rows:
        payload = _payload_from_records(
            item=item,
            board=board,
            source=source,
            job=job,
            observations=observations_by_board[board.id],
            prediction_override=latest_predictions.get(item.id),
        )
        if payload is not None:
            payloads.append(payload)
    return tuple(payloads)


def _payload_from_records(
    *,
    item: ImageReviewItemModel,
    board: RecognizedBoardModel,
    source: SourceImageModel,
    job: JobModel,
    observations: Sequence[CellObservationModel],
    prediction_override: Sequence[Mapping[str, object]] | None,
) -> BoardSearchProjectionPayload | None:
    if item.status not in _SEARCHABLE_STATUSES or job.game_id is None:
        return None
    primary: tuple[str | None, ...]
    alternatives: tuple[tuple[str | None, ...], ...]
    if item.status in {"accepted", "corrected"}:
        resolved = item.resolved_value
        if not isinstance(resolved, Mapping):
            return None
        raw_sequence = resolved.get("sequenceNumber")
        raw_symbols = resolved.get("symbolCodes")
        if (
            not isinstance(raw_sequence, int)
            or isinstance(raw_sequence, bool)
            or raw_sequence < 1
            or not _is_complete_symbol_codes(raw_symbols)
        ):
            return None
        primary = tuple(cast(str, symbol) for symbol in cast(Sequence[object], raw_symbols))
        alternatives = ((),) * BOARD_SEARCH_CELL_COUNT
        sequence_number = raw_sequence
    else:
        if board.sequence_number is None:
            return None
        raw_predictions = prediction_override
        if raw_predictions is None:
            raw_predictions = tuple(
                cast(Mapping[str, object], observation.prediction) for observation in observations
            )
        parsed = _parse_pending_predictions(raw_predictions)
        if parsed is None:
            return None
        primary, alternatives = parsed
        sequence_number = int(board.sequence_number)

    return BoardSearchProjectionPayload(
        game_id=job.game_id,
        import_job_id=source.import_job_id,
        recognized_board_id=board.id,
        candidate=BoardSearchCandidate(
            review_item_id=item.id,
            sequence_number=sequence_number,
            status=item.status,
            primary_symbol_codes=primary,
            alternative_symbol_codes=alternatives,
        ),
        board_checksum_sha256=board.board_checksum_sha256,
        board_confidence=board.board_confidence,
        sequence_confidence=board.sequence_confidence,
        source_pixel_count=source.width * source.height,
    )


def _parse_pending_predictions(
    raw_predictions: Sequence[Mapping[str, object]],
) -> tuple[tuple[str | None, ...], tuple[tuple[str | None, ...], ...]] | None:
    if len(raw_predictions) != BOARD_SEARCH_CELL_COUNT:
        return None
    primary: list[str | None] = []
    alternatives: list[tuple[str | None, ...]] = []
    for prediction in raw_predictions:
        symbol = _optional_symbol_code(prediction.get("symbolCode"))
        raw_alternatives = prediction.get("alternatives")
        if not isinstance(raw_alternatives, Sequence) or isinstance(raw_alternatives, str | bytes):
            return None
        parsed_alternatives: list[str | None] = []
        for raw_alternative in raw_alternatives[:4]:
            if not isinstance(raw_alternative, Mapping):
                return None
            parsed_alternatives.append(_optional_symbol_code(raw_alternative.get("symbolCode")))
        primary.append(symbol)
        alternatives.append(tuple(parsed_alternatives))
    return tuple(primary), tuple(alternatives)


def _optional_symbol_code(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _is_complete_symbol_codes(value: object) -> bool:
    return (
        isinstance(value, Sequence)
        and not isinstance(value, str | bytes)
        and len(value) == BOARD_SEARCH_CELL_COUNT
        and all(isinstance(symbol, str) and symbol.strip() for symbol in value)
    )


def _candidate_values(payload: BoardSearchProjectionPayload) -> dict[str, object]:
    return {
        "review_item_id": payload.candidate.review_item_id,
        "game_id": payload.game_id,
        "import_job_id": payload.import_job_id,
        "recognized_board_id": payload.recognized_board_id,
        "sequence_number": payload.candidate.sequence_number,
        "status": payload.candidate.status,
        "board_checksum_sha256": payload.board_checksum_sha256,
        "board_confidence": payload.board_confidence,
        "sequence_confidence": payload.sequence_confidence,
        "source_pixel_count": payload.source_pixel_count,
        "primary_symbol_codes": list(payload.candidate.primary_symbol_codes),
        "alternative_symbol_codes": [
            list(alternatives) for alternatives in payload.candidate.alternative_symbol_codes
        ],
        "primary_match_tokens": list(payload.primary_match_tokens),
        "alternative_rank_1_match_tokens": list(payload.alternative_match_tokens(0)),
        "alternative_rank_2_match_tokens": list(payload.alternative_match_tokens(1)),
        "alternative_rank_3_match_tokens": list(payload.alternative_match_tokens(2)),
        "alternative_rank_4_match_tokens": list(payload.alternative_match_tokens(3)),
    }


def _payload_from_candidate(
    candidate: ImageBoardSearchCandidateModel,
) -> BoardSearchProjectionPayload:
    primary = tuple(candidate.primary_symbol_codes)
    alternatives = tuple(tuple(raw) for raw in candidate.alternative_symbol_codes)
    return BoardSearchProjectionPayload(
        game_id=candidate.game_id,
        import_job_id=candidate.import_job_id,
        recognized_board_id=candidate.recognized_board_id,
        candidate=BoardSearchCandidate(
            review_item_id=candidate.review_item_id,
            sequence_number=int(candidate.sequence_number),
            status=candidate.status,
            primary_symbol_codes=primary,
            alternative_symbol_codes=alternatives,
        ),
        board_checksum_sha256=candidate.board_checksum_sha256,
        board_confidence=candidate.board_confidence,
        sequence_confidence=candidate.sequence_confidence,
        source_pixel_count=int(candidate.source_pixel_count),
    )


__all__ = [
    "BoardSearchProjectionRebuildResult",
    "SqlAlchemyBoardSearchProjectionRepository",
]
