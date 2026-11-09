"""Real frozen readers reject bad evidence before any network is created."""

from copy import deepcopy

import pytest
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_worker.images.grid_content_experiment_data import require_render_preflight
from game_predictor_worker.images.production_cell_run import ProductionContentRun
from test_production_cell_frozen_pipeline import frozen_fixture


def v2_references(fixture, rows, split, root):
    from game_predictor_api.domain.grid_render_reference import execution_context
    from test_production_crop_comparison import model

    classifier = model(root).to_payload()
    configuration = {
        **rows[0]["targets"][0]["productionContentReference"]["sourceContext"][
            "renderConfiguration"
        ],
        "paddingFraction": 0.08,
    }
    body = {
        "version": "active-symbol-render-contract-v1",
        "gameId": fixture.game,
        "classifier": classifier,
        "renderConfiguration": configuration,
        "renderConfigurationSha256": digest(configuration),
    }
    contract = {**body, "sha256": digest(body)}
    split["contentSampling"]["evaluationContract"] = contract
    for source in rows:
        for target in source["targets"]:
            old = target["productionContentReference"]
            measurement = deepcopy(old["measurement"])
            if measurement is not None:
                report = measurement["report"]
                report["evaluationContract"] = contract
                report["sha256"] = digest({k: v for k, v in report.items() if k != "sha256"})
            provenance = old["sourceContext"]
            context = execution_context(provenance, contract)
            body = {
                "version": "production-cell-evaluation-reference-v2",
                "evaluationContract": contract,
                "importProvenance": provenance,
                "importProvenanceSha256": digest(provenance),
                "sourceContext": context,
                "sourceContextSha256": digest(context),
                "measurement": measurement,
            }
            target["productionContentReference"] = {**body, "sha256": digest(body)}
            if measurement is not None:
                oracle = {
                    "contentReferenceSha256": target["contentReferenceSha256"],
                    "renderConfiguration": configuration,
                    "classifierSnapshotSha256": digest(
                        {"classifier": classifier, "renderConfiguration": configuration}
                    ),
                }
                target["contentOracle"] = {**oracle, "sha256": digest(oracle)}
    return contract


def test_complete_a_does_not_require_b_or_reg_labels(tmp_path):
    def configure(_fixture, rows, split):
        for source in rows:
            if source.get("validationPurpose") != "A":
                for target in source["targets"]:
                    target.pop("productionContentReference", None)
                    target.pop("contentAnnotation", None)
                    target.pop("contentReferenceSha256", None)
                    target.pop("contentReferenceRevision", None)

    _, snapshot, _ = frozen_fixture(tmp_path, configure=configure)
    require_render_preflight([snapshot])


def test_direct_evaluation_rejects_legacy_reference_under_v2_selection(tmp_path):
    def configure(_fixture, rows, split):
        split.setdefault("contentSampling", {})["evaluationContract"] = {"sha256": "a" * 64}

    _, snapshot, _ = frozen_fixture(tmp_path, configure=configure)
    with pytest.raises(ContentError) as error:
        ProductionContentRun(snapshot)
    assert error.value.code == "CONTENT_PRODUCTION_REFERENCE_INVALID"


@pytest.mark.parametrize("mutation", ["missing_a", "measurement"])
def test_preflight_rejects_missing_a_or_mixed_existing_control_contract(tmp_path, mutation):
    def configure(_fixture, rows, split):
        target = rows[1 if mutation == "mixed_b" else 0]["targets"][0]
        if mutation == "missing_a":
            target.pop("productionContentReference")
        else:
            pin = target["productionContentReference"]
            if mutation == "mixed_b":
                pin["sourceContext"] = deepcopy(pin["sourceContext"])
                pin["sourceContext"]["renderConfiguration"]["paddingFraction"] = 0.2
                pin["sourceContextSha256"] = digest(pin["sourceContext"])
            else:
                pin["measurement"] = None
            pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})

    _, snapshot, _ = frozen_fixture(tmp_path, configure=configure)
    with pytest.raises(ValueError, match="CONTENT_"):
        require_render_preflight([snapshot])


def test_legacy_mixed_b_and_unavailable_train_do_not_gain_v2_rules(tmp_path):
    def configure(fixture, rows, split):
        pin = rows[1]["targets"][0]["productionContentReference"]
        pin["sourceContext"]["renderConfiguration"]["paddingFraction"] = 0.2
        pin["sourceContextSha256"] = digest(pin["sourceContext"])
        pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})
        source = fixture.source("TRAIN")
        source.update(validationPurpose=None, purposeProofSha256="d" * 64)
        unavailable = {
            "version": "production-cell-evaluation-reference-v1",
            "sourceContext": {"state": "unavailable"},
            "sourceContextSha256": digest({"state": "unavailable"}),
            "measurement": None,
        }
        source["targets"][0]["productionContentReference"] = {
            **unavailable,
            "sha256": digest(unavailable),
        }
        split["sources"].append(
            {
                "sourceId": source["sourceId"],
                "role": "TRAIN",
                "validationPurpose": None,
                "representative": True,
                "purposeProofSha256": "d" * 64,
                "eligibleBoards": 1,
                "componentIds": [],
            }
        )

    _, snapshot, _ = frozen_fixture(tmp_path, configure=configure)
    require_render_preflight([snapshot])
    require_render_preflight([snapshot])  # retry has the same legacy input interpretation


@pytest.mark.parametrize(
    "mutation",
    ["none", "two_a", "mixed_b", "missing_second_a", "missing_second_oracle", "unavailable_b"],
)
def test_v2_checks_each_a_board_and_keeps_unavailable_controls_explicit(tmp_path, mutation):
    def configure(fixture, rows, split):
        if mutation.startswith("missing_second") or mutation == "two_a":
            target = deepcopy(rows[0]["targets"][0])
            target["positionIndex"] = 1
            target["sequenceNumber"] += 1
            annotation = target["contentAnnotation"]
            annotation["reference"]["positionIndex"] = 1
            annotation["sequenceNumber"] = target["sequenceNumber"]
            target["contentReferenceSha256"] = digest(annotation)
            target["blindGeometry"]["contentReferenceSha256"] = digest(annotation)
            rows[0]["targets"].append(target)
            split["sources"][0]["eligibleBoards"] = 2
            split["purposeCounts"]["VALIDATION-A"]["boards"] = 2
        v2_references(fixture, rows, split, tmp_path)
        target = (
            rows[0]["targets"][-1]
            if mutation.startswith("missing_second")
            else rows[1]["targets"][0]
        )
        pin = target["productionContentReference"]
        if mutation == "mixed_b":
            pin["evaluationContract"] = deepcopy(pin["evaluationContract"])
            contract = pin["evaluationContract"]
            from dataclasses import replace

            from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

            contract["classifier"] = replace(
                SymbolModelJobSnapshot.from_payload(contract["classifier"]),
                onnx_checksum_sha256="c" * 64,
            ).to_payload()
            contract["sha256"] = digest({k: v for k, v in contract.items() if k != "sha256"})
            pin["sourceContext"]["classifier"] = contract["classifier"]
            pin["sourceContextSha256"] = digest(pin["sourceContext"])
        elif mutation == "missing_second_a":
            pin["measurement"] = None
        elif mutation == "missing_second_oracle":
            target.pop("contentOracle")
        elif mutation == "unavailable_b":
            missing = {"state": "unavailable", "reasonCode": "CONTENT_ORACLE_PROVENANCE_MISSING"}
            pin.update(
                sourceContext=missing,
                importProvenance=missing,
                sourceContextSha256=digest(missing),
                importProvenanceSha256=digest(missing),
            )
        pin["sha256"] = digest({k: v for k, v in pin.items() if k != "sha256"})

    _, snapshot, _ = frozen_fixture(tmp_path, configure=configure)
    if mutation in ("none", "two_a", "unavailable_b"):
        require_render_preflight([snapshot])
    else:
        expected = {
            "mixed_b": "CONTENT_RENDER_CONTRACT_MIXED",
            "missing_second_a": "CONTENT_A_MEASUREMENT_REQUIRED",
            "missing_second_oracle": "CONTENT_ORACLE_CONTRACT_CHANGED",
        }[mutation]
        with pytest.raises(ValueError, match=expected):
            require_render_preflight([snapshot])
