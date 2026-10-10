"""The symbol vertical uses the existing protected loopback API."""

from fastapi.testclient import TestClient
from game_predictor_worker.vision_lab.api import create_app
from test_vision_lab_symbol_labels import symbols

HEADERS = {"origin": "http://127.0.0.1:3102"}


def test_symbol_api_bootstrap_and_schema(tmp_path):
    store, source = symbols(tmp_path)
    client = TestClient(
        create_app(store.catalog, store.annotations.root, symbol_root=store.root),
        base_url="http://127.0.0.1:8102",
    )
    assert client.get("/symbols").json()["total"] == 0
    body = dict(
        op="dictionary_draft",
        request_id="api-draft",
        expected_revision=0,
        actor="operator",
        game_id=source.game_id,
        base_version=None,
        entries=[dict(id="a", code="A", display_name="A")],
    )
    assert client.post("/symbols", json=body).status_code == 403
    response = client.post("/symbols", json=body, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 1
    assert client.post("/symbols", json=body, headers=HEADERS).json()["replayed"]
    assert client.get(f"/symbol-dictionaries/{source.game_id}/1").json()["status"] == "draft"
    assert client.get("/symbols?offset=1").status_code == 409
    assert (
        client.post("/symbols", json={**body, "origin": "db_approved"}, headers=HEADERS).status_code
        == 422
    )
    assert (
        client.post(
            "/symbol-crops", json={"kind": "db_approved", "sample_id": "x"}, headers=HEADERS
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/symbols",
            content=b"x" * (1024 * 1024 + 1),
            headers={**HEADERS, "content-type": "application/json"},
        ).status_code
        == 413
    )


def test_symbol_config_is_optional(tmp_path):
    store, _ = symbols(tmp_path)
    client = TestClient(
        create_app(store.catalog, store.annotations.root), base_url="http://127.0.0.1:8102"
    )
    assert client.get("/symbols").status_code == 503
    assert client.get("/annotations").status_code == 200
