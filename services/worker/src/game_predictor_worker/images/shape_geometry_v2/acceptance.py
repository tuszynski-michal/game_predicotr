"""Independent, local-only acceptance evaluator for shared shape geometry v2."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from game_predictor_api.domain.global_geometry_library import (
    GlobalGeometryCandidate,
    GlobalGeometryLibraryError,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationReport,
    report_from_mapping,
)
from numpy.typing import NDArray

from .core import SHAPE_GEOMETRY_V2_CORE_VERSION, ShapeGeometryV2Config
from .corpus import (
    CorpusVisibility,
    ShapeGeometryCorpusError,
    ShapeGeometryCorpusManifest,
    ShapeGeometryFrozenInventory,
    ShapeGeometryManualAnnotations,
    canonical_json_bytes,
    verify_split_boundary,
)
from .pilot import (
    ShapeGeometryPilotError,
    ShapeGeometryPilotInput,
    run_shape_geometry_pilot,
)
from .preflight import (
    ShapeGeometryV2PreflightError,
    ShapeGeometryV2PreflightProfile,
    parse_shape_geometry_v2_preflight_profile,
    verify_shape_geometry_v2_profile,
)

SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_VERSION = 1
SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_VERSION = "shape-geometry-v2-acceptance-report-v1"

_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_REASON_CODE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{2,127}$")


class ShapeGeometryAcceptanceError(ValueError):
    """Stable error for malformed local acceptance artifacts."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ShapeGeometryAcceptanceStatus(StrEnum):
    PASSED = "passed"
    REJECTED = "rejected"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True, slots=True)
class ShapeGeometryAcceptanceTruth:
    source_id: str
    source_checksum_sha256: str
    expected_verdict: str
    expected_reason_code: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryAcceptanceTruth:
        _require_exact_keys(
            raw,
            {"sourceId", "sourceChecksumSha256", "expectedVerdict", "expectedReasonCode"},
            "acceptance truth item",
        )
        source_id = raw["sourceId"]
        if not isinstance(source_id, str) or _SOURCE_ID.fullmatch(source_id) is None:
            _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", "Truth sourceId is invalid.")
        verdict = raw["expectedVerdict"]
        if verdict not in {"needs_manual_review", "proposal_requires_manual_confirmation"}:
            _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", "Truth verdict is invalid.")
        reason = raw["expectedReasonCode"]
        if not isinstance(reason, str) or _REASON_CODE.fullmatch(reason) is None:
            _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", "Truth reason code is invalid.")
        return cls(
            source_id=cast(str, source_id),
            source_checksum_sha256=_require_checksum(
                raw["sourceChecksumSha256"], "truth source checksum"
            ),
            expected_verdict=cast(str, verdict),
            expected_reason_code=cast(str, reason),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "expectedReasonCode": self.expected_reason_code,
            "expectedVerdict": self.expected_verdict,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryAcceptanceInput:
    core_version: str
    core_config: dict[str, object]
    preflight_profile: dict[str, object]
    pilot_input: dict[str, object]
    executor_annotations: dict[str, object]
    pilot_report: dict[str, object]
    pilot_report_checksum_sha256: str
    qualification_report: dict[str, object]
    qualification_report_checksum_sha256: str
    truth: tuple[ShapeGeometryAcceptanceTruth, ...]
    truth_checksum_sha256: str

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryAcceptanceInput:
        _require_exact_keys(
            raw,
            {
                "schemaVersion",
                "coreVersion",
                "coreConfig",
                "preflightProfile",
                "pilotInput",
                "executorAnnotations",
                "pilotReport",
                "pilotReportChecksumSha256",
                "qualificationReport",
                "qualificationReportChecksumSha256",
                "truth",
                "truthChecksumSha256",
            },
            "acceptance input",
        )
        if raw["schemaVersion"] != SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_VERSION:
            _fail(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", "Input schema version is unsupported."
            )
        core_version = raw["coreVersion"]
        if not isinstance(core_version, str) or not core_version:
            _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", "Input coreVersion is invalid.")
        truth = tuple(
            ShapeGeometryAcceptanceTruth.from_mapping(_require_mapping(item, "truth item"))
            for item in _require_sequence(raw["truth"], "truth")
        )
        source_ids = tuple(item.source_id for item in truth)
        if not truth or len(source_ids) != len(set(source_ids)):
            _fail(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID",
                "Acceptance truth must be non-empty and have unique source IDs.",
            )
        return cls(
            core_version=cast(str, core_version),
            core_config=_json_object(_require_mapping(raw["coreConfig"], "coreConfig")),
            preflight_profile=_json_object(
                _require_mapping(raw["preflightProfile"], "preflightProfile")
            ),
            pilot_input=_json_object(_require_mapping(raw["pilotInput"], "pilotInput")),
            executor_annotations=_json_object(
                _require_mapping(raw["executorAnnotations"], "executorAnnotations")
            ),
            pilot_report=_json_object(_require_mapping(raw["pilotReport"], "pilotReport")),
            pilot_report_checksum_sha256=_require_checksum(
                raw["pilotReportChecksumSha256"], "pilot report checksum"
            ),
            qualification_report=_json_object(
                _require_mapping(raw["qualificationReport"], "qualificationReport")
            ),
            qualification_report_checksum_sha256=_require_checksum(
                raw["qualificationReportChecksumSha256"], "qualification report checksum"
            ),
            truth=truth,
            truth_checksum_sha256=_require_checksum(raw["truthChecksumSha256"], "truth checksum"),
        )

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "coreConfig": self.core_config,
                "coreVersion": self.core_version,
                "pilotInput": self.pilot_input,
                "executorAnnotations": self.executor_annotations,
                "pilotReport": self.pilot_report,
                "pilotReportChecksumSha256": self.pilot_report_checksum_sha256,
                "preflightProfile": self.preflight_profile,
                "qualificationReport": self.qualification_report,
                "qualificationReportChecksumSha256": self.qualification_report_checksum_sha256,
                "schemaVersion": SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_VERSION,
                "truth": [
                    item.as_dict() for item in sorted(self.truth, key=lambda item: item.source_id)
                ],
                "truthChecksumSha256": self.truth_checksum_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class ShapeGeometryAcceptanceSourceResult:
    source_id: str
    source_checksum_sha256: str
    expected_verdict: str
    expected_reason_code: str
    actual_verdict: str
    actual_reason_code: str
    actual_verification_checksum_sha256: str

    @property
    def matches_truth(self) -> bool:
        return (
            self.expected_verdict == self.actual_verdict
            and self.expected_reason_code == self.actual_reason_code
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "actualReasonCode": self.actual_reason_code,
            "actualVerificationChecksumSha256": self.actual_verification_checksum_sha256,
            "actualVerdict": self.actual_verdict,
            "expectedReasonCode": self.expected_reason_code,
            "expectedVerdict": self.expected_verdict,
            "matchesTruth": self.matches_truth,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryAcceptanceResult:
    status: ShapeGeometryAcceptanceStatus
    input_fingerprint: str
    reason_codes: tuple[str, ...]
    split_boundary: dict[str, object] | None
    source_results: tuple[ShapeGeometryAcceptanceSourceResult, ...]
    acceptance_snapshot_checksum_sha256: str | None

    def as_dict(self) -> dict[str, object]:
        return {
            "acceptanceSnapshotChecksumSha256": self.acceptance_snapshot_checksum_sha256,
            "inputFingerprint": self.input_fingerprint,
            "reasonCodes": list(self.reason_codes),
            "schemaVersion": SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_VERSION,
            "sourceResults": [item.as_dict() for item in self.source_results],
            "splitBoundary": self.split_boundary,
            "status": self.status.value,
        }


def load_shape_geometry_v2_acceptance_input(path: Path) -> ShapeGeometryAcceptanceInput:
    """Load the single frozen, local-only acceptance input artifact."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryAcceptanceError(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_UNREADABLE", "Acceptance input cannot be read."
        ) from error
    return ShapeGeometryAcceptanceInput.from_mapping(_require_mapping(raw, "acceptance input"))


def run_shape_geometry_v2_acceptance(
    *,
    executor_manifest: ShapeGeometryCorpusManifest | None = None,
    executor_inventory: Mapping[str, object] | None = None,
    acceptance_manifest: ShapeGeometryCorpusManifest | None = None,
    acceptance_inventory: Mapping[str, object] | None = None,
    frozen_input: ShapeGeometryAcceptanceInput | None = None,
) -> ShapeGeometryAcceptanceResult:
    """Evaluate an immutable acceptance set without publishing or activating a profile."""

    provided = (
        executor_manifest,
        executor_inventory,
        acceptance_manifest,
        acceptance_inventory,
        frozen_input,
    )
    if not any(value is not None for value in provided):
        return ShapeGeometryAcceptanceResult(
            status=ShapeGeometryAcceptanceStatus.NOT_EVALUABLE,
            input_fingerprint=_fingerprint(
                {"reason": "acceptance_artifacts_missing", "schemaVersion": 1}
            ),
            reason_codes=("SHAPE_GEOMETRY_V2_ACCEPTANCE_ARTIFACTS_MISSING",),
            split_boundary=None,
            source_results=(),
            acceptance_snapshot_checksum_sha256=None,
        )
    if any(value is None for value in provided):
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_ARGUMENTS_INCOMPLETE",
            "Executor, acceptance, inventory, and frozen input artifacts are all required.",
        )

    resolved_executor_manifest = cast(ShapeGeometryCorpusManifest, executor_manifest)
    resolved_executor_inventory = cast(Mapping[str, object], executor_inventory)
    resolved_acceptance_manifest = cast(ShapeGeometryCorpusManifest, acceptance_manifest)
    resolved_acceptance_inventory = cast(Mapping[str, object], acceptance_inventory)
    resolved_input = cast(ShapeGeometryAcceptanceInput, frozen_input)
    input_fingerprint = resolved_input.fingerprint()

    try:
        split_boundary, executor_current_inventory = _validate_corpora(
            resolved_executor_manifest,
            resolved_executor_inventory,
            resolved_acceptance_manifest,
            resolved_acceptance_inventory,
        )
    except (ShapeGeometryCorpusError, ShapeGeometryAcceptanceError) as error:
        return _rejected(input_fingerprint, (error.code,))

    profile, frozen_reasons = _validate_frozen_chain(
        resolved_input, resolved_executor_manifest, executor_current_inventory
    )
    if frozen_reasons:
        return _rejected(input_fingerprint, frozen_reasons, split_boundary)
    assert profile is not None
    try:
        first = _evaluate_sources(resolved_acceptance_manifest, profile, resolved_input.truth)
        second = _evaluate_sources(resolved_acceptance_manifest, profile, resolved_input.truth)
    except (ShapeGeometryCorpusError, ShapeGeometryAcceptanceError) as error:
        return _rejected(input_fingerprint, (error.code,), split_boundary)
    if canonical_json_bytes([item.as_dict() for item in first]) != canonical_json_bytes(
        [item.as_dict() for item in second]
    ):
        return _rejected(
            input_fingerprint,
            ("SHAPE_GEOMETRY_V2_ACCEPTANCE_REPLAY_DRIFT",),
            split_boundary,
        )
    snapshot_checksum = _fingerprint(
        {
            "inputFingerprint": input_fingerprint,
            "sourceResults": [item.as_dict() for item in first],
            "splitBoundary": split_boundary,
        }
    )
    if any(not item.matches_truth for item in first):
        return ShapeGeometryAcceptanceResult(
            status=ShapeGeometryAcceptanceStatus.REJECTED,
            input_fingerprint=input_fingerprint,
            reason_codes=("SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_MISMATCH",),
            split_boundary=split_boundary,
            source_results=first,
            acceptance_snapshot_checksum_sha256=snapshot_checksum,
        )
    return ShapeGeometryAcceptanceResult(
        status=ShapeGeometryAcceptanceStatus.PASSED,
        input_fingerprint=input_fingerprint,
        reason_codes=(),
        split_boundary=split_boundary,
        source_results=first,
        acceptance_snapshot_checksum_sha256=snapshot_checksum,
    )


def require_matching_shape_geometry_v2_acceptance(
    saved_report: Mapping[str, object], current_report: ShapeGeometryAcceptanceResult
) -> None:
    """Fail closed when the same frozen acceptance artifacts replay differently."""

    if canonical_json_bytes(saved_report) != canonical_json_bytes(current_report.as_dict()):
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_DRIFT",
            "Acceptance output differs from the saved checksum-bound report.",
        )


def _validate_corpora(
    executor_manifest: ShapeGeometryCorpusManifest,
    executor_inventory: Mapping[str, object],
    acceptance_manifest: ShapeGeometryCorpusManifest,
    acceptance_inventory: Mapping[str, object],
) -> tuple[dict[str, object], ShapeGeometryFrozenInventory]:
    if executor_manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail("SHAPE_GEOMETRY_V2_BOUNDARY_INVALID", "Executor manifest visibility is required.")
    if acceptance_manifest.visibility is not CorpusVisibility.ACCEPTANCE:
        _fail("SHAPE_GEOMETRY_V2_BOUNDARY_INVALID", "Acceptance manifest visibility is required.")
    executor_current = _require_current_inventory(executor_manifest, executor_inventory)
    _require_current_inventory(acceptance_manifest, acceptance_inventory)
    return (
        verify_split_boundary(executor_manifest, acceptance_manifest),
        executor_current,
    )


def _require_current_inventory(
    manifest: ShapeGeometryCorpusManifest, saved: Mapping[str, object]
) -> ShapeGeometryFrozenInventory:
    current = manifest.freeze_inventory()
    if canonical_json_bytes(saved) != canonical_json_bytes(current.as_dict()):
        _fail("SHAPE_GEOMETRY_V2_INVENTORY_DRIFT", "Frozen inventory differs from current sources.")
    return current


def _validate_frozen_chain(
    frozen_input: ShapeGeometryAcceptanceInput,
    executor_manifest: ShapeGeometryCorpusManifest,
    executor_inventory: ShapeGeometryFrozenInventory,
) -> tuple[ShapeGeometryV2PreflightProfile | None, tuple[str, ...]]:
    reasons: set[str] = set()
    if frozen_input.core_version != SHAPE_GEOMETRY_V2_CORE_VERSION:
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_CORE_VERSION_MISMATCH")
    if canonical_json_bytes(frozen_input.core_config) != canonical_json_bytes(
        ShapeGeometryV2Config().as_dict()
    ):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_CORE_CONFIG_MISMATCH")
    if frozen_input.pilot_report_checksum_sha256 != _fingerprint(frozen_input.pilot_report):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_REPORT_DRIFT")
    if frozen_input.truth_checksum_sha256 != _fingerprint(
        {
            "truth": [
                item.as_dict()
                for item in sorted(frozen_input.truth, key=lambda item: item.source_id)
            ]
        }
    ):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_DRIFT")
    try:
        profile = parse_shape_geometry_v2_preflight_profile(frozen_input.preflight_profile)
    except ShapeGeometryV2PreflightError as error:
        return None, tuple(sorted({*reasons, error.code}))
    try:
        pilot_input = ShapeGeometryPilotInput.from_mapping(frozen_input.pilot_input)
    except ShapeGeometryPilotError as error:
        return None, tuple(sorted({*reasons, error.code}))
    if pilot_input.corpus_manifest_fingerprint != executor_manifest.fingerprint():
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_EXECUTOR_MANIFEST_MISMATCH")
    if pilot_input.inventory_fingerprint != executor_inventory.fingerprint():
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_EXECUTOR_INVENTORY_MISMATCH")
    if frozen_input.pilot_report.get("inputFingerprint") != pilot_input.fingerprint():
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_INPUT_CHAIN_MISMATCH")
    try:
        executor_annotations = ShapeGeometryManualAnnotations.from_mapping(
            frozen_input.executor_annotations
        )
        replayed_pilot = run_shape_geometry_pilot(
            executor_manifest,
            executor_inventory,
            executor_annotations,
            pilot_input,
        )
    except (ShapeGeometryCorpusError, ShapeGeometryPilotError) as error:
        return None, tuple(sorted({*reasons, error.code}))
    if canonical_json_bytes(replayed_pilot.as_dict()) != canonical_json_bytes(
        frozen_input.pilot_report
    ):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_REPLAY_DRIFT")
    try:
        qualification = report_from_mapping(frozen_input.qualification_report)
    except GlobalGeometryLibraryError as error:
        return None, tuple(sorted({*reasons, error.code}))
    if frozen_input.qualification_report_checksum_sha256 != qualification.checksum_sha256():
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_REPORT_DRIFT")
    candidate, candidate_reason = _parse_pilot_candidate(frozen_input.pilot_report.get("candidate"))
    if candidate_reason is not None:
        reasons.add(candidate_reason)
    if frozen_input.pilot_report.get("status") != "measured":
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_NOT_MEASURED")
    pilot_qualification = frozen_input.pilot_report.get("qualificationReport")
    if not isinstance(pilot_qualification, Mapping) or canonical_json_bytes(
        pilot_qualification
    ) != canonical_json_bytes(qualification.as_dict()):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_CHAIN_MISMATCH")
    if candidate is not None:
        if (
            candidate.profile_checksum_sha256 != qualification.candidate_profile_checksum_sha256
            or candidate.profile_checksum_sha256 != profile.profile_checksum_sha256
            or canonical_json_bytes(candidate.normalized_template)
            != canonical_json_bytes(profile.normalized_template)
            or canonical_json_bytes(candidate.frame_appearance)
            != canonical_json_bytes(profile.frame_appearance)
            or candidate.topology != profile.topology
        ):
            reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_PROFILE_CHAIN_MISMATCH")
        contributor_refs = tuple(sorted({item.source_game_ref for item in candidate.evidence}))
        if qualification.contributor_game_refs != contributor_refs:
            reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_CONTRIBUTOR_MISMATCH")
        if qualification.transfer_target_game_ref in contributor_refs:
            reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_TRANSFER_LEAKAGE")
    if (
        qualification.baseline_active_profile_checksum_sha256 is None
        or not _qualification_counts_complete(qualification)
    ):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_INCOMPLETE")
    if (
        qualification.replay_automatic_incorrect_source_count
        or qualification.transfer_automatic_incorrect_source_count
        or qualification.regression_candidate_automatic_incorrect_source_count
        > qualification.regression_baseline_automatic_incorrect_source_count
    ):
        reasons.add("SHAPE_GEOMETRY_V2_ACCEPTANCE_QUALIFICATION_NOT_PASSED")
    return profile, tuple(sorted(reasons))


def _parse_pilot_candidate(
    raw: object,
) -> tuple[GlobalGeometryCandidate | None, str | None]:
    if not isinstance(raw, Mapping):
        return None, "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_CANDIDATE_INVALID"
    try:
        _require_exact_keys(
            raw,
            {
                "geometryFamily",
                "topology",
                "normalizedTemplate",
                "frameAppearance",
                "evidenceSummary",
                "evidence",
                "profileChecksumSha256",
            },
            "pilot candidate",
        )
        topology_raw = _require_mapping(raw["topology"], "pilot candidate topology")
        _require_exact_keys(
            topology_raw,
            {"pageBoardRows", "pageBoardColumns", "boardCellRows", "boardCellColumns"},
            "pilot candidate topology",
        )
        topology = GlobalGeometryTopology(
            page_board_rows=_require_positive_int(topology_raw["pageBoardRows"], "pageBoardRows"),
            page_board_columns=_require_positive_int(
                topology_raw["pageBoardColumns"], "pageBoardColumns"
            ),
            board_cell_rows=_require_positive_int(topology_raw["boardCellRows"], "boardCellRows"),
            board_cell_columns=_require_positive_int(
                topology_raw["boardCellColumns"], "boardCellColumns"
            ),
        )
        evidence_raw = _require_sequence(raw["evidence"], "pilot candidate evidence")
        evidence: list[tuple[str, Mapping[str, object]]] = []
        declared_evidence_checksums: list[str] = []
        for value in evidence_raw:
            item = _require_mapping(value, "pilot candidate evidence item")
            _require_exact_keys(
                item,
                {"sourceGameRef", "evidencePayload", "evidenceChecksumSha256"},
                "pilot candidate evidence item",
            )
            source_game_ref = item["sourceGameRef"]
            if not isinstance(source_game_ref, str):
                return None, "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_CANDIDATE_INVALID"
            evidence.append(
                (source_game_ref, _require_mapping(item["evidencePayload"], "evidencePayload"))
            )
            declared_evidence_checksums.append(
                _require_checksum(item["evidenceChecksumSha256"], "evidence checksum")
            )
        candidate = build_global_geometry_candidate(
            geometry_family=cast(str, raw["geometryFamily"]),
            topology=topology,
            normalized_template=_require_mapping(raw["normalizedTemplate"], "normalizedTemplate"),
            frame_appearance=_require_mapping(raw["frameAppearance"], "frameAppearance"),
            evidence_summary=_require_mapping(raw["evidenceSummary"], "evidenceSummary"),
            evidence=evidence,
        )
    except (GlobalGeometryLibraryError, ShapeGeometryAcceptanceError, TypeError, ValueError):
        return None, "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_CANDIDATE_INVALID"
    if raw[
        "profileChecksumSha256"
    ] != candidate.profile_checksum_sha256 or declared_evidence_checksums != [
        item.evidence_checksum_sha256 for item in candidate.evidence
    ]:
        return None, "SHAPE_GEOMETRY_V2_ACCEPTANCE_PILOT_CANDIDATE_DRIFT"
    return candidate, None


def _qualification_counts_complete(qualification: GlobalGeometryQualificationReport) -> bool:
    return bool(
        qualification.replay_expected_source_count > 0
        and qualification.replay_expected_source_count
        == qualification.replay_evaluated_source_count
        and qualification.regression_expected_source_count > 0
        and qualification.regression_expected_source_count
        == qualification.regression_evaluated_source_count
        and qualification.transfer_expected_source_count > 0
        and qualification.transfer_expected_source_count
        == qualification.transfer_evaluated_source_count
    )


def _evaluate_sources(
    manifest: ShapeGeometryCorpusManifest,
    profile: ShapeGeometryV2PreflightProfile,
    truth: Sequence[ShapeGeometryAcceptanceTruth],
) -> tuple[ShapeGeometryAcceptanceSourceResult, ...]:
    sources = {source.source_id: source for source in manifest.sources}
    expected_ids = tuple(sorted(sources))
    truth_ids = tuple(sorted(item.source_id for item in truth))
    if expected_ids != truth_ids:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_SOURCE_SET_MISMATCH",
            "Acceptance truth must cover exactly the frozen acceptance sources.",
        )
    truth_by_id = {item.source_id: item for item in truth}
    results: list[ShapeGeometryAcceptanceSourceResult] = []
    for source_id in expected_ids:
        source = sources[source_id]
        expected = truth_by_id[source_id]
        if expected.source_checksum_sha256 != source.source_checksum_sha256:
            _fail(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_TRUTH_SOURCE_CHECKSUM_MISMATCH",
                "Acceptance truth source checksum differs from the manifest.",
            )
        image_path = manifest.resolve_source_path(source)
        try:
            encoded = image_path.read_bytes()
        except OSError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_CORPUS_SOURCE_UNAVAILABLE", "Acceptance source cannot be read."
            ) from error
        if hashlib.sha256(encoded).hexdigest() != source.source_checksum_sha256:
            _fail(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_SOURCE_DRIFT",
                "Acceptance bytes differ from the frozen source checksum.",
            )
        decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
        if decoded is None:
            _fail(
                "SHAPE_GEOMETRY_V2_ACCEPTANCE_IMAGE_UNREADABLE",
                "Acceptance source cannot be decoded as an image.",
            )
        assert decoded is not None
        rgb = cast(NDArray[np.uint8], cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB))
        actual = verify_shape_geometry_v2_profile(rgb, profile)
        results.append(
            ShapeGeometryAcceptanceSourceResult(
                source_id=source.source_id,
                source_checksum_sha256=source.source_checksum_sha256,
                expected_verdict=expected.expected_verdict,
                expected_reason_code=expected.expected_reason_code,
                actual_verdict=actual.verdict,
                actual_reason_code=actual.reason_code,
                actual_verification_checksum_sha256=_fingerprint(actual.to_payload()),
            )
        )
    return tuple(results)


def _rejected(
    input_fingerprint: str,
    reason_codes: Sequence[str],
    split_boundary: dict[str, object] | None = None,
) -> ShapeGeometryAcceptanceResult:
    return ShapeGeometryAcceptanceResult(
        status=ShapeGeometryAcceptanceStatus.REJECTED,
        input_fingerprint=input_fingerprint,
        reason_codes=tuple(sorted(set(reason_codes))),
        split_boundary=split_boundary,
        source_results=(),
        acceptance_snapshot_checksum_sha256=None,
    )


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    decoded = json.loads(
        json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    )
    if not isinstance(decoded, dict):  # pragma: no cover - Mapping input guarantees this
        raise AssertionError("JSON mapping did not decode to an object.")
    return cast(dict[str, object], decoded)


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", f"{name} must be positive.")
    return cast(int, value)


def _require_checksum(value: object, name: str) -> str:
    if not isinstance(value, str) or _CHECKSUM.fullmatch(value) is None:
        _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", f"{name} must be SHA-256.")
    return cast(str, value)


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", f"{name} must be an object.")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", f"{name} must be an array.")
    return cast(Sequence[object], value)


def _require_exact_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        _fail("SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_INVALID", f"{name} fields are invalid.")


def _fail(code: str, message: str) -> None:
    raise ShapeGeometryAcceptanceError(code, message)


__all__ = [
    "SHAPE_GEOMETRY_V2_ACCEPTANCE_INPUT_VERSION",
    "SHAPE_GEOMETRY_V2_ACCEPTANCE_REPORT_VERSION",
    "ShapeGeometryAcceptanceError",
    "ShapeGeometryAcceptanceInput",
    "ShapeGeometryAcceptanceResult",
    "ShapeGeometryAcceptanceSourceResult",
    "ShapeGeometryAcceptanceStatus",
    "ShapeGeometryAcceptanceTruth",
    "load_shape_geometry_v2_acceptance_input",
    "require_matching_shape_geometry_v2_acceptance",
    "run_shape_geometry_v2_acceptance",
]
