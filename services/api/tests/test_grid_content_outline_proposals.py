"""Symbol outline proposals from approved grids (D-608): pure cells and the HTTP contract."""

from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.grid_cell_content import (
    content_error_response,
    create_grid_cell_content_router,
)
from game_predictor_api.application.grid_cell_content import GridCellContentService
from game_predictor_api.domain.grid_cell_content import ContentError
from game_predictor_api.domain.grid_content_outline_proposals import outline_proposal_cells
from game_predictor_api.schemas.grid_cell_content import ContentWriteCommand


def lattice(x0=100.0, y0=50.0, width=50.0, height=40.0):
    return [{"x": x0 + c * width, "y": y0 + r * height} for r in range(4) for c in range(6)]


def test_grid_cells_become_visible_outlines_in_board_order():
    cells = outline_proposal_cells(lattice(), 1000, 800)
    assert cells is not None and len(cells) == 15
    assert all(cell.state == "visible" for cell in cells)
    # Row 1, column 1 and row 3, column 5 (cell 14) span the matching lattice nodes.
    assert cells[0].quad == ((100.0, 50.0), (150.0, 50.0), (150.0, 90.0), (100.0, 90.0))
    assert cells[14].quad == ((300.0, 130.0), (350.0, 130.0), (350.0, 170.0), (300.0, 170.0))


def test_points_outside_the_photo_are_clamped_to_the_frame():
    cells = outline_proposal_cells(lattice(x0=-10.0, y0=-5.0), 400, 300)
    assert cells is not None
    assert cells[0].quad[0] == (0.0, 0.0)
    assert all(0 <= x <= 400 and 0 <= y <= 300 for cell in cells for x, y in cell.quad or ())


def test_unusable_grids_give_no_partial_proposal():
    assert outline_proposal_cells(None, 100, 100) is None
    assert outline_proposal_cells(lattice()[:23], 1000, 800) is None
    assert outline_proposal_cells([{"x": 1.0}] * 24, 1000, 800) is None
    collapsed = lattice()
    collapsed[1] = dict(collapsed[0])  # cell 0 loses its top edge -> not a convex quad
    assert outline_proposal_cells(collapsed, 1000, 800) is None


def test_proposal_cells_are_a_valid_approved_write():
    source, cells = uuid4(), outline_proposal_cells(lattice(), 1000, 800)
    assert cells is not None
    command = ContentWriteCommand.model_validate(
        {
            "idempotencyKey": str(uuid4()),
            "sourceId": str(source),
            "expectedSourceSha256": "a" * 64,
            "expectedPixelSha256": "b" * 64,
            "positionIndex": 0,
            "sequenceNumber": 7,
            "expectedRevision": 0,
            "cells": [cell.model_dump(mode="json") for cell in cells],
            "origin": "manual",
            "humanApproval": True,
        }
    )
    assert command.humanApproval and len(command.cells) == 15


def test_outline_proposal_page_http_contract(tmp_path):
    game, board, source = uuid4(), uuid4(), uuid4()
    calls = []
    cells = outline_proposal_cells(lattice(), 1000, 800)

    class Repository:
        def list_outline_proposals(self, game_id, view, limit, offset):
            calls.append((game_id, view, limit, offset))
            return {
                "gameId": game_id,
                "view": view,
                "counts": {"todo": 1, "approved": 0},
                "items": [
                    {
                        "boardId": board,
                        "source": {
                            "sourceId": source,
                            "sourceSha256": "a" * 64,
                            "sourceRepresentativeSha256": "b" * 64,
                            "width": 1000,
                            "height": 800,
                        },
                        "positionIndex": 2,
                        "sequenceNumber": 7,
                        "contentRevision": 0,
                        "contentApproved": False,
                        "cells": cells,
                    }
                ],
                "offset": offset,
                "nextOffset": None,
            }

    service = SimpleNamespace(grid_cell_content=GridCellContentService(Repository()))
    app = FastAPI()

    @app.exception_handler(ContentError)
    async def handle_content(_request, error):
        return content_error_response(error)

    app.include_router(create_grid_cell_content_router(lambda: service), prefix="/api/v1")
    path = f"/api/v1/admin/games/{game}/grid-quality-measurements/content-outline-proposals"
    with TestClient(app) as client:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["version"] == "grid-cell-outline-proposal-v1"
        assert body["items"][0]["cells"][0]["state"] == "visible"
        assert len(body["items"][0]["cells"]) == 15
        assert calls[-1][1:] == ("todo", 48, 0)
        approved = {"view": "approved", "limit": 60, "offset": 96}
        assert client.get(path, params=approved).status_code == 200
        assert calls[-1][1:] == ("approved", 60, 96)
        for params in ({"view": "rejected"}, {"limit": 61}, {"limit": 0}, {"offset": -1}):
            assert client.get(path, params=params).status_code == 422
        assert len(calls) == 2
