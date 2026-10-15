"""Transactional registration, immutable reads and game-scoped assignment views."""

from __future__ import annotations

import json
from typing import Any, Protocol
from uuid import UUID

from game_predictor_api.application.grid_model_publication import (
    GridModelControlRepository,
    GridModelPublicationService,
)
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    descriptor_sha256,
    historical_catalogue,
    validate_manifest,
)


class GridModelRecord(Protocol):
    id: UUID
    manifest_json: str
    manifest_sha256: str


class GridModelReceipt(Protocol):
    command_sha256: str
    version_id: UUID


class GridModelAssignment(Protocol):
    revision: int
    version_id: UUID


class GridModelRegistryRepository(GridModelControlRepository, Protocol):
    def lock(self) -> None: ...
    def receipt(self, key: UUID) -> GridModelReceipt | None: ...
    def versions(self) -> list[Any]: ...
    def version(self, version_id: UUID) -> GridModelRecord | None: ...
    def register(
        self, payload: dict[str, Any], manifest_json: str, checksum: str, key: UUID
    ) -> GridModelRecord: ...
    def assignment(self, game_id: UUID) -> tuple[GridModelAssignment | None, int]: ...


class GridModelInspector(Protocol):
    def inspect(self, payload: dict[str, Any]) -> tuple[bool, str]: ...
    def historical_evidence(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class GridModelRegistryService:
    def __init__(
        self, repository: GridModelRegistryRepository, inspector: GridModelInspector
    ) -> None:
        self.repository, self.inspector = repository, inspector
        self.control = GridModelPublicationService(self, repository)

    def view(self, record: GridModelRecord, *, include_eligibility: bool = True) -> dict[str, Any]:
        payload = json.loads(record.manifest_json)
        if (
            validate_manifest(payload) != record.manifest_json
            or descriptor_sha256(payload) != record.manifest_sha256
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_REGISTRY_CORRUPT", "Stored immutable descriptor differs."
            )
        available, reason = self.inspector.inspect(payload)
        view = {
            "manifest": payload,
            "manifestSha256": record.manifest_sha256,
            "available": available,
            "reasonCode": reason,
            "published": self.repository.publication(record.id) is not None,
            "eligible": False,
            "eligibilityReasonCode": "GRID_MODEL_NOT_PUBLISHED",
        }
        if include_eligibility and view["published"]:
            try:
                self.control._eligible_inspected(view)
            except GridModelRegistryError as error:
                view["eligibilityReasonCode"] = error.code
            else:
                view["eligible"] = True
                view["eligibilityReasonCode"] = "GRID_MODEL_ELIGIBLE"
        return view

    def list_versions(self) -> list[dict[str, Any]]:
        return [self.view(record) for record in self.repository.versions()]

    def register(self, key: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        manifest_json = validate_manifest(payload)
        checksum = descriptor_sha256(payload)
        if payload["admission"] == "historical_baseline" and payload not in historical_catalogue():
            raise GridModelRegistryError(
                "GRID_MODEL_HISTORICAL_BASE_INVALID",
                "Only frozen historical bases may claim admission.",
            )
        if payload["admission"] == "not_evaluated" and payload["baseVersionId"] is None:
            raise GridModelRegistryError(
                "GRID_MODEL_BASE_INVALID", "New versions must pin a base version."
            )
        self.repository.lock()
        receipt = self.repository.receipt(key)
        if receipt is not None:
            if receipt.command_sha256 != checksum:
                raise GridModelRegistryError(
                    "GRID_MODEL_IDEMPOTENCY_CONFLICT", "Idempotency key has different content."
                )
            record = self.repository.version(receipt.version_id)
            if record is None:
                raise GridModelRegistryError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Receipt refers to a missing version."
                )
            view = self.view(record)
            if not view["available"]:
                raise GridModelRegistryError(
                    "GRID_MODEL_ARTIFACT_UNAVAILABLE", str(view["reasonCode"])
                )
            return view
        available, reason = self.inspector.inspect(payload)
        if not available:
            raise GridModelRegistryError("GRID_MODEL_ARTIFACT_UNAVAILABLE", reason)
        view = self.view(self.repository.register(payload, manifest_json, checksum, key))
        if not view["available"]:
            raise GridModelRegistryError("GRID_MODEL_ARTIFACT_UNAVAILABLE", str(view["reasonCode"]))
        return view

    def game_assignment(self, game_id: UUID) -> dict[str, Any]:
        assignment, event_count = self.repository.assignment(game_id)
        view = None
        if assignment is not None:
            record = self.repository.version(assignment.version_id)
            if record is None:
                raise GridModelRegistryError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Assignment version is missing."
                )
            view = self.view(record)
        return {
            "gameId": game_id,
            "revision": None if assignment is None else assignment.revision,
            "version": view,
            "eventCount": event_count,
        }
