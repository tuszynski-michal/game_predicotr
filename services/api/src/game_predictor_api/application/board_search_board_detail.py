"""Application boundary for one board's payline detail and cropped view (D-470).

`BoardSearchBoardDetailService` evaluates one board-search document with the
same published rules and payout-v3 evaluator as the range calculator and
returns the winning lines plus the cell polygons of a cropped view.
`BoardSearchBoardViewService` renders that cropped view as WebP through a
disposable, checksum-keyed file cache shared by the whole process.

Both refuse to pair a document with geometry of another revision: the
board's current identity checksum must equal the search document checksum,
so an `immutable` cached image never meets different polygons.
"""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import UUID

from game_predictor_worker.domain.errors import DomainValidationError
from game_predictor_worker.payouts.contracts import RulesPayoutConfiguration
from PIL import Image, ImageOps, UnidentifiedImageError

from game_predictor_api.application.board_search_approximate_win import (
    APPROXIMATE_WIN_PAYOUT_ALGORITHM_VERSION,
    prepare_approximate_win_evaluator,
)
from game_predictor_api.application.board_search_assets import resolve_board_search_image
from game_predictor_api.domain.board_search import BoardSearchAssetMode, BoardSearchError
from game_predictor_api.domain.board_search_board_detail import (
    BOARD_VIEW_MAX_CROP_PIXELS,
    BoardPayoutKind,
    BoardSearchBoardCell,
    BoardSearchBoardDocument,
    BoardSearchBoardView,
    BoardSearchBoardViewSource,
    BoardSearchLineMatch,
    BoardViewCrop,
    PaylineLabel,
    board_cell_quads,
    board_payout_kind,
    board_view,
    board_view_crop,
    board_view_revision,
    resized_view_size,
)

_UNKNOWN_MOBILE_CODE = 0
_VIEW_CACHE_DIRECTORY = "board-search-views-v1"
DEFAULT_BOARD_VIEW_CACHE_BYTES = 512 * 1024 * 1024
_VIEW_WEBP_QUALITY = 80
_VIEW_FILL = (20, 32, 45)
_VIEW_MAX_SOURCE_PIXELS = 100_000_000
_EXIF_ORIENTATION = 0x0112


class BoardSearchBoardDetailRepository(Protocol):
    def latest_published_rules(self, game_id: UUID) -> RulesPayoutConfiguration | None: ...

    def board_document(
        self, *, game_id: UUID, sequence_number: int
    ) -> tuple[BoardSearchAssetMode, BoardSearchBoardDocument | None]: ...

    def board_view_source(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> BoardSearchBoardViewSource | None: ...

    def payline_labels(self, rules_version_id: UUID) -> Mapping[str, PaylineLabel]: ...

    def symbol_codes(self, game_id: UUID) -> Mapping[int, str]: ...

    def board_cells(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> tuple[BoardSearchBoardCell, ...]: ...

    def refresh_board_document(
        self, *, game_id: UUID, document: BoardSearchBoardDocument
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BoardSearchBoardDetail:
    game_id: UUID
    sequence_number: int
    board_status: str
    board_checksum_sha256: str
    data_source: BoardSearchAssetMode
    rules_version_id: UUID
    rules_version: int
    spin_cost: int
    algorithm_version: str
    symbol_codes: tuple[str | None, ...]
    payout_credits: int
    payout_kind: BoardPayoutKind
    matches: tuple[BoardSearchLineMatch, ...]
    view: BoardSearchBoardView | None
    cells: tuple[BoardSearchBoardCell, ...] | None
    document_stale: bool


def _board_not_found() -> BoardSearchError:
    return BoardSearchError(
        "BOARD_SEARCH_BOARD_NOT_FOUND",
        "No board-search document exists for this sequence position.",
    )


def _revision_conflict() -> BoardSearchError:
    return BoardSearchError(
        "BOARD_SEARCH_BOARD_REVISION_CONFLICT",
        "The board changed since the search document was written; refresh the result.",
    )


def _load_document(
    repository: BoardSearchBoardDetailRepository,
    game_id: UUID,
    sequence_number: int,
) -> BoardSearchBoardDocument:
    _source, document = repository.board_document(game_id=game_id, sequence_number=sequence_number)
    if document is None:
        raise _board_not_found()
    return document


def _is_stale(
    source: BoardSearchBoardViewSource | None, document: BoardSearchBoardDocument
) -> bool:
    """The board's identity changed after its search document was written
    (e.g. a later grid revision the projection never picked up)."""

    return (
        source is not None
        and source.current_board_checksum_sha256 != document.board_checksum_sha256
    )


def _checked_view_source(
    repository: BoardSearchBoardDetailRepository,
    game_id: UUID,
    document: BoardSearchBoardDocument,
) -> BoardSearchBoardViewSource | None:
    source = repository.board_view_source(game_id=game_id, document=document)
    if _is_stale(source, document):
        raise _revision_conflict()
    return source


def _prepare_view(
    source: BoardSearchBoardViewSource,
    asset_mode: BoardSearchAssetMode,
    artifact_root: Path | None,
) -> tuple[BoardViewCrop | None, BoardSearchBoardView] | None:
    """Crop and view metadata for one board, or `None` without a usable view.

    Operational boards need a saved grid (their view is a crop of the photo).
    Archive boards are already single-board images: the view is the whole
    image, resized, with no cell polygons; its size comes from the header.
    """

    if asset_mode is BoardSearchAssetMode.OPERATIONAL_REVIEW:
        if source.geometry is None:
            return None
        quads = board_cell_quads(source.geometry)
        crop = None if quads is None else board_view_crop(quads)
        if quads is None or crop is None:
            return None
        revision = board_view_revision(source.image_checksum_sha256, crop)
        return crop, board_view(quads, crop, revision=revision)
    if artifact_root is None:
        return None
    try:
        image = resolve_board_search_image(
            source.image_relative_path,
            source.image_checksum_sha256,
            artifact_root,
            code_prefix="BOARD_SEARCH_BOARD_VIEW_SOURCE",
            verify_checksum=False,
        )
        with Image.open(image.path) as opened:
            width, height = opened.size
            if opened.getexif().get(_EXIF_ORIENTATION, 1) in {5, 6, 7, 8}:
                width, height = height, width
    except (BoardSearchError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        return None
    view_width, view_height = resized_view_size(width, height)
    return None, BoardSearchBoardView(
        width=view_width,
        height=view_height,
        revision=board_view_revision(source.image_checksum_sha256, None),
        cell_polygons=None,
    )


class BoardSearchBoardDetailService:
    def __init__(
        self,
        repository: BoardSearchBoardDetailRepository,
        *,
        artifact_root: Path | None = None,
    ) -> None:
        self._repository = repository
        self._artifact_root = artifact_root

    def detail(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        include_cells: bool = True,
    ) -> BoardSearchBoardDetail:
        """`include_cells=False` is the online share (D-471): cell records carry
        review identities and correction is Admin-only (D-473)."""
        if sequence_number < 1:
            raise _board_not_found()
        configuration = self._repository.latest_published_rules(game_id)
        if configuration is None:
            raise BoardSearchError(
                "APPROXIMATE_WIN_RULES_NOT_PUBLISHED",
                "The game has no published rules version to calculate payout against.",
            )
        evaluator = prepare_approximate_win_evaluator(game_id, configuration)
        document = _load_document(self._repository, game_id, sequence_number)
        try:
            evaluation = evaluator.evaluate(
                tuple(
                    _UNKNOWN_MOBILE_CODE if code is None else code for code in document.mobile_codes
                )
            )
        except DomainValidationError as error:
            raise BoardSearchError(
                "APPROXIMATE_WIN_BOARD_SYMBOL_OUTSIDE_RULES",
                (
                    "The board contains a symbol outside the active rules "
                    f"configuration ({error.code})."
                ),
            ) from error

        labels = self._repository.payline_labels(configuration.rules_version_id)
        codes = self._repository.symbol_codes(game_id)
        matches: list[BoardSearchLineMatch] = []
        for match in evaluation.matches:
            label = labels.get(match.payline_id)
            symbol_code = codes.get(match.symbol_mobile_code)
            if label is None or symbol_code is None:
                # Evaluator and labels come from the same rules version; a gap
                # here is a data defect, never a line to hide silently.
                raise BoardSearchError(
                    "APPROXIMATE_WIN_RULES_INVALID",
                    "A winning payline or symbol is missing from the published rules.",
                )
            matches.append(
                BoardSearchLineMatch(
                    payline_id=match.payline_id,
                    payline_code=label.code,
                    payline_name=label.name,
                    payline_display_order=label.display_order,
                    row_path=label.row_path,
                    symbol_code=symbol_code,
                    matched_length=match.matched_length,
                    matched_cells=tuple(match.matched_cells),
                    joker_cells=tuple(match.joker_cells),
                    payout_credits=match.payout_credits,
                )
            )
        matches.sort(key=lambda item: (item.payline_display_order, item.payline_code))

        source = self._repository.board_view_source(game_id=game_id, document=document)
        # A stale document still explains the table (both read it), but its
        # symbols belong to an older grid: no photo, no cell editing, and the
        # modal offers to refresh this one board (TASK-0773).
        stale = _is_stale(source, document)
        prepared = (
            None
            if source is None or stale
            else _prepare_view(source, document.asset_mode, self._artifact_root)
        )
        view = None if prepared is None else prepared[1]
        # Only a pending operational board is corrected cell by cell (D-462,
        # D-473); resolved boards read the whole-board decision instead.
        cells: tuple[BoardSearchBoardCell, ...] | None = None
        if (
            include_cells
            and document.asset_mode is BoardSearchAssetMode.OPERATIONAL_REVIEW
            and document.status == "pending"
            and not stale
        ):
            records = self._repository.board_cells(game_id=game_id, document=document)
            # Correction needs one current record per logical cell; a partial
            # set (e.g. mid-backfill) is offered as not editable.
            cells = records if len(records) == 15 else None

        return BoardSearchBoardDetail(
            game_id=game_id,
            sequence_number=document.sequence_number,
            board_status=document.status,
            board_checksum_sha256=document.board_checksum_sha256,
            data_source=document.asset_mode,
            rules_version_id=configuration.rules_version_id,
            rules_version=configuration.version,
            spin_cost=configuration.spin_cost,
            algorithm_version=APPROXIMATE_WIN_PAYOUT_ALGORITHM_VERSION,
            symbol_codes=tuple(
                None if code is None else codes.get(code) for code in document.mobile_codes
            ),
            payout_credits=evaluation.total_payout,
            payout_kind=board_payout_kind(evaluation.total_payout, document.mobile_codes),
            matches=tuple(matches),
            view=view,
            cells=cells,
            document_stale=stale,
        )

    def refresh(self, *, game_id: UUID, sequence_number: int) -> BoardSearchBoardRefreshResult:
        """Rebuild this board's search document from its current records.

        Uses the same projection sync the system runs after every cell or
        geometry decision, scoped to one board; it never changes a human
        decision. Only operational documents can be rebuilt.
        """

        if sequence_number < 1:
            raise _board_not_found()
        document = _load_document(self._repository, game_id, sequence_number)
        if document.asset_mode is not BoardSearchAssetMode.OPERATIONAL_REVIEW:
            raise BoardSearchError(
                "BOARD_SEARCH_BOARD_REFRESH_UNSUPPORTED",
                "Only operational board-search documents can be refreshed.",
            )
        self._repository.refresh_board_document(game_id=game_id, document=document)
        # The rebuild may legitimately leave no document at this position
        # (the board left the searchable states or moved in the sequence).
        # That outcome must be committed and reported, never turned into a
        # 404 that rolls the rebuild back.
        _source, refreshed = self._repository.board_document(
            game_id=game_id, sequence_number=sequence_number
        )
        if refreshed is None:
            return BoardSearchBoardRefreshResult(detail=None, document_removed=True)
        return BoardSearchBoardRefreshResult(
            detail=self.detail(game_id=game_id, sequence_number=sequence_number),
            document_removed=False,
        )


@dataclass(frozen=True, slots=True)
class BoardSearchBoardRefreshResult:
    detail: BoardSearchBoardDetail | None
    document_removed: bool


@dataclass(frozen=True, slots=True)
class BoardSearchBoardViewAsset:
    content: bytes
    media_type: str
    revision: str


def _cache_error() -> BoardSearchError:
    return BoardSearchError(
        "BOARD_SEARCH_BOARD_VIEW_CACHE_UNSAFE",
        "The board view cache is not a usable local directory.",
    )


class BoardSearchBoardViewCache:
    """Process-wide cache directory, single-flight locks and size bound.

    The cache holds only derived WebP files that can be re-rendered from the
    source photo at any time; pruning removes least recently used files of
    this directory only.
    """

    def __init__(
        self,
        artifact_root: Path,
        *,
        max_cache_bytes: int = DEFAULT_BOARD_VIEW_CACHE_BYTES,
    ) -> None:
        if max_cache_bytes < 1:
            raise ValueError("max_cache_bytes must be positive")
        self.artifact_root = artifact_root.resolve()
        self.root = self.artifact_root / "data" / "working" / _VIEW_CACHE_DIRECTORY
        self._max_cache_bytes = max_cache_bytes
        self._lock = threading.Lock()
        self._flights: dict[str, threading.Lock] = {}

    def _assert_root(self) -> None:
        if self.root.is_symlink():
            raise _cache_error()

    def read(self, key: str) -> bytes | None:
        """Cached bytes, or `None`; a hit refreshes the file's recency."""

        self._assert_root()
        path = self.root / f"{key}.webp"
        try:
            if path.is_symlink() or not path.is_file():
                return None
            content = path.read_bytes()
        except OSError:
            # Pruned by another request between the check and the read.
            return None
        with contextlib.suppress(OSError):
            os.utime(path, None)
        return content

    def flight(self, key: str) -> threading.Lock:
        with self._lock:
            return self._flights.setdefault(key, threading.Lock())

    def release(self, key: str, flight: threading.Lock) -> None:
        with self._lock:
            if self._flights.get(key) is flight and not flight.locked():
                del self._flights[key]

    def write(self, key: str, content: bytes) -> None:
        self._assert_root()
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self.root, prefix=f".{key}.", suffix=".tmp"
            )
        except OSError as error:
            raise _cache_error() from error
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.root / f"{key}.webp")
        except OSError as error:
            raise _cache_error() from error
        finally:
            with contextlib.suppress(OSError):
                temporary.unlink(missing_ok=True)
        self._prune()

    def _prune(self) -> None:
        entries: list[tuple[float, int, Path]] = []
        total = 0
        for path in self.root.glob("*.webp"):
            try:
                if path.is_symlink() or not path.is_file():
                    continue
                stat = path.stat()
            except OSError:
                continue
            entries.append((stat.st_mtime, stat.st_size, path))
            total += stat.st_size
        for _mtime, size, path in sorted(entries):
            if total <= self._max_cache_bytes:
                break
            try:
                path.unlink()
                total -= size
            except OSError:
                continue


class BoardSearchBoardViewService:
    def __init__(
        self,
        repository: BoardSearchBoardDetailRepository,
        cache: BoardSearchBoardViewCache,
        *,
        render: Callable[[Path, BoardViewCrop | None], bytes] | None = None,
    ) -> None:
        self._repository = repository
        self._cache = cache
        self._render = render or render_board_view

    def view(
        self,
        *,
        game_id: UUID,
        sequence_number: int,
        expected_board_checksum_sha256: str,
        expected_view_revision: str | None = None,
    ) -> BoardSearchBoardViewAsset:
        if sequence_number < 1:
            raise _board_not_found()
        document = _load_document(self._repository, game_id, sequence_number)
        if document.board_checksum_sha256 != expected_board_checksum_sha256:
            raise _revision_conflict()
        source = _checked_view_source(self._repository, game_id, document)
        if source is None:
            raise BoardSearchError(
                "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
                "No image is available for this board.",
            )
        crop: BoardViewCrop | None = None
        if document.asset_mode is BoardSearchAssetMode.OPERATIONAL_REVIEW:
            prepared = _prepare_view(source, document.asset_mode, None)
            if prepared is None:
                raise BoardSearchError(
                    "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
                    "The board has no saved grid to crop its view from.",
                )
            crop = prepared[0]
        key = board_view_revision(source.image_checksum_sha256, crop)
        if expected_view_revision is not None and expected_view_revision != key:
            # The grid (and so the crop) changed since the detail was read.
            raise _revision_conflict()
        cached = self._cache.read(key)
        if cached is not None:
            return BoardSearchBoardViewAsset(cached, "image/webp", key)
        flight = self._cache.flight(key)
        try:
            with flight:
                content = self._cache.read(key)
                if content is None:
                    image = resolve_board_search_image(
                        source.image_relative_path,
                        source.image_checksum_sha256,
                        self._cache.artifact_root,
                        code_prefix="BOARD_SEARCH_BOARD_VIEW_SOURCE",
                    )
                    content = self._render(image.path, crop)
                    self._cache.write(key, content)
        finally:
            self._cache.release(key, flight)
        return BoardSearchBoardViewAsset(content, "image/webp", key)


def render_board_view(path: Path, crop: BoardViewCrop | None) -> bytes:
    """Crop (padding outside the photo is filled) and downscale to WebP.

    EXIF orientation is applied first because saved geometry uses the
    EXIF-normalized pixel space (`rgb-uint8-exif-normalized-v1`).
    """

    try:
        with Image.open(path) as opened:
            if opened.width * opened.height > _VIEW_MAX_SOURCE_PIXELS:
                raise BoardSearchError(
                    "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
                    "The board image is too large to render.",
                )
            image = ImageOps.exif_transpose(opened).convert("RGB")
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise BoardSearchError(
            "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
            "The board image cannot be decoded.",
        ) from error
    if crop is not None:
        if (crop.right - crop.left) * (crop.bottom - crop.top) > BOARD_VIEW_MAX_CROP_PIXELS:
            raise BoardSearchError(
                "BOARD_SEARCH_BOARD_VIEW_UNAVAILABLE",
                "The saved board geometry is too large to render.",
            )
        canvas = Image.new("RGB", (crop.right - crop.left, crop.bottom - crop.top), _VIEW_FILL)
        canvas.paste(image, (-crop.left, -crop.top))
        image = canvas.resize((crop.width, crop.height), Image.Resampling.LANCZOS)
    else:
        size = resized_view_size(image.width, image.height)
        if size != image.size:
            image = image.resize(size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=_VIEW_WEBP_QUALITY, method=4)
    return buffer.getvalue()


__all__ = [
    "BoardSearchBoardDetail",
    "BoardSearchBoardDetailRepository",
    "BoardSearchBoardDetailService",
    "BoardSearchBoardRefreshResult",
    "BoardSearchBoardViewAsset",
    "BoardSearchBoardViewCache",
    "BoardSearchBoardViewService",
    "DEFAULT_BOARD_VIEW_CACHE_BYTES",
    "render_board_view",
]
