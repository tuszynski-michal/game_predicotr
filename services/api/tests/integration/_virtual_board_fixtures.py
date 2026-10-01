"""Shared PostgreSQL fixtures for ``virtual_source`` boards (D-467 S6, TASK-0796).

Since migration 0135 a recognized board and its symbol cells can only be
``virtual_source``.  These helpers build the minimal consistent virtual
provenance the readers require, without rendering pixels:

* one accepted source geometry revision per source image (9 attested slots),
* a ``virtual_source`` board bound to it,
* the board render manifest of the board's current geometry revision (the
  only cell record since D-467 S5), built with the production manifest
  builders so crop sample identities and checksums match the readers,
* for ``geometry_revision > 0`` the matching virtual geometry revision record.

Render specs are synthetic: no test using these helpers renders pixels.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime
from uuid import UUID, uuid4

from game_predictor_api.domain.board_render_manifests import (
    BoardRenderManifest,
    ObservedRenderCell,
    build_observation_render_manifest,
    revision_render_manifest,
    sha256_canonical_json,
)
from game_predictor_api.domain.rules import RulesVersionStatus
from game_predictor_api.storage.board_render_manifest_repository import (
    ensure_board_render_manifest,
)
from game_predictor_api.storage.board_search_projection_repository import (
    SqlAlchemyBoardSearchProjectionRepository,
)
from game_predictor_api.storage.image_symbol_review_repository import (
    SymbolCellReviewWriteThroughCoordinator,
)
from game_predictor_api.storage.models import (
    ImageBoardGeometryReviewEventModel,
    ImageBoardGeometryRevisionModel,
    ImageLayoutStagingRowModel,
    ImageReviewItemModel,
    ImageReviewResolutionEventModel,
    ImageSequenceCanonicalModel,
    ImageSourceGeometryRevisionModel,
    RecognizedBoardModel,
    RulesVersionModel,
    SourceImageModel,
)
from sqlalchemy import delete, func, null, select
from sqlalchemy.orm import Session

VIRTUAL_FIXTURE_ENGINE_NAME = "structured_opencv_v1"
VIRTUAL_FIXTURE_ENGINE_VERSION = "virtual-fixture-engine-v1"
VIRTUAL_FIXTURE_EXTRACTOR_VERSION = "virtual-fixture-renderer-v1"
_SOURCE_SLOTS = 9


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def virtual_render_spec(
    *, board_label: str, cell_index: int, geometry_revision: int, variant: str = ""
) -> dict[str, object]:
    """A synthetic, checksum-stable render spec for one virtual cell."""

    return {
        "boardLabel": board_label,
        "cellIndex": cell_index,
        "columnIndex": cell_index % 5,
        "geometryRevision": geometry_revision,
        "outputSize": [96, 96],
        "rowIndex": cell_index // 5,
        "variant": variant,
    }


def ensure_topology_rules_version(session: Session, *, game_id: UUID) -> UUID:
    """The 3 x 5 rules version a source geometry revision is bound to."""

    existing = session.scalar(
        select(RulesVersionModel.id)
        .where(RulesVersionModel.game_id == game_id)
        .order_by(RulesVersionModel.version)
        .limit(1)
    )
    if existing is not None:
        return existing
    version = (
        session.scalar(
            select(func.max(RulesVersionModel.version)).where(RulesVersionModel.game_id == game_id)
        )
        or 0
    ) + 1
    record = RulesVersionModel(
        game_id=game_id,
        version=version,
        rows=3,
        columns=5,
        spin_cost=0,
        status=RulesVersionStatus.DRAFT,
    )
    session.add(record)
    session.flush()
    return record.id


def ensure_source_geometry(
    session: Session,
    *,
    game_id: UUID,
    source: SourceImageModel,
    sequence_range_start: int,
    created_at: datetime,
    quad: Sequence[Mapping[str, object]] | None = None,
) -> ImageSourceGeometryRevisionModel:
    """Revision 0 of one source's geometry (created once per source)."""

    existing = session.scalar(
        select(ImageSourceGeometryRevisionModel)
        .where(ImageSourceGeometryRevisionModel.source_image_id == source.id)
        .order_by(ImageSourceGeometryRevisionModel.revision.desc())
        .limit(1)
    )
    if existing is not None:
        return existing
    # The source carries the canonical coordinate metadata its geometry pins.
    normalized_checksum = _sha(f"normalized:{source.checksum_sha256}")
    source.raw_width = source.raw_width or source.width
    source.raw_height = source.raw_height or source.height
    source.oriented_width = source.oriented_width or source.width
    source.oriented_height = source.oriented_height or source.height
    source.coordinate_space = "exif-normalized-rgb-pixels-v1"
    source.normalized_pixel_checksum_sha256 = (
        source.normalized_pixel_checksum_sha256 or normalized_checksum
    )
    source.normalization_adapter_version = (
        source.normalization_adapter_version or "virtual-fixture-normalization-v1"
    )
    final_quad = (
        [dict(point) for point in quad]
        if quad is not None
        else [
            {"x": source.width * 0.1, "y": source.height * 0.1},
            {"x": source.width * 0.9, "y": source.height * 0.1},
            {"x": source.width * 0.9, "y": source.height * 0.9},
            {"x": source.width * 0.1, "y": source.height * 0.9},
        ]
    )
    start = max(1, sequence_range_start)
    record = ImageSourceGeometryRevisionModel(
        game_id=game_id,
        source_image_id=source.id,
        topology_rules_version_id=ensure_topology_rules_version(session, game_id=game_id),
        revision=0,
        sequence_range_start=start,
        sequence_range_end=start + _SOURCE_SLOTS - 1,
        active_board_slots=list(range(_SOURCE_SLOTS)),
        coordinate_space="exif-normalized-rgb-pixels-v1",
        source_checksum_sha256=source.checksum_sha256,
        normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
        oriented_width=source.oriented_width,
        oriented_height=source.oriented_height,
        normalization_adapter_version=source.normalization_adapter_version,
        global_initialization={},
        board_geometries=[
            {
                "disposition": "automatic",
                "finalQuad": final_quad,
                "positionIndex": slot,
                "sequenceNumber": start + slot,
            }
            for slot in range(_SOURCE_SLOTS)
        ],
        engine_kind=VIRTUAL_FIXTURE_ENGINE_NAME,
        engine_version=VIRTUAL_FIXTURE_ENGINE_VERSION,
        geometry_source="auto",
        status="accepted",
        geometry_checksum_sha256=_sha(f"source-geometry:{source.id}"),
        processing_time_ms=1,
        warnings=[],
        created_by="virtual-board-fixture",
        created_at=created_at,
    )
    session.add(record)
    session.flush()
    return record


def virtual_board_columns(
    source_geometry: ImageSourceGeometryRevisionModel,
) -> dict[str, object]:
    """Board columns that bind a ``virtual_source`` board to its source geometry."""

    return {
        "asset_mode": "virtual_source",
        "source_geometry_revision_id": source_geometry.id,
        "geometry_engine_name": VIRTUAL_FIXTURE_ENGINE_NAME,
        "geometry_engine_version": VIRTUAL_FIXTURE_ENGINE_VERSION,
        "geometry_checksum_sha256": source_geometry.geometry_checksum_sha256,
        "board_relative_path": None,
        "board_checksum_sha256": None,
        "grid_rows": 3,
        "grid_columns": 5,
    }


def _observed_cells(
    board: RecognizedBoardModel,
    *,
    geometry_revision: int,
    cell_indices: Sequence[int],
    variant: str,
    changed_cells: Collection[int] | None,
) -> list[ObservedRenderCell]:
    """Render identities of one revision.

    The render spec always changes with the revision; the rendered pixels
    change only with ``variant`` (for ``changed_cells`` or every cell), so a
    test can save a geometry that keeps some or all pixels (D-462 R6/R10).
    """

    label = str(board.id)
    cells: list[ObservedRenderCell] = []
    for index in cell_indices:
        pixels = variant if changed_cells is None or index in changed_cells else ""
        spec = virtual_render_spec(
            board_label=label,
            cell_index=index,
            geometry_revision=geometry_revision,
            variant=variant,
        )
        cells.append(
            ObservedRenderCell(
                cell_index=index,
                render_spec=spec,
                render_spec_checksum_sha256=sha256_canonical_json(spec),
                rendered_pixel_checksum_sha256=_sha(f"pixels:{label}:{index}:{pixels}"),
                logical_cell_key=_sha(f"logical:{label}:{index}"),
                logical_cell_key_v2=_sha(f"logical-v2:{label}:{index}"),
                render_identity_v2_sha256=_sha(f"identity-v2:{label}:{geometry_revision}:{index}"),
            )
        )
    return cells


def add_board_render_manifest_for(
    session: Session,
    *,
    game_id: UUID,
    board: RecognizedBoardModel,
    review_item_id: UUID | None = None,
    cell_indices: Sequence[int] | None = None,
    variant: str = "",
    changed_cells: Collection[int] | None = None,
    created_at: datetime | None = None,
    corrected_by: str = "virtual-board-fixture",
) -> BoardRenderManifest:
    """Persist the render manifest of ``board.geometry_revision``.

    Revision 0 uses the import manifest builder; a positive revision also
    appends the virtual geometry revision record whose ``virtual_render_spec``
    the manifest copies (``review_item_id`` is then required).
    """

    assert board.source_geometry_revision_id is not None, "bind the board to a source geometry"
    indices = tuple(range(15)) if cell_indices is None else tuple(cell_indices)
    revision = board.geometry_revision
    observed = build_observation_render_manifest(
        recognized_board_id=board.id,
        cells=_observed_cells(
            board,
            geometry_revision=revision,
            cell_indices=indices,
            variant=variant,
            changed_cells=changed_cells,
        ),
    )
    if revision == 0:
        manifest = observed
    else:
        assert review_item_id is not None, "a geometry revision belongs to a review item"
        document = dict(observed.document)
        checksum = sha256_canonical_json(document)
        session.add(
            ImageBoardGeometryRevisionModel(
                review_item_id=review_item_id,
                recognized_board_id=board.id,
                revision=revision,
                idempotency_key=uuid4(),
                command_sha256=_sha(f"command:{board.id}:{revision}:{variant}"),
                corners=[
                    {"x": 100, "y": 100},
                    {"x": 600, "y": 100},
                    {"x": 600, "y": 400},
                    {"x": 100, "y": 400},
                ],
                geometry=dict(board.board_geometry),
                asset_mode="virtual_source",
                source_geometry_revision_id=board.source_geometry_revision_id,
                geometry_checksum_sha256=board.geometry_checksum_sha256,
                virtual_render_spec=document,
                virtual_render_spec_checksum_sha256=checksum,
                board_relative_path=None,
                board_checksum_sha256=None,
                cropper_version=VIRTUAL_FIXTURE_EXTRACTOR_VERSION,
                crop_artifacts=None,
                corrected_by=corrected_by,
                **({} if created_at is None else {"created_at": created_at}),
            )
        )
        manifest = revision_render_manifest(
            recognized_board_id=board.id,
            geometry_revision=revision,
            virtual_render_spec=document,
            virtual_render_spec_checksum_sha256=checksum,
        )
    ensure_board_render_manifest(
        session,
        game_id=game_id,
        manifest=manifest,
        source_geometry_revision_id=board.source_geometry_revision_id,
        extractor_version=VIRTUAL_FIXTURE_EXTRACTOR_VERSION,
    )
    session.flush()
    return manifest


def replace_virtual_geometry(
    session: Session,
    *,
    game_id: UUID,
    review_item_id: UUID,
    board_id: UUID,
    variant: str,
    changed_cells: Collection[int] | None = None,
    corrected_by: str = "integration-owner",
    cell_indices: Sequence[int] | None = None,
) -> int:
    """Append the next virtual geometry revision of one board (storage level).

    ``cell_indices`` limits the rendered cells (a qualified partial board).
    """

    board = session.get(RecognizedBoardModel, board_id)
    assert board is not None
    board.geometry_revision += 1
    session.flush()
    add_board_render_manifest_for(
        session,
        game_id=game_id,
        board=board,
        review_item_id=review_item_id,
        variant=variant,
        changed_cells=changed_cells,
        corrected_by=corrected_by,
        cell_indices=cell_indices,
    )
    return board.geometry_revision


def save_manual_virtual_geometry(
    session: Session,
    *,
    game_id: UUID,
    import_job_id: UUID,
    review_item_id: UUID,
    board_id: UUID,
    actor: str,
    variant: str,
    created_at: datetime,
    changed_cells: Collection[int] | None = None,
) -> int:
    """Storage effects of one manual geometry save, without rendering pixels.

    D-467 S6 (TASK-0796): the v19 file-crop save is gone and the virtual save
    renders a real source, which these synthetic fixtures do not have.  This
    helper reproduces the persisted effects the write-through tests depend on
    (new virtual revision + manifest, reopened item, approval metadata,
    geometry event, projection and cell synchronization) in the order of the
    former save; the production path is covered with a real source by
    ``test_reviewer_operational_geometry_postgres.py``.
    """

    item = session.get(ImageReviewItemModel, review_item_id, with_for_update=True)
    board = session.get(RecognizedBoardModel, board_id, with_for_update=True)
    assert item is not None and board is not None
    previous_status = item.status
    previous_resolved = item.resolved_value
    previous_sequence = (
        previous_resolved.get("sequenceNumber") if isinstance(previous_resolved, dict) else None
    )
    revision = replace_virtual_geometry(
        session,
        game_id=game_id,
        review_item_id=review_item_id,
        board_id=board_id,
        variant=variant,
        changed_cells=changed_cells,
        corrected_by=actor,
    )
    if previous_status in {"accepted", "corrected"} and isinstance(previous_sequence, int):
        session.execute(
            delete(ImageSequenceCanonicalModel).where(
                ImageSequenceCanonicalModel.game_id == game_id,
                ImageSequenceCanonicalModel.sequence_number == previous_sequence,
                ImageSequenceCanonicalModel.review_item_id == review_item_id,
            )
        )
    item.status = "pending"
    item.resolved_value = null()
    item.resolved_by = None
    item.resolved_at = None
    item.resolution_revision += 1
    session.add(
        ImageReviewResolutionEventModel(
            review_item_id=review_item_id,
            revision=item.resolution_revision,
            idempotency_key=uuid4(),
            action="reopened",
            command_sha256=_sha(f"reopen:{board_id}:{revision}"),
            resolved_value={
                "action": "reopened",
                "geometryRevision": revision,
                "previousStatus": previous_status,
            },
            resolved_by=actor,
            created_at=created_at,
        )
    )
    previous_approved = board.approved_geometry_revision
    board.approved_geometry_revision = revision
    board.geometry_approved_at = created_at
    board.geometry_approved_by = actor
    board.status = "pending_review"
    session.add(
        ImageBoardGeometryReviewEventModel(
            review_item_id=review_item_id,
            recognized_board_id=board_id,
            geometry_revision=revision,
            grid_rows=3,
            grid_columns=5,
            board_checksum_sha256=board.geometry_checksum_sha256,
            action="geometry_saved",
            previous_approved_geometry_revision=previous_approved,
            approved_geometry_revision=revision,
            actor=actor,
            created_at=created_at,
        )
    )
    session.execute(
        delete(ImageLayoutStagingRowModel).where(
            ImageLayoutStagingRowModel.import_job_id == import_job_id,
            ImageLayoutStagingRowModel.recognized_board_id == board_id,
        )
    )
    session.flush()
    projection = SqlAlchemyBoardSearchProjectionRepository(session)
    projection.sync_review_item(review_item_id)
    if isinstance(previous_sequence, int):
        projection.sync_sequence_candidates(game_id, previous_sequence)
    coordinator = SymbolCellReviewWriteThroughCoordinator(session)
    coordinator.synchronize_after_geometry_change(
        game_id=game_id, review_item_id=review_item_id, actor=actor
    )
    coordinator.synchronize_board_from_cells(
        game_id=game_id, review_item_id=review_item_id, actor=actor
    )
    coordinator.synchronize_after_projection_change(game_id=game_id)
    return revision


def manifest_cell(manifest: BoardRenderManifest, cell_index: int) -> Mapping[str, object]:
    cells = manifest.document["cells"]
    assert isinstance(cells, list)
    for cell in cells:
        if isinstance(cell, Mapping) and cell.get("cellIndex") == cell_index:
            return cell
    raise AssertionError(f"manifest has no cell {cell_index}")


__all__ = [
    "VIRTUAL_FIXTURE_ENGINE_NAME",
    "VIRTUAL_FIXTURE_ENGINE_VERSION",
    "VIRTUAL_FIXTURE_EXTRACTOR_VERSION",
    "add_board_render_manifest_for",
    "ensure_source_geometry",
    "ensure_topology_rules_version",
    "manifest_cell",
    "replace_virtual_geometry",
    "save_manual_virtual_geometry",
    "virtual_board_columns",
    "virtual_render_spec",
]
