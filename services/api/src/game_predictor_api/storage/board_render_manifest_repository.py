"""Write-side persistence for per-board render manifests (D-467, TASK-0757).

Writers call this inside the transaction that already writes the board's cell
observations or virtual geometry revision.  Readers still use the existing
sources until TASK-0758 switches them to this table.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from game_predictor_api.domain.board_render_manifests import (
    BOARD_RENDER_MANIFEST_ASSET_MODE,
    BoardRenderManifest,
)
from game_predictor_api.storage.models import BoardRenderManifestModel


class BoardRenderManifestConflictError(RuntimeError):
    """An immutable manifest already exists with different content."""

    code = "BOARD_RENDER_MANIFEST_CONFLICT"

    def __init__(self, recognized_board_id: UUID, geometry_revision: int) -> None:
        super().__init__(
            "A board render manifest already exists with a different checksum or provenance."
        )
        self.recognized_board_id = recognized_board_id
        self.geometry_revision = geometry_revision


def add_board_render_manifest(
    session: Session,
    *,
    game_id: UUID,
    manifest: BoardRenderManifest,
    source_geometry_revision_id: UUID,
    extractor_version: str,
) -> BoardRenderManifestModel:
    """Add a manifest for a board revision that is new in this transaction."""

    record = BoardRenderManifestModel(
        game_id=game_id,
        recognized_board_id=manifest.recognized_board_id,
        geometry_revision=manifest.geometry_revision,
        asset_mode=BOARD_RENDER_MANIFEST_ASSET_MODE,
        source_geometry_revision_id=source_geometry_revision_id,
        extractor_version=extractor_version,
        cells=dict(manifest.document),
        manifest_checksum_sha256=manifest.checksum_sha256,
    )
    session.add(record)
    return record


def ensure_board_render_manifest(
    session: Session,
    *,
    game_id: UUID,
    manifest: BoardRenderManifest,
    source_geometry_revision_id: UUID,
    extractor_version: str,
) -> bool:
    """Idempotently add a manifest; an existing row must match exactly.

    Returns ``True`` when a new row was added.
    """

    existing = session.get(
        BoardRenderManifestModel,
        (game_id, manifest.recognized_board_id, manifest.geometry_revision),
    )
    if existing is None:
        add_board_render_manifest(
            session,
            game_id=game_id,
            manifest=manifest,
            source_geometry_revision_id=source_geometry_revision_id,
            extractor_version=extractor_version,
        )
        return True
    if (
        existing.manifest_checksum_sha256 != manifest.checksum_sha256
        or existing.source_geometry_revision_id != source_geometry_revision_id
        or existing.extractor_version != extractor_version
    ):
        raise BoardRenderManifestConflictError(
            manifest.recognized_board_id, manifest.geometry_revision
        )
    return False


__all__ = [
    "BoardRenderManifestConflictError",
    "add_board_render_manifest",
    "ensure_board_render_manifest",
]
