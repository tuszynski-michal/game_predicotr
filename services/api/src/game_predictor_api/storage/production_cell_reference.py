"""Freeze renderer provenance and measured uncertainty for new content cohorts only."""

from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import ContentRevision
from game_predictor_api.domain.grid_render_reference import (
    REFERENCE_V2,
    execution_context,
    require_reference_v2,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot

from .grid_cell_content_models import GridCellContentSessionModel
from .grid_content_oracle_context import capture_oracle_context

REFERENCE_VERSION = "production-cell-evaluation-reference-v1"


@contextmanager
def production_reference_reader(session: Session, game: UUID) -> Iterator[Session]:
    """A catalogue/other-game transaction must never be rebound while reading evidence."""
    from .game_storage_routing import GameStorageIntent, GameStorageRouter, game_storage_scope

    bind = session.get_bind()
    engine = bind.engine if isinstance(bind, Connection) else bind
    with game_storage_scope(game), Session(bind=engine) as reader, reader.begin():
        if reader.get_bind().dialect.name == "postgresql":
            reader.execute(text("SET TRANSACTION READ ONLY"))
        GameStorageRouter().bind(reader, game, intent=GameStorageIntent.READ)
        yield reader


def capture_production_reference(
    session: Session,
    game: UUID,
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    evaluation_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """No live defaults, predicted labels or inferred tolerances enter this pin."""
    provenance = capture_oracle_context(session, game, source, target)
    is_a = "blindGeometry" in target
    context = provenance
    if evaluation_contract is not None and (is_a or provenance.get("state") == "available"):
        context = execution_context(provenance, evaluation_contract)
    measurement = None
    if "contentAnnotation" in target and (evaluation_contract is None or is_a):
        annotation = ContentRevision.model_validate(target["contentAnnotation"])
        if annotation.sessionId is not None and annotation.passNumber == 2:
            row = session.get(GridCellContentSessionModel, (game, annotation.sessionId))
            if row is not None and row.phase == "frozen" and row.report is not None:
                measurement = {
                    "sessionId": str(row.id),
                    "report": deepcopy(row.report),
                }
    body: dict[str, Any] = {
        "version": REFERENCE_VERSION,
        "sourceContext": context,
        "sourceContextSha256": digest(context),
        "measurement": measurement,
    }
    if evaluation_contract is not None:
        body.update(
            version=REFERENCE_V2,
            evaluationContract=evaluation_contract,
            importProvenance=provenance,
            importProvenanceSha256=digest(provenance),
        )
    result = {**body, "sha256": digest(body)}
    if evaluation_contract is not None:
        require_reference_v2(result, str(game))
    return result


def require_current_production_reference(
    session: Session,
    game: UUID,
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    artifact_root: Path | None = None,
) -> None:
    """Original workflow provenance must still match, independently of content revision."""
    pin = target.get("productionContentReference")
    if pin is not None and pin.get("version") == REFERENCE_V2:
        require_reference_v2(pin, str(game))
        if artifact_root is None:
            raise GridCohortError(
                "CONTENT_ARTIFACT_ROOT_REQUIRED", "The active render must be checked."
            )
        from .grid_content_oracle_context import require_current_evaluation_contract

        require_current_evaluation_contract(session, artifact_root, game, pin["evaluationContract"])
    if (
        pin is not None
        and capture_production_reference(
            session, game, source, target, evaluation_contract=pin.get("evaluationContract")
        )
        != pin
    ):
        raise GridCohortError(
            "CONTENT_RENDER_REFERENCE_CHANGED", "The pinned production rendering context changed."
        )


def current_render_configuration(
    session: Session, root: Path, game: UUID, *, model: SymbolModelJobSnapshot | None = None
) -> dict[str, Any]:
    from game_predictor_worker.images.pipeline_contract import (
        SYMBOL_RGB_PREPROCESSING_VERSION,
        VIRTUAL_CELL_RENDERER_VERSION,
    )
    from game_predictor_worker.images.virtual_cell_extraction import (
        VIRTUAL_CELL_INTERPOLATION_VERSION,
    )

    from game_predictor_api.domain.image_geometry_v2 import DirectCellRenderConfiguration

    from .symbol_model_snapshot_resolver import SqlAlchemySymbolModelSnapshotResolver

    if model is None:
        model = SqlAlchemySymbolModelSnapshotResolver(session, artifact_root=root).resolve(
            game_id=game
        )
    return DirectCellRenderConfiguration(
        extractor_version=VIRTUAL_CELL_RENDERER_VERSION,
        preprocessing_version=SYMBOL_RGB_PREPROCESSING_VERSION,
        interpolation=VIRTUAL_CELL_INTERPOLATION_VERSION,
        output_width=model.crop_output_size,
        output_height=model.crop_output_size,
        padding_fraction=model.crop_padding_fraction,
    ).to_dict()


def require_production_content_freshness(
    session: Session, root: Path | None, report: dict[str, Any]
) -> None:
    """Publication/default/apply bind current crop settings, not classifier weight identity."""
    import hashlib
    import json

    from game_predictor_worker.images.grid_cohort_dataset import GridCohortSnapshot
    from game_predictor_worker.images.grid_model_evaluation_handler import detail_path
    from game_predictor_worker.images.production_cell_input import manifest_input_context
    from game_predictor_worker.images.production_cell_run import ProductionContentRun

    from game_predictor_api.domain.grid_model_registry import GridModelRegistryError
    from game_predictor_api.domain.production_cell_evaluation import REPORT_SCHEMA

    from .game_storage_routing import GameStorageRoutingError
    from .grid_model_registry_models import GridModelVersionModel
    from .grid_training_cohort_models import GridTrainingCohortModel

    if report.get("schemaVersion") != REPORT_SCHEMA:
        return
    try:
        if root is None:
            raise ValueError("CONTENT_ARTIFACT_ROOT_REQUIRED")
        input_contexts = {}
        for name, identifier in (
            ("base", report["baseVersionId"]),
            ("candidate", report["versionId"]),
        ):
            version = session.get(GridModelVersionModel, UUID(identifier))
            if version is None:
                raise ValueError("INPUT_CONTENT_MODEL_CONTEXT_REQUIRED")
            input_contexts[name] = manifest_input_context(root, json.loads(version.manifest_json))
        for evidence in report["contentEvaluation"]:
            game = UUID(evidence["gameId"])
            with production_reference_reader(session, game) as reader:
                pin = next(p for p in report["cohorts"] if p["gameId"] == str(game))
                row = reader.get(GridTrainingCohortModel, (game, UUID(pin["cohortId"])))
                if (
                    row is None
                    or row.status != "frozen"
                    or row.manifest_path is None
                    or row.manifest_sha256 != pin["manifestSha256"]
                ):
                    raise ValueError("CONTENT_FROZEN_COHORT_CHANGED")
                snapshot = GridCohortSnapshot(root, row.manifest_path, row.manifest_sha256)
                run = ProductionContentRun(snapshot)
                expected = digest(current_render_configuration(reader, root, game))
                if set(evidence["renderConfigurationSha256s"]) != {expected}:
                    raise ValueError("CONTENT_RENDER_CONFIGURATION_CHANGED")
                quality = next(g for g in report["rawQuality"]["games"] if g["gameId"] == str(game))
                job_ids = set()
                verified_details = {}
                for role, measured in quality["roles"].items():
                    detail = measured["detail"]
                    path = (root / detail["path"]).resolve()
                    if (
                        not path.is_relative_to((root / "grid-model-evaluations").resolve())
                        or path.stat().st_size > 96 * 1024 * 1024
                    ):
                        raise ValueError("CONTENT_DETAIL_PATH_OR_SIZE")
                    payload = path.read_bytes()
                    if hashlib.sha256(payload).hexdigest() != detail["sha256"]:
                        raise ValueError("CONTENT_DETAIL_CHECKSUM")
                    document = json.loads(payload)
                    if document["gameId"] != str(game) or document["role"] != role:
                        raise ValueError("CONTENT_DETAIL_IDENTITY")
                    job_id = UUID(document["jobId"])
                    if detail["path"] != detail_path(job_id, str(game), role):
                        raise ValueError("CONTENT_DETAIL_CANONICAL_PATH_REQUIRED")
                    job_ids.add(job_id)
                    run.verify_photo_details(
                        role, document["photos"], input_contexts=input_contexts
                    )
                    verified_details[role] = document
                if (
                    len(job_ids) != 1
                    or run.finish(root, next(iter(job_ids)), verified_details=verified_details)
                    != evidence
                ):
                    raise ValueError("CONTENT_REPORT_EVIDENCE_CHANGED")
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        StopIteration,
        GameStorageRoutingError,
    ) as error:
        raise GridModelRegistryError("GRID_MODEL_EVALUATION_STALE", str(error)) from error
