"""A single runtime/RLS repeatable-read capture and retained command receipts."""

import copy
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from uuid import UUID, uuid4

from sqlalchemy import Connection, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_model_snapshots import uses_neural_grid
from game_predictor_api.domain.grid_quality_measurements import (
    POLICY,
    POPULATION_POLICY,
    PopulationSampler,
    digest,
    empty_judgments,
    measurement_report,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.grid_quality_manifest import GridQualityManifestStore
from game_predictor_api.storage.grid_quality_measurement_models import (
    GridQualityMeasurementCommandModel as Command,
)
from game_predictor_api.storage.grid_quality_measurement_models import (
    GridQualityMeasurementJudgmentModel as Judgment,
)
from game_predictor_api.storage.grid_quality_measurement_models import (
    GridQualityMeasurementMemberModel as Member,
)
from game_predictor_api.storage.grid_quality_measurement_models import (
    GridQualityMeasurementModel as Measurement,
)
from game_predictor_api.storage.grid_quality_observations import (
    approval_blocker,
    current_targets,
    freeze_member,
    observation,
    read_source,
    symbol_confirmation_count,
)
from game_predictor_api.storage.grid_quality_repoint import unchanged_frozen_target
from game_predictor_api.storage.grid_reinference import source_fence
from game_predictor_api.storage.image_geometry_completeness_repository import _IMAGE_STATES_CTE
from game_predictor_api.storage.models import GameModel

CAPTURE_SECONDS = 60
PAGE_SIZE = 500


def conflict(code: str, message: str) -> NoReturn:
    raise ImageReviewConflictError("GRID_QUALITY_" + code, message)


def now() -> str:
    return datetime.now(UTC).isoformat()


class CaptureDeadline:
    def __init__(self) -> None:
        self.expires = time.monotonic() + CAPTURE_SECONDS

    def apply(self, session: Session) -> None:
        remaining = self.expires - time.monotonic()
        if remaining <= 0:
            conflict("CAPTURE_TIMEOUT", "The capture exceeded its 60 second deadline.")
        session.execute(
            select(
                func.set_config(
                    "statement_timeout",
                    str(min(30_000, max(1, math.floor(remaining * 1000)))),
                    True,
                )
            )
        )


class SqlAlchemyGridQualityMeasurementRepository:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session = session
        self.store = GridQualityManifestStore(artifact_root)

    def bind(self, game: UUID, *, write: bool = False) -> None:
        GameStorageRouter().bind(
            self.session, game, intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ
        )
        self.session.connection().execute(text("SET LOCAL lock_timeout='5s'"))
        self.session.connection().execute(text("SET LOCAL statement_timeout='30s'"))

    def key_lock(self, game: UUID, key: str) -> None:
        self.session.execute(
            select(
                func.pg_advisory_xact_lock(int(digest([POLICY, str(game), key])[:16], 16) - 2**63)
            )
        )

    def header(self, game: UUID, measurement: UUID) -> Measurement:
        row = self.session.get(Measurement, (game, measurement))
        if row is None:
            raise ImageReviewNotFoundError("GRID_QUALITY_NOT_FOUND", "Measurement not found.")
        return row

    def member(
        self, game: UUID, measurement: UUID, source: UUID, sample: str, *, lock: bool = False
    ) -> Member:
        statement = select(Member).where(
            Member.game_id == game,
            Member.measurement_id == measurement,
            Member.source_id == source,
            Member.sample_kind == sample,
        )
        if lock:
            statement = statement.with_for_update()
        row = self.session.scalar(statement.execution_options(populate_existing=True))
        if row is None:
            raise ImageReviewNotFoundError(
                "GRID_QUALITY_MEMBER_NOT_FOUND", "Source outside sample."
            )
        return row

    def _replay(self, game: UUID, key: str, command: object) -> Command | None:
        old = self.session.get(Command, (game, UUID(key)))
        if old is not None and old.command_sha256 != digest(command):
            conflict("IDEMPOTENCY_CONFLICT", "The key already represents another command.")
        if old:
            self.store.verify(
                self.header(game, old.measurement_id).manifest_path,
                self.header(game, old.measurement_id).manifest_sha256,
            )
        return old

    def capture(self, game: UUID, command: dict[str, Any], actor: str) -> dict[str, Any]:
        deadline = CaptureDeadline()
        # Serialize the command before the independent RR connection takes its
        # first snapshot. A competing request returns 409 without publishing a
        # second manifest; retry after this request commits reads the receipt.
        # The request transaction owns this lock, so do not reacquire it from
        # the separate snapshot connection (that would wait on ourselves).
        if not self.session.scalar(
            select(
                func.pg_try_advisory_xact_lock(
                    int(digest([POLICY, str(game), command["idempotencyKey"]])[:16], 16) - 2**63
                )
            )
        ):
            conflict("CAPTURE_BUSY", "The capture key is in use. Retry the same command.")
        # Do not alter the request Session's isolation or route. The independent
        # connection uses the same validated runtime identity as the caller.
        caller_role = self.session.execute(text("SELECT current_user")).scalar_one()
        bind = self.session.get_bind()
        engine = bind.engine if isinstance(bind, Connection) else bind
        try:
            with (
                engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
                connection.begin(),
            ):

                def guard_statement(
                    _connection: Any,
                    cursor: Any,
                    _statement: Any,
                    _parameters: Any,
                    _context: Any,
                    _many: Any,
                ) -> None:
                    remaining = deadline.expires - time.monotonic()
                    if remaining <= 0:
                        conflict("CAPTURE_TIMEOUT", "The capture exceeded its 60 second deadline.")
                    milliseconds = min(30_000, max(1, math.floor(remaining * 1000)))
                    cursor.execute(f"SET LOCAL statement_timeout = {milliseconds}")

                event.listen(connection, "before_cursor_execute", guard_statement)
                connection.exec_driver_sql("SET TRANSACTION READ WRITE")
                quoted = connection.dialect.identifier_preparer.quote(caller_role)
                connection.exec_driver_sql(f"SET LOCAL ROLE {quoted}")
                safe = connection.execute(
                    text(
                        "SELECT NOT rolsuper AND NOT rolbypassrls "
                        "FROM pg_roles WHERE rolname=current_user"
                    )
                ).scalar_one()
                if not safe:
                    conflict("RUNTIME_ROLE_REQUIRED", "Capture requires a restricted runtime role.")
                with Session(bind=connection) as snapshot:
                    repository = type(self)(snapshot, self.store.root)
                    repository.bind(game, write=True)
                    deadline.apply(snapshot)
                    old = repository._replay(
                        game,
                        command["idempotencyKey"],
                        {"kind": "capture", "game": str(game), "command": command},
                    )
                    if old:
                        return {
                            "receipt": old.document["receipt"],
                            "current": repository.get(game, old.measurement_id),
                        }
                    game_record = snapshot.get(GameModel, game)
                    if (
                        game_record is None
                        or game_record.code == "7"
                        or not uses_neural_grid(str(game_record.shape_geometry_configuration))
                    ):
                        conflict("GAME_UNSUPPORTED", "A current V3 game is required.")
                    result_id = repository._capture_snapshot(game, command, actor, deadline)
                    deadline.apply(snapshot)
                    snapshot.flush()
                    # The connection commits only after atomic manifest publication.
                # Fresh GET uses a fresh transaction after the capture commit.
            return self._command_result(game, result_id, command["idempotencyKey"])
        except DBAPIError as error:
            if getattr(error.orig, "sqlstate", None) == "57014":
                conflict("CAPTURE_TIMEOUT", "Capture rolled back after a statement deadline.")
            raise

    def _capture_snapshot(
        self, game: UUID, command: dict[str, Any], actor: str, deadline: CaptureDeadline
    ) -> UUID:
        sampler = PopulationSampler(command["seed"], command["sampleSize"])
        hard = set(command["hardSourceIds"])
        hard_seen: set[str] = set()
        after, excluded = None, 0
        prefix = _IMAGE_STATES_CTE.format(
            import_filter=(
                " AND (CAST(:after AS uuid) IS NULL OR s.id>CAST(:after AS uuid)) "
                "ORDER BY s.id LIMIT 500"
            )
        )
        while True:
            deadline.apply(self.session)
            rows = list(
                self.session.execute(
                    text(
                        prefix
                        + """
                SELECT i.id,i.image_state,to_jsonb(s) AS source FROM image_states i
                JOIN source_images s ON s.game_id=:game_id AND s.id=i.id ORDER BY i.id
            """
                    ),
                    {"game_id": game, "after": after},
                ).mappings()
            )
            for row in rows:
                after = row["id"]
                if row["image_state"] == "superseded":
                    excluded += 1
                    continue
                identity = source_fence(row["source"])
                sampler.add(
                    {
                        "sourceId": str(row["id"]),
                        "identity": identity,
                        "imageState": row["image_state"],
                    }
                )
                if str(row["id"]) in hard:
                    hard_seen.add(str(row["id"]))
            if len(rows) < PAGE_SIZE:
                break
        if hard_seen != hard:
            conflict(
                "HARD_SCOPE_CONFLICT", "Hard sample requires current own-game source occurrences."
            )
        measurement = uuid4()
        members = []
        frozen_by_source: dict[str, dict[str, Any]] = {}
        for sample, source_ids in (("random", sampler.selected), ("hard", sorted(hard))):
            for source_id in source_ids:
                deadline.apply(self.session)
                if source_id not in frozen_by_source:
                    frozen_by_source[source_id] = freeze_member(self.session, game, UUID(source_id))
                frozen = copy.deepcopy(frozen_by_source[source_id])
                members.append({"sampleKind": sample, **frozen})
        document = {
            "measurementId": str(measurement),
            "gameId": str(game),
            "policy": POLICY,
            "populationPolicy": POPULATION_POLICY,
            "seed": command["seed"],
            "capturedAt": now(),
            "frozenPopulationCount": sampler.count,
            "excludedSupersededCount": excluded,
            "populationSha256": sampler.population_sha256,
            "randomSampleCount": len(sampler.selected),
            "hardSampleCount": len(hard),
        }
        deadline.apply(self.session)
        path, sha = self.store.publish({**document, "members": members})
        deadline.apply(self.session)
        self.session.add(
            Measurement(
                game_id=game,
                id=measurement,
                manifest_path=path,
                manifest_sha256=sha,
                document=document,
            )
        )
        self.session.flush()
        for frozen in members:
            self.session.add(
                Member(
                    game_id=game,
                    measurement_id=measurement,
                    source_id=UUID(frozen["sourceId"]),
                    sample_kind=frozen["sampleKind"],
                    live_source_image_id=UUID(frozen["sourceId"]),
                    revision=0,
                    frozen=frozen,
                    current={"judgments": empty_judgments(), "unexpectedJudgments": []},
                )
            )
        self.session.flush()
        receipt = {
            "measurementId": str(measurement),
            "manifestSha256": sha,
            "commandSha256": digest(command),
            "kind": "capture",
            "actor": actor,
            "at": now(),
        }
        self.session.add(
            Command(
                game_id=game,
                idempotency_key=UUID(command["idempotencyKey"]),
                measurement_id=measurement,
                kind="capture",
                command_sha256=digest({"kind": "capture", "game": str(game), "command": command}),
                document={"command": command, "receipt": receipt},
            )
        )
        return measurement

    def _command_result(self, game: UUID, measurement: UUID, key: str) -> dict[str, Any]:
        self.bind(game)
        old = self.session.get(Command, (game, UUID(key)))
        assert old is not None
        return {"receipt": old.document["receipt"], "current": self.get(game, measurement)}

    def assess(
        self, game: UUID, measurement: UUID, command: dict[str, Any], actor: str
    ) -> dict[str, Any]:
        self.bind(game, write=True)
        self.key_lock(game, command["idempotencyKey"])
        canonical_command = {"kind": "assess", "measurement": str(measurement), "command": command}
        old = self._replay(game, command["idempotencyKey"], canonical_command)
        if old:
            return {"receipt": old.document["receipt"], "current": self.get(game, measurement)}
        header = self.header(game, measurement)
        self.store.verify(header.manifest_path, header.manifest_sha256)
        member = self.member(
            game, measurement, UUID(command["sourceId"]), command["sampleKind"], lock=True
        )
        if (
            header.manifest_sha256 != command["manifestSha256"]
            or member.revision != command["expectedRevision"]
        ):
            conflict("REVISION_CONFLICT", "The measurement or member revision changed.")
        source = read_source(self.session, game, member.source_id)
        if member.live_source_image_id is None or source is None:
            conflict("SOURCE_UNAVAILABLE", "The measured source has been removed.")
        if source_fence(source) != member.frozen["sourceFence"]:
            conflict("SOURCE_CHANGED", "The source identity differs from the frozen observation.")
        from game_predictor_api.application.image_review_assets import _resolve

        _resolve(
            self.store.root,
            source["relative_path"],
            source["checksum_sha256"],
            asset_kind="grid-quality-source",
        )
        positions = sorted(command["positions"], key=lambda value: value["positionIndex"])
        for verdict, frozen in zip(positions, member.frozen["positions"], strict=True):
            if verdict["geometry"] in ("correct", "incorrect") and (
                not frozen["original"]["available"] or not frozen["original"].get("producer")
            ):
                conflict(
                    "OBSERVATION_UNAVAILABLE",
                    "Missing original geometry cannot receive a geometry verdict.",
                )
            if verdict["sequence"] in ("correct", "incorrect") and frozen["sequenceNumber"] is None:
                conflict(
                    "SEQUENCE_UNKNOWN", "An unresolved sequence cannot receive a guessed verdict."
                )
            if verdict["detection"] in ("correct", "incorrect") and not frozen["original"].get(
                "producer"
            ):
                conflict("DETECTION_UNKNOWN", "No exact original detector result is available.")
        if sorted(value["index"] for value in command["unexpected"]) != list(
            range(len(member.frozen["unexpectedDetections"]))
        ):
            conflict(
                "UNEXPECTED_COVERAGE", "Every unexpected detection requires an explicit verdict."
            )
        member.revision += 1
        member.current = {"judgments": positions, "unexpectedJudgments": command["unexpected"]}
        receipt = {
            "measurementId": str(measurement),
            "sourceId": command["sourceId"],
            "sampleKind": member.sample_kind,
            "revision": member.revision,
            "kind": "assess",
            "commandSha256": digest(canonical_command),
            "actor": actor,
            "at": now(),
        }
        self.session.add(
            Judgment(
                game_id=game,
                measurement_id=measurement,
                source_id=member.source_id,
                sample_kind=member.sample_kind,
                revision=member.revision,
                document={"command": command, "receipt": receipt},
            )
        )
        self.session.add(
            Command(
                game_id=game,
                idempotency_key=UUID(command["idempotencyKey"]),
                measurement_id=measurement,
                kind="assess",
                command_sha256=digest(canonical_command),
                document={"command": command, "receipt": receipt},
            )
        )
        self.session.flush()
        return {"receipt": receipt, "current": self.get(game, measurement)}

    def get(self, game: UUID, measurement: UUID) -> dict[str, Any]:
        self.bind(game)
        header = self.header(game, measurement)
        blocker = None
        try:
            self.store.verify(header.manifest_path, header.manifest_sha256)
        except ImageReviewConflictError as error:
            blocker = error.code
        members = []
        own_symbols = {
            str(value)
            for value in self.session.connection().scalars(
                text("SELECT id FROM public.symbols WHERE game_id=:game AND status='active'"),
                {"game": game},
            )
        }
        for member in self.session.scalars(
            select(Member)
            .where(Member.game_id == game, Member.measurement_id == measurement)
            .order_by(Member.sample_kind, Member.source_id)
        ):
            value = copy.deepcopy(member.frozen)
            source = read_source(self.session, game, member.source_id)
            available = member.live_source_image_id is not None and source is not None
            reason = None if available else "SOURCE_UNAVAILABLE"
            if source and source_fence(source) != member.frozen["sourceFence"]:
                available, reason = False, "SOURCE_CHANGED"
            if available:
                path = (
                    self.store.root / "data" / member.frozen["source"]["relative_path"]
                ).resolve()
                if not path.is_relative_to(self.store.root) or not path.is_file():
                    available, reason = False, "SOURCE_FILE_UNAVAILABLE"
            targets = current_targets(self.session, game, member.source_id) if available else {}
            for position in value["positions"]:
                target = targets.get(position["positionIndex"]) or {}
                board = target.get("board") or {}
                position["current"] = observation(
                    board.get("board_geometry"),
                    None,
                    None if board else "CURRENT_GEOMETRY_UNAVAILABLE",
                )
                position["currentManualSymbolCount"] = symbol_confirmation_count(
                    target, own_symbols
                )
                position["currentSymbolCellCount"] = len(target.get("cells", []))
                position["approvalEligible"] = bool(
                    available
                    and position["approvalEligible"]
                    and unchanged_frozen_target(
                        self.session, game, member.source_id, position["targetFence"], target
                    )
                )
                live_blocker = approval_blocker(self.session, game, target)
                if live_blocker:
                    position["approvalEligible"] = False
                    position["approvalBlocker"] = live_blocker
                elif not position["approvalEligible"]:
                    position["approvalBlocker"] = (
                        position.get("approvalBlocker") or "TARGET_CHANGED"
                    )
            membership = (
                self.session.connection()
                .execute(
                    text(
                        "SELECT public.resolve_own_groups("
                        "CAST(:game AS uuid),NULL::uuid[],NULL::uuid,1,NULL::uuid,"
                        "CAST(:source AS uuid))"
                    ),
                    {"game": game, "source": member.source_id},
                )
                .scalar_one()
            )
            # The resolver returns a bounded document and never exposes private tables.
            groups = membership.get("items", []) if isinstance(membership, dict) else []
            value.update(
                revision=member.revision,
                available=available,
                unavailableReason=reason,
                recordingStatus="declared"
                if any(
                    group.get("declared") is True and group.get("membershipComplete") is True
                    for group in groups
                )
                else "unresolved",
                judgments=member.current.get("judgments", empty_judgments()),
                unexpectedJudgments=member.current.get("unexpectedJudgments", []),
            )
            members.append(value)
        return {
            **header.document,
            "manifestSha256": header.manifest_sha256,
            "manifestAvailable": blocker is None,
            "manifestBlocker": blocker,
            "members": members,
            "report": measurement_report(members),
        }

    def list_measurements(self, game: UUID, cursor: UUID | None, limit: int) -> dict[str, Any]:
        self.bind(game)
        query = select(Measurement).where(Measurement.game_id == game)
        if cursor:
            query = query.where(Measurement.id < cursor)
        rows = list(self.session.scalars(query.order_by(Measurement.id.desc()).limit(limit + 1)))
        page = rows[:limit]
        return {
            "items": [{**row.document, "manifestSha256": row.manifest_sha256} for row in page],
            "nextCursor": str(page[-1].id) if len(rows) > limit else None,
        }
