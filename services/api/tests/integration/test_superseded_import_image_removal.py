"""Isolated PostgreSQL coverage of the dead duplicate-import image removal (TASK-0811).

Each test builds its own world: game A with an older import, the target
(duplicate) import and a newer successor import, plus a second game B. The
target import mixes dead images (every board rejected, every review item
superseded, every sequence number live in the successor import) with live,
mixed, human-touched, uncovered, referenced and protected images. Only the dead
images may disappear; everything else, the other imports and game B stay
byte-for-byte. Executions shared with another import or another game stay in
``public``.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from _virtual_board_fixtures import (
    add_board_render_manifest_for,
    ensure_topology_rules_version,
    virtual_board_columns,
)
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.game_data_v2_manifest_v4 import GAME_TABLES, VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImagePipelineStageResultModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceAlternativeModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolPredictionRevisionModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from game_predictor_api.storage.superseded_import_image_removal_repository import (
    BOARD_NOT_REJECTED,
    COMPLETENESS_NOT_SUPERSEDED,
    HUMAN_BOARD_GEOMETRY_REVISION,
    OWNER_REFERENCE,
    PROTECTED_ROWS,
    REFERENCED_BY,
    REVIEW_ITEM_NOT_SUPERSEDED,
    SEQUENCE_WITHOUT_LIVE_SUCCESSOR,
    RemovalError,
    RemovalInvariantError,
    SupersededImportImageRemovalRepository,
    plan_report,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

SYSTEM_OWNER = "system:pending-sequence-owner"
SLOTS = 3


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "gp_task0811_" + uuid4().hex[:12] + "_test"
    url = make_url(ApiSettings.from_environment().owner_database_url)
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5},
    )
    engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    with maintenance.connect() as connection:
        connection.execute(text("SET statement_timeout='10s'"))
        connection.execute(text(f"CREATE DATABASE {_quote(name)}"))
    try:
        config = Config(str(Path(__file__).resolve().parents[4] / "alembic.ini"))
        config.set_main_option(
            "sqlalchemy.url",
            url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
        )
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with maintenance.connect() as connection:
            connection.execute(text(f"DROP DATABASE {_quote(name)}"))
        maintenance.dispose()


def _provision(session: Session, game_id: UUID) -> None:
    session.execute(
        text(
            "INSERT INTO public.game_storage_locations "
            "(game_id, store_schema, generation, manifest_version, status, revision) "
            "VALUES (:game_id, 'game_data_v2', 2, :version, 'active', 0)"
        ),
        {"game_id": game_id, "version": VERSION},
    )
    for table in GAME_TABLES:
        session.execute(
            text(
                f"CREATE TABLE game_data_v2.{table}_g_{game_id.hex[:20]} "
                f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game_id}')"
            )
        )
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)


@dataclass(slots=True)
class _Builder:
    session: Session
    game_id: UUID
    order: int = 0
    images: dict[str, UUID] = field(default_factory=dict)
    items: dict[str, list[UUID]] = field(default_factory=dict)
    keys: dict[str, str] = field(default_factory=dict)

    def job(self, created_at: datetime) -> JobModel:
        job = JobModel(
            game_id=self.game_id,
            job_type="import",
            status="waiting_for_review",
            input_payload={"import_kind": "image_directory"},
            input_key=uuid4().hex,
            created_at=created_at,
        )
        self.session.add(job)
        self.session.flush()
        return job

    def source(self, job: JobModel, name: str, *, key: str | None = None) -> SourceImageModel:
        """A source image with its import file; ``key`` reuses an existing execution."""

        execution_key = key or uuid4().hex * 2
        checksum = _sha(f"file:{execution_key}")
        if key is None:
            self.session.add(
                ImageFileExecutionModel(
                    file_execution_key=execution_key,
                    source_checksum_sha256=checksum,
                    pipeline_fingerprint="b" * 64,
                    checkpoint_payload={},
                    status="waiting_for_review",
                    review_required=True,
                )
            )
            self.session.flush()
            self.session.add(
                ImagePipelineStageResultModel(
                    file_execution_key=execution_key,
                    stage="board_detection",
                    adapter_version="removal-test-v1",
                    result_payload={"key": execution_key},
                )
            )
            self.session.flush()
        self.session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=execution_key,
                order_index=self.order,
                source_relative_path=name,
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        self.order += 1
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=execution_key,
            relative_path=name,
            checksum_sha256=checksum,
            width=1080,
            height=652,
            raw_width=1080,
            raw_height=652,
            oriented_width=1080,
            oriented_height=652,
            exif_orientation=None,
            coordinate_space="exif-normalized-rgb-pixels-v1",
            normalization_adapter_version="removal-test-v1",
            normalized_pixel_checksum_sha256=_sha(f"normalized:{checksum}"),
            status="waiting_for_review",
        )
        self.session.add(source)
        self.session.flush()
        self.images[name] = source.id
        self.keys[name] = execution_key
        return source

    def revision(
        self,
        source: SourceImageModel,
        start: int,
        *,
        slots: int = SLOTS,
        created_by: str = "system:image-pipeline-v0.10",
    ) -> ImageSourceGeometryRevisionModel:
        record = ImageSourceGeometryRevisionModel(
            game_id=self.game_id,
            source_image_id=source.id,
            topology_rules_version_id=ensure_topology_rules_version(
                self.session, game_id=self.game_id
            ),
            revision=0,
            sequence_range_start=start,
            sequence_range_end=start + slots - 1,
            active_board_slots=list(range(slots)),
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=source.checksum_sha256,
            normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
            oriented_width=1080,
            oriented_height=652,
            normalization_adapter_version="removal-test-v1",
            global_initialization={},
            board_geometries=[
                {
                    "disposition": "automatic",
                    "positionIndex": position,
                    "sequenceNumber": start + position,
                    "finalQuad": [
                        {"x": 10.0 + position, "y": 20.0},
                        {"x": 90.0 + position, "y": 20.0},
                        {"x": 90.0 + position, "y": 60.0},
                        {"x": 10.0 + position, "y": 60.0},
                    ],
                }
                for position in range(slots)
            ],
            engine_kind="structured_opencv_v1",
            engine_version="removal-test-engine-v1",
            geometry_source="auto",
            status="accepted",
            geometry_checksum_sha256=_sha(f"geometry:{source.id}"),
            processing_time_ms=1,
            warnings=[],
            created_by=created_by,
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def board(
        self,
        name: str,
        source: SourceImageModel,
        geometry: ImageSourceGeometryRevisionModel,
        position: int,
        *,
        live: bool,
        owner_item: UUID | None = None,
        geometry_revision: int = 0,
    ) -> tuple[RecognizedBoardModel, ImageReviewItemModel]:
        sequence_number = geometry.sequence_range_start + position
        board = RecognizedBoardModel(
            source_image_id=source.id,
            position_index=position,
            sequence_number_raw=str(sequence_number),
            sequence_number=sequence_number,
            sequence_confidence=1,
            board_geometry={},
            **virtual_board_columns(geometry),
            cells_prediction={},
            completeness_status="complete",
            unavailable_cell_indices=[],
            board_confidence=1,
            pipeline_fingerprint="b" * 64,
            geometry_revision=geometry_revision,
            status="pending_review" if live else "rejected",
        )
        self.session.add(board)
        self.session.flush()
        resolved_value = {
            "action": "superseded",
            "ownerReviewItemId": str(owner_item or uuid4()),
            "reason": "pending_sequence_replaced_by_newer_import",
            "sequenceNumber": sequence_number,
        }
        item = ImageReviewItemModel(
            game_id=self.game_id,
            import_job_id=source.import_job_id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            status="pending" if live else "superseded",
            snapshot={},
            **(
                {}
                if live
                else {
                    "resolved_value": resolved_value,
                    "resolved_by": SYSTEM_OWNER,
                    "resolved_at": datetime.now(UTC),
                    "resolution_revision": 1,
                }
            ),
        )
        self.session.add(item)
        self.session.flush()
        if not live:
            self.session.add(
                ImageReviewResolutionEventModel(
                    review_item_id=item.id,
                    revision=1,
                    idempotency_key=uuid5(NAMESPACE_URL, f"removal-test:{item.id}"),
                    action="superseded",
                    command_sha256=_sha(f"command:{item.id}"),
                    resolved_value=resolved_value,
                    resolved_by=SYSTEM_OWNER,
                )
            )
            self.session.flush()
        self.items.setdefault(name, []).append(item.id)
        return board, item

    def image(
        self,
        job: JobModel,
        name: str,
        start: int,
        *,
        live: tuple[bool, ...] = (False, False, False),
        key: str | None = None,
        slots: int = SLOTS,
        owner_items: list[UUID] | None = None,
    ) -> tuple[SourceImageModel, ImageSourceGeometryRevisionModel]:
        source = self.source(job, name, key=key)
        geometry = self.revision(source, start, slots=slots)
        for position, is_live in enumerate(live[:slots]):
            owner = owner_items[position] if owner_items else None
            self.board(name, source, geometry, position, live=is_live, owner_item=owner)
        return source, geometry


@dataclass(frozen=True, slots=True)
class _World:
    game_id: UUID
    other_game_id: UUID
    old_job: UUID
    target_job: UUID
    successor_job: UUID
    other_job: UUID
    images: dict[str, UUID]
    keys: dict[str, str]
    dead: frozenset[str]


def _build_world(engine: Engine) -> _World:
    now = datetime.now(UTC)
    with Session(engine, expire_on_commit=False) as session, session.begin():
        game = GameModel(code=f"rm-{uuid4().hex[:8]}", name="Removal A", expected_layout_count=1000)
        other = GameModel(
            code=f"rm-{uuid4().hex[:8]}", name="Removal B", expected_layout_count=1000
        )
        session.add_all([game, other])
        session.flush()
        game_id, other_id = game.id, other.id
    with Session(engine, expire_on_commit=False) as session, session.begin():
        _provision(session, game_id)
        build = _Builder(session, game_id)
        old = build.job(datetime(2026, 9, 1, tzinfo=UTC))
        target = build.job(datetime(2026, 9, 2, tzinfo=UTC))
        successor = build.job(datetime(2026, 9, 3, tzinfo=UTC))

        # Successor import: live items for every covered range.
        for start in (100, 110, 140, 160, 170, 180, 190):
            build.image(successor, f"succ_{start}.jpg", start, live=(True, True, True))
        # Only 150..151 are covered: 152 has no live successor.
        build.image(successor, "succ_150.jpg", 150, live=(True, True), slots=2)

        # Target (duplicate) import. dead_a gets its third board below.
        dead_a, dead_a_rev = build.image(target, "dead_a.jpg", 100, live=(False, False))
        build.image(target, "dead_b.jpg", 110)
        build.image(target, "dead_c.jpg", 170)
        build.image(target, "live.jpg", 120, live=(True, True, True))
        build.image(target, "mixed.jpg", 130, live=(False, False, True))
        human, human_rev = build.image(target, "human.jpg", 140, live=())
        build.image(target, "orphan.jpg", 150)
        build.image(target, "owner_ref.jpg", 160)
        fk_ref, _ = build.image(target, "fk_ref.jpg", 180)
        protected, _ = build.image(target, "protected.jpg", 190)

        # dead_a carries the automatic rows that go with it: a render manifest,
        # a system board geometry revision, a resolved deferred row and a
        # prediction revision.
        first = session.get(RecognizedBoardModel, _board_of(session, build.items["dead_a.jpg"][0]))
        assert first is not None
        add_board_render_manifest_for(session, game_id=game_id, board=first)
        session.add(
            ImageBoardGeometryPendingModel(
                game_id=game_id,
                import_job_id=target.id,
                source_image_id=dead_a.id,
                sequence_number=101,
                position_index=1,
                source_checksum_sha256=dead_a.checksum_sha256,
                source_relative_path=dead_a.relative_path,
                status="resolved",
                reason_code="incomplete_lattice",
                processing_manifest_checksum_sha256=_sha(f"manifest:{dead_a.id}"),
                processing_manifest_relative_path="manifests/removal-test.json",
                pipeline_fingerprint_sha256="b" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                resolved_geometry_revision=1,
                resolved_at=now,
            )
        )
        session.add(
            ImageSymbolPredictionRevisionModel(
                game_id=game_id,
                review_item_id=build.items["dead_a.jpg"][0],
                recognized_board_id=first.id,
                source_job_id=target.id,
                model_iteration_id=None,
                model_version="removal-test-model",
                model_checksum_sha256=_sha("model"),
                crop_manifest_checksum_sha256=_sha("crops"),
                predictions=[],
            )
        )
        session.flush()
        # Position 2 of dead_a has a system geometry revision (revision 1).
        system_board, system_item = build.board(
            "dead_a.jpg", dead_a, dead_a_rev, 2, live=False, geometry_revision=1
        )
        add_board_render_manifest_for(
            session,
            game_id=game_id,
            board=system_board,
            review_item_id=system_item.id,
            corrected_by="system:legacy-board-conversion-v1",
        )

        # human: boards with a geometry revision written by an operator.
        for position in range(SLOTS):
            board, item = build.board(
                "human.jpg", human, human_rev, position, live=False, geometry_revision=1
            )
            add_board_render_manifest_for(
                session,
                game_id=game_id,
                board=board,
                review_item_id=item.id,
                corrected_by="reviewer-operator",
            )

        # owner_ref: an item of the older import names one of its items as owner.
        older, older_rev = build.image(old, "older.jpg", 160, live=())
        build.board(
            "older.jpg",
            older,
            older_rev,
            0,
            live=False,
            owner_item=build.items["owner_ref.jpg"][0],
        )
        # fk_ref: the rollout state points to the image (FK outside the delete set).
        session.execute(
            text(
                "INSERT INTO game_data_v2.image_geometry_rollout_states "
                "(game_id, revision, backfill_status, last_source_image_id, updated_by) "
                "VALUES (:game_id, 0, 'processing', :image_id, 'removal-test')"
            ),
            {"game_id": game_id, "image_id": fk_ref.id},
        )
        # protected: a sequence alternative of the target import and its file.
        session.add(
            ImageSequenceAlternativeModel(
                game_id=game_id,
                sequence_number=190,
                import_job_id=target.id,
                source_checksum_sha256=protected.checksum_sha256,
                source_relative_path=protected.relative_path,
                reason="canonical_sequence_already_resolved",
            )
        )
        session.flush()
        # dead_b's execution is shared with another import of the same game.
        build.source(successor, "succ_shared_with_dead_b.jpg", key=build.keys["dead_b.jpg"])
        images, keys = dict(build.images), dict(build.keys)
        ids = (old.id, target.id, successor.id)

    with Session(engine, expire_on_commit=False) as session, session.begin():
        _provision(session, other_id)
        other_build = _Builder(session, other_id)
        other_job = other_build.job(datetime(2026, 9, 4, tzinfo=UTC))
        other_build.image(other_job, "b_live.jpg", 100, live=(True, True, True))
        # dead_a's execution is shared with game B.
        other_build.source(other_job, "b_shared_with_dead_a.jpg", key=keys["dead_a.jpg"])
        other_job_id = other_job.id

    return _World(
        game_id=game_id,
        other_game_id=other_id,
        old_job=ids[0],
        target_job=ids[1],
        successor_job=ids[2],
        other_job=other_job_id,
        images=images,
        keys=keys,
        dead=frozenset({"dead_a.jpg", "dead_b.jpg", "dead_c.jpg"}),
    )


def _board_of(session: Session, item_id: UUID) -> UUID:
    item = session.get(ImageReviewItemModel, item_id)
    assert item is not None
    return item.recognized_board_id


_COUNTED_TABLES = (
    "source_images",
    "image_source_geometry_revisions",
    "recognized_boards",
    "image_review_items",
    "image_review_resolution_events",
    "image_review_queue_items",
    "board_render_manifests",
    "image_board_geometry_revisions",
    "image_board_geometry_pending",
    "image_symbol_prediction_revisions",
    "image_import_job_files",
    "image_sequence_alternatives",
    "image_geometry_rollout_states",
)


def _snapshot(engine: Engine, world: _World) -> dict[str, Any]:
    """Row counts per game, per import and of the public executions."""

    result: dict[str, Any] = {}
    with engine.connect() as connection:
        for game in (world.game_id, world.other_game_id):
            for table in _COUNTED_TABLES:
                result[f"{game}:{table}"] = connection.execute(
                    text(f"SELECT count(*) FROM game_data_v2.{table} WHERE game_id = :g"),
                    {"g": game},
                ).scalar_one()
            result[f"{game}:per_import"] = sorted(
                (str(job), int(count))
                for job, count in connection.execute(
                    text(
                        "SELECT s.import_job_id, count(*) FROM game_data_v2.recognized_boards b "
                        "JOIN game_data_v2.source_images s ON s.game_id = b.game_id "
                        "AND s.id = b.source_image_id WHERE b.game_id = :g GROUP BY 1"
                    ),
                    {"g": game},
                ).all()
            )
            result[f"{game}:queue"] = sorted(
                tuple(str(value) for value in row)
                for row in connection.execute(
                    text(
                        "SELECT import_job_id, total_count, pending_count, superseded_count "
                        "FROM game_data_v2.image_review_queue_states WHERE game_id = :g"
                    ),
                    {"g": game},
                ).all()
            )
        for table in (
            "image_file_executions",
            "image_pipeline_stage_results",
            "image_pipeline_terminal_manifests",
        ):
            result[f"public:{table}"] = sorted(
                str(value)
                for (value,) in connection.execute(
                    text(f"SELECT file_execution_key FROM public.{table}")
                ).all()
            )
        result["jobs"] = sorted(
            (str(job), str(status))
            for job, status in connection.execute(text("SELECT id, status FROM public.jobs")).all()
        )
    return result


def _image_ids(engine: Engine, world: _World) -> set[str]:
    with engine.connect() as connection:
        return {
            str(value)
            for (value,) in connection.execute(
                text("SELECT id FROM game_data_v2.source_images WHERE game_id = :g"),
                {"g": world.game_id},
            ).all()
        }


@pytest.fixture
def world(database: Engine) -> _World:
    return _build_world(database)


def test_preview_qualifies_only_dead_images_and_writes_nothing(
    database: Engine, world: _World
) -> None:
    before = _snapshot(database, world)
    plan = SupersededImportImageRemovalRepository(database).preview(world.game_id, world.target_job)
    assert _snapshot(database, world) == before

    by_name = {
        name: decision
        for decision in plan.images
        for name, image_id in world.images.items()
        if image_id == decision.source_image_id
    }
    assert {name for name, decision in by_name.items() if decision.qualifies} == world.dead
    assert {str(value) for value in plan.image_ids} == {
        str(world.images[name]) for name in world.dead
    }
    reasons = {name: set(decision.reasons) for name, decision in by_name.items()}
    assert {BOARD_NOT_REJECTED, REVIEW_ITEM_NOT_SUPERSEDED} <= reasons["live.jpg"]
    assert {BOARD_NOT_REJECTED, REVIEW_ITEM_NOT_SUPERSEDED} <= reasons["mixed.jpg"]
    assert reasons["human.jpg"] == {HUMAN_BOARD_GEOMETRY_REVISION}
    assert {SEQUENCE_WITHOUT_LIVE_SUCCESSOR, COMPLETENESS_NOT_SUPERSEDED} <= reasons["orphan.jpg"]
    assert reasons["owner_ref.jpg"] == {f"{OWNER_REFERENCE}:image_review_items"} | {
        f"{OWNER_REFERENCE}:image_review_resolution_events"
    }
    assert len(reasons["fk_ref.jpg"]) == 1
    (fk_reason,) = reasons["fk_ref.jpg"]
    assert fk_reason.startswith(f"{REFERENCED_BY}:game_data_v2.image_geometry_rollout_states")
    assert reasons["protected.jpg"] == {f"{PROTECTED_ROWS}:image_sequence_alternatives"}

    counts = plan.row_counts
    assert counts["game_data_v2.source_images"] == 3
    assert counts["game_data_v2.recognized_boards"] == 9
    assert counts["game_data_v2.image_review_items"] == 9
    assert counts["game_data_v2.image_review_queue_items"] == 9
    assert counts["game_data_v2.image_review_resolution_events"] == 9
    assert counts["game_data_v2.image_source_geometry_revisions"] == 3
    assert counts["game_data_v2.board_render_manifests"] == 2
    assert counts["game_data_v2.image_board_geometry_revisions"] == 1
    assert counts["game_data_v2.image_board_geometry_pending"] == 1
    assert counts["game_data_v2.image_symbol_prediction_revisions"] == 1
    assert counts["game_data_v2.image_import_job_files"] == 3
    # dead_a's execution is used by game B, dead_b's by the successor import.
    assert plan.execution_keys == (world.keys["dead_c.jpg"],)
    assert set(plan.retained_execution_keys) == {
        world.keys["dead_a.jpg"],
        world.keys["dead_b.jpg"],
    }
    assert counts["public.image_file_executions"] == 1
    assert counts["public.image_pipeline_stage_results"] == 1
    assert plan.blockers == ()
    # Children before parents, read from the catalog.
    order = plan.delete_order
    assert order.index("game_data_v2.image_review_items") < order.index(
        "game_data_v2.recognized_boards"
    )
    assert order.index("game_data_v2.recognized_boards") < order.index(
        "game_data_v2.image_source_geometry_revisions"
    )
    assert order.index("game_data_v2.source_images") < order.index("public.image_file_executions")
    assert any("image_symbol_review_cells" in key for key in plan.foreign_keys)
    report = plan_report(plan)
    assert report["images"]["qualifying"] == 3
    assert report["images"]["kept"] == 7
    json.dumps(report)


def test_execute_removes_only_dead_images_and_backs_up_every_row(
    database: Engine, world: _World, tmp_path: Path
) -> None:
    repository = SupersededImportImageRemovalRepository(database)
    plan = repository.preview(world.game_id, world.target_job)
    before = _snapshot(database, world)
    ids_before = _image_ids(database, world)

    execution = repository.execute(
        world.game_id,
        world.target_job,
        confirm_plan_sha256=plan.plan_sha256,
        backup_root=tmp_path,
    )

    assert execution.committed
    assert execution.deleted_counts == dict(plan.row_counts)
    after = _snapshot(database, world)
    dead_ids = {str(world.images[name]) for name in world.dead}
    assert _image_ids(database, world) == ids_before - dead_ids
    game = world.game_id
    for table, removed in (
        ("source_images", 3),
        ("recognized_boards", 9),
        ("image_review_items", 9),
        ("image_review_queue_items", 9),
        ("image_review_resolution_events", 9),
        ("board_render_manifests", 2),
        ("image_board_geometry_revisions", 1),
        ("image_board_geometry_pending", 1),
        ("image_symbol_prediction_revisions", 1),
        ("image_import_job_files", 3),
        ("image_source_geometry_revisions", 3),
    ):
        assert before[f"{game}:{table}"] - after[f"{game}:{table}"] == removed, table
    for table in ("image_sequence_alternatives", "image_geometry_rollout_states"):
        assert before[f"{game}:{table}"] == after[f"{game}:{table}"]
    # Other imports and the second game are unchanged.
    per_import_before = dict(before[f"{game}:per_import"])
    per_import_after = dict(after[f"{game}:per_import"])
    for job in (world.old_job, world.successor_job):
        assert per_import_after[str(job)] == per_import_before[str(job)]
    assert per_import_before[str(world.target_job)] - per_import_after[str(world.target_job)] == 9
    for key, value in before.items():
        if key.startswith(str(world.other_game_id)) or key == "jobs":
            assert after[key] == value, key
    # Only the unshared execution left public.
    removed_keys = set(before["public:image_file_executions"]) - set(
        after["public:image_file_executions"]
    )
    assert removed_keys == {world.keys["dead_c.jpg"]}
    assert world.keys["dead_c.jpg"] not in after["public:image_pipeline_stage_results"]
    assert world.keys["dead_a.jpg"] in after["public:image_pipeline_stage_results"]
    # Queue state of the target import lost exactly the superseded items.
    queue_before = {row[0]: row for row in before[f"{game}:queue"]}
    queue_after = {row[0]: row for row in after[f"{game}:queue"]}
    target = str(world.target_job)
    assert int(queue_before[target][1]) - int(queue_after[target][1]) == 9
    assert queue_before[target][2] == queue_after[target][2]
    assert int(queue_before[target][3]) - int(queue_after[target][3]) == 9

    # Backup: every deleted row in JSON Lines with a matching manifest.
    assert execution.backup_directory is not None
    manifest = json.loads((execution.backup_directory / "manifest.json").read_text("utf-8"))
    assert manifest["planSha256"] == plan.plan_sha256
    by_table = {entry["table"]: entry for entry in manifest["tables"]}
    for table, count in plan.row_counts.items():
        entry = by_table[table]
        assert entry["rows"] == count
        data = (execution.backup_directory / entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
        lines = [json.loads(line) for line in data.decode("utf-8").splitlines()]
        assert len(lines) == count
    images = [
        json.loads(line)
        for line in (execution.backup_directory / "game_data_v2.source_images.jsonl")
        .read_text("utf-8")
        .splitlines()
    ]
    assert {row["id"] for row in images} == dead_ids
    queue_state = by_table["game_data_v2.image_review_queue_states"]
    assert queue_state["rows"] == 1


def test_a_second_run_deletes_nothing(database: Engine, world: _World, tmp_path: Path) -> None:
    repository = SupersededImportImageRemovalRepository(database)
    first = repository.preview(world.game_id, world.target_job)
    repository.execute(
        world.game_id,
        world.target_job,
        confirm_plan_sha256=first.plan_sha256,
        backup_root=tmp_path,
    )
    before = _snapshot(database, world)

    second = repository.preview(world.game_id, world.target_job)
    assert second.image_ids == ()
    assert all(count == 0 for count in second.row_counts.values())
    assert len(second.kept) == 7
    execution = repository.execute(
        world.game_id,
        world.target_job,
        confirm_plan_sha256=second.plan_sha256,
        backup_root=tmp_path / "second",
    )
    assert not execution.committed
    assert execution.backup_directory is None
    assert _snapshot(database, world) == before


def _script() -> Any:
    path = Path(__file__).resolve().parents[4] / "scripts" / "remove_superseded_import_images.py"
    spec = importlib.util.spec_from_file_location("remove_superseded_import_images", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_script_preview_report_drives_the_confirmed_execute(
    database: Engine, world: _World, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = database.url.render_as_string(hide_password=False)
    monkeypatch.setenv("GAME_PREDICTOR_DATABASE_URL", url)
    monkeypatch.delenv("GAME_PREDICTOR_OWNER_DATABASE_URL", raising=False)
    monkeypatch.setenv("GAME_PREDICTOR_ARTIFACT_ROOT", str(tmp_path))
    script = _script()
    arguments = ["--game-id", str(world.game_id), "--import-job-id", str(world.target_job)]
    report_dir = tmp_path / "data" / "exports" / "remove-superseded-import-images"
    report_dir = report_dir / str(world.game_id)

    before = _snapshot(database, world)
    assert script.main(arguments) == 0
    (preview_path,) = report_dir.glob("*-preview.json")
    preview = json.loads(preview_path.read_text("utf-8"))
    assert preview["plan"]["images"]["qualifying"] == 3
    assert len(preview["plan"]["keptImages"]) == 7
    assert _snapshot(database, world) == before

    with pytest.raises(SystemExit):
        script.main([*arguments, "--execute"])
    assert script.main([*arguments, "--execute", "--confirm-plan-sha256", "0" * 64]) == 2
    assert _snapshot(database, world) == before

    digest = preview["plan"]["planSha256"]
    assert script.main([*arguments, "--execute", "--confirm-plan-sha256", digest]) == 0
    (report_path,) = report_dir.glob("*/report.json")
    report = json.loads(report_path.read_text("utf-8"))
    assert report["committed"] is True
    assert report["deletedCounts"]["game_data_v2.source_images"] == 3
    assert (report_path.parent / "manifest.json").is_file()
    assert _image_ids(database, world).isdisjoint({str(world.images[name]) for name in world.dead})


def test_an_invariant_violation_rolls_back_every_delete(
    database: Engine, world: _World, tmp_path: Path
) -> None:
    repository = SupersededImportImageRemovalRepository(database)
    plan = repository.preview(world.game_id, world.target_job)
    before = _snapshot(database, world)

    def break_a_live_item(session: Session) -> None:
        session.execute(
            text(
                "UPDATE game_data_v2.image_review_items SET status = 'superseded', "
                "resolved_by = 'removal-test', resolved_at = now(), "
                'resolved_value = \'{"action": "superseded"}\'::jsonb, '
                "resolution_revision = resolution_revision + 1 "
                "WHERE game_id = :g AND import_job_id = :j AND status = 'pending' "
                "AND id = (SELECT min(id::text)::uuid FROM game_data_v2.image_review_items "
                "WHERE game_id = :g AND import_job_id = :j AND status = 'pending')"
            ),
            {"g": world.game_id, "j": world.successor_job},
        )

    with pytest.raises(RemovalInvariantError) as raised:
        repository.execute(
            world.game_id,
            world.target_job,
            confirm_plan_sha256=plan.plan_sha256,
            backup_root=tmp_path,
            before_invariants=break_a_live_item,
        )
    assert any(item.startswith("live_items") for item in raised.value.violations)
    assert _snapshot(database, world) == before
    # The lock was released: a fresh run still works and removes the dead images.
    execution = repository.execute(
        world.game_id,
        world.target_job,
        confirm_plan_sha256=plan.plan_sha256,
        backup_root=tmp_path / "retry",
    )
    assert execution.committed


def test_execute_refuses_a_plan_that_changed_since_the_preview(
    database: Engine, world: _World, tmp_path: Path
) -> None:
    repository = SupersededImportImageRemovalRepository(database)
    before = _snapshot(database, world)
    with pytest.raises(RemovalError) as raised:
        repository.execute(
            world.game_id,
            world.target_job,
            confirm_plan_sha256="0" * 64,
            backup_root=tmp_path,
        )
    assert raised.value.code == "REMOVAL_PLAN_CHANGED"
    assert _snapshot(database, world) == before
    assert not any(tmp_path.iterdir())
