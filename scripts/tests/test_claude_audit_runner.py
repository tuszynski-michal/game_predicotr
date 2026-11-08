"""Subprocess regression tests. All CLI traffic is fake; git belongs to fixtures."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.run_claude_audit import AuditError, validate_report

RUNNER = Path(__file__).resolve().parents[1] / "run_claude_audit.py"
ARTIFACTS = RUNNER.parents[1] / "artifacts"
FAKE_CLI = r'''
import hashlib, json, os, subprocess, sys, time
from pathlib import Path
prompt = sys.stdin.read()
payload = prompt.split("\n\n", 1)[1]
config = json.loads(payload)
mode = config["mode"]
with Path(config["calls"]).open("a") as log:
    log.write(json.dumps({"args": sys.argv[1:], "cwd": os.getcwd()}) + "\n")
sha = hashlib.sha256(payload.encode()).hexdigest()
report = f"""# Audyt TASK-1163 — Runner

Werdykt: PASS
Audytor: claude-opus-5-5/high
Wykonawca: gpt-6.1-sol/high
Zakres: fixture
Runda: 1
SHA pakietu: {sha}
Otwarte P0: 0
Otwarte P1: 0

Przegląd statyczny, bez zmian w plikach.

## Streszczenie
Sprawdzono fixture.
## Znaleziska
### P0
Brak.
### P1
Brak.
### P2
Brak.
## Pokrycie kryteriów akceptacji
Spełnione.
## Listy zamknięte i otwarte
Zamknięte: Brak.
Otwarte: Brak.
## Proponowane testy
Brak.
## Zakres przeglądu i ograniczenia
Przegląd statyczny bez testów.
"""
if mode in ("revise", "open_p1", "undeclared"):
    report = report.replace("### P1\nBrak.", "### P1\n- [P1-1] `a.py:1` — błąd.")
    if mode != "undeclared":
        report = report.replace("Otwarte P1: 0", "Otwarte P1: 1")
        report = report.replace("Otwarte: Brak.", "Otwarte: P1-1")
    if mode == "revise":
        report = report.replace("Werdykt: PASS", "Werdykt: REVISE")
if mode in ("oauth_topic", "error_exit_oauth_topic"):
    report = report.replace("Sprawdzono fixture.", "Sprawdzono błędy OAuth i rate limit w audycie.")
if mode == "conflict":
    report += "\nWerdykt: REVISE\n"
if mode == "incomplete":
    report = report.replace("### P1\nBrak.\n", "")
if mode == "wrong_sha":
    report = report.replace(sha, "0" * 64)
Path(config["raw"]).write_text(report, encoding="utf-8")
def emit(value):
    print(json.dumps(value), flush=True)
model = "claude-other" if mode == "wrong_model" else "claude-opus-5-5"
if mode != "no_init":
    emit({"type":"system", "subtype":"init", "model":model, "session_id":"fake-session"})
if mode in ("hang", "noise", "child"):
    if mode == "child":
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        Path(config["child"]).write_text(str(child.pid))
    for _ in range(300):
        if mode == "noise": print("not a stream event", flush=True)
        time.sleep(.1)
if mode == "slow_events":
    for _ in range(20):
        emit({"type":"stream_event", "event":{"type":"content_block_delta"}})
        time.sleep(.3)
if mode in ("oauth", "rate"):
    message = ("OAuth token expired access_token=secret-test-token-123456789"
               if mode == "oauth" else "rate_limit_error")
    emit({"type":"result", "subtype":"error_during_execution", "is_error":True, "result":message})
    sys.exit(1)
if mode == "no_result": sys.exit(0)
final = {"type":"result", "subtype":"success", "is_error":False, "result":report,
    "modelUsage":{"claude-opus-5-5":{}, "claude-helper":{}}}
if mode in ("error_exit", "error_exit_oauth_topic"):
    emit(final)
    sys.exit(1)
if mode == "error_result": final["is_error"] = True
emit(final)
'''


def git(repo: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *arguments], check=True, capture_output=True, timeout=20
    )


@pytest.fixture(scope="module")
def disposable_worktree() -> Iterator[Path]:
    ARTIFACTS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audit-runner-test-", dir=ARTIFACTS) as directory:
        root = Path(directory)
        seed = root / "seed"
        seed.mkdir()
        git(seed, "init")
        git(
            seed,
            "-c",
            "user.name=Audit fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--allow-empty",
            "-m",
            "fixture",
        )
        worktree = root / "worktree"
        git(seed, "worktree", "add", "--detach", str(worktree))
        (worktree / "fake_cli.py").write_text(FAKE_CLI, encoding="utf-8")
        yield worktree


@pytest.fixture
def audit(disposable_worktree: Path) -> dict[str, Path]:
    directory = disposable_worktree / "artifacts" / "audits" / str(time.time_ns())
    directory.mkdir(parents=True)
    paths = {
        "repo": disposable_worktree,
        "brief": directory / "brief.md",
        "calls": directory / "calls",
        "raw": directory / "raw.md",
        "child": directory / "child.pid",
    }
    configure(paths, "pass")
    return paths


def configure(audit: dict[str, Path], mode: str) -> None:
    audit["brief"].write_text(
        json.dumps(
            {
                "mode": mode,
                **{name: str(audit[name]) for name in ("calls", "raw", "child")},
            }
        ),
        encoding="utf-8",
    )


def command(audit: dict[str, Path], *extra: str) -> list[str]:
    return [
        sys.executable,
        str(RUNNER),
        "--repo",
        str(audit["repo"]),
        "--task",
        "TASK-1163",
        "--brief",
        str(audit["brief"]),
        "--cli",
        sys.executable,
        "--cli-prefix",
        str(audit["repo"] / "fake_cli.py"),
        "--timeout",
        "20",
        *extra,
    ]


def invoke(audit: dict[str, Path], *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command(audit, *extra), capture_output=True, text=True, timeout=40)


def receipt(audit: dict[str, Path]) -> dict[str, object]:
    payload_sha = hashlib.sha256(audit["brief"].read_bytes()).hexdigest()
    for path in (audit["repo"] / "artifacts/audits/requests").glob("*/receipt.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        if value["payload_sha256"] == payload_sha:
            return value  # type: ignore[no-any-return]
    raise AssertionError("receipt not found")


def report_path(audit: dict[str, Path]) -> Path:
    return audit["repo"] / "ai_docs/quality/TASK-1163_AUDIT_claude-opus-5-5.md"


@pytest.mark.parametrize("explicit", [False, True], ids=["default", "explicit-1800"])
def test_thirty_minute_deadline_completes_fast_fake_cli(
    audit: dict[str, Path], explicit: bool
) -> None:
    arguments = command(audit)
    index = arguments.index("--timeout")
    del arguments[index : index + 2]
    if explicit:
        arguments += ["--timeout", "1800"]
    started = time.monotonic()
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=40)
    assert result.returncode == 0, result.stderr
    assert time.monotonic() - started < 40
    assert re.search(r"total=1800(?:\.0)?s idle=60s", result.stdout)
    assert len(audit["calls"].read_text().splitlines()) == 1
    assert "Werdykt: PASS" in report_path(audit).read_text(encoding="utf-8")


@pytest.mark.parametrize("mode, verdict", [("pass", "PASS"), ("revise", "REVISE")])
def test_completed_replay_after_lost_publication(
    audit: dict[str, Path],
    mode: str,
    verdict: str,
) -> None:
    configure(audit, mode)
    first = invoke(audit)
    assert first.returncode == 0, first.stderr
    report = report_path(audit).read_bytes()
    assert f"Werdykt: {verdict}".encode() in report
    report_path(audit).unlink()  # a lost publication/response after durable completion
    second = invoke(audit)
    assert second.returncode == 0, second.stderr
    assert report_path(audit).read_bytes() == report
    assert len(audit["calls"].read_text().splitlines()) == 1
    info = json.loads(report_path(audit).with_suffix(".receipt.json").read_text())
    assert info["evidence_source"] == "cli-system.init;effort-requested-only"
    assert info["observed_model"] == "claude-opus-5-5"
    assert info["report_sha256"] == hashlib.sha256(report).hexdigest()
    call = json.loads(audit["calls"].read_text().splitlines()[0])
    assert Path(call["cwd"]).resolve() == audit["repo"].resolve()
    arguments = call["args"]
    assert arguments[arguments.index("--tools") + 1] == "Read,Glob,Grep"
    assert arguments[arguments.index("--allowedTools") + 1] == "Read,Glob,Grep"
    assert arguments[arguments.index("--mcp-config") + 1] == '{"mcpServers":{}}'
    assert arguments[arguments.index("--effort") + 1] == "high"
    assert "--strict-mcp-config" in arguments
    assert "--no-session-persistence" in arguments
    assert "--setting-sources" not in arguments


@pytest.mark.parametrize(
    "mode",
    [
        "open_p1",
        "undeclared",
        "wrong_model",
        "no_init",
        "no_result",
        "conflict",
        "error_exit",
        "error_result",
        "incomplete",
        "wrong_sha",
    ],
)
def test_fail_closed(audit: dict[str, Path], mode: str) -> None:
    configure(audit, mode)
    before = report_path(audit).read_bytes() if report_path(audit).exists() else None
    result = invoke(audit)
    assert result.returncode != 0
    assert receipt(audit)["attempts"][0]["status"] == "blocked"  # type: ignore[index]
    after = report_path(audit).read_bytes() if report_path(audit).exists() else None
    assert after == before  # an earlier report never gets overwritten by failed output
    repeated = invoke(audit)
    assert repeated.returncode == 6
    assert len(audit["calls"].read_text().splitlines()) == 1


@pytest.mark.parametrize(
    "mode, category",
    [
        ("oauth", "cli-auth;desktop-session-independent"),
        ("rate", "rate-limit"),
    ],
)
def test_auth_rate_diagnostic_and_explicit_new_attempt(
    audit: dict[str, Path],
    mode: str,
    category: str,
) -> None:
    configure(audit, mode)
    result = invoke(audit)
    assert result.returncode == 3
    value = receipt(audit)
    assert value["attempts"][0]["failure_category"] == category  # type: ignore[index]
    directory = audit["repo"] / "artifacts/audits/requests" / str(value["request_sha256"])
    diagnostic = (directory / "attempt-1-diagnostics.json").read_text()
    assert ("OAuth token expired" if mode == "oauth" else "rate_limit_error") in diagnostic
    assert "secret-test-token" not in diagnostic
    assert invoke(audit).returncode == 6
    assert invoke(audit, "--transport-attempt", "2").returncode == 3
    assert len(receipt(audit)["attempts"]) == 2  # type: ignore[arg-type]
    assert len(audit["calls"].read_text().splitlines()) == 2


@pytest.mark.parametrize("mode", ["hang", "noise", "child"])
def test_timeout_stops_owned_tree(audit: dict[str, Path], mode: str) -> None:
    configure(audit, mode)
    idle = "15" if mode == "child" else "5"
    result = invoke(audit, "--idle-timeout", idle, "--timeout", "25")
    assert result.returncode == 2, result.stderr
    value = receipt(audit)
    pid = value["attempts"][0]["pid"]  # type: ignore[index]
    if os.name == "nt":
        from ctypes import WinDLL, wintypes

        kernel = WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        for check_pid in [pid] + ([int(audit["child"].read_text())] if mode == "child" else []):
            handle = kernel.OpenProcess(0x1000, False, check_pid)
            if handle:
                code = wintypes.DWORD()
                kernel.GetExitCodeProcess.argtypes = [
                    wintypes.HANDLE,
                    ctypes.POINTER(wintypes.DWORD),
                ]
                assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
                kernel.CloseHandle(handle)
                assert code.value != 259
    assert invoke(audit).returncode == 6


def test_stream_activity_not_wall_clock_idle(audit: dict[str, Path]) -> None:
    configure(audit, "slow_events")
    result = invoke(audit, "--idle-timeout", "5")
    assert result.returncode == 0, result.stderr


def test_active_duplicate_and_interrupted_owner(audit: dict[str, Path]) -> None:
    configure(audit, "hang")
    first = subprocess.Popen(command(audit), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for _ in range(750):
            if audit["calls"].exists():
                break
            time.sleep(0.02)
        assert audit["calls"].exists()
        second = invoke(audit)
        assert second.returncode == 6
        assert "Active duplicate" in second.stderr
        assert len(audit["calls"].read_text().splitlines()) == 1
    finally:
        first.kill()
        first.communicate(timeout=10)
    # On Windows the runner's job kills the CLI when the owner dies.
    if os.name == "nt":
        rejected = invoke(audit)
        assert rejected.returncode == 6
        assert receipt(audit)["attempts"][0]["status"] == "interrupted"  # type: ignore[index]
        retry = invoke(audit, "--transport-attempt", "2", "--idle-timeout", "5")
        assert retry.returncode == 2, retry.stderr


def test_desktop_import_validates_scope_and_provenance(audit: dict[str, Path]) -> None:
    # Produce a fake report locally, then import through the same CLI validator.
    assert invoke(audit).returncode == 0
    original = audit["raw"].read_text(encoding="utf-8")
    # A different frozen package cannot reuse an old report, even with a new SHA argument.
    audit["brief"].write_text(audit["brief"].read_text() + " ")
    sha = hashlib.sha256(audit["brief"].read_bytes()).hexdigest()
    extras = [
        "--import-report",
        str(audit["raw"]),
        "--payload-sha",
        sha,
        "--observed-model",
        "claude-opus-5-5",
        "--observed-effort",
        "high",
        "--session-ref",
        "desktop-session-observed-20261108",
    ]
    rejected = invoke(audit, *extras)
    assert rejected.returncode == 4, rejected.stderr
    audit["raw"].write_text(
        __import__("re").sub(r"SHA pakietu: [a-f0-9]+", f"SHA pakietu: {sha}", original),
        encoding="utf-8",
    )
    # Import preflight failures do not consume transport attempt 1.
    imported = invoke(audit, *extras)
    assert imported.returncode == 0, imported.stderr
    info = json.loads(report_path(audit).with_suffix(".receipt.json").read_text())
    assert info["transport"] == "desktop-ui"
    assert info["evidence_source"] == "operator-ui-observation"
    assert info["effort_evidence"] == {"observed_ui": "high"}
    assert info["payload_sha256"] == sha
    assert len(audit["calls"].read_text().splitlines()) == 1


def test_tampered_completed_report_not_replayed(audit: dict[str, Path]) -> None:
    assert invoke(audit).returncode == 0
    value = receipt(audit)
    directory = audit["repo"] / "artifacts/audits/requests" / str(value["request_sha256"])
    (directory / "attempt-1-report.md").write_text("tampered")
    result = invoke(audit)
    assert result.returncode == 3
    assert "SHA mismatch" in result.stderr
    assert len(audit["calls"].read_text().splitlines()) == 1


def report_from_repository_template(payload_sha: str) -> str:
    """Render the actual copyable block, preserving its headings and list labels."""
    text = (RUNNER.parents[1] / "ai_docs/quality/AUDIT_REPORT_TEMPLATE.md").read_text(
        encoding="utf-8"
    )
    report = text.split("```markdown\n", 1)[1].split("\n```", 1)[0]
    report = report.replace("TASK-NNNN", "TASK-1163")
    report = report.replace("<SHA256 zamrożonego briefu>", payload_sha)
    report = re.sub(r"(?m)^Zamknięte: .+$", "Zamknięte: Brak.", report)
    report = re.sub(r"(?m)^Otwarte: .+$", "Otwarte: Brak.", report)
    for severity in ("P0", "P1", "P2"):
        report = re.sub(
            rf"(?ms)(^### {severity}\n).*?(?=^### |^## |\Z)",
            r"\1\nBrak.\n\n",
            report,
        )
    return re.sub(r"<[^>]+>", "Fixture.", report)


@pytest.mark.parametrize("mode", ["round1_closed", "overlap", "unnumbered_P0", "unnumbered_P1"])
def test_finding_lists_cannot_hide_findings(mode: str) -> None:
    sha = "f" * 64
    report = report_from_repository_template(sha)
    review_round = 1
    if mode.startswith("unnumbered_"):
        severity = mode.split("_", 1)[1]
        report = report.replace(f"### {severity}\n\nBrak.", f"### {severity}\n\nWykryto błąd.")
    else:
        report = report.replace("### P1\n\nBrak.", "### P1\n\n- [P1-1] `a.py:1` — błąd.")
        report = report.replace("Zamknięte: Brak.", "Zamknięte: P1-1")
        if mode == "overlap":
            review_round = 2
            report = report.replace("Runda: 1", "Runda: 2")
            report = report.replace("Otwarte: Brak.", "Otwarte: P1-1")
            report = report.replace("Otwarte P1: 0", "Otwarte P1: 1")
            report = report.replace("Werdykt: PASS", "Werdykt: REVISE")
    with pytest.raises(AuditError) as caught:
        validate_report(report, "TASK-1163", review_round, sha)
    assert caught.value.code == 4


def test_round_two_can_record_closed_finding_from_template() -> None:
    sha = "f" * 64
    report = report_from_repository_template(sha).replace("Runda: 1", "Runda: 2")
    report = report.replace("### P1\n\nBrak.", "### P1\n\n- [P1-1] `a.py:1` — poprawiono.")
    report = report.replace("Zamknięte: Brak.", "Zamknięte: P1-1 — a.py:1 poprawiono.")
    assert validate_report(report, "TASK-1163", 2, sha) == "PASS"


@pytest.mark.parametrize("mode, expected_code", [("oauth_topic", 0), ("error_exit_oauth_topic", 3)])
def test_audit_oauth_topic_is_not_auth_failure(
    audit: dict[str, Path],
    mode: str,
    expected_code: int,
) -> None:
    configure(audit, mode)
    result = invoke(audit)
    assert result.returncode == expected_code, result.stderr
    assert "failure_category" not in receipt(audit)["attempts"][0]  # type: ignore[index]


@pytest.mark.parametrize(
    "invalid",
    [
        ["--review-round", "3"],
        ["--timeout", "invalid"],
        ["--timeout", "1800.000001"],
        ["--timeout", "nan"],
        ["--timeout", "inf"],
        ["--timeout=-inf"],
        ["--timeout", "0"],
        ["--model"],
        ["--effort", "max"],
    ],
)
def test_invalid_cli_input_is_not_timeout(audit: dict[str, Path], invalid: list[str]) -> None:
    result = invoke(audit, *invalid)
    assert result.returncode == 1, result.stderr
    assert not audit["calls"].exists()
    with pytest.raises(AssertionError, match="receipt not found"):
        receipt(audit)


def test_powershell_rejects_missing_import_parameters(audit: dict[str, Path]) -> None:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(RUNNER.with_name("audit_task.ps1")),
            "-Task",
            "1163",
            "-Auditor",
            "claude",
            "-ImportReport",
            str(audit["raw"]),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 1, result.stderr
    assert "Desktop import requires non-empty" in result.stderr
    assert not audit["calls"].exists()


def test_real_template_bom_import_preflight_preserves_attempt(audit: dict[str, Path]) -> None:
    sha = hashlib.sha256(audit["brief"].read_bytes()).hexdigest()
    audit["raw"].write_text(report_from_repository_template(sha), encoding="utf-8-sig")
    extras = [
        "--import-report",
        str(audit["raw"]),
        "--payload-sha",
        sha,
        "--observed-model",
        "claude-opus-5-5",
        "--observed-effort",
        "high",
        "--session-ref",
        "desktop-template-regression",
    ]
    for invalid in [
        ["--payload-sha", "typo"],
        ["--observed-model", "wrong-model"],
        ["--session-ref", " "],
        ["--import-report", str(audit["raw"].with_name("missing.md"))],
    ]:
        result = invoke(audit, *extras, *invalid)
        assert result.returncode == 1, result.stderr
        with pytest.raises(AssertionError, match="receipt not found"):
            receipt(audit)
    valid = invoke(audit, *extras)
    assert valid.returncode == 0, valid.stderr
    assert len(receipt(audit)["attempts"]) == 1  # type: ignore[arg-type]
    assert not audit["calls"].exists()
    assert report_path(audit).read_text(encoding="utf-8").startswith("# Audyt TASK-1163")
