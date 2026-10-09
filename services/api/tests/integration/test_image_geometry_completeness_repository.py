"""Isolated PostgreSQL coverage of the D-484 geometry completeness report (TASK-0806, 0808).

Builds a game routed to ``game_data_v2`` with one source image per state and
the edge cases the definition names (older revisions, closed pending rows,
boards outside the current slots) directly through the ORM, then reads it back
through ``SqlAlchemyImageGeometryCompletenessRepository``. A second world covers
the TASK-0808 states (rejected boards, superseded positions and images, failed
imports, checksum twins) in a game of its own. The repository is read-only:
every call below also runs in a ``READ ONLY`` transaction.
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
from game_predictor_api.storage.game_data_v2_manifest_v7 import VERSION
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
        self,
        job: JobModel,
        relative_path: str,
        *,
        status: str = "waiting_for_review",
        checksum: str | None = None,
        pipeline: str = "b" * 64,
        failed_code: str | None = None,
    ) -> SourceImageModel:
        """A source image with its import file; ``failed_code`` makes the file ``failed``.

        An explicit ``checksum`` shared by two images makes them checksum twins; the
        second one needs another ``pipeline`` fingerprint (one execution per pair).
        """

        execution_key = uuid4().hex * 2
        checksum = checksum or execution_key
        failure = (
            {
                "failed_stage": "image_geometry",
                "error_code": failed_code,
                "error_message": "fixture failure",
                "last_failed_at": datetime.now(UTC),
            }
            if failed_code is not None
            else {}
        )
        workflow_status = "failed" if failed_code is not None else "waiting_for_review"
        self.session.add(
            ImageFileExecutionModel(
                file_execution_key=execution_key,
                source_checksum_sha256=checksum,
                pipeline_fingerprint=pipeline,
                checkpoint_payload={},
                status=workflow_status,
                review_required=failed_code is None,
                **failure,
            )
        )
        self.session.flush()
        self.session.add(
            ImageImportJobFileModel(
                job_id=job.id,
                file_execution_key=execution_key,
                order_index=self.order,
                source_relative_path=relative_path,
                workflow_checkpoint_payload={},
                workflow_status=workflow_status,
                review_required=failed_code is None,
                **failure,
            )
        )
        self.order += 1
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=execution_key,
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
        board_status: str = "pending_review",
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
            status=board_status,
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
    assert (images.superseded, images.import_failed) == (0, 0)
    assert report.expected_board_count == 80
    assert {(p.state, p.reason_code): p.count for p in report.positions} == {
        (GeometryPositionState.OK, None): 56,
        (GeometryPositionState.UNCERTAIN, None): 19,
        (GeometryPositionState.PARTIAL, None): 1,
        (GeometryPositionState.SUPERSEDED, None): 0,
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


def test_listed_images_carry_no_import_error_code_when_their_file_did_not_fail(
    database: Engine, world: _World
) -> None:
    with Session(database) as session:
        page = SqlAlchemyImageGeometryCompletenessRepository(session).incomplete_images(
            world.game_id
        )

    assert page is not None
    assert all(image.import_error_code is None for image in page.images)
    by_name = {image.relative_path: image for image in page.images}
    assert by_name["e_no_geometry.jpg"].positions == ()
    assert by_name["e_no_geometry.jpg"].expected_board_count is None


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


def test_every_query_runs_in_a_read_only_transaction(
    database: Engine, world: _World, supersession: _SupersessionWorld
) -> None:
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

    for game_id in (supersession.game_id, supersession.other_game_id):
        with Session(database) as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            repository = SqlAlchemyImageGeometryCompletenessRepository(session)
            assert repository.completeness_report(game_id) is not None
            for state in (None, GeometryImageState.SUPERSEDED, GeometryImageState.IMPORT_FAILED):
                assert repository.incomplete_images(game_id, image_state=state) is not None
            image_id = next(iter(supersession.images.values()), None)
            if game_id == supersession.game_id and image_id is not None:
                assert repository.source_image_asset(game_id, image_id) is not None
            session.rollback()


# --------------------------------------------------------------------------------------
# TASK-0808: rejected boards, superseded positions and images, failed imports, twins.
# --------------------------------------------------------------------------------------

FAILED_STAGE_EXECUTION = "IMAGE_STAGE_EXECUTION_FAILED"
FAILED_RESULT_INVALID = "IMAGE_STAGE_RESULT_INVALID"
FAILED_VIRTUAL_SUPPORT = "IMAGE_VIRTUAL_CELL_SOURCE_SUPPORT_INCOMPLETE"
REJECTED = "rejected"


@dataclass(slots=True)
class _SupersessionWorld:
    game_id: UUID
    other_game_id: UUID
    job_old: UUID
    job_new: UUID
    images: dict[str, UUID]
    other_image: UUID


@pytest.fixture(scope="module")
def supersession(database: Engine, world: _World) -> _SupersessionWorld:
    """Game C: the old import holds the ``s*`` images, the newer one the ``d*`` covers.

    ``world.other_game_id`` (game B) owns a live review item for sequence number 100.
    """

    images: dict[str, UUID] = {}
    with Session(database, expire_on_commit=False) as session, session.begin():
        game = GameModel(code="geo-c", name="Geometry C", expected_layout_count=100000)
        session.add(game)
        session.flush()
        _provision_v2_storage_location(session, game_id=game.id)
        build = _Builder(session, game.id)
        old = _import_job(session, game_id=game.id)
        new = _import_job(session, game_id=game.id)

        def add(
            name: str,
            job: JobModel,
            *,
            checksum: str | None = None,
            pipeline: str = "b" * 64,
            failed_code: str | None = None,
            status: str = "waiting_for_review",
        ) -> SourceImageModel:
            source = build.source(
                job,
                name,
                status=status,
                checksum=checksum,
                pipeline=pipeline,
                failed_code=failed_code,
            )
            images[name] = source.id
            return source

        def rejected_boards(
            source: SourceImageModel, revision: ImageSourceGeometryRevisionModel, positions: range
        ) -> None:
            for position in positions:
                build.board(
                    source,
                    revision,
                    position,
                    item_status="superseded",
                    board_status=REJECTED,
                )

        def live_boards(
            source: SourceImageModel,
            revision: ImageSourceGeometryRevisionModel,
            positions: range,
            *,
            item_status: str = "pending",
        ) -> None:
            for position in positions:
                build.board(source, revision, position, item_status=item_status)

        # s01: every board rejected; every sequence number lives on d01 -> superseded image.
        s01 = add("s01_rejected_all_covered.jpg", old)
        rejected_boards(s01, build.revision(s01, revision=0, range_start=1000), range(9))
        d01 = add("d01_cover_1000.jpg", new)
        live_boards(d01, build.revision(d01, revision=0, range_start=1000), range(9))

        # s02: 7 ok + 2 rejected positions covered by accepted / corrected items -> complete.
        s02 = add("s02_mixed_complete.jpg", old)
        s02_rev = build.revision(s02, revision=0, range_start=2000)
        live_boards(s02, s02_rev, range(7))
        rejected_boards(s02, s02_rev, range(7, 9))
        d02 = add("d02_cover_2007.jpg", new)
        d02_rev = build.revision(d02, revision=0, range_start=2007, slots=2)
        build.board(d02, d02_rev, 0, item_status="accepted")
        build.board(d02, d02_rev, 1, item_status="corrected")

        # s03: 7 ok, one rejected position covered elsewhere, one rejected and uncovered.
        s03 = add("s03_mixed_missing.jpg", old)
        s03_rev = build.revision(s03, revision=0, range_start=3000)
        live_boards(s03, s03_rev, range(7))
        rejected_boards(s03, s03_rev, range(7, 9))
        d03 = add("d03_cover_3007.jpg", new)
        live_boards(d03, build.revision(d03, revision=0, range_start=3007, slots=1), range(1))

        # s04: every board rejected, nothing live elsewhere -> plain missing.
        s04 = add("s04_rejected_uncovered.jpg", old)
        rejected_boards(s04, build.revision(s04, revision=0, range_start=4000), range(9))

        # s05: failed import, no board, no twin, numbers not covered -> import_failed.
        s05 = add("s05_failed_no_twin.jpg", old, failed_code=FAILED_STAGE_EXECUTION)
        build.revision(s05, revision=0, range_start=5000)

        # s06: failed import whose content was imported again (checksum twin d06) -> superseded,
        # although its own sequence numbers are not covered.
        twin_checksum = _sha("twin-with-revision")
        s06 = add(
            "s06_failed_with_twin.jpg",
            old,
            checksum=twin_checksum,
            failed_code=FAILED_RESULT_INVALID,
        )
        build.revision(s06, revision=0, range_start=6000)
        d06 = add("d06_twin.jpg", new, checksum=twin_checksum, pipeline="c" * 64)
        live_boards(d06, build.revision(d06, revision=0, range_start=6100), range(9))

        # s07: failed import without any source geometry and a checksum twin -> superseded.
        twin_checksum_2 = _sha("twin-without-revision")
        add(
            "s07_failed_no_revision_twin.jpg",
            old,
            checksum=twin_checksum_2,
            failed_code=FAILED_RESULT_INVALID,
        )
        d07 = add("d07_twin.jpg", new, checksum=twin_checksum_2, pipeline="c" * 64)
        live_boards(d07, build.revision(d07, revision=0, range_start=7100), range(9))

        # s08: failed import without source geometry and no twin -> import_failed, not
        # no_source_geometry.
        add("s08_failed_no_revision_no_twin.jpg", old, failed_code=FAILED_VIRTUAL_SUPPORT)

        # s09: every board rejected; sequence number 100 lives only in the OTHER game.
        s09 = add("s09_other_game_sequence.jpg", old)
        rejected_boards(s09, build.revision(s09, revision=0, range_start=100), range(9))

        # s10: a superseded position wins over an open pending row; the uncovered one stays
        # deferred.
        s10 = add("s10_superseded_beats_deferred.jpg", old)
        s10_rev = build.revision(s10, revision=0, range_start=8000)
        live_boards(s10, s10_rev, range(7))
        build.pending(s10, 7, 8007, status="pending", reason="residual_too_high")
        build.pending(s10, 8, 8008, status="pending", reason="incomplete_lattice")
        d10 = add("d10_cover_8007.jpg", new)
        live_boards(d10, build.revision(d10, revision=0, range_start=8007, slots=1), range(1))

        # s11: the numbers are held only by non-live review items elsewhere -> missing.
        s11 = add("s11_covered_by_a_rejected_item.jpg", old)
        rejected_boards(s11, build.revision(s11, revision=0, range_start=9000), range(9))
        d11 = add("d11_rejected_items_9000.jpg", new)
        live_boards(
            d11, build.revision(d11, revision=0, range_start=9000), range(9), item_status="rejected"
        )

        # s12: no source geometry, no boards, a file that did not fail.
        add("s12_no_geometry.jpg", old, status="processing")

        # s14: failed file, but live boards exist -> the failure is irrelevant.
        s14 = add("s14_failed_with_boards.jpg", old, failed_code=FAILED_STAGE_EXECUTION)
        live_boards(s14, build.revision(s14, revision=0, range_start=10000), range(9))

        game_id, old_id, new_id = game.id, old.id, new.id

    return _SupersessionWorld(
        game_id=game_id,
        other_game_id=world.other_game_id,
        job_old=old_id,
        job_new=new_id,
        images=images,
        other_image=world.images["z_other_game.jpg"],
    )


def _list_all(
    repository: SqlAlchemyImageGeometryCompletenessRepository,
    game_id: UUID,
    state: GeometryImageState | None = None,
) -> list[repository_module.IncompleteGeometryImage]:
    page = repository.incomplete_images(game_id, image_state=state, limit=100)
    assert page is not None and page.next_cursor is None
    return list(page.images)


def _states(image: repository_module.IncompleteGeometryImage) -> list[GeometryPositionState]:
    return [position.state for position in image.positions]


def test_rejected_and_superseded_images_are_counted_separately_from_gaps(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        report = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            supersession.game_id
        )

    assert report is not None
    images = report.images
    assert (images.total, images.complete, images.superseded, images.import_failed) == (20, 9, 3, 2)
    assert (
        images.incomplete_missing,
        images.incomplete_partial,
        images.incomplete_uncertain,
        images.no_source_geometry,
    ) == (5, 0, 0, 1)
    # superseded images are not incomplete; import_failed and no_source_geometry are
    assert images.incomplete == 20 - 9 - 3 == 8
    assert report.expected_board_count == 130
    assert {(p.state, p.reason_code): p.count for p in report.positions} == {
        (GeometryPositionState.OK, None): 70,
        (GeometryPositionState.UNCERTAIN, None): 0,
        (GeometryPositionState.PARTIAL, None): 0,
        (GeometryPositionState.SUPERSEDED, None): 13,
        (GeometryPositionState.MISSING, None): 46,
        (GeometryPositionState.DEFERRED, "incomplete_lattice"): 1,
    }
    assert sum(p.count for p in report.positions) == report.expected_board_count
    statuses = {(s.image_state, s.source_status): s.count for s in report.source_statuses}
    assert statuses[(GeometryImageState.NO_SOURCE_GEOMETRY, "processing")] == 1
    assert statuses[(GeometryImageState.IMPORT_FAILED, "waiting_for_review")] == 2
    assert sum(statuses.values()) == images.total


def test_report_scoped_to_one_import_still_finds_the_checksum_twin_in_the_other_import(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        old = repository.completeness_report(
            supersession.game_id, import_job_id=supersession.job_old
        )
        new = repository.completeness_report(
            supersession.game_id, import_job_id=supersession.job_new
        )

    assert old is not None and new is not None
    assert (old.images.total, old.images.superseded, old.images.import_failed) == (13, 3, 2)
    assert (new.images.total, new.images.complete, new.images.superseded) == (7, 7, 0)
    assert new.images.incomplete == 0


def test_default_list_holds_gaps_and_failed_imports_but_not_superseded_or_complete_images(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        listed = _list_all(
            SqlAlchemyImageGeometryCompletenessRepository(session), supersession.game_id
        )

    assert [(image.relative_path, image.image_state) for image in listed] == [
        ("s03_mixed_missing.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("s04_rejected_uncovered.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("s05_failed_no_twin.jpg", GeometryImageState.IMPORT_FAILED),
        ("s08_failed_no_revision_no_twin.jpg", GeometryImageState.IMPORT_FAILED),
        ("s09_other_game_sequence.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("s10_superseded_beats_deferred.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("s11_covered_by_a_rejected_item.jpg", GeometryImageState.INCOMPLETE_MISSING),
        ("s12_no_geometry.jpg", GeometryImageState.NO_SOURCE_GEOMETRY),
    ]
    codes = {image.relative_path: image.import_error_code for image in listed}
    assert codes["s05_failed_no_twin.jpg"] == FAILED_STAGE_EXECUTION
    assert codes["s08_failed_no_revision_no_twin.jpg"] == FAILED_VIRTUAL_SUPPORT
    assert codes["s03_mixed_missing.jpg"] is None
    assert codes["s12_no_geometry.jpg"] is None


def test_the_superseded_filter_lists_replaced_images_with_their_positions_and_error_code(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        listed = _list_all(
            SqlAlchemyImageGeometryCompletenessRepository(session),
            supersession.game_id,
            GeometryImageState.SUPERSEDED,
        )

    by_name = {image.relative_path: image for image in listed}
    assert list(by_name) == [
        "s01_rejected_all_covered.jpg",
        "s06_failed_with_twin.jpg",
        "s07_failed_no_revision_twin.jpg",
    ]
    s01, s06, s07 = by_name.values()
    # rule 1: every expected position is covered by a live item on another image
    assert _states(s01) == [GeometryPositionState.SUPERSEDED] * 9
    assert all(position.recognized_board_id is None for position in s01.positions)
    assert s01.import_error_code is None
    # rule 2: no live board and a checksum twin; the positions themselves are plain gaps
    assert _states(s06) == [GeometryPositionState.MISSING] * 9
    assert s06.import_error_code == FAILED_RESULT_INVALID
    assert (s07.positions, s07.expected_board_count, s07.source_revision) == ((), None, None)
    assert s07.import_error_code == FAILED_RESULT_INVALID


def test_import_failed_and_no_source_geometry_filters(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        failed = _list_all(repository, supersession.game_id, GeometryImageState.IMPORT_FAILED)
        no_geometry = _list_all(
            repository, supersession.game_id, GeometryImageState.NO_SOURCE_GEOMETRY
        )

    assert [image.relative_path for image in failed] == [
        "s05_failed_no_twin.jpg",
        "s08_failed_no_revision_no_twin.jpg",
    ]
    assert [image.relative_path for image in no_geometry] == ["s12_no_geometry.jpg"]


def test_position_states_of_rejected_boards_depend_on_a_live_sequence_elsewhere(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        listed = _list_all(
            SqlAlchemyImageGeometryCompletenessRepository(session), supersession.game_id
        )

    by_name = {image.relative_path: image for image in listed}
    ok, superseded, missing = (
        GeometryPositionState.OK,
        GeometryPositionState.SUPERSEDED,
        GeometryPositionState.MISSING,
    )
    # rejected board + live item elsewhere -> superseded; without one -> missing
    s03 = by_name["s03_mixed_missing.jpg"]
    assert _states(s03) == [ok] * 7 + [superseded, missing]
    assert [position.recognized_board_id is None for position in s03.positions[7:]] == [True, True]
    assert _states(by_name["s04_rejected_uncovered.jpg"]) == [missing] * 9
    # a review item that is not live (rejected) elsewhere does not cover the number
    assert _states(by_name["s11_covered_by_a_rejected_item.jpg"]) == [missing] * 9
    # a sequence number that is live only in ANOTHER game never supersedes a position
    s09 = by_name["s09_other_game_sequence.jpg"]
    assert s09.positions[0].sequence_number == 100
    assert _states(s09) == [missing] * 9
    # a superseded position wins over an open pending row; the uncovered one stays deferred
    s10 = by_name["s10_superseded_beats_deferred.jpg"]
    assert _states(s10)[7:] == [superseded, GeometryPositionState.DEFERRED]
    assert [position.reason_code for position in s10.positions[7:]] == [None, "incomplete_lattice"]
    # the grid of the current revision is still drawn for a position whose board was rejected
    assert all(position.quad is not None for position in s03.positions)


def test_a_mixed_image_with_superseded_positions_and_ok_boards_is_complete(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        everything = {
            image.relative_path
            for state in (None, GeometryImageState.SUPERSEDED)
            for image in _list_all(repository, supersession.game_id, state)
        }

    # 7 ok + 2 superseded is complete: in no list; 7 ok + 1 superseded + 1 missing is not
    assert "s02_mixed_complete.jpg" not in everything
    assert "s03_mixed_missing.jpg" in everything
    assert "s14_failed_with_boards.jpg" not in everything


def test_sql_and_the_pure_classifier_agree_on_the_new_states(
    database: Engine, supersession: _SupersessionWorld
) -> None:
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        report = repository.completeness_report(supersession.game_id)
        listed = [
            *_list_all(repository, supersession.game_id),
            *_list_all(repository, supersession.game_id, GeometryImageState.SUPERSEDED),
        ]
        assert report is not None
        GameStorageRouter().bind(session, supersession.game_id, intent=GameStorageIntent.READ)
        non_ok: dict[tuple[GeometryPositionState, str | None], int] = {}
        for image in listed:
            live, twin = session.execute(
                text(
                    "SELECT (SELECT count(*) FROM recognized_boards b "
                    "        WHERE b.game_id = :g AND b.source_image_id = s.id "
                    "          AND b.status <> 'rejected'), "
                    "  EXISTS (SELECT 1 FROM source_images t JOIN recognized_boards tb "
                    "          ON tb.game_id = t.game_id AND tb.source_image_id = t.id "
                    "          WHERE t.game_id = :g AND t.id <> s.id "
                    "            AND t.checksum_sha256 = s.checksum_sha256 "
                    "            AND tb.status <> 'rejected') "
                    "FROM source_images s WHERE s.game_id = :g AND s.id = :id"
                ),
                {"g": supersession.game_id, "id": image.source_image_id},
            ).one()
            assert image.image_state is classify_image(
                _states(image),
                has_source_geometry=image.source_revision is not None,
                has_live_boards=live > 0,
                checksum_twin_has_live_boards=bool(twin),
                import_file_failed=image.import_error_code is not None,
            ), image.relative_path
            for position in image.positions:
                if position.state is not GeometryPositionState.OK:
                    key = (position.state, position.reason_code)
                    non_ok[key] = non_ok.get(key, 0) + 1

    # s02 is the one complete image that holds non-ok positions (2 superseded) and is in no list
    non_ok[(GeometryPositionState.SUPERSEDED, None)] += 2
    assert non_ok == {
        (p.state, p.reason_code): p.count
        for p in report.positions
        if p.state is not GeometryPositionState.OK and p.count
    }


def test_the_second_game_does_not_change_the_first_games_superseded_result(
    database: Engine, world: _World, supersession: _SupersessionWorld
) -> None:
    """Sequence 100 is live in game B only: game C's s09 stays a gap, B stays untouched."""

    with Session(database) as session:
        other = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            supersession.other_game_id
        )
    with Session(database) as session:
        first = SqlAlchemyImageGeometryCompletenessRepository(session).completeness_report(
            world.game_id
        )

    assert other is not None and first is not None
    assert (other.images.total, other.images.superseded, other.images.import_failed) == (1, 0, 0)
    assert (first.images.total, first.images.superseded, first.images.import_failed) == (11, 0, 0)


def test_source_image_asset_is_keyed_by_the_source_image_and_bound_to_its_game(
    database: Engine, world: _World, supersession: _SupersessionWorld
) -> None:
    image_id = supersession.images["s05_failed_no_twin.jpg"]
    with Session(database) as session:
        repository = SqlAlchemyImageGeometryCompletenessRepository(session)
        asset = repository.source_image_asset(supersession.game_id, image_id)
        # an image without any recognized board still has its file
        assert asset is not None
        assert (asset.source_image_id, asset.relative_path) == (
            image_id,
            "s05_failed_no_twin.jpg",
        )
        assert len(asset.checksum_sha256) == 64
        # another game's image and an unknown identifier are 404, an unknown game is None
        with pytest.raises(ImageReviewNotFoundError) as foreign:
            repository.source_image_asset(supersession.game_id, supersession.other_image)
        with pytest.raises(ImageReviewNotFoundError) as unknown:
            repository.source_image_asset(supersession.game_id, uuid4())
        assert repository.source_image_asset(uuid4(), image_id) is None

    code = "IMAGE_GEOMETRY_COMPLETENESS_SOURCE_IMAGE_NOT_FOUND"
    assert foreign.value.code == unknown.value.code == code
