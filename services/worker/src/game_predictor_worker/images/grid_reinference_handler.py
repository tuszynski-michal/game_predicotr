"""Resumable prepare/infer phases with per-source atomic selected writes."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4, uuid5

import numpy as np
from game_predictor_api.application.grid_reinference import (
    CONTRACT,
    SOURCE_DEADLINE_SECONDS,
    canonical,
    digest,
    now_text,
)
from game_predictor_api.application.grid_reinference_stats import (
    EFFECT_FIELDS,
    STATS_POLICY,
    add_counts,
    empty_effect,
    refresh_effect_gap,
)
from game_predictor_api.application.virtual_grid_geometry import (
    VirtualGridGeometryService,
    VirtualGridGeometrySourceCommand,
)
from game_predictor_api.domain.image_geometry_v2 import (
    AttestedSequenceRange,
    SourceLatticeNodes,
    SourcePoint,
)
from game_predictor_api.domain.image_reviews import ImageReviewGeometryPoint
from game_predictor_api.domain.jobs import Job, update_job_progress
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_api.storage.grid_reinference import (
    SqlAlchemyGridReinferenceRepository,
    source_fence,
    target_fence,
    target_protection,
)
from game_predictor_api.storage.grid_reinference_models import GridReinferenceSourceModel as Source
from game_predictor_api.storage.grid_reinference_models import GridReinferenceTargetModel as Target
from game_predictor_api.storage.image_review_repository import acquire_image_sequence_locks
from game_predictor_api.storage.job_repository import apply_job_to_record, job_from_record
from game_predictor_api.storage.models import ImageSourceGeometryRevisionModel, JobModel
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)
from sqlalchemy import select, text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
from game_predictor_worker.geometry_core.proposal_runtime import CPUGridProposalRunner
from game_predictor_worker.images.normalization import (
    CanonicalSourceLoader,
    CanonicalSourceLoadError,
)
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .pending_grid_reinference import PendingGridReinferenceHandler


class GridReinferenceHandler:
    def __init__(
        self, session_factory: sessionmaker[Session], artifact_root: Path, *, runner: Any = None
    ) -> None:
        self.sessions, self.root, self.runner = session_factory, artifact_root.resolve(), runner

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        if job.input_payload.get("inference_kind") != CONTRACT:
            return PendingGridReinferenceHandler(self.sessions, self.root)(context, job)
        if job.input_payload.get("schema_version") != 3:
            raise JobHandlerError(
                "GRID_REINFERENCE_PAYLOAD_INVALID", "Unsupported reinference payload."
            )
        with self.sessions() as session, session.begin():
            repository = SqlAlchemyGridReinferenceRepository(session, self.root)
            operation = repository.worker_record(job)
            phase = operation.document["phase"]
        if phase == "prepare":
            self.prepare(context, job)
            return
        runner = self.runner or CPUGridProposalRunner(threads=1)
        try:
            self.infer(context, job, runner)
        finally:
            runner.close()

    @staticmethod
    def cancellation_boundary(context: JobExecutionContext) -> None:
        context.heartbeat()
        current = context.job
        if current.cancel_requested_at is not None:
            stage = current.stage or "grid_reinference:prepare"
            checkpoint = current.checkpoint_payload
            if checkpoint is None or checkpoint.get("schema_version") != 1:
                checkpoint = {
                    "schema_version": 1,
                    "workflow": CONTRACT,
                    "phase": "infer" if stage == "grid_reinference:infer" else "prepare",
                    "cursor": current.progress_current,
                }
            context.checkpoint(
                checkpoint_payload=checkpoint,
                stage=stage,
                current=current.progress_current,
                total=current.progress_total,
                success_count=current.success_count,
                failure_count=current.failure_count,
                review_count=current.review_count,
            )

    def prepare(self, context: JobExecutionContext, job: Job) -> None:
        self.cancellation_boundary(context)
        with self.sessions() as session, session.begin():
            repository = SqlAlchemyGridReinferenceRepository(session, self.root)
            operation = repository.worker_record(job)
            repository.capture(operation)
        while True:
            self.cancellation_boundary(context)
            with self.sessions() as session, session.begin():
                repository = SqlAlchemyGridReinferenceRepository(session, self.root)
                operation = repository.worker_record(job)
                done = repository.prepare_page(operation)
                self.progress(session, job, operation.document, "prepare")
            self.cancellation_boundary(context)
            if done:
                break
        # The job store finalizes the SHA and prepared state atomically with
        # removing the processing lease, rather than two separate commits.
        context.wait_for_review()

    def infer(self, context: JobExecutionContext, job: Job, runner: Any) -> None:
        assert job.game_id is not None and job.lease_token is not None
        self.cancellation_boundary(context)
        ManagedGridEngineModelStore(self.root).require(
            NeuralGridSnapshot.from_payload(job.input_payload["model_snapshot"]).version
        )
        while True:
            self.cancellation_boundary(context)
            with self.sessions() as session, session.begin():
                repository = SqlAlchemyGridReinferenceRepository(session, self.root)
                operation = repository.worker_record(job)
                d = copy.deepcopy(operation.document)
                if d.get("startSha256") != d["manifestSha256"]:
                    raise JobHandlerError(
                        "GRID_REINFERENCE_START_REQUIRED", "No authorized frozen target manifest."
                    )
                source = session.scalar(
                    select(Source)
                    .where(
                        Source.game_id == job.game_id,
                        Source.operation_id == operation.id,
                        Source.ordinal > d["processedSources"],
                    )
                    .order_by(Source.ordinal)
                    .limit(1)
                )
                if source is None:
                    return
                source_id, ordinal = source.source_image_id, source.ordinal
                source_missing = (
                    source.live_source_image_id != source_id
                    or session.scalar(
                        text("SELECT id FROM source_images WHERE game_id=:game AND id=:source"),
                        {"game": job.game_id, "source": source_id},
                    )
                    is None
                )
                source_document, checkpoint = (
                    copy.deepcopy(source.document),
                    copy.deepcopy(source.checkpoint),
                )
                targets = list(
                    session.scalars(
                        select(Target)
                        .where(
                            Target.game_id == job.game_id,
                            Target.operation_id == operation.id,
                            Target.source_ordinal == ordinal,
                        )
                        .order_by(Target.ordinal)
                    )
                )
                frozen = [copy.deepcopy(row.snapshot) for row in targets]
                operation_id = operation.id
                source_pin = d["modelSnapshot"]
            if checkpoint is None:
                checkpoint = (
                    self.save_checkpoint(
                        operation_id, ordinal, {"outcome": "source_missing", "byPosition": {}}
                    )
                    if source_missing
                    else self.recognize(
                        source_document, frozen, source_pin, operation_id, ordinal, runner, context
                    )
                )
                with self.sessions() as session, session.begin():
                    repository = SqlAlchemyGridReinferenceRepository(session, self.root)
                    repository.worker_record(job)
                    source = session.get(Source, (job.game_id, operation_id, ordinal))
                    assert source is not None
                    if source.checkpoint is None:
                        source.checkpoint = checkpoint
                    elif source.checkpoint != checkpoint:
                        raise JobHandlerError(
                            "GRID_REINFERENCE_CHECKPOINT_CONFLICT",
                            "The immutable source checkpoint differs.",
                        )
            self.cancellation_boundary(context)
            checkpoint_payload = self.load_checkpoint(checkpoint)
            # Render eligible exact slots outside all domain write transactions.
            prepared = None if source_missing else self.render(job, frozen, checkpoint_payload)
            self.cancellation_boundary(context)
            with self.sessions() as session, session.begin():
                repository = SqlAlchemyGridReinferenceRepository(session, self.root)
                operation = repository.worker_record(job)
                if ordinal <= operation.document["processedSources"]:
                    continue
                targets = list(
                    session.scalars(
                        select(Target)
                        .where(
                            Target.game_id == job.game_id,
                            Target.operation_id == operation_id,
                            Target.source_ordinal == ordinal,
                        )
                        .order_by(Target.ordinal)
                    )
                )
                acquire_sequence_ownership_lock(session, game_id=job.game_id)
                writer = SqlAlchemyVirtualGridGeometryRepository(session)
                writer._ensure_projection_state(job.game_id)
                acquire_image_sequence_locks(
                    session,
                    game_id=job.game_id,
                    sequence_numbers={
                        row.snapshot["sequenceNumber"]
                        for row in targets
                        if row.snapshot["sequenceNumber"] is not None
                    },
                )
                current_source = session.execute(
                    text(
                        """
SELECT to_jsonb(s) FROM source_images s WHERE s.game_id=:game AND s.id=:source FOR UPDATE
                        """
                    ),
                    {"game": job.game_id, "source": source_id},
                ).scalar_one_or_none()
                live_source = session.get(Source, (job.game_id, operation_id, ordinal))
                source_missing = (
                    live_source is None
                    or live_source.live_source_image_id != source_id
                    or current_source is None
                )
                source_conflict = (
                    current_source is None
                    or source_missing
                    or source_fence(current_source) != source_fence(source_document["source"])
                )
                latest_context = session.execute(
                    text(
                        """
SELECT to_jsonb(g) FROM image_source_geometry_revisions g WHERE g.game_id=:game AND
g.source_image_id=:source ORDER BY g.revision DESC LIMIT 1
                        """
                    ),
                    {"game": job.game_id, "source": source_id},
                ).scalar_one_or_none()
                if latest_context is None or latest_context != source_document["geometryContext"]:
                    source_conflict = True
                current = repository.source_targets(
                    job.game_id,
                    source_id,
                    {"categories": ["grid_issue", "deferred", "all_automatic"]},
                )
                current_by_position = {item["positionIndex"]: item for item in current}
                good, outcomes = [], {}
                for target in targets:
                    position = target.position_index
                    current_target = current_by_position.get(position)
                    outcome = None
                    if source_missing:
                        outcome = "source_missing"
                    elif (
                        source_conflict
                        or current_target is None
                        or digest(target_fence(current_target)) != target.fingerprint_sha256
                    ):
                        outcome = "conflict"
                    elif target_protection(target.snapshot):
                        outcome = "protected"
                    elif checkpoint_payload.get("outcome"):
                        outcome = checkpoint_payload["outcome"]
                    elif position not in checkpoint_payload["byPosition"]:
                        outcome = "binding_required"
                    elif self.unchanged(
                        target.snapshot, checkpoint_payload["byPosition"][position]
                    ):
                        outcome = "unchanged"
                    elif target.snapshot["kind"] == "grid_issue":
                        outcome = "proposal_ready"
                    else:
                        good.append(position)
                    outcomes[position] = outcome
                acceptance = {"status": "not_evaluated", "blockers": ["NO_AUTOMATIC_WRITE"]}
                effect_collector: dict[UUID, dict[str, Any]] = {}
                if good:
                    if prepared is None:
                        for position in good:
                            outcomes[position] = "conflict"
                    else:
                        entries = tuple(
                            entry
                            for entry in prepared.entries
                            if entry.context.position_index in good
                        )
                        # A per-target conflict must never apply its stale geometry
                        # through the full source snapshot of another target.
                        if len(entries) != len(prepared.entries):
                            prepared = self.keep_selected_geometry(prepared, entries)
                        latest = session.scalar(
                            select(ImageSourceGeometryRevisionModel.id)
                            .where(ImageSourceGeometryRevisionModel.source_image_id == source_id)
                            .order_by(ImageSourceGeometryRevisionModel.revision.desc())
                            .limit(1)
                        )
                        if not entries or latest != entries[0].context.source_geometry_revision_id:
                            for position in good:
                                outcomes[position] = "conflict"
                        else:
                            _, blockers = writer.save_automatic_reinference_source(
                                prepared=prepared,
                                idempotency_key=operation_id,
                                created_at=context.now(),
                                proposal=checkpoint_payload["proposal"],
                                binding=checkpoint_payload["binding"],
                                model_snapshot=operation.document["modelSnapshot"],
                                acceptance_policy=operation.document["acceptancePolicy"],
                                **(
                                    {"effect_collector": effect_collector}
                                    if operation.document.get("statsPolicy") == STATS_POLICY
                                    else {}
                                ),
                            )
                            acceptance = {
                                "status": "needs_review" if blockers else "accepted",
                                "blockers": list(blockers),
                            }
                            for position in good:
                                outcomes[position] = "automatic_written"
                d = copy.deepcopy(operation.document)
                source_record = session.get(Source, (job.game_id, operation_id, ordinal))
                assert source_record is not None
                source_record.document = {**source_record.document, "acceptance": acceptance}
                status_counts = d.setdefault("sourceStatusCounts", {})
                status_counts[acceptance["status"]] = status_counts.get(acceptance["status"], 0) + 1
                for target in targets:
                    target.outcome = outcomes[target.position_index]
                    target.result = {
                        "schemaVersion": "grid-reinference-target-result-v1",
                        "operationId": str(operation_id),
                        "targetResultId": str(target.target_result_id),
                        "sourceResultId": str(uuid5(operation_id, f"source:{source_id}")),
                        "sourceImageId": str(source_id),
                        "positionIndex": target.position_index,
                        "outcome": target.outcome,
                        "sourceAcceptance": acceptance,
                        "frozenFenceSha256": target.fingerprint_sha256,
                        "checkpoint": checkpoint,
                        "geometry": checkpoint_payload.get("byPosition", {}).get(
                            target.position_index
                        ),
                        "actor": "system:grid-reinference",
                        "at": now_text(),
                    }
                    if d.get("statsPolicy") == STATS_POLICY:
                        target.result["protectionReason"] = (
                            target_protection(target.snapshot)
                            if target.outcome == "protected"
                            else None
                        )
                        target_id = (target.snapshot["pending"] or target.snapshot["review"])["id"]
                        effect = effect_collector.get(UUID(target_id))
                        if target.outcome == "automatic_written" and effect is None:
                            raise JobHandlerError(
                                "GRID_REINFERENCE_STATS_MISSING",
                                "The automatic writer returned no effect receipt.",
                            )
                        if effect is None:
                            effect = empty_effect()
                            effect["recordedTargetCount"] = 1
                        target.result["effectStats"] = effect
                        add_counts(d["effectStats"], effect, EFFECT_FIELDS)
                    d["outcomes"][target.outcome] = d["outcomes"].get(target.outcome, 0) + 1
                d.update(state="running", processedSources=ordinal)
                refresh_effect_gap(d)
                operation.document = d
                self.progress(session, job, d, "infer")

    def recognize(
        self,
        source_document: dict[str, Any],
        frozen: list[dict[str, Any]],
        pin: dict[str, Any],
        operation_id: UUID,
        ordinal: int,
        runner: Any,
        context: JobExecutionContext,
    ) -> dict[str, Any]:
        source = source_document["source"]
        if not frozen:
            return self.save_checkpoint(
                operation_id, ordinal, {"outcome": "unchanged", "byPosition": {}}
            )
        path = (self.root / "data" / source["relative_path"]).resolve()
        if not path.is_relative_to(self.root / "data"):
            return self.save_checkpoint(
                operation_id, ordinal, {"outcome": "conflict", "byPosition": {}}
            )
        loader = CanonicalSourceLoader()
        try:
            frame = loader.load(path, expected_source_checksum_sha256=source["checksum_sha256"])
        except CanonicalSourceLoadError as error:
            return self.save_checkpoint(
                operation_id,
                ordinal,
                {
                    "outcome": "source_missing"
                    if error.code == "IMAGE_CANONICAL_SOURCE_NOT_FOUND"
                    else "conflict",
                    "reason": error.code,
                    "byPosition": {},
                },
            )
        finally:
            loader.clear()
        actual = frame.source
        if (
            actual.normalized_pixel_checksum_sha256 != source["normalized_pixel_checksum_sha256"]
            or actual.width != source["oriented_width"]
            or actual.height != source["oriented_height"]
            or actual.exif_orientation != source["exif_orientation"]
            or actual.normalization_adapter_version != source["normalization_adapter_version"]
            or frame.raw_width != source["raw_width"]
            or frame.raw_height != source["raw_height"]
        ):
            return self.save_checkpoint(
                operation_id,
                ordinal,
                {"outcome": "conflict", "reason": "NORMALIZATION_FENCE", "byPosition": {}},
            )
        rgb = frame.rgb
        snapshot = NeuralGridSnapshot.from_payload(pin)
        raw_result = self.raw_inference(source, rgb, pin, snapshot, operation_id, runner, context)
        if raw_result.get("outcome"):
            return self.save_checkpoint(operation_id, ordinal, {**raw_result, "byPosition": {}})
        geometry = source_document["geometryContext"]
        if geometry is None:
            return self.save_checkpoint(
                operation_id, ordinal, {"outcome": "conflict", "byPosition": {}}
            )
        sequence = AttestedSequenceRange(
            start=geometry["sequence_range_start"], end=geometry["sequence_range_end"]
        )
        height, width = rgb.shape[:2]
        detections = raw_result["detections"]
        proposal: dict[str, Any] = cast(
            dict[str, Any],
            build_neural_source_proposal(
                game_id=str(snapshot.game_id),
                source_selection_id=source["import_job_id"],
                source_checksum_sha256=source["checksum_sha256"],
                source_width=width,
                source_height=height,
                original_range=sequence,
                snapshot=snapshot,
                detections=detections,
            ),
        )
        binding = cast(dict[str, Any] | None, associate_expected_slots(proposal))
        by_position = {}
        if binding is not None:
            by_id = {item["detectionId"]: item for item in detections}
            for assignment in binding["assignments"]:
                detection = by_id[assignment["detectionId"]]
                if all(item == "full" for item in detection["cellVisibility"]):
                    by_position[str(assignment["positionIndex"])] = detection
        return self.save_checkpoint(
            operation_id,
            ordinal,
            {
                "proposal": proposal,
                "binding": binding,
                "byPosition": by_position,
                "sourceGeometryRevisionId": geometry["id"],
            },
        )

    def raw_inference(
        self,
        source: dict[str, Any],
        rgb: Any,
        pin: dict[str, Any],
        snapshot: NeuralGridSnapshot,
        operation_id: UUID,
        runner: Any,
        context: JobExecutionContext,
    ) -> dict[str, Any]:
        """Deduplicate pixels/model only; each occurrence retains its own binding."""
        identity = digest(
            {
                "source": {
                    key: source.get(key)
                    for key in (
                        "checksum_sha256",
                        "normalized_pixel_checksum_sha256",
                        "exif_orientation",
                        "oriented_width",
                        "oriented_height",
                        "normalization_adapter_version",
                    )
                },
                "model": pin,
                "runtime": "grid-reinference-runtime-v1",
            }
        )
        cache = self.root / "grid-reinference" / str(operation_id) / "raw" / f"{identity}.json"
        if cache.exists():
            envelope = json.loads(cache.read_text(encoding="utf-8"))
            if envelope.get("inputSha256") != identity or digest(
                envelope["result"]
            ) != envelope.get("sha256"):
                raise JobHandlerError(
                    "GRID_REINFERENCE_CHECKPOINT_INVALID", "The raw inference checkpoint differs."
                )
            return cast(dict[str, Any], envelope["result"])
        bundle = ManagedGridEngineModelStore(self.root).require(snapshot.version)
        bundle_sha = next(
            item.sha256 for item in snapshot.version.files if item.name == "bundle.json"
        )
        try:
            found = runner.run(
                bundle,
                bundle_sha,
                rgb,
                heartbeat=lambda: self.cancellation_boundary(context),
                max_seconds=SOURCE_DEADLINE_SECONDS,
            )
        except GeometryRuntimeError as error:
            if error.code not in {
                "NEURAL_GRID_SOURCE_TIME_LIMIT",
                "NEURAL_GRID_STARTUP_TIME_LIMIT",
            }:
                raise
            result = {"outcome": "inference_timeout", "reason": error.code, "detections": []}
            return self.publish_raw(cache, identity, result)
        height, width = rgb.shape[:2]
        detections = []
        for index, found_board in enumerate(found):
            nodes = (
                None
                if found_board.nodes is None
                else [
                    {"x": float(x), "y": float(y)}
                    for x, y in np.asarray(found_board.nodes).reshape(-1, 2)
                ]
            )
            quads, visibility = [], ["unknown"] * 15
            if nodes is not None:
                try:
                    exact = lattice_cell_quads(nodes, width=width, height=height)
                    quads, visibility = (
                        [quad.to_dict() for quad in exact],
                        lattice_visibility(exact, width=width, height=height),
                    )
                except ValueError:
                    nodes = None
            detections.append(
                {
                    "detectionId": f"detection-{index}",
                    "score": float(found_board.score),
                    "latticeNodes": nodes,
                    "cellQuads": quads,
                    "cellVisibility": visibility,
                    "structurallyValid": nodes is not None,
                    "reasonCodes": list(
                        dict.fromkeys(["NEURAL_GRID_GATE_UNCALIBRATED", *found_board.reasons])
                    ),
                }
            )
        return self.publish_raw(cache, identity, {"detections": detections})

    @staticmethod
    def publish_raw(path: Path, identity: str, result: dict[str, Any]) -> dict[str, Any]:
        envelope = {"inputSha256": identity, "result": result, "sha256": digest(result)}
        raw = canonical(envelope).encode()
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.parent / f"{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                if os.name == "nt":
                    os.rename(temporary, path)  # Windows rename never replaces a destination.
                else:
                    os.link(temporary, path)  # Atomic create-only publication.
            except FileExistsError:
                if path.read_bytes() != raw:
                    raise JobHandlerError(
                        "GRID_REINFERENCE_CHECKPOINT_CONFLICT",
                        "A raw result already has different content.",
                    ) from None
        finally:
            temporary.unlink(missing_ok=True)
        return result

    def save_checkpoint(
        self, operation_id: UUID, ordinal: int, payload: dict[str, Any]
    ) -> dict[str, Any]:
        raw = canonical(payload).encode()
        sha = hashlib.sha256(raw).hexdigest()
        relative = f"grid-reinference/{operation_id}/sources/{ordinal}-{sha}.json"
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            temporary = path.parent / f"{uuid4().hex}.tmp"
            with temporary.open("xb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != sha:
            raise JobHandlerError(
                "GRID_REINFERENCE_CHECKPOINT_INVALID", "The source checkpoint differs."
            )
        return {"path": relative, "sha256": sha}

    def load_checkpoint(self, checkpoint: dict[str, Any]) -> dict[str, Any]:
        path = (self.root / checkpoint["path"]).resolve()
        if not path.is_relative_to(self.root):
            raise JobHandlerError(
                "GRID_REINFERENCE_CHECKPOINT_INVALID", "Unsafe source checkpoint path."
            )
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != checkpoint["sha256"]:
            raise JobHandlerError(
                "GRID_REINFERENCE_CHECKPOINT_INVALID", "The source checkpoint checksum differs."
            )
        result: dict[str, Any] = json.loads(raw)
        result["byPosition"] = {int(key): value for key, value in result["byPosition"].items()}
        return result

    @staticmethod
    def unchanged(target: dict[str, Any], detection: dict[str, Any]) -> bool:
        board = target["board"]
        return (
            board is not None
            and board["board_geometry"].get("latticeNodes") == detection["latticeNodes"]
        )

    def render(self, job: Job, frozen: list[dict[str, Any]], checkpoint: dict[str, Any]) -> Any:
        assert job.game_id is not None
        if checkpoint.get("outcome") or not checkpoint["byPosition"]:
            return None
        with self.sessions() as session, session.begin():
            repository = SqlAlchemyGridReinferenceRepository(session, self.root)
            repository.bind(job.game_id, write=False)
            writer = SqlAlchemyVirtualGridGeometryRepository(session)
            service = VirtualGridGeometryService(writer, self.root)
            commands = []
            for target in frozen:
                position = target["positionIndex"]
                if (
                    target["kind"] == "grid_issue"
                    or target_protection(target)
                    or position not in checkpoint["byPosition"]
                    or self.unchanged(target, checkpoint["byPosition"][position])
                ):
                    continue
                nodes = checkpoint["byPosition"][position]["latticeNodes"]
                board, review, pending, source = (
                    target["board"],
                    target["review"],
                    target["pending"],
                    target["source"],
                )
                commands.append(
                    VirtualGridGeometrySourceCommand(
                        review_item_id=None if review is None else UUID(review["id"]),
                        pending_geometry_id=None if pending is None else UUID(pending["id"]),
                        expected_geometry_revision=board["geometry_revision"]
                        if board
                        else pending["expected_geometry_revision"],
                        expected_resolution_revision=review["resolution_revision"]
                        if review
                        else pending["expected_review_resolution_revision"],
                        expected_source_checksum_sha256=source["checksum_sha256"],
                        expected_source_width=source["oriented_width"],
                        expected_source_height=source["oriented_height"],
                        expected_grid_rows=3,
                        expected_grid_columns=5,
                        corners=tuple(
                            ImageReviewGeometryPoint(x=nodes[index]["x"], y=nodes[index]["y"])
                            for index in (0, 5, 23, 18)
                        ),
                        lattice_nodes=SourceLatticeNodes(
                            tuple(SourcePoint(point["x"], point["y"]) for point in nodes)
                        ),
                        expected_proposal_checksum_sha256=(
                            board["board_geometry"]
                            if board
                            else target["geometryContext"]["board_geometries"][position]
                        ).get("neuralProposalChecksumSha256"),
                    )
                )
            if not commands:
                return None
            import_job = UUID(frozen[0]["source"]["import_job_id"])
            from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError

            try:
                prepared, _ = service._prepare_source(
                    game_id=job.game_id,
                    import_job_id=import_job,
                    commands=commands,
                    actor="system:grid-reinference",
                    require_complete_source=False,
                    predict=False,
                    automatic=True,
                )
            except ImageGridReviewError as error:
                if error.code in {
                    "IMAGE_GRID_REVIEW_REVISION_CONFLICT",
                    "IMAGE_GRID_REVIEW_SOURCE_SLOT_CONFLICT",
                    "IMAGE_GRID_REVIEW_SOURCE_CONTEXT_CONFLICT",
                }:
                    return None
                raise
            return self.neural_provenance(prepared, checkpoint)

    @staticmethod
    def neural_provenance(prepared: Any, checkpoint: dict[str, Any]) -> Any:
        geometries = [dict(value) for value in prepared.board_geometries]
        for entry in prepared.entries:
            position = entry.context.position_index
            detection = checkpoint["byPosition"][position]
            geometries[position].update(
                neuralExecutionPolicy="neural-auto-crop-v1",
                neuralProposalChecksumSha256=checkpoint["proposal"]["proposalChecksumSha256"],
                neuralProposalBinding=checkpoint["binding"],
                detectionId=detection["detectionId"],
                geometrySource="auto",
            )
        sha = digest(
            {
                "policy": CONTRACT,
                "previous": str(prepared.entries[0].context.source_geometry_revision_id),
                "boards": geometries,
            }
        )
        entries = []
        for entry in prepared.entries:
            board_geometry = {
                **entry.board_geometry,
                **geometries[entry.context.position_index],
                "source": "neural_grid_v1",
                "geometryVersion": CONTRACT,
                "quad": geometries[entry.context.position_index]["finalQuad"],
            }
            manifest = {**entry.virtual_render_spec, "geometryChecksumSha256": sha}
            entries.append(
                replace(
                    entry,
                    board_geometries=tuple(geometries),
                    source_geometry_checksum_sha256=sha,
                    board_geometry=board_geometry,
                    virtual_render_spec=manifest,
                    virtual_render_spec_checksum_sha256=digest(manifest),
                )
            )
        return replace(
            prepared,
            entries=tuple(entries),
            board_geometries=tuple(geometries),
            source_geometry_checksum_sha256=sha,
        )

    @staticmethod
    def keep_selected_geometry(prepared: Any, entries: tuple[Any, ...]) -> Any:
        geometries = [dict(value) for value in prepared.entries[0].context.board_geometries]
        for entry in entries:
            geometries[entry.context.position_index] = dict(
                prepared.board_geometries[entry.context.position_index]
            )
        sha = digest(
            {
                "policy": CONTRACT,
                "previous": str(prepared.entries[0].context.source_geometry_revision_id),
                "boards": geometries,
            }
        )
        replaced = []
        for entry in entries:
            manifest = {**entry.virtual_render_spec, "geometryChecksumSha256": sha}
            replaced.append(
                replace(
                    entry,
                    board_geometries=tuple(geometries),
                    source_geometry_checksum_sha256=sha,
                    virtual_render_spec=manifest,
                    virtual_render_spec_checksum_sha256=digest(manifest),
                )
            )
        return replace(
            prepared,
            entries=tuple(replaced),
            board_geometries=tuple(geometries),
            source_geometry_checksum_sha256=sha,
        )

    @staticmethod
    def progress(session: Session, job: Job, document: dict[str, Any], phase: str) -> None:
        record = session.get(JobModel, job.id)
        assert record is not None and job.lease_token is not None
        current = (
            document["prepareCursor"]
            if phase == "prepare"
            else document["sourceCount"] + document["processedSources"]
        )
        updated = update_job_progress(
            job_from_record(record),
            lease_token=job.lease_token,
            stage=f"grid_reinference:{phase}",
            current=current,
            total=2 * document["sourceCount"],
            success_count=0,
            failure_count=0,
            review_count=0,
        )
        apply_job_to_record(record, updated)
