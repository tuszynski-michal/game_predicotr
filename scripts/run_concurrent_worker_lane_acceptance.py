"""Bounded real-process acceptance for concurrent worker lanes.

The runner creates an isolated PostgreSQL database and disposable fixtures,
starts the production worker entry point once per lane, and never touches the
owner database or image staging.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from game_predictor_api.application.catalog import CatalogService
from game_predictor_api.application.image_selections import ImageSelectionService
from game_predictor_api.application.jobs import JobService
from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.application.worker_lanes import WorkerLaneStatusService
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.jobs import JobStatus
from game_predictor_api.domain.worker_lanes import WorkerLaneName
from game_predictor_api.storage.catalog_repository import SqlAlchemyCatalogRepository
from game_predictor_api.storage.database import create_session_factory
from game_predictor_api.storage.image_selection_repository import (
    SqlAlchemyImageSelectionRepository,
)
from game_predictor_api.storage.job_repository import SqlAlchemyJobRepository
from game_predictor_api.storage.worker_lane_repository import (
    SqlAlchemyWorkerLaneRepository,
)
from game_predictor_worker.images.selection.manifest import (
    APPEARANCE_ONLY_SELECTOR_MANIFEST_V9,
)
from game_predictor_worker.imports.fixtures import write_layout_import_fixture
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.orm import Session

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPOSITORY_ROOT / "alembic.ini"
TERMINAL_STATUSES = {
    JobStatus.COMPLETED,
    JobStatus.FAILED,
    JobStatus.CANCELLED,
    JobStatus.WAITING_FOR_REVIEW,
}


@dataclass(slots=True)
class ProcessMetrics:
    peak_working_set_bytes: int = 0
    cpu_seconds: float = 0.0
    read_bytes: int = 0
    write_bytes: int = 0
    samples: int = 0

    def observe(self, sample: dict[str, int | float]) -> None:
        self.peak_working_set_bytes = max(
            self.peak_working_set_bytes,
            int(sample["working_set_bytes"]),
        )
        self.cpu_seconds = max(self.cpu_seconds, float(sample["cpu_seconds"]))
        self.read_bytes = max(self.read_bytes, int(sample["read_bytes"]))
        self.write_bytes = max(self.write_bytes, int(sample["write_bytes"]))
        self.samples += 1


@dataclass(slots=True)
class AcceptanceState:
    started_at: float
    simultaneous_processing_observed: bool = False
    selection_progress_during_general_cancel: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)

    def record(self, name: str, **details: object) -> None:
        self.events.append(
            {
                "name": name,
                "elapsedSeconds": round(time.monotonic() - self.started_at, 3),
                **details,
            }
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=180)
    parser.add_argument("--selection-images", type=int, default=600)
    parser.add_argument("--layout-records", type=int, default=75_000)
    values = parser.parse_args()
    if not 30 <= values.timeout_seconds <= 600:
        parser.error("--timeout-seconds must be between 30 and 600")
    if not 100 <= values.selection_images <= 10_000:
        parser.error("--selection-images must be between 100 and 10000")
    if not 10_000 <= values.layout_records <= 500_000:
        parser.error("--layout-records must be between 10000 and 500000")
    return values


def migration_config(database_url: URL) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option(
        "sqlalchemy.url",
        database_url.render_as_string(hide_password=False).replace("%", "%%"),
    )
    return config


def create_database(database_url: URL) -> None:
    maintenance = create_engine(
        database_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    identifier = f'"{database_url.database}"'
    try:
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
            connection.exec_driver_sql(f"CREATE DATABASE {identifier}")
    finally:
        maintenance.dispose()


def drop_database(database_url: URL) -> None:
    maintenance = create_engine(
        database_url.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    identifier = f'"{database_url.database}"'
    try:
        with maintenance.connect() as connection:
            connection.exec_driver_sql(f"DROP DATABASE IF EXISTS {identifier} WITH (FORCE)")
    finally:
        maintenance.dispose()


def write_selection_fixture(import_root: Path, file_count: int) -> tuple[UUID, str]:
    selection_id = uuid4()
    source_root = import_root / "browser-selections" / str(selection_id)
    source_root.mkdir(parents=True)
    files: list[dict[str, object]] = []
    for index in range(file_count):
        stored_name = f"{index + 1:08d}.jpg"
        path = source_root / stored_name
        image = Image.new("RGB", (320, 240), (8, 18, 48))
        draw = ImageDraw.Draw(image)
        group = index // 12
        for board in range(9):
            column = board % 3
            row = board // 3
            left = 18 + column * 101
            top = 34 + row * 62
            color = (
                80 + (group * 13 + board * 17) % 150,
                45 + (group * 29 + board * 11) % 170,
                35 + (group * 7 + board * 31) % 180,
            )
            draw.rectangle((left, top, left + 82, top + 45), fill=color, outline="white")
            draw.text((left + 4, top + 3), str(group * 9 + board + 1), fill="white")
        draw.line((5, 5 + index % 17, 314, 20 + index % 23), fill=(30, 90, 210), width=2)
        image.save(path, format="JPEG", quality=76, optimize=False)
        content = path.read_bytes()
        files.append(
            {
                "checksumSha256": hashlib.sha256(content).hexdigest(),
                "orderIndex": index,
                "relativePath": f"photos/photo-{index + 1:06d}.jpg",
                "sizeBytes": len(content),
                "storedFileName": stored_name,
            }
        )
    payload = {
        "files": files,
        "orderingPolicy": "natural_relative_path_v1",
        "purpose": "photo_selection",
        "schemaVersion": 1,
    }
    content = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    (source_root / "_browser_manifest.json").write_bytes(content)
    (source_root / "_upload_metrics.json").write_text(
        json.dumps({"durationSeconds": 0.0}),
        encoding="utf-8",
    )
    return selection_id, hashlib.sha256(content).hexdigest()


def seed_jobs(
    database_url: URL,
    import_root: Path,
    *,
    layout_records: int,
    selection_images: int,
) -> tuple[UUID, UUID]:
    layout_path = import_root / "acceptance-layouts.jsonl"
    write_layout_import_fixture(
        layout_path,
        layout_count=layout_records,
        seed=177,
        duplicate_group_count=0,
    )
    selection_id, manifest_sha256 = write_selection_fixture(import_root, selection_images)
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            game = CatalogService(SqlAlchemyCatalogRepository(session)).create_game(
                code=f"lane-acceptance-{uuid4().hex[:8]}",
                name="Concurrent lane acceptance",
                status=GameStatus.ACTIVE,
            )
            job_service = JobService(
                SqlAlchemyJobRepository(session),
                LayoutImportSourceInspector(import_root, max_bytes=1024 * 1024 * 1024),
            )
            import_job = job_service.create_layout_import_job(
                game_id=game.id,
                source_path=layout_path.name,
                contract_version=1,
            )
            selection_run, created = ImageSelectionService(
                SqlAlchemyImageSelectionRepository(session)
            ).create_run(
                game_id=game.id,
                source_selection_id=selection_id,
                input_manifest_sha256=manifest_sha256,
                selector_fingerprint=APPEARANCE_ONLY_SELECTOR_MANIFEST_V9.fingerprint,
            )
            if not created:
                raise RuntimeError("The isolated image-selection run was not created.")
            session.commit()
            return import_job.id, selection_run.job.id
    finally:
        engine.dispose()


def job_snapshot(database_url: URL, job_id: UUID) -> dict[str, object]:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            job = JobService(SqlAlchemyJobRepository(session)).get_job(job_id)
            return {
                "status": job.status,
                "current": job.progress_current,
                "total": job.progress_total,
                "attemptCount": job.attempt_count,
                "stage": job.stage,
            }
    finally:
        engine.dispose()


def cancel_job(database_url: URL, job_id: UUID) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            JobService(SqlAlchemyJobRepository(session)).cancel_job(job_id)
            session.commit()
    finally:
        engine.dispose()


def retry_job(database_url: URL, job_id: UUID) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with Session(engine, expire_on_commit=False) as session:
            JobService(SqlAlchemyJobRepository(session)).retry_job(job_id)
            session.commit()
    finally:
        engine.dispose()


def lane_states(database_url: URL) -> dict[str, str]:
    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    try:
        statuses = WorkerLaneStatusService(
            SqlAlchemyWorkerLaneRepository(session_factory)
        ).list_statuses()
        return {status.lane.value: status.state.value for status in statuses}
    finally:
        engine.dispose()


def stop_lane(database_url: URL, lane: WorkerLaneName, token: UUID) -> None:
    engine = create_engine(database_url, pool_pre_ping=True)
    session_factory = create_session_factory(engine)
    try:
        SqlAlchemyWorkerLaneRepository(session_factory).stop(
            lane=lane,
            instance_token=token,
            stopped_at=datetime.now(UTC),
        )
    finally:
        engine.dispose()


def start_worker(
    database_url: URL,
    root: Path,
    *,
    lane: str,
    budget: int,
) -> tuple[subprocess.Popen[str], UUID, Any, Any]:
    token = uuid4()
    log_root = root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_handle = (log_root / f"{lane}.out.log").open("w", encoding="utf-8")
    stderr_handle = (log_root / f"{lane}.error.log").open("w", encoding="utf-8")
    environment = os.environ.copy()
    environment.update(
        {
            "GAME_PREDICTOR_DATABASE_URL": database_url.render_as_string(
                hide_password=False
            ),
            "GAME_PREDICTOR_IMPORT_ROOT": str(root / "imports"),
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(root / "artifacts"),
            "GAME_PREDICTOR_WORKER_THREAD_BUDGET": str(budget),
            "OMP_NUM_THREADS": "1" if lane == "image-selection" else str(budget),
            "OPENBLAS_NUM_THREADS": "1" if lane == "image-selection" else str(budget),
            "MKL_NUM_THREADS": "1" if lane == "image-selection" else str(budget),
            "NUMEXPR_NUM_THREADS": "1" if lane == "image-selection" else str(budget),
            "VECLIB_MAXIMUM_THREADS": "1" if lane == "image-selection" else str(budget),
        }
    )
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "game_predictor_worker",
            "--poll",
            "--poll-interval",
            "0.1",
            "--lane",
            lane,
            "--cpu-thread-budget",
            str(budget),
            "--lane-instance-token",
            str(token),
            "--artifact-root",
            str(root / "artifacts"),
        ],
        cwd=REPOSITORY_ROOT,
        env=environment,
        stdout=stdout_handle,
        stderr=stderr_handle,
        text=True,
        creationflags=creation_flags,
    )
    return process, token, stdout_handle, stderr_handle


def _windows_process_tree(root_pid: int) -> tuple[int, ...]:
    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("size", wintypes.DWORD),
            ("usage", wintypes.DWORD),
            ("process_id", wintypes.DWORD),
            ("default_heap_id", ctypes.c_size_t),
            ("module_id", wintypes.DWORD),
            ("thread_count", wintypes.DWORD),
            ("parent_process_id", wintypes.DWORD),
            ("base_priority", wintypes.LONG),
            ("flags", wintypes.DWORD),
            ("executable", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry),
    )
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(ProcessEntry),
    )
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    parents: dict[int, int] = {}
    try:
        entry = ProcessEntry()
        entry.size = ctypes.sizeof(entry)
        found = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while found:
            parents[int(entry.process_id)] = int(entry.parent_process_id)
            found = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for process_id, parent_id in parents.items():
            if parent_id in result and process_id not in result:
                result.add(process_id)
                changed = True
    return tuple(sorted(result))


def _windows_process_sample(process_id: int) -> dict[str, int | float]:
    class FileTime(ctypes.Structure):
        _fields_ = [("low", wintypes.DWORD), ("high", wintypes.DWORD)]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            ("read_ops", ctypes.c_ulonglong),
            ("write_ops", ctypes.c_ulonglong),
            ("other_ops", ctypes.c_ulonglong),
            ("read_bytes", ctypes.c_ulonglong),
            ("write_bytes", ctypes.c_ulonglong),
            ("other_bytes", ctypes.c_ulonglong),
        ]

    class MemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("page_faults", wintypes.DWORD),
            ("peak_working_set", ctypes.c_size_t),
            ("working_set", ctypes.c_size_t),
            ("quota_peak_paged_pool", ctypes.c_size_t),
            ("quota_paged_pool", ctypes.c_size_t),
            ("quota_peak_nonpaged_pool", ctypes.c_size_t),
            ("quota_nonpaged_pool", ctypes.c_size_t),
            ("pagefile_usage", ctypes.c_size_t),
            ("peak_pagefile_usage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetProcessTimes.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
        ctypes.POINTER(FileTime),
    )
    kernel32.GetProcessTimes.restype = wintypes.BOOL
    kernel32.GetProcessIoCounters.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(IoCounters),
    )
    kernel32.GetProcessIoCounters.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    psapi.GetProcessMemoryInfo.argtypes = (
        wintypes.HANDLE,
        ctypes.POINTER(MemoryCounters),
        wintypes.DWORD,
    )
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, process_id)
    if not handle:
        raise OSError(ctypes.get_last_error(), "OpenProcess failed")
    try:
        created = FileTime()
        exited = FileTime()
        kernel = FileTime()
        user = FileTime()
        io = IoCounters()
        memory = MemoryCounters()
        memory.cb = ctypes.sizeof(memory)
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            raise OSError(ctypes.get_last_error(), "GetProcessTimes failed")
        if not kernel32.GetProcessIoCounters(handle, ctypes.byref(io)):
            raise OSError(ctypes.get_last_error(), "GetProcessIoCounters failed")
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb):
            raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
        kernel_ticks = (kernel.high << 32) | kernel.low
        user_ticks = (user.high << 32) | user.low
        return {
            "working_set_bytes": int(memory.working_set),
            "cpu_seconds": (kernel_ticks + user_ticks) / 10_000_000,
            "read_bytes": int(io.read_bytes),
            "write_bytes": int(io.write_bytes),
        }
    finally:
        kernel32.CloseHandle(handle)


def process_sample(process: subprocess.Popen[str]) -> dict[str, int | float]:
    if os.name != "nt":
        return {
            "working_set_bytes": 0,
            "cpu_seconds": 0.0,
            "read_bytes": 0,
            "write_bytes": 0,
        }
    samples: list[dict[str, int | float]] = []
    for process_id in _windows_process_tree(process.pid):
        with contextlib.suppress(OSError):
            samples.append(_windows_process_sample(process_id))
    if not samples:
        raise OSError("No process in the worker tree could be sampled.")
    return {
        "working_set_bytes": sum(int(sample["working_set_bytes"]) for sample in samples),
        "cpu_seconds": sum(float(sample["cpu_seconds"]) for sample in samples),
        "read_bytes": sum(int(sample["read_bytes"]) for sample in samples),
        "write_bytes": sum(int(sample["write_bytes"]) for sample in samples),
    }


def wait_until(
    predicate: Any,
    *,
    deadline: float,
    processes: tuple[subprocess.Popen[str], ...],
    metrics: tuple[ProcessMetrics, ...],
) -> Any:
    while time.monotonic() < deadline:
        for process, process_metrics in zip(processes, metrics, strict=True):
            if process.poll() is not None:
                raise RuntimeError(
                    f"Worker process {process.pid} exited with {process.returncode}."
                )
            with contextlib.suppress(OSError):
                process_metrics.observe(process_sample(process))
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise TimeoutError("Concurrent worker acceptance exceeded its bounded deadline.")


def main() -> int:
    options = parse_arguments()
    run_id = uuid4().hex[:10]
    root = REPOSITORY_ROOT / ".pytest-tmp" / f"v04-concurrent-{run_id}"
    output = options.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir(parents=True)
    import_root = root / "imports"
    import_root.mkdir()
    database_url = make_url(ApiSettings.from_environment().database_url).set(
        database=f"game_predictor_concurrent_{run_id}"
    )
    state = AcceptanceState(started_at=time.monotonic())
    processes: list[subprocess.Popen[str]] = []
    handles: list[Any] = []
    tokens: dict[str, UUID] = {}
    process_metrics = {"general": ProcessMetrics(), "image_selection": ProcessMetrics()}
    failure: str | None = None
    import_job_id: UUID | None = None
    selection_job_id: UUID | None = None
    try:
        create_database(database_url)
        command.upgrade(migration_config(database_url), "head")
        import_job_id, selection_job_id = seed_jobs(
            database_url,
            import_root,
            layout_records=options.layout_records,
            selection_images=options.selection_images,
        )
        state.record("fixtures_seeded")
        general, general_token, general_out, general_err = start_worker(
            database_url, root, lane="general", budget=2
        )
        selection, selection_token, selection_out, selection_err = start_worker(
            database_url, root, lane="image-selection", budget=4
        )
        processes.extend((general, selection))
        handles.extend((general_out, general_err, selection_out, selection_err))
        tokens.update({"general": general_token, "image_selection": selection_token})
        deadline = time.monotonic() + options.timeout_seconds
        metrics_tuple = (
            process_metrics["general"],
            process_metrics["image_selection"],
        )
        process_tuple = (general, selection)

        wait_until(
            lambda: all(value == "running" for value in lane_states(database_url).values()),
            deadline=deadline,
            processes=process_tuple,
            metrics=metrics_tuple,
        )
        state.record("both_lanes_running", laneStates=lane_states(database_url))

        def both_processing() -> bool:
            assert import_job_id is not None and selection_job_id is not None
            general_job = job_snapshot(database_url, import_job_id)
            selection_job = job_snapshot(database_url, selection_job_id)
            if (
                general_job["status"] is JobStatus.PROCESSING
                and selection_job["status"] is JobStatus.PROCESSING
            ):
                state.simultaneous_processing_observed = True
                return True
            return False

        wait_until(
            both_processing,
            deadline=deadline,
            processes=process_tuple,
            metrics=metrics_tuple,
        )
        selection_before = job_snapshot(database_url, selection_job_id)
        state.record(
            "simultaneous_processing",
            importJob=job_snapshot(database_url, import_job_id),
            selectionJob=selection_before,
        )
        cancel_job(database_url, import_job_id)
        state.record("general_cancel_requested")

        wait_until(
            lambda: job_snapshot(database_url, import_job_id)["status"]
            is JobStatus.CANCELLED,
            deadline=deadline,
            processes=process_tuple,
            metrics=metrics_tuple,
        )
        selection_after = job_snapshot(database_url, selection_job_id)
        selection_before_current = selection_before["current"]
        selection_after_current = selection_after["current"]
        if not isinstance(selection_before_current, int) or not isinstance(
            selection_after_current, int
        ):
            raise RuntimeError("Image-selection progress is not an integer.")
        state.selection_progress_during_general_cancel = (
            selection_after["status"] is not JobStatus.CANCELLED
            and selection_after_current >= selection_before_current
        )
        if not state.selection_progress_during_general_cancel:
            raise RuntimeError("Cancelling general disturbed image-selection progress.")
        state.record("general_cancelled_selection_preserved", selectionJob=selection_after)

        retry_job(database_url, import_job_id)
        state.record("general_retried")

        def both_terminal() -> bool:
            general_job = job_snapshot(database_url, import_job_id)
            selection_job = job_snapshot(database_url, selection_job_id)
            return (
                general_job["status"] in TERMINAL_STATUSES
                and selection_job["status"] in TERMINAL_STATUSES
            )

        wait_until(
            both_terminal,
            deadline=deadline,
            processes=process_tuple,
            metrics=metrics_tuple,
        )
        final_general = job_snapshot(database_url, import_job_id)
        final_selection = job_snapshot(database_url, selection_job_id)
        if final_general["status"] is not JobStatus.COMPLETED:
            raise RuntimeError(f"Retried general job ended as {final_general['status']}.")
        if final_selection["status"] is JobStatus.FAILED:
            raise RuntimeError("Image-selection job failed during concurrent acceptance.")
        state.record(
            "workflows_terminal",
            importJob=final_general,
            selectionJob=final_selection,
        )
    except Exception as error:  # noqa: BLE001 - report must persist every failure
        failure = f"{type(error).__name__}: {error}"
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for handle in handles:
            handle.close()
        try:
            if tokens:
                stop_lane(database_url, WorkerLaneName.GENERAL, tokens["general"])
                stop_lane(
                    database_url,
                    WorkerLaneName.IMAGE_SELECTION,
                    tokens["image_selection"],
                )
                stopped_states = lane_states(database_url)
                if any(value != "stopped" for value in stopped_states.values()):
                    raise RuntimeError(f"Worker lanes did not stop cleanly: {stopped_states}")
                state.record("both_lanes_stopped", laneStates=stopped_states)
        except Exception as stop_error:  # noqa: BLE001
            if failure is None:
                failure = f"{type(stop_error).__name__}: {stop_error}"

        report = {
            "schemaVersion": 1,
            "acceptanceProfile": "v0.4-concurrent-real-worker-lanes",
            "generatedAt": datetime.now(UTC).isoformat(),
            "status": "passed" if failure is None else "failed",
            "decision": "passed" if failure is None else "failed",
            "includesOwnerData": False,
            "isolatedPostgres": True,
            "configuration": {
                "selectionImages": options.selection_images,
                "layoutRecords": options.layout_records,
                "timeoutSeconds": options.timeout_seconds,
                "generalThreadBudget": 2,
                "imageSelectionThreadBudget": 4,
                "imageSelectionNativeThreadBudget": 1,
                "platform": sys.platform,
                "logicalCpuCount": os.cpu_count(),
            },
            "observations": {
                "simultaneousProcessing": state.simultaneous_processing_observed,
                "selectionPreservedDuringGeneralCancel": (
                    state.selection_progress_during_general_cancel
                ),
                "durationSeconds": round(time.monotonic() - state.started_at, 3),
                "processes": {
                    name: {
                        "peakWorkingSetBytes": value.peak_working_set_bytes,
                        "cpuSeconds": round(value.cpu_seconds, 3),
                        "readBytes": value.read_bytes,
                        "writeBytes": value.write_bytes,
                        "samples": value.samples,
                    }
                    for name, value in process_metrics.items()
                },
            },
            "events": state.events,
            "failure": failure,
        }
        output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        try:
            drop_database(database_url)
        finally:
            resolved_temp_root = (REPOSITORY_ROOT / ".pytest-tmp").resolve()
            resolved_root = root.resolve()
            if resolved_root.parent == resolved_temp_root and resolved_root.name.startswith(
                "v04-concurrent-"
            ):
                shutil.rmtree(resolved_root, ignore_errors=True)

    print(f"Acceptance report: {output}")
    if failure is not None:
        print(failure, file=sys.stderr)
        return 1
    print("Concurrent real worker lane acceptance passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
