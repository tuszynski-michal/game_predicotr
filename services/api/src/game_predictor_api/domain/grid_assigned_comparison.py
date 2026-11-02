"""Immutable assigned-baseline comparison, separate from the candidate's training base."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from .grid_correction_evaluation import (
    PHOTO_ONLY_LIMITATIONS,
    PRODUCER,
    _closed,
    _require_role,
    decide_game,
)
from .grid_model_evaluation import MAX_REPORT_BYTES, ROLES, _count, _sha, _uuid, verdict_of
from .grid_model_evaluation import GridEvaluationReportError as GridEvaluationReportError
from .grid_model_registry import canonical_json, descriptor_sha256

REPORT_SCHEMA: Final = "grid-model-assigned-comparison-v1"
POLICY_VERSION: Final = "grid-model-assigned-nonregression-v1"
REPORT_KEYS: Final = {
    "schemaVersion",
    "producer",
    "policyVersion",
    "versionId",
    "manifestSha256",
    "baselineVersionId",
    "baselineManifestSha256",
    "gameId",
    "assignmentRevision",
    "cohort",
    "parity",
    "roles",
    "decision",
    "verdict",
    "evidenceLevel",
    "limitations",
}


def build_report(
    *,
    manifest: Mapping[str, Any],
    baseline_manifest_sha256: str,
    baseline_version_id: str,
    game_id: str,
    assignment_revision: int,
    cohort: Mapping[str, Any],
    measured: Mapping[str, Any],
    parity: Mapping[str, Any],
) -> dict[str, Any]:
    """The server supplies the actual assignment pins; no candidate manifest is rewritten."""
    measurement = _closed(dict(measured), {"mode", "roles"}, "Assigned measurement")
    decision = decide_game(
        mode=measurement["mode"],
        training=False,
        parity_passed=parity["passed"],
        roles=measurement["roles"],
    )
    report = {
        "schemaVersion": REPORT_SCHEMA,
        "producer": PRODUCER,
        "policyVersion": POLICY_VERSION,
        "versionId": manifest["versionId"],
        "manifestSha256": descriptor_sha256(dict(manifest)),
        "baselineVersionId": baseline_version_id,
        "baselineManifestSha256": baseline_manifest_sha256,
        "gameId": game_id,
        "assignmentRevision": assignment_revision,
        "cohort": dict(cohort),
        "parity": dict(parity),
        "roles": dict(measurement["roles"]),
        "decision": decision,
        "verdict": verdict_of([decision]),
        "evidenceLevel": "photo-only",
        "limitations": PHOTO_ONLY_LIMITATIONS,
    }
    return require_report(
        canonical_json(report),
        manifest=manifest,
        baseline_sha256=baseline_manifest_sha256,
        expected_baseline_version_id=baseline_version_id,
        expected_game_id=game_id,
        expected_assignment_revision=assignment_revision,
        expected_cohort=cohort,
    )


def require_report(
    report_json: str,
    *,
    manifest: Mapping[str, Any],
    baseline_sha256: str,
    expected_baseline_version_id: str | None = None,
    expected_game_id: str | None = None,
    expected_assignment_revision: int | None = None,
    expected_cohort: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate immutable measures and gate; expected pins bind the server's saved assignment.

    A baseline hash alone cannot prove its UUID or an assignment revision. Publication/apply
    callers must supply the expected pins from the durable job and check live assignment CAS.
    The training base remains part of the unchanged candidate manifest's descriptor hash.
    """
    try:
        if len(report_json.encode("utf-8")) > MAX_REPORT_BYTES:
            raise GridEvaluationReportError("The assigned comparison report is too large.")
        report = _closed(json.loads(report_json), REPORT_KEYS, "Assigned report")
        if canonical_json(report) != report_json:
            raise GridEvaluationReportError("The assigned comparison is not canonical JSON.")
        if (
            report["schemaVersion"] != REPORT_SCHEMA
            or report["producer"] != PRODUCER
            or report["policyVersion"] != POLICY_VERSION
            or report["versionId"] != manifest["versionId"]
            or report["manifestSha256"] != descriptor_sha256(dict(manifest))
            or report["baselineManifestSha256"] != baseline_sha256
            or report["evidenceLevel"] != "photo-only"
            or report["limitations"] != PHOTO_ONLY_LIMITATIONS
        ):
            raise GridEvaluationReportError(
                "Assigned comparison identity, policy or evidence differs."
            )
        for key in ("versionId", "baselineVersionId", "gameId"):
            _uuid(report[key])
        _sha(report["manifestSha256"])
        _sha(report["baselineManifestSha256"])
        _count(report["assignmentRevision"])
        cohort = _closed(
            report["cohort"], {"gameId", "cohortId", "manifestSha256"}, "Assigned cohort"
        )
        _uuid(cohort["gameId"])
        _uuid(cohort["cohortId"])
        _sha(cohort["manifestSha256"])
        if cohort["gameId"] != report["gameId"]:
            raise GridEvaluationReportError("Assigned comparison cohort belongs to another game.")
        for key, expected in (
            ("baselineVersionId", expected_baseline_version_id),
            ("gameId", expected_game_id),
            ("assignmentRevision", expected_assignment_revision),
        ):
            if expected is not None and report[key] != expected:
                raise GridEvaluationReportError("Assigned comparison differs from its server pins.")
        if expected_cohort is not None and cohort != dict(expected_cohort):
            raise GridEvaluationReportError(
                "Assigned comparison cohort differs from its server pin."
            )
        parity = _closed(report["parity"], {"passed", "bundleSha256"}, "Assigned parity")
        if type(parity["passed"]) is not bool:
            raise GridEvaluationReportError("Parity requires a boolean result.")
        _sha(parity["bundleSha256"])
        roles = _closed(report["roles"], set(ROLES), "Assigned roles")
        for role in ROLES:
            _require_role(roles[role])
        decision = decide_game(
            mode="grid-only", training=False, parity_passed=parity["passed"], roles=roles
        )
        stored = _closed(
            report["decision"],
            {"validation", "regression", "coverage", "reasons"},
            "Assigned decision",
        )
        if stored != decision or report["verdict"] != verdict_of([decision]):
            raise GridEvaluationReportError(
                "Assigned comparison decision differs from non-regression policy."
            )
        return report
    except (KeyError, TypeError, AttributeError, ValueError) as error:
        if isinstance(error, GridEvaluationReportError):
            raise
        raise GridEvaluationReportError(
            "The report does not follow the assigned-comparison contract."
        ) from error
