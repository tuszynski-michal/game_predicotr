"""SQLAlchemy persistence for scoped Reviewer work assignments."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from game_predictor_api.application.reviewer_work_assignments import (
    ReviewerWorkAssignmentRepository,
)
from game_predictor_api.domain.jobs import JobStatus, JobType
from game_predictor_api.domain.reviewer_work_assignments import (
    ReviewerWorkAssignment,
    ReviewerWorkAssignmentConflictError,
    ReviewerWorkAssignmentType,
)
from game_predictor_api.storage.game_entity_locator import (
    GameEntityLocator,
    bind_located_game,
    session_is_scoped,
)
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
    GameStorageRoutingError,
    game_storage_scope,
)
from game_predictor_api.storage.models import (
    ImageReviewItemModel,
    JobModel,
    RecognizedBoardModel,
    ReviewerWorkAssignmentModel,
    SourceImageModel,
)
from game_predictor_api.storage.partition_constraints import resolve_unique_constraint_name

_ASSIGNMENTS_TABLE = "reviewer_work_assignments"


class SqlAlchemyReviewerWorkAssignmentRepository(ReviewerWorkAssignmentRepository):
    def __init__(
        self,
        session: Session,
        locator: GameEntityLocator | None = None,
        *,
        other_games_online: Callable[[UUID | None], Sequence[ReviewerWorkAssignment]] | None = None,
    ) -> None:
        self._session = session
        # TASK-0797: heartbeat/close name only the assignment id; the locator
        # binds the owning game first. Online capacity and the shared tunnel
        # span all games, which the application role sees only one game at a
        # time; ``other_games_online`` reads the remaining games.
        self._locator = locator
        self._other_games_online = other_games_online

    def lock_scope(self, game_id: UUID, import_job_id: UUID) -> bool:
        if not session_is_scoped(self._session):
            try:
                GameStorageRouter().bind(self._session, game_id, intent=GameStorageIntent.READ)
            except GameStorageRoutingError:
                return False
        job = self._session.scalar(
            select(JobModel)
            .where(
                JobModel.id == import_job_id,
                JobModel.game_id == game_id,
                JobModel.job_type == JobType.IMPORT,
            )
            .with_for_update()
        )
        if (
            job is None
            or (job.input_payload.get("importKind") or job.input_payload.get("import_kind"))
            != "image_directory"
            or job.status not in {JobStatus.WAITING_FOR_REVIEW, JobStatus.COMPLETED}
        ):
            return False
        review_item_id = self._session.scalar(
            select(ImageReviewItemModel.id)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .join(
                SourceImageModel,
                SourceImageModel.id == RecognizedBoardModel.source_image_id,
            )
            .where(SourceImageModel.import_job_id == import_job_id)
            .limit(1)
        )
        return review_item_id is not None

    def add(self, assignment: ReviewerWorkAssignment) -> ReviewerWorkAssignment:
        record = ReviewerWorkAssignmentModel(
            id=assignment.id,
            game_id=assignment.game_id,
            import_job_id=assignment.import_job_id,
            assignment_type=assignment.assignment_type.value,
            reviewer_access_session_id=assignment.reviewer_access_session_id,
            lease_owner=assignment.lease_owner,
            lease_token=assignment.lease_token,
            heartbeat_at=assignment.heartbeat_at,
            lease_expires_at=assignment.lease_expires_at,
            closed_at=assignment.closed_at,
            close_reason=assignment.close_reason,
            closed_by=assignment.closed_by,
            created_at=assignment.created_at,
            updated_at=assignment.updated_at,
        )
        try:
            # The savepoint keeps the transaction usable so that the violated
            # index can be resolved through the catalog (partition-aware).
            with self._session.begin_nested():
                self._session.add(record)
                self._session.flush()
        except IntegrityError as error:
            constraint = resolve_unique_constraint_name(
                self._session, error, ReviewerWorkAssignmentModel.__table__
            )
            if constraint == "uq_reviewer_work_assignments_active_import":
                raise ReviewerWorkAssignmentConflictError(
                    "REVIEWER_ASSIGNMENT_ALREADY_ACTIVE",
                    "The selected import already has an active work assignment.",
                    details={"importJobId": str(assignment.import_job_id)},
                ) from error
            raise ReviewerWorkAssignmentConflictError(
                "REVIEWER_ASSIGNMENT_PERSISTENCE_CONFLICT",
                "Reviewer work assignment conflicts with persisted data.",
            ) from error
        return _to_assignment(record)

    def get_for_update(self, assignment_id: UUID) -> ReviewerWorkAssignment | None:
        if not bind_located_game(
            self._session, self._locator, _ASSIGNMENTS_TABLE, "id", assignment_id
        ):
            return None
        record = self._session.scalar(
            select(ReviewerWorkAssignmentModel)
            .where(ReviewerWorkAssignmentModel.id == assignment_id)
            .with_for_update()
        )
        return None if record is None else _to_assignment(record)

    def get(self, assignment_id: UUID) -> ReviewerWorkAssignment | None:
        if not bind_located_game(
            self._session, self._locator, _ASSIGNMENTS_TABLE, "id", assignment_id
        ):
            return None
        record = self._session.get(ReviewerWorkAssignmentModel, assignment_id)
        return None if record is None else _to_assignment(record)

    def find_active_for_import(
        self,
        import_job_id: UUID,
    ) -> ReviewerWorkAssignment | None:
        record = self._session.scalar(
            select(ReviewerWorkAssignmentModel)
            .where(
                ReviewerWorkAssignmentModel.import_job_id == import_job_id,
                ReviewerWorkAssignmentModel.closed_at.is_(None),
            )
            .with_for_update()
        )
        return None if record is None else _to_assignment(record)

    def save_active(
        self,
        assignment: ReviewerWorkAssignment,
        *,
        expected_lease_token: UUID,
    ) -> ReviewerWorkAssignment:
        record = self._session.scalar(
            update(ReviewerWorkAssignmentModel)
            .where(
                ReviewerWorkAssignmentModel.id == assignment.id,
                ReviewerWorkAssignmentModel.lease_token == expected_lease_token,
                ReviewerWorkAssignmentModel.closed_at.is_(None),
            )
            .values(
                heartbeat_at=assignment.heartbeat_at,
                lease_expires_at=assignment.lease_expires_at,
                closed_at=assignment.closed_at,
                close_reason=assignment.close_reason,
                closed_by=assignment.closed_by,
                updated_at=assignment.updated_at,
            )
            .returning(ReviewerWorkAssignmentModel)
        )
        if record is None:
            raise ReviewerWorkAssignmentConflictError(
                "REVIEWER_ASSIGNMENT_LEASE_LOST",
                "The caller no longer owns an active lease for this assignment.",
                details={"assignmentId": str(assignment.id)},
            )
        return _to_assignment(record)

    def list_for_import(self, import_job_id: UUID) -> Sequence[ReviewerWorkAssignment]:
        return tuple(
            _to_assignment(record)
            for record in self._session.scalars(
                select(ReviewerWorkAssignmentModel)
                .where(ReviewerWorkAssignmentModel.import_job_id == import_job_id)
                .order_by(
                    ReviewerWorkAssignmentModel.created_at,
                    ReviewerWorkAssignmentModel.id,
                )
            )
        )

    def list_active_for_game(self, game_id: UUID) -> Sequence[ReviewerWorkAssignment]:
        return tuple(
            _to_assignment(record)
            for record in self._session.scalars(
                select(ReviewerWorkAssignmentModel)
                .where(
                    ReviewerWorkAssignmentModel.game_id == game_id,
                    ReviewerWorkAssignmentModel.closed_at.is_(None),
                )
                .order_by(
                    ReviewerWorkAssignmentModel.created_at,
                    ReviewerWorkAssignmentModel.id,
                )
            )
        )

    @contextmanager
    def lock_online_capacity(self) -> Iterator[None]:
        # The two stable 32-bit keys encode "GPRE" / "VIEW". PostgreSQL keeps
        # this transaction-scoped lock until commit/rollback, including after
        # this context exits, so a concurrent API transaction cannot pass the
        # capacity decision before the current assignment mutation is durable.
        self._session.execute(select(func.pg_advisory_xact_lock(0x47505245, 0x56494557)))
        yield

    def list_active_online_all_games(self) -> Sequence[ReviewerWorkAssignment]:
        """Open online assignments of every game (the shared tunnel and the cap).

        The bound game's rows come from this transaction; other games are read
        in their own READ-bound sessions. Every capacity mutation takes the
        global advisory lock first, so those reads cannot race a decision.
        """

        own = self.list_active_online()
        if self._other_games_online is None:
            return own
        current = GameStorageRouter.bound_game_id(self._session)
        return (*own, *self._other_games_online(current))

    def list_active_online(self) -> Sequence[ReviewerWorkAssignment]:
        """Open online assignments of the bound game only (locked for update)."""

        statement = select(ReviewerWorkAssignmentModel).where(
            ReviewerWorkAssignmentModel.assignment_type == ReviewerWorkAssignmentType.ONLINE.value,
            ReviewerWorkAssignmentModel.closed_at.is_(None),
        )
        current = GameStorageRouter.bound_game_id(self._session)
        if current is not None:
            # Explicit, so a schema-owner session (RLS bypass) sees the same rows.
            statement = statement.where(ReviewerWorkAssignmentModel.game_id == current)
        return tuple(
            _to_assignment(record)
            for record in self._session.scalars(
                statement.order_by(
                    ReviewerWorkAssignmentModel.created_at,
                    ReviewerWorkAssignmentModel.id,
                ).with_for_update()
            )
        )


class OtherGamesOnlineAssignments:
    """Read open online assignments of every game except one (TASK-0797).

    Each game is read in its own short READ-bound session, so the application
    role's RLS stays in force; the rows are not locked (the caller holds the
    global online-capacity advisory lock that every mutation takes).
    """

    def __init__(self, session_factory: Callable[[], Session], locator: GameEntityLocator) -> None:
        self._session_factory = session_factory
        self._locator = locator

    def __call__(self, exclude_game_id: UUID | None) -> Sequence[ReviewerWorkAssignment]:
        found: list[ReviewerWorkAssignment] = []
        for game_id in self._locator.registered_games():
            if game_id == exclude_game_id:
                continue
            # Its own scope: the caller's request scope must not rebind it.
            with game_storage_scope(game_id), self._session_factory() as session:
                try:
                    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
                except GameStorageRoutingError:
                    continue
                found.extend(
                    _to_assignment(record)
                    for record in session.scalars(
                        select(ReviewerWorkAssignmentModel).where(
                            ReviewerWorkAssignmentModel.game_id == game_id,
                            ReviewerWorkAssignmentModel.assignment_type
                            == ReviewerWorkAssignmentType.ONLINE.value,
                            ReviewerWorkAssignmentModel.closed_at.is_(None),
                        )
                    )
                )
                session.rollback()
        return tuple(found)


def _to_assignment(record: ReviewerWorkAssignmentModel) -> ReviewerWorkAssignment:
    return ReviewerWorkAssignment(
        id=record.id,
        game_id=record.game_id,
        import_job_id=record.import_job_id,
        assignment_type=ReviewerWorkAssignmentType(record.assignment_type),
        reviewer_access_session_id=record.reviewer_access_session_id,
        lease_owner=record.lease_owner,
        lease_token=record.lease_token,
        heartbeat_at=record.heartbeat_at,
        lease_expires_at=record.lease_expires_at,
        closed_at=record.closed_at,
        close_reason=record.close_reason,
        closed_by=record.closed_by,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


__all__ = ["OtherGamesOnlineAssignments", "SqlAlchemyReviewerWorkAssignmentRepository"]
