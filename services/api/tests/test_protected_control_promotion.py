from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_registry import SymbolModelActivationAction
from game_predictor_api.storage import symbol_model_registry_repository as registry

GAME = UUID(registry.MUMIE_GAME_ID)


class Session:
    def __init__(self, receipt=None):
        self.values = iter([SimpleNamespace(id=GAME), receipt])
        self.writes = []

    def scalar(self, *_):
        return next(self.values)

    def add(self, record):
        self.writes.append(record)


def target(origin="production_training", game=GAME):
    return SimpleNamespace(
        id=uuid4(),
        game_id=game,
        origin=origin,
        candidate_manifest_checksum_sha256="a" * 64,
        configuration_payload={"protectedSourceExclusions": {"sha": "fixed"}},
    )


def repository(monkeypatch, session, model):
    repo = registry.SqlAlchemySymbolModelRegistryRepository(session, artifact_root=Path("unused"))
    monkeypatch.setattr(repo, "_eligible_target", lambda *_: model)
    monkeypatch.setattr(repo, "_current", lambda *_: None)
    monkeypatch.setattr(repo, "_validate_transition", lambda **_: None)
    return repo


def test_preview_then_new_human_conflict_is_rechecked_before_any_write(monkeypatch):
    session = Session()
    model = target()
    repo = repository(monkeypatch, session, model)
    calls = []

    def guard(*_, lock):
        calls.append(lock)
        if lock:
            raise JobConflictError("PROTECTED_CONTROL_TRUTH_CONFLICT_OPEN", "OPEN")

    monkeypatch.setattr(registry, "require_control_truth_promotion", guard)
    assert repo.preview(
        game_id=GAME, model_iteration_id=model.id, action=SymbolModelActivationAction.ACTIVATE
    ).can_activate
    with pytest.raises(JobConflictError) as error:
        repo.activate(
            game_id=GAME,
            model_iteration_id=model.id,
            expected_manifest_checksum_sha256="a" * 64,
            expected_current_model_iteration_id=None,
            action=SymbolModelActivationAction.ACTIVATE,
            actor="operator",
            reason=None,
            idempotency_key=uuid4(),
            command_sha256="b" * 64,
        )
    assert error.value.code == "PROTECTED_CONTROL_TRUTH_CONFLICT_OPEN"
    assert calls == [False, True]
    assert session.writes == []


@pytest.mark.parametrize("model", [target("lab_import"), target(game=uuid4())])
def test_qualified_initial_r2_and_other_games_preserve_existing_gate(monkeypatch, model):
    repo = repository(monkeypatch, Session(), model)
    monkeypatch.setattr(
        registry,
        "require_control_truth_promotion",
        lambda *_, **__: pytest.fail("Legacy promotion acquired pilot guard"),
    )
    repo._require_control_truth(model, lock=True)


def test_restart_lost_response_replays_receipt_before_new_drift(monkeypatch):
    model = target()
    key = uuid4()
    receipt = SimpleNamespace(
        id=uuid4(),
        game_id=GAME,
        model_iteration_id=model.id,
        previous_model_iteration_id=None,
        action="activate",
        activation_number=1,
        actor="operator",
        reason=None,
        idempotency_key=key,
        command_sha256="b" * 64,
        created_at=datetime.now(UTC),
    )
    session = Session(receipt)
    repo = registry.SqlAlchemySymbolModelRegistryRepository(session, artifact_root=Path("unused"))
    monkeypatch.setattr(
        registry,
        "require_control_truth_promotion",
        lambda *_, **__: pytest.fail("Receipt replay reactivated model"),
    )
    result, created = repo.activate(
        game_id=GAME,
        model_iteration_id=model.id,
        expected_manifest_checksum_sha256="a" * 64,
        expected_current_model_iteration_id=None,
        action=SymbolModelActivationAction.ACTIVATE,
        actor="operator",
        reason=None,
        idempotency_key=key,
        command_sha256="b" * 64,
    )
    assert not created and result.id == receipt.id
    assert session.writes == []
