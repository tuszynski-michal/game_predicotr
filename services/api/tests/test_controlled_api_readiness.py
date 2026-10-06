import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.request import urlopen

import pytest

ROOT = Path(__file__).resolve().parents[3]
POWERSHELL = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
pytestmark = pytest.mark.skipif(
    os.name != "nt" or POWERSHELL is None, reason="Windows PowerShell is required."
)


@pytest.fixture
def healthy_listener():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"status": "ok"}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _fixture_script(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    script = scripts / "start_controlled_api.ps1"
    shutil.copyfile(ROOT / "scripts" / script.name, script)
    (scripts / "windows_process_environment.ps1").write_text(
        "function Repair-WindowsProcessPath {}\n", encoding="utf-8"
    )
    python = tmp_path / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    python.touch()
    return script


def _run(script: str, environment: dict[str, str]):
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=os.environ | environment,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _assert_old_listener_healthy(port: int):
    with urlopen(f"http://127.0.0.1:{port}/api/v1/health", timeout=2) as response:
        assert json.load(response) == {"status": "ok"}


def test_existing_healthy_api_does_not_start_or_report_a_second_api(
    tmp_path: Path, healthy_listener: int
):
    script = _fixture_script(tmp_path)
    result = _run(
        "& $env:GP_START_SCRIPT -Port $env:GP_TEST_PORT -TimeoutSeconds 1 -StateName guard",
        {"GP_START_SCRIPT": str(script), "GP_TEST_PORT": str(healthy_listener)},
    )
    assert result.returncode != 0
    assert "already occupied" in result.stderr
    assert not (tmp_path / ".runtime").exists()
    _assert_old_listener_healthy(healthy_listener)


@pytest.mark.parametrize("ownership_failure", ["foreign_listener", "query_error"])
def test_health_from_another_process_cannot_satisfy_api_readiness(
    tmp_path: Path, healthy_listener: int, ownership_failure: str
):
    script = _fixture_script(tmp_path)
    result = _run(
        """
$global:gpListenerQueries = 0
function Get-NetTCPConnection {
    $global:gpListenerQueries += 1
    if ($global:gpListenerQueries -eq 1) { return }
    [pscustomobject]@{ OwningProcess = [int]$env:GP_FOREIGN_PID }
}
function Get-CimInstance {
    if ($env:GP_FAILURE_MODE -eq 'query_error') { throw 'ownership query failed' }
    return @()
}
function Start-Process {
    [IO.File]::WriteAllText($env:GP_START_COUNT, '1')
    [pscustomobject]@{ Id = $PID }
}
& $env:GP_START_SCRIPT -Port $env:GP_TEST_PORT -TimeoutSeconds 1 -StateName guard
""",
        {
            "GP_START_SCRIPT": str(script),
            "GP_TEST_PORT": str(healthy_listener),
            "GP_FOREIGN_PID": str(os.getpid()),
            "GP_FAILURE_MODE": ownership_failure,
            "GP_START_COUNT": str(tmp_path / "starts.txt"),
        },
    )
    assert result.returncode != 0
    assert "Controlled API did not become ready" in result.stderr
    assert (tmp_path / "starts.txt").read_text() == "1"
    _assert_old_listener_healthy(healthy_listener)
