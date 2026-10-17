"""Eligibility read contract. Only the server evaluator owns evaluation outcomes.

No HTTP command can create a report. The TASK-0997 evaluator job writes measured
v2 reports; v1 keeps its closed historical contract. The v2 reader recomputes the
policy decisions from stored measures (``grid_model_evaluation``); cohort
currentness proofs are a separate barrier of the publication service.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from .grid_model_evaluation import REPORT_SCHEMA as EVALUATION_SCHEMA_V2
from .grid_model_evaluation import GridEvaluationReportError, require_report
from .grid_model_registry import GridModelRegistryError, canonical_json, descriptor_sha256

EVALUATION_SCHEMA = "grid-model-evaluation-read-v1"
EVALUATION_PRODUCER = "server:grid-model-evaluator-v1"
EVALUATION_POLICY = "grid-model-per-game-gate-v1"
_SHA = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class GridEvaluationEvidence:
    report_id: UUID
    report_sha256: str
    games: frozenset[UUID]
    # v2 only: the (gameId, cohortId, manifestSha256) entries whose proofs must be current.
    cohorts: tuple[dict[str, str], ...] = ()


def require_evaluation_evidence(
    *,
    report_id: UUID,
    report_json: str,
    report_sha256: str,
    producer: str,
    invalidated: bool,
    manifest: dict[str, Any],
    base_sha256: str,
    game_id: UUID | None,
) -> GridEvaluationEvidence:
    """Check a persisted trusted read model, its complete scope and immutable pins.

    Outcomes are evaluator-owned; accepting client-created JSON here would violate
    the trust boundary. The repository reads rows, never request payloads.
    """
    try:
        if len(report_json) > 1024 * 1024:
            raise ValueError("Evaluation read model is too large.")
        report = json.loads(report_json)
        if isinstance(report, dict) and report.get("schemaVersion") == EVALUATION_SCHEMA_V2:
            return _require_v2(
                report_id=report_id,
                report_json=report_json,
                report_sha256=report_sha256,
                producer=producer,
                invalidated=invalidated,
                manifest=manifest,
                base_sha256=base_sha256,
                game_id=game_id,
            )
        if (
            producer != EVALUATION_PRODUCER
            or invalidated
            or canonical_json(report) != report_json
            or descriptor_sha256(report) != report_sha256
            or report.keys()
            != {
                "schemaVersion",
                "producer",
                "policyVersion",
                "versionId",
                "manifestSha256",
                "baseVersionId",
                "baseManifestSha256",
                "cohortId",
                "cohortSha256",
                "requiredGameIds",
                "games",
            }
            or report["schemaVersion"] != EVALUATION_SCHEMA
            or report["producer"] != EVALUATION_PRODUCER
            or report["policyVersion"] != EVALUATION_POLICY
            or report["versionId"] != manifest["versionId"]
            or report["manifestSha256"] != descriptor_sha256(manifest)
            or report["baseVersionId"] != manifest["baseVersionId"]
            or report["baseManifestSha256"] != base_sha256
            or manifest["cohortId"] is None
            or report["cohortId"] != manifest["cohortId"]
            or _SHA.fullmatch(report["cohortSha256"]) is None
        ):
            raise ValueError("Evidence identity, policy or currentness differs.")
        UUID(report["cohortId"])
        required = report["requiredGameIds"]
        games = report["games"]
        if (
            not isinstance(required, list)
            or not 1 <= len(required) <= 100
            or not isinstance(games, list)
            or len(games) != len(required)
            or len(set(required)) != len(required)
        ):
            raise ValueError("Incomplete evaluation scope.")
        identifiers = frozenset(UUID(value) for value in required)
        measured: set[UUID] = set()
        for outcome in games:
            if (
                outcome.keys() != {"gameId", "validation", "regression", "coverage"}
                or outcome["validation"] != "pass"
                or outcome["regression"] != "pass"
                or outcome["coverage"] != "complete"
            ):
                raise ValueError("Each required game needs a complete passing evaluation.")
            measured.add(UUID(outcome["gameId"]))
        if measured != identifiers or len(measured) != len(games):
            raise ValueError("Evaluation game coverage differs.")
        if game_id is not None and game_id not in identifiers:
            raise ValueError("The game is outside this evaluated scope.")
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        raise GridModelRegistryError(
            "GRID_MODEL_EVALUATION_REQUIRED",
            "A current compatible server evaluation must pass for every required game.",
        ) from error
    return GridEvaluationEvidence(report_id, report_sha256, identifiers)


def _require_v2(
    *,
    report_id: UUID,
    report_json: str,
    report_sha256: str,
    producer: str,
    invalidated: bool,
    manifest: dict[str, Any],
    base_sha256: str,
    game_id: UUID | None,
) -> GridEvaluationEvidence:
    """Only a measured PASS of every required game is publication evidence."""
    if (
        producer != EVALUATION_PRODUCER
        or invalidated
        or descriptor_sha256(json.loads(report_json)) != report_sha256
    ):
        raise ValueError("Evidence identity or currentness differs.")
    try:
        report = require_report(report_json, manifest=manifest, base_sha256=base_sha256)
    except GridEvaluationReportError as error:
        raise ValueError(str(error)) from error
    if report["verdict"] != "PASS":
        raise ValueError("The measured evaluation did not pass.")
    identifiers = frozenset(UUID(value) for value in report["requiredGameIds"])
    if game_id is not None and game_id not in identifiers:
        raise ValueError("The game is outside this evaluated scope.")
    return GridEvaluationEvidence(
        report_id,
        report_sha256,
        identifiers,
        tuple(dict(entry) for entry in report["cohorts"]),
    )
