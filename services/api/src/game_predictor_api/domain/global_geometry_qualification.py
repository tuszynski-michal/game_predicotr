"""Deterministic qualification policy for immutable shared geometry candidates."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from game_predictor_api.domain.global_geometry_library import (
    GlobalGeometryCandidate,
    GlobalGeometryLibraryError,
    GlobalGeometryProfileStatus,
    GlobalGeometryProfileWithEvidence,
    canonicalize_global_geometry_candidate,
)

if TYPE_CHECKING:
    from game_predictor_api.domain.global_geometry_library import JSONValue


GLOBAL_GEOMETRY_QUALIFICATION_REPORT_SCHEMA_VERSION = (
    "shape-geometry-global-qualification-report-v1"
)
GLOBAL_GEOMETRY_QUALIFICATION_POLICY_VERSION = "shape-geometry-v2-qualification-v1"
GLOBAL_GEOMETRY_QUALIFICATION_RESULT_SCHEMA_VERSION = (
    "shape-geometry-global-qualification-result-v1"
)

_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_GAME_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


class GlobalGeometryQualificationOutcome(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class GlobalGeometryQualificationReport:
    """Descriptor-only output of an external replay, regression and transfer run."""

    candidate_profile_checksum_sha256: str
    baseline_active_profile_checksum_sha256: str | None
    replay_snapshot_checksum_sha256: str
    regression_snapshot_checksum_sha256: str
    transfer_snapshot_checksum_sha256: str
    contributor_game_refs: tuple[str, ...]
    transfer_target_game_ref: str
    replay_expected_source_count: int
    replay_evaluated_source_count: int
    replay_automatic_incorrect_source_count: int
    regression_expected_source_count: int
    regression_evaluated_source_count: int
    regression_baseline_automatic_incorrect_source_count: int
    regression_candidate_automatic_incorrect_source_count: int
    transfer_expected_source_count: int
    transfer_evaluated_source_count: int
    transfer_automatic_incorrect_source_count: int

    def as_dict(self) -> dict[str, JSONValue]:
        return {
            "baselineActiveProfileChecksumSha256": self.baseline_active_profile_checksum_sha256,
            "candidateProfileChecksumSha256": self.candidate_profile_checksum_sha256,
            "contributorGameRefs": list(self.contributor_game_refs),
            "policyVersion": GLOBAL_GEOMETRY_QUALIFICATION_POLICY_VERSION,
            "regressionAutomaticIncorrectSourceCount": (
                self.regression_candidate_automatic_incorrect_source_count
            ),
            "regressionBaselineAutomaticIncorrectSourceCount": (
                self.regression_baseline_automatic_incorrect_source_count
            ),
            "regressionEvaluatedSourceCount": self.regression_evaluated_source_count,
            "regressionExpectedSourceCount": self.regression_expected_source_count,
            "regressionSnapshotChecksumSha256": self.regression_snapshot_checksum_sha256,
            "replayAutomaticIncorrectSourceCount": self.replay_automatic_incorrect_source_count,
            "replayEvaluatedSourceCount": self.replay_evaluated_source_count,
            "replayExpectedSourceCount": self.replay_expected_source_count,
            "replaySnapshotChecksumSha256": self.replay_snapshot_checksum_sha256,
            "schemaVersion": GLOBAL_GEOMETRY_QUALIFICATION_REPORT_SCHEMA_VERSION,
            "transferAutomaticIncorrectSourceCount": self.transfer_automatic_incorrect_source_count,
            "transferEvaluatedSourceCount": self.transfer_evaluated_source_count,
            "transferExpectedSourceCount": self.transfer_expected_source_count,
            "transferSnapshotChecksumSha256": self.transfer_snapshot_checksum_sha256,
            "transferTargetGameRef": self.transfer_target_game_ref,
        }

    def checksum_sha256(self) -> str:
        return _sha256(self.as_dict())


@dataclass(frozen=True, slots=True)
class GlobalGeometryQualificationDecision:
    outcome: GlobalGeometryQualificationOutcome
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GlobalGeometryQualificationResult:
    id: UUID
    profile_id: UUID
    previous_active_profile_id: UUID | None
    outcome: GlobalGeometryQualificationOutcome
    reason_codes: tuple[str, ...]
    report: GlobalGeometryQualificationReport | None
    qualification_checksum_sha256: str
    created_at: datetime


def build_global_geometry_qualification_report(
    *,
    candidate_profile_checksum_sha256: str,
    baseline_active_profile_checksum_sha256: str | None,
    replay_snapshot_checksum_sha256: str,
    regression_snapshot_checksum_sha256: str,
    transfer_snapshot_checksum_sha256: str,
    contributor_game_refs: Sequence[str],
    transfer_target_game_ref: str,
    replay_expected_source_count: int,
    replay_evaluated_source_count: int,
    replay_automatic_incorrect_source_count: int,
    regression_expected_source_count: int,
    regression_evaluated_source_count: int,
    regression_baseline_automatic_incorrect_source_count: int,
    regression_candidate_automatic_incorrect_source_count: int,
    transfer_expected_source_count: int,
    transfer_evaluated_source_count: int,
    transfer_automatic_incorrect_source_count: int,
) -> GlobalGeometryQualificationReport:
    """Validate and freeze a report before it crosses the application boundary."""

    checksums: tuple[str, ...] = (
        candidate_profile_checksum_sha256,
        replay_snapshot_checksum_sha256,
        regression_snapshot_checksum_sha256,
        transfer_snapshot_checksum_sha256,
    )
    if baseline_active_profile_checksum_sha256 is not None:
        checksums = (*checksums, baseline_active_profile_checksum_sha256)
    if any(not isinstance(value, str) or not _CHECKSUM.fullmatch(value) for value in checksums):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_CHECKSUM_INVALID",
            "Qualification checksums must be lowercase SHA-256 digests.",
        )
    contributors = tuple(sorted(contributor_game_refs))
    if not contributors or len(set(contributors)) != len(contributors) or any(
        not isinstance(value, str) or not _GAME_REF.fullmatch(value) for value in contributors
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_CONTRIBUTORS_INVALID",
            "Qualification contributors must be unique short provenance references.",
        )
    if not isinstance(transfer_target_game_ref, str) or not _GAME_REF.fullmatch(
        transfer_target_game_ref
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_TRANSFER_TARGET_INVALID",
            "Qualification transfer target must be a short provenance reference.",
        )
    counts = (
        replay_expected_source_count,
        replay_evaluated_source_count,
        replay_automatic_incorrect_source_count,
        regression_expected_source_count,
        regression_evaluated_source_count,
        regression_baseline_automatic_incorrect_source_count,
        regression_candidate_automatic_incorrect_source_count,
        transfer_expected_source_count,
        transfer_evaluated_source_count,
        transfer_automatic_incorrect_source_count,
    )
    if any(type(value) is not int or value < 0 for value in counts):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_COUNTER_INVALID",
            "Qualification counters must be non-negative integers.",
        )
    if (
        replay_automatic_incorrect_source_count > replay_evaluated_source_count
        or regression_baseline_automatic_incorrect_source_count
        > regression_evaluated_source_count
        or regression_candidate_automatic_incorrect_source_count
        > regression_evaluated_source_count
        or transfer_automatic_incorrect_source_count > transfer_evaluated_source_count
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_COUNTER_INVALID",
            "Qualification incorrect-source counters cannot exceed evaluated sources.",
        )
    return GlobalGeometryQualificationReport(
        candidate_profile_checksum_sha256=candidate_profile_checksum_sha256,
        baseline_active_profile_checksum_sha256=baseline_active_profile_checksum_sha256,
        replay_snapshot_checksum_sha256=replay_snapshot_checksum_sha256,
        regression_snapshot_checksum_sha256=regression_snapshot_checksum_sha256,
        transfer_snapshot_checksum_sha256=transfer_snapshot_checksum_sha256,
        contributor_game_refs=contributors,
        transfer_target_game_ref=transfer_target_game_ref,
        replay_expected_source_count=replay_expected_source_count,
        replay_evaluated_source_count=replay_evaluated_source_count,
        replay_automatic_incorrect_source_count=replay_automatic_incorrect_source_count,
        regression_expected_source_count=regression_expected_source_count,
        regression_evaluated_source_count=regression_evaluated_source_count,
        regression_baseline_automatic_incorrect_source_count=(
            regression_baseline_automatic_incorrect_source_count
        ),
        regression_candidate_automatic_incorrect_source_count=(
            regression_candidate_automatic_incorrect_source_count
        ),
        transfer_expected_source_count=transfer_expected_source_count,
        transfer_evaluated_source_count=transfer_evaluated_source_count,
        transfer_automatic_incorrect_source_count=transfer_automatic_incorrect_source_count,
    )


def evaluate_global_geometry_candidate(
    *,
    stored: GlobalGeometryProfileWithEvidence,
    report: GlobalGeometryQualificationReport | None,
    current_active_profile_checksum_sha256: str | None,
) -> GlobalGeometryQualificationDecision:
    """Return a fail-closed publication decision without changing storage."""

    try:
        _validate_candidate_integrity(stored)
    except GlobalGeometryLibraryError as error:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.REJECTED,
            ("GLOBAL_GEOMETRY_QUALIFICATION_PROFILE_INVALID", error.code),
        )
    if report is None:
        return _not_evaluable("GLOBAL_GEOMETRY_QUALIFICATION_REPORT_MISSING")
    profile = stored.profile
    if report.candidate_profile_checksum_sha256 != profile.profile_checksum_sha256:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.REJECTED,
            ("GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_CHECKSUM_MISMATCH",),
        )
    contributor_refs = tuple(sorted({item.source_game_ref for item in stored.evidence}))
    if report.contributor_game_refs != contributor_refs:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.REJECTED,
            ("GLOBAL_GEOMETRY_QUALIFICATION_CONTRIBUTOR_MISMATCH",),
        )
    if report.baseline_active_profile_checksum_sha256 != current_active_profile_checksum_sha256:
        return _not_evaluable("GLOBAL_GEOMETRY_QUALIFICATION_BASELINE_STALE")
    incomplete_codes = _incomplete_report_codes(report)
    if incomplete_codes:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.NOT_EVALUABLE,
            incomplete_codes,
        )
    if report.transfer_target_game_ref in contributor_refs:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.REJECTED,
            ("GLOBAL_GEOMETRY_QUALIFICATION_TRANSFER_TARGET_LEAKAGE",),
        )
    quality_codes: list[str] = []
    if report.replay_automatic_incorrect_source_count:
        quality_codes.append("GLOBAL_GEOMETRY_QUALIFICATION_REPLAY_INCORRECT")
    if (
        report.regression_candidate_automatic_incorrect_source_count
        > report.regression_baseline_automatic_incorrect_source_count
    ):
        quality_codes.append("GLOBAL_GEOMETRY_QUALIFICATION_REGRESSION")
    if report.transfer_automatic_incorrect_source_count:
        quality_codes.append("GLOBAL_GEOMETRY_QUALIFICATION_TRANSFER_INCORRECT")
    if quality_codes:
        return GlobalGeometryQualificationDecision(
            GlobalGeometryQualificationOutcome.REJECTED, tuple(quality_codes)
        )
    return GlobalGeometryQualificationDecision(GlobalGeometryQualificationOutcome.PASSED, ())


def qualification_command_sha256(
    *, profile_id: UUID, report: GlobalGeometryQualificationReport | None
) -> str:
    return _sha256(
        {
            "operation": "qualify_global_geometry_candidate",
            "profileId": str(profile_id),
            "reportChecksumSha256": None if report is None else report.checksum_sha256(),
        }
    )


def qualification_result_checksum_sha256(
    *,
    profile_checksum_sha256: str,
    previous_active_profile_checksum_sha256: str | None,
    decision: GlobalGeometryQualificationDecision,
    report: GlobalGeometryQualificationReport | None,
) -> str:
    return _sha256(
        {
            "candidateProfileChecksumSha256": profile_checksum_sha256,
            "outcome": decision.outcome.value,
            "previousActiveProfileChecksumSha256": previous_active_profile_checksum_sha256,
            "reasonCodes": list(decision.reason_codes),
            "reportChecksumSha256": None if report is None else report.checksum_sha256(),
            "schemaVersion": GLOBAL_GEOMETRY_QUALIFICATION_RESULT_SCHEMA_VERSION,
        }
    )


def report_from_mapping(raw: Mapping[str, object]) -> GlobalGeometryQualificationReport:
    """Deserialize the bounded report stored in the append-only audit record."""

    expected = {
        "baselineActiveProfileChecksumSha256",
        "candidateProfileChecksumSha256",
        "contributorGameRefs",
        "policyVersion",
        "regressionAutomaticIncorrectSourceCount",
        "regressionBaselineAutomaticIncorrectSourceCount",
        "regressionEvaluatedSourceCount",
        "regressionExpectedSourceCount",
        "regressionSnapshotChecksumSha256",
        "replayAutomaticIncorrectSourceCount",
        "replayEvaluatedSourceCount",
        "replayExpectedSourceCount",
        "replaySnapshotChecksumSha256",
        "schemaVersion",
        "transferAutomaticIncorrectSourceCount",
        "transferEvaluatedSourceCount",
        "transferExpectedSourceCount",
        "transferSnapshotChecksumSha256",
        "transferTargetGameRef",
    }
    if set(raw) != expected:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_REPORT_INVALID",
            "Qualification report fields are invalid.",
        )
    if (
        raw["schemaVersion"] != GLOBAL_GEOMETRY_QUALIFICATION_REPORT_SCHEMA_VERSION
        or raw["policyVersion"] != GLOBAL_GEOMETRY_QUALIFICATION_POLICY_VERSION
    ):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_REPORT_VERSION_INVALID",
            "Qualification report schema or policy version is unsupported.",
        )
    contributors = raw["contributorGameRefs"]
    if not isinstance(contributors, list):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_CONTRIBUTORS_INVALID",
            "Qualification contributors must be a list.",
        )
    baseline = raw["baselineActiveProfileChecksumSha256"]
    if baseline is not None and not isinstance(baseline, str):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_CHECKSUM_INVALID",
            "Qualification baseline checksum is invalid.",
        )
    return build_global_geometry_qualification_report(
        candidate_profile_checksum_sha256=_require_string(
            raw["candidateProfileChecksumSha256"], "candidate checksum"
        ),
        baseline_active_profile_checksum_sha256=baseline,
        replay_snapshot_checksum_sha256=_require_string(
            raw["replaySnapshotChecksumSha256"], "replay checksum"
        ),
        regression_snapshot_checksum_sha256=_require_string(
            raw["regressionSnapshotChecksumSha256"], "regression checksum"
        ),
        transfer_snapshot_checksum_sha256=_require_string(
            raw["transferSnapshotChecksumSha256"], "transfer checksum"
        ),
        contributor_game_refs=tuple(contributors),
        transfer_target_game_ref=_require_string(raw["transferTargetGameRef"], "transfer target"),
        replay_expected_source_count=_require_count(raw["replayExpectedSourceCount"]),
        replay_evaluated_source_count=_require_count(raw["replayEvaluatedSourceCount"]),
        replay_automatic_incorrect_source_count=_require_count(
            raw["replayAutomaticIncorrectSourceCount"]
        ),
        regression_expected_source_count=_require_count(raw["regressionExpectedSourceCount"]),
        regression_evaluated_source_count=_require_count(raw["regressionEvaluatedSourceCount"]),
        regression_baseline_automatic_incorrect_source_count=_require_count(
            raw["regressionBaselineAutomaticIncorrectSourceCount"]
        ),
        regression_candidate_automatic_incorrect_source_count=_require_count(
            raw["regressionAutomaticIncorrectSourceCount"]
        ),
        transfer_expected_source_count=_require_count(raw["transferExpectedSourceCount"]),
        transfer_evaluated_source_count=_require_count(raw["transferEvaluatedSourceCount"]),
        transfer_automatic_incorrect_source_count=_require_count(
            raw["transferAutomaticIncorrectSourceCount"]
        ),
    )


def _validate_candidate_integrity(stored: GlobalGeometryProfileWithEvidence) -> None:
    if stored.profile.status is not GlobalGeometryProfileStatus.CANDIDATE:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_CANDIDATE_STATUS_INVALID",
            "Only a candidate profile can be qualified.",
        )
    canonicalize_global_geometry_candidate(
        # The candidate builder validates the same descriptor and full evidence checksum
        # without requiring the persisted candidate to be active first.
        GlobalGeometryCandidate(
            geometry_family=stored.profile.geometry_family,
            topology=stored.profile.topology,
            normalized_template=stored.profile.normalized_template,
            frame_appearance=stored.profile.frame_appearance,
            evidence_summary=stored.profile.evidence_summary,
            evidence=stored.evidence,
            profile_checksum_sha256=stored.profile.profile_checksum_sha256,
        )
    )


def _incomplete_report_codes(report: GlobalGeometryQualificationReport) -> tuple[str, ...]:
    codes: list[str] = []
    for prefix, expected, evaluated in (
        ("REPLAY", report.replay_expected_source_count, report.replay_evaluated_source_count),
        (
            "REGRESSION",
            report.regression_expected_source_count,
            report.regression_evaluated_source_count,
        ),
        ("TRANSFER", report.transfer_expected_source_count, report.transfer_evaluated_source_count),
    ):
        if expected < 1 or evaluated != expected:
            codes.append(f"GLOBAL_GEOMETRY_QUALIFICATION_{prefix}_INCOMPLETE")
    return tuple(codes)


def _not_evaluable(code: str) -> GlobalGeometryQualificationDecision:
    return GlobalGeometryQualificationDecision(
        GlobalGeometryQualificationOutcome.NOT_EVALUABLE, (code,)
    )


def _require_count(value: object) -> int:
    if type(value) is not int:
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_COUNTER_INVALID",
            "Qualification counters must be integers.",
        )
    return value


def _require_string(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise GlobalGeometryLibraryError(
            "GLOBAL_GEOMETRY_QUALIFICATION_REPORT_INVALID",
            f"Qualification {name} is invalid.",
        )
    return value


def _sha256(value: Mapping[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "GLOBAL_GEOMETRY_QUALIFICATION_POLICY_VERSION",
    "GLOBAL_GEOMETRY_QUALIFICATION_REPORT_SCHEMA_VERSION",
    "GlobalGeometryQualificationDecision",
    "GlobalGeometryQualificationOutcome",
    "GlobalGeometryQualificationReport",
    "GlobalGeometryQualificationResult",
    "build_global_geometry_qualification_report",
    "evaluate_global_geometry_candidate",
    "qualification_command_sha256",
    "qualification_result_checksum_sha256",
    "report_from_mapping",
]
