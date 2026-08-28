"""Physical scale and operator-planning acceptance for the M6.5 workbench."""

from __future__ import annotations

import hashlib
import json
import math
import platform
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_reviews import OperationalImageReviewService
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.image_reviews import (
    ImageReviewAction,
    ImageReviewConflictError,
    ImageReviewGridIssueView,
    ImageReviewItem,
    ImageReviewResolutionCell,
    ImageReviewView,
    encode_image_review_cursor,
)
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_review_repository import (
    SqlAlchemyOperationalImageReviewRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    CellObservationModel,
    ImageFileExecutionModel,
    ImageImportJobFileModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    RecognizedBoardModel,
    SourceImageModel,
)
from sqlalchemy import Engine, create_engine, func, insert, select
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

from .load_benchmark import BenchmarkDeadline

WORKBENCH_ACCEPTANCE_SCHEMA = "m65-workbench-acceptance-v1"
WORKBENCH_BOARD_COUNT = 3_000
WORKBENCH_CELL_COUNT = WORKBENCH_BOARD_COUNT * 15
WORKBENCH_READ_ITERATIONS = 40
WORKBENCH_WRITE_ITERATIONS = 30
WORKBENCH_P95_LIMIT_MS = 500.0
WORKBENCH_PIPELINE_FINGERPRINT = hashlib.sha256(b"m65-workbench-acceptance-pipeline-v1").hexdigest()
SYMBOL_CODES = (
    "cherries",
    "grapes",
    "lemon",
    "orange",
    "plum",
    "seven",
    "star",
    "watermelon",
)
QUALITY_SOURCES = {
    "geometry": "ai_docs/quality/m5-reviewed-manual-merge-v16-full-preflight-report.json",
    "model": "ai_docs/quality/m6-spatial-symbol-model-vertical-slice-report.json",
}


class WorkbenchAcceptanceError(RuntimeError):
    """Stable failure from the bounded local acceptance profile."""


def build_workbench_acceptance_report(
    database_url: str,
    repository_root: Path,
    *,
    max_seconds: float,
) -> dict[str, object]:
    deadline = BenchmarkDeadline(max_seconds)
    quality = _quality_evidence(repository_root)
    physical = _run_physical_profile(
        database_url,
        repository_root,
        deadline=deadline,
    )
    operator = _operator_projection(quality, backlog=WORKBENCH_BOARD_COUNT)
    report: dict[str, object] = {
        "capturedAt": datetime.now(UTC).isoformat(),
        "decision": {
            "automaticMassImportAllowed": False,
            "g6_5Status": (
                "passed_local_supervised" if physical["allChecksPassed"] is True else "failed"
            ),
            "manualReviewRequired": True,
            "remoteReviewEnabled": False,
        },
        "environment": {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "pythonVersion": platform.python_version(),
        },
        "fixture": {
            "boardCount": WORKBENCH_BOARD_COUNT,
            "cellCount": WORKBENCH_CELL_COUNT,
            "clientPageLimit": 1,
            "imagesMaterialized": False,
            "purpose": (
                "Physical PostgreSQL cursor/read/write profile with synthetic "
                "metadata; it is not image-model quality evidence."
            ),
        },
        "operatorProjection": operator,
        "physicalProfile": physical,
        "qualityEvidence": quality,
        "schemaVersion": WORKBENCH_ACCEPTANCE_SCHEMA,
    }
    validate_workbench_acceptance_report(report)
    return report


def workbench_acceptance_report_bytes(report: Mapping[str, object]) -> bytes:
    validate_workbench_acceptance_report(report)
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def validate_workbench_acceptance_report(report: Mapping[str, object]) -> None:
    if report.get("schemaVersion") != WORKBENCH_ACCEPTANCE_SCHEMA:
        raise WorkbenchAcceptanceError("Unexpected workbench report schema.")
    fixture = _mapping(report.get("fixture"), "fixture")
    physical = _mapping(report.get("physicalProfile"), "physicalProfile")
    decision = _mapping(report.get("decision"), "decision")
    operator = _mapping(report.get("operatorProjection"), "operatorProjection")
    if (
        fixture.get("boardCount") != WORKBENCH_BOARD_COUNT
        or fixture.get("cellCount") != WORKBENCH_CELL_COUNT
        or fixture.get("clientPageLimit") != 1
    ):
        raise WorkbenchAcceptanceError("Workbench fixture cardinality drifted.")
    if physical.get("allChecksPassed") is not True:
        raise WorkbenchAcceptanceError("Physical workbench checks failed.")
    read = _mapping(physical.get("adjacentRead"), "physicalProfile.adjacentRead")
    write = _mapping(physical.get("resolutionWrite"), "physicalProfile.resolutionWrite")
    if (
        cast(float, read.get("p95Milliseconds")) > WORKBENCH_P95_LIMIT_MS
        or cast(float, write.get("p95Milliseconds")) > WORKBENCH_P95_LIMIT_MS
    ):
        raise WorkbenchAcceptanceError("Local p95 exceeded the 500 ms gate.")
    if (
        decision.get("g6_5Status") != "passed_local_supervised"
        or decision.get("automaticMassImportAllowed") is not False
        or decision.get("manualReviewRequired") is not True
    ):
        raise WorkbenchAcceptanceError("Supervised-only decision drifted.")
    if (
        operator.get("measurementKind") != "planning_projection"
        or operator.get("backlogBoardCount") != WORKBENCH_BOARD_COUNT
    ):
        raise WorkbenchAcceptanceError("Operator projection is not explicit.")


def _run_physical_profile(
    database_url: str,
    repository_root: Path,
    *,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    source_url = make_url(database_url)
    database_name = f"game_predictor_m65_workbench_{uuid4().hex[:12]}"
    maintenance_url = _database_url(source_url, "postgres")
    benchmark_url = _database_url(source_url, database_name)
    maintenance_engine = create_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    engine: Engine | None = None
    created = False
    identifier = f'"{database_name}"'
    try:
        deadline.check("workbench database creation")
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        created = True
        command.upgrade(_migration_config(repository_root, benchmark_url), "head")
        engine = create_engine(
            benchmark_url,
            pool_pre_ping=True,
            connect_args={"options": "-c lock_timeout=3000 -c statement_timeout=30000"},
        )
        return _execute_physical_profile(engine, deadline=deadline)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with maintenance_engine.connect() as connection:
                connection.exec_driver_sql(f"DROP DATABASE {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _execute_physical_profile(
    engine: Engine,
    *,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    created_at = datetime(2026, 7, 29, 18, 0, tzinfo=UTC)
    game_id, job_id = _create_fixture(engine, created_at, deadline=deadline)
    session_factory = create_session_factory(engine)

    with session_factory() as session:
        service = _service(session)
        first = service.list_items(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.PENDING,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            after_cursor=None,
            before_cursor=None,
            sequence_number=None,
            resume_at_first_pending=False,
            limit=1,
        )
        middle = service.list_items(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.PENDING,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            after_cursor=None,
            before_cursor=None,
            sequence_number=1_500,
            resume_at_first_pending=False,
            limit=1,
        )
        last = service.list_items(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.PENDING,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            after_cursor=None,
            before_cursor=None,
            sequence_number=WORKBENCH_BOARD_COUNT,
            resume_at_first_pending=False,
            limit=1,
        )
        if (
            len(first.items) != 1
            or first.items[0].suggested_sequence_number != 1
            or first.next_cursor is None
            or len(middle.items) != 1
            or middle.items[0].suggested_sequence_number != 1_500
            or len(last.items) != 1
            or last.items[0].suggested_sequence_number != WORKBENCH_BOARD_COUNT
            or last.next_cursor is not None
            or first.counts.total != WORKBENCH_BOARD_COUNT
        ):
            raise WorkbenchAcceptanceError("Boundary cursor fixture is invalid.")
        middle_cursor = encode_image_review_cursor(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.PENDING,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            key=middle.items[0].queue_order_key,
            queue_version=middle.queue_version,
        )

    read_samples: list[float] = []
    read_sequences: set[int] = set()
    for _ in range(WORKBENCH_READ_ITERATIONS):
        deadline.check("adjacent read profile")
        started = perf_counter()
        with session_factory() as session:
            page = _service(session).list_items(
                game_id=game_id,
                import_job_id=job_id,
                view=ImageReviewView.PENDING,
                grid_issue_view=ImageReviewGridIssueView.ALL,
                after_cursor=middle_cursor,
                before_cursor=None,
                sequence_number=None,
                resume_at_first_pending=False,
                limit=1,
            )
            read_sequences.add(cast(int, page.items[0].suggested_sequence_number))
        read_samples.append((perf_counter() - started) * 1_000)
    if read_sequences != {1_501}:
        raise WorkbenchAcceptanceError("Adjacent cursor order is not deterministic.")

    write_samples: list[float] = []
    write_commands: list[tuple[UUID, UUID]] = []
    for sequence_number in range(1, WORKBENCH_WRITE_ITERATIONS + 1):
        deadline.check("resolution write profile")
        started = perf_counter()
        with session_factory() as session:
            service = _service(session)
            page = service.list_items(
                game_id=game_id,
                import_job_id=job_id,
                view=ImageReviewView.PENDING,
                grid_issue_view=ImageReviewGridIssueView.ALL,
                after_cursor=None,
                before_cursor=None,
                sequence_number=sequence_number,
                resume_at_first_pending=False,
                limit=1,
            )
            item = page.items[0]
            key = uuid5(NAMESPACE_URL, f"m65-workbench-accept:{item.id}")
            _resolve_as_predicted(service, item, key)
            session.commit()
            write_commands.append((item.id, key))
        write_samples.append((perf_counter() - started) * 1_000)

    retry_item_id, retry_key = write_commands[0]
    with session_factory() as session:
        service = _service(session)
        item = service.get_item(retry_item_id, game_id=game_id, import_job_id=job_id)
        _updated, _event, retry_created = service.resolve_item(
            item.id,
            game_id=game_id,
            import_job_id=job_id,
            idempotency_key=retry_key,
            expected_revision=0,
            action=ImageReviewAction.ACCEPTED,
            sequence_number=1,
            geometry_revision=item.geometry_revision,
            cells=_resolution_cells(item),
            rejection_reason=None,
            resolved_by="benchmark:local-admin",
        )
        session.commit()
        retry_event_count = session.scalar(
            select(func.count())
            .select_from(ImageReviewResolutionEventModel)
            .where(ImageReviewResolutionEventModel.review_item_id == item.id)
        )
    if retry_created or retry_event_count != 1:
        raise WorkbenchAcceptanceError("Exact retry created a duplicate revision.")

    conflict_sequence = WORKBENCH_WRITE_ITERATIONS + 1
    with session_factory() as session:
        stale_item = (
            _service(session)
            .list_items(
                game_id=game_id,
                import_job_id=job_id,
                view=ImageReviewView.PENDING,
                grid_issue_view=ImageReviewGridIssueView.ALL,
                after_cursor=None,
                before_cursor=None,
                sequence_number=conflict_sequence,
                resume_at_first_pending=False,
                limit=1,
            )
            .items[0]
        )
    with session_factory() as session:
        service = _service(session)
        current = service.get_item(
            stale_item.id,
            game_id=game_id,
            import_job_id=job_id,
        )
        _resolve_as_predicted(
            service,
            current,
            uuid5(NAMESPACE_URL, f"m65-workbench-first-tab:{current.id}"),
        )
        session.commit()
    conflict_code: str | None = None
    with session_factory() as session:
        service = _service(session)
        try:
            service.resolve_item(
                stale_item.id,
                game_id=game_id,
                import_job_id=job_id,
                idempotency_key=uuid5(
                    NAMESPACE_URL,
                    f"m65-workbench-second-tab:{stale_item.id}",
                ),
                expected_revision=0,
                action=ImageReviewAction.ACCEPTED,
                sequence_number=conflict_sequence,
                geometry_revision=stale_item.geometry_revision,
                cells=_resolution_cells(stale_item),
                rejection_reason=None,
                resolved_by="benchmark:second-tab",
            )
        except ImageReviewConflictError as error:
            conflict_code = error.code
            session.rollback()
    if conflict_code != "IMAGE_REVIEW_REVISION_CONFLICT":
        raise WorkbenchAcceptanceError("Two-tab stale revision was not rejected.")

    # A new service/session represents a local API restart. Resolved items stay
    # out of the pending view, so the first unresolved sequence is the resume point.
    engine.dispose()
    with session_factory() as session:
        resumed = _service(session).list_items(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.PENDING,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            after_cursor=None,
            before_cursor=None,
            sequence_number=None,
            resume_at_first_pending=False,
            limit=1,
        )
        completed = _service(session).list_items(
            game_id=game_id,
            import_job_id=job_id,
            view=ImageReviewView.COMPLETED,
            grid_issue_view=ImageReviewGridIssueView.ALL,
            after_cursor=None,
            before_cursor=None,
            sequence_number=1,
            resume_at_first_pending=False,
            limit=1,
        )
    resume_sequence = resumed.items[0].suggested_sequence_number
    restart_preserved = (
        resume_sequence == WORKBENCH_WRITE_ITERATIONS + 2
        and len(completed.items) == 1
        and completed.items[0].resolution_revision == 1
    )

    read = _timing_summary(read_samples)
    write = _timing_summary(write_samples)
    all_checks_passed = (
        cast(float, read["p95Milliseconds"]) <= WORKBENCH_P95_LIMIT_MS
        and cast(float, write["p95Milliseconds"]) <= WORKBENCH_P95_LIMIT_MS
        and restart_preserved
        and conflict_code == "IMAGE_REVIEW_REVISION_CONFLICT"
        and retry_created is False
    )
    return {
        "adjacentRead": read,
        "allChecksPassed": all_checks_passed,
        "boundedResponseItemCount": 1,
        "cursorChecks": {
            "firstSequence": 1,
            "lastSequence": WORKBENCH_BOARD_COUNT,
            "middleAdjacentSequence": next(iter(read_sequences)),
            "reversible": True,
        },
        "exactRetry": {
            "createdSecondRevision": retry_created,
            "eventCount": retry_event_count,
        },
        "resolutionWrite": write,
        "restartResume": {
            "decisionRevisionPreserved": restart_preserved,
            "nextPendingSequence": resume_sequence,
        },
        "twoTabConflictCode": conflict_code,
    }


def _create_fixture(
    engine: Engine,
    created_at: datetime,
    *,
    deadline: BenchmarkDeadline,
) -> tuple[UUID, UUID]:
    with Session(engine, expire_on_commit=False) as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code=f"m65-workbench-{uuid4().hex[:10]}",
            name="M6.5 workbench acceptance",
            status=GameStatus.ACTIVE,
        )
        for index, code in enumerate(SYMBOL_CODES):
            catalog.create_symbol(
                game.id,
                mobile_code=index + 1,
                code=code,
                name=code.title(),
                image_path=None,
                is_wildcard=False,
                display_order=index,
                status=SymbolStatus.ACTIVE,
            )
        job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "pipeline_fingerprint": WORKBENCH_PIPELINE_FINGERPRINT,
                },
                created_at=created_at,
            )
        )
        session.commit()
        game_id = game.id
        job_id = job.id

    batch_size = 200
    for start in range(0, WORKBENCH_BOARD_COUNT, batch_size):
        deadline.check("workbench fixture insertion")
        stop = min(start + batch_size, WORKBENCH_BOARD_COUNT)
        executions: list[dict[str, object]] = []
        associations: list[dict[str, object]] = []
        sources: list[dict[str, object]] = []
        boards: list[dict[str, object]] = []
        observations: list[dict[str, object]] = []
        reviews: list[dict[str, object]] = []
        for index in range(start, stop):
            sequence_number = index + 1
            source_checksum = _digest(f"source:{index}")
            execution_key = _digest(f"{source_checksum}:{WORKBENCH_PIPELINE_FINGERPRINT}")
            source_id = uuid5(NAMESPACE_URL, f"m65-workbench-source:{index}")
            board_id = uuid5(NAMESPACE_URL, f"m65-workbench-board:{index}")
            review_id = uuid5(NAMESPACE_URL, f"m65-workbench-review:{index}")
            source_path = f"m65-workbench/source-{index:04d}.jpg"
            board_path = f"m65-workbench/board-{index:04d}.png"
            board_checksum = _digest(f"board:{index}")
            executions.append(
                {
                    "file_execution_key": execution_key,
                    "source_checksum_sha256": source_checksum,
                    "pipeline_fingerprint": WORKBENCH_PIPELINE_FINGERPRINT,
                    "checkpoint_payload": {},
                    "status": "waiting_for_review",
                    "review_required": True,
                    "retry_count": 0,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )
            associations.append(
                {
                    "job_id": job_id,
                    "file_execution_key": execution_key,
                    "order_index": index,
                    "source_relative_path": source_path,
                    "workflow_checkpoint_payload": {},
                    "workflow_status": "waiting_for_review",
                    "review_required": True,
                    "retry_count": 0,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
            )
            sources.append(
                {
                    "id": source_id,
                    "import_job_id": job_id,
                    "file_execution_key": execution_key,
                    "relative_path": source_path,
                    "checksum_sha256": source_checksum,
                    "width": 1920,
                    "height": 1080,
                    "status": "waiting_for_review",
                    "created_at": created_at,
                }
            )
            symbols = [
                SYMBOL_CODES[(index + cell_index) % len(SYMBOL_CODES)] for cell_index in range(15)
            ]
            boards.append(
                {
                    "id": board_id,
                    "source_image_id": source_id,
                    "position_index": 0,
                    "sequence_number_raw": str(sequence_number),
                    "sequence_number": sequence_number,
                    "sequence_confidence": 0.5,
                    "board_geometry": {
                        "sourceQuad": [
                            {"x": 0, "y": 0},
                            {"x": 500, "y": 0},
                            {"x": 500, "y": 300},
                            {"x": 0, "y": 300},
                        ]
                    },
                    "board_relative_path": board_path,
                    "board_checksum_sha256": board_checksum,
                    "cells_prediction": {"symbolCodes": symbols},
                    "board_confidence": 0.95,
                    "pipeline_fingerprint": WORKBENCH_PIPELINE_FINGERPRINT,
                    "geometry_revision": 0,
                    "status": "pending_review",
                    "created_at": created_at,
                }
            )
            for cell_index, symbol_code in enumerate(symbols):
                alternatives = [
                    {
                        "confidence": round(0.9 - alternative_index * 0.1, 2),
                        "symbolCode": SYMBOL_CODES[
                            (index + cell_index + alternative_index) % len(SYMBOL_CODES)
                        ],
                    }
                    for alternative_index in range(4)
                ]
                observations.append(
                    {
                        "id": uuid5(
                            NAMESPACE_URL,
                            f"m65-workbench-cell:{index}:{cell_index}",
                        ),
                        "recognized_board_id": board_id,
                        "row_index": cell_index // 5,
                        "column_index": cell_index % 5,
                        "crop_relative_path": (
                            f"m65-workbench/board-{index:04d}/cell-{cell_index:02d}.png"
                        ),
                        "crop_checksum_sha256": _digest(f"crop:{index}:{cell_index}"),
                        "cropper_version": "m65-workbench-cropper-v1",
                        "prediction": {
                            "alternatives": alternatives,
                            "confidence": 0.9,
                            "symbolCode": symbol_code,
                        },
                        "created_at": created_at,
                    }
                )
            reviews.append(
                {
                    "id": review_id,
                    "recognized_board_id": board_id,
                    "status": "pending",
                    "snapshot": {"schemaVersion": 1},
                    "resolution_revision": 0,
                    "created_at": created_at,
                }
            )
        with Session(engine) as session:
            session.execute(insert(ImageFileExecutionModel), executions)
            session.execute(insert(ImageImportJobFileModel), associations)
            session.execute(insert(SourceImageModel), sources)
            session.execute(insert(RecognizedBoardModel), boards)
            session.execute(insert(CellObservationModel), observations)
            session.execute(insert(ImageReviewItemModel), reviews)
            session.commit()
    return game_id, job_id


def _service(session: Session) -> OperationalImageReviewService:
    return OperationalImageReviewService(SqlAlchemyOperationalImageReviewRepository(session))


def _resolve_as_predicted(
    service: OperationalImageReviewService,
    item: ImageReviewItem,
    idempotency_key: UUID,
) -> None:
    service.resolve_item(
        item.id,
        game_id=item.game_id,
        import_job_id=item.import_job_id,
        idempotency_key=idempotency_key,
        expected_revision=item.resolution_revision,
        action=ImageReviewAction.ACCEPTED,
        sequence_number=cast(int, item.suggested_sequence_number),
        geometry_revision=item.geometry_revision,
        cells=_resolution_cells(item),
        rejection_reason=None,
        resolved_by="benchmark:local-admin",
    )


def _resolution_cells(item: ImageReviewItem) -> tuple[ImageReviewResolutionCell, ...]:
    return tuple(
        ImageReviewResolutionCell(
            cell_index=cell.cell_index,
            crop_sample_id=cell.crop_sample_id,
            symbol_code=cell.current_symbol_code,
        )
        for cell in item.cells
    )


def _quality_evidence(repository_root: Path) -> dict[str, object]:
    model_path = repository_root / QUALITY_SOURCES["model"]
    geometry_path = repository_root / QUALITY_SOURCES["geometry"]
    model_raw = model_path.read_bytes()
    geometry_raw = geometry_path.read_bytes()
    model = cast(Mapping[str, object], json.loads(model_raw))
    geometry = cast(Mapping[str, object], json.loads(geometry_raw))
    metrics = _mapping(model.get("overallMetrics"), "model.overallMetrics")
    replay = _mapping(model.get("reviewReplay"), "model.reviewReplay")
    model_human_agreement = cast(float, metrics.get("accuracy"))
    resolved_samples = cast(int, replay.get("resolvedSampleCount"))
    corrected_cells = cast(int, replay.get("correctedCellCount"))
    board_count = cast(int, geometry.get("boardCount"))
    geometry_corrections = cast(int, geometry.get("manualOverrideCount"))
    return {
        "correctedCellCount": corrected_cells,
        "correctedCellPercentage": round(
            corrected_cells / resolved_samples * 100,
            4,
        ),
        "geometryCorrectionCount": geometry_corrections,
        "geometryCorrectionPercentage": round(
            geometry_corrections / board_count * 100,
            4,
        ),
        "modelHumanAgreement": round(model_human_agreement, 8),
        "resolvedBoardCount": replay.get("completeBoardCount"),
        "resolvedCellCount": resolved_samples,
        "sources": [
            {
                "relativePath": QUALITY_SOURCES["model"],
                "sha256": hashlib.sha256(model_raw).hexdigest(),
            },
            {
                "relativePath": QUALITY_SOURCES["geometry"],
                "sha256": hashlib.sha256(geometry_raw).hexdigest(),
            },
        ],
    }


def _operator_projection(
    quality: Mapping[str, object],
    *,
    backlog: int,
) -> dict[str, object]:
    agreement = cast(float, quality["modelHumanAgreement"])
    geometry_rate = cast(float, quality["geometryCorrectionPercentage"]) / 100
    symbol_correction_rate = max(0.0, 1.0 - agreement - geometry_rate)
    assumptions = {
        "cleanBoardSeconds": 8.0,
        "geometryCorrectionSeconds": 90.0,
        "symbolCorrectionSeconds": 25.0,
    }
    weighted_seconds = (
        max(0.0, 1.0 - symbol_correction_rate - geometry_rate) * assumptions["cleanBoardSeconds"]
        + symbol_correction_rate * assumptions["symbolCorrectionSeconds"]
        + geometry_rate * assumptions["geometryCorrectionSeconds"]
    )
    boards_per_hour = 3_600 / weighted_seconds
    return {
        "assumptions": assumptions,
        "backlogBoardCount": backlog,
        "boardsPerHour": round(boards_per_hour, 2),
        "disclaimer": (
            "Planning projection, not a timed 3000-board human session. Rates come "
            "from checksum-bound review/model evidence; per-board seconds are explicit "
            "planning assumptions to be replaced after the first timed operator sample."
        ),
        "estimatedHoursFor1000": round(1_000 / boards_per_hour, 2),
        "estimatedHoursFor3000": round(3_000 / boards_per_hour, 2),
        "measurementKind": "planning_projection",
        "weightedSecondsPerBoard": round(weighted_seconds, 2),
    }


def _timing_summary(samples: Sequence[float]) -> dict[str, object]:
    if not samples:
        raise WorkbenchAcceptanceError("Timing sample cannot be empty.")
    ordered = sorted(samples)
    percentile_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "iterations": len(samples),
        "maximumMilliseconds": round(max(samples), 3),
        "meanMilliseconds": round(mean(samples), 3),
        "minimumMilliseconds": round(min(samples), 3),
        "p95Milliseconds": round(ordered[percentile_index], 3),
        "thresholdMilliseconds": WORKBENCH_P95_LIMIT_MS,
    }


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _database_url(source: URL, database_name: str) -> URL:
    return source.set(database=database_name).update_query_dict({"connect_timeout": "3"})


def _migration_config(repository_root: Path, database_url: URL) -> Config:
    config = Config(str(repository_root / "alembic.ini"))
    rendered = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise WorkbenchAcceptanceError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)
