"""New report dispatch and HTTP shape; fixture counts are not real qualification."""

from copy import deepcopy
from types import SimpleNamespace
from uuid import UUID

import pytest
from game_predictor_api.application.grid_model_evaluation import GridModelEvaluationService
from game_predictor_api.domain.full_board_calibration_report import attach_calibration, unqualified
from game_predictor_api.domain.grid_correction_evaluation import build_report
from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.production_cell_evaluation import (
    BASE_VERSION_ID,
    attach_content,
)
from game_predictor_api.schemas.grid_model_evaluations import GridProductionCellEvaluationReport
from test_grid_correction_evaluation import fixture, metrics, role


def production_report(*, calibrated=False, missing=False):
    manifest, old = fixture()
    manifest["baseVersionId"] = BASE_VERSION_ID
    measured = {
        game["gameId"]: {
            "mode": "grid-only",
            "roles": {
                "VALIDATION": role(metrics(), metrics()),
                "REGRESSION": role(metrics(full=True), metrics(full=True, correct=13)),
            },
        }
        for game in old["games"]
    }
    raw = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=old["trainingGameId"],
        parity=old["parity"],
        cohorts=old["cohorts"],
        measured=measured,
        scope=old["scope"],
        checkpoint_selection=old["checkpointSelection"],
    )
    if calibrated:
        raw = attach_calibration(
            raw, [unqualified(g, "TEST_NO_CALIBRATION") for g in raw["requiredGameIds"]]
        )
    contents = []
    for game in raw["games"]:
        roles = {}
        for name in ("VALIDATION", "REGRESSION"):
            count = game["roles"][name]["base"]["boards_expected"]
            counts = dict(
                preserved=count * 15,
                borderline=0,
                clipped=0,
                missing=0,
                wrongCells=0,
                ties=0,
                foreignSymbols=0,
                ambiguousBoards=0,
                usableBoards=11,
            )
            roles[name] = dict(
                state="ready",
                reasonCodes=[],
                photos=5,
                fullPhotos=5 if name == "REGRESSION" else 0,
                slots=count * 15,
                visible=count * 15,
                unknown=0,
                occluded=0,
                outOfFrame=0,
                referenceSha256="e" * 64,
                base=counts,
                candidate={**counts, "usableBoards": 12},
                degradedInstances=0,
                newWrongCells=0,
                newTies=0,
                newForeignSymbols=0,
                newMatchAmbiguities=0,
            )
        contents.append(
            dict(
                gameId=game["gameId"],
                state="not_evaluable" if missing else "ready",
                reasonCodes=["CONTENT_REFERENCE_MISSING"] if missing else [],
                u=None if missing else 0.01,
                delta=None if missing else 0.001,
                measurementSha256=None if missing else "f" * 64,
                classifierSnapshotSha256s=["a" * 64],
                renderConfigurationSha256s=["b" * 64],
                freshRegression=True,
                roles=roles,
            )
        )
    return manifest, attach_content(raw, contents)


def evidence(manifest, report):
    return require_evaluation_evidence(
        report_id=UUID(int=22),
        report_json=canonical_json(report),
        report_sha256=descriptor_sha256(report),
        producer=report["producer"],
        invalidated=False,
        manifest=manifest,
        base_sha256="c" * 64,
        game_id=UUID(report["trainingGameId"]),
    )


@pytest.mark.parametrize("calibrated", [False, True])
def test_v6_http_roundtrip_and_publication_keep_raw_report(calibrated):
    manifest, report = production_report(calibrated=calibrated)
    assert report["verdict"] == "PASS"
    parsed = GridProductionCellEvaluationReport.model_validate(report)
    assert parsed.model_dump(mode="json") == report
    assert evidence(manifest, report).scoped
    if calibrated:
        assert report["automaticCalibration"] == report["rawQuality"]["automaticCalibration"]
    else:
        assert "automaticCalibration" not in parsed.model_dump(mode="json")


def test_legacy_quality_pass_cannot_admit_missing_content():
    manifest, report = production_report(missing=True)
    assert report["rawQuality"]["verdict"] == "PASS"
    assert report["verdict"] == "NOT_EVALUABLE"
    with pytest.raises(GridModelRegistryError):
        evidence(manifest, report)


def test_content_pass_preserves_calibrated_raw_revise_with_delta_and_usable_gain():
    from game_predictor_api.domain.production_cell_evaluation import require_report

    manifest, template = production_report(calibrated=True)
    original = template["rawQuality"]
    measured = {}
    for game in original["games"]:
        roles = deepcopy(game["roles"])
        for role_value in roles.values():
            # Raw gate rejects the NME increase; content gate allows measured delta.
            # No raw correct-board gain occurs, but usableBoards improves 11 -> 12.
            candidate = {**role_value["base"], "normalized_error": 0.0205}
            role_value["candidate"] = candidate
            role_value["recordings"][0]["candidate"] = deepcopy(candidate)
        measured[game["gameId"]] = {"mode": game["mode"], "roles": roles}
    quality = build_report(
        manifest=manifest,
        base_manifest_sha256="c" * 64,
        training_game_id=original["trainingGameId"],
        parity=original["parity"],
        cohorts=original["cohorts"],
        measured=measured,
        scope=original["scope"],
        checkpoint_selection=original["checkpointSelection"],
    )
    raw = attach_calibration(quality, original["automaticCalibration"])
    frozen_raw = canonical_json(raw)
    assert raw["schemaVersion"] == "grid-model-evaluation-read-v5"
    assert raw["verdict"] == "REVISE"
    report = attach_content(raw, template["contentEvaluation"])
    assert report["verdict"] == "PASS"
    assert canonical_json(report["rawQuality"]) == canonical_json(raw) == frozen_raw
    assert report["automaticCalibration"] == raw["automaticCalibration"]
    assert (
        GridProductionCellEvaluationReport.model_validate(report).model_dump(mode="json") == report
    )
    assert require_report(canonical_json(report), manifest=manifest, base_sha256="c" * 64) == report
    assert evidence(manifest, report).scoped


@pytest.mark.parametrize(
    "schema,policy",
    [
        ("grid-model-evaluation-read-v6", "grid-model-per-game-gate-v2"),
        ("grid-model-evaluation-read-v6", "grid-model-per-game-gate-v3"),
        ("grid-model-evaluation-read-v5", "production-cell-per-game-gate-v1"),
        ("grid-model-evaluation-read-v3", "production-cell-per-game-gate-v1"),
    ],
)
def test_publication_rejects_crossed_report_gate_pair(schema, policy):
    manifest, report = production_report()
    report.update(schemaVersion=schema, policyVersion=policy)
    with pytest.raises(GridModelRegistryError):
        evidence(manifest, report)


def test_api_reader_dispatches_v6_and_rejects_forged_decision(monkeypatch):
    import game_predictor_api.application.grid_model_evaluation as application

    manifest, report = production_report()
    records = {
        UUID(manifest["versionId"]): SimpleNamespace(manifest_json=canonical_json(manifest)),
        UUID(BASE_VERSION_ID): SimpleNamespace(manifest_sha256="c" * 64),
    }
    monkeypatch.setattr(
        application,
        "SqlAlchemyGridModelRegistryRepository",
        lambda session: SimpleNamespace(version=records.get),
    )
    row = SimpleNamespace(
        version_id=UUID(manifest["versionId"]),
        producer=report["producer"],
        report_json=canonical_json(report),
    )
    service = object.__new__(GridModelEvaluationService)
    assert service._report(None, row) == report
    forged = deepcopy(report)
    forged["games"][0]["reasons"] = ["FORGED"]
    row.report_json = canonical_json(forged)
    with pytest.raises(GridModelRegistryError):
        service._report(None, row)


def test_operation_evidence_passes_real_artifact_root(monkeypatch, tmp_path):
    import game_predictor_api.storage.neural_grid_operation_qualification as qualification

    observed = []
    monkeypatch.setattr(qualification, "snapshot_descriptor", lambda snapshot: {})
    monkeypatch.setattr(qualification, "SqlAlchemyGridModelRegistryRepository", lambda s: s)

    def service(repo, inspector):
        observed.append(inspector.root)
        return SimpleNamespace(
            control=SimpleNamespace(_eligible_inspected=lambda *a, **k: ({}, {}))
        )

    monkeypatch.setattr(qualification, "GridModelRegistryService", service)
    qualification._evidence(None, None, UUID(int=1), tmp_path)
    qualification._evidence(None, None, UUID(int=1))
    assert observed == [tmp_path, None]


@pytest.mark.parametrize("version", ["legacy", "content", "calibrated-content"])
def test_http_get_and_list_serialize_exact_report_without_new_nulls(version):
    import asyncio

    from fastapi import FastAPI
    from game_predictor_api.api.grid_model_evaluations import create_grid_model_evaluations_router
    from httpx import ASGITransport, AsyncClient
    from test_grid_correction_learning_api import evaluation_value

    _, report = production_report(calibrated=version == "calibrated-content")
    if version == "legacy":
        report = report["rawQuality"]
    view = {**evaluation_value(), "report": report, "verdict": report["verdict"]}
    service = SimpleNamespace(get=lambda _: view, list=lambda _: {"items": [view]})
    app = FastAPI()
    app.include_router(create_grid_model_evaluations_router(lambda: service))

    async def read():
        async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
            response = await client.get(
                "/api/v1/admin/grid-model-evaluations/" + view["evaluationId"]
            )
            assert response.status_code == 200
            assert response.json()["report"] == report
            response = await client.get(
                "/api/v1/admin/grid-model-evaluations", params={"versionId": view["versionId"]}
            )
            assert response.status_code == 200
            assert response.json()["items"][0]["report"] == report

    asyncio.run(read())
