"""A fresh READ COMMITTED metadata-only transaction closes actual recording use."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import event, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_training_cohorts import GridCohortError, require_minima
from game_predictor_api.storage.grid_training_cohort_currentness import check_member
from game_predictor_api.storage.grid_training_cohort_repository import (
    CohortDeadline,
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.models import GameModel
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock

if TYPE_CHECKING:
    from game_predictor_api.application.grid_training_cohorts import GridTrainingCohortService


def _lock_inputs(
    repo: SqlAlchemyGridTrainingCohortRepository,
    game: UUID,
    identifier: UUID,
    deadline: CohortDeadline,
) -> None:
    session = repo.session
    # Catalogue -> recording registry -> owner -> game projection -> every
    # sequence ascending -> every source ascending -> board/review/cell rows.
    session.execute(text("SELECT pg_advisory_xact_lock(9910994)"))
    session.execute(text("SELECT pg_advisory_xact_lock(9921002)"))
    acquire_sequence_ownership_lock(session, game_id=game)
    session.execute(select(GameModel.id).where(GameModel.id == game).with_for_update())
    sequences = session.execute(
        text("""SELECT DISTINCT b.sequence_number
      FROM recognized_boards b JOIN grid_training_cohort_members m
      ON m.game_id=b.game_id AND m.source_id=b.source_image_id
      WHERE m.game_id=:game AND m.cohort_id=:cohort AND m.frozen->'used'='true'::jsonb
      ORDER BY b.sequence_number""").execution_options(yield_per=200),
        {"game": game, "cohort": identifier},
    ).scalars()
    for sequence in sequences:
        deadline.check(session)
        acquire_image_sequence_locks(session, game_id=game, sequence_numbers=[sequence])
    # Server-side streaming retains only one bounded cursor buffer. The database
    # orders the complete set before locking; no cross-page ordering reversal.
    sources = session.execute(
        text("""SELECT s.id FROM source_images s
      JOIN grid_training_cohort_members m ON m.game_id=s.game_id AND m.source_id=s.id
      WHERE m.game_id=:game AND m.cohort_id=:cohort AND m.frozen->'used'='true'::jsonb
      ORDER BY s.id FOR UPDATE OF s""").execution_options(yield_per=200),
        {"game": game, "cohort": identifier},
    )
    for _ in sources:
        deadline.check(session)
    for table, identifier_column in (
        ("recognized_boards", "board_ids"),
        ("image_review_items", "review_ids"),
        ("image_symbol_review_cells", "cell_ids"),
    ):
        rows = session.execute(
            text(f"""SELECT r.id FROM {table} r WHERE r.game_id=:game
          AND EXISTS(SELECT 1 FROM grid_training_cohort_members m WHERE m.game_id=:game
          AND m.cohort_id=:cohort AND m.frozen->'used'='true'::jsonb
          AND m.{identifier_column} @> ARRAY[r.id])
          ORDER BY r.id FOR UPDATE OF r""").execution_options(yield_per=200),
            {"game": game, "cohort": identifier},
        )
        for _ in rows:
            deadline.check(session)


def freeze(
    service: GridTrainingCohortService,
    game: UUID,
    identifier: UUID,
    body: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    deadline = CohortDeadline()
    request_repo = service.repository
    request_repo.bind(game)
    if replay := request_repo.replay(game, "freeze", body, identifier):
        return replay
    before = request_repo.cohort(game, identifier)
    request_repo.cas(before, body["expectedRevision"])
    if (
        before.status != "ready_to_freeze"
        or before.manifest_path is None
        or before.manifest_sha256 != body["expectedManifestSha256"]
        or before.summary.get("previewSha256") != body["expectedPreviewSha256"]
    ):
        raise GridCohortError(
            "GRID_COHORT_MANIFEST_CONFLICT", "The shown immutable preview or manifest differs."
        )
    # All bytes and metadata files are verified before the write transaction.
    root = service.artifacts.read_json(before.manifest_path, before.manifest_sha256)
    for page in request_repo.pages(game, identifier, "materialization"):
        value = service.artifacts.read_json(page.path, page.sha256)
        for source in value["sources"]:
            if source["used"]:
                descriptor = source["original"]
                service.artifacts.verify(
                    descriptor["path"], descriptor["sha256"], size=descriptor["bytes"]
                )
        deadline.check()
    if root["previewSha256"] != body["expectedPreviewSha256"]:
        raise GridCohortError("GRID_COHORT_MANIFEST_CONFLICT", "The root preview binding differs.")
    caller_role = request_repo.session.execute(text("SELECT current_user")).scalar_one()
    bind = request_repo.session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    with (
        engine.connect().execution_options(isolation_level="READ COMMITTED") as connection,
        connection.begin(),
    ):

        def budget(
            _connection: Any,
            cursor: Any,
            _statement: Any,
            _parameters: Any,
            _context: Any,
            _many: Any,
        ) -> None:
            deadline.apply_statement_timeout(_connection, cursor, _statement)

        event.listen(connection, "before_cursor_execute", budget)
        connection.exec_driver_sql("SET TRANSACTION READ WRITE")
        quoted = connection.dialect.identifier_preparer.quote(caller_role)
        connection.exec_driver_sql(f"SET LOCAL ROLE {quoted}")
        if not connection.execute(
            text(
                "SELECT NOT rolsuper AND NOT rolbypassrls FROM pg_roles WHERE rolname=current_user"
            )
        ).scalar_one():
            raise GridCohortError(
                "RUNTIME_ROLE_REQUIRED", "Freeze requires the restricted runtime identity.", 403
            )
        with Session(bind=connection) as session:
            repo = SqlAlchemyGridTrainingCohortRepository(session, service.artifacts.root)
            repo.bind(game, write=True)
            repo.key_lock(game, "freeze", body["idempotencyKey"])
            if replay := repo.replay(game, "freeze", body, identifier):
                return replay
            _lock_inputs(repo, game, identifier, deadline)
            row = repo.cohort(game, identifier, lock=True)
            repo.cas(row, body["expectedRevision"])
            if (
                row.status != "ready_to_freeze"
                or row.manifest_sha256 != body["expectedManifestSha256"]
                or row.summary.get("previewSha256") != body["expectedPreviewSha256"]
            ):
                raise GridCohortError(
                    "GRID_COHORT_MANIFEST_CONFLICT",
                    "The immutable root changed before closure.",
                )
            require_minima(row.summary)
            for member in repo.iter_members(game, identifier):
                deadline.check(session)
                check_member(repo, member)
            result = repo.recording_command(
                game,
                {
                    "kind": "register_cohort_use",
                    "idempotencyKey": body["idempotencyKey"],
                    "cohortId": str(identifier),
                    "expectedRevision": row.revision,
                    "manifestSha256": row.manifest_sha256,
                },
                actor,
            )
            row.status, row.revision = "frozen", row.revision + 1
            repo.event(
                game,
                identifier,
                "frozen",
                {"recordingUse": result, "manifestSha256": row.manifest_sha256},
            )
            response = repo.receipt(game, row, "freeze", body, "frozen")
            session.flush()
            return response
