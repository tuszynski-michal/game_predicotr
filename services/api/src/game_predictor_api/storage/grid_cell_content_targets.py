"""Snapshot-bound, source-only metadata for ordinary labels and blind-session setup."""

from __future__ import annotations

from collections.abc import Iterator
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import text

from game_predictor_api.domain.grid_cell_content import ContentError, ContentSource

from .grid_quality_observations import current_targets
from .grid_training_cohort_artifacts import GridCohortArtifactStore

if TYPE_CHECKING:
    from .grid_cell_content import SqlAlchemyGridCellContentRepository

_UNRESOLVED_SOURCE_CODES = {
    "CONTENT_SOURCE_UNAVAILABLE",
    "CONTENT_SOURCE_RETIRED",
    "CONTENT_SOURCE_IDENTITY_UNRESOLVED",
}


def _snapshot(repo: SqlAlchemyGridCellContentRepository, game: UUID, cohort: UUID, sha: str) -> Any:
    snapshot = repo.snapshot(game, cohort, sha)
    manifest = snapshot.manifest
    if manifest["gameId"] != str(game) or manifest["cohortId"] != str(cohort):
        raise ContentError("CONTENT_FROZEN_COHORT_REQUIRED", "The exact scoped cohort is required.")
    return snapshot


def _members(snapshot: Any) -> Iterator[tuple[dict[str, Any], str, dict[str, Any]]]:
    # sources() verifies the manifest purpose pins and metadata checksums without
    # decoding any pixels. Retain its immutable ordinal order, then physical slot.
    for source in snapshot.sources():
        if not source["used"]:
            continue
        role = source.get("validationPurpose") if source["role"] == "VALIDATION" else source["role"]
        if role not in {"TRAIN", "A", "B", "REGRESSION"}:
            raise ContentError("CONTENT_ROLE_CONFLICT", "An exact frozen role is required.")
        for target in sorted(source["targets"], key=lambda value: value["positionIndex"]):
            yield source, role, target


def _display_name(value: str | None) -> str | None:
    # Internal relative_path is storage addressing, never an operator label.
    if value is None:
        return None
    name = value.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name if name and name not in {".", ".."} else None


def _logical_names(
    repo: SqlAlchemyGridCellContentRepository, game: UUID, sources: dict[UUID, ContentSource]
) -> dict[UUID, str | None]:
    """One page-bounded read of the same import name used by correction population."""
    if not sources:
        return {}
    rows = repo.session.execute(
        text("""
        SELECT s.id,s.checksum_sha256,s.normalized_pixel_checksum_sha256,
               f.source_relative_path AS logical_name
        FROM source_images s LEFT JOIN image_import_job_files f
          ON f.game_id=s.game_id AND f.job_id=s.import_job_id
          AND f.file_execution_key=s.file_execution_key
        WHERE s.game_id=:game AND s.id=ANY(CAST(:sources AS uuid[]))
        """),
        {"game": game, "sources": list(sources)},
    ).mappings()
    names = {}
    for row in rows:
        source_id = UUID(str(row["id"]))
        expected = sources.get(source_id)
        if (
            expected is not None
            and row["checksum_sha256"] == expected.sourceSha256
            and row["normalized_pixel_checksum_sha256"] == expected.sourceRepresentativeSha256
        ):
            names[source_id] = _display_name(row["logical_name"])
    return names


def list_targets(
    repo: SqlAlchemyGridCellContentRepository,
    game: UUID,
    cohort: UUID,
    manifest: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    from .grid_cell_content import source_identity

    if not 1 <= limit <= 50 or offset < 0:
        raise ContentError("CONTENT_PAGE_LIMIT", "Choose a valid target page.", 422)
    snapshot = _snapshot(repo, game, cohort, manifest)
    selected = list(islice(_members(snapshot), offset, offset + limit + 1))
    page_sources = {
        UUID(frozen["sourceId"]): source_identity(frozen["sourceIdentity"])
        for frozen, _role, _target in selected[:limit]
    }
    names = _logical_names(repo, game, page_sources)
    items = []
    live: dict[UUID, tuple[str | None, dict[int, dict[str, Any]]]] = {}
    for frozen, role, target in selected[:limit]:
        source = source_identity(frozen["sourceIdentity"])
        if source.sourceId not in live:
            reason, boards = _live_source(repo, game, source)
            live[source.sourceId] = reason, boards
        reason, boards = live[source.sourceId]
        sequence = target.get("sequenceNumber")
        if reason is None:
            if type(sequence) is not int or sequence < 1:
                reason = "CONTENT_SEQUENCE_CONFLICT"
            else:
                try:
                    repo.require_current_board(boards.get(target["positionIndex"]), sequence)
                except ContentError as error:
                    # This helper only raises the writer's two known target conflicts.
                    if error.code not in {
                        "CONTENT_TARGET_UNAVAILABLE",
                        "CONTENT_SEQUENCE_CONFLICT",
                    }:
                        raise
                    reason = error.code
        items.append(
            {
                "source": source.model_dump(mode="json"),
                "displayName": names.get(source.sourceId),
                "positionIndex": target["positionIndex"],
                "sequenceNumber": sequence if reason is None else None,
                "role": role,
                "state": "ready" if reason is None else "unresolved",
                "reasonCodes": [] if reason is None else [reason],
            }
        )
    return {
        "version": "source-cell-content-targets-v1",
        "gameId": str(game),
        "cohortId": str(cohort),
        "manifestSha256": manifest,
        "items": items,
        "nextOffset": offset + limit if len(selected) > limit else None,
    }


def _live_source(
    repo: SqlAlchemyGridCellContentRepository, game: UUID, frozen: ContentSource
) -> tuple[str | None, dict[int, dict[str, Any]]]:
    try:
        source = repo.current_source(game, frozen.sourceId)
    except ContentError as error:
        if error.code not in _UNRESOLVED_SOURCE_CODES:
            raise
        return error.code, {}
    if source != frozen:
        return "CONTENT_SOURCE_IDENTITY_CONFLICT", {}
    return None, current_targets(repo.session, game, frozen.sourceId)


def target_source_asset(
    repo: SqlAlchemyGridCellContentRepository, game: UUID, cohort: UUID, manifest: str, source: UUID
) -> Path:
    snapshot = _snapshot(repo, game, cohort, manifest)
    for frozen, _role, _target in _members(snapshot):
        if frozen["sourceId"] != str(source):
            continue
        pin = frozen["original"]
        identity = frozen["sourceIdentity"]
        if pin["sha256"] != identity["checksum_sha256"]:
            raise ContentError("CONTENT_SOURCE_IDENTITY_CONFLICT", "The original pin differs.")
        # Only this JPEG is read. A live managed crop cannot replace its pixels.
        return GridCohortArtifactStore(repo.root).verify(
            pin["path"], pin["sha256"], size=pin["bytes"]
        )
    raise ContentError("CONTENT_TARGET_UNAVAILABLE", "The source is outside this cohort.", 404)
