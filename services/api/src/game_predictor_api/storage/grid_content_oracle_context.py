"""Pin existing import classifier/render provenance; never infer a default classifier."""

from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.symbol_model_snapshots import SymbolModelJobSnapshot


def capture_oracle_context(
    session: Session, game: UUID, source: dict[str, Any], target: dict[str, Any]
) -> dict[str, Any]:
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
