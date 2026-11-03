"""Real evaluator reader on synthetic server records, without real model runs."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.neural_grid_operation_pin import GAME_EVALUATION_REQUIRED
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.grid_model_registry_models import (
    GridModelEvaluationInvalidationModel,
    GridModelPublicationModel,
)
from game_predictor_api.storage.models import RulesVersionModel
from game_predictor_api.storage.neural_grid_operation_qualification import (
    prepare_operation_pin,
    recheck_operation_pin,
)
from sqlalchemy.orm import Session
from test_grid_model_publication_and_activation import (  # noqa: F401
    controls as _controls_fixture,
)
from test_grid_model_publication_and_activation import (
    execute,
    publish_fixture,
    registry,
    seed_report,
)
from test_grid_model_registry import engine as registry_engine  # noqa: F401


@pytest.fixture
def operation_controls(request, tmp_path):
    return _controls_fixture.__wrapped__(request, tmp_path)


def snapshot(c, game, *, historical=False):
    return NeuralGridSnapshot.from_catalogue(
        game_id=str(game),
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=c.baseline if historical else c.candidate,
    )


def prepare(session, c, game, *, historical=False):
    rules = uuid4()
    return prepare_operation_pin(
        session,
        snapshot=snapshot(c, game, historical=historical),
        game_id=game,
        rules_version_id=rules,
        rows=3,
        columns=5,
    )


def recheck(session, c, game, pin, *, historical=False):
    original = session.get

    def get(model, key, **kwargs):
        if model is RulesVersionModel:
            return SimpleNamespace(game_id=game, rows=3, columns=5)
        return original(model, key, **kwargs)

    with patch.object(session, "get", side_effect=get):
        return recheck_operation_pin(
            session,
            pin=pin,
            model_snapshot=snapshot(c, game, historical=historical).to_payload(),
            game_id=game,
        )


def test_historical_publication_does_not_qualify_any_game(operation_controls):
    c = operation_controls
    with Session(c.engine) as session:
        execute(registry(session, c.root), "publish", c.baseline["versionId"])
        pin = prepare(session, c, c.game, historical=True)
        assert pin["qualification"]["state"] == "unqualified"
        assert recheck(session, c, c.game, pin, historical=True) == (GAME_EVALUATION_REQUIRED,)


def test_exact_game_pass_and_foreign_game_rejected_without_blocking_proposals(operation_controls):
    c = operation_controls
    with Session(c.engine) as session:
        _, report = publish_fixture(c, session)
        qualified = prepare(session, c, c.game)
        assert qualified["qualification"]["evaluationId"] == str(report)
        assert recheck(session, c, c.game, qualified) == ()
        foreign = prepare(session, c, c.other)
        assert foreign["qualification"]["state"] == "unqualified"
        assert recheck(session, c, c.other, foreign) == (GAME_EVALUATION_REQUIRED,)


def test_frozen_unqualified_never_upgrades_and_invalidation_blocks_exact_qualified(
    operation_controls,
):
    c = operation_controls
    with Session(c.engine) as session:
        unqualified = prepare(session, c, c.game)
        _, report = publish_fixture(c, session)
        assert recheck(session, c, c.game, unqualified) == (GAME_EVALUATION_REQUIRED,)
        qualified = prepare(session, c, c.game)
        session.add(
            GridModelEvaluationInvalidationModel(
                id=uuid4(), report_id=report, reason="test", actor="test"
            )
        )
        session.flush()
        assert recheck(session, c, c.game, qualified) == ("NEURAL_GRID_GAME_EVALUATION_STALE",)


def test_infrastructure_error_does_not_become_unqualified_success(operation_controls):
    c = operation_controls
    with (
        Session(c.engine) as session,
        patch(
            "game_predictor_api.storage.neural_grid_operation_qualification._evidence",
            side_effect=RuntimeError("database unavailable"),
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        prepare(session, c, c.game)


@pytest.mark.parametrize(
    "field,value",
    [
        ("evaluationId", str(uuid4())),
        ("evaluationSha256", "d" * 64),
        ("publicationEvidenceSha256", "e" * 64),
    ],
)
def test_exact_qualified_game_rejects_mismatched_report_or_publication_pin(
    operation_controls, field, value
):
    c = operation_controls
    with Session(c.engine) as session:
        publish_fixture(c, session)
        pin = prepare(session, c, c.game)
        assert recheck(session, c, c.game, pin) == ()  # real current report for this game
        forged = deepcopy(pin)
        forged["qualification"][field] = value
        forged["pinSha256"] = descriptor_sha256(
            {k: v for k, v in forged.items() if k != "pinSha256"}
        )
        assert recheck(session, c, c.game, forged) == ("NEURAL_GRID_GAME_EVALUATION_STALE",)


def test_second_publish_is_forbidden_and_read_model_replacement_is_stale(operation_controls):
    from uuid import UUID

    from game_predictor_api.storage.neural_grid_operation_qualification import _evidence

    c = operation_controls
    with Session(c.engine) as session:
        service, _ = publish_fixture(c, session)
        old_pin = prepare(session, c, c.game)
        new_report = seed_report(session, c.candidate, [c.game])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_REVISION_CONFLICT"):
            execute(service, "publish", c.candidate["versionId"], evaluation=new_report, expected=1)
        assert recheck(session, c, c.game, old_pin) == ()
        # Corruption simulation in this synthetic SQLite read model only.
        # The real publication command above forbids replacing an immutable row.
        publication = session.get(GridModelPublicationModel, UUID(c.candidate["versionId"]))
        publication.evaluation_id = new_report
        evidence = service.control._evidence(
            service.control._version(UUID(c.candidate["versionId"])), new_report, c.game
        )
        publication.evidence_json = canonical_json(evidence)
        publication.evidence_sha256 = descriptor_sha256(evidence)
        session.flush()
        assert _evidence(session, snapshot(c, c.game), c.game)["evaluationId"] == str(new_report)
        assert recheck(session, c, c.game, old_pin) == ("NEURAL_GRID_GAME_EVALUATION_STALE",)
