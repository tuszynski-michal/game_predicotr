"""Server-owned corpus resolution and profiles for V7 label calibration."""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Final
from uuid import uuid4

from game_predictor_worker.semi_automatic_selection.v7_calibration import (
    V7AnnotationState,
    V7CalibrationError,
    V7CropAssessment,
    V7EvaluationStatus,
    V7GeometryAdoption,
    V7GeometryCalibration,
    V7GeometryProfile,
    V7LabelGeometryAnnotation,
    V7SourceReference,
    V7ValidationAcceptanceTruth,
    V7ValidationPredictionSnapshot,
    V7ValidationQualityStatus,
    V7ValidationSourceObservation,
    calibrate_v7_label_geometry,
    evaluate_v7_validation_acceptance,
)
from game_predictor_worker.semi_automatic_selection.v7_calibration_sessions import (
    V7CalibrationSession,
    V7CalibrationSessionError,
    V7CalibrationSessionExport,
    V7CalibrationSessionOperation,
    V7CalibrationSessionOperationKind,
    V7CalibrationSessionReceipt,
    V7CalibrationSessionSource,
    V7CalibrationSessionStatus,
    V7CalibrationSessionStore,
)
from game_predictor_worker.semi_automatic_selection.v7_configuration import (
    V7CorpusCase,
    V7CorpusCaseInventory,
    V7CorpusManifest,
    V7CorpusSplit,
    V7SelectionConfigurationError,
    load_v7_corpus_manifest,
)
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_api.application.v7_label_geometry_validation import (
    V7ValidationRegistry,
    V7ValidationRegistryError,
    V7ValidationReport,
)

_PROFILE_SCHEMA_VERSION: Final = 1
_WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT: Final = 0x0400


class V7LabelGeometryCalibrationApiError(ValueError):
    """Stable failures at the API application boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class V7CanonicalLabelGeometryAsset:
    content: bytes
    source_checksum_sha256: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class V7LabelGeometryProfileRecord:
    profile: V7GeometryProfile
    session_export_checksum_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "calibration": self.profile.calibration.as_dict(),
            "profileFingerprint": self.profile.profile_fingerprint,
            "revision": self.profile.revision,
            "sessionExportChecksumSha256": self.session_export_checksum_sha256,
        }


@dataclass(frozen=True, slots=True)
class _ResolvedCorpus:
    manifest_fingerprint: str
    sources: tuple[V7CalibrationSessionSource, ...]
    paths_by_source_id: dict[str, Path]


class V7LabelGeometryCalibrationService:
    """Resolve calibration cases and keep all source filesystem paths private."""

    def __init__(
        self,
        *,
        runtime_root: Path,
        corpus_manifest_path: Path | None,
    ) -> None:
        self._runtime_root = Path(runtime_root).resolve()
        self._manifest_path = None if corpus_manifest_path is None else Path(corpus_manifest_path)
        self._sessions = V7CalibrationSessionStore(self._runtime_root)
        self._profiles_root = self._runtime_root / "v7-label-geometry" / "profiles"
        self._validation = V7ValidationRegistry(self._runtime_root)

    def create_session(
        self,
        *,
        geometry_family_id: str,
        corpus_case_ids: tuple[str, ...],
    ) -> V7CalibrationSession:
        resolved = self._resolve_requested_cases(geometry_family_id, corpus_case_ids)
        try:
            return self._sessions.create(
                manifest_fingerprint=resolved.manifest_fingerprint,
                geometry_family_id=geometry_family_id,
                sources=resolved.sources,
            )
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error

    def get_session(self, session_id: str) -> V7CalibrationSession:
        session, _resolved = self._current_session(session_id)
        return session

    def mutate_session(
        self,
        session_id: str,
        operation: V7CalibrationSessionOperation,
    ) -> tuple[V7CalibrationSession, V7CalibrationSessionReceipt]:
        # Preserve TASK-0600's receipt-before-revision/source rule at the HTTP
        # boundary. A lost answer can be recovered even when a later read would
        # now observe corpus drift.
        try:
            prior = self._sessions.read(session_id)
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error
        prior_receipt = prior.receipt_for(operation.operation_id)
        if prior_receipt is not None:
            if prior_receipt.operation_fingerprint != operation.fingerprint:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_SESSION_OPERATION_ID_CONFLICT",
                    "Operation ID was already used with different content.",
                )
            return prior, prior_receipt
        _session, resolved = self._current_session(session_id)
        try:
            return self._sessions.apply(
                session_id,
                operation,
                current_sources=resolved.sources,
                current_manifest_fingerprint=resolved.manifest_fingerprint,
            )
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error

    def export_session(
        self,
        session_id: str,
        *,
        expected_revision: int,
    ) -> V7CalibrationSessionExport:
        _session, resolved = self._current_session(session_id)
        try:
            return self._sessions.export(
                session_id,
                expected_revision=expected_revision,
                current_sources=resolved.sources,
                current_manifest_fingerprint=resolved.manifest_fingerprint,
            )
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error

    def canonical_asset(
        self,
        session_id: str,
        source_id: str,
        *,
        expected_source_checksum_sha256: str,
    ) -> V7CanonicalLabelGeometryAsset:
        session, resolved = self._current_session(session_id)
        if session.status is not V7CalibrationSessionStatus.ACTIVE:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SESSION_BLOCKED",
                "The calibration session is blocked and cannot serve more assets.",
            )
        source = next((item for item in session.sources if item.source_id == source_id), None)
        if source is None:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SOURCE_NOT_FOUND", "The requested calibration source is absent."
            )
        if source.source_checksum_sha256 != expected_source_checksum_sha256:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SOURCE_CHECKSUM_CONFLICT",
                "The requested calibration source checksum is stale.",
            )
        path = resolved.paths_by_source_id.get(source_id)
        if path is None:
            self._block_source_drift(session_id)
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SESSION_SOURCE_DRIFT",
                "The calibration source inventory changed after session creation.",
            )
        try:
            content = path.read_bytes()
        except OSError as error:
            self._block_source_drift(session_id)
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SESSION_SOURCE_DRIFT",
                "The calibration source is no longer readable.",
            ) from error
        if hashlib.sha256(content).hexdigest() != source.source_checksum_sha256:
            self._block_source_drift(session_id)
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SESSION_SOURCE_DRIFT",
                "The calibration source changed after session creation.",
            )
        try:
            with Image.open(BytesIO(content)) as source_image:
                canonical = ImageOps.exif_transpose(source_image)
                canonical.load()
                if canonical.width < 1 or canonical.height < 1:
                    raise ValueError("empty image")
                if canonical.mode not in {"RGB", "RGBA", "L"}:
                    canonical = canonical.convert("RGB")
                output = BytesIO()
                canonical.save(output, format="PNG", optimize=False)
                return V7CanonicalLabelGeometryAsset(
                    content=output.getvalue(),
                    source_checksum_sha256=source.source_checksum_sha256,
                    width=canonical.width,
                    height=canonical.height,
                )
        except (OSError, UnidentifiedImageError, ValueError) as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_SOURCE_IMAGE_INVALID",
                "The calibration source cannot be decoded as an image.",
            ) from error

    def create_profile(
        self,
        session_id: str,
        *,
        expected_revision: int,
    ) -> V7LabelGeometryProfileRecord:
        _session, resolved = self._current_session(session_id)
        try:
            exported = self._sessions.export(
                session_id,
                expected_revision=expected_revision,
                current_sources=resolved.sources,
                current_manifest_fingerprint=resolved.manifest_fingerprint,
            )
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error
        snapshot = exported.session
        annotations = _annotations_from_session(snapshot)
        try:
            calibration = calibrate_v7_label_geometry(
                annotations,
                manifest_fingerprint=snapshot.manifest_fingerprint,
                geometry_family_id=snapshot.geometry_family_id,
            )
        except V7CalibrationError as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_REJECTED", str(error)
            ) from error
        if calibration.status.value != "passed":
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_REJECTED",
                "The measured label geometry did not pass the p95 residual gate.",
            )
        profile_fingerprint = _fingerprint(
            {
                "calibration": calibration.as_dict(),
                "sessionExportChecksumSha256": exported.export_checksum_sha256,
            }
        )
        record = V7LabelGeometryProfileRecord(
            profile=V7GeometryProfile(
                profile_fingerprint=profile_fingerprint,
                calibration=calibration,
                revision=snapshot.revision,
            ),
            session_export_checksum_sha256=exported.export_checksum_sha256,
        )
        self._write_profile(record)
        return record

    def get_profile(self, profile_fingerprint: str) -> V7LabelGeometryProfileRecord:
        if not _is_sha256(profile_fingerprint):
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_NOT_FOUND", "The requested geometry profile does not exist."
            )
        return self._read_profile(profile_fingerprint)

    def list_profiles(self) -> tuple[V7LabelGeometryProfileRecord, ...]:
        if not self._profiles_root.exists():
            return ()
        if self._profiles_root.is_symlink() or not self._profiles_root.is_dir():
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_STORE_INVALID", "The profile store is unavailable."
            )
        paths = tuple(sorted(self._profiles_root.glob("*.json"), key=lambda item: item.name))
        if any(path.is_symlink() or not path.is_file() for path in paths):
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_STORE_INVALID", "The profile store is unavailable."
            )
        return tuple(self._read_profile(path.stem) for path in paths)

    def create_validation_report(
        self,
        *,
        operation_id: str,
        profile_fingerprint: str,
        source_game_ref: str,
        truth_values: tuple[dict[str, object], ...],
        source_observation_values: tuple[dict[str, object], ...],
        prediction_snapshot_values: tuple[dict[str, object], ...],
    ) -> tuple[V7ValidationReport, bool]:
        """Seal non-holdout T05 inputs after server-owned corpus validation."""

        try:
            truths = tuple(_validation_truth_from_payload(item) for item in truth_values)
            source_observations = tuple(
                _validation_source_observation_from_payload(item)
                for item in source_observation_values
            )
            snapshots = tuple(
                _validation_prediction_snapshot_from_payload(item)
                for item in prediction_snapshot_values
            )
        except (KeyError, TypeError, ValueError, V7CalibrationError) as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_PAYLOAD_INVALID", "The V7 validation payload is invalid."
            ) from error
        canonical_truth = tuple(
            item.as_dict() for item in sorted(truths, key=lambda item: item.case_id)
        )
        canonical_observations = tuple(
            item.as_dict()
            for item in sorted(source_observations, key=lambda item: item.source.source_id)
        )
        canonical_snapshots = tuple(
            item.as_dict() for item in sorted(snapshots, key=lambda item: item.case_id)
        )
        operation_fingerprint = _fingerprint(
            {
                "predictionSnapshots": canonical_snapshots,
                "profileFingerprint": profile_fingerprint,
                "sourceGameRef": source_game_ref,
                "sourceObservations": canonical_observations,
                "truth": canonical_truth,
            }
        )
        try:
            replayed = self._validation.replay_report(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
            )
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error
        if replayed is not None:
            return replayed, False
        profile = self.get_profile(profile_fingerprint).profile
        if profile.calibration.status is not V7EvaluationStatus.PASSED:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_PROFILE_REJECTED",
                "Only a passed geometry profile can be validated for adoption.",
            )
        case_ids = tuple(sorted({item.corpus_case_id for item in truths}))
        manifest, corpus_snapshot_fingerprint, sources = self._resolve_validation_sources(
            geometry_family_id=profile.calibration.geometry_family_id,
            source_game_ref=source_game_ref,
            case_ids=case_ids,
        )
        _validate_validation_source_identities(
            truths=truths,
            source_observations=source_observations,
            snapshots=snapshots,
            sources=sources,
        )
        try:
            acceptance = evaluate_v7_validation_acceptance(
                truths,
                snapshots,
                source_observations,
            )
        except V7CalibrationError as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_EVIDENCE_INVALID", str(error)
            ) from error
        if (
            _validation_corpus_fingerprint(manifest, manifest.freeze_inventory())
            != corpus_snapshot_fingerprint
        ):
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_CORPUS_DRIFT",
                "The V7 validation corpus changed while the report was prepared.",
            )
        from game_predictor_worker.semi_automatic_selection.v7_profile_bound_observer import (
            v7_profile_bound_localizer_fingerprint,
        )

        report = V7ValidationReport.create(
            profile_fingerprint=profile.profile_fingerprint,
            observer_fingerprint=v7_profile_bound_localizer_fingerprint(profile),
            geometry_family_id=profile.calibration.geometry_family_id,
            source_game_ref=source_game_ref,
            corpus_manifest_fingerprint=manifest.fingerprint(),
            corpus_inventory_fingerprint=corpus_snapshot_fingerprint,
            acceptance=acceptance,
            truth=canonical_truth,
            source_observations=canonical_observations,
            prediction_snapshots=canonical_snapshots,
        )
        try:
            return self._validation.persist_report(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
                report=report,
            )
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error

    def create_adoption(
        self,
        *,
        operation_id: str,
        profile_fingerprint: str,
        source_game_ref: str,
        validation_report_fingerprint: str,
    ) -> tuple[V7GeometryAdoption, bool]:
        """Approve one exact passed report for one source game without activation."""

        operation_fingerprint = _fingerprint(
            {
                "profileFingerprint": profile_fingerprint,
                "sourceGameRef": source_game_ref,
                "validationReportFingerprint": validation_report_fingerprint,
            }
        )
        try:
            replayed = self._validation.replay_adoption(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
            )
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error
        if replayed is not None:
            return replayed, False
        profile = self.get_profile(profile_fingerprint).profile
        if profile.calibration.status is not V7EvaluationStatus.PASSED:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_PROFILE_REJECTED",
                "Only a passed geometry profile can be adopted.",
            )
        try:
            report = self._validation.get_report(validation_report_fingerprint)
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error
        if (
            report.profile_fingerprint != profile.profile_fingerprint
            or report.geometry_family_id != profile.calibration.geometry_family_id
            or report.source_game_ref != source_game_ref
        ):
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_ADOPTION_IDENTITY_CONFLICT",
                "Validation report identity does not match the requested profile and game.",
            )
        from game_predictor_worker.semi_automatic_selection.v7_profile_bound_observer import (
            v7_profile_bound_localizer_fingerprint,
        )

        if report.observer_fingerprint != v7_profile_bound_localizer_fingerprint(profile):
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_ADOPTION_OBSERVER_CONFLICT",
                "Validation report was created by another observer contract.",
            )
        if report.acceptance.status is not V7EvaluationStatus.PASSED:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_ADOPTION_REPORT_REJECTED",
                "Only a passed, evaluable T05 validation report can create an adoption.",
            )
        manifest = self._load_manifest()
        if (
            manifest.fingerprint() != report.corpus_manifest_fingerprint
            or _validation_corpus_fingerprint(manifest, manifest.freeze_inventory())
            != report.corpus_inventory_fingerprint
        ):
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_ADOPTION_CORPUS_DRIFT",
                "The corpus changed after the validation report was sealed.",
            )
        adoption_key = _fingerprint(
            {
                "geometryFamilyId": report.geometry_family_id,
                "profileFingerprint": report.profile_fingerprint,
                "sourceGameRef": report.source_game_ref,
            }
        )
        adoption = V7GeometryAdoption(
            adoption_key=adoption_key,
            source_game_ref=report.source_game_ref,
            geometry_family_id=report.geometry_family_id,
            profile_fingerprint=report.profile_fingerprint,
            validation_report_fingerprint=report.validation_report_fingerprint,
        )
        try:
            return self._validation.persist_adoption(
                operation_id=operation_id,
                operation_fingerprint=operation_fingerprint,
                adoption=adoption,
            )
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error

    def list_adoptions(self) -> tuple[V7GeometryAdoption, ...]:
        try:
            return self._validation.list_adoptions()
        except V7ValidationRegistryError as error:
            raise _validation_error(error) from error

    def operation_from_values(
        self,
        *,
        operation_id: str,
        expected_revision: int,
        kind: str,
        source_id: str,
        position_index: int | None,
        center_x: float | None,
        center_y: float | None,
        crop_assessment: str | None,
        capture_group_id: str | None,
    ) -> V7CalibrationSessionOperation:
        try:
            return V7CalibrationSessionOperation(
                operation_id=operation_id,
                expected_revision=expected_revision,
                kind=V7CalibrationSessionOperationKind(kind),
                source_id=source_id,
                position_index=position_index,
                center_x=center_x,
                center_y=center_y,
                crop_assessment=(
                    None if crop_assessment is None else V7CropAssessment(crop_assessment)
                ),
                capture_group_id=capture_group_id,
            )
        except (ValueError, V7CalibrationSessionError) as error:
            raise _session_error(error) from error

    def _current_session(self, session_id: str) -> tuple[V7CalibrationSession, _ResolvedCorpus]:
        try:
            session = self._sessions.read(session_id)
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error
        try:
            resolved = self._resolve_session_sources(session)
            verified = self._sessions.verify(
                session_id,
                current_sources=resolved.sources,
                current_manifest_fingerprint=resolved.manifest_fingerprint,
            )
            return verified, resolved
        except V7LabelGeometryCalibrationApiError:
            self._block_source_drift(session_id)
            raise
        except V7CalibrationSessionError as error:
            raise _session_error(error) from error

    def _resolve_requested_cases(
        self,
        geometry_family_id: str,
        corpus_case_ids: tuple[str, ...],
    ) -> _ResolvedCorpus:
        manifest = self._load_manifest()
        if not corpus_case_ids or len(set(corpus_case_ids)) != len(corpus_case_ids):
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_CASE_INVALID", "Calibration cases must be unique and non-empty."
            )
        cases_by_id = {case.case_id: case for case in manifest.cases}
        selected: list[V7CorpusCase] = []
        for case_id in corpus_case_ids:
            case = cases_by_id.get(case_id)
            if case is None:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_CASE_NOT_FOUND", "The requested corpus case is not declared."
                )
            if case.split is V7CorpusSplit.HOLDOUT:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_HOLDOUT_FORBIDDEN",
                    "A holdout case cannot be opened for calibration.",
                )
            if case.split is not V7CorpusSplit.CALIBRATION:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_CASE_SPLIT_FORBIDDEN",
                    "Only calibration corpus cases can create an annotation session.",
                )
            if case.geometry_family_id != geometry_family_id:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_GEOMETRY_FAMILY_CONFLICT",
                    "The requested corpus case belongs to another geometry family.",
                )
            selected.append(case)
        return self._resolved_from_manifest(manifest, tuple(case.case_id for case in selected))

    def _resolve_session_sources(self, session: V7CalibrationSession) -> _ResolvedCorpus:
        case_ids = tuple(dict.fromkeys(source.corpus_case_id for source in session.sources))
        resolved = self._resolve_requested_cases(session.geometry_family_id, case_ids)
        return resolved

    def _resolve_validation_sources(
        self,
        *,
        geometry_family_id: str,
        source_game_ref: str,
        case_ids: tuple[str, ...],
    ) -> tuple[V7CorpusManifest, str, tuple[V7CalibrationSessionSource, ...]]:
        if not case_ids:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_CASE_INVALID", "Validation requires at least one corpus case."
            )
        manifest = self._load_manifest()
        cases_by_id = {case.case_id: case for case in manifest.cases}
        for case_id in case_ids:
            case = cases_by_id.get(case_id)
            if case is None:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_VALIDATION_CASE_NOT_FOUND", "Validation case is not declared by the corpus."
                )
            if case.split in {V7CorpusSplit.HOLDOUT, V7CorpusSplit.REFERENCE_ONLY}:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_VALIDATION_SPLIT_FORBIDDEN",
                    "Holdout and reference-only corpus cases cannot create a T05 report.",
                )
            if case.geometry_family_id != geometry_family_id:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_VALIDATION_GEOMETRY_FAMILY_CONFLICT",
                    "Validation corpus case belongs to another geometry family.",
                )
            if case.source_game_ref != source_game_ref:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_VALIDATION_SOURCE_GAME_CONFLICT",
                    "Validation corpus case belongs to another source game.",
                )
        try:
            initial_inventory = manifest.freeze_inventory()
        except V7SelectionConfigurationError as error:
            raise V7LabelGeometryCalibrationApiError(error.code, str(error)) from error
        resolved = self._resolved_from_manifest(manifest, case_ids)
        return (
            manifest,
            _validation_corpus_fingerprint(manifest, initial_inventory),
            resolved.sources,
        )

    def _resolved_from_manifest(
        self,
        manifest: V7CorpusManifest,
        case_ids: tuple[str, ...],
    ) -> _ResolvedCorpus:
        try:
            inventory = manifest.freeze_inventory()
            files = manifest.resolve_case_sources(case_ids)
        except V7SelectionConfigurationError as error:
            raise V7LabelGeometryCalibrationApiError(error.code, str(error)) from error
        fingerprint = _fingerprint(
            {
                "corpusRoot": str(manifest.resolved_corpus_root()),
                "inventory": [item.as_dict() for item in inventory],
                "manifestFingerprint": manifest.fingerprint(),
            }
        )
        sources: list[V7CalibrationSessionSource] = []
        paths: dict[str, Path] = {}
        source_checksums: set[str] = set()
        cases_by_id = {case.case_id: case for case in manifest.cases}
        for item in files:
            source_id = f"{item.case_id}-{item.source_checksum_sha256}"
            if source_id in paths or item.source_checksum_sha256 in source_checksums:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_SOURCE_DUPLICATE",
                    "A calibration source checksum is duplicated within a session.",
                )
            case = cases_by_id[item.case_id]
            sources.append(
                V7CalibrationSessionSource(
                    source_id=source_id,
                    source_checksum_sha256=item.source_checksum_sha256,
                    corpus_case_id=item.case_id,
                    split=case.split,
                    geometry_family_id=case.geometry_family_id or "",
                )
            )
            paths[source_id] = item.path
            source_checksums.add(item.source_checksum_sha256)
        return _ResolvedCorpus(
            manifest_fingerprint=fingerprint,
            sources=tuple(sources),
            paths_by_source_id=paths,
        )

    def _load_manifest(self) -> V7CorpusManifest:
        path = self._manifest_path
        if path is None:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_CORPUS_UNAVAILABLE",
                "No operator-owned V7 label-geometry corpus manifest is configured.",
            )
        if _has_link_or_reparse_ancestor(path) or not path.is_file():
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_CORPUS_UNAVAILABLE",
                "The configured V7 label-geometry corpus manifest is unavailable or unsafe.",
            )
        try:
            return load_v7_corpus_manifest(path)
        except (OSError, V7SelectionConfigurationError) as error:
            code = getattr(error, "code", "V7_CALIBRATION_CORPUS_UNAVAILABLE")
            raise V7LabelGeometryCalibrationApiError(code, str(error)) from error

    def _block_source_drift(self, session_id: str) -> None:
        with suppress(V7CalibrationSessionError):
            self._sessions.block_source_drift(session_id)

    def _write_profile(self, record: V7LabelGeometryProfileRecord) -> None:
        self._profiles_root.mkdir(parents=True, exist_ok=True)
        path = self._profiles_root / f"{record.profile.profile_fingerprint}.json"
        content = _canonical_json(
            {
                "profile": record.profile.as_dict(),
                "schemaVersion": _PROFILE_SCHEMA_VERSION,
                "sessionExportChecksumSha256": record.session_export_checksum_sha256,
            }
        )
        temporary = path.parent / f".{record.profile.profile_fingerprint}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, path)
        except FileExistsError:
            if not path.is_file() or path.is_symlink() or path.read_bytes() != content:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_CALIBRATION_PROFILE_CONFLICT",
                    "The immutable geometry profile path has different content.",
                ) from None
        except OSError as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_WRITE_FAILED", "The geometry profile could not be saved."
            ) from error
        finally:
            temporary.unlink(missing_ok=True)

    def _read_profile(self, profile_fingerprint: str) -> V7LabelGeometryProfileRecord:
        path = self._profiles_root / f"{profile_fingerprint}.json"
        if not path.is_file() or path.is_symlink():
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_NOT_FOUND", "The requested geometry profile does not exist."
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if (
                not isinstance(payload, dict)
                or payload.get("schemaVersion") != _PROFILE_SCHEMA_VERSION
            ):
                raise ValueError("schema")
            profile = payload["profile"]
            export_checksum = payload["sessionExportChecksumSha256"]
            if (
                not isinstance(profile, dict)
                or not isinstance(export_checksum, str)
                or not _is_sha256(export_checksum)
            ):
                raise ValueError("content")
            calibration = profile["calibration"]
            if not isinstance(calibration, dict):
                raise ValueError("calibration")
            restored_profile = _profile_from_payload(profile)
            expected_fingerprint = _fingerprint(
                {
                    "calibration": restored_profile.calibration.as_dict(),
                    "sessionExportChecksumSha256": export_checksum,
                }
            )
            if (
                restored_profile.profile_fingerprint != profile_fingerprint
                or restored_profile.profile_fingerprint != expected_fingerprint
            ):
                raise ValueError("fingerprint")
            return V7LabelGeometryProfileRecord(
                profile=restored_profile,
                session_export_checksum_sha256=export_checksum,
            )
        except (IndexError, KeyError, OSError, TypeError, ValueError, V7CalibrationError) as error:
            raise V7LabelGeometryCalibrationApiError(
                "V7_CALIBRATION_PROFILE_CORRUPT", "The stored geometry profile is invalid."
            ) from error


def _annotations_from_session(
    session: V7CalibrationSession,
) -> tuple[V7LabelGeometryAnnotation, ...]:
    source_by_id = {source.source_id: source for source in session.sources}
    groups = dict(session.capture_groups)
    annotations: list[V7LabelGeometryAnnotation] = []
    for slot in session.slots:
        capture_group_id = groups.get(slot.source_id)
        if (
            slot.state is not V7AnnotationState.ANNOTATED
            or slot.crop_assessment is not V7CropAssessment.CONTAINED
            or capture_group_id is None
            or not capture_group_id.strip()
        ):
            continue
        source = source_by_id[slot.source_id]
        annotations.append(
            V7LabelGeometryAnnotation(
                source_id=source.source_id,
                source_checksum_sha256=source.source_checksum_sha256,
                split=source.split,
                position_index=slot.position_index,
                center_x=slot.center_x or 0.0,
                center_y=slot.center_y or 0.0,
                geometry_family_id=source.geometry_family_id,
                capture_group_id=capture_group_id,
                crop_assessment=V7CropAssessment.CONTAINED,
            )
        )
    return tuple(annotations)


def _validation_truth_from_payload(value: dict[str, object]) -> V7ValidationAcceptanceTruth:
    return V7ValidationAcceptanceTruth(
        case_id=_validation_string(value["caseId"]),
        corpus_case_id=_validation_string(value["corpusCaseId"]),
        split=V7CorpusSplit(_validation_string(value["split"])),
        expected_range_start=_validation_integer(value["expectedRangeStart"]),
        expected_range_end=_validation_integer(value["expectedRangeEnd"]),
        evidence_sources=_validation_source_references(value["evidenceSources"]),
        acceptable_representative_sources=_validation_source_references(
            value["acceptableRepresentativeSources"]
        ),
        automatically_recoverable=_validation_boolean(value["automaticallyRecoverable"]),
        eligible_acceptable_representative=_validation_boolean(
            value["eligibleAcceptableRepresentative"]
        ),
    )


def _validation_source_observation_from_payload(
    value: dict[str, object],
) -> V7ValidationSourceObservation:
    return V7ValidationSourceObservation(
        source=_validation_source_reference(value),
        represented_range_start=_validation_integer(value["representedRangeStart"]),
        represented_range_end=_validation_integer(value["representedRangeEnd"]),
        top_cropped=_validation_boolean(value["topCropped"]),
        bottom_cropped=_validation_boolean(value["bottomCropped"]),
    )


def _validation_prediction_snapshot_from_payload(
    value: dict[str, object],
) -> V7ValidationPredictionSnapshot:
    selected_source = value["selectedSource"]
    return V7ValidationPredictionSnapshot(
        case_id=_validation_string(value["caseId"]),
        predicted_range_start=_validation_optional_integer(value["predictedRangeStart"]),
        predicted_range_end=_validation_optional_integer(value["predictedRangeEnd"]),
        selected_source=(
            None
            if selected_source is None
            else _validation_source_reference(_validation_mapping(selected_source))
        ),
        # This endpoint carries raw, caller-supplied observations only. The
        # current observer has no server-owned representative-quality result,
        # therefore it is always fail-closed as UNKNOWN. A later runtime
        # integration may attach a verifiable, server-owned quality snapshot.
        quality_status=V7ValidationQualityStatus.UNKNOWN,
        top_warning=_validation_boolean(value["topWarning"]),
        bottom_warning=_validation_boolean(value["bottomWarning"]),
        manual_review=_validation_boolean(value["manualReview"]),
    )


def _validation_source_references(value: object) -> tuple[V7SourceReference, ...]:
    if not isinstance(value, list):
        raise ValueError("sources")
    return tuple(_validation_source_reference(_validation_mapping(item)) for item in value)


def _validation_source_reference(value: dict[str, object]) -> V7SourceReference:
    return V7SourceReference(
        source_id=_validation_string(value["sourceId"]),
        source_checksum_sha256=_validation_string(value["sourceChecksumSha256"]),
    )


def _validate_validation_source_identities(
    *,
    truths: tuple[V7ValidationAcceptanceTruth, ...],
    source_observations: tuple[V7ValidationSourceObservation, ...],
    snapshots: tuple[V7ValidationPredictionSnapshot, ...],
    sources: tuple[V7CalibrationSessionSource, ...],
) -> None:
    source_by_id = {item.source_id: item for item in sources}
    truth_by_case = {item.case_id: item for item in truths}
    if len(truth_by_case) != len(truths):
        raise V7LabelGeometryCalibrationApiError(
            "V7_VALIDATION_EVIDENCE_INVALID", "Validation truth case ID is duplicated."
        )
    for truth in truths:
        for reference in (*truth.evidence_sources, *truth.acceptable_representative_sources):
            source = _validated_validation_source(source_by_id, reference)
            if source.corpus_case_id != truth.corpus_case_id or source.split is not truth.split:
                raise V7LabelGeometryCalibrationApiError(
                    "V7_VALIDATION_SOURCE_IDENTITY_CONFLICT",
                    "Validation truth source belongs to another corpus case or split.",
                )
    for observation in source_observations:
        _validated_validation_source(source_by_id, observation.source)
    for snapshot in snapshots:
        truth = truth_by_case.get(snapshot.case_id)
        if truth is None:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_SOURCE_IDENTITY_CONFLICT",
                "Validation prediction has no matching truth case.",
            )
        if snapshot.selected_source is None:
            continue
        source = _validated_validation_source(source_by_id, snapshot.selected_source)
        if source.corpus_case_id != truth.corpus_case_id:
            raise V7LabelGeometryCalibrationApiError(
                "V7_VALIDATION_SOURCE_IDENTITY_CONFLICT",
                "Validation selected source belongs to another corpus case.",
            )


def _validated_validation_source(
    source_by_id: dict[str, V7CalibrationSessionSource],
    reference: V7SourceReference,
) -> V7CalibrationSessionSource:
    source = source_by_id.get(reference.source_id)
    if source is None or source.source_checksum_sha256 != reference.source_checksum_sha256:
        raise V7LabelGeometryCalibrationApiError(
            "V7_VALIDATION_SOURCE_IDENTITY_CONFLICT",
            "Validation source identity or checksum differs from the frozen corpus.",
        )
    return source


def _validation_corpus_fingerprint(
    manifest: V7CorpusManifest,
    inventory: tuple[V7CorpusCaseInventory, ...],
) -> str:
    """Bind validation to the physical corpus root as well as file identities."""

    return _fingerprint(
        {
            "corpusRoot": str(manifest.resolved_corpus_root()),
            "inventory": [item.as_dict() for item in inventory],
            "manifestFingerprint": manifest.fingerprint(),
        }
    )


def _validation_mapping(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError("mapping")
    return value


def _validation_string(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("string")
    return value


def _validation_integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("integer")
    return value


def _validation_optional_integer(value: object) -> int | None:
    return None if value is None else _validation_integer(value)


def _validation_boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError("boolean")
    return value


def _profile_from_payload(payload: dict[str, object]) -> V7GeometryProfile:
    """Reconstruct only a validated immutable profile payload for the read endpoint."""

    calibration_payload = payload["calibration"]
    if not isinstance(calibration_payload, dict):
        raise ValueError("calibration")
    from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
        V7DynamicGridLabelLocatorConfig,
        V7GridLabelLocatorConfig,
    )

    config_payload = calibration_payload["locatorConfig"]
    if not isinstance(config_payload, dict):
        raise ValueError("locatorConfig")
    if config_payload.get("kind") == "dynamic_lattice_v2":
        config = V7DynamicGridLabelLocatorConfig(
            crop_height_spacing_ratio=float(config_payload["cropHeightSpacingRatio"]),
            crop_width_spacing_ratio=float(config_payload["cropWidthSpacingRatio"]),
            minimum_aspect_ratio=float(config_payload["minimumAspectRatio"]),
            maximum_aspect_ratio=float(config_payload["maximumAspectRatio"]),
            minimum_lattice_margin=float(config_payload["minimumLatticeMargin"]),
            maximum_lattice_residual_ratio=float(config_payload["maximumLatticeResidualRatio"]),
            position_confidence=float(config_payload["positionConfidence"]),
        )
    else:
        centers = config_payload["centers"]
        if not isinstance(centers, list):
            raise ValueError("centers")
        config = V7GridLabelLocatorConfig(
            centers=tuple((float(item[0]), float(item[1])) for item in centers),
            width_ratios=tuple(float(value) for value in config_payload["widthRatios"]),
            height_ratio=float(config_payload["heightRatio"]),
            minimum_aspect_ratio=float(config_payload["minimumAspectRatio"]),
            maximum_aspect_ratio=float(config_payload["maximumAspectRatio"]),
            position_confidence=float(config_payload["positionConfidence"]),
        )
    calibration = V7GeometryCalibration(
        manifest_fingerprint=str(calibration_payload["manifestFingerprint"]),
        input_fingerprint=str(calibration_payload["inputFingerprint"]),
        geometry_family_id=str(calibration_payload["geometryFamilyId"]),
        locator_config=config,
        source_count_by_position=tuple(
            int(value) for value in calibration_payload["sourceCountByPosition"]
        ),
        capture_group_count_by_position=tuple(
            int(value) for value in calibration_payload["captureGroupCountByPosition"]
        ),
        p95_center_residual_by_position=tuple(
            float(value) for value in calibration_payload["p95CenterResidualByPosition"]
        ),
        p95_center_residual=float(calibration_payload["p95CenterResidual"]),
        maximum_p95_center_residual=float(calibration_payload["maximumP95CenterResidual"]),
        minimum_sources_per_position=int(calibration_payload["minimumSourcesPerPosition"]),
        minimum_capture_groups_per_position=int(
            calibration_payload["minimumCaptureGroupsPerPosition"]
        ),
    )
    return V7GeometryProfile(
        profile_fingerprint=str(payload["profileFingerprint"]),
        calibration=calibration,
        revision=int(payload["revision"]),
    )


def _session_error(error: ValueError) -> V7LabelGeometryCalibrationApiError:
    return V7LabelGeometryCalibrationApiError(
        getattr(error, "code", "V7_CALIBRATION_SESSION_INVALID"), str(error)
    )


def _validation_error(error: V7ValidationRegistryError) -> V7LabelGeometryCalibrationApiError:
    return V7LabelGeometryCalibrationApiError(error.code, str(error))


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _is_link_or_reparse(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
        return isinstance(attributes, int) and bool(
            attributes & _WINDOWS_FILE_ATTRIBUTE_REPARSE_POINT
        )
    except OSError:
        return False


def _has_link_or_reparse_ancestor(path: Path) -> bool:
    try:
        absolute = path.absolute()
    except OSError:
        return True
    return any(_is_link_or_reparse(component) for component in (absolute, *absolute.parents))


__all__ = [
    "V7CanonicalLabelGeometryAsset",
    "V7LabelGeometryCalibrationApiError",
    "V7LabelGeometryCalibrationService",
    "V7LabelGeometryProfileRecord",
]
