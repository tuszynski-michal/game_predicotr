"""One durable reservation before bounded, restartable game-partition provisioning."""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID, uuid4

from game_predictor_api.domain.catalog import Game
from game_predictor_api.domain.grid_model_registry import GridModelRegistryError, descriptor_sha256
from game_predictor_api.domain.grid_model_snapshots import uses_neural_grid
from game_predictor_api.domain.new_game_geometry import transfer_evidence, verified_json

# Only known availability/currentness failures allow an ordinary unassigned game.
# EVALUATION_REQUIRED includes malformed trusted evidence and is deliberately absent.
DEFAULT_UNASSIGNED_CODES = frozenset(
    {
        "GRID_MODEL_EVALUATION_STALE",
    }
)
DEFAULT_UNAVAILABLE_REASONS = frozenset(
    {
        "GRID_MODEL_ARTIFACT_MISSING",
        "GRID_MODEL_TRAINING_ARTIFACT_MISSING",
        "GRID_MODEL_ARTIFACT_MISMATCH",
        "GRID_MODEL_TRAINING_ARTIFACT_MISMATCH",
    }
)


class NewGameGeometryService:
    def __init__(self, catalog: Any, receipts: Any, registry: Any) -> None:
        self.catalog, self.receipts, self.registry = catalog, receipts, registry

    def create(self, *, key: UUID, fields: dict[str, Any], selection: dict[str, Any]) -> Game:
        command = {
            "schemaVersion": "game-create-v1",
            "kind": "create_game",
            "idempotencyKey": str(key),
            "actor": "local-owner",
            "game": {k: (v.value if hasattr(v, "value") else v) for k, v in fields.items()},
            "gridModel": selection,
        }
        self.registry.repository.lock()
        previous = self.receipts.receipt(key)
        if previous is not None:
            verified_json(previous.command_json, previous.command_sha256)
            reserved = verified_json(previous.reservation_json, previous.reservation_sha256)
            if previous.command_sha256 != descriptor_sha256(command):
                raise GridModelRegistryError(
                    "GAME_CREATE_IDEMPOTENCY_CONFLICT", "Create key has different content."
                )
            if reserved["gameId"] != str(previous.game_id):
                raise GridModelRegistryError(
                    "GRID_MODEL_REGISTRY_CORRUPT", "Create receipt identity differs."
                )
            return cast(Game, self.catalog.resume_game_create(previous.game_id))
        view, evidence, revision, reason = self._selection(selection)
        private = fields["code"] != "7" and uses_neural_grid(fields["shape_geometry_configuration"])

        def initialize(game_id: UUID) -> None:
            if private:
                self.registry.repository.mark_game_grid_model_private(game_id)
            assignment = None
            if view is not None:
                family_id = UUID(view["manifest"]["familyId"])
                lineage = self.registry.repository.lineage(UUID(view["manifest"]["versionId"]))
                if private:
                    family_id = self._private_fork(
                        game_id, fields["name"], view, lineage, "local-owner", selection
                    )
                elif selection["mode"] == "fork":
                    family_id = uuid4()
                    self.registry.repository.create_family_fork(
                        family_id=family_id,
                        code=selection["familyCode"],
                        label=selection["familyLabel"],
                        view=view,
                        lineage=lineage,
                        actor="local-owner",
                    )
                assignment = self._bootstrap(
                    game_id=game_id,
                    key=key,
                    view=view,
                    evidence=evidence,
                    training_family_id=family_id,
                    default_revision=revision,
                    lineage=lineage,
                    command={
                        "kind": "bootstrap",
                        "idempotencyKey": str(key),
                        "expectedRevision": 0,
                        "versionId": view["manifest"]["versionId"],
                        "gameId": str(game_id),
                        "evaluationId": None,
                        "actor": "local-owner",
                        "origin": "game-create-v1",
                    },
                )
            self.receipts.record(
                command,
                {
                    "schemaVersion": "game-create-reservation-v1",
                    "gameId": str(game_id),
                    "reasonCode": reason,
                    "defaultRevision": revision,
                    "assignment": assignment,
                    "gridModelPrivate": private,
                },
            )

        return cast(Game, self.catalog.reserve_game(**fields, initializer=initialize))

    def _selection(self, selection: dict[str, Any]) -> tuple[Any, Any, int | None, str]:
        revision = None
        if selection["mode"] == "default":
            default = self.registry.repository.default()
            if default is None:
                return None, None, 0, "GRID_MODEL_DEFAULT_REQUIRED"
            version_id, revision = default.version_id, default.revision
        else:
            version_id = UUID(
                selection["versionId"]
                if selection["mode"] == "published"
                else selection["baseVersionId"]
            )
        try:
            view, evidence = self._eligible_shared_base(version_id)
        except GridModelRegistryError as error:
            expected = error.code in DEFAULT_UNASSIGNED_CODES or (
                error.code == "GRID_MODEL_ARTIFACT_UNAVAILABLE"
                and error.message in DEFAULT_UNAVAILABLE_REASONS
            )
            if selection["mode"] != "default" or not expected:
                raise
            return (
                None,
                None,
                revision,
                (error.message if error.code == "GRID_MODEL_ARTIFACT_UNAVAILABLE" else error.code),
            )
        return view, evidence, revision, "GRID_MODEL_TRANSFER_ASSIGNED"

    def _eligible_shared_base(self, version_id: UUID) -> tuple[Any, Any]:
        if self.registry.repository.version_owner_game_id(version_id) is not None:
            raise GridModelRegistryError(
                "GRID_MODEL_PRIVATE_OWNER_MISMATCH",
                "A private model cannot be the starting version of another game.",
            )
        view, evidence = self.registry.control.eligible(version_id)
        return view, evidence

    def _private_fork(
        self,
        game_id: UUID,
        game_name: str,
        view: dict[str, Any],
        lineage: dict[str, Any],
        actor: str,
        selection: dict[str, Any] | None = None,
    ) -> UUID:
        family_id = uuid4()
        explicit = selection if selection is not None and selection["mode"] == "fork" else {}
        self.registry.repository.create_family_fork(
            family_id=family_id,
            code=explicit.get("familyCode", f"grid_game_{game_id.hex}"),
            label=explicit.get("familyLabel", game_name),
            view=view,
            lineage=lineage,
            actor=actor,
            owner_game_id=game_id,
        )
        return family_id

    def _bootstrap(
        self,
        *,
        game_id: UUID,
        key: UUID,
        view: dict[str, Any],
        evidence: dict[str, Any],
        training_family_id: UUID,
        default_revision: int | None,
        lineage: dict[str, Any],
        command: dict[str, Any],
    ) -> dict[str, Any]:
        provenance = transfer_evidence(
            view,
            evidence,
            training_family_id=str(training_family_id),
            default_revision=default_revision,
            lineage_sha256=descriptor_sha256(lineage),
        )
        receipt = {
            **command,
            "eventId": str(uuid4()),
            "revision": 1,
            "commandSha256": descriptor_sha256(command),
            "manifestSha256": view["manifestSha256"],
            "evidenceKind": "transfer_bootstrap",
            "evidenceSha256": descriptor_sha256(provenance),
            "transfer": provenance,
            "trainingFamilyId": str(training_family_id),
        }
        self.registry.repository.apply_control(command, receipt, provenance)
        return receipt

    def initial_transfer(
        self, *, game_id: UUID, key: UUID, expected_revision: int, version_id: UUID, actor: str
    ) -> dict[str, Any]:
        command = {
            "kind": "bootstrap",
            "idempotencyKey": str(key),
            "expectedRevision": expected_revision,
            "versionId": str(version_id),
            "gameId": str(game_id),
            "evaluationId": None,
            "actor": actor,
            "mode": "initial_transfer",
        }
        repository = self.registry.repository
        repository.lock()
        game = repository.game(game_id)
        previous = self._recover_assignment(command, game_id, key)
        if previous is not None:
            return previous
        head, count = repository.assignment(game_id)
        created = self.receipts.game_receipt(game_id)
        reserved = (
            None
            if created is None
            else verified_json(created.reservation_json, created.reservation_sha256)
        )
        if created is not None:
            verified_json(created.command_json, created.command_sha256)
        if (
            expected_revision != 0
            or head is not None
            or count
            or game.code == "7"
            or not uses_neural_grid(game.shape_geometry_configuration)
            or reserved is None
            or reserved.get("gameId") != str(game_id)
            or reserved.get("assignment") is not None
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_INITIAL_TRANSFER_UNAVAILABLE",
                "Initial transfer requires a new unassigned V3 game and revision zero.",
            )
        view, evidence = self._eligible_shared_base(version_id)
        lineage = repository.lineage(version_id)
        family_id = UUID(view["manifest"]["familyId"])
        if game.grid_model_private:
            family_id = self._private_fork(game_id, game.name, view, lineage, actor)
        return self._bootstrap(
            game_id=game_id,
            key=key,
            view=view,
            evidence=evidence,
            training_family_id=family_id,
            default_revision=None,
            lineage=lineage,
            command=command,
        )

    def enable_private_model(
        self, *, game_id: UUID, key: UUID, expected_revision: int, actor: str
    ) -> dict[str, Any]:
        if type(expected_revision) is not int or expected_revision < 1 or not actor:
            raise GridModelRegistryError(
                "GRID_MODEL_COMMAND_INVALID", "Invalid enrollment command."
            )
        repository = self.registry.repository
        repository.lock()
        game = repository.game(game_id)
        command = {
            "kind": "private_enable",
            "idempotencyKey": str(key),
            "expectedRevision": expected_revision,
            "gameId": str(game_id),
            "evaluationId": None,
            "actor": actor,
        }
        previous = self._recover_assignment(command, game_id, key)
        if previous is not None:
            return previous
        head, _ = repository.assignment(game_id)
        if head is None or head.revision != expected_revision:
            raise GridModelRegistryError(
                "GRID_MODEL_REVISION_CONFLICT", "Expected revision differs from the assignment."
            )
        if game.code == "7" or not uses_neural_grid(game.shape_geometry_configuration):
            raise GridModelRegistryError(
                "GRID_MODEL_GAME_INCOMPATIBLE", "Private models require a compatible V3 game."
            )
        if game.grid_model_private:
            raise GridModelRegistryError(
                "GRID_MODEL_ALREADY_PRIVATE", "This game already uses a private model family."
            )
        active = repository.active_grid_operation(game_id)
        if active is not None:
            error = GridModelRegistryError(
                "GRID_MODEL_PRIVATE_OPERATION_ACTIVE",
                "Finish the active geometry operation before enabling a private family.",
            )
            error.details = {"jobId": str(active)}
            raise error
        view, evidence = self.registry.control.assigned_comparison_reference(game_id)
        lineage = repository.lineage(head.version_id)
        repository.mark_game_grid_model_private(game_id)
        family_id = self._private_fork(game_id, game.name, view, lineage, actor)
        enrollment = transfer_evidence(
            view,
            evidence,
            training_family_id=str(family_id),
            default_revision=None,
            lineage_sha256=descriptor_sha256(lineage),
        )
        command["versionId"] = str(head.version_id)
        receipt = {
            **command,
            "eventId": str(uuid4()),
            "revision": expected_revision + 1,
            "commandSha256": descriptor_sha256(command),
            "manifestSha256": view["manifestSha256"],
            "evidenceKind": "private_family_enrollment",
            "evidenceSha256": descriptor_sha256(enrollment),
            "transfer": enrollment,
            "trainingFamilyId": str(family_id),
        }
        repository.apply_control(command, receipt, enrollment)
        return receipt

    def _recover_assignment(
        self, command: dict[str, Any], game_id: UUID, key: UUID
    ) -> dict[str, Any] | None:
        previous = self.registry.repository.control_receipt(key, game_id)
        if previous is None:
            return None
        stored_command = verified_json(previous.command_json, previous.command_sha256)
        if command["kind"] == "private_enable":
            command = {**command, "versionId": stored_command.get("versionId")}
        if previous.command_sha256 != descriptor_sha256(command):
            raise GridModelRegistryError(
                "GRID_MODEL_IDEMPOTENCY_CONFLICT", "Assignment key has different content."
            )
        try:
            result = json.loads(previous.receipt_json)
        except (ValueError, TypeError) as error:
            raise GridModelRegistryError(
                "GRID_MODEL_REGISTRY_CORRUPT", "Assignment receipt differs."
            ) from error
        if (
            not isinstance(result, dict)
            or result.get("commandSha256") != previous.command_sha256
            or result.get("evidenceSha256") != previous.evidence_sha256
            or descriptor_sha256(result.get("transfer")) != previous.evidence_sha256
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_REGISTRY_CORRUPT", "Assignment receipt differs."
            )
        return result
