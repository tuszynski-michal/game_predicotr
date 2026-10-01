"""D-467 S7 (TASK-0792/0793): every reader of a cell render spec uses the board manifest.

Runs on a dedicated ``*_test`` database only (fixture from the TASK-0790
test).  Two deferred slots of one real source are resolved through the
Reviewer endpoint: a full board and a partial board cut by the left source
edge.  Since migration ``0136`` (TASK-0793) the cells have no ``render_spec``
column; the reference is the manifest entry of each cell read independently
in SQL and bound to the cell by ``render_spec_checksum_sha256`` (TASK-0792
compared the same readers with the former column, 0 differences):

- ``get_assets`` returns the same specification; the preview atlas and the
  full-resolution PNG render byte-identical pixels;
- a checksum mismatch and a missing manifest fail closed with explicit codes;
- symbol reference candidates and the training inventory carry the same
  specification, and the training cohort manifest checksum is unchanged;
- the manual geometry context pins the same render configuration.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.virtual_cell_previews import (
    VirtualCellPreviewService,
    render_virtual_symbol_cell_png,
    symbol_cell_preview_renderer_fingerprint,
    symbol_cell_preview_renderer_version,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_render_manifests import sha256_canonical_json
from game_predictor_api.domain.catalog import SymbolStatus
from game_predictor_api.domain.symbol_cell_training_cohorts import (
    build_symbol_cell_training_manifest,
    select_symbol_cell_training_samples,
)
from game_predictor_api.main import create_app
from game_predictor_api.storage.cell_render_specs import (
    RENDER_MANIFEST_MISSING,
    RENDER_SPEC_MISMATCH,
    CellRenderSpecError,
)
from game_predictor_api.storage.game_storage_routing import game_storage_scope
from game_predictor_api.storage.image_symbol_review_repository import (
    SqlAlchemySymbolCellReviewQueryRepository,
)
from game_predictor_api.storage.models import SymbolModel
from game_predictor_api.storage.symbol_cell_training_source_repository import (
    SqlAlchemySymbolCellTrainingSourceRepository,
)
from game_predictor_api.storage.symbol_references_repository import (
    SqlAlchemyApprovedSymbolReferenceRepository,
)
from game_predictor_api.storage.virtual_grid_geometry_repository import (
    SqlAlchemyVirtualGridGeometryRepository,
    _configuration,
)
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_virtual_deferred_resolution_postgres import (
    _PARTIAL_CORNERS,
    _PARTIAL_MASK,
    _corners,
    _Database,
    _factory,
    _provision_game,
    _Seed,
    _seed,
    database,  # noqa: F401
)

pytestmark = pytest.mark.skipif(
    os.environ.get("GAME_PREDICTOR_RUN_POSTGRES_TESTS") != "1",
    reason="Explicit isolated PostgreSQL tests only",
)

_CELLS = "game_data_v2.image_symbol_review_cells"
# Approved human decisions: three cells of the full board, two visible cells
# of the partial board (0, 1, 5, 6, 10, 11 are outside the source there).
_APPROVED_FULL = (1, 2, 7)
_APPROVED_PARTIAL = (3, 4)


def _resolve_full_and_partial(db: _Database, artifact_root: Path, seed: _Seed) -> None:
    app = create_app(
        ApiSettings.from_environment(
            {
                "GAME_PREDICTOR_DATABASE_URL": db.url,
                "GAME_PREDICTOR_ARTIFACT_ROOT": str(artifact_root),
            }
        )
    )
    base = (
        f"/api/v1/admin/games/{seed.game_id}/image-imports/{seed.import_job_id}/"
        "board-cell-geometry-pending"
    )
    full = {
        "corners": _corners(),
        "correctedBy": "task-0792-operator",
        "expectedGeometryRevision": 0,
        "expectedManifestChecksumSha256": seed.manifest_checksums[0],
        "expectedResolutionRevision": 0,
        "idempotencyKey": str(uuid4()),
    }
    partial = {
        **full,
        "corners": _PARTIAL_CORNERS,
        "expectedManifestChecksumSha256": seed.manifest_checksums[1],
        "idempotencyKey": str(uuid4()),
        "geometryQualification": {
            "completenessStatus": "pending_partial",
            "excludeFromGeometryTraining": True,
            "exclusionReason": "missing_pixels",
            "unavailableCellIndices": list(_PARTIAL_MASK),
            "version": "manual-geometry-qualification-v1",
        },
    }
    try:
        with TestClient(app) as client:
            for pending_id, command in zip(seed.pending_ids, (full, partial), strict=True):
                response = client.post(f"{base}/{pending_id}/manual-resolution", json=command)
                assert response.status_code == 200, response.text
    finally:
        app.state.database_engine.dispose()


def _managed_source(artifact_root: Path, game_id: UUID, session: Session) -> None:
    """Place the source where the preview renderer looks for managed originals."""

    relative, checksum = session.execute(
        text(
            """SELECT relative_path, checksum_sha256 FROM game_data_v2.source_images
            WHERE game_id = :game_id"""
        ),
        {"game_id": game_id},
    ).one()
    target = artifact_root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(artifact_root / "data" / relative, target)


def _boards(session: Session, game_id: UUID) -> list[tuple[UUID, int, UUID, UUID]]:
    """(board, position, review item, import job) of both resolved boards."""

    return [
        (row.id, row.position_index, row.review_item_id, row.import_job_id)
        for row in session.execute(
            text(
                """SELECT b.id, b.position_index, i.id AS review_item_id, s.import_job_id
                FROM game_data_v2.recognized_boards b
                JOIN game_data_v2.image_review_items i ON i.recognized_board_id = b.id
                JOIN game_data_v2.source_images s ON s.id = b.source_image_id
                WHERE b.game_id = :game_id ORDER BY b.position_index"""
            ),
            {"game_id": game_id},
        )
    ]


def _approve(
    session: Session, game_id: UUID, board_id: UUID, symbol_id: UUID, indices: Any
) -> None:
    session.execute(
        text(
            f"""UPDATE {_CELLS}
            SET review_state = 'approved',
                assigned_symbol_id = :symbol_id,
                assignment_source = 'human',
                verification_outcome = 'verified_symbol',
                verified_symbol_id_v2 = :symbol_id,
                approved_crop_sample_id = crop_sample_id,
                approved_crop_checksum_sha256 = crop_checksum_sha256,
                approved_geometry_revision = geometry_revision,
                approved_asset_mode = asset_mode,
                approved_source_geometry_revision_id = source_geometry_revision_id,
                approved_render_spec_checksum_sha256 = render_spec_checksum_sha256,
                approved_rendered_pixel_checksum_sha256 = rendered_pixel_checksum_sha256,
                last_reviewed_by = 'task-0792-operator'
            WHERE game_id = :game_id AND recognized_board_id = :board_id
              AND cell_index = ANY(:indices)"""
        ),
        {
            "game_id": game_id,
            "board_id": board_id,
            "symbol_id": symbol_id,
            "indices": list(indices),
        },
    )


def _manifest_specs(
    session: Session, game_id: UUID
) -> dict[UUID, tuple[UUID, int, dict[str, object]]]:
    """Reference: each virtual cell's manifest entry, independent of the reader.

    Returns ``cell id -> (board id, cell index, renderSpec)``; the entry's
    canonical checksum must equal the cell's ``render_spec_checksum_sha256``.
    """

    assert (
        session.execute(
            text(
                """SELECT count(*) FROM information_schema.columns
                WHERE table_schema = 'game_data_v2'
                  AND table_name = 'image_symbol_review_cells'
                  AND column_name = 'render_spec'"""
            )
        ).scalar_one()
        == 0
    )
    expected: dict[UUID, tuple[UUID, int, dict[str, object]]] = {}
    for row in session.execute(
        text(
            f"""SELECT c.id, c.recognized_board_id, c.cell_index,
                   c.render_spec_checksum_sha256, entry -> 'renderSpec' AS spec
            FROM {_CELLS} c
            JOIN game_data_v2.board_render_manifests m
              ON m.game_id = c.game_id AND m.recognized_board_id = c.recognized_board_id
             AND m.geometry_revision = c.geometry_revision
            CROSS JOIN LATERAL jsonb_array_elements(m.cells -> 'cells') AS entry
            WHERE c.game_id = :game_id AND c.asset_mode = 'virtual_source'
              AND (entry ->> 'cellIndex')::int = c.cell_index"""
        ),
        {"game_id": game_id},
    ):
        spec = cast(dict[str, object], row.spec)
        assert sha256_canonical_json(spec) == row.render_spec_checksum_sha256
        assert row.id not in expected
        expected[row.id] = (row.recognized_board_id, row.cell_index, spec)
    return expected


def test_switched_readers_reproduce_the_cell_column_from_the_manifest(
    database: _Database,  # noqa: F811
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    game_id = _provision_game(database.engine, "task0792-readers")
    factory = _factory(database.engine)
    seed = _seed(factory, game_id, artifact_root, label="task0792-source", slot_count=2)
    _resolve_full_and_partial(database, artifact_root, seed)

    with game_storage_scope(game_id), factory() as session, session.begin():
        _managed_source(artifact_root, game_id, session)
        boards = _boards(session, game_id)
        assert [position for _board, position, _item, _job in boards] == [0, 1]
        symbol = SymbolModel(
            game_id=game_id,
            mobile_code=3,
            code="CYTRYNA",
            name="Cytryna",
            display_order=3,
            status=SymbolStatus.ACTIVE,
        )
        session.add(symbol)
        session.flush()
        symbol_id = symbol.id
        _approve(session, game_id, boards[0][0], symbol_id, _APPROVED_FULL)
        _approve(session, game_id, boards[1][0], symbol_id, _APPROVED_PARTIAL)

    with game_storage_scope(game_id), factory() as session:
        references = _manifest_specs(session, game_id)
        column = {cell_id: spec for cell_id, (_b, _i, spec) in references.items()}
        # Full board: 15 virtual cells; partial board: 9 (6 positions outside).
        assert len(column) == 15 + 15 - len(_PARTIAL_MASK)
        approved_ids = {
            row.id
            for row in session.execute(
                text(f"SELECT id FROM {_CELLS} WHERE game_id = :g AND review_state = 'approved'"),
                {"g": game_id},
            )
        }
        assert len(approved_ids) == len(_APPROVED_FULL) + len(_APPROVED_PARTIAL)

        # get_assets: the manifest specification, from one batched read.
        repository = SqlAlchemySymbolCellReviewQueryRepository(session)
        assets = repository.get_assets(game_id=game_id, cell_review_ids=tuple(column))
        assert {asset.cell_review_id for asset in assets} == set(column)
        for asset in assets:
            assert asset.render_spec == column[asset.cell_review_id]
        before = tuple(replace(asset, render_spec=column[asset.cell_review_id]) for asset in assets)

        # Pixels: the full-resolution PNG and the atlas are byte-identical.
        for new, old in zip(assets, before, strict=True):
            assert render_virtual_symbol_cell_png(
                artifact_root=artifact_root, asset=new
            ) == render_virtual_symbol_cell_png(artifact_root=artifact_root, asset=old)
        previews = VirtualCellPreviewService(artifact_root)
        atlas_args: dict[str, Any] = {
            "game_id": game_id,
            "batch_key": "0" * 64,
            "preview_size": 64,
            "now": datetime.now(UTC),
            "renderer_mode": "current",
            "renderer_version": symbol_cell_preview_renderer_version("current"),
            "renderer_fingerprint_sha256": symbol_cell_preview_renderer_fingerprint("current"),
        }
        atlas_new = previews._render_atlas(assets=assets, **atlas_args)
        atlas_old = previews._render_atlas(assets=before, **atlas_args)
        assert atlas_new.content == atlas_old.content
        assert atlas_new.batch.tiles == atlas_old.batch.tiles
        # The public batch path renders the same atlas too.
        batch = previews.render_batch(game_id=game_id, assets=assets, preview_size=64)
        assert batch.atlas_checksum_sha256 == atlas_new.batch.atlas_checksum_sha256

        # Symbol reference candidates: same cells, same specification.
        reference_repository = SqlAlchemyApprovedSymbolReferenceRepository(session)
        candidates = reference_repository.list_candidates(
            game_id=game_id, symbol_id=symbol_id, after_key=None, limit=50
        )
        assert {candidate.cell_review_id for candidate in candidates} == approved_ids
        for candidate in candidates:
            assert candidate.virtual_asset is not None
            assert candidate.virtual_asset.render_spec == column[candidate.cell_review_id]
            assert render_virtual_symbol_cell_png(
                artifact_root=artifact_root, asset=candidate.virtual_asset
            ) == render_virtual_symbol_cell_png(
                artifact_root=artifact_root,
                asset=replace(
                    candidate.virtual_asset, render_spec=column[candidate.cell_review_id]
                ),
            )

        # Training inventory: same specification and the same cohort manifest.
        inventory = SqlAlchemySymbolCellTrainingSourceRepository(session, artifact_root).inventory(
            game_id=game_id, lock_game=False
        )
        assert {candidate.cell_review_id for candidate in inventory.candidates} == approved_ids
        for candidate in inventory.candidates:
            assert candidate.render_spec == column[candidate.cell_review_id]
        selection_new = select_symbol_cell_training_samples(
            candidates=inventory.candidates, active_symbol_codes=("CYTRYNA",)
        )
        selection_old = select_symbol_cell_training_samples(
            candidates=tuple(
                replace(candidate, render_spec=column[candidate.cell_review_id])
                for candidate in inventory.candidates
            ),
            active_symbol_codes=("CYTRYNA",),
        )
        manifest_new = build_symbol_cell_training_manifest(game_id=game_id, selection=selection_new)
        manifest_old = build_symbol_cell_training_manifest(game_id=game_id, selection=selection_old)
        assert manifest_new[1] == manifest_old[1]
        assert manifest_new[2] == manifest_old[2]

        # Manual geometry: the pinned configuration of the current cells.
        geometry = SqlAlchemyVirtualGridGeometryRepository(session)
        for board_id, _position, review_item_id, import_job_id in boards:
            context = geometry.virtual_geometry_context(
                game_id=game_id,
                import_job_id=import_job_id,
                review_item_id=review_item_id,
                pending_geometry_id=None,
            )
            first = min(
                (index, spec) for board, index, spec in references.values() if board == board_id
            )[1]
            assert context.render_configuration == _configuration(first)

    # Fail closed: a cell whose checksum differs from its manifest entry.
    target = next(iter(column))
    with game_storage_scope(game_id), factory() as session:
        session.execute(
            text(
                f"""UPDATE {_CELLS} SET render_spec_checksum_sha256 = :checksum
                WHERE game_id = :g AND id = :id"""
            ),
            {"checksum": "f" * 64, "g": game_id, "id": target},
        )
        with pytest.raises(CellRenderSpecError) as mismatch:
            SqlAlchemySymbolCellReviewQueryRepository(session).get_assets(
                game_id=game_id, cell_review_ids=(target,)
            )
        session.rollback()
    assert mismatch.value.code == RENDER_SPEC_MISMATCH

    # Fail closed: the board's manifest is missing.
    with game_storage_scope(game_id), factory() as session:
        session.execute(
            text(
                """DELETE FROM game_data_v2.board_render_manifests
                WHERE game_id = :g AND recognized_board_id = :b"""
            ),
            {"g": game_id, "b": boards[0][0]},
        )
        full_board_cells = tuple(
            session.scalars(
                text(
                    f"""SELECT id FROM {_CELLS}
                    WHERE game_id = :g AND recognized_board_id = :b"""
                ),
                {"g": game_id, "b": boards[0][0]},
            )
        )
        with pytest.raises(CellRenderSpecError) as missing:
            SqlAlchemySymbolCellReviewQueryRepository(session).get_assets(
                game_id=game_id, cell_review_ids=full_board_cells
            )
        session.rollback()
    assert missing.value.code == RENDER_MANIFEST_MISSING
