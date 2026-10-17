"""Exact current human label proofs; descriptive model judgments are never labels."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.grid_training_cohorts import (
    GridCohortError,
    digest,
    exact_lattice,
    target_fence,
)
from game_predictor_api.domain.image_geometry_v2 import (
    ImageGeometryContractError,
    NormalizedSourceImage,
)
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
from game_predictor_api.storage.grid_quality_manifest import GridQualityManifestStore
from game_predictor_api.storage.grid_quality_observations import (
    current_targets,
    geometry_approval_fence,
    own_target,
    read_source,
)
from game_predictor_api.storage.grid_quality_repoint import unchanged_frozen_target
from game_predictor_api.storage.grid_reinference import source_fence
from game_predictor_api.storage.models import JobModel
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
)


def normalized_source(source: dict[str, Any]) -> NormalizedSourceImage:
    try:
        return NormalizedSourceImage(
            source_checksum_sha256=source["checksum_sha256"],
            normalized_pixel_checksum_sha256=source["normalized_pixel_checksum_sha256"],
            width=source["oriented_width"],
            height=source["oriented_height"],
            exif_orientation=source["exif_orientation"],
            normalization_adapter_version=source["normalization_adapter_version"],
            coordinate_space=source["coordinate_space"],
        )
    except (ImageGeometryContractError, TypeError) as error:
        raise GridCohortError(
            "SOURCE_METADATA_MISSING", "Canonical source metadata is unresolved."
        ) from error


def _approval_projection(fence: dict[str, Any]) -> dict[str, Any]:
    """Remove only symbol workflow facts, retaining geometry/owner/issue fences."""
    result = copy.deepcopy(fence)
    result["board"]["status"] = None
    result["review"] = {
        "id": result["review"].get("id"),
        "status": None,
        "resolution_revision": None,
    }
    result["cells"] = []
    result["renders"] = []
    return result


def unchanged_approved_target(
    session: Session,
    game: UUID,
    source: UUID,
    old: dict[str, Any],
    target: dict[str, Any],
    *,
    render_proof: dict[str, Any],
    source_row: dict[str, Any],
) -> bool:
    """Use the real publication verifier without coupling geometry to symbol choices."""
    if old.get("issues") or target_fence(target)["issues"]:
        return False
    try:
        _, cells = exact_lattice(
            target["board"]["board_geometry"],
            source_row["oriented_width"],
            source_row["oriented_height"],
        )
        rendered = GridCohortEvidenceReader(session, Path(".")).render(
            game, source_row, target, cells
        )
        if any(rendered[key] != render_proof[key] for key in ("configuration", "cellQuads")):
            return False
    except (GridCohortError, KeyError, TypeError):
        return False
    projected = _approval_projection(old)
    current = copy.deepcopy(target)
    current["board"]["status"] = None
    current["review"] = {
        "id": (current.get("review") or {}).get("id"),
        "status": None,
        "resolution_revision": None,
    }
    current["cells"] = []
    current["renders"] = []
    return unchanged_frozen_target(session, game, source, projected, current)


class GridCohortEvidenceReader:
    def __init__(self, session: Session, artifact_root: Path) -> None:
        self.session = session
        self.manifests = GridQualityManifestStore(artifact_root)
        self.cached_manifest: tuple[str, dict[str, Any]] | None = None

    def _row(self, sql: str, **parameters: Any) -> dict[str, Any] | None:
        return self.session.execute(text(sql), parameters).scalar_one_or_none()

    def _measurement(self, path: str, sha: str) -> dict[str, Any]:
        if self.cached_manifest and self.cached_manifest[0] == sha:
            return self.cached_manifest[1]
        source = self.manifests.root / path
        if source.stat().st_size > 128 * 1024 * 1024:
            raise GridCohortError(
                "APPROVAL_MANIFEST_LIMIT", "Approval evidence exceeds its metadata bound."
            )
        self.manifests.verify(path, sha)
        with source.open(encoding="utf-8") as stream:
            value = json.load(stream)
        self.cached_manifest = (sha, value)
        return cast(dict[str, Any], value)

    def approval(self, game: UUID, source: UUID, target: dict[str, Any]) -> dict[str, Any]:
        board = target["board"]
        revision = board["geometry_revision"]
        if (
            board.get("approved_geometry_revision") != revision
            or not board.get("geometry_approved_by")
            or not board.get("geometry_approved_at")
        ):
            raise GridCohortError(
                "HUMAN_APPROVAL_REQUIRED", "The current geometry requires human approval."
            )
        if str(board["geometry_approved_by"]).startswith(("system:", "worker:")):
            raise GridCohortError(
                "HUMAN_APPROVAL_REQUIRED", "Automatic acceptance is not a human label."
            )
        event = self._row(
            """SELECT CASE WHEN count(*) OVER ()=1 THEN to_jsonb(e) END
          FROM image_board_geometry_review_events e
          WHERE e.game_id=:game AND e.recognized_board_id=CAST(:board AS uuid)
          AND e.review_item_id=CAST(:review AS uuid) AND e.geometry_revision=:revision
          AND e.approved_geometry_revision=:revision AND e.actor=:actor
          AND e.created_at=CAST(:at AS timestamptz) AND e.action IN ('approved','geometry_saved')
          LIMIT 1""",
            game=game,
            board=board["id"],
            review=target["review"]["id"],
            revision=revision,
            actor=board["geometry_approved_by"],
            at=board["geometry_approved_at"],
        )
        if not event:
            raise GridCohortError(
                "APPROVAL_PROVENANCE_UNRESOLVED",
                "The actual current approval event is unavailable.",
            )
        manual = self._row(
            """SELECT to_jsonb(r) FROM image_board_geometry_revisions r
          JOIN image_board_geometry_review_events e ON e.game_id=r.game_id
          AND e.recognized_board_id=r.recognized_board_id AND e.review_item_id=r.review_item_id
          AND e.geometry_revision=r.revision AND e.action='geometry_saved'
          AND e.actor=r.corrected_by
          AND e.board_checksum_sha256=r.geometry_checksum_sha256
          WHERE r.game_id=:game AND r.recognized_board_id=CAST(:board AS uuid)
          AND r.revision=:revision
          AND r.source_geometry_revision_id=CAST(:source_revision AS uuid)
          AND r.geometry_checksum_sha256=:sha AND r.asset_mode='virtual_source' LIMIT 1""",
            game=game,
            board=board["id"],
            revision=revision,
            source_revision=board["source_geometry_revision_id"],
            sha=board["geometry_checksum_sha256"],
        )
        if event["action"] == "geometry_saved" and not manual:
            raise GridCohortError(
                "APPROVAL_PROVENANCE_UNRESOLVED", "The guarded manual save is unavailable."
            )
        if event["action"] == "approved":
            stored = self._row(
                """SELECT CASE WHEN count(*) OVER ()=1 THEN to_jsonb(c) END
              FROM grid_geometry_approval_commands c
              WHERE c.game_id=:game AND c.review_item_id=CAST(:review AS uuid)
              AND c.document->'receipt'->>'eventId'=:event LIMIT 1""",
                game=game,
                review=target["review"]["id"],
                event=event["id"],
            )
            if not stored:
                # A complete guarded manual lineage can prove the same current
                # target even when a later legacy approval lacks a measurement.
                if (
                    not manual
                    or event["board_checksum_sha256"] != board["geometry_checksum_sha256"]
                ):
                    raise GridCohortError(
                        "APPROVAL_PROVENANCE_UNRESOLVED",
                        "The exact approval command is unavailable.",
                    )
            else:
                command, receipt = stored["document"]["command"], stored["document"]["receipt"]
                header = self._row(
                    "SELECT to_jsonb(m) FROM grid_quality_measurements m "
                    "WHERE m.game_id=:game AND m.id=CAST(:id AS uuid)",
                    game=game,
                    id=command["measurementId"],
                )
                if not header or header["manifest_sha256"] != command["manifestSha256"]:
                    raise GridCohortError(
                        "APPROVAL_PROVENANCE_UNRESOLVED", "Approval manifest binding differs."
                    )
                manifest = self._measurement(header["manifest_path"], header["manifest_sha256"])
                members = [
                    member
                    for member in manifest["members"]
                    if member["sourceId"] == str(source)
                    and member["sampleKind"] == command["sampleKind"]
                ]
                if len(members) != 1:
                    raise GridCohortError(
                        "APPROVAL_PROVENANCE_UNRESOLVED", "Approval source membership differs."
                    )
                frozen = members[0]["positions"][command["positionIndex"]]
                current_source = read_source(self.session, game, source)
                if current_source is None:
                    raise GridCohortError(
                        "APPROVAL_PROVENANCE_UNRESOLVED", "The current source is unavailable."
                    )
                _, old_cells = exact_lattice(
                    frozen["targetFence"]["board"]["board_geometry"],
                    current_source["oriented_width"],
                    current_source["oriented_height"],
                )
                old_render = self.render(game, current_source, frozen["targetFence"], old_cells)
                if (
                    receipt["eventId"] != event["id"]
                    or receipt["boardId"] != board["id"]
                    or receipt["geometryRevision"] != revision
                    or receipt["actor"] != event["actor"]
                    or receipt["geometryChecksumSha256"] != event["board_checksum_sha256"]
                    or frozen["targetSha256"] != command["targetSha256"]
                    or frozen["reviewItemId"] != target["review"]["id"]
                    or source_fence(members[0]["source"])
                    != source_fence(read_source(self.session, game, source) or {})
                    or not unchanged_approved_target(
                        self.session,
                        game,
                        source,
                        frozen["targetFence"],
                        target,
                        render_proof=old_render,
                        source_row=current_source,
                    )
                ):
                    raise GridCohortError(
                        "APPROVAL_PROVENANCE_UNRESOLVED",
                        "The exact approved target no longer matches.",
                    )
        return {
            "origin": "human_corrected" if manual else "human_checked_unchanged",
            "basis": "guarded_manual_save" if manual else "canonical_approval_receipt",
            "eventId": event["id"],
            "actor": event["actor"],
            "at": event["created_at"],
            "geometryRevision": revision,
            "weight": 4 if manual else 1,
            "manualRevisionId": manual["id"] if manual else None,
        }

    def render(
        self, game: UUID, source: dict[str, Any], target: dict[str, Any], cells: list[Any]
    ) -> dict[str, Any]:
        configurations = []
        for row in target.get("renders", []):
            document = row.get("cells") or {}
            entries = document.get("cells", []) if isinstance(document, dict) else []
            if len(entries) != 15 or {cell["cellIndex"] for cell in entries} != set(range(15)):
                raise GridCohortError(
                    "RENDER_PROVENANCE_UNRESOLVED", "The stored render manifest is incomplete."
                )
            for entry in entries:
                spec = entry["renderSpec"]
                if (
                    sha256_canonical_json(spec) != entry["renderSpecChecksumSha256"]
                    or spec.get("sourceQuad") != cells[entry["cellIndex"]]
                ):
                    raise GridCohortError(
                        "RENDER_PROVENANCE_UNRESOLVED",
                        "Stored render geometry differs from the exact lattice.",
                    )
                configurations.append(spec.get("configuration"))
        if not configurations:
            job = self.session.get(JobModel, UUID(source["import_job_id"]))
            if job is None:
                raise GridCohortError(
                    "RENDER_PROVENANCE_UNRESOLVED", "The pinned rendering context is unavailable."
                )
            try:
                configuration = SqlAlchemyVirtualGridGeometryRepository(
                    self.session
                )._pending_render_configuration(
                    source_image_id=UUID(source["id"]), import_job_id=job.id, job=job
                )
            except ImageGridReviewError as error:
                raise GridCohortError("RENDER_PROVENANCE_UNRESOLVED", str(error)) from error
            configurations = [configuration.to_dict()]
        if not all(
            isinstance(configuration, dict) and configuration == configurations[0]
            for configuration in configurations
        ):
            raise GridCohortError(
                "RENDER_PROVENANCE_UNRESOLVED", "The rendering configuration is inconsistent."
            )
        return {
            "configuration": configurations[0],
            "cellQuads": cells,
            "basis": "exact_lattice",
            "existingManifest": bool(target.get("renders")),
        }

    def capture(
        self, game: UUID, source_id: UUID, ordinal: int, recording: dict[str, Any], mode: str
    ) -> dict[str, Any]:
        source = read_source(self.session, game, source_id)
        if source is None:
            raise GridCohortError(
                "GRID_COHORT_SOURCE_REMOVED", "The selected source is no longer available."
            )
        metadata_missing = False
        try:
            identity = normalized_source(source)
        except GridCohortError:
            identity, metadata_missing = None, True
        targets = current_targets(self.session, game, source_id)
        positions, reasons = [], set(recording.get("reasonCodes", []))
        for index in range(9):
            target = targets.get(index)
            label, reason = None, None
            if not target or not target.get("board"):
                reason = "GEOMETRY_TARGET_MISSING"
            elif identity is None:
                reason = "SOURCE_METADATA_MISSING"
            else:
                board = target["board"]
                qualification = board.get("geometry_qualification") or {}
                try:
                    if not own_target(target) or target_fence(target)["rejected"]:
                        raise GridCohortError(
                            "CURRENT_OWNER_UNAVAILABLE", "The target owner is unavailable."
                        )
                    if (
                        board.get("completeness_status") != "complete"
                        or board.get("unavailable_cell_indices")
                        or qualification.get("excludeFromGeometryTraining")
                    ):
                        raise GridCohortError(
                            "PARTIAL_OR_EXCLUDED_TARGET",
                            "Partial or excluded labels are not pilot targets.",
                        )
                    if (
                        target_fence(target)["issues"]
                        or board.get("grid_rows") != 3
                        or board.get("grid_columns") != 5
                    ):
                        raise GridCohortError(
                            "GRID_ISSUE_OR_TOPOLOGY", "A full issue-free 3 by 5 target is required."
                        )
                    revision = self._row(
                        "SELECT to_jsonb(r) FROM image_source_geometry_revisions r "
                        "WHERE r.game_id=:game AND r.source_image_id=:source "
                        "AND r.id=CAST(:id AS uuid)",
                        game=game,
                        source=source_id,
                        id=board["source_geometry_revision_id"],
                    )
                    if (
                        not revision
                        or revision["status"] == "reverted"
                        or revision["geometry_checksum_sha256"] != board["geometry_checksum_sha256"]
                        or any(
                            revision[key] != source[key]
                            for key in (
                                "normalized_pixel_checksum_sha256",
                                "normalization_adapter_version",
                                "oriented_width",
                                "oriented_height",
                                "coordinate_space",
                            )
                        )
                        or revision["source_checksum_sha256"] != source["checksum_sha256"]
                    ):
                        raise GridCohortError(
                            "SOURCE_GEOMETRY_IDENTITY_UNRESOLVED",
                            "The current geometry source identity differs.",
                        )
                    geometry = board.get("board_geometry") or {}
                    nodes, cells = exact_lattice(geometry, identity.width, identity.height)
                    slot = [
                        entry
                        for entry in revision["board_geometries"]
                        if entry.get("positionIndex") == index
                    ]
                    if (
                        len(slot) != 1
                        or slot[0].get("sequenceNumber") != board["sequence_number"]
                        or slot[0].get("latticeNodes") != nodes
                    ):
                        raise GridCohortError(
                            "CURRENT_GEOMETRY_BINDING_CHANGED",
                            "The stored slot and exact nodes differ.",
                        )
                    proof = self.approval(game, source_id, target)
                    label = {
                        "positionIndex": index,
                        "sequenceNumber": board["sequence_number"],
                        "boardId": board["id"],
                        "reviewItemId": target["review"]["id"],
                        "nodes": nodes,
                        "approval": proof,
                        "render": self.render(game, source, target, cells),
                        "targetFence": target_fence(target),
                        "approvalFence": _approval_projection(geometry_approval_fence(target)),
                    }
                except GridCohortError as error:
                    reason = error.code
            if reason:
                reasons.add(reason)
            positions.append({"positionIndex": index, "label": label, "reason": reason})
        boards = sum(position["label"] is not None for position in positions)
        full = boards == 9
        if not full:
            reasons.add("PHOTO_NOT_FULLY_ANNOTATED")
        role = recording.get("role")
        ready = recording.get("qualification") == "eligible" and boards > 0 and role is not None
        used = ready and (full or (role == "TRAIN" and mode == "grid-only"))
        if not used and ready:
            reasons.add("FULL_PHOTO_REQUIRED_FOR_ROLE")
        return {
            "dependencyCellIds": [
                cell["id"] for target in targets.values() for cell in target.get("cells", [])
            ],
            "sourceId": str(source_id),
            "ordinal": ordinal,
            "role": role,
            "used": used,
            "source": source,
            "sourceFence": source_fence(source),
            "recording": recording,
            "positions": positions,
            "reasons": sorted(reasons),
            "metadataMissing": metadata_missing,
            "qualification": "eligible" if used else "unresolved",
            "boardEligibleCount": boards if ready else 0,
            "screenEligible": full and ready,
            "captureSha256": digest(
                {"source": source_fence(source), "positions": positions, "recording": recording}
            ),
        }
