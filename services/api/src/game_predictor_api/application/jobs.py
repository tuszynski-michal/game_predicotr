"""Application service and repository port for durable jobs."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from game_predictor_worker.images.board_cell_geometry_activation import (
    board_cell_processing_snapshot,
    board_cell_recrop_snapshot,
)
from game_predictor_worker.images.board_cell_geometry_contract import BoardCellTopology
from game_predictor_worker.images.lateral_partial_contract import (
    LATERAL_PARTIAL_SNAPSHOT_VERSION,
    LATERAL_PARTIAL_SNAPSHOT_VERSION_V2,
    LATERAL_PARTIAL_SNAPSHOT_VERSION_V3,
    SELECTIVE_FRAME_SNAPSHOT_VERSION,
    GeometryEngineVariant,
    LateralPartialContractError,
    LateralPartialGeometrySnapshot,
    require_geometry_engine_variant_available,
)
from game_predictor_worker.images.page_geometry_registration import (
    PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
    PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
    PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
    PAGE_REGISTRATION_THRESHOLDS_VERSION,
    PAGE_REGISTRATION_VERSION,
)
from game_predictor_worker.images.partial_grid_learning import PartialGridTrainingProfile
from game_predictor_worker.images.pipeline_contract import (
    CURRENT_NORMALIZATION_ADAPTER_VERSION,
    STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION,
    STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION,
    SYMBOL_RGB_PREPROCESSING_VERSION,
    VIRTUAL_CELL_RENDERER_VERSION,
    CellAssetRolloutMode,
    GeometryPipelineRolloutSnapshot,
    GeometryRolloutMode,
    StructuredGeometryActivationSnapshot,
    StructuredGeometryCandidateSnapshot,
    effective_pipeline_fingerprint,
)
from game_predictor_worker.images.structured_geometry import (
    structured_lattice_active_config_payload,
    structured_lattice_candidate_config_payload,
)

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.application.managed_reprocess_evidence import (
    ManagedReprocessEvidenceError,
    resolve_managed_reprocess_evidence,
)
from game_predictor_api.domain.datasets import DatasetVersionStatus
from game_predictor_api.domain.image_import_engine_policy import (
    ImageImportEnginePolicySnapshot,
    policy_from_rollout_modes,
)
from game_predictor_api.domain.jobs import (
    Job,
    JobConflictError,
    JobError,
    JobNotFoundError,
    JobStatus,
    JobType,
    create_job,
    request_job_cancellation,
    requeue_job,
    requeue_job_with_fresh_progress,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.domain.symbol_model_snapshots import (
    SymbolModelJobSnapshot,
    bootstrap_symbol_model_snapshot,
)

PAYOUT_ALGORITHM_VERSION = "payout-v3-unknown-prefix-stop"
# Must match migration 0091 and the immutable v2 recognizer contract.  This
# module cannot import the workflow classifier without an application cycle.
_LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINT = (
    "8b876e8a7cdc25f0709bf27ece4e99b1c777231fa3fcef4aa31e617123825b0f"
)
_IMAGE_GEOMETRY_SYSTEMIC_GUARD_POLICY: dict[str, object] = {
    "policyVersion": "image-geometry-systemic-guard-v2-manual-review",
    "minimumSourceCount": 100,
    "minimumActiveBoardCount": 500,
    "sampleSourceLimit": 25,
    "minimumFinalCellGridReadyRate": 0.98,
    "requireZeroInvariantViolations": True,
}
_PAGE_REGISTRATION_VARIANTS = frozenset({"standard_v0_10", "board_area_test"})
_BOARD_AREA_PREFLIGHT_POLICY_VERSION = "page-geometry-preflight-v3-board-area-mask"
_PAGE_GEOMETRY_REUSE_CONTRACT_VERSION = "page-geometry-entry-reuse-v1"


@dataclass(frozen=True, slots=True)
class LayoutImportRulesReference:
    game_id: UUID
    status: RulesVersionStatus


@dataclass(frozen=True, slots=True)
class BoardTopologyJobReference:
    rules_version_id: UUID
    rows: int
    columns: int


@dataclass(frozen=True, slots=True)
class ImageGeometryRolloutJobReference:
    geometry_mode: str
    cell_asset_mode: str
    revision: int


@dataclass(frozen=True, slots=True)
class PayoutDatasetReference:
    game_id: UUID
    status: DatasetVersionStatus
    rows: int
    columns: int
    expected_layout_count: int
    layout_count: int


@dataclass(frozen=True, slots=True)
class PayoutRulesReference:
    game_id: UUID
    status: RulesVersionStatus
    rows: int
    columns: int


@dataclass(frozen=True, slots=True)
class ImageSelectionJobDeletionReference:
    run_id: UUID
    source_selection_id: UUID
    source_reference_count: int
    has_curated_import_source: bool
    has_published_output: bool


@dataclass(frozen=True, slots=True)
class ImageSelectionJobDeletion:
    job_id: UUID
    run_id: UUID
    managed_run_files_deleted: bool
    source_staging_deleted: bool
    shared_source_staging_preserved: bool


@dataclass(frozen=True, slots=True)
class _QuarantinedDirectory:
    original: Path
    quarantined: Path


@dataclass(frozen=True, slots=True)
class ImageSelectionDeletionQuarantine:
    directories: tuple[_QuarantinedDirectory, ...]


class ImageSelectionDeletionArtifactStore(Protocol):
    def quarantine(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        source_selection_id: UUID,
        delete_source_staging: bool,
    ) -> ImageSelectionDeletionQuarantine: ...

    def finalize(self, quarantine: ImageSelectionDeletionQuarantine) -> None: ...

    def restore(self, quarantine: ImageSelectionDeletionQuarantine) -> None: ...


class ManagedImageSelectionDeletionArtifactStore:
    """Quarantine run-owned files before their database transaction commits."""

    def __init__(self, *, artifact_root: Path, import_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._import_root = import_root.resolve()
        self._manual_root = self._artifact_root / "data" / "working" / "is-manual"
        self._manual_trash = self._artifact_root / "data" / "trash" / "image-selection-deletions"
        self._source_root = self._import_root / "browser-selections"
        self._source_trash = self._import_root / ".trash" / "image-selection-deletions"

    def quarantine(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
        source_selection_id: UUID,
        delete_source_staging: bool,
    ) -> ImageSelectionDeletionQuarantine:
        requested = [
            (
                self._manual_root / run_id.hex[:12],
                self._manual_trash / str(job_id) / "manual",
                self._manual_root,
                self._manual_trash,
            )
        ]
        if delete_source_staging:
            requested.append(
                (
                    self._source_root / str(source_selection_id),
                    self._source_trash / str(job_id) / "source",
                    self._source_root,
                    self._source_trash,
                )
            )
        moved: list[_QuarantinedDirectory] = []
        try:
            for original, quarantined, source_root, trash_root in requested:
                original = original.resolve()
                quarantined = quarantined.resolve()
                if not original.is_relative_to(source_root.resolve()):
                    raise JobConflictError(
                        "IMAGE_SELECTION_JOB_ARTIFACT_PATH_INVALID",
                        "The managed image-selection path is unsafe.",
                    )
                if not quarantined.is_relative_to(trash_root.resolve()):
                    raise JobConflictError(
                        "IMAGE_SELECTION_JOB_ARTIFACT_PATH_INVALID",
                        "The image-selection quarantine path is unsafe.",
                    )
                if not original.exists():
                    continue
                if not original.is_dir() or quarantined.exists():
                    raise JobConflictError(
                        "IMAGE_SELECTION_JOB_ARTIFACT_DELETE_CONFLICT",
                        "Managed image-selection files cannot be quarantined safely.",
                    )
                quarantined.parent.mkdir(parents=True, exist_ok=True)
                original.replace(quarantined)
                moved.append(
                    _QuarantinedDirectory(
                        original=original,
                        quarantined=quarantined,
                    )
                )
        except OSError as error:
            self.restore(ImageSelectionDeletionQuarantine(tuple(moved)))
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_ARTIFACT_DELETE_FAILED",
                "Managed image-selection files could not be quarantined.",
            ) from error
        except JobError:
            self.restore(ImageSelectionDeletionQuarantine(tuple(moved)))
            raise
        return ImageSelectionDeletionQuarantine(tuple(moved))

    def finalize(self, quarantine: ImageSelectionDeletionQuarantine) -> None:
        for item in quarantine.directories:
            if item.quarantined.exists():
                shutil.rmtree(item.quarantined)
            with suppress(OSError):
                item.quarantined.parent.rmdir()

    def restore(self, quarantine: ImageSelectionDeletionQuarantine) -> None:
        for item in reversed(quarantine.directories):
            if not item.quarantined.exists():
                continue
            item.original.parent.mkdir(parents=True, exist_ok=True)
            if item.original.exists():
                raise JobConflictError(
                    "IMAGE_SELECTION_JOB_ARTIFACT_RESTORE_CONFLICT",
                    "Managed image-selection files could not be restored safely.",
                )
            item.quarantined.replace(item.original)


class JobRepository(Protocol):
    def game_exists(self, game_id: UUID) -> bool: ...

    def get_or_pin_board_topology(
        self,
        game_id: UUID,
    ) -> BoardTopologyJobReference | None: ...

    def get_image_geometry_rollout(
        self,
        game_id: UUID,
    ) -> ImageGeometryRolloutJobReference | None: ...

    def get_layout_import_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> LayoutImportRulesReference | None: ...

    def get_payout_dataset_reference(
        self,
        dataset_version_id: UUID,
    ) -> PayoutDatasetReference | None: ...

    def get_payout_rules_reference(
        self,
        rules_version_id: UUID,
    ) -> PayoutRulesReference | None: ...

    def add_job(self, job: Job) -> Job: ...

    def add_source_bound_job(
        self,
        job: Job,
        *,
        source_selection_id: UUID,
    ) -> Job: ...

    def get_job(self, job_id: UUID) -> Job | None: ...

    def get_job_for_update(self, job_id: UUID) -> Job | None: ...

    def get_job_by_input_key(self, input_key: str) -> Job | None: ...

    def get_image_import_by_source_selection(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
    ) -> Job | None: ...

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]: ...

    def save_job(self, job: Job) -> Job: ...

    def get_image_selection_deletion_reference(
        self,
        job_id: UUID,
    ) -> ImageSelectionJobDeletionReference | None: ...

    def delete_image_selection_run_and_job(
        self,
        *,
        job_id: UUID,
        run_id: UUID,
    ) -> None: ...


class SymbolModelSnapshotResolver(Protocol):
    def resolve(self, *, game_id: UUID) -> SymbolModelJobSnapshot: ...

    def resolve_unclassified_cold_start(
        self, *, game_id: UUID
    ) -> SymbolModelJobSnapshot | None: ...


class GridProfileSnapshotResolver(Protocol):
    def resolve(self, *, game_id: UUID) -> dict[str, object]: ...


class PageGeometryOverrideSnapshotResolver(Protocol):
    def snapshot(self, *, game_id: UUID) -> dict[str, object]: ...

    def exclusion_snapshot(
        self, *, game_id: UUID, browser_selection_id: UUID
    ) -> dict[str, object]: ...

    def partial_grid_training_profile(self, *, game_id: UUID) -> dict[str, object] | None: ...


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        import_source_inspector: LayoutImportSourceInspector | None = None,
        symbol_model_snapshot_resolver: SymbolModelSnapshotResolver | None = None,
        grid_profile_snapshot_resolver: GridProfileSnapshotResolver | None = None,
        *,
        artifact_root: Path | None = None,
        page_geometry_override_snapshot_resolver: (
            PageGeometryOverrideSnapshotResolver | None
        ) = None,
        deletion_artifact_store: ImageSelectionDeletionArtifactStore | None = None,
    ) -> None:
        self._repository = repository
        self._import_source_inspector = import_source_inspector
        self._symbol_model_snapshot_resolver = symbol_model_snapshot_resolver
        self._grid_profile_snapshot_resolver = grid_profile_snapshot_resolver
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()
        self._page_geometry_override_snapshot_resolver = page_geometry_override_snapshot_resolver
        self._deletion_artifact_store = deletion_artifact_store
        self._pending_deletion_quarantines: list[ImageSelectionDeletionQuarantine] = []

    def _current_lateral_partial_policy(
        self, *, game_id: UUID, geometry_engine_variant: GeometryEngineVariant | None
    ) -> LateralPartialGeometrySnapshot:
        resolver = self._page_geometry_override_snapshot_resolver
        method = (
            None if resolver is None else getattr(resolver, "partial_grid_training_profile", None)
        )
        payload = method(game_id=game_id) if callable(method) else None
        return LateralPartialGeometrySnapshot(
            training_profile=(
                None if payload is None else PartialGridTrainingProfile.from_payload(payload)
            ),
            # TASK-0561: new runs use the accepted v1/v2 behavior. Pinned v3
            # snapshots remain replayable through from_payload().
            frame_support_review=(
                geometry_engine_variant is GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
            ),
            selective_frame_review=(
                geometry_engine_variant is GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
            ),
        )

    @staticmethod
    def _geometry_variant_matches_pinned_lateral_snapshot(
        value: object,
        *,
        geometry_engine_variant: GeometryEngineVariant | None,
    ) -> bool:
        """Match a run variant without rebinding its immutable training profile."""

        if geometry_engine_variant is None:
            return value is None
        try:
            pinned = LateralPartialGeometrySnapshot.from_payload(value)
        except LateralPartialContractError:
            return False
        return pinned.selective_frame_review == (
            geometry_engine_variant is GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
        )

    def current_image_import_engine_policy(
        self, *, game_id: UUID
    ) -> ImageImportEnginePolicySnapshot:
        reference = self._repository.get_image_geometry_rollout(game_id)
        geometry_mode = "legacy" if reference is None else reference.geometry_mode
        cell_asset_mode = "legacy_files" if reference is None else reference.cell_asset_mode
        revision = 0 if reference is None else reference.revision
        try:
            policy = policy_from_rollout_modes(geometry_mode, cell_asset_mode)
        except ValueError as error:
            raise JobError(
                "IMAGE_ENGINE_POLICY_UNSUPPORTED_STATE",
                "The game uses an image engine state that is not available for new imports.",
            ) from error
        return ImageImportEnginePolicySnapshot(
            game_id=game_id,
            policy=policy,
            geometry_mode=geometry_mode,
            cell_asset_mode=cell_asset_mode,
            revision=revision,
        )

    def _pin_image_geometry_rollout(
        self,
        *,
        game_id: UUID,
        input_payload: dict[str, object],
        effective_fingerprint: str,
        symbol_model: SymbolModelJobSnapshot,
        geometry_engine_variant: GeometryEngineVariant | None = None,
        lateral_partial_geometry: LateralPartialGeometrySnapshot | None = None,
    ) -> str:
        getter = getattr(self._repository, "get_image_geometry_rollout", None)
        reference = getter(game_id) if callable(getter) else None
        snapshot = GeometryPipelineRolloutSnapshot(
            geometry_mode=GeometryRolloutMode(
                GeometryRolloutMode.STRUCTURED_LATTICE_V3.value
                if geometry_engine_variant is not None
                else "legacy"
                if reference is None
                else reference.geometry_mode
            ),
            cell_asset_mode=CellAssetRolloutMode(
                CellAssetRolloutMode.VIRTUAL_DEFAULT.value
                if geometry_engine_variant is not None
                else "legacy_files"
                if reference is None
                else reference.cell_asset_mode
            ),
            rollout_revision=0 if reference is None else reference.revision,
            geometry_engine_version=(
                STRUCTURED_OPENCV_INDEPENDENT_BOARD_VERSION
                if geometry_engine_variant is None
                and (
                    reference is None or reference.geometry_mode == GeometryRolloutMode.LEGACY.value
                )
                else STRUCTURED_OPENCV_PINNED_PREFLIGHT_VERSION
            ),
            virtual_renderer_version=VIRTUAL_CELL_RENDERER_VERSION,
            preprocessing_version=SYMBOL_RGB_PREPROCESSING_VERSION,
            candidate_geometry=(
                StructuredGeometryCandidateSnapshot.from_config_payload(
                    structured_lattice_candidate_config_payload()
                )
                if geometry_engine_variant is None
                and reference is not None
                and reference.geometry_mode == GeometryRolloutMode.STRUCTURED_SHADOW.value
                else None
            ),
            active_lattice_geometry=(
                StructuredGeometryActivationSnapshot.from_config_payload(
                    structured_lattice_active_config_payload()
                )
                if geometry_engine_variant is not None
                or reference is not None
                and reference.geometry_mode == GeometryRolloutMode.STRUCTURED_LATTICE_V3.value
                else None
            ),
            lateral_partial_geometry=(
                (
                    lateral_partial_geometry
                    or self._current_lateral_partial_policy(
                        game_id=game_id,
                        geometry_engine_variant=geometry_engine_variant,
                    )
                )
                if geometry_engine_variant is not None
                else None
            ),
        )
        if not snapshot.is_legacy and "board_cell_processing" not in input_payload:
            topology_reference = self._repository.get_or_pin_board_topology(game_id)
            if topology_reference is None:
                raise JobError(
                    "GAME_BOARD_TOPOLOGY_REQUIRED",
                    "A rules version must define board dimensions before boards can be imported.",
                )
            if (topology_reference.rows, topology_reference.columns) != (3, 5):
                raise JobError(
                    "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED",
                    "The structured geometry adapter currently supports only 3x5 boards.",
                )
            processing = board_cell_processing_snapshot(
                cell_output_size=symbol_model.input_size,
                topology=BoardCellTopology(
                    rows=topology_reference.rows,
                    columns=topology_reference.columns,
                    rules_version_id=str(topology_reference.rules_version_id),
                ),
            )
            input_payload["board_cell_processing"] = processing
            effective_fingerprint = hashlib.sha256(
                (f"{effective_fingerprint}:{processing['configurationFingerprintSha256']}").encode(
                    "ascii"
                )
            ).hexdigest()
        input_payload["image_geometry_rollout"] = snapshot.to_payload()
        return effective_pipeline_fingerprint(effective_fingerprint, snapshot)

    def create_job(
        self,
        job_type: JobType,
        *,
        game_id: UUID | None,
        input_payload: dict[str, object],
    ) -> Job:
        if job_type in {JobType.IMPORT, JobType.IMAGE_SELECTION}:
            code = (
                "IMPORT_SOURCE_NOT_ATTESTED"
                if job_type is JobType.IMPORT
                else "IMAGE_SELECTION_SOURCE_PURPOSE_INVALID"
            )
            raise JobError(
                code,
                "Source-bound jobs must be created through their validated workflow.",
            )
        return self._persist_job(
            job_type,
            game_id=game_id,
            input_payload=input_payload,
        )

    def create_layout_import_job(
        self,
        *,
        game_id: UUID,
        source_path: str,
        contract_version: int,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        if self._import_source_inspector is None:
            raise JobError(
                "IMPORT_ROOT_NOT_CONFIGURED",
                "The import source inspector is not configured.",
            )
        source = self._import_source_inspector.inspect(
            source_path,
            contract_version=contract_version,
        )
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "import_kind": "layout_file",
                "source_path": source.relative_path,
                "source_checksum": source.checksum,
                "source_size_bytes": source.size_bytes,
                "file_format": source.file_format.value,
                "contract_version": source.contract_version,
            },
            game_already_validated=True,
        )

    def create_image_import_job(
        self,
        *,
        game_id: UUID,
        selection_id: UUID,
        source_directory: Path,
        source_display_name: str,
        pipeline_fingerprint: str,
        image_selection_run_id: UUID | None = None,
        canonical_sequence_numbers: Sequence[int] | None = None,
        source_manifest_sha256: str | None = None,
        source_exclusions: dict[str, object] | None = None,
        start_mode: str | None = None,
        previous_job_id: UUID | None = None,
        page_geometry_manifest: dict[str, object] | None = None,
        geometry_guard_resolution_manifest: dict[str, object] | None = None,
        use_verified_board_cell_geometry: bool = False,
        allow_unclassified_symbol_cold_start: bool = False,
        geometry_engine_variant: GeometryEngineVariant | None = None,
    ) -> Job:
        # Do not persist an executable v4 job before its detector and acceptance.
        try:
            require_geometry_engine_variant_available(geometry_engine_variant)
        except LateralPartialContractError as error:
            raise JobError(error.code, str(error)) from error
        lateral_partial_geometry: LateralPartialGeometrySnapshot | None = None
        if geometry_engine_variant is not None:
            if geometry_guard_resolution_manifest is not None:
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED",
                    "v0.10.4 cannot silently rebind a v3 guard resolution manifest.",
                )
            existing = self.require_lateral_browser_source_history(
                game_id=game_id, source_selection_id=selection_id
            )
            if existing is not None:
                previous_rollout = existing.input_payload.get("image_geometry_rollout")
                if (
                    isinstance(previous_rollout, Mapping)
                    and previous_rollout.get("lateralPartialGeometry") is not None
                ):
                    # Keep the original lineage on retries, not the newly
                    # created v4 job, or every click would create another run.
                    previous = existing.input_payload.get("previous_job_id")
                    previous_job_id = UUID(str(previous)) if previous is not None else None
                else:
                    previous_job_id = existing.id
            lateral_partial_geometry = self._require_lateral_preflight(
                page_geometry_manifest,
                game_id=game_id,
                selection_id=selection_id,
                source_manifest_sha256=source_manifest_sha256,
                geometry_engine_variant=geometry_engine_variant,
            )
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        try:
            resolved = source_directory.resolve(strict=True)
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_NOT_FOUND",
                "The selected image folder does not exist or is unavailable.",
            ) from error
        if not resolved.is_dir():
            raise JobError(
                "IMAGE_FOLDER_NOT_DIRECTORY",
                "The selected image source must be a directory.",
            )
        symbol_model = self._resolve_import_symbol_snapshot(
            game_id=game_id,
            allow_unclassified_cold_start=allow_unclassified_symbol_cold_start,
        )
        effective_pipeline_fingerprint = hashlib.sha256(
            f"{pipeline_fingerprint}:{symbol_model.inference_fingerprint}".encode("ascii")
        ).hexdigest()
        input_payload: dict[str, object] = {
            "schema_version": 2 if start_mode is None else 7,
            "import_kind": "image_directory",
            "source_selection_id": str(selection_id),
            "source_directory": str(resolved),
            "source_display_name": source_display_name,
            "pipeline_fingerprint": effective_pipeline_fingerprint,
            "source_pipeline_fingerprint": pipeline_fingerprint,
            "normalization_adapter_version": CURRENT_NORMALIZATION_ADAPTER_VERSION,
            "symbol_model": symbol_model.to_payload(),
        }
        if start_mode is not None:
            if page_geometry_manifest is None:
                raise JobError(
                    "IMAGE_PAGE_GEOMETRY_PREFLIGHT_REQUIRED",
                    "A new browser import requires a pinned page geometry manifest.",
                )
            grid_profile = (
                _baseline_grid_profile_snapshot()
                if self._grid_profile_snapshot_resolver is None
                else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
            )
            grid_fingerprint = grid_profile.get("inferenceFingerprint")
            if not isinstance(grid_fingerprint, str) or len(grid_fingerprint) != 64:
                raise JobError(
                    "GRID_PROFILE_SNAPSHOT_INVALID",
                    "The active grid profile snapshot is invalid.",
                )
            effective_pipeline_fingerprint = hashlib.sha256(
                (
                    f"{pipeline_fingerprint}:{symbol_model.inference_fingerprint}:{grid_fingerprint}:"
                    f"{_page_geometry_manifest_fingerprint(page_geometry_manifest)}:"
                    f"{_geometry_guard_resolution_manifest_fingerprint(geometry_guard_resolution_manifest)}:"
                    f"{_source_exclusions_fingerprint(source_exclusions)}"
                ).encode("ascii")
            ).hexdigest()
            input_payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
            input_payload["start_mode"] = start_mode
            input_payload["source_exclusions"] = dict(source_exclusions or {})
            input_payload["previous_job_id"] = (
                None if previous_job_id is None else str(previous_job_id)
            )
            input_payload["grid_profile"] = grid_profile
            if page_geometry_manifest is not None:
                input_payload["page_geometry_manifest"] = dict(page_geometry_manifest)
            if geometry_guard_resolution_manifest is not None:
                input_payload["geometry_guard_resolution_manifest"] = dict(
                    geometry_guard_resolution_manifest
                )
            input_payload["geometry_systemic_guard_policy"] = dict(
                _IMAGE_GEOMETRY_SYSTEMIC_GUARD_POLICY
            )
            effective_pipeline_fingerprint = _bind_geometry_guard_policy(
                effective_pipeline_fingerprint
            )
        if use_verified_board_cell_geometry:
            topology_reference = self._repository.get_or_pin_board_topology(game_id)
            if topology_reference is None:
                raise JobError(
                    "GAME_BOARD_TOPOLOGY_REQUIRED",
                    "A rules version must define board dimensions before boards can be imported.",
                )
            if (topology_reference.rows, topology_reference.columns) != (3, 5):
                raise JobError(
                    "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED",
                    "The active v20 geometry adapter supports only 3x5 boards.",
                    details={
                        "rows": topology_reference.rows,
                        "columns": topology_reference.columns,
                        "topologyRulesVersionId": str(topology_reference.rules_version_id),
                    },
                )
            processing_snapshot = board_cell_processing_snapshot(
                cell_output_size=symbol_model.input_size,
                topology=BoardCellTopology(
                    rows=topology_reference.rows,
                    columns=topology_reference.columns,
                    rules_version_id=str(topology_reference.rules_version_id),
                ),
            )
            configuration_fingerprint = processing_snapshot["configurationFingerprintSha256"]
            if not isinstance(configuration_fingerprint, str):
                raise JobError(
                    "IMAGE_BOARD_CELL_PROCESSING_SNAPSHOT_INVALID",
                    "The verified board-cell processing snapshot is invalid.",
                )
            effective_pipeline_fingerprint = hashlib.sha256(
                f"{effective_pipeline_fingerprint}:{configuration_fingerprint}".encode("ascii")
            ).hexdigest()
            input_payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
            input_payload["board_cell_processing"] = processing_snapshot
        # The verified v19 board-cell path is the immutable v20 pipeline.
        # It owns its geometry and crop snapshot in ``board_cell_processing``;
        # querying the newer per-game virtual-geometry rollout here would both
        # change that contract and make the historical v20 import depend on
        # the v0.10 rollout tables.
        if not use_verified_board_cell_geometry:
            effective_pipeline_fingerprint = self._pin_image_geometry_rollout(
                game_id=game_id,
                input_payload=input_payload,
                effective_fingerprint=effective_pipeline_fingerprint,
                symbol_model=symbol_model,
                geometry_engine_variant=geometry_engine_variant,
                lateral_partial_geometry=lateral_partial_geometry,
            )
        input_payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
        if image_selection_run_id is not None:
            input_payload["image_selection_run_id"] = str(image_selection_run_id)
        if canonical_sequence_numbers is not None:
            input_payload["canonical_sequence_numbers"] = sorted(
                {int(number) for number in canonical_sequence_numbers if int(number) > 0}
            )
        if source_manifest_sha256 is not None:
            input_payload["source_manifest_sha256"] = source_manifest_sha256
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload=input_payload,
            game_already_validated=True,
        )

    def _resolve_import_symbol_snapshot(
        self,
        *,
        game_id: UUID,
        allow_unclassified_cold_start: bool,
    ) -> SymbolModelJobSnapshot:
        if self._symbol_model_snapshot_resolver is None:
            return bootstrap_symbol_model_snapshot()
        try:
            return self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        except JobConflictError as error:
            if (
                not allow_unclassified_cold_start
                or error.code != "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED"
            ):
                raise
            snapshot = self._symbol_model_snapshot_resolver.resolve_unclassified_cold_start(
                game_id=game_id
            )
            if snapshot is None:
                raise
            return snapshot

    def _require_lateral_preflight(
        self,
        descriptor: object,
        *,
        game_id: UUID,
        selection_id: UUID,
        source_manifest_sha256: str | None,
        geometry_engine_variant: GeometryEngineVariant,
    ) -> LateralPartialGeometrySnapshot:
        from game_predictor_worker.images.lateral_partial_artifact import load_lateral_manifest

        if self._artifact_root is None or source_manifest_sha256 is None:
            raise JobConflictError(
                "IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED",
                "v0.10.4 requires a compatible immutable preflight; no upload is required.",
            )
        try:
            if not isinstance(descriptor, Mapping):
                raise ValueError("Invalid descriptor.")
            preflight = self._repository.get_job(UUID(str(descriptor.get("preflightJobId"))))
            if preflight is None:
                raise ValueError("The preflight job is missing.")
            policy = LateralPartialGeometrySnapshot.from_payload(
                preflight.input_payload.get("lateral_partial_geometry")
            )
            if policy.selective_frame_review != (
                geometry_engine_variant is GeometryEngineVariant.SELECTIVE_BOARD_REVIEW_V1_1
            ):
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_ARTIFACT_INVALID",
                    "The pinned preflight uses a different geometry engine variant.",
                )
            load_lateral_manifest(
                self._artifact_root,
                descriptor,
                game_id=str(game_id),
                source_selection_id=str(selection_id),
                source_manifest_sha256=source_manifest_sha256,
                policy=policy,
            )
            if (
                preflight.game_id != game_id
                or preflight.status is not JobStatus.COMPLETED
                or preflight.input_payload.get("source_selection_id") != str(selection_id)
                or preflight.input_payload.get("source_manifest_sha256") != source_manifest_sha256
                or preflight.input_payload.get("lateral_partial_geometry") != policy.to_payload()
                or not isinstance(preflight.checkpoint_payload, Mapping)
                or preflight.checkpoint_payload.get("geometry_manifest_checksum_sha256")
                != descriptor.get("checksumSha256")
            ):
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_PREFLIGHT_REQUIRED",
                    "The preflight did not pin v0.10.4 evidence.",
                )
            return policy
        except LateralPartialContractError as error:
            raise JobConflictError(error.code, str(error)) from error
        except JobConflictError:
            raise
        except ValueError as error:
            raise JobConflictError("IMAGE_LATERAL_PARTIAL_ARTIFACT_INVALID", str(error)) from error

    def create_pending_symbol_reinference_job(self, *, game_id: UUID) -> Job:
        """Create an explicit job that may update pending symbol predictions only."""

        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        snapshot = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        return self._persist_job(
            JobType.IMAGE_SYMBOL_REINFERENCE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "inference_kind": "pending_symbols_only",
                "symbol_model": snapshot.to_payload(),
            },
            game_already_validated=True,
        )

    def create_pending_grid_reinference_job(self, *, game_id: UUID) -> Job:
        """Create a pinned v19 recrop job for unresolved boards only."""

        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        symbol_model = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        recrop_snapshot = board_cell_recrop_snapshot(cell_output_size=symbol_model.input_size)
        return self._persist_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=game_id,
            input_payload={
                "schema_version": 2,
                "inference_kind": "pending_grid_only",
                "cell_output_size": symbol_model.input_size,
                "board_cell_recrop": recrop_snapshot,
            },
            game_already_validated=True,
        )

    def create_curated_image_import_job(
        self,
        *,
        game_id: UUID,
        source_id: UUID,
        batch_id: UUID,
        source_directory: Path,
        source_display_name: str,
        manifest_relative_path: str,
        manifest_checksum_sha256: str,
        entry_start: int,
        entry_count: int,
        image_selection_run_id: UUID,
        pipeline_fingerprint: str,
        grid_profile: dict[str, object] | None = None,
    ) -> Job:
        """Create a job pinned to one verified, ordered curated-manifest slice."""

        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        try:
            resolved = source_directory.resolve(strict=True)
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_NOT_FOUND",
                "The curated image output does not exist or is unavailable.",
            ) from error
        if not resolved.is_dir():
            raise JobError(
                "IMAGE_FOLDER_NOT_DIRECTORY",
                "The curated image source must be a directory.",
            )
        if entry_start < 0 or entry_count < 1:
            raise JobError(
                "CURATED_IMAGE_IMPORT_RANGE_INVALID",
                "The curated image manifest slice is invalid.",
            )
        symbol_model = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        pinned_grid_profile = grid_profile or (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
        )
        grid_fingerprint = pinned_grid_profile.get("inferenceFingerprint")
        if not isinstance(grid_fingerprint, str) or len(grid_fingerprint) != 64:
            raise JobError(
                "GRID_PROFILE_SNAPSHOT_INVALID",
                "The pinned grid profile snapshot is invalid.",
            )
        effective_pipeline_fingerprint = hashlib.sha256(
            (
                f"{pipeline_fingerprint}:{symbol_model.inference_fingerprint}:"
                f"{grid_fingerprint}:{manifest_checksum_sha256}:"
                f"{entry_start}:{entry_count}"
            ).encode("ascii")
        ).hexdigest()
        input_payload: dict[str, object] = {
            "schema_version": 3,
            "import_kind": "image_directory",
            "source_selection_id": str(source_id),
            "source_directory": str(resolved),
            "source_display_name": source_display_name,
            "pipeline_fingerprint": effective_pipeline_fingerprint,
            "source_pipeline_fingerprint": pipeline_fingerprint,
            "normalization_adapter_version": CURRENT_NORMALIZATION_ADAPTER_VERSION,
            "image_selection_run_id": str(image_selection_run_id),
            "curated_image_import_source_id": str(source_id),
            "curated_image_import_batch_id": str(batch_id),
            "curated_manifest_relative_path": manifest_relative_path,
            "curated_manifest_checksum_sha256": manifest_checksum_sha256,
            "curated_manifest_entry_start": entry_start,
            "curated_manifest_entry_count": entry_count,
            "symbol_model": symbol_model.to_payload(),
            "grid_profile": pinned_grid_profile,
        }
        effective_pipeline_fingerprint = self._pin_image_geometry_rollout(
            game_id=game_id,
            input_payload=input_payload,
            effective_fingerprint=effective_pipeline_fingerprint,
            symbol_model=symbol_model,
        )
        input_payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload=input_payload,
            game_already_validated=True,
        )

    def create_managed_image_reprocess_job(
        self,
        source_job_id: UUID,
        *,
        pipeline_fingerprint: str,
        continue_with_manual_geometry: bool = False,
        geometry_engine_variant: GeometryEngineVariant | None = None,
        page_geometry_manifest: Mapping[str, object] | None = None,
    ) -> Job:
        """Create a new import pinned to an earlier job's managed originals."""

        try:
            require_geometry_engine_variant_available(geometry_engine_variant)
        except LateralPartialContractError as error:
            raise JobConflictError(error.code, str(error)) from error
        if geometry_engine_variant is not None and continue_with_manual_geometry:
            raise JobConflictError(
                "IMAGE_REPROCESS_MODE_CONFLICT", "Choose a new engine or historical continuation."
            )
        if page_geometry_manifest is not None and geometry_engine_variant is None:
            raise JobConflictError(
                "IMAGE_REPROCESS_MODE_CONFLICT", "A replacement preflight requires v0.10.4."
            )

        source = self.get_job(source_job_id)
        if (
            source.job_type is not JobType.IMPORT
            or source.input_payload.get("import_kind") != "image_directory"
            or source.game_id is None
        ):
            raise JobConflictError(
                "IMAGE_REPROCESS_SOURCE_TYPE_INVALID",
                "Only an image-directory import can be reprocessed.",
            )
        if source.status in {JobStatus.CREATED, JobStatus.PROCESSING}:
            raise JobConflictError(
                "IMAGE_REPROCESS_SOURCE_ACTIVE",
                "An active image import cannot be reprocessed.",
            )
        if geometry_engine_variant is not None:
            self._require_no_unreplayed_guard_decisions(source)
        if self._artifact_root is None:
            raise JobConflictError(
                "IMAGE_REPROCESS_PAGE_GEOMETRY_MANIFEST_REQUIRED",
                "Managed v0.10 reprocessing requires configured immutable artifacts.",
            )
        try:
            evidence = resolve_managed_reprocess_evidence(
                source,
                artifact_root=self._artifact_root,
                get_job=self._repository.get_job,
                page_geometry_manifest=page_geometry_manifest,
            )
        except ManagedReprocessEvidenceError as error:
            raise JobConflictError(error.code, error.message) from error
        if geometry_engine_variant is not None:
            self._require_lateral_preflight(
                evidence.page_geometry_manifest,
                game_id=source.game_id,
                selection_id=evidence.source_selection_id,
                source_manifest_sha256=evidence.source_manifest_sha256,
                geometry_engine_variant=geometry_engine_variant,
            )
        source_directory = source.input_payload.get("source_directory")
        if not isinstance(source_directory, str) or not source_directory:
            raise JobConflictError(
                "IMAGE_REPROCESS_SOURCE_INVALID",
                "The source image import has no managed source provenance.",
            )
        if continue_with_manual_geometry:
            if (
                source.status is not JobStatus.FAILED
                or source.error_code != "IMAGE_GEOMETRY_SYSTEMIC_REGRESSION"
            ):
                raise JobConflictError(
                    "IMAGE_REPROCESS_MANUAL_CONTINUATION_NOT_AVAILABLE",
                    "Manual continuation requires an import stopped by its geometry quality guard.",
                )
            required_snapshots = (
                "symbol_model",
                "grid_profile",
                "board_cell_processing",
                "image_geometry_rollout",
            )
            if any(
                not isinstance(source.input_payload.get(key), dict) for key in required_snapshots
            ):
                raise JobConflictError(
                    "IMAGE_REPROCESS_PINNED_SNAPSHOTS_REQUIRED",
                    "Manual continuation requires the original model and geometry snapshots.",
                )
            continuation: dict[str, object] = {
                key: source.input_payload[key] for key in required_snapshots
            }
            for key in ("normalization_adapter_version", "image_selection_run_id"):
                if key in source.input_payload:
                    continuation[key] = source.input_payload[key]
            continuation.update(
                {
                    "schema_version": 6,
                    "import_kind": "image_directory",
                    "source_selection_id": str(evidence.source_selection_id),
                    "source_directory": source_directory,
                    "source_display_name": str(
                        source.input_payload.get("source_display_name") or "Import obrazów"
                    )[:210]
                    + " (kontynuacja z ręczną korektą)",
                    "source_pipeline_fingerprint": source.input_payload.get(
                        "source_pipeline_fingerprint", source.input_payload["pipeline_fingerprint"]
                    ),
                    "managed_source_job_id": str(source.id),
                    "managed_source_manifest_checksum_sha256": (
                        evidence.managed_source_manifest_checksum_sha256
                    ),
                    "source_manifest_sha256": evidence.source_manifest_sha256,
                    "page_geometry_manifest": evidence.page_geometry_manifest,
                    "geometry_systemic_guard_policy": dict(_IMAGE_GEOMETRY_SYSTEMIC_GUARD_POLICY),
                }
            )
            fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        **continuation,
                        "sourceRunFingerprint": source.input_payload["pipeline_fingerprint"],
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=True,
                ).encode("ascii")
            ).hexdigest()
            continuation["pipeline_fingerprint"] = fingerprint
            try:
                return self._persist_job(
                    JobType.IMPORT,
                    game_id=source.game_id,
                    input_payload=continuation,
                    game_already_validated=True,
                )
            except JobConflictError as error:
                if error.code != "JOB_INPUT_ALREADY_EXISTS":
                    raise
                key = create_job(
                    JobType.IMPORT, game_id=source.game_id, input_payload=continuation
                ).input_key
                existing = self._repository.get_job_by_input_key(key)
                if existing is None:
                    raise
                return existing
        symbol_model = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=source.game_id)
        )
        grid_profile = (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=source.game_id)
        )
        grid_fingerprint = grid_profile.get("inferenceFingerprint")
        if not isinstance(grid_fingerprint, str) or len(grid_fingerprint) != 64:
            raise JobError(
                "GRID_PROFILE_SNAPSHOT_INVALID",
                "The pinned grid profile snapshot is invalid.",
            )
        effective_pipeline_fingerprint = hashlib.sha256(
            (
                f"{pipeline_fingerprint}:{symbol_model.inference_fingerprint}:"
                f"{grid_fingerprint}:{source.id}:"
                f"{evidence.managed_source_manifest_checksum_sha256}:"
                f"{evidence.page_geometry_manifest['checksumSha256']}"
            ).encode("ascii")
        ).hexdigest()
        payload: dict[str, object] = {
            "schema_version": 6,
            "import_kind": "image_directory",
            "source_selection_id": str(evidence.source_selection_id),
            "source_directory": source_directory,
            "source_display_name": (
                f"{source.input_payload.get('source_display_name') or 'Import obrazów'} "
                "(ponowne przetworzenie)"
            ),
            "pipeline_fingerprint": effective_pipeline_fingerprint,
            "source_pipeline_fingerprint": pipeline_fingerprint,
            "normalization_adapter_version": CURRENT_NORMALIZATION_ADAPTER_VERSION,
            "managed_source_job_id": str(source.id),
            "managed_source_manifest_checksum_sha256": (
                evidence.managed_source_manifest_checksum_sha256
            ),
            "source_manifest_sha256": evidence.source_manifest_sha256,
            "page_geometry_manifest": evidence.page_geometry_manifest,
            "symbol_model": symbol_model.to_payload(),
            "grid_profile": grid_profile,
        }
        topology_reference = self._repository.get_or_pin_board_topology(source.game_id)
        if topology_reference is None:
            raise JobError(
                "GAME_BOARD_TOPOLOGY_REQUIRED",
                "A rules version must define board dimensions before boards can be imported.",
            )
        if (topology_reference.rows, topology_reference.columns) != (3, 5):
            raise JobError(
                "IMAGE_PIPELINE_TOPOLOGY_UNSUPPORTED",
                "The active v20 geometry adapter supports only 3x5 boards.",
                details={
                    "rows": topology_reference.rows,
                    "columns": topology_reference.columns,
                    "topologyRulesVersionId": str(topology_reference.rules_version_id),
                },
            )
        processing_snapshot = board_cell_processing_snapshot(
            cell_output_size=symbol_model.input_size,
            topology=BoardCellTopology(
                rows=topology_reference.rows,
                columns=topology_reference.columns,
                rules_version_id=str(topology_reference.rules_version_id),
            ),
        )
        configuration_fingerprint = processing_snapshot["configurationFingerprintSha256"]
        if not isinstance(configuration_fingerprint, str):
            raise JobError(
                "IMAGE_BOARD_CELL_PROCESSING_SNAPSHOT_INVALID",
                "The verified board-cell processing snapshot is invalid.",
            )
        effective_pipeline_fingerprint = hashlib.sha256(
            f"{effective_pipeline_fingerprint}:{configuration_fingerprint}".encode("ascii")
        ).hexdigest()
        payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
        payload["board_cell_processing"] = processing_snapshot
        payload["geometry_systemic_guard_policy"] = dict(_IMAGE_GEOMETRY_SYSTEMIC_GUARD_POLICY)
        effective_pipeline_fingerprint = _bind_geometry_guard_policy(effective_pipeline_fingerprint)
        effective_pipeline_fingerprint = self._pin_image_geometry_rollout(
            game_id=source.game_id,
            input_payload=payload,
            effective_fingerprint=effective_pipeline_fingerprint,
            symbol_model=symbol_model,
            geometry_engine_variant=geometry_engine_variant,
        )
        payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
        image_selection_run_id = source.input_payload.get("image_selection_run_id")
        if image_selection_run_id is not None:
            payload["image_selection_run_id"] = image_selection_run_id
        try:
            return self._persist_job(
                JobType.IMPORT,
                game_id=source.game_id,
                input_payload=payload,
                game_already_validated=True,
            )
        except JobConflictError as error:
            if geometry_engine_variant is None or error.code != "JOB_INPUT_ALREADY_EXISTS":
                raise
            key = create_job(
                JobType.IMPORT, game_id=source.game_id, input_payload=payload
            ).input_key
            existing = self._repository.get_job_by_input_key(key)
            if existing is None:
                raise
            return existing

    def create_layout_import_validation_job(
        self,
        *,
        game_id: UUID,
        import_job_id: UUID,
        rules_version_id: UUID,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        import_job = self._repository.get_job(import_job_id)
        if import_job is None or import_job.job_type is not JobType.IMPORT:
            raise JobNotFoundError(
                "LAYOUT_IMPORT_JOB_NOT_FOUND",
                "The referenced layout import job does not exist.",
                details={"importJobId": str(import_job_id)},
            )
        if import_job.game_id != game_id:
            raise JobConflictError(
                "LAYOUT_IMPORT_GAME_MISMATCH",
                "The referenced import job belongs to a different game.",
            )
        if import_job.status is not JobStatus.COMPLETED:
            raise JobConflictError(
                "LAYOUT_IMPORT_NOT_COMPLETED",
                "The referenced import job must be completed before validation.",
            )
        rules = self._repository.get_layout_import_rules_reference(rules_version_id)
        if rules is None:
            raise JobNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "The selected rules version does not exist.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        if rules.game_id != game_id:
            raise JobConflictError(
                "LAYOUT_IMPORT_RULES_GAME_MISMATCH",
                "The selected rules version belongs to a different game.",
            )
        if rules.status is not RulesVersionStatus.PUBLISHED:
            raise JobConflictError(
                "RULES_VERSION_NOT_PUBLISHED",
                "The selected rules version must be published.",
            )
        return self._persist_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "validation_kind": "layout_import",
                "import_job_id": str(import_job_id),
                "rules_version_id": str(rules_version_id),
            },
            game_already_validated=True,
        )

    def create_geometry_guard_report_reconstruction_job(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
        source_guard_job_id: UUID,
        legacy_report_checksum_sha256: str,
        source_manifest_checksum_sha256: str,
        page_geometry_manifest_checksum_sha256: str,
    ) -> Job:
        source = self._repository.get_job(source_guard_job_id)
        if source is None or source.job_type is not JobType.IMPORT:
            raise JobNotFoundError(
                "IMAGE_GEOMETRY_GUARD_SOURCE_JOB_NOT_FOUND",
                "The source geometry guard import job does not exist.",
            )
        if source.game_id != game_id:
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_SOURCE_GAME_MISMATCH",
                "The source geometry guard import belongs to another game.",
            )
        if source.input_payload.get("source_selection_id") != str(source_selection_id):
            raise JobConflictError(
                "IMAGE_GEOMETRY_GUARD_SOURCE_STAGING_MISMATCH",
                "The source geometry guard import belongs to another browser staging.",
            )
        return self._persist_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "validation_kind": "image_geometry_guard_report_reconstruction",
                "source_selection_id": str(source_selection_id),
                "source_guard_job_id": str(source_guard_job_id),
                "legacy_report_checksum_sha256": legacy_report_checksum_sha256,
                "source_manifest_checksum_sha256": source_manifest_checksum_sha256,
                "page_geometry_manifest_checksum_sha256": (page_geometry_manifest_checksum_sha256),
            },
            game_already_validated=True,
        )

    def create_payout_job(
        self,
        *,
        game_id: UUID,
        dataset_version_id: UUID,
        rules_version_id: UUID,
        algorithm_version: str,
    ) -> Job:
        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        if algorithm_version != PAYOUT_ALGORITHM_VERSION:
            raise JobError(
                "UNSUPPORTED_PAYOUT_ALGORITHM",
                f"Only {PAYOUT_ALGORITHM_VERSION} is supported.",
                details={"algorithmVersion": algorithm_version},
            )

        dataset = self._repository.get_payout_dataset_reference(dataset_version_id)
        if dataset is None:
            raise JobNotFoundError(
                "DATASET_VERSION_NOT_FOUND",
                "Dataset version does not exist.",
                details={"datasetVersionId": str(dataset_version_id)},
            )
        rules = self._repository.get_payout_rules_reference(rules_version_id)
        if rules is None:
            raise JobNotFoundError(
                "RULES_VERSION_NOT_FOUND",
                "Rules version does not exist.",
                details={"rulesVersionId": str(rules_version_id)},
            )
        if dataset.game_id != game_id or rules.game_id != game_id:
            raise JobConflictError(
                "PAYOUT_GAME_MISMATCH",
                "Dataset, rules and job must belong to the same game.",
            )
        if dataset.status is not DatasetVersionStatus.PUBLISHED:
            raise JobConflictError(
                "PAYOUT_DATASET_NOT_PUBLISHED",
                "The selected dataset must be published.",
            )
        if rules.status is not RulesVersionStatus.PUBLISHED:
            raise JobConflictError(
                "PAYOUT_RULES_NOT_PUBLISHED",
                "The selected rules version must be published.",
            )
        if (dataset.rows, dataset.columns) != (rules.rows, rules.columns):
            raise JobConflictError(
                "PAYOUT_DIMENSIONS_MISMATCH",
                "Dataset and rules dimensions must match.",
                details={
                    "datasetRows": dataset.rows,
                    "datasetColumns": dataset.columns,
                    "rulesRows": rules.rows,
                    "rulesColumns": rules.columns,
                },
            )
        if dataset.layout_count == 0:
            raise JobConflictError(
                "PAYOUT_DATASET_EMPTY",
                "The selected dataset does not contain layouts.",
            )
        if dataset.layout_count != dataset.expected_layout_count:
            raise JobConflictError(
                "PAYOUT_DATASET_INCOMPLETE",
                "The selected dataset has missing or excess layouts.",
                details={
                    "expectedLayoutCount": dataset.expected_layout_count,
                    "layoutCount": dataset.layout_count,
                },
            )

        return self._persist_job(
            JobType.PAYOUT,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "dataset_version_id": str(dataset_version_id),
                "rules_version_id": str(rules_version_id),
                "algorithm_version": algorithm_version,
            },
            game_already_validated=True,
        )

    def _persist_job(
        self,
        job_type: JobType,
        *,
        game_id: UUID | None,
        input_payload: dict[str, object],
        game_already_validated: bool = False,
    ) -> Job:
        if (
            game_id is not None
            and not game_already_validated
            and not self._repository.game_exists(game_id)
        ):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        job = create_job(
            job_type,
            game_id=game_id,
            input_payload=input_payload,
        )
        existing = self._repository.get_job_by_input_key(job.input_key)
        if existing is not None:
            raise JobConflictError(
                "JOB_INPUT_ALREADY_EXISTS",
                "A job with the same type and input already exists.",
                details={"existingJobId": str(existing.id)},
            )
        source_selection_id = input_payload.get("source_selection_id")
        if isinstance(source_selection_id, str):
            try:
                selection_id = UUID(source_selection_id)
            except ValueError as error:
                raise JobError(
                    "IMAGE_FOLDER_SELECTION_ID_INVALID",
                    "The source selection identifier is invalid.",
                ) from error
            return self._repository.add_source_bound_job(
                job,
                source_selection_id=selection_id,
            )
        return self._repository.add_job(job)

    def get_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        return job

    def get_job_by_input_key(self, input_key: str) -> Job | None:
        return self._repository.get_job_by_input_key(input_key)

    def current_image_import_model_fingerprints(self, *, game_id: UUID) -> tuple[str, str]:
        symbol = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        grid = (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
        )
        fingerprint = grid.get("inferenceFingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise JobError(
                "GRID_PROFILE_SNAPSHOT_INVALID",
                "The active grid profile snapshot is invalid.",
            )
        return symbol.inference_fingerprint, fingerprint

    def preview_image_import_model_fingerprints(
        self, *, game_id: UUID
    ) -> tuple[str | None, str, str | None, bool, str | None]:
        """Resolve report metadata without weakening the strict import snapshot gate."""

        symbol_fingerprint: str | None
        symbol_blocker_code: str | None = None
        unclassified_cold_start_allowed = False
        symbol_snapshot_fingerprint: str | None = None
        try:
            symbol = (
                bootstrap_symbol_model_snapshot()
                if self._symbol_model_snapshot_resolver is None
                else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
            )
            symbol_fingerprint = symbol.inference_fingerprint
            symbol_snapshot_fingerprint = symbol.inference_fingerprint
        except JobConflictError as error:
            if error.code not in {
                "SYMBOL_MODEL_ACTIVATION_REQUIRED",
                "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED",
            }:
                raise
            symbol_fingerprint = None
            symbol_blocker_code = error.code
            if (
                error.code == "SYMBOL_MODEL_COMPATIBLE_MODEL_REQUIRED"
                and self._symbol_model_snapshot_resolver is not None
            ):
                cold_start_resolver = getattr(
                    self._symbol_model_snapshot_resolver,
                    "resolve_unclassified_cold_start",
                    None,
                )
                cold_start = (
                    cold_start_resolver(game_id=game_id) if callable(cold_start_resolver) else None
                )
                unclassified_cold_start_allowed = cold_start is not None
                if cold_start is not None:
                    symbol_snapshot_fingerprint = cold_start.inference_fingerprint
        grid = (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
        )
        grid_fingerprint = grid.get("inferenceFingerprint")
        if not isinstance(grid_fingerprint, str) or len(grid_fingerprint) != 64:
            raise JobError(
                "GRID_PROFILE_SNAPSHOT_INVALID",
                "The active grid profile snapshot is invalid.",
            )
        return (
            symbol_fingerprint,
            grid_fingerprint,
            symbol_blocker_code,
            unclassified_cold_start_allowed,
            symbol_snapshot_fingerprint,
        )

    def require_lateral_browser_source_history(
        self, *, game_id: UUID, source_selection_id: UUID
    ) -> Job | None:
        source = self.get_image_import_by_source_selection(
            game_id=game_id, source_selection_id=source_selection_id
        )
        if source is not None:
            self._require_no_unreplayed_guard_decisions(source)
        return source

    def _require_no_unreplayed_guard_decisions(self, source: Job) -> None:
        # Guard artifacts bind the previous page geometry checksum and the v3
        # snapshot. Never drop rejected/manual/partial decisions while replacing
        # that evidence with a v4 preflight. They require explicit rebinding.
        seen: set[UUID] = set()
        current: Job | None = source
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.input_payload.get("geometry_guard_resolution_manifest") is not None:
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED",
                    "The source has pinned manual guard decisions. Rebind their source-bound "
                    "resolution manifest before running v0.10.4; no decisions were changed.",
                )
            parent = current.input_payload.get(
                "managed_source_job_id"
            ) or current.input_payload.get("previous_job_id")
            if parent is None:
                return
            try:
                current = self._repository.get_job(UUID(str(parent)))
            except ValueError as error:
                raise JobConflictError(
                    "IMAGE_REPROCESS_SOURCE_INVALID", "Managed source lineage is invalid."
                ) from error
            if current is None or current.game_id != source.game_id or len(seen) >= 32:
                break
        raise JobConflictError(
            "IMAGE_REPROCESS_SOURCE_INVALID", "Managed source lineage cannot be verified."
        )

    def create_page_geometry_preflight_job(
        self,
        *,
        game_id: UUID,
        selection_id: UUID,
        source_directory: Path,
        source_display_name: str,
        source_manifest_sha256: str,
        canonical_sequence_numbers: Sequence[int] = (),
        page_registration_variant: str = "standard_v0_10",
        geometry_engine_variant: GeometryEngineVariant | None = None,
        managed_source_job_id: UUID | None = None,
    ) -> Job:
        """Create an idempotent verified-page geometry preflight.

        The job pins the reviewed anchors together with the browser manifest;
        the later import can therefore reject stale geometry instead of silently
        returning to the heuristic detector.
        """

        try:
            require_geometry_engine_variant_available(geometry_engine_variant)
        except LateralPartialContractError as error:
            raise JobConflictError(error.code, str(error)) from error

        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        if not isinstance(source_manifest_sha256, str) or len(source_manifest_sha256) != 64:
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_SOURCE_MANIFEST_INVALID",
                "The browser source manifest checksum is invalid.",
            )
        if page_registration_variant not in _PAGE_REGISTRATION_VARIANTS:
            raise JobError(
                "IMAGE_PAGE_REGISTRATION_VARIANT_UNSUPPORTED",
                "The selected page registration variant is not supported.",
                details={"pageRegistrationVariant": page_registration_variant},
            )
        managed_input: dict[str, object] = {}
        if managed_source_job_id is not None:
            if geometry_engine_variant is None or self._artifact_root is None:
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_MANAGED_PREFLIGHT_INVALID",
                    "Managed preflight preparation requires the explicit v0.10.4 variant.",
                )
            from .managed_reprocess_evidence import resolve_managed_preflight_source

            try:
                managed_checksum, browser_checksum = resolve_managed_preflight_source(
                    self.get_job(managed_source_job_id),
                    artifact_root=self._artifact_root,
                    game_id=game_id,
                    selection_id=selection_id,
                )
            except ManagedReprocessEvidenceError as error:
                raise JobConflictError(error.code, error.message) from error
            if browser_checksum != source_manifest_sha256:
                raise JobConflictError(
                    "IMAGE_LATERAL_PARTIAL_ARTIFACT_INVALID", "Managed source checksum differs."
                )
            managed_input = {
                "managed_source_job_id": str(managed_source_job_id),
                "managed_source_manifest_checksum_sha256": managed_checksum,
            }
        try:
            resolved = source_directory.resolve(strict=not bool(managed_input))
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_NOT_FOUND",
                "The staged image folder does not exist or is unavailable.",
            ) from error
        if not managed_input and not resolved.is_dir():
            raise JobError(
                "IMAGE_FOLDER_NOT_DIRECTORY",
                "The staged image source must be a directory.",
            )
        grid = (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
        )
        registration = grid.get("pageRegistrationProfile")
        if not isinstance(registration, dict) or not registration.get("anchors"):
            registration = {
                "schemaVersion": 1,
                "policy": PAGE_REGISTRATION_VERSION,
                "thresholdsVersion": PAGE_REGISTRATION_THRESHOLDS_VERSION,
                "anchors": [],
            }
        if page_registration_variant == "board_area_test":
            registration = {
                **registration,
                "policy": PAGE_REGISTRATION_BOARD_AREA_MASK_VERSION,
                "anchorMaskVersion": PAGE_REGISTRATION_ANCHOR_MASK_VERSION,
                "anchorMaskPaddingRatio": PAGE_REGISTRATION_ANCHOR_MASK_PADDING_RATIO,
            }
            preflight_policy_version = _BOARD_AREA_PREFLIGHT_POLICY_VERSION
        else:
            registration = {
                key: value
                for key, value in registration.items()
                if key not in {"anchorMaskVersion", "anchorMaskPaddingRatio"}
            }
            registration["policy"] = PAGE_REGISTRATION_VERSION
            preflight_policy_version = "page-geometry-preflight-v2-auto-anchor"
        overrides = (
            {}
            if self._page_geometry_override_snapshot_resolver is None
            else self._page_geometry_override_snapshot_resolver.snapshot(game_id=game_id)
        )
        if not isinstance(overrides, dict):
            raise JobError(
                "IMAGE_PAGE_GEOMETRY_OVERRIDE_SNAPSHOT_INVALID",
                "The page geometry override snapshot is invalid.",
            )
        partial_policy = self._current_lateral_partial_policy(
            game_id=game_id,
            geometry_engine_variant=geometry_engine_variant,
        )
        exclusions = (
            {}
            if self._page_geometry_override_snapshot_resolver is None
            else self._page_geometry_override_snapshot_resolver.exclusion_snapshot(
                game_id=game_id, browser_selection_id=selection_id
            )
        )
        if not isinstance(exclusions, dict):
            raise JobError(
                "IMAGE_PAGE_SOURCE_EXCLUSION_SNAPSHOT_INVALID",
                "The page source exclusion snapshot is invalid.",
            )
        input_payload: dict[str, object] = {
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "preflight_policy_version": preflight_policy_version,
            "source_selection_id": str(selection_id),
            "source_directory": str(resolved),
            "source_display_name": source_display_name,
            "source_manifest_sha256": source_manifest_sha256,
            "page_registration_profile": registration,
            "page_geometry_overrides": overrides,
            **managed_input,
            **(
                {"lateral_partial_geometry": partial_policy.to_payload()}
                if geometry_engine_variant is not None
                else {}
            ),
            "source_exclusions": exclusions,
            "canonical_sequence_numbers": sorted(
                {int(number) for number in canonical_sequence_numbers if int(number) > 0}
            ),
        }
        candidates = self._repository.list_jobs(
            status=None,
            job_type=JobType.VALIDATE,
            game_id=game_id,
            limit=10_000,
        )
        base_manifest = self._select_page_geometry_base_manifest(
            candidates,
            input_payload=input_payload,
        )
        if base_manifest is not None:
            input_payload["base_page_geometry_manifest"] = base_manifest
        equivalent = _equivalent_page_geometry_preflight(candidates, input_payload)
        if equivalent is not None:
            raise JobConflictError(
                "JOB_INPUT_ALREADY_EXISTS",
                "A job with the same type and input already exists.",
                details={"existingJobId": str(equivalent.id)},
            )
        return self._persist_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload=input_payload,
            game_already_validated=True,
        )

    def _select_page_geometry_base_manifest(
        self,
        candidates: Sequence[Job],
        *,
        input_payload: Mapping[str, object],
    ) -> dict[str, object] | None:
        if self._artifact_root is None:
            return None
        transition: dict[str, object] | None = None
        for candidate in candidates:
            mode = _page_geometry_candidate_compatibility(candidate, input_payload)
            if mode is None:
                continue
            descriptor = _completed_page_geometry_manifest_descriptor(
                candidate,
                artifact_root=self._artifact_root,
                target=input_payload,
                compatibility_mode=mode,
            )
            if descriptor is None:
                continue
            if mode == "exact_policy":
                return descriptor
            if transition is None:
                transition = descriptor
        return transition

    def list_jobs(
        self,
        *,
        status: JobStatus | None,
        job_type: JobType | None,
        game_id: UUID | None,
        limit: int,
    ) -> Sequence[Job]:
        return self._repository.list_jobs(
            status=status,
            job_type=job_type,
            game_id=game_id,
            limit=limit,
        )

    def get_image_import_by_source_selection(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
    ) -> Job | None:
        method = getattr(self._repository, "get_image_import_by_source_selection", None)
        if callable(method):
            found = cast(
                Job | None,
                method(game_id=game_id, source_selection_id=source_selection_id),
            )
            if found is not None:
                return found
        for job in self._repository.list_jobs(
            status=None,
            job_type=JobType.IMPORT,
            game_id=game_id,
            limit=10_000,
        ):
            if job.input_payload.get("source_selection_id") == str(source_selection_id):
                return job
        return None

    def get_image_import_run_by_source_selection(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
        source_manifest_sha256: str,
        engine_policy: ImageImportEnginePolicySnapshot,
        symbol_model_inference_fingerprint: str | None,
        symbol_model_snapshot_fingerprint: str | None,
        grid_profile_inference_fingerprint: str,
        geometry_engine_variant: GeometryEngineVariant | None,
    ) -> Job | None:
        """Replay the newest run for one staging and one explicit engine variant."""

        if symbol_model_snapshot_fingerprint is None:
            return None
        for job in self._repository.list_jobs(
            status=None,
            job_type=JobType.IMPORT,
            game_id=game_id,
            limit=10_000,
        ):
            if job.input_payload.get("source_selection_id") != str(source_selection_id):
                continue
            if job.input_payload.get("source_manifest_sha256") != source_manifest_sha256:
                continue
            symbol_model = job.input_payload.get("symbol_model")
            grid_profile = job.input_payload.get("grid_profile")
            try:
                symbol_snapshot = SymbolModelJobSnapshot.from_payload(symbol_model)
            except (TypeError, ValueError):
                continue
            if (
                symbol_snapshot.inference_fingerprint != symbol_model_snapshot_fingerprint
                or (
                    symbol_model_inference_fingerprint is None
                    and symbol_snapshot.inference_mode != "unclassified"
                )
                or (
                    symbol_model_inference_fingerprint is not None
                    and (
                        symbol_snapshot.inference_mode != "model"
                        or symbol_snapshot.inference_fingerprint
                        != symbol_model_inference_fingerprint
                    )
                )
                or not isinstance(grid_profile, Mapping)
                or grid_profile.get("inferenceFingerprint") != grid_profile_inference_fingerprint
            ):
                continue
            rollout = job.input_payload.get("image_geometry_rollout")
            if rollout is None:
                if (
                    engine_policy.geometry_mode != GeometryRolloutMode.LEGACY.value
                    or engine_policy.cell_asset_mode != CellAssetRolloutMode.LEGACY_FILES.value
                    or engine_policy.revision != 0
                    or geometry_engine_variant is not None
                ):
                    continue
            else:
                try:
                    snapshot = GeometryPipelineRolloutSnapshot.from_payload(rollout)
                except (TypeError, ValueError):
                    continue
                if (
                    snapshot.geometry_mode.value
                    != (
                        GeometryRolloutMode.STRUCTURED_LATTICE_V3.value
                        if geometry_engine_variant is not None
                        else engine_policy.geometry_mode
                    )
                    or snapshot.cell_asset_mode.value
                    != (
                        CellAssetRolloutMode.VIRTUAL_DEFAULT.value
                        if geometry_engine_variant is not None
                        else engine_policy.cell_asset_mode
                    )
                    or snapshot.rollout_revision != engine_policy.revision
                    or not self._geometry_variant_matches_pinned_lateral_snapshot(
                        (
                            None
                            if snapshot.lateral_partial_geometry is None
                            else snapshot.lateral_partial_geometry.to_payload()
                        ),
                        geometry_engine_variant=geometry_engine_variant,
                    )
                ):
                    continue
            return job
        return None

    def get_page_geometry_preflight_by_source_selection(
        self,
        *,
        game_id: UUID,
        source_selection_id: UUID,
        source_manifest_sha256: str,
        geometry_engine_variant: GeometryEngineVariant | None,
    ) -> Job | None:
        """Replay a compatible preflight without dispatching any work."""

        for job in self._repository.list_jobs(
            status=None,
            job_type=JobType.VALIDATE,
            game_id=game_id,
            limit=10_000,
        ):
            payload = job.input_payload
            if (
                payload.get("validation_kind") != "page_geometry_preflight"
                or payload.get("source_selection_id") != str(source_selection_id)
                or payload.get("source_manifest_sha256") != source_manifest_sha256
            ):
                continue
            if self._geometry_variant_matches_pinned_lateral_snapshot(
                payload.get("lateral_partial_geometry"),
                geometry_engine_variant=geometry_engine_variant,
            ):
                return job
        return None

    def cancel_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        updated = request_job_cancellation(job)
        if updated is job:
            return job
        return self._repository.save_job(updated)

    def retry_job(self, job_id: UUID) -> Job:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        if (
            job.job_type is JobType.VALIDATE
            and job.input_payload.get("validation_kind") == "page_geometry_preflight"
        ):
            return self._repository.save_job(requeue_job_with_fresh_progress(job))
        if job.job_type is JobType.SEMI_AUTOMATIC_IMAGE_SELECTION and _is_filename_verification_job(
            job
        ):
            return self._repository.save_job(requeue_job_with_fresh_progress(job))
        if (
            job.job_type is JobType.IMPORT
            and job.input_payload.get("import_kind") == "image_directory"
        ):
            return self._repository.save_job(requeue_job_with_fresh_progress(job))
        return self._repository.save_job(requeue_job(job))

    def delete_cancelled_image_selection_job(
        self,
        job_id: UUID,
    ) -> ImageSelectionJobDeletion:
        job = self._repository.get_job_for_update(job_id)
        if job is None:
            raise JobNotFoundError(
                "JOB_NOT_FOUND",
                "Job does not exist.",
                details={"jobId": str(job_id)},
            )
        if job.job_type is not JobType.IMAGE_SELECTION:
            raise JobConflictError(
                "JOB_DELETE_TYPE_UNSUPPORTED",
                "Only image-selection jobs can be deleted.",
            )
        if job.status is not JobStatus.CANCELLED:
            raise JobConflictError(
                "JOB_DELETE_STATUS_INVALID",
                "Only cancelled image-selection jobs can be deleted.",
            )
        reference = self._repository.get_image_selection_deletion_reference(job_id)
        if reference is None:
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_RUN_MISSING",
                "The cancelled job has no durable image-selection run.",
            )
        if reference.has_curated_import_source:
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_HANDOFF_EXISTS",
                "A run already handed to layout import cannot be deleted.",
            )
        if reference.has_published_output:
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_PUBLISHED_OUTPUT_EXISTS",
                "A run with published output cannot be deleted.",
            )
        if self._deletion_artifact_store is None:
            raise JobConflictError(
                "IMAGE_SELECTION_JOB_DELETE_UNAVAILABLE",
                "Managed image-selection deletion is not configured.",
            )
        delete_source_staging = reference.source_reference_count == 1
        quarantine = self._deletion_artifact_store.quarantine(
            job_id=job_id,
            run_id=reference.run_id,
            source_selection_id=reference.source_selection_id,
            delete_source_staging=delete_source_staging,
        )
        try:
            self._repository.delete_image_selection_run_and_job(
                job_id=job_id,
                run_id=reference.run_id,
            )
        except BaseException:
            self._deletion_artifact_store.restore(quarantine)
            raise
        self._pending_deletion_quarantines.append(quarantine)
        moved = {item.quarantined.name for item in quarantine.directories}
        return ImageSelectionJobDeletion(
            job_id=job_id,
            run_id=reference.run_id,
            managed_run_files_deleted="manual" in moved,
            source_staging_deleted="source" in moved,
            shared_source_staging_preserved=not delete_source_staging,
        )

    def finalize_pending_deletions(self) -> None:
        pending = tuple(self._pending_deletion_quarantines)
        self._pending_deletion_quarantines.clear()
        for quarantine in pending:
            if self._deletion_artifact_store is not None:
                self._deletion_artifact_store.finalize(quarantine)

    def restore_pending_deletions(self) -> None:
        pending = tuple(reversed(self._pending_deletion_quarantines))
        self._pending_deletion_quarantines.clear()
        for quarantine in pending:
            if self._deletion_artifact_store is not None:
                self._deletion_artifact_store.restore(quarantine)


def _equivalent_page_geometry_preflight(
    candidates: Sequence[Job],
    input_payload: Mapping[str, object],
) -> Job | None:
    identity = _page_geometry_request_identity(input_payload)
    for candidate in candidates:
        if (
            candidate.input_payload.get("validation_kind") == "page_geometry_preflight"
            and _page_geometry_request_identity(candidate.input_payload) == identity
        ):
            return candidate
        if (
            candidate.status in {JobStatus.CANCELLED, JobStatus.FAILED}
            or candidate.input_payload.get("validation_kind") != "page_geometry_preflight"
        ):
            continue
        # A live or completed run with identical source and decisions still
        # owns the request even if its historical base pin differs. Failed and
        # cancelled runs can be replaced when a compatible base became ready.
        if _page_geometry_request_identity(
            candidate.input_payload, include_base=False
        ) == _page_geometry_request_identity(input_payload, include_base=False):
            return candidate
    return None


def _page_geometry_request_identity(
    payload: Mapping[str, object], *, include_base: bool = True
) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key != "source_display_name" and (include_base or key != "base_page_geometry_manifest")
    }


def _page_geometry_candidate_compatibility(
    candidate: Job,
    target: Mapping[str, object],
) -> str | None:
    payload = candidate.input_payload
    if (
        candidate.status is not JobStatus.COMPLETED
        or payload.get("validation_kind") != "page_geometry_preflight"
        or payload.get("source_selection_id") != target.get("source_selection_id")
        or payload.get("source_manifest_sha256") != target.get("source_manifest_sha256")
        or payload.get("preflight_policy_version") != target.get("preflight_policy_version")
        or payload.get("page_registration_profile") != target.get("page_registration_profile")
    ):
        return None
    base_lateral = payload.get("lateral_partial_geometry")
    target_lateral = target.get("lateral_partial_geometry")
    if base_lateral == target_lateral:
        return "exact_policy"
    if (
        isinstance(base_lateral, Mapping)
        and isinstance(target_lateral, Mapping)
        and base_lateral.get("schemaVersion")
        in {LATERAL_PARTIAL_SNAPSHOT_VERSION, LATERAL_PARTIAL_SNAPSHOT_VERSION_V2}
        and target_lateral.get("schemaVersion") == SELECTIVE_FRAME_SNAPSHOT_VERSION
        and base_lateral.get("partialGridTrainingProfile")
        == target_lateral.get("partialGridTrainingProfile")
    ):
        return "baseline_to_selective_v1_1"
    if (
        isinstance(base_lateral, Mapping)
        and isinstance(target_lateral, Mapping)
        and base_lateral.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V2
        and target_lateral.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V3
        and base_lateral.get("variant") == target_lateral.get("variant")
        and base_lateral.get("partialGridTrainingProfile")
        == target_lateral.get("partialGridTrainingProfile")
    ):
        return "lateral_v2_to_v3"
    if (
        isinstance(base_lateral, Mapping)
        and isinstance(target_lateral, Mapping)
        and base_lateral.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V3
        and target_lateral.get("schemaVersion") == LATERAL_PARTIAL_SNAPSHOT_VERSION_V2
        and base_lateral.get("variant") == target_lateral.get("variant")
        and base_lateral.get("partialGridTrainingProfile")
        == target_lateral.get("partialGridTrainingProfile")
    ):
        return "lateral_v3_to_v2"
    return None


def _completed_page_geometry_manifest_descriptor(
    candidate: Job,
    *,
    artifact_root: Path,
    target: Mapping[str, object],
    compatibility_mode: str,
) -> dict[str, object] | None:
    checkpoint = candidate.checkpoint_payload
    if not isinstance(checkpoint, Mapping) or checkpoint.get("complete") is not True:
        return None
    checksum = checkpoint.get("geometry_manifest_checksum_sha256")
    relative = checkpoint.get("geometry_manifest_relative_path")
    if (
        not _lower_sha256(checksum)
        or not isinstance(relative, str)
        or not relative.startswith("data/")
    ):
        return None
    path = (artifact_root / Path(*relative.split("/"))).resolve()
    data_root = (artifact_root / "data").resolve()
    if not path.is_relative_to(data_root) or not path.is_file():
        return None
    try:
        content = path.read_bytes()
        manifest = json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None
    if (
        hashlib.sha256(content).hexdigest() != checksum
        or not isinstance(manifest, Mapping)
        or manifest.get("gameId") != str(candidate.game_id)
        or manifest.get("sourceSelectionId") != target.get("source_selection_id")
        or manifest.get("sourceManifestChecksumSha256") != target.get("source_manifest_sha256")
        or manifest.get("version") != target.get("preflight_policy_version")
        or manifest.get("pageRegistrationProfile") != target.get("page_registration_profile")
        or not isinstance(manifest.get("entries"), Mapping)
    ):
        return None
    return {
        "contractVersion": _PAGE_GEOMETRY_REUSE_CONTRACT_VERSION,
        "jobId": str(candidate.id),
        "manifestChecksumSha256": checksum,
        "sourceManifestChecksumSha256": target["source_manifest_sha256"],
        "compatibilityMode": compatibility_mode,
        **(
            {"baseOverrideFingerprints": fingerprints}
            if (
                fingerprints := _page_geometry_override_fingerprints(
                    candidate.input_payload.get("page_geometry_overrides")
                )
            )
            else {}
        ),
    }


def _page_geometry_override_fingerprints(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    fingerprints: dict[str, str] = {}
    for checksum, override in value.items():
        if not _lower_sha256(checksum) or not isinstance(override, Mapping):
            continue
        identity = {
            "decisionChecksumSha256": override.get("decisionChecksumSha256"),
            "overrideId": override.get("overrideId"),
            "revision": override.get("revision"),
        }
        if (
            not _lower_sha256(identity["decisionChecksumSha256"])
            or not isinstance(identity["overrideId"], str)
            or not isinstance(identity["revision"], int)
        ):
            continue
        fingerprints[checksum] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("ascii")
        ).hexdigest()
    return dict(sorted(fingerprints.items()))


def _lower_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _is_filename_verification_job(job: Job) -> bool:
    # Migration 0091 materializes the workflow on historical v2 jobs.  A
    # retry must rely on that durable classification rather than re-inferring
    # it from a mutable recognizer configuration.
    workflow_mode = job.input_payload.get("workflow_mode")
    if workflow_mode in {"selection", "filename_verification"}:
        return workflow_mode == "filename_verification"
    recognizer_fingerprint = job.input_payload.get("recognizer_fingerprint")
    return (
        isinstance(recognizer_fingerprint, str)
        and recognizer_fingerprint == _LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINT
    )


def _bind_geometry_guard_policy(pipeline_fingerprint: str) -> str:
    policy_checksum = hashlib.sha256(
        json.dumps(
            _IMAGE_GEOMETRY_SYSTEMIC_GUARD_POLICY,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    ).hexdigest()
    return hashlib.sha256(f"{pipeline_fingerprint}:{policy_checksum}".encode("ascii")).hexdigest()


def _page_geometry_manifest_fingerprint(value: dict[str, object] | None) -> str:
    if value is None:
        return "page-geometry-manifest-none-v1"
    checksum = value.get("checksumSha256")
    path = value.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(path, str)
        or not path
    ):
        raise JobError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "The pinned page geometry manifest descriptor is invalid.",
        )
    return checksum


def _geometry_guard_resolution_manifest_fingerprint(
    value: dict[str, object] | None,
) -> str:
    if value is None:
        return "image-geometry-guard-resolution-none-v1"
    checksum = value.get("checksumSha256")
    path = value.get("relativePath")
    if (
        not isinstance(checksum, str)
        or len(checksum) != 64
        or not isinstance(path, str)
        or not path
    ):
        raise JobError(
            "IMAGE_GEOMETRY_GUARD_MANIFEST_INVALID",
            "The pinned geometry guard resolution manifest descriptor is invalid.",
        )
    return checksum


def _source_exclusions_fingerprint(value: dict[str, object] | None) -> str:
    canonical = json.dumps(
        value or {},
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    return hashlib.sha256(canonical).hexdigest()


def _baseline_grid_profile_snapshot() -> dict[str, object]:
    value: dict[str, object] = {
        "profileId": None,
        "profileVersion": "detector-baseline-v1",
        "profileChecksumSha256": hashlib.sha256(b"detector-baseline-v1").hexdigest(),
        "activationId": None,
        "profilePayload": {
            "schemaVersion": 1,
            "calibrationPolicy": "detector-baseline-v1",
            "scopes": [],
            "positionFallbacks": [],
        },
    }
    canonical = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")
    value["inferenceFingerprint"] = hashlib.sha256(canonical).hexdigest()
    return value
