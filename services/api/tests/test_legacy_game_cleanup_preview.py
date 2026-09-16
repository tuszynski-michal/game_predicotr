from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import pytest

from scripts.preview_legacy_game_cleanup import (
    LEGACY_GAME_CODE,
    LEGACY_GAME_ID,
    LEGACY_GAME_NAME,
    PROTECTED_GAME_CODE,
    PROTECTED_GAME_ID,
    PROTECTED_GAME_NAME,
    PreviewError,
    build_preview,
    classify_direct_table,
    managed_data_root,
    report_fingerprint,
    summarize_archive_file_results,
    validate_scope,
    verify_archive_file,
)


def _game_rows() -> list[dict[str, object]]:
    return [
        {
            "id": LEGACY_GAME_ID,
            "code": LEGACY_GAME_CODE,
            "name": LEGACY_GAME_NAME,
            "status": "archived",
        },
        {
            "id": PROTECTED_GAME_ID,
            "code": PROTECTED_GAME_CODE,
            "name": PROTECTED_GAME_NAME,
            "status": "active",
        },
    ]


def test_scope_is_pinned_to_exact_legacy_and_protected_games() -> None:
    scope = validate_scope(_game_rows())
    assert scope["legacy"] == {
        "id": str(LEGACY_GAME_ID),
        "code": "777",
        "name": "777 v0.1",
        "status": "archived",
    }
    invalid = _game_rows()
    invalid[0] = {**invalid[0], "id": uuid4()}
    with pytest.raises(PreviewError, match="LEGACY_CLEANUP_SCOPE_MISMATCH"):
        validate_scope(invalid)


def test_search_tables_are_blocked_until_sequence_split_is_archived() -> None:
    classification = classify_direct_table(
        table_name="image_board_search_fast_documents",
        legacy_count=10,
        has_sequence_number=True,
    )
    assert classification == (
        "blocked",
        "split_by_sequence_and_archive_migration_required",
    )
    assert (
        classify_direct_table(
            table_name="image_symbol_review_cells",
            legacy_count=10,
            has_sequence_number=True,
        )[0]
        == "blocked"
    )


def test_archive_file_verification_checks_real_bytes(tmp_path: Path) -> None:
    target = tmp_path / "boards" / "one.png"
    target.parent.mkdir()
    target.write_bytes(b"board")
    checksum = hashlib.sha256(b"board").hexdigest()

    verified = verify_archive_file(tmp_path, 45_163, "boards/one.png", checksum)
    mismatch = verify_archive_file(tmp_path, 45_164, "boards/one.png", "0" * 64)
    unsafe = verify_archive_file(tmp_path, 45_165, "../outside.png", checksum)

    assert verified == {"sequenceNumber": 45_163, "status": "verified", "sizeBytes": 5}
    assert mismatch["status"] == "checksum_mismatch"
    assert unsafe["status"] == "unsafe_path"


def test_managed_board_paths_are_resolved_below_artifact_data(tmp_path: Path) -> None:
    assert managed_data_root(tmp_path) == tmp_path.resolve() / "data"


def test_unreadable_archive_file_becomes_a_blocker_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "board.png"
    target.write_bytes(b"board")

    def deny_open(*_args: object, **_kwargs: object) -> object:
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "open", deny_open)
    result = verify_archive_file(tmp_path, 45_163, "board.png", "0" * 64)
    assert result == {"sequenceNumber": 45_163, "status": "unreadable"}


def test_archive_summary_is_bounded_and_counts_failures() -> None:
    results = [{"sequenceNumber": number, "status": "missing_or_unsafe"} for number in range(30)]
    summary = summarize_archive_file_results(results)
    assert summary["counts"] == {"missing_or_unsafe": 30}
    assert len(summary["failureExamples"]) == 20


def test_preview_fingerprint_is_deterministic_and_detects_file_blockers() -> None:
    kwargs = {
        "scope": {"legacy": {"id": str(LEGACY_GAME_ID)}},
        "direct_tables": [
            {
                "table": "jobs",
                "classification": "blocked",
                "reason": "policy",
                "legacyRows": 2,
                "protectedRows": 1,
            }
        ],
        "path_columns": [],
        "dependency_edges": [],
        "archive": {
            "removalRange": {"classification": "delete", "documents": 1},
            "retainedRange": {
                "classification": "preserve",
                "documents": 2,
                "missingReviewLinks": 0,
                "missingBoardLinks": 0,
                "missingBoardPaths": 0,
                "metadataChecksumMismatches": 0,
            },
        },
        "archive_files": {
            "mode": "full",
            "checked": 2,
            "counts": {"verified": 1, "checksum_mismatch": 1},
            "verifiedBytes": 5,
        },
        "jobs": {"active": 0, "byStatus": {}, "classification": "delete"},
    }
    first = build_preview(**kwargs)  # type: ignore[arg-type]
    second = build_preview(**kwargs)  # type: ignore[arg-type]
    assert first == second
    assert first["fingerprint"] == report_fingerprint(first)
    assert {item["code"] for item in first["blockers"]} >= {
        "ARCHIVE_FILE_VERIFICATION_FAILED",
        "ARCHIVE_MIGRATION_REQUIRED",
    }
