"""Application service for durable global semi-automatic selection runs."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Protocol, cast
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.engine import (
    grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.five_anchor_range_runtime import (
    FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
)
from game_predictor_worker.semi_automatic_selection.local_source_manifest import (
    LocalSourceManifest,
    LocalSourceManifestError,
    build_local_source_manifest,
    load_local_source_manifest,
    resolve_local_source_asset,
    write_local_source_manifest,
)
from game_predictor_worker.semi_automatic_selection.middle_row_grouping import (
    five_anchor_grouping_policy_fingerprint,
)
from game_predictor_worker.semi_automatic_selection.range_only_ocr import (
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT,
    RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2,
)
from game_predictor_worker.semi_automatic_selection.v7_draft_catalog import (
    draft_folder,
    folder_reference,
    read_draft,
)
from game_predictor_worker.semi_automatic_selection.v7_pilot_configuration import V7PilotArtifacts

from game_predictor_api.application.image_imports import (
    BrowserImageSelectionService,
    BrowserReadySource,
    ImageFolderSelectionService,
    ImageSelectionPurpose,
    SelectedImageFolder,
)
from game_predictor_api.domain.jobs import JobStatus, request_job_cancellation, requeue_job
from game_predictor_api.domain.semi_automatic_image_selections import (
    SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
    SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
    SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
    FilenameRangeVerificationReview,
    FilenameRangeVerificationReviewDecision,
    FilenameVerificationHistoryDeletion,
    SemiAutomaticSelectionConflictError,
    SemiAutomaticSelectionDirection,
    SemiAutomaticSelectionError,
    SemiAutomaticSelectionNotFoundError,
    SemiAutomaticSelectionRange,
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionRunStatus,
    SemiAutomaticSelectionSourceManifest,
    SemiAutomaticSelectionWorkflowMode,
    SemiAutomaticV7BorderStyle,
    SemiAutomaticV7SelectionMode,
    acknowledge_manual_output,
    acknowledge_output,
    apply_range_status_transition,
    cancel_run,
    classify_filename_range_verification,
    create_semi_automatic_selection_run,
    create_v7_selection_configuration,
    pause_run,
    resume_run,
    run_identity_key,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7_PENDING_STATES,
    V7DeliveryConflict,
    V7OutputDecision,
    V7OutputOperation,
    V7PilotGate,
    payload_fingerprint,
)
from game_predictor_api.domain.v7_selection_feedback import capture_feedback_snapshot

SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT
SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT = grouping_policy_fingerprint()
SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE = "filename_verification"
SEMI_AUTOMATIC_SELECTION_MODE = "selection"
SEMI_AUTOMATIC_V7_SELECTION_MODE = "v7_selection"
V7_SELECTION_ACTIVATION_STATUS = "blocked"
V7_SELECTION_BLOCKED_REASON = (
    "V7 selection remains blocked until the T12 holdout acceptance is recorded."
)
SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT = "default_v3"
SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT = "five_anchor_v6"
_LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINTS = frozenset(
    {RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2}
)
_SELECTION_RECOGNIZER_VARIANTS: dict[str, dict[str, object]] = {
    SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT: {
        "default": True,
        "experimental": False,
        "fingerprint": SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
        "label": "OCR zakresu v3 (domyślny)",
    },
    SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT: {
        "default": False,
        "experimental": True,
        "fingerprint": FIVE_ANCHOR_RECOGNIZER_CONTRACT_FINGERPRINT_V6,
        "label": "OCR pięciu anchorów v6 (eksperymentalny)",
    },
}


def workflow_mode_for_recognizer_fingerprint(
    recognizer_fingerprint: str | None,
) -> SemiAutomaticSelectionWorkflowMode:
    """Classify version-one payloads without inferring from mutable job state."""

    if recognizer_fingerprint in _LEGACY_FILENAME_VERIFICATION_RECOGNIZER_FINGERPRINTS:
        return SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION
    return SemiAutomaticSelectionWorkflowMode.SELECTION


class SemiAutomaticSelectionRepository(Protocol):
    def get_v7_pilot_gate(
        self, *, for_update: bool = False, for_share: bool = False
    ) -> V7PilotGate: ...

    def get_v7_output_operation(
        self, operation_id: UUID, *, for_update: bool = False
    ) -> V7OutputOperation | None: ...

    def get_pending_v7_output(
        self, run_id: UUID, *, for_update: bool = False
    ) -> V7OutputOperation | None: ...

    def save_v7_output_operation(self, operation: V7OutputOperation) -> V7OutputOperation: ...

    def get_v7_source_observations(
        self, run_id: UUID, source_indexes: Sequence[int]
    ) -> dict[int, dict[str, object]]: ...

    def find_by_identity(self, identity_key: str) -> SemiAutomaticSelectionRun | None: ...

    def find_v7_runs_by_source_name(self, name: str) -> tuple[SemiAutomaticSelectionRun, ...]: ...

    def add(
        self,
        run: SemiAutomaticSelectionRun,
        ranges: Sequence[SemiAutomaticSelectionRange],
        *,
        identity_key: str,
    ) -> SemiAutomaticSelectionRun: ...

    def get(
        self,
        run_id: UUID,
        *,
        for_update: bool = False,
    ) -> SemiAutomaticSelectionRun | None: ...

    def save(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun: ...

    def get_for_v7_review(
        self, run_id: UUID, *, for_update: bool = False
    ) -> SemiAutomaticSelectionRun | None: ...

    def save_v7_review_state(self, run: SemiAutomaticSelectionRun) -> SemiAutomaticSelectionRun: ...

    def list_runs(
        self,
        *,
        workflow_mode: SemiAutomaticSelectionWorkflowMode,
        offset: int,
        limit: int,
    ) -> tuple[tuple[SemiAutomaticSelectionRun, ...], int | None]: ...

    def get_filename_verification_reviews(
        self,
        run_id: UUID,
        source_indexes: Sequence[int],
    ) -> dict[int, FilenameRangeVerificationReview]: ...

    def save_filename_verification_review(
        self,
        review: FilenameRangeVerificationReview,
        *,
        expected_revision: int,
    ) -> FilenameRangeVerificationReview: ...

    def delete_completed_filename_verification_history(
        self,
        *,
        run_id: UUID,
        job_id: UUID,
    ) -> FilenameVerificationHistoryDeletion: ...

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]: ...

    def get_range_for_update(
        self,
        run_id: UUID,
        expected_index: int,
    ) -> SemiAutomaticSelectionRange | None: ...

    def save_range(self, item: SemiAutomaticSelectionRange) -> SemiAutomaticSelectionRange: ...

    def save_run_and_range(
        self,
        run: SemiAutomaticSelectionRun,
        item: SemiAutomaticSelectionRange,
    ) -> tuple[SemiAutomaticSelectionRun, SemiAutomaticSelectionRange]: ...


class SemiAutomaticImageSelectionService:
    def __init__(
        self,
        repository: SemiAutomaticSelectionRepository,
        staging: BrowserImageSelectionService,
        *,
        enabled: bool,
        artifact_root: Path | None = None,
        folder_selection: ImageFolderSelectionService | None = None,
        v7_artifacts: V7PilotArtifacts | None = None,
        v7_output_base: Path | None = None,
        output_picker: Callable[[], Path | None] | None = None,
    ) -> None:
        self._repository = repository
        self._staging = staging
        self._enabled = enabled
        self._artifact_root = None if artifact_root is None else artifact_root.resolve()
        self._folder_selection = folder_selection
        self._v7_artifacts = v7_artifacts
        self._v7_output_base = v7_output_base
        self._output_picker = output_picker

    def output_directory(self, run: SemiAutomaticSelectionRun) -> str | None:
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            return None
        read_pin = getattr(self._repository, "get_v7_output_root", None)
        if read_pin is not None:
            pin = read_pin(run.id)
            if pin is not None:
                if pin == "":  # An older operation owns the original sibling directory.
                    manifest = self._local_source_manifest(run)
                    if manifest is None:
                        return None
                    return str(manifest.source_root.with_name(f"{manifest.source_root.name} cut"))
                return str(pin)
        if run.v7_configuration is not None and run.v7_configuration.output_directory is not None:
            return run.v7_configuration.output_directory
        if self._v7_output_base is not None:
            return str(self._v7_output_base / str(run.id))
        manifest = self._local_source_manifest(run)
        if manifest is None:
            return None
        return str(manifest.source_root.with_name(f"{manifest.source_root.name} cut"))

    def capabilities(self) -> dict[str, object]:
        return {
            "enabled": self._enabled,
            "filenameVerificationEnabled": True,
            "contractVersion": SEMI_AUTOMATIC_SELECTION_CONTRACT_VERSION,
            "rangeConvention": SEMI_AUTOMATIC_SELECTION_RANGE_CONVENTION,
            "fullRangeSize": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "minimumSequenceNumber": 1,
            "maximumBoardsPerRange": SEMI_AUTOMATIC_SELECTION_FULL_RANGE_SIZE,
            "stagingPurpose": ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION.value,
            "sourceMode": "local_folder",
            "recognizerFingerprint": SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT,
            "selectionRecognizerVariants": [
                {"id": variant, **values}
                for variant, values in _SELECTION_RECOGNIZER_VARIANTS.items()
            ],
            "filenameVerificationRecognizerFingerprint": (
                RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2
            ),
            "groupingPolicyFingerprint": SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT,
            "v7": self._v7_capabilities(),
        }

    def _v7_capabilities(self) -> dict[str, object]:
        enabled = False
        source_policy = "exact_sources"
        reason = V7_SELECTION_BLOCKED_REASON
        if self._v7_artifacts is not None:
            try:
                gate = self._repository.get_v7_pilot_gate()
                self._v7_artifacts.validate(gate)
                enabled = gate.enabled
                source_policy = gate.source_policy
                reason = "Each V7 output requires operator confirmation; quality may be unknown."
            except (V7DeliveryConflict, ValueError) as error:
                reason = str(error)
        return {
            "activationStatus": "active" if enabled else V7_SELECTION_ACTIVATION_STATUS,
            "startEnabled": enabled,
            "automaticStartEnabled": False,
            "manualConfirmationRequired": True,
            "sourcePolicy": source_policy,
            "reason": reason,
            "configurationVersion": (
                "v7-selection-configuration-v2"
                if self._v7_artifacts is not None
                else "v7-selection-configuration-v1"
            ),
            "defaultMode": SemiAutomaticV7SelectionMode.SEMI_AUTOMATIC.value,
            "defaultDirection": SemiAutomaticSelectionDirection.ASCENDING.value,
            "defaultBorderStyle": SemiAutomaticV7BorderStyle.TOP_AND_SIDES.value,
            "borderStyles": [style.value for style in SemiAutomaticV7BorderStyle],
        }

    def select_local_source(self) -> SelectedImageFolder | None:
        if not self._enabled:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DISABLED",
                "Semi-automatic image selection is disabled by the server rollout gate.",
            )
        if self._folder_selection is None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_UNAVAILABLE",
                "The controlled local source picker is unavailable.",
            )
        return self._folder_selection.select(purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION)

    def select_output_folder(self) -> Path | None:
        if not self._enabled or self._output_picker is None:
            raise SemiAutomaticSelectionError(
                "V7_OUTPUT_PICKER_UNAVAILABLE", "The local output folder picker is unavailable."
            )
        selected = self._output_picker()
        return None if selected is None else self._validate_output_base(selected)

    @staticmethod
    def _validate_output_base(base: Path) -> Path:
        from game_predictor_worker.semi_automatic_selection.v7_output_writer import (
            _is_supported_local_ntfs,
        )

        try:
            if not base.is_absolute() or not base.is_dir() or base.is_symlink():
                raise ValueError("Choose an existing absolute local output directory.")
            resolved = base.resolve(strict=True)
            if resolved != base.absolute() or not _is_supported_local_ntfs(resolved):
                raise ValueError("Output requires a local NTFS directory without junctions.")
            return resolved
        except (OSError, ValueError) as error:
            raise SemiAutomaticSelectionError("V7_OUTPUT_DIRECTORY_INVALID", str(error)) from error

    def create(
        self,
        *,
        upload_id: UUID | None = None,
        selection_token: str | None = None,
        first_sequence_number: int,
        last_sequence_number: int,
        direction: SemiAutomaticSelectionDirection,
        mode: str = SEMI_AUTOMATIC_SELECTION_MODE,
        recognizer_variant: str = SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT,
        v7_mode: SemiAutomaticV7SelectionMode = SemiAutomaticV7SelectionMode.SEMI_AUTOMATIC,
        v7_border_style: SemiAutomaticV7BorderStyle = SemiAutomaticV7BorderStyle.TOP_AND_SIDES,
        output_base_directory: str | None = None,
    ) -> tuple[SemiAutomaticSelectionRun, bool]:
        pilot_gate = None
        if mode == SEMI_AUTOMATIC_V7_SELECTION_MODE:
            if (
                v7_mode is not SemiAutomaticV7SelectionMode.SEMI_AUTOMATIC
                or self._v7_artifacts is None
            ):
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_V7_BLOCKED", V7_SELECTION_BLOCKED_REASON
                )
            pilot_gate = self._repository.get_v7_pilot_gate()
            self._v7_artifacts.validate(pilot_gate)
            if upload_id is not None or selection_token is None or self._folder_selection is None:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_REQUIRED",
                    "V7 requires a local source token.",
                )
            selected = self._folder_selection.get_for_semi_automatic_selection(selection_token)
            pilot_gate.require_source_root(selected.path)
        if mode == SEMI_AUTOMATIC_SELECTION_MODE and not self._enabled:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DISABLED",
                "Semi-automatic image selection is disabled by the server rollout gate.",
            )
        if mode not in {
            SEMI_AUTOMATIC_SELECTION_MODE,
            SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE,
            SEMI_AUTOMATIC_V7_SELECTION_MODE,
        }:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The requested semi-automatic workflow mode is unsupported.",
            )
        if pilot_gate is not None:
            if recognizer_variant != SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_VARIANT_INVALID",
                    "V7 uses its pinned observer/model.",
                )
            recognizer_fingerprint = cast(str, pilot_gate.ocr_model_fingerprint)
            grouping_policy = payload_fingerprint(
                {"version": "v7-reviewed-grouping-v1", "observer": pilot_gate.observer_fingerprint}
            )
        elif mode == SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE:
            if recognizer_variant != SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_VARIANT_INVALID",
                    "Filename verification does not support the selected recognizer variant.",
                )
            recognizer_fingerprint = RANGE_ONLY_RECOGNIZER_CONTRACT_FINGERPRINT_V2
            grouping_policy = SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT
        else:
            variant = _SELECTION_RECOGNIZER_VARIANTS.get(recognizer_variant)
            if variant is None:
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_RECOGNIZER_VARIANT_INVALID",
                    "The requested semi-automatic range recognizer variant is unsupported.",
                )
            recognizer_fingerprint = str(variant["fingerprint"])
            grouping_policy = (
                five_anchor_grouping_policy_fingerprint()
                if recognizer_variant == SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT
                else SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT
            )
        if selection_token is not None:
            if (
                mode not in {SEMI_AUTOMATIC_SELECTION_MODE, SEMI_AUTOMATIC_V7_SELECTION_MODE}
                or upload_id is not None
            ):
                raise SemiAutomaticSelectionError(
                    "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_REQUIRED",
                    "A local source token can be used only by the selection workflow.",
                )
            source, local_manifest_path, local_selection = self._prepare_local_source(
                selection_token
            )
        else:
            if upload_id is None:
                raise SemiAutomaticSelectionError(
                    (
                        "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_REQUIRED"
                        if mode == SEMI_AUTOMATIC_SELECTION_MODE
                        else "SEMI_AUTOMATIC_SELECTION_STAGING_REQUIRED"
                    ),
                    "The requested workflow has no finalized source.",
                )
            ready = self._staging.get_ready_source_selection(
                upload_id,
                purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
            )
            source = SemiAutomaticSelectionSourceManifest(
                upload_id=ready.upload_id,
                display_name=ready.display_name,
                manifest_checksum_sha256=ready.manifest_checksum_sha256,
                source_fingerprint=ready.source_fingerprint,
                source_count=len(ready.sources),
                source_total_bytes=ready.total_bytes,
            )
            local_manifest_path = None
            local_selection = None
        pilot_snapshot = None
        selected_output = None
        if output_base_directory is not None:
            if mode != SEMI_AUTOMATIC_V7_SELECTION_MODE or local_selection is None:
                raise SemiAutomaticSelectionError(
                    "V7_OUTPUT_DIRECTORY_INVALID",
                    "Output folder selection requires a local V7 run.",
                )
            base = self._validate_output_base(Path(output_base_directory))
            selected_output = (base / local_selection.path.name).resolve()
            if selected_output.parent != base:
                raise SemiAutomaticSelectionError(
                    "V7_OUTPUT_DIRECTORY_INVALID",
                    "Output folder must remain inside the selected base.",
                )
            source_root = local_selection.path.resolve(strict=True)
            if selected_output.is_relative_to(source_root) or source_root.is_relative_to(
                selected_output
            ):
                raise SemiAutomaticSelectionError(
                    "V7_OUTPUT_DIRECTORY_INVALID", "Output must be separate from the source folder."
                )
        if pilot_gate is not None:
            assert local_selection is not None
            pilot_snapshot = pilot_gate.snapshot_for(
                local_selection.path, source.source_fingerprint
            )
            self._repository.get_v7_pilot_gate(for_share=True).require_snapshot(
                pilot_snapshot, local_selection.path, source.source_fingerprint
            )
        v7_configuration = (
            create_v7_selection_configuration(
                first_sequence_number=first_sequence_number,
                last_sequence_number=last_sequence_number,
                direction=direction,
                mode=v7_mode,
                border_style=v7_border_style,
                localizer_fingerprint=cast(str, pilot_gate.observer_fingerprint)
                if pilot_gate is not None
                else "0" * 64,
                calibration_fingerprint=cast(str, pilot_gate.profile_fingerprint)
                if pilot_gate is not None
                else "0" * 64,
                pilot=pilot_snapshot,
                output_directory=None if selected_output is None else str(selected_output),
            )
            if mode == SEMI_AUTOMATIC_V7_SELECTION_MODE
            else None
        )
        identity_key = run_identity_key(
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            recognizer_fingerprint=recognizer_fingerprint,
            grouping_policy_fingerprint=grouping_policy,
            v7_configuration=v7_configuration,
        )
        existing = self._repository.find_by_identity(identity_key)
        if existing is not None:
            self._consume_local_selection(selection_token, local_selection)
            return existing, False
        run, ranges = create_semi_automatic_selection_run(
            source=source,
            first_sequence_number=first_sequence_number,
            last_sequence_number=last_sequence_number,
            direction=direction,
            workflow_mode=SemiAutomaticSelectionWorkflowMode(mode),
            v7_configuration=v7_configuration,
            recognizer_fingerprint=recognizer_fingerprint,
            grouping_policy_fingerprint=grouping_policy,
            local_source_manifest_relative_path=local_manifest_path,
        )
        try:
            stored = self._repository.add(run, ranges, identity_key=identity_key)
            self._consume_local_selection(selection_token, local_selection)
            return stored, True
        except SemiAutomaticSelectionConflictError:
            concurrent = self._repository.find_by_identity(identity_key)
            if concurrent is None:
                raise
            self._consume_local_selection(selection_token, local_selection)
            return concurrent, False

    def _consume_local_selection(
        self,
        selection_token: str | None,
        selection: SelectedImageFolder | None,
    ) -> None:
        if (
            selection_token is not None
            and selection is not None
            and self._folder_selection is not None
        ):
            self._folder_selection.consume_semi_automatic_selection(
                selection_token,
                selection_id=selection.selection_id,
            )

    def _prepare_local_source(
        self,
        selection_token: str,
    ) -> tuple[SemiAutomaticSelectionSourceManifest, str, SelectedImageFolder]:
        if self._folder_selection is None or self._artifact_root is None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_LOCAL_SOURCE_UNAVAILABLE",
                "The local source manifest store is unavailable.",
            )
        selected = self._folder_selection.get_for_semi_automatic_selection(selection_token)
        try:
            manifest = build_local_source_manifest(
                selected.path,
                selection_id=selected.selection_id,
                display_name=selected.display_name,
            )
            relative_path = write_local_source_manifest(self._artifact_root, manifest)
        except LocalSourceManifestError as error:
            raise SemiAutomaticSelectionError(error.code, str(error)) from error
        return (
            SemiAutomaticSelectionSourceManifest(
                upload_id=selected.selection_id,
                display_name=manifest.display_name,
                manifest_checksum_sha256=manifest.checksum_sha256,
                source_fingerprint=manifest.source_fingerprint,
                source_count=len(manifest.sources),
                source_total_bytes=manifest.total_bytes,
            ),
            relative_path,
            selected,
        )

    def list_filename_verification_items(
        self,
        run_id: UUID,
        *,
        after_source_index: int | None,
        limit: int,
    ) -> tuple[dict[str, object], ...]:
        run = self.get(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The run was not created for filename range verification.",
            )
        if limit < 1 or limit > 500:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The verification page limit must be between 1 and 500.",
            )
        if self._artifact_root is None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_DIAGNOSTICS_UNAVAILABLE",
                "The range verification diagnostics store is unavailable.",
            )
        observations_path = (
            self._artifact_root
            / "exports"
            / "semi-automatic-selection"
            / str(run.id)
            / "observations.jsonl"
        ).resolve()
        expected_parent = (
            self._artifact_root / "exports" / "semi-automatic-selection" / str(run.id)
        ).resolve()
        if (
            observations_path.parent != expected_parent
            or self._artifact_root not in observations_path.parents
        ):
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The verification diagnostics path is unsafe.",
            )
        committed = _committed_observation_count(run)
        if not observations_path.exists() or committed == 0:
            return ()
        first_index = 0 if after_source_index is None else after_source_index + 1
        if first_index >= committed:
            return ()
        items: list[dict[str, object]] = []
        try:
            with observations_path.open("r", encoding="utf-8") as source:
                for line_index, line in enumerate(source):
                    if line_index >= committed or len(items) >= limit:
                        break
                    if line_index < first_index:
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict) or value.get("sourceIndex") != line_index:
                        raise ValueError("non-contiguous observation")
                    items.append(
                        classify_filename_range_verification(cast(dict[str, object], value))
                    )
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
                "The committed filename verification diagnostics are invalid.",
            ) from error
        reviews = self._repository.get_filename_verification_reviews(
            run.id,
            [_filename_verification_source_index(item) for item in items],
        )
        return tuple(
            {
                **item,
                "reviewDecision": (
                    None
                    if (review := reviews.get(_filename_verification_source_index(item))) is None
                    else review.decision.value
                ),
                "reviewRevision": (None if review is None else review.revision),
            }
            for item in items
        )

    def list_runs(
        self,
        *,
        workflow_mode: SemiAutomaticSelectionWorkflowMode,
        offset: int,
        limit: int,
    ) -> tuple[tuple[SemiAutomaticSelectionRun, ...], int | None]:
        if offset < 0 or limit < 1 or limit > 100:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The run history page is invalid.",
            )
        return self._repository.list_runs(
            workflow_mode=workflow_mode,
            offset=offset,
            limit=limit,
        )

    def decide_filename_verification(
        self,
        run_id: UUID,
        source_index: int,
        *,
        decision: FilenameRangeVerificationReviewDecision,
        expected_source_checksum_sha256: str,
        expected_revision: int,
    ) -> FilenameRangeVerificationReview:
        run = self.get(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_MODE_INVALID",
                "The run was not created for filename range verification.",
            )
        if run.status not in {
            SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
            SemiAutomaticSelectionRunStatus.REVIEW_MODE,
        }:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_NOT_REVIEWABLE",
                "Filename verification decisions are available only after analysis completes.",
            )
        ready = self._staging.get_ready_source_selection(
            run.source.upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        )
        if source_index < 0 or source_index >= len(ready.sources):
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                "The requested source does not exist.",
            )
        source = ready.sources[source_index]
        if source.checksum_sha256 != expected_source_checksum_sha256:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The reviewed source changed after it was loaded.",
            )
        observation_items = self.list_filename_verification_items(
            run.id,
            after_source_index=None if source_index == 0 else source_index - 1,
            limit=1,
        )
        if (
            len(observation_items) != 1
            or _filename_verification_source_index(observation_items[0]) != source_index
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                "The requested filename verification observation is unavailable.",
            )
        if observation_items[0].get("verificationStatus") == "verified":
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_REVIEW_NOT_REQUIRED",
                "A filename verification decision is allowed only for an unreadable, "
                "mismatched, or invalid filename.",
            )
        existing = self._repository.get_filename_verification_reviews(
            run.id,
            [source_index],
        ).get(source_index)
        if (
            existing is not None
            and existing.decision is decision
            and existing.source_checksum_sha256 == source.checksum_sha256
        ):
            return existing
        if existing is not None and existing.revision != expected_revision:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_REVIEW_STALE",
                "The filename verification decision changed in another session.",
            )
        now = datetime.now(UTC)
        return self._repository.save_filename_verification_review(
            FilenameRangeVerificationReview(
                run_id=run.id,
                source_index=source_index,
                source_checksum_sha256=source.checksum_sha256,
                decision=decision,
                revision=0 if existing is None else existing.revision + 1,
                created_at=now if existing is None else existing.created_at,
                updated_at=now,
            ),
            expected_revision=0 if existing is None else expected_revision,
        )

    def delete_filename_verification_history(
        self,
        run_id: UUID,
    ) -> FilenameVerificationHistoryDeletion:
        """Remove only the compact, already-cleaned filename review history."""

        run = self._locked(run_id)
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.FILENAME_VERIFICATION:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_MODE_INVALID",
                "Only filename verification history can be deleted here.",
            )
        if run.status is not SemiAutomaticSelectionRunStatus.COMPLETED:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_NOT_COMPLETED",
                "Only a completed filename verification history entry can be deleted.",
            )
        if run.job.status is not JobStatus.COMPLETED:
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_JOB_ACTIVE",
                "The filename verification job is not terminal.",
            )
        if run.checkpoint.get("cleanup") != "completed":
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_HISTORY_DELETE_CLEANUP_INCOMPLETE",
                "The filename verification working data has not been safely cleaned.",
            )
        return self._repository.delete_completed_filename_verification_history(
            run_id=run.id,
            job_id=run.job.id,
        )

    def get(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._repository.get(run_id)
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run does not exist.",
            )
        return run

    def get_for_display(
        self, run_id: UUID, *, include_checkpoint: bool = False
    ) -> SemiAutomaticSelectionRun:
        """Use a bounded read projection when the persistence adapter provides it."""
        read = getattr(self._repository, "get_for_display", None)
        run: SemiAutomaticSelectionRun | None = (
            self._repository.get(run_id)
            if read is None
            else read(run_id, include_checkpoint=include_checkpoint)
        )
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run does not exist.",
            )
        return run

    def list_ranges(
        self,
        run_id: UUID,
        *,
        after_expected_index: int | None,
        limit: int,
    ) -> tuple[SemiAutomaticSelectionRange, ...]:
        run = self.get_for_display(run_id)
        if limit < 1 or limit > 500:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The expected-range page limit must be between 1 and 500.",
            )
        items = self._repository.list_ranges(
            run_id,
            after_expected_index=after_expected_index,
            limit=limit,
        )
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            return items
        try:
            directory = self._draft_folder(run)
            if directory is None:
                return items
            result = []
            for item in items:
                review = item.v7_review
                if (
                    review is None
                    or item.v7_output_owner_operation_id is not None
                    or review.get("candidate") is not None
                ):
                    result.append(item)
                    continue
                prepared_draft = read_draft(
                    directory,
                    run_id=str(run.id),
                    start=item.range_start,
                    end=item.range_end,
                    source_count=run.source.source_count,
                )
                result.append(replace(item, v7_review={**review, "draft": prepared_draft}))
            indexes = [
                cast(int, draft["sourceIndex"])
                for row in result
                if row.v7_review is not None
                and isinstance((draft := row.v7_review.get("draft")), dict)
            ]
            observations = (
                self._repository.get_v7_source_observations(run_id, indexes) if indexes else {}
            )
            for row in result:
                draft = None if row.v7_review is None else row.v7_review.get("draft")
                if isinstance(draft, dict):
                    observation = observations.get(cast(int, draft["sourceIndex"]), {})
                    if (
                        observation.get("sourceChecksumSha256") != draft["sourceChecksumSha256"]
                        or observation.get("sourceErrorCode") is not None
                    ):
                        raise ValueError(
                            "Draft source identity differs from the pinned observation."
                        )
            return tuple(result)
        except (OSError, ValueError) as error:
            raise SemiAutomaticSelectionConflictError(
                "V7_DRAFT_CATALOG_INVALID", str(error)
            ) from error

    def _draft_folder(self, run: SemiAutomaticSelectionRun) -> Path | None:
        if self._artifact_root is not None:
            pinned = draft_folder(
                self._artifact_root, run_id=str(run.id), fingerprint=run.source.source_fingerprint
            )
            if pinned is not None:
                return pinned
        if run.v7_configuration is not None and run.v7_configuration.output_directory is not None:
            return Path(run.v7_configuration.output_directory) / "propozycje"
        return None

    def open_review_folder(self) -> SemiAutomaticSelectionRun | None:
        if not self._enabled or self._output_picker is None:
            raise SemiAutomaticSelectionError(
                "V7_REVIEW_PICKER_UNAVAILABLE", "The local folder picker is unavailable."
            )
        selected = self._output_picker()
        if selected is None:
            return None
        try:
            reference = folder_reference(selected)
            if reference is not None:
                run = self.get_for_display(UUID(str(reference["runId"])))
                if (
                    run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION
                    or reference.get("sourceFingerprint") != run.source.source_fingerprint
                ):
                    raise ValueError("Review folder has foreign source identity.")
                directory = self._draft_folder(run)
                root = selected.parent if selected.name == "propozycje" else selected
                if directory is None or directory.parent != root and directory != root:
                    raise ValueError("Review folder does not match the pinned draft directory.")
                return run
            candidates = self._repository.find_v7_runs_by_source_name(selected.name)
            matches = []
            for run in candidates:
                manifest = self._local_source_manifest(run)
                if manifest is not None and manifest.source_root == selected:
                    matches.append(run)
            non_cancelled = [
                run
                for run in matches
                if run.status is not SemiAutomaticSelectionRunStatus.CANCELLED
            ]
            if non_cancelled:
                matches = non_cancelled
            if len(matches) != 1:
                raise ValueError(
                    "No unique saved run matches this source folder; select it in saved choices."
                )
            return matches[0]
        except (OSError, ValueError, KeyError) as error:
            raise SemiAutomaticSelectionConflictError(
                "V7_REVIEW_FOLDER_INVALID", str(error)
            ) from error

    def pause(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        return self._repository.save(pause_run(run))

    def resume(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        resumed = resume_run(run)
        if resumed.job.status is JobStatus.WAITING_FOR_REVIEW:
            resumed = replace(resumed, job=requeue_job(resumed.job))
        return self._repository.save(resumed)

    def cancel(self, run_id: UUID) -> SemiAutomaticSelectionRun:
        run = self._locked(run_id)
        updated = cancel_run(run)
        job = request_job_cancellation(updated.job)
        return self._repository.save(replace(updated, job=job))

    def acknowledge_output(
        self,
        run_id: UUID,
        expected_index: int,
        *,
        expected_revision: int,
        expected_source_checksum_sha256: str,
        output_checksum_sha256: str,
        source_index: int | None = None,
    ) -> SemiAutomaticSelectionRange:
        run = self._locked(run_id)
        if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            raise V7DeliveryConflict(
                "V7_MANUAL_COMMAND_REQUIRED", "V7 requires a reviewed manual command."
            )
        item = self._repository.get_range_for_update(run_id, expected_index)
        if item is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_RANGE_NOT_FOUND",
                "The expected range does not exist.",
            )
        if source_index is None:
            updated_item = acknowledge_output(
                item,
                expected_revision=expected_revision,
                expected_source_checksum_sha256=expected_source_checksum_sha256,
                output_checksum_sha256=output_checksum_sha256,
            )
        else:
            sources = self._source_entries(run)
            if source_index < 0 or source_index >= len(sources):
                raise SemiAutomaticSelectionNotFoundError(
                    "SEMI_AUTOMATIC_SELECTION_SOURCE_NOT_FOUND",
                    "The requested source does not exist.",
                )
            source = sources[source_index]
            if source.checksum_sha256 != expected_source_checksum_sha256:
                raise SemiAutomaticSelectionConflictError(
                    "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                    "The manually selected source changed after it was loaded.",
                )
            updated_item = acknowledge_manual_output(
                item,
                expected_revision=expected_revision,
                source_index=source.source_index,
                source_relative_path=source.relative_path,
                source_size_bytes=source.size_bytes,
                source_checksum_sha256=source.checksum_sha256,
                output_checksum_sha256=output_checksum_sha256,
            )
        updated_run = apply_range_status_transition(run, previous=item, current=updated_item)
        _, stored_item = self._repository.save_run_and_range(updated_run, updated_item)
        return stored_item

    def acknowledge_v7_output(
        self, run_id: UUID, expected_index: int, decision: V7OutputDecision
    ) -> SemiAutomaticSelectionRange:
        existing = self._repository.get_v7_output_operation(decision.operation_id)
        # Terminal replay is read-only and survives a later replace or gate closure.
        if existing is not None and existing.state not in V7_PENDING_STATES:
            self._require_operation_body(existing, run_id, decision)
            items = self._repository.list_ranges(
                run_id, after_expected_index=expected_index - 1, limit=1
            )
            if (
                not items
                or items[0].expected_index != expected_index
                or items[0].id != existing.range_id
            ):
                raise V7DeliveryConflict(
                    "V7_OPERATION_ID_CONFLICT", "Operation belongs to another range."
                )
            return replace(
                items[0],
                output_operation=existing.as_response(),
                acknowledgement_receipt=existing.receipt,
            )
        run = self._repository.get_for_v7_review(run_id, for_update=True)
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND", "The selection run does not exist."
            )
        item = self._repository.get_range_for_update(run_id, expected_index)
        if item is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_RANGE_NOT_FOUND", "Range does not exist."
            )
        if run.workflow_mode is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
            raise V7DeliveryConflict("V7_WORKFLOW_REQUIRED", "Manual V7 command requires a V7 run.")
        configuration = run.v7_configuration
        manifest = self._local_source_manifest(run)
        if (
            configuration is None
            or configuration.pilot is None
            or manifest is None
            or self._v7_artifacts is None
        ):
            raise V7DeliveryConflict(
                "SEMI_AUTOMATIC_SELECTION_V7_BLOCKED", "V7 pilot configuration is unavailable."
            )
        gate = self._repository.get_v7_pilot_gate(for_update=True)
        gate.require_snapshot(
            configuration.pilot, manifest.source_root, manifest.source_fingerprint
        )
        self._v7_artifacts.validate(gate)
        existing = self._repository.get_v7_output_operation(decision.operation_id, for_update=True)
        if existing is not None:
            self._require_operation_body(existing, run_id, decision)
            if existing.range_id != item.id:
                raise V7DeliveryConflict(
                    "V7_OPERATION_ID_CONFLICT", "Operation belongs to another range."
                )
            if (
                run.status == SemiAutomaticSelectionRunStatus.CANCELLED
                or run.job.status == JobStatus.CANCELLED
            ):
                raise V7DeliveryConflict(
                    "V7_OUTPUT_RETRY_FORBIDDEN", "Cancelled jobs cannot retry output."
                )
            if existing.state in V7_PENDING_STATES and run.job.status in {
                JobStatus.FAILED,
                JobStatus.WAITING_FOR_REVIEW,
            }:
                self._repository.save_v7_review_state(
                    replace(
                        run,
                        job=requeue_job(run.job),
                        status=SemiAutomaticSelectionRunStatus.SYNCING_OUTPUT,
                    )
                )
            return replace(
                item,
                output_operation=existing.as_response(),
                acknowledgement_receipt=existing.receipt,
            )
        if self._repository.get_pending_v7_output(run_id, for_update=True) is not None:
            raise V7DeliveryConflict(
                "V7_OUTPUT_DECISION_PENDING", "An output decision is still pending."
            )
        if (
            run.status
            not in {
                SemiAutomaticSelectionRunStatus.ANALYSIS_COMPLETE,
                SemiAutomaticSelectionRunStatus.REVIEW_MODE,
            }
            or run.job.status not in {JobStatus.WAITING_FOR_REVIEW, JobStatus.FAILED}
            or run.checkpoint.get("blockedReason") is not None
            or not isinstance(run.checkpoint.get("scanState"), dict)
            or cast(dict[str, object], run.checkpoint["scanState"]).get("phase") != "finalized"
        ):
            raise V7DeliveryConflict(
                "V7_SCAN_FINALIZATION_REQUIRED", "The run is not ready for reviewed output."
            )
        if item.revision != decision.expected_revision:
            raise V7DeliveryConflict(
                "SEMI_AUTOMATIC_SELECTION_CURSOR_STALE", "The range revision changed."
            )
        if not 0 <= decision.source_index < len(manifest.sources):
            raise V7DeliveryConflict("V7_SOURCE_NOT_ANALYZED", "The source is outside this run.")
        source = manifest.sources[decision.source_index]
        if source.checksum_sha256 != decision.expected_source_checksum_sha256:
            raise V7DeliveryConflict(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED", "The source SHA changed."
            )
        diagnostics = self._repository.get_v7_source_observations(
            run_id, [decision.source_index]
        ).get(decision.source_index)
        if diagnostics is None or diagnostics.get("sourceErrorCode") is not None:
            raise V7DeliveryConflict(
                "V7_SOURCE_NOT_ANALYZED", "The source has no decoded observation."
            )
        if item.v7_review is None or item.v7_projection_fingerprint is None:
            raise V7DeliveryConflict(
                "V7_SCAN_FINALIZATION_REQUIRED", "The range has no final review projection."
            )
        if not item.range_start <= decision.range_start <= decision.range_end <= item.range_end:
            raise V7DeliveryConflict(
                "V7_CONFIRMED_RANGE_INVALID", "Confirmed range is outside the expected page."
            )
        partial = decision.range_end - decision.range_start + 1 < 9
        last_start = (
            run.first_sequence_number
            if run.direction is SemiAutomaticSelectionDirection.DESCENDING
            else run.last_sequence_number - 8
        )
        if partial and (
            item.range_start != last_start
            or not decision.operator_confirmed_incomplete_page
            or (decision.kind != "manual_no_ocr" and item.v7_output_owner_operation_id is None)
        ):
            raise V7DeliveryConflict(
                "V7_INCOMPLETE_PAGE_CONFIRMATION_REQUIRED",
                "Confirm an actually incomplete last page without OCR.",
            )
        if item.v7_output_owner_operation_id is not None:
            if (
                decision.kind != "manual_replace"
                or decision.expected_owner_operation_id != item.v7_output_owner_operation_id
                or decision.expected_target_checksum_sha256 != item.output_checksum_sha256
                or (decision.range_start, decision.range_end)
                != (item.v7_confirmed_range_start, item.v7_confirmed_range_end)
            ):
                raise V7DeliveryConflict(
                    "V7_OUTPUT_OWNER_CHANGED",
                    "Replace requires the same confirmed target and current owner/SHA.",
                )
        elif decision.kind == "manual_replace":
            raise V7DeliveryConflict(
                "V7_OUTPUT_OWNER_REQUIRED", "An unowned target cannot be replaced."
            )
        if decision.kind == "manual_first":
            proofs = cast(list[dict[str, object]], item.v7_review.get("provenSources", []))
            if not any(proof.get("sourceIndex") == decision.source_index for proof in proofs):
                raise V7DeliveryConflict(
                    "V7_MANUAL_NO_OCR_REQUIRED",
                    "This source has no range proof; explicitly confirm without OCR.",
                )
        now = datetime.now(UTC)
        feedback_snapshot = capture_feedback_snapshot(
            manifest=manifest,
            expected_index=item.expected_index,
            expected_range=(item.range_start, item.range_end),
            review=deepcopy(item.v7_review),
            selected_diagnostics=diagnostics,
            decision=decision,
            configuration=configuration.as_payload(),
        )
        operation = V7OutputOperation(
            decision.operation_id,
            run_id,
            item.id,
            decision.as_payload(),
            {
                "sourceRelativePath": source.relative_path,
                "outputRoot": self.output_directory(run),
                "sourceSizeBytes": source.size_bytes,
                "projectionFingerprint": item.v7_projection_fingerprint,
                "pilotSnapshot": configuration.pilot.as_payload(),
                "manifestChecksumSha256": manifest.checksum_sha256,
                "sourceFingerprint": manifest.source_fingerprint,
                "feedbackSnapshot": feedback_snapshot,
                "feedbackFingerprint": payload_fingerprint(feedback_snapshot),
            },
            0 if item.v7_output_generation is None else item.v7_output_generation + 1,
            item.revision + 1,
            "reserved",
            None,
            None,
            now,
            now,
        )
        updated_item = replace(item, revision=item.revision + 1, updated_at=now)
        updated_run = apply_range_status_transition(run, previous=item, current=updated_item)
        updated_run = replace(
            updated_run,
            job=requeue_job(run.job),
            status=SemiAutomaticSelectionRunStatus.SYNCING_OUTPUT,
        )
        self._repository.save_range(updated_item)
        self._repository.save_v7_review_state(updated_run)
        stored_operation = self._repository.save_v7_output_operation(operation)
        return replace(updated_item, output_operation=stored_operation.as_response())

    @staticmethod
    def _require_operation_body(
        operation: V7OutputOperation, run_id: UUID, decision: V7OutputDecision
    ) -> None:
        if operation.run_id != run_id or operation.request_payload != decision.as_payload():
            raise V7DeliveryConflict(
                "V7_OPERATION_ID_CONFLICT", "Operation UUID has another immutable request."
            )

    def v7_source_diagnostics(
        self, run_id: UUID, source_indexes: Sequence[int]
    ) -> dict[int, dict[str, object]]:
        run = self.get_for_display(run_id)
        return (
            self._repository.get_v7_source_observations(run_id, source_indexes)
            if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION
            else {}
        )

    def source_asset(
        self,
        run_id: UUID,
        source_index: int,
        *,
        expected_checksum_sha256: str,
    ) -> tuple[Path, str]:
        run = self.get_for_display(run_id)
        local_manifest = self._local_source_manifest(run)
        if local_manifest is not None:
            try:
                path, source = resolve_local_source_asset(
                    local_manifest,
                    source_index=source_index,
                    expected_checksum_sha256=expected_checksum_sha256,
                )
            except LocalSourceManifestError as error:
                raise SemiAutomaticSelectionConflictError(error.code, str(error)) from error
            return path, PurePosixPath(source.relative_path).name
        return self._staging.get_ready_source_asset(
            run.source.upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
            source_index=source_index,
            expected_checksum_sha256=expected_checksum_sha256,
        )

    def list_sources(
        self,
        run_id: UUID,
        *,
        after_source_index: int | None,
        limit: int,
    ) -> tuple[BrowserReadySource, ...]:
        if limit < 1 or limit > 500:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_PAGE_INVALID",
                "The source page limit must be between 1 and 500.",
            )
        run = self.get_for_display(run_id)
        sources = self._source_entries(run)
        first = 0 if after_source_index is None else after_source_index + 1
        return sources[first : first + limit]

    def _source_entries(self, run: SemiAutomaticSelectionRun) -> tuple[BrowserReadySource, ...]:
        local_manifest = self._local_source_manifest(run)
        if local_manifest is not None:
            return tuple(
                BrowserReadySource(
                    source_index=source.source_index,
                    relative_path=source.relative_path,
                    stored_file_name=source.relative_path,
                    size_bytes=source.size_bytes,
                    checksum_sha256=source.checksum_sha256,
                )
                for source in local_manifest.sources
            )
        return self._staging.get_ready_source_selection(
            run.source.upload_id,
            purpose=ImageSelectionPurpose.SEMI_AUTOMATIC_SELECTION,
        ).sources

    def _local_source_manifest(
        self,
        run: SemiAutomaticSelectionRun,
    ) -> LocalSourceManifest | None:
        payload = run.job.input_payload
        version = payload.get("schema_version")
        if version not in {3, 4}:
            if run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION:
                raise V7DeliveryConflict(
                    "V7_SOURCE_MANIFEST_REQUIRED", "V7 requires schema 4 local sources."
                )
            return None
        if (version == 4) != (run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION):
            raise V7DeliveryConflict(
                "V7_SOURCE_MANIFEST_REQUIRED", "Source schema/workflow mismatch."
            )
        if self._artifact_root is None:
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_MANIFEST_UNAVAILABLE",
                "The local source manifest store is unavailable.",
            )
        relative_path = payload.get("source_manifest_relative_path")
        if payload.get("source_kind") != "local_folder" or not isinstance(relative_path, str):
            raise SemiAutomaticSelectionError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The local source contract is invalid.",
            )
        try:
            manifest = load_local_source_manifest(
                self._artifact_root,
                relative_path=relative_path,
                expected_checksum_sha256=run.source.manifest_checksum_sha256,
                expected_selection_id=run.source.upload_id,
            )
        except LocalSourceManifestError as error:
            raise SemiAutomaticSelectionError(error.code, str(error)) from error
        if (
            manifest.source_fingerprint != run.source.source_fingerprint
            or len(manifest.sources) != run.source.source_count
            or manifest.total_bytes != run.source.source_total_bytes
        ):
            raise SemiAutomaticSelectionConflictError(
                "SEMI_AUTOMATIC_SELECTION_SOURCE_CHANGED",
                "The local source manifest differs from the durable run.",
            )
        return manifest

    def _locked(self, run_id: UUID, *, allow_v7_pending: bool = False) -> SemiAutomaticSelectionRun:
        run = self._repository.get(run_id, for_update=True)
        if run is None:
            raise SemiAutomaticSelectionNotFoundError(
                "SEMI_AUTOMATIC_SELECTION_NOT_FOUND",
                "The semi-automatic selection run does not exist.",
            )
        if (
            run.workflow_mode is SemiAutomaticSelectionWorkflowMode.V7_SELECTION
            and not allow_v7_pending
            and self._repository.get_pending_v7_output(run_id) is not None
        ):
            raise V7DeliveryConflict(
                "V7_OUTPUT_DECISION_PENDING", "An output decision is still pending."
            )
        return run


def _filename_verification_source_index(item: dict[str, object]) -> int:
    value = item.get("sourceIndex")
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemiAutomaticSelectionError(
            "SEMI_AUTOMATIC_SELECTION_CHECKPOINT_INVALID",
            "A filename verification item has an invalid source index.",
        )
    return value


def _committed_observation_count(run: SemiAutomaticSelectionRun) -> int:
    raw = run.checkpoint.get("observationCount")
    if isinstance(raw, int) and not isinstance(raw, bool):
        return max(0, min(raw, run.source.source_count))
    processed = run.counters.get("processedSources", 0)
    return max(0, min(processed, run.source.source_count))


__all__ = [
    "SEMI_AUTOMATIC_GROUPING_CONTRACT_FINGERPRINT",
    "SEMI_AUTOMATIC_DEFAULT_RECOGNIZER_VARIANT",
    "SEMI_AUTOMATIC_FIVE_ANCHOR_RECOGNIZER_VARIANT",
    "SEMI_AUTOMATIC_RECOGNIZER_FINGERPRINT",
    "SEMI_AUTOMATIC_FILENAME_VERIFICATION_MODE",
    "SEMI_AUTOMATIC_SELECTION_MODE",
    "SEMI_AUTOMATIC_V7_SELECTION_MODE",
    "V7_SELECTION_ACTIVATION_STATUS",
    "V7_SELECTION_BLOCKED_REASON",
    "SemiAutomaticImageSelectionService",
    "SemiAutomaticSelectionRepository",
    "workflow_mode_for_recognizer_fingerprint",
]
