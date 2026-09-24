"""SQLAlchemy repository computing D-437 board-import coverage for one game.

Two SQL passes feed the pure sweep in ``domain.board_import_coverage``:
gaps-and-islands over the "added" definition (D-437) and one query per
missing-reason category (see ``ai_docs/process/DECISION_LOG.md`` D-437 and
``ai_docs/tasks/completed/0629-board-import-coverage-definition.md``). Both passes are
scoped to the same read transaction so counts and segments stay consistent
with each other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import BigInteger, and_, func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from game_predictor_api.domain.board_import_coverage import (
    CoveragePage,
    MissingReason,
    ReasonSpan,
    SequenceInterval,
    build_coverage_page,
    count_missing_by_reason,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    parse_attested_sequence_range_filename,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageSequenceCanonicalModel,
    JobModel,
    RecognizedBoardModel,
)

_LIVE_STATUSES = ("pending", "accepted", "corrected")


@dataclass(frozen=True, slots=True)
class BoardImportCoverageCounts:
    expected: int
    added: int
    missing: int
    approved: int
    out_of_range: int


@dataclass(frozen=True, slots=True)
class BoardImportCoverageNotices:
    unnumbered_cut_board_count: int
    failed_sources_without_range_count: int
    active_import_job_count: int
    active_sources_without_range_count: int


@dataclass(frozen=True, slots=True)
class BoardImportCoverageReport:
    game_id: UUID
    expected_layout_count: int
    counts: BoardImportCoverageCounts
    missing_by_reason: dict[MissingReason, int]
    notices: BoardImportCoverageNotices
    view: str
    range_from: int | None
    range_to: int | None
    range_counts: tuple[int, int] | None  # (added, missing) in the requested range
    page: CoveragePage
    computed_at: datetime


class SqlAlchemyBoardImportCoverageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def expected_layout_count(self, game_id: UUID) -> int | None:
        return self._session.scalar(
            select(GameModel.expected_layout_count).where(GameModel.id == game_id)
        )

    def board_import_coverage(
        self,
        game_id: UUID,
        *,
        view: str,
        range_from: int | None = None,
        range_to: int | None = None,
        after_sequence_number: int | None = None,
        limit: int = 100,
    ) -> BoardImportCoverageReport | None:
        expected = self.expected_layout_count(game_id)
        if expected is None:
            return None
        # `games`/`jobs` are catalog tables in `public`, always reachable
        # without routing. Every table touched below (image_review_items,
        # recognized_boards, image_sequence_canonical, ...) is game-owned and
        # may live in `game_data_v2` — bind the session's search_path/RLS
        # scope to this game before touching any of them. Without this, none
        # of this router's endpoints sit under `/admin/games/{game_id}/...`,
        # so the app-wide `bind_game_storage_request` middleware never fires
        # for them, and ORM-level auto-detection never fires either (it only
        # inspects explicit `session.execute(stmt, params)` parameters, which
        # plain `select(...).where(Model.col == value)` never populates).
        GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)

        job_files = self._job_file_spans(game_id)
        added = self._added_islands(game_id, expected)
        reasons = self._reason_spans(game_id, expected, job_files)

        added_total = sum(interval.end - interval.start + 1 for interval in added)
        approved = int(
            self._session.scalar(
                select(func.count(func.distinct(ImageSequenceCanonicalModel.sequence_number)))
                .where(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.sequence_number.between(1, expected),
                )
            )
            or 0
        )
        out_of_range = int(
            self._session.scalar(
                select(func.count(func.distinct(ImageSequenceCanonicalModel.sequence_number))).where(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.sequence_number > expected,
                )
            )
            or 0
        )
        counts = BoardImportCoverageCounts(
            expected=expected,
            added=added_total,
            missing=expected - added_total,
            approved=approved,
            out_of_range=out_of_range,
        )
        missing_by_reason = count_missing_by_reason(expected=expected, added=added, reasons=reasons)
        notices = self._notices(game_id, job_files)

        page = build_coverage_page(
            expected=expected,
            added=added,
            reasons=reasons,
            view=view,
            range_from=range_from,
            range_to=range_to,
            after_sequence_number=after_sequence_number,
            limit=limit,
        )

        range_counts: tuple[int, int] | None = None
        if range_from is not None or range_to is not None:
            window_start = max(1, range_from or 1)
            window_end = min(expected, range_to or expected)
            if window_start <= window_end:
                window_added = sum(
                    max(0, min(interval.end, window_end) - max(interval.start, window_start) + 1)
                    for interval in added
                    if interval.start <= window_end and interval.end >= window_start
                )
                window_size = window_end - window_start + 1
                range_counts = (window_added, window_size - window_added)
            else:
                range_counts = (0, 0)

        return BoardImportCoverageReport(
            game_id=game_id,
            expected_layout_count=expected,
            counts=counts,
            missing_by_reason=missing_by_reason,
            notices=notices,
            view=view,
            range_from=range_from,
            range_to=range_to,
            range_counts=range_counts,
            page=page,
            computed_at=datetime.now(UTC),
        )

    def _added_islands(self, game_id: UUID, expected: int) -> list[SequenceInterval]:
        live_complete = (
            select(ImageReviewItemModel.sequence_number)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_LIVE_STATUSES),
                ImageReviewItemModel.sequence_number.between(1, expected),
                RecognizedBoardModel.completeness_status == "complete",
            )
        )
        canonical = select(ImageSequenceCanonicalModel.sequence_number).where(
            ImageSequenceCanonicalModel.game_id == game_id,
            ImageSequenceCanonicalModel.sequence_number.between(1, expected),
        )
        numbers = live_complete.union(canonical).subquery()
        return self._islands(numbers.c.sequence_number)

    def _islands(self, number_column: ColumnElement[int]) -> list[SequenceInterval]:
        ordered = select(
            number_column.label("n"),
            (
                number_column
                - func.row_number().over(order_by=number_column).cast(BigInteger)
            ).label("grp"),
        ).subquery()
        rows = self._session.execute(
            select(func.min(ordered.c.n), func.max(ordered.c.n))
            .group_by(ordered.c.grp)
            .order_by(func.min(ordered.c.n))
        ).all()
        return [SequenceInterval(int(start), int(end)) for start, end in rows]

    def _reason_spans(
        self,
        game_id: UUID,
        expected: int,
        job_files: tuple[list[tuple[UUID, str, str | None]], list[tuple[UUID, str]]],
    ) -> list[ReasonSpan]:
        spans: list[ReasonSpan] = []

        geometry_pending_rows = self._session.execute(
            select(
                ImageBoardGeometryPendingModel.sequence_number,
                ImageBoardGeometryPendingModel.reason_code,
            ).where(
                ImageBoardGeometryPendingModel.game_id == game_id,
                ImageBoardGeometryPendingModel.status == "pending",
                ImageBoardGeometryPendingModel.sequence_number.between(1, expected),
            )
        ).all()
        for sequence_number, reason_code in geometry_pending_rows:
            spans.append(
                ReasonSpan(
                    SequenceInterval(int(sequence_number), int(sequence_number)),
                    MissingReason.WAITING_FOR_GEOMETRY,
                    geometry_reason_code=reason_code,
                )
            )

        partial_rows = self._session.execute(
            select(ImageReviewItemModel.sequence_number)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.status.in_(_LIVE_STATUSES),
                ImageReviewItemModel.sequence_number.between(1, expected),
                RecognizedBoardModel.completeness_status == "pending_partial",
                ~select(ImageSequenceCanonicalModel.sequence_number)
                .where(
                    ImageSequenceCanonicalModel.game_id == game_id,
                    ImageSequenceCanonicalModel.sequence_number
                    == ImageReviewItemModel.sequence_number,
                )
                .exists(),
            )
        ).scalars().all()
        for sequence_number in partial_rows:
            assert sequence_number is not None  # filtered by .between(1, expected) above
            spans.append(
                ReasonSpan(
                    SequenceInterval(int(sequence_number), int(sequence_number)),
                    MissingReason.PARTIAL_SOURCE,
                )
            )

        rejected_rows = self._session.execute(
            select(func.distinct(ImageReviewItemModel.sequence_number))
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.status == "rejected",
                ImageReviewItemModel.sequence_number.between(1, expected),
                ~select(literal_column("1"))
                .select_from(ImageReviewItemModel.__table__.alias("live"))
                .where(
                    and_(
                        literal_column("live.game_id") == game_id,
                        literal_column("live.sequence_number")
                        == ImageReviewItemModel.sequence_number,
                        literal_column("live.status").in_(_LIVE_STATUSES),
                    )
                )
                .exists(),
            )
        ).scalars().all()
        for sequence_number in rejected_rows:
            spans.append(
                ReasonSpan(
                    SequenceInterval(int(sequence_number), int(sequence_number)),
                    MissingReason.REJECTED,
                )
            )

        superseded_rows = self._session.execute(
            select(func.distinct(ImageReviewItemModel.sequence_number))
            .where(
                ImageReviewItemModel.game_id == game_id,
                ImageReviewItemModel.status == "superseded",
                ImageReviewItemModel.sequence_number.between(1, expected),
                ~select(literal_column("1"))
                .select_from(ImageReviewItemModel.__table__.alias("live"))
                .where(
                    and_(
                        literal_column("live.game_id") == game_id,
                        literal_column("live.sequence_number")
                        == ImageReviewItemModel.sequence_number,
                        literal_column("live.status").in_((*_LIVE_STATUSES, "rejected")),
                    )
                )
                .exists(),
            )
        ).scalars().all()
        for sequence_number in superseded_rows:
            spans.append(
                ReasonSpan(
                    SequenceInterval(int(sequence_number), int(sequence_number)),
                    MissingReason.UNKNOWN,
                )
            )

        failed_files, active_files = job_files
        for job_id, path, error_code in failed_files:
            try:
                parsed = parse_attested_sequence_range_filename(path)
            except ImageGeometryContractError:
                continue
            clipped = SequenceInterval(max(1, parsed.start), min(expected, parsed.end))
            if clipped.start <= clipped.end:
                spans.append(
                    ReasonSpan(
                        clipped,
                        MissingReason.FAILED,
                        error_code=error_code,
                        import_job_id=job_id,
                    )
                )
        for job_id, path in active_files:
            try:
                parsed = parse_attested_sequence_range_filename(path)
            except ImageGeometryContractError:
                continue
            clipped = SequenceInterval(max(1, parsed.start), min(expected, parsed.end))
            if clipped.start <= clipped.end:
                spans.append(
                    ReasonSpan(clipped, MissingReason.IMPORT_IN_PROGRESS, import_job_id=job_id)
                )

        return spans

    def _job_file_spans(
        self, game_id: UUID
    ) -> tuple[list[tuple[UUID, str, str | None]], list[tuple[UUID, str]]]:
        failed = self._session.execute(
            select(
                ImageImportJobFileModel.job_id,
                ImageImportJobFileModel.source_relative_path,
                ImageImportJobFileModel.error_code,
            )
            .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMPORT,
                ImageImportJobFileModel.workflow_status == "failed",
            )
        ).all()
        active = self._session.execute(
            select(
                ImageImportJobFileModel.job_id,
                ImageImportJobFileModel.source_relative_path,
            )
            .join(JobModel, JobModel.id == ImageImportJobFileModel.job_id)
            .where(
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMPORT,
                JobModel.status.in_((JobStatus.CREATED, JobStatus.PROCESSING)),
                ImageImportJobFileModel.workflow_status == "processing",
            )
        ).all()
        return (
            [(row[0], row[1], row[2]) for row in failed],
            [(row[0], row[1]) for row in active],
        )

    def _notices(
        self,
        game_id: UUID,
        job_files: tuple[list[tuple[UUID, str, str | None]], list[tuple[UUID, str]]],
    ) -> BoardImportCoverageNotices:
        unnumbered = int(
            self._session.scalar(
                select(func.count())
                .select_from(ImageReviewItemModel)
                .where(
                    ImageReviewItemModel.game_id == game_id,
                    ImageReviewItemModel.sequence_number.is_(None),
                    ImageReviewItemModel.status.in_((*_LIVE_STATUSES, "rejected")),
                )
            )
            or 0
        )
        active_import_job_count = int(
            self._session.scalar(
                select(func.count())
                .select_from(JobModel)
                .where(
                    JobModel.game_id == game_id,
                    JobModel.job_type == JobType.IMPORT,
                    JobModel.status.in_((JobStatus.CREATED, JobStatus.PROCESSING)),
                )
            )
            or 0
        )
        failed_files, active_files = job_files
        failed_without_range = 0
        for _job_id, path, _error_code in failed_files:
            try:
                parse_attested_sequence_range_filename(path)
            except ImageGeometryContractError:
                failed_without_range += 1
        active_without_range = 0
        for _job_id, path in active_files:
            try:
                parse_attested_sequence_range_filename(path)
            except ImageGeometryContractError:
                active_without_range += 1
        return BoardImportCoverageNotices(
            unnumbered_cut_board_count=unnumbered,
            failed_sources_without_range_count=failed_without_range,
            active_import_job_count=active_import_job_count,
            active_sources_without_range_count=active_without_range,
        )


__all__ = [
    "BoardImportCoverageCounts",
    "BoardImportCoverageNotices",
    "BoardImportCoverageReport",
    "SqlAlchemyBoardImportCoverageRepository",
]
