from pathlib import Path
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardQueue,
    ImageGeometryGuardReportReconstructionInput,
)
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardTarget,
)
from game_predictor_api.domain.jobs import Job, JobType, create_job

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
