from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)


def test_local_reviewer_symbol_job_still_requires_owner_headers(tmp_path):
    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    path = "/api/v1/admin/image-review-items/pending-symbol-reinference/{game_id}"

    @app.post(path)
    def start(game_id: str):
        return {"gameId": game_id}

    game = uuid4()
    endpoint = path.replace("{game_id}", str(game))
    origin = {"Origin": "http://127.0.0.1:3001"}
    with TestClient(app, client=("127.0.0.1", 50000)) as client:
        assert client.post(endpoint, headers=origin).status_code == 403
        assert (
            client.post(
                endpoint, headers=origin | {"Authorization": "Bearer remote-session"}
            ).status_code
            == 403
        )
        headers = origin | {
            "X-Admin-Intent": "local-owner",
            "X-Admin-Confirmation": "confirmed",
            "X-Admin-Target": f"pending-symbol-reinference:{game}",
        }
        response = client.post(endpoint, headers=headers)
        assert response.status_code == 200, response.text


def test_local_job_dispatch_requires_owner_intent_without_socket_runtime(tmp_path):
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    middleware = LocalAdminSecurityMiddleware(
        FastAPI(),
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )
    game = uuid4()
    path = f"/api/v1/admin/image-review-items/pending-symbol-reinference/{game}"
    origin = {"origin": "http://127.0.0.1:3001"}

    async def next_response(_request):
        return JSONResponse({"ok": True})

    for headers, expected in (
        (origin, 403),
        (origin | {"authorization": "Bearer remote-session"}, 403),
        # This existing route requires local owner intent; it has never been
        # registered as a high-impact operation requiring target confirmation.
        (origin | {"x-admin-intent": "local-owner"}, 200),
        (
            origin
            | {
                "x-admin-intent": "local-owner",
                "x-admin-confirmation": "confirmed",
                "x-admin-target": f"pending-symbol-reinference:{game}",
            },
            200,
        ),
    ):
        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": path,
                "scheme": "http",
                "server": ("127.0.0.1", 8000),
                "client": ("127.0.0.1", 50000),
                "query_string": b"",
                "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
            }
        )
        # dispatch and the stub next_response complete synchronously: no loop,
        # socket, server or weakened security code is needed for this check.
        coroutine = middleware.dispatch(request, next_response)
        with pytest.raises(StopIteration) as result:
            coroutine.send(None)
        assert result.value.value.status_code == expected
