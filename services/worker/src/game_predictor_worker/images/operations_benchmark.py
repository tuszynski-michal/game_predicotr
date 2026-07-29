"""Physical M7 image-import recovery and review operations benchmark."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter, process_time
from typing import Never, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.domain.catalog import GameStatus, SymbolStatus
from game_predictor_api.domain.jobs import Job, JobType, create_job
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.models import (
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    RecognizedBoardModel,
)
from sqlalchemy import create_engine, select
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session

from game_predictor_worker.benchmarks.performance import PeakMemorySampler
from game_predictor_worker.jobs.runtime import JobExecutionContext
from game_predictor_worker.jobs.store import SqlAlchemyWorkerJobStore

from .load_benchmark import (
    BenchmarkDeadline,
    OperationMeasurement,
)
from .orchestration import (
    ImageBatchHandler,
    ImageBatchStats,
    ImageFileRegistration,
)
from .orchestration_store import SqlAlchemyImageBatchStore
from .pipeline_contract import PIPELINE_STAGES
from .pipeline_execution import (
    FunctionImageStageAdapter,
    ImagePipelineStageExecutor,
    ImageStageContext,
    VersionedImageStageAdapter,
)
from .pipeline_store import SqlAlchemyImagePipelineStore

OPERATIONS_BENCHMARK_SCHEMA = "m7-import-operations-benchmark-v1"
OPERATIONS_PIPELINE_FINGERPRINT = hashlib.sha256(b"m7-operations-benchmark-pipeline-v1").hexdigest()
SOURCE_FILE_COUNT = 43
BOARDS_PER_SOURCE = 9
BOARD_COUNT = SOURCE_FILE_COUNT * BOARDS_PER_SOURCE
CELLS_PER_BOARD = 15
CELL_COUNT = BOARD_COUNT * CELLS_PER_BOARD
QUALITY_REPORT_PATHS = {
    "m5Image": "ai_docs/quality/m5-image-benchmark-report.json",
    "m6VerticalSlice": ("ai_docs/quality/m6-classifier-review-vertical-slice-report.json"),
}
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
AUTOMATED_STAGES = PIPELINE_STAGES[:6]


class ImageOperationsBenchmarkError(RuntimeError):
    """Stable local benchmark failure."""


class _BenchmarkWait(BaseException):
    pass


class _BenchmarkCrash(BaseException):
    pass


@dataclass
class _BenchmarkContext:
    lease_token: UUID
    timestamp: datetime
    crash_after_checkpoint: int | None = None
    checkpoint_count: int = 0
    waiting: bool = False

    def now(self) -> datetime:
        return self.timestamp

    def checkpoint(self, **_values: object) -> None:
        self.checkpoint_count += 1
        if self.checkpoint_count == self.crash_after_checkpoint:
            raise _BenchmarkCrash

    def wait_for_review(self) -> Never:
        self.waiting = True
        raise _BenchmarkWait


class _SyntheticAdapterSuite:
    """Valid deterministic payloads with one controlled failure per stage."""

    def __init__(self, failure_sources: Mapping[str, str]) -> None:
        self._failure_sources = dict(failure_sources)
        self._failed: set[tuple[str, str]] = set()
        self.calls: Counter[tuple[str, str]] = Counter()

    def adapters(self) -> list[VersionedImageStageAdapter]:
        return cast(
            list[VersionedImageStageAdapter],
            [
                FunctionImageStageAdapter(
                    stage=stage,
                    version=f"m7-operations-{stage}-v1",
                    runner=self._runner(stage),
                )
                for stage in AUTOMATED_STAGES
            ],
        )

    def _runner(
        self,
        stage: str,
    ) -> Callable[[ImageStageContext], Mapping[str, object]]:
        def run(context: ImageStageContext) -> Mapping[str, object]:
            return self._execute(stage, context)

        return run

    def _execute(
        self,
        stage: str,
        context: ImageStageContext,
    ) -> Mapping[str, object]:
        key = (context.source_checksum_sha256, stage)
        self.calls[key] += 1
        if (
            self._failure_sources.get(context.source_checksum_sha256) == stage
            and key not in self._failed
        ):
            self._failed.add(key)
            raise RuntimeError("controlled operational benchmark failure")
        source_index = _source_index(context.source_relative_path)
        return _stage_payload(stage, context, source_index)


def build_operations_report(
    database_url: str,
    repository_root: Path,
    *,
    max_seconds: float,
) -> dict[str, object]:
    deadline = BenchmarkDeadline(max_seconds)
    quality = _quality_evidence(repository_root)
    operations = _run_physical_operations(
        database_url,
        repository_root,
        deadline=deadline,
    )
    report: dict[str, object] = {
        "capturedAt": datetime.now(UTC).isoformat(),
        "decision": {
            "additionalQueueRequired": False,
            "autoAcceptEnabled": quality["autoAcceptEnabled"],
            "g7_4Status": (
                "passed_manual_review_only" if operations["allChecksPassed"] else "failed"
            ),
            "massImportAllowed": quality["massImportAllowed"],
            "nextAction": (
                "collect_review_feedback_and_retrain"
                if not quality["massImportAllowed"]
                else "proceed_to_publication_validation"
            ),
        },
        "operationalFixture": {
            "boardsPerSource": BOARDS_PER_SOURCE,
            "cellCount": CELL_COUNT,
            "purpose": (
                "PostgreSQL orchestration, recovery and review persistence only; "
                "synthetic predictions are not ML quality evidence."
            ),
            "sourceFileCount": SOURCE_FILE_COUNT,
            "totalBoardCount": BOARD_COUNT,
        },
        "operations": operations,
        "qualityEvidence": quality,
        "schemaVersion": OPERATIONS_BENCHMARK_SCHEMA,
    }
    validate_operations_report(report)
    return report


def operations_report_bytes(report: Mapping[str, object]) -> bytes:
    validate_operations_report(report)
    return (
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


def validate_operations_report(report: Mapping[str, object]) -> None:
    if report.get("schemaVersion") != OPERATIONS_BENCHMARK_SCHEMA:
        raise ImageOperationsBenchmarkError("Unexpected operations report schema.")
    fixture = _mapping(report.get("operationalFixture"), "operationalFixture")
    operations = _mapping(report.get("operations"), "operations")
    quality = _mapping(report.get("qualityEvidence"), "qualityEvidence")
    decision = _mapping(report.get("decision"), "decision")
    if (
        fixture.get("sourceFileCount") != SOURCE_FILE_COUNT
        or fixture.get("totalBoardCount") != BOARD_COUNT
        or fixture.get("cellCount") != CELL_COUNT
    ):
        raise ImageOperationsBenchmarkError("Operational cardinality drifted.")
    if operations.get("allChecksPassed") is not True:
        raise ImageOperationsBenchmarkError("Operational recovery checks failed.")
    if (
        operations.get("stagingLayoutCount") != BOARD_COUNT
        or operations.get("stagingCellCount") != CELL_COUNT
        or operations.get("reviewDecisionCount") != BOARD_COUNT
    ):
        raise ImageOperationsBenchmarkError("Review or staging cardinality drifted.")
    if quality.get("massImportAllowed") is not False:
        raise ImageOperationsBenchmarkError("Current M6 evidence unexpectedly allows mass import.")
    if (
        decision.get("massImportAllowed") is not False
        or decision.get("autoAcceptEnabled") is not False
    ):
        raise ImageOperationsBenchmarkError("Quality decision was weakened.")
    for value in _all_strings(report):
        lowered = value.lower()
        if "postgresql://" in lowered or "postgresql+psycopg://" in lowered:
            raise ImageOperationsBenchmarkError("Report exposes a database URL.")
        if len(value) >= 3 and value[0].isalpha() and value[1:3] in {":\\", ":/"}:
            raise ImageOperationsBenchmarkError("Report exposes an absolute path.")


def _run_physical_operations(
    database_url: str,
    repository_root: Path,
    *,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    source_url = make_url(database_url)
    database_name = f"game_predictor_m7_operations_{uuid4().hex[:12]}"
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
        deadline.check("operations database creation")
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        created = True
        command.upgrade(_migration_config(repository_root, benchmark_url), "head")
        engine = create_engine(
            benchmark_url,
            pool_pre_ping=True,
            connect_args={
                "options": "-c lock_timeout=3000 -c statement_timeout=30000",
            },
        )
        return _execute_operations(engine, deadline=deadline)
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with maintenance_engine.connect() as connection:
                connection.exec_driver_sql(f"DROP DATABASE {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def _execute_operations(
    engine: Engine,
    *,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    session_factory = create_session_factory(engine)
    batch_store = SqlAlchemyImageBatchStore(session_factory)
    pipeline_store = SqlAlchemyImagePipelineStore(session_factory)
    worker_store = SqlAlchemyWorkerJobStore(session_factory)
    now = datetime(2026, 7, 29, 14, 0, tzinfo=UTC)
    job = _create_job_and_catalog(engine, now)
    claimed = worker_store.claim_next(
        worker_id="m7-operations-benchmark",
        worker_version="worker-v5",
        lease_duration=timedelta(days=1),
        claimed_at=now,
    )
    if claimed is None or claimed.id != job.id or claimed.lease_token is None:
        raise ImageOperationsBenchmarkError("Benchmark image job was not claimed.")
    lease_token = claimed.lease_token

    registrations = [
        ImageFileRegistration(
            source_checksum_sha256=_source_checksum(index),
            source_relative_path=f"synthetic/page-{index:03d}.jpg",
            order_index=index,
        )
        for index in range(SOURCE_FILE_COUNT)
    ]
    batch_store.register_files(
        claimed.id,
        registrations=registrations,
        pipeline_fingerprint=OPERATIONS_PIPELINE_FINGERPRINT,
        registered_at=now,
    )
    failure_sources = {
        _source_checksum(index + 1): stage for index, stage in enumerate(AUTOMATED_STAGES)
    }
    adapters = _SyntheticAdapterSuite(failure_sources)
    handler = ImageBatchHandler(
        batch_store,
        ImagePipelineStageExecutor(pipeline_store, adapters.adapters()),
    )

    crash_context = _BenchmarkContext(
        lease_token=lease_token,
        timestamp=now + timedelta(seconds=1),
        crash_after_checkpoint=1,
    )
    try:
        handler(cast(JobExecutionContext, crash_context), claimed)
    except _BenchmarkCrash:
        pass
    else:
        raise ImageOperationsBenchmarkError("Controlled checkpoint crash did not occur.")
    first_discovery_calls = adapters.calls[(_source_checksum(0), "discovery")]

    automated = _measure_operation(
        lambda: _run_until_review(
            handler,
            claimed,
            _BenchmarkContext(
                lease_token=lease_token,
                timestamp=now + timedelta(seconds=2),
            ),
        ),
        SOURCE_FILE_COUNT,
    )
    before_retry = batch_store.batch_stats(
        claimed.id,
        pipeline_fingerprint=OPERATIONS_PIPELINE_FINGERPRINT,
    )
    if before_retry.failed != len(AUTOMATED_STAGES):
        raise ImageOperationsBenchmarkError("Controlled stage failures were not isolated.")

    for source_checksum, stage in failure_sources.items():
        execution_key = hashlib.sha256(
            (
                "image-file-execution-v1\0"
                + source_checksum
                + "\0"
                + OPERATIONS_PIPELINE_FINGERPRINT
            ).encode()
        ).hexdigest()
        batch_store.retry_file(
            claimed.id,
            file_execution_key=execution_key,
            expected_stage=stage,
            retried_at=now + timedelta(seconds=3),
        )

    recovery = _measure_operation(
        lambda: _run_until_review(
            handler,
            claimed,
            _BenchmarkContext(
                lease_token=lease_token,
                timestamp=now + timedelta(seconds=4),
            ),
        ),
        len(AUTOMATED_STAGES),
    )
    after_retry = batch_store.batch_stats(
        claimed.id,
        pipeline_fingerprint=OPERATIONS_PIPELINE_FINGERPRINT,
    )
    if after_retry.failed or after_retry.waiting != SOURCE_FILE_COUNT:
        raise ImageOperationsBenchmarkError("Retry did not reach the review boundary.")

    deadline.check("review resolution")
    reviews = _review_rows(engine)
    if len(reviews) != BOARD_COUNT:
        raise ImageOperationsBenchmarkError("Unexpected pending review cardinality.")
    review_started = perf_counter()
    review_cpu_started = process_time()
    with PeakMemorySampler() as memory_sampler:
        for index, (review_id, revision, sequence_number, symbols) in enumerate(reviews):
            if index % 25 == 0:
                deadline.check("review resolution")
            pipeline_store.resolve_board(
                review_id,
                expected_revision=revision,
                action="accepted",
                sequence_number=sequence_number,
                symbol_codes=symbols,
                resolved_by="benchmark:local-admin",
                resolved_at=now + timedelta(seconds=5),
                idempotency_key=uuid5(
                    NAMESPACE_URL,
                    f"m7-operations-review:{review_id}",
                ),
            )
    review_elapsed = perf_counter() - review_started
    review_measurement = OperationMeasurement(
        elapsed_seconds=review_elapsed,
        cpu_seconds=process_time() - review_cpu_started,
        throughput_per_second=BOARD_COUNT / review_elapsed,
        memory=memory_sampler.summary().to_dict(),
    )

    completion = _measure_operation(
        lambda: handler(
            cast(
                JobExecutionContext,
                _BenchmarkContext(
                    lease_token=lease_token,
                    timestamp=now + timedelta(seconds=6),
                ),
            ),
            claimed,
        ),
        SOURCE_FILE_COUNT,
    )
    final_stats = batch_store.batch_stats(
        claimed.id,
        pipeline_fingerprint=OPERATIONS_PIPELINE_FINGERPRINT,
    )
    staging_count, staging_cell_count = _staging_cardinality(engine)
    retry_stages_exact = all(
        adapters.calls[(source_checksum, stage)] == 2
        and all(
            adapters.calls[(source_checksum, previous)] == 1
            for previous in AUTOMATED_STAGES[: AUTOMATED_STAGES.index(stage)]
        )
        for source_checksum, stage in failure_sources.items()
    )
    all_checks_passed = (
        first_discovery_calls == 1
        and retry_stages_exact
        and before_retry.failed == len(AUTOMATED_STAGES)
        and before_retry.waiting == SOURCE_FILE_COUNT - len(AUTOMATED_STAGES)
        and final_stats
        == ImageBatchStats(
            total=SOURCE_FILE_COUNT,
            current=SOURCE_FILE_COUNT,
            succeeded=SOURCE_FILE_COUNT,
            failed=0,
            review=SOURCE_FILE_COUNT,
            waiting=0,
        )
        and staging_count == BOARD_COUNT
        and staging_cell_count == CELL_COUNT
    )
    return {
        "allChecksPassed": all_checks_passed,
        "automatedPass": automated.to_dict(),
        "checkpointCrashCount": 1,
        "failedStageCount": before_retry.failed,
        "failureStages": list(AUTOMATED_STAGES),
        "finalStats": _stats_dict(final_stats),
        "recoveryPass": recovery.to_dict(),
        "restartRepeatedCompletedStage": first_discovery_calls != 1,
        "retryStartedAtExactStage": retry_stages_exact,
        "reviewDecisionCount": len(reviews),
        "reviewPersistence": review_measurement.to_dict(),
        "stagingCellCount": staging_cell_count,
        "stagingLayoutCount": staging_count,
        "stagingPass": completion.to_dict(),
    }


def _run_until_review(
    handler: ImageBatchHandler,
    job: Job,
    context: _BenchmarkContext,
) -> None:
    try:
        handler(cast(JobExecutionContext, context), job)
    except _BenchmarkWait:
        return
    raise ImageOperationsBenchmarkError("Pipeline did not stop at review.")


def _measure_operation(
    runner: Callable[[], None],
    item_count: int,
) -> OperationMeasurement:
    started = perf_counter()
    cpu_started = process_time()
    with PeakMemorySampler() as memory_sampler:
        runner()
    elapsed = perf_counter() - started
    return OperationMeasurement(
        elapsed_seconds=elapsed,
        cpu_seconds=process_time() - cpu_started,
        throughput_per_second=item_count / elapsed,
        memory=memory_sampler.summary().to_dict(),
    )


def _create_job_and_catalog(engine: Engine, now: datetime) -> Job:
    with Session(engine, expire_on_commit=False) as session:
        catalog = CatalogService(SqlAlchemyCatalogRepository(session))
        game = catalog.create_game(
            code=f"m7-operations-{uuid4().hex[:10]}",
            name="M7 operations benchmark",
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
                    "pipeline_fingerprint": OPERATIONS_PIPELINE_FINGERPRINT,
                },
                created_at=now,
            )
        )
        session.commit()
        return job


def _review_rows(
    engine: Engine,
) -> list[tuple[UUID, int, int, list[str]]]:
    with Session(engine) as session:
        rows = session.execute(
            select(ImageReviewItemModel, RecognizedBoardModel)
            .join(
                RecognizedBoardModel,
                RecognizedBoardModel.id == ImageReviewItemModel.recognized_board_id,
            )
            .where(ImageReviewItemModel.status == "pending")
            .order_by(RecognizedBoardModel.sequence_number)
        ).all()
        result: list[tuple[UUID, int, int, list[str]]] = []
        for review, board in rows:
            sequence_number = board.sequence_number
            if sequence_number is None:
                raise ImageOperationsBenchmarkError("Fixture sequence is missing.")
            cells = cast(Sequence[object], board.cells_prediction["cells"])
            symbols = [cast(str, cast(Mapping[str, object], cell)["symbolCode"]) for cell in cells]
            result.append(
                (
                    review.id,
                    review.resolution_revision,
                    sequence_number,
                    symbols,
                )
            )
        return result


def _staging_cardinality(engine: Engine) -> tuple[int, int]:
    with Session(engine) as session:
        rows = session.scalars(
            select(ImageLayoutStagingRowModel).order_by(ImageLayoutStagingRowModel.sequence_number)
        ).all()
        if [row.sequence_number for row in rows] != list(range(1, BOARD_COUNT + 1)):
            raise ImageOperationsBenchmarkError("Staging sequence is not continuous.")
        return len(rows), sum(len(row.cells) for row in rows)


def _stage_payload(
    stage: str,
    context: ImageStageContext,
    source_index: int,
) -> Mapping[str, object]:
    if stage == "discovery":
        return {
            "height": 1280,
            "sourceChecksumSha256": context.source_checksum_sha256,
            "sourceRelativePath": context.source_relative_path,
            "width": 720,
        }
    if stage == "normalization":
        return {
            "height": 1280,
            "normalizedChecksumSha256": _digest(context.source_checksum_sha256, stage),
            "normalizedRelativePath": f"working/{source_index:03d}/normalized.png",
            "width": 720,
        }
    boards: list[dict[str, object]] = []
    for position in range(BOARDS_PER_SOURCE):
        sequence_number = source_index * BOARDS_PER_SOURCE + position + 1
        if stage == "board_detection":
            board: dict[str, object] = {
                "confidence": 0.99,
                "geometry": {
                    "quad": [[0, 0], [500, 0], [500, 300], [0, 300]],
                },
                "positionIndex": position,
            }
        elif stage == "board_crops":
            board = {
                "boardChecksumSha256": _digest(
                    context.source_checksum_sha256,
                    f"board:{position}",
                ),
                "boardRelativePath": (f"crops/{source_index:03d}/board-{position}.png"),
                "cells": [
                    {
                        "columnIndex": cell % 5,
                        "cropChecksumSha256": _digest(
                            context.source_checksum_sha256,
                            f"board:{position}:cell:{cell}",
                        ),
                        "cropRelativePath": (
                            f"crops/{source_index:03d}/board-{position}/"
                            f"r{cell // 5}-c{cell % 5}.png"
                        ),
                        "rowIndex": cell // 5,
                    }
                    for cell in range(CELLS_PER_BOARD)
                ],
                "cropperVersion": "m7-operations-cropper-v1",
                "positionIndex": position,
            }
        elif stage == "sequence_ocr":
            board = {
                "confidence": 0.5,
                "normalizedNumber": sequence_number,
                "positionIndex": position,
                "rawText": str(sequence_number),
                "reviewReasons": ["OCR_MANUAL_REVIEW_REQUIRED"],
            }
        elif stage == "symbol_inference":
            board = {
                "cells": [
                    _symbol_cell(source_index, position, cell) for cell in range(CELLS_PER_BOARD)
                ],
                "positionIndex": position,
            }
        else:
            raise ImageOperationsBenchmarkError(f"Unsupported fixture stage: {stage}.")
        boards.append(board)
    payload: dict[str, object] = {"boards": boards}
    if stage == "symbol_inference":
        payload["modelVersion"] = "m7-operations-synthetic-model-v1"
    return payload


def _symbol_cell(source_index: int, position: int, cell: int) -> dict[str, object]:
    code = SYMBOL_CODES[(source_index + position + cell) % len(SYMBOL_CODES)]
    return {
        "alternatives": [{"confidence": 0.8, "symbolCode": code}],
        "columnIndex": cell % 5,
        "confidence": 0.8,
        "rowIndex": cell // 5,
        "symbolCode": code,
    }


def _quality_evidence(repository_root: Path) -> dict[str, object]:
    reports: dict[str, tuple[dict[str, object], str]] = {}
    for name, relative_path in QUALITY_REPORT_PATHS.items():
        raw = (repository_root / relative_path).read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ImageOperationsBenchmarkError(f"{name} report must be an object.")
        reports[name] = (cast(dict[str, object], value), hashlib.sha256(raw).hexdigest())
    m5, m5_sha = reports["m5Image"]
    m6, m6_sha = reports["m6VerticalSlice"]
    m5_decision = _mapping(m5.get("decision"), "m5.decision")
    m6_gate = _mapping(m6.get("qualityGate"), "m6.qualityGate")
    m6_geometry = _mapping(m6.get("geometry"), "m6.geometry")
    manual_review = _mapping(m6.get("manualReview"), "m6.manualReview")
    automatic_quality = _mapping(m6.get("automaticQuality"), "m6.automaticQuality")
    overall = _mapping(automatic_quality.get("overall"), "m6.automaticQuality.overall")
    if (
        m5_decision.get("thresholdsAccepted") is not True
        or m5_decision.get("ocrAutoAcceptEnabled") is not False
        or m6_gate.get("verticalSlicePassed") is not True
        or m6_gate.get("massImportAllowed") is not False
    ):
        raise ImageOperationsBenchmarkError("Accepted quality evidence drifted.")
    return {
        "autoAcceptEnabled": False,
        "classifierAccuracy": overall.get("accuracy"),
        "geometryAcceptedBoardCount": m6_geometry.get("acceptedBoardCount"),
        "geometryAcceptedCellCount": m6_geometry.get("acceptedCellCount"),
        "manualReviewShare": manual_review.get("manualReviewShare"),
        "massImportAllowed": False,
        "ocrAutoAcceptEnabled": False,
        "sources": [
            {
                "name": "m5Image",
                "relativePath": QUALITY_REPORT_PATHS["m5Image"],
                "sha256": m5_sha,
            },
            {
                "name": "m6VerticalSlice",
                "relativePath": QUALITY_REPORT_PATHS["m6VerticalSlice"],
                "sha256": m6_sha,
            },
        ],
    }


def _source_checksum(index: int) -> str:
    return hashlib.sha256(f"m7-operations-source:{index}".encode()).hexdigest()


def _source_index(relative_path: str) -> int:
    try:
        return int(Path(relative_path).stem.removeprefix("page-"))
    except ValueError as error:
        raise ImageOperationsBenchmarkError("Fixture source path is invalid.") from error


def _digest(source: str, suffix: str) -> str:
    return hashlib.sha256(f"{source}:{suffix}".encode()).hexdigest()


def _database_url(source: URL, database_name: str) -> URL:
    return source.set(database=database_name).update_query_dict({"connect_timeout": "3"})


def _migration_config(repository_root: Path, database_url: URL) -> Config:
    config = Config(str(repository_root / "alembic.ini"))
    rendered = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


def _stats_dict(stats: ImageBatchStats) -> dict[str, int]:
    return {
        "current": stats.current,
        "failed": stats.failed,
        "review": stats.review,
        "succeeded": stats.succeeded,
        "total": stats.total,
        "waiting": stats.waiting,
    }


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ImageOperationsBenchmarkError(f"{label} must be an object.")
    return cast(Mapping[str, object], value)


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_all_strings(key))
            result.extend(_all_strings(item))
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        result = []
        for item in value:
            result.extend(_all_strings(item))
        return result
    return []


__all__ = [
    "BOARD_COUNT",
    "CELL_COUNT",
    "ImageOperationsBenchmarkError",
    "OPERATIONS_BENCHMARK_SCHEMA",
    "SOURCE_FILE_COUNT",
    "build_operations_report",
    "operations_report_bytes",
    "validate_operations_report",
]
