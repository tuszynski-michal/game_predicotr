"""Pin existing import classifier/render provenance; never infer a default classifier."""

from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_render_reference import (
    CONTRACT_VERSION,
    execution_context,
    require_evaluation_contract,
)
from game_predictor_api.domain.grid_training_cohorts import digest
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot


def resolve_evaluation_contract(session: Session, root: Path, game: UUID) -> dict[str, Any]:
    from .production_cell_reference import current_render_configuration
    from .symbol_model_snapshot_resolver import SqlAlchemySymbolModelSnapshotResolver

    try:
        model = SqlAlchemySymbolModelSnapshotResolver(session, artifact_root=root).resolve(
            game_id=game
        )
    except JobConflictError as error:
        raise ContentError(error.code, str(error)) from error
    configuration = current_render_configuration(session, root, game, model=model)
    body = {
        "version": CONTRACT_VERSION,
        "gameId": str(game),
        "classifier": model.to_payload(),
        "renderConfiguration": configuration,
        "renderConfigurationSha256": digest(configuration),
    }
    result = {**body, "sha256": digest(body)}
    require_evaluation_contract(result, str(game))
    return result


def require_current_evaluation_contract(
    session: Session, root: Path, game: UUID, contract: dict[str, Any]
) -> None:
    from .production_cell_reference import current_render_configuration

    require_evaluation_contract(contract, str(game))
    try:
        current = current_render_configuration(session, root, game)
    except JobConflictError as error:
        raise ContentError(error.code, str(error)) from error
    if digest(current) != contract["renderConfigurationSha256"]:
        raise ContentError(
            "CONTENT_RENDER_CONFIGURATION_CHANGED", "Start a new measurement for this crop."
        )


def capture_oracle_context(
    session: Session,
    game: UUID,
    source: dict[str, Any],
    target: dict[str, Any],
    *,
    evaluation_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if evaluation_contract is not None:
        require_evaluation_contract(evaluation_contract, str(game))
        return execution_context(
            capture_oracle_context(session, game, source, target), evaluation_contract
        )
    revision_id = target["targetFence"]["board"]["source_geometry_revision_id"]
    geometry = session.execute(
        text("""SELECT to_jsonb(r) FROM image_source_geometry_revisions r
        WHERE game_id=:g AND id=CAST(:r AS uuid) AND source_image_id=CAST(:s AS uuid)"""),
        {"g": game, "r": revision_id, "s": source["id"]},
    ).scalar_one_or_none()
    job = session.execute(
        text("SELECT input_payload FROM jobs WHERE game_id=:g AND id=CAST(:j AS uuid)"),
        {"g": game, "j": source["import_job_id"]},
    ).scalar_one_or_none()
    if geometry is None or not isinstance(job, dict):
        return {"state": "unavailable", "reasonCode": "CONTENT_ORACLE_PROVENANCE_MISSING"}
    try:
        model = SymbolModelJobSnapshot.from_payload(job.get("symbol_model"))
    except (ValueError, TypeError):
        return {"state": "unavailable", "reasonCode": "CONTENT_ORACLE_CLASSIFIER_MISSING"}
    configuration = target["render"]["configuration"]
    if (
        configuration["outputWidth"] != model.crop_output_size
        or configuration["outputHeight"] != model.crop_output_size
        or configuration["paddingFraction"] != model.crop_padding_fraction
    ):
        return {"state": "unavailable", "reasonCode": "CONTENT_ORACLE_CLASSIFIER_RENDER_CONFLICT"}
    return {
        "state": "available",
        "classifier": model.to_payload(),
        "renderConfiguration": configuration,
        "topologyRulesVersionId": geometry["topology_rules_version_id"],
        "sequenceRangeStart": geometry["sequence_range_start"],
        "sequenceRangeEnd": geometry["sequence_range_end"],
        "importJobId": source["import_job_id"],
        "fileExecutionKey": source["file_execution_key"],
    }
