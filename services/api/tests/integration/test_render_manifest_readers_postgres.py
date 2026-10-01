"""TASK-0758: readers switched from ``cell_observations`` to render manifests.

Equivalence on an isolated ``*_test`` database: the same import-shaped boards
are read through the pre-switch code (``v1.7.111``, loaded from git) and
through the current code, and every materialized review cell, re-inference
render record, board-search document and stale-base-crop verdict must be
identical.  The pre-switch modules are executed from ``git show``; the only
edit is dropping the removed ``ImageReviewCell.observation_id`` argument.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.jobs import JobStatus, JobType, create_job
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage import board_search_projection_repository as new_search
from game_predictor_api.storage import image_review_repository as new_mapper
from game_predictor_api.storage import image_symbol_review_repository as new_symbol_review
from game_predictor_api.storage.board_render_manifest_backfill import (
    BackfillBatchResult,
    run_game,
)
from game_predictor_api.storage.board_render_manifest_reader import load_current_render_manifest
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.current_board_cell_sources import (
    load_current_board_cell_sources,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemyImageSymbolReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.legacy_cell_observation_adapter import legacy_base_cells
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageBoardGeometryRevisionModel,
    ImageReviewItemModel,
    ImageSourceGeometryRevisionModel,
    ImageSymbolReviewCellModel,
    JobModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)
from game_predictor_worker.images import pending_symbol_reinference as new_reinference
from game_predictor_worker.images.orchestration_store import SqlAlchemyImageBatchStore
from sqlalchemy import Engine, create_engine, func, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

ROOT = Path(__file__).resolve().parents[4]
# v1.7.111 (TASK-0757): the last commit whose readers used cell_observations.
PRE_SWITCH_COMMIT = "f2336115"
PIPELINE = "b" * 64
EXTRACTOR = "virtual-cell-renderer-test-v1"
REVISION_EXTRACTOR = "virtual-cell-renderer-test-v2"
SYMBOLS = ("s0", "s1", "s2")
QUAD = [{"x": 100, "y": 100}, {"x": 600, "y": 100}, {"x": 600, "y": 400}, {"x": 100, "y": 400}]
# Slot -> the cell whose footprint lies outside the source (partial boards).
OUTSIDE = {1: 14, 2: 7}


def _cell_quads(outside: int) -> list[dict[str, object]]:
    def quad(x: float, y: float) -> list[dict[str, float]]:
        return [
            {"x": x, "y": y},
            {"x": x + 50, "y": y},
            {"x": x + 50, "y": y + 50},
            {"x": x, "y": y + 50},
        ]

    return [
        {
            "rowIndex": index // 5,
            "columnIndex": index % 5,
            "sourceQuad": quad(-500, -500) if index == outside else quad(100 + index * 60, 100),
        }
        for index in range(15)
    ]


def _pre_switch_module(relative_path: str, *, remove: tuple[str, ...] = ()) -> ModuleType:
    try:
        source = subprocess.run(
            ["git", "show", f"{PRE_SWITCH_COMMIT}:{relative_path}"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            timeout=60,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.SubprocessError) as error:
        pytest.skip(f"pre-switch source {PRE_SWITCH_COMMIT} is unavailable: {error}")
    for fragment in remove:
        assert fragment in source, fragment
        source = source.replace(fragment, "")
    name = "task0758_pre_switch_" + re.sub(r"\W", "_", relative_path)
    module = ModuleType(name)
    module.__file__ = f"<{PRE_SWITCH_COMMIT}:{relative_path}>"
    sys.modules[name] = module
    try:
        exec(compile(source, module.__file__, "exec"), module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.fixture(scope="module")
def old() -> SimpleNamespace:
    mapper = _pre_switch_module(
        "services/api/src/game_predictor_api/storage/image_review_repository.py",
        remove=(
            "                observation_id=observation.id,\n",
            "                observation_id=observation.id if observation is not None else None,\n",
        ),
    )
    return SimpleNamespace(
        mapper=mapper,
        symbol_review=_pre_switch_module(
            "services/api/src/game_predictor_api/storage/image_symbol_review_repository.py"
        ),
        search=_pre_switch_module(
            "services/api/src/game_predictor_api/storage/board_search_projection_repository.py"
        ),
        reinference=_pre_switch_module(
            "services/worker/src/game_predictor_worker/images/pending_symbol_reinference.py"
        ),
    )


@dataclass(frozen=True)
class _Database:
    engine: Engine
    config: Config


@pytest.fixture
def database() -> Iterator[_Database]:
    name = "game_predictor_task0758_" + uuid4().hex[:12] + "_test"
    assert re.fullmatch(r"game_predictor_task0758_[0-9a-f]{12}_test", name)
    url = make_url(ApiSettings.from_environment().database_url)
    assert url.database != name
    maintenance = create_engine(
        url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    database_engine = create_engine(url.set(database=name), connect_args={"connect_timeout": 5})
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option(
        "sqlalchemy.url",
        url.set(database=name).render_as_string(hide_password=False).replace("%", "%%"),
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        command.upgrade(config, "head")
        yield _Database(database_engine, config)
    finally:
        database_engine.dispose()
        with maintenance.connect() as connection:
            active = -1
            for _attempt in range(50):
                active = connection.execute(
                    text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                    {"name": name},
                ).scalar_one()
                if active == 0:
                    break
                time.sleep(0.1)
            assert active == 0, "Refusing DROP while a test connection remains"
            connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        maintenance.dispose()


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _spec(label: str, index: int) -> dict[str, object]:
    return {
        "boardLabel": label,
        "cellIndex": index,
        "columnIndex": index % 5,
        "rowIndex": index // 5,
        "quad": [[10.5, 20.25], [30.125, 20.25], [30.125, 40.0], [10.5, 40.0]],
        "scale": 1e-07,
        "outputSize": [96, 96],
    }


def _prediction(label: str, index: int) -> dict[str, object]:
    symbol = SYMBOLS[(index + len(label)) % 3]
    return {
        "symbolCode": symbol,
        "confidence": round(0.5 + index / 100, 4),
        "alternatives": [
            {"symbolCode": symbol, "confidence": round(0.5 + index / 100, 4)},
            {"symbolCode": SYMBOLS[(index + 1) % 3], "confidence": 0.125},
        ],
    }


def _cells_prediction(label: str, indices: list[int]) -> dict[str, object]:
    return {
        "cells": [
            {"rowIndex": index // 5, "columnIndex": index % 5, **_prediction(label, index)}
            for index in indices
        ],
        "modelVersion": "task-0758-test",
    }


@dataclass(frozen=True)
class _Seed:
    game_id: UUID
    boards: dict[str, UUID]
    items: dict[str, UUID]


def _seed(factory: sessionmaker[Session], now: datetime) -> _Seed:
    with factory() as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code="render-manifest-readers", name="Readers", status=GameStatus.ACTIVE
        )
        for mobile_code, code in enumerate(SYMBOLS, start=1):
            catalog.create_symbol(
                game.id,
                mobile_code=mobile_code,
                code=code,
                name=code,
                image_path=None,
                is_wildcard=False,
                display_order=mobile_code,
                status=SymbolStatus.ACTIVE,
            )
        job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "pipeline_fingerprint": PIPELINE,
                    "test_source_batch": now.isoformat(),
                },
                created_at=now,
            )
        )
        session.commit()
    execution = SqlAlchemyImageBatchStore(factory).register_file(
        job.id,
        source_checksum_sha256="7" * 64,
        pipeline_fingerprint=PIPELINE,
        source_relative_path="seq_1-9.jpg",
        order_index=0,
        registered_at=now,
    )
    boards: dict[str, UUID] = {}
    items: dict[str, UUID] = {}
    with game_storage_scope(game.id), factory() as session:
        source = SourceImageModel(
            import_job_id=job.id,
            file_execution_key=execution.file_execution_key,
            relative_path="seq_1-9.jpg",
            checksum_sha256="7" * 64,
            width=1920,
            height=1080,
            oriented_width=1920,
            oriented_height=1080,
            status="waiting_for_review",
            created_at=now,
        )
        session.add(source)
        rules = RulesVersionModel(
            game_id=game.id,
            version=1,
            rows=3,
            columns=5,
            spin_cost=0,
            status=RulesVersionStatus.DRAFT,
            created_at=now,
            published_at=None,
        )
        session.add(rules)
        session.flush()
        geometry = ImageSourceGeometryRevisionModel(
            game_id=game.id,
            source_image_id=source.id,
            topology_rules_version_id=rules.id,
            revision=0,
            sequence_range_start=1,
            sequence_range_end=6,
            active_board_slots=[0, 1, 2, 3, 4, 5],
            coordinate_space="exif-normalized-rgb-pixels-v1",
            source_checksum_sha256="7" * 64,
            normalized_pixel_checksum_sha256="c" * 64,
            oriented_width=1920,
            oriented_height=1080,
            normalization_adapter_version="normalization-test-v1",
            global_initialization={},
            board_geometries=[
                {
                    "positionIndex": slot,
                    "sequenceNumber": slot + 1,
                    "finalQuad": QUAD,
                    **({"cells": _cell_quads(OUTSIDE[slot])} if slot in OUTSIDE else {}),
                }
                for slot in range(6)
            ],
            engine_kind="structured_opencv_v1",
            engine_version="structured-test-v1",
            geometry_source="auto",
            status="accepted",
            geometry_checksum_sha256="d" * 64,
            processing_time_ms=1,
            warnings=[],
            created_by="task-0758-test",
            created_at=now,
        )
        session.add(geometry)
        session.flush()

        def board(
            label: str,
            position: int,
            indices: list[int],
            *,
            virtual: bool = True,
            **values: object,
        ) -> RecognizedBoardModel:
            record = RecognizedBoardModel(
                source_image_id=source.id,
                position_index=position,
                sequence_number_raw=str(position + 1),
                sequence_number=position + 1,
                sequence_confidence=1.0,
                board_geometry={"quad": QUAD},
                asset_mode="virtual_source" if virtual else "legacy_file",
                source_geometry_revision_id=geometry.id if virtual else None,
                geometry_engine_name="structured_opencv_v1" if virtual else None,
                geometry_engine_version="structured-test-v1" if virtual else None,
                geometry_checksum_sha256="d" * 64 if virtual else None,
                board_relative_path=None if virtual else f"boards/{label}.png",
                board_checksum_sha256=None if virtual else _sha(f"{label}:board"),
                cells_prediction=_cells_prediction(label, indices),
                board_confidence=1.0,
                pipeline_fingerprint=PIPELINE,
                grid_rows=3,
                grid_columns=5,
                status="pending_review",
                created_at=now,
                **values,
            )
            session.add(record)
            session.flush()
            review = ImageReviewItemModel(
                game_id=game.id,
                import_job_id=job.id,
                sequence_number=position + 1,
                recognized_board_id=record.id,
                status="pending",
                snapshot={"sequenceNumber": position + 1},
                resolution_revision=0,
                created_at=now,
            )
            session.add(review)
            session.flush()
            boards[label], items[label] = record.id, review.id
            for index in indices:
                pixel = _sha(f"{label}:px:{index}")
                session.add(
                    CellObservationModel(
                        recognized_board_id=record.id,
                        row_index=index // 5,
                        column_index=index % 5,
                        asset_mode="virtual_source" if virtual else "legacy_file",
                        source_geometry_revision_id=geometry.id if virtual else None,
                        logical_cell_key=_sha(f"{label}:key:{index}") if virtual else None,
                        logical_cell_key_v2=_sha(f"{label}:key2:{index}") if virtual else None,
                        render_identity_v2_sha256=(
                            _sha(f"{label}:id2:{index}") if virtual else None
                        ),
                        render_spec=_spec(label, index) if virtual else None,
                        render_spec_checksum_sha256=(
                            sha256_canonical_json(_spec(label, index)) if virtual else None
                        ),
                        rendered_pixel_checksum_sha256=pixel if virtual else None,
                        extractor_version=EXTRACTOR if virtual else None,
                        crop_relative_path=None if virtual else f"crops/{label}/{index}.png",
                        crop_checksum_sha256=pixel,
                        cropper_version=EXTRACTOR if virtual else "legacy-cropper-v19",
                        prediction=_prediction(label, index),
                        created_at=now,
                    )
                )
            return record

        def revision(record: RecognizedBoardModel, label: str, **values: object) -> None:
            session.add(
                ImageBoardGeometryRevisionModel(
                    review_item_id=items[label],
                    recognized_board_id=record.id,
                    revision=1,
                    idempotency_key=uuid4(),
                    command_sha256="a" * 64,
                    corners=[
                        {"x": 0, "y": 0},
                        {"x": 1, "y": 0},
                        {"x": 1, "y": 1},
                        {"x": 0, "y": 1},
                    ],
                    geometry={"quad": QUAD},
                    corrected_by="task-0758-test",
                    created_at=now,
                    **values,
                )
            )
            record.geometry_revision = 1

        every = list(range(15))
        board("complete", 0, every)
        board(
            "trailing",
            1,
            [index for index in every if index != 14],
            completeness_status="pending_partial",
            unavailable_cell_indices=[14],
            geometry_qualification=GeometryQualification(
                "pending_partial", (14,), True, "missing_pixels"
            ).to_dict(),
        )
        board(
            "middle",
            2,
            [index for index in every if index != 7],
            completeness_status="pending_partial",
            unavailable_cell_indices=[7],
            geometry_qualification=GeometryQualification(
                "pending_partial", (7,), True, "missing_pixels"
            ).to_dict(),
        )
        revised = board("revised", 3, every)
        revised_spec: dict[str, object] = {
            "assetMode": "virtual_source",
            "cells": [
                {
                    "cellIndex": index,
                    "cropSampleId": _sha(f"revised-r1:sample:{index}"),
                    "logicalCellKeySha256": _sha(f"revised-r1:key:{index}"),
                    "logicalCellKeyV2Sha256": _sha(f"revised-r1:key2:{index}"),
                    "renderIdentityV2Sha256": _sha(f"revised-r1:id2:{index}"),
                    "renderSpec": _spec("revised-r1", index),
                    "renderSpecChecksumSha256": sha256_canonical_json(_spec("revised-r1", index)),
                    "renderedPixelChecksumSha256": _sha(f"revised-r1:px:{index}"),
                }
                for index in every
            ],
            "schemaVersion": "virtual-board-render-manifest-v2-dual-identity-v1",
        }
        revision(
            revised,
            "revised",
            asset_mode="virtual_source",
            source_geometry_revision_id=geometry.id,
            geometry_checksum_sha256="d" * 64,
            virtual_render_spec=revised_spec,
            virtual_render_spec_checksum_sha256=sha256_canonical_json(revised_spec),
            cropper_version=REVISION_EXTRACTOR,
        )
        manual_legacy = board("legacy-revised", 4, every, virtual=False)
        revision(
            manual_legacy,
            "legacy-revised",
            asset_mode="legacy_file",
            board_relative_path="boards/legacy-revised.png",
            board_checksum_sha256=_sha("legacy-revised:board"),
            cropper_version="legacy-cropper-v19",
            crop_artifacts=[
                {
                    "columnIndex": index % 5,
                    "cropChecksumSha256": _sha(f"legacy-revised:px:{index}"),
                    "cropRelativePath": f"crops/legacy-revised/{index}.png",
                    "rowIndex": index // 5,
                }
                for index in every
            ],
        )
        board("legacy-base", 5, every, virtual=False)
        job_record = session.get(JobModel, job.id)
        assert job_record is not None
        job_record.status = JobStatus.WAITING_FOR_REVIEW
        session.commit()
    return _Seed(game.id, boards, items)


def _rows(
    session: Session, seed: _Seed
) -> dict[str, tuple[ImageReviewItemModel, RecognizedBoardModel, SourceImageModel, JobModel]]:
    rows = {}
    for label, item_id in seed.items.items():
        item = session.get(ImageReviewItemModel, item_id)
        assert item is not None
        board = session.get(RecognizedBoardModel, item.recognized_board_id)
        assert board is not None
        source = session.get(SourceImageModel, board.source_image_id)
        assert source is not None
        job = session.get(JobModel, source.import_job_id)
        assert job is not None
        rows[label] = (item, board, source, job)
    return rows


def _observations(session: Session, board_id: UUID) -> list[CellObservationModel]:
    return list(
        session.scalars(
            select(CellObservationModel)
            .where(CellObservationModel.recognized_board_id == board_id)
            .order_by(CellObservationModel.row_index, CellObservationModel.column_index)
        )
    )


def _revision(session: Session, board: RecognizedBoardModel) -> Any:
    if board.geometry_revision == 0:
        return None
    return session.scalar(
        select(ImageBoardGeometryRevisionModel).where(
            ImageBoardGeometryRevisionModel.recognized_board_id == board.id,
            ImageBoardGeometryRevisionModel.revision == board.geometry_revision,
        )
    )


def _old_virtual_records(module: ModuleType, **arguments: object) -> list[tuple[object, ...]]:
    return [dataclasses.astuple(record) for record in module._virtual_records(**arguments)]


def _outcome(call: Callable[[], object]) -> object:
    try:
        return call()
    except Exception as error:  # noqa: BLE001 - the error identity is compared
        return ("raised", type(error).__name__, getattr(error, "code", None))


def test_readers_match_the_observation_readers(database: _Database, old: SimpleNamespace) -> None:
    engine = database.engine
    factory = create_session_factory(engine)
    now = datetime(2026, 10, 1, 12, tzinfo=UTC)
    seed = _seed(factory, now)
    game_id = seed.game_id

    # The real resumable backfill writes the manifests (TASK-0757).
    batches: list[BackfillBatchResult] = []
    run_game(
        cast("sessionmaker[Session]", factory),
        game_id,
        after_board_id=None,
        batch_size=50,
        on_batch=batches.append,
    )
    assert not [board for batch in batches for board in batch.refused]
    totals: dict[str, int] = {}
    for batch in batches:
        for name, value in batch.counts.items():
            totals[name] = totals.get(name, 0) + value
    assert totals["built_revision_zero"] == 3
    assert totals["copied"] == 1
    assert totals["legacy_skipped"] == 2

    with game_storage_scope(game_id), factory() as session:
        rows = _rows(session, seed)
        sources = load_current_board_cell_sources(
            session, ((board, game_id) for _item, board, _source, _job in rows.values())
        )
        legacy = legacy_base_cells(session, [rows["legacy-base"][1].id])
        queue_item = SimpleNamespace(source_order_index=0, position_index=0)
        compared = 0
        for label, (item, board, source, job) in rows.items():
            observations = _observations(session, board.id)
            revision = _revision(session, board)
            overrides: list[list[dict[str, object]] | None] = [None]
            if label == "complete":
                overrides.append(
                    [
                        {
                            "rowIndex": index // 5,
                            "columnIndex": index % 5,
                            **_prediction("override", index),
                        }
                        for index in range(15)
                    ]
                )
            for override in overrides:
                # 1. The central mapper: every ImageReviewCell field.
                old_cells = old.mapper.materialize_current_image_review_cells(
                    item=item,
                    board=board,
                    source=source,
                    queue_item=queue_item,
                    job=job,
                    observations=observations,
                    geometry_revision=revision,
                    prediction_override=override,
                )
                new_cells = new_mapper.materialize_current_image_review_cells(
                    item=item,
                    board=board,
                    source=source,
                    queue_item=queue_item,
                    job=job,
                    cell_sources=sources[board.id],
                    geometry_revision=revision,
                    prediction_override=override,
                )
                assert new_cells == old_cells, label
                assert len(new_cells) == (14 if label in {"trailing", "middle"} else 15)
                compared += 1
            # 2. The symbol-review cropper version of the current crops.
            assert new_symbol_review._current_cropper_version(
                board=board, cell_sources=sources[board.id], geometry=revision
            ) == old.symbol_review._current_cropper_version(
                board=board, observations=observations, geometry=revision
            )
            # 3. The board-search document payload.
            assert new_search._payload_from_records(
                item=item,
                board=board,
                source=source,
                job=job,
                prediction_override=None,
                geometry_revision=revision,
                legacy_base_cells=legacy.get(board.id, ()),
            ) == old.search._payload_from_records(
                item=item,
                board=board,
                source=source,
                job=job,
                observations=observations,
                prediction_override=None,
                geometry_revision=revision,
            )
            # 4. Re-inference render records of virtual boards.
            if board.asset_mode != "virtual_source":
                continue
            expected = new_reinference._available_indices(
                board.geometry_qualification, asset_mode=board.asset_mode
            )
            manifest = load_current_render_manifest(session, game_id=game_id, board=board)
            new_records = [
                dataclasses.astuple(record)
                for record in new_reinference._virtual_records(
                    render_manifest=manifest, expected_indices=expected
                )
            ]
            assert [record[0] for record in new_records] == list(expected)
            old_records = _outcome(
                partial(
                    _old_virtual_records,
                    old.reinference,
                    observations=observations,
                    revised=revision,
                    expected_indices=expected,
                )
            )
            if label == "middle":
                # The auditor's note: the observation path numbered partial
                # revision-0 cells by ordinal and refused a masked middle cell;
                # the manifest carries the real index.
                assert old_records == (
                    "raised",
                    "JobHandlerError",
                    "IMAGE_SYMBOL_REINFERENCE_CELLS_INCOMPLETE",
                )
                assert 7 not in [record[0] for record in new_records]
            else:
                assert new_records == old_records, label
        assert compared == 7

        # The rebuilt search documents and the symbol-review backfill read the
        # switched sources end to end.
        SqlAlchemyBoardSearchProjectionRepository(session).rebuild_game(game_id)
        session.commit()

    with game_storage_scope(game_id), factory() as session:
        backfill = SqlAlchemyImageSymbolReviewRepository(session)
        backfill.start_or_resume_backfill(game_id)
        step = backfill.backfill_next_batch(game_id, batch_size=50)
        while step.has_more:
            step = backfill.backfill_next_batch(game_id, batch_size=50)
        session.commit()

    def stale() -> tuple[set[UUID], set[UUID]]:
        with game_storage_scope(game_id), factory() as session:
            new_ids = set(
                SqlAlchemyImageSymbolReviewRepository(session)._selected_items_with_stale_base_crop(
                    game_id
                )
            )
            old_ids = set(
                old.symbol_review.SqlAlchemyImageSymbolReviewRepository(
                    session
                )._selected_items_with_stale_base_crop(game_id)
            )
        return new_ids, old_ids

    with game_storage_scope(game_id), factory() as session:
        counts = session.execute(
            select(ImageSymbolReviewCellModel.source_available, func.count()).group_by(
                ImageSymbolReviewCellModel.source_available
            )
        ).all()
    # Six boards keep 15 logical positions; the two outside cells have no asset.
    assert dict(counts) == {True: 15 * 4 + 14 * 2, False: 2}
    assert stale() == (set(), set())

    # A review cell whose identity no longer matches its base render is stale
    # for both readers (virtual from the manifest, legacy from the adapter).
    with game_storage_scope(game_id), factory.begin() as session:
        for label, column in (
            ("complete", ImageSymbolReviewCellModel.render_spec_checksum_sha256),
            ("middle", ImageSymbolReviewCellModel.logical_cell_key),
            ("legacy-base", ImageSymbolReviewCellModel.crop_checksum_sha256),
        ):
            session.execute(
                update(ImageSymbolReviewCellModel)
                .where(
                    ImageSymbolReviewCellModel.review_item_id == seed.items[label],
                    ImageSymbolReviewCellModel.cell_index == 3,
                )
                .values({column: "f" * 64})
            )
    expected_stale = {seed.items["complete"], seed.items["middle"], seed.items["legacy-base"]}
    assert stale() == (expected_stale, expected_stale)

    # Rule "no manifest <=> no cells": a revision-0 board with available cells
    # but without a manifest is stale for the new reader (observations do not
    # count any more).
    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM game_data_v2.board_render_manifests "
                "WHERE game_id = :game_id AND recognized_board_id = :board"
            ),
            {"game_id": game_id, "board": seed.boards["trailing"]},
        )
    new_ids, old_ids = stale()
    assert new_ids == expected_stale | {seed.items["trailing"]}
    assert old_ids == expected_stale


def _reset_to_revision(database: _Database, revision: str) -> None:
    """Rebuild the isolated database at ``revision``.

    Migration 0133 (TASK-0790) refuses to downgrade, so a test of an older
    migration's downgrade cannot start from head.
    """

    database.engine.dispose()
    with database.engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA IF EXISTS game_data_v2 CASCADE")
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")
    command.upgrade(database.config, revision)


def test_migration_0132_drops_and_restores_the_reference_observation(database: _Database) -> None:
    """0132 drops ``source_observation_id``; downgrade restores it from the cell."""

    engine = database.engine
    _reset_to_revision(database, "0132_symbol_reference_images_cell_identity")
    factory = create_session_factory(engine)
    seed = _seed(factory, datetime(2026, 10, 1, 12, tzinfo=UTC))
    game_id, board_id = seed.game_id, seed.boards["legacy-base"]

    def observation(cell_index: int) -> UUID:
        with engine.connect() as connection:
            return UUID(
                str(
                    connection.execute(
                        text(
                            "SELECT id FROM game_data_v2.cell_observations "
                            "WHERE game_id = :game AND recognized_board_id = :board "
                            "AND row_index = :row AND column_index = :column"
                        ),
                        {
                            "game": game_id,
                            "board": board_id,
                            "row": cell_index // 5,
                            "column": cell_index % 5,
                        },
                    ).scalar_one()
                )
            )

    def columns() -> set[str]:
        with engine.connect() as connection:
            return set(
                connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = 'game_data_v2' "
                        "AND table_name = 'symbol_reference_images'"
                    )
                ).scalars()
            )

    assert "source_observation_id" not in columns()
    with engine.begin() as connection:
        symbol_id = connection.execute(
            text("SELECT id FROM public.symbols WHERE game_id = :game ORDER BY code LIMIT 1"),
            {"game": game_id},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO game_data_v2.symbol_reference_images (symbol_id, game_id, "
                "source_review_item_id, source_recognized_board_id, sequence_number, "
                "cell_index, resolution_revision, geometry_revision, image_relative_path, "
                "image_checksum_sha256, selected_by) VALUES (:symbol, :game, :item, :board, "
                "6, 8, 0, 0, 'data/symbol-references/x.png', :checksum, 'task-0758-test')"
            ),
            {
                "symbol": symbol_id,
                "game": game_id,
                "item": seed.items["legacy-base"],
                "board": board_id,
                "checksum": "a" * 64,
            },
        )

    command.downgrade(database.config, "0131_board_render_manifests")
    assert "source_observation_id" in columns()
    with engine.connect() as connection:
        restored = connection.execute(
            text("SELECT source_observation_id FROM game_data_v2.symbol_reference_images")
        ).scalar_one()
        constraint = connection.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'v2_fk_657ff3d6c526545fcfa6' "
                "AND conrelid = 'game_data_v2.symbol_reference_images'::regclass"
            )
        ).scalar_one()
    assert UUID(str(restored)) == observation(8)
    assert "REFERENCES game_data_v2.cell_observations(game_id, id)" in constraint

    # The upgrade refuses a reference whose observation is another cell's.
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE game_data_v2.symbol_reference_images SET source_observation_id = :id"),
            {"id": observation(9)},
        )
    with pytest.raises(Exception, match="SYMBOL_REFERENCE_OBSERVATION_MISMATCH"):
        command.upgrade(database.config, "0132_symbol_reference_images_cell_identity")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE game_data_v2.symbol_reference_images SET source_observation_id = :id"),
            {"id": observation(8)},
        )
    command.upgrade(database.config, "0132_symbol_reference_images_cell_identity")
    assert "source_observation_id" not in columns()
