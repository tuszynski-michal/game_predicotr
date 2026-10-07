"""Read-only pinned artifact composition for the reviewed V7 pilot."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from game_predictor_api.application.v7_label_geometry_calibration import (
    V7LabelGeometryCalibrationApiError,
    read_immutable_v7_geometry_profile,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7DeliveryConflict,
    V7PilotGate,
    V7PilotSnapshot,
)

from game_predictor_worker.images.sequence_ocr import (
    SequenceOcrError,
    sequence_number_model_fingerprint,
)

from .local_source_manifest import LocalSourceManifest
from .v7_calibration import V7GeometryProfile
from .v7_partial_profile_bound_observer import (
    build_paddle_v7_partial_profile_bound_observer_factory,
    v7_partial_profile_bound_localizer_fingerprint,
)
from .v7_pilot_attestation import validate_v7_pilot_attestation
from .v7_worker_runtime import V7SourceObserver, V7WorkerConfiguration, V7WorkerRuntimeError


class V7PilotArtifacts:
    def __init__(
        self, runtime_root: Path, model_root: Path, *, acceptance_scope: str | None = None
    ) -> None:
        if acceptance_scope not in (None, "real_pilot", "technical_fixture"):
            raise ValueError("Unknown V7 pilot acceptance scope.")
        self.runtime_root = runtime_root
        self.profiles_root = runtime_root / "v7-label-geometry" / "profiles"
        self.model_root = model_root
        self.acceptance_scope = acceptance_scope

    def validate(self, gate: V7PilotGate) -> V7GeometryProfile:
        """Never create runtime directories, recover sessions or construct Paddle."""
        if not gate.enabled or gate.profile_fingerprint is None:
            raise V7DeliveryConflict("SEMI_AUTOMATIC_SELECTION_V7_BLOCKED", "V7 pilot is blocked.")
        if self.acceptance_scope is not None and (
            gate.acceptance_receipt is None
            or gate.acceptance_receipt.get("scope") != self.acceptance_scope
        ):
            raise V7DeliveryConflict(
                "V7_PILOT_ACCEPTANCE_SCOPE_MISMATCH",
                "This composition does not accept that receipt scope.",
            )
        try:
            record = read_immutable_v7_geometry_profile(
                self.profiles_root, gate.profile_fingerprint
            )
            profile = record.profile
            if (
                profile.calibration.status.value != "passed"
                or profile.calibration.geometry_family_id != gate.geometry_family_id
                or v7_partial_profile_bound_localizer_fingerprint(profile)
                != gate.observer_fingerprint
                or sequence_number_model_fingerprint(self.model_root) != gate.ocr_model_fingerprint
            ):
                raise V7DeliveryConflict(
                    "V7_PILOT_ARTIFACT_MISMATCH", "Pinned V7 artifacts changed."
                )
            validate_v7_pilot_attestation(
                self.runtime_root, profile, record.session_export_checksum_sha256, gate
            )
            return profile
        except (
            V7LabelGeometryCalibrationApiError,
            SequenceOcrError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
        ) as error:
            if isinstance(error, V7DeliveryConflict):
                raise
            raise V7DeliveryConflict(
                getattr(error, "code", "V7_PILOT_ARTIFACT_UNAVAILABLE"), str(error)
            ) from error


class V7GatedObserverFactory:
    def __init__(self, artifacts: V7PilotArtifacts, gate_reader: Callable[[], V7PilotGate]) -> None:
        self._artifacts = artifacts
        self._gate_reader = gate_reader

    def create(
        self, configuration: V7WorkerConfiguration, manifest: LocalSourceManifest
    ) -> V7SourceObserver:
        try:
            snapshot = V7PilotSnapshot.from_payload(configuration.pilot)
            gate = self._gate_reader()
            gate.require_snapshot(snapshot, manifest.source_root, manifest.source_fingerprint)
            profile = self._artifacts.validate(gate)
            if (
                configuration.calibration_fingerprint != snapshot.profile_fingerprint
                or configuration.localizer_fingerprint != snapshot.observer_fingerprint
            ):
                raise V7DeliveryConflict(
                    "V7_PILOT_ARTIFACT_MISMATCH", "Worker configuration mismatch."
                )
            return build_paddle_v7_partial_profile_bound_observer_factory(
                profile, self._artifacts.model_root
            ).create(configuration, manifest)
        except (V7DeliveryConflict, ValueError) as error:
            raise V7WorkerRuntimeError(
                getattr(error, "code", "V7_CONFIGURATION_INVALID"), str(error)
            ) from error
