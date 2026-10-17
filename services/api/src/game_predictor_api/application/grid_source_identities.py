"""Explicit bounded canonical metadata completion, without import lease impersonation."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import text

from game_predictor_api.domain.grid_training_cohorts import GridCohortError, digest, target_fence
from game_predictor_api.domain.source_canonical_metadata import (
    SourceCanonicalMetadata,
    compare_source_metadata,
)
from game_predictor_api.storage.grid_quality_observations import (
    current_targets,
    own_target,
    read_source,
)
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from game_predictor_api.storage.grid_training_cohort_models import GridSourceIdentityCommandModel
from game_predictor_api.storage.grid_training_cohort_repository import (
    CohortDeadline,
    SqlAlchemyGridTrainingCohortRepository,
)
from game_predictor_api.storage.sequence_ownership_lock import acquire_sequence_ownership_lock


def complete(
    repo: SqlAlchemyGridTrainingCohortRepository,
    assets: GridCohortArtifactStore,
    game: UUID,
    body: dict[str, Any],
    actor: str,
) -> dict[str, Any]:
    deadline = CohortDeadline()
    repo.bind(game)
    if not 1 <= len(body["sources"]) <= 5 or len(
        {item["sourceId"] for item in body["sources"]}
    ) != len(body["sources"]):
        raise GridCohortError(
            "SOURCE_IDENTITY_SELECTION_INVALID", "Select one to five distinct sources.", 422
        )
    if replay := repo.identity_replay(game, body):
        return replay
    expected: dict[str, SourceCanonicalMetadata] = {}
    for item in body["sources"]:
        deadline.check()
        source = read_source(repo.session, game, UUID(item["sourceId"]))
        if source is None or source["checksum_sha256"] != item["expectedSourceSha256"]:
            raise GridCohortError(
                "SOURCE_IDENTITY_CONFLICT", "The selected source identity changed."
            )
        frame, content = assets.decode_source(source)
        identity = frame.source
        expected[item["sourceId"]] = SourceCanonicalMetadata(
            frame.raw_width,
            frame.raw_height,
            identity.width,
            identity.height,
            identity.exif_orientation,
            identity.coordinate_space,
            identity.normalization_adapter_version,
            identity.normalized_pixel_checksum_sha256,
        )
        del frame, content
    repo.bind(game, write=True)
    repo.key_lock(game, "complete_identities", body["idempotencyKey"])
    if replay := repo.identity_replay(game, body):
        return replay
    acquire_sequence_ownership_lock(repo.session, game_id=game)
    results = []
    for item in sorted(body["sources"], key=lambda value: value["sourceId"]):
        deadline.check(repo.session)
        source_id = UUID(item["sourceId"])
        repo.session.execute(
            text("SELECT id FROM source_images WHERE game_id=:game AND id=:source FOR UPDATE"),
            {"game": game, "source": source_id},
        )
        source = read_source(repo.session, game, source_id)
        revision = repo.session.execute(
            text(
                "SELECT to_jsonb(r) FROM image_source_geometry_revisions r "
                "WHERE game_id=:game AND source_image_id=:source "
                "AND id=CAST(:revision AS uuid)"
            ),
            {
                "game": game,
                "source": source_id,
                "revision": item["expectedSourceGeometryRevisionId"],
            },
        ).scalar_one_or_none()
        canonical = expected[item["sourceId"]]
        if (
            source is None
            or source["checksum_sha256"] != item["expectedSourceSha256"]
            or not revision
            or revision["status"] == "reverted"
            or revision["geometry_checksum_sha256"] != item["expectedGeometrySha256"]
            or revision["source_checksum_sha256"] != source["checksum_sha256"]
            or any(
                revision[key] != canonical.to_dict()[key]
                for key in (
                    "normalized_pixel_checksum_sha256",
                    "normalization_adapter_version",
                    "oriented_width",
                    "oriented_height",
                    "coordinate_space",
                )
            )
        ):
            raise GridCohortError(
                "SOURCE_GEOMETRY_IDENTITY_UNRESOLVED",
                "The exact existing geometry identity cannot be verified.",
            )
        # Ownership and the source row remain locked through metadata/receipt
        # commit. A retained historical revision alone is not a current target.
        if not any(
            own_target(target)
            and not target_fence(target)["rejected"]
            and str(target["board"].get("source_geometry_revision_id"))
            == item["expectedSourceGeometryRevisionId"]
            for target in current_targets(repo.session, game, source_id).values()
        ):
            raise GridCohortError(
                "SOURCE_GEOMETRY_IDENTITY_UNRESOLVED",
                "The exact geometry revision is not referenced by a current own target.",
            )
        comparison = compare_source_metadata(
            SourceCanonicalMetadata.from_mapping(source), canonical
        )
        if comparison == "conflict":
            raise GridCohortError(
                "SOURCE_METADATA_CONFLICT", "Existing canonical metadata differs."
            )
        if comparison == "complete":
            values = canonical.to_dict()
            repo.session.execute(
                text(
                    "UPDATE source_images SET "
                    + ",".join(f"{key}=:{key}" for key in values)
                    + " WHERE game_id=:game AND id=:source"
                ),
                {**values, "game": game, "source": source_id},
            )
        results.append(
            {
                "sourceId": str(source_id),
                "outcome": "completed" if comparison == "complete" else "already_complete",
            }
        )
    response = {
        "receipt": {
            "idempotencyKey": body["idempotencyKey"],
            "kind": "complete_identities",
            "outcome": "completed",
            "results": results,
        }
    }
    repo.session.add(
        GridSourceIdentityCommandModel(
            game_id=game,
            idempotency_key=UUID(body["idempotencyKey"]),
            command_sha256=digest(body),
            document={"command": body, "response": response, "actor": actor},
        )
    )
    repo.session.flush()
    return response
