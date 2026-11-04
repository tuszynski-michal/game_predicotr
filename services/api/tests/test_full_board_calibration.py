"""Numeric product gates, not evidence of model quality on real operator data."""

from uuid import UUID

import pytest
from game_predictor_api.domain.full_board_calibration import (
    AXES,
    AssessedTarget,
    CalibrationPlan,
    FeatureVector,
    ReferenceTarget,
    acceptance_reasons,
    assess_regression,
    make_plan,
    measure_targets,
    seal_b,
)

GAME = UUID("10000000-0000-0000-0000-000000000001")


def features(**overrides):
    return FeatureVector(values={**dict.fromkeys(AXES, 0.5), **overrides})


def plan(references=None):
    return make_plan(
        references
        or [
            ReferenceTarget(
                gameId=GAME,
                sourceRepresentativeSha256="1" * 64,
                positionIndex=0,
                role="VALIDATION-A",
                humanGood=True,
                features=features(),
            )
        ],
        game_id=GAME,
        candidate_sha="2" * 64,
        baseline_sha="3" * 64,
        routing_sha="4" * 64,
        role_proof_sha="5" * 64,
        b_assessment_sha="6" * 64,
        regression_assessment_sha="7" * 64,
    )


def targets(n=30):
    # The SAME 30 photos supply two labelled targets, one old bad and one good.
    # Candidate fixes every old bad target: there must not be a deficit of negatives.
    return [
        AssessedTarget(
            gameId=GAME,
            sourceId=UUID(int=i + 1),
            sourceRepresentativeSha256=f"{i:064x}",
            positionIndex=slot,
            groundTruthSha256=f"{i * 2 + slot:064x}",
            baselineGood=bool(slot),
            candidateGood=True,
            candidateCropped=False,
            baselinePreT0Accepted=True,
            baselineT0Accepted=bool(slot),
            candidateFeatures=features(),
        )
        for i in range(n)
        for slot in range(2)
    ]


def test_mixed_partial_sources_overlap_and_candidate_repairs_all_baseline_errors():
    p = plan()
    sealed = seal_b(p, targets())
    result = assess_regression(p, sealed, targets())
    assert result["state"] == "qualified"
    measured = result["regression"]
    assert measured["candidateBad"] == 0
    assert measured["baselineBadSources"] == measured["baselineGoodSources"] == 30
    assert measured["stratumOverlapSources"] == measured["stratumUnionSources"] == 30
    assert measured["candidateCorrectAutomatic"] == 60
    assert result["wholePhotoClaims"] is False


def test_duplicates_do_not_turn_29_into_30_and_conflicting_gt_never_picks_a_winner():
    p = plan()
    values = targets(29)
    measured = measure_targets(p, values + values, p.menu[0])
    assert measured["baselineBadSources"] == 29
    assert assess_regression(p, seal_b(p, values), values)["state"] == "unqualified"
    conflict = values[0].model_copy(update={"groundTruthSha256": "f" * 64})
    with pytest.raises(ValueError, match="ALIAS_CONFLICT"):
        seal_b(p, [*values, conflict])


def test_menu_is_bounded_preregistered_per_game_and_integrity_checked():
    refs = [
        ReferenceTarget(
            gameId=GAME,
            sourceRepresentativeSha256=f"{i:064x}",
            positionIndex=0,
            role="TRAIN",
            humanGood=True,
            features=features(**dict.fromkeys(AXES, i / 100)),
        )
        for i in range(100)
    ]
    p = plan(refs)
    assert len(p.menu) == 256
    assert p.axisCounts["peak"] == {"nTargets": 100, "nSources": 100}
    assert p == plan(list(reversed(refs)) + refs)
    changed = p.model_dump(mode="json")
    changed["menu"][0]["peak"] += 0.1
    with pytest.raises(ValueError):
        CalibrationPlan.model_validate(changed)


def test_missing_axis_is_manual_only_when_applicable_and_no_fake_threshold():
    p = plan(
        [
            ReferenceTarget(
                gameId=GAME,
                sourceRepresentativeSha256="1" * 64,
                positionIndex=0,
                role="TRAIN",
                humanGood=True,
                features=FeatureVector(
                    values={**dict.fromkeys(AXES, 0.5), "rescueDisagreement": None},
                    notApplicable=("rescueDisagreement",),
                ),
            )
        ]
    )
    assert p.manualWhenApplicable == ("rescueDisagreement",)
    assert acceptance_reasons(features(), p.menu[0])
    not_applicable = FeatureVector(
        values={**dict.fromkeys(AXES, 0.5), "rescueDisagreement": None},
        notApplicable=("rescueDisagreement",),
    )
    assert acceptance_reasons(not_applicable, p.menu[0]) == ()


@pytest.mark.parametrize("damage", ["crop", "unknown", "reject_all", "synthetic"])
def test_regression_never_tunes_or_calls_unknown_success(damage):
    p = plan()
    sealed = seal_b(p, targets())
    values = targets()
    if damage == "crop":
        values[0] = values[0].model_copy(update={"candidateCropped": True})
    elif damage == "unknown":
        values[0] = values[0].model_copy(update={"candidateCropped": None})
    elif damage == "synthetic":
        values[0] = values[0].model_copy(update={"synthetic": True})
    else:
        values = [
            item.model_copy(update={"candidateFeatures": features(peak=0)}) for item in values
        ]
    result = assess_regression(p, sealed, values)
    assert result["state"] == "unqualified"
    assert sealed["configuration"] == p.menu[sealed["configurationIndex"]]


def test_other_game_and_mutated_seal_rejected():
    p = plan()
    wrong = targets()[0].model_copy(update={"gameId": UUID(int=8)})
    with pytest.raises(ValueError, match="GAME_MISMATCH"):
        seal_b(p, [wrong])
    sealed = seal_b(p, targets())
    sealed["configurationIndex"] = 99
    with pytest.raises(ValueError, match="CHECKSUM"):
        assess_regression(p, sealed, targets())
