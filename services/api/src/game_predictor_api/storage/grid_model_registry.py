"""Explicit public catalogue statements and fail-closed artifact inspection."""

from __future__ import annotations

import hashlib
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
    historical_catalogue,
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
    GridModelControlEventModel,
    GridModelDefaultModel,
    GridModelEvaluationInvalidationModel,
    GridModelEvaluationReportModel,
    GridModelFamilyModel,
    GridModelPublicationModel,
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

    def historical_evidence(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload not in historical_catalogue():
            raise GridModelRegistryError(
                "GRID_MODEL_HISTORICAL_BASE_INVALID", "Only exact frozen historical bases qualify."
            )
        root = Path(__file__).resolve().parents[5]
        relative = payload["inferenceManifest"]["report"]
        report = (root / relative).resolve()
        try:
            if not report.is_relative_to(root / "ai_docs" / "quality"):
                raise ValueError("Historical report path differs.")
            if not 0 < report.stat().st_size <= 1024 * 1024:
                raise ValueError("Historical report size is invalid.")
            content = report.read_bytes()
            content.decode("utf-8")
        except (OSError, UnicodeError, ValueError) as error:
            raise GridModelRegistryError(
                "GRID_MODEL_HISTORICAL_REPORT_UNAVAILABLE",
                "Existing historical report is required.",
            ) from error
        return {
            "kind": "historical_admission",
            "report": relative,
            "reportSha256": hashlib.sha256(content).hexdigest(),
            "historicalResults": payload["historicalReports"],
            "manifestSha256": descriptor_sha256(payload),
        }


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
            select(GameGridModelAssignmentModel)
            .where(GameGridModelAssignmentModel.game_id == game_id)
            .execution_options(populate_existing=True)
        )
        count = self.session.scalar(
            select(func.count())
            .select_from(GameGridModelAssignmentEventModel)
            .where(GameGridModelAssignmentEventModel.game_id == game_id)
        )
        return assignment, int(count or 0)

    def publication(self, version_id: UUID) -> GridModelPublicationModel | None:
        return self.session.get(GridModelPublicationModel, version_id)

    def evaluation(self, report_id: UUID) -> tuple[GridModelEvaluationReportModel | None, bool]:
        report = self.session.get(GridModelEvaluationReportModel, report_id)
        invalidated = (
            self.session.scalar(
                select(GridModelEvaluationInvalidationModel.id)
                .where(GridModelEvaluationInvalidationModel.report_id == report_id)
                .limit(1)
            )
            is not None
        )
        return report, invalidated

    def default(self) -> GridModelDefaultModel | None:
        # A caller may have read the head before waiting for the transaction lock.
        return self.session.get(GridModelDefaultModel, "geometry-v3", populate_existing=True)

    def game(self, game_id: UUID) -> Any:
        # Explicit predicate and the same session/scope guards as assignment reads.
        self.assignment(game_id)
        games = table(
            "games",
            column("id", Uuid),
            column("code"),
            column("shape_geometry_configuration"),
            schema="public",
        )
        return self.session.execute(
            select(games).where(games.c.id == game_id).with_for_update()
        ).one()

    def control_receipt(self, key: UUID, game_id: UUID | None) -> Any:
        if game_id is None:
            return self.session.get(GridModelControlEventModel, key)
        return self.session.scalar(
            select(GameGridModelAssignmentEventModel).where(
                GameGridModelAssignmentEventModel.game_id == game_id,
                GameGridModelAssignmentEventModel.idempotency_key == key,
            )
        )

    def previous_assignment(self, game_id: UUID, version_id: UUID) -> bool:
        head, _ = self.assignment(game_id)
        return (
            head is not None
            and self.session.scalar(
                select(GameGridModelAssignmentEventModel.id)
                .where(
                    GameGridModelAssignmentEventModel.game_id == game_id,
                    GameGridModelAssignmentEventModel.version_id == version_id,
                    GameGridModelAssignmentEventModel.revision < head.revision,
                )
                .limit(1)
            )
            is not None
        )

    def apply_control(
        self, command: dict[str, Any], receipt: dict[str, Any], evidence: dict[str, Any]
    ) -> None:
        kind, version_id = command["kind"], UUID(command["versionId"])
        game_id = None if command["gameId"] is None else UUID(command["gameId"])
        common = {
            "version_id": version_id,
            "kind": kind,
            "revision": receipt["revision"],
            "expected_revision": command["expectedRevision"],
            "command_sha256": receipt["commandSha256"],
            "command_json": canonical_json(command),
            "receipt_json": canonical_json(receipt),
            "actor": command["actor"],
            "evidence_sha256": receipt["evidenceSha256"],
        }
        if kind == "publish":
            self.session.add(
                GridModelPublicationModel(
                    version_id=version_id,
                    evaluation_id=None
                    if command["evaluationId"] is None
                    else UUID(command["evaluationId"]),
                    evidence_json=canonical_json(evidence),
                    evidence_sha256=receipt["evidenceSha256"],
                )
            )
        elif kind == "set_default":
            default = self.default()
            if default is None:
                self.session.add(
                    GridModelDefaultModel(
                        id="geometry-v3", version_id=version_id, revision=receipt["revision"]
                    )
                )
            else:
                default.version_id, default.revision = version_id, receipt["revision"]
        else:
            assert game_id is not None
            assignment, _ = self.assignment(game_id)
            if assignment is None:
                self.session.add(
                    GameGridModelAssignmentModel(
                        game_id=game_id, version_id=version_id, revision=receipt["revision"]
                    )
                )
            else:
                assignment.version_id, assignment.revision = version_id, receipt["revision"]
            self.session.flush()
        if game_id is None:
            self.session.add(
                GridModelControlEventModel(
                    idempotency_key=UUID(command["idempotencyKey"]), **common
                )
            )
        else:
            self.session.add(
                GameGridModelAssignmentEventModel(
                    game_id=game_id,
                    id=uuid4(),
                    idempotency_key=UUID(command["idempotencyKey"]),
                    **common,
                )
            )
        self.session.flush()

    def history(self, game_id: UUID | None) -> list[dict[str, Any]]:
        if game_id is None:
            events = self.session.scalars(
                select(GridModelControlEventModel)
                .order_by(
                    GridModelControlEventModel.created_at.desc(),
                    GridModelControlEventModel.idempotency_key,
                )
                .limit(200)
            )
        else:
            self.assignment(game_id)
            events = self.session.scalars(
                select(GameGridModelAssignmentEventModel)
                .where(GameGridModelAssignmentEventModel.game_id == game_id)
                .order_by(GameGridModelAssignmentEventModel.revision.desc())
                .limit(200)
            )
        return [
            {
                **(
                    json.loads(event.receipt_json)
                    if event.receipt_json
                    else {
                        "kind": event.kind,
                        "gameId": str(game_id),
                        "versionId": str(event.version_id),
                        "revision": event.revision,
                        "actor": "migration:0156",
                    }
                ),
                "createdAt": event.created_at,
            }
            for event in events
        ]
