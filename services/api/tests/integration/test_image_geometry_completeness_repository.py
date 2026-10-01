"""Isolated PostgreSQL coverage of the D-479 geometry completeness report (TASK-0806).

Builds a game routed to ``game_data_v2`` with one source image per state and
the edge cases the definition names (older revisions, closed pending rows,
boards outside the current slots) directly through the ORM, then reads it back
through ``SqlAlchemyImageGeometryCompletenessRepository``. The repository is
read-only: every call below also runs in a ``READ ONLY`` transaction.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from _virtual_board_fixtures import ensure_topology_rules_version, virtual_board_columns
from alembic import command
from alembic.config import Config
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.image_geometry_completeness import (
    GeometryImageCursor,
    GeometryImageState,
    GeometryPositionState,
    LowQualityThresholds,
    classify_image,
)
from game_predictor_api.domain.image_reviews import (
    ImageReviewConflictError,
    ImageReviewNotFoundError,
)
from game_predictor_api.storage import image_geometry_completeness_repository as repository_module
from game_predictor_api.storage.game_data_v2_manifest_v4 import VERSION
from game_predictor_api.storage.game_storage_routing import (
    GameStorageIntent,
    GameStorageRouter,
)
from game_predictor_api.storage.image_geometry_completeness_repository import (
    SqlAlchemyImageGeometryCompletenessRepository,
)
from game_predictor_api.storage.models import (
    GameModel,
    ImageBoardGeometryPendingModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Set GAME_PREDICTOR_RUN_POSTGRES_TESTS=1 to run isolated PostgreSQL tests.",
)

COMPLETE = "complete"
PARTIAL = "pending_partial"
_V2_PARTITIONED_TABLES = (
    "source_images",
    "image_source_geometry_revisions",
    "recognized_boards",
    "image_review_items",
    "image_sequence_canonical",
    "image_import_job_files",
    "image_review_queue_items",
    "image_review_queue_states",
    "image_board_geometry_pending",
    "image_symbol_review_cells",
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


@pytest.fixture(scope="module")
def database() -> Iterator[Engine]:
    name = "game_predictor_task0806_" + uuid4().hex[:12]
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


def _provision_v2_storage_location(session: Session, *, game_id: UUID) -> None:
    session.execute(
        text(
            "INSERT INTO public.game_storage_locations "
            "(game_id, store_schema, generation, manifest_version, status, revision) "
            "VALUES (:game_id, 'game_data_v2', 2, :version, 'active', 0)"
        ),
        {"game_id": game_id, "version": VERSION},
    )
    for table in _V2_PARTITIONED_TABLES:
        session.execute(
            text(
                f"CREATE TABLE game_data_v2.{table}_g_{game_id.hex} "
                f"PARTITION OF game_data_v2.{table} FOR VALUES IN ('{game_id}')"
            )
        )
    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)


def _import_job(session: Session, *, game_id: UUID) -> JobModel:
    job = JobModel(
        game_id=game_id,
        job_type="import",
        status="completed",
        input_payload={"import_kind": "image_directory"},
        input_key=uuid4().hex,
    )
    session.add(job)
    session.flush()
    return job


@dataclass(slots=True)
class _Builder:
    """Creates the rows of one game inside the caller's transaction."""

    session: Session
    game_id: UUID
    order: int = 0

    def source(
        self, job: JobModel, relative_path: str, *, status: str = "waiting_for_review"
    ) -> SourceImageModel:
        checksum = uuid4().hex * 2
        self.session.add(
            ImageFileExecutionModel(
                file_execution_key=checksum,
                source_checksum_sha256=checksum,
                pipeline_fingerprint="b" * 64,
                checkpoint_payload={},
                status="waiting_for_review",
                review_required=True,
            )
        )
        self.session.flush()
        self.session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=checksum,
                order_index=self.order,
                source_relative_path=relative_path,
                workflow_checkpoint_payload={},
                workflow_status="waiting_for_review",
                review_required=True,
            )
        )
        self.order += 1
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=checksum,
            relative_path=relative_path,
            checksum_sha256=checksum,
            width=1080,
            height=652,
            raw_width=1080,
            raw_height=652,
            oriented_width=1080,
            oriented_height=652,
            exif_orientation=None,
            coordinate_space="exif-normalized-rgb-pixels-v1",
            normalization_adapter_version="completeness-test-v1",
            normalized_pixel_checksum_sha256=_sha(f"normalized:{checksum}"),
            status=status,
        )
        self.session.add(source)
        self.session.flush()
        return source

    def revision(
        self,
        source: SourceImageModel,
        *,
        revision: int,
        range_start: int,
        slots: int = 9,
        status: str = "accepted",
        geometry_source: str = "auto",
    ) -> ImageSourceGeometryRevisionModel:
        """A source geometry revision whose quads encode ``revision`` and position."""

        record = ImageSourceGeometryRevisionModel(
            game_id=self.game_id,
            source_image_id=source.id,
            topology_rules_version_id=ensure_topology_rules_version(
                self.session, game_id=self.game_id
            ),
            revision=revision,
            sequence_range_start=range_start,
            sequence_range_end=range_start + slots - 1,
            active_board_slots=list(range(slots)),
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256=source.checksum_sha256,
            normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
            oriented_width=1080,
            oriented_height=652,
            normalization_adapter_version="completeness-test-v1",
            global_initialization={},
            board_geometries=[
                {
                    "disposition": "automatic",
                    "positionIndex": position,
                    "sequenceNumber": range_start + position,
                    "finalQuad": _quad(revision, position),
                    "symbolGridQuad": _quad(revision, position),
                }
                for position in range(slots)
            ],
            engine_kind="manual_v1" if geometry_source == "manual" else "structured_opencv_v1",
            engine_version="completeness-test-engine-v1",
            geometry_source=geometry_source,
            status=status,
            geometry_checksum_sha256=_sha(f"geometry:{source.id}:{revision}"),
            processing_time_ms=1,
            warnings=[],
            created_by="completeness-test",
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        self.session.flush()
        return record

    def board(
        self,
        source: SourceImageModel,
        geometry: ImageSourceGeometryRevisionModel,
        position: int,
        *,
        completeness: str = COMPLETE,
        approved: bool = False,
        geometry_revision: int = 0,
        approved_revision: int | None = None,
        item_status: str | None = "pending",
    ) -> RecognizedBoardModel:
        sequence_number = geometry.sequence_range_start + position
        approval = (
            {
                "approved_geometry_revision": (
                    geometry_revision if approved_revision is None else approved_revision
                ),
                "geometry_approved_at": datetime.now(UTC),
                "geometry_approved_by": "completeness-test",
            }
            if approved or approved_revision is not None
            else {}
        )
        board = RecognizedBoardModel(
            source_image_id=source.id,
            position_index=position,
            sequence_number_raw=str(sequence_number),
            sequence_number=sequence_number,
            sequence_confidence=1,
            board_geometry={},
            **virtual_board_columns(geometry),
            cells_prediction={},
            completeness_status=completeness,
            unavailable_cell_indices=[0] if completeness == PARTIAL else [],
            board_confidence=1,
            pipeline_fingerprint="b" * 64,
            geometry_revision=geometry_revision,
            status="pending_review",
            **approval,
        )
        self.session.add(board)
        self.session.flush()
        if item_status is not None:
            self.item(source, board, sequence_number, item_status)
        return board

    def item(
        self,
        source: SourceImageModel,
        board: RecognizedBoardModel,
        sequence_number: int,
        status: str,
    ) -> ImageReviewItemModel:
        item = ImageReviewItemModel(
            game_id=self.game_id,
            import_job_id=source.import_job_id,
            recognized_board_id=board.id,
            sequence_number=sequence_number,
            status=status,
            snapshot={},
            **(
                {}
                if status == "pending"
                else {
                    "resolved_value": {"action": status},
                    "resolved_by": "fixture",
                    "resolved_at": datetime.now(UTC),
                    "resolution_revision": 1,
                }
            ),
        )
        self.session.add(item)
        self.session.flush()
        return item

    def pending(
        self,
        source: SourceImageModel,
        position: int,
        sequence_number: int,
        *,
        status: str,
        reason: str = "incomplete_lattice",
    ) -> None:
        extra: dict[str, object] = {}
        if status == "resolved":
            extra = {"resolved_geometry_revision": 1, "resolved_at": datetime.now(UTC)}
        elif status == "superseded":
            extra = {"superseded_at": datetime.now(UTC)}
        self.session.add(
            ImageBoardGeometryPendingModel(
                game_id=self.game_id,
                import_job_id=source.import_job_id,
                source_image_id=source.id,
                sequence_number=sequence_number,
                position_index=position,
                source_checksum_sha256=source.checksum_sha256,
                source_relative_path=source.relative_path,
                status=status,
                reason_code=reason,
                processing_manifest_checksum_sha256=_sha(
                    f"manifest:{source.id}:{position}:{status}"
                ),
                processing_manifest_relative_path="manifests/completeness-test.json",
                pipeline_fingerprint_sha256="b" * 64,
                expected_geometry_revision=0,
                expected_review_resolution_revision=0,
                **extra,
            )
        )
        self.session.flush()

    def cells(
        self,
        board: RecognizedBoardModel,
        geometry: ImageSourceGeometryRevisionModel,
        job: JobModel,
        *,
        specs: list[tuple[float, str, bool]],
    ) -> None:
        """Symbol cells of ``board``: ``(confidence, review_state, source_available)``."""

        item = (
            self.session.query(ImageReviewItemModel).filter_by(recognized_board_id=board.id).one()
        )
        assert board.sequence_number is not None
        for cell_index, (confidence, review_state, available) in enumerate(specs):
            label = f"{board.id}:{cell_index}"
            self.session.add(
                ImageSymbolReviewCellModel(
                    game_id=self.game_id,
                    import_job_id=job.id,
                    review_item_id=item.id,
                    recognized_board_id=board.id,
                    sequence_number=board.sequence_number,
                    cell_index=cell_index,
                    row_index=cell_index // 5,
                    column_index=cell_index % 5,
                    asset_mode="virtual_source",
                    source_geometry_revision_id=geometry.id,
                    logical_cell_key=_sha(f"logical:{label}"),
                    render_spec_checksum_sha256=_sha(f"spec:{label}"),
                    rendered_pixel_checksum_sha256=_sha(f"pixels:{label}"),
                    extractor_version="completeness-test-renderer-v1",
                    crop_sample_id=_sha(f"sample:{label}"),
                    crop_checksum_sha256=_sha(f"crop:{label}"),
                    geometry_revision=0,
                    cropper_version="completeness-test-cropper-v1",
                    prediction_confidence=confidence,
                    review_state=review_state,
                    assigned_symbol_id=None,
                    quality_issue="unreadable" if review_state == "approved" else None,
                    source_available=available,
                    source_visibility="full" if available else "partial",
                    assignment_source="human" if review_state == "approved" else "model",
                    last_reviewed_by="completeness-test",
                )
            )
        self.session.flush()


def _quad(revision: int, position: int) -> list[dict[str, float]]:
    base = revision * 1000 + position * 10
    return [
        {"x": base + 1.0, "y": 20.0},
        {"x": base + 9.0, "y": 20.0},
        {"x": base + 9.0, "y": 60.0},
        {"x": base + 1.0, "y": 60.0},
    ]


@dataclass(slots=True)
class _World:
    game_id: UUID
    other_game_id: UUID
    job1: UUID
    job2: UUID
    other_job: UUID
    images: dict[str, UUID]
    boards: dict[str, UUID]


@pytest.fixture(scope="module")
def world(database: Engine) -> _World:
    images: dict[str, UUID] = {}
    boards: dict[str, UUID] = {}
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="geo-a", name="Geometry A", expected_layout_count=100000)
        other = GameModel(code="geo-b", name="Geometry B", expected_layout_count=100000)
        session.add_all([game, other])
        session.flush()

        # One storage binding per transaction: game A is built here, game B afterwards.
        _provision_v2_storage_location(session, game_id=game.id)
        build = _Builder(session, game.id)
        job1 = _import_job(session, game_id=game.id)
        job2 = _import_job(session, game_id=game.id)

        def add(
            name: str, job: JobModel, *, status: str = "waiting_for_review"
        ) -> SourceImageModel:
            source = build.source(job, name, status=status)
            images[name] = source.id
            return source

        # complete: 9 boards, mixed evidence (accepted source revision / human approval).
        a = add("a_complete_9.jpg", job1)
        a_rev = build.revision(a, revision=0, range_start=1000)
        for position in range(9):
            boards[f"a{position}"] = build.board(
                a,
                a_rev,
                position,
                approved=position in (4, 5),
            ).id

        # incomplete_missing: one deferred (open pending row) and one plain missing.
        b = add("b_missing.jpg", job1)
        b_rev = build.revision(b, revision=0, range_start=2000)
        for position in range(7):
            boards[f"b{position}"] = build.board(b, b_rev, position).id
        build.pending(b, 7, 2007, status="pending", reason="residual_too_high")

        # incomplete_partial: 8 ok + 1 pending_partial.
        c = add("c_partial.jpg", job1)
        c_rev = build.revision(c, revision=0, range_start=3000)
        for position in range(8):
            build.board(c, c_rev, position)
        build.board(c, c_rev, 8, completeness=PARTIAL)

        # incomplete_uncertain: needs_review source revision; 8 human-approved, one with a
        # stale approval (approved revision 0 but geometry revision 1).
        d = add("d_uncertain.jpg", job1)
        d_rev = build.revision(d, revision=0, range_start=4000, status="needs_review")
        for position in range(8):
            build.board(d, d_rev, position, approved=True)
        build.board(d, d_rev, 8, geometry_revision=1, approved_revision=0)

        # no source geometry at all; still processing.
        add("e_no_geometry.jpg", job1, status="processing")

        # a four-board range: 4 ok boards are complete.
        f = add("f_four_boards_complete.jpg", job1)
        f_rev = build.revision(f, revision=0, range_start=5000, slots=4)
        for position in range(4):
            build.board(f, f_rev, position)

        # newest revision is manual+accepted but every board still points to the older
        # needs_review revision without approval: uncertain, grid shown from the revision
        # the board was cut from. Position 0's item is superseded (preview prefers pending).
        g = add("g_stale_pointer.jpg", job1)
        g_old = build.revision(g, revision=0, range_start=6000, status="needs_review")
        build.revision(g, revision=1, range_start=6000, geometry_source="manual")
        for position in range(9):
            build.board(
                g, g_old, position, item_status="superseded" if position == 0 else "pending"
            )

        # closed pending rows (resolved / superseded) do not make a position deferred.
        h = add("h_closed_pending.jpg", job1)
        h_rev = build.revision(h, revision=0, range_start=7000)
        for position in range(7):
            build.board(h, h_rev, position)
        build.pending(h, 7, 7007, status="resolved")
        build.pending(h, 8, 7008, status="superseded")

        # the older revision had 9 slots, the newest has 4: boards outside the newest
        # slots (a stray partial one at position 4) do not count.
        i = add("i_trimmed_slots.jpg", job1)
        i_old = build.revision(i, revision=0, range_start=8000)
        i_new = build.revision(i, revision=1, range_start=8000, slots=4, geometry_source="manual")
        for position in range(4):
            build.board(i, i_new, position)
        build.board(i, i_old, 4, completeness=PARTIAL)

        # second import of the same game.
        j = add("j_second_import_uncertain.jpg", job2, status="completed")
        j_rev = build.revision(j, revision=0, range_start=9000, status="needs_review")
        for position in range(9):
            boards[f"j{position}"] = build.board(j, j_rev, position).id
        k = add("k_second_import_complete.jpg", job2)
        k_rev = build.revision(k, revision=0, range_start=9500)
        for position in range(9):
            boards[f"k{position}"] = build.board(k, k_rev, position).id

        # symbol cells for the low-quality signal.
        a_boards = {
            position: session.get(RecognizedBoardModel, boards[f"a{position}"])
            for position in range(5)
        }
        pending, approved = "pending", "approved"
        build.cells(a_boards[0], a_rev, job1, specs=[(0.5, pending, True)] * 6)
        build.cells(
            a_boards[1], a_rev, job1, specs=[(0.5, pending, True)] * 4 + [(0.95, pending, True)] * 2
        )
        build.cells(a_boards[2], a_rev, job1, specs=[(0.8, pending, True)] * 6)
        build.cells(
            a_boards[3], a_rev, job1, specs=[(0.3, pending, True)] * 4 + [(0.3, approved, True)] * 2
        )
        build.cells(a_boards[4], a_rev, job1, specs=[(0.2, pending, False)] * 5)
        k0 = session.get(RecognizedBoardModel, boards["k0"])
        build.cells(k0, k_rev, job2, specs=[(0.4, pending, True)] * 5)

        game_id, other_id, job1_id, job2_id = game.id, other.id, job1.id, job2.id

    with Session(database, expire_on_commit=False) as session, session.begin():
        _provision_v2_storage_location(session, game_id=other_id)
        build = _Builder(session, other_id)
        other_job = _import_job(session, game_id=other_id)
        z = build.source(other_job, "z_other_game.jpg")
        z_rev = build.revision(z, revision=0, range_start=100)
        images["z_other_game.jpg"] = z.id
        boards["z0"] = build.board(z, z_rev, 0).id
        build.cells(
            session.get(RecognizedBoardModel, boards["z0"]),
            z_rev,
            other_job,
            specs=[(0.1, "pending", True)] * 6,
        )
        other_job_id = other_job.id

    return _World(
        game_id=game_id,
        other_game_id=other_id,
        job1=job1_id,
        job2=job2_id,
        other_job=other_job_id,
        images=images,
        boards=boards,
    )


def _name(world: _World, image_id: UUID) -> str:
    return next(name for name, value in world.images.items() if value == image_id)


def test_report_counts_every_image_state_and_position_state(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        report = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            world.game_id
        )

    assert report is not None
    images = report.images
    assert (
        images.total,
        images.complete,
        images.incomplete,
        images.incomplete_missing,
        images.incomplete_partial,
        images.incomplete_uncertain,
        images.no_source_geometry,
    ) == (11, 4, 7, 2, 1, 3, 1)
    assert report.expected_board_count == 80
    assert {(p.state, p.reason_code): p.count for p in report.positions} == {
        (GeometryPositionState.OK, None): 56,
        (GeometryPositionState.UNCERTAIN, None): 19,
        (GeometryPositionState.PARTIAL, None): 1,
        (GeometryPositionState.MISSING, None): 3,
        (GeometryPositionState.DEFERRED, "residual_too_high"): 1,
    }
    assert sum(p.count for p in report.positions) == report.expected_board_count
    statuses = {(s.image_state, s.source_status): s.count for s in report.source_statuses}
    assert statuses[(GeometryImageState.NO_SOURCE_GEOMETRY, "processing")] == 1
    assert statuses[(GeometryImageState.INCOMPLETE_UNCERTAIN, "completed")] == 1
    assert sum(statuses.values()) == images.total


def test_report_can_be_narrowed_to_one_import(database: Engine, world: _World) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        first = repository.completeness_report(world.game_id, import_job_id=world.job1)
        second = repository.completeness_report(world.game_id, import_job_id=world.job2)

    assert first is not None and second is not None
    assert first.import_job_id == world.job1
    assert (first.images.total, first.images.complete, first.images.incomplete) == (9, 3, 6)
    assert (second.images.total, second.images.complete, second.images.incomplete) == (2, 1, 1)
    assert second.images.incomplete_uncertain == 1


def test_a_second_game_never_leaks_into_the_result(database: Engine, world: _World) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        other = repository.completeness_report(world.other_game_id)
        listing = repository.incomplete_images(world.other_game_id)

    assert other is not None and listing is not None
    assert (other.images.total, other.images.incomplete_missing) == (1, 1)
    assert [image.relative_path for image in listing.images] == ["z_other_game.jpg"]
    assert [p.state for p in listing.images[0].positions].count(GeometryPositionState.MISSING) == 8


def test_unknown_game_returns_none_and_foreign_import_is_not_found(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        assert (
            SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(uuid4())
            is None
        )
    with Session(database) as session, pytest.raises(ImageReviewNotFoundError) as error:
        SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            world.game_id, import_job_id=world.other_job
        )
    assert error.value.code == "IMAGE_GEOMETRY_COMPLETENESS_IMPORT_NOT_FOUND"


def test_list_returns_only_incomplete_images_in_path_order(database: Engine, world: _World) -> None:
    with Session(database) as session:
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            world.game_id
        )

    assert page is not None
    assert page.next_cursor is None
    assert [(image.relative_path, image.image_state) for image in page.images] == [
        ("b_missing.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("c_partial.jpg", GeometryImageState.INCOMPLETE_PARTIAL),
        ("d_uncertain.jpg", GeometryImageState.INCOMPLETE_UNCERTAIN),
        ("e_no_geometry.jpg", GeometryImageState.NO_SOURCE_GEOMETRY),
        ("g_stale_pointer.jpg", GeometryImageState.INCOMPLETE_UNCERTAIN),
        ("h_closed_pending.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("j_second_import_uncertain.jpg", GeometryImageState.INCOMPLETE_UNCERTAIN),
    ]


def test_list_positions_carry_state_sequence_number_reason_and_quad(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            world.game_id, image_state=GeometryImageState.INCOMPLETE_MISSING
        )

    assert page is not None
    b, h = page.images
    assert (b.sequence_range_start, b.sequence_range_end, b.expected_board_count) == (2000, 2008, 9)
    assert (b.oriented_width, b.oriented_height, b.source_revision) == (1080, 652, 0)
    assert [(p.position_index, p.sequence_number) for p in b.positions] == [
        (position, 2000 + position) for position in range(9)
    ]
    states = [(p.state, p.reason_code) for p in b.positions]
    assert states[:7] == [(GeometryPositionState.OK, None)] * 7
    assert states[7] == (GeometryPositionState.DEFERRED, "residual_too_high")
    assert states[8] == (GeometryPositionState.MISSING, None)
    assert b.positions[7].recognized_board_id is None
    # a position without a board still shows the grid of the current revision
    assert b.positions[7].quad == (
        (71.0, 20.0),
        (79.0, 20.0),
        (79.0, 60.0),
        (71.0, 60.0),
    )
    # resolved / superseded pending rows are closed: plain missing, not deferred
    assert [p.state for p in h.positions[7:]] == [GeometryPositionState.MISSING] * 2
    assert all(p.reason_code is None for p in h.positions)


def test_older_revision_slots_and_boards_do_not_change_the_expected_positions(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        page = repository.incomplete_images(world.game_id, limit=100)
        report = repository.completeness_report(world.game_id)

    assert page is not None and report is not None
    assert "i_trimmed_slots.jpg" not in [image.relative_path for image in page.images]
    # 4 expected positions, all ok; the stray partial board at position 4 is ignored
    assert report.images.complete == 4


def test_stale_pointer_shows_the_grid_of_the_revision_the_board_was_cut_from(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            world.game_id
        )

    assert page is not None
    g = next(image for image in page.images if image.relative_path == "g_stale_pointer.jpg")
    assert g.source_revision == 1
    assert all(p.state is GeometryPositionState.UNCERTAIN for p in g.positions)
    # revision 0 quads (x around 1..90), not the newest revision's (x around 1000+)
    assert all(p.quad is not None and p.quad[0][0] < 1000 for p in g.positions)


def test_preview_review_item_is_a_board_item_and_prefers_a_non_superseded_one(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            world.game_id
        )
        assert page is not None
        by_name = {image.relative_path: image for image in page.images}
        stale = by_name["g_stale_pointer.jpg"]
        assert stale.preview_review_item_id is not None
        GameStorageRouter().bind(session, world.game_id, intent=GameStorageIntent.READ)
        status, position = session.execute(
            text(
                "SELECT ri.status, b.position_index FROM image_review_items ri "
                "JOIN recognized_boards b "
                "ON b.game_id = ri.game_id AND b.id = ri.recognized_board_id "
                "WHERE ri.game_id = :game_id AND ri.id = :id"
            ),
            {"game_id": world.game_id, "id": stale.preview_review_item_id},
        ).one()

    # position 0 holds the superseded item; the pending one of position 1 is preferred
    assert (status, position) == ("pending", 1)
    assert by_name["e_no_geometry.jpg"].preview_review_item_id is None
    assert by_name["e_no_geometry.jpg"].positions == ()
    assert by_name["e_no_geometry.jpg"].expected_board_count is None
    assert by_name["b_missing.jpg"].preview_review_item_id is not None


def test_state_filter_import_filter_and_stable_pagination(database: Engine, world: _World) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        uncertain = repository.incomplete_images(
            world.game_id, image_state=GeometryImageState.INCOMPLETE_UNCERTAIN
        )
        in_job2 = repository.incomplete_images(world.game_id, import_job_id=world.job2)
        walked: list[str] = []
        cursor: GeometryImageCursor | None = None
        for _ in range(10):
            page = repository.incomplete_images(world.game_id, after=cursor, limit=2)
            assert page is not None
            walked.extend(image.relative_path for image in page.images)
            cursor = page.next_cursor
            if cursor is None:
                break
        everything = repository.incomplete_images(world.game_id)

    assert uncertain is not None and in_job2 is not None and everything is not None
    assert [image.relative_path for image in uncertain.images] == [
        "d_uncertain.jpg",
        "g_stale_pointer.jpg",
        "j_second_import_uncertain.jpg",
    ]
    assert [image.relative_path for image in in_job2.images] == ["j_second_import_uncertain.jpg"]
    assert walked == [image.relative_path for image in everything.images]
    assert len(walked) == len(set(walked)) == 7


def test_the_sql_counters_agree_with_the_pure_classifier_on_every_listed_image(
    database: Engine, world: _World
) -> None:
    """The aggregate SQL and ``classify_position`` implement one definition."""

    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        report = repository.completeness_report(world.game_id)
        page = repository.incomplete_images(world.game_id)

    assert report is not None and page is not None
    non_ok: dict[tuple[GeometryPositionState, str | None], int] = {}
    for image in page.images:
        assert image.image_state is classify_image(
            (position.state for position in image.positions),
            has_source_geometry=image.source_revision is not None,
        )
        for position in image.positions:
            if position.state is not GeometryPositionState.OK:
                key = (position.state, position.reason_code)
                non_ok[key] = non_ok.get(key, 0) + 1
    # complete images contain only ok positions, so every non-ok one is in the list
    assert non_ok == {
        (p.state, p.reason_code): p.count
        for p in report.positions
        if p.state is not GeometryPositionState.OK and p.count
    }


def test_the_list_is_bounded_and_rejects_the_complete_state(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        with pytest.raises(Exception) as limit_error:
            repository.incomplete_images(world.game_id, limit=101)
        with pytest.raises(Exception) as state_error:
            repository.incomplete_images(world.game_id, image_state=GeometryImageState.COMPLETE)

    assert getattr(limit_error.value, "code", None) == "IMAGE_GEOMETRY_COMPLETENESS_LIMIT_INVALID"
    assert getattr(state_error.value, "code", None) == "IMAGE_GEOMETRY_COMPLETENESS_STATE_INVALID"


def test_low_quality_boards_use_the_cell_review_definition(database: Engine, world: _World) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        default = repository.low_quality_boards(world.game_id, thresholds=LowQualityThresholds())
        wider = repository.low_quality_boards(
            world.game_id, thresholds=LowQualityThresholds(max_confidence=0.8, min_cells=4)
        )
        strict = repository.low_quality_boards(
            world.game_id, thresholds=LowQualityThresholds(max_confidence=0.6, min_cells=5)
        )
        job2_only = repository.low_quality_boards(
            world.game_id, import_job_id=world.job2, thresholds=LowQualityThresholds()
        )

    assert (
        default is not None and wider is not None and strict is not None and job2_only is not None
    )
    by_board = {board.recognized_board_id: board for board in default.boards}
    # a0: 6 pending cells at 0.5; a2: 6 cells exactly at the 0.80 bound (<=); k0: second import
    assert set(by_board) == {world.boards["a0"], world.boards["a2"], world.boards["k0"]}
    assert by_board[world.boards["a0"]].low_cell_count == 6
    assert by_board[world.boards["a0"]].min_confidence == 0.5
    assert by_board[world.boards["a2"]].min_confidence == 0.8
    assert default.total_boards == 3
    assert (default.max_confidence, default.min_cells) == (0.8, 5)
    # a1 has 4 low pending cells and a3 has 4 (two are human-approved): only minCells=4 sees them;
    # a4's cells are not visible (source unavailable) and never count.
    assert {board.recognized_board_id for board in wider.boards} == {
        world.boards[name] for name in ("a0", "a1", "a2", "a3", "k0")
    }
    assert [board.low_cell_count for board in wider.boards][:2] == [6, 6]
    assert {board.recognized_board_id for board in strict.boards} == {
        world.boards["a0"],
        world.boards["k0"],
    }
    assert [board.recognized_board_id for board in job2_only.boards] == [world.boards["k0"]]
    assert job2_only.boards[0].relative_path == "k_second_import_complete.jpg"
    assert job2_only.boards[0].sequence_number == 9500
    assert job2_only.boards[0].position_index == 0


def test_low_quality_never_returns_another_games_boards(database: Engine, world: _World) -> None:
    with Session(database) as session:
        report = SqlAlchemyImageGeometryCompletenessRepository(session).low_quality_boards(
            world.other_game_id, thresholds=LowQualityThresholds()
        )

    assert report is not None
    assert [board.recognized_board_id for board in report.boards] == [world.boards["z0"]]


def test_low_quality_timeout_raises_a_domain_error_instead_of_an_empty_result(
    database: Engine, world: _World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(repository_module, "LOW_QUALITY_STATEMENT_TIMEOUT_MS", 200)
    monkeypatch.setattr(
        repository_module,
        "_LOW_QUALITY_SQL",
        repository_module._LOW_QUALITY_SQL.replace(
            "WHERE c.game_id = :game_id", "WHERE pg_sleep(1) IS NOT NULL AND c.game_id = :game_id"
        ),
    )
    with Session(database) as session, pytest.raises(ImageReviewConflictError) as error:
        SqlAlchemyImageGeometryCompletenessRepository(session).low_quality_boards(
            world.game_id, thresholds=LowQualityThresholds()
        )

    assert error.value.code == "IMAGE_GEOMETRY_LOW_QUALITY_TIMEOUT"
    assert error.value.details == {"timeoutMs": 200}


def test_every_query_runs_in_a_read_only_transaction(database: Engine, world: _World) -> None:
    """A write anywhere in the repository would raise ``ReadOnlySqlTransaction``."""

    with Session(database) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        assert repository.completeness_report(world.game_id) is not None
        assert repository.completeness_report(world.game_id, import_job_id=world.job1) is not None
        assert repository.incomplete_images(world.game_id) is not None
        assert (
            repository.low_quality_boards(world.game_id, thresholds=LowQualityThresholds())
            is not None
        )
        session.rollback()
