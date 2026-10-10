"""Read-only check that every file path stored in the database exists on disk (TASK-0956).

Plan ``ai_docs/delivery/DISK_D_MIGRATION_PLAN_20261009.md``, decision 10. The
script discovers every ``*_path`` / ``relative_path`` column of the
``game_data_v2`` and ``public`` schemas (partition children excluded, the parent
covers them), resolves each stored relative path under the root the
application uses for that column and checks that the file exists. Manifest
columns are also read as JSON and scanned for strings under the legacy prefix.

Roots follow the application code: a path that starts with ``data/`` is
relative to ``GAME_PREDICTOR_ARTIFACT_ROOT``; any other path is relative to the
column's root, which is ``<artifact_root>/data`` (managed storage of
``image_storage.py`` / ``image_job_repository.py``, ``root_name="data"``) for
every mapped column; imported lab symbol candidates
(``models/lab-symbol-candidates/...``) are relative to the artifact root.
``image_import_job_files.source_relative_path`` holds managed ``originals/...``
paths, so it is resolved under ``<artifact_root>/data`` and the
job's ``input_payload.source_directory`` is checked separately as a directory.

"Legacy-dependent" counts: resolved files under the legacy prefix, manifest
strings under it, ``jobs.input_payload.source_directory`` values and
``remote_manual_selection_sessions.host_base_path`` values under it. Without
``--forbid-prefix`` they are reported only; with it every one of them is an
error. Missing files, invalid paths and unmapped columns that hold data are
always errors (exit code 1).

The connection uses the owner URL of ``ApiSettings`` (the local superuser owner
bypasses the game row-level security) inside read-only transactions.

Usage (repository root, PowerShell):

    .venv\\Scripts\\python.exe scripts/verify_artifact_references.py --output <report.json>
    .venv\\Scripts\\python.exe scripts/verify_artifact_references.py `
        --forbid-prefix C:\\Users\\tuszy\\Documents\\game_predicotr
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

DEFAULT_LEGACY_PREFIX = r"C:\Users\tuszy\Documents\game_predicotr"
ROOT_DATA = "artifact_root/data"
ROOT_ARTIFACT = "artifact_root"
# Imported lab symbol candidates keep their files in
# <artifact_root>/models/lab-symbol-candidates/<fingerprint> (domain
# lab_symbol_candidate.py) and every symbol_model_iterations column of such a
# row stores that artifact-root-relative path.
ARTIFACT_ROOT_PREFIXES: tuple[str, ...] = ("models/lab-symbol-candidates/",)
SAMPLE_LIMIT = 20
MANIFEST_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True)
class ColumnMapping:
    schema: str
    table: str
    column: str
    root: str
    manifest: bool = False

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.schema, self.table, self.column)

    @property
    def name(self) -> str:
        return f"{self.schema}.{self.table}.{self.column}"


def _m(table: str, column: str, root: str = ROOT_DATA, *, manifest: bool = False) -> ColumnMapping:
    schema, _, name = table.partition(".")
    return ColumnMapping(schema, name, column, root, manifest)


COLUMN_MAPPINGS: tuple[ColumnMapping, ...] = (
    _m(
        "game_data_v2.browser_selection_retention_states",
        "managed_manifest_relative_path",
        manifest=True,
    ),
    _m("game_data_v2.curated_image_import_sources", "manifest_relative_path", manifest=True),
    _m(
        "game_data_v2.image_board_geometry_pending",
        "processing_manifest_relative_path",
        manifest=True,
    ),
    _m("game_data_v2.image_board_geometry_pending", "source_relative_path"),
    _m("game_data_v2.image_board_geometry_revisions", "board_relative_path"),
    _m("game_data_v2.image_import_geometry_guard_decisions", "source_relative_path"),
    _m(
        "game_data_v2.image_import_geometry_guard_resolution_manifests",
        "manifest_relative_path",
        manifest=True,
    ),
    _m("game_data_v2.image_import_job_files", "source_relative_path"),
    _m("game_data_v2.image_page_source_exclusions", "source_relative_path"),
    _m("game_data_v2.image_symbol_review_cells", "crop_relative_path"),
    _m("game_data_v2.recognized_boards", "board_relative_path"),
    _m("game_data_v2.review_items", "board_relative_path"),
    _m("game_data_v2.source_images", "relative_path"),
    _m("game_data_v2.symbol_model_iterations", "candidate_manifest_relative_path", manifest=True),
    _m("game_data_v2.symbol_model_iterations", "checkpoint_relative_path"),
    _m("game_data_v2.symbol_model_iterations", "dataset_manifest_relative_path", manifest=True),
    _m("game_data_v2.symbol_model_iterations", "gate_report_relative_path"),
    _m(
        "game_data_v2.symbol_model_iterations",
        "origin_manifest_relative_path",
        ROOT_ARTIFACT,
        manifest=True,
    ),
    _m("game_data_v2.symbol_reference_images", "image_relative_path"),
    _m("game_data_v2.verified_training_cohorts", "artifact_relative_path"),
    _m("public.storage_gc_runs", "manifest_relative_path", manifest=True),
    _m("public.symbols", "image_path"),
)

# Columns that match the discovery pattern but are not relative file paths.
EXCLUDED_COLUMNS: dict[tuple[str, str, str], str] = {
    ("public", "paylines", "row_path"): "integer array of payline rows, not a file path",
    (
        "public",
        "remote_manual_selection_sessions",
        "host_base_path",
    ): "absolute host directory, checked separately as a directory",
}

_DISCOVERY_SQL = """
select c.table_schema, c.table_name, c.column_name
from information_schema.columns c
join pg_namespace n on n.nspname = c.table_schema
join pg_class t on t.relnamespace = n.oid and t.relname = c.table_name
where c.table_schema in ('public', 'game_data_v2')
  and t.relkind in ('r', 'p')
  and not t.relispartition
  and (c.column_name like '%\\_path' or c.column_name = 'relative_path')
order by 1, 2, 3
"""


def normalize_prefix(value: str) -> str:
    """Case-insensitive Windows form without a trailing separator."""

    return value.strip().replace("/", "\\").rstrip("\\").casefold()


def is_under_prefix(value: str, prefix: str) -> bool:
    if not prefix:
        return False
    normalized = normalize_prefix(value)
    wanted = normalize_prefix(prefix)
    return normalized == wanted or normalized.startswith(wanted + "\\")


def resolve_reference(value: str, root: str, artifact_root: Path) -> Path | None:
    """Return the file the application resolves for ``value``; ``None`` if invalid."""

    text = value.strip().replace("\\", "/")
    if not text:
        return None
    windows = PureWindowsPath(value.strip())
    pure = PurePosixPath(text)
    if pure.is_absolute() or windows.drive or windows.is_absolute() or ".." in pure.parts:
        return None
    if pure.parts[0] == "data" or pure.as_posix().startswith(ARTIFACT_ROOT_PREFIXES):
        return artifact_root.joinpath(*pure.parts)
    base = artifact_root / "data" if root == ROOT_DATA else artifact_root
    return base.joinpath(*pure.parts)


def find_prefixed_strings(value: Any, prefix: str) -> list[str]:
    """Every string anywhere in a decoded JSON value that lies under ``prefix``."""

    found: list[str] = []
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if is_under_prefix(item, prefix):
                found.append(item)
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return found


@dataclass
class ColumnReport:
    name: str
    root: str
    manifest: bool
    rows_total: int = 0
    rows_non_null: int = 0
    distinct_paths: int = 0
    existing: int = 0
    missing: int = 0
    invalid: int = 0
    legacy_resolved: int = 0
    manifests_read: int = 0
    manifests_unreadable: int = 0
    manifest_legacy_entries: int = 0
    missing_samples: list[str] = field(default_factory=list)
    invalid_samples: list[str] = field(default_factory=list)
    manifest_legacy_samples: list[str] = field(default_factory=list)
    manifest_unreadable_samples: list[str] = field(default_factory=list)


def check_column(
    mapping: ColumnMapping,
    paths: Iterable[str],
    artifact_root: Path,
    legacy_prefix: str,
) -> ColumnReport:
    """Check distinct non-null path values of one column."""

    report = ColumnReport(mapping.name, mapping.root, mapping.manifest)
    for value in paths:
        report.distinct_paths += 1
        resolved = resolve_reference(value, mapping.root, artifact_root)
        if resolved is None:
            report.invalid += 1
            if len(report.invalid_samples) < SAMPLE_LIMIT:
                report.invalid_samples.append(value)
            continue
        if is_under_prefix(str(resolved), legacy_prefix):
            report.legacy_resolved += 1
        if not resolved.is_file():
            report.missing += 1
            if len(report.missing_samples) < SAMPLE_LIMIT:
                report.missing_samples.append(value)
            continue
        report.existing += 1
        if mapping.manifest:
            _scan_manifest(report, resolved, value, legacy_prefix)
    return report


def _scan_manifest(report: ColumnReport, resolved: Path, value: str, legacy_prefix: str) -> None:
    try:
        if resolved.stat().st_size > MANIFEST_MAX_BYTES:
            raise ValueError("manifest larger than the scan limit")
        decoded = json.loads(resolved.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        report.manifests_unreadable += 1
        if len(report.manifest_unreadable_samples) < SAMPLE_LIMIT:
            report.manifest_unreadable_samples.append(f"{value}: {error}")
        return
    report.manifests_read += 1
    hits = find_prefixed_strings(decoded, legacy_prefix)
    report.manifest_legacy_entries += len(hits)
    for hit in hits:
        if len(report.manifest_legacy_samples) >= SAMPLE_LIMIT:
            break
        report.manifest_legacy_samples.append(f"{value}: {hit}")


@dataclass
class DirectoryReport:
    name: str
    rows: int = 0
    legacy_prefixed: int = 0
    existing: int = 0
    missing: int = 0
    legacy_equivalent_existing: int = 0
    by_status: dict[str, dict[str, int]] = field(default_factory=dict)
    missing_samples: list[str] = field(default_factory=list)


def check_directories(
    name: str,
    rows: Iterable[tuple[str, str, str]],
    legacy_prefix: str,
    repository_root: Path,
) -> DirectoryReport:
    """Rows are ``(id, status, directory)``; directories must be absolute."""

    report = DirectoryReport(name)
    for row_id, status, directory in rows:
        report.rows += 1
        counts = report.by_status.setdefault(status, {"rows": 0, "legacy_prefixed": 0})
        counts["rows"] += 1
        if Path(directory).is_dir():
            report.existing += 1
        else:
            report.missing += 1
            if len(report.missing_samples) < SAMPLE_LIMIT:
                report.missing_samples.append(f"{row_id} {status} {directory}")
        if is_under_prefix(directory, legacy_prefix):
            report.legacy_prefixed += 1
            counts["legacy_prefixed"] += 1
            tail = directory.strip().replace("/", "\\")[len(legacy_prefix.rstrip("\\/")) :]
            if (repository_root / tail.lstrip("\\")).is_dir():
                report.legacy_equivalent_existing += 1
    return report


@dataclass
class Discovery:
    mapped: list[ColumnMapping]
    unmapped: list[tuple[str, str, str]]
    excluded: list[tuple[str, str, str]]
    absent: list[ColumnMapping]


def classify_columns(discovered: Iterable[tuple[str, str, str]]) -> Discovery:
    by_key = {mapping.key: mapping for mapping in COLUMN_MAPPINGS}
    seen: set[tuple[str, str, str]] = set()
    result = Discovery([], [], [], [])
    for key in discovered:
        seen.add(key)
        if key in EXCLUDED_COLUMNS:
            result.excluded.append(key)
        elif key in by_key:
            result.mapped.append(by_key[key])
        else:
            result.unmapped.append(key)
    result.absent = [mapping for mapping in COLUMN_MAPPINGS if mapping.key not in seen]
    return result


def evaluate(report: dict[str, Any], forbid_prefix: str | None) -> list[str]:
    """Error codes of a finished report; empty list means the gate passes."""

    errors: list[str] = []
    columns = report["columns"]
    missing = sum(column["missing"] for column in columns)
    invalid = sum(column["invalid"] for column in columns)
    unreadable = sum(column["manifests_unreadable"] for column in columns)
    if missing:
        errors.append(f"MISSING_FILES {missing}")
    if invalid:
        errors.append(f"INVALID_PATHS {invalid}")
    if unreadable:
        errors.append(f"UNREADABLE_MANIFESTS {unreadable}")
    with_data = [item["column"] for item in report["unmapped_columns"] if item["rows_non_null"]]
    if with_data:
        errors.append(f"UNMAPPED_COLUMNS_WITH_DATA {', '.join(with_data)}")
    if forbid_prefix:
        legacy = report["legacy"]
        for label in (
            "resolved_files",
            "manifest_entries",
            "job_source_directories",
            "remote_sessions",
        ):
            if legacy[label]:
                errors.append(f"FORBIDDEN_PREFIX_{label.upper()} {legacy[label]}")
    return errors


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _run(connection: Any, sql: str) -> list[Any]:
    from sqlalchemy import text

    return list(connection.execute(text(sql)))


def build_report(
    connection: Any,
    artifact_root: Path,
    repository_root: Path,
    legacy_prefix: str,
    progress: Any,
) -> dict[str, Any]:
    discovery = classify_columns(
        (str(row[0]), str(row[1]), str(row[2])) for row in _run(connection, _DISCOVERY_SQL)
    )
    columns: list[dict[str, Any]] = []
    for mapping in discovery.mapped:
        started = time.monotonic()
        table = f"{_quote(mapping.schema)}.{_quote(mapping.table)}"
        column = _quote(mapping.column)
        total, non_null = _run(connection, f"select count(*), count({column}) from {table}")[0]
        paths = (
            str(row[0])
            for row in _run(
                connection,
                f"select distinct {column}::text from {table} where {column} is not null",
            )
        )
        column_report = check_column(mapping, paths, artifact_root, legacy_prefix)
        column_report.rows_total = int(total)
        column_report.rows_non_null = int(non_null)
        columns.append(column_report.__dict__)
        progress(
            f"{mapping.name}: rows={total} non_null={non_null} "
            f"distinct={column_report.distinct_paths} "
            f"missing={column_report.missing} invalid={column_report.invalid} "
            f"seconds={time.monotonic() - started:.0f}"
        )
    unmapped: list[dict[str, Any]] = []
    for schema, table_name, column_name in discovery.unmapped:
        count = _run(
            connection,
            f"select count({_quote(column_name)}) from {_quote(schema)}.{_quote(table_name)}",
        )[0][0]
        unmapped.append(
            {"column": f"{schema}.{table_name}.{column_name}", "rows_non_null": int(count)}
        )
    jobs = check_directories(
        "public.jobs.input_payload.source_directory",
        (
            (str(row[0]), str(row[1]), str(row[2]))
            for row in _run(
                connection,
                "select id::text, status::text, input_payload::jsonb ->> 'source_directory' "
                "from public.jobs where input_payload::jsonb ? 'source_directory' "
                "and coalesce(input_payload::jsonb ->> 'source_directory', '') <> '' "
                "order by created_at",
            )
        ),
        legacy_prefix,
        repository_root,
    )
    sessions = check_directories(
        "public.remote_manual_selection_sessions.host_base_path",
        (
            (str(row[0]), str(row[1]), str(row[2]))
            for row in _run(
                connection,
                "select id::text, status::text, host_base_path from "
                "public.remote_manual_selection_sessions order by created_at",
            )
        ),
        legacy_prefix,
        repository_root,
    )
    return {
        "artifact_root": str(artifact_root),
        "repository_root": str(repository_root),
        "legacy_prefix": legacy_prefix,
        "columns": columns,
        "unmapped_columns": unmapped,
        "excluded_columns": [
            {"column": ".".join(key), "reason": EXCLUDED_COLUMNS[key]} for key in discovery.excluded
        ],
        "mapped_but_absent": [mapping.name for mapping in discovery.absent],
        "directories": [jobs.__dict__, sessions.__dict__],
        "totals": {
            "distinct_paths": sum(item["distinct_paths"] for item in columns),
            "existing": sum(item["existing"] for item in columns),
            "missing": sum(item["missing"] for item in columns),
            "invalid": sum(item["invalid"] for item in columns),
            "manifests_read": sum(item["manifests_read"] for item in columns),
        },
        "legacy": {
            "resolved_files": sum(item["legacy_resolved"] for item in columns),
            "manifest_entries": sum(item["manifest_legacy_entries"] for item in columns),
            "job_source_directories": jobs.legacy_prefixed,
            "remote_sessions": sessions.legacy_prefixed,
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--artifact-root", type=Path, default=None)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--legacy-prefix", default=DEFAULT_LEGACY_PREFIX)
    parser.add_argument("--forbid-prefix", default=None)
    parser.add_argument("--output", type=Path, default=None)
    arguments = parser.parse_args(argv)

    from game_predictor_api.config import ApiSettings
    from sqlalchemy import create_engine

    settings = ApiSettings.from_environment()
    artifact_root = (arguments.artifact_root or settings.artifact_root).resolve()
    repository_root = arguments.repository_root.resolve()
    legacy_prefix = arguments.forbid_prefix or arguments.legacy_prefix
    engine = create_engine(
        settings.owner_database_url,
        connect_args={
            "connect_timeout": 5,
            "options": "-c default_transaction_read_only=on -c statement_timeout=1800000",
        },
    )
    started = time.monotonic()

    def progress(message: str) -> None:
        print(message, flush=True)

    try:
        with engine.connect() as connection:
            report = build_report(
                connection, artifact_root, repository_root, legacy_prefix, progress
            )
            connection.rollback()
    finally:
        engine.dispose()
    report["seconds"] = round(time.monotonic() - started, 1)
    errors = evaluate(report, arguments.forbid_prefix)
    report["errors"] = errors
    if arguments.output is not None:
        arguments.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print(json.dumps({"totals": report["totals"], "legacy": report["legacy"]}, sort_keys=True))
    for item in report["unmapped_columns"]:
        print(f"unmapped {item['column']} rows_non_null={item['rows_non_null']}")
    for directory in report["directories"]:
        print(
            f"{directory['name']}: rows={directory['rows']} legacy={directory['legacy_prefixed']} "
            f"existing={directory['existing']} missing={directory['missing']} "
            f"legacy_equivalent_existing={directory['legacy_equivalent_existing']}"
        )
    print("RESULT: " + ("OK" if not errors else "FAIL " + "; ".join(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
