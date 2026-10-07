"""Explicitly selected partial V2 observer, separate from immutable legacy adapters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .middle_row_locator import canonicalize_source_image
from .v7_calibration import V7_DYNAMIC_GEOMETRY_FAMILY_ID, V7GeometryProfile
from .v7_label_locator import (
    V7DynamicGridLabelLocatorConfig,
    V7LabelRecognitionBackend,
    recognize_grid_label_crops,
)
from .v7_partial_label_locator import V7PartialGridLabelLocator
from .v7_partial_lattice import partial_lattice_policy
from .v7_profile_bound_observer import (
    _canonical_sha256,
    _fail,
    _observation_from_labels,
    _require_profile_matches_configuration,
    _source_error_observation,
)
from .v7_range_proof import V7RangeProofResolver
from .v7_run_state import V7ScanObservation
from .v7_worker_runtime import V7SourceObservationRequest, V7WorkerConfiguration

V7_PARTIAL_PROFILE_BOUND_OBSERVER_VERSION = "v7-partial-profile-bound-observer-v2"


def v7_partial_profile_bound_localizer_fingerprint(profile: V7GeometryProfile) -> str:
    return _canonical_sha256(
        {
            "version": V7_PARTIAL_PROFILE_BOUND_OBSERVER_VERSION,
            "geometryFamilyId": profile.calibration.geometry_family_id,
            "profileFingerprint": profile.profile_fingerprint,
            "locatorConfig": profile.calibration.locator_config.as_dict(),
            "partialLatticePolicy": partial_lattice_policy(),
        }
    )


def _require_partial_profile(
    profile: V7GeometryProfile, configuration: V7WorkerConfiguration
) -> V7DynamicGridLabelLocatorConfig:
    config = profile.calibration.locator_config
    if profile.calibration.geometry_family_id != V7_DYNAMIC_GEOMETRY_FAMILY_ID or not isinstance(
        config, V7DynamicGridLabelLocatorConfig
    ):
        _fail("V7_CALIBRATION_FAMILY_UNSUPPORTED", "Partial V7 geometry requires a V2 profile.")
    _require_profile_matches_configuration(
        profile,
        configuration,
        localizer_fingerprint=v7_partial_profile_bound_localizer_fingerprint(profile),
    )
    return config


class V7PartialProfileBoundObserverFactory:
    def __init__(
        self,
        profile: V7GeometryProfile,
        recognizer_factory: Callable[[], V7LabelRecognitionBackend],
    ) -> None:
        self._profile = profile
        self._recognizer_factory = recognizer_factory

    def create(
        self, configuration: V7WorkerConfiguration, _manifest: object
    ) -> V7PartialProfileBoundObserver:
        _require_partial_profile(self._profile, configuration)
        recognizer = self._recognizer_factory()
        if not callable(getattr(recognizer, "recognize_many", None)):
            _fail("V7_OCR_BACKEND_INVALID", "The V7 numeric-label recognizer is invalid.")
        return V7PartialProfileBoundObserver(self._profile, configuration, recognizer)


class V7PartialProfileBoundObserver:
    requires_config_bound_checkpoint = True

    def __init__(
        self,
        profile: V7GeometryProfile,
        configuration: V7WorkerConfiguration,
        recognizer: V7LabelRecognitionBackend,
    ) -> None:
        self._locator = V7PartialGridLabelLocator(_require_partial_profile(profile, configuration))
        self._recognizer = recognizer
        self._resolver = V7RangeProofResolver(configuration.expected_ranges)

    def observe(self, request: V7SourceObservationRequest) -> V7ScanObservation:
        try:
            canonical = canonicalize_source_image(request.source_content)
        except ValueError:
            return _source_error_observation(request.source.source_index)
        location = self._locator.locate_with_diagnostics(canonical.rgb)
        labels = (
            recognize_grid_label_crops(
                location.crops, self._recognizer, self._locator.config.position_confidence
            )
            if location.crops
            else ()
        )
        observation = _observation_from_labels(
            request.source, canonical.rgb, labels, self._resolver
        )
        proof = observation.proof
        if location.reason_code is not None:
            proof = replace(proof, reason_codes=(*proof.reason_codes, location.reason_code))
        return replace(
            observation,
            proof=proof,
            labels=labels,
            observed_position_indices=tuple(crop.position_index for crop in location.crops),
        )


def build_paddle_v7_partial_profile_bound_observer_factory(
    profile: V7GeometryProfile, model_root: Path
) -> V7PartialProfileBoundObserverFactory:
    def create_recognizer() -> V7LabelRecognitionBackend:
        from game_predictor_worker.images.sequence_ocr import PaddleSequenceNumberRecognizer

        return PaddleSequenceNumberRecognizer(model_root)

    return V7PartialProfileBoundObserverFactory(profile, create_recognizer)
