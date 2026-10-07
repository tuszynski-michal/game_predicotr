"""R3 canonical receipts and non-mutating pilot calibration bootstrap."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationApiError,
    V7LabelGeometryCalibrationService,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.v7_pilot_acceptance import (
    receipt_matches_gate,
    validate_pilot_acceptance,
)
from game_predictor_api.domain.v7_selection_delivery import V7PilotGate, payload_fingerprint
from game_predictor_api.storage import database_roles
from game_predictor_api.storage.models import (
    SemiAutomaticV7ActivationGateModel,
    V7PilotAcceptanceModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration_sessions import (
    V7CalibrationSessionSource,
    V7CalibrationSessionStore,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import V7CorpusSplit
from sqlalchemy.orm import Session


def acceptance(tmp_path: Path) -> tuple[dict[str, object], V7PilotGate]:
    fixture = tmp_path / ".claude" / "v7-pilot-runtime" / "fixtures"
    source = fixture / "B"
    source.mkdir(parents=True)
    bindings = [
        {
            "sourceRoot": str(source.resolve()),
            "sourceFingerprint": "a" * 64,
            "sourceGameRef": "777",
            "geometryFamilyId": "family",
        }
    ]
    payload: dict[str, object] = {
        "version": "v7-reviewed-pilot-acceptance-v1",
        "scope": "technical_fixture",
        "mode": "semi_automatic",
        "manualConfirmationRequired": True,
        "automaticAllowed": False,
        "countsTowardT12": False,
        "fixtureRoot": str(fixture.resolve()),
        "databaseName": "game_predictor_v7_pilot",
        "geometryFamilyId": "family",
        "sourceGameRef": "777",
        "profileFingerprint": "b" * 64,
        "sessionExportChecksumSha256": "c" * 64,
        "historicalManifestFingerprint": "d" * 64,
        "observerFingerprint": "e" * 64,
        "ocrModelFingerprint": "f" * 64,
        "functionalReportFingerprint": "1" * 64,
        "reviewReportFingerprint": "2" * 64,
        "sourceBindings": bindings,
        "ocrRuntimeIdentity": {"name": "paddlepaddle-cpu", "version": "3.3.1"},
        "actor": "TASK-0853 technical executor",
        "acceptedAt": datetime.now(UTC).isoformat(),
        "operatorDecisionReference": "TASK-0853 authorized exact-copy technical fixture",
        "calibrationSessionId": str(uuid4()),
    }
    gate = V7PilotGate(
        status="active",
        generation=1,
        accepted=True,
        geometry_family_id="family",
        source_game_ref="777",
        profile_fingerprint="b" * 64,
        observer_fingerprint="e" * 64,
        ocr_model_fingerprint="f" * 64,
        source_bindings=tuple(bindings),
        receipt_fingerprint=payload_fingerprint(payload),
    )
    return payload, gate


def test_valid_receipt_is_pinned_to_every_gate_field(tmp_path: Path) -> None:
    receipt, gate = acceptance(tmp_path)
    validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")
    assert receipt_matches_gate(
        receipt, payload_fingerprint(receipt), gate, "game_predictor_v7_pilot"
    )
    assert not receipt_matches_gate(receipt, "0" * 64, gate, "game_predictor_v7_pilot")
    for key, value in (
        ("source_game_ref", "other"),
        ("geometry_family_id", "other"),
        ("profile_fingerprint", "0" * 64),
        ("observer_fingerprint", "0" * 64),
        ("ocr_model_fingerprint", "0" * 64),
        ("source_bindings", ()),
    ):
        assert not receipt_matches_gate(
            receipt,
            payload_fingerprint(receipt),
            replace(gate, **{key: value}),
            "game_predictor_v7_pilot",
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("manualConfirmationRequired", 1),
        ("automaticAllowed", 0),
        ("countsTowardT12", 0),
        ("scope", "automatic"),
        ("databaseName", "game_predictor"),
        ("fixtureRoot", None),
        ("profileFingerprint", "bad"),
        ("actor", ""),
        ("acceptedAt", "2026-10-05T12:00:00"),
        ("sourceBindings", []),
        ("ocrRuntimeIdentity", {"name": "paddlepaddle-cpu"}),
    ],
)
def test_receipt_rejects_invalid_policy_or_identity(
    tmp_path: Path, key: str, value: object
) -> None:
    receipt, _ = acceptance(tmp_path)
    receipt[key] = value
    with pytest.raises(ValueError):
        validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")


def test_fixture_receipt_cannot_bind_operator_root(tmp_path: Path) -> None:
    receipt, _ = acceptance(tmp_path)
    receipt["sourceBindings"] = [
        {
            "sourceRoot": str(tmp_path.resolve()),
            "sourceFingerprint": "a" * 64,
            "sourceGameRef": "777",
            "geometryFamilyId": "family",
        }
    ]
    with pytest.raises(ValueError, match="scope"):
        validate_pilot_acceptance(receipt, "game_predictor_v7_pilot")


def test_read_only_bootstrap_and_temporary_session_never_write(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    read_only = V7LabelGeometryCalibrationService(
        runtime_root=empty,
        corpus_manifest_path=None,
        read_only=True,
    )
    assert not empty.exists()
    with pytest.raises(V7LabelGeometryCalibrationApiError, match="read-only"):
        read_only.create_session(geometry_family_id="family", corpus_case_ids=())
    assert not empty.exists()
    root = tmp_path / "runtime"
    corpus = tmp_path / "corpus"
    source_path = corpus / "calibration" / "one.jpg"
    source_path.parent.mkdir(parents=True)
    source_path.write_bytes(b"calibration fixture metadata")
    checksum = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "corpusRoot": str(corpus),
                "cases": [
                    {
                        "caseId": split,
                        "directoryName": split,
                        "split": split,
                        "borderStyle": "top_and_sides",
                        "scenarios": ["small_groups"],
                        "expectedDirection": "ascending",
                        "geometryFamilyId": "family",
                        "sourceGameRef": "777",
                    }
                    for split in ("calibration", "development", "validation", "holdout")
                ],
            }
        )
    )
    session = V7CalibrationSessionStore(root).create(
        manifest_fingerprint="a" * 64,
        geometry_family_id="family",
        sources=(
            V7CalibrationSessionSource(
                source_id=f"calibration-{checksum}",
                source_checksum_sha256=checksum,
                corpus_case_id="calibration",
                split=V7CorpusSplit.CALIBRATION,
                geometry_family_id="family",
            ),
        ),
    )
    read_only = V7LabelGeometryCalibrationService(
        runtime_root=root,
        corpus_manifest_path=manifest_path,
        read_only=True,
    )
    before = {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    assert read_only.get_session(session.session_id) == session
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "from pathlib import Path;import sys;"
            "from game_predictor_api.application.v7_label_geometry_calibration "
            "import V7LabelGeometryCalibrationService;"
            "s=V7LabelGeometryCalibrationService(runtime_root=Path(sys.argv[1]),"
            "corpus_manifest_path=Path(sys.argv[3]),read_only=True);"
            "print(s.get_session(sys.argv[2]).revision)",
            str(root),
            session.session_id,
            str(manifest_path),
        ],
        timeout=20,
        capture_output=True,
        text=True,
        check=True,
    )
    assert child.stdout.strip() == "0"
    assert before == {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    source_path.write_bytes(b"drift")
    with pytest.raises(V7LabelGeometryCalibrationApiError) as error:
        read_only.get_session(session.session_id)
    assert error.value.code == "V7_CALIBRATION_SESSION_SOURCE_DRIFT"
    assert before == {str(path): path.read_bytes() for path in root.rglob("*") if path.is_file()}
    directory = root / "v7-label-geometry" / "sessions" / session.session_id
    temporary = directory / "state.json.tmp"
    temporary.write_text(json.dumps({"invalid": True}))
    state = (directory / "state.json").read_bytes()
    with pytest.raises(V7LabelGeometryCalibrationApiError) as error:
        read_only.get_session(session.session_id)
    assert error.value.code == "V7_CALIBRATION_SESSION_RECOVERY_REQUIRED"
    assert (directory / "state.json").read_bytes() == state
    assert temporary.exists()


def test_read_only_setting_is_opt_in() -> None:
    assert ApiSettings.from_environment({}).v7_label_geometry_read_only is False
    assert (
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_V7_LABEL_GEOMETRY_READ_ONLY": "true",
            }
        ).v7_label_geometry_read_only
        is True
    )


@pytest.mark.parametrize("corruption", ["none", "missing", "generation", "body", "actor", "time"])
def test_shared_provider_requires_actual_receipt_and_matching_generation(
    tmp_path: Path, corruption: str
) -> None:
    payload, identity = acceptance(tmp_path)
    row = SemiAutomaticV7ActivationGateModel(
        singleton=True,
        pilot_status="active",
        pilot_generation=1,
        pilot_mode="semi_automatic",
        pilot_geometry_family_id=identity.geometry_family_id,
        pilot_source_game_ref="777",
        pilot_profile_fingerprint=identity.profile_fingerprint,
        pilot_observer_fingerprint=identity.observer_fingerprint,
        pilot_ocr_model_fingerprint=identity.ocr_model_fingerprint,
        pilot_source_bindings=list(identity.source_bindings),
        pilot_source_policy="exact_sources",
        pilot_acceptance_receipt_fingerprint=identity.receipt_fingerprint,
        pilot_accepted_by=payload["actor"],
        pilot_accepted_at=datetime.fromisoformat(str(payload["acceptedAt"])),
    )
    receipt = V7PilotAcceptanceModel(
        operation_id=uuid4(),
        request_fingerprint="0" * 64,
        receipt_fingerprint=identity.receipt_fingerprint,
        receipt=payload,
        expected_generation=0,
        resulting_generation=1,
    )
    if corruption == "generation":
        row.pilot_generation = 2
    elif corruption == "body":
        payload["countsTowardT12"] = True
    elif corruption == "actor":
        row.pilot_accepted_by = "unrelated actor"
    elif corruption == "time":
        row.pilot_accepted_at = datetime(2020, 1, 1, tzinfo=UTC)
    values = iter([row, None if corruption == "missing" else receipt, "game_predictor_v7_pilot"])

    class ReadSession:
        def scalar(self, statement: object) -> object:
            return next(values)

    gate = SqlAlchemySemiAutomaticSelectionRepository(
        cast(Session, ReadSession())
    ).get_v7_pilot_gate()
    assert gate.enabled is (corruption == "none")


@pytest.mark.parametrize("migrated", [False, True])
def test_role_protection_is_conditional_and_covers_gate_and_registry(
    monkeypatch: pytest.MonkeyPatch, migrated: bool
) -> None:
    monkeypatch.setattr(database_roles, "_relation_exists", lambda connection, table: migrated)
    protected = database_roles._read_only_tables(cast("object", None))
    assert "public.alembic_version" in protected
    assert ("public.semi_automatic_selection_v7_pilot_acceptances" in protected) is migrated
    assert ("public.semi_automatic_selection_v7_activation_gate" in protected) is migrated
