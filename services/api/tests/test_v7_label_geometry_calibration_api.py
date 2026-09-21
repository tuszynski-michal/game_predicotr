from __future__ import annotations

import json
import shutil
from pathlib import Path
from uuid import uuid4

import game_predictor_api.application.v7_label_geometry_calibration as label_geometry_application
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
from game_predictor_api.config import ApiSettings
from game_predictor_api.main import create_app
from game_predictor_worker.semi_automatic_selection.v7_calibration_sessions import (
    V7CalibrationSession,
    V7CalibrationSessionStatus,
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
            crop_assessment="contained" if kind == "annotated" else None,
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
