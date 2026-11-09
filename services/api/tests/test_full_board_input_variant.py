"""Separate recorded input identity survives DTOs and rejects stale/false transforms."""

import json
from copy import deepcopy

import pytest
from game_predictor_api.domain.full_board_input_variant import (
    InputVariant,
    require_runtime_input_variant,
)
from game_predictor_api.domain.grid_model_registry import (
    descriptor_sha256 as digest,
)
from game_predictor_api.domain.grid_model_registry import (
    historical_catalogue,
)
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    proposal_checksum_sha256,
    validate_neural_source_proposal,
)
from game_predictor_api.schemas.neural_grid_proposals import NeuralSourceProposalPayload
from test_full_board_variant_calibration import contexts_fixture, stamp_fixture
from test_neural_grid_proposal import proposal


def seal(value):
    body = {k: v for k, v in value.items() if k != "sha256"}
    return {**body, "sha256": digest(body)}


def test_runtime_recomputes_support_and_binds_current_source_box():
    contexts, _ = contexts_fixture()
    context = next(c for c in contexts if c["stage"] == "wide")
    detection = {
        "detectionId": "det-1",
        "latticeNodes": [{"x": float(i), "y": float(i)} for i in range(24)],
    }
    stamp = stamp_fixture(context, detection)
    args = dict(
        pin={
            "catalogueManifestSha256": "a" * 64,
            "pinSha256": "b" * 64,
            "automaticQualification": {"profile": {"allowedVariants": contexts}},
        },
        proposal={"sourceChecksumSha256": "c" * 64, "sourceWidth": 1000, "sourceHeight": 1000},
        detection=detection,
    )
    assert require_runtime_input_variant(stamp, **args).sha256 == stamp["sha256"]
    changed = deepcopy(stamp)
    changed["boardInputSupport"][0][0] += 0.01
    with pytest.raises(ValueError, match="TRANSFORM_CHANGED"):
        require_runtime_input_variant(seal(changed), **args)
    with pytest.raises(ValueError, match="SOURCE_OR_OPERATION_CHANGED"):
        require_runtime_input_variant(stamp, **args, available_source_box=[1, 1, 999, 999])
    for key in ("sourceSha256", "modelManifestSha256", "nodesSha256", "operationPinSha256"):
        with pytest.raises(ValueError):
            require_runtime_input_variant(seal({**stamp, key: "0" * 64}), **args)
    for quad in ([[0.0, 0.0]] * 4, [[float("nan"), 0.0]] * 4):
        with pytest.raises(ValueError):
            InputVariant.model_validate(seal({**stamp, "screenQuad": quad}))


def test_optional_stamp_roundtrip_preserves_historical_bytes_and_binds_new_snapshot():
    old = proposal(count=1)
    encoded = json.dumps(old, sort_keys=True)
    assert (
        NeuralSourceProposalPayload.model_validate(old).model_dump(mode="json", by_alias=True)
        == old
    )
    assert json.dumps(old, sort_keys=True) == encoded
    contexts, _ = contexts_fixture()
    context = next(c for c in contexts if c["stage"] == "baseline")
    detection = old["detections"][0]
    stamp = stamp_fixture(context, detection)
    stamped = deepcopy(old)
    stamped["detections"][0]["inputVariant"] = stamp
    stamped["proposalChecksumSha256"] = proposal_checksum_sha256(stamped)
    with pytest.raises(ValueError, match="catalogue content"):
        validate_neural_source_proposal(stamped)
    descriptor = deepcopy(historical_catalogue()[0])
    descriptor.update(modelVersion="neural-grid-v2", bundleFormat="neural-grid-bundle-v2")
    descriptor["inferenceManifest"].update(
        modelVersion="neural-grid-v2", bundleFormat="neural-grid-bundle-v2"
    )
    snapshot = NeuralGridSnapshot.from_catalogue(
        game_id=old["gameId"],
        game_configuration="neural_grid_v3",
        expected_layout_count=500000,
        descriptor=descriptor,
    )
    stamped["engineSnapshot"] = snapshot.to_payload()
    stamp = seal(
        {
            **stamp,
            "modelManifestSha256": digest(descriptor),
            "sourceSha256": old["sourceChecksumSha256"],
            "availableSourceBox": [0, 0, 500, 300],
        }
    )
    stamped["detections"][0]["inputVariant"] = stamp
    stamped["proposalChecksumSha256"] = proposal_checksum_sha256(stamped)
    assert validate_neural_source_proposal(stamped) == stamped
    assert (
        NeuralSourceProposalPayload.model_validate(stamped).model_dump(mode="json", by_alias=True)
        == stamped
    )
    # The independently persisted proposal checksum covers the actual input stamp.
    stamped["detections"][0]["inputVariant"]["variantKey"] = "0" * 64
    with pytest.raises(ValueError, match="checksum"):
        validate_neural_source_proposal(stamped)


def test_finalizer_rejects_valid_old_base_proof_for_wide_input_with_identical_nodes():
    from game_predictor_api.domain.calibrated_neural_evidence import calibrated_result_blockers
    from game_predictor_api.domain.full_board_calibration import AXES_V2
    from game_predictor_api.domain.full_board_calibration_report import AutomaticProfile
    from game_predictor_api.domain.full_board_variant_calibration_types import (
        VariantAutomaticProfile,
    )
    from test_full_board_variant_calibration import GAME

    contexts, _ = contexts_fixture()
    # Two closed profiles are sufficient for this identity regression: no
    # calibration population, inference, environment switch or database is needed.
    children = []
    for context in contexts:
        child = AutomaticProfile.model_validate(
            seal(
                {
                    "version": "full-board-auto-profile-v2",
                    "gameId": str(GAME),
                    "candidateManifestSha256": "a" * 64,
                    "planSha256": "d" * 64,
                    "sealedSha256": "e" * 64,
                    "routingSha256": context["sha256"],
                    "configuration": dict.fromkeys(AXES_V2, 0.5),
                    "gameLogAspectReference": None,
                    "assessmentScope": "labelled_targets",
                }
            )
        )
        children.append({"variantKey": context["sha256"], "profile": child.model_dump(mode="json")})
    profile = VariantAutomaticProfile.model_validate(
        seal(
            {
                "version": "full-board-auto-profile-v3",
                "gameId": str(GAME),
                "candidateManifestSha256": "a" * 64,
                "routingSha256": contexts[0]["routingSha256"],
                "variantPlanSha256": "f" * 64,
                "allowedVariants": contexts,
                "usedVariantKeys": [context["sha256"] for context in contexts],
                "variants": children,
                "assessmentScope": "labelled_targets",
            }
        )
    ).model_dump(mode="json")
    pin = {
        "contractVersion": "neural-grid-operation-pin-v3",
        "catalogueManifestSha256": "a" * 64,
        "pinSha256": "b" * 64,
        "automaticQualification": {"state": "qualified", "profile": profile},
    }
    proposal = {"sourceChecksumSha256": "c" * 64, "sourceWidth": 1000, "sourceHeight": 1000}
    detection = {
        "detectionId": "same-board",
        "latticeNodes": [
            {"x": float(col), "y": float(row)} for row in range(4) for col in range(6)
        ],
    }
    documents, proofs = {}, {}
    for context, child in zip(contexts, children, strict=True):
        document = {**detection, "inputVariant": stamp_fixture(context, detection)}
        proof = seal(
            {
                "version": "full-board-result-evidence-v3",
                "sourceSha256": "c" * 64,
                "modelManifestSha256": "a" * 64,
                "operationPinSha256": "b" * 64,
                "profileSha256": profile["sha256"],
                "detectionId": detection["detectionId"],
                "nodesSha256": digest(detection["latticeNodes"]),
                "features": {
                    "version": "full-board-completeness-features-v2",
                    "values": dict.fromkeys(AXES_V2, 0.5),
                },
                "variantKey": context["sha256"],
                "variantProfileSha256": child["profile"]["sha256"],
                "inputVariantSha256": document["inputVariant"]["sha256"],
            }
        )
        assert (
            calibrated_result_blockers(proof, pin=pin, proposal=proposal, detection=document) == ()
        )
        documents[context["stage"]], proofs[context["stage"]] = document, proof
    assert documents["baseline"]["latticeNodes"] == documents["wide"]["latticeNodes"]
    assert proofs["baseline"]["nodesSha256"] == proofs["wide"]["nodesSha256"]
    assert calibrated_result_blockers(
        proofs["baseline"], pin=pin, proposal=proposal, detection=documents["wide"]
    ) == ("COMPLETENESS_INPUT_VARIANT_CHANGED",)
