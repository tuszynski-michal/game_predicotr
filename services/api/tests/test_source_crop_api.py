"""TASK-1046 (D-562): serving, decoders and gates of the API for cropped originals."""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.image_review_assets import (
    SOURCE_FRAME_PREVIEW_DIRECTORY,
    resolve_grid_review_source_asset,
    resolve_grid_review_source_path,
)
from game_predictor_api.application.managed_reprocess_evidence import (
    ManagedReprocessEvidenceError,
    require_full_managed_originals,
    resolve_managed_browser_selection,
    resolve_managed_page_source,
)
from game_predictor_api.application.virtual_cell_previews import render_spec_cell_rgb
from game_predictor_api.domain.board_topology import BoardTopology
from game_predictor_api.domain.canonical_source import (
    CanonicalSourceCrop,
    CanonicalSourceFrame,
    CanonicalSourceLoadError,
    rgb_pixel_checksum_sha256,
)
from game_predictor_api.domain.grid_training_cohorts import GridCohortError
from game_predictor_api.domain.image_geometry_v2 import NormalizedSourceImage
from game_predictor_api.domain.image_grid_reviews import ImageGridReviewSourceAsset
from game_predictor_api.domain.image_reviews import ImageReviewNotFoundError
from game_predictor_api.domain.source_crop import (
    PixelBox,
    ProtectedBox,
    SourceCropAttestation,
    compose_canvas,
    cropped_original_relative_paths,
    encode_attestation,
)
from game_predictor_api.storage.grid_training_cohort_artifacts import GridCohortArtifactStore
from numpy.typing import NDArray
from PIL import Image, ImageOps
from test_managed_reprocess_evidence import _terminal_import, _write_managed_manifest

_TOOL = "libjpeg-turbo version 3.2.0 (build 20260630)"
_BOX = PixelBox(16, 24, 112, 88)


def _jpeg(rgb: NDArray[np.uint8]) -> bytes:
    """4:4:4 quality 100: equal 8x8 input blocks decode to equal blocks."""

    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="JPEG", quality=100, subsampling=0)
    return buffer.getvalue()


def _decode(content: bytes) -> NDArray[np.uint8]:
    with Image.open(io.BytesIO(content)) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB"), dtype=np.uint8)


def _managed(root: Path, *, crop: bool = True) -> tuple[str, NDArray[np.uint8]]:
    """A managed original (removed when ``crop``) and its attested crop."""

    rgb = np.random.default_rng(3).integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    original = _jpeg(rgb)
    checksum = hashlib.sha256(original).hexdigest()
    oriented = _decode(original)
    path = root / "data" / "originals" / checksum[:2] / f"{checksum}.jpg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(original)
    if not crop:
        return checksum, oriented
    crop_bytes = _jpeg(np.ascontiguousarray(rgb[_BOX.top : _BOX.bottom, _BOX.left : _BOX.right]))
    crop_rgb = _decode(crop_bytes)
    canvas = compose_canvas(crop_rgb, crop_box=_BOX, width=128, height=96)
    attestation = SourceCropAttestation(
        original_checksum_sha256=checksum,
        original_size_bytes=len(original),
        original_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(oriented),
        original_width=128,
        original_height=96,
        original_exif_orientation=None,
        crop_checksum_sha256=hashlib.sha256(crop_bytes).hexdigest(),
        crop_size_bytes=len(crop_bytes),
        crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(crop_rgb),
        canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
        crop_box=_BOX,
        raw_crop_box=_BOX,
        protected_box=ProtectedBox(40.0, 40.0, 80.0, 72.0),
        margin_px=0,
        imcu_width=8,
        imcu_height=8,
        edge_mismatch_pixels=0,
        tool_version=_TOOL,
    )
    crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
    data = root / "data"
    data.joinpath(*crop_relative.parts).parent.mkdir(parents=True, exist_ok=True)
    data.joinpath(*crop_relative.parts).write_bytes(crop_bytes)
    data.joinpath(*attestation_relative.parts).write_bytes(encode_attestation(attestation))
    path.unlink()
    return checksum, oriented


def _grid_asset(checksum: str) -> ImageGridReviewSourceAsset:
    return ImageGridReviewSourceAsset(
        review_item_id=uuid4(),
        source_image_id=uuid4(),
        source_relative_path=f"originals/{checksum[:2]}/{checksum}.jpg",
        source_checksum_sha256=checksum,
        source_width=128,
        source_height=96,
        geometry_revision=0,
        resolution_revision=0,
        topology=BoardTopology(rows=3, columns=5),
    )


def test_a_present_original_is_served_unchanged(tmp_path: Path) -> None:
    checksum, _oriented = _managed(tmp_path, crop=False)

    asset = resolve_grid_review_source_asset(_grid_asset(checksum), tmp_path)

    assert asset.path.name == f"{checksum}.jpg"
    assert hashlib.sha256(asset.path.read_bytes()).hexdigest() == checksum


def test_a_cropped_source_is_served_as_a_full_frame_preview(tmp_path: Path) -> None:
    checksum, oriented = _managed(tmp_path)

    first = resolve_grid_review_source_asset(_grid_asset(checksum), tmp_path)
    second = resolve_grid_review_source_asset(_grid_asset(checksum), tmp_path)

    assert first.path == second.path and first.media_type == "image/jpeg"
    assert first.path.parent == (tmp_path / "data" / SOURCE_FRAME_PREVIEW_DIRECTORY).resolve()
    served = _decode(first.path.read_bytes())
    assert served.shape == oriented.shape
    inner = served[_BOX.top + 8 : _BOX.bottom - 8, _BOX.left + 8 : _BOX.right - 8]
    expected = oriented[_BOX.top + 8 : _BOX.bottom - 8, _BOX.left + 8 : _BOX.right - 8]
    # A lossy JPEG of noise: compare the region's brightness, not its pixels.
    assert abs(float(inner.mean()) - float(expected.mean())) < 5.0
    assert int(served[:8, :8].max()) < 16  # the fill outside the crop


def test_the_loader_path_stays_the_managed_original(tmp_path: Path) -> None:
    checksum, _oriented = _managed(tmp_path)

    path = resolve_grid_review_source_path(_grid_asset(checksum), tmp_path)

    assert path == (tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg").resolve()
    assert not path.exists()


def test_a_tampered_attestation_is_not_served(tmp_path: Path) -> None:
    checksum, _oriented = _managed(tmp_path)
    _, attestation_relative = cropped_original_relative_paths(checksum)
    path = tmp_path.joinpath("data", *attestation_relative.parts)
    document = json.loads(path.read_bytes())
    document["marginPx"] = 7
    path.write_bytes(json.dumps(document).encode())

    with pytest.raises(ImageReviewNotFoundError) as error:
        resolve_grid_review_source_asset(_grid_asset(checksum), tmp_path)
    assert error.value.code == "IMAGE_REVIEW_ASSET_NOT_FOUND"


def test_a_missing_original_without_crop_is_not_found(tmp_path: Path) -> None:
    checksum, _oriented = _managed(tmp_path, crop=False)
    (tmp_path / "data" / "originals" / checksum[:2] / f"{checksum}.jpg").unlink()

    with pytest.raises(ImageReviewNotFoundError):
        resolve_grid_review_source_asset(_grid_asset(checksum), tmp_path)
    with pytest.raises(ImageReviewNotFoundError):
        resolve_grid_review_source_path(_grid_asset(checksum), tmp_path)


def test_a_stored_render_spec_is_refused_outside_the_crop() -> None:
    rgb = np.random.default_rng(9).integers(0, 256, size=(96, 128, 3), dtype=np.uint8)
    region = np.ascontiguousarray(rgb[_BOX.top : _BOX.bottom, _BOX.left : _BOX.right])
    canvas = compose_canvas(region, crop_box=_BOX, width=128, height=96)
    source = NormalizedSourceImage(
        source_checksum_sha256="a" * 64,
        normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(rgb),
        width=128,
        height=96,
        exif_orientation=None,
        normalization_adapter_version="image-normalization-v2-in-memory-source-v1",
    )
    frame = CanonicalSourceFrame(
        source=source,
        raw_width=128,
        raw_height=96,
        source_mode="RGB",
        orientation_action="none",
        rgb=canvas,
        crop=CanonicalSourceCrop(
            SourceCropAttestation(
                original_checksum_sha256="a" * 64,
                original_size_bytes=50_000,
                original_normalized_pixel_checksum_sha256=source.normalized_pixel_checksum_sha256,
                original_width=128,
                original_height=96,
                original_exif_orientation=None,
                crop_checksum_sha256="c" * 64,
                crop_size_bytes=20_000,
                crop_normalized_pixel_checksum_sha256=rgb_pixel_checksum_sha256(region),
                canvas_pixel_checksum_sha256=rgb_pixel_checksum_sha256(canvas),
                crop_box=_BOX,
                raw_crop_box=_BOX,
                protected_box=ProtectedBox(40.0, 40.0, 80.0, 72.0),
                margin_px=0,
                imcu_width=8,
                imcu_height=8,
                edge_mismatch_pixels=0,
                tool_version=_TOOL,
            )
        ),
    )

    def spec(quad: list[tuple[float, float]]) -> dict[str, object]:
        return {
            "configuration": {"outputWidth": 8, "outputHeight": 8},
            "paddedSourceQuad": [{"x": x, "y": y} for x, y in quad],
        }

    inside = render_spec_cell_rgb(
        render_spec=spec([(40, 40), (80, 40), (80, 72), (40, 72)]), frame=frame
    )
    assert inside.shape == (8, 8, 3)
    with pytest.raises(CanonicalSourceLoadError) as error:
        render_spec_cell_rgb(render_spec=spec([(4, 40), (80, 40), (80, 72), (4, 72)]), frame=frame)
    assert error.value.code == "SOURCE_REGION_UNAVAILABLE"


def test_a_v3_cohort_refuses_a_cropped_original(tmp_path: Path) -> None:
    checksum, _oriented = _managed(tmp_path)

    with pytest.raises(GridCohortError) as error:
        GridCohortArtifactStore(tmp_path).decode_source(
            {
                "relative_path": f"originals/{checksum[:2]}/{checksum}.jpg",
                "checksum_sha256": checksum,
            }
        )
    assert error.value.code == "SOURCE_ORIGINAL_CROPPED"


def test_reprocess_and_managed_page_sources_refuse_cropped_originals(tmp_path: Path) -> None:
    game_id, selection_id = uuid4(), uuid4()
    checksum, _oriented = _managed(tmp_path)
    source_job = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    _write_managed_manifest(tmp_path, source_job, source_checksum=checksum)

    for call in (
        lambda: require_full_managed_originals(source_job, artifact_root=tmp_path),
        lambda: resolve_managed_page_source(
            source_job,
            artifact_root=tmp_path,
            game_id=game_id,
            selection_id=selection_id,
            source_checksum_sha256=checksum,
        ),
        lambda: resolve_managed_browser_selection(
            source_job, artifact_root=tmp_path, game_id=game_id, selection_id=selection_id
        ),
    ):
        with pytest.raises(ManagedReprocessEvidenceError) as error:
            call()
        assert error.value.code == "SOURCE_ORIGINAL_CROPPED"


def test_reprocess_gate_accepts_present_originals(tmp_path: Path) -> None:
    game_id, selection_id = uuid4(), uuid4()
    checksum, _oriented = _managed(tmp_path, crop=False)
    source_job = _terminal_import(
        game_id,
        selection_id=selection_id,
        source_manifest_sha256="b" * 64,
        page_descriptor=None,
    )
    _write_managed_manifest(tmp_path, source_job, source_checksum=checksum)

    require_full_managed_originals(source_job, artifact_root=tmp_path)


def _grid_client(tmp_path: Path, checksum: str) -> tuple[TestClient, object]:
    from fastapi import FastAPI
    from game_predictor_api.api.image_grid_reviews import create_image_grid_reviews_router
    from game_predictor_api.application.image_geometry_rollout import (
        ImageGeometryRolloutService,
    )
    from game_predictor_api.application.image_grid_reviews import ImageGridReviewService
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewState
    from test_image_grid_review_api import (
        MemoryGridReviewRepository,
        MemoryImageGeometryRolloutRepository,
        UnusedVirtualGeometryService,
        _item,
    )

    game_id, import_job_id = uuid4(), uuid4()
    item = replace(
        _item(game_id, import_job_id, 1, ImageGridReviewState.NEEDS_VALIDATION),
        source_checksum_sha256=checksum,
        source_width=128,
        source_height=96,
    )
    repository = MemoryGridReviewRepository((item,), f"originals/{checksum[:2]}/{checksum}.jpg")
    app = FastAPI()
    app.include_router(
        create_image_grid_reviews_router(
            lambda: ImageGridReviewService(repository),
            lambda: ImageGeometryRolloutService(MemoryImageGeometryRolloutRepository(game_id)),
            lambda: UnusedVirtualGeometryService(),
            tmp_path,
        ),
        prefix="/api/v1",
    )
    return TestClient(app), item


@pytest.mark.parametrize("cropped", [False, True])
def test_the_grid_review_source_endpoint_serves_the_original_frame_size(
    tmp_path: Path, cropped: bool
) -> None:
    checksum, oriented = _managed(tmp_path, crop=cropped)
    client, item = _grid_client(tmp_path, checksum)

    response = client.get(
        f"/api/v1/admin/image-reviews/{item.review_item_id}/source-asset",  # type: ignore[attr-defined]
        params={
            "gameId": str(item.game_id),  # type: ignore[attr-defined]
            "expectedSourceChecksumSha256": checksum,
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, immutable, max-age=31536000"
    assert _decode(response.content).shape == oriented.shape
    if not cropped:
        assert hashlib.sha256(response.content).hexdigest() == checksum


def test_equal_crop_bytes_of_different_originals_get_separate_previews(tmp_path: Path) -> None:
    first_root, second_root = tmp_path / "a", tmp_path / "b"
    checksum, _oriented = _managed(first_root)
    shared = tmp_path / "shared"
    _managed(second_root)
    # Same crop bytes, attested at a different place of the same original.
    crop_relative, attestation_relative = cropped_original_relative_paths(checksum)
    document = json.loads(second_root.joinpath("data", *attestation_relative.parts).read_bytes())
    assert (
        document["crop"]["checksumSha256"]
        == json.loads(first_root.joinpath("data", *attestation_relative.parts).read_bytes())[
            "crop"
        ]["checksumSha256"]
    )
    one = resolve_grid_review_source_asset(_grid_asset(checksum), first_root)
    for root in (first_root, second_root):
        target = shared / "data"
        for relative in (crop_relative, attestation_relative):
            destination = target.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(root.joinpath("data", *relative.parts).read_bytes())
    two = resolve_grid_review_source_asset(_grid_asset(checksum), shared)
    assert one.path.name == two.path.name  # same attestation, same canvas
    data = shared / "data"
    attestation = json.loads(data.joinpath(*attestation_relative.parts).read_bytes())
    attestation["crop"]["edgeMismatchPixels"] = 1
    attestation.pop("attestationSha256")
    body = json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    attestation["attestationSha256"] = hashlib.sha256(body).hexdigest()
    data.joinpath(*attestation_relative.parts).write_bytes(
        json.dumps(attestation, sort_keys=True, separators=(",", ":")).encode()
    )
    three = resolve_grid_review_source_asset(_grid_asset(checksum), shared)
    assert three.path.name != two.path.name


def test_reprocess_http_refuses_a_cropped_original_without_creating_a_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_predictor_api.application.jobs import JobService
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.main import create_app
    from game_predictor_worker.images import lateral_partial_contract as contract
    from test_lateral_managed_reprocess import _setup

    repository, source, _descriptor, root = _setup(tmp_path, monkeypatch)
    checksum = "c" * 64
    for relative in cropped_original_relative_paths(checksum):
        path = root.joinpath("data", *relative.parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"attested crop placeholder")
    before = len(repository.items)
    client = TestClient(
        create_app(
            ApiSettings.from_environment({"GAME_PREDICTOR_ARTIFACT_ROOT": str(root)}),
            job_service_dependency=lambda: JobService(repository, artifact_root=root),
        )
    )

    with client:
        response = client.post(
            f"/api/v1/admin/image-imports/{source.id}/reprocess",
            params={
                "geometryEngineVariant": (
                    contract.GeometryEngineVariant.STRUCTURED_LATTICE_V4_PARTIAL_SIDES.value
                )
            },
            headers={"X-Admin-Target": f"image-import:{source.id}:reprocess"},
        )

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "SOURCE_ORIGINAL_CROPPED"
    assert len(repository.items) == before


@pytest.mark.parametrize("code", ["SOURCE_REGION_UNAVAILABLE", "SOURCE_ORIGINAL_CROPPED"])
def test_grid_review_crop_errors_are_conflicts(code: str) -> None:
    from game_predictor_api.config import ApiSettings
    from game_predictor_api.domain.image_grid_reviews import ImageGridReviewError
    from game_predictor_api.main import create_app

    app = create_app(ApiSettings.from_environment({}))

    def refuse() -> None:
        raise ImageGridReviewError(code, "outside the retained crop")

    app.add_api_route("/__crop-error", refuse)
    with TestClient(app) as client:
        response = client.get("/__crop-error")

    assert response.status_code == 409
    assert response.json()["code"] == code
