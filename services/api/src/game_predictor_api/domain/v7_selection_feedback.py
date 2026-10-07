"""Immutable representative preferences; never individual OCR/symbol labels."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from copy import deepcopy
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import cast
from uuid import UUID

from game_predictor_worker.semi_automatic_selection.local_source_manifest import LocalSourceManifest

from .v7_selection_delivery import (
    V7DeliveryConflict,
    V7OutputDecision,
    V7OutputOperation,
    payload_fingerprint,
)

FEEDBACK_VERSION = "v7-selection-feedback-context-v1"
SourceValidator = Callable[[str, dict[str, object]], str | None]


def capture_feedback_snapshot(
    *,
    manifest: LocalSourceManifest,
    expected_index: int,
    expected_range: tuple[int, int],
    review: dict[str, object],
    selected_diagnostics: dict[str, object],
    decision: V7OutputDecision,
    configuration: dict[str, object],
) -> dict[str, object]:
    def source_identity(index: int) -> dict[str, object]:
        if type(index) is not int or not 0 <= index < len(manifest.sources):
            raise V7DeliveryConflict("V7_FEEDBACK_CONTEXT_INVALID", "Invalid proposal source.")
        source = manifest.sources[index]
        return {
            "sourceIndex": index,
            "relativePath": source.relative_path,
            "sizeBytes": source.size_bytes,
            "checksumSha256": source.checksum_sha256,
        }

    candidate = review.get("candidate")
    proposal_source = None
    if isinstance(candidate, dict):
        proposal_source = source_identity(candidate["sourceIndex"])
    selected = source_identity(decision.source_index)
    if (
        selected_diagnostics.get("sourceIndex") != decision.source_index
        or selected_diagnostics.get("sourceChecksumSha256") != selected["checksumSha256"]
    ):
        raise V7DeliveryConflict("V7_FEEDBACK_CONTEXT_INVALID", "Selected diagnostics changed.")
    proofs = cast(list[dict[str, object]], review.get("provenSources", []))
    return deepcopy(
        {
            "version": FEEDBACK_VERSION,
            "expectedIndex": expected_index,
            "expectedRange": {"start": expected_range[0], "end": expected_range[1]},
            "sourceRoot": str(manifest.source_root),
            "proposal": candidate,
            "proposalSource": proposal_source,
            "selectedSource": selected,
            "selectedDiagnostics": selected_diagnostics,
            "selectedProof": next(
                (proof for proof in proofs if proof.get("sourceIndex") == decision.source_index),
                None,
            ),
            "configuration": configuration,
        }
    )


@dataclass(frozen=True)
class V7FeedbackOwner:
    operation_id: UUID | None
    source_index: int | None
    checksum_sha256: str | None
    generation: int | None


def _valid_receipt(operation: V7OutputOperation) -> bool:
    decision = operation.decision
    receipt = operation.receipt
    expected = {
        "operationId": str(operation.operation_id),
        "state": "committed",
        "sourceIndex": decision.source_index,
        "sourceChecksumSha256": decision.expected_source_checksum_sha256,
        "confirmedRange": {"start": decision.range_start, "end": decision.range_end},
        "targetName": f"seq_{decision.range_start}-{decision.range_end}.jpg",
        "ownerOperationId": str(operation.operation_id),
        "decisionGeneration": operation.decision_generation,
        "outputChecksumSha256": decision.expected_source_checksum_sha256,
        "errorCode": None,
    }
    # Python dict equality equates False with 0 and 1.0 with 1; canonical JSON must not.
    return receipt is not None and payload_fingerprint(receipt) == payload_fingerprint(expected)


def _snapshot_error(operation: V7OutputOperation, snapshot: dict[str, object]) -> str | None:
    decision, context = operation.decision, operation.context_payload
    selected = snapshot.get("selectedSource")
    diagnostics = snapshot.get("selectedDiagnostics")
    configuration = snapshot.get("configuration")
    if (
        snapshot.get("version") != FEEDBACK_VERSION
        or payload_fingerprint(snapshot) != context.get("feedbackFingerprint")
        or not isinstance(selected, dict)
        or not isinstance(diagnostics, dict)
        or not isinstance(configuration, dict)
        or payload_fingerprint(configuration.get("pilot"))
        != payload_fingerprint(context.get("pilotSnapshot"))
        or type(snapshot.get("expectedIndex")) is not int
        or cast(int, snapshot["expectedIndex"]) < 0
        or type(selected.get("sourceIndex")) is not int
        or type(diagnostics.get("sourceIndex")) is not int
        or selected.get("sourceIndex") != decision.source_index
        or selected.get("checksumSha256") != decision.expected_source_checksum_sha256
        or selected.get("relativePath") != context.get("sourceRelativePath")
        or selected.get("sizeBytes") != context.get("sourceSizeBytes")
        or diagnostics.get("sourceChecksumSha256") != decision.expected_source_checksum_sha256
        or diagnostics.get("sourceIndex") != decision.source_index
        or diagnostics.get("sourceErrorCode") is not None
        or not isinstance(snapshot.get("sourceRoot"), str)
        or not isinstance(snapshot.get("expectedRange"), dict)
    ):
        return "snapshot_invalid"
    expected = cast(dict[str, object], snapshot["expectedRange"])
    if (
        type(expected.get("start")) is not int
        or type(expected.get("end")) is not int
        or not cast(int, expected["start"])
        <= decision.range_start
        <= decision.range_end
        <= cast(int, expected["end"])
    ):
        return "snapshot_invalid"
    proposal, source = snapshot.get("proposal"), snapshot.get("proposalSource")
    if proposal is None:
        return None if source is None else "snapshot_invalid"
    if (
        not isinstance(proposal, dict)
        or not isinstance(source, dict)
        or type(source.get("sourceIndex")) is not int
        or source.get("sourceIndex") != proposal.get("sourceIndex")
    ):
        return "snapshot_invalid"
    return None


def build_feedback_manifest(
    operations: Iterable[V7OutputOperation],
    owners: dict[tuple[UUID, UUID], V7FeedbackOwner],
    *,
    validate_source: SourceValidator,
) -> dict[str, object]:
    """Deterministic projection of a consistent journal snapshot; no implicit fitting."""
    unique: dict[UUID, V7OutputOperation] = {}
    for operation in operations:
        previous = unique.get(operation.operation_id)
        if previous is not None and previous != operation:
            raise ValueError("Conflicting operation UUID in feedback snapshot.")
        unique[operation.operation_id] = operation
    ordered = sorted(
        unique.values(),
        key=lambda op: (
            str(op.run_id),
            op.decision.range_start,
            op.decision_generation,
            str(op.operation_id),
        ),
    )
    history: list[dict[str, object]] = []
    examples: list[dict[str, object]] = []
    exclusions: Counter[str] = Counter()
    outcomes: Counter[str] = Counter()
    source_cache: dict[tuple[str, str], str | None] = {}
    for operation in ordered:
        decision, context = operation.decision, operation.context_payload
        snapshot = context.get("feedbackSnapshot")
        reason = None
        if operation.state != "committed":
            reason = "operation_" + operation.state
        elif not _valid_receipt(operation):
            reason = "receipt_invalid"
        elif not isinstance(snapshot, dict):
            reason = "legacy_context_missing"
        else:
            reason = _snapshot_error(operation, snapshot)
            if reason is None:
                root = cast(str, snapshot["sourceRoot"])
                for source in (snapshot["selectedSource"], snapshot.get("proposalSource")):
                    if source is None:
                        continue
                    source = cast(dict[str, object], source)
                    # Cache equal identities, not equal indices from different folders.
                    key = (root, payload_fingerprint(source))
                    if key not in source_cache:
                        source_cache[key] = validate_source(root, source)
                    if source_cache[key] is not None:
                        reason = source_cache[key]
                        break
        if reason is None and decision.kind == "manual_replace":
            previous = (
                unique.get(decision.expected_owner_operation_id)
                if decision.expected_owner_operation_id
                else None
            )
            if (
                previous is None
                or previous.state != "committed"
                or not _valid_receipt(previous)
                or (previous.run_id, previous.range_id) != (operation.run_id, operation.range_id)
                or previous.decision_generation + 1 != operation.decision_generation
                or previous.decision.expected_source_checksum_sha256
                != decision.expected_target_checksum_sha256
                or (previous.decision.range_start, previous.decision.range_end)
                != (decision.range_start, decision.range_end)
            ):
                reason = "replacement_chain_invalid"
        owner = owners.get((operation.run_id, operation.range_id))
        current = owner is not None and owner.operation_id == operation.operation_id
        if (
            current
            and reason is None
            and (
                owner is None
                or owner.source_index != decision.source_index
                or owner.checksum_sha256 != decision.expected_source_checksum_sha256
                or owner.generation != operation.decision_generation
            )
        ):
            reason = "owner_invalid"
        outcome = "unavailable"
        if reason is None and isinstance(snapshot, dict):
            proposal = snapshot.get("proposalSource")
            outcome = (
                "no_proposal"
                if proposal is None
                else "accepted_proposal"
                if cast(dict[str, object], proposal)["sourceIndex"] == decision.source_index
                else "different_selection"
            )
        record: dict[str, object] = {
            "operationId": str(operation.operation_id),
            "runId": str(operation.run_id),
            "rangeId": str(operation.range_id),
            "requestFingerprint": operation.request_fingerprint,
            "decision": deepcopy(operation.request_payload),
            "context": deepcopy(context),
            "receipt": deepcopy(operation.receipt),
            "state": operation.state,
            "decisionGeneration": operation.decision_generation,
            "createdAt": operation.created_at.isoformat(),
            "committedAt": operation.updated_at.isoformat()
            if operation.state == "committed"
            else None,
            "currentOwner": current,
            "outcome": outcome,
            "reasonTarget": "previous_output" if decision.kind == "manual_replace" else "proposal",
            "rangeEvidence": (
                "source_proof_and_human"
                if isinstance(snapshot, dict) and snapshot.get("selectedProof") is not None
                else "human_only"
            ),
            "exclusionReason": reason,
        }
        history.append(record)
        if reason is not None:
            exclusions[reason] += 1
        elif current:
            examples.append(record)
            outcomes[outcome] += 1
    comparable = outcomes["accepted_proposal"] + outcomes["different_selection"]
    return {
        "version": "v7-selection-feedback-manifest-v1",
        "labelScope": "human_representative_preference",
        "individualSymbolLabels": False,
        "splitPolicy": "unassigned_capture_groups_required",
        "history": history,
        "examples": examples,
        "report": {
            "status": "available" if examples else "not_evaluable",
            "trainingStatus": "not_trained",
            "trainingReadiness": "capture_groups_required" if examples else "no_examples",
            "agreementScope": "source_identity_only",
            "operationCount": len(history),
            "exampleCount": len(examples),
            "excludedOperations": dict(sorted(exclusions.items())),
            "outcomes": dict(sorted(outcomes.items())),
            "agreementRate": None
            if comparable == 0
            else outcomes["accepted_proposal"] / comparable,
            "humanOnlyRangeCount": sum(item["rangeEvidence"] == "human_only" for item in examples),
            "manualWithoutOcrCount": sum(
                cast(dict[str, object], item["decision"]).get("kind") == "manual_no_ocr"
                for item in examples
            ),
            "replacementCount": sum(
                cast(dict[str, object], item["decision"]).get("kind") == "manual_replace"
                for item in history
                if item["exclusionReason"] is None
            ),
        },
    }


def relative_source_path(source: dict[str, object]) -> PurePosixPath:
    raw = source.get("relativePath")
    if not isinstance(raw, str) or not raw or "\\" in raw or ":" in raw:
        raise ValueError("Invalid feedback source path.")
    relative = PurePosixPath(raw)
    if relative.is_absolute() or ".." in relative.parts or relative.as_posix() != raw:
        raise ValueError("Invalid feedback source path.")
    return relative
