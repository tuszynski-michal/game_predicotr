"""One per-board render manifest for virtual cells (D-467, TASK-0757).

A manifest document has exactly the shape of
``image_board_geometry_revisions.virtual_render_spec``: an object with a
``cells`` array whose entries carry ``cellIndex`` and ``renderSpec`` plus the
checksummed cell identities.  Revision-0 manifests are built from the import
cell payload (or, for the backfill, from ``cell_observations``); revisions
above zero are exact copies of the geometry revision's ``virtual_render_spec``.

The manifest checksum is ``sha256(canonical_json(document))``.  For a copied
geometry revision it therefore equals ``virtual_render_spec_checksum_sha256``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes

BOARD_RENDER_MANIFEST_SCHEMA_VERSION: Final = "board-render-manifest-observations-v1"
BOARD_RENDER_MANIFEST_ASSET_MODE: Final = "virtual_source"
_SHA256: Final = re.compile(r"^[0-9a-f]{64}$")


class BoardRenderManifestError(ValueError):
    """Stable, fail-closed manifest validation failure."""

    def __init__(self, code: str, message: str, *, cell_index: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.cell_index = cell_index


@dataclass(frozen=True, slots=True)
class ObservedRenderCell:
    """One virtual cell identity as persisted by the import (observation shape)."""

    cell_index: int
    render_spec: Mapping[str, object]
    render_spec_checksum_sha256: str
    rendered_pixel_checksum_sha256: str
    logical_cell_key: str
    logical_cell_key_v2: str | None
    render_identity_v2_sha256: str | None


@dataclass(frozen=True, slots=True)
class BoardRenderManifest:
    """A validated manifest document ready to persist for one board revision."""

    recognized_board_id: UUID
    geometry_revision: int
    document: Mapping[str, object]
    checksum_sha256: str
    cell_count: int


def sha256_canonical_json(value: object) -> str:
    """The checksum used for render specs, render manifests and geometry revisions."""

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def crop_sample_id(*, recognized_board_id: UUID, render_spec_checksum_sha256: str) -> str:
    """Identical to the virtual review cell sample identity (image_review_repository)."""

    return sha256_canonical_json(
        {
            "assetMode": BOARD_RENDER_MANIFEST_ASSET_MODE,
            "recognizedBoardId": str(recognized_board_id),
            "renderSpecChecksumSha256": render_spec_checksum_sha256,
        }
    )


def build_observation_render_manifest(
    *,
    recognized_board_id: UUID,
    cells: Sequence[ObservedRenderCell],
    expected_cell_indices: frozenset[int] | None = None,
) -> BoardRenderManifest:
    """Build the revision-0 manifest and verify every cell render-spec checksum.

    A missing, duplicated or unexpected cell, or a render spec whose canonical
    checksum differs from the persisted one, rejects the whole board.
    """

    if not cells:
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_EMPTY", "A render manifest needs at least one cell."
        )
    by_index: dict[int, ObservedRenderCell] = {}
    for cell in cells:
        if isinstance(cell.cell_index, bool) or cell.cell_index < 0:
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_CELL_INDEX_INVALID",
                "A render manifest cell index is invalid.",
                cell_index=cell.cell_index,
            )
        if cell.cell_index in by_index:
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_CELL_DUPLICATE",
                "A render manifest cell index is duplicated.",
                cell_index=cell.cell_index,
            )
        by_index[cell.cell_index] = cell
    if expected_cell_indices is not None and set(by_index) != expected_cell_indices:
        missing = sorted(expected_cell_indices - set(by_index))
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_CELLS_INCOMPLETE",
            "The board cells do not match its declared availability mask.",
            cell_index=missing[0] if missing else None,
        )
    entries: list[dict[str, object]] = []
    for index in sorted(by_index):
        cell = by_index[index]
        _require_cell_identity(cell)
        entries.append(
            {
                "cellIndex": index,
                "cropSampleId": crop_sample_id(
                    recognized_board_id=recognized_board_id,
                    render_spec_checksum_sha256=cell.render_spec_checksum_sha256,
                ),
                "logicalCellKeySha256": cell.logical_cell_key,
                "logicalCellKeyV2Sha256": cell.logical_cell_key_v2,
                "renderIdentityV2Sha256": cell.render_identity_v2_sha256,
                "renderSpec": dict(cell.render_spec),
                "renderSpecChecksumSha256": cell.render_spec_checksum_sha256,
                "renderedPixelChecksumSha256": cell.rendered_pixel_checksum_sha256,
            }
        )
    document: dict[str, object] = {
        "assetMode": BOARD_RENDER_MANIFEST_ASSET_MODE,
        "cells": entries,
        "schemaVersion": BOARD_RENDER_MANIFEST_SCHEMA_VERSION,
    }
    return BoardRenderManifest(
        recognized_board_id=recognized_board_id,
        geometry_revision=0,
        document=document,
        checksum_sha256=sha256_canonical_json(document),
        cell_count=len(entries),
    )


def revision_render_manifest(
    *,
    recognized_board_id: UUID,
    geometry_revision: int,
    virtual_render_spec: Mapping[str, object],
    virtual_render_spec_checksum_sha256: str,
) -> BoardRenderManifest:
    """Copy one virtual geometry revision's render spec verbatim, after verification."""

    if geometry_revision <= 0:
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_REVISION_INVALID",
            "A geometry revision manifest requires a positive revision.",
        )
    document = dict(virtual_render_spec)
    checksum = sha256_canonical_json(document)
    if checksum != virtual_render_spec_checksum_sha256:
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_REVISION_CHECKSUM_MISMATCH",
            "The geometry revision render spec differs from its persisted checksum.",
        )
    cell_count = validate_render_manifest_document(document)
    return BoardRenderManifest(
        recognized_board_id=recognized_board_id,
        geometry_revision=geometry_revision,
        document=document,
        checksum_sha256=checksum,
        cell_count=cell_count,
    )


def validate_render_manifest_document(document: Mapping[str, object]) -> int:
    """Validate the shared ``{"cells": [{"cellIndex", "renderSpec", ...}]}`` shape.

    Returns the number of cells.  A per-cell ``renderSpecChecksumSha256``, when
    present, must equal the canonical checksum of that cell's ``renderSpec``.
    """

    raw_cells = document.get("cells")
    if not isinstance(raw_cells, list) or not raw_cells:
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_SHAPE_INVALID",
            "A render manifest needs a non-empty cells array.",
        )
    seen: set[int] = set()
    for raw in raw_cells:
        index = raw.get("cellIndex") if isinstance(raw, Mapping) else None
        if not isinstance(raw, Mapping) or not isinstance(index, int) or isinstance(index, bool):
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_SHAPE_INVALID", "A render manifest cell is invalid."
            )
        if index < 0 or index in seen:
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_CELL_INDEX_INVALID",
                "A render manifest cell index is invalid or duplicated.",
                cell_index=index,
            )
        seen.add(index)
        render_spec = raw.get("renderSpec")
        if not isinstance(render_spec, Mapping):
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_SHAPE_INVALID",
                "A render manifest cell has no render spec.",
                cell_index=index,
            )
        declared = raw.get("renderSpecChecksumSha256")
        if declared is not None and declared != sha256_canonical_json(render_spec):
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_CELL_CHECKSUM_MISMATCH",
                "A render manifest cell differs from its render-spec checksum.",
                cell_index=index,
            )
    return len(raw_cells)


def _require_cell_identity(cell: ObservedRenderCell) -> None:
    if not isinstance(cell.render_spec, Mapping):
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_RENDER_SPEC_MISSING",
            "A virtual cell has no render spec.",
            cell_index=cell.cell_index,
        )
    for value in (
        cell.render_spec_checksum_sha256,
        cell.rendered_pixel_checksum_sha256,
        cell.logical_cell_key,
    ):
        if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
            raise BoardRenderManifestError(
                "BOARD_RENDER_MANIFEST_CELL_IDENTITY_INVALID",
                "A virtual cell identity checksum is invalid.",
                cell_index=cell.cell_index,
            )
    if (cell.logical_cell_key_v2 is None) != (cell.render_identity_v2_sha256 is None):
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_CELL_IDENTITY_INVALID",
            "A virtual cell v2 identity is incomplete.",
            cell_index=cell.cell_index,
        )
    if sha256_canonical_json(dict(cell.render_spec)) != cell.render_spec_checksum_sha256:
        raise BoardRenderManifestError(
            "BOARD_RENDER_MANIFEST_CELL_CHECKSUM_MISMATCH",
            "A virtual cell render spec differs from its persisted checksum.",
            cell_index=cell.cell_index,
        )


__all__ = [
    "BOARD_RENDER_MANIFEST_ASSET_MODE",
    "BOARD_RENDER_MANIFEST_SCHEMA_VERSION",
    "BoardRenderManifest",
    "BoardRenderManifestError",
    "ObservedRenderCell",
    "build_observation_render_manifest",
    "crop_sample_id",
    "revision_render_manifest",
    "sha256_canonical_json",
    "validate_render_manifest_document",
]
