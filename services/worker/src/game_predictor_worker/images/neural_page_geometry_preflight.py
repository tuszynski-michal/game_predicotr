"""Durable Mumie neural staging; unverified proposals remain correction drafts."""

from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast
from uuid import UUID

import numpy as np
from game_predictor_api.domain.image_geometry_v2 import AttestedSequenceRange, canonical_json_bytes
from game_predictor_api.domain.jobs import Job, JobType
from game_predictor_api.domain.neural_grid_proposal import (
    NEURAL_GRID_MANIFEST_SCHEMA_VERSION,
    NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
    NEURAL_GRID_REVIEW_REASON,
    NeuralGridProposalError,
    NeuralGridSnapshot,
    associate_expected_slots,
    build_neural_source_proposal,
    lattice_cell_quads,
    lattice_visibility,
    validate_neural_source_binding,
    validate_neural_source_proposal,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_worker.geometry_core.bounded_runtime import GeometryRuntimeError
from game_predictor_worker.geometry_core.inference import BoardDetection
from game_predictor_worker.geometry_core.preprocessing import ByteImage
from game_predictor_worker.geometry_core.proposal_runtime import CPUGridProposalRunner
from game_predictor_worker.jobs.runtime import JobExecutionContext, JobHandlerError

from .page_geometry_incremental import PageGeometryCheckpointStore, source_inventory_checksum
from .source_ingestion import ManagedOriginal, ManagedOriginalStore


class ProposalRunner(Protocol):
    def run(
        self,
        bundle: Path,
        bundle_sha256: str,
        rgb: ByteImage,
        *,
        heartbeat: Callable[[], None],
        max_seconds: float,
    ) -> list[BoardDetection]: ...
    def close(self) -> None: ...


def _input(job: Job) -> tuple[dict[str, object], NeuralGridSnapshot]:
    raw = job.input_payload
    required = {
        "schema_version",
        "validation_kind",
        "source_selection_id",
        "source_directory",
        "source_manifest_sha256",
        "page_registration_profile",
        "page_geometry_overrides",
        "canonical_sequence_numbers",
        "preflight_policy_version",
        "neural_grid_proposal",
    }
    optional = {
        "source_display_name",
        "source_exclusions",
        "managed_source_job_id",
        "managed_source_manifest_checksum_sha256",
        "base_page_geometry_manifest",
        "replacement_parent_upload_id",
        "replacement_parent_manifest_sha256",
    }
    if (
        job.job_type is not JobType.VALIDATE
        or job.game_id is None
        or not required.issubset(raw)
        or not set(raw).issubset(required | optional)
        or raw["schema_version"] != 2
        or raw["validation_kind"] != "page_geometry_preflight"
        or raw["preflight_policy_version"] != NEURAL_GRID_PREFLIGHT_POLICY_VERSION
    ):
        raise JobHandlerError(
            "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD", "The neural page-geometry input is invalid."
        )
    try:
        snapshot = NeuralGridSnapshot.from_payload(raw["neural_grid_proposal"])
        UUID(str(raw["source_selection_id"]))
        if (
            not isinstance(raw["source_directory"], str)
            or not isinstance(raw["page_geometry_overrides"], Mapping)
            or not isinstance(raw["page_registration_profile"], Mapping)
            or not isinstance(raw["source_manifest_sha256"], str)
            or len(raw["source_manifest_sha256"]) != 64
            or any(value not in "0123456789abcdef" for value in raw["source_manifest_sha256"])
        ):
            raise ValueError("Invalid source owner.")
        canonical = raw["canonical_sequence_numbers"]
        if not isinstance(canonical, list) or any(
            isinstance(value, bool) or not isinstance(value, int) or value < 1
            for value in canonical
        ):
            raise ValueError("Invalid canonical snapshot.")
    except (ValueError, TypeError) as error:
        raise JobHandlerError(
            getattr(error, "code", "INVALID_PAGE_GEOMETRY_PREFLIGHT_PAYLOAD"), str(error)
        ) from error
    return {
        "sourceSelectionId": raw["source_selection_id"],
        "sourceDirectory": raw["source_directory"],
        "sourceManifestChecksumSha256": raw["source_manifest_sha256"],
        "pageRegistrationProfile": raw["page_registration_profile"],
        "pageGeometryOverrides": raw["page_geometry_overrides"],
        "canonicalSequenceNumbers": set(canonical),
        "preflightPolicyVersion": NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
    }, snapshot


def validate_neural_page_manifest(
    value: object,
    *,
    game_id: str,
    source_selection_id: str,
    source_manifest_sha256: str,
    snapshot: NeuralGridSnapshot,
) -> Mapping[str, object]:
    if (
        not isinstance(value, Mapping)
        or value.get("schemaVersion") != NEURAL_GRID_MANIFEST_SCHEMA_VERSION
        or value.get("version") != NEURAL_GRID_PREFLIGHT_POLICY_VERSION
        or value.get("gameId") != game_id
        or value.get("sourceSelectionId") != source_selection_id
        or value.get("sourceManifestChecksumSha256") != source_manifest_sha256
        or value.get("neuralGridProposal") != snapshot.to_payload()
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_DRIFT",
            "The neural manifest has incompatible source or model pins.",
        )
    entries = value.get("entries")
    for field in (
        "sourceCount",
        "registeredSourceCount",
        "reviewRequiredSourceCount",
        "skippedHumanResolvedSourceCount",
    ):
        count = value.get(field)
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
                "Neural manifest counts require nonnegative integers.",
            )
    if not isinstance(entries, Mapping) or value.get("sourceCount") != len(entries):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID", "The neural manifest inventory is invalid."
        )
    reviews = skipped = 0
    for checksum, entry in entries.items():
        if not isinstance(entry, Mapping) or not isinstance(entry.get("sourceRelativePath"), str):
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID", "A neural source entry is invalid."
            )
        if entry.get("status") == "skipped_human_resolved":
            skipped += 1
            continue
        try:
            proposal = validate_neural_source_proposal(entry.get("neuralProposal"))
            if (
                proposal["sourceChecksumSha256"] != checksum
                or proposal["gameId"] != game_id
                or proposal["sourceSelectionId"] != source_selection_id
                or proposal["engineSnapshot"] != snapshot.to_payload()
                or proposal["sourceWidth"] != entry.get("imageWidth")
                or proposal["sourceHeight"] != entry.get("imageHeight")
            ):
                raise NeuralGridProposalError(
                    "NEURAL_GRID_PROPOSAL_DRIFT", "The neural source entry provenance differs."
                )
            binding = entry.get("neuralProposalBinding")
            if binding is None:
                if entry.get("status") != "slot_binding_required":
                    raise NeuralGridProposalError(
                        "NEURAL_GRID_PROPOSAL_INVALID", "An unbound source cannot seed boards."
                    )
            else:
                validate_neural_source_binding(binding, proposal)
                if entry.get("status") != "review_required":
                    raise NeuralGridProposalError(
                        "NEURAL_GRID_PROPOSAL_INVALID", "A neural binding never qualifies geometry."
                    )
        except NeuralGridProposalError as error:
            raise JobHandlerError(error.code, str(error)) from error
        reviews += 1
    if (
        value.get("reviewRequiredSourceCount") != reviews
        or value.get("skippedHumanResolvedSourceCount") != skipped
        or value.get("registeredSourceCount") != 0
    ):
        raise JobHandlerError(
            "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
            "Neural manifest counts differ from source states.",
        )
    return value


class NeuralPageGeometryPreflightHandler:
    def __init__(
        self,
        *,
        artifact_root: Path,
        runner: ProposalRunner | None = None,
        model_store: ManagedGridEngineModelStore | None = None,
    ) -> None:
        self._root = artifact_root.resolve()
        self._runner = runner
        self._models = model_store or ManagedGridEngineModelStore(self._root)

    def __call__(self, context: JobExecutionContext, job: Job) -> None:
        from .page_geometry_preflight import (
            PageGeometryPreflightHandler,
            _checkpoint,
            _verify_browser_source_manifest,
        )

        payload, snapshot = _input(job)
        # This read-only verification runs even on a completed-manifest replay.
        bundle = self._models.require(snapshot.version)
        bundle_sha = next(
            item.sha256 for item in snapshot.version.files if item.name == "bundle.json"
        )
        originals = ManagedOriginalStore(self._root)
        directory = Path(cast(str, payload["sourceDirectory"]))
        managed_reprepare = "managed_source_job_id" in job.input_payload
        if not managed_reprepare:
            _verify_browser_source_manifest(
                directory, expected_checksum=cast(str, payload["sourceManifestChecksumSha256"])
            )
        manifest = originals.load_or_create_manifest(
            replace(job, input_payload={**job.input_payload, "schema_version": 6})
            if managed_reprepare
            else job,
            source_directory=directory,
        )
        if managed_reprepare:
            for original in manifest.originals:
                originals.ensure_original(manifest, original)
            manifest = replace(
                manifest,
                source_directory=self._root,
                originals=tuple(
                    replace(item, source_storage_relative_path=item.managed_relative_path)
                    for item in manifest.originals
                ),
            )
        inventory = source_inventory_checksum(manifest.originals)
        if len({item.checksum_sha256 for item in manifest.originals}) != len(manifest.originals):
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_MANIFEST_INVALID",
                "Neural sources require unique immutable byte identities.",
            )
        checkpoint_store = PageGeometryCheckpointStore(
            self._root,
            job_id=str(job.id),
            input_fingerprint_sha256=job.input_key,
            source_inventory_checksum_sha256=inventory,
            shard_size=25,
        )
        checkpoint_payload = job.checkpoint_payload
        required = (
            isinstance(checkpoint_payload, Mapping)
            and "durable_checkpoint_relative_path" in checkpoint_payload
        )
        state = checkpoint_store.load(required=required)
        if state is None:
            state = checkpoint_store.initialize(
                {}, metadata={"phase": "source_registration", "sourceNextIndex": 0}
            )
        entries = dict(state.entries)
        if not set(entries).issubset({item.checksum_sha256 for item in manifest.originals}):
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_CHECKPOINT_INVALID",
                "The neural checkpoint contains a foreign source.",
            )
        previous = self._base_proposals(job, payload, snapshot)
        runner = self._runner or CPUGridProposalRunner(threads=1)
        try:
            for index, original in enumerate(manifest.originals):
                context.heartbeat()
                from .source_ingestion import _safe_source_path

                source_path = _safe_source_path(
                    manifest.source_directory,
                    original.source_storage_relative_path or original.source_relative_path,
                )
                source_bytes = source_path.read_bytes()
                if hashlib.sha256(source_bytes).hexdigest() != original.checksum_sha256:
                    raise JobHandlerError(
                        "IMAGE_PAGE_GEOMETRY_SOURCE_MANIFEST_CHANGED",
                        "A neural source changed after it was frozen.",
                    )
                if original.checksum_sha256 not in entries:
                    try:
                        with Image.open(io.BytesIO(source_bytes)) as image:
                            rgb = np.asarray(
                                ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8
                            )
                    except (OSError, UnidentifiedImageError) as error:
                        raise JobHandlerError(
                            "IMAGE_PAGE_GEOMETRY_SOURCE_UNAVAILABLE",
                            "A pinned neural JPEG cannot be decoded.",
                        ) from error
                    entry = self._evaluate(
                        original,
                        rgb,
                        job,
                        payload,
                        snapshot,
                        runner,
                        bundle,
                        bundle_sha,
                        context,
                        previous,
                    )
                    entries[original.checksum_sha256] = entry
                    state = checkpoint_store.append(
                        {original.checksum_sha256: entry},
                        metadata={"phase": "source_registration", "sourceNextIndex": index + 1},
                        all_entries=entries,
                    )
                    reviews = sum(
                        isinstance(item, Mapping)
                        and item.get("status") in {"review_required", "slot_binding_required"}
                        for item in entries.values()
                    )
                    _checkpoint(
                        context,
                        payload,
                        manifest_checksum=None,
                        manifest_relative_path=None,
                        processed=index + 1,
                        total=len(manifest.originals),
                        registered=0,
                        review_required=reviews,
                        complete=False,
                        phase="source_registration",
                        phase_current=index + 1,
                        phase_total=len(manifest.originals),
                        durable_checkpoint=state,
                    )
        finally:
            runner.close()
        for original in manifest.originals:
            path = _safe_source_path(
                manifest.source_directory,
                original.source_storage_relative_path or original.source_relative_path,
            )
            if hashlib.sha256(path.read_bytes()).hexdigest() != original.checksum_sha256:
                raise JobHandlerError(
                    "IMAGE_PAGE_GEOMETRY_SOURCE_MANIFEST_CHANGED",
                    "A neural source changed before manifest publication.",
                )
        self._models.require(snapshot.version)
        reviews = sum(
            isinstance(item, Mapping)
            and item.get("status") in {"review_required", "slot_binding_required"}
            for item in entries.values()
        )
        skipped = len(entries) - reviews
        value: dict[str, object] = {
            "schemaVersion": NEURAL_GRID_MANIFEST_SCHEMA_VERSION,
            "version": NEURAL_GRID_PREFLIGHT_POLICY_VERSION,
            "gameId": str(job.game_id),
            "sourceSelectionId": payload["sourceSelectionId"],
            "sourceManifestChecksumSha256": payload["sourceManifestChecksumSha256"],
            "neuralGridProposal": snapshot.to_payload(),
            "pageRegistrationProfile": payload["pageRegistrationProfile"],
            "entries": dict(sorted(entries.items())),
            "sourceCount": len(entries),
            "registeredSourceCount": 0,
            "reviewRequiredSourceCount": reviews,
            "skippedHumanResolvedSourceCount": skipped,
        }
        validate_neural_page_manifest(
            value,
            game_id=str(job.game_id),
            source_selection_id=cast(str, payload["sourceSelectionId"]),
            source_manifest_sha256=cast(str, payload["sourceManifestChecksumSha256"]),
            snapshot=snapshot,
        )
        content = (json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode()
        checksum = hashlib.sha256(content).hexdigest()
        relative = f"data/page-geometry-manifests/{checksum}.json"
        PageGeometryPreflightHandler._write_immutable(self._root / relative, content)
        state = checkpoint_store.append(
            {},
            metadata={
                "phase": "complete",
                "sourceNextIndex": len(entries),
                "geometryManifestChecksumSha256": checksum,
                "geometryManifestRelativePath": relative,
            },
            all_entries=entries,
        )
        _checkpoint(
            context,
            payload,
            manifest_checksum=checksum,
            manifest_relative_path=relative,
            processed=len(entries),
            total=len(entries),
            registered=0,
            review_required=reviews,
            complete=True,
            phase="complete",
            phase_current=1,
            phase_total=1,
            durable_checkpoint=state,
        )

    def _base_proposals(
        self, job: Job, payload: Mapping[str, object], snapshot: NeuralGridSnapshot
    ) -> Mapping[str, object]:
        descriptor = job.input_payload.get("base_page_geometry_manifest")
        if descriptor is None:
            return {}
        checksum = (
            descriptor.get("manifestChecksumSha256") if isinstance(descriptor, Mapping) else None
        )
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(value not in "0123456789abcdef" for value in checksum)
        ):
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_BASE_MANIFEST_INVALID",
                "The neural base manifest pin is invalid.",
            )
        path = self._root / "data" / "page-geometry-manifests" / f"{checksum}.json"
        content = path.read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise JobHandlerError(
                "IMAGE_PAGE_GEOMETRY_BASE_MANIFEST_INVALID", "The neural base manifest changed."
            )
        value = validate_neural_page_manifest(
            json.loads(content),
            game_id=str(job.game_id),
            source_selection_id=cast(str, payload["sourceSelectionId"]),
            source_manifest_sha256=cast(str, payload["sourceManifestChecksumSha256"]),
            snapshot=snapshot,
        )
        return cast(Mapping[str, object], value["entries"])

    def _evaluate(
        self,
        original: ManagedOriginal,
        rgb: ByteImage,
        job: Job,
        payload: Mapping[str, object],
        snapshot: NeuralGridSnapshot,
        runner: ProposalRunner,
        bundle: Path,
        bundle_sha: str,
        context: JobExecutionContext,
        previous: Mapping[str, object],
    ) -> dict[str, object]:
        start, end = original.sequence_range_start, original.sequence_range_end
        if start is None or end is None:
            raise JobHandlerError(
                "IMAGE_BOARD_CELL_SEQUENCE_UNATTESTED",
                "Neural staging requires the original filename range.",
            )
        sequence = AttestedSequenceRange(start=start, end=end)
        canonical = cast(set[int], payload["canonicalSequenceNumbers"])
        if all(number in canonical for number in range(start, end + 1)):
            return {
                "sourceRelativePath": original.source_relative_path,
                "status": "skipped_human_resolved",
            }
        width, height = int(rgb.shape[1]), int(rgb.shape[0])
        overrides = cast(Mapping[str, object], payload["pageGeometryOverrides"])
        override = overrides.get(original.checksum_sha256)
        prior = previous.get(original.checksum_sha256)
        old_proposal = override.get("neuralProposal") if isinstance(override, Mapping) else None
        source_reason = NEURAL_GRID_REVIEW_REASON
        if old_proposal is None and isinstance(prior, Mapping):
            old_proposal = prior.get("neuralProposal")
        if old_proposal is None:
            try:
                found = runner.run(
                    bundle, bundle_sha, rgb, heartbeat=context.heartbeat, max_seconds=30.0
                )
            except GeometryRuntimeError as error:
                if error.code != "NEURAL_GRID_SOURCE_TIME_LIMIT":
                    raise
                # The runtime has already reaped its child and transport. A
                # source-specific deadline remains durable review, never a
                # fabricated slot or an automatic retry during replay.
                runner.close()
                found = []
                source_reason = error.code
            detections = []
            for index, detection in enumerate(found):
                nodes = (
                    None
                    if detection.nodes is None
                    else [
                        {"x": float(x), "y": float(y)}
                        for x, y in np.asarray(detection.nodes).reshape(-1, 2)
                    ]
                )
                reasons = list(dict.fromkeys([NEURAL_GRID_REVIEW_REASON, *detection.reasons]))
                quads = []
                visibility = ["unknown"] * 15
                try:
                    exact = lattice_cell_quads(nodes, width=width, height=height)
                    quads = [quad.to_dict() for quad in exact]
                    visibility = lattice_visibility(exact, width=width, height=height)
                except NeuralGridProposalError:
                    nodes = None
                    reasons.append("NEURAL_GRID_STRUCTURE_INVALID")
                identity = hashlib.sha256(
                    canonical_json_bytes(
                        {"source": original.checksum_sha256, "index": index, "nodes": nodes}
                    )
                ).hexdigest()[:16]
                detections.append(
                    {
                        "detectionId": f"detection-{index}-{identity}",
                        "score": float(detection.score),
                        "latticeNodes": nodes,
                        "cellQuads": quads,
                        "cellVisibility": visibility,
                        "structurallyValid": nodes is not None,
                        "reasonCodes": reasons,
                    }
                )
            proposal = build_neural_source_proposal(
                game_id=str(job.game_id),
                source_selection_id=cast(str, payload["sourceSelectionId"]),
                source_checksum_sha256=original.checksum_sha256,
                source_width=width,
                source_height=height,
                original_range=sequence,
                snapshot=snapshot,
                detections=detections,
            )
        else:
            proposal = dict(validate_neural_source_proposal(old_proposal))
            if (
                isinstance(prior, Mapping)
                and prior.get("reasonCode") == "NEURAL_GRID_SOURCE_TIME_LIMIT"
            ):
                source_reason = "NEURAL_GRID_SOURCE_TIME_LIMIT"
            if (
                proposal["gameId"] != str(job.game_id)
                or proposal["sourceSelectionId"] != payload["sourceSelectionId"]
                or proposal["sourceChecksumSha256"] != original.checksum_sha256
                or proposal["sourceWidth"] != width
                or proposal["sourceHeight"] != height
                or proposal["originalRange"] != sequence.to_dict()
                or proposal["engineSnapshot"] != snapshot.to_payload()
            ):
                raise JobHandlerError(
                    "NEURAL_GRID_BINDING_STALE",
                    "The reused neural proposal belongs to different source or model pins.",
                )
        binding = override.get("neuralProposalBinding") if isinstance(override, Mapping) else None
        if binding is None:
            binding = associate_expected_slots(proposal)
        else:
            validate_neural_source_binding(binding, proposal)
        return {
            "sourceRelativePath": original.source_relative_path,
            "imageWidth": width,
            "imageHeight": height,
            "status": "review_required" if binding is not None else "slot_binding_required",
            "reasonCode": source_reason
            if source_reason == "NEURAL_GRID_SOURCE_TIME_LIMIT"
            else NEURAL_GRID_REVIEW_REASON
            if binding is not None
            else "NEURAL_GRID_SLOT_BINDING_REQUIRED",
            "neuralProposal": proposal,
            "neuralProposalBinding": binding,
        }
