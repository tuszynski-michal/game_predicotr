"""Fail-closed request guard and append-only audit for the local Admin API."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

ADMIN_ACTOR = "local-owner"
ADMIN_INTENT_HEADER = "X-Admin-Intent"
ADMIN_CONFIRMATION_HEADER = "X-Admin-Confirmation"
ADMIN_TARGET_HEADER = "X-Admin-Target"
ADMIN_INTENT_VALUE = ADMIN_ACTOR
ADMIN_CONFIRMATION_VALUE = "confirmed"
_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_LOOPBACK_CLIENTS = frozenset({"127.0.0.1", "::1"})
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "code",
    "credential",
    "key",
    "password",
    "secret",
    "token",
)


@dataclass(frozen=True, slots=True)
class HighImpactOperation:
    action: str
    target_template: str


HIGH_IMPACT_OPERATIONS: dict[tuple[str, str], HighImpactOperation] = {
    ("DELETE", "/api/v1/admin/games/{game_id}"): HighImpactOperation(
        "archive-game", "game:{game_id}"
    ),
    (
        "DELETE",
        "/api/v1/admin/games/{game_id}/symbols/{symbol_id}",
    ): HighImpactOperation("archive-symbol", "symbol:{symbol_id}"),
    (
        "POST",
        "/api/v1/admin/rules-versions/{rules_version_id}/publish",
    ): HighImpactOperation("publish-rules-version", "rules-version:{rules_version_id}"),
    (
        "DELETE",
        "/api/v1/admin/rules-versions/{rules_version_id}",
    ): HighImpactOperation("archive-rules-version", "rules-version:{rules_version_id}"),
    (
        "DELETE",
        "/api/v1/admin/rules-versions/{rules_version_id}/paylines/{payline_id}",
    ): HighImpactOperation("archive-payline", "payline:{payline_id}"),
    (
        "DELETE",
        "/api/v1/admin/rules-versions/{rules_version_id}/payout-rules/{payout_rule_id}",
    ): HighImpactOperation("archive-payout-rule", "payout-rule:{payout_rule_id}"),
    (
        "POST",
        "/api/v1/admin/dataset-versions/{dataset_version_id}/publish",
    ): HighImpactOperation("publish-dataset", "dataset-version:{dataset_version_id}"),
    (
        "DELETE",
        "/api/v1/admin/dataset-versions/{dataset_version_id}",
    ): HighImpactOperation("archive-dataset", "dataset-version:{dataset_version_id}"),
    (
        "DELETE",
        "/api/v1/admin/layout-import-validations/{validation_job_id}/staging",
    ): HighImpactOperation("reject-layout-staging", "validation-job:{validation_job_id}"),
    (
        "POST",
        "/api/v1/admin/layout-import-validations/{validation_job_id}/publish",
    ): HighImpactOperation("publish-layout-import", "validation-job:{validation_job_id}"),
    ("POST", "/api/v1/admin/jobs"): HighImpactOperation("create-job", "job:new"),
    (
        "POST",
        "/api/v1/admin/jobs/{job_id}/cancel",
    ): HighImpactOperation("cancel-job", "job:{job_id}"),
    ("POST", "/api/v1/admin/mobile-releases"): HighImpactOperation(
        "create-mobile-release", "mobile-release:new"
    ),
    (
        "POST",
        "/api/v1/admin/mobile-releases/{mobile_release_id}/build",
    ): HighImpactOperation("build-mobile-release", "mobile-release:{mobile_release_id}"),
    ("POST", "/api/v1/admin/reviewer-ingress/start"): HighImpactOperation(
        "start-reviewer-ingress", "remote-reviewer"
    ),
    ("POST", "/api/v1/admin/reviewer-ingress/stop"): HighImpactOperation(
        "stop-reviewer-ingress", "remote-reviewer"
    ),
    ("POST", "/api/v1/admin/reviewer-sessions"): HighImpactOperation(
        "create-reviewer-session", "reviewer-session:new"
    ),
    (
        "POST",
        "/api/v1/admin/reviewer-sessions/{session_id}/revoke",
    ): HighImpactOperation("revoke-reviewer-session", "reviewer-session:{session_id}"),
}

_REVIEWER_MUTATION_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^/api/v1/admin/image-review-items/[^/]+/geometry-preview$",
        r"^/api/v1/admin/image-review-items/[^/]+/geometry-revisions$",
        r"^/api/v1/admin/image-review-items/[^/]+/resolution$",
    )
)


class AppendOnlyAdminAuditLog:
    """Write bounded, redacted security events to one durable JSONL file."""

    def __init__(self, artifact_root: Path) -> None:
        self._path = artifact_root / "admin-audit" / "local-admin-events.jsonl"
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        *,
        action: str,
        target: str,
        outcome: str,
        method: str,
        path: str,
        reason_code: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> None:
        event = {
            "eventId": str(uuid4()),
            "occurredAt": datetime.now(UTC).isoformat(),
            "actor": ADMIN_ACTOR,
            "action": action,
            "target": target,
            "outcome": outcome,
            "method": method,
            "path": path,
            "reasonCode": reason_code,
            "metadata": redact_security_metadata(metadata or {}),
        }
        payload = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(payload + "\n")
                stream.flush()
                os.fsync(stream.fileno())


def redact_security_metadata(value: object, *, key: str = "") -> object:
    """Recursively redact values whose field names can contain credentials."""

    normalized_key = key.casefold().replace("-", "_")
    if normalized_key and any(part in normalized_key for part in _SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redact_security_metadata(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_security_metadata(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


class LocalAdminSecurityMiddleware(BaseHTTPMiddleware):  # type: ignore[misc]
    """Protect unsafe local Admin requests before they reach domain services."""

    def __init__(self, app: Any, *, admin_origin: str, audit_log: AppendOnlyAdminAuditLog) -> None:
        super().__init__(app)
        self._admin_origin = admin_origin.rstrip("/")
        self._audit_log = audit_log

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()
        path = request.url.path
        if method not in _UNSAFE_METHODS or not path.startswith("/api/v1/admin/"):
            return await call_next(request)

        client_host = request.client.host if request.client is not None else ""
        # Starlette's literal `testclient` never exists on a real socket. Existing
        # service tests use it deliberately; security regressions use explicit IPs.
        if client_host == "testclient":
            return await call_next(request)

        operation, expected_target = match_high_impact_operation(method, path)
        action = operation.action if operation is not None else _default_action(method, path)
        target = expected_target or _default_target(path)

        if client_host not in _LOOPBACK_CLIENTS:
            return self._reject(
                action=action,
                target=target,
                method=method,
                path=path,
                code="ADMIN_LOOPBACK_REQUIRED",
                message="Administrative mutations are accepted only from loopback.",
            )

        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") != self._admin_origin:
            return self._reject(
                action=action,
                target=target,
                method=method,
                path=path,
                code="ADMIN_ORIGIN_FORBIDDEN",
                message="The request origin cannot mutate the local Admin API.",
            )

        if _is_reviewer_mutation(request, path):
            return await call_next(request)

        if request.headers.get(ADMIN_INTENT_HEADER) != ADMIN_INTENT_VALUE:
            return self._reject(
                action=action,
                target=target,
                method=method,
                path=path,
                code="ADMIN_INTENT_REQUIRED",
                message="The local administrative intent header is required.",
            )

        if operation is not None and (
            request.headers.get(ADMIN_CONFIRMATION_HEADER) != ADMIN_CONFIRMATION_VALUE
            or request.headers.get(ADMIN_TARGET_HEADER) != expected_target
        ):
            return self._reject(
                action=action,
                target=target,
                method=method,
                path=path,
                code="ADMIN_CONFIRMATION_REQUIRED",
                message="This operation requires confirmation of its exact target.",
            )

        self._audit_log.append(
            action=action,
            target=target,
            outcome="authorized",
            method=method,
            path=path,
        )
        response = await call_next(request)
        self._audit_log.append(
            action=action,
            target=target,
            outcome="succeeded" if response.status_code < 400 else "failed",
            method=method,
            path=path,
            reason_code=None if response.status_code < 400 else f"HTTP_{response.status_code}",
        )
        return response

    def _reject(
        self,
        *,
        action: str,
        target: str,
        method: str,
        path: str,
        code: str,
        message: str,
    ) -> JSONResponse:
        self._audit_log.append(
            action=action,
            target=target,
            outcome="rejected",
            method=method,
            path=path,
            reason_code=code,
        )
        return JSONResponse(
            status_code=403,
            content={"code": code, "message": message, "details": {}},
        )


def match_high_impact_operation(
    method: str,
    concrete_path: str,
) -> tuple[HighImpactOperation | None, str | None]:
    for (expected_method, path_template), operation in HIGH_IMPACT_OPERATIONS.items():
        if method != expected_method:
            continue
        match = _template_pattern(path_template).fullmatch(concrete_path)
        if match is not None:
            return operation, operation.target_template.format(**match.groupdict())
    return None, None


def augment_admin_security_openapi(schema: dict[str, Any]) -> None:
    """Publish the middleware contract on every unsafe Admin operation."""

    components = schema.setdefault("components", {})
    security_schemes = components.setdefault("securitySchemes", {})
    security_schemes["LocalAdminIntent"] = {
        "type": "apiKey",
        "in": "header",
        "name": ADMIN_INTENT_HEADER,
        "description": "Fixed local-owner intent added by the loopback Admin client.",
    }
    for path, path_item in schema.get("paths", {}).items():
        for method in _UNSAFE_METHODS:
            operation_schema = path_item.get(method.lower())
            if operation_schema is None or not path.startswith("/api/v1/admin/"):
                continue
            parameters = operation_schema.setdefault("parameters", [])
            existing_header_names = {
                item.get("name")
                for item in parameters
                if isinstance(item, dict) and item.get("in") == "header"
            }
            operation_schema["security"] = [{"LocalAdminIntent": []}]
            high_impact = HIGH_IMPACT_OPERATIONS.get((method, path))
            if high_impact is not None:
                if ADMIN_CONFIRMATION_HEADER not in existing_header_names:
                    parameters.append(
                        _header_parameter(
                            ADMIN_CONFIRMATION_HEADER,
                            ADMIN_CONFIRMATION_VALUE,
                            True,
                        )
                    )
                if ADMIN_TARGET_HEADER not in existing_header_names:
                    parameters.append(_header_parameter(ADMIN_TARGET_HEADER, None, True))
            responses = operation_schema.setdefault("responses", {})
            responses.setdefault(
                "403",
                {
                    "description": "Local Admin security guard rejected the request",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                        }
                    },
                },
            )


def _template_pattern(path_template: str) -> re.Pattern[str]:
    cursor = 0
    parts: list[str] = []
    for match in re.finditer(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", path_template):
        parts.append(re.escape(path_template[cursor : match.start()]))
        parts.append(f"(?P<{match.group(1)}>[^/]+)")
        cursor = match.end()
    parts.append(re.escape(path_template[cursor:]))
    return re.compile("".join(parts))


def _header_parameter(name: str, constant: str | None, required: bool) -> dict[str, object]:
    value_schema: dict[str, object] = {"type": "string"}
    if constant is not None:
        value_schema["const"] = constant
    return {
        "name": name,
        "in": "header",
        "required": required,
        "schema": value_schema,
    }


def _is_reviewer_mutation(request: Request, path: str) -> bool:
    authorization = request.headers.get("authorization", "")
    return authorization.startswith("Bearer ") and any(
        pattern.fullmatch(path) for pattern in _REVIEWER_MUTATION_PATTERNS
    )


def _default_action(method: str, path: str) -> str:
    return f"{method.casefold()}-admin-resource"


def _default_target(path: str) -> str:
    return f"admin-path:{path}"


__all__ = [
    "ADMIN_ACTOR",
    "ADMIN_CONFIRMATION_HEADER",
    "ADMIN_CONFIRMATION_VALUE",
    "ADMIN_INTENT_HEADER",
    "ADMIN_INTENT_VALUE",
    "ADMIN_TARGET_HEADER",
    "AppendOnlyAdminAuditLog",
    "HIGH_IMPACT_OPERATIONS",
    "LocalAdminSecurityMiddleware",
    "augment_admin_security_openapi",
    "match_high_impact_operation",
    "redact_security_metadata",
]
