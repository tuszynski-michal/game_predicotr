"""One transaction per command: authenticated actor, replay, independent CAS, receipt."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import (
    MAX_SESSION_BOARDS,
    ContentError,
    ContentRevision,
    ContentSource,
    ContentTarget,
    content_readiness_views,
    content_source_identity,
    oracle_qualification,
    require_content_bounds,
    require_human,
)
from game_predictor_api.domain.grid_content_repeatability import repeatability_report
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.grid_visibility_contract import BoardContentReference
from game_predictor_api.schemas.grid_cell_content import (
    ContentBlindWrite,
    ContentSamplingPreview,
    ContentSessionAdvance,
    ContentSessionCreate,
    ContentWriteCommand,
)

from .game_storage_routing import GameStorageIntent, GameStorageRouter
from .grid_cell_content_models import GridCellContentCommandModel as Command
from .grid_cell_content_models import GridCellContentRevisionModel as Revision
from .grid_cell_content_models import GridCellContentSessionModel as Measurement
from .grid_quality_observations import current_targets, own_target, read_source
from .grid_training_cohort_models import GridTrainingCohortModel
from .sequence_ownership_lock import acquire_sequence_ownership_lock


def source_identity(source: dict[str, Any]) -> ContentSource:
    return content_source_identity(source)


class SqlAlchemyGridCellContentRepository:
    def __init__(
        self, session: Session, artifact_root: Path, provider_index_sha256: str | None = None
    ) -> None:
        self.session, self.root = session, artifact_root
        self.provider_index_sha256 = provider_index_sha256

    def sampling_preview(self, game: UUID, command: ContentSamplingPreview) -> dict[str, Any]:
        from game_predictor_api.domain.grid_training_cohorts import GridCohortError
        from game_predictor_api.domain.source_recording_groups import RecordingError

        from .grid_content_sampling import ContentSamplingPreparationError, resolve_content_sampling
        from .grid_correction_split import prepare_split
        from .grid_training_cohort_repository import (
            CohortDeadline,
            SqlAlchemyGridTrainingCohortRepository,
        )

        self.bind(game)
        repo = SqlAlchemyGridTrainingCohortRepository(self.session, self.root)
        try:
            policy = resolve_content_sampling(
                repo, game, command.baseVersionId, command.familyId, self.provider_index_sha256
            )
            split = prepare_split(
                repo,
                game,
                sorted({str(v) for v in command.importJobIds}),
                CohortDeadline(),
                policy="application-grid-corrections-v4",
                mode=command.trainingMode,
                validation_assignments={
                    str(k): v for k, v in command.validationAssignments.items()
                },
                content_sampling=policy,
            )
            return {
                "state": "selection_ready",
                "policy": policy["policy"],
                "split": split,
                "selection": split["contentSampling"],
                "roleWrites": False,
            }
        except ContentSamplingPreparationError as error:
            return {"state": "not_evaluable", "selection": error.report, "roleWrites": False}
        except (GridCohortError, RecordingError, ContentError) as error:
            return {"state": "not_evaluable", "reasonCodes": [error.code], "roleWrites": False}

    def bind(self, game: UUID, *, write: bool = False) -> None:
        GameStorageRouter().bind(
            self.session, game, intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ
        )
        self.session.execute(text("SET LOCAL lock_timeout='5s'"))
        self.session.execute(text("SET LOCAL statement_timeout='30s'"))

    def lock(self, game: UUID, *key: object) -> None:
        number = int(digest(["cell-content-v1", str(game), *key])[:16], 16) - 2**63
        self.session.execute(select(func.pg_advisory_xact_lock(number)))

    def replay(self, game: UUID, key: UUID, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = self.session.get(Command, (game, key))
        if row is not None:
            if row.command_sha256 != digest(payload):
                raise ContentError(
                    "CONTENT_IDEMPOTENCY_CONFLICT",
                    "This key already represents a different command.",
                )
            return dict(row.document["response"])
        return None

    def receipt(
        self, game: UUID, key: UUID, payload: dict[str, Any], response: dict[str, Any]
    ) -> dict[str, Any]:
        self.session.add(
            Command(
                game_id=game,
                idempotency_key=key,
                command_sha256=digest(payload),
                document={"command": payload, "response": response},
            )
        )
        self.session.flush()
        return response

    def begin_command(
        self, game: UUID, key: UUID, payload: dict[str, Any], actor: str
    ) -> dict[str, Any] | None:
        require_human(actor)
        self.bind(game, write=True)
        self.lock(game, "command", str(key))
        return self.replay(game, key, payload)

    def current_source(self, game: UUID, source_id: UUID, *, lock: bool = False) -> ContentSource:
        if lock:
            acquire_sequence_ownership_lock(self.session, game_id=game)
            self.session.execute(
                text("SELECT id FROM source_images WHERE game_id=:g AND id=:s FOR UPDATE"),
                {"g": game, "s": source_id},
            )
        source = read_source(self.session, game, source_id)
        if source is None:
            raise ContentError(
                "CONTENT_SOURCE_UNAVAILABLE", "The source is no longer available.", 404
            )
        current = self.session.scalar(
            text("SELECT public.source_replacement_source_current_v1(:g,:s,:sha)"),
            {"g": game, "s": source_id, "sha": source["checksum_sha256"]},
        )
        if not current:
            raise ContentError(
                "CONTENT_SOURCE_RETIRED", "Retired sources cannot receive new labels."
            )
        return source_identity(source)

    def require_board(
        self, game: UUID, source: ContentSource, position: int, sequence: int
    ) -> None:
        target = current_targets(self.session, game, source.sourceId).get(position)
        self.require_current_board(target, sequence)

    @staticmethod
    def require_current_board(target: dict[str, Any] | None, sequence: int) -> None:
        if target is None or not own_target(target):
            raise ContentError("CONTENT_TARGET_UNAVAILABLE", "A current own board is required.")
        board = target.get("board") or {}
        if board.get("sequence_number") != sequence or board.get("status") == "rejected":
            raise ContentError("CONTENT_SEQUENCE_CONFLICT", "The logical board sequence differs.")

    def list_targets(
        self, game: UUID, cohort: UUID, manifest: str, limit: int, offset: int
    ) -> dict[str, Any]:
        from .grid_cell_content_targets import list_targets

        self.bind(game)
        return list_targets(self, game, cohort, manifest, limit, offset)

    def list_source_targets(
        self, game: UUID, sources: list[UUID], limit: int, offset: int
    ) -> dict[str, Any]:
        from .grid_cell_content_targets import list_source_targets

        self.bind(game)
        return list_source_targets(self, game, sources, limit, offset)

    def annotation_source_asset(
        self, game: UUID, source: UUID, expected_source: str, expected_pixel: str
    ) -> Path:
        from .grid_cell_content_targets import annotation_source_asset

        self.bind(game)
        return annotation_source_asset(self, game, source, expected_source, expected_pixel)

    def target_source_asset(self, game: UUID, cohort: UUID, manifest: str, source: UUID) -> Path:
        from .grid_cell_content_targets import target_source_asset

        self.bind(game)
        return target_source_asset(self, game, cohort, manifest, source)

    def latest(self, game: UUID, pixel: str, position: int) -> Revision | None:
        return self.session.scalar(
            select(Revision)
            .where(
                Revision.game_id == game,
                Revision.pixel_sha256 == pixel,
                Revision.position_index == position,
            )
            .order_by(Revision.revision.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )

    def get(self, game: UUID, source_id: UUID, position: int) -> dict[str, Any]:
        self.bind(game)
        source = self.current_source(game, source_id)
        row = self.latest(game, source.sourceRepresentativeSha256, position)
        return self.reference_view(row)

    def get_preview(
        self, game: UUID, source_id: UUID, position: int, cohort: UUID, manifest: str
    ) -> dict[str, Any]:
        from .grid_content_preview import ordinary_preview

        self.bind(game)
        preview = ordinary_preview(self, game, source_id, position, cohort, manifest)
        return {**self.get(game, source_id, position), "ordinaryPreview": preview}

    @staticmethod
    def reference_view(row: Revision | None) -> dict[str, Any]:
        return {
            "annotation": None if row is None else row.document,
            "contentReferenceSha256": None if row is None else row.document_sha256,
            "revision": 0 if row is None else row.revision,
        }

    def append(
        self, annotation: ContentRevision, *, oracle: dict[str, Any] | None = None
    ) -> Revision:
        ref = annotation.reference
        row = Revision(
            game_id=ref.gameId,
            pixel_sha256=ref.sourceRepresentativeSha256,
            position_index=ref.positionIndex,
            revision=ref.revision,
            source_id=annotation.source.sourceId,
            live_source_image_id=annotation.source.sourceId,
            document_sha256=annotation.sha256,
            document=annotation.model_dump(mode="json"),
            oracle=oracle,
        )
        self.session.add(row)
        self.session.flush()
        return row

    def write(self, game: UUID, command: ContentWriteCommand, actor: str) -> dict[str, Any]:
        payload = {"kind": "write", "actor": actor, "body": command.model_dump(mode="json")}
        if replay := self.begin_command(game, command.idempotencyKey, payload, actor):
            return replay
        source = self.current_source(game, command.sourceId, lock=True)
        if (
            source.sourceSha256 != command.expectedSourceSha256
            or source.sourceRepresentativeSha256 != command.expectedPixelSha256
        ):
            raise ContentError(
                "CONTENT_SOURCE_IDENTITY_CONFLICT", "Reload the exact source identity."
            )
        self.require_board(game, source, command.positionIndex, command.sequenceNumber)
        self.lock(game, "board", source.sourceRepresentativeSha256, command.positionIndex)
        prior = self.latest(game, source.sourceRepresentativeSha256, command.positionIndex)
        if (0 if prior is None else prior.revision) != command.expectedRevision:
            raise ContentError(
                "CONTENT_REVISION_CONFLICT", "A newer independent content revision exists."
            )
        now = datetime.now(UTC)
        require_content_bounds(source, command.cells)
        row = self.append(
            ContentRevision(
                source=source,
                reference=BoardContentReference(
                    gameId=game,
                    sourceRepresentativeSha256=source.sourceRepresentativeSha256,
                    positionIndex=command.positionIndex,
                    revision=command.expectedRevision + 1,
                    humanApproved=command.humanApproval,
                    cells=command.cells,
                ),
                sequenceNumber=command.sequenceNumber,
                origin=command.origin,
                actor=actor,
                approvedBy=actor if command.humanApproval else None,
                approvedAt=now if command.humanApproval else None,
                recordedAt=now,
                proposalSha256=command.proposalSha256,
            )
        )
        return self.receipt(
            game,
            command.idempotencyKey,
            payload,
            {**self.reference_view(row), "idempotencyKey": str(command.idempotencyKey)},
        )

    def snapshot(self, game: UUID, cohort: UUID, expected: str) -> Any:
        from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot

        row = self.session.get(GridTrainingCohortModel, (game, cohort))
        if (
            row is None
            or row.status != "frozen"
            or row.manifest_sha256 != expected
            or row.manifest_path is None
        ):
            raise ContentError(
                "CONTENT_FROZEN_COHORT_REQUIRED", "The exact frozen cohort is required."
            )
        snapshot = GridCohortSnapshot(self.root, row.manifest_path, expected)
        if snapshot.manifest["policyVersion"] != "application-grid-corrections-v4":
            raise ContentError(
                "CONTENT_PURPOSE_COHORT_REQUIRED", "Explicit A/B purpose evidence is required."
            )
        return snapshot

    def create_session(
        self, game: UUID, command: ContentSessionCreate, actor: str
    ) -> dict[str, Any]:
        from game_predictor_worker.images.grid_cohort_dataset import (
            GridBoardDataset,
            has_full_geometry,
        )

        from .grid_content_oracle_context import capture_oracle_context
        from .grid_training_cohort_repository import CohortDeadline

        body = command.model_dump(mode="json")
        if command.renderReferencePolicy is None:
            body.pop("renderReferencePolicy")
        payload = {
            "kind": "session_create",
            "actor": actor,
            "body": body,
        }
        if replay := self.begin_command(game, command.idempotencyKey, payload, actor):
            return replay
        from .grid_content_oracle_context import resolve_evaluation_contract

        evaluation_contract = (
            resolve_evaluation_contract(self.session, self.root, game)
            if command.renderReferencePolicy is not None
            else None
        )
        if len(set(command.sourceIds)) != len(command.sourceIds):
            raise ContentError("CONTENT_SOURCE_DUPLICATE", "Choose each source once.", 422)
        snapshot = self.snapshot(game, command.cohortId, command.expectedManifestSha256)
        deadline = CohortDeadline()
        selected = {str(value) for value in command.sourceIds}
        requested = (
            None
            if command.targetSelection is None
            else {
                str(entry.sourceId): set(entry.positionIndices) for entry in command.targetSelection
            }
        )
        targets, found, keys = [], set(), set()
        oracle_contexts = {}
        for role in ("TRAIN", "VALIDATION"):
            for frozen, _ in GridBoardDataset(snapshot, role).indexed():
                if frozen["sourceId"] not in selected:
                    continue
                source = self.current_source(game, UUID(frozen["sourceId"]), lock=True)
                identity = frozen["sourceIdentity"]
                if (
                    source.sourceRepresentativeSha256
                    != identity["normalized_pixel_checksum_sha256"]
                ):
                    raise ContentError(
                        "CONTENT_SOURCE_IDENTITY_CONFLICT",
                        "Frozen pixels differ from the live source.",
                    )
                found.add(frozen["sourceId"])
                if requested is not None and not requested[frozen["sourceId"]].issubset(
                    {board["positionIndex"] for board in frozen["targets"]}
                ):
                    raise ContentError("CONTENT_SESSION_MEMBERSHIP", "A selected slot is absent.")
                for board in frozen["targets"]:
                    deadline.check(self.session)
                    if (
                        requested is not None
                        and board["positionIndex"] not in requested[frozen["sourceId"]]
                    ):
                        continue
                    target = ContentTarget(
                        gameId=game,
                        source=source,
                        positionIndex=board["positionIndex"],
                        sequenceNumber=board["sequenceNumber"],
                        role="A" if role == "VALIDATION" else "TRAIN",
                        fullPhoto=has_full_geometry(frozen),
                        targetSha256=digest(board),
                        roleProofSha256=frozen["purposeProofSha256"],
                    )
                    if target.key in keys:
                        raise ContentError(
                            "CONTENT_ALIAS_DUPLICATE", "Choose one copy of each photo."
                        )
                    keys.add(target.key)
                    targets.append(target.model_dump(mode="json"))
                    oracle_contexts[
                        f"{source.sourceRepresentativeSha256}:{target.positionIndex}"
                    ] = capture_oracle_context(
                        self.session,
                        game,
                        frozen["sourceIdentity"],
                        board,
                        evaluation_contract=evaluation_contract,
                    )
        if found != selected or not 1 <= len(targets) <= MAX_SESSION_BOARDS:
            raise ContentError(
                "CONTENT_SESSION_MEMBERSHIP", "The selected sources must be frozen TRAIN/A."
            )
        identifier = uuid5(game, "content-session:" + str(command.idempotencyKey))
        row = Measurement(
            game_id=game,
            id=identifier,
            cohort_id=command.cohortId,
            revision=1,
            phase="pass1",
            document={
                "version": "cell-content-blind-session-v1",
                "actor": actor,
                "createdAt": datetime.now(UTC).isoformat(),
                "manifestSha256": command.expectedManifestSha256,
                "oracleContexts": oracle_contexts,
                **(
                    {"evaluationContract": evaluation_contract}
                    if evaluation_contract is not None
                    else {}
                ),
                "targets": sorted(
                    targets,
                    key=lambda t: (t["source"]["sourceRepresentativeSha256"], t["positionIndex"]),
                ),
            },
            progress={"pass1": {}, "pass2": {}},
            report=None,
        )
        self.session.add(row)
        self.session.flush()
        return self.receipt(
            game,
            command.idempotencyKey,
            payload,
            {"idempotencyKey": str(command.idempotencyKey), "session": self.session_status(row)},
        )

    def measurement(self, game: UUID, identifier: UUID, *, lock: bool = False) -> Measurement:
        query = select(Measurement).where(Measurement.game_id == game, Measurement.id == identifier)
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query.execution_options(populate_existing=True))
        if row is None:
            raise ContentError(
                "CONTENT_SESSION_NOT_FOUND", "The blind session does not exist.", 404
            )
        return row

    @staticmethod
    def session_status(row: Measurement) -> dict[str, Any]:
        phase = "pass2" if row.phase == "frozen" else row.phase
        return {
            "sessionId": str(row.id),
            "gameId": str(row.game_id),
            "revision": row.revision,
            "phase": row.phase,
            "completed": len(row.progress[phase]),
            "total": len(row.document["targets"]),
            "report": row.report if row.phase == "frozen" else None,
        }

    @staticmethod
    def session_view(row: Measurement) -> dict[str, Any]:
        phase = "pass2" if row.phase == "frozen" else row.phase
        completed = row.progress[phase]
        targets = []
        for raw in row.document["targets"]:
            target = ContentTarget.model_validate(raw)
            key = f"{target.source.sourceRepresentativeSha256}:{target.positionIndex}"
            targets.append(
                {
                    "source": target.source.model_dump(mode="json"),
                    "positionIndex": target.positionIndex,
                    "sequenceNumber": target.sequenceNumber,
                    "completed": key in completed,
                }
            )
        return {
            "sessionId": str(row.id),
            "gameId": str(row.game_id),
            "revision": row.revision,
            "phase": row.phase,
            "targets": targets,
            "completed": len(completed),
            "total": len(targets),
            "report": row.report if row.phase == "frozen" else None,
        }

    def get_session(self, game: UUID, identifier: UUID) -> dict[str, Any]:
        self.bind(game)
        return self.session_view(self.measurement(game, identifier))

    def list_sessions(self, game: UUID, limit: int = 20) -> dict[str, Any]:
        self.bind(game)
        if not 1 <= limit <= 50:
            raise ContentError("CONTENT_PAGE_LIMIT", "Choose a page size from one to fifty.", 422)
        rows = self.session.scalars(
            select(Measurement)
            .where(Measurement.game_id == game)
            .order_by(Measurement.document["createdAt"].astext.desc(), Measurement.id)
            .limit(limit)
        ).all()
        return {"items": [self.session_status(row) for row in rows]}

    def source_asset(self, game: UUID, identifier: UUID, source: UUID) -> Path:
        from .grid_training_cohort_artifacts import GridCohortArtifactStore

        self.bind(game)
        row = self.measurement(game, identifier)
        if not any(t["source"]["sourceId"] == str(source) for t in row.document["targets"]):
            raise ContentError(
                "CONTENT_SESSION_MEMBERSHIP", "The source is outside this session.", 404
            )
        snapshot = self.snapshot(game, row.cohort_id, row.document["manifestSha256"])
        frozen = next((s for s in snapshot.sources() if s["sourceId"] == str(source)), None)
        if frozen is None:
            raise ContentError("CONTENT_SOURCE_UNAVAILABLE", "The source is unavailable.", 404)
        pin = frozen["original"]
        return GridCohortArtifactStore(self.root).verify(
            pin["path"], pin["sha256"], size=pin["bytes"]
        )

    def readiness(self, game: UUID, cohort: UUID, manifest: str) -> dict[str, Any]:
        from game_predictor_worker.images.grid_cell_content_reference import (
            frozen_content_reference,
        )
        from game_predictor_worker.images.grid_cohort_dataset import (
            GridAssessmentDataset,
            GridBoardDataset,
            has_full_geometry,
        )

        self.bind(game)
        snapshot = self.snapshot(game, cohort, manifest)
        targets, references, frozen_references = [], [], []
        seen_sources: set[str] = set()
        for role in ("TRAIN", "A", "B", "REGRESSION"):
            dataset_role = "VALIDATION" if role in {"A", "B"} else role
            dataset = (GridAssessmentDataset if role in {"B", "REGRESSION"} else GridBoardDataset)(
                snapshot, dataset_role
            )
            for frozen, _ in dataset.indexed():
                seen_sources.add(frozen["sourceId"])
                source = source_identity(frozen["sourceIdentity"])
                for board in frozen["targets"]:
                    targets.append(
                        ContentTarget(
                            gameId=game,
                            source=source,
                            positionIndex=board["positionIndex"],
                            sequenceNumber=board["sequenceNumber"],
                            role=role,
                            fullPhoto=has_full_geometry(frozen),
                            targetSha256=digest(board),
                            roleProofSha256=frozen["purposeProofSha256"],
                        )
                    )
                    reference = self.latest(
                        game, source.sourceRepresentativeSha256, board["positionIndex"]
                    )
                    if reference is not None:
                        references.append(ContentRevision.model_validate(reference.document))
                    if frozen_content_reference(game, frozen, board) is not None:
                        frozen_references.append(
                            ContentRevision.model_validate(board["contentAnnotation"])
                        )
        pins = {pin["sourceId"]: pin for pin in snapshot.manifest["photoSplit"]["sources"]}
        unresolved: dict[tuple[str, str], set[str]] = {}
        for frozen in snapshot.sources():
            pin = pins[frozen["sourceId"]]
            incomplete_targets = pin.get("canonicalBoards", len(frozen["targets"])) > len(
                frozen["targets"]
            )
            if (
                (frozen["sourceId"] in seen_sources and not incomplete_targets)
                or not pin.get("representative")
                or pin.get("contentExcluded")
                or pin.get("buffer")
                or not pin.get("role")
            ):
                continue
            role = pin.get("validationPurpose") if pin["role"] == "VALIDATION" else pin["role"]
            unresolved.setdefault((str(game), role), set()).add(pin["pixelSha256"])
        unresolved_counts = {key: len(value) for key, value in unresolved.items()}
        return content_readiness_views(
            targets, references, frozen_references, [game], unresolved_photos=unresolved_counts
        )

    def blind_write(
        self, game: UUID, identifier: UUID, command: ContentBlindWrite, actor: str
    ) -> dict[str, Any]:
        payload = {
            "kind": "blind_write",
            "sessionId": str(identifier),
            "actor": actor,
            "body": command.model_dump(mode="json"),
        }
        if replay := self.begin_command(game, command.idempotencyKey, payload, actor):
            return replay
        row = self.measurement(game, identifier, lock=True)
        if (
            row.revision != command.expectedSessionRevision
            or row.phase != f"pass{command.passNumber}"
        ):
            raise ContentError(
                "CONTENT_SESSION_REVISION_CONFLICT", "Reload the current blind session."
            )
        selected = [
            ContentTarget.model_validate(t)
            for t in row.document["targets"]
            if t["source"]["sourceId"] == str(command.sourceId)
            and t["positionIndex"] == command.positionIndex
        ]
        if len(selected) != 1:
            raise ContentError("CONTENT_SESSION_MEMBERSHIP", "The board is outside this session.")
        target = selected[0]
        source = self.current_source(game, command.sourceId, lock=True)
        if source != target.source:
            raise ContentError("CONTENT_SOURCE_IDENTITY_CONFLICT", "The frozen source changed.")
        self.require_board(game, source, target.positionIndex, target.sequenceNumber)
        key = f"{source.sourceRepresentativeSha256}:{target.positionIndex}"
        if key in row.progress[row.phase]:
            raise ContentError(
                "CONTENT_BLIND_ALREADY_MEASURED",
                "A pass is append-only; start a new session to repeat it.",
            )
        self.lock(game, "board", source.sourceRepresentativeSha256, target.positionIndex)
        prior = self.latest(game, source.sourceRepresentativeSha256, target.positionIndex)
        now = datetime.now(UTC)
        require_content_bounds(source, command.cells)
        annotation = ContentRevision(
            source=source,
            reference=BoardContentReference(
                gameId=game,
                sourceRepresentativeSha256=source.sourceRepresentativeSha256,
                positionIndex=target.positionIndex,
                revision=1 if prior is None else prior.revision + 1,
                humanApproved=True,
                cells=command.cells,
            ),
            sequenceNumber=target.sequenceNumber,
            origin="manual_blind",
            actor=actor,
            approvedBy=actor,
            approvedAt=now,
            recordedAt=now,
            sessionId=identifier,
            passNumber=command.passNumber,
            measuredNodes=command.measuredNodes,
        )
        oracle = self.measure_oracle(row, annotation) if command.passNumber == 2 else None
        saved = self.append(annotation, oracle=oracle)
        row.progress = {**row.progress, row.phase: {**row.progress[row.phase], key: saved.revision}}
        row.revision += 1
        self.session.flush()
        return self.receipt(
            game,
            command.idempotencyKey,
            payload,
            {"idempotencyKey": str(command.idempotencyKey), "session": self.session_status(row)},
        )

    def pass_references(self, row: Measurement, number: int) -> list[ContentRevision]:
        values = []
        for key, revision in row.progress[f"pass{number}"].items():
            pixel, position = key.split(":")
            saved = self.session.get(Revision, (row.game_id, pixel, int(position), revision))
            if saved is None or digest(saved.document) != saved.document_sha256:
                raise ContentError(
                    "CONTENT_REFERENCE_UNAVAILABLE", "A retained content reference is unavailable."
                )
            annotation = ContentRevision.model_validate(saved.document)
            if annotation.sessionId != row.id or annotation.passNumber != number:
                raise ContentError(
                    "CONTENT_BLIND_PROVENANCE_CONFLICT", "A pass references another session."
                )
            values.append(annotation)
        return values

    def measure_oracle(self, row: Measurement, annotation: ContentRevision) -> dict[str, Any]:
        from game_predictor_worker.images.grid_cell_content_reference import (
            run_blind_content_oracle,
        )
        from game_predictor_worker.images.grid_cohort_dataset import GridCohortDatasetError

        from game_predictor_api.domain.image_geometry_v2 import ImageGeometryContractError

        snapshot = self.snapshot(row.game_id, row.cohort_id, row.document["manifestSha256"])
        ref = annotation.reference
        key = f"{ref.sourceRepresentativeSha256}:{ref.positionIndex}"
        frozen = next(
            (s for s in snapshot.sources() if s["sourceId"] == str(annotation.source.sourceId)),
            None,
        )
        if frozen is None:
            raise ContentError("CONTENT_ORACLE_SOURCE_MISSING", "The immutable source is missing.")
        try:
            frame = snapshot.frame(frozen, frozen["role"], validation_purpose="A")
            return run_blind_content_oracle(frame, annotation, row.document["oracleContexts"][key])
        except (ImageGeometryContractError, GridCohortDatasetError) as error:
            # The independent human label survives a renderer/data availability
            # failure. It cannot authorize automatic qualification.
            body = {
                "version": "production-cell-content-oracle-v1",
                "state": "render_contract_blocked",
                "reasonCode": error.code,
                "contentReferenceSha256": annotation.sha256,
            }
            return {**body, "sha256": digest(body)}

    def advance(
        self, game: UUID, identifier: UUID, command: ContentSessionAdvance, actor: str
    ) -> dict[str, Any]:
        payload = {
            "kind": "advance",
            "sessionId": str(identifier),
            "actor": actor,
            "body": command.model_dump(mode="json"),
        }
        if replay := self.begin_command(game, command.idempotencyKey, payload, actor):
            return replay
        row = self.measurement(game, identifier, lock=True)
        if row.revision != command.expectedSessionRevision or row.phase == "frozen":
            raise ContentError(
                "CONTENT_SESSION_REVISION_CONFLICT", "Reload the current blind session."
            )
        targets = [ContentTarget.model_validate(t) for t in row.document["targets"]]
        if len(row.progress[row.phase]) != len(targets):
            raise ContentError(
                "CONTENT_PASS_INCOMPLETE", "Every selected board needs a blind measurement."
            )
        self.snapshot(game, row.cohort_id, row.document["manifestSha256"])
        for target in targets:
            if self.current_source(game, target.source.sourceId, lock=True) != target.source:
                raise ContentError("CONTENT_SOURCE_IDENTITY_CONFLICT", "The frozen source changed.")
        if row.phase == "pass1":
            row.phase = "pass2"
        else:
            first, second = self.pass_references(row, 1), self.pass_references(row, 2)
            contract = row.document.get("evaluationContract")
            if contract is not None:
                from .grid_content_oracle_context import require_current_evaluation_contract

                require_current_evaluation_contract(self.session, self.root, game, contract)
            report = repeatability_report(targets, first, second, [game])
            if report["state"] != "ready":
                error = ContentError(
                    "CONTENT_REPEATABILITY_NOT_READY",
                    "Correct the labels in a new blind session; tolerances cannot grow.",
                )
                error.report = report
                raise error
            for reference in second:
                ref = reference.reference
                self.lock(game, "board", ref.sourceRepresentativeSha256, ref.positionIndex)
                current = self.latest(game, ref.sourceRepresentativeSha256, ref.positionIndex)
                if current is None or current.document_sha256 != reference.sha256:
                    raise ContentError(
                        "CONTENT_REFERENCE_STALE",
                        "A newer label exists; the old blind result cannot be frozen.",
                    )
            oracle_rows = []
            for reference in second:
                ref = reference.reference
                saved = self.session.get(
                    Revision,
                    (game, ref.sourceRepresentativeSha256, ref.positionIndex, ref.revision),
                )
                assert saved is not None
                oracle = saved.oracle
                if (
                    oracle is None
                    or oracle.get("contentReferenceSha256") != reference.sha256
                    or oracle.get("sha256")
                    != digest({k: v for k, v in oracle.items() if k != "sha256"})
                ):
                    raise ContentError(
                        "CONTENT_ORACLE_RECEIPT_MISSING",
                        "The second-pass oracle receipt is incomplete.",
                    )
                oracle_rows.append(
                    {
                        "contentReferenceSha256": reference.sha256,
                        "oracleSha256": oracle["sha256"],
                        "state": oracle["state"],
                    }
                )
                if contract is not None and (
                    oracle.get("state") == "render_contract_blocked"
                    and oracle.get("reasonCode") is not None
                    and "renderConfiguration" not in oracle
                ):
                    raise ContentError(
                        "CONTENT_ORACLE_RENDER_UNAVAILABLE",
                        f"Oracle could not render this input: {oracle['reasonCode']}",
                    )
                if contract is not None and (
                    oracle.get("renderConfiguration") != contract["renderConfiguration"]
                    or oracle.get("classifierSnapshotSha256")
                    != digest(
                        {
                            "classifier": contract["classifier"],
                            "renderConfiguration": contract["renderConfiguration"],
                        }
                    )
                ):
                    raise ContentError(
                        "CONTENT_ORACLE_CONTRACT_CHANGED",
                        "Oracle render differs from this session.",
                    )
            qualification = oracle_qualification([o["state"] for o in oracle_rows])
            oracle_summary = {k: v for k, v in qualification.items() if k != "qualificationState"}
            oracle_summary["referencesSha256"] = digest(oracle_rows)
            body = {
                **{k: v for k, v in report.items() if k != "sha256"},
                "oracle": oracle_summary,
                "qualificationState": qualification["qualificationState"],
                **({"evaluationContract": contract} if contract is not None else {}),
            }
            row.report, row.phase = {**body, "sha256": digest(body)}, "frozen"
        row.revision += 1
        self.session.flush()
        return self.receipt(
            game,
            command.idempotencyKey,
            payload,
            {"idempotencyKey": str(command.idempotencyKey), "session": self.session_status(row)},
        )
