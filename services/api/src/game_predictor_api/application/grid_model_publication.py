"""Explicit publication, game activation, global default and assignment rollback."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from game_predictor_api.domain.grid_model_publication import require_evaluation_evidence
from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.domain.grid_model_snapshots import catalogue_model_version, uses_neural_grid

if TYPE_CHECKING:
    from .grid_model_registry import GridModelRegistryService


class GridModelControlRepository(Protocol):
    def lock(self) -> None: ...
    def version(self, version_id: UUID) -> Any: ...
    def publication(self, version_id: UUID) -> Any: ...
    def evaluation(self, report_id: UUID) -> tuple[Any, bool]: ...
    def default(self) -> Any: ...
    def game(self, game_id: UUID) -> Any: ...
    def assignment(self, game_id: UUID) -> tuple[Any, int]: ...
    def control_receipt(self, key: UUID, game_id: UUID | None) -> Any: ...
    def previous_assignment(self, game_id: UUID, version_id: UUID) -> bool: ...
    def apply_control(
        self, command: dict[str, Any], receipt: dict[str, Any], evidence: dict[str, Any]
    ) -> None: ...
    def history(self, game_id: UUID | None) -> list[dict[str, Any]]: ...


class GridModelPublicationService:
    def __init__(
        self, registry: GridModelRegistryService, repository: GridModelControlRepository
    ) -> None:
        self.registry, self.repository = registry, repository

    def _version(self, version_id: UUID) -> dict[str, Any]:
        record = self.repository.version(version_id)
        if record is None:
            raise GridModelRegistryError("GRID_MODEL_VERSION_NOT_FOUND", "Version not found.", 404)
        view = self.registry.view(record, include_eligibility=False)
        if not view["available"]:
            raise GridModelRegistryError("GRID_MODEL_ARTIFACT_UNAVAILABLE", view["reasonCode"])
        # Reuse the worker's exact topology, preprocessing and capabilities policy.
        try:
            catalogue_model_version(view["manifest"])
        except (TypeError, ValueError) as error:
            raise GridModelRegistryError(
                "GRID_MODEL_CONTRACT_UNSUPPORTED", "The stored model contract is unsupported."
            ) from error
        return view

    def _evidence(
        self, view: dict[str, Any], evaluation_id: UUID | None, game_id: UUID | None
    ) -> dict[str, Any]:
        manifest = view["manifest"]
        if manifest["admission"] == "historical_baseline":
            if evaluation_id is not None:
                raise GridModelRegistryError(
                    "GRID_MODEL_HISTORICAL_BASE_INVALID",
                    "A historical admission is not a new PASS.",
                )
            return self.registry.inspector.historical_evidence(manifest)
        if evaluation_id is None or manifest["baseVersionId"] is None:
            raise GridModelRegistryError(
                "GRID_MODEL_EVALUATION_REQUIRED", "A server-owned evaluation and base are required."
            )
        report, invalidated = self.repository.evaluation(evaluation_id)
        if invalidated:
            raise GridModelRegistryError(
                "GRID_MODEL_EVALUATION_STALE", "The published evaluation was invalidated."
            )
        base = self.repository.version(UUID(manifest["baseVersionId"]))
        if report is None or base is None or report.version_id != UUID(manifest["versionId"]):
            raise GridModelRegistryError(
                "GRID_MODEL_EVALUATION_REQUIRED", "The pinned evaluation or base is missing."
            )
        base_payload = json.loads(base.manifest_json)
        if (
            descriptor_sha256(base_payload) != base.manifest_sha256
            or canonical_json(base_payload) != base.manifest_json
        ):
            raise GridModelRegistryError("GRID_MODEL_REGISTRY_CORRUPT", "Base descriptor differs.")
        evidence = require_evaluation_evidence(
            report_id=evaluation_id,
            report_json=report.report_json,
            report_sha256=report.report_sha256,
            producer=report.producer,
            invalidated=invalidated,
            manifest=manifest,
            base_sha256=base.manifest_sha256,
            game_id=game_id,
        )
        return {
            "kind": "evaluated_candidate",
            "evaluationId": str(evidence.report_id),
            "evaluationSha256": evidence.report_sha256,
            "manifestSha256": view["manifestSha256"],
        }

    def eligible(
        self,
        version_id: UUID,
        *,
        game_id: UUID | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Read contract for later GameCreate: no future game's evaluation is claimed."""
        return self._eligible_inspected(self._version(version_id), game_id=game_id)

    def _eligible_inspected(
        self, view: dict[str, Any], *, game_id: UUID | None = None
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        """Registry view already inspected artifact bytes; avoid hashing them twice."""
        version_id = UUID(view["manifest"]["versionId"])
        if not view["available"]:
            raise GridModelRegistryError("GRID_MODEL_ARTIFACT_UNAVAILABLE", view["reasonCode"])
        publication = self.repository.publication(version_id)
        if publication is None:
            raise GridModelRegistryError("GRID_MODEL_NOT_PUBLISHED", "Version is not published.")
        evidence = self._evidence(view, publication.evaluation_id, game_id)
        if (
            canonical_json(evidence) != publication.evidence_json
            or descriptor_sha256(evidence) != publication.evidence_sha256
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_PUBLICATION_STALE", "Published evidence no longer matches."
            )
        return {**view, "eligible": True, "eligibilityReasonCode": "GRID_MODEL_ELIGIBLE"}, evidence

    def default_view(self) -> dict[str, Any]:
        default = self.repository.default()
        if default is None:
            return {
                "revision": 0,
                "version": None,
                "eligible": False,
                "reasonCode": "GRID_MODEL_DEFAULT_REQUIRED",
            }
        record = self.repository.version(default.version_id)
        if record is None:
            raise GridModelRegistryError("GRID_MODEL_REGISTRY_CORRUPT", "Default version missing.")
        view = self.registry.view(record)
        if not view["eligible"]:
            return {
                "revision": default.revision,
                "version": view,
                "eligible": False,
                "reasonCode": view["eligibilityReasonCode"],
            }
        return {
            "revision": default.revision,
            "version": view,
            "eligible": True,
            "reasonCode": "GRID_MODEL_ELIGIBLE",
        }

    def history(self, game_id: UUID | None = None) -> list[dict[str, Any]]:
        """Read the bounded global or explicitly scoped game control history."""
        return self.repository.history(game_id)

    def execute(
        self,
        *,
        kind: str,
        key: UUID,
        expected_revision: int,
        version_id: UUID,
        actor: str,
        game_id: UUID | None = None,
        evaluation_id: UUID | None = None,
    ) -> dict[str, Any]:
        if (
            kind not in {"publish", "set_default", "activate", "rollback"}
            or (kind in {"activate", "rollback"}) != (game_id is not None)
            or type(expected_revision) is not int
            or expected_revision < 0
            or not actor
        ):
            raise GridModelRegistryError("GRID_MODEL_COMMAND_INVALID", "Invalid control command.")
        command = {
            "kind": kind,
            "idempotencyKey": str(key),
            "expectedRevision": expected_revision,
            "versionId": str(version_id),
            "gameId": None if game_id is None else str(game_id),
            "evaluationId": None if evaluation_id is None else str(evaluation_id),
            "actor": actor,
        }
        checksum = descriptor_sha256(command)
        self.repository.lock()
        game = None if game_id is None else self.repository.game(game_id)
        previous = self.repository.control_receipt(key, game_id)
        if previous is not None:
            if previous.command_sha256 != checksum:
                raise GridModelRegistryError(
                    "GRID_MODEL_IDEMPOTENCY_CONFLICT", "Idempotency key has different content."
                )
            recovered = json.loads(previous.receipt_json)
            if not isinstance(recovered, dict):
                raise GridModelRegistryError("GRID_MODEL_REGISTRY_CORRUPT", "Receipt differs.")
            return recovered
        if kind == "publish":
            current = 0 if self.repository.publication(version_id) is None else 1
        elif kind == "set_default":
            head = self.repository.default()
            current = 0 if head is None else head.revision
        else:
            head, _ = self.repository.assignment(game_id)  # type: ignore[arg-type]
            current = 0 if head is None else head.revision
        if current != expected_revision or kind == "publish" and current != 0:
            raise GridModelRegistryError(
                "GRID_MODEL_REVISION_CONFLICT", "Expected revision differs from the current head."
            )
        if kind == "publish":
            view = self._version(version_id)
            evidence = self._evidence(view, evaluation_id, None)
        else:
            view, evidence = self.eligible(version_id, game_id=game_id)
        if game is not None:
            assert game_id is not None
            if game.code == "7" or not uses_neural_grid(game.shape_geometry_configuration):
                raise GridModelRegistryError(
                    "GRID_MODEL_GAME_INCOMPATIBLE",
                    "Only a compatible nonhistorical V3 game may activate.",
                )
            if kind == "rollback" and not self.repository.previous_assignment(game_id, version_id):
                raise GridModelRegistryError(
                    "GRID_MODEL_ROLLBACK_TARGET_INVALID",
                    "Target is not in this game's earlier history.",
                )
        receipt = {
            **command,
            "revision": current + 1,
            "commandSha256": checksum,
            "manifestSha256": view["manifestSha256"],
            "evidenceKind": evidence["kind"],
            "evidenceSha256": descriptor_sha256(evidence),
        }
        self.repository.apply_control(command, receipt, evidence)
        return receipt
