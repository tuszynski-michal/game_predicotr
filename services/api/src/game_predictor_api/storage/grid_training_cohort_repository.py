"""Runtime, game-scoped persistence for immutable geometry cohort operations."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_training_cohorts import (
    COMMAND_SECONDS,
    METADATA_PAGE_SIZE,
    POLICY,
    GridCohortError,
    digest,
    role_summary,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_training_cohort_models import (
    GridSourceIdentityCommandModel as IdentityCommand,
)
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortCommandModel as Command,
)
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortEventModel as Event,
)
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortMemberModel as Member,
)
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortModel as Cohort,
)
from game_predictor_api.storage.grid_training_cohort_models import (
    GridTrainingCohortPageModel as Page,
)
from game_predictor_api.storage.models import GameModel


class CohortDeadline:
    def __init__(self) -> None:
        self.end = time.monotonic() + COMMAND_SECONDS

    def check(self, session: Session | None = None) -> None:
        remaining = self.end - time.monotonic()
        if remaining <= 0:
            raise GridCohortError(
                "GRID_COHORT_TIMEOUT", "The command exceeded its 60 second budget.", 503
            )
        if session is not None and session.get_bind().dialect.name == "postgresql":
            session.execute(
                select(
                    func.set_config(
                        "statement_timeout", str(max(1, min(30_000, int(remaining * 1000)))), True
                    )
                )
            )

    def apply_statement_timeout(
        self, connection: Any, _query_cursor: Any, statement: str = ""
    ) -> None:
        words = statement.upper().split()
        if words == ["ROLLBACK"] or words[:3] == ["ROLLBACK", "TO", "SAVEPOINT"]:
            # An expected capability error leaves the savepoint aborted. SET
            # cannot precede its rollback, even when the command budget expired.
            return
        self.check()
        remaining = max(1, min(30_000, int((self.end - time.monotonic()) * 1000)))
        # A streamed query uses a named psycopg cursor, which cannot execute
        # SET (it would become DECLARE CURSOR FOR SET). A normal cursor on the
        # same DBAPI connection changes this transaction without another session.
        with connection.connection.dbapi_connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL statement_timeout={remaining}")


class SqlAlchemyGridTrainingCohortRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session, self.artifact_root = session, artifact_root

    def bind(self, game: UUID, *, write: bool = False) -> None:
        GameStorageRouter().bind(
            self.session, game, intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ
        )
        row = self.session.get(GameModel, game)
        if row is None or row.code == "7":
            raise GridCohortError(
                "GRID_COHORT_NOT_FOUND", "The requested geometry scope is unavailable.", 404
            )
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL lock_timeout='5s'"))
            self.session.execute(text("SET LOCAL statement_timeout='30s'"))

    def key_lock(self, game: UUID, kind: str, key: str) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            value = int(digest([POLICY, str(game), kind, key])[:16], 16) - 2**63
            self.session.execute(select(func.pg_advisory_xact_lock(value)))

    def cohort(self, game: UUID, identifier: UUID, *, lock: bool = False) -> Cohort:
        query = select(Cohort).where(Cohort.game_id == game, Cohort.id == identifier)
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise GridCohortError("GRID_COHORT_NOT_FOUND", "Cohort not found.", 404)
        return row

    def replay(
        self, game: UUID, kind: str, body: dict[str, Any], cohort: UUID | None
    ) -> dict[str, Any] | None:
        row = self.session.get(Command, (game, kind, UUID(body["idempotencyKey"])))
        if row:
            if row.command_sha256 != digest(
                {"cohortId": str(cohort) if cohort else None, "command": body}
            ):
                raise GridCohortError(
                    "GRID_COHORT_IDEMPOTENCY_CONFLICT", "The key has different command content."
                )
            return cast(dict[str, Any], row.document["response"])
        return None

    def receipt(
        self, game: UUID, cohort: Cohort, kind: str, body: dict[str, Any], outcome: str
    ) -> dict[str, Any]:
        self.session.flush()
        response = {
            "cohort": self.view(cohort),
            "receipt": {
                "idempotencyKey": body["idempotencyKey"],
                "kind": kind,
                "revision": cohort.revision,
                "outcome": outcome,
            },
        }
        self.session.add(
            Command(
                game_id=game,
                kind=kind,
                idempotency_key=UUID(body["idempotencyKey"]),
                cohort_id=cohort.id,
                command_sha256=digest(
                    {"cohortId": None if kind == "prepare" else str(cohort.id), "command": body}
                ),
                document={"command": body, "response": response},
            )
        )
        self.session.flush()
        return response

    def cas(self, row: Cohort, expected: int) -> None:
        if row.revision != expected:
            raise GridCohortError(
                "GRID_COHORT_REVISION_CONFLICT", "Reload the current cohort revision."
            )

    def members(
        self, game: UUID, cohort: UUID, after: int, limit: int = METADATA_PAGE_SIZE
    ) -> list[Member]:
        return list(
            self.session.scalars(
                select(Member)
                .where(Member.game_id == game, Member.cohort_id == cohort, Member.ordinal >= after)
                .order_by(Member.ordinal)
                .limit(limit)
            )
        )

    def iter_members(self, game: UUID, cohort: UUID) -> Iterator[Member]:
        after = 0
        while page := self.members(game, cohort, after):
            yield from page
            after = page[-1].ordinal + 1

    def pages(self, game: UUID, cohort: UUID, kind: str) -> Iterator[Page]:
        query = (
            select(Page)
            .where(Page.game_id == game, Page.cohort_id == cohort, Page.kind == kind)
            .order_by(Page.page_index)
        )
        yield from self.session.scalars(query.execution_options(yield_per=200))

    def event(self, game: UUID, cohort: UUID, kind: str, document: dict[str, Any]) -> None:
        self.session.add(
            Event(
                game_id=game,
                id=uuid4(),
                cohort_id=cohort,
                kind=kind,
                document=document,
                source_id=None,
                board_id=None,
                review_id=None,
                cell_id=None,
            )
        )

    def next_capture(self, row: Cohort) -> int | None:
        return self.session.scalar(
            select(func.min(Member.ordinal)).where(
                Member.game_id == row.game_id, Member.cohort_id == row.id, Member.frozen == {}
            )
        )

    def next_materialization(self, row: Cohort) -> int | None:
        value = self.session.scalar(
            select(func.max(Page.page_index)).where(
                Page.game_id == row.game_id,
                Page.cohort_id == row.id,
                Page.kind == "materialization",
            )
        )
        after = 0 if value is None else value + 5
        return self.session.scalar(
            select(func.min(Member.ordinal)).where(
                Member.game_id == row.game_id, Member.cohort_id == row.id, Member.ordinal >= after
            )
        )

    def refresh_summary(self, row: Cohort) -> None:
        row.summary = role_summary(
            row.document["mode"],
            (member.frozen for member in self.iter_members(row.game_id, row.id) if member.frozen),
        )

    def summary_view(self, row: Cohort) -> dict[str, Any]:
        result = json.loads(
            json.dumps(
                {
                    key: row.summary.get(key, [] if key == "roles" else {})
                    for key in ("roles", "reasonCounts")
                }
            )
        )
        counts = {item["role"]: {"boards": 0, "photos": 0, "full": 0} for item in result["roles"]}
        for page in self.pages(row.game_id, row.id, "materialization"):
            for source in page.document["sources"]:
                if source["used"]:
                    count = counts[source["role"]]
                    count["boards"] += source["boards"]
                    count["photos"] += 1
                    count["full"] += source["full"]
        for item in result["roles"]:
            count = counts[item["role"]]
            item.update(
                materializedBoards=count["boards"],
                materializedPhotos=count["photos"],
                materializedFullPhotos=count["full"],
            )
        return cast(dict[str, Any], result)

    def view(self, row: Cohort) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "gameId": str(row.game_id),
            "revision": row.revision,
            "status": row.status,
            "mode": row.document["mode"],
            "familyId": row.document["familyId"],
            "baseVersionId": row.document["baseVersionId"],
            "previewSha256": row.summary.get("previewSha256"),
            "manifestSha256": row.manifest_sha256,
            "summary": self.summary_view(row),
            "nextCaptureCursor": self.next_capture(row) if row.status == "preparing" else None,
            "nextMaterializationCursor": self.next_materialization(row)
            if row.status in ("preview_ready", "materializing")
            else None,
            "createdAt": (row.created_at or datetime.now(UTC)).isoformat(),
        }

    def recording_page(self, game: UUID, cohort: UUID, after_source: UUID | None) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            self.session.execute(
                text("SELECT public.recording_cohort_page_v3(:game,:cohort,:after,200)"),
                {"game": game, "cohort": cohort, "after": after_source},
            ).scalar_one(),
        )

    def recording_command(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        try:
            with self.session.begin_nested():
                return cast(
                    dict[str, Any],
                    self.session.execute(
                        text(
                            "SELECT public.recording_cohort_command_v3("
                            ":game,CAST(:body AS jsonb),:actor)"
                        ),
                        {"game": game, "body": json.dumps(command), "actor": actor},
                    ).scalar_one(),
                )
        except DBAPIError as error:
            code = str(error.orig).splitlines()[0]
            if code.startswith(("RECORDING_", "SOURCE_REMOVED_", "GRID_COHORT_")):
                raise GridCohortError(
                    code, "The recording dependency is unresolved or changed."
                ) from error
            if str(getattr(error.orig, "sqlstate", "")) in {"55P03", "57014"}:
                raise GridCohortError(
                    "GRID_COHORT_TIMEOUT",
                    "The metadata closure exceeded its bounded lock budget.",
                    503,
                ) from error
            raise

    def identity_replay(self, game: UUID, body: dict[str, Any]) -> dict[str, Any] | None:
        row = self.session.get(IdentityCommand, (game, UUID(body["idempotencyKey"])))
        if row and row.command_sha256 != digest(body):
            raise GridCohortError(
                "GRID_COHORT_IDEMPOTENCY_CONFLICT", "The identity key has different input."
            )
        return row.document["response"] if row else None
