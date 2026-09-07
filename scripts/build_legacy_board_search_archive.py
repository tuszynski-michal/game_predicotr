r"""Build the frozen board-search archive for the pinned legacy 777 game.

The default mode is read-only.  ``--execute`` performs only additive archive
writes and requires the exact reviewed TASK-0502 preview fingerprint.  It never
deletes operational review data or touches ``C:\Users\user\Documents\777``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine
from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping

LEGACY_GAME_ID = UUID("80f3c7ec-6110-4e20-a263-2675ee5b15d6")
PROTECTED_GAME_ID = UUID("03d64bfe-4d29-47dd-9153-76bd99b3b5d9")
LEGACY_GAME_CODE = "777"
LEGACY_GAME_NAME = "777 v0.1"
ARCHIVE_SEQUENCE_START = 45_163
ARCHIVE_SEQUENCE_END = 499_995
EXPECTED_DOCUMENT_COUNT = 369_554
ARCHIVE_POLICY_VERSION = "legacy-board-search-archive-v1"
EMPTY_FINGERPRINT = "0" * 64
DEFAULT_PREVIEW_PATH = Path("ai_docs/quality/legacy-game-cleanup-preview-2026-09-07.json")


class ArchiveBuildError(RuntimeError):
    """Stable fail-closed error raised before an archive can be activated."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview-path", type=Path, default=DEFAULT_PREVIEW_PATH)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-preview-fingerprint")
    parser.add_argument("--statement-timeout-ms", type=int, default=120_000)
    return parser.parse_args()


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _preview_fingerprint(preview: Mapping[str, object]) -> str:
    payload = dict(preview)
    payload.pop("fingerprint", None)
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def validate_preview(
    preview: Mapping[str, Any],
    *,
    expected_fingerprint: str | None,
    execute: bool,
) -> str:
    stored_fingerprint = str(preview.get("fingerprint", ""))
    if len(stored_fingerprint) != 64 or stored_fingerprint != _preview_fingerprint(preview):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_PREVIEW_DRIFT",
            "The cleanup preview fingerprint is missing or invalid.",
        )
    if execute and expected_fingerprint != stored_fingerprint:
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_CONFIRMATION_REQUIRED",
            "Execution requires the exact reviewed preview fingerprint.",
        )
    scope = preview.get("scope")
    archive = preview.get("boardSearchArchive")
    files = preview.get("managedFiles")
    if not isinstance(scope, Mapping) or not isinstance(archive, Mapping):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_PREVIEW_INVALID",
            "The preview does not contain the required scope and archive summary.",
        )
    legacy = scope.get("legacy")
    retained = archive.get("retainedRange")
    retained_files = files.get("retainedBoardImages") if isinstance(files, Mapping) else None
    if not isinstance(legacy, Mapping) or (
        str(legacy.get("id")) != str(LEGACY_GAME_ID)
        or legacy.get("code") != LEGACY_GAME_CODE
        or legacy.get("name") != LEGACY_GAME_NAME
    ):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_SCOPE_MISMATCH",
            "The preview is not pinned to the expected legacy game.",
        )
    if not isinstance(retained, Mapping) or (
        int(retained.get("start", 0)) != ARCHIVE_SEQUENCE_START
        or int(retained.get("end", 0)) != ARCHIVE_SEQUENCE_END
        or int(retained.get("documents", -1)) != EXPECTED_DOCUMENT_COUNT
        or int(retained.get("missingBoardLinks", -1)) != 0
        or int(retained.get("missingBoardPaths", -1)) != 0
        or int(retained.get("metadataChecksumMismatches", -1)) != 0
    ):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_SOURCE_INCOMPLETE",
            "The retained board-search range is incomplete or has inconsistent metadata.",
        )
    if not isinstance(retained_files, Mapping) or (
        retained_files.get("mode") != "full"
        or int(retained_files.get("checked", -1)) != EXPECTED_DOCUMENT_COUNT
        or retained_files.get("counts") != {"verified": EXPECTED_DOCUMENT_COUNT}
    ):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_FILES_UNVERIFIED",
            "Every retained board image must be checksum-verified before archive creation.",
        )
    return stored_fingerprint


def _validate_database_scope(connection: Connection) -> None:
    rows = connection.execute(
        text("SELECT id, code, name FROM games WHERE id IN (:legacy_id, :protected_id)"),
        {"legacy_id": LEGACY_GAME_ID, "protected_id": PROTECTED_GAME_ID},
    ).mappings()
    games = {UUID(str(row["id"])): row for row in rows}
    legacy = games.get(LEGACY_GAME_ID)
    if (
        set(games) != {LEGACY_GAME_ID, PROTECTED_GAME_ID}
        or legacy is None
        or legacy["code"] != LEGACY_GAME_CODE
        or legacy["name"] != LEGACY_GAME_NAME
    ):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_SCOPE_MISMATCH",
            "The database does not contain the pinned legacy and protected games.",
        )


_SOURCE_ROWS_SQL = """
SELECT
  d.sequence_number,
  d.status,
  b.board_relative_path,
  d.board_checksum_sha256,
  d.known_evidence_positions,
  d.primary_symbol_mobile_codes,
  d.alternative_rank_1_mobile_codes,
  d.alternative_rank_2_mobile_codes,
  d.alternative_rank_3_mobile_codes,
  d.alternative_rank_4_mobile_codes
FROM image_board_search_fast_documents d
JOIN recognized_boards b ON b.id = d.recognized_board_id
WHERE d.game_id = :game_id
  AND d.sequence_number BETWEEN :sequence_start AND :sequence_end
  AND b.board_relative_path IS NOT NULL
  AND b.board_checksum_sha256 = d.board_checksum_sha256
ORDER BY d.sequence_number
"""

_ARCHIVE_ROWS_SQL = """
SELECT
  sequence_number,
  status,
  board_relative_path,
  board_checksum_sha256,
  known_evidence_positions,
  primary_symbol_mobile_codes,
  alternative_rank_1_mobile_codes,
  alternative_rank_2_mobile_codes,
  alternative_rank_3_mobile_codes,
  alternative_rank_4_mobile_codes
FROM legacy_board_search_archive_documents
WHERE game_id = :game_id
ORDER BY sequence_number
"""


def archive_rows_fingerprint(rows: Iterable[Mapping[str, object] | RowMapping]) -> tuple[int, str]:
    digest = hashlib.sha256()
    count = 0
    for row in rows:
        payload = {
            key: list(value) if isinstance(value, tuple) else value for key, value in row.items()
        }
        digest.update(_canonical_json(payload).encode())
        digest.update(b"\n")
        count += 1
    return count, digest.hexdigest()


def _source_summary(connection: Connection) -> tuple[int, str]:
    parameters = {
        "game_id": LEGACY_GAME_ID,
        "sequence_start": ARCHIVE_SEQUENCE_START,
        "sequence_end": ARCHIVE_SEQUENCE_END,
    }
    statement = text(_SOURCE_ROWS_SQL).execution_options(stream_results=True)
    rows = connection.execute(statement, parameters).mappings()
    return archive_rows_fingerprint(rows)


def _archive_summary(connection: Connection) -> tuple[int, str]:
    statement = text(_ARCHIVE_ROWS_SQL).execution_options(stream_results=True)
    rows = connection.execute(statement, {"game_id": LEGACY_GAME_ID}).mappings()
    return archive_rows_fingerprint(rows)


def _write_archive(connection: Connection, preview_fingerprint: str) -> dict[str, object]:
    source_count, source_fingerprint = _source_summary(connection)
    if source_count != EXPECTED_DOCUMENT_COUNT:
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_SOURCE_DRIFT",
            f"Expected {EXPECTED_DOCUMENT_COUNT} source documents, found {source_count}.",
        )
    parameters = {
        "game_id": LEGACY_GAME_ID,
        "sequence_start": ARCHIVE_SEQUENCE_START,
        "sequence_end": ARCHIVE_SEQUENCE_END,
    }
    connection.execute(
        text(
            "DELETE FROM legacy_board_search_archive_documents "
            "WHERE game_id = :game_id AND "
            "(sequence_number < :sequence_start OR sequence_number > :sequence_end)"
        ),
        parameters,
    )
    connection.execute(
        text(
            """
INSERT INTO legacy_board_search_archive_documents (
  game_id, sequence_number, status, board_relative_path, board_checksum_sha256,
  known_evidence_positions, primary_symbol_mobile_codes,
  alternative_rank_1_mobile_codes, alternative_rank_2_mobile_codes,
  alternative_rank_3_mobile_codes, alternative_rank_4_mobile_codes
)
SELECT
  d.game_id, d.sequence_number, d.status, b.board_relative_path,
  d.board_checksum_sha256, d.known_evidence_positions,
  d.primary_symbol_mobile_codes, d.alternative_rank_1_mobile_codes,
  d.alternative_rank_2_mobile_codes, d.alternative_rank_3_mobile_codes,
  d.alternative_rank_4_mobile_codes
FROM image_board_search_fast_documents d
JOIN recognized_boards b ON b.id = d.recognized_board_id
WHERE d.game_id = :game_id
  AND d.sequence_number BETWEEN :sequence_start AND :sequence_end
  AND b.board_relative_path IS NOT NULL
  AND b.board_checksum_sha256 = d.board_checksum_sha256
ON CONFLICT (game_id, sequence_number) DO UPDATE SET
  status = EXCLUDED.status,
  board_relative_path = EXCLUDED.board_relative_path,
  board_checksum_sha256 = EXCLUDED.board_checksum_sha256,
  known_evidence_positions = EXCLUDED.known_evidence_positions,
  primary_symbol_mobile_codes = EXCLUDED.primary_symbol_mobile_codes,
  alternative_rank_1_mobile_codes = EXCLUDED.alternative_rank_1_mobile_codes,
  alternative_rank_2_mobile_codes = EXCLUDED.alternative_rank_2_mobile_codes,
  alternative_rank_3_mobile_codes = EXCLUDED.alternative_rank_3_mobile_codes,
  alternative_rank_4_mobile_codes = EXCLUDED.alternative_rank_4_mobile_codes
WHERE (
  legacy_board_search_archive_documents.status,
  legacy_board_search_archive_documents.board_relative_path,
  legacy_board_search_archive_documents.board_checksum_sha256,
  legacy_board_search_archive_documents.known_evidence_positions,
  legacy_board_search_archive_documents.primary_symbol_mobile_codes,
  legacy_board_search_archive_documents.alternative_rank_1_mobile_codes,
  legacy_board_search_archive_documents.alternative_rank_2_mobile_codes,
  legacy_board_search_archive_documents.alternative_rank_3_mobile_codes,
  legacy_board_search_archive_documents.alternative_rank_4_mobile_codes
) IS DISTINCT FROM (
  EXCLUDED.status,
  EXCLUDED.board_relative_path,
  EXCLUDED.board_checksum_sha256,
  EXCLUDED.known_evidence_positions,
  EXCLUDED.primary_symbol_mobile_codes,
  EXCLUDED.alternative_rank_1_mobile_codes,
  EXCLUDED.alternative_rank_2_mobile_codes,
  EXCLUDED.alternative_rank_3_mobile_codes,
  EXCLUDED.alternative_rank_4_mobile_codes
)
"""
        ),
        parameters,
    )
    archive_count, archive_fingerprint = _archive_summary(connection)
    if archive_count != source_count or archive_fingerprint != source_fingerprint:
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_VERIFICATION_FAILED",
            "The frozen archive differs from its source projection.",
        )
    connection.execute(
        text(
            """
INSERT INTO legacy_board_search_archive_states (
  game_id, status, sequence_start, sequence_end, document_count,
  source_preview_fingerprint, archive_fingerprint, failure_message
)
VALUES (
  :game_id, 'ready', :sequence_start, :sequence_end, :document_count,
  :preview_fingerprint, :archive_fingerprint, NULL
)
ON CONFLICT (game_id) DO UPDATE SET
  status = EXCLUDED.status,
  sequence_start = EXCLUDED.sequence_start,
  sequence_end = EXCLUDED.sequence_end,
  document_count = EXCLUDED.document_count,
  source_preview_fingerprint = EXCLUDED.source_preview_fingerprint,
  archive_fingerprint = EXCLUDED.archive_fingerprint,
  failure_message = NULL,
  updated_at = now()
"""
        ),
        {
            **parameters,
            "document_count": archive_count,
            "preview_fingerprint": preview_fingerprint,
            "archive_fingerprint": archive_fingerprint,
        },
    )
    return {
        "archiveFingerprint": archive_fingerprint,
        "documentCount": archive_count,
        "gameId": str(LEGACY_GAME_ID),
        "mode": "executed",
        "policyVersion": ARCHIVE_POLICY_VERSION,
        "sequenceEnd": ARCHIVE_SEQUENCE_END,
        "sequenceStart": ARCHIVE_SEQUENCE_START,
        "sourcePreviewFingerprint": preview_fingerprint,
        "status": "ready",
    }


def main() -> int:
    arguments = _arguments()
    if not 1 <= arguments.statement_timeout_ms <= 120_000:
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_TIMEOUT_INVALID",
            "Statement timeout must be between 1 and 120000 ms.",
        )
    preview = json.loads(arguments.preview_path.read_text(encoding="utf-8"))
    if not isinstance(preview, dict):
        raise ArchiveBuildError(
            "LEGACY_BOARD_ARCHIVE_PREVIEW_INVALID",
            "The cleanup preview must be a JSON object.",
        )
    preview_fingerprint = validate_preview(
        preview,
        expected_fingerprint=arguments.expected_preview_fingerprint,
        execute=arguments.execute,
    )
    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    try:
        with engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('statement_timeout', :timeout, true)"),
                {"timeout": f"{arguments.statement_timeout_ms}ms"},
            )
            _validate_database_scope(connection)
            if arguments.execute:
                result = _write_archive(connection, preview_fingerprint)
            else:
                source_count, source_fingerprint = _source_summary(connection)
                if source_count != EXPECTED_DOCUMENT_COUNT:
                    raise ArchiveBuildError(
                        "LEGACY_BOARD_ARCHIVE_SOURCE_DRIFT",
                        f"Expected {EXPECTED_DOCUMENT_COUNT} source documents, "
                        f"found {source_count}.",
                    )
                result = {
                    "archiveFingerprint": source_fingerprint,
                    "documentCount": source_count,
                    "gameId": str(LEGACY_GAME_ID),
                    "mode": "preview",
                    "policyVersion": ARCHIVE_POLICY_VERSION,
                    "sequenceEnd": ARCHIVE_SEQUENCE_END,
                    "sequenceStart": ARCHIVE_SEQUENCE_START,
                    "sourcePreviewFingerprint": preview_fingerprint,
                    "status": "ready_to_execute",
                }
    finally:
        engine.dispose()
    output = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
