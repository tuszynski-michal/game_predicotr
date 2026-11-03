"""Own-game metadata adapter for exact correction splitting, without image I/O."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from typing import Any
from uuid import UUID

from sqlalchemy import text

from game_predictor_api.domain.grid_correction_policy import CORRECTION_POLICY
from game_predictor_api.domain.grid_correction_split import (
    CorrectionSplitError,
    CorrectionSplitSource,
    correction_data_availability,
    solve_correction_split,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest
from game_predictor_api.storage.grid_training_cohort_evidence import GridCohortEvidenceReader

CORRECTIONS_POLICY = CORRECTION_POLICY


class GridCorrectionSplitPreparationError(GridCohortError):
    """Keep measured solver counts through the existing cohort error boundary."""

    def __init__(self, error: CorrectionSplitError) -> None:
        super().__init__(
            error.code, f"{error} Available photos: {error.photos}; boards: {error.boards}."
        )
        self.data_availability: dict[str, int | str] | None = None
        if error.code in {"GRID_CORRECTION_SPLIT_MINIMA", "GRID_CORRECTION_SPLIT_INFEASIBLE"}:
            self.data_availability = correction_data_availability(
                error.photos,
                error.boards,
                "minima" if error.code == "GRID_CORRECTION_SPLIT_MINIMA" else "infeasible",
            )


def population(repo: Any, game: UUID, imports: list[str]) -> list[dict[str, Any]]:
    """The complete import population, including unlabelled buffer candidates."""
    rows = list(
        repo.session.execute(
            text("""
      SELECT to_jsonb(s) source, f.source_relative_path logical_name,
       EXISTS(SELECT 1 FROM recognized_boards b WHERE b.game_id=s.game_id
        AND b.source_image_id=s.id AND b.approved_geometry_revision=b.geometry_revision
        AND b.geometry_approved_by IS NOT NULL AND b.geometry_approved_at IS NOT NULL
        AND b.geometry_approved_by NOT LIKE 'system:%'
        AND b.geometry_approved_by NOT LIKE 'worker:%') approved
      FROM source_images s LEFT JOIN image_import_job_files f
       ON f.game_id=s.game_id AND f.job_id=s.import_job_id
       AND f.file_execution_key=s.file_execution_key
      WHERE s.game_id=:game AND s.import_job_id=ANY(CAST(:imports AS uuid[]))
      ORDER BY s.id LIMIT 5001"""),
            {"game": game, "imports": imports},
        ).mappings()
    )
    if len(rows) > 5000:
        raise GridCohortError(
            "GRID_CORRECTION_POPULATION_LIMIT",
            "The complete population exceeds 5000 sources; no subset was used.",
        )
    if {r["source"]["import_job_id"] for r in rows} != set(imports):
        raise GridCohortError("GRID_COHORT_SELECTION_UNAVAILABLE", "An import has no own sources.")
    revisions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    bindings: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for row in repo.session.execute(
        text("""
      SELECT b.source_image_id,b.position_index,b.sequence_number,
       r.id revision_id,r.status,r.sequence_range_start,r.sequence_range_end,
       r.active_board_slots,r.sequence_attestation_checksum_sha256,
       r.source_checksum_sha256,r.normalized_pixel_checksum_sha256,
       r.normalization_adapter_version,r.oriented_width,r.oriented_height,r.coordinate_space
      FROM recognized_boards b JOIN source_images s
       ON s.game_id=b.game_id AND s.id=b.source_image_id
      LEFT JOIN image_source_geometry_revisions r
       ON r.game_id=b.game_id AND r.source_image_id=b.source_image_id
       AND r.id=b.source_geometry_revision_id
      WHERE b.game_id=:game AND s.import_job_id=ANY(CAST(:imports AS uuid[]))
      ORDER BY b.source_image_id,b.position_index"""),
        {"game": game, "imports": imports},
    ).mappings():
        key = str(row["source_image_id"])
        revisions[key].append(
            {
                k: str(v) if isinstance(v, UUID) else v
                for k, v in row.items()
                if k not in ("source_image_id", "position_index", "sequence_number")
            }
        )
        bindings[key].append((row["position_index"], row["sequence_number"]))
    return [
        {
            "source": r["source"],
            "logicalName": r["logical_name"] or "",
            "approved": r["approved"],
            "revisions": revisions[r["source"]["id"]],
            "bindings": bindings[r["source"]["id"]],
        }
        for r in rows
    ]


def population_sha(rows: list[dict[str, Any]]) -> str:
    """Only identity/order facts; symbol edits and unrelated status are not chronology."""
    return digest(
        [
            {
                "source": {
                    k: row["source"].get(k)
                    for k in (
                        "id",
                        "import_job_id",
                        "checksum_sha256",
                        "normalized_pixel_checksum_sha256",
                        "relative_path",
                        "oriented_width",
                        "oriented_height",
                        "coordinate_space",
                        "normalization_adapter_version",
                    )
                },
                "logicalName": row["logicalName"],
                "attestations": [
                    {
                        **{k: v for k, v in revision.items() if k not in ("revision_id", "status")},
                        "active": bool(revision["revision_id"])
                        and revision["status"] != "reverted",
                    }
                    for revision in row["revisions"]
                ],
                "bindings": row["bindings"],
            }
            for row in rows
        ]
    )


def contexts(repo: Any, game: UUID, ids: list[str]) -> dict[str, dict[str, Any]]:
    result = {}
    for offset in range(0, len(ids), 200):
        values = repo.session.scalar(
            text("SELECT public.recording_photo_context_v1(:game,CAST(:ids AS uuid[]))"),
            {"game": game, "ids": ids[offset : offset + 200]},
        )
        result.update({item["sourceId"]: item for item in values})
    if set(result) != set(ids):
        raise GridCohortError("GRID_CORRECTION_CONTEXT_MISSING", "Source registry context differs.")
    return result


def prepare_split(repo: Any, game: UUID, imports: list[str], deadline: Any) -> dict[str, Any]:
    rows = population(repo, game, imports)
    metadata = contexts(repo, game, [r["source"]["id"] for r in rows])
    reader = GridCohortEvidenceReader(repo.session, repo.artifact_root)
    sources, pins = [], []
    for index, row in enumerate(rows):
        deadline.check(repo.session)
        source, revs = row["source"], row["revisions"]
        key = source["id"]
        if not source.get("normalized_pixel_checksum_sha256"):
            raise GridCohortError(
                "SOURCE_METADATA_MISSING", "Complete canonical identities before splitting imports."
            )
        valid = bool(revs) and all(
            r["revision_id"]
            and r["status"] != "reverted"
            and r["source_checksum_sha256"] == source["checksum_sha256"]
            and all(
                r[k] == source[k]
                for k in (
                    "normalized_pixel_checksum_sha256",
                    "normalization_adapter_version",
                    "oriented_width",
                    "oriented_height",
                    "coordinate_space",
                )
            )
            for r in revs
        )
        order_fields = (
            "sequence_range_start",
            "sequence_range_end",
            "active_board_slots",
            "sequence_attestation_checksum_sha256",
        )
        valid = valid and all(all(r[k] == revs[0][k] for k in order_fields) for r in revs)
        first = revs[0] if valid else {}
        count = 0
        if row["approved"]:
            measured = reader.capture(
                game,
                UUID(key),
                index,
                {"role": "TRAIN", "qualification": "eligible", "reasonCodes": []},
                "grid-only",
            )
            count = measured["boardEligibleCount"]
        context = metadata[key]
        roles = context["priorRoles"]
        sources.append(
            CorrectionSplitSource(
                source_id=key,
                import_id=source["import_job_id"],
                byte_sha256=source["checksum_sha256"],
                pixel_sha256=source["normalized_pixel_checksum_sha256"],
                logical_filename=row["logicalName"],
                eligible_boards=count,
                attested_start=first.get("sequence_range_start"),
                attested_end=first.get("sequence_range_end"),
                attested_slots=tuple(first.get("active_board_slots") or ()),
                attestation_checksum_sha256=first.get("sequence_attestation_checksum_sha256"),
                board_bindings=tuple(row["bindings"]),
                component_ids=tuple(context["componentIds"]),
                allowed_roles=frozenset(context["allowedRoles"]),
                frozen_role=roles[0]
                if len(roles) == 1 and roles[0] in context["allowedRoles"]
                else None,
                frozen_buffer=roles == ["BUFFER"],
            )
        )
        pins.append(
            {
                "sourceId": key,
                "importId": source["import_job_id"],
                "sourceSha256": source["checksum_sha256"],
                "pixelSha256": source["normalized_pixel_checksum_sha256"],
                "registryProofSha256": context["proofSha256"],
                "componentIds": context["componentIds"],
                "eligibleBoards": count,
                "rangeStart": first.get("sequence_range_start"),
                "rangeEnd": first.get("sequence_range_end"),
            }
        )
    try:
        solved = solve_correction_split(sources)
    except CorrectionSplitError as error:
        raise GridCorrectionSplitPreparationError(error) from error
    assignments = dict(solved.assignments)
    buffers = set(solved.buffers)
    representatives = set(solved.representative_sources)
    for pin in pins:
        pin.update(
            role=assignments[pin["sourceId"]],
            buffer=pin["sourceId"] in buffers,
            representative=pin["sourceId"] in representatives,
        )
    result = {
        "schemaVersion": solved.schema_version,
        "solverVersion": solved.solver_version,
        "sources": pins,
        "importIds": imports,
        "populationSha256": population_sha(rows),
        "importOrders": [asdict(order) for order in solved.import_orders],
        "roleCounts": [asdict(count) for count in solved.role_counts],
        "evidenceLevel": "photo-only",
        "limitations": list(solved.limitations),
        "objective": [solved.objective_numerator, solved.objective_denominator],
    }
    return {**result, "sha256": digest(result)}


def validate_population(repo: Any, game: UUID, split: dict[str, Any]) -> None:
    if population_sha(population(repo, game, split["importIds"])) != split["populationSha256"]:
        raise GridCohortError(
            "GRID_CORRECTION_POPULATION_CHANGED",
            "Source population or attested order changed; create a new preview.",
        )


def split_mapping(split: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item["sourceId"]: {
            "sourceId": item["sourceId"],
            "role": item["role"],
            "groupId": None,
            "photoIdentity": item["sourceSha256"],
            "evidenceLevel": "photo-only",
            "qualification": "eligible"
            if item["role"] is not None and item["representative"]
            else "blocked",
            "reasonCodes": ["GRID_CORRECTION_BUFFER"]
            if item["buffer"]
            else ["GRID_CORRECTION_EXACT_ALIAS"]
            if not item["representative"]
            else [],
            "splitSha256": split["sha256"],
            "expectedBoardCount": item["eligibleBoards"],
        }
        for item in split["sources"]
    }
