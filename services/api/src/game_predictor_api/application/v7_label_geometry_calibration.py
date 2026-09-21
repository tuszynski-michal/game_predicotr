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
    V7GeometryCalibration,
    V7GeometryProfile,
    V7LabelGeometryAnnotation,
    calibrate_v7_label_geometry,
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
    V7CorpusManifest,
    V7CorpusSplit,
    V7SelectionConfigurationError,
    load_v7_corpus_manifest,
)
from PIL import Image, ImageOps, UnidentifiedImageError

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

    def list_adoptions(self) -> tuple[dict[str, object], ...]:
        """Adoptions are intentionally unavailable until T0605 validates them."""

        return ()

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
        if slot.state is not V7AnnotationState.ANNOTATED:
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
                capture_group_id=groups.get(source.source_id),
                crop_assessment=slot.crop_assessment or V7CropAssessment.UNCERTAIN,
            )
        )
    return tuple(annotations)


def _profile_from_payload(payload: dict[str, object]) -> V7GeometryProfile:
    """Reconstruct only a validated immutable profile payload for the read endpoint."""

    calibration_payload = payload["calibration"]
    if not isinstance(calibration_payload, dict):
        raise ValueError("calibration")
    from game_predictor_worker.semi_automatic_selection.v7_label_locator import (
        V7GridLabelLocatorConfig,
    )

    config_payload = calibration_payload["locatorConfig"]
    if not isinstance(config_payload, dict):
        raise ValueError("locatorConfig")
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
