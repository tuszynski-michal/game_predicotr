from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from game_predictor_api.api.semi_automatic_image_selections import (
    create_semi_automatic_image_selections_router,
)
from game_predictor_api.application.semi_automatic_image_selections import (
    SemiAutomaticImageSelectionService,
)
from game_predictor_api.domain.jobs import JobError, JobStatus
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSourceManifest,
    SemiAutomaticSelectionWorkflowMode,
    create_semi_automatic_selection_run,
    create_v7_selection_configuration,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7_PENDING_STATES,
    V7PilotGate,
    V7SourcePolicy,
)
from game_predictor_worker.semi_automatic_selection.contracts import (
    SemiAutomaticSelectionDirection as WorkerDirection,
)
from game_predictor_worker.semi_automatic_selection.contracts import SemiAutomaticSelectionRange
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    build_local_source_manifest,
    write_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7_CALIBRATION_POSITION_CONFIDENCE,
    V7_DYNAMIC_GEOMETRY_FAMILY_ID,
    V7GeometryCalibration,
    V7GeometryProfile,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7BorderStyle
from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
    V7DynamicGridLabelLocatorConfig,
)
from game_predictor_worker.semi_automatic_selection.v7_partial_profile_bound_observer import (
    V7PartialProfileBoundObserverFactory,
    v7_partial_profile_bound_localizer_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.v7_quality import (
    V7BlurSeverity,
    V7BoardQuality,
    V7BoardReadability,
    V7BoardVisibility,
    V7DecorationVisibility,
    V7FrameQuality,
    V7OcclusionSeverity,
    V7SymbolContentLoss,
)
from game_predictor_worker.semi_automatic_selection.v7_range_proof import (
    V7RangeProofKind,
    V7RangeProofResult,
)
from game_predictor_worker.semi_automatic_selection.v7_review_projection import source_diagnostics
from game_predictor_worker.semi_automatic_selection.v7_run_state import (
    V7ScanObservation,
    V7ScanRunState,
)
from game_predictor_worker.semi_automatic_selection.v7_worker_runtime import (
    V7SourceObservationRequest,
    V7WorkerConfiguration,
)
from PIL import Image
from test_semi_automatic_image_selections import MemorySemiAutomaticSelectionRepository


class V7MemoryRepository(MemorySemiAutomaticSelectionRepository):
    def __init__(self, gate):
        super().__init__()
        self.gate = gate
        self.operations = {}
        self.diagnostics = {}

    def get_v7_pilot_gate(self, **_kwargs):
        return self.gate

    def get_v7_output_operation(self, operation_id, **_kwargs):
        return self.operations.get(operation_id)

    def get_pending_v7_output(self, run_id, **_kwargs):
        return next(
            (
                op
                for op in self.operations.values()
                if op.run_id == run_id and op.state in V7_PENDING_STATES
            ),
            None,
        )

    def save_v7_output_operation(self, operation):
        self.operations[operation.operation_id] = operation
        return operation

    def get_v7_source_observations(self, run_id, source_indexes):
        return {
            index: self.diagnostics[index] for index in source_indexes if index in self.diagnostics
        }


def delivery_fixture(
    tmp_path: Path,
    *,
    direction=SemiAutomaticSelectionDirection.ASCENDING,
    source_content=b"selected-jpeg-fixture",
    source_policy: V7SourcePolicy = "exact_sources",
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "1.jpg").write_bytes(source_content)
    manifest = build_local_source_manifest(source, selection_id=uuid4(), display_name="fixture")
    artifacts = tmp_path / "artifacts"
    relative = write_local_source_manifest(artifacts, manifest)
    gate = V7PilotGate(
        "active",
        7,
        "semi_automatic",
        "family",
        "game",
        "a" * 64,
        "b" * 64,
        "c" * 64,
        (
            {
                "sourceRoot": str(source.resolve()),
                "sourceFingerprint": manifest.source_fingerprint,
                "sourceGameRef": "game",
                "geometryFamilyId": "family",
            },
        ),
        "d" * 64,
        True,
    )
    if source_policy == "operator_selected_local_folder":
        gate = replace(gate, source_game_ref=None, source_bindings=(), source_policy=source_policy)
    configuration = create_v7_selection_configuration(
        first_sequence_number=1,
        last_sequence_number=18,
        direction=direction,
        calibration_fingerprint="a" * 64,
        localizer_fingerprint="b" * 64,
        pilot=gate.snapshot_for(source, manifest.source_fingerprint),
    )
    run, ranges = create_semi_automatic_selection_run(
        source=SemiAutomaticSelectionSourceManifest(
            manifest.selection_id,
            manifest.display_name,
            manifest.checksum_sha256,
            manifest.source_fingerprint,
            1,
            manifest.total_bytes,
        ),
        first_sequence_number=1,
        last_sequence_number=18,
        direction=direction,
        recognizer_fingerprint="c" * 64,
        grouping_policy_fingerprint="e" * 64,
        workflow_mode=SemiAutomaticSelectionWorkflowMode.V7_SELECTION,
        v7_configuration=configuration,
        local_source_manifest_relative_path=relative,
    )
    run = replace(
        run,
        status=SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
        job=replace(run.job, status=JobStatus.WAITING_FOR_REVIEW),
        checkpoint={"scanState": {"phase": "finalized"}},
    )
    repository = V7MemoryRepository(gate)
    repository.runs[run.id] = run
    repository.ranges.update(
        {
            (run.id, item.expected_index): replace(
                item,
                v7_projection_fingerprint="f" * 64,
                v7_review={
                    "version": "v7-review-projection-v1",
                    "rangeStart": item.range_start,
                    "rangeEnd": item.range_end,
                    "candidate": None,
                    "provenSources": [],
                    "occurrenceId": None,
                    "manualConfirmationRequired": True,
                    "sourceManifestFingerprint": manifest.source_fingerprint,
                },
            )
            for item in ranges
        }
    )
    state = V7ScanRunState(
        manifest,
        expected_ranges=(SemiAutomaticSelectionRange(1, 9), SemiAutomaticSelectionRange(10, 18)),
        border_style=V7BorderStyle.TOP_AND_SIDES,
    )
    state.consume(
        V7ScanObservation(
            0,
            V7RangeProofResult(V7RangeProofKind.NONE, None, (), ("NO_LABELS",)),
            V7FrameQuality(
                state.source_manifest.sources[0].source_id,
                0,
                tuple(
                    V7BoardQuality(
                        index,
                        V7SymbolContentLoss.UNKNOWN,
                        V7BoardReadability.UNKNOWN,
                        V7BoardVisibility.UNKNOWN,
                        V7BlurSeverity.UNKNOWN,
                        V7OcclusionSeverity.UNKNOWN,
                        V7DecorationVisibility.UNKNOWN,
                    )
                    for index in range(9)
                ),
            ),
        )
    )
    repository.diagnostics = source_diagnostics(state.checkpoint())
    service = SemiAutomaticImageSelectionService(
        repository,
        object(),
        enabled=True,
        artifact_root=artifacts,
        v7_artifacts=SimpleNamespace(validate=lambda _gate: None),
    )
    app = FastAPI()

    @app.exception_handler(JobError)
    def job_error(_request, error):
        return JSONResponse(
            status_code=409, content={"error": {"code": error.code, "message": error.message}}
        )

    app.include_router(create_semi_automatic_image_selections_router(lambda: service))
    return TestClient(app), repository, service, run, manifest


def decision_body(run, manifest, *, expected_index=1, start=10, end=18):
    return {
        "workflowMode": "v7_selection",
        "operationId": str(uuid4()),
        "expectedRevision": 0,
        "sourceIndex": 0,
        "expectedSourceChecksumSha256": manifest.sources[0].checksum_sha256,
        "kind": "manual_no_ocr",
        "confirmedRange": {"start": start, "end": end},
        "operatorConfirmedRange": True,
        "operatorConfirmedIncompletePage": False,
    }


def test_feedback_reason_and_snapshot_survive_retry_without_recapturing_review(tmp_path):
    from game_predictor_api.domain.v7_selection_delivery import payload_fingerprint

    client, repository, _service, run, manifest = delivery_fixture(tmp_path)
    body = {**decision_body(run, manifest), "correctionReason": "occlusion"}
    url = f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements"
    response = client.post(url, json=body)
    assert response.status_code == 200, response.text
    operation = next(iter(repository.operations.values()))
    context = operation.context_payload
    snapshot = context["feedbackSnapshot"]
    assert operation.decision.correction_reason == "occlusion"
    assert context["feedbackFingerprint"] == payload_fingerprint(snapshot)
    assert snapshot["proposal"] is None
    assert snapshot["selectedSource"]["checksumSha256"] == manifest.sources[0].checksum_sha256
    # Mutable review/diagnostics after a lost response must not alter the frozen intent.
    repository.diagnostics[0]["slots"][0]["readability"] = "readable"
    repository.ranges[(run.id, 1)].v7_review["candidate"] = {
        "sourceIndex": 0,
        "sourceId": "a" * 64,
        "proofKinds": [],
        "warnings": [],
    }
    retry = client.post(url, json=body)
    assert retry.status_code == 200
    assert retry.json()["outputOperation"] == response.json()["outputOperation"]
    assert snapshot["selectedDiagnostics"]["slots"][0]["readability"] == "unknown"
    assert snapshot["proposal"] is None
    assert len(repository.operations) == 1
    assert (
        client.post(url, json={**body, "correctionReason": "blur"}).json()["error"]["code"]
        == "V7_OPERATION_ID_CONFLICT"
    )


def test_feedback_absent_or_null_reason_preserves_historical_body(tmp_path):
    client, repository, _service, run, manifest = delivery_fixture(tmp_path)
    capability = client.get("/admin/semi-automatic-image-selections/capabilities")
    assert capability.status_code == 200
    assert capability.json()["v7"]["feedbackTraceVersion"] == "v7-selection-feedback-context-v1"
    body = decision_body(run, manifest)
    url = f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    operation = next(iter(repository.operations.values()))
    assert "correctionReason" not in operation.request_payload
    fingerprint = operation.request_fingerprint
    assert client.post(url, json={**body, "correctionReason": None}).json() == first.json()
    assert next(iter(repository.operations.values())).request_fingerprint == fingerprint
    assert client.post(url, json={**body, "correctionReason": "invented"}).status_code == 422


def test_configured_output_root_is_in_run_response_and_pinned_in_command(tmp_path):
    client, repository, service, run, manifest = delivery_fixture(tmp_path)
    service._v7_output_base = tmp_path / "outputs"
    expected = str(service._v7_output_base / str(run.id))
    response = client.get(f"/admin/semi-automatic-image-selections/{run.id}")
    assert response.status_code == 200
    assert response.json()["outputDirectory"] == expected
    body = decision_body(run, manifest)
    url = f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements"
    assert client.post(url, json=body).status_code == 200
    operation = next(iter(repository.operations.values()))
    assert operation.context_payload["outputRoot"] == expected
    service._v7_output_base = tmp_path / "another-config"
    repository.get_v7_output_root = lambda _id: expected
    assert service.output_directory(run) == expected
    assert client.post(url, json=body).status_code == 200
    assert next(iter(repository.operations.values())).context_payload["outputRoot"] == expected


def test_existing_legacy_owner_retains_sibling_after_new_output_config(tmp_path):
    _, repository, service, run, manifest = delivery_fixture(tmp_path)
    service._v7_output_base = tmp_path / "new-outputs"
    repository.get_v7_output_root = lambda _id: ""
    assert service.output_directory(run) == str(manifest.source_root.with_name("source cut"))


@pytest.mark.parametrize("source_policy", ["exact_sources", "operator_selected_local_folder"])
def test_reservation_is_not_publication_exact_retry_survives_lost_response(tmp_path, source_policy):
    client, repository, _service, run, manifest = delivery_fixture(
        tmp_path, source_policy=source_policy
    )
    body = decision_body(run, manifest)
    url = f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements"
    first = client.post(url, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "missing"
    assert first.json()["outputChecksumSha256"] is None
    assert first.json()["outputOperation"]["state"] == "reserved"
    assert client.post(url, json=body).json() == first.json()
    for action in ("pause", "cancel"):
        assert (
            client.post(f"/admin/semi-automatic-image-selections/{run.id}/{action}").json()[
                "error"
            ]["code"]
            == "V7_OUTPUT_DECISION_PENDING"
        )
    mutated = {**body, "sourceIndex": 1}
    assert client.post(url, json=mutated).json()["error"]["code"] == "V7_OPERATION_ID_CONFLICT"
    assert not (tmp_path / "source cut").exists()
    assert len(repository.operations) == 1


@pytest.mark.parametrize(
    "direction,last_index,start,end", [("ascending", 1, 11, 15), ("descending", 0, 2, 6)]
)
def test_partial_requires_explicit_actual_incomplete_last_expected_page(
    tmp_path, direction, last_index, start, end
):
    client, _repository, _service, run, manifest = delivery_fixture(
        tmp_path, direction=SemiAutomaticSelectionDirection(direction)
    )
    body = decision_body(run, manifest, start=start, end=end)
    url = (
        f"/admin/semi-automatic-image-selections/{run.id}/ranges/"
        f"{last_index}/output-acknowledgements"
    )
    assert (
        client.post(url, json=body).json()["error"]["code"]
        == "V7_INCOMPLETE_PAGE_CONFIRMATION_REQUIRED"
    )
    body["operatorConfirmedIncompletePage"] = True
    assert client.post(url, json=body).status_code == 200


def test_schema4_asset_and_nine_unknown_slots_use_local_manifest(tmp_path):
    client, _repository, _service, run, manifest = delivery_fixture(tmp_path)
    page = client.get(f"/admin/semi-automatic-image-selections/{run.id}/sources")
    assert page.status_code == 200, page.text
    slots = page.json()["items"][0]["v7Diagnostics"]["slots"]
    assert len(slots) == 9
    assert all(
        slot["state"] == "not_observed" and slot["readability"] == "unknown" for slot in slots
    )
    asset = client.get(
        f"/admin/semi-automatic-image-selections/{run.id}/sources/0/asset",
        params={"expected_checksum_sha256": manifest.sources[0].checksum_sha256},
    )
    assert asset.content == b"selected-jpeg-fixture"


def test_actual_decoded_unknown_geometry_rejection_allows_confirmed_manual_no_ocr(tmp_path):
    stream = BytesIO()
    Image.new("RGB", (560, 360), "white").save(stream, format="JPEG")
    content = stream.getvalue()
    client, repository, _service, run, manifest = delivery_fixture(tmp_path, source_content=content)
    profile = V7GeometryProfile(
        "c" * 64,
        V7GeometryCalibration(
            manifest_fingerprint="a" * 64,
            input_fingerprint="b" * 64,
            geometry_family_id=V7_DYNAMIC_GEOMETRY_FAMILY_ID,
            locator_config=V7DynamicGridLabelLocatorConfig(
                position_confidence=V7_CALIBRATION_POSITION_CONFIDENCE
            ),
            source_count_by_position=(5,) * 9,
            capture_group_count_by_position=(2,) * 9,
            p95_center_residual_by_position=(0.01,) * 9,
            p95_center_residual=0.01,
            maximum_p95_center_residual=0.04,
            minimum_sources_per_position=5,
            minimum_capture_groups_per_position=2,
        ),
        revision=0,
    )
    configuration = V7WorkerConfiguration(
        1,
        18,
        WorkerDirection.ASCENDING,
        V7BorderStyle.TOP_AND_SIDES,
        v7_partial_profile_bound_localizer_fingerprint(profile),
        profile.profile_fingerprint,
    )
    observer = V7PartialProfileBoundObserverFactory(
        profile,
        lambda: SimpleNamespace(
            recognize_many=lambda _crops: pytest.fail("Geometry rejection must not call OCR."),
        ),
    ).create(configuration, manifest)
    state = V7ScanRunState(
        manifest,
        expected_ranges=(SemiAutomaticSelectionRange(1, 9), SemiAutomaticSelectionRange(10, 18)),
        border_style=V7BorderStyle.TOP_AND_SIDES,
    )
    observation = observer.observe(
        V7SourceObservationRequest(state.source_manifest.sources[0], content)
    )
    assert observation.source_error_code is None
    assert observation.quality is not None
    assert "V7_LABEL_COMPONENTS_INSUFFICIENT" in observation.proof.reason_codes
    state.consume(observation)
    repository.diagnostics = source_diagnostics(state.checkpoint())
    diagnostics = repository.diagnostics[0]
    assert all(slot["readability"] == "unknown" for slot in diagnostics["slots"])
    url = f"/admin/semi-automatic-image-selections/{run.id}/ranges/1/output-acknowledgements"
    response = client.post(url, json=decision_body(run, manifest))
    assert response.status_code == 200, response.text
    assert response.json()["outputOperation"]["state"] == "reserved"
