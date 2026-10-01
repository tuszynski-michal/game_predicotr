"""Cell render specifications read from board render manifests (D-467 S7, TASK-0792).

``image_symbol_review_cells.render_spec`` duplicates, per cell, the
``renderSpec`` that ``board_render_manifests`` already stores once per board
revision.  Every runtime reader that needs a cell's full render specification
(preview/atlas, symbol reference candidates, training cohorts, manual
geometry configuration, rollout validation, evaluation scripts) resolves it
here from the manifest of ``(recognized_board_id, geometry_revision)``.  The
cell keeps only ``render_spec_checksum_sha256`` and its identity keys; the
column itself is removed by TASK-0793.

Rules (fail closed, no silent substitution):

- the cell's ``(board, geometry revision)`` has no manifest row:
  ``IMAGE_REVIEW_RENDER_MANIFEST_MISSING`` (a renderable cell always has one,
  TASK-0757 rule "no manifest <=> no renderable cells");
- the manifest has no entry (or more than one) for the cell index:
  ``IMAGE_REVIEW_RENDER_SPEC_MISSING``;
- the entry's declared ``renderSpecChecksumSha256`` or the canonical checksum
  of its ``renderSpec`` differs from the cell's ``render_spec_checksum_sha256``:
  ``IMAGE_REVIEW_RENDER_SPEC_MISMATCH``.

Reads are batched: one statement per chunk of requested cells, expanding only
the requested manifest entries server-side, never one query per cell and never
whole manifests to the client.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, cast
from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.image_reviews import ImageReviewConflictError

RENDER_MANIFEST_MISSING: Final = "IMAGE_REVIEW_RENDER_MANIFEST_MISSING"
RENDER_SPEC_MISSING: Final = "IMAGE_REVIEW_RENDER_SPEC_MISSING"
RENDER_SPEC_MISMATCH: Final = "IMAGE_REVIEW_RENDER_SPEC_MISMATCH"

# One statement expands at most this many requested cells.  The atlas asks
# for <= 100 cells, a training inventory for a few thousand.
_CHUNK_SIZE: Final = 2_000

ManifestSchema = Literal["game_data_v2"]

_STATEMENT_TEMPLATE: Final = """
WITH wanted AS (
  SELECT *
  FROM unnest(
    CAST(:board_ids AS uuid[]),
    CAST(:revisions AS integer[]),
    CAST(:cell_indices AS integer[])
  ) AS w(recognized_board_id, geometry_revision, cell_index)
)
SELECT w.recognized_board_id AS recognized_board_id,
       w.geometry_revision AS geometry_revision,
       w.cell_index AS cell_index,
       m.recognized_board_id IS NOT NULL AS manifest_present,
       entry.value AS manifest_cell
FROM wanted w
LEFT JOIN {table} m
  ON m.game_id = :game_id
 AND m.recognized_board_id = w.recognized_board_id
 AND m.geometry_revision = w.geometry_revision
LEFT JOIN LATERAL (
  SELECT x AS value
  FROM jsonb_array_elements(m.cells -> 'cells') AS x
  WHERE x -> 'cellIndex' = to_jsonb(w.cell_index)
) entry ON true
"""
_TABLES: Final[dict[ManifestSchema | None, str]] = {
    None: "board_render_manifests",
    "game_data_v2": "game_data_v2.board_render_manifests",
}


class CellRenderSpecError(ImageReviewConflictError):
    """A cell's render specification is not available from its manifest."""

    def __init__(self, code: str, message: str, *, key: CellRenderSpecKey) -> None:
        super().__init__(
            code,
            message,
            details={
                "recognizedBoardId": str(key.recognized_board_id),
                "geometryRevision": key.geometry_revision,
                "cellIndex": key.cell_index,
            },
        )
        self.key = key


@dataclass(frozen=True, slots=True)
class CellRenderSpecKey:
    """The persisted render identity of one review cell."""

    recognized_board_id: UUID
    geometry_revision: int
    cell_index: int
    render_spec_checksum_sha256: str

    @property
    def location(self) -> tuple[UUID, int, int]:
        return (self.recognized_board_id, self.geometry_revision, self.cell_index)


def verified_cell_render_spec(
    key: CellRenderSpecKey,
    *,
    manifest_present: bool,
    manifest_cells: Sequence[object],
) -> Mapping[str, object]:
    """Return the manifest ``renderSpec`` of one cell after the checksum checks.

    ``manifest_cells`` are the manifest entries whose ``cellIndex`` equals the
    key's index (normally exactly one).
    """

    if not manifest_present:
        raise CellRenderSpecError(
            RENDER_MANIFEST_MISSING,
            "The virtual cell has no render manifest for its geometry revision.",
            key=key,
        )
    if len(manifest_cells) != 1 or not isinstance(manifest_cells[0], Mapping):
        raise CellRenderSpecError(
            RENDER_SPEC_MISSING,
            "The render manifest has no unique entry for the virtual cell.",
            key=key,
        )
    entry = cast(Mapping[str, object], manifest_cells[0])
    render_spec = entry.get("renderSpec")
    if not isinstance(render_spec, Mapping):
        raise CellRenderSpecError(
            RENDER_SPEC_MISSING,
            "The render manifest entry of the virtual cell has no render specification.",
            key=key,
        )
    if entry.get("renderSpecChecksumSha256") != key.render_spec_checksum_sha256:
        raise CellRenderSpecError(
            RENDER_SPEC_MISMATCH,
            "The render manifest entry belongs to another render of the virtual cell.",
            key=key,
        )
    spec = cast(Mapping[str, object], render_spec)
    if sha256_canonical_json(spec) != key.render_spec_checksum_sha256:
        raise CellRenderSpecError(
            RENDER_SPEC_MISMATCH,
            "The manifest render specification differs from the cell render checksum.",
            key=key,
        )
    return spec


def load_cell_render_specs(
    connection: Session | Connection,
    *,
    game_id: UUID,
    keys: Iterable[CellRenderSpecKey],
    schema: ManifestSchema | None = None,
) -> dict[CellRenderSpecKey, Mapping[str, object]]:
    """Resolve every key to its checksum-verified manifest ``renderSpec``.

    ``schema=None`` reads the store the session is bound to (search path set by
    the game storage router); scripts on a plain connection pass
    ``"game_data_v2"``.  ``game_id`` keeps the read on the manifest primary
    key and one partition.  Any missing manifest, missing entry or checksum
    mismatch raises :class:`CellRenderSpecError`.
    """

    unique = tuple(dict.fromkeys(keys))
    if not unique:
        return {}
    statement = text(_STATEMENT_TEMPLATE.format(table=_TABLES[schema]))
    by_location: dict[tuple[UUID, int, int], list[CellRenderSpecKey]] = {}
    for key in unique:
        by_location.setdefault(key.location, []).append(key)
    locations = tuple(by_location)
    result: dict[CellRenderSpecKey, Mapping[str, object]] = {}
    for start in range(0, len(locations), _CHUNK_SIZE):
        chunk = locations[start : start + _CHUNK_SIZE]
        present: dict[tuple[UUID, int, int], bool] = {}
        entries: dict[tuple[UUID, int, int], list[object]] = {}
        rows = connection.execute(
            statement,
            {
                "game_id": game_id,
                "board_ids": [location[0] for location in chunk],
                "revisions": [location[1] for location in chunk],
                "cell_indices": [location[2] for location in chunk],
            },
        ).mappings()
        for row in rows:
            location = (
                _uuid(row["recognized_board_id"]),
                int(row["geometry_revision"]),
                int(row["cell_index"]),
            )
            present[location] = bool(row["manifest_present"])
            cell = row["manifest_cell"]
            if cell is not None:
                entries.setdefault(location, []).append(cell)
        for location in chunk:
            for key in by_location[location]:
                result[key] = verified_cell_render_spec(
                    key,
                    manifest_present=present.get(location, False),
                    manifest_cells=entries.get(location, ()),
                )
    return result


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


__all__ = [
    "RENDER_MANIFEST_MISSING",
    "RENDER_SPEC_MISMATCH",
    "RENDER_SPEC_MISSING",
    "CellRenderSpecError",
    "CellRenderSpecKey",
    "load_cell_render_specs",
    "verified_cell_render_spec",
]
