"""Application service and repository port for durable jobs."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

from game_predictor_api.application.layout_imports import LayoutImportSourceInspector
from game_predictor_api.domain.datasets import DatasetVersionStatus
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

PAYOUT_ALGORITHM_VERSION = "payout-v2"


@dataclass(frozen=True, slots=True)
class LayoutImportRulesReference:
    game_id: UUID
    status: RulesVersionStatus


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


class GridProfileSnapshotResolver(Protocol):
    def resolve(self, *, game_id: UUID) -> dict[str, object]: ...


class PageGeometryOverrideSnapshotResolver(Protocol):
    def snapshot(self, *, game_id: UUID) -> dict[str, object]: ...


class JobService:
    def __init__(
        self,
        repository: JobRepository,
        import_source_inspector: LayoutImportSourceInspector | None = None,
        symbol_model_snapshot_resolver: SymbolModelSnapshotResolver | None = None,
        grid_profile_snapshot_resolver: GridProfileSnapshotResolver | None = None,
        *,
        page_geometry_override_snapshot_resolver: (
            PageGeometryOverrideSnapshotResolver | None
        ) = None,
        deletion_artifact_store: ImageSelectionDeletionArtifactStore | None = None,
    ) -> None:
        self._repository = repository
        self._import_source_inspector = import_source_inspector
        self._symbol_model_snapshot_resolver = symbol_model_snapshot_resolver
        self._grid_profile_snapshot_resolver = grid_profile_snapshot_resolver
        self._page_geometry_override_snapshot_resolver = page_geometry_override_snapshot_resolver
        self._deletion_artifact_store = deletion_artifact_store
        self._pending_deletion_quarantines: list[ImageSelectionDeletionQuarantine] = []

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
        start_mode: str | None = None,
        previous_job_id: UUID | None = None,
        page_geometry_manifest: dict[str, object] | None = None,
    ) -> Job:
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
        symbol_model = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        effective_pipeline_fingerprint = hashlib.sha256(
            f"{pipeline_fingerprint}:{symbol_model.inference_fingerprint}".encode("ascii")
        ).hexdigest()
        input_payload: dict[str, object] = {
            "schema_version": 2 if start_mode is None else 5,
            "import_kind": "image_directory",
            "source_selection_id": str(selection_id),
            "source_directory": str(resolved),
            "source_display_name": source_display_name,
            "pipeline_fingerprint": effective_pipeline_fingerprint,
            "source_pipeline_fingerprint": pipeline_fingerprint,
            "symbol_model": symbol_model.to_payload(),
        }
        if start_mode is not None:
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
                    f"{_page_geometry_manifest_fingerprint(page_geometry_manifest)}"
                ).encode("ascii")
            ).hexdigest()
            input_payload["pipeline_fingerprint"] = effective_pipeline_fingerprint
            input_payload["start_mode"] = start_mode
            input_payload["previous_job_id"] = (
                None if previous_job_id is None else str(previous_job_id)
            )
            input_payload["grid_profile"] = grid_profile
            if page_geometry_manifest is not None:
                input_payload["page_geometry_manifest"] = dict(page_geometry_manifest)
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
        """Create a job that refreshes geometry and crops for pending boards only."""

        if not self._repository.game_exists(game_id):
            raise JobNotFoundError(
                "GAME_NOT_FOUND",
                "Game does not exist.",
                details={"gameId": str(game_id)},
            )
        grid_profile = (
            _baseline_grid_profile_snapshot()
            if self._grid_profile_snapshot_resolver is None
            else self._grid_profile_snapshot_resolver.resolve(game_id=game_id)
        )
        fingerprint = grid_profile.get("inferenceFingerprint")
        if not isinstance(fingerprint, str) or len(fingerprint) != 64:
            raise JobError(
                "GRID_PROFILE_SNAPSHOT_INVALID",
                "The active grid profile snapshot is invalid.",
            )
        symbol_model = (
            bootstrap_symbol_model_snapshot()
            if self._symbol_model_snapshot_resolver is None
            else self._symbol_model_snapshot_resolver.resolve(game_id=game_id)
        )
        return self._persist_job(
            JobType.IMAGE_GRID_REINFERENCE,
            game_id=game_id,
            input_payload={
                "schema_version": 1,
                "inference_kind": "pending_grid_only",
                "cell_output_size": symbol_model.input_size,
                "grid_profile": grid_profile,
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
        return self._persist_job(
            JobType.IMPORT,
            game_id=game_id,
            input_payload={
                "schema_version": 3,
                "import_kind": "image_directory",
                "source_selection_id": str(source_id),
                "source_directory": str(resolved),
                "source_display_name": source_display_name,
                "pipeline_fingerprint": effective_pipeline_fingerprint,
                "source_pipeline_fingerprint": pipeline_fingerprint,
                "image_selection_run_id": str(image_selection_run_id),
                "curated_image_import_source_id": str(source_id),
                "curated_image_import_batch_id": str(batch_id),
                "curated_manifest_relative_path": manifest_relative_path,
                "curated_manifest_checksum_sha256": manifest_checksum_sha256,
                "curated_manifest_entry_start": entry_start,
                "curated_manifest_entry_count": entry_count,
                "symbol_model": symbol_model.to_payload(),
                "grid_profile": pinned_grid_profile,
            },
            game_already_validated=True,
        )

    def create_managed_image_reprocess_job(
        self,
        source_job_id: UUID,
        *,
        pipeline_fingerprint: str,
    ) -> Job:
        """Create a new import pinned to an earlier job's managed originals."""

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
        source_directory = source.input_payload.get("source_directory")
        if not isinstance(source_directory, str) or not source_directory:
            raise JobConflictError(
                "IMAGE_REPROCESS_SOURCE_INVALID",
                "The source image import has no managed source provenance.",
            )
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
                f"{grid_fingerprint}:{source.id}"
            ).encode("ascii")
        ).hexdigest()
        payload: dict[str, object] = {
            "schema_version": 4,
            "import_kind": "image_directory",
            "source_directory": source_directory,
            "source_display_name": (
                f"{source.input_payload.get('source_display_name') or 'Import obrazów'} "
                "(ponowne przetworzenie)"
            ),
            "pipeline_fingerprint": effective_pipeline_fingerprint,
            "source_pipeline_fingerprint": pipeline_fingerprint,
            "managed_source_job_id": str(source.id),
            "symbol_model": symbol_model.to_payload(),
            "grid_profile": grid_profile,
        }
        source_selection_id = source.input_payload.get("source_selection_id")
        if source_selection_id is not None:
            payload["source_selection_id"] = source_selection_id
        image_selection_run_id = source.input_payload.get("image_selection_run_id")
        if image_selection_run_id is not None:
            payload["image_selection_run_id"] = image_selection_run_id
        return self._persist_job(
            JobType.IMPORT,
            game_id=source.game_id,
            input_payload=payload,
            game_already_validated=True,
        )

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

    def create_page_geometry_preflight_job(
        self,
        *,
        game_id: UUID,
        selection_id: UUID,
        source_directory: Path,
        source_manifest_sha256: str,
        canonical_sequence_numbers: Sequence[int] = (),
    ) -> Job:
        """Create an idempotent verified-page geometry preflight.

        The job pins the reviewed anchors together with the browser manifest;
        the later import can therefore reject stale geometry instead of silently
        returning to the heuristic detector.
        """

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
        try:
            resolved = source_directory.resolve(strict=True)
        except OSError as error:
            raise JobError(
                "IMAGE_FOLDER_NOT_FOUND",
                "The staged image folder does not exist or is unavailable.",
            ) from error
        if not resolved.is_dir():
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
            raise JobConflictError(
                "IMAGE_PAGE_GEOMETRY_PROFILE_EMPTY",
                "Create or activate a grid profile from reviewed pages before geometry preflight.",
            )
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
        return self._persist_job(
            JobType.VALIDATE,
            game_id=game_id,
            input_payload={
                "schema_version": 2,
                "validation_kind": "page_geometry_preflight",
                "source_selection_id": str(selection_id),
                "source_directory": str(resolved),
                "source_manifest_sha256": source_manifest_sha256,
                "page_registration_profile": registration,
                "page_geometry_overrides": overrides,
                "canonical_sequence_numbers": sorted(
                    {int(number) for number in canonical_sequence_numbers if int(number) > 0}
                ),
            },
            game_already_validated=True,
        )

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
