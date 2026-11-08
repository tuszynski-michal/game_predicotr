"""Small fixtures prove the production limit and final streaming-only verification."""

import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from game_predictor_worker.images import grid_model_evaluation_handler as module


def details(tmp_path, payload):
    job, game = SimpleNamespace(id=uuid4()), str(uuid4())
    state = {"units": {}}
    for role in ("VALIDATION", "REGRESSION"):
        relative = module.detail_path(job.id, game, role)
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        state["units"][f"{game}:{role}"] = {
            "detail": {"path": relative, "sha256": hashlib.sha256(payload).hexdigest()}
        }
    return module.GridModelEvaluationJobHandler(None, tmp_path), job, state, [{"game_id": game}]


@pytest.mark.parametrize("load", [False, True])
def test_detail_limit_precedes_read_and_parse(tmp_path, monkeypatch, load):
    handler, job, state, cohorts = details(tmp_path, b"x" * 129)
    monkeypatch.setattr(module, "DETAIL_MAX_BYTES", 128)
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("must not parse oversized data"))
    with pytest.raises(module.JobHandlerError) as caught:
        handler._verify_details(job, state, cohorts, load_documents=load)
    assert caught.value.code == "GRID_EVALUATION_DETAIL_TOO_LARGE"


def test_final_pass_checks_bytes_without_parsing_or_retaining_documents(tmp_path, monkeypatch):
    handler, job, state, cohorts = details(tmp_path, b"hash-only receipt")
    monkeypatch.setattr(json, "loads", lambda *a, **k: pytest.fail("final pass must not parse"))
    assert handler._verify_details(job, state, cohorts) == {}
    path = tmp_path / state["units"][next(iter(state["units"]))]["detail"]["path"]
    path.write_bytes(b"changed bytes")
    with pytest.raises(module.JobHandlerError) as caught:
        handler._verify_details(job, state, cohorts)
    assert caught.value.code == "GRID_EVALUATION_DETAIL_CHANGED"
