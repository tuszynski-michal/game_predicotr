"""Read-only, bounded staging/duplicate/manual-draft audit for one game."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.jobs import JobConflictError
from game_predictor_api.storage.board_cell_geometry_pending_repository import (
    _manual_draft_from_source_revision,
    _validated_detected_board_geometry,
)
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def audit(game_id: UUID) -> dict[str, object]:
    settings = ApiSettings.from_environment()
    engine = create_engine(
        settings.database_url,
        connect_args={
            "connect_timeout": 5,
            "options": "-c statement_timeout=15000 -c default_transaction_read_only=on",
        },
    )
    with Session(engine) as session:
        GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
        params = {"game": game_id}
        imports = (
            session.execute(
                text("""
            SELECT job.id, job.status, job.input_payload->>'source_selection_id' staging,
                   job.input_payload->>'source_display_name' name,
                   retention.board_import_status staging_board_import_status,
                   job.input_payload->'page_geometry_manifest' manifest
            FROM public.jobs AS job
            LEFT JOIN browser_selection_retention_states AS retention
              ON retention.upload_id = (job.input_payload->>'source_selection_id')::uuid
            WHERE job.game_id=:game AND job.job_type='import'
              AND job.input_payload->>'import_kind'='image_directory'
            ORDER BY job.created_at, job.id LIMIT 1000
        """),
                params,
            )
            .mappings()
            .all()
        )
        summaries = []
        for job in imports:
            descriptor = job["manifest"]
            content = (settings.artifact_root / descriptor["relativePath"]).read_bytes()
            if hashlib.sha256(content).hexdigest() != descriptor["checksumSha256"]:
                raise ValueError("Pinned geometry manifest checksum mismatch")
            manifest = json.loads(content)
            summaries.append(
                {
                    "jobId": str(job["id"]),
                    "staging": job["staging"],
                    "name": job["name"],
                    "status": job["status"],
                    "stagingBoardImportStatus": job["staging_board_import_status"],
                    "deferredWholeSources": manifest["reviewRequiredSourceCount"],
                }
            )
        duplicates = (
            session.execute(
                text("""
            SELECT count(*) groups, coalesce(sum(n-1),0) extras FROM (
              SELECT s.checksum_sha256,b.position_index,count(*) n
              FROM recognized_boards b JOIN source_images s ON s.id=b.source_image_id
              WHERE s.game_id=:game GROUP BY s.checksum_sha256,b.position_index
              HAVING count(*)>1
            ) d
        """),
                params,
            )
            .mappings()
            .one()
        )
        canonical_duplicates = session.execute(
            text("""
            SELECT count(*) FROM (
              SELECT sequence_number FROM image_sequence_canonical WHERE game_id=:game
              GROUP BY sequence_number HAVING count(*)>1
            ) d
        """),
            params,
        ).scalar_one()
        pending = (
            session.execute(
                text("""
            SELECT p.id,p.import_job_id,p.source_relative_path,s.width,s.height,
                   p.position_index,p.sequence_number,
                   p.processing_manifest_relative_path,
                   d.result_payload->'boards'->p.position_index->'geometry' geometry,
                   r.board_geometries->p.position_index draft
            FROM image_board_geometry_pending p
            JOIN source_images s ON s.id=p.source_image_id
            LEFT JOIN public.image_pipeline_stage_results d
              ON d.file_execution_key=s.file_execution_key AND d.stage='board_detection'
            LEFT JOIN image_source_geometry_revisions r
              ON r.source_image_id=s.id AND r.revision=0
              AND r.source_checksum_sha256=p.source_checksum_sha256
            WHERE p.game_id=:game AND p.status='pending' LIMIT 20000
        """),
                params,
            )
            .mappings()
            .all()
        )
        counts: dict[str, int] = {}
        invalid = []
        missing = []
        for row in pending:
            key = str(row["import_job_id"])
            counts[key] = counts.get(key, 0) + 1
            geometry = row["geometry"]
            try:
                if isinstance(geometry, dict) and geometry.get("quad") is None:
                    geometry = _manual_draft_from_source_revision(
                        [row["draft"]],
                        position_index=row["position_index"],
                        sequence_number=row["sequence_number"],
                    )
                _validated_detected_board_geometry(
                    geometry, source_width=row["width"], source_height=row["height"]
                )
            except JobConflictError as error:
                invalid.append({"id": str(row["id"]), "error": str(error)})
            source = settings.artifact_root / "data" / row["source_relative_path"]
            manifest_path = settings.artifact_root / row["processing_manifest_relative_path"]
            if not source.is_file() or not manifest_path.is_file():
                missing.append(str(row["id"]))
        session.rollback()
    engine.dispose()
    return {
        "gameId": str(game_id),
        "readOnly": True,
        "imports": summaries,
        "duplicateBoardGroups": int(duplicates["groups"]),
        "extraBoards": int(duplicates["extras"]),
        "duplicateCanonicalNumbers": canonical_duplicates,
        "pendingByImport": counts,
        "pendingCount": len(pending),
        "invalidDrafts": invalid,
        "invalidDraftCount": len(invalid),
        "missingAssets": missing,
        "missingAssetCount": len(missing),
        "limitReached": len(imports) == 1000 or len(pending) == 20000,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-id", type=UUID, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.game_id)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        json.dumps(
            {
                key: value
                for key, value in result.items()
                if key not in {"imports", "pendingByImport", "invalidDrafts", "missingAssets"}
            }
        )
    )
