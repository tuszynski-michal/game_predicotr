"""Deterministic, read-only G01 experiment reports for shape geometry v2.

The runner records externally reviewed observations.  It deliberately does not
call a geometry detector: G02 owns the detector while G01 owns the frozen
corpus, provenance, denominators, and transfer-isolation contract.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from .corpus import (
    CorpusRole,
    CorpusVisibility,
    ShapeGeometryCorpusError,
    ShapeGeometryCorpusManifest,
    ShapeGeometryFrozenInventory,
    ShapeGeometryManualAnnotations,
    _fail,
    _fingerprint,
    _require_exact_keys,
    _require_identifier,
    _require_mapping,
    _require_sequence,
    _require_sha256,
    canonical_json_bytes,
    select_v2_anchors,
)

SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_VERSION = 1
SHAPE_GEOMETRY_V2_EXPERIMENT_REPORT_VERSION = "shape-geometry-v2-experiment-v1"


class ShapeGeometryExperimentVariant(StrEnum):
    SHAPE_CONTRAST = "shape_contrast_v1"
    SHAPE_CONTRAST_COLOR_ASSIST = "shape_contrast_color_assist_v1"
    SHAPE_CONTRAST_LOCAL_ANCHOR = "shape_contrast_local_anchor_v1"
    SHAPE_CONTRAST_SHARED_PROFILE = "shape_contrast_shared_profile_v1"


class ShapeGeometryExperimentOutcome(StrEnum):
    AUTOMATIC_CORRECT = "automatic_correct"
    AUTOMATIC_INCORRECT = "automatic_incorrect"
    REVIEW_REQUIRED = "review_required"
    CORRECTION_REQUIRED = "correction_required"
    CONFIRMATION_ONLY = "confirmation_only"


@dataclass(frozen=True, slots=True)
class ShapeGeometryExperimentObservation:
    game_id: str
    source_id: str
    source_checksum_sha256: str
    variant: ShapeGeometryExperimentVariant
    outcome: ShapeGeometryExperimentOutcome
    active_operator_seconds: int
    profile_contributor_game_ids: tuple[str, ...]
    profile_fingerprint: str | None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryExperimentObservation:
        _require_exact_keys(
            raw,
            {
                "gameId",
                "sourceId",
                "sourceChecksumSha256",
                "variant",
                "outcome",
                "activeOperatorSeconds",
                "profileContributorGameIds",
                "profileFingerprint",
            },
            "experiment observation",
        )
        try:
            variant = ShapeGeometryExperimentVariant(cast(str, raw["variant"]))
            outcome = ShapeGeometryExperimentOutcome(cast(str, raw["outcome"]))
        except ValueError as error:
            raise ShapeGeometryCorpusError(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID",
                "Experiment observation variant or outcome is invalid.",
            ) from error
        seconds = raw["activeOperatorSeconds"]
        if type(seconds) is not int or seconds < 0:
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID",
                "Experiment activeOperatorSeconds must be a non-negative integer.",
            )
        contributors = tuple(
            sorted(
                _require_identifier(value, "profileContributorGameIds item")
                for value in _require_sequence(
                    raw["profileContributorGameIds"], "profileContributorGameIds"
                )
            )
        )
        if len(set(contributors)) != len(contributors):
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID",
                "Experiment profile contributor game IDs are duplicated.",
            )
        profile_fingerprint = raw["profileFingerprint"]
        if profile_fingerprint is not None:
            profile_fingerprint = _require_sha256(
                profile_fingerprint, "experiment profileFingerprint"
            )
        if variant is ShapeGeometryExperimentVariant.SHAPE_CONTRAST_SHARED_PROFILE:
            if not contributors or profile_fingerprint is None:
                _fail(
                    "SHAPE_GEOMETRY_V2_SHARED_PROFILE_PROVENANCE_INVALID",
                    "A shared-profile observation requires contributors and a profile fingerprint.",
                )
        elif contributors or profile_fingerprint is not None:
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID",
                "Only a shared-profile observation may declare profile provenance.",
            )
        source_id = raw["sourceId"]
        if not isinstance(source_id, str):
            _fail("SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID", "Experiment sourceId is invalid.")
        return cls(
            game_id=_require_identifier(raw["gameId"], "experiment gameId"),
            source_id=source_id,
            source_checksum_sha256=_require_sha256(
                raw["sourceChecksumSha256"], "experiment sourceChecksumSha256"
            ),
            variant=variant,
            outcome=outcome,
            active_operator_seconds=seconds,
            profile_contributor_game_ids=contributors,
            profile_fingerprint=profile_fingerprint,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "activeOperatorSeconds": self.active_operator_seconds,
            "gameId": self.game_id,
            "outcome": self.outcome.value,
            "profileContributorGameIds": list(self.profile_contributor_game_ids),
            "profileFingerprint": self.profile_fingerprint,
            "sourceChecksumSha256": self.source_checksum_sha256,
            "sourceId": self.source_id,
            "variant": self.variant.value,
        }


@dataclass(frozen=True, slots=True)
class ShapeGeometryExperimentObservations:
    corpus_manifest_fingerprint: str
    inventory_fingerprint: str
    annotation_fingerprint: str
    algorithm: Mapping[str, object]
    observations: tuple[ShapeGeometryExperimentObservation, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> ShapeGeometryExperimentObservations:
        _require_exact_keys(
            raw,
            {
                "schemaVersion",
                "corpusManifestFingerprint",
                "inventoryFingerprint",
                "annotationFingerprint",
                "algorithm",
                "observations",
            },
            "experiment observations",
        )
        if raw["schemaVersion"] != SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_VERSION:
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_INVALID",
                "Experiment observation document version is unsupported.",
            )
        algorithm = _require_mapping(raw["algorithm"], "experiment algorithm")
        _require_exact_keys(
            algorithm,
            {"algorithmId", "algorithmVersion", "parameters"},
            "experiment algorithm",
        )
        _require_identifier(algorithm["algorithmId"], "experiment algorithmId")
        _require_identifier(algorithm["algorithmVersion"], "experiment algorithmVersion")
        _require_mapping(algorithm["parameters"], "experiment algorithm parameters")
        observations = tuple(
            ShapeGeometryExperimentObservation.from_mapping(
                _require_mapping(item, "experiment observation")
            )
            for item in _require_sequence(raw["observations"], "experiment observations")
        )
        keys = tuple(
            (observation.source_id, observation.variant.value) for observation in observations
        )
        if len(set(keys)) != len(keys):
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_OBSERVATION_DUPLICATE",
                "Each source and experiment variant may occur only once.",
            )
        return cls(
            corpus_manifest_fingerprint=_require_sha256(
                raw["corpusManifestFingerprint"], "experiment corpusManifestFingerprint"
            ),
            inventory_fingerprint=_require_sha256(
                raw["inventoryFingerprint"], "experiment inventoryFingerprint"
            ),
            annotation_fingerprint=_require_sha256(
                raw["annotationFingerprint"], "experiment annotationFingerprint"
            ),
            algorithm=dict(algorithm),
            observations=observations,
        )

    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "algorithm": dict(self.algorithm),
                "annotationFingerprint": self.annotation_fingerprint,
                "corpusManifestFingerprint": self.corpus_manifest_fingerprint,
                "inventoryFingerprint": self.inventory_fingerprint,
                "observations": [
                    observation.as_dict()
                    for observation in sorted(
                        self.observations,
                        key=lambda value: (value.game_id, value.source_id, value.variant.value),
                    )
                ],
                "schemaVersion": SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_VERSION,
            }
        )


def load_shape_geometry_experiment_observations(
    path: Path,
) -> ShapeGeometryExperimentObservations:
    """Load observations only after the caller has admitted an executor corpus."""

    from json import JSONDecodeError, loads
    try:
        raw = loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError) as error:
        raise ShapeGeometryCorpusError(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_UNREADABLE",
            "Experiment observations cannot be read.",
        ) from error
    return ShapeGeometryExperimentObservations.from_mapping(
        _require_mapping(raw, "experiment observations")
    )


def run_shape_geometry_experiment(
    manifest: ShapeGeometryCorpusManifest,
    inventory: ShapeGeometryFrozenInventory,
    annotations: ShapeGeometryManualAnnotations,
    observations: ShapeGeometryExperimentObservations,
) -> dict[str, object]:
    """Report G01 outcomes without importing images, jobs, or application data."""

    if manifest.visibility is not CorpusVisibility.EXECUTOR:
        _fail(
            "SHAPE_GEOMETRY_V2_ACCEPTANCE_VISIBILITY_FORBIDDEN",
            "Shape geometry experiment cannot read an acceptance corpus.",
        )
    current_inventory = manifest.freeze_inventory()
    if canonical_json_bytes(inventory.as_dict()) != canonical_json_bytes(
        current_inventory.as_dict()
    ):
        _fail(
            "SHAPE_GEOMETRY_V2_INVENTORY_DRIFT",
            "Experiment inventory differs from the current manifest or corpus sources.",
        )
    if observations.corpus_manifest_fingerprint != manifest.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_DRIFT",
            "Experiment observations reference another corpus manifest.",
        )
    if observations.inventory_fingerprint != inventory.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_DRIFT",
            "Experiment observations reference another frozen inventory.",
        )
    if observations.annotation_fingerprint != annotations.fingerprint():
        _fail(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_DRIFT",
            "Experiment observations reference another annotation document.",
        )

    sources_by_id = {source.source_id: source for source in manifest.sources}
    annotations_by_source = {
        annotation.source_id: annotation for annotation in annotations.annotations
    }
    observations_by_game_variant: dict[
        tuple[str, ShapeGeometryExperimentVariant],
        list[ShapeGeometryExperimentObservation],
    ] = defaultdict(list)
    for observation in observations.observations:
        source = sources_by_id.get(observation.source_id)
        if (
            source is None
            or source.game_id != observation.game_id
            or source.source_checksum_sha256 != observation.source_checksum_sha256
            or source.corpus_role is not CorpusRole.MEASUREMENT
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_EXPERIMENT_SOURCE_INVALID",
                "An experiment observation does not match a measurement corpus source.",
            )
        if (
            observation.variant
            is ShapeGeometryExperimentVariant.SHAPE_CONTRAST_SHARED_PROFILE
            and observation.game_id in observation.profile_contributor_game_ids
        ):
            _fail(
                "SHAPE_GEOMETRY_V2_SHARED_PROFILE_TARGET_LEAKAGE",
                "A shared profile cannot contain contributions from its evaluated game.",
            )
        observations_by_game_variant[(observation.game_id, observation.variant)].append(
            observation
        )

    anchor_selection = select_v2_anchors(manifest, annotations)
    anchors_by_game = {
        cast(str, game["gameId"]): game["anchor"]
        for game in cast(Sequence[Mapping[str, object]], anchor_selection["games"])
    }
    games: list[dict[str, object]] = []
    for game in sorted(manifest.games, key=lambda value: value.game_id):
        expected = sorted(
            (
                source
                for source in manifest.sources
                if source.game_id == game.game_id
                and source.corpus_role is CorpusRole.MEASUREMENT
            ),
            key=lambda value: (
                value.capture_family_id,
                value.source_ordinal,
                value.source_checksum_sha256,
                value.source_id,
            ),
        )
        expected_ids = {source.source_id for source in expected}
        variants: list[dict[str, object]] = []
        for variant in ShapeGeometryExperimentVariant:
            evaluated = sorted(
                observations_by_game_variant[(game.game_id, variant)],
                key=lambda value: value.source_id,
            )
            evaluated_ids = {value.source_id for value in evaluated}
            reasons: list[str] = []
            if not expected:
                reasons.append("MEASUREMENT_SOURCES_MISSING")
            missing_annotation_source_ids = sorted(
                source.source_id
                for source in expected
                if source.source_id not in annotations_by_source
            )
            if missing_annotation_source_ids:
                reasons.append("MEASUREMENT_ANNOTATIONS_INCOMPLETE")
            if expected_ids - evaluated_ids:
                reasons.append("OBSERVATIONS_INCOMPLETE")
            if variant is ShapeGeometryExperimentVariant.SHAPE_CONTRAST_LOCAL_ANCHOR and (
                anchors_by_game[game.game_id] is None
            ):
                reasons.append("LOCAL_ANCHOR_UNAVAILABLE")
            contributor_sets = {
                value.profile_contributor_game_ids for value in evaluated
            }
            profile_fingerprints = {value.profile_fingerprint for value in evaluated}
            if (
                variant is ShapeGeometryExperimentVariant.SHAPE_CONTRAST_SHARED_PROFILE
                and (len(contributor_sets) > 1 or len(profile_fingerprints) > 1)
            ):
                _fail(
                    "SHAPE_GEOMETRY_V2_SHARED_PROFILE_PROVENANCE_INVALID",
                    "One game and shared-profile variant require one frozen profile provenance.",
                )
            automatic_correct = sum(
                value.outcome is ShapeGeometryExperimentOutcome.AUTOMATIC_CORRECT
                for value in evaluated
            )
            automatic_incorrect = sum(
                value.outcome is ShapeGeometryExperimentOutcome.AUTOMATIC_INCORRECT
                for value in evaluated
            )
            review_required = sum(
                value.outcome is ShapeGeometryExperimentOutcome.REVIEW_REQUIRED
                for value in evaluated
            )
            correction_required = sum(
                value.outcome is ShapeGeometryExperimentOutcome.CORRECTION_REQUIRED
                for value in evaluated
            )
            confirmation_only = sum(
                value.outcome is ShapeGeometryExperimentOutcome.CONFIRMATION_ONLY
                for value in evaluated
            )
            variants.append(
                {
                    "automaticCorrectSourceCount": automatic_correct,
                    "automaticIncorrectSourceCount": automatic_incorrect,
                    "automaticSourceCount": (
                        automatic_correct + automatic_incorrect + confirmation_only
                    ),
                    "confirmationOnlySourceCount": confirmation_only,
                    "correctionRequiredSourceCount": correction_required,
                    "evaluatedSourceCount": len(evaluated),
                    "expectedSourceCount": len(expected),
                    "missingSourceIds": sorted(expected_ids - evaluated_ids),
                    "missingAnnotationSourceIds": missing_annotation_source_ids,
                    "operatorActiveSeconds": sum(
                        value.active_operator_seconds for value in evaluated
                    ),
                    "profileContributorGameIds": (
                        []
                        if not contributor_sets
                        else list(next(iter(contributor_sets)))
                    ),
                    "profileFingerprint": (
                        None
                        if not profile_fingerprints
                        else next(iter(profile_fingerprints))
                    ),
                    "reasons": reasons,
                    "reviewRequiredSourceCount": review_required,
                    "status": "not_evaluable" if reasons else "measured",
                    "variant": variant.value,
                }
            )
        games.append(
            {
                "gameId": game.game_id,
                "status": (
                    "measured"
                    if variants and all(value["status"] == "measured" for value in variants)
                    else "not_evaluable"
                ),
                "variants": variants,
            }
        )
    return {
        "algorithmFingerprint": _fingerprint(dict(observations.algorithm)),
        "anchorSelectionFingerprint": _fingerprint(anchor_selection),
        "annotationFingerprint": annotations.fingerprint(),
        "corpusInventoryFingerprint": inventory.fingerprint(),
        "corpusManifestFingerprint": manifest.fingerprint(),
        "experimentObservationFingerprint": observations.fingerprint(),
        "games": games,
        "schemaVersion": SHAPE_GEOMETRY_V2_EXPERIMENT_REPORT_VERSION,
    }


def require_matching_experiment(
    saved_report: Mapping[str, object], current_report: Mapping[str, object]
) -> None:
    if canonical_json_bytes(saved_report) != canonical_json_bytes(current_report):
        _fail(
            "SHAPE_GEOMETRY_V2_EXPERIMENT_DRIFT",
            "Experiment output differs from the checksum-bound saved report.",
        )


__all__ = [
    "SHAPE_GEOMETRY_V2_EXPERIMENT_INPUT_VERSION",
    "SHAPE_GEOMETRY_V2_EXPERIMENT_REPORT_VERSION",
    "ShapeGeometryExperimentObservation",
    "ShapeGeometryExperimentObservations",
    "ShapeGeometryExperimentOutcome",
    "ShapeGeometryExperimentVariant",
    "load_shape_geometry_experiment_observations",
    "require_matching_experiment",
    "run_shape_geometry_experiment",
]
