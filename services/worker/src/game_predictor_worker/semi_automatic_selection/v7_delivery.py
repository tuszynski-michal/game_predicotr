"""Execute the SQL outbox through the existing NTFS journal with a fenced receipt."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import cast
from uuid import UUID

from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.semi_automatic_image_selections import (
    SemiAutomaticSelectionRun,
    SemiAutomaticSelectionWorkflowMode,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7_PENDING_STATES,
    V7DeliveryConflict,
)
from game_predictor_api.domain.v7_selection_delivery import (
    V7OutputOperation as DurableOperation,
)
from game_predictor_api.storage.models import (
    SemiAutomaticImageSelectionRangeModel,
    SemiAutomaticImageSelectionRunModel,
)
from game_predictor_api.storage.semi_automatic_image_selection_repository import (
    SqlAlchemySemiAutomaticSelectionRepository,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .contracts import SemiAutomaticSelectionRange, SemiAutomaticSelectionSource
from .local_source_manifest import LocalSourceManifest, build_local_source_manifest
from .v7_output_writer import (
    FaultHook,
    PublicationRecorder,
    V7ManualOutputRequest,
    V7OutputDecisionKind,
    V7OutputOperation,
    V7OutputOperationState,
    V7OutputWriter,
    V7OutputWriterError,
)
from .v7_pilot_configuration import V7PilotArtifacts
from .v7_run_state import V7PinnedSourceManifest


def writer_request(operation: DurableOperation) -> V7ManualOutputRequest:
    decision = operation.decision
    return V7ManualOutputRequest(
        operation_id=operation.operation_id,
        sequence_range=SemiAutomaticSelectionRange(decision.range_start, decision.range_end),
        source_index=decision.source_index,
        source_relative_path=cast(str, operation.context_payload["sourceRelativePath"]),
        source_size_bytes=cast(int, operation.context_payload["sourceSizeBytes"]),
        source_checksum_sha256=decision.expected_source_checksum_sha256,
        decision_kind=V7OutputDecisionKind(decision.kind),
        decision_generation=operation.decision_generation,
        operator_confirmed_range=decision.operator_confirmed_range,
        expected_previous_checksum_sha256=decision.expected_target_checksum_sha256,
        expected_previous_owner_operation_id=decision.expected_owner_operation_id,
    )


def output_receipt(
    operation: DurableOperation,
    state: str,
    *,
    error_code: str | None = None,
) -> dict[str, object]:
    decision = operation.decision
    return {
        "operationId": str(operation.operation_id),
        "state": state,
        "sourceIndex": decision.source_index,
        "sourceChecksumSha256": decision.expected_source_checksum_sha256,
        "confirmedRange": {"start": decision.range_start, "end": decision.range_end},
        "targetName": writer_request(operation).target_name,
        "ownerOperationId": str(operation.operation_id) if state == "committed" else None,
        "decisionGeneration": operation.decision_generation,
        "outputChecksumSha256": (
            decision.expected_source_checksum_sha256 if state == "committed" else None
        ),
        "errorCode": error_code,
    }


def _operation_output_root(operation: DurableOperation, manifest: LocalSourceManifest) -> Path:
    value = operation.context_payload.get("outputRoot")
    if value is None:  # Commands reserved before output-root pinning retain their old path.
        return manifest.source_root.with_name(f"{manifest.source_root.name} cut")
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise V7DeliveryConflict("V7_OUTPUT_PATH_UNSAFE", "The pinned output directory is invalid.")
    return Path(value)


class V7ReviewedDelivery:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        artifacts: V7PilotArtifacts,
        *,
        fault_hook: FaultHook | None = None,
        filesystem_validator: Callable[[Path], bool] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._artifacts = artifacts
        self._fault_hook = fault_hook
        self._filesystem_validator = filesystem_validator

    def pending(self, run_id: UUID) -> DurableOperation | None:
        with self._session_factory() as session:
            return SqlAlchemySemiAutomaticSelectionRepository(session).get_pending_v7_output(run_id)

    def execute(
        self,
        context: JobExecutionContext,
        run: SemiAutomaticSelectionRun,
        manifest: LocalSourceManifest,
    ) -> None:
        operation = self.pending(run.id)
        if operation is None:
            return
        guard = _SqlPublicationGuard(
            self._session_factory, context, run, manifest, operation, self._artifacts
        )
        writer = V7OutputWriter(
            manifest,
            # The finalized manifest was loaded and verified by checksum by the
            # handler. The writer verifies the selected file and copied bytes;
            # unrelated source JPEGs are not rehashed for each manual decision.
            refresh_manifest=lambda: manifest,
            output_root=_operation_output_root(operation, manifest),
            generation_validator=guard.generation_is_current,
            publication_guard=guard.publication_guard,
            fault_hook=self._fault_hook,
            filesystem_validator=self._filesystem_validator,
        )
        try:
            self._preflight(run, manifest)
            request = writer_request(operation)
            if request.decision_kind is V7OutputDecisionKind.MANUAL_REPLACE:
                writer.manual_replace(request)
            elif request.decision_kind is V7OutputDecisionKind.MANUAL_NO_OCR:
                writer.write_manual_no_ocr(request)
            else:
                writer.write_manual_first(request)
        except JobConflictError as error:
            if error.code == "JOB_LEASE_LOST":
                raise
            self._record_failure(context, run, operation, writer, error.code)
            raise JobHandlerError(error.code, str(error)) from error
        except (V7OutputWriterError, OSError, ValueError, RuntimeError) as error:
            code = getattr(error, "code", "V7_OUTPUT_RECOVERY_REQUIRED")
            self._record_failure(context, run, operation, writer, code)
            raise JobHandlerError(code, str(error)) from error

    def _preflight(self, run: SemiAutomaticSelectionRun, manifest: LocalSourceManifest) -> None:
        configuration = run.v7_configuration
        if configuration is None or configuration.pilot is None:
            raise V7DeliveryConflict("V7_PILOT_SNAPSHOT_REQUIRED", "Missing reviewed pilot pin.")
        with self._session_factory() as session:
            gate = SqlAlchemySemiAutomaticSelectionRepository(session).get_v7_pilot_gate()
        gate.require_snapshot(
            configuration.pilot, manifest.source_root, manifest.source_fingerprint
        )
        self._artifacts.validate(gate)

    def require_review_current(
        self, run: SemiAutomaticSelectionRun, manifest: LocalSourceManifest
    ) -> None:
        self._preflight(run, manifest)
        current = build_local_source_manifest(
            manifest.source_root,
            selection_id=manifest.selection_id,
            display_name=manifest.display_name,
        )
        if (
            current.checksum_sha256 != manifest.checksum_sha256
            or current.sources != manifest.sources
        ):
            raise V7DeliveryConflict("V7_SOURCE_MANIFEST_DRIFT", "The reviewed inventory changed.")

    def _record_failure(
        self,
        context: JobExecutionContext,
        run: SemiAutomaticSelectionRun,
        operation: DurableOperation,
        writer: V7OutputWriter | None,
        code: str,
    ) -> None:
        # Classify only after leaving the writer's directory/SQL critical section.
        try:
            may_have_published = (
                True if writer is None else writer.publication_may_exist(operation.operation_id)
            )
        except (OSError, V7OutputWriterError):
            may_have_published = True
        target_conflict = code in {
            "V7_OUTPUT_TARGET_CONFLICT",
            "V7_OUTPUT_TARGET_CHECKSUM_MISMATCH",
            "V7_OUTPUT_REPLACE_OWNER_CHANGED",
            "V7_OUTPUT_REPLACE_CHECKSUM_MISMATCH",
            "V7_OUTPUT_PREVIOUS_OWNER_CHANGED",
            "V7_OUTPUT_PREVIOUS_CHECKSUM_MISMATCH",
            "V7_OUTPUT_REPLACE_STALE_TARGET",
            "V7_OUTPUT_TARGET_OWNER_CONFLICT",
            "V7_OUTPUT_TEMP_CHECKSUM_MISMATCH",
        }
        transient = code in {
            "V7_OUTPUT_RECOVERY_REQUIRED",
            "V7_OUTPUT_LOCK_BUSY",
            "V7_OUTPUT_WRITE_FAILED",
            "V7_OUTPUT_COPY_FAILED",
            "V7_OUTPUT_JOURNAL_WRITE_FAILED",
            "V7_OUTPUT_PUBLISH_FAILED",
            "V7_OUTPUT_REPLACE_FAILED",
            "V7_OUTPUT_READ_FAILED",
        }
        if transient or (may_have_published and not target_conflict):
            state = "recovery_required"
        elif target_conflict:
            state = "conflict"
        else:
            state = "failed"
        from .job import _assert_fence, _locked_run

        with self._session_factory() as session, session.begin():
            repo = SqlAlchemySemiAutomaticSelectionRepository(session)
            repo.get_v7_pilot_gate(for_update=True)
            _assert_fence(session, run.job.id, context.lease_token, context.now())
            record = _locked_run(session, run.id, include_checkpoint=False)
            session.scalar(
                select(SemiAutomaticImageSelectionRangeModel)
                .where(SemiAutomaticImageSelectionRangeModel.id == operation.range_id)
                .with_for_update()
            )
            current = repo.get_v7_output_operation(operation.operation_id, for_update=True)
            if current is None or current.state not in V7_PENDING_STATES:
                return  # A SQL receipt already committed; never turn success into failure.
            repo.save_v7_output_operation(
                replace(
                    current,
                    state=state,
                    error_code=code,
                    receipt=None
                    if state == "recovery_required"
                    else output_receipt(current, state, error_code=code),
                    updated_at=context.now(),
                )
            )
            record.status = "syncing_output" if state == "recovery_required" else "review_mode"
            record.revision += 1
            record.updated_at = context.now()

    def dispatch_failure(
        self,
        context: JobExecutionContext,
        run: SemiAutomaticSelectionRun,
        code: str,
        manifest: LocalSourceManifest | None,
    ) -> None:
        """Classify errors before delivery dispatch against the durable journal too."""
        operation = self.pending(run.id)
        if operation is None:
            return
        writer = None
        try:
            if manifest is None:
                scan_state = run.checkpoint.get("scanState")
                if not isinstance(scan_state, dict):
                    raise ValueError("Missing pinned V7 source checkpoint.")
                pinned = V7PinnedSourceManifest.from_dict(scan_state.get("sourceManifest"))
                manifest = LocalSourceManifest(
                    pinned.selection_id,
                    run.source.display_name,
                    pinned.source_root,
                    tuple(
                        SemiAutomaticSelectionSource(
                            source.source_index,
                            source.relative_path,
                            source.size_bytes,
                            source.checksum_sha256,
                        )
                        for source in pinned.sources
                    ),
                    pinned.source_fingerprint,
                    run.source.source_total_bytes,
                    b"",
                    pinned.manifest_checksum_sha256,
                )
            # This instance only inspects the journal; it cannot copy or publish.
            writer = V7OutputWriter(
                manifest,
                refresh_manifest=lambda: manifest,
                output_root=_operation_output_root(operation, manifest),
            )
        except (ValueError, OSError, V7DeliveryConflict):
            pass  # Unreadable durable identity requires explicit recovery, never cancellation.
        self._record_failure(context, run, operation, writer, code)

    def block_scan_failure(
        self,
        context: JobExecutionContext,
        run: SemiAutomaticSelectionRun,
        code: str,
    ) -> None:
        """A terminal pre-output scan/config error cannot leave a runnable anonymous state."""
        from .job import _assert_fence, _locked_run

        with self._session_factory() as session, session.begin():
            repo = SqlAlchemySemiAutomaticSelectionRepository(session)
            repo.get_v7_pilot_gate(for_update=True)
            _assert_fence(session, run.job.id, context.lease_token, context.now())
            record = _locked_run(session, run.id)
            if repo.get_pending_v7_output(run.id) is not None:
                return  # Delivery errors own their journal-aware classification.
            record.status = "failed"
            record.checkpoint = {**record.checkpoint, "blockedReason": code}
            record.revision += 1
            record.updated_at = context.now()


class _SqlPublicationGuard:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        context: JobExecutionContext,
        run: SemiAutomaticSelectionRun,
        manifest: LocalSourceManifest,
        operation: DurableOperation,
        artifacts: V7PilotArtifacts,
    ) -> None:
        self._session_factory = session_factory
        self._context = context
        self._run = run
        self._manifest = manifest
        self._operation = operation
        self._artifacts = artifacts
        self._validated_operation: UUID | None = None

    def generation_is_current(self, operation: V7OutputOperation) -> bool:
        # This callback cannot perform an unlocked second SQL read. The guard owns the locks.
        return self._validated_operation == operation.operation_id

    @contextmanager
    def publication_guard(
        self, journal_operation: V7OutputOperation
    ) -> Iterator[PublicationRecorder | None]:
        from .job import _assert_fence, _locked_run

        # Hash immutable artifacts under the directory lock, before SQL row locks.
        # The short transaction below rechecks the exact receipt/generation pin.
        with self._session_factory() as read_session:
            verified = SqlAlchemySemiAutomaticSelectionRepository(read_session).get_v7_pilot_gate()
        self._artifacts.validate(verified)
        with self._session_factory() as session, session.begin():
            repo = SqlAlchemySemiAutomaticSelectionRepository(session)
            gate = repo.get_v7_pilot_gate(for_update=True)
            _assert_fence(session, self._run.job.id, self._context.lease_token, self._context.now())
            record = _locked_run(session, self._run.id, include_checkpoint=False)
            identity = repo.get_v7_output_operation(journal_operation.operation_id)
            if identity is None or identity.run_id != self._run.id:
                raise V7DeliveryConflict(
                    "V7_OUTPUT_FOREIGN_OPERATION", "Journal has a foreign operation."
                )
            item = session.scalar(
                select(SemiAutomaticImageSelectionRangeModel)
                .where(SemiAutomaticImageSelectionRangeModel.id == identity.range_id)
                .with_for_update()
            )
            current = repo.get_v7_output_operation(journal_operation.operation_id, for_update=True)
            if (
                current is None
                or item is None
                or writer_request(current).command_fingerprint
                != journal_operation.command_fingerprint
            ):
                raise V7DeliveryConflict(
                    "V7_OPERATION_ID_CONFLICT", "Journal and SQL commands differ."
                )
            if current.state not in V7_PENDING_STATES:
                if current.receipt is None:
                    raise V7DeliveryConflict(
                        "V7_OUTPUT_RECEIPT_INVALID", "Historical command has no receipt."
                    )
                yield None  # Historical receipt never restores the owner after a later replacement.
                return
            if current.operation_id != self._operation.operation_id:
                raise V7DeliveryConflict(
                    "V7_OUTPUT_FOREIGN_OPERATION", "Another command is pending."
                )
            configuration = repo.get_for_v7_review(self._run.id)
            if (
                configuration is None
                or configuration.v7_configuration is None
                or configuration.v7_configuration.pilot is None
                or configuration.workflow_mode
                is not SemiAutomaticSelectionWorkflowMode.V7_SELECTION
            ):
                raise V7DeliveryConflict("V7_PILOT_SNAPSHOT_REQUIRED", "Missing V7 run pin.")
            gate.require_snapshot(
                configuration.v7_configuration.pilot,
                self._manifest.source_root,
                self._manifest.source_fingerprint,
            )
            _require_current_command(
                record, item, current, self._manifest, configuration.checkpoint
            )
            self._validated_operation = current.operation_id

            def record_receipt(committed: V7OutputOperation) -> None:
                _assert_fence(
                    session, self._run.job.id, self._context.lease_token, self._context.now()
                )
                if committed.operation_id != current.operation_id or committed.state not in {
                    V7OutputOperationState.COMMITTED,
                    V7OutputOperationState.CONFLICT,
                }:
                    raise V7DeliveryConflict(
                        "V7_OUTPUT_RECEIPT_INVALID", "Writer has no final outcome."
                    )
                state = (
                    "committed"
                    if committed.state is V7OutputOperationState.COMMITTED
                    else "conflict"
                )
                changed_at = self._context.now()
                if state == "committed":
                    apply_output_owner(record, item, current, changed_at)
                repo.save_v7_output_operation(
                    replace(
                        current,
                        state=state,
                        error_code=committed.conflict_code,
                        receipt=output_receipt(current, state, error_code=committed.conflict_code),
                        updated_at=changed_at,
                    )
                )
                record.status = "review_mode"
                record.revision += 1
                record.updated_at = changed_at

            try:
                yield record_receipt
            finally:
                self._validated_operation = None


def _require_current_command(
    run: SemiAutomaticImageSelectionRunModel,
    item: SemiAutomaticImageSelectionRangeModel,
    operation: DurableOperation,
    manifest: LocalSourceManifest,
    checkpoint: dict[str, object],
) -> None:
    decision = operation.decision
    configuration = run.v7_configuration
    if (
        run.status != "syncing_output"
        or configuration is None
        or checkpoint.get("blockedReason") is not None
        or not isinstance(checkpoint.get("scanState"), dict)
        or cast(dict[str, object], checkpoint["scanState"]).get("phase") != "finalized"
        or item.revision != operation.reserved_revision
        or item.v7_projection_fingerprint != operation.context_payload.get("projectionFingerprint")
        or configuration.get("pilot") != operation.context_payload.get("pilotSnapshot")
        or manifest.checksum_sha256 != operation.context_payload.get("manifestChecksumSha256")
        or manifest.source_fingerprint != operation.context_payload.get("sourceFingerprint")
        or operation.decision_generation
        != (0 if item.v7_output_generation is None else item.v7_output_generation + 1)
    ):
        raise V7DeliveryConflict(
            "V7_OUTPUT_STALE_GENERATION", "Run/revision/projection/generation changed."
        )
    if decision.kind == "manual_replace":
        if (
            item.v7_output_owner_operation_id != decision.expected_owner_operation_id
            or item.output_checksum_sha256 != decision.expected_target_checksum_sha256
            or (item.v7_confirmed_range_start, item.v7_confirmed_range_end)
            != (decision.range_start, decision.range_end)
        ):
            raise V7DeliveryConflict("V7_OUTPUT_OWNER_CHANGED", "The target owner changed.")
    elif item.v7_output_owner_operation_id is not None:
        raise V7DeliveryConflict("V7_OUTPUT_OWNER_CHANGED", "First output already has an owner.")


def apply_output_owner(
    run: SemiAutomaticImageSelectionRunModel,
    item: SemiAutomaticImageSelectionRangeModel,
    operation: DurableOperation,
    changed_at: datetime,
) -> None:
    decision = operation.decision
    counters = dict(run.counters)
    previous_key = {
        "proposed": "proposed",
        "missing": "missing",
        "output_synced": "outputSynced",
    }.get(item.status)
    if previous_key is not None:
        counters[previous_key] = max(0, int(counters.get(previous_key, 0)) - 1)
    counters["outputSynced"] = int(counters.get("outputSynced", 0)) + 1
    if item.v7_output_owner_operation_id is None:
        counters["manualSelected"] = int(counters.get("manualSelected", 0)) + 1
    run.counters = counters
    item.status = "output_synced"
    item.source_index = decision.source_index
    item.source_relative_path = cast(str, operation.context_payload["sourceRelativePath"])
    item.source_size_bytes = cast(int, operation.context_payload["sourceSizeBytes"])
    item.source_checksum_sha256 = decision.expected_source_checksum_sha256
    item.output_checksum_sha256 = decision.expected_source_checksum_sha256
    item.selection_method = decision.kind
    item.v7_output_owner_operation_id = operation.operation_id
    item.v7_output_generation = operation.decision_generation
    item.v7_confirmed_range_start = decision.range_start
    item.v7_confirmed_range_end = decision.range_end
    item.revision += 1
    item.updated_at = changed_at
