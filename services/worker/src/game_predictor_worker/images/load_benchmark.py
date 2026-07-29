"""Bounded database and filesystem load benchmark for M7 image imports."""

from __future__ import annotations

import hashlib
import platform
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, perf_counter, process_time
from typing import cast
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_storage import (
    ImageArtifactStore,
    ImageStorageInventory,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.jobs import JobType, create_job
from game_predictor_api.storage.catalog_repository import (
    SqlAlchemyCatalogRepository,
)
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, Engine, make_url
from sqlalchemy.orm import Session

from game_predictor_worker.benchmarks.performance import (
    PeakMemorySampler,
    measure,
)
from game_predictor_worker.images.orchestration import (
    ImageBatchCandidate,
    ImageBatchStats,
    ImageFileRegistration,
)
from game_predictor_worker.images.orchestration_store import (
    SqlAlchemyImageBatchStore,
)

LOAD_BENCHMARK_SCHEMA = "m7-storage-database-load-v1"
DEFAULT_LOAD_SEED = 740_074
PIPELINE_FINGERPRINT = hashlib.sha256(b"m7-load-benchmark-pipeline-v1").hexdigest()
PLACEHOLDER_SIZE_BYTES = 32
DATABASE_REGISTRATION_BATCH_SIZE = 500


class ImageLoadBenchmarkError(RuntimeError):
    """Stable benchmark failure that is safe to show in local tooling."""


@dataclass(frozen=True, slots=True)
class ImageLoadProfile:
    name: str
    file_count: int
    layouts_per_image: int
    shard_count: int
    query_iterations: int

    @property
    def represented_layout_capacity(self) -> int:
        return self.file_count * self.layouts_per_image


LOAD_PROFILES = {
    "smoke": ImageLoadProfile(
        name="smoke",
        file_count=1_000,
        layouts_per_image=9,
        shard_count=32,
        query_iterations=5,
    ),
    "full": ImageLoadProfile(
        name="full",
        file_count=55_556,
        layouts_per_image=9,
        shard_count=256,
        query_iterations=20,
    ),
}


class BenchmarkDeadline:
    def __init__(self, max_seconds: float) -> None:
        if max_seconds <= 0:
            raise ImageLoadBenchmarkError("Benchmark deadline must be positive.")
        self._started_at = monotonic()
        self._max_seconds = max_seconds

    def check(self, stage: str) -> None:
        if monotonic() - self._started_at > self._max_seconds:
            raise ImageLoadBenchmarkError(f"Benchmark deadline exceeded during {stage}.")


@dataclass(frozen=True, slots=True)
class OperationMeasurement:
    elapsed_seconds: float
    cpu_seconds: float
    throughput_per_second: float
    memory: dict[str, int | None]

    def to_dict(self) -> dict[str, object]:
        ratio = 0.0 if self.elapsed_seconds <= 0 else self.cpu_seconds / self.elapsed_seconds
        return {
            "clientCpuSeconds": round(self.cpu_seconds, 4),
            "clientCpuToWallRatio": round(ratio, 4),
            "elapsedSeconds": round(self.elapsed_seconds, 4),
            "memory": self.memory,
            "throughputPerSecond": round(self.throughput_per_second, 2),
        }


def load_profile(name: str) -> ImageLoadProfile:
    try:
        return LOAD_PROFILES[name]
    except KeyError as error:
        raise ImageLoadBenchmarkError(f"Unknown load profile: {name!r}.") from error


def source_checksum(seed: int, order_index: int) -> str:
    if seed < 0 or order_index < 0:
        raise ImageLoadBenchmarkError("Seed and order index must be non-negative.")
    return hashlib.sha256(f"{seed}:{order_index}".encode()).hexdigest()


def source_relative_path(
    profile: ImageLoadProfile,
    seed: int,
    order_index: int,
) -> str:
    checksum = source_checksum(seed, order_index)
    shard = order_index % profile.shard_count
    return f"load/{profile.name}/{shard:03d}/{checksum}.jpg"


def run_storage_load(
    artifact_root: Path,
    profile: ImageLoadProfile,
    *,
    seed: int,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    working_root = artifact_root / "data" / "working"
    for shard in range(profile.shard_count):
        (working_root / "load" / profile.name / f"{shard:03d}").mkdir(
            parents=True,
            exist_ok=True,
        )
    payload_prefix = seed.to_bytes(8, byteorder="big", signed=False)

    started_at = perf_counter()
    cpu_started_at = process_time()
    with PeakMemorySampler() as memory_sampler:
        for order_index in range(profile.file_count):
            if order_index % 100 == 0:
                deadline.check("storage materialization")
            checksum = source_checksum(seed, order_index)
            shard = order_index % profile.shard_count
            path = working_root / "load" / profile.name / f"{shard:03d}" / f"{checksum}.bin"
            payload = payload_prefix + order_index.to_bytes(
                PLACEHOLDER_SIZE_BYTES - len(payload_prefix),
                byteorder="big",
                signed=False,
            )
            path.write_bytes(payload)
    elapsed_seconds = perf_counter() - started_at
    cpu_seconds = process_time() - cpu_started_at
    materialization = OperationMeasurement(
        elapsed_seconds=elapsed_seconds,
        cpu_seconds=cpu_seconds,
        throughput_per_second=profile.file_count / elapsed_seconds,
        memory=memory_sampler.summary().to_dict(),
    )

    store = ImageArtifactStore(artifact_root)

    def inventory_operation() -> ImageStorageInventory:
        deadline.check("storage inventory")
        return store.inventory()

    inventory_timing, inventory = measure(
        inventory_operation,
        iterations=profile.query_iterations,
        warmups=1,
    )
    working = next(namespace for namespace in inventory.namespaces if namespace.name == "working")
    expected_size = profile.file_count * PLACEHOLDER_SIZE_BYTES
    if working.file_count != profile.file_count or working.size_bytes != expected_size:
        raise ImageLoadBenchmarkError(
            "Managed storage inventory does not match benchmark cardinality."
        )
    return {
        "automaticDeletion": inventory.automatic_deletion,
        "inventory": inventory_timing.to_dict(),
        "materialization": materialization.to_dict(),
        "placeholderSizeBytes": PLACEHOLDER_SIZE_BYTES,
        "totalFileCount": inventory.total_file_count,
        "totalSizeBytes": inventory.total_size_bytes,
        "workingFileCount": working.file_count,
        "workingIgnoredSymlinkCount": working.ignored_symlink_count,
        "workingSizeBytes": working.size_bytes,
    }


def run_database_load(
    database_url: str,
    repository_root: Path,
    profile: ImageLoadProfile,
    *,
    seed: int,
    deadline: BenchmarkDeadline,
) -> dict[str, object]:
    source_url = make_url(database_url)
    maintenance_url = _benchmark_url(source_url, "postgres")
    database_name = f"game_predictor_m7_load_{uuid4().hex[:12]}"
    benchmark_url = _benchmark_url(source_url, database_name)
    maintenance_engine = create_engine(
        maintenance_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    database_created = False
    engine = None
    identifier = f'"{database_name}"'
    try:
        deadline.check("database creation")
        with maintenance_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
        database_created = True

        migration_started_at = perf_counter()
        command.upgrade(
            _migration_config(repository_root, benchmark_url),
            "head",
        )
        migration_seconds = perf_counter() - migration_started_at
        deadline.check("database migration")

        engine = create_engine(
            benchmark_url,
            pool_pre_ping=True,
            connect_args={
                "options": "-c lock_timeout=3000 -c statement_timeout=30000",
            },
        )
        session_factory = create_session_factory(engine)
        job_id = _create_benchmark_job(engine)
        store = SqlAlchemyImageBatchStore(session_factory)
        registered_at = datetime(2026, 7, 29, 23, 0, tzinfo=UTC)

        started_at = perf_counter()
        cpu_started_at = process_time()
        with PeakMemorySampler() as memory_sampler:
            for batch_start in range(
                0,
                profile.file_count,
                DATABASE_REGISTRATION_BATCH_SIZE,
            ):
                deadline.check("database registration")
                registrations = [
                    ImageFileRegistration(
                        source_checksum_sha256=source_checksum(seed, order_index),
                        source_relative_path=source_relative_path(
                            profile,
                            seed,
                            order_index,
                        ),
                        order_index=order_index,
                    )
                    for order_index in range(
                        batch_start,
                        min(
                            batch_start + DATABASE_REGISTRATION_BATCH_SIZE,
                            profile.file_count,
                        ),
                    )
                ]
                store.register_files(
                    job_id,
                    registrations=registrations,
                    pipeline_fingerprint=PIPELINE_FINGERPRINT,
                    registered_at=registered_at,
                )
        elapsed_seconds = perf_counter() - started_at
        cpu_seconds = process_time() - cpu_started_at
        registration = OperationMeasurement(
            elapsed_seconds=elapsed_seconds,
            cpu_seconds=cpu_seconds,
            throughput_per_second=profile.file_count / elapsed_seconds,
            memory=memory_sampler.summary().to_dict(),
        )

        def count_operation() -> int:
            deadline.check("count_job_files query")
            return store.count_job_files(
                job_id,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

        def stats_operation() -> ImageBatchStats:
            deadline.check("batch_stats query")
            return store.batch_stats(
                job_id,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

        def next_operation() -> ImageBatchCandidate | None:
            deadline.check("next_processing_file query")
            return store.next_processing_file(
                job_id,
                pipeline_fingerprint=PIPELINE_FINGERPRINT,
            )

        count_timing, count_result = measure(
            count_operation,
            iterations=profile.query_iterations,
            warmups=1,
        )
        stats_timing, stats_result = measure(
            stats_operation,
            iterations=profile.query_iterations,
            warmups=1,
        )
        next_timing, next_result = measure(
            next_operation,
            iterations=profile.query_iterations,
            warmups=1,
        )
        if (
            count_result != profile.file_count
            or stats_result.total != profile.file_count
            or next_result is None
            or next_result.order_index != 0
        ):
            raise ImageLoadBenchmarkError(
                "PostgreSQL benchmark results do not match source cardinality."
            )

        with engine.connect() as connection:
            postgres_version = cast(
                str,
                connection.scalar(text("SELECT current_setting('server_version')")),
            )
            database_size = int(
                cast(int, connection.scalar(text("SELECT pg_database_size(current_database())")))
            )
            relations = {
                table: {
                    "indexSizeBytes": int(
                        cast(
                            int,
                            connection.scalar(
                                text("SELECT pg_indexes_size(:table_name)"),
                                {"table_name": table},
                            ),
                        )
                    ),
                    "rowCount": int(
                        cast(
                            int,
                            connection.scalar(text(f'SELECT count(*) FROM "{table}"')),
                        )
                    ),
                    "totalSizeBytes": int(
                        cast(
                            int,
                            connection.scalar(
                                text("SELECT pg_total_relation_size(:table_name)"),
                                {"table_name": table},
                            ),
                        )
                    ),
                }
                for table in (
                    "image_file_executions",
                    "image_import_job_files",
                )
            }
        return {
            "databaseSizeBytes": database_size,
            "migrationElapsedSeconds": round(migration_seconds, 4),
            "postgresVersion": postgres_version,
            "registrationBatchSize": DATABASE_REGISTRATION_BATCH_SIZE,
            "queries": {
                "batchStats": stats_timing.to_dict(),
                "countJobFiles": count_timing.to_dict(),
                "nextProcessingFile": next_timing.to_dict(),
            },
            "registration": registration.to_dict(),
            "relations": relations,
        }
    finally:
        if engine is not None:
            engine.dispose()
        if database_created:
            with maintenance_engine.connect() as connection:
                connection.exec_driver_sql(f"DROP DATABASE {identifier} WITH (FORCE)")
        maintenance_engine.dispose()


def build_load_report(
    profile: ImageLoadProfile,
    database: dict[str, object],
    storage: dict[str, object],
) -> dict[str, object]:
    report: dict[str, object] = {
        "capturedAt": datetime.now(UTC).isoformat(),
        "database": database,
        "environment": {
            "machine": platform.machine(),
            "operatingSystem": platform.platform(),
            "python": platform.python_version(),
            "processBits": 64 if sys.maxsize > 2**32 else 32,
        },
        "profile": {
            "fileCount": profile.file_count,
            "layoutsPerImage": profile.layouts_per_image,
            "name": profile.name,
            "queryIterations": profile.query_iterations,
            "representedLayoutCapacity": profile.represented_layout_capacity,
            "shardCount": profile.shard_count,
        },
        "schemaVersion": LOAD_BENCHMARK_SCHEMA,
        "scope": (
            "PostgreSQL image-file registration and managed filesystem metadata "
            "load only; image decoding, OCR, ONNX, review and publication are excluded."
        ),
        "storage": storage,
    }
    validate_load_report(report, expected_profile=profile)
    return report


def validate_load_report(
    report: object,
    *,
    expected_profile: ImageLoadProfile | None = None,
) -> None:
    if not isinstance(report, dict):
        raise ImageLoadBenchmarkError("Load report must be a JSON object.")
    if report.get("schemaVersion") != LOAD_BENCHMARK_SCHEMA:
        raise ImageLoadBenchmarkError("Load report schemaVersion is invalid.")
    profile = report.get("profile")
    database = report.get("database")
    storage = report.get("storage")
    if (
        not isinstance(profile, dict)
        or not isinstance(database, dict)
        or not isinstance(storage, dict)
    ):
        raise ImageLoadBenchmarkError("Load report sections are incomplete.")
    file_count = profile.get("fileCount")
    represented = profile.get("representedLayoutCapacity")
    if not isinstance(file_count, int) or file_count < 1:
        raise ImageLoadBenchmarkError("Load report fileCount is invalid.")
    if not isinstance(represented, int) or represented < file_count:
        raise ImageLoadBenchmarkError("Load report representedLayoutCapacity is invalid.")
    if expected_profile is not None and (
        profile.get("name") != expected_profile.name
        or file_count != expected_profile.file_count
        or represented != expected_profile.represented_layout_capacity
    ):
        raise ImageLoadBenchmarkError("Load report profile does not match request.")
    if storage.get("workingFileCount") != file_count:
        raise ImageLoadBenchmarkError("Storage report file count is invalid.")
    relations = database.get("relations")
    if not isinstance(relations, dict):
        raise ImageLoadBenchmarkError("Database relation measurements are missing.")
    for table in ("image_file_executions", "image_import_job_files"):
        relation = relations.get(table)
        if not isinstance(relation, dict) or relation.get("rowCount") != file_count:
            raise ImageLoadBenchmarkError(f"Database row count is invalid for {table}.")
    for value in _all_strings(report):
        lowered = value.lower()
        if "postgresql://" in lowered or "postgresql+psycopg://" in lowered:
            raise ImageLoadBenchmarkError("Load report exposes a database URL.")
        if _looks_like_absolute_windows_path(value):
            raise ImageLoadBenchmarkError("Load report exposes an absolute path.")


def _create_benchmark_job(engine: Engine) -> UUID:
    with Session(engine, expire_on_commit=False) as session:
        game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
            code=f"m7-load-{uuid4().hex[:12]}",
            name="M7 load benchmark",
            status=GameStatus.ACTIVE,
        )
        job = SqlAlchemyJobRepository(session).add_job(
            create_job(
                JobType.IMPORT,
                game_id=game.id,
                input_payload={
                    "schema_version": 1,
                    "import_kind": "image_directory",
                    "pipeline_fingerprint": PIPELINE_FINGERPRINT,
                },
                created_at=datetime(2026, 7, 29, 23, 0, tzinfo=UTC),
            )
        )
        session.commit()
        return job.id


def _benchmark_url(source_url: URL, database_name: str) -> URL:
    return source_url.set(database=database_name).update_query_dict({"connect_timeout": "3"})


def _migration_config(repository_root: Path, database_url: URL) -> Config:
    config = Config(str(repository_root / "alembic.ini"))
    rendered = database_url.render_as_string(hide_password=False).replace("%", "%%")
    config.set_main_option("sqlalchemy.url", rendered)
    return config


def _all_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        result: list[str] = []
        for key, item in value.items():
            result.extend(_all_strings(key))
            result.extend(_all_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(_all_strings(item))
        return result
    return []


def _looks_like_absolute_windows_path(value: str) -> bool:
    return len(value) >= 3 and value[0].isalpha() and value[1:3] in {":\\", ":/"}


def default_database_url() -> str:
    return str(ApiSettings.from_environment().database_url)


__all__ = [
    "BenchmarkDeadline",
    "DATABASE_REGISTRATION_BATCH_SIZE",
    "DEFAULT_LOAD_SEED",
    "ImageLoadBenchmarkError",
    "ImageLoadProfile",
    "LOAD_BENCHMARK_SCHEMA",
    "LOAD_PROFILES",
    "build_load_report",
    "default_database_url",
    "load_profile",
    "run_database_load",
    "run_storage_load",
    "source_checksum",
    "source_relative_path",
    "validate_load_report",
]
