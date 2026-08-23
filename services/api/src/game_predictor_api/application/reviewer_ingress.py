"""Controlled lifecycle for the optional public Reviewer ingress."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final, Literal, Protocol, cast
from urllib.parse import urlparse
from uuid import UUID, uuid4

ReviewerIngressState = Literal["running", "stopped", "stale", "degraded"]
CommandRunner = Callable[
    [Sequence[str], Path, float],
    subprocess.CompletedProcess[str],
]

_SCRIPT_BY_ACTION: Final = {
    "start": "start_remote_reviewer_tunnel.ps1",
    "start-local": "start_local_reviewer.ps1",
    "status": "get_remote_reviewer_tunnel_status.ps1",
    "stop": "stop_remote_reviewer_tunnel.ps1",
}


def _normalized_subprocess_environment(
    environment: Mapping[str, str],
    *,
    windows: bool | None = None,
) -> dict[str, str]:
    """Return an environment without case-colliding Windows variable names."""

    is_windows = os.name == "nt" if windows is None else windows
    if not is_windows:
        return dict(environment)

    normalized: dict[str, str] = {}
    key_by_folded_name: dict[str, str] = {}
    path_values: list[str] = []
    path_was_present = False
    for key, value in environment.items():
        folded_name = key.casefold()
        if folded_name == "path":
            path_was_present = True
            path_values.append(value)
            continue
        existing_key = key_by_folded_name.get(folded_name)
        if existing_key is None:
            key_by_folded_name[folded_name] = key
            normalized[key] = value
        else:
            normalized[existing_key] = value

    if path_was_present:
        path_entries: list[str] = []
        seen_entries: set[str] = set()
        for path_value in path_values:
            for raw_entry in path_value.split(";"):
                entry = raw_entry.strip()
                if not entry:
                    continue
                identity = entry.rstrip("\\/").casefold()
                if identity in seen_entries:
                    continue
                seen_entries.add(identity)
                path_entries.append(entry)
        normalized["Path"] = ";".join(path_entries)
    return normalized


@dataclass(frozen=True, slots=True)
class ReviewerIngressStatus:
    """Safe status returned to the local Admin."""

    state: ReviewerIngressState
    public_origin: str | None
    target: str
    started_at: datetime | None
    reviewer_ready: bool | None
    instance_id: UUID | None = None


class ReviewerIngressError(RuntimeError):
    """Stable failure raised by the fixed ingress controller."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class SharedReviewerIngress(Protocol):
    def status(self) -> ReviewerIngressStatus: ...

    def start(self) -> ReviewerIngressStatus: ...


def is_ready_online_reviewer_ingress(status: ReviewerIngressStatus) -> bool:
    if (
        status.state != "running"
        or status.reviewer_ready is not True
        or status.target != "http://127.0.0.1:3001"
        or status.public_origin is None
    ):
        return False
    parsed = urlparse(status.public_origin)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".trycloudflare.com")
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and parsed.path in {"", "/"}
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def ensure_online_reviewer_ingress(
    ingress: SharedReviewerIngress,
) -> ReviewerIngressStatus:
    status = ingress.status()
    if is_ready_online_reviewer_ingress(status):
        return status
    started = ingress.start()
    if not is_ready_online_reviewer_ingress(started):
        raise ReviewerIngressError(
            "REVIEWER_INGRESS_NOT_READY",
            "Shared Reviewer ingress did not reach a ready online state.",
        )
    return started


def _run_command(
    command: Sequence[str],
    working_directory: Path,
    timeout_seconds: float,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=working_directory,
        env=_normalized_subprocess_environment(os.environ),
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
        request_id_factory: Callable[[], UUID] = uuid4,
    ) -> None:
        self._project_root = project_root.resolve()
        self._powershell_executable = powershell_executable
        self._runner = runner
        self._request_id_factory = request_id_factory
        self._lock = threading.Lock()

    def status(self) -> ReviewerIngressStatus:
        return self._execute("status", timeout_seconds=12)

    def start(self) -> ReviewerIngressStatus:
        return self._execute("start", timeout_seconds=60)

    def start_local(self) -> ReviewerIngressStatus:
        return self._execute("start-local", timeout_seconds=30)

    def stop(self) -> ReviewerIngressStatus:
        return self._execute("stop", timeout_seconds=12)

    def stop_if_current(self, instance_id: UUID) -> ReviewerIngressStatus:
        return self._execute(
            "stop",
            timeout_seconds=12,
            extra_arguments=("-ExpectedInstanceId", str(instance_id)),
        )

    def _execute(
        self,
        action: Literal["start", "start-local", "status", "stop"],
        *,
        timeout_seconds: float,
        extra_arguments: Sequence[str] = (),
    ) -> ReviewerIngressStatus:
        script_path = self._project_root / "scripts" / _SCRIPT_BY_ACTION[action]
        if not script_path.is_file():
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_CONTROLLER_MISSING",
                "The controlled Reviewer ingress script is unavailable.",
            )

        runtime_directory = self._project_root / ".runtime"
        runtime_directory.mkdir(parents=True, exist_ok=True)
        result_directory = runtime_directory / "reviewer-ingress-controller-results"
        result_directory.mkdir(parents=True, exist_ok=True)
        result_path = result_directory / f"{self._request_id_factory()}.json"
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
            *extra_arguments,
        ]
        try:
            with self._lock:
                completed = self._runner(
                    command,
                    self._project_root,
                    timeout_seconds,
                )
        except (OSError, subprocess.TimeoutExpired) as error:
            result_path.unlink(missing_ok=True)
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
        return self._status_from_payload(
            payload,
            allow_local_only=action == "start-local",
        )

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
    def _status_from_payload(
        payload: dict[str, object],
        *,
        allow_local_only: bool = False,
    ) -> ReviewerIngressStatus:
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
        instance_id = payload.get("instanceId")
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
        parsed_instance_id: UUID | None = None
        if instance_id is not None:
            if not isinstance(instance_id, str):
                raise ReviewerIngressError(
                    "REVIEWER_INGRESS_INVALID_RESPONSE",
                    "Reviewer ingress instance id is invalid.",
                )
            try:
                parsed_instance_id = UUID(instance_id)
            except ValueError as error:
                raise ReviewerIngressError(
                    "REVIEWER_INGRESS_INVALID_RESPONSE",
                    "Reviewer ingress instance id is invalid.",
                ) from error
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
        local_only_ready = (
            allow_local_only
            and target == "http://127.0.0.1:3001"
            and reviewer_ready is True
            and public_origin is None
        )
        if parsed_state == "running" and public_origin is None and not local_only_ready:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Running Reviewer ingress has no public origin.",
            )
        if allow_local_only and parsed_state == "running" and not local_only_ready:
            raise ReviewerIngressError(
                "REVIEWER_INGRESS_INVALID_RESPONSE",
                "Local Reviewer controller returned a non-local target.",
            )
        return ReviewerIngressStatus(
            state=parsed_state,
            public_origin=public_origin,
            target=target,
            started_at=parsed_started_at,
            reviewer_ready=reviewer_ready,
            instance_id=parsed_instance_id,
        )


__all__ = [
    "ReviewerIngressError",
    "ReviewerIngressService",
    "ReviewerIngressState",
    "ReviewerIngressStatus",
    "SharedReviewerIngress",
    "ensure_online_reviewer_ingress",
    "is_ready_online_reviewer_ingress",
]
