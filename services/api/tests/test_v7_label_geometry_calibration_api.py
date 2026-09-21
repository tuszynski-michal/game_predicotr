from __future__ import annotations

import json
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import game_predictor_api.application.v7_label_geometry_calibration as label_geometry_application
import game_predictor_api.application.v7_label_geometry_validation as label_geometry_validation
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.v7_label_geometry_calibration import (
    create_v7_label_geometry_calibration_router,
)
from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationApiError,
    V7LabelGeometryCalibrationService,
)
from game_predictor_api.application.v7_label_geometry_validation import V7ValidationReport
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7AcceptanceEvaluation,
    V7AcceptanceMetric,
    V7GeometryAdoption,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration_sessions import (
    V7CalibrationSession,
    V7CalibrationSessionStatus,
)
from game_predictor_worker.semi_automatic_selection.v7_profile_bound_observer import (
    v7_profile_bound_localizer_fingerprint,
)
from PIL import Image

FAMILY = "standard_3x3_numeric_labels_v1"


def _write_jpeg(path: Path, *, color: tuple[int, int, int], orientation: int | None = None) -> None:
    image = Image.new("RGB", (40, 20), color)
    path.parent.mkdir(parents=True, exist_ok=True)
    if orientation is None:
        image.save(path, format="JPEG")
        return
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, format="JPEG", exif=exif)


def _service(tmp_path: Path, *, calibration_count: int = 5) -> V7LabelGeometryCalibrationService:
    root = tmp_path / "corpus"
    colors = [((index + 1) * 35, 50, 100) for index in range(calibration_count)]
    for index, color in enumerate(colors):
        _write_jpeg(root / "777" / f"cal-{index}.jpg", color=color, orientation=6)
    _write_jpeg(root / "development" / "dev.jpg", color=(10, 20, 30))
    _write_jpeg(root / "validation" / "validation.jpg", color=(30, 20, 10))
    _write_jpeg(root / "reels_test" / "holdout.jpg", color=(20, 10, 30))
    manifest = {
        "schemaVersion": 2,
        "corpusRoot": str(root),
        "cases": [
            {
                "caseId": "game777",
                "directoryName": "777",
                "split": "calibration",
                "borderStyle": "top_and_sides",
                "scenarios": ["small_groups"],
                "expectedDirection": "ascending",
                "geometryFamilyId": FAMILY,
                "sourceGameRef": "777",
            },
            {
                "caseId": "development",
                "directoryName": "development",
                "split": "development",
                "borderStyle": "top_and_sides",
                "scenarios": ["small_groups"],
                "expectedDirection": "ascending",
                "geometryFamilyId": FAMILY,
                "sourceGameRef": "777",
            },
            {
                "caseId": "validation",
                "directoryName": "validation",
                "split": "validation",
                "borderStyle": "top_and_sides",
                "scenarios": ["small_groups"],
                "expectedDirection": "ascending",
                "geometryFamilyId": FAMILY,
                "sourceGameRef": "777",
            },
            {
                "caseId": "reels_test",
                "directoryName": "reels_test",
                "split": "holdout",
                "borderStyle": "top_and_sides",
                "scenarios": ["holdout"],
                "expectedDirection": "ascending",
                "geometryFamilyId": FAMILY,
                "sourceGameRef": "777",
            },
        ],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return V7LabelGeometryCalibrationService(
        runtime_root=tmp_path / "runtime",
        corpus_manifest_path=manifest_path,
    )


def _operation(
    service: V7LabelGeometryCalibrationService,
    session: object,
    *,
    kind: str,
    source_id: str,
    position_index: int | None = None,
    capture_group_id: str | None = None,
    crop_assessment: str | None = None,
) -> tuple[object, object]:
    return service.mutate_session(
        session.session_id,  # type: ignore[attr-defined]
        service.operation_from_values(
            operation_id=str(uuid4()),
            expected_revision=session.revision,  # type: ignore[attr-defined]
            kind=kind,
            source_id=source_id,
            position_index=position_index,
            center_x=0.2 + (position_index or 0) * 0.01 if kind == "annotated" else None,
            center_y=0.3 + (position_index or 0) * 0.01 if kind == "annotated" else None,
            crop_assessment=(
                "contained" if kind == "annotated" and crop_assessment is None else crop_assessment
            ),
            capture_group_id=capture_group_id,
        ),
    )


def _complete_calibration_session(
    service: V7LabelGeometryCalibrationService,
) -> V7CalibrationSession:
    session = service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    for source_index, source in enumerate(session.sources):
        session, _receipt = _operation(
            service,
            session,
            kind="set_capture_group",
            source_id=source.source_id,
            capture_group_id="capture-a" if source_index < 3 else "capture-b",
        )
    for position_index in range(9):
        for source in session.sources:
            session, _receipt = _operation(
                service,
                session,
                kind="annotated",
                source_id=source.source_id,
                position_index=position_index,
            )
    return session


def _validation_values(
    service: V7LabelGeometryCalibrationService,
    *,
    incorrect_range: bool = False,
) -> tuple[
    tuple[dict[str, object], ...], tuple[dict[str, object], ...], tuple[dict[str, object], ...]
]:
    _manifest, _inventory, sources = service._resolve_validation_sources(
        geometry_family_id=FAMILY,
        source_game_ref="777",
        case_ids=("development", "validation"),
    )
    by_case = {item.corpus_case_id: item for item in sources}

    def source(case_id: str) -> dict[str, object]:
        item = by_case[case_id]
        return {
            "sourceId": item.source_id,
            "sourceChecksumSha256": item.source_checksum_sha256,
        }

    truths = (
        {
            "caseId": "development-1-9",
            "corpusCaseId": "development",
            "split": "development",
            "expectedRangeStart": 1,
            "expectedRangeEnd": 9,
            "evidenceSources": [source("development")],
            "acceptableRepresentativeSources": [source("development")],
            "automaticallyRecoverable": True,
            "eligibleAcceptableRepresentative": True,
        },
        {
            "caseId": "validation-10-18",
            "corpusCaseId": "validation",
            "split": "validation",
            "expectedRangeStart": 10,
            "expectedRangeEnd": 18,
            "evidenceSources": [source("validation")],
            "acceptableRepresentativeSources": [source("validation")],
            "automaticallyRecoverable": True,
            "eligibleAcceptableRepresentative": True,
        },
    )
    observations = (
        {
            **source("development"),
            "representedRangeStart": 1,
            "representedRangeEnd": 9,
            "topCropped": True,
            "bottomCropped": False,
        },
        {
            **source("validation"),
            "representedRangeStart": 10,
            "representedRangeEnd": 18,
            "topCropped": False,
            "bottomCropped": True,
        },
    )
    predictions = (
        {
            "caseId": "development-1-9",
            "predictedRangeStart": 99 if incorrect_range else 1,
            "predictedRangeEnd": 107 if incorrect_range else 9,
            "selectedSource": source("development"),
            "topWarning": True,
            "bottomWarning": False,
            "manualReview": False,
        },
        {
            "caseId": "validation-10-18",
            "predictedRangeStart": 10,
            "predictedRangeEnd": 18,
            "selectedSource": source("validation"),
            "topWarning": False,
            "bottomWarning": True,
            "manualReview": False,
        },
    )
    return truths, observations, predictions


def _persist_server_owned_passed_report(
    service: V7LabelGeometryCalibrationService,
    *,
    profile_fingerprint: str,
) -> V7ValidationReport:
    """Create a registry fixture that models a future server-owned observer.

    The public endpoint cannot create this report: its raw client snapshot is
    intentionally stamped quality=unknown and therefore fails the T05 gate.
    """

    profile = service.get_profile(profile_fingerprint).profile
    manifest, corpus_snapshot_fingerprint, _sources = service._resolve_validation_sources(
        geometry_family_id=profile.calibration.geometry_family_id,
        source_game_ref="777",
        case_ids=("development", "validation"),
    )
    acceptance = V7AcceptanceEvaluation(
        input_fingerprint="a" * 64,
        range_recovery=V7AcceptanceMetric(numerator=1, denominator=1, minimum_percent=95),
        representative_selection=V7AcceptanceMetric(numerator=1, denominator=1, minimum_percent=95),
        top_crop_recall=V7AcceptanceMetric(numerator=1, denominator=1, minimum_percent=100),
        bottom_crop_recall=V7AcceptanceMetric(numerator=1, denominator=1, minimum_percent=100),
        incorrect_automatic_range_count=0,
        top_crop_false_positive_count=0,
        bottom_crop_false_positive_count=0,
        manual_review_count=0,
        total_case_count=1,
    )
    report = V7ValidationReport.create(
        profile_fingerprint=profile.profile_fingerprint,
        observer_fingerprint=v7_profile_bound_localizer_fingerprint(profile),
        geometry_family_id=profile.calibration.geometry_family_id,
        source_game_ref="777",
        corpus_manifest_fingerprint=manifest.fingerprint(),
        corpus_inventory_fingerprint=corpus_snapshot_fingerprint,
        acceptance=acceptance,
        truth=(),
        source_observations=(),
        prediction_snapshots=(),
    )
    service._validation.persist_report(
        operation_id=str(uuid4()),
        operation_fingerprint="b" * 64,
        report=report,
    )
    return report


def _adoption_for_report(report: V7ValidationReport) -> V7GeometryAdoption:
    key = label_geometry_validation._fingerprint(
        {
            "geometryFamilyId": report.geometry_family_id,
            "profileFingerprint": report.profile_fingerprint,
            "sourceGameRef": report.source_game_ref,
        }
    )
    return V7GeometryAdoption(
        adoption_key=key,
        source_game_ref=report.source_game_ref,
        geometry_family_id=report.geometry_family_id,
        profile_fingerprint=report.profile_fingerprint,
        validation_report_fingerprint=report.validation_report_fingerprint,
    )


def test_service_uses_only_calibration_cases_and_returns_exif_canonical_asset(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))

    assert len(session.sources) == 5
    assert len(session.slots) == 45
    asset = service.canonical_asset(
        session.session_id,
        session.sources[0].source_id,
        expected_source_checksum_sha256=session.sources[0].source_checksum_sha256,
    )
    assert (asset.width, asset.height) == (20, 40)
    assert asset.content.startswith(b"\x89PNG")

    with pytest.raises(V7LabelGeometryCalibrationApiError) as holdout:
        service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("reels_test",))
    assert holdout.value.code == "V7_CALIBRATION_HOLDOUT_FORBIDDEN"

    with pytest.raises(V7LabelGeometryCalibrationApiError) as development:
        service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("development",))
    assert development.value.code == "V7_CALIBRATION_CASE_SPLIT_FORBIDDEN"


def test_source_drift_blocks_session_and_receipt_replay_still_returns_original_answer(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    original_source = (tmp_path / "corpus" / "777" / "cal-0.jpg").read_bytes()
    operation = service.operation_from_values(
        operation_id=str(uuid4()),
        expected_revision=0,
        kind="set_capture_group",
        source_id=session.sources[0].source_id,
        position_index=None,
        center_x=None,
        center_y=None,
        crop_assessment=None,
        capture_group_id="capture-a",
    )
    updated, receipt = service.mutate_session(session.session_id, operation)
    source_path = tmp_path / "corpus" / "777" / "cal-0.jpg"
    _write_jpeg(source_path, color=(250, 1, 1))

    replayed, replay_receipt = service.mutate_session(session.session_id, operation)
    assert replay_receipt == receipt
    assert replayed.revision == updated.revision

    with pytest.raises(V7LabelGeometryCalibrationApiError) as drift:
        service.get_session(session.session_id)
    assert drift.value.code == "V7_CALIBRATION_SESSION_SOURCE_DRIFT"
    assert (
        service._sessions.read(session.session_id).status
        is V7CalibrationSessionStatus.BLOCKED_SOURCE_DRIFT
    )
    source_path.write_bytes(original_source)
    with pytest.raises(V7LabelGeometryCalibrationApiError) as blocked_asset:
        service.canonical_asset(
            session.session_id,
            session.sources[0].source_id,
            expected_source_checksum_sha256=session.sources[0].source_checksum_sha256,
        )
    assert blocked_asset.value.code == "V7_CALIBRATION_SESSION_BLOCKED"


def test_session_rejects_duplicate_source_checksum_across_declared_files(tmp_path: Path) -> None:
    service = _service(tmp_path)
    duplicate = tmp_path / "corpus" / "777" / "cal-5.jpg"
    duplicate.write_bytes((tmp_path / "corpus" / "777" / "cal-0.jpg").read_bytes())

    with pytest.raises(V7LabelGeometryCalibrationApiError) as duplicate_error:
        service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    assert duplicate_error.value.code == "V7_CALIBRATION_SOURCE_DUPLICATE"


def test_complete_session_creates_content_addressed_profile_and_rejects_incomplete_one(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)

    assert profile.profile.calibration.status.value == "passed"
    assert service.get_profile(profile.profile.profile_fingerprint) == profile
    assert service.list_profiles() == (profile,)

    incomplete = _service(tmp_path / "incomplete")
    incomplete_session = incomplete.create_session(
        geometry_family_id=FAMILY,
        corpus_case_ids=("game777",),
    )
    with pytest.raises(V7LabelGeometryCalibrationApiError) as rejected:
        incomplete.create_profile(
            incomplete_session.session_id,
            expected_revision=incomplete_session.revision,
        )
    assert rejected.value.code == "V7_CALIBRATION_PROFILE_REJECTED"
    assert incomplete.list_profiles() == ()


def test_profile_uses_only_contained_annotations_and_keeps_crop_diagnostics(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path, calibration_count=6)
    session = _complete_calibration_session(service)
    diagnostic_source = session.sources[-1]
    session, _receipt = _operation(
        service,
        session,
        kind="annotated",
        source_id=diagnostic_source.source_id,
        position_index=0,
        crop_assessment="clipped",
    )

    profile = service.create_profile(session.session_id, expected_revision=session.revision)

    assert profile.profile.calibration.status.value == "passed"
    assert profile.profile.calibration.source_count_by_position[0] == 5


def test_profile_ignores_contained_points_without_a_capture_group(tmp_path: Path) -> None:
    service = _service(tmp_path, calibration_count=6)
    session = service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    for source_index, source in enumerate(session.sources[:-1]):
        session, _receipt = _operation(
            service,
            session,
            kind="set_capture_group",
            source_id=source.source_id,
            capture_group_id="capture-a" if source_index < 3 else "capture-b",
        )
    for position_index in range(9):
        for source in session.sources:
            session, _receipt = _operation(
                service,
                session,
                kind="annotated",
                source_id=source.source_id,
                position_index=position_index,
            )

    profile = service.create_profile(session.session_id, expected_revision=session.revision)

    assert profile.profile.calibration.status.value == "passed"
    assert profile.profile.calibration.source_count_by_position == (5,) * 9


def test_profile_read_rejects_tampering_and_a_swapped_content_addressed_path(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    path = service._profiles_root / f"{profile.profile.profile_fingerprint}.json"
    original = path.read_bytes()

    changed_center = json.loads(original)
    changed_center["profile"]["calibration"]["locatorConfig"]["centers"][0][0] = 0.99
    path.write_text(json.dumps(changed_center), encoding="utf-8")
    with pytest.raises(V7LabelGeometryCalibrationApiError) as changed_center_error:
        service.get_profile(profile.profile.profile_fingerprint)
    assert changed_center_error.value.code == "V7_CALIBRATION_PROFILE_CORRUPT"

    path.write_bytes(original)
    changed_export = json.loads(original)
    changed_export["sessionExportChecksumSha256"] = "f" * 64
    path.write_text(json.dumps(changed_export), encoding="utf-8")
    with pytest.raises(V7LabelGeometryCalibrationApiError) as changed_export_error:
        service.get_profile(profile.profile.profile_fingerprint)
    assert changed_export_error.value.code == "V7_CALIBRATION_PROFILE_CORRUPT"

    path.write_bytes(original)
    swapped_fingerprint = "0" * 64
    swapped_path = service._profiles_root / f"{swapped_fingerprint}.json"
    shutil.copyfile(path, swapped_path)
    with pytest.raises(V7LabelGeometryCalibrationApiError) as swapped_error:
        service.get_profile(swapped_fingerprint)
    assert swapped_error.value.code == "V7_CALIBRATION_PROFILE_CORRUPT"


def test_profile_uses_the_exact_export_snapshot_when_a_mutation_interleaves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    original_export = service._sessions.export
    changed = False

    def export_after_interleaved_mutation(*args: object, **kwargs: object) -> object:
        nonlocal changed
        if not changed:
            changed = True
            updated, _receipt = _operation(
                service,
                session,
                kind="set_capture_group",
                source_id=session.sources[0].source_id,
                capture_group_id="capture-a",
            )
            assert updated.revision == session.revision + 1
        return original_export(*args, **kwargs)

    monkeypatch.setattr(service._sessions, "export", export_after_interleaved_mutation)
    profile = service.create_profile(session.session_id, expected_revision=session.revision + 1)

    assert changed
    assert profile.profile.revision == session.revision + 1


def test_corpus_root_change_blocks_existing_session_even_with_identical_files(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    replacement_root = tmp_path / "replacement-corpus"
    shutil.copytree(tmp_path / "corpus", replacement_root)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corpusRoot"] = str(replacement_root)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(V7LabelGeometryCalibrationApiError) as drift:
        service.get_session(session.session_id)
    assert drift.value.code == "V7_CALIBRATION_SESSION_SOURCE_DRIFT"
    assert (
        service._sessions.read(session.session_id).status
        is V7CalibrationSessionStatus.BLOCKED_SOURCE_DRIFT
    )


def test_manifest_parent_junction_is_rejected_before_loading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    manifest_parent = (tmp_path / "manifest.json").absolute().parent
    original_check = label_geometry_application._is_link_or_reparse

    monkeypatch.setattr(
        label_geometry_application,
        "_is_link_or_reparse",
        lambda path: path == manifest_parent or original_check(path),
    )
    with pytest.raises(V7LabelGeometryCalibrationApiError) as unsafe:
        service.create_session(geometry_family_id=FAMILY, corpus_case_ids=("game777",))
    assert unsafe.value.code == "V7_CALIBRATION_CORPUS_UNAVAILABLE"


def test_router_exposes_only_safe_session_contract_and_no_adoptions(tmp_path: Path) -> None:
    service = _service(tmp_path)
    app = FastAPI()
    app.include_router(
        create_v7_label_geometry_calibration_router(lambda: service), prefix="/api/v1"
    )
    client = TestClient(app)

    created = client.post(
        "/api/v1/admin/v7-label-geometry/sessions",
        json={"geometryFamilyId": FAMILY, "corpusCaseIds": ["game777"]},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert "path" not in json.dumps(body).casefold()
    assert body["sources"][0]["split"] == "calibration"
    asset = client.get(
        "/api/v1/admin/v7-label-geometry/sessions/"
        f"{body['sessionId']}/sources/{body['sources'][0]['sourceId']}/asset",
        params={"expectedSourceChecksumSha256": body["sources"][0]["sourceChecksumSha256"]},
    )
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("image/png")
    assert client.get("/api/v1/admin/v7-label-geometry/adoptions").json() == {"items": []}


def test_application_openapi_registers_calibration_with_local_admin_security(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    settings = ApiSettings(
        host="127.0.0.1",
        port=8000,
        admin_origin="http://127.0.0.1:3000",
        artifact_root=tmp_path / "artifacts",
        import_root=tmp_path / "imports",
        v7_label_geometry_runtime_root=tmp_path / "runtime",
        v7_label_geometry_corpus_manifest=tmp_path / "manifest.json",
    )
    app = create_app(settings, v7_label_geometry_calibration_service_dependency=lambda: service)
    schema = app.openapi()

    assert "/api/v1/admin/v7-label-geometry/sessions" in schema["paths"]
    assert (
        schema["paths"]["/api/v1/admin/v7-label-geometry/sessions"]["post"]["operationId"]
        == "createV7LabelGeometryCalibrationSession"
    )
    assert schema["paths"]["/api/v1/admin/v7-label-geometry/sessions"]["post"]["security"]


def test_validation_report_replays_before_corpus_drift_and_rejects_unverified_quality(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    truths, observations, predictions = _validation_values(service)
    operation_id = str(uuid4())

    report, created = service.create_validation_report(
        operation_id=operation_id,
        profile_fingerprint=profile.profile.profile_fingerprint,
        source_game_ref="777",
        truth_values=truths,
        source_observation_values=observations,
        prediction_snapshot_values=predictions,
    )
    replayed, replayed_created = service.create_validation_report(
        operation_id=operation_id,
        profile_fingerprint=profile.profile.profile_fingerprint,
        source_game_ref="777",
        truth_values=truths,
        source_observation_values=observations,
        prediction_snapshot_values=predictions,
    )

    assert created is True
    assert replayed_created is False
    assert replayed == report
    assert report.acceptance.status.value == "failed"
    restarted = V7LabelGeometryCalibrationService(
        runtime_root=tmp_path / "runtime",
        corpus_manifest_path=tmp_path / "manifest.json",
    )
    with pytest.raises(V7LabelGeometryCalibrationApiError) as adoption_rejected:
        restarted.create_adoption(
            operation_id=str(uuid4()),
            profile_fingerprint=profile.profile.profile_fingerprint,
            source_game_ref="777",
            validation_report_fingerprint=report.validation_report_fingerprint,
        )
    assert adoption_rejected.value.code == "V7_VALIDATION_ADOPTION_REPORT_REJECTED"

    changed_predictions = list(predictions)
    changed_predictions[0] = {
        **changed_predictions[0],
        "predictedRangeStart": 99,
        "predictedRangeEnd": 107,
    }
    with pytest.raises(V7LabelGeometryCalibrationApiError) as report_operation_conflict:
        restarted.create_validation_report(
            operation_id=operation_id,
            profile_fingerprint=profile.profile.profile_fingerprint,
            source_game_ref="777",
            truth_values=truths,
            source_observation_values=observations,
            prediction_snapshot_values=tuple(changed_predictions),
        )
    assert report_operation_conflict.value.code == "V7_VALIDATION_OPERATION_ID_CONFLICT"

    _write_jpeg(tmp_path / "corpus" / "validation" / "validation.jpg", color=(99, 88, 77))
    replayed_report, replayed_report_created = restarted.create_validation_report(
        operation_id=operation_id,
        profile_fingerprint=profile.profile.profile_fingerprint,
        source_game_ref="777",
        truth_values=truths,
        source_observation_values=observations,
        prediction_snapshot_values=predictions,
    )
    assert replayed_report == report
    assert replayed_report_created is False


def test_validation_rejects_failed_reports_and_holdout(tmp_path: Path) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    truths, observations, predictions = _validation_values(service, incorrect_range=True)
    failed, _created = service.create_validation_report(
        operation_id=str(uuid4()),
        profile_fingerprint=profile.profile.profile_fingerprint,
        source_game_ref="777",
        truth_values=truths,
        source_observation_values=observations,
        prediction_snapshot_values=predictions,
    )
    assert failed.acceptance.status.value == "failed"
    with pytest.raises(V7LabelGeometryCalibrationApiError) as failed_adoption:
        service.create_adoption(
            operation_id=str(uuid4()),
            profile_fingerprint=profile.profile.profile_fingerprint,
            source_game_ref="777",
            validation_report_fingerprint=failed.validation_report_fingerprint,
        )
    assert failed_adoption.value.code == "V7_VALIDATION_ADOPTION_REPORT_REJECTED"

    truths, observations, predictions = _validation_values(service)
    unverified_quality, _created = service.create_validation_report(
        operation_id=str(uuid4()),
        profile_fingerprint=profile.profile.profile_fingerprint,
        source_game_ref="777",
        truth_values=truths,
        source_observation_values=observations,
        prediction_snapshot_values=predictions,
    )
    assert unverified_quality.acceptance.status.value == "failed"
    with pytest.raises(V7LabelGeometryCalibrationApiError) as unverified_quality_adoption:
        service.create_adoption(
            operation_id=str(uuid4()),
            profile_fingerprint=profile.profile.profile_fingerprint,
            source_game_ref="777",
            validation_report_fingerprint=unverified_quality.validation_report_fingerprint,
        )
    assert unverified_quality_adoption.value.code == "V7_VALIDATION_ADOPTION_REPORT_REJECTED"

    with pytest.raises(V7LabelGeometryCalibrationApiError) as holdout:
        service._resolve_validation_sources(
            geometry_family_id=FAMILY,
            source_game_ref="777",
            case_ids=("reels_test",),
        )
    assert holdout.value.code == "V7_VALIDATION_SPLIT_FORBIDDEN"


def test_validation_router_derives_metrics_and_keeps_adoption_contract_path_safe(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    truths, observations, predictions = _validation_values(service)
    app = create_app(
        ApiSettings(
            host="127.0.0.1",
            port=8000,
            admin_origin="http://127.0.0.1:3000",
            artifact_root=tmp_path / "artifacts",
            import_root=tmp_path / "imports",
            v7_label_geometry_runtime_root=tmp_path / "runtime",
            v7_label_geometry_corpus_manifest=tmp_path / "manifest.json",
        ),
        v7_label_geometry_calibration_service_dependency=lambda: service,
    )
    client = TestClient(app)
    payload = {
        "operationId": str(uuid4()),
        "profileFingerprint": profile.profile.profile_fingerprint,
        "sourceGameRef": "777",
        "truth": list(truths),
        "sourceObservations": list(observations),
        "predictionSnapshots": list(predictions),
    }

    untrusted_outcome = json.loads(json.dumps(payload))
    untrusted_outcome["predictionSnapshots"][0]["rangeOutcome"] = "correct"
    assert (
        client.post(
            "/api/v1/admin/v7-label-geometry/validation-reports",
            json=untrusted_outcome,
        ).status_code
        == 422
    )
    untrusted_quality = json.loads(json.dumps(payload))
    untrusted_quality["predictionSnapshots"][0]["qualityStatus"] = "acceptable"
    assert (
        client.post(
            "/api/v1/admin/v7-label-geometry/validation-reports",
            json=untrusted_quality,
        ).status_code
        == 422
    )
    half_range = json.loads(json.dumps(payload))
    half_range["predictionSnapshots"][0]["predictedRangeEnd"] = None
    assert (
        client.post(
            "/api/v1/admin/v7-label-geometry/validation-reports",
            json=half_range,
        ).status_code
        == 422
    )

    report = client.post("/api/v1/admin/v7-label-geometry/validation-reports", json=payload)
    assert report.status_code == 200, report.text
    report_body = report.json()
    assert report_body["acceptance"]["status"] == "failed"
    assert "path" not in json.dumps(report_body).casefold()
    adoption = client.post(
        "/api/v1/admin/v7-label-geometry/adoptions",
        json={
            "operationId": str(uuid4()),
            "profileFingerprint": profile.profile.profile_fingerprint,
            "sourceGameRef": "777",
            "validationReportFingerprint": report_body["validationReportFingerprint"],
        },
    )
    assert adoption.status_code == 422, adoption.text
    assert adoption.json()["code"] == "V7_VALIDATION_ADOPTION_REPORT_REJECTED"
    assert client.get("/api/v1/admin/v7-label-geometry/adoptions").json() == {"items": []}


def test_validation_adoption_rejects_identical_inventory_at_a_different_corpus_root(
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    report = _persist_server_owned_passed_report(
        service,
        profile_fingerprint=profile.profile.profile_fingerprint,
    )
    replacement_root = tmp_path / "replacement-corpus"
    shutil.copytree(tmp_path / "corpus", replacement_root)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["corpusRoot"] = str(replacement_root)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(V7LabelGeometryCalibrationApiError) as drift:
        service.create_adoption(
            operation_id=str(uuid4()),
            profile_fingerprint=profile.profile.profile_fingerprint,
            source_game_ref="777",
            validation_report_fingerprint=report.validation_report_fingerprint,
        )
    assert drift.value.code == "V7_VALIDATION_ADOPTION_CORPUS_DRIFT"


def test_validation_registry_hides_unreceipted_records_and_serializes_conflicting_adoption(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _service(tmp_path)
    session = _complete_calibration_session(service)
    profile = service.create_profile(session.session_id, expected_revision=session.revision)
    report = _persist_server_owned_passed_report(
        service,
        profile_fingerprint=profile.profile.profile_fingerprint,
    )
    registry = service._validation
    adoption = _adoption_for_report(report)

    # The same visibility rule applies to reports. A durable object without a
    # receipt may be recovered only by replaying its exact operation.
    unreceipted_report = V7ValidationReport.create(
        profile_fingerprint=report.profile_fingerprint,
        observer_fingerprint=report.observer_fingerprint,
        geometry_family_id=report.geometry_family_id,
        source_game_ref="unreceipted-game",
        corpus_manifest_fingerprint=report.corpus_manifest_fingerprint,
        corpus_inventory_fingerprint=report.corpus_inventory_fingerprint,
        acceptance=report.acceptance,
        truth=(),
        source_observations=(),
        prediction_snapshots=(),
    )
    original_write = label_geometry_validation._write_immutable
    interrupted_report = False

    def crash_after_report_record(
        path: Path, content: bytes, *, conflict_code: str, conflict_message: str
    ) -> bool:
        nonlocal interrupted_report
        created = original_write(
            path,
            content,
            conflict_code=conflict_code,
            conflict_message=conflict_message,
        )
        if path.parent.name == "reports" and not interrupted_report:
            interrupted_report = True
            raise RuntimeError("simulated report crash")
        return created

    monkeypatch.setattr(label_geometry_validation, "_write_immutable", crash_after_report_record)
    report_operation_id = str(uuid4())
    with pytest.raises(RuntimeError, match="simulated report crash"):
        registry.persist_report(
            operation_id=report_operation_id,
            operation_fingerprint="c" * 64,
            report=unreceipted_report,
        )
    restarted = type(registry)(tmp_path / "runtime")
    with pytest.raises(label_geometry_validation.V7ValidationRegistryError) as report_orphan:
        restarted.get_report(unreceipted_report.validation_report_fingerprint)
    assert report_orphan.value.code == "V7_VALIDATION_REPORT_NOT_FOUND"
    monkeypatch.setattr(label_geometry_validation, "_write_immutable", original_write)
    recovered_report, recovered_report_created = restarted.persist_report(
        operation_id=report_operation_id,
        operation_fingerprint="c" * 64,
        report=unreceipted_report,
    )
    assert recovered_report == unreceipted_report
    assert recovered_report_created is False

    # A process crash after the immutable record and before its receipt leaves
    # no observable adoption. Retrying the same command makes it visible.
    interrupted = False

    def crash_after_adoption_record(
        path: Path, content: bytes, *, conflict_code: str, conflict_message: str
    ) -> bool:
        nonlocal interrupted
        created = original_write(
            path,
            content,
            conflict_code=conflict_code,
            conflict_message=conflict_message,
        )
        if path.parent.name == "adoptions" and not interrupted:
            interrupted = True
            raise RuntimeError("simulated process crash")
        return created

    monkeypatch.setattr(label_geometry_validation, "_write_immutable", crash_after_adoption_record)
    operation_id = str(uuid4())
    with pytest.raises(RuntimeError, match="simulated process crash"):
        registry.persist_adoption(
            operation_id=operation_id,
            operation_fingerprint="c" * 64,
            adoption=adoption,
        )
    restarted = type(registry)(tmp_path / "runtime")
    assert restarted.list_adoptions() == ()
    with pytest.raises(label_geometry_validation.V7ValidationRegistryError) as orphan:
        restarted.get_adoption(adoption.adoption_key)
    assert orphan.value.code == "V7_VALIDATION_ADOPTION_NOT_FOUND"

    monkeypatch.setattr(label_geometry_validation, "_write_immutable", original_write)
    recovered, recovered_created = restarted.persist_adoption(
        operation_id=operation_id,
        operation_fingerprint="c" * 64,
        adoption=adoption,
    )
    assert recovered == adoption
    assert recovered_created is False
    assert restarted.list_adoptions() == (adoption,)

    adoption_path = restarted._adoption_path(adoption.adoption_key)
    original_adoption_content = adoption_path.read_bytes()
    tampered_adoption = json.loads(original_adoption_content)
    tampered_adoption["adoption"]["adoptionKey"] = "f" * 64
    adoption_path.write_bytes(label_geometry_validation._canonical_json(tampered_adoption))
    with pytest.raises(label_geometry_validation.V7ValidationRegistryError) as invalid_key:
        restarted.get_adoption(adoption.adoption_key)
    assert invalid_key.value.code == "V7_VALIDATION_ADOPTION_STORE_INVALID"
    adoption_path.write_bytes(original_adoption_content)
    tampered_report_link = json.loads(original_adoption_content)
    tampered_report_link["adoption"]["validationReportFingerprint"] = "e" * 64
    adoption_path.write_bytes(label_geometry_validation._canonical_json(tampered_report_link))
    with pytest.raises(label_geometry_validation.V7ValidationRegistryError) as invalid_report_link:
        restarted.get_adoption(adoption.adoption_key)
    assert invalid_report_link.value.code == "V7_VALIDATION_ADOPTION_STORE_INVALID"
    adoption_path.write_bytes(original_adoption_content)

    entered_write = threading.Event()
    release_write = threading.Event()

    def block_first_adoption_record(
        path: Path, content: bytes, *, conflict_code: str, conflict_message: str
    ) -> bool:
        created = original_write(
            path,
            content,
            conflict_code=conflict_code,
            conflict_message=conflict_message,
        )
        if path.parent.name == "adoptions" and created:
            entered_write.set()
            assert release_write.wait(timeout=2)
        return created

    monkeypatch.setattr(label_geometry_validation, "_write_immutable", block_first_adoption_record)
    other_report = V7ValidationReport.create(
        profile_fingerprint=report.profile_fingerprint,
        observer_fingerprint=report.observer_fingerprint,
        geometry_family_id=report.geometry_family_id,
        source_game_ref="other-game",
        corpus_manifest_fingerprint=report.corpus_manifest_fingerprint,
        corpus_inventory_fingerprint=report.corpus_inventory_fingerprint,
        acceptance=report.acceptance,
        truth=(),
        source_observations=(),
        prediction_snapshots=(),
    )
    restarted.persist_report(
        operation_id=str(uuid4()),
        operation_fingerprint="e" * 64,
        report=other_report,
    )
    concurrent_adoption = _adoption_for_report(other_report)
    concurrent_operation_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(
            restarted.persist_adoption,
            operation_id=concurrent_operation_id,
            operation_fingerprint="d" * 64,
            adoption=concurrent_adoption,
        )
        assert entered_write.wait(timeout=2)
        second = executor.submit(
            restarted.persist_adoption,
            operation_id=concurrent_operation_id,
            operation_fingerprint="e" * 64,
            adoption=adoption,
        )
        release_write.set()
        assert first.result(timeout=2)[0] == concurrent_adoption
        with pytest.raises(label_geometry_validation.V7ValidationRegistryError) as conflict:
            second.result(timeout=2)
    assert conflict.value.code == "V7_VALIDATION_ADOPTION_OPERATION_ID_CONFLICT"
    assert set(restarted.list_adoptions()) == {adoption, concurrent_adoption}
