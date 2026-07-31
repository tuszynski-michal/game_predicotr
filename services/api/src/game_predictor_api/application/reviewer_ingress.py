"""Controlled lifecycle for the optional public Reviewer ingress."""

from __future__ import annotations

import json
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, cast

ReviewerIngressState = Literal["running", "stopped", "stale", "degraded"]
CommandRunner = Callable[
    [Sequence[str], Path, float],
    subprocess.CompletedProcess[str],
]

_SCRIPT_BY_ACTION: Final = {
    "start": "start_remote_reviewer_tunnel.ps1",
    "status": "get_remote_reviewer_tunnel_status.ps1",
    "stop": "stop_remote_reviewer_tunnel.ps1",
}


@dataclass(frozen=True, slots=True)
class ReviewerIngressStatus:
    """Safe status returned to the local Admin."""

    state: ReviewerIngressState
    public_origin: str | None
    target: str
    started_at: datetime | None
    reviewer_ready: bool | None


class ReviewerIngressError(RuntimeError):
    """Stable failure raised by the fixed ingress controller."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _run_command(
    command: Sequence[str],
    working_directory: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=working_directory,
        check=False,
        stderr=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        text=True,
        timeout=timeout_seconds,
    )


class ReviewerIngressService:
    """Run only the fixed start/status/stop PowerShell controllers."""

    def __init__(
        self,
        project_root: Path,
        *,
        powershell_executable: str = "powershell.exe",
        runner: CommandRunner = _run_command,
    ) -> None:
        self._project_root = project_root.resolve()
        self._powershell_executable = powershell_executable
        self._runner = runner
        self._lock = threading.Lock()

    def status(self) -> ReviewerIngressStatus:
        return self._execute("status", timeout_seconds=8)

    def start(self) -> ReviewerIngressStatus:
        return self._execute("start", timeout_seconds=25)

    def stop(self) -> ReviewerIngressStatus:
        return self._execute("stop", timeout_seconds=8)

    def _execute(
        self,
        action: Literal["start", "status", "stop"],
        *,
        timeout_seconds: float,
    ) -> ReviewerIngressStatus:
        script_path = self._project_root / "scripts" / _SCRIPT_BY_ACTION[action]
        if not script_path.is_file():
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_CONTROLLER_MISSING",
                "The controlled Reviewer ingress script is unavailable.",
            )

        runtime_directory = self._project_root / ".runtime"
        runtime_directory.mkdir(parents=True, exist_ok=True)
        result_path = runtime_directory / "reviewer-ingress-controller-result.json"
        result_path.unlink(missing_ok=True)
        command = [
            self._powershell_executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
            "-Json",
            "-ResultPath",
            str(result_path),
        ]
        try:
            with self._lock:
                completed = self._runner(
                    command,
                    self._project_root,
                    timeout_seconds,
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_COMMAND_FAILED",
                "Reviewer ingress controller did not finish within its bounded time.",
            ) from error

        output = completed.stdout or ""
        if result_path.is_file():
            try:
                output = result_path.read_text(encoding="utf-8")
            except OSError as error:
                raise ReviewerIngressError(
                    "REVIEWER_INGRESS_INVALID_RESPONSE",
                    "Reviewer ingress controller status could not be read.",
                ) from error
            finally:
                result_path.unlink(missing_ok=True)
        payload = self._parse_payload(output)
        if completed.returncode != 0:
            message = str(
                payload.get(
                    "message",
                    "Reviewer ingress could not be changed. Run the local setup check.",
                )
            )
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_COMMAND_FAILED",
                message,
            )
        return self._status_from_payload(payload)

    @staticmethod
    def _parse_payload(output: str) -> dict[str, object]:
        candidates = [line.strip() for line in output.splitlines() if line.strip()]
        if not candidates:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress controller returned no status.",
            )
        try:
            parsed = json.loads(candidates[-1])
        except (json.JSONDecodeError, TypeError) as error:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress controller returned an invalid status.",
            ) from error
        if not isinstance(parsed, dict):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress controller returned an invalid status.",
            )
        return parsed

    @staticmethod
    def _status_from_payload(payload: dict[str, object]) -> ReviewerIngressStatus:
        state = payload.get("state")
        if state not in {"running", "stopped", "stale", "degraded"}:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress controller returned an unknown state.",
            )
        parsed_state = cast(ReviewerIngressState, state)
        public_origin = payload.get("publicOrigin")
        target = payload.get("target")
        started_at = payload.get("startedAt")
        reviewer_ready = payload.get("reviewerReady")
        if public_origin is not None and not isinstance(public_origin, str):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress public origin is invalid.",
            )
        if not isinstance(target, str):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer ingress target is invalid.",
            )
        if reviewer_ready is not None and not isinstance(reviewer_ready, bool):
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Reviewer readiness status is invalid.",
            )
        parsed_started_at: datetime | None = None
        if started_at is not None:
            if not isinstance(started_at, str):
                raise ReviewerIngressError(
                    "REVIEWER_INGRESS_INVALID_RESPONSE",
                    "Reviewer ingress start time is invalid.",
                )
            try:
                parsed_started_at = datetime.fromisoformat(started_at)
            except ValueError as error:
                raise ReviewerIngressError(
                    "REVIEWER_INGRESS_INVALID_RESPONSE",
                    "Reviewer ingress start time is invalid.",
                ) from error
        if parsed_state == "running" and public_origin is None:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Running Reviewer ingress has no public origin.",
            )
        return ReviewerIngressStatus(
            state=parsed_state,
            public_origin=public_origin,
            target=target,
            started_at=parsed_started_at,
            reviewer_ready=reviewer_ready,
        )


__all__ = [
    "ReviewerIngressError",
    "ReviewerIngressService",
    "ReviewerIngressState",
    "ReviewerIngressStatus",
]
