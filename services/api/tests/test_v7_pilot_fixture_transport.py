"""Fixture-only lost response preserves the normal UI-created UUID/body."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from starlette.types import Message

_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_ROOT))
_SPEC = importlib.util.spec_from_file_location(
    "fixture_app", _ROOT / "scripts" / "v7_pilot_fixture_app.py"
)
assert _SPEC is not None and _SPEC.loader is not None
fixture = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fixture)


def test_response_loss_occurs_once_after_actual_app_success_and_exact_body_survives(
    tmp_path: Path,
) -> None:
    fault = tmp_path / "fault.json"
    fault.write_text(
        json.dumps({"armed": True, "runId": "run", "expectedIndex": 0}), encoding="utf-8"
    )
    body = {"operationId": "ui-generated-uuid", "expectedRevision": 4, "sourceIndex": 1}
    original = json.dumps(body).encode()
    delivered: list[bytes] = []

    async def app(scope, receive, send):
        delivered.append((await receive())["body"])
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"access-control-allow-origin", b"http://127.0.0.1:3020")],
            }
        )
        await send({"type": "http.response.body", "body": b'{"persisted":true}'})

    middleware = fixture.FixtureResponseLoss(app, fault)

    async def request() -> list[Message]:
        messages: list[Message] = []

        async def receive():
            return {"type": "http.request", "body": original}

        async def send(message):
            messages.append(message)

        await middleware(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/admin/semi-automatic-image-selections/run/ranges/0/"
                "output-acknowledgements",
            },
            receive,
            send,
        )
        return messages

    first = asyncio.run(request())
    assert first[0]["status"] == 503
    assert (b"access-control-allow-origin", b"http://127.0.0.1:3020") in first[0]["headers"]
    proof = json.loads(fault.read_text(encoding="utf-8"))
    assert proof["actualServerResponseStatus"] == 200
    assert proof["consumedBody"] == body
    assert proof["consumedOperationId"] == body["operationId"]
    assert proof["armed"] is False
    retry = asyncio.run(request())
    assert retry[0]["status"] == 200
    assert delivered == [original, original]
    proof = json.loads(fault.read_text(encoding="utf-8"))
    assert proof["replayedRequests"] == [
        {
            "body": body,
            "bodySha256": hashlib.sha256(original).hexdigest(),
            "actualServerResponseStatus": 200,
        }
    ]
