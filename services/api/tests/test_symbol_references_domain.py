from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest
from game_predictor_api.application.symbol_references import (
    ApprovedSymbolReferenceService,
    ManagedSymbolReferenceArtifactStore,
)
from game_predictor_api.domain.catalog import CatalogConflictError, Symbol, SymbolStatus
from game_predictor_api.domain.image_symbol_reviews import SymbolCellReviewAsset
from game_predictor_api.domain.symbol_references import (
    ApprovedSymbolReferenceCandidate,
)


class MemoryRepository:
    def __init__(self, game_id, candidates=()):
        self.game_id = game_id
        self.candidates = tuple(sorted(candidates, key=lambda item: item.cursor_key))

    def game_exists(self, game_id):
        return game_id == self.game_id

    def list_candidates(self, *, game_id, symbol_id, after_key, limit):
        rows = self.candidates
        if after_key is not None:
            rows = tuple(row for row in rows if row.cursor_key > after_key)
        return rows[:limit]

    def get_candidate(self, *, game_id, symbol_id, cell_review_id):
        return next((row for row in self.candidates if row.cell_review_id == cell_review_id), None)

    def get_reference(self, *, game_id, symbol_id):
        return None

    def select_reference(self, **kwargs):
        return Symbol(
            id=kwargs["symbol_id"],
            game_id=kwargs["game_id"],
            mobile_code=1,
            code="lemon",
            name="Lemon",
            image_path="data/reference.png",
            is_wildcard=False,
            display_order=0,
            status=SymbolStatus.ACTIVE,
        )


def _candidate(*, geometry_revision=0, sequence_number=1, cell_index=0):
    # D-467 S6 (TASK-0796): an approved reference candidate is a virtual render.
    cell_review_id = uuid4()
    source_geometry_revision_id = uuid4()
    return ApprovedSymbolReferenceCandidate(
        cell_review_id=cell_review_id,
        review_item_id=uuid4(),
        recognized_board_id=uuid4(),
        sequence_number=sequence_number,
        cell_index=cell_index,
        resolution_revision=1,
        geometry_revision=geometry_revision,
        crop_relative_path=None,
        crop_checksum_sha256="a" * 64,
        status="corrected",
        asset_mode="virtual_source",
        virtual_asset=SymbolCellReviewAsset(
            cell_review_id=cell_review_id,
            crop_relative_path=None,
            crop_checksum_sha256="a" * 64,
            geometry_revision=geometry_revision,
            current_geometry_revision=geometry_revision,
            asset_mode="virtual_source",
            source_checksum_sha256="b" * 64,
            normalized_pixel_checksum_sha256="c" * 64,
            source_geometry_revision_id=source_geometry_revision_id,
            current_source_geometry_revision_id=source_geometry_revision_id,
            geometry_checksum_sha256="d" * 64,
            logical_cell_key="e" * 64,
            render_spec={"cellIndex": cell_index},
            render_spec_checksum_sha256="f" * 64,
            rendered_pixel_checksum_sha256="a" * 64,
            extractor_version="virtual-renderer-v1",
        ),
    )


def test_approved_reference_cursor_is_scope_bound_and_orders_corrected_geometry_first():
    game_id, symbol_id = uuid4(), uuid4()
    raw = (
        _candidate(sequence_number=2),
        _candidate(geometry_revision=1, sequence_number=9),
        _candidate(sequence_number=1),
    )
    service = ApprovedSymbolReferenceService(MemoryRepository(game_id, raw))

    first = service.candidates(game_id, symbol_id, after_cursor=None, limit=2)
    second = service.candidates(game_id, symbol_id, after_cursor=first.next_cursor, limit=2)

    assert first.items[0].geometry_revision == 1
    assert {item.cell_review_id for item in first.items}.isdisjoint(
        item.cell_review_id for item in second.items
    )
    with pytest.raises(CatalogConflictError, match="invalid for this scope"):
        service.candidates(game_id, uuid4(), after_cursor=first.next_cursor, limit=2)


def test_select_rejects_stale_checksum_without_calling_repository():
    game_id, symbol_id = uuid4(), uuid4()
    candidate = _candidate()
    repository = MemoryRepository(game_id, (candidate,))
    service = ApprovedSymbolReferenceService(repository)

    with pytest.raises(CatalogConflictError, match="changed after it was loaded"):
        service.select(
            game_id,
            symbol_id,
            candidate.cell_review_id,
            expected_checksum_sha256="b" * 64,
            selected_by="admin",
        )


def test_select_materializes_the_virtual_render_into_a_content_addressed_reference(
    tmp_path, monkeypatch
):
    from game_predictor_api.application import symbol_references as module

    rendered = b"virtual-render-png"
    monkeypatch.setattr(module, "render_virtual_symbol_cell_png", lambda **_kwargs: rendered)
    game_id, symbol_id = uuid4(), uuid4()
    candidate = _candidate()
    checksum = candidate.crop_checksum_sha256
    rendered_checksum = hashlib.sha256(rendered).hexdigest()
    repository = MemoryRepository(game_id, (candidate,))
    service = ApprovedSymbolReferenceService(
        repository,
        ManagedSymbolReferenceArtifactStore(tmp_path),
    )

    selected = service.select(
        game_id,
        symbol_id,
        candidate.cell_review_id,
        expected_checksum_sha256=checksum,
        selected_by="admin",
    )

    destination = (
        tmp_path
        / "data"
        / "symbol-references"
        / str(game_id)
        / str(symbol_id)
        / f"{rendered_checksum}.png"
    )
    assert selected.image_path == "data/reference.png"
    assert destination.read_bytes() == rendered
