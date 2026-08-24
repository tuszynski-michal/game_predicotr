from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.access_credentials import hash_access_code
from game_predictor_api.application.remote_manual_selection_access import (
    REMOTE_SELECTION_COOKIE_NAME,
    REMOTE_SELECTION_PROXY_INTENT,
    RemoteManualSelectionAuthenticationError,
    RemoteManualSelectionAuthorizationError,
)
from game_predictor_api.application.remote_manual_selection_control import (
    RemoteManualSelectionControlRateLimiter,
    RemoteManualSelectionRateLimitError,
)
from game_predictor_api.application.remote_manual_selection_path_safety import (
    WindowsPathLimits,
    validate_windows_component,
)
from game_predictor_api.application.remote_manual_selection_transfer import (
    RemoteManualSelectionTransferLimitError,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.remote_manual_selections import (
    RemoteManualSelectionConflictError,
)
from game_predictor_api.main import create_app

from scripts.verify_remote_manual_selection_security_gate import (
    SecurityGateReportError,
    report_checksum,
    validate_report,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
REPORT_PATH = (
    REPOSITORY_ROOT / "ai_docs" / "quality" / "remote-manual-selection-security-gate-v1.json"
)
CLIENT_ID = "11111111-1111-4111-8111-111111111111"
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")


def _report() -> dict[str, object]:
    value = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_committed_security_gate_report_is_complete_and_content_addressed() -> None:
    report = _report()

    checksum = validate_report(report, repository_root=REPOSITORY_ROOT)

    assert checksum == report["contentChecksumSha256"]
    assert report["openCriticalHighCount"] == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "open_high",
        "missing_control",
        "absolute_evidence",
        "tampered_content",
    ],
)
def test_security_gate_report_fails_closed_when_evidence_is_unsafe(
    mutation: str,
) -> None:
    report = deepcopy(_report())
    controls = report["controls"]
    findings = report["findings"]
    assert isinstance(controls, list)
    assert isinstance(findings, list)
    if mutation == "open_high":
        findings.append(
            {
                "id": "F-X",
                "severity": "high",
                "status": "open",
                "summary": "Blocking test finding.",
            }
        )
        report["openCriticalHighCount"] = 1
    elif mutation == "missing_control":
        controls.pop()
    elif mutation == "absolute_evidence":
        control = controls[0]
        assert isinstance(control, dict)
        control["evidence"] = [r"C:\private\evidence.txt"]
    else:
        report["decision"] = "failed"
    report["contentChecksumSha256"] = report_checksum(report)

    with pytest.raises(SecurityGateReportError):
        validate_report(report, repository_root=REPOSITORY_ROOT)


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (
            RemoteManualSelectionAuthenticationError(
                "REMOTE_SELECTION_TOKEN_INVALID",
                "The access token is invalid.",
            ),
            401,
        ),
        (
            RemoteManualSelectionAuthorizationError(
                "REMOTE_SELECTION_SCOPE_FORBIDDEN",
                "The scope is forbidden.",
            ),
            403,
        ),
        (
            RemoteManualSelectionConflictError(
                "REMOTE_SELECTION_REVISION_CONFLICT",
                "The revision is stale.",
            ),
            409,
        ),
        (
            RemoteManualSelectionTransferLimitError(
                "REMOTE_SELECTION_SESSION_QUOTA_EXCEEDED",
                "The byte quota is exhausted.",
            ),
            413,
        ),
        (
            RemoteManualSelectionRateLimitError(
                "REMOTE_SELECTION_CONTROL_RATE_LIMITED",
                "The request rate is too high.",
            ),
            429,
        ),
    ],
)
def test_public_error_contract_is_stable_and_path_free(
    error: Exception,
    expected_status: int,
    tmp_path: Path,
) -> None:
    class FailingAccess:
        def context(self, **_kwargs: object) -> None:
            raise error

    app = create_app(
        ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(tmp_path / "artifacts")}),
        remote_manual_selection_access_service_dependency=lambda: FailingAccess(),
        remote_manual_selection_recovery_service_dependency=lambda: object(),
    )
    with TestClient(app, base_url="https://testserver") as client:
        response = client.get(
            "/api/v1/remote-manual-selections/context",
            headers={
                "Cookie": f"{REMOTE_SELECTION_COOKIE_NAME}=opaque-token",
                "X-Remote-Selection-Client": CLIENT_ID,
                "X-Remote-Selection-Proxy": REMOTE_SELECTION_PROXY_INTENT,
            },
        )

    assert response.status_code == expected_status
    assert response.json()["code"] == error.code
    assert "C:\\" not in response.text


def test_security_primitives_remain_bounded_under_local_parallel_load() -> None:
    limiter = RemoteManualSelectionControlRateLimiter(limit=1_200)

    def consume_budget(worker: int) -> None:
        client_id = UUID(int=worker + 1)
        for _ in range(150):
            limiter.consume(SESSION_ID, client_id)

    started_at = perf_counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        tuple(executor.map(consume_budget, range(8)))
    rate_elapsed = perf_counter() - started_at
    with pytest.raises(RemoteManualSelectionRateLimitError):
        limiter.consume(SESSION_ID, UUID(int=99))

    salts = tuple(bytes([value]) * 16 for value in range(1, 9))
    started_at = perf_counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        hashes = tuple(executor.map(lambda salt: hash_access_code("ABCD-2345", salt), salts))
    pbkdf_elapsed = perf_counter() - started_at

    limits = WindowsPathLimits(max_component_utf16_units=255, max_path_utf16_units=259)
    started_at = perf_counter()
    for value in range(10_000):
        validate_windows_component(f"batch-{value}", limits=limits)
    path_elapsed = perf_counter() - started_at

    assert len(set(hashes)) == len(salts)
    assert rate_elapsed < 2.0
    assert pbkdf_elapsed < 5.0
    assert path_elapsed < 2.0
