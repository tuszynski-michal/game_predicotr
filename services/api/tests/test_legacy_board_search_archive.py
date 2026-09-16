from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest
from game_predictor_api.application.board_search_assets import (
    resolve_board_search_archive_asset,
)
from game_predictor_api.domain.board_search import (
    BoardSearchArchiveAssetReference,
    BoardSearchAssetMode,
    BoardSearchError,
    BoardSearchResult,
    BoardSearchScore,
)
from game_predictor_api.storage.models import LegacyBoardSearchArchiveDocumentModel

from scripts.build_legacy_board_search_archive import (
    ARCHIVE_SEQUENCE_END,
    ARCHIVE_SEQUENCE_START,
    EXPECTED_DOCUMENT_COUNT,
    LEGACY_GAME_CODE,
    LEGACY_GAME_ID,
    LEGACY_GAME_NAME,
    ArchiveBuildError,
    _preview_fingerprint,
    archive_rows_fingerprint,
    validate_preview,
)


def _preview() -> dict[str, Any]:
    preview: dict[str, Any] = {
        "scope": {
            "legacy": {
                "id": str(LEGACY_GAME_ID),
                "code": LEGACY_GAME_CODE,
                "name": LEGACY_GAME_NAME,
            }
        },
        "boardSearchArchive": {
            "retainedRange": {
                "start": ARCHIVE_SEQUENCE_START,
                "end": ARCHIVE_SEQUENCE_END,
                "documents": EXPECTED_DOCUMENT_COUNT,
                "missingBoardLinks": 0,
                "missingBoardPaths": 0,
                "metadataChecksumMismatches": 0,
            }
        },
        "managedFiles": {
            "retainedBoardImages": {
                "mode": "full",
                "checked": EXPECTED_DOCUMENT_COUNT,
                "counts": {"verified": EXPECTED_DOCUMENT_COUNT},
            }
        },
    }
    preview["fingerprint"] = _preview_fingerprint(preview)
    return preview


def test_archive_preview_requires_exact_reviewed_fingerprint_for_execution() -> None:
    preview = _preview()
    fingerprint = str(preview["fingerprint"])

    assert validate_preview(preview, expected_fingerprint=None, execute=False) == fingerprint
    assert validate_preview(preview, expected_fingerprint=fingerprint, execute=True) == fingerprint
    with pytest.raises(ArchiveBuildError) as error:
        validate_preview(preview, expected_fingerprint="f" * 64, execute=True)
    assert error.value.code == "LEGACY_BOARD_ARCHIVE_CONFIRMATION_REQUIRED"


def test_archive_preview_rejects_unverified_files_and_scope_drift() -> None:
    preview = _preview()
    preview["managedFiles"]["retainedBoardImages"]["counts"] = {"verified": 1}
    preview["fingerprint"] = _preview_fingerprint(preview)
    with pytest.raises(ArchiveBuildError) as files_error:
        validate_preview(preview, expected_fingerprint=None, execute=False)
    assert files_error.value.code == "LEGACY_BOARD_ARCHIVE_FILES_UNVERIFIED"

    preview = _preview()
    preview["scope"]["legacy"]["name"] = "another game"
    preview["fingerprint"] = _preview_fingerprint(preview)
    with pytest.raises(ArchiveBuildError) as scope_error:
        validate_preview(preview, expected_fingerprint=None, execute=False)
    assert scope_error.value.code == "LEGACY_BOARD_ARCHIVE_SCOPE_MISMATCH"


def test_archive_fingerprint_is_order_and_content_sensitive() -> None:
    first = {
        "sequence_number": 1,
        "status": "accepted",
        "codes": [1, 2, None],
    }
    second = {
        "sequence_number": 2,
        "status": "corrected",
        "codes": [3, None, 4],
    }

    assert archive_rows_fingerprint((first, second)) == archive_rows_fingerprint((first, second))
    assert (
        archive_rows_fingerprint((first, second))[1] != archive_rows_fingerprint((second, first))[1]
    )


def test_archive_document_has_no_operational_foreign_keys() -> None:
    foreign_targets = {
        foreign_key.target_fullname
        for foreign_key in LegacyBoardSearchArchiveDocumentModel.__table__.foreign_keys
    }
    assert foreign_targets == {"games.id"}


def test_archived_result_cannot_expose_operational_ids() -> None:
    result = BoardSearchResult(
        asset_mode=BoardSearchAssetMode.LEGACY_ARCHIVE,
        review_item_id=None,
        recognized_board_id=None,
        import_job_id=None,
        sequence_number=45_163,
        status="accepted",
        board_checksum_sha256="a" * 64,
        score=BoardSearchScore(100.0, 1, 0, 0.0, 0, 0),
    )
    assert result.asset_mode is BoardSearchAssetMode.LEGACY_ARCHIVE


def test_archive_asset_is_checksum_bound_and_stays_inside_managed_root(
    tmp_path: Path,
) -> None:
    board = tmp_path / "data" / "archive" / "board.png"
    board.parent.mkdir(parents=True)
    board.write_bytes(b"frozen-board")
    checksum = hashlib.sha256(board.read_bytes()).hexdigest()
    reference = BoardSearchArchiveAssetReference("archive/board.png", checksum)

    asset = resolve_board_search_archive_asset(reference, tmp_path)
    assert asset.path == board
    assert asset.media_type == "image/png"

    with pytest.raises(BoardSearchError) as checksum_error:
        resolve_board_search_archive_asset(
            BoardSearchArchiveAssetReference("archive/board.png", "0" * 64),
            tmp_path,
        )
    assert checksum_error.value.code == "BOARD_SEARCH_ARCHIVE_ASSET_CHECKSUM_DRIFT"

    with pytest.raises(BoardSearchError) as path_error:
        resolve_board_search_archive_asset(
            BoardSearchArchiveAssetReference("../board.png", checksum),
            tmp_path,
        )
    assert path_error.value.code == "BOARD_SEARCH_ARCHIVE_ASSET_PATH_UNSAFE"
