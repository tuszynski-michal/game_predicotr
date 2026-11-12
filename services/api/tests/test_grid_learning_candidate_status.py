"""TASK-1189: current candidate state never rewrites the learning's pinned verdict."""

from game_predictor_api.domain.grid_learning_candidate_status import candidate_status
from game_predictor_api.schemas.grid_correction_learning import GridCorrectionLearningView

CANDIDATE = "bf327cfa-b35c-5c79-95bd-707301b703a5"
LATER = {
    "evaluationId": "6f7bcc1d-70c2-414d-ad92-ceeced1dc710",
    "reportId": "0c2e483e-082a-5f2e-a65d-313503a7d911",
    "verdict": "PASS",
    "policyVersion": "grid-model-per-game-gate-v4",
    "createdAt": "2026-11-12T08:03:15+00:00",
}


def test_later_pass_and_current_use_are_reported() -> None:
    status = candidate_status(
        candidate_version_id=CANDIDATE,
        learning_evaluation_id="8723857d-e305-4ecb-b91d-db44461465d8",
        default_version_id=CANDIDATE,
        assigned_version_id=CANDIDATE,
        evaluations=[LATER],
    )
    assert status == {
        "versionId": CANDIDATE,
        "isDefault": True,
        "assignedToGame": True,
        "latestEvaluation": LATER,
        "laterEvaluation": True,
    }


def test_own_evaluation_is_not_later_and_unused_candidate_is_not_claimed() -> None:
    status = candidate_status(
        candidate_version_id=CANDIDATE,
        learning_evaluation_id=LATER["evaluationId"],
        default_version_id="3ed60010-7c3e-5c3b-91aa-4e03eb9bfa5e",
        assigned_version_id=None,
        evaluations=[LATER],
    )
    assert status["laterEvaluation"] is False
    assert (status["isDefault"], status["assignedToGame"]) == (False, False)
    assert (
        candidate_status(
            candidate_version_id=CANDIDATE,
            learning_evaluation_id=None,
            default_version_id=None,
            assigned_version_id=None,
            evaluations=[],
        )["latestEvaluation"]
        is None
    )


def test_view_keeps_pinned_verdict_and_omits_absent_candidate() -> None:
    from test_grid_correction_learning_api import view_value

    plain = GridCorrectionLearningView.model_validate(view_value()).model_dump(mode="json")
    assert plain == view_value() and "candidate" not in plain
    enriched = {
        **view_value(),
        "verdict": "REVISE",
        "candidate": candidate_status(
            candidate_version_id=CANDIDATE,
            learning_evaluation_id=None,
            default_version_id=CANDIDATE,
            assigned_version_id=CANDIDATE,
            evaluations=[LATER],
        ),
    }
    dumped = GridCorrectionLearningView.model_validate(enriched).model_dump(mode="json")
    assert dumped["verdict"] == "REVISE"
    assert dumped["candidate"]["latestEvaluation"]["verdict"] == "PASS"
