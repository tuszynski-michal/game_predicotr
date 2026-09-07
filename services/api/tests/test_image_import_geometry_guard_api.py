import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from game_predictor_api.api.image_imports import create_image_imports_router
from game_predictor_api.application.image_import_geometry_guard import (
    ImageGeometryGuardQueue,
    ImageGeometryGuardReportReconstructionInput,
)
from game_predictor_api.domain.geometry_qualification import GeometryQualification
from game_predictor_api.domain.image_import_geometry_guard import (
    ImageGeometryGuardBoardContext,
    ImageGeometryGuardBoardTarget,
    ImageGeometryGuardResolutionManifest,
)
from game_predictor_api.domain.jobs import Job, JobError, JobType, create_job
from PIL import Image

GAME_ID = UUID("11111111-1111-1111-1111-111111111111")
UPLOAD_ID = UUID("22222222-2222-2222-2222-222222222222")
JOB_ID = UUID("33333333-3333-3333-3333-333333333333")


class _GuardService:
    def __init__(
        self,
        *,
        page_geometry_preflight_job_id: UUID | None = None,
        current_resolution_manifest: ImageGeometryGuardResolutionManifest | None = None,
    ) -> None:
        self.page_geometry_preflight_job_id = page_geometry_preflight_job_id
        self.current_resolution_manifest = current_resolution_manifest

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
                    reason_codes=("incomplete_lattice",),
                    page_geometry={"quad": []},
                    analysis_quad=[],
                    symbol_grid_quad=None,
                    evidence={"supportedIntersectionCount": 12},
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
            page_geometry_preflight_job_id=self.page_geometry_preflight_job_id,
            current_resolution_manifest=self.current_resolution_manifest,
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


class _PreviewGuardService(_GuardService):
    def __init__(self, checksum: str) -> None:
        super().__init__()
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
                    reason_codes=board.reason_codes,
                    page_geometry={"quad": _preview_quad()},
                    analysis_quad=_preview_quad(),
                    symbol_grid_quad=_preview_quad(),
                    evidence=board.evidence,
                    requires_decision=True,
                ),
                ImageGeometryGuardBoardContext(
                    source_checksum_sha256=self.checksum,
                    source_relative_path=board.source_relative_path,
                    position_index=3,
                    sequence_number=20533,
                    reason_codes=(),
                    page_geometry={"quad": _preview_quad()},
                    analysis_quad=_preview_quad(),
                    symbol_grid_quad=_preview_quad(),
                    evidence={"supportedIntersectionCount": 15},
                    requires_decision=False,
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
            page_geometry_preflight_job_id=base.page_geometry_preflight_job_id,
            current_resolution_manifest=base.current_resolution_manifest,
        )


def _preview_quad() -> list[dict[str, int]]:
    return [
        {"x": 0, "y": 0},
        {"x": 299, "y": 0},
        {"x": 299, "y": 179},
        {"x": 0, "y": 179},
    ]


def _unused() -> object:
    return object()


def test_board_exception_queue_is_exposed_by_the_http_contract(tmp_path: Path) -> None:
    job_service = _JobService()
    job_service.job = create_job(
        JobType.VALIDATE,
        game_id=GAME_ID,
        input_payload={
            "schema_version": 2,
            "validation_kind": "page_geometry_preflight",
            "source_selection_id": str(UPLOAD_ID),
            "source_directory": str(tmp_path),
            "source_display_name": "fixture",
            "source_manifest_sha256": "b" * 64,
            "page_registration_profile": {},
        },
    )
    manifest = ImageGeometryGuardResolutionManifest(
        id=UUID("55555555-5555-5555-5555-555555555555"),
        game_id=GAME_ID,
        browser_selection_id=UPLOAD_ID,
        guard_job_id=JOB_ID,
        guard_report_checksum_sha256="a" * 64,
        source_manifest_checksum_sha256="b" * 64,
        page_geometry_manifest_checksum_sha256="c" * 64,
        manifest_relative_path="data/image-geometry-guard-resolutions/ee/fixture.json",
        manifest_checksum_sha256="e" * 64,
        decision_count=1,
        sealed_by="local-owner",
        created_at=datetime(2026, 9, 6, tzinfo=UTC),
    )
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            _unused,
            _unused,
            lambda: job_service,
            _unused,
            _unused,
            _unused,
            lambda: _GuardService(
                page_geometry_preflight_job_id=job_service.job.id,
                current_resolution_manifest=manifest,
            ),
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
            "reasonCodes": ["incomplete_lattice"],
            "pageGeometry": {"quad": []},
            "analysisQuad": [],
            "symbolGridQuad": None,
            "evidence": {"supportedIntersectionCount": 12},
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
    assert payload["pageGeometryPreflightJob"]["id"] == str(job_service.job.id)
    assert payload["currentResolutionManifest"]["id"] == str(manifest.id)


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


def test_guard_decision_preview_accepts_ready_board_from_same_review_source(
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
            "positionIndex": 3,
            "symbolGridQuad": _preview_quad(),
            "unavailableCellIndices": [],
        },
    )

    assert response.status_code == 200
    assert len(response.json()["cells"]) == 15


@pytest.mark.parametrize("tamper", (None, "bytes", "size"))
def test_qualified_save_uses_verified_exif_header_and_never_saves_tampered_source(tmp_path, tamper):
    path = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (300, 180)).save(path, exif=exif)
    original = path.read_bytes()
    checksum = hashlib.sha256(original).hexdigest()
    if tamper == "bytes":
        path.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
    browser = SimpleNamespace(
        bind_ready_game=lambda *_: SimpleNamespace(
            upload=SimpleNamespace(path=tmp_path),
            manifest=SimpleNamespace(
                files=(
                    SimpleNamespace(
                        checksum_sha256=checksum,
                        relative_path="seq_1-9.jpg",
                        stored_file_name=path.name,
                        size_bytes=len(original) + (1 if tamper == "size" else 0),
                    ),
                )
            ),
        )
    )
    guard = Mock()
    guard.save_decisions.return_value = ()
    app = FastAPI()
    app.include_router(
        create_image_imports_router(
            _unused,
            lambda: browser,
            _unused,
            _unused,
            _unused,
            _unused,
            lambda: guard,
            tmp_path,
        )
    )
    payload = dict(
        gameId=str(GAME_ID),
        expectedGuardReportChecksumSha256="a" * 64,
        actor="operator",
        decisions=[
            dict(
                sourceChecksumSha256=checksum,
                positionIndex=0,
                sequenceNumber=1,
                disposition="partial",
                unavailableCellIndices=[0, 5, 10],
                symbolGridQuad=[
                    {"x": x, "y": y} for x, y in ((-10, 10), (150, 10), (150, 200), (-10, 200))
                ],
                geometryQualification=GeometryQualification(
                    "pending_partial", (0, 5, 10), True, "missing_pixels"
                ).to_dict(),
            )
        ],
    )
    client = TestClient(app)
    url = f"/admin/image-imports/browser-selections/{UPLOAD_ID}/geometry-guards/{JOB_ID}/decisions"
    if tamper:
        with pytest.raises(JobError):
            client.post(url, json=payload)
        guard.save_decisions.assert_not_called()
    else:
        response = client.post(url, json=payload)
        assert response.status_code == 201, response.text
        assert guard.save_decisions.call_args.kwargs["source_dimensions"] == (180, 300)
        command = guard.save_decisions.call_args.kwargs["commands"][0]
        assert command.symbol_grid_quad[0]["x"] == -10
