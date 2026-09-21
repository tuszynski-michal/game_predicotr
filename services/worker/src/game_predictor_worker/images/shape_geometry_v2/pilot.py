"""Deterministic, local-only G05 pilot for shared shape geometry v2.

The pilot binds operator-owned corpus artifacts and reviewed observations.  It
never imports game data, accepts geometry automatically, or opens a database.
Only its descriptor-only candidate and G07 report can cross the application
boundary through the dedicated application service.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from game_predictor_api.domain.global_geometry_library import (
    SUPPORTED_GEOMETRY_FAMILY,
    GlobalGeometryCandidate,
    GlobalGeometryLibraryError,
    GlobalGeometryTopology,
    build_global_geometry_candidate,
)
from game_predictor_api.domain.global_geometry_qualification import (
    GlobalGeometryQualificationReport,
    build_global_geometry_qualification_report,
)

from .corpus import (
    CorpusRole,
    CorpusSplit,
    CorpusVisibility,
    ManualPageState,
    ShapeGeometryCorpusManifest,
    ShapeGeometryCorpusSource,
    ShapeGeometryFrozenInventory,
    ShapeGeometryManualAnnotation,
    ShapeGeometryManualAnnotations,
    canonical_json_bytes,
)

SHAPE_GEOMETRY_V2_PILOT_INPUT_VERSION = 1
SHAPE_GEOMETRY_V2_PILOT_REPORT_VERSION = "shape-geometry-v2-pilot-report-v1"

_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")
_GAME_REF = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")
_SOURCE_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}$")
_ALLOWED_SPLITS = frozenset({CorpusSplit.DEVELOPMENT, CorpusSplit.CALIBRATION})
_ALLOWED_ROLES = frozenset({CorpusRole.MEASUREMENT, CorpusRole.ANCHOR_POOL})


class ShapeGeometryPilotError(ValueError):
    """Stable validation error for a malformed local pilot artifact."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ShapeGeometryPilotPhase(StrEnum):
    MUMMIES_CORRECTION = "mummies_correction"
    MUMMIES_REPLAY = "mummies_replay"
    REGRESSION_BASELINE = "regression_baseline"
    REGRESSION_CANDIDATE = "regression_candidate"
    TRANSFER = "transfer"


class ShapeGeometryPilotOutcome(StrEnum):
    AUTOMATIC_CORRECT = "automatic_correct"
    AUTOMATIC_INCORRECT = "automatic_incorrect"
    REVIEW_REQUIRED = "review_required"
    CORRECTION_REQUIRED = "correction_required"
    CONFIRMATION_ONLY = "confirmation_only"


@dataclass(frozen=True, slots=True)
class ShapeGeometryPilotObservation:
    source_id: str
    source_checksum_sha256: str
    profile_checksum_sha256: str
    phase: ShapeGeometryPilotPhase
    outcome: ShapeGeometryPilotOutcome
    active_operator_seconds: int
    correction_accepted: bool

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryPilotObservation:
        _require_exact_keys(
            raw,
            {
                "sourceId",
                "sourceChecksumSha256",
                "profileChecksumSha256",
                "phase",
                "outcome",
                "activeOperatorSeconds",
                "correctionAccepted",
            },
            "pilot observation",
        )
        source_id = raw["sourceId"]
        if not isinstance(source_id, str) or _SOURCE_ID.fullmatch(source_id) is None:
            _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", "Pilot observation sourceId is invalid.")
        checksum = _require_checksum(raw["sourceChecksumSha256"], "pilot observation checksum")
        profile_checksum = _require_checksum(
            raw["profileChecksumSha256"], "pilot observation profile checksum"
        )
        try:
            phase = ShapeGeometryPilotPhase(cast(str, raw["phase"]))
            outcome = ShapeGeometryPilotOutcome(cast(str, raw["outcome"]))
        except ValueError as error:
            raise ShapeGeometryPilotError(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID", "Pilot observation phase or outcome is invalid."
            ) from error
        active_operator_seconds = raw["activeOperatorSeconds"]
        if type(active_operator_seconds) is not int or active_operator_seconds < 0:
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID",
                "Pilot observation activeOperatorSeconds must be a non-negative integer.",
            )
        accepted = raw["correctionAccepted"]
        if type(accepted) is not bool:
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID",
                "Pilot observation correctionAccepted must be boolean.",
            )
        if phase is not ShapeGeometryPilotPhase.MUMMIES_CORRECTION and accepted:
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID",
                "Only a Mummies correction observation can be accepted as a correction.",
            )
        return cls(
            source_id=cast(str, source_id),
            source_checksum_sha256=checksum,
            profile_checksum_sha256=profile_checksum,
            phase=phase,
            outcome=outcome,
            active_operator_seconds=cast(int, active_operator_seconds),
            correction_accepted=cast(bool, accepted),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "activeOperatorSeconds": self.active_operator_seconds,
            "correctionAccepted": self.correction_accepted,
            "outcome": self.outcome.value,
            "phase": self.phase.value,
            "profileChecksumSha256": self.profile_checksum_sha256,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryPilotInput:
    corpus_manifest_fingerprint: str
    inventory_fingerprint: str
    annotation_fingerprint: str
    baseline_active_profile_checksum_sha256: str | None
    baseline_contributor_game_refs: tuple[str, ...]
    correction_game_ref: str
    transfer_target_game_ref: str
    candidate_payload: dict[str, object] | None
    observations: tuple[ShapeGeometryPilotObservation, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryPilotInput:
        _require_exact_keys(
            raw,
            {
                "schemaVersion",
                "corpusManifestFingerprint",
                "inventoryFingerprint",
                "annotationFingerprint",
                "baselineActiveProfileChecksumSha256",
                "baselineContributorGameRefs",
                "correctionGameRef",
                "transferTargetGameRef",
                "candidate",
                "observations",
            },
            "pilot input",
        )
        if raw["schemaVersion"] != SHAPE_GEOMETRY_V2_PILOT_INPUT_VERSION:
            _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", "Pilot input schema version is unsupported.")
        baseline = raw["baselineActiveProfileChecksumSha256"]
        if baseline is not None:
            baseline = _require_checksum(baseline, "pilot baseline checksum")
        baseline_contributors = tuple(
            sorted(
                _require_game_ref(value, "baselineContributorGameRefs item")
                for value in _require_sequence(
                    raw["baselineContributorGameRefs"], "baselineContributorGameRefs"
                )
            )
        )
        if not baseline_contributors or len(set(baseline_contributors)) != len(
            baseline_contributors
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID",
                "baselineContributorGameRefs must be a non-empty unique list.",
            )
        correction_game_ref = _require_game_ref(raw["correctionGameRef"], "correctionGameRef")
        transfer_target_game_ref = _require_game_ref(
            raw["transferTargetGameRef"], "transferTargetGameRef"
        )
        if correction_game_ref == transfer_target_game_ref:
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_INVALID",
                "Pilot correction and transfer games must be different.",
            )
        candidate = raw["candidate"]
        if candidate is not None and not isinstance(candidate, Mapping):
            _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", "Pilot candidate must be an object or null.")
        observations = tuple(
            ShapeGeometryPilotObservation.from_mapping(_require_mapping(value, "pilot observation"))
            for value in _require_sequence(raw["observations"], "pilot observations")
        )
        keys = tuple((value.phase.value, value.source_id) for value in observations)
        if len(set(keys)) != len(keys):
            _fail(
                "SHAPE_GEOMETRY_V2_PILOT_OBSERVATION_DUPLICATE",
                "A source may occur once in each pilot phase.",
            )
        return cls(
            corpus_manifest_fingerprint=_require_checksum(
                raw["corpusManifestFingerprint"], "pilot corpus manifest fingerprint"
            ),
            inventory_fingerprint=_require_checksum(
                raw["inventoryFingerprint"], "pilot inventory fingerprint"
            ),
            annotation_fingerprint=_require_checksum(
                raw["annotationFingerprint"], "pilot annotation fingerprint"
            ),
            baseline_active_profile_checksum_sha256=baseline,
            baseline_contributor_game_refs=baseline_contributors,
            correction_game_ref=correction_game_ref,
            transfer_target_game_ref=transfer_target_game_ref,
            candidate_payload=(
                None
                if candidate is None
                else _json_object(_require_mapping(candidate, "pilot candidate"))
            ),
            observations=observations,
        )

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "annotationFingerprint": self.annotation_fingerprint,
                "baselineActiveProfileChecksumSha256": self.baseline_active_profile_checksum_sha256,
                "baselineContributorGameRefs": list(self.baseline_contributor_game_refs),
                "candidate": self.candidate_payload,
                "corpusManifestFingerprint": self.corpus_manifest_fingerprint,
                "correctionGameRef": self.correction_game_ref,
                "inventoryFingerprint": self.inventory_fingerprint,
                "observations": [
                    observation.as_dict()
                    for observation in sorted(
                        self.observations, key=lambda value: (value.phase.value, value.source_id)
                    )
                ],
                "schemaVersion": SHAPE_GEOMETRY_V2_PILOT_INPUT_VERSION,
                "transferTargetGameRef": self.transfer_target_game_ref,
            }
        )


@dataclass(frozen=True, slots=True)
class ShapeGeometryPilotPhaseMetrics:
    phase: ShapeGeometryPilotPhase
    expected_source_ids: tuple[str, ...]
    evaluated_source_ids: tuple[str, ...]
    automatic_correct_source_count: int
    automatic_incorrect_source_count: int
    review_required_source_count: int
    correction_required_source_count: int
    confirmation_only_source_count: int
    operator_active_seconds: int
    reason_codes: tuple[str, ...]

    @property
    def status(self) -> str:
        return "not_evaluable" if self.reason_codes else "measured"

    def as_dict(self) -> dict[str, object]:
        return {
            "automaticCorrectSourceCount": self.automatic_correct_source_count,
            "automaticIncorrectSourceCount": self.automatic_incorrect_source_count,
            "automaticSourceCount": (
                self.automatic_correct_source_count
                + self.automatic_incorrect_source_count
                + self.confirmation_only_source_count
            ),
            "confirmationOnlySourceCount": self.confirmation_only_source_count,
            "correctionRequiredSourceCount": self.correction_required_source_count,
            "evaluatedSourceCount": len(self.evaluated_source_ids),
            "evaluatedSourceIds": list(self.evaluated_source_ids),
            "expectedSourceCount": len(self.expected_source_ids),
            "expectedSourceIds": list(self.expected_source_ids),
            "operatorActiveSeconds": self.operator_active_seconds,
            "phase": self.phase.value,
            "reasonCodes": list(self.reason_codes),
            "reviewRequiredSourceCount": self.review_required_source_count,
            "status": self.status,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryPilotResult:
    input_fingerprint: str
    status: str
    reason_codes: tuple[str, ...]
    phases: tuple[ShapeGeometryPilotPhaseMetrics, ...]
    candidate: GlobalGeometryCandidate | None
    qualification_report: GlobalGeometryQualificationReport | None
    work_reduction: dict[str, int] | None

    def publication_inputs(
        self,
    ) -> tuple[GlobalGeometryCandidate, GlobalGeometryQualificationReport]:
        """Return the only inputs allowed to cross into the write boundary."""

        if self.status != "measured" or self.candidate is None or self.qualification_report is None:
            raise ShapeGeometryPilotError(
                "SHAPE_GEOMETRY_V2_PILOT_PUBLICATION_BLOCKED",
                "Only a complete, measured pilot may be sent to the global control plane.",
            )
        return self.candidate, self.qualification_report

    def as_dict(self) -> dict[str, object]:
        return {
            "candidate": None if self.candidate is None else _candidate_as_dict(self.candidate),
            "inputFingerprint": self.input_fingerprint,
            "phases": [phase.as_dict() for phase in self.phases],
            "qualificationReport": (
                None if self.qualification_report is None else self.qualification_report.as_dict()
            ),
            "reasonCodes": list(self.reason_codes),
            "schemaVersion": SHAPE_GEOMETRY_V2_PILOT_REPORT_VERSION,
            "status": self.status,
            "workReduction": self.work_reduction,
        }


def load_shape_geometry_pilot_input(path: Path) -> ShapeGeometryPilotInput:
    """Load a local pilot input without opening a database or importing game data."""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ShapeGeometryPilotError(
            "SHAPE_GEOMETRY_V2_PILOT_UNREADABLE", "Pilot input cannot be read."
        ) from error
    return ShapeGeometryPilotInput.from_mapping(_require_mapping(raw, "pilot input"))


def run_shape_geometry_pilot(
    manifest: ShapeGeometryCorpusManifest,
    inventory: ShapeGeometryFrozenInventory,
    annotations: ShapeGeometryManualAnnotations,
    pilot: ShapeGeometryPilotInput,
) -> ShapeGeometryPilotResult:
    """Evaluate an ordered local pilot and prepare safe G06/G07 inputs.

    A missing phase remains an auditable ``not_evaluable`` result. It never
    becomes an automatic success and does not cause this runner to write data.
    """

    _require_executor_inputs(manifest, inventory, annotations, pilot)
    sources = {source.source_id: source for source in manifest.sources}
    annotations_by_source = {
        annotation.source_id: annotation for annotation in annotations.annotations
    }
    grouped: dict[ShapeGeometryPilotPhase, list[ShapeGeometryPilotObservation]] = defaultdict(list)
    for observation in pilot.observations:
        grouped[observation.phase].append(observation)

    all_reasons: set[str] = set()
    candidate = _parse_candidate(pilot, all_reasons)
    candidate_checksum = None if candidate is None else candidate.profile_checksum_sha256
    correction_sources = _eligible_sources(manifest, pilot.correction_game_ref)
    transfer_sources = _eligible_sources(manifest, pilot.transfer_target_game_ref)
    regression_sources = _eligible_sources_for_games(manifest, pilot.baseline_contributor_game_refs)
    if any(
        not _eligible_sources(manifest, game_ref)
        for game_ref in pilot.baseline_contributor_game_refs
    ):
        all_reasons.add("PILOT_REGRESSION_CONTRIBUTOR_SOURCES_MISSING")

    correction = _measure_phase(
        ShapeGeometryPilotPhase.MUMMIES_CORRECTION,
        grouped[ShapeGeometryPilotPhase.MUMMIES_CORRECTION],
        expected_sources=(),
        required_game_ref=pilot.correction_game_ref,
        required_profile_checksum=candidate_checksum,
        sources=sources,
        annotations_by_source=annotations_by_source,
        require_accepted_correction=True,
    )
    replay = _measure_phase(
        ShapeGeometryPilotPhase.MUMMIES_REPLAY,
        grouped[ShapeGeometryPilotPhase.MUMMIES_REPLAY],
        expected_sources=correction_sources,
        required_game_ref=pilot.correction_game_ref,
        required_profile_checksum=candidate_checksum,
        sources=sources,
        annotations_by_source=annotations_by_source,
    )
    regression_baseline = _measure_phase(
        ShapeGeometryPilotPhase.REGRESSION_BASELINE,
        grouped[ShapeGeometryPilotPhase.REGRESSION_BASELINE],
        expected_sources=regression_sources,
        required_game_ref=None,
        required_profile_checksum=pilot.baseline_active_profile_checksum_sha256,
        sources=sources,
        annotations_by_source=annotations_by_source,
    )
    regression_candidate = _measure_phase(
        ShapeGeometryPilotPhase.REGRESSION_CANDIDATE,
        grouped[ShapeGeometryPilotPhase.REGRESSION_CANDIDATE],
        expected_sources=regression_sources,
        required_game_ref=None,
        required_profile_checksum=candidate_checksum,
        sources=sources,
        annotations_by_source=annotations_by_source,
    )
    transfer = _measure_phase(
        ShapeGeometryPilotPhase.TRANSFER,
        grouped[ShapeGeometryPilotPhase.TRANSFER],
        expected_sources=transfer_sources,
        required_game_ref=pilot.transfer_target_game_ref,
        required_profile_checksum=candidate_checksum,
        sources=sources,
        annotations_by_source=annotations_by_source,
    )
    phases = (correction, replay, regression_baseline, regression_candidate, transfer)
    for phase in phases:
        all_reasons.update(phase.reason_codes)
    if pilot.baseline_active_profile_checksum_sha256 is None:
        all_reasons.add("PILOT_BASELINE_PROFILE_MISSING")
    if regression_baseline.evaluated_source_ids != regression_candidate.evaluated_source_ids:
        all_reasons.add("PILOT_REGRESSION_COHORT_MISMATCH")
    if correction.reason_codes:
        all_reasons.add("PILOT_CANDIDATE_CORRECTION_UNAVAILABLE")
        candidate = None
    if candidate is not None and pilot.transfer_target_game_ref in {
        evidence.source_game_ref for evidence in candidate.evidence
    }:
        all_reasons.add("PILOT_TRANSFER_TARGET_CONTRIBUTOR_LEAKAGE")
        candidate = None

    report = None
    if candidate is not None and pilot.baseline_active_profile_checksum_sha256 is not None:
        report = build_global_geometry_qualification_report(
            candidate_profile_checksum_sha256=candidate.profile_checksum_sha256,
            baseline_active_profile_checksum_sha256=pilot.baseline_active_profile_checksum_sha256,
            replay_snapshot_checksum_sha256=_phase_snapshot_checksum(
                pilot, replay, grouped[ShapeGeometryPilotPhase.MUMMIES_REPLAY]
            ),
            regression_snapshot_checksum_sha256=_regression_snapshot_checksum(
                pilot,
                regression_baseline,
                grouped[ShapeGeometryPilotPhase.REGRESSION_BASELINE],
                regression_candidate,
                grouped[ShapeGeometryPilotPhase.REGRESSION_CANDIDATE],
            ),
            transfer_snapshot_checksum_sha256=_phase_snapshot_checksum(
                pilot, transfer, grouped[ShapeGeometryPilotPhase.TRANSFER]
            ),
            contributor_game_refs=tuple(
                sorted({evidence.source_game_ref for evidence in candidate.evidence})
            ),
            transfer_target_game_ref=pilot.transfer_target_game_ref,
            replay_expected_source_count=len(replay.expected_source_ids),
            replay_evaluated_source_count=len(replay.evaluated_source_ids),
            replay_automatic_incorrect_source_count=replay.automatic_incorrect_source_count,
            regression_expected_source_count=len(regression_baseline.expected_source_ids),
            regression_evaluated_source_count=len(regression_candidate.evaluated_source_ids),
            regression_baseline_automatic_incorrect_source_count=(
                regression_baseline.automatic_incorrect_source_count
            ),
            regression_candidate_automatic_incorrect_source_count=(
                regression_candidate.automatic_incorrect_source_count
            ),
            transfer_expected_source_count=len(transfer.expected_source_ids),
            transfer_evaluated_source_count=len(transfer.evaluated_source_ids),
            transfer_automatic_incorrect_source_count=transfer.automatic_incorrect_source_count,
        )
    if candidate is None:
        all_reasons.add("PILOT_CANDIDATE_UNAVAILABLE")
    work_reduction = _work_reduction(regression_baseline, regression_candidate)
    return ShapeGeometryPilotResult(
        input_fingerprint=pilot.fingerprint(),
        status="not_evaluable" if all_reasons else "measured",
        reason_codes=tuple(sorted(all_reasons)),
        phases=phases,
        candidate=candidate,
        qualification_report=report,
        work_reduction=work_reduction,
    )


def require_matching_shape_geometry_pilot(
    saved_report: Mapping[str, object], current_report: ShapeGeometryPilotResult
) -> None:
    """Fail closed when replaying the same input gives another report."""

    if canonical_json_bytes(saved_report) != canonical_json_bytes(current_report.as_dict()):
        _fail(
            "SHAPE_GEOMETRY_V2_PILOT_DRIFT",
            "Pilot output differs from the checksum-bound saved report.",
        )


def _require_executor_inputs(
    manifest: ShapeGeometryCorpusManifest,
    inventory: ShapeGeometryFrozenInventory,
    annotations: ShapeGeometryManualAnnotations,
    pilot: ShapeGeometryPilotInput,
) -> None:
    if manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
            "The pilot cannot read an acceptance corpus.",
        )
    current = manifest.freeze_inventory()
    if canonical_json_bytes(current.as_dict()) != canonical_json_bytes(inventory.as_dict()):
        _fail("SHAPE_GEOMETRY_V2_INVENTORY_DRIFT", "Pilot inventory differs from the corpus.")
    if pilot.corpus_manifest_fingerprint != manifest.fingerprint():
        _fail("SHAPE_GEOMETRY_V2_PILOT_INPUT_DRIFT", "Pilot references another corpus manifest.")
    if pilot.inventory_fingerprint != inventory.fingerprint():
        _fail("SHAPE_GEOMETRY_V2_PILOT_INPUT_DRIFT", "Pilot references another inventory.")
    if pilot.annotation_fingerprint != annotations.fingerprint():
        _fail("SHAPE_GEOMETRY_V2_PILOT_INPUT_DRIFT", "Pilot references another annotation set.")


def _eligible_sources(
    manifest: ShapeGeometryCorpusManifest, game_ref: str
) -> tuple[ShapeGeometryCorpusSource, ...]:
    return tuple(
        sorted(
            (
                source
                for source in manifest.sources
                if source.game_id == game_ref
                and source.split in _ALLOWED_SPLITS
                and source.corpus_role in _ALLOWED_ROLES
            ),
            key=lambda source: (
                source.capture_family_id,
                source.source_ordinal,
                source.source_checksum_sha256,
                source.source_id,
            ),
        )
    )


def _eligible_sources_for_games(
    manifest: ShapeGeometryCorpusManifest, game_refs: Sequence[str]
) -> tuple[ShapeGeometryCorpusSource, ...]:
    sources = [source for game_ref in game_refs for source in _eligible_sources(manifest, game_ref)]
    return tuple(sorted(sources, key=lambda source: source.source_id))


def _measure_phase(
    phase: ShapeGeometryPilotPhase,
    observations: Sequence[ShapeGeometryPilotObservation],
    *,
    expected_sources: Sequence[ShapeGeometryCorpusSource],
    required_game_ref: str | None,
    required_profile_checksum: str | None,
    sources: Mapping[str, ShapeGeometryCorpusSource],
    annotations_by_source: Mapping[str, ShapeGeometryManualAnnotation],
    require_accepted_correction: bool = False,
) -> ShapeGeometryPilotPhaseMetrics:
    expected = tuple(expected_sources)
    expected_ids = tuple(value.source_id for value in expected)
    expected_by_id = {value.source_id: value for value in expected}
    reasons: set[str] = set()
    accepted_count = 0
    valid: list[ShapeGeometryPilotObservation] = []
    if required_profile_checksum is None:
        reasons.add("PILOT_PHASE_PROFILE_UNAVAILABLE")
    for observation in observations:
        source = sources.get(observation.source_id)
        if source is None:
            reasons.add("PILOT_SOURCE_MISSING")
            continue
        if source.source_checksum_sha256 != observation.source_checksum_sha256 or (
            required_game_ref is not None and source.game_id != required_game_ref
        ):
            reasons.add("PILOT_SOURCE_IDENTITY_MISMATCH")
            continue
        if required_profile_checksum is None:
            continue
        if observation.profile_checksum_sha256 != required_profile_checksum:
            reasons.add("PILOT_OBSERVATION_PROFILE_MISMATCH")
            continue
        if source.split not in _ALLOWED_SPLITS:
            reasons.add("PILOT_SOURCE_SPLIT_FORBIDDEN")
            continue
        if source.corpus_role not in _ALLOWED_ROLES:
            reasons.add("PILOT_SOURCE_ROLE_FORBIDDEN")
            continue
        annotation = annotations_by_source.get(observation.source_id)
        if annotation is None or not _annotation_is_complete(annotation):
            reasons.add("PILOT_SOURCE_ANNOTATION_INCOMPLETE")
            continue
        if expected_by_id and observation.source_id not in expected_by_id:
            reasons.add("PILOT_SOURCE_NOT_IN_PHASE_COHORT")
            continue
        if observation.correction_accepted:
            accepted_count += 1
        valid.append(observation)
    evaluated_ids = tuple(sorted(value.source_id for value in valid))
    if phase is not ShapeGeometryPilotPhase.MUMMIES_CORRECTION:
        if not expected_ids:
            reasons.add("PILOT_PHASE_SOURCES_MISSING")
        if set(evaluated_ids) != set(expected_ids):
            reasons.add("PILOT_PHASE_OBSERVATIONS_INCOMPLETE")
    elif not valid:
        reasons.add("PILOT_CORRECTION_MISSING")
    if require_accepted_correction and accepted_count < 1:
        reasons.add("PILOT_CORRECTION_NOT_ACCEPTED")
    return ShapeGeometryPilotPhaseMetrics(
        phase=phase,
        expected_source_ids=tuple(sorted(expected_ids)),
        evaluated_source_ids=evaluated_ids,
        automatic_correct_source_count=sum(
            value.outcome is ShapeGeometryPilotOutcome.AUTOMATIC_CORRECT for value in valid
        ),
        automatic_incorrect_source_count=sum(
            value.outcome is ShapeGeometryPilotOutcome.AUTOMATIC_INCORRECT for value in valid
        ),
        review_required_source_count=sum(
            value.outcome is ShapeGeometryPilotOutcome.REVIEW_REQUIRED for value in valid
        ),
        correction_required_source_count=sum(
            value.outcome is ShapeGeometryPilotOutcome.CORRECTION_REQUIRED for value in valid
        ),
        confirmation_only_source_count=sum(
            value.outcome is ShapeGeometryPilotOutcome.CONFIRMATION_ONLY for value in valid
        ),
        operator_active_seconds=sum(value.active_operator_seconds for value in valid),
        reason_codes=tuple(sorted(reasons)),
    )


def _work_reduction(
    baseline: ShapeGeometryPilotPhaseMetrics,
    candidate: ShapeGeometryPilotPhaseMetrics,
) -> dict[str, int] | None:
    if (
        baseline.reason_codes
        or candidate.reason_codes
        or not baseline.expected_source_ids
        or baseline.evaluated_source_ids != candidate.evaluated_source_ids
        or baseline.evaluated_source_ids != baseline.expected_source_ids
        or candidate.evaluated_source_ids != candidate.expected_source_ids
    ):
        return None
    return {
        "correctionRequiredSourceCountReduction": (
            baseline.correction_required_source_count - candidate.correction_required_source_count
        ),
        "operatorActiveSecondsReduction": (
            baseline.operator_active_seconds - candidate.operator_active_seconds
        ),
        "reviewRequiredSourceCountReduction": (
            baseline.review_required_source_count - candidate.review_required_source_count
        ),
    }


def _annotation_is_complete(annotation: ShapeGeometryManualAnnotation) -> bool:
    return (
        annotation.page_state is ManualPageState.COMPLETE
        and annotation.topology_confirmed
        and annotation.visible_grid
    )


def _parse_candidate(
    pilot: ShapeGeometryPilotInput, all_reasons: set[str]
) -> GlobalGeometryCandidate | None:
    if pilot.candidate_payload is None:
        all_reasons.add("PILOT_CANDIDATE_MISSING")
        return None
    try:
        raw = pilot.candidate_payload
        _require_exact_keys(
            raw,
            {
                "geometryFamily",
                "topology",
                "normalizedTemplate",
                "frameAppearance",
                "evidenceSummary",
                "evidence",
            },
            "pilot candidate",
        )
        geometry_family = raw["geometryFamily"]
        if geometry_family != SUPPORTED_GEOMETRY_FAMILY:
            _fail("SHAPE_GEOMETRY_V2_PILOT_CANDIDATE_INVALID", "Pilot geometry family is invalid.")
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
        raw_evidence = _require_sequence(raw["evidence"], "pilot candidate evidence")
        evidence: list[tuple[str, Mapping[str, object]]] = []
        for value in raw_evidence:
            item = _require_mapping(value, "pilot candidate evidence item")
            _require_exact_keys(
                item,
                {"sourceGameRef", "evidencePayload"},
                "pilot candidate evidence item",
            )
            source_game_ref = _require_game_ref(item["sourceGameRef"], "sourceGameRef")
            evidence.append(
                (source_game_ref, _require_mapping(item["evidencePayload"], "evidencePayload"))
            )
        candidate = build_global_geometry_candidate(
            geometry_family=cast(str, geometry_family),
            topology=topology,
            normalized_template=_require_mapping(raw["normalizedTemplate"], "normalizedTemplate"),
            frame_appearance=_require_mapping(raw["frameAppearance"], "frameAppearance"),
            evidence_summary=_require_mapping(raw["evidenceSummary"], "evidenceSummary"),
            evidence=evidence,
        )
    except GlobalGeometryLibraryError as error:
        raise ShapeGeometryPilotError(error.code, str(error)) from error
    contributor_refs = {value.source_game_ref for value in candidate.evidence}
    if contributor_refs != {pilot.correction_game_ref}:
        all_reasons.add("PILOT_CANDIDATE_CONTRIBUTOR_MISMATCH")
        return None
    return candidate


def _phase_snapshot_checksum(
    pilot: ShapeGeometryPilotInput,
    metrics: ShapeGeometryPilotPhaseMetrics,
    observations: Sequence[ShapeGeometryPilotObservation],
) -> str:
    return _fingerprint(
        {
            "annotationFingerprint": pilot.annotation_fingerprint,
            "corpusManifestFingerprint": pilot.corpus_manifest_fingerprint,
            "inventoryFingerprint": pilot.inventory_fingerprint,
            "metrics": metrics.as_dict(),
            "observations": [
                value.as_dict() for value in sorted(observations, key=lambda value: value.source_id)
            ],
            "phase": metrics.phase.value,
        }
    )


def _regression_snapshot_checksum(
    pilot: ShapeGeometryPilotInput,
    baseline: ShapeGeometryPilotPhaseMetrics,
    baseline_observations: Sequence[ShapeGeometryPilotObservation],
    candidate: ShapeGeometryPilotPhaseMetrics,
    candidate_observations: Sequence[ShapeGeometryPilotObservation],
) -> str:
    return _fingerprint(
        {
            "baseline": {
                "metrics": baseline.as_dict(),
                "observations": [
                    value.as_dict()
                    for value in sorted(baseline_observations, key=lambda value: value.source_id)
                ],
            },
            "baselineActiveProfileChecksumSha256": pilot.baseline_active_profile_checksum_sha256,
            "candidate": {
                "metrics": candidate.as_dict(),
                "observations": [
                    value.as_dict()
                    for value in sorted(candidate_observations, key=lambda value: value.source_id)
                ],
            },
            "corpusManifestFingerprint": pilot.corpus_manifest_fingerprint,
            "inventoryFingerprint": pilot.inventory_fingerprint,
            "phase": "regression",
        }
    )


def _candidate_as_dict(candidate: GlobalGeometryCandidate) -> dict[str, object]:
    return {
        "evidence": [
            {
                "evidenceChecksumSha256": value.evidence_checksum_sha256,
                "evidencePayload": _json_object(value.evidence_payload),
                "sourceGameRef": value.source_game_ref,
            }
            for value in candidate.evidence
        ],
        "evidenceSummary": _json_object(candidate.evidence_summary),
        "frameAppearance": _json_object(candidate.frame_appearance),
        "geometryFamily": candidate.geometry_family,
        "normalizedTemplate": _json_object(candidate.normalized_template),
        "profileChecksumSha256": candidate.profile_checksum_sha256,
        "topology": candidate.topology.to_dict(),
    }


def _json_object(value: Mapping[str, object]) -> dict[str, object]:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - guarded by Mapping input
        raise AssertionError("JSON mapping did not decode to an object")
    return cast(dict[str, object], decoded)


def _fingerprint(value: Mapping[str, object]) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _require_checksum(value: object, name: str) -> str:
    if not isinstance(value, str) or _CHECKSUM.fullmatch(value) is None:
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} must be a lowercase SHA-256 digest.")
    return cast(str, value)


def _require_game_ref(value: object, name: str) -> str:
    if not isinstance(value, str) or _GAME_REF.fullmatch(value) is None:
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} is invalid.")
    return cast(str, value)


def _require_positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} must be a positive integer.")
    return cast(int, value)


def _require_mapping(value: object, name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} must be an object.")
    return cast(Mapping[str, object], value)


def _require_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} must be an array.")
    return cast(Sequence[object], value)


def _require_exact_keys(value: Mapping[str, object], expected: set[str], name: str) -> None:
    if set(value) != expected:
        _fail("SHAPE_GEOMETRY_V2_PILOT_INVALID", f"{name} fields are invalid.")


def _fail(code: str, message: str) -> None:
    raise ShapeGeometryPilotError(code, message)


__all__ = [
    "SHAPE_GEOMETRY_V2_PILOT_INPUT_VERSION",
    "SHAPE_GEOMETRY_V2_PILOT_REPORT_VERSION",
    "ShapeGeometryPilotError",
    "ShapeGeometryPilotInput",
    "ShapeGeometryPilotObservation",
    "ShapeGeometryPilotOutcome",
    "ShapeGeometryPilotPhase",
    "ShapeGeometryPilotPhaseMetrics",
    "ShapeGeometryPilotResult",
    "load_shape_geometry_pilot_input",
    "require_matching_shape_geometry_pilot",
    "run_shape_geometry_pilot",
]
