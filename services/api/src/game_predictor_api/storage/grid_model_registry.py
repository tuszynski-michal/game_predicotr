"""Explicit public catalogue statements and fail-closed artifact inspection."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Table, Uuid, column, func, select, table, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_model_registry import (
    GridModelRegistryError,
    canonical_json,
    descriptor_sha256,
    historical_catalogue,
)
from game_predictor_api.storage import grid_model_evaluation_repository as evaluation_evidence
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
    def __init__(self, artifact_root: Path | None) -> None:
        self.root = None if artifact_root is None else artifact_root.resolve()

    def inspect(self, payload: dict[str, Any]) -> tuple[bool, str]:
        if self.root is None:
            return False, "GRID_MODEL_STORE_UNCONFIGURED"
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
            fork = self.family_fork(family_id)
            if fork is not None:
                lineage = self.lineage(base.id)
                if not any(
                    item["versionId"] == str(fork.base_version_id)
                    and item["manifestSha256"] == fork.base_manifest_sha256
                    for item in lineage["ancestors"]
                ):
                    raise GridModelRegistryError(
                        "GRID_MODEL_FORK_BASE_CONFLICT",
                        "Candidate does not descend from the fork base.",
                    )
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

    def cohort_currentness(
        self, report_id: UUID, cohorts: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        """D-559 barrier: public proofs and notice watermarks only, no game partition."""
        return evaluation_evidence.cohort_currentness(self.session, report_id, cohorts)

    def family_games(self, family_id: UUID) -> set[str]:
        return evaluation_evidence.family_games(self.session, family_id)

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
        if kind == "bootstrap":
            assert game_id is not None
            head, count = self.assignment(game_id)
            if head is not None or count or command["expectedRevision"] != 0:
                raise GridModelRegistryError(
                    "GRID_MODEL_REVISION_CONFLICT", "Initial assignment must be revision zero."
                )
            # No game-owned ORM flush while the reserved store is MIGRATING.
            # Typed public Core writes use exactly the caller's transaction/role.
            connection = self.session.connection()
            connection.execute(
                cast(Table, GameGridModelAssignmentModel.__table__)
                .insert()
                .values(
                    game_id=game_id,
                    version_id=version_id,
                    revision=1,
                    training_family_id=UUID(receipt["trainingFamilyId"]),
                )
            )
            connection.execute(
                cast(Table, GameGridModelAssignmentEventModel.__table__)
                .insert()
                .values(
                    game_id=game_id,
                    id=UUID(receipt["eventId"]),
                    idempotency_key=UUID(command["idempotencyKey"]),
                    **common,
                )
            )
            return
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
            assignment = self.session.get(GameGridModelAssignmentModel, game_id)
            assert assignment is not None
            version = self.version(version_id)
            assert version is not None
            assignment.training_family_id = version.family_id
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

    def family_fork(self, family_id: UUID) -> Any:
        from game_predictor_api.storage.grid_model_registry_models import GridModelFamilyForkModel

        return self.session.get(GridModelFamilyForkModel, family_id)

    def family_label(self, family_id: UUID) -> str:
        family = self.session.get(GridModelFamilyModel, family_id)
        if family is None:
            raise GridModelRegistryError(
                "GRID_MODEL_REGISTRY_CORRUPT", "Training family is missing."
            )
        descriptor = json.loads(family.descriptor_json)
        return str(descriptor["familyLabel"])

    def initial_transfer_allowed(self, game_id: UUID) -> bool:
        assignment, events = self.assignment(game_id)
        if assignment is not None or events:
            return False
        created = self.game_receipt(game_id)
        if created is None:
            return False
        from game_predictor_api.domain.new_game_geometry import verified_json

        reservation = verified_json(created.reservation_json, created.reservation_sha256)
        if reservation.get("gameId") != str(game_id) or reservation.get("assignment") is not None:
            return False
        games = table(
            "games",
            column("id", Uuid),
            column("code"),
            column("shape_geometry_configuration"),
            schema="public",
        )
        game = self.session.execute(select(games).where(games.c.id == game_id)).one_or_none()
        if game is None:
            raise GridModelRegistryError("GRID_MODEL_GAME_NOT_FOUND", "Game is missing.", 404)
        return bool(game.code != "7" and game.shape_geometry_configuration == "neural_grid_v3")

    def game_receipt(self, game_id: UUID) -> Any:
        from game_predictor_api.storage.game_create_receipts import (
            SqlAlchemyGameCreateReceiptRepository,
        )

        return SqlAlchemyGameCreateReceiptRepository(self.session).game_receipt(game_id)

    def lineage(self, version_id: UUID) -> dict[str, Any]:
        """Pin ancestors; unresolved protection never means empty TRAIN exclusions."""
        from game_predictor_api.domain.new_game_geometry import PROTECTED_ROLES, verified_json

        ancestors: list[dict[str, Any]] = []
        families: dict[str, str] = {}
        seen: set[UUID] = set()
        current: UUID | None = version_id
        while current is not None:
            if current in seen or len(seen) >= 64:
                raise GridModelRegistryError(
                    "GRID_MODEL_LINEAGE_INVALID", "Ancestry cycles or exceeds 64 versions."
                )
            seen.add(current)
            version = self.version(current)
            if version is None:
                raise GridModelRegistryError(
                    "GRID_MODEL_LINEAGE_INVALID", "An ancestor is missing."
                )
            manifest = verified_json(version.manifest_json, version.manifest_sha256)
            if (
                manifest["versionId"] != str(current)
                or manifest["familyId"] != str(version.family_id)
                or manifest["baseVersionId"]
                != (None if version.base_version_id is None else str(version.base_version_id))
            ):
                raise GridModelRegistryError(
                    "GRID_MODEL_LINEAGE_INVALID", "Ancestor identity differs."
                )
            publication = self.publication(current)
            evidence = (
                None
                if publication is None
                else verified_json(publication.evidence_json, publication.evidence_sha256)
            )
            evaluation = None
            if publication is not None and publication.evaluation_id is not None:
                report, _ = self.evaluation(publication.evaluation_id)
                if report is None:
                    raise GridModelRegistryError(
                        "GRID_MODEL_LINEAGE_INVALID", "Ancestor evaluation is missing."
                    )
                body = verified_json(report.report_json, report.report_sha256)
                evaluation = {
                    "evaluationId": str(report.id),
                    "evaluationSha256": report.report_sha256,
                    "cohortSha256": body["cohortSha256"],
                }
            ancestors.append(
                {
                    "versionId": str(current),
                    "manifestSha256": version.manifest_sha256,
                    "snapshotId": manifest["provenance"]["snapshotId"],
                    "cohortId": manifest["cohortId"],
                    "publicationEvidenceSha256": None
                    if publication is None
                    else publication.evidence_sha256,
                    "historicalReportSha256": None
                    if evidence is None
                    else evidence.get("reportSha256"),
                    "evaluation": evaluation,
                }
            )
            fork = self.family_fork(version.family_id)
            if fork is not None:
                verified_json(fork.lineage_json, fork.lineage_sha256)
                families[str(version.family_id)] = fork.lineage_sha256
            current = version.base_version_id
        return {
            "schemaVersion": "grid-model-family-lineage-v1",
            "ancestors": ancestors,
            "familyForks": families,
            "protectedRoles": list(PROTECTED_ROLES),
            "requiresProtectedSourceResolution": True,
        }

    def create_family_fork(
        self,
        *,
        family_id: UUID,
        code: str,
        label: str,
        view: dict[str, Any],
        lineage: dict[str, Any],
        actor: str,
    ) -> None:
        from game_predictor_api.storage.grid_model_registry_models import GridModelFamilyForkModel

        existing = self.session.scalar(
            select(GridModelFamilyModel.id).where(GridModelFamilyModel.code == code)
        )
        if existing is not None:
            raise GridModelRegistryError(
                "GRID_MODEL_FAMILY_CONFLICT", "The new family code is already in use."
            )
        manifest = view["manifest"]
        self.session.add(
            GridModelFamilyModel(
                id=family_id,
                code=code,
                descriptor_json=canonical_json(
                    {
                        "familyCode": code,
                        "familyLabel": label,
                        "topology": manifest["topology"],
                        "capabilities": manifest["capabilities"],
                    }
                ),
            )
        )
        self.session.flush()
        self.session.add(
            GridModelFamilyForkModel(
                family_id=family_id,
                base_version_id=UUID(manifest["versionId"]),
                base_manifest_sha256=view["manifestSha256"],
                lineage_json=canonical_json(lineage),
                lineage_sha256=descriptor_sha256(lineage),
                actor=actor,
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
