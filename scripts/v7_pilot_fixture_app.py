"""Task-owned normal API composition: exact-copy picker and one-shot response loss.

No fixture HTTP endpoint, gate bypass, browser-state injection or alternate API
contract. The operator uses normal UI buttons. Controls are local task files.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from game_predictor_api.config import ApiSettings
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from scripts.prepare_v7_reviewed_pilot import DATABASE, ROLE, ROOT, RUNTIME, _load


def fixture_picker() -> Path:
    selector = json.loads((RUNTIME / "fixture-selector.json").read_text(encoding="utf-8"))
    if set(selector) != {"fixture"} or selector["fixture"] not in ("B", "A0", "A1", "A2", "A3"):
        raise ValueError("Invalid scoped fixture selection.")
    path: Path = RUNTIME / "fixtures" / selector["fixture"]
    canonical = path.resolve(strict=True)
    report = json.loads((RUNTIME / "fixture-bindings.json").read_text(encoding="utf-8"))
    if str(canonical) != str(path) or not any(
        binding["sourceRoot"] == str(canonical) for binding in report["sourceBindings"]
    ):
        raise ValueError("Selected fixture is outside its exact-copy allowlist.")
    return canonical


def fixture_environment(scope: str = "real_pilot") -> dict[str, str]:
    if scope not in ("real_pilot", "technical_fixture"):
        raise ValueError("Unknown pilot composition.")
    value = _load()
    main = ROOT.parents[2]
    return {
        "GAME_PREDICTOR_DATABASE_URL": str(value["databaseUrl"]),
        "GAME_PREDICTOR_OWNER_DATABASE_URL": str(value["ownerDatabaseUrl"]),
        "GAME_PREDICTOR_API_HOST": "127.0.0.1",
        "GAME_PREDICTOR_API_PORT": "8020",
        "GAME_PREDICTOR_ADMIN_ORIGIN": "http://127.0.0.1:3020",
        "GAME_PREDICTOR_ARTIFACT_ROOT": str(RUNTIME / "artifacts"),
        "GAME_PREDICTOR_IMPORT_ROOT": str(RUNTIME / "imports"),
        **(
            {"GAME_PREDICTOR_V7_REVIEW_OUTPUT_BASE": str(main / "v7-output")}
            if scope == "real_pilot"
            else {}
        ),
        "GAME_PREDICTOR_STORAGE_GC_OBSERVE_ONLY": "true",
        "GAME_PREDICTOR_ENABLE_SEMI_AUTOMATIC_IMAGE_SELECTION": "true",
        "GAME_PREDICTOR_V7_LABEL_GEOMETRY_READ_ONLY": "true",
        "GAME_PREDICTOR_V7_PILOT_ACCEPTANCE_SCOPE": scope,
        "GAME_PREDICTOR_V7_LABEL_GEOMETRY_RUNTIME_ROOT": str(main / ".runtime"),
        "GAME_PREDICTOR_V7_LABEL_GEOMETRY_CORPUS_MANIFEST": str(
            main / ".runtime" / "v7-label-geometry-calibration-t0603-v2.local.json"
        ),
        "GAME_PREDICTOR_V7_SELECTION_OCR_MODEL_ROOT": str(
            main / "artifacts" / "m5-models" / "sequence-number-ocr-v1"
        ),
    }


class FixtureResponseLoss:
    """Consume one normal successful ack response; preserve the UI's exact body."""

    def __init__(self, app: ASGIApp, fault_file: Path) -> None:
        self.app = app
        self.fault_file = fault_file

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        fault = (
            json.loads(self.fault_file.read_text(encoding="utf-8"))
            if self.fault_file.exists()
            else {}
        )
        expected = (
            f"/api/v1/admin/semi-automatic-image-selections/{fault.get('runId')}"
            f"/ranges/{fault.get('expectedIndex')}/output-acknowledgements"
        )
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != expected
            or (
                fault.get("armed") is not True
                and (
                    not isinstance(fault.get("consumedOperationId"), str)
                    or len(fault.get("replayedRequests", [])) >= 4
                )
            )
        ):
            await self.app(scope, receive, send)
            return
        request: list[bytes] = []
        response: list[Message] = []

        async def capture_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                request.append(message.get("body", b""))
            return message

        async def capture_send(message: Message) -> None:
            response.append(message)

        await self.app(scope, capture_receive, capture_send)
        status = next(
            (message["status"] for message in response if message["type"] == "http.response.start"),
            None,
        )
        original = b"".join(request)
        try:
            body = json.loads(original)
        except ValueError:
            body = None
        if fault.get("armed") is not True:
            # Observe normal retries after reload without changing their transport.
            self.fault_file.write_text(
                json.dumps(
                    {
                        **fault,
                        "replayedRequests": [
                            *fault.get("replayedRequests", []),
                            {
                                "body": body,
                                "bodySha256": hashlib.sha256(original).hexdigest(),
                                "actualServerResponseStatus": status,
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            for message in response:
                await send(message)
            return
        if status != 200:
            for message in response:
                await send(message)
            return
        if not isinstance(body, dict) or "operationId" not in body:
            for message in response:
                await send(message)
            return
        self.fault_file.write_text(
            json.dumps(
                {
                    **fault,
                    "armed": False,
                    "consumedOperationId": body["operationId"],
                    "consumedBody": body,
                    "consumedBodySha256": hashlib.sha256(original).hexdigest(),
                    "actualServerResponseStatus": status,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        payload = b'{"code":"TECHNICAL_FIXTURE_RESPONSE_LOSS","message":"Test response withheld."}'
        headers = [
            header
            for message in response
            if message["type"] == "http.response.start"
            for header in message.get("headers", [])
            if header[0].lower() not in (b"content-type", b"content-length")
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 503,
                "headers": [
                    *headers,
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


def _pilot_settings(scope: str) -> ApiSettings:
    os.environ.update(fixture_environment(scope))
    settings = ApiSettings.from_environment()
    from sqlalchemy.engine import make_url

    url = make_url(settings.database_url)
    if url.database != DATABASE or url.username != ROLE or not settings.v7_label_geometry_read_only:
        raise ValueError("Technical fixture requires the isolated runtime/read-only composition.")
    return settings


def create_operator_app() -> ASGIApp:
    """Default composition keeps the native picker and the unmodified transport."""
    from game_predictor_api.main import create_app

    return create_app(_pilot_settings("real_pilot"))


def create_fixture_app() -> ASGIApp:
    from game_predictor_api.main import create_app

    return FixtureResponseLoss(
        create_app(_pilot_settings("technical_fixture"), local_source_picker=fixture_picker),
        RUNTIME / "fixture-response-loss.json",
    )
