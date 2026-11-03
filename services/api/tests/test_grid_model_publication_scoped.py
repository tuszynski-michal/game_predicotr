"""Real control execute and persistence with measured-format scoped fixture evidence."""

from uuid import UUID, uuid4

import pytest
from game_predictor_api.domain.grid_correction_evaluation import CHECKPOINT_RULE, build_report
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.grid_model_registry_models import (
    GridModelEvaluationReportModel,
    GridModelPublicationModel,
)
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_grid_correction_evaluation import roles
from test_grid_model_publication_and_activation import execute, registry

pytest_plugins = ["test_grid_model_publication_and_activation"]


def scoped_fixture(c, session, monkeypatch, state="current"):
    checks = []

    def currentness(self, report_id, cohorts):
        checks.append(report_id)
        return [
            {"state": state, "gameId": pin["gameId"], "cohortId": pin["cohortId"]}
            for pin in cohorts
        ]

    monkeypatch.setattr(SqlAlchemyGridModelRegistryRepository, "cohort_currentness", currentness)
    # An untested family game would reject legacy publication. Scoped skips only this check.
    monkeypatch.setattr(
        SqlAlchemyGridModelRegistryRepository,
        "family_games",
        lambda *args: {str(c.game), str(c.other)},
    )
    report = build_report(
        manifest=c.candidate,
        base_manifest_sha256=descriptor_sha256(c.baseline),
        training_game_id=str(c.game),
        parity={"passed": True, "bundleSha256": "a" * 64},
        cohorts=[
            {"gameId": str(c.game), "cohortId": c.candidate["cohortId"], "manifestSha256": "c" * 64}
        ],
        measured={str(c.game): {"mode": "grid-only", "roles": roles()}},
        scope={
            "currentGameId": str(c.game),
            "trainingGameIds": [str(c.game)],
            "priorVerifiedGameIds": [],
            "priorScopeDocumented": False,
            "exclusions": [],
        },
        checkpoint_selection={
            "rule": CHECKPOINT_RULE,
            "role": "VALIDATION",
            "step": 1,
            "metrics": {"boardCorrectRate": 0.8, "normalizedError": 0.02},
            "earlyStopping": {"patience": 4, "evaluationsWithoutImprovement": 0, "stopped": False},
        },
    )
    report_id = uuid4()
    session.add(
        GridModelEvaluationReportModel(
            id=report_id,
            version_id=UUID(c.candidate["versionId"]),
            producer=report["producer"],
            report_json=canonical_json(report),
            report_sha256=descriptor_sha256(report),
        )
    )
    session.flush()
    return registry(session, c.root), report_id, checks


@pytest.mark.parametrize("state", ["current", "stale", "missing", "unavailable"])
def test_scoped_publish_skips_only_family_guard_and_requires_currentness(
    controls, monkeypatch, state
):
    c = controls
    with Session(c.engine) as session:
        service, report_id, checks = scoped_fixture(c, session, monkeypatch, state)
        if state == "current":
            receipt = execute(service, "publish", c.candidate["versionId"], evaluation=report_id)
            assert receipt["evidenceKind"] == "evaluated_candidate"
            assert (
                session.get(GridModelPublicationModel, UUID(c.candidate["versionId"])) is not None
            )
        else:
            code = (
                "GRID_MODEL_EVALUATION_REQUIRED"
                if state == "missing"
                else "GRID_MODEL_EVALUATION_STALE"
            )
            with pytest.raises(GridModelRegistryError, match=code):
                execute(service, "publish", c.candidate["versionId"], evaluation=report_id)
            assert session.scalar(select(GridModelPublicationModel)) is None
        assert checks == [report_id]


def test_scoped_default_checks_live_base_under_lock_but_replays_own_receipt(controls, monkeypatch):
    c = controls
    with Session(c.engine) as session:
        service, report_id, _ = scoped_fixture(c, session, monkeypatch)
        execute(service, "publish", c.baseline["versionId"])
        execute(service, "publish", c.candidate["versionId"], evaluation=report_id)
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_SCOPE_STALE"):
            execute(service, "set_default", c.candidate["versionId"])
        execute(service, "set_default", c.baseline["versionId"])
        key = uuid4()
        first = execute(service, "set_default", c.candidate["versionId"], expected=1, key=key)
        # Setting the same current head is safe even though its base is the older default.
        execute(service, "set_default", c.candidate["versionId"], expected=2)
        other = historical_catalogue()[1]["versionId"]
        service.register(uuid4(), historical_catalogue()[1])
        execute(service, "publish", other)
        execute(service, "set_default", other, expected=3)  # legacy remains unchanged
        locks = []
        original = service.repository.lock
        monkeypatch.setattr(service.repository, "lock", lambda: (locks.append(True), original())[1])
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_SCOPE_STALE"):
            execute(service, "set_default", c.candidate["versionId"], expected=4)
        assert locks and service.repository.default().version_id == UUID(other)
        # Receipt replay is independent of the subsequently replaced default and old revision.
        assert (
            execute(service, "set_default", c.candidate["versionId"], expected=1, key=key) == first
        )


def test_scoped_activation_requires_game_inside_evaluated_scope(controls, monkeypatch):
    c = controls
    with Session(c.engine) as session:
        service, report_id, _ = scoped_fixture(c, session, monkeypatch)
        execute(service, "publish", c.candidate["versionId"], evaluation=report_id)
        accepted = execute(service, "activate", c.candidate["versionId"], game=c.game, expected=1)
        assert accepted["revision"] == 2
        with pytest.raises(GridModelRegistryError, match="GRID_MODEL_EVALUATION_REQUIRED"):
            execute(service, "activate", c.candidate["versionId"], game=c.other)
        assert service.repository.assignment(c.other)[0] is None
