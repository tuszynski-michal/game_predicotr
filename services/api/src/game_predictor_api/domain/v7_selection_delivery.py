"""Versioned metadata contracts for the existing V7 selection workflow."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal, cast
from uuid import UUID

from game_predictor_api.domain.jobs import JobConflictError

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
V7_PENDING_STATES = ("reserved", "recovery_required")
V7_MANUAL_KINDS = ("manual_first", "manual_no_ocr", "manual_replace")
V7SourcePolicy = Literal["exact_sources", "operator_selected_local_folder"]
V7CorrectionReason = Literal["blur", "occlusion", "range_error", "framing", "other"]
V7_CORRECTION_REASONS = ("blur", "occlusion", "range_error", "framing", "other")


class V7DeliveryConflict(JobConflictError):
    """Stable fail-closed error shared by HTTP and the worker adapter."""


def payload_fingerprint(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def require_sha256(value: str) -> None:
    if not _SHA256.fullmatch(value):
        raise ValueError("Expected a lowercase SHA256 fingerprint.")


@dataclass(frozen=True, slots=True)
class V7PilotSnapshot:
    geometry_family_id: str
    source_game_ref: str | None
    profile_fingerprint: str
    observer_fingerprint: str
    ocr_model_fingerprint: str
    pilot_generation: int
    binding_fingerprint: str
    receipt_fingerprint: str
    source_policy: V7SourcePolicy = "exact_sources"

    def __post_init__(self) -> None:
        if (
            not self.geometry_family_id
            or self.source_policy not in ("exact_sources", "operator_selected_local_folder")
            or (self.source_policy == "exact_sources" and not self.source_game_ref)
            or (
                self.source_policy == "operator_selected_local_folder"
                and self.source_game_ref is not None
            )
            or type(self.pilot_generation) is not int
            or self.pilot_generation < 0
        ):
            raise ValueError("Incomplete V7 pilot identity.")
        for value in (
            self.profile_fingerprint,
            self.observer_fingerprint,
            self.ocr_model_fingerprint,
            self.binding_fingerprint,
            self.receipt_fingerprint,
        ):
            require_sha256(value)

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "geometryFamilyId": self.geometry_family_id,
            "sourceGameRef": self.source_game_ref,
            "profileFingerprint": self.profile_fingerprint,
            "observerFingerprint": self.observer_fingerprint,
            "ocrModelFingerprint": self.ocr_model_fingerprint,
            "pilotGeneration": self.pilot_generation,
            "bindingFingerprint": self.binding_fingerprint,
            "receiptFingerprint": self.receipt_fingerprint,
        }
        if self.source_policy != "exact_sources":
            payload["sourcePolicy"] = self.source_policy
        return payload

    @classmethod
    def from_payload(cls, raw: object) -> V7PilotSnapshot:
        if not isinstance(raw, dict):
            raise ValueError("Missing V7 pilot snapshot.")
        data = cast(dict[str, object], raw)
        generation = data.get("pilotGeneration")
        if type(generation) is not int:
            raise ValueError("Invalid V7 pilot generation.")
        policy = data.get("sourcePolicy", "exact_sources")
        if policy not in ("exact_sources", "operator_selected_local_folder"):
            raise ValueError("Invalid V7 source policy.")
        if "sourceGameRef" not in data:
            raise ValueError("Missing V7 source game reference.")
        game = data.get("sourceGameRef")
        if game is not None and not isinstance(game, str):
            raise ValueError("Invalid V7 source game reference.")
        return cls(
            geometry_family_id=_string(data, "geometryFamilyId"),
            source_game_ref=game,
            profile_fingerprint=_string(data, "profileFingerprint"),
            observer_fingerprint=_string(data, "observerFingerprint"),
            ocr_model_fingerprint=_string(data, "ocrModelFingerprint"),
            pilot_generation=generation,
            binding_fingerprint=_string(data, "bindingFingerprint"),
            receipt_fingerprint=_string(data, "receiptFingerprint"),
            source_policy=cast(V7SourcePolicy, policy),
        )


def _string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Missing string {key}.")
    return value


@dataclass(frozen=True, slots=True)
class V7PilotGate:
    status: str = "blocked"
    generation: int = 0
    mode: str = "semi_automatic"
    geometry_family_id: str | None = None
    source_game_ref: str | None = None
    profile_fingerprint: str | None = None
    observer_fingerprint: str | None = None
    ocr_model_fingerprint: str | None = None
    source_bindings: tuple[dict[str, object], ...] = ()
    receipt_fingerprint: str | None = None
    accepted: bool = False
    acceptance_receipt: dict[str, object] | None = None
    source_policy: V7SourcePolicy = "exact_sources"

    @property
    def enabled(self) -> bool:
        if (
            self.status != "active"
            or self.mode != "semi_automatic"
            or not self.accepted
            or type(self.generation) is not int
            or self.generation < 0
            or not self.geometry_family_id
        ):
            return False
        if self.source_policy == "exact_sources":
            if not self.source_game_ref or not self.source_bindings:
                return False
        elif self.source_policy == "operator_selected_local_folder":
            if self.source_game_ref is not None or self.source_bindings:
                return False
        else:
            return False
        return all(
            isinstance(value, str) and bool(_SHA256.fullmatch(value))
            for value in (
                self.profile_fingerprint,
                self.observer_fingerprint,
                self.ocr_model_fingerprint,
                self.receipt_fingerprint,
            )
        )

    def require_source_root(self, source_root: Path) -> None:
        """Admission uses only a server-issued native picker token before this check."""
        if not self.enabled:
            raise V7DeliveryConflict("SEMI_AUTOMATIC_SELECTION_V7_BLOCKED", "V7 pilot is blocked.")
        canonical = str(source_root.resolve(strict=True))
        if self.source_policy == "operator_selected_local_folder":
            return
        if not any(
            binding.get("sourceRoot") == canonical
            and binding.get("sourceGameRef") == self.source_game_ref
            and binding.get("geometryFamilyId") == self.geometry_family_id
            for binding in self.source_bindings
        ):
            raise V7DeliveryConflict("V7_SOURCE_BINDING_MISMATCH", "Source root is not approved.")

    def snapshot_for(self, source_root: Path, source_fingerprint: str) -> V7PilotSnapshot:
        self.require_source_root(source_root)
        require_sha256(source_fingerprint)
        canonical = str(source_root.resolve(strict=True))
        matches = [
            binding
            for binding in self.source_bindings
            if (
                binding.get("sourceRoot") == canonical
                and binding.get("sourceFingerprint") == source_fingerprint
                and binding.get("sourceGameRef") == self.source_game_ref
                and binding.get("geometryFamilyId") == self.geometry_family_id
            )
        ]
        if self.source_policy == "operator_selected_local_folder":
            binding: dict[str, object] = {
                "sourceRoot": canonical,
                "sourceFingerprint": source_fingerprint,
                "sourceGameRef": None,
                "geometryFamilyId": self.geometry_family_id,
                "sourcePolicy": self.source_policy,
            }
        elif len(matches) == 1:
            binding = {
                key: matches[0][key]
                for key in ("sourceRoot", "sourceFingerprint", "sourceGameRef", "geometryFamilyId")
            }
        else:
            raise V7DeliveryConflict(
                "V7_SOURCE_BINDING_MISMATCH", "Source root/inventory/game/family is not approved."
            )
        return V7PilotSnapshot(
            geometry_family_id=cast(str, self.geometry_family_id),
            source_game_ref=self.source_game_ref,
            profile_fingerprint=cast(str, self.profile_fingerprint),
            observer_fingerprint=cast(str, self.observer_fingerprint),
            ocr_model_fingerprint=cast(str, self.ocr_model_fingerprint),
            pilot_generation=self.generation,
            binding_fingerprint=payload_fingerprint(binding),
            receipt_fingerprint=cast(str, self.receipt_fingerprint),
            source_policy=self.source_policy,
        )

    def require_snapshot(
        self, snapshot: V7PilotSnapshot, source_root: Path, source_fingerprint: str
    ) -> None:
        if self.snapshot_for(source_root, source_fingerprint) != snapshot:
            raise V7DeliveryConflict("V7_PILOT_GENERATION_CHANGED", "V7 pilot snapshot changed.")


@dataclass(frozen=True, slots=True)
class V7OutputDecision:
    operation_id: UUID
    expected_revision: int
    source_index: int
    expected_source_checksum_sha256: str
    kind: str
    range_start: int
    range_end: int
    operator_confirmed_range: bool
    operator_confirmed_incomplete_page: bool = False
    expected_target_checksum_sha256: str | None = None
    expected_owner_operation_id: UUID | None = None
    correction_reason: V7CorrectionReason | None = None

    def __post_init__(self) -> None:
        if (
            self.correction_reason is not None
            and self.correction_reason not in V7_CORRECTION_REASONS
        ):
            raise ValueError("Invalid correction reason.")
        if not isinstance(self.operation_id, UUID) or (
            self.expected_owner_operation_id is not None
            and not isinstance(self.expected_owner_operation_id, UUID)
        ):
            raise ValueError("Operation identities must be UUIDs.")
        require_sha256(self.expected_source_checksum_sha256)
        if (
            any(
                type(value) is not int
                for value in (
                    self.expected_revision,
                    self.source_index,
                    self.range_start,
                    self.range_end,
                )
            )
            or type(self.operator_confirmed_range) is not bool
            or type(self.operator_confirmed_incomplete_page) is not bool
        ):
            raise ValueError("Decision coordinates/confirmations must be strict integers/booleans.")
        if self.expected_revision < 0 or self.source_index < 0:
            raise ValueError("Invalid decision coordinates.")
        if self.kind not in V7_MANUAL_KINDS:
            raise ValueError("V7 pilot accepts only explicit manual output commands.")
        if self.range_start < 1 or not 1 <= self.range_end - self.range_start + 1 <= 9:
            raise ValueError("Invalid confirmed range.")
        if not self.operator_confirmed_range:
            raise V7DeliveryConflict(
                "V7_OPERATOR_CONFIRMATION_REQUIRED", "Confirm the source/range."
            )
        if self.kind == "manual_replace":
            if (
                self.expected_target_checksum_sha256 is None
                or self.expected_owner_operation_id is None
            ):
                raise ValueError("Replace requires the expected owner and target SHA.")
            require_sha256(self.expected_target_checksum_sha256)
        elif (
            self.expected_target_checksum_sha256 is not None
            or self.expected_owner_operation_id is not None
        ):
            raise ValueError("Only replace accepts a previous output owner.")

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "workflowMode": "v7_selection",
            "operationId": str(self.operation_id),
            "expectedRevision": self.expected_revision,
            "sourceIndex": self.source_index,
            "expectedSourceChecksumSha256": self.expected_source_checksum_sha256,
            "kind": self.kind,
            "confirmedRange": {"start": self.range_start, "end": self.range_end},
            "operatorConfirmedRange": self.operator_confirmed_range,
            "operatorConfirmedIncompletePage": self.operator_confirmed_incomplete_page,
            "expectedTargetChecksumSha256": self.expected_target_checksum_sha256,
            "expectedOwnerOperationId": (
                None
                if self.expected_owner_operation_id is None
                else str(self.expected_owner_operation_id)
            ),
        }
        # Preserve historical request fingerprints and exact replay when omitted/null.
        if self.correction_reason is not None:
            payload["correctionReason"] = self.correction_reason
        return payload

    @classmethod
    def from_payload(cls, data: dict[str, object]) -> V7OutputDecision:
        raw_range = data["confirmedRange"]
        if not isinstance(raw_range, dict):
            raise ValueError("Invalid confirmed range.")
        for key in ("expectedRevision", "sourceIndex"):
            if type(data.get(key)) is not int:
                raise ValueError("Decision coordinates must be integers.")
        if type(raw_range.get("start")) is not int or type(raw_range.get("end")) is not int:
            raise ValueError("Confirmed range coordinates must be integers.")
        return cls(
            operation_id=UUID(_string(data, "operationId")),
            expected_revision=cast(int, data["expectedRevision"]),
            source_index=cast(int, data["sourceIndex"]),
            expected_source_checksum_sha256=_string(data, "expectedSourceChecksumSha256"),
            kind=_string(data, "kind"),
            range_start=raw_range["start"],
            range_end=raw_range["end"],
            operator_confirmed_range=data.get("operatorConfirmedRange") is True,
            operator_confirmed_incomplete_page=data.get("operatorConfirmedIncompletePage") is True,
            expected_target_checksum_sha256=cast(
                str | None, data.get("expectedTargetChecksumSha256")
            ),
            expected_owner_operation_id=(
                None
                if data.get("expectedOwnerOperationId") is None
                else UUID(_string(data, "expectedOwnerOperationId"))
            ),
            correction_reason=cast(V7CorrectionReason | None, data.get("correctionReason")),
        )


@dataclass(frozen=True, slots=True)
class V7OutputOperation:
    operation_id: UUID
    run_id: UUID
    range_id: UUID
    request_payload: dict[str, object]
    context_payload: dict[str, object]
    decision_generation: int
    reserved_revision: int
    state: str
    receipt: dict[str, object] | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.decision_generation) is not int
            or self.decision_generation < 0
            or type(self.reserved_revision) is not int
            or self.reserved_revision < 0
            or self.state not in (*V7_PENDING_STATES, "committed", "conflict", "failed")
            or self.decision.operation_id != self.operation_id
        ):
            raise ValueError("Invalid durable V7 operation identity.")

    @property
    def decision(self) -> V7OutputDecision:
        return V7OutputDecision.from_payload(self.request_payload)

    @property
    def request_fingerprint(self) -> str:
        return payload_fingerprint(
            {
                "runId": str(self.run_id),
                "rangeId": str(self.range_id),
                "request": self.request_payload,
            }
        )

    def as_response(self) -> dict[str, object]:
        decision = self.decision
        return {
            "operationId": str(self.operation_id),
            "state": self.state,
            "decisionGeneration": self.decision_generation,
            "sourceIndex": decision.source_index,
            "confirmedRange": {"start": decision.range_start, "end": decision.range_end},
            "errorCode": self.error_code,
        }
