from __future__ import annotations

import hashlib
import io
import os
import threading
from collections.abc import Mapping
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from game_predictor_api.application.board_search_board_detail import (
    BoardSearchBoardViewCache,
    BoardSearchBoardViewService,
    render_board_view,
)
from game_predictor_api.config import ApiSettings
from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_board_detail import (
    BoardSearchBoardDocument,
    BoardSearchBoardViewSource,
    BoardViewCrop,
    PaylineLabel,
)
from game_predictor_api.main import create_app
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from PIL import Image

_GAME_ID = uuid4()
_CHECKSUM = "c" * 64
_LATTICE = [[100, 200], [600, 200], [600, 500], [100, 500]]


def _write_source(artifact_root: Path, relative: str = "imports/source.png") -> str:
    path = artifact_root / "data" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (2000, 1000), (200, 40, 40)).save(path, format="PNG")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ViewRepository:
    def __init__(
        self,
        *,
        image_relative_path: str,
        image_checksum: str,
        geometry: Mapping[str, object] | None = None,
        current_checksum: str = _CHECKSUM,
        asset_mode: BoardSearchAssetMode = BoardSearchAssetMode.OPERATIONAL_REVIEW,
    ) -> None:
        self._source = BoardSearchBoardViewSource(
            image_relative_path=image_relative_path,
            image_checksum_sha256=image_checksum,
            geometry=geometry if geometry is not None else {"latticeBoundsQuad": _LATTICE},
            current_board_checksum_sha256=current_checksum,
        )
        self._asset_mode = asset_mode

    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None:
        return None

    def board_document(
        self, *, game_id: UUID, sequence_number: int
    ) -> tuple[BoardSearchAssetMode, BoardSearchBoardDocument | None]:
        if sequence_number != 7:
            return self._asset_mode, None
        return self._asset_mode, BoardSearchBoardDocument(
            sequence_number=7,
            status="accepted",
            board_checksum_sha256=_CHECKSUM,
            mobile_codes=(1,) * 15,
            asset_mode=self._asset_mode,
            review_item_id=uuid4(),
        )

    def board_view_source(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> BoardSearchBoardViewSource | None:
        return self._source

    def payline_labels(self, rules_version_id: UUID) -> Mapping[str, PaylineLabel]:
        return {}

    def symbol_codes(self, game_id: UUID) -> Mapping[int, str]:
        return {}

    def board_cells(self, *, game_id: UUID, document: BoardSearchBoardDocument) -> tuple[()]:
        return ()

    def refresh_board_document(self, *, game_id: UUID, document: BoardSearchBoardDocument) -> None:
        raise AssertionError("the view never refreshes a document")


class CountingRender:
    def __init__(self) -> None:
        self.calls = 0
        self._lock = threading.Lock()

    def __call__(self, path: Path, crop: BoardViewCrop | None) -> bytes:
        with self._lock:
            self.calls += 1
        return render_board_view(path, crop)


def _service(
    tmp_path: Path, repository: ViewRepository, render: CountingRender | None = None
) -> BoardSearchBoardViewService:
    return BoardSearchBoardViewService(
        repository, BoardSearchBoardViewCache(tmp_path), render=render
    )


def test_view_is_a_cropped_webp_and_the_second_read_comes_from_the_cache(
    tmp_path: Path,
) -> None:
    checksum = _write_source(tmp_path)
    render = CountingRender()
    service = _service(
        tmp_path,
        ViewRepository(image_relative_path="imports/source.png", image_checksum=checksum),
        render,
    )
    first = service.view(
        game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM
    )
    second = service.view(
        game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM
    )
    assert render.calls == 1
    assert first.media_type == "image/webp"
    assert first.content == second.content
    assert first.revision == second.revision
    content = first.content
    with Image.open(io.BytesIO(content)) as image:
        assert image.format == "WEBP"
        # Board 500 x 300 plus 20% padding on every side.
        assert image.size == (700, 420)
    cached = list((tmp_path / "data" / "working" / "board-search-views-v1").glob("*.webp"))
    assert [path.stem for path in cached] == [first.revision]


def test_parallel_requests_render_the_view_once(tmp_path: Path) -> None:
    checksum = _write_source(tmp_path)
    render = CountingRender()
    service = _service(
        tmp_path,
        ViewRepository(image_relative_path="imports/source.png", image_checksum=checksum),
        render,
    )
    results: list[bytes] = []

    def read() -> None:
        results.append(
            service.view(
                game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM
            ).content
        )

    threads = [threading.Thread(target=read) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert len(results) == 6 and len(set(results)) == 1
    assert render.calls == 1


def test_board_outside_the_photo_is_padded_not_rejected(tmp_path: Path) -> None:
    checksum = _write_source(tmp_path)
    service = _service(
        tmp_path,
        ViewRepository(
            image_relative_path="imports/source.png",
            image_checksum=checksum,
            geometry={"latticeBoundsQuad": [[-200, -100], [300, -100], [300, 200], [-200, 200]]},
        ),
    )
    asset = service.view(
        game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM
    )
    with Image.open(io.BytesIO(asset.content)) as image:
        assert image.size == (700, 420)


@pytest.mark.parametrize(
    ("repository_kwargs", "expected_checksum", "code"),
    [
        ({}, "f" * 64, "BOARD_SEARCH_BOARD_REVISION_CONFLICT"),
        ({"current_checksum": "e" * 64}, _CHECKSUM, "BOARD_SEARCH_BOARD_REVISION_CONFLICT"),
        (
            {"image_relative_path": "../escape.png"},
            _CHECKSUM,
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_PATH_UNSAFE",
        ),
        (
            {"image_relative_path": "imports/missing.png"},
            _CHECKSUM,
            "BOARD_SEARCH_BOARD_VIEW_SOURCE_NOT_FOUND",
        ),
        ({"image_checksum": "0" * 64}, _CHECKSUM, "BOARD_SEARCH_BOARD_VIEW_SOURCE_CHECKSUM_DRIFT"),
        ({"geometry": {"cells": []}}, _CHECKSUM, "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE"),
    ],
)
def test_view_fails_closed(
    tmp_path: Path,
    repository_kwargs: dict[str, object],
    expected_checksum: str,
    code: str,
) -> None:
    checksum = _write_source(tmp_path)
    arguments: dict[str, object] = {
        "image_relative_path": "imports/source.png",
        "image_checksum": checksum,
        **repository_kwargs,
    }
    service = _service(tmp_path, ViewRepository(**arguments))  # type: ignore[arg-type]
    with pytest.raises(BoardSearchError) as raised:
        service.view(
            game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=expected_checksum
        )
    assert raised.value.code == code


def test_view_endpoint_serves_an_immutable_webp_and_maps_errors(tmp_path: Path) -> None:
    checksum = _write_source(tmp_path)
    repository = ViewRepository(image_relative_path="imports/source.png", image_checksum=checksum)
    cache = BoardSearchBoardViewCache(tmp_path)
    app = create_app(
        ApiSettings.from_environment(
            {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
        ),
        board_search_board_view_service_dependency=lambda: BoardSearchBoardViewService(
            repository, cache
        ),
    )
    client = TestClient(app)
    url = f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/7/view"
    response = client.get(url, params={"expectedBoardChecksumSha256": _CHECKSUM})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "image/webp"
    # Without the view revision the browser must revalidate.
    assert response.headers["cache-control"] == "private, no-cache"
    etag = response.headers["etag"]
    revision = etag.strip('"')
    revalidated = client.get(
        url,
        params={"expectedBoardChecksumSha256": _CHECKSUM},
        headers={"If-None-Match": etag},
    )
    assert revalidated.status_code == 304
    pinned = client.get(
        url, params={"expectedBoardChecksumSha256": _CHECKSUM, "viewRevision": revision}
    )
    assert pinned.status_code == 200
    assert "immutable" in pinned.headers["cache-control"]
    stale = client.get(
        url, params={"expectedBoardChecksumSha256": _CHECKSUM, "viewRevision": "0" * 64}
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "BOARD_SEARCH_BOARD_REVISION_CONFLICT"
    conflict = client.get(url, params={"expectedBoardChecksumSha256": "a" * 64})
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "BOARD_SEARCH_BOARD_REVISION_CONFLICT"
    missing = client.get(
        f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/8/view",
        params={"expectedBoardChecksumSha256": _CHECKSUM},
    )
    assert missing.status_code == 404
    assert missing.json()["code"] == "BOARD_SEARCH_BOARD_NOT_FOUND"
    invalid = client.get(url, params={"expectedBoardChecksumSha256": "nope"})
    assert invalid.status_code == 422


def test_a_changed_grid_with_the_same_board_checksum_gets_a_new_view_revision(
    tmp_path: Path,
) -> None:
    """A v19 re-crop rewrites a legacy_file board's geometry but keeps its
    board checksum; the view revision (and so the image URL) must change."""

    checksum = _write_source(tmp_path)
    cache = BoardSearchBoardViewCache(tmp_path)
    before = BoardSearchBoardViewService(
        ViewRepository(image_relative_path="imports/source.png", image_checksum=checksum),
        cache,
    ).view(game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM)
    moved = ViewRepository(
        image_relative_path="imports/source.png",
        image_checksum=checksum,
        geometry={"latticeBoundsQuad": [[120, 200], [620, 200], [620, 500], [120, 500]]},
    )
    service = BoardSearchBoardViewService(moved, cache)
    with pytest.raises(BoardSearchError) as raised:
        service.view(
            game_id=_GAME_ID,
            sequence_number=7,
            expected_board_checksum_sha256=_CHECKSUM,
            expected_view_revision=before.revision,
        )
    assert raised.value.code == "BOARD_SEARCH_BOARD_REVISION_CONFLICT"
    after = service.view(
        game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM
    )
    assert after.revision != before.revision


def test_view_source_errors_map_to_http_codes(tmp_path: Path) -> None:
    checksum = _write_source(tmp_path)
    cache = BoardSearchBoardViewCache(tmp_path)
    cases = {
        "../escape.png": (409, "BOARD_SEARCH_BOARD_VIEW_SOURCE_PATH_UNSAFE"),
        "imports/missing.png": (404, "BOARD_SEARCH_BOARD_VIEW_SOURCE_NOT_FOUND"),
    }
    for relative, (status, code) in cases.items():
        repository = ViewRepository(image_relative_path=relative, image_checksum=checksum)
        app = create_app(
            ApiSettings.from_environment(
                {"GAME_PREDICTOR_REMOTE_SELECTION_HOST_MAPPING_ENABLED": "false"}
            ),
            board_search_board_view_service_dependency=(
                lambda repository=repository: BoardSearchBoardViewService(repository, cache)
            ),
        )
        response = TestClient(app).get(
            f"/api/v1/admin/games/{_GAME_ID}/board-search/boards/7/view",
            params={"expectedBoardChecksumSha256": _CHECKSUM},
        )
        assert response.status_code == status
        assert response.json()["code"] == code


def test_a_symlinked_cache_root_is_refused(tmp_path: Path) -> None:
    checksum = _write_source(tmp_path)
    target = tmp_path / "elsewhere"
    target.mkdir()
    root = tmp_path / "data" / "working" / "board-search-views-v1"
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        root.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Symbolic links are not permitted for this user.")
    service = _service(
        tmp_path, ViewRepository(image_relative_path="imports/source.png", image_checksum=checksum)
    )
    with pytest.raises(BoardSearchError) as raised:
        service.view(game_id=_GAME_ID, sequence_number=7, expected_board_checksum_sha256=_CHECKSUM)
    assert raised.value.code == "BOARD_SEARCH_BOARD_VIEW_CACHE_UNSAFE"


def test_the_cache_prunes_least_recently_used_views(tmp_path: Path) -> None:
    cache = BoardSearchBoardViewCache(tmp_path, max_cache_bytes=25)
    cache.write("a" * 64, b"x" * 10)
    cache.write("b" * 64, b"y" * 10)
    # Deterministic recency: coarse file times on Windows could otherwise tie.
    os.utime(cache.root / f"{'a' * 64}.webp", (1_000, 1_000))
    os.utime(cache.root / f"{'b' * 64}.webp", (2_000, 2_000))
    assert cache.read("a" * 64) is not None  # refreshes "a" to now
    cache.write("c" * 64, b"z" * 10)
    assert cache.read("b" * 64) is None
    assert cache.read("a" * 64) == b"x" * 10
    assert cache.read("c" * 64) == b"z" * 10


def test_exif_rotated_sources_are_rendered_upright(tmp_path: Path) -> None:
    path = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[0x0112] = 6
    Image.new("RGB", (300, 100), (10, 200, 10)).save(path, format="JPEG", exif=exif)
    content = render_board_view(path, None)
    with Image.open(io.BytesIO(content)) as image:
        assert image.size == (100, 300)
