"""Verify managed lab bytes and their persisted game/origin/runtime bindings."""

from pathlib import Path
from typing import cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.lab_symbol_candidate import (
    LabSymbolCandidate,
    load_lab_symbol_candidate,
)
from game_predictor_api.storage.models import SymbolModel, SymbolModelIterationModel


def require_candidate(root: Path, fingerprint: str, game_id: UUID) -> LabSymbolCandidate:
    try:
        candidate = load_lab_symbol_candidate(root, fingerprint)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise JobConflictError(
            "LAB_CANDIDATE_INVALID", "Managed candidate bytes or identity changed."
        ) from error
    if candidate.game_id != game_id:
        raise JobConflictError("LAB_CANDIDATE_GAME_MISMATCH", "Candidate belongs to another game.")
    return candidate


def require_catalog(session: Session, candidate: LabSymbolCandidate) -> None:
    codes = tuple(
        session.scalars(
            select(SymbolModel.code)
            .where(
                SymbolModel.game_id == candidate.game_id, SymbolModel.status == SymbolStatus.ACTIVE
            )
            .order_by(SymbolModel.code)
        )
    )
    expected = tuple(sorted(cast(list[str], candidate.manifest["classCodes"])))
    if codes != expected:
        raise JobConflictError(
            "SYMBOL_MODEL_CLASS_CATALOG_MISMATCH",
            "Candidate classes differ from the active catalog.",
        )


def require_iteration_candidate(
    session: Session, root: Path, record: SymbolModelIterationModel
) -> LabSymbolCandidate:
    candidate = require_candidate(root, record.origin_fingerprint or "", record.game_id)
    artifacts = cast(dict[str, dict[str, str]], candidate.manifest["artifacts"])
    identity = cast(dict[str, object], candidate.manifest["identity"])
    if (
        record.origin != "lab_import"
        or record.cohort_id is not None
        or record.origin_manifest_relative_path != artifacts["origin"]["relativePath"]
        or record.origin_manifest_checksum_sha256 != artifacts["origin"]["sha256"]
        or record.configuration_payload != identity
        or record.configuration_fingerprint != candidate.fingerprint
        or record.candidate_manifest_relative_path != candidate.manifest_relative_path
        or record.candidate_manifest_checksum_sha256 != candidate.manifest_sha256
        or record.gate_report_relative_path != artifacts["gateReport"]["relativePath"]
        or record.gate_report_checksum_sha256 != artifacts["gateReport"]["sha256"]
    ):
        raise JobConflictError(
            "LAB_CANDIDATE_BINDING_DRIFT", "Stored candidate origin binding changed."
        )
    require_catalog(session, candidate)
    return candidate
