"""Persistence and backfill for the compact partial-board search projection."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast
from uuid import UUID

from sqlalchemy import Numeric, and_, case, delete, func, literal, or_, select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.domain.board_search import (
    BOARD_SEARCH_ALTERNATIVE_WEIGHTS,
    BOARD_SEARCH_CELL_COUNT,
    BoardSearchCandidate,
    BoardSearchError,
    BoardSearchProjectionPayload,
    BoardSearchQueryCell,
    BoardSearchResult,
    BoardSearchScope,
    BoardSearchScore,
    select_board_search_document,
)
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.storage.models import (
    CellObservationModel,
    GameModel,
    ImageBoardSearchCandidateModel,
    ImageBoardSearchFastDocumentModel,
    ImageBoardSearchProjectionStateModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
    SymbolModel,
)

_SEARCHABLE_STATUSES = frozenset({"pending", "accepted", "corrected"})
_REBUILD_BATCH_SIZE = 400


@dataclass(frozen=True, slots=True)
class BoardSearchProjectionRebuildResult:
    candidate_count: int
    document_count: int
    skipped_review_item_count: int


@dataclass(frozen=True, slots=True)
class BoardSearchProjectionState:
    game_id: UUID
    status: str
    candidate_count: int
    document_count: int
    skipped_review_item_count: int
    failure_message: str | None


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
        self.upsert_candidates((payload,))

    def upsert_candidates(self, payloads: Sequence[BoardSearchProjectionPayload]) -> None:
        if not payloads:
            return
        mobile_codes_by_game = _symbol_mobile_codes_by_game(self._session, payloads)
        values = [
            _candidate_values(payload, mobile_codes_by_game[payload.game_id])
            for payload in payloads
        ]
        insert_statement = postgresql_insert(ImageBoardSearchCandidateModel).values(values)
        update_statement = insert_statement.on_conflict_do_update(
            index_elements=[ImageBoardSearchCandidateModel.review_item_id],
            set_={
                key: getattr(insert_statement.excluded, key)
                for key in values[0]
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

    def sync_review_item(self, review_item_id: UUID) -> None:
        """Synchronize one changed review item and every affected document.

        The old candidate is read before mutation so a rejection or geometry
        correction removes its former search document as well.
        """

        previous = self._session.get(ImageBoardSearchCandidateModel, review_item_id)
        affected_sequences: set[tuple[UUID, int]] = set()
        if previous is not None:
            affected_sequences.add((previous.game_id, int(previous.sequence_number)))
        row = self._session.execute(
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
            .where(ImageReviewItemModel.id == review_item_id)
        ).one_or_none()
        if row is None:
            self.remove_candidate(review_item_id)
        else:
            payloads = _payloads_from_rows(
                self._session,
                (cast(ReviewProjectionRow, row),),
            )
            if not payloads:
                self.remove_candidate(review_item_id)
            else:
                payload = payloads[0]
                self.upsert_candidate(payload)
                affected_sequences.add((payload.game_id, payload.candidate.sequence_number))
        self._session.flush()
        for game_id, sequence_number in sorted(affected_sequences, key=_sequence_sort_key):
            self.reconcile_sequence(game_id, sequence_number)

    def sync_review_items(self, review_item_ids: Sequence[UUID]) -> None:
        for review_item_id in sorted(set(review_item_ids), key=str):
            self.sync_review_item(review_item_id)

    def sync_sequence_candidates(self, game_id: UUID, sequence_number: int) -> None:
        """Refresh every current candidate that could own one sequence document."""

        review_item_ids = self._session.scalars(
            select(ImageBoardSearchCandidateModel.review_item_id).where(
                ImageBoardSearchCandidateModel.game_id == game_id,
                ImageBoardSearchCandidateModel.sequence_number == sequence_number,
            )
        ).all()
        self.sync_review_items(tuple(review_item_ids))
        self.reconcile_sequence(game_id, sequence_number)

    def reconcile_import_job(self, import_job_id: UUID) -> None:
        """Refresh documents after the job's review visibility changes."""

        rows = self._session.execute(
            select(
                ImageBoardSearchCandidateModel.game_id,
                ImageBoardSearchCandidateModel.sequence_number,
            )
            .where(ImageBoardSearchCandidateModel.import_job_id == import_job_id)
            .distinct()
        ).all()
        for game_id, sequence_number in sorted(
            rows,
            key=lambda row: _sequence_sort_key((cast(UUID, row[0]), int(row[1]))),
        ):
            self.reconcile_sequence(cast(UUID, game_id), int(sequence_number))

    def start_rebuild(self, game_id: UUID) -> None:
        values = {
            "game_id": game_id,
            "status": "rebuilding",
            "candidate_count": 0,
            "document_count": 0,
            "skipped_review_item_count": 0,
            "failure_message": None,
        }
        statement = postgresql_insert(ImageBoardSearchProjectionStateModel).values(**values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ImageBoardSearchProjectionStateModel.game_id],
                set_={
                    **{key: value for key, value in values.items() if key != "game_id"},
                    "updated_at": func.now(),
                },
            )
        )

    def mark_rebuild_failed(self, game_id: UUID, failure_message: str) -> None:
        message = failure_message.strip()[:500] or "Board-search projection rebuild failed."
        values = {
            "game_id": game_id,
            "status": "failed",
            "candidate_count": 0,
            "document_count": 0,
            "skipped_review_item_count": 0,
            "failure_message": message,
        }
        statement = postgresql_insert(ImageBoardSearchProjectionStateModel).values(**values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ImageBoardSearchProjectionStateModel.game_id],
                set_={
                    **{key: value for key, value in values.items() if key != "game_id"},
                    "updated_at": func.now(),
                },
            )
        )

    def state_for_game(self, game_id: UUID) -> BoardSearchProjectionState | None:
        record = self._session.get(ImageBoardSearchProjectionStateModel, game_id)
        if record is None:
            return None
        return BoardSearchProjectionState(
            game_id=record.game_id,
            status=record.status,
            candidate_count=int(record.candidate_count),
            document_count=int(record.document_count),
            skipped_review_item_count=int(record.skipped_review_item_count),
            failure_message=record.failure_message,
        )

    def search(
        self,
        *,
        game_id: UUID,
        query: Sequence[BoardSearchQueryCell],
        scope: BoardSearchScope,
        limit: int,
    ) -> tuple[BoardSearchResult, ...]:
        if self._session.get(GameModel, game_id) is None:
            raise BoardSearchError("GAME_NOT_FOUND", "The selected game does not exist.")
        state = self.state_for_game(game_id)
        if state is None or state.status != "ready":
            raise BoardSearchError(
                "BOARD_SEARCH_PROJECTION_INCOMPLETE",
                "The board-search projection is not ready for this game.",
            )
        active_mobile_codes: dict[str, int] = {
            code: int(mobile_code)
            for code, mobile_code in self._session.execute(
                select(SymbolModel.code, SymbolModel.mobile_code).where(
                    SymbolModel.game_id == game_id,
                    SymbolModel.status == SymbolStatus.ACTIVE,
                )
            ).tuples()
        }
        if any(cell.symbol_code is None for cell in query):
            raise BoardSearchError(
                "BOARD_SEARCH_QUERY_EMPTY",
                "Select at least one known symbol before searching boards.",
            )
        if any(cell.symbol_code not in active_mobile_codes for cell in query):
            raise BoardSearchError(
                "BOARD_SEARCH_SYMBOL_INVALID",
                "Every board-search symbol must be active in the selected game.",
            )

        document = ImageBoardSearchFastDocumentModel
        mobile_codes_by_cell = {
            cell.cell_index: int(active_mobile_codes[cell.symbol_code])
            for cell in query
            if cell.symbol_code is not None
        }
        positive_evidence = _positive_evidence_expression(
            document,
            query,
            mobile_codes_by_cell=mobile_codes_by_cell,
        )
        scope_filter = (
            document.status.in_(("accepted", "corrected"))
            if scope is BoardSearchScope.APPROVED_ONLY
            else literal(True)
        )
        (
            score_expression,
            exact_expression,
            alternative_expression,
            weighted_alternative,
            mismatch,
            unknown,
        ) = _search_score_expressions(
            document,
            query,
            mobile_codes_by_cell=mobile_codes_by_cell,
        )
        status_priority = case(
            (document.status.in_(("accepted", "corrected")), 0),
            else_=1,
        )
        statement = (
            select(
                document.review_item_id,
                document.recognized_board_id,
                document.import_job_id,
                document.sequence_number,
                document.status,
                document.board_checksum_sha256,
                score_expression.label("score"),
                exact_expression.label("exact_match_count"),
                alternative_expression.label("alternative_match_count"),
                weighted_alternative.label("weighted_alternative_score"),
                mismatch.label("mismatch_count"),
                unknown.label("unknown_count"),
            )
            .where(document.game_id == game_id, positive_evidence, scope_filter)
            .order_by(
                score_expression.desc(),
                exact_expression.desc(),
                weighted_alternative.desc(),
                mismatch.asc(),
                status_priority.asc(),
                document.sequence_number.asc(),
                document.review_item_id.asc(),
            )
            .limit(limit)
        )
        return tuple(
            BoardSearchResult(
                review_item_id=review_item_id,
                recognized_board_id=recognized_board_id,
                import_job_id=import_job_id,
                sequence_number=int(sequence_number),
                status=status,
                board_checksum_sha256=board_checksum_sha256,
                score=BoardSearchScore(
                    score=float(score),
                    exact_match_count=int(exact_match_count),
                    alternative_match_count=int(alternative_match_count),
                    weighted_alternative_score=float(weighted_alternative_score),
                    mismatch_count=int(mismatch_count),
                    unknown_count=int(unknown_count),
                ),
            )
            for (
                review_item_id,
                recognized_board_id,
                import_job_id,
                sequence_number,
                status,
                board_checksum_sha256,
                score,
                exact_match_count,
                alternative_match_count,
                weighted_alternative_score,
                mismatch_count,
                unknown_count,
            ) in self._session.execute(statement).all()
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
                delete(ImageBoardSearchFastDocumentModel).where(
                    ImageBoardSearchFastDocumentModel.game_id == game_id,
                    ImageBoardSearchFastDocumentModel.sequence_number == sequence_number,
                )
            )
            return
        selected_candidate = next(
            candidate
            for candidate, _job in rows
            if candidate.review_item_id == selection.review_item_id
        )
        fast_values = _fast_document_values(selected_candidate)
        self._session.execute(
            delete(ImageBoardSearchFastDocumentModel).where(
                ImageBoardSearchFastDocumentModel.review_item_id == selection.review_item_id,
                ImageBoardSearchFastDocumentModel.sequence_number != sequence_number,
            )
        )
        fast_statement = postgresql_insert(ImageBoardSearchFastDocumentModel).values(**fast_values)
        self._session.execute(
            fast_statement.on_conflict_do_update(
                index_elements=[
                    ImageBoardSearchFastDocumentModel.game_id,
                    ImageBoardSearchFastDocumentModel.sequence_number,
                ],
                set_={
                    **{
                        key: value
                        for key, value in fast_values.items()
                        if key not in {"game_id", "sequence_number"}
                    },
                    "updated_at": func.now(),
                },
            )
        )

    def rebuild_game(self, game_id: UUID) -> BoardSearchProjectionRebuildResult:
        """Rebuild one game atomically from review records in bounded batches."""

        self._session.execute(
            delete(ImageBoardSearchFastDocumentModel).where(
                ImageBoardSearchFastDocumentModel.game_id == game_id
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
        last_review_item_id: UUID | None = None
        while True:
            review_item_ids = self._session.scalars(
                select(ImageReviewItemModel.id)
                .join(
                    RecognizedBoardModel,
                    RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
                )
                .join(SourceImageModel, SourceImageModel.id == RecognizedBoardModel.source_image_id)
                .join(JobModel, JobModel.id == SourceImageModel.import_job_id)
                .where(
                    JobModel.game_id == game_id,
                    *(
                        ()
                        if last_review_item_id is None
                        else (ImageReviewItemModel.id > last_review_item_id,)
                    ),
                )
                .order_by(ImageReviewItemModel.id)
                .limit(_REBUILD_BATCH_SIZE)
            ).all()
            if not review_item_ids:
                break
            last_review_item_id = review_item_ids[-1]
            rows = self._session.execute(
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
                .where(ImageReviewItemModel.id.in_(review_item_ids))
                .order_by(ImageReviewItemModel.id)
            ).all()
            batch = tuple(cast(ReviewProjectionRow, row) for row in rows)
            payloads = _payloads_from_rows(self._session, batch)
            candidate_count += len(payloads)
            skipped_count += len(batch) - len(payloads)
            self.upsert_candidates(payloads)
            self._session.flush()

        self._rebuild_fast_documents(game_id)
        self._session.flush()
        document_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(ImageBoardSearchFastDocumentModel)
                .where(ImageBoardSearchFastDocumentModel.game_id == game_id)
            )
            or 0
        )
        result = BoardSearchProjectionRebuildResult(
            candidate_count=candidate_count,
            document_count=document_count,
            skipped_review_item_count=skipped_count,
        )
        self._mark_ready(game_id, result)
        return result

    def mark_live_projection_ready(self, game_id: UUID) -> None:
        """Mark a new game ready after its complete import becomes reviewable."""

        state = self._session.get(ImageBoardSearchProjectionStateModel, game_id)
        if state is None:
            self._session.add(
                ImageBoardSearchProjectionStateModel(
                    game_id=game_id,
                    status="ready",
                    candidate_count=0,
                    document_count=0,
                    skipped_review_item_count=0,
                    failure_message=None,
                )
            )
        elif state.status != "rebuilding":
            state.status = "ready"
            state.failure_message = None

    def _mark_ready(self, game_id: UUID, result: BoardSearchProjectionRebuildResult) -> None:
        values = {
            "game_id": game_id,
            "status": "ready",
            "candidate_count": result.candidate_count,
            "document_count": result.document_count,
            "skipped_review_item_count": result.skipped_review_item_count,
            "failure_message": None,
        }
        statement = postgresql_insert(ImageBoardSearchProjectionStateModel).values(**values)
        self._session.execute(
            statement.on_conflict_do_update(
                index_elements=[ImageBoardSearchProjectionStateModel.game_id],
                set_={
                    **{key: value for key, value in values.items() if key != "game_id"},
                    "updated_at": func.now(),
                },
            )
        )

    def _rebuild_fast_documents(self, game_id: UUID) -> None:
        canonical = ImageSequenceCanonicalModel
        candidate = ImageBoardSearchCandidateModel
        eligibility = case(
            (candidate.review_item_id == canonical.review_item_id, 2),
            (
                (candidate.status == "pending") & (JobModel.status == JobStatus.WAITING_FOR_REVIEW),
                1,
            ),
            else_=0,
        )
        ranked = (
            select(
                candidate.game_id.label("game_id"),
                candidate.sequence_number.label("sequence_number"),
                candidate.review_item_id.label("review_item_id"),
                candidate.recognized_board_id.label("recognized_board_id"),
                candidate.import_job_id.label("import_job_id"),
                candidate.status.label("status"),
                candidate.board_checksum_sha256.label("board_checksum_sha256"),
                candidate.known_evidence_positions.label("known_evidence_positions"),
                candidate.primary_symbol_mobile_codes.label("primary_symbol_mobile_codes"),
                candidate.alternative_rank_1_mobile_codes.label("alternative_rank_1_mobile_codes"),
                candidate.alternative_rank_2_mobile_codes.label("alternative_rank_2_mobile_codes"),
                candidate.alternative_rank_3_mobile_codes.label("alternative_rank_3_mobile_codes"),
                candidate.alternative_rank_4_mobile_codes.label("alternative_rank_4_mobile_codes"),
                func.row_number()
                .over(
                    partition_by=(candidate.game_id, candidate.sequence_number),
                    order_by=(
                        eligibility.desc(),
                        candidate.board_confidence.desc(),
                        candidate.sequence_confidence.desc(),
                        candidate.source_pixel_count.desc(),
                        candidate.review_item_id.asc(),
                    ),
                )
                .label("selection_rank"),
                eligibility.label("eligibility"),
            )
            .join(JobModel, JobModel.id == candidate.import_job_id)
            .outerjoin(
                canonical,
                (canonical.game_id == candidate.game_id)
                & (canonical.sequence_number == candidate.sequence_number),
            )
            .where(candidate.game_id == game_id)
            .subquery()
        )
        selected = select(
            ranked.c.game_id,
            ranked.c.sequence_number,
            ranked.c.review_item_id,
            ranked.c.recognized_board_id,
            ranked.c.import_job_id,
            ranked.c.status,
            ranked.c.board_checksum_sha256,
            ranked.c.known_evidence_positions,
            ranked.c.primary_symbol_mobile_codes,
            ranked.c.alternative_rank_1_mobile_codes,
            ranked.c.alternative_rank_2_mobile_codes,
            ranked.c.alternative_rank_3_mobile_codes,
            ranked.c.alternative_rank_4_mobile_codes,
        ).where(ranked.c.eligibility > 0, ranked.c.selection_rank == 1)
        statement = postgresql_insert(ImageBoardSearchFastDocumentModel).from_select(
            [
                ImageBoardSearchFastDocumentModel.game_id,
                ImageBoardSearchFastDocumentModel.sequence_number,
                ImageBoardSearchFastDocumentModel.review_item_id,
                ImageBoardSearchFastDocumentModel.recognized_board_id,
                ImageBoardSearchFastDocumentModel.import_job_id,
                ImageBoardSearchFastDocumentModel.status,
                ImageBoardSearchFastDocumentModel.board_checksum_sha256,
                ImageBoardSearchFastDocumentModel.known_evidence_positions,
                ImageBoardSearchFastDocumentModel.primary_symbol_mobile_codes,
                ImageBoardSearchFastDocumentModel.alternative_rank_1_mobile_codes,
                ImageBoardSearchFastDocumentModel.alternative_rank_2_mobile_codes,
                ImageBoardSearchFastDocumentModel.alternative_rank_3_mobile_codes,
                ImageBoardSearchFastDocumentModel.alternative_rank_4_mobile_codes,
            ],
            selected,
        )
        self._session.execute(statement)


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
        primary = tuple(
            cast(str, symbol) if symbol is not None else None
            for symbol in cast(Sequence[object], raw_symbols)
        )
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

    board_identity_checksum = (
        board.board_checksum_sha256
        if board.asset_mode == "legacy_file"
        else board.geometry_checksum_sha256
    )
    if board_identity_checksum is None:
        return None

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
        board_checksum_sha256=board_identity_checksum,
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
        and all(symbol is None or (isinstance(symbol, str) and symbol.strip()) for symbol in value)
    )


def _symbol_mobile_codes_by_game(
    session: Session,
    payloads: Sequence[BoardSearchProjectionPayload],
) -> dict[UUID, dict[str, int]]:
    game_ids = tuple(sorted({payload.game_id for payload in payloads}, key=str))
    mobile_codes_by_game: dict[UUID, dict[str, int]] = defaultdict(dict)
    for game_id, code, mobile_code in session.execute(
        select(SymbolModel.game_id, SymbolModel.code, SymbolModel.mobile_code).where(
            SymbolModel.game_id.in_(game_ids)
        )
    ):
        mobile_codes_by_game[game_id][code] = int(mobile_code)
    return mobile_codes_by_game


def _candidate_values(
    payload: BoardSearchProjectionPayload,
    symbol_mobile_codes: Mapping[str, int],
) -> dict[str, object]:
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
        "known_evidence_positions": list(payload.known_evidence_positions),
        "primary_symbol_mobile_codes": _mobile_codes(
            payload.candidate.primary_symbol_codes,
            symbol_mobile_codes,
        ),
        "alternative_rank_1_mobile_codes": _alternative_mobile_codes(
            payload,
            rank=0,
            symbol_mobile_codes=symbol_mobile_codes,
        ),
        "alternative_rank_2_mobile_codes": _alternative_mobile_codes(
            payload,
            rank=1,
            symbol_mobile_codes=symbol_mobile_codes,
        ),
        "alternative_rank_3_mobile_codes": _alternative_mobile_codes(
            payload,
            rank=2,
            symbol_mobile_codes=symbol_mobile_codes,
        ),
        "alternative_rank_4_mobile_codes": _alternative_mobile_codes(
            payload,
            rank=3,
            symbol_mobile_codes=symbol_mobile_codes,
        ),
    }


def _fast_document_values(candidate: ImageBoardSearchCandidateModel) -> dict[str, object]:
    return {
        "game_id": candidate.game_id,
        "sequence_number": int(candidate.sequence_number),
        "review_item_id": candidate.review_item_id,
        "recognized_board_id": candidate.recognized_board_id,
        "import_job_id": candidate.import_job_id,
        "status": candidate.status,
        "board_checksum_sha256": candidate.board_checksum_sha256,
        "known_evidence_positions": candidate.known_evidence_positions,
        "primary_symbol_mobile_codes": candidate.primary_symbol_mobile_codes,
        "alternative_rank_1_mobile_codes": candidate.alternative_rank_1_mobile_codes,
        "alternative_rank_2_mobile_codes": candidate.alternative_rank_2_mobile_codes,
        "alternative_rank_3_mobile_codes": candidate.alternative_rank_3_mobile_codes,
        "alternative_rank_4_mobile_codes": candidate.alternative_rank_4_mobile_codes,
    }


def _mobile_codes(
    symbol_codes: Sequence[str | None],
    symbol_mobile_codes: Mapping[str, int],
) -> list[int | None]:
    return [None if code is None else symbol_mobile_codes.get(code) for code in symbol_codes]


def _alternative_mobile_codes(
    payload: BoardSearchProjectionPayload,
    *,
    rank: int,
    symbol_mobile_codes: Mapping[str, int],
) -> list[int | None]:
    return _mobile_codes(
        tuple(
            alternatives[rank] if rank < len(alternatives) else None
            for alternatives in payload.candidate.alternative_symbol_codes
        ),
        symbol_mobile_codes,
    )


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


def _search_score_expressions(
    candidate: type[ImageBoardSearchCandidateModel] | type[ImageBoardSearchFastDocumentModel],
    query: Sequence[BoardSearchQueryCell],
    *,
    mobile_codes_by_cell: Mapping[int, int],
) -> tuple[
    ColumnElement[Any],
    ColumnElement[Any],
    ColumnElement[Any],
    ColumnElement[Any],
    ColumnElement[Any],
    ColumnElement[Any],
]:
    weighted_evidence: ColumnElement[Any] = literal(0.0)
    exact_count: ColumnElement[Any] = literal(0)
    alternative_count: ColumnElement[Any] = literal(0)
    weighted_alternative: ColumnElement[Any] = literal(0.0)
    mismatch_count: ColumnElement[Any] = literal(0)
    unknown_count: ColumnElement[Any] = literal(0)
    for cell in query:
        mobile_code = mobile_codes_by_cell[cell.cell_index]
        postgres_index = cell.cell_index + 1
        primary_matches = candidate.primary_symbol_mobile_codes[postgres_index] == mobile_code
        has_pending_status = candidate.status == "pending"
        alternative_matches = (
            and_(
                has_pending_status,
                candidate.alternative_rank_1_mobile_codes[postgres_index] == mobile_code,
            ),
            and_(
                has_pending_status,
                candidate.alternative_rank_2_mobile_codes[postgres_index] == mobile_code,
            ),
            and_(
                has_pending_status,
                candidate.alternative_rank_3_mobile_codes[postgres_index] == mobile_code,
            ),
            and_(
                has_pending_status,
                candidate.alternative_rank_4_mobile_codes[postgres_index] == mobile_code,
            ),
        )
        matched = or_(primary_matches, *alternative_matches)
        has_known_evidence = candidate.known_evidence_positions.contains([str(cell.cell_index)])
        alternative_weight = case(
            (primary_matches, 0.0),
            *(
                (alternative_matches[rank], weight)
                for rank, weight in enumerate(BOARD_SEARCH_ALTERNATIVE_WEIGHTS)
            ),
            else_=0.0,
        )
        weighted_evidence = weighted_evidence + case(
            (primary_matches, 1.0),
            *(
                (alternative_matches[rank], weight)
                for rank, weight in enumerate(BOARD_SEARCH_ALTERNATIVE_WEIGHTS)
            ),
            else_=0.0,
        )
        exact_count = exact_count + case((primary_matches, 1), else_=0)
        alternative_count = alternative_count + case(
            (primary_matches, 0),
            (or_(*alternative_matches), 1),
            else_=0,
        )
        weighted_alternative = weighted_alternative + alternative_weight
        mismatch_count = mismatch_count + case(
            (matched, 0),
            (has_known_evidence, 1),
            else_=0,
        )
        unknown_count = unknown_count + case(
            (matched, 0),
            (has_known_evidence, 0),
            else_=1,
        )
    score = func.round(
        (weighted_evidence * literal(100.0 / len(query))).cast(Numeric(10, 6)),
        1,
    )
    return (
        score,
        exact_count,
        alternative_count,
        weighted_alternative,
        mismatch_count,
        unknown_count,
    )


def _positive_evidence_expression(
    document: type[ImageBoardSearchFastDocumentModel],
    query: Sequence[BoardSearchQueryCell],
    *,
    mobile_codes_by_cell: Mapping[int, int],
) -> ColumnElement[bool]:
    matches: list[ColumnElement[bool]] = []
    for cell in query:
        mobile_code = mobile_codes_by_cell[cell.cell_index]
        postgres_index = cell.cell_index + 1
        matches.extend(
            (
                document.primary_symbol_mobile_codes[postgres_index] == mobile_code,
                and_(
                    document.status == "pending",
                    document.alternative_rank_1_mobile_codes[postgres_index] == mobile_code,
                ),
                and_(
                    document.status == "pending",
                    document.alternative_rank_2_mobile_codes[postgres_index] == mobile_code,
                ),
                and_(
                    document.status == "pending",
                    document.alternative_rank_3_mobile_codes[postgres_index] == mobile_code,
                ),
                and_(
                    document.status == "pending",
                    document.alternative_rank_4_mobile_codes[postgres_index] == mobile_code,
                ),
            )
        )
    return or_(*matches)


def _sequence_sort_key(value: tuple[UUID, int]) -> tuple[str, int]:
    return str(value[0]), value[1]


__all__ = [
    "BoardSearchProjectionRebuildResult",
    "BoardSearchProjectionState",
    "SqlAlchemyBoardSearchProjectionRepository",
]
