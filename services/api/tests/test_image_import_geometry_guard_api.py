from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardQueue,
)
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardTarget,
)

GAME_ID = UUID("11111111-1111-1111-1111-111111111111")
UPLOAD_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")


class _GuardService:
    def queue(self, **_kwargs: object) -> ImageGeometryGuardQueue:
        return ImageGeometryGuardQueue(
            game_id=GAME_ID,
            browser_selection_id=UPLOAD_ID,
            guard_job_id=JOB_ID,
            guard_report_checksum_sha256="a" * 64,
            source_manifest_checksum_sha256="b" * 64,
            page_geometry_manifest_checksum_sha256="c" * 64,
            targets=(
                ImageGeometryGuardBoardTarget(
                    source_checksum_sha256="d" * 64,
                    source_relative_path="seq_20530-20538.jpg",
                    position_index=2,
                    sequence_number=20532,
                    reason_codes=("incomplete_lattice",),
                    page_geometry={"quad": []},
                    analysis_quad=[],
                    proposed_symbol_grid_quad=None,
                    evidence={"supportedIntersectionCount": 12},
                ),
            ),
            decisions=(),
        )


def _unused() -> object:
    return object()


def test_board_exception_queue_is_exposed_by_the_http_contract(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            _unused,
            _unused,
            _unused,
            _unused,
            _unused,
            _unused,
            lambda: _GuardService(),
            tmp_path,
        )
    )

    response = TestClient(app).get(
        f"/admin/image-imports/browser-selections/{UPLOAD_ID}/geometry-guards/{JOB_ID}/boards",
        params={"game_id": str(GAME_ID)},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["unresolvedCount"] == 1
    assert payload["targets"] == [
        {
            "sourceChecksumSha256": "d" * 64,
            "sourceRelativePath": "seq_20530-20538.jpg",
            "positionIndex": 2,
            "sequenceNumber": 20532,
            "reasonCodes": ["incomplete_lattice"],
            "pageGeometry": {"quad": []},
            "analysisQuad": [],
            "proposedSymbolGridQuad": None,
            "evidence": {"supportedIntersectionCount": 12},
        }
    ]
    assert payload["decisions"] == []
