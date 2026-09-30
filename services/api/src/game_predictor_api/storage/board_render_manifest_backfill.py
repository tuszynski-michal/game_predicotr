"""Resumable backfill of ``board_render_manifests`` for one game (D-467, TASK-0757).

Current virtual board revisions only:

* revision 0: built from ``cell_observations``; every cell render spec must
  match its persisted ``render_spec_checksum_sha256`` and the cells must be
  exactly the board's declared availability mask, otherwise the board is
  refused and reported (the run continues);
* revision > 0: an exact, checksum-verified copy of the current
  ``image_board_geometry_revisions.virtual_render_spec``;
* ``legacy_file`` boards are skipped and counted;
* a board without renderable cells (no observations and an empty
  availability mask, or a geometry revision with ``cells: []``) is skipped
  and counted as ``no_cells_skipped``: no manifest row <=> no cells.

Each batch is one routed write transaction.  Existing manifests are skipped
before any observation is read and inserts use ``ON CONFLICT DO NOTHING``, so
a repeated run is a no-op.  Preview mode issues only ``SELECT`` statements.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from game_predictor_api.domain.board_render_manifests import (
    BoardRenderManifest,
    BoardRenderManifestError,
    ObservedRenderCell,
    build_observation_render_manifest,
    revision_render_manifest,
    sha256_canonical_json,
)
from game_predictor_api.domain.geometry_qualification import available_cell_indices
from game_predictor_api.domain.image_geometry_v2 import canonical_json_bytes
from game_predictor_api.storage.game_storage_routing import GameStorageIntent, GameStorageRouter

DEFAULT_BATCH_SIZE: Final = 500
MAX_BATCH_SIZE: Final = 2000

_BOARDS_SQL = """
SELECT b.id, b.geometry_revision, b.asset_mode, b.grid_rows, b.grid_columns,
       b.unavailable_cell_indices, b.geometry_qualification
FROM game_data_v2.recognized_boards AS b
WHERE b.game_id = :game_id AND (CAST(:after AS uuid) IS NULL OR b.id > CAST(:after AS uuid))
ORDER BY b.id
LIMIT :limit
"""
_EXISTING_SQL = """
SELECT recognized_board_id, geometry_revision
FROM game_data_v2.board_render_manifests
WHERE game_id = :game_id AND recognized_board_id = ANY(CAST(:board_ids AS uuid[]))
"""
_OBSERVATIONS_SQL = """
SELECT recognized_board_id, row_index, column_index, asset_mode, source_geometry_revision_id,
       logical_cell_key, logical_cell_key_v2, render_identity_v2_sha256, render_spec,
       render_spec_checksum_sha256, rendered_pixel_checksum_sha256, extractor_version,
       cropper_version, crop_checksum_sha256
FROM game_data_v2.cell_observations
WHERE game_id = :game_id AND recognized_board_id = ANY(CAST(:board_ids AS uuid[]))
"""
_REVISIONS_SQL = """
SELECT r.recognized_board_id, r.revision, r.asset_mode, r.source_geometry_revision_id,
       r.cropper_version, r.virtual_render_spec, r.virtual_render_spec_checksum_sha256
FROM game_data_v2.image_board_geometry_revisions AS r
JOIN unnest(CAST(:board_ids AS uuid[]), CAST(:revisions AS integer[])) AS wanted(board_id, rev)
  ON wanted.board_id = r.recognized_board_id AND wanted.rev = r.revision
WHERE r.game_id = :game_id
"""
_INSERT_SQL = """
INSERT INTO game_data_v2.board_render_manifests
    (game_id, recognized_board_id, geometry_revision, asset_mode,
     source_geometry_revision_id, extractor_version, cells, manifest_checksum_sha256)
VALUES (:game_id, :board_id, :revision, 'virtual_source', :source_geometry_revision_id,
        :extractor_version, CAST(:cells AS jsonb), :checksum)
ON CONFLICT (game_id, recognized_board_id, geometry_revision) DO NOTHING
"""
_PREVIEW_SQL = """
SELECT
  count(*) AS boards_total,
  count(*) FILTER (WHERE b.asset_mode <> 'virtual_source') AS legacy_boards,
  count(*) FILTER (WHERE b.asset_mode = 'virtual_source' AND b.geometry_revision = 0)
    AS revision_zero_boards,
  count(*) FILTER (WHERE b.asset_mode = 'virtual_source' AND b.geometry_revision = 0
                   AND m.recognized_board_id IS NOT NULL) AS revision_zero_existing,
  count(*) FILTER (WHERE b.asset_mode = 'virtual_source' AND b.geometry_revision > 0)
    AS revision_positive_boards,
  count(*) FILTER (WHERE b.asset_mode = 'virtual_source' AND b.geometry_revision > 0
                   AND m.recognized_board_id IS NOT NULL) AS revision_positive_existing,
  count(*) FILTER (WHERE b.asset_mode = 'virtual_source' AND b.geometry_revision > 0
                   AND (r.id IS NULL OR r.asset_mode <> 'virtual_source'
                        OR r.virtual_render_spec IS NULL)) AS revision_positive_unusable
FROM game_data_v2.recognized_boards AS b
LEFT JOIN game_data_v2.board_render_manifests AS m
  ON m.game_id = b.game_id AND m.recognized_board_id = b.id
 AND m.geometry_revision = b.geometry_revision
LEFT JOIN game_data_v2.image_board_geometry_revisions AS r
  ON r.game_id = b.game_id AND r.recognized_board_id = b.id AND r.revision = b.geometry_revision
WHERE b.game_id = :game_id
"""
_ZERO_WITHOUT_OBSERVATIONS_SQL = """
SELECT count(*) FROM game_data_v2.recognized_boards AS b
WHERE b.game_id = :game_id AND b.asset_mode = 'virtual_source' AND b.geometry_revision = 0
  AND NOT EXISTS (SELECT 1 FROM game_data_v2.cell_observations AS o
                  WHERE o.game_id = b.game_id AND o.recognized_board_id = b.id)
"""


@dataclass(frozen=True, slots=True)
class RefusedBoard:
    recognized_board_id: UUID
    geometry_revision: int
    code: str
    cell_index: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "recognizedBoardId": str(self.recognized_board_id),
            "geometryRevision": self.geometry_revision,
            "code": self.code,
            "cellIndex": self.cell_index,
        }


@dataclass(slots=True)
class BackfillBatchResult:
    last_board_id: UUID | None
    scanned: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    refused: list[RefusedBoard] = field(default_factory=list)
    manifest_bytes: int = 0

    @property
    def exhausted(self) -> bool:
        return self.last_board_id is None


@dataclass(frozen=True, slots=True)
class _Board:
    id: UUID
    geometry_revision: int
    asset_mode: str
    rows: int
    columns: int
    unavailable_cell_indices: tuple[int, ...]
    geometry_qualification: Mapping[str, object] | None


@dataclass(frozen=True, slots=True)
class _NoCells:
    """The board has no renderable cell, so it has no manifest by design."""


@dataclass(frozen=True, slots=True)
class _Prepared:
    manifest: BoardRenderManifest
    source_geometry_revision_id: UUID
    extractor_version: str


def preview_counts(session: Session, game_id: UUID) -> dict[str, int]:
    """Read-only category counts for one game; binds the game store for reading."""

    GameStorageRouter().bind(session, game_id, intent=GameStorageIntent.READ)
    row = session.execute(text(_PREVIEW_SQL), {"game_id": game_id}).mappings().one()
    counts = {key: int(value) for key, value in row.items()}
    counts["revision_zero_to_build"] = (
        counts["revision_zero_boards"] - counts["revision_zero_existing"]
    )
    counts["revision_positive_to_copy"] = (
        counts["revision_positive_boards"]
        - counts["revision_positive_existing"]
        - counts["revision_positive_unusable"]
    )
    counts["revision_zero_without_observations"] = int(
        session.execute(text(_ZERO_WITHOUT_OBSERVATIONS_SQL), {"game_id": game_id}).scalar_one()
    )
    return counts


def run_batch(
    session: Session,
    game_id: UUID,
    *,
    after_board_id: UUID | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    write: bool,
) -> BackfillBatchResult:
    """Process the next ``batch_size`` boards after ``after_board_id``.

    With ``write=False`` the batch is only validated (read-only sampling);
    with ``write=True`` valid manifests are inserted in the caller transaction.
    """

    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    GameStorageRouter().bind(
        session,
        game_id,
        intent=GameStorageIntent.WRITE if write else GameStorageIntent.READ,
    )
    boards = [
        _board_from_row(row)
        for row in session.execute(
            text(_BOARDS_SQL),
            {
                "game_id": game_id,
                "after": None if after_board_id is None else str(after_board_id),
                "limit": batch_size,
            },
        ).mappings()
    ]
    result = BackfillBatchResult(last_board_id=boards[-1].id if boards else None)
    result.scanned = len(boards)
    if not boards:
        return result
    existing = {
        (UUID(str(row[0])), int(row[1]))
        for row in session.execute(
            text(_EXISTING_SQL),
            {"game_id": game_id, "board_ids": [str(board.id) for board in boards]},
        )
    }
    zero: list[_Board] = []
    positive: list[_Board] = []
    for board in boards:
        if board.asset_mode != "virtual_source":
            result.counts["legacy_skipped"] += 1
        elif (board.id, board.geometry_revision) in existing:
            result.counts["existing_skipped"] += 1
        elif board.geometry_revision == 0:
            zero.append(board)
        else:
            positive.append(board)
    prepared: list[_Prepared] = []
    for board, outcome in (
        *_prepare_zero(session, game_id, zero),
        *_prepare_positive(session, game_id, positive),
    ):
        if isinstance(outcome, RefusedBoard):
            result.refused.append(outcome)
            result.counts["refused"] += 1
        elif isinstance(outcome, _NoCells):
            result.counts["no_cells_skipped"] += 1
        else:
            prepared.append(outcome)
            result.counts["built_revision_zero" if board.geometry_revision == 0 else "copied"] += 1
            result.manifest_bytes += len(canonical_json_bytes(outcome.manifest.document))
    if write and prepared:
        session.execute(
            text(_INSERT_SQL),
            [
                {
                    "game_id": game_id,
                    "board_id": item.manifest.recognized_board_id,
                    "revision": item.manifest.geometry_revision,
                    "source_geometry_revision_id": item.source_geometry_revision_id,
                    "extractor_version": item.extractor_version,
                    "cells": json.dumps(item.manifest.document, allow_nan=False),
                    "checksum": item.manifest.checksum_sha256,
                }
                for item in prepared
            ],
        )
    return result


def run_game(
    session_factory: sessionmaker[Session],
    game_id: UUID,
    *,
    after_board_id: UUID | None,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batches: int | None = None,
    max_seconds: float | None = None,
    on_batch: Callable[[BackfillBatchResult], None] | None = None,
) -> tuple[UUID | None, bool]:
    """Run committed batches until exhausted or a bound is reached.

    Returns ``(last_board_id, exhausted)``; ``on_batch`` runs after each commit
    so the caller can persist a checkpoint and the refused-board report.
    """

    started = time.monotonic()
    batches = 0
    cursor = after_board_id
    while True:
        with session_factory.begin() as session:
            result = run_batch(
                session, game_id, after_board_id=cursor, batch_size=batch_size, write=True
            )
        if result.exhausted:
            return cursor, True
        cursor = result.last_board_id
        batches += 1
        if on_batch is not None:
            on_batch(result)
        if (max_batches is not None and batches >= max_batches) or (
            max_seconds is not None and time.monotonic() - started >= max_seconds
        ):
            return cursor, False


def _prepare_zero(
    session: Session, game_id: UUID, boards: Sequence[_Board]
) -> list[tuple[_Board, _Prepared | RefusedBoard | _NoCells]]:
    if not boards:
        return []
    grouped: dict[UUID, list[Mapping[Any, Any]]] = {board.id: [] for board in boards}
    for row in session.execute(
        text(_OBSERVATIONS_SQL),
        {"game_id": game_id, "board_ids": [str(board.id) for board in boards]},
    ).mappings():
        grouped[UUID(str(row["recognized_board_id"]))].append(row)
    return [(board, _prepare_zero_board(board, grouped[board.id])) for board in boards]


def _prepare_zero_board(
    board: _Board, observations: Sequence[Mapping[Any, Any]]
) -> _Prepared | RefusedBoard | _NoCells:
    def refuse(code: str, cell_index: int | None = None) -> RefusedBoard:
        return RefusedBoard(board.id, 0, code, cell_index)

    expected = available_cell_indices(
        unavailable_cell_indices=board.unavailable_cell_indices,
        geometry_qualification=board.geometry_qualification,
        asset_mode=board.asset_mode,
        cell_count=board.rows * board.columns,
    )
    if not observations:
        # No renderable cell at all is a valid board without a manifest; a
        # board that declares available cells but has none stored is not.
        return _NoCells() if not expected else refuse("BOARD_RENDER_MANIFEST_OBSERVATIONS_MISSING")
    if any(row["asset_mode"] != "virtual_source" for row in observations):
        return refuse("BOARD_RENDER_MANIFEST_OBSERVATION_NOT_VIRTUAL")
    source_ids = {row["source_geometry_revision_id"] for row in observations}
    extractors = {row["extractor_version"] for row in observations}
    if len(source_ids) != 1 or None in source_ids or len(extractors) != 1 or None in extractors:
        return refuse("BOARD_RENDER_MANIFEST_PROVENANCE_INVALID")
    cells: list[ObservedRenderCell] = []
    for row in observations:
        index = int(row["row_index"]) * board.columns + int(row["column_index"])
        render_spec = row["render_spec"]
        if not isinstance(render_spec, Mapping):
            return refuse("BOARD_RENDER_MANIFEST_RENDER_SPEC_MISSING", index)
        if (
            row["cropper_version"] != row["extractor_version"]
            or row["crop_checksum_sha256"] != row["rendered_pixel_checksum_sha256"]
        ):
            return refuse("BOARD_RENDER_MANIFEST_CROP_PROVENANCE_MISMATCH", index)
        cells.append(
            ObservedRenderCell(
                cell_index=index,
                render_spec=cast(Mapping[str, object], render_spec),
                render_spec_checksum_sha256=cast(str, row["render_spec_checksum_sha256"]),
                rendered_pixel_checksum_sha256=cast(str, row["rendered_pixel_checksum_sha256"]),
                logical_cell_key=cast(str, row["logical_cell_key"]),
                logical_cell_key_v2=cast(str | None, row["logical_cell_key_v2"]),
                render_identity_v2_sha256=cast(str | None, row["render_identity_v2_sha256"]),
            )
        )
    try:
        manifest = build_observation_render_manifest(
            recognized_board_id=board.id, cells=cells, expected_cell_indices=expected
        )
    except BoardRenderManifestError as error:
        return refuse(error.code, error.cell_index)
    return _Prepared(
        manifest=manifest,
        source_geometry_revision_id=UUID(str(next(iter(source_ids)))),
        extractor_version=str(next(iter(extractors))),
    )


def _prepare_positive(
    session: Session, game_id: UUID, boards: Sequence[_Board]
) -> list[tuple[_Board, _Prepared | RefusedBoard | _NoCells]]:
    if not boards:
        return []
    revisions = {
        UUID(str(row["recognized_board_id"])): row
        for row in session.execute(
            text(_REVISIONS_SQL),
            {
                "game_id": game_id,
                "board_ids": [str(board.id) for board in boards],
                "revisions": [board.geometry_revision for board in boards],
            },
        ).mappings()
    }
    prepared: list[tuple[_Board, _Prepared | RefusedBoard | _NoCells]] = []
    for board in boards:
        row = revisions.get(board.id)
        if (
            row is None
            or row["asset_mode"] != "virtual_source"
            or not isinstance(row["virtual_render_spec"], Mapping)
            or row["source_geometry_revision_id"] is None
        ):
            prepared.append(
                (
                    board,
                    RefusedBoard(
                        board.id,
                        board.geometry_revision,
                        "BOARD_RENDER_MANIFEST_REVISION_UNUSABLE",
                    ),
                )
            )
            continue
        if row["virtual_render_spec"].get("cells") == []:
            # A revision without renderable cells is legitimate only when the board's
            # availability mask is empty too and the stored spec is intact.
            spec = cast(Mapping[str, object], row["virtual_render_spec"])
            expected = available_cell_indices(
                unavailable_cell_indices=board.unavailable_cell_indices,
                geometry_qualification=board.geometry_qualification,
                asset_mode=board.asset_mode,
                cell_count=board.rows * board.columns,
            )
            if sha256_canonical_json(dict(spec)) != str(row["virtual_render_spec_checksum_sha256"]):
                code = "BOARD_RENDER_MANIFEST_REVISION_CHECKSUM_MISMATCH"
                prepared.append((board, RefusedBoard(board.id, board.geometry_revision, code)))
            elif expected:
                code = "BOARD_RENDER_MANIFEST_CELLS_INCOMPLETE"
                prepared.append((board, RefusedBoard(board.id, board.geometry_revision, code)))
            else:
                prepared.append((board, _NoCells()))
            continue
        try:
            manifest = revision_render_manifest(
                recognized_board_id=board.id,
                geometry_revision=board.geometry_revision,
                virtual_render_spec=cast(Mapping[str, object], row["virtual_render_spec"]),
                virtual_render_spec_checksum_sha256=str(row["virtual_render_spec_checksum_sha256"]),
            )
        except BoardRenderManifestError as error:
            prepared.append(
                (
                    board,
                    RefusedBoard(board.id, board.geometry_revision, error.code, error.cell_index),
                )
            )
            continue
        prepared.append(
            (
                board,
                _Prepared(
                    manifest=manifest,
                    source_geometry_revision_id=UUID(str(row["source_geometry_revision_id"])),
                    extractor_version=str(row["cropper_version"]),
                ),
            )
        )
    return prepared


def _board_from_row(row: Mapping[Any, Any]) -> _Board:
    qualification = row["geometry_qualification"]
    return _Board(
        id=UUID(str(row["id"])),
        geometry_revision=int(row["geometry_revision"]),
        asset_mode=str(row["asset_mode"]),
        rows=int(row["grid_rows"] or 3),
        columns=int(row["grid_columns"] or 5),
        unavailable_cell_indices=tuple(
            int(value) for value in row["unavailable_cell_indices"] or ()
        ),
        geometry_qualification=(
            cast(Mapping[str, object], qualification)
            if isinstance(qualification, Mapping)
            else None
        ),
    )


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "MAX_BATCH_SIZE",
    "BackfillBatchResult",
    "RefusedBoard",
    "preview_counts",
    "run_batch",
    "run_game",
]
