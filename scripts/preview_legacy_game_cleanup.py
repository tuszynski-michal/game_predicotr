r"""Build a read-only inventory before slimming the legacy 777 game.

The command is deliberately pinned to the two known games.  It never scans the
operator-owned ``C:\Users\user\Documents\777`` tree and never executes DML or
DDL.  Full archive verification is the default because a database checksum is
not proof that the corresponding file still exists.

Examples::

    .venv\Scripts\python.exe scripts\preview_legacy_game_cleanup.py \
        --output ai_docs\quality\legacy-game-cleanup-preview.json
    .venv\Scripts\python.exe scripts\preview_legacy_game_cleanup.py \
        --metadata-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from typing import Any, Literal, cast
from uuid import UUID

from game_predictor_api.config import ApiSettings
from game_predictor_api.storage.database import create_database_engine
from sqlalchemy import Connection, text
from sqlalchemy.engine import RowMapping

LEGACY_GAME_ID = UUID("80f3c7ec-6110-4e20-a263-2675ee5b15d6")
PROTECTED_GAME_ID = UUID("03d64bfe-4d29-47dd-9153-76bd99b3b5d9")
LEGACY_GAME_CODE = "777"
LEGACY_GAME_NAME = "777 v0.1"
PROTECTED_GAME_CODE = "new-siedem"
PROTECTED_GAME_NAME = "777"
REMOVAL_RANGE_END = 45_162
EXCLUDED_OPERATOR_ROOT = Path(r"C:\Users\user\Documents\777")
SCHEMA_VERSION = "legacy-game-cleanup-preview-v1"
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
_ACTIVE_JOB_STATUSES = ("created", "processing")
_MAX_FAILURE_EXAMPLES = 20
_ARCHIVE_BATCH_SIZE = 512

Classification = Literal["preserve", "delete", "shared", "blocked"]


class PreviewError(RuntimeError):
    """Fail-closed inventory error with a stable operator-facing code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="Skip physical archive file hashing and leave an explicit blocker.",
    )
    parser.add_argument("--statement-timeout-ms", type=int, default=60_000)
    parser.add_argument("--file-workers", type=int, default=4)
    parser.add_argument("--quiet", action="store_true", help="Do not print the JSON report.")
    return parser.parse_args()


def canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def report_fingerprint(report: Mapping[str, object]) -> str:
    payload = dict(report)
    payload.pop("fingerprint", None)
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _as_int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise PreviewError("LEGACY_CLEANUP_VALUE_INVALID", f"Expected an integer, got {value!r}.")
    return int(value)


def validate_scope(rows: Iterable[Mapping[str, Any] | RowMapping]) -> dict[str, object]:
    games = {UUID(str(row["id"])): row for row in rows}
    expected = {
        LEGACY_GAME_ID: (LEGACY_GAME_CODE, LEGACY_GAME_NAME, "legacy"),
        PROTECTED_GAME_ID: (PROTECTED_GAME_CODE, PROTECTED_GAME_NAME, "protected"),
    }
    if set(games) != set(expected):
        raise PreviewError("LEGACY_CLEANUP_SCOPE_MISMATCH", "Expected games were not found.")

    result: dict[str, object] = {}
    for game_id, (code, name, role) in expected.items():
        row = games[game_id]
        if str(row["code"]) != code or str(row["name"]) != name:
            raise PreviewError(
                "LEGACY_CLEANUP_SCOPE_MISMATCH",
                f"The {role} game identity does not match its pinned code and name.",
            )
        result[role] = {
            "id": str(game_id),
            "code": code,
            "name": name,
            "status": str(row["status"]),
        }
    return result


def classify_direct_table(
    *, table_name: str, legacy_count: int, has_sequence_number: bool
) -> tuple[Classification, str]:
    if legacy_count == 0:
        return "preserve", "no_legacy_rows"
    if (
        table_name
        in {
            "image_board_search_candidates",
            "image_board_search_fast_documents",
        }
        and has_sequence_number
    ):
        return "blocked", "split_by_sequence_and_archive_migration_required"
    if table_name == "mobile_release_games":
        return "shared", "release_ownership_must_be_resolved_per_release"
    return "blocked", "legacy_rows_require_an_approved_cleanup_policy"


def _quote_identifier(value: str) -> str:
    if _IDENTIFIER.fullmatch(value) is None:
        raise PreviewError("LEGACY_CLEANUP_SCHEMA_UNSAFE", f"Unsafe identifier: {value!r}.")
    return f'"{value}"'


def _is_safe_relative_path(value: str) -> bool:
    candidate = PurePosixPath(value.replace("\\", "/"))
    return bool(value.strip()) and not candidate.is_absolute() and ".." not in candidate.parts


def managed_data_root(artifact_root: Path) -> Path:
    """Match the operational image asset resolver's ``artifact_root/data`` contract."""

    return artifact_root.resolve() / "data"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_archive_file(
    artifact_root: Path, sequence_number: int, relative_path: str, expected_checksum: str
) -> dict[str, object]:
    if not _is_safe_relative_path(relative_path):
        return {"sequenceNumber": sequence_number, "status": "unsafe_path"}
    candidate = artifact_root.joinpath(*PurePosixPath(relative_path.replace("\\", "/")).parts)
    try:
        if candidate.is_symlink():
            return {"sequenceNumber": sequence_number, "status": "not_regular_file"}
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(artifact_root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        return {"sequenceNumber": sequence_number, "status": "missing_or_unsafe"}
    try:
        if not resolved.is_file() or resolved.is_symlink():
            return {"sequenceNumber": sequence_number, "status": "not_regular_file"}
        size_bytes = resolved.stat().st_size
        actual_checksum = _sha256(resolved)
    except OSError:
        return {"sequenceNumber": sequence_number, "status": "unreadable"}
    return {
        "sequenceNumber": sequence_number,
        "status": "verified" if actual_checksum == expected_checksum else "checksum_mismatch",
        "sizeBytes": size_bytes,
    }


def summarize_archive_file_results(results: Sequence[Mapping[str, object]]) -> dict[str, object]:
    counts: dict[str, int] = {}
    total_bytes = 0
    failures: list[dict[str, object]] = []
    for result in results:
        status = str(result["status"])
        counts[status] = counts.get(status, 0) + 1
        total_bytes += _as_int(result.get("sizeBytes", 0))
        if status != "verified" and len(failures) < _MAX_FAILURE_EXAMPLES:
            failures.append({"sequenceNumber": _as_int(result["sequenceNumber"]), "status": status})
    return {
        "mode": "full",
        "checked": len(results),
        "counts": dict(sorted(counts.items())),
        "verifiedBytes": total_bytes,
        "failureExamples": failures,
    }


def _fetch_scope(connection: Connection) -> dict[str, object]:
    rows = connection.execute(
        text(
            "SELECT id, code, name, status FROM games "
            "WHERE id IN (:legacy_id, :protected_id) ORDER BY id"
        ),
        {"legacy_id": LEGACY_GAME_ID, "protected_id": PROTECTED_GAME_ID},
    ).mappings()
    scope = validate_scope(rows)
    artifact_root = Path(ApiSettings.from_environment().artifact_root).resolve()
    excluded_root = EXCLUDED_OPERATOR_ROOT.resolve()
    if artifact_root == excluded_root or artifact_root.is_relative_to(excluded_root):
        raise PreviewError(
            "LEGACY_CLEANUP_OPERATOR_ROOT_COLLISION",
            "Managed artifact root overlaps the excluded operator directory.",
        )
    scope["excludedOperatorRoot"] = {
        "classification": "preserve",
        "path": str(EXCLUDED_OPERATOR_ROOT),
        "reason": "operator_owned_directory_never_scanned",
    }
    scope["artifactRoot"] = str(artifact_root)
    scope["removalRange"] = {"start": 1, "end": REMOVAL_RANGE_END}
    return scope


def _schema_inventory(
    connection: Connection,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    column_rows = list(
        connection.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' ORDER BY table_name, ordinal_position"
            )
        ).mappings()
    )
    columns: dict[str, set[str]] = {}
    for row in column_rows:
        columns.setdefault(str(row["table_name"]), set()).add(str(row["column_name"]))
    direct_tables: list[dict[str, object]] = []
    path_columns: list[dict[str, object]] = []
    for table_name, table_columns in columns.items():
        if "game_id" in table_columns:
            quoted = _quote_identifier(table_name)
            counts = (
                connection.execute(
                    text(
                        f"SELECT count(*) FILTER (WHERE game_id = :legacy_id) AS legacy_count, "
                        f"count(*) FILTER (WHERE game_id = :protected_id) AS protected_count "
                        f"FROM {quoted}"
                    ),
                    {"legacy_id": LEGACY_GAME_ID, "protected_id": PROTECTED_GAME_ID},
                )
                .mappings()
                .one()
            )
            legacy_count = int(counts["legacy_count"])
            classification, reason = classify_direct_table(
                table_name=table_name,
                legacy_count=legacy_count,
                has_sequence_number="sequence_number" in table_columns,
            )
            item: dict[str, object] = {
                "table": table_name,
                "classification": classification,
                "reason": reason,
                "legacyRows": legacy_count,
                "protectedRows": int(counts["protected_count"]),
                "globalRelationBytes": int(
                    connection.execute(
                        text("SELECT pg_total_relation_size(to_regclass(:table_name))"),
                        {"table_name": table_name},
                    ).scalar_one()
                ),
            }
            if "sequence_number" in table_columns:
                split = (
                    connection.execute(
                        text(
                            f"SELECT count(*) FILTER (WHERE sequence_number BETWEEN 1 AND :cutoff) "
                            f"AS removal_rows, count(*) FILTER (WHERE sequence_number > :cutoff) "
                            f"AS retained_rows FROM {quoted} WHERE game_id = :legacy_id"
                        ),
                        {"legacy_id": LEGACY_GAME_ID, "cutoff": REMOVAL_RANGE_END},
                    )
                    .mappings()
                    .one()
                )
                item["sequenceSplit"] = {
                    "delete": int(split["removal_rows"]),
                    "preserve": int(split["retained_rows"]),
                }
            direct_tables.append(item)

        for column in sorted(table_columns):
            if column.endswith("_relative_path") or column in {
                "image_path",
                "audit_path",
                "snapshot_path",
                "apk_path",
            }:
                path_columns.append(
                    {
                        "table": table_name,
                        "column": column,
                        "classification": "blocked",
                        "ownership": "direct_game" if "game_id" in table_columns else "indirect",
                        "reason": "physical_path_requires_reference_ownership_resolution",
                    }
                )
    return direct_tables, path_columns


def _dependency_inventory(connection: Connection) -> list[dict[str, object]]:
    rows = connection.execute(
        text(
            "SELECT child.relname AS child_table, parent.relname AS parent_table "
            "FROM pg_constraint fk "
            "JOIN pg_class child ON child.oid = fk.conrelid "
            "JOIN pg_class parent ON parent.oid = fk.confrelid "
            "JOIN pg_namespace ns ON ns.oid = child.relnamespace "
            "WHERE fk.contype = 'f' AND ns.nspname = 'public' "
            "ORDER BY child.relname, parent.relname"
        )
    ).mappings()
    return [
        {
            "table": str(row["child_table"]),
            "dependsOn": str(row["parent_table"]),
            "classification": "blocked",
            "reason": "foreign_key_dependency_requires_owned_row_resolution",
        }
        for row in rows
        if str(row["parent_table"]) != str(row["child_table"])
    ]


def _archive_database_summary(connection: Connection) -> dict[str, object]:
    row = (
        connection.execute(
            text(
                """
            SELECT
              count(*) FILTER (WHERE f.sequence_number BETWEEN 1 AND :cutoff) AS delete_documents,
              count(*) FILTER (WHERE f.sequence_number > :cutoff) AS preserve_documents,
              min(f.sequence_number) FILTER (WHERE f.sequence_number > :cutoff) AS preserve_min,
              max(f.sequence_number) FILTER (WHERE f.sequence_number > :cutoff) AS preserve_max,
              count(*) FILTER (WHERE f.sequence_number > :cutoff AND ri.id IS NULL)
                AS missing_review_links,
              count(*) FILTER (WHERE f.sequence_number > :cutoff AND rb.id IS NULL)
                AS missing_board_links,
              count(*) FILTER (WHERE f.sequence_number > :cutoff
                AND rb.board_relative_path IS NULL) AS missing_board_paths,
              count(*) FILTER (WHERE f.sequence_number > :cutoff
                AND f.board_checksum_sha256 IS DISTINCT FROM rb.board_checksum_sha256)
                AS metadata_checksum_mismatches
            FROM image_board_search_fast_documents f
            LEFT JOIN image_review_items ri ON ri.id = f.review_item_id
            LEFT JOIN recognized_boards rb ON rb.id = ri.recognized_board_id
            WHERE f.game_id = :legacy_id
            """
            ),
            {"legacy_id": LEGACY_GAME_ID, "cutoff": REMOVAL_RANGE_END},
        )
        .mappings()
        .one()
    )
    return {
        "removalRange": {
            "classification": "delete",
            "start": 1,
            "end": REMOVAL_RANGE_END,
            "documents": int(row["delete_documents"]),
        },
        "retainedRange": {
            "classification": "preserve",
            "start": int(row["preserve_min"]) if row["preserve_min"] is not None else None,
            "end": int(row["preserve_max"]) if row["preserve_max"] is not None else None,
            "documents": int(row["preserve_documents"]),
            "missingReviewLinks": int(row["missing_review_links"]),
            "missingBoardLinks": int(row["missing_board_links"]),
            "missingBoardPaths": int(row["missing_board_paths"]),
            "metadataChecksumMismatches": int(row["metadata_checksum_mismatches"]),
        },
    }


def _archive_rows(connection: Connection) -> Iterable[tuple[int, str, str]]:
    cursor = REMOVAL_RANGE_END
    while True:
        rows = list(
            connection.execute(
                text(
                    """
                    SELECT f.sequence_number, rb.board_relative_path, rb.board_checksum_sha256
                    FROM image_board_search_fast_documents f
                    JOIN image_review_items ri ON ri.id = f.review_item_id
                    JOIN recognized_boards rb ON rb.id = ri.recognized_board_id
                    WHERE f.game_id = :legacy_id AND f.sequence_number > :cursor
                    ORDER BY f.sequence_number LIMIT :batch_size
                    """
                ),
                {
                    "legacy_id": LEGACY_GAME_ID,
                    "cursor": cursor,
                    "batch_size": _ARCHIVE_BATCH_SIZE,
                },
            )
        )
        if not rows:
            return
        for row in rows:
            sequence_number = int(row[0])
            if row[1] is None or row[2] is None:
                yield sequence_number, "", ""
            else:
                yield sequence_number, str(row[1]), str(row[2])
            cursor = sequence_number


def _verify_archive_files(
    connection: Connection, artifact_root: Path, *, workers: int
) -> dict[str, object]:
    checked = 0
    verified_bytes = 0
    counts: dict[str, int] = {}
    failures: list[dict[str, object]] = []

    def retain(results: Iterable[Mapping[str, object]]) -> None:
        nonlocal checked, verified_bytes
        for result in results:
            checked += 1
            status = str(result["status"])
            counts[status] = counts.get(status, 0) + 1
            verified_bytes += _as_int(result.get("sizeBytes", 0))
            if status != "verified" and len(failures) < _MAX_FAILURE_EXAMPLES:
                failures.append(
                    {"sequenceNumber": _as_int(result["sequenceNumber"]), "status": status}
                )

    with ThreadPoolExecutor(max_workers=workers) as executor:
        batch: list[tuple[int, str, str]] = []
        for item in _archive_rows(connection):
            batch.append(item)
            if len(batch) < _ARCHIVE_BATCH_SIZE:
                continue
            retain(
                executor.map(
                    lambda args: verify_archive_file(artifact_root, *args),
                    batch,
                )
            )
            batch.clear()
            if checked % 10_240 == 0:
                print(f"Verified {checked} retained board images...", file=sys.stderr)
        if batch:
            retain(
                executor.map(
                    lambda args: verify_archive_file(artifact_root, *args),
                    batch,
                )
            )
    return {
        "mode": "full",
        "checked": checked,
        "counts": dict(sorted(counts.items())),
        "verifiedBytes": verified_bytes,
        "failureExamples": failures,
    }


def _job_summary(connection: Connection) -> dict[str, object]:
    rows = list(
        connection.execute(
            text(
                "SELECT status, count(*) AS count FROM jobs WHERE game_id = :legacy_id "
                "GROUP BY status ORDER BY status"
            ),
            {"legacy_id": LEGACY_GAME_ID},
        ).mappings()
    )
    by_status = {str(row["status"]): int(row["count"]) for row in rows}
    return {
        "classification": (
            "blocked"
            if any(by_status.get(status, 0) for status in _ACTIVE_JOB_STATUSES)
            else "delete"
        ),
        "byStatus": by_status,
        "active": sum(by_status.get(status, 0) for status in _ACTIVE_JOB_STATUSES),
    }


def build_preview(
    *,
    scope: Mapping[str, object],
    direct_tables: Sequence[Mapping[str, object]],
    path_columns: Sequence[Mapping[str, object]],
    dependency_edges: Sequence[Mapping[str, object]],
    archive: Mapping[str, object],
    archive_files: Mapping[str, object],
    jobs: Mapping[str, object],
) -> dict[str, object]:
    retained = cast(Mapping[str, object], archive["retainedRange"])
    blockers: list[dict[str, object]] = []
    for key in (
        "missingReviewLinks",
        "missingBoardLinks",
        "missingBoardPaths",
        "metadataChecksumMismatches",
    ):
        if _as_int(retained[key]) > 0:
            blockers.append({"code": f"ARCHIVE_{key.upper()}", "count": _as_int(retained[key])})
    file_counts = cast(Mapping[str, object], archive_files.get("counts", {}))
    file_failures = sum(
        _as_int(value) for key, value in file_counts.items() if str(key) != "verified"
    )
    if archive_files.get("mode") != "full":
        blockers.append({"code": "ARCHIVE_FILE_VERIFICATION_NOT_RUN"})
    elif file_failures:
        blockers.append({"code": "ARCHIVE_FILE_VERIFICATION_FAILED", "count": file_failures})
    if _as_int(jobs["active"]) > 0:
        blockers.append({"code": "ACTIVE_LEGACY_GAME_JOBS", "count": _as_int(jobs["active"])})
    blockers.append(
        {
            "code": "ARCHIVE_MIGRATION_REQUIRED",
            "reason": "Board search still resolves images through operational review records.",
        }
    )
    report: dict[str, object] = {
        "schemaVersion": SCHEMA_VERSION,
        "scope": dict(scope),
        "database": {
            "directGameTables": [dict(item) for item in direct_tables],
            "dependencyEdges": [dict(item) for item in dependency_edges],
            "jobs": dict(jobs),
        },
        "managedFiles": {
            "pathColumns": [dict(item) for item in path_columns],
            "retainedBoardImages": dict(archive_files),
        },
        "boardSearchArchive": dict(archive),
        "blockers": blockers,
        "backupRequirements": {
            "classification": "blocked",
            "database": "consistent PostgreSQL backup before cleanup execution",
            "artifacts": (
                "copy and verify retained whole-board images before deleting operational review"
            ),
            "minimumTransitionalBytes": _as_int(archive_files.get("verifiedBytes", 0)),
            "operatorDirectoryIncluded": False,
        },
        "totals": {
            "directLegacyRows": sum(_as_int(item["legacyRows"]) for item in direct_tables),
            "directProtectedRows": sum(_as_int(item["protectedRows"]) for item in direct_tables),
            "retainedBoardDocuments": _as_int(retained["documents"]),
            "blockers": len(blockers),
        },
    }
    report["fingerprint"] = report_fingerprint(report)
    return report


def create_preview(
    connection: Connection,
    *,
    verify_files: bool,
    file_workers: int,
) -> dict[str, object]:
    scope = _fetch_scope(connection)
    direct_tables, path_columns = _schema_inventory(connection)
    dependency_edges = _dependency_inventory(connection)
    archive = _archive_database_summary(connection)
    jobs = _job_summary(connection)
    if verify_files:
        archive_files = _verify_archive_files(
            connection,
            managed_data_root(Path(str(scope["artifactRoot"]))),
            workers=file_workers,
        )
    else:
        archive_files = {
            "mode": "metadata_only",
            "checked": 0,
            "counts": {},
            "verifiedBytes": 0,
            "failureExamples": [],
        }
    return build_preview(
        scope=scope,
        direct_tables=direct_tables,
        path_columns=path_columns,
        dependency_edges=dependency_edges,
        archive=archive,
        archive_files=archive_files,
        jobs=jobs,
    )


def main() -> int:
    arguments = _arguments()
    if arguments.statement_timeout_ms < 1 or arguments.statement_timeout_ms > 120_000:
        raise PreviewError("LEGACY_CLEANUP_TIMEOUT_INVALID", "Timeout must be 1..120000 ms.")
    if arguments.file_workers < 1 or arguments.file_workers > 16:
        raise PreviewError("LEGACY_CLEANUP_WORKERS_INVALID", "File workers must be 1..16.")

    settings = ApiSettings.from_environment()
    engine = create_database_engine(settings)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text("SELECT set_config('statement_timeout', :timeout, false)"),
                {"timeout": f"{arguments.statement_timeout_ms}ms"},
            )
            connection.execute(text("SET default_transaction_read_only = on"))
            report = create_preview(
                connection,
                verify_files=not arguments.metadata_only,
                file_workers=arguments.file_workers,
            )
    finally:
        engine.dispose()

    content = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(content, encoding="utf-8")
    if not arguments.quiet:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
