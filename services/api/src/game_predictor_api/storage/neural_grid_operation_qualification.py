"""Read existing evaluator evidence; no independent qualification store."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.application.grid_model_registry import GridModelRegistryService
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.neural_grid_operation_pin import (
    CALIBRATED_PIN_VERSION,
    CALIBRATION_REQUIRED,
    GAME_EVALUATION_REQUIRED,
    NeuralOperationPinError,
    make_operation_pin,
    require_operation_pin,
    snapshot_descriptor,
)
from game_predictor_api.domain.neural_grid_proposal import NeuralGridSnapshot
from game_predictor_api.storage.grid_model_registry import SqlAlchemyGridModelRegistryRepository
from game_predictor_api.storage.models import RulesVersionModel

# These are normal lack/loss of evidence, not registry corruption or infrastructure errors.
_UNQUALIFIED = {
    "GRID_MODEL_NOT_PUBLISHED",
    "GRID_MODEL_EVALUATION_REQUIRED",
    "GRID_MODEL_EVALUATION_STALE",
    "GRID_MODEL_PUBLICATION_STALE",
    "GRID_MODEL_EVALUATION_SCOPE_STALE",
}


class _PinnedInspector:
    """The snapshot loader already verified bytes; this reader checks evidence only."""

    def inspect(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return True, "PINNED_MODEL"

    def historical_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise GridModelRegistryError(
            "GRID_MODEL_EVALUATION_REQUIRED", "Historical admission is not a game evaluation."
        )


def _evidence(session: Session, snapshot: NeuralGridSnapshot, game_id: UUID) -> dict[str, Any]:
    descriptor = snapshot_descriptor(snapshot)
    repository = SqlAlchemyGridModelRegistryRepository(session)
    service = GridModelRegistryService(repository, _PinnedInspector())
    # Deliberately skip mutable assignment/default. The exact frozen descriptor is authority.
    _, evidence = service.control._eligible_inspected(
        {
            "manifest": descriptor,
            "manifestSha256": descriptor_sha256(descriptor),
            "available": True,
        },
        game_id=game_id,
    )
    return evidence


def prepare_operation_pin(
    session: Session,
    *,
    snapshot: NeuralGridSnapshot,
    game_id: UUID,
    rules_version_id: UUID,
    rows: int,
    columns: int,
    artifact_root: Path | None = None,
) -> dict[str, object]:
    qualification: dict[str, object] = {
        "state": "unqualified",
        "reasonCodes": [GAME_EVALUATION_REQUIRED],
    }
    try:
        evidence = _evidence(session, snapshot, game_id)
    except GridModelRegistryError as error:
        if error.code not in _UNQUALIFIED:
            raise
    else:
        qualification = {
            "state": "qualified",
            "reasonCodes": [],
            "evaluationId": evidence["evaluationId"],
            "evaluationSha256": evidence["evaluationSha256"],
            "publicationEvidenceSha256": descriptor_sha256(evidence),
        }
    rescue = None
    automatic: dict[str, Any] = {"state": "unqualified", "reasonCodes": [CALIBRATION_REQUIRED]}
    if qualification["state"] == "qualified" and artifact_root is not None:
        from .grid_model_registry import GridModelArtifactInspector

        rescue, _ = GridModelArtifactInspector(artifact_root).inspect_rescue(
            snapshot_descriptor(snapshot), game_id=str(game_id), publication_evidence=evidence
        )
        automatic = _automatic_evidence(session, evidence, snapshot, game_id, artifact_root)
    return make_operation_pin(
        snapshot=snapshot,
        game_id=str(game_id),
        rules_version_id=str(rules_version_id),
        rows=rows,
        columns=columns,
        qualification=qualification,
        rescue=rescue,
        automatic_qualification=automatic,
    )


def recheck_operation_pin(
    session: Session,
    *,
    pin: object,
    model_snapshot: object,
    game_id: UUID,
) -> tuple[str, ...]:
    snapshot = NeuralGridSnapshot.from_payload(model_snapshot)
    try:
        checked = require_operation_pin(pin, snapshot=snapshot, game_id=str(game_id))
    except NeuralOperationPinError:
        return (NeuralOperationPinError.code,)
    rules = session.get(RulesVersionModel, UUID(checked["topologyRulesVersionId"]))
    if rules is None or rules.game_id != game_id or (rules.rows, rules.columns) != (3, 5):
        return ("NEURAL_GRID_TOPOLOGY_UNSUPPORTED",)
    qualification = checked["qualification"]
    if qualification["state"] == "unqualified":
        return (GAME_EVALUATION_REQUIRED,)
    # Check the exact report and evidence selected at prepare, never replace it.
    try:
        evidence = _evidence(session, snapshot, game_id)
    except GridModelRegistryError as error:
        if error.code not in _UNQUALIFIED:
            raise
        return ("NEURAL_GRID_GAME_EVALUATION_STALE",)
    if (
        evidence.get("evaluationId") != qualification["evaluationId"]
        or evidence.get("evaluationSha256") != qualification["evaluationSha256"]
        or descriptor_sha256(evidence) != qualification["publicationEvidenceSha256"]
    ):
        return ("NEURAL_GRID_GAME_EVALUATION_STALE",)
    if checked["contractVersion"] == CALIBRATED_PIN_VERSION:
        automatic = checked["automaticQualification"]
        if automatic["state"] != "qualified":
            return (CALIBRATION_REQUIRED,)
        # The exact trusted report is already revalidated above. Its profile is immutable.
        report, invalidated = SqlAlchemyGridModelRegistryRepository(session).evaluation(
            UUID(automatic["reportId"])
        )
        if report is None or invalidated or report.report_sha256 != automatic["reportSha256"]:
            return ("NEURAL_GRID_CALIBRATION_STALE",)
        document = json.loads(report.report_json)
        found = [
            item
            for item in document.get("automaticCalibration", [])
            if item.get("gameId") == str(game_id)
        ]
        if (
            len(found) != 1
            or found[0].get("state") != "qualified"
            or found[0].get("profile") != automatic["profile"]
        ):
            return ("NEURAL_GRID_CALIBRATION_STALE",)
    return ()


def _automatic_evidence(
    session: Session, evidence: dict[str, Any], snapshot: NeuralGridSnapshot, game: UUID, root: Path
) -> dict[str, Any]:
    unqualified = {"state": "unqualified", "reasonCodes": [CALIBRATION_REQUIRED]}
    identifier = evidence.get("evaluationId")
    if identifier is None:
        return unqualified
    report, invalidated = SqlAlchemyGridModelRegistryRepository(session).evaluation(
        UUID(identifier)
    )
    if report is None or invalidated or report.report_sha256 != evidence["evaluationSha256"]:
        return unqualified
    document = json.loads(report.report_json)
    if document.get("schemaVersion") != "grid-model-evaluation-read-v5":
        return unqualified
    matches = [item for item in document["automaticCalibration"] if item["gameId"] == str(game)]
    if len(matches) != 1 or matches[0]["state"] != "qualified":
        return unqualified
    from .full_board_calibration_evidence import (
        load_frozen_assessment,
        require_calibration_evidence,
    )

    try:
        require_calibration_evidence(
            root,
            matches[0],
            frozen=load_frozen_assessment(session, root, document, game),
            candidate_sha=descriptor_sha256(snapshot_descriptor(snapshot)),
            baseline_sha=document["baseManifestSha256"],
        )
    except (OSError, ValueError, KeyError, TypeError):
        return unqualified
    if matches[0]["profile"]["candidateManifestSha256"] != descriptor_sha256(
        snapshot_descriptor(snapshot)
    ):
        return unqualified
    return {
        "state": "qualified",
        "reasonCodes": [],
        "reportId": str(report.id),
        "reportSha256": report.report_sha256,
        "profile": matches[0]["profile"],
    }
