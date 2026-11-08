"""V2 numeric tests are not qualification of an operator model."""

import math
from uuid import UUID

import pytest
from game_predictor_api.domain.full_board_calibration import (
    AXES,
    AXES_V2,
    FeatureVector,
    ReferenceTarget,
    acceptance_reasons,
    make_plan,
)
from game_predictor_api.domain.input_edge_clearance import (
    InputEdgeReference,
    select_input_edge_threshold,
)


def references():
    return [
        InputEdgeReference(
            sourceRepresentativeSha256=f"{i // 2:064x}",
            positionIndex=i % 2,
            variantSha256="4" * 64,
            clearance=0.1 + i * 0.01,
            inputCropped=True,
            referenceKind="verified_content",
            contentReferenceSha256=f"{100 + i:064x}",
            contentRevision=1,
        )
        for i in range(6)
    ]


def test_edge_minimum_real_cuts_per_variant_and_no_negative_data():
    refs = references()
    proxies = [
        item.model_copy(
            update={
                "referenceKind": "geometry_proxy",
                "contentReferenceSha256": None,
                "contentRevision": None,
            }
        )
        for item in refs
    ]
    assert select_input_edge_threshold(proxies, "4" * 64)[0] is None
    assert select_input_edge_threshold(refs[:4], "4" * 64)[0] is None
    assert (
        select_input_edge_threshold(
            [x.model_copy(update={"inputCropped": False}) for x in refs], "4" * 64
        )[0]
        is None
    )
    assert (
        select_input_edge_threshold(
            [x.model_copy(update={"synthetic": True}) for x in refs], "4" * 64
        )[0]
        is None
    )
    assert select_input_edge_threshold(refs * 3, "4" * 64)[1]["cutTargets"] == 6
    with pytest.raises(ValueError, match="VARIANT_MISMATCH"):
        select_input_edge_threshold(refs, "5" * 64)


def test_edge_objective_missed_then_unnecessary_then_lower_threshold_and_ties():
    refs = references()
    good = refs[0].model_copy(
        update={"sourceRepresentativeSha256": "f" * 64, "clearance": 0.2, "inputCropped": False}
    )
    threshold, counts = select_input_edge_threshold([*refs, good], "4" * 64)
    assert threshold == math.nextafter(max(x.clearance for x in refs), math.inf)
    assert counts["cutSources"] == 3
    # Equal confidence cannot magically separate opposite outcomes.
    tied = good.model_copy(update={"clearance": max(x.clearance for x in refs)})
    assert select_input_edge_threshold([*refs, tied], "4" * 64)[0] == threshold
    assert select_input_edge_threshold(list(reversed(refs)) + refs, "4" * 64)[0] == threshold


def plan(refs):
    return make_plan(
        refs,
        game_id=UUID(int=1),
        candidate_sha="2" * 64,
        baseline_sha="3" * 64,
        routing_sha="4" * 64,
        role_proof_sha="5" * 64,
        b_assessment_sha="6" * 64,
        regression_assessment_sha="7" * 64,
    )


def test_v2_axis_is_one_a_threshold_and_never_extra_b_sweep():
    refs = [
        ReferenceTarget(
            gameId=UUID(int=1),
            sourceRepresentativeSha256=x.sourceRepresentativeSha256,
            positionIndex=x.positionIndex,
            role="VALIDATION-A",
            humanGood=False,
            features=FeatureVector(
                version="full-board-completeness-features-v2",
                values={**dict.fromkeys(AXES, 0.5), "inputEdgeClearance": x.clearance},
            ),
            inputEdgeReference=x,
        )
        for x in references()
    ]
    for i in range(100):
        refs.append(
            ReferenceTarget(
                gameId=UUID(int=1),
                sourceRepresentativeSha256=f"{100 + i:064x}",
                positionIndex=0,
                role="VALIDATION-A",
                humanGood=True,
                features=FeatureVector(
                    version="full-board-completeness-features-v2",
                    values={**dict.fromkeys(AXES, i / 100), "inputEdgeClearance": 1},
                ),
            )
        )
    result = plan(refs)
    assert result.version == "full-board-calibration-plan-v2"
    assert len(result.menu) == 256
    assert set(result.axisCounts) == set(AXES_V2)
    assert len({x["inputEdgeClearance"] for x in result.menu}) == 1
    absent = plan([x.model_copy(update={"inputEdgeReference": None}) for x in refs])
    assert "inputEdgeClearance" in absent.manualWhenApplicable
    assert "COMPLETENESS_REFERENCE_MISSING:inputEdgeClearance" in acceptance_reasons(
        refs[-1].features, absent.menu[0]
    )


def test_legacy_payload_has_no_new_null_fields_or_axes():
    feature = FeatureVector(values=dict.fromkeys(AXES, 0.5))
    ref = ReferenceTarget(
        gameId=UUID(int=1),
        sourceRepresentativeSha256="1" * 64,
        positionIndex=0,
        role="TRAIN",
        humanGood=True,
        features=feature,
    )
    assert "inputEdgeReference" not in ref.model_dump(mode="json")
    result = plan([ref])
    assert result.version == "full-board-calibration-plan-v1" and set(result.menu[0]) == set(AXES)


def test_v2_profile_survives_operation_pin_validation_and_requires_exact_axes():
    from game_predictor_api.domain.grid_training_cohorts import digest
    from game_predictor_api.domain.neural_grid_operation_pin import require_automatic_qualification

    game = str(UUID(int=1))
    profile = {
        "version": "full-board-auto-profile-v2",
        "gameId": game,
        "candidateManifestSha256": "2" * 64,
        "planSha256": "3" * 64,
        "sealedSha256": "4" * 64,
        "routingSha256": "5" * 64,
        "configuration": dict.fromkeys(AXES_V2, 0.5),
        "gameLogAspectReference": 0.0,
        "assessmentScope": "labelled_targets",
    }
    profile["sha256"] = digest(profile)
    value = {
        "state": "qualified",
        "reasonCodes": [],
        "reportId": str(UUID(int=2)),
        "reportSha256": "6" * 64,
        "profile": profile,
    }
    assert require_automatic_qualification(value, game_id=game, manifest_sha="2" * 64) == value
    profile["configuration"].pop("inputEdgeClearance")
    profile["sha256"] = digest({k: v for k, v in profile.items() if k != "sha256"})
    with pytest.raises(ValueError, match="PROFILE_INVALID"):
        require_automatic_qualification(value, game_id=game, manifest_sha="2" * 64)


def test_api_requires_trusted_a_content_hash_and_revision_not_worker_claim():
    from game_predictor_api.domain.full_board_assessment_reference import FrozenAssessmentReferences

    edge = references()[0]
    target = {
        "positionIndex": 0,
        "contentReferenceSha256": edge.contentReferenceSha256,
        "contentReferenceRevision": edge.contentRevision,
        "contentReferenceInputCropped": edge.inputCropped,
    }
    source = {
        "sourceId": str(UUID(int=3)),
        "sourceIdentity": {"normalized_pixel_checksum_sha256": edge.sourceRepresentativeSha256},
        "targets": [target],
        "validationPurpose": "A",
        "purposeProofSha256": "8" * 64,
    }
    frozen = FrozenAssessmentReferences.from_sources(
        {
            "gameId": str(UUID(int=1)),
            "cohortId": str(UUID(int=2)),
            "photoSplit": {"sha256": "9" * 64},
        },
        "a" * 64,
        {"A": [source], "B": [], "REGRESSION": []},
    )

    def prepared(reference):
        ref = ReferenceTarget(
            gameId=UUID(int=1),
            sourceRepresentativeSha256=edge.sourceRepresentativeSha256,
            positionIndex=0,
            role="VALIDATION-A",
            humanGood=False,
            features=FeatureVector(
                version="full-board-completeness-features-v2",
                values={**dict.fromkeys(AXES, 0.5), "inputEdgeClearance": edge.clearance},
            ),
            inputEdgeReference=reference,
        )
        p = make_plan(
            [ref],
            game_id=frozen.game_id,
            candidate_sha="2" * 64,
            baseline_sha="3" * 64,
            routing_sha="4" * 64,
            role_proof_sha=frozen.role_proof_sha256,
            b_assessment_sha=frozen.references["B"],
            regression_assessment_sha=frozen.references["REGRESSION"],
        )
        return {
            "plan": p.model_dump(mode="json"),
            "selectionReferences": [ref.model_dump(mode="json")],
            "referenceAssessmentSha256": frozen.references["A"],
            "cohortManifestSha256": frozen.manifest_sha256,
            "cohortId": str(frozen.cohort_id),
            "bTargets": 0,
            "bSources": 0,
            "regressionTargets": 0,
            "regressionSources": 0,
            "plannedConfigurations": len(p.menu),
            "plannedComparisons": 0,
        }

    assert frozen.require_plan(prepared(edge)).axisCounts["inputEdgeClearance"]["cutTargets"] == 1
    for fault in (
        {"contentReferenceSha256": "f" * 64},
        {"contentRevision": 2},
        {"inputCropped": not edge.inputCropped},
    ):
        with pytest.raises(ValueError, match="FROZEN_CONTENT_REFERENCE_REQUIRED"):
            frozen.require_plan(prepared(edge.model_copy(update=fault)))
    from dataclasses import replace

    with pytest.raises(ValueError, match="FROZEN_CONTENT_REFERENCE_REQUIRED"):
        replace(frozen, content_references={}).require_plan(prepared(edge))
