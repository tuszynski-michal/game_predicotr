"""The new crop pin is distinct from import provenance and legacy command identity."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_render_reference import (
    execution_context,
    require_evaluation_contract,
    require_reference_v2,
)
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.symbol_model_snapshots import (
    LAB_RGB_SYMBOL_MODEL_VERSION,
    SymbolModelJobSnapshot,
    SymbolModelStorageRoot,
)
from game_predictor_api.schemas.grid_cell_content import ContentSessionCreate
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository
from game_predictor_api.storage.grid_content_oracle_context import (
    require_current_evaluation_contract,
    resolve_evaluation_contract,
)


def lab_snapshot():
    return SymbolModelJobSnapshot(
        iteration_id=UUID(int=8),
        model_version=LAB_RGB_SYMBOL_MODEL_VERSION,
        manifest_checksum_sha256="a" * 64,
        onnx_checksum_sha256="b" * 64,
        onnx_relative_path="test/model.onnx",
        storage_root=SymbolModelStorageRoot.ARTIFACT,
        class_codes=("J", "10"),
        input_size=64,
        crop_size=96,
        temperature=1.05,
    )


def pin(monkeypatch, tmp_path, game=None):
    game = UUID(int=1) if game is None else game
    from game_predictor_api.storage.symbol_model_snapshot_resolver import (
        SqlAlchemySymbolModelSnapshotResolver,
    )

    monkeypatch.setattr(
        SqlAlchemySymbolModelSnapshotResolver, "resolve", lambda self, **kw: lab_snapshot()
    )
    return resolve_evaluation_contract(None, tmp_path, game)


def test_pin_selects_verified_contract_once_and_separates_original_import(monkeypatch, tmp_path):
    contract = pin(monkeypatch, tmp_path)
    require_evaluation_contract(contract, str(UUID(int=1)))
    original = {
        "state": "available",
        "classifier": {"old": True},
        "renderConfiguration": {"paddingFraction": 0.08},
        "importJobId": "old-job",
    }
    before = deepcopy(original)
    context = execution_context(original, contract)
    assert context["renderConfiguration"]["paddingFraction"] == 0
    assert context["classifier"] == contract["classifier"]
    assert original == before and context["importJobId"] == "old-job"
    forged = deepcopy(contract)
    forged["renderConfiguration"]["paddingFraction"] = 0.08
    forged["renderConfigurationSha256"] = digest(forged["renderConfiguration"])
    forged["sha256"] = digest({k: v for k, v in forged.items() if k != "sha256"})
    with pytest.raises(ContentError) as caught:
        require_evaluation_contract(forged)
    assert caught.value.code == "CONTENT_EVALUATION_CONTRACT_INVALID"


def test_active_freshness_uses_crop_not_weights(monkeypatch, tmp_path):
    contract = pin(monkeypatch, tmp_path)
    from dataclasses import replace

    from game_predictor_api.storage.symbol_model_snapshot_resolver import (
        SqlAlchemySymbolModelSnapshotResolver,
    )

    monkeypatch.setattr(
        SqlAlchemySymbolModelSnapshotResolver,
        "resolve",
        lambda self, **kw: replace(lab_snapshot(), onnx_checksum_sha256="c" * 64),
    )
    require_current_evaluation_contract(None, tmp_path, UUID(int=1), contract)
    monkeypatch.setattr(
        SqlAlchemySymbolModelSnapshotResolver,
        "resolve",
        lambda self, **kw: replace(
            lab_snapshot(), model_version="spatial-symbol-cnn-onnx-v1", crop_size=None
        ),
    )
    with pytest.raises(ContentError) as caught:
        require_current_evaluation_contract(None, tmp_path, UUID(int=1), contract)
    assert caught.value.code == "CONTENT_RENDER_CONFIGURATION_CHANGED"


@pytest.mark.parametrize("policy", [None, "active-symbol-render-v2"])
def test_exact_receipt_precedes_resolver_and_preserves_old_nullable_body(monkeypatch, policy):
    from game_predictor_api.storage import grid_content_oracle_context as module

    command = ContentSessionCreate(
        idempotencyKey=uuid4(),
        cohortId=uuid4(),
        expectedManifestSha256="a" * 64,
        sourceIds=[uuid4()],
        renderReferencePolicy=policy,
    )
    old_body = command.model_dump(mode="json")
    if policy is None:
        old_body.pop("renderReferencePolicy")
    assert old_body["targetSelection"] is None
    receipt = {"idempotencyKey": str(command.idempotencyKey), "session": {"old": "unchanged"}}

    def replay(game, key, payload, actor):
        assert payload["body"] == old_body
        return receipt

    monkeypatch.setattr(
        module,
        "resolve_evaluation_contract",
        lambda *a: pytest.fail("replay resolved a live model"),
    )
    repo = SimpleNamespace(begin_command=replay)
    assert (
        SqlAlchemyGridCellContentRepository.create_session(repo, uuid4(), command, "local-owner")
        is receipt
    )


def test_reference_v2_rejects_old_measurement_even_when_rehashed(monkeypatch, tmp_path):
    contract = pin(monkeypatch, tmp_path)
    provenance = {"state": "available", "classifier": {}, "renderConfiguration": {}}
    context = execution_context(provenance, contract)
    body = {
        "version": "production-cell-evaluation-reference-v2",
        "sourceContext": context,
        "sourceContextSha256": digest(context),
        "importProvenance": provenance,
        "importProvenanceSha256": digest(provenance),
        "evaluationContract": contract,
        "measurement": {"sessionId": "old", "report": {"qualificationState": "ready"}},
    }
    with pytest.raises(ContentError) as caught:
        require_reference_v2({**body, "sha256": digest(body)})
    assert caught.value.code == "CONTENT_MEASUREMENT_CONTRACT_CHANGED"


def test_v2_receipt_and_pin_survive_new_process_without_live_resolution(monkeypatch, tmp_path):
    """File SQL durability; PostgreSQL locks/RLS are covered by the owned PG fixture."""
    import json
    import subprocess
    import sys

    from game_predictor_api.storage.grid_cell_content_models import (
        GridCellContentCommandModel as Command,
    )
    from game_predictor_api.storage.grid_cell_content_models import (
        GridCellContentSessionModel as Measurement,
    )
    from sqlalchemy import JSON, Column, MetaData, Table, create_engine
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.orm import Session

    contract = pin(monkeypatch, tmp_path)
    game, identifier = UUID(int=1), uuid4()
    command = ContentSessionCreate(
        idempotencyKey=uuid4(),
        cohortId=uuid4(),
        expectedManifestSha256="a" * 64,
        sourceIds=[uuid4()],
        renderReferencePolicy="active-symbol-render-v2",
    )
    payload = {
        "kind": "session_create",
        "actor": "local-owner",
        "body": command.model_dump(mode="json"),
    }
    response = {
        "idempotencyKey": str(command.idempotencyKey),
        "session": {"sessionId": str(identifier)},
    }
    engine = create_engine("sqlite:///" + str(tmp_path / "receipt.sqlite"))
    metadata = MetaData()
    for model in (Command, Measurement):
        Table(
            model.__tablename__,
            metadata,
            *[
                Column(
                    c.name,
                    JSON() if isinstance(c.type, JSONB) else c.type,
                    primary_key=c.primary_key,
                )
                for c in model.__table__.columns
            ],
        )
    metadata.create_all(engine)
    with Session(engine) as session, session.begin():
        repo = SqlAlchemyGridCellContentRepository(session, tmp_path)
        repo.receipt(game, command.idempotencyKey, payload, response)
        session.add(
            Measurement(
                game_id=game,
                id=identifier,
                cohort_id=command.cohortId,
                revision=1,
                phase="pass1",
                document={"evaluationContract": contract},
                progress={"pass1": {}, "pass2": {}},
                report=None,
            )
        )
    engine.dispose()
    config = tmp_path / "replay.json"
    config.write_text(
        json.dumps(
            {
                "body": command.model_dump(mode="json"),
                "response": response,
                "contract": contract,
                "sessionId": str(identifier),
            }
        )
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import json, sys
from pathlib import Path
from uuid import UUID
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from game_predictor_api.schemas.grid_cell_content import ContentSessionCreate
from game_predictor_api.storage.grid_cell_content import SqlAlchemyGridCellContentRepository as Repo
from game_predictor_api.storage.grid_cell_content_models import (
    GridCellContentSessionModel as Measurement,
)
from game_predictor_api.storage import grid_content_oracle_context as context
root = Path(sys.argv[1]); saved = json.loads((root / "replay.json").read_text())
def changed_active_model(*args, **kwargs):
    raise AssertionError("A replay must not resolve the changed active model")
context.resolve_evaluation_contract = changed_active_model
engine = create_engine("sqlite:///" + str(root / "receipt.sqlite"))
with Session(engine) as session:
    repo = Repo(session, root)
    repo.bind = lambda *args, **kwargs: None
    repo.lock = lambda *args, **kwargs: None
    command = ContentSessionCreate.model_validate(saved["body"])
    assert repo.create_session(UUID(int=1), command, "local-owner") == saved["response"]
    row = session.get(Measurement, (UUID(int=1), UUID(saved["sessionId"])))
    assert row.document["evaluationContract"] == saved["contract"]
engine.dispose()
print("cold v2 receipt and exact pin PASS")
""",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "cold v2 receipt and exact pin PASS" in result.stdout
