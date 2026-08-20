import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.reviewer_ingress import (
    ReviewerIngressError,
    ReviewerIngressService,
    ReviewerIngressStatus,
    _normalized_subprocess_environment,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app


def _completed(
    payload: dict[str, object], *, returncode: int = 0
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=[],
        returncode=returncode,
        stdout=json.dumps(payload),
        stderr="",
    )


def test_windows_command_environment_collapses_path_casing() -> None:
    normalized = _normalized_subprocess_environment(
        {
            "Path": r"C:\Windows;C:\Tools",
            "PATH": r"c:\tools;C:\Project",
            "TEMP": r"C:\Temp-A",
            "temp": r"C:\Temp-B",
        },
        windows=True,
    )

    assert [key for key in normalized if key.casefold() == "path"] == ["Path"]
    assert normalized["Path"] == r"C:\Windows;C:\Tools;C:\Project"
    assert len([key for key in normalized if key.casefold() == "temp"]) == 1
    assert normalized["TEMP"] == r"C:\Temp-B"


def test_non_windows_command_environment_preserves_case_distinct_names() -> None:
    environment = {"Path": "/first", "PATH": "/second"}

    assert _normalized_subprocess_environment(environment, windows=False) == environment


def test_ingress_service_runs_only_fixed_bounded_controller(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    for script_name in (
        "start_remote_reviewer_tunnel.ps1",
        "start_local_reviewer.ps1",
        "get_remote_reviewer_tunnel_status.ps1",
        "stop_remote_reviewer_tunnel.ps1",
    ):
        (scripts / script_name).write_text("# controlled", encoding="utf-8")

    calls: list[tuple[list[str], Path, float]] = []

    def runner(
        command: list[str] | tuple[str, ...],
        working_directory: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), working_directory, timeout_seconds))
        return _completed(
            {
                "state": "running",
                "publicOrigin": "https://safe-name.trycloudflare.com",
                "target": "http://127.0.0.1:3001",
                "startedAt": "2026-07-31T12:00:00+02:00",
                "reviewerReady": True,
                "instanceId": "11111111-2222-3333-4444-555555555555",
            }
        )

    service = ReviewerIngressService(
        tmp_path,
        powershell_executable="powershell.exe",
        runner=runner,
        request_id_factory=lambda: UUID(int=1),
    )

    status = service.start()

    assert status.state == "running"
    assert status.public_origin == "https://safe-name.trycloudflare.com"
    assert status.instance_id == UUID("11111111-2222-3333-4444-555555555555")
    assert calls == [
        (
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(scripts / "start_remote_reviewer_tunnel.ps1"),
                "-Json",
                "-ResultPath",
                str(
                    tmp_path
                    / ".runtime"
                    / "reviewer-ingress-controller-results"
                    / "00000000-0000-0000-0000-000000000001.json"
                ),
            ],
            tmp_path,
            60,
        )
    ]


def test_ingress_service_starts_only_the_loopback_reviewer_without_public_origin(
    tmp_path: Path,
) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "start_local_reviewer.ps1"
    script.write_text("# controlled", encoding="utf-8")
    calls: list[tuple[list[str], Path, float]] = []

    def runner(
        command: list[str] | tuple[str, ...],
        working_directory: Path,
        timeout_seconds: float,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((list(command), working_directory, timeout_seconds))
        return _completed(
            {
                "state": "running",
                "publicOrigin": None,
                "target": "http://127.0.0.1:3001",
                "startedAt": "2026-08-15T20:00:00+02:00",
                "reviewerReady": True,
            }
        )

    service = ReviewerIngressService(
        tmp_path,
        runner=runner,
        request_id_factory=lambda: UUID(int=2),
    )

    status = service.start_local()

    assert status.state == "running"
    assert status.public_origin is None
    assert status.target == "http://127.0.0.1:3001"
    assert calls == [
        (
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(script),
                "-Json",
                "-ResultPath",
                str(
                    tmp_path
                    / ".runtime"
                    / "reviewer-ingress-controller-results"
                    / "00000000-0000-0000-0000-000000000002.json"
                ),
            ],
            tmp_path,
            30,
        )
    ]


def test_local_reviewer_start_rejects_a_public_or_non_loopback_result(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "start_local_reviewer.ps1").write_text("# controlled", encoding="utf-8")
    service = ReviewerIngressService(
        tmp_path,
        runner=lambda _command, _cwd, _timeout: _completed(
            {
                "state": "running",
                "publicOrigin": "https://unexpected.example",
                "target": "https://unexpected.example",
                "startedAt": None,
                "reviewerReady": True,
            }
        ),
    )

    with pytest.raises(ReviewerIngressError) as raised:
        service.start_local()

    assert raised.value.code == "REVIEWER_INGRESS_INVALID_RESPONSE"


def test_ingress_service_fails_closed_for_invalid_or_failed_output(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "start_remote_reviewer_tunnel.ps1"
    script.write_text("# controlled", encoding="utf-8")

    invalid = ReviewerIngressService(
        tmp_path,
        runner=lambda _command, _cwd, _timeout: subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"state":"running","publicOrigin":null}',
            stderr="sensitive",
        ),
    )
    with pytest.raises(ReviewerIngressError) as invalid_error:
        invalid.start()
    assert invalid_error.value.code == "REVIEWER_INGRESS_INVALID_RESPONSE"

    failed = ReviewerIngressService(
        tmp_path,
        runner=lambda _command, _cwd, _timeout: _completed(
            {
                "state": "error",
                "message": "Reviewer production build is missing.",
            },
            returncode=1,
        ),
    )
    with pytest.raises(ReviewerIngressError) as failed_error:
        failed.start()
    assert failed_error.value.code == "REVIEWER_INGRESS_COMMAND_FAILED"
    assert "sensitive" not in failed_error.value.message


def test_compare_stop_passes_only_the_expected_instance_fence(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    stop_script = scripts / "stop_remote_reviewer_tunnel.ps1"
    stop_script.write_text("# controlled", encoding="utf-8")
    calls: list[list[str]] = []
    instance_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

    def runner(command, _working_directory, _timeout_seconds):
        calls.append(list(command))
        return _completed(
            {
                "state": "stopped",
                "publicOrigin": None,
                "target": "http://127.0.0.1:3001",
                "startedAt": None,
                "reviewerReady": None,
                "instanceId": None,
            }
        )

    service = ReviewerIngressService(
        tmp_path,
        runner=runner,
        request_id_factory=lambda: UUID(int=3),
    )

    status = service.stop_if_current(instance_id)

    assert status.state == "stopped"
    assert calls[0][-2:] == ["-ExpectedInstanceId", str(instance_id)]


def test_independent_api_processes_use_unique_controller_result_paths(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "get_remote_reviewer_tunnel_status.ps1").write_text(
        "# controlled",
        encoding="utf-8",
    )
    barrier = Barrier(2)
    result_paths: list[str] = []

    def runner(command, _working_directory, _timeout_seconds):
        result_paths.append(command[command.index("-ResultPath") + 1])
        barrier.wait(timeout=2)
        return _completed(
            {
                "state": "stopped",
                "publicOrigin": None,
                "target": "http://127.0.0.1:3001",
                "startedAt": None,
                "reviewerReady": False,
                "instanceId": None,
            }
        )

    services = (
        ReviewerIngressService(
            tmp_path,
            runner=runner,
            request_id_factory=lambda: UUID(int=4),
        ),
        ReviewerIngressService(
            tmp_path,
            runner=runner,
            request_id_factory=lambda: UUID(int=5),
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        states = list(executor.map(lambda service: service.status(), services))

    assert [state.state for state in states] == ["stopped", "stopped"]
    assert len(set(result_paths)) == 2
    assert all("reviewer-ingress-controller-results" in path for path in result_paths)


class _FakeIngress:
    def __init__(self) -> None:
        self.state = "stopped"
        self.calls: list[str] = []

    def status(self) -> ReviewerIngressStatus:
        self.calls.append("status")
        return self._response()

    def start(self) -> ReviewerIngressStatus:
        self.calls.append("start")
        self.state = "running"
        return self._response()

    def start_local(self) -> ReviewerIngressStatus:
        self.calls.append("start_local")
        return ReviewerIngressStatus(
            state="running",
            public_origin=None,
            target="http://127.0.0.1:3001",
            started_at=datetime(2026, 8, 15, 18, 0, tzinfo=UTC),
            reviewer_ready=True,
        )

    def stop(self) -> ReviewerIngressStatus:
        self.calls.append("stop")
        self.state = "stopped"
        return self._response()

    def _response(self) -> ReviewerIngressStatus:
        running = self.state == "running"
        return ReviewerIngressStatus(
            state=self.state,  # type: ignore[arg-type]
            public_origin=("https://safe-name.trycloudflare.com" if running else None),
            target="http://127.0.0.1:3001",
            started_at=datetime(2026, 7, 31, 10, 0, tzinfo=UTC) if running else None,
            reviewer_ready=True,
        )


def test_admin_ingress_endpoints_require_explicit_target_confirmation() -> None:
    ingress = _FakeIngress()
    app = create_app(
        ApiSettings.from_environment({}),
        reviewer_ingress_service_dependency=lambda: ingress,
    )

    with TestClient(app) as client:
        initial = client.get("/api/v1/admin/reviewer-ingress")
        assert initial.status_code == 200
        assert initial.json()["state"] == "stopped"

        rejected = client.post(
            "/api/v1/admin/reviewer-ingress/start",
            json={"confirmed": False, "target": "remote-reviewer"},
        )
        assert rejected.status_code == 422

        started = client.post(
            "/api/v1/admin/reviewer-ingress/start",
            json={"confirmed": True, "target": "remote-reviewer"},
        )
        assert started.status_code == 200
        assert started.json()["publicOrigin"].endswith(".trycloudflare.com")

        local_started = client.post(
            "/api/v1/admin/reviewer-local/start",
            json={"confirmed": True, "target": "local-reviewer"},
        )
        assert local_started.status_code == 200
        assert local_started.json()["state"] == "running"
        assert local_started.json()["publicOrigin"] is None
        assert local_started.json()["target"] == "http://127.0.0.1:3001"

        stopped = client.post(
            "/api/v1/admin/reviewer-ingress/stop",
            json={"confirmed": True, "target": "remote-reviewer"},
        )
        assert stopped.status_code == 200
        assert stopped.json()["state"] == "stopped"

    assert ingress.calls == ["status", "start", "start_local", "stop"]
