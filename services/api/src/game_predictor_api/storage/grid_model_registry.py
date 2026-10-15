"""Explicit public catalogue statements and fail-closed artifact inspection."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Uuid, column, func, select, table, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
)
from game_predictor_api.storage.database import session_game
from game_predictor_api.storage.game_storage_routing import (
    GameStorageRouter,
    current_game_storage_scope,
)
from game_predictor_api.storage.grid_engine_model_store import file_sha256, receipt_bytes
from game_predictor_api.storage.grid_model_registry_models import (
    GameGridModelAssignmentEventModel,
    GameGridModelAssignmentModel,
    GridModelFamilyModel,
    GridModelRegistrationReceiptModel,
    GridModelVersionEventModel,
    GridModelVersionModel,
)


class GridModelArtifactInspector:
    def __init__(self, artifact_root: Path) -> None:
        self.root = artifact_root.resolve()

    def inspect(self, payload: dict[str, Any]) -> tuple[bool, str]:
        directory = self.root / payload["managedDirectory"]
        try:
            targets = [
                directory / "manifest.json",
                *(directory / file["name"] for file in payload["files"]),
            ]
            if any(
                not target.resolve().is_relative_to(self.root / "models" / "grid-engine")
                for target in targets
            ):
                return False, "GRID_MODEL_PATH_INVALID"
            if any(not target.is_file() for target in targets):
                return False, "GRID_MODEL_ARTIFACT_MISSING"
            training_directory = directory / "training-base"
            training_targets = [
                training_directory / file["name"] for file in payload["trainingArtifacts"]
            ]
            receipt = training_directory / "receipt.json"
            if any(
                not target.resolve().is_relative_to(self.root / "models" / "grid-engine")
                for target in (*training_targets, receipt)
            ):
                return False, "GRID_MODEL_PATH_INVALID"
            if any(not target.is_file() for target in (*training_targets, receipt)):
                return False, "GRID_MODEL_TRAINING_ARTIFACT_MISSING"
            if receipt.stat().st_size > 65536:
                return False, "GRID_MODEL_TRAINING_RECEIPT_INVALID"
            envelope = json.loads(receipt.read_text(encoding="utf-8"))
            training_identity = envelope["payload"]
            if not isinstance(training_identity, dict):
                return False, "GRID_MODEL_TRAINING_RECEIPT_INVALID"
            sources = training_identity.get("sources")
            names = {file["name"] for file in payload["trainingArtifacts"]}
            if (
                not isinstance(sources, dict)
                or sources.keys() != names
                or any(
                    not isinstance(value, str) or not Path(value).is_absolute()
                    for value in sources.values()
                )
                or training_directory.is_symlink()
                or training_directory.is_junction()
                or {path.name for path in training_directory.iterdir()} != names | {"receipt.json"}
            ):
                return False, "GRID_MODEL_TRAINING_RECEIPT_INVALID"
            if (
                receipt_bytes(training_identity) != receipt.read_bytes()
                or training_identity.get("schemaVersion") != "grid-engine-training-base-v1"
                or training_identity.get("model") != payload["inferenceManifest"]
                or training_identity.get("files") != payload["trainingArtifacts"]
            ):
                return False, "GRID_MODEL_TRAINING_RECEIPT_INVALID"
            for file, target in zip(payload["trainingArtifacts"], training_targets, strict=True):
                if (
                    target.stat().st_size != file["sizeBytes"]
                    or file_sha256(target) != file["sha256"]
                ):
                    return False, "GRID_MODEL_TRAINING_ARTIFACT_MISMATCH"
            # Manifest is descriptor-only, bounded before parsing. Old manifests stay unchanged.
            if (
                targets[0].stat().st_size > 65536
                or json.loads(targets[0].read_text(encoding="utf-8"))
                != payload["inferenceManifest"]
            ):
                return False, "GRID_MODEL_MANIFEST_MISMATCH"
            for file, target in zip(payload["files"], targets[1:], strict=True):
                if (
                    target.stat().st_size != file["sizeBytes"]
                    or file_sha256(target) != file["sha256"]
                ):
                    return False, "GRID_MODEL_ARTIFACT_MISMATCH"
        except (OSError, UnicodeError, ValueError, KeyError, TypeError):
            return False, "GRID_MODEL_ARTIFACT_UNREADABLE"
        return True, "GRID_MODEL_ARTIFACT_AVAILABLE"


class SqlAlchemyGridModelRegistryRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(text("SET LOCAL lock_timeout='5s'"))
            self.session.execute(text("SELECT pg_advisory_xact_lock(9910994)"))

    def receipt(self, key: UUID) -> GridModelRegistrationReceiptModel | None:
        return self.session.get(GridModelRegistrationReceiptModel, key)

    def versions(self) -> list[GridModelVersionModel]:
        return list(
            self.session.scalars(
                select(GridModelVersionModel).order_by(
                    GridModelVersionModel.family_id, GridModelVersionModel.version
                )
            )
        )

    def version(self, version_id: UUID) -> GridModelVersionModel | None:
        return self.session.get(GridModelVersionModel, version_id)

    def register(
        self, payload: dict[str, Any], manifest_json: str, checksum: str, key: UUID
    ) -> GridModelVersionModel:
        family_id, version_id = UUID(payload["familyId"]), UUID(payload["versionId"])
        descriptor = canonical_json(
            {key: payload[key] for key in ("familyCode", "familyLabel", "topology", "capabilities")}
        )
        family = self.session.get(GridModelFamilyModel, family_id)
        by_code = self.session.scalar(
            select(GridModelFamilyModel).where(GridModelFamilyModel.code == payload["familyCode"])
        )
        if (
            family is None
            and by_code is not None
            or family is not None
            and family.descriptor_json != descriptor
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_FAMILY_CONFLICT", "Family identity or compatibility differs."
            )
        existing = self.session.scalar(
            select(GridModelVersionModel).where(
                GridModelVersionModel.family_id == family_id,
                GridModelVersionModel.version == payload["version"],
            )
        )
        by_id = self.version(version_id)
        if (
            existing is not None
            and existing.id != version_id
            or by_id is not None
            and by_id.manifest_sha256 != checksum
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_VERSION_CONFLICT", "Immutable version identity differs."
            )
        if payload["baseVersionId"] is not None:
            base = self.version(UUID(payload["baseVersionId"]))
            if base is None or base.id == version_id:
                raise GridModelRegistryError(
                    "GRID_MODEL_BASE_INVALID", "Base version is missing or self-referential."
                )
            base_payload = json.loads(base.manifest_json)
            if descriptor_sha256(base_payload) != base.manifest_sha256 or any(
                base_payload[k] != payload[k]
                for k in (
                    "topology",
                    "capabilities",
                    "modelVersion",
                    "bundleFormat",
                    "preprocessingVersion",
                    "decodingPolicyVersion",
                )
            ):
                raise GridModelRegistryError(
                    "GRID_MODEL_BASE_INVALID", "Base version contracts differ."
                )
        if family is None:
            self.session.add(
                GridModelFamilyModel(
                    id=family_id, code=payload["familyCode"], descriptor_json=descriptor
                )
            )
            self.session.flush()
        if by_id is None:
            by_id = GridModelVersionModel(
                id=version_id,
                family_id=family_id,
                version=payload["version"],
                base_version_id=None
                if payload["baseVersionId"] is None
                else UUID(payload["baseVersionId"]),
                manifest_json=manifest_json,
                manifest_sha256=checksum,
            )
            self.session.add(by_id)
            self.session.flush()
            self.session.add(
                GridModelVersionEventModel(id=uuid4(), version_id=version_id, kind="registered")
            )
        self.session.add(
            GridModelRegistrationReceiptModel(
                idempotency_key=key, command_sha256=checksum, version_id=version_id
            )
        )
        self.session.flush()
        return by_id

    def assignment(self, game_id: UUID) -> tuple[GameGridModelAssignmentModel | None, int]:
        scope = current_game_storage_scope()
        bound = session_game(self.session) or GameStorageRouter.bound_game_id(self.session)
        if (scope is not None and scope.game_id != game_id) or (
            bound is not None and bound != game_id
        ):
            raise GridModelRegistryError(
                "GRID_MODEL_GAME_SCOPE_CONFLICT", "Request and session games differ."
            )
        games = table("games", column("id", Uuid), schema="public")
        exists = self.session.scalar(select(games.c.id).where(games.c.id == game_id))
        if exists is None:
            raise GridModelRegistryError("GRID_MODEL_GAME_NOT_FOUND", "Game was not found.", 404)
        assignment = self.session.scalar(
            select(GameGridModelAssignmentModel).where(
                GameGridModelAssignmentModel.game_id == game_id
            )
        )
        count = self.session.scalar(
            select(func.count())
            .select_from(GameGridModelAssignmentEventModel)
            .where(GameGridModelAssignmentEventModel.game_id == game_id)
        )
        return assignment, int(count or 0)
