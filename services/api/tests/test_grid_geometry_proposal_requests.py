"""Real transport and local security boundary, without a database or server."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.image_reviews import create_image_reviews_router
from game_predictor_api.application.grid_geometry_proposals import (
    GridGeometryProposalService,
    ProposalCommandOutcome,
)
from game_predictor_api.application.reviewer_access import ReviewerAccessError
from game_predictor_api.security.local_admin import (
    AppendOnlyAdminAuditLog,
    LocalAdminSecurityMiddleware,
)


def test_real_local_principal_scope_and_typed_conflict_commits(tmp_path):
    game, job, review, target = (uuid4() for _ in range(4))
    records, exits = [], []

    class Repository:
        def command(self, *args):
            records.append(args)
            return ProposalCommandOutcome(
                409,
                {"code": "GRID_PROPOSAL_SOURCE_MISSING", "message": "Missing", "details": {}},
                None,
            )

        def list_proposals(self, *args):
            return {"proposals": [], "candidates": []}

    class Access:
        def authenticate(self, token):
            if token != "real-session":
                raise ReviewerAccessError("REVIEWER_TOKEN_INVALID", "Invalid")
            return SimpleNamespace(id=target)

        def authorize_scope(self, session, *, game_id, import_job_id):
            if (game_id, import_job_id) != (game, job):
                raise ReviewerAccessError("REVIEWER_SCOPE_FORBIDDEN", "Wrong scope")

    def dependency():
        try:
            yield SimpleNamespace(grid_geometry_proposals=GridGeometryProposalService(Repository()))
            exits.append("commit")
        except BaseException:
            exits.append("rollback")
            raise

    app = FastAPI()
    app.add_middleware(
        LocalAdminSecurityMiddleware,
        admin_origin="http://127.0.0.1:3000",
        reviewer_origin="http://127.0.0.1:3001",
        audit_log=AppendOnlyAdminAuditLog(tmp_path),
    )

    @app.exception_handler(ReviewerAccessError)
    async def denied(request, failure):
        return JSONResponse(status_code=403, content={"code": failure.code})

    app.include_router(
        create_image_reviews_router(dependency, tmp_path, lambda: Access(), lambda: None),
        prefix="/api/v1",
    )
    base = f"/api/v1/admin/image-review-items/{review}/grid-geometry-proposals"
    scope = {"gameId": str(game), "importJobId": str(job)}
    body = {"idempotencyKey": str(uuid4()), "targetResultId": str(target)}
    headers = {"Origin": "http://127.0.0.1:3001", "X-Admin-Intent": "local-owner"}
    with TestClient(app, client=("127.0.0.1", 12345)) as client:
        assert client.get(base, params=scope).status_code == 200
        response = client.post(base, params=scope, json=body, headers=headers)
        assert response.status_code == 409 and records[-1][-1] == "local-owner"
        assert exits[-1] == "commit"
        assert client.post(base, params=scope, json=body).status_code == 403
        assert (
            client.post(
                base, params=scope, json={**body, "actor": "spoof"}, headers=headers
            ).status_code
            == 422
        )
        assert (
            client.post(
                base, params=scope, json=body, headers={"Authorization": "Bearer forged"}
            ).status_code
            == 403
        )
        assert (
            client.post(
                base, params=scope, json=body, headers={"Authorization": "Bearer real-session"}
            ).status_code
            == 409
        )
        assert records[-1][-1] == f"reviewer-session:{target}"
        assert (
            client.get(
                base,
                params={**scope, "importJobId": str(uuid4())},
                headers={"Authorization": "Bearer real-session"},
            ).status_code
            == 403
        )
    with TestClient(app, client=("192.0.2.1", 12345)) as client:
        assert client.post(base, params=scope, json=body, headers=headers).status_code == 403
