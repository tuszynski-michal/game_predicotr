import hashlib
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardQueue,
    ImageGeometryGuardReportReconstructionInput,
)
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardContext,
    ImageGeometryGuardBoardTarget,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job
from PIL import Image

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
            boards=(
                ImageGeometryGuardBoardContext(
                    source_checksum_sha256="d" * 64,
                    source_relative_path="seq_20530-20538.jpg",
                    position_index=2,
                    sequence_number=20532,
                    page_geometry={"quad": []},
                    requires_decision=True,
                ),
            ),
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

    def report_reconstruction_input(
        self, **_kwargs: object
    ) -> ImageGeometryGuardReportReconstructionInput:
        return ImageGeometryGuardReportReconstructionInput(
            source_guard_job_id=JOB_ID,
            legacy_report_checksum_sha256="a" * 64,
            source_manifest_checksum_sha256="b" * 64,
            page_geometry_manifest_checksum_sha256="c" * 64,
        )


class _JobService:
    def __init__(self) -> None:
        self.job: Job | None = None

    def create_geometry_guard_report_reconstruction_job(self, **values: object) -> Job:
        self.job = create_job(
            JobType.VALIDATE,
            game_id=GAME_ID,
            input_payload={
                "schema_version": 1,
                "validation_kind": "image_geometry_guard_report_reconstruction",
                "source_selection_id": str(values["source_selection_id"]),
                "source_guard_job_id": str(values["source_guard_job_id"]),
                "legacy_report_checksum_sha256": values["legacy_report_checksum_sha256"],
                "source_manifest_checksum_sha256": values["source_manifest_checksum_sha256"],
                "page_geometry_manifest_checksum_sha256": values[
                    "page_geometry_manifest_checksum_sha256"
                ],
            },
        )
        return self.job


class _PreviewGuardService(_GuardService):
    def __init__(self, checksum: str) -> None:
        self.checksum = checksum

    def queue(self, **_kwargs: object) -> ImageGeometryGuardQueue:
        base = super().queue()
        target = base.targets[0]
        board = base.boards[0]
        return ImageGeometryGuardQueue(
            game_id=base.game_id,
            browser_selection_id=base.browser_selection_id,
            guard_job_id=base.guard_job_id,
            guard_report_checksum_sha256=base.guard_report_checksum_sha256,
            source_manifest_checksum_sha256=base.source_manifest_checksum_sha256,
            page_geometry_manifest_checksum_sha256=(base.page_geometry_manifest_checksum_sha256),
            boards=(
                ImageGeometryGuardBoardContext(
                    source_checksum_sha256=self.checksum,
                    source_relative_path=board.source_relative_path,
                    position_index=board.position_index,
                    sequence_number=board.sequence_number,
                    page_geometry={"quad": _preview_quad()},
                    requires_decision=True,
                ),
            ),
            targets=(
                ImageGeometryGuardBoardTarget(
                    source_checksum_sha256=self.checksum,
                    source_relative_path=target.source_relative_path,
                    position_index=target.position_index,
                    sequence_number=target.sequence_number,
                    reason_codes=target.reason_codes,
                    page_geometry={"quad": _preview_quad()},
                    analysis_quad=_preview_quad(),
                    proposed_symbol_grid_quad=_preview_quad(),
                    evidence=target.evidence,
                ),
            ),
            decisions=(),
        )


def _preview_quad() -> list[dict[str, int]]:
    return [
        {"x": 0, "y": 0},
        {"x": 299, "y": 0},
        {"x": 299, "y": 179},
        {"x": 0, "y": 179},
    ]

    def get_job(self, _job_id: UUID) -> Job:
        assert self.job is not None
        return self.job


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
    assert payload["boards"] == [
        {
            "sourceChecksumSha256": "d" * 64,
            "sourceRelativePath": "seq_20530-20538.jpg",
            "positionIndex": 2,
            "sequenceNumber": 20532,
            "pageGeometry": {"quad": []},
            "requiresDecision": True,
        }
    ]
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


def test_legacy_report_reconstruction_is_started_as_a_separate_job(tmp_path: Path) -> None:
    job_service = _JobService()
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            _unused,
            _unused,
            lambda: job_service,
            _unused,
            _unused,
            _unused,
            lambda: _GuardService(),
            tmp_path,
        )
    )

    response = TestClient(app).post(
        f"/admin/image-imports/browser-selections/{UPLOAD_ID}/geometry-guards/{JOB_ID}/report-reconstruction",
        json={"gameId": str(GAME_ID)},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["created"] is True
    assert payload["job"]["jobType"] == "validate"
    assert payload["job"]["inputPayload"]["sourceGuardJobId"] == str(JOB_ID)


def test_guard_decision_preview_reads_exact_staging_bytes_and_returns_fifteen_cells(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.jpg"
    Image.new("RGB", (300, 180), color=(160, 30, 20)).save(source_path, format="JPEG")
    content = source_path.read_bytes()
    checksum = hashlib.sha256(content).hexdigest()
    browser_service = SimpleNamespace(
        bind_ready_game=lambda _upload_id, _game_id: SimpleNamespace(
            upload=SimpleNamespace(path=tmp_path),
            manifest=SimpleNamespace(
                files=(
                    SimpleNamespace(
                        checksum_sha256=checksum,
                        relative_path="seq_20530-20538.jpg",
                        size_bytes=len(content),
                        stored_file_name=source_path.name,
                    ),
                )
            ),
        )
    )
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            _unused,
            lambda: browser_service,
            _unused,
            _unused,
            _unused,
            _unused,
            lambda: _PreviewGuardService(checksum),
            tmp_path,
        )
    )

    response = TestClient(app).post(
        f"/admin/image-imports/browser-selections/{UPLOAD_ID}/geometry-guards/{JOB_ID}/preview",
        json={
            "gameId": str(GAME_ID),
            "sourceChecksumSha256": checksum,
            "positionIndex": 2,
            "symbolGridQuad": _preview_quad(),
            "unavailableCellIndices": [14],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["cells"]) == 15
    assert payload["cells"][0]["currentDataUrl"].startswith("data:image/jpeg;base64,")
    assert payload["cells"][14] == {
        "cellIndex": 14,
        "sourceUnavailable": True,
        "currentDataUrl": None,
        "proposedDataUrl": None,
    }
