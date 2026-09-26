"""T08: the source-run release works in fresh processes after Alembic 0125.

Only a uniquely named disposable database and pytest's temporary directory are
mutated. This is a bounded release smoke, not the historical M2 acceptance suite.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import UUID, uuid4

import pytest
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.catalog import GameStatus
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.storage.database import GameStorageSession
from game_predictor_api.storage.game_data_v2_manifest_v1 import CATALOG, CONTROL_TABLES, GAME_TABLES
from game_predictor_api.storage.game_data_v2_manifest_v2 import SHARED
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from game_predictor_api.storage.models import DatasetVersionModel, GameModel, LayoutModel
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[4]
REVISION = "0125_remove_legacy_public_game_store"
API = "/api/v1/admin"
PROBE = Path(__file__).with_name("legacy_release_process_probe.py")
pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)


def _run(arguments: list[str], environment: dict[str, str], *, timeout: int = 60) -> str:
    process = subprocess.Popen(
        arguments,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        assert process.returncode == 0, stdout + stderr
        return stdout.strip()
    finally:
        _stop(process)


def _source_identity() -> dict[str, str]:
    """Pin the actual source artifact; a commit alone misses uncommitted code."""
    paths = [ROOT / name for name in ("pyproject.toml", "package.json", "alembic.ini")]
    for directory in ("services/api/src", "services/worker/src", "services/api/alembic"):
        paths.extend(
            path for path in (ROOT / directory).rglob("*") if path.suffix in {".py", ".sql"}
        )
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {
        "gitRevision": _run(["git", "rev-parse", "HEAD"], dict(os.environ), timeout=10),
        "sourceSha256": digest.hexdigest(),
        "pythonExecutable": sys.executable,
        "pythonVersion": sys.version,
        "deployment": "source-run: python -m game_predictor_api / game_predictor_worker",
    }


@pytest.fixture
def isolated_release_database(tmp_path: Path) -> Iterator[tuple[Engine, dict[str, str]]]:
    name = "game_predictor_t08_" + uuid4().hex
    assert re.fullmatch(r"game_predictor_t08_[0-9a-f]{32}", name)
    configured = make_url(ApiSettings.from_environment().database_url)
    url = configured.set(database=name)
    maintenance = create_engine(
        configured.set(database="postgres"),
        isolation_level="AUTOCOMMIT",
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
    engine = create_engine(
        url, connect_args={"connect_timeout": 5, "options": "-c statement_timeout=15000"}
    )
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("GAME_PREDICTOR_")
    }
    environment.update(
        {
            "GAME_PREDICTOR_DATABASE_URL": url.render_as_string(hide_password=False),
            "GAME_PREDICTOR_API_HOST": "127.0.0.1",
            "GAME_PREDICTOR_ADMIN_ORIGIN": "http://127.0.0.1:3000",
            "GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts"),
            "GAME_PREDICTOR_IMPORT_ROOT": str(tmp_path / "imports"),
            "GAME_PREDICTOR_REVIEW_CROP_ROOT": str(tmp_path / "crops"),
            "GAME_PREDICTOR_REVIEW_SOURCE_ROOT": str(tmp_path / "sources"),
            "GAME_PREDICTOR_V7_LABEL_GEOMETRY_RUNTIME_ROOT": str(tmp_path / "runtime"),
            "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=2000",
            "PYTHONUNBUFFERED": "1",
        }
    )
    with maintenance.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    try:
        _run([sys.executable, "-m", "alembic", "upgrade", REVISION], environment, timeout=120)
        print(f"T08 isolated database {name}: {REVISION}", flush=True)
        yield engine, environment
    finally:
        engine.dispose()
        try:
            with maintenance.connect() as connection:
                assert (
                    connection.scalar(
                        text("SELECT count(*) FROM pg_stat_activity WHERE datname=:name"),
                        {"name": name},
                    )
                    == 0
                ), "A smoke process still owns a connection; do not force-drop its database."
                connection.exec_driver_sql(f'DROP DATABASE "{name}"')
        finally:
            maintenance.dispose()


def _http(
    base: str,
    path: str,
    *,
    status: int = 200,
    payload: dict[str, object] | None = None,
    method: str = "GET",
    timeout: float = 10,
) -> Any:
    request = Request(
        base + path,
        data=None if payload is None else json.dumps(payload).encode(),
        method=method,
        headers={
            "Content-Type": "application/json",
            "Origin": "http://127.0.0.1:3000",
            "X-Admin-Intent": "local-owner",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            actual_status, body = response.status, response.read().decode()
    except HTTPError as error:
        actual_status, body = error.code, error.read().decode()
    assert actual_status == status, f"{method} {path}: {actual_status} {body}"
    return json.loads(body)


def _stop(process: subprocess.Popen[Any]) -> None:
    if process.poll() is None:
        if os.name == "nt":
            # The Windows venv launcher may own another interpreter PID.
            # Stop this exact owned tree, including a child on timeout.
            stopped = subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            assert stopped.returncode == 0 or process.poll() is not None, stopped.stderr
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    assert process.poll() is not None


@contextmanager
def _api_process(
    environment: dict[str, str],
    log: Path,
) -> Iterator[tuple[str, int]]:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    child_environment = {**environment, "GAME_PREDICTOR_API_PORT": str(port)}
    base = f"http://127.0.0.1:{port}"
    marker = log.with_suffix(".json")
    with log.open("wb") as output:
        process = subprocess.Popen(
            [sys.executable, str(PROBE), "api", str(marker)],
            cwd=ROOT,
            env=child_environment,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        try:
            # Cold imports take ~13 s on the Windows host. Initialization has
            # its own explicit bound; HTTP readiness still has a 10 s budget.
            initialization_deadline = time.monotonic() + 30
            while not marker.exists() and time.monotonic() < initialization_deadline:
                assert process.poll() is None, log.read_text(encoding="utf-8")
                time.sleep(0.1)
            assert marker.exists(), "API initialization exceeded 30 seconds."
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                assert process.poll() is None, log.read_text(encoding="utf-8")
                try:
                    _http(base, API + "/games", timeout=min(0.5, deadline - time.monotonic()))
                    break
                except (URLError, TimeoutError):
                    time.sleep(min(0.1, max(0, deadline - time.monotonic())))
            else:
                pytest.fail("API readiness exceeded 10 seconds: " + log.read_text(encoding="utf-8"))
            probe = json.loads(marker.read_text(encoding="utf-8"))
            assert Path(probe["pythonExecutable"]) == Path(sys.executable)
            assert Path(probe["modulePath"]) == ROOT / "services/api/src/game_predictor_api/main.py"
            yield base, probe["pid"]
        finally:
            _stop(process)


def _schema_contract(engine: Engine) -> None:
    inspector = inspect(engine)
    public = set(inspector.get_table_names(schema="public"))
    assert len(GAME_TABLES) == 65
    assert not public.intersection(GAME_TABLES)
    assert set(CATALOG) | set(SHARED) | set(CONTROL_TABLES) <= public
    assert set(GAME_TABLES) <= set(inspector.get_table_names(schema="game_data_v2"))
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM public.alembic_version")) == REVISION


def _seed_layouts(engine: Engine, game_id: UUID) -> UUID:
    dataset_id = uuid4()
    with GameStorageSession(engine) as session, session.begin():
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.WRITE)
        session.add(
            DatasetVersionModel(
                id=dataset_id,
                game_id=game_id,
                version=1,
                rows=1,
                columns=1,
                signature_cell_width=1,
                expected_layout_count=2,
                layout_count=2,
                status=DatasetVersionStatus.STAGING,
                generation_seed=687,
                generator_version="t08-two-layout-fixture",
            )
        )
        session.flush()
        session.add_all(
            [
                LayoutModel(
                    dataset_version_id=dataset_id,
                    sequence_number=sequence,
                    signature=str(sequence),
                    cells=[sequence],
                )
                for sequence in (1, 2)
            ]
        )
    return dataset_id


def test_fresh_api_and_worker_release_is_v2_only(
    isolated_release_database: tuple[Engine, dict[str, str]],
    tmp_path: Path,
) -> None:
    engine, environment = isolated_release_database
    failures: list[str] = []
    identity = _source_identity()
    _schema_contract(engine)
    with _api_process(environment, tmp_path / "api-first.log") as (base, first_pid):
        game = _http(
            base,
            API + "/games",
            method="POST",
            status=201,
            payload={
                "code": "t08-readiness",
                "name": "T08 readiness",
                "status": "active",
                "expectedLayoutCount": 2,
            },
        )
        game_id = UUID(game["id"])
        assert game["storageSchema"] == "game_data_v2"
        assert game["storageGeneration"] == 2
        assert game["storageWriteAvailable"] is True
        dataset_id = _seed_layouts(engine, game_id)
        datasets = _http(base, f"{API}/games/{game_id}/dataset-versions")
        assert [item["id"] for item in datasets] == [str(dataset_id)]
        status_path = f"{API}/games/{game_id}/image-geometry-rollout"
        readiness_key = "backfillStatus"
        try:
            rollout = _http(base, status_path, method="POST", status=202)
            job_id = rollout["job"]["id"]
        except AssertionError as error:
            failures.append(str(error))
            # Keep the failed rollout assertion while still obtaining an
            # independent worker result from another production V2 handler.
            status_path = f"{API}/games/{game_id}/symbol-cell-review-projection"
            readiness_key = "status"
            projection = _http(base, status_path, method="POST")
            job_id = projection["jobId"]
        assert job_id is not None

    # The API is stopped before the real worker claims its persisted job.
    worker_command = [
        sys.executable,
        str(PROBE),
        "worker",
        str(tmp_path / "worker-first.json"),
        "--lane",
        "general",
        "--cpu-thread-budget",
        "1",
        "--artifact-root",
        environment["GAME_PREDICTOR_ARTIFACT_ROOT"],
    ]
    worker_output = _run(worker_command, environment)
    assert worker_output.splitlines()[-1] == "completed", worker_output
    print("T08 fresh worker completed the persisted V2 projection job", flush=True)
    with _api_process(environment, tmp_path / "api-restarted.log") as (base, second_pid):
        assert first_pid != second_pid
        job = _http(base, f"{API}/jobs/{job_id}")
        assert job["status"] == "completed"
        status = _http(base, status_path)
        assert status[readiness_key] == "ready"
        try:
            layouts = _http(base, f"{API}/dataset-versions/{dataset_id}/layouts")
            assert [item["sequenceNumber"] for item in layouts["items"]] == [1, 2]
        except AssertionError as error:
            failures.append(str(error))
        try:
            _http(base, f"{API}/review-batches")
        except AssertionError as error:
            failures.append(str(error))
        missing_id = uuid4()
        with Session(engine) as session, session.begin():
            session.add(
                GameModel(
                    id=missing_id,
                    code="missing-location",
                    name="Missing location",
                    status=GameStatus.ACTIVE,
                )
            )
        failure = _http(base, f"{API}/games/{missing_id}/dataset-versions", status=409)
        assert failure["code"] == "GAME_STORAGE_LOCATION_MISSING"
        catalog = _http(base, API + "/games")
        assert {item["id"] for item in catalog} == {str(game_id), str(missing_id)}
    worker_command[3] = str(tmp_path / "worker-restarted.json")
    assert _run(worker_command, environment).splitlines()[-1] == "no_job"
    _schema_contract(engine)
    assert _source_identity() == identity, "Release sources changed during the smoke."
    report = {
        **identity,
        "alembicRevision": REVISION,
        "database": engine.url.database,
        "apiPids": [first_pid, second_pid],
        "workerCommand": worker_command,
        "processProbes": [
            json.loads((tmp_path / name).read_text(encoding="utf-8"))
            for name in (
                "api-first.json",
                "api-restarted.json",
                "worker-first.json",
                "worker-restarted.json",
            )
        ],
        "configuration": {
            key: value
            for key, value in environment.items()
            if key.startswith("GAME_PREDICTOR_") and key != "GAME_PREDICTOR_DATABASE_URL"
        },
        "legacyPublicAbsent": 65,
        "catalogControlSharedRetained": True,
        "workerResult": "completed; fresh worker no_job",
        "missingLocation": "409 fail-closed",
        "failures": failures,
        "result": "no-go" if failures else "smoke passed; final T08 review remains separate",
    }
    print("T08_READINESS " + json.dumps(report, sort_keys=True))
    (tmp_path / "release-readiness.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    assert not failures, "\n".join(failures)
