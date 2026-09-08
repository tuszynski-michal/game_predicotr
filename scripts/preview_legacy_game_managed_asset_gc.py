"""Create a read-only, reference-aware managed-asset GC preview for 777 v0.1.

The command never deletes files and never writes to PostgreSQL. It verifies
the terminal database receipt, protects paths still referenced by the database
or a live JSON manifest, and writes a deterministic preview plus JSONL details.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat as stat_module
import time
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any

from game_predictor_api.config import ApiSettings  # type: ignore[import-not-found]
from game_predictor_api.storage.database import (  # type: ignore[import-not-found]
    create_database_engine,
)
from game_predictor_api.storage.game_deletion_policy_v1 import (  # type: ignore[import-not-found]
    LEGACY_ID,
    PROTECTED_ID,
)
from sqlalchemy import text

POLICY = "legacy-game-managed-asset-gc-preview-v1"
EXECUTION_POLICY = "legacy-game-managed-asset-gc-execution-v1"
LEGACY_COMPACT_ID = LEGACY_ID.replace("-", "")
PROTECTED_OPERATOR_ROOT = Path(r"C:\Users\user\Documents\777")

DIRECT_PATH_COLUMNS = (
    ("browser_selection_retention_states", "managed_manifest_relative_path"),
    ("cell_observations", "crop_relative_path"),
    ("image_board_geometry_pending", "processing_manifest_relative_path"),
    ("image_board_geometry_pending", "source_relative_path"),
    ("image_board_geometry_revisions", "board_relative_path"),
    ("image_import_job_files", "source_relative_path"),
    ("image_sequence_alternatives", "source_relative_path"),
    ("image_symbol_review_cells", "crop_relative_path"),
    ("legacy_board_search_archive_documents", "board_relative_path"),
    ("recognized_boards", "board_relative_path"),
    ("source_images", "relative_path"),
    ("symbol_model_iterations", "candidate_manifest_relative_path"),
    ("symbol_model_iterations", "checkpoint_relative_path"),
    ("symbol_model_iterations", "dataset_manifest_relative_path"),
    ("symbol_model_iterations", "gate_report_relative_path"),
    ("symbol_reference_images", "image_relative_path"),
    ("symbols", "image_path"),
    ("verified_training_cohorts", "artifact_relative_path"),
)

JSON_PATH_COLUMNS = (
    ("image_board_geometry_revisions", "crop_artifacts"),
    ("image_review_items", "snapshot"),
    ("jobs", "checkpoint_payload"),
    ("jobs", "input_payload"),
    ("verified_training_cohort_items", "board_manifest"),
)


class PreviewBlocked(RuntimeError):
    pass


def _required_confirmation(preview_sha256: str) -> str:
    return (
        f"DELETE MANAGED ASSETS 777 v0.1 {preview_sha256}; "
        r"PRESERVE new-siedem AND C:\Users\user\Documents\777"
    )


def _is_link_or_reparse(path: Path, stat: os.stat_result | None = None) -> bool:
    if path.is_symlink():
        return True
    current = stat if stat is not None else path.lstat()
    reparse_flag = getattr(stat_module, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(getattr(current, "st_file_attributes", 0) & reparse_flag)


def _path_values(value: Any, prefix: str = "") -> Iterator[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            location = f"{prefix}.{key}" if prefix else key
            normalized = key.lower().replace("_", "")
            if isinstance(child, str) and "path" in normalized:
                yield child
            elif isinstance(child, dict | list):
                yield from _path_values(child, location)
    elif isinstance(value, list):
        for child in value:
            if isinstance(child, str) and "path" in prefix.lower():
                yield child
            else:
                yield from _path_values(child, prefix)


def _managed_relative(value: str) -> str | None:
    normalized = value.strip().replace("\\", "/")
    if not normalized or ":" in normalized or normalized.startswith("/"):
        return None
    relative = PurePosixPath(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    parts = relative.parts
    if parts and parts[0] == "artifacts":
        parts = parts[1:]
    if not parts:
        return None
    if parts[0] != "data":
        parts = ("data", *parts)
    return PurePosixPath(*parts).as_posix()


def _validate_managed_data_root(artifact_root: Path, managed_data_root: Path | None) -> Path:
    artifact_root = artifact_root.resolve()
    active_root = (artifact_root / "data").resolve()
    selected = active_root if managed_data_root is None else managed_data_root.resolve()
    if not selected.exists() or not selected.is_dir() or _is_link_or_reparse(selected):
        raise PreviewBlocked("managed data root is missing or unsafe")
    if selected != active_root:
        if selected.parent != artifact_root or not selected.name.startswith("data.detached-"):
            raise PreviewBlocked(
                "detached managed data root must be a direct data.detached-* child"
            )
        if not active_root.exists() or not active_root.is_dir() or _is_link_or_reparse(active_root):
            raise PreviewBlocked("active managed data root is missing or unsafe")
        if next(active_root.iterdir(), None) is not None:
            raise PreviewBlocked(
                "active managed data root must remain empty while detached GC resumes"
            )
    protected = PROTECTED_OPERATOR_ROOT.resolve()
    if selected == protected or protected in selected.parents or selected in protected.parents:
        raise PreviewBlocked("operator source root entered managed execution")
    return selected


def _managed_root_descriptor(managed_data_root: Path) -> dict[str, Any]:
    current = managed_data_root.stat()
    return {
        "path": str(managed_data_root.resolve()),
        "stDev": int(current.st_dev),
        "stIno": int(current.st_ino),
    }


def _logical_relative(path: Path, managed_data_root: Path) -> str:
    return PurePosixPath("data", *path.relative_to(managed_data_root).parts).as_posix()


def _artifact_path(
    artifact_root: Path,
    relative: str,
    *,
    managed_data_root: Path | None = None,
) -> Path:
    data_root = (
        (artifact_root / "data").resolve()
        if managed_data_root is None
        else managed_data_root.resolve()
    )
    parts = PurePosixPath(relative).parts
    if not parts or parts[0] != "data":
        raise PreviewBlocked(f"path is outside the logical managed data root: {relative}")
    candidate = data_root.joinpath(*parts[1:]).resolve()
    if candidate != data_root and data_root not in candidate.parents:
        raise PreviewBlocked(f"path escapes managed data root: {relative}")
    protected = PROTECTED_OPERATOR_ROOT.resolve()
    if candidate == protected or protected in candidate.parents:
        raise PreviewBlocked("operator source root entered managed preview")
    return candidate


def _operation_guard(connection: Any) -> dict[str, Any]:
    operation = (
        connection.execute(
            text(
                """
SELECT status,stage_index,batch_sequence,failure_code,archive_sha256,archive_proof
FROM public.game_deletion_operations
WHERE game_id=CAST(:game_id AS uuid)
"""
            ),
            {"game_id": LEGACY_ID},
        )
        .mappings()
        .one()
    )
    if operation["status"] != "database_done" or operation["failure_code"] is not None:
        raise PreviewBlocked("legacy database deletion is not terminal")
    identities = connection.execute(
        text(
            """
SELECT id::text,code,name FROM public.games
WHERE id IN (CAST(:legacy AS uuid),CAST(:protected AS uuid))
"""
        ),
        {"legacy": LEGACY_ID, "protected": PROTECTED_ID},
    ).all()
    actual = {row.id: (row.code, row.name) for row in identities}
    if LEGACY_ID in actual or actual.get(PROTECTED_ID) != ("new-siedem", "777"):
        raise PreviewBlocked("legacy/protected game identity guard failed")
    active = int(
        connection.scalar(
            text("SELECT count(*) FROM public.jobs WHERE status IN ('created','processing')")
        )
        or 0
    )
    if active:
        raise PreviewBlocked(f"{active} active jobs block the filesystem snapshot")
    return dict(operation)


def _collect_live_paths(connection: Any) -> set[str]:
    paths: set[str] = set()
    discovered = {
        (str(row.table_name), str(row.column_name))
        for row in connection.execute(
            text(
                """
SELECT table_name,column_name
FROM information_schema.columns
WHERE table_schema='public'
  AND data_type IN ('character varying','text')
  AND lower(column_name) LIKE '%path%'
"""
            )
        )
    }
    direct_columns = tuple(sorted(set(DIRECT_PATH_COLUMNS) | discovered))
    for table_name, column_name in direct_columns:
        print(f"live refs: {table_name}.{column_name}", flush=True)
        rows = (
            connection.execution_options(stream_results=True)
            .execute(
                text(
                    f'SELECT "{column_name}" FROM public."{table_name}" '
                    f'WHERE "{column_name}" IS NOT NULL'
                )
            )
            .scalars()
        )
        for value in rows:
            if isinstance(value, str) and (relative := _managed_relative(value)) is not None:
                paths.add(relative)
    for table_name, column_name in JSON_PATH_COLUMNS:
        print(f"live refs: {table_name}.{column_name}", flush=True)
        rows = (
            connection.execution_options(stream_results=True)
            .execute(
                text(
                    f'SELECT "{column_name}" FROM public."{table_name}" '
                    f'WHERE "{column_name}" IS NOT NULL'
                )
            )
            .scalars()
        )
        for value in rows:
            for raw_path in _path_values(value):
                if (relative := _managed_relative(raw_path)) is not None:
                    paths.add(relative)
    return paths


def _expand_live_manifests(
    artifact_root: Path,
    live_paths: set[str],
    *,
    managed_data_root: Path | None = None,
) -> None:
    pending = [path for path in live_paths if path.lower().endswith(".json")]
    visited: set[str] = set()
    while pending:
        relative = pending.pop()
        if relative in visited:
            continue
        visited.add(relative)
        path = _artifact_path(artifact_root, relative, managed_data_root=managed_data_root)
        if (
            not path.is_file()
            or _is_link_or_reparse(path)
            or path.stat().st_size > 128 * 1024 * 1024
        ):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        for raw_path in _path_values(payload):
            normalized = _managed_relative(raw_path)
            if normalized is None or normalized in live_paths:
                continue
            live_paths.add(normalized)
            if normalized.lower().endswith(".json"):
                pending.append(normalized)


def _walk_files(root: Path) -> Iterator[tuple[Path, os.stat_result]]:
    stack = [root]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            ordered = sorted(entries, key=lambda item: item.name.casefold())
            directories: list[Path] = []
            for entry in ordered:
                entry_stat = entry.stat(follow_symlinks=False)
                if _is_link_or_reparse(Path(entry.path), entry_stat):
                    raise PreviewBlocked(f"symlink/reparse point inside candidate: {entry.path}")
                if entry.is_dir(follow_symlinks=False):
                    directories.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    yield Path(entry.path), entry_stat
            stack.extend(reversed(directories))


def _measure_tree(
    artifact_root: Path,
    root_relative: str,
    live_paths: set[str],
    detail_handle: Any,
) -> dict[str, Any]:
    root = _artifact_path(artifact_root, root_relative)
    digest = hashlib.sha256()
    candidate_count = candidate_bytes = protected_count = protected_bytes = 0
    last_progress = time.monotonic()
    if not root.exists():
        return {
            "root": root_relative,
            "exists": False,
            "candidateFiles": 0,
            "candidateBytes": 0,
            "protectedFiles": 0,
            "protectedBytes": 0,
            "treeSha256": digest.hexdigest(),
        }
    if not root.is_dir() or _is_link_or_reparse(root):
        raise PreviewBlocked(f"candidate root is not a regular directory: {root_relative}")
    live_prefix = root_relative.rstrip("/") + "/"
    fully_unreferenced = not any(
        path == root_relative or path.startswith(live_prefix) for path in live_paths
    )
    for path, stat in _walk_files(root):
        relative = _logical_relative(path, (artifact_root / "data").resolve())
        protected = False if fully_unreferenced else relative in live_paths
        encoded = f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}"
        digest.update(encoded.encode("utf-8"))
        digest.update(b"\n")
        if protected:
            protected_count += 1
            protected_bytes += stat.st_size
        else:
            candidate_count += 1
            candidate_bytes += stat.st_size
            if not fully_unreferenced:
                detail_handle.write(
                    json.dumps(
                        {"path": relative, "size": stat.st_size, "mtimeNs": stat.st_mtime_ns},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
        if time.monotonic() - last_progress >= 10:
            print(
                f"scan {root_relative}: {candidate_count + protected_count} files, "
                f"{candidate_bytes / (1024**3):.2f} GiB candidate",
                flush=True,
            )
            last_progress = time.monotonic()
    summary = {
        "root": root_relative,
        "exists": True,
        "wholeTreeCandidate": fully_unreferenced,
        "candidateFiles": candidate_count,
        "candidateBytes": candidate_bytes,
        "protectedFiles": protected_count,
        "protectedBytes": protected_bytes,
        "treeSha256": digest.hexdigest(),
    }
    if fully_unreferenced:
        detail_handle.write(json.dumps(summary, sort_keys=True, separators=(",", ":")) + "\n")
    return summary


def _measure_source_groups(
    artifact_root: Path,
    root_relative: str,
    live_paths: set[str],
    detail_handle: Any,
) -> dict[str, Any]:
    """Measure removable checksum directories while retaining whole live sources."""
    root = _artifact_path(artifact_root, root_relative)
    if not root.exists():
        return {
            "root": root_relative,
            "exists": False,
            "candidateGroups": 0,
            "candidateFiles": 0,
            "candidateBytes": 0,
            "protectedGroups": 0,
            "treeSha256": hashlib.sha256().hexdigest(),
        }
    if not root.is_dir() or _is_link_or_reparse(root):
        raise PreviewBlocked(f"candidate root is not a regular directory: {root_relative}")
    root_parts = PurePosixPath(root_relative).parts
    protected_groups: set[str] = set()
    for live_path in live_paths:
        parts = PurePosixPath(live_path).parts
        if parts[: len(root_parts)] != root_parts:
            continue
        if len(parts) < len(root_parts) + 2:
            raise PreviewBlocked(f"broad live reference blocks source tree: {live_path}")
        protected_groups.add(PurePosixPath(*parts[: len(root_parts) + 2]).as_posix())

    digest = hashlib.sha256()
    candidate_groups = candidate_count = candidate_bytes = 0
    protected_group_count = 0
    last_progress = time.monotonic()
    with os.scandir(root) as bucket_entries:
        buckets = sorted(bucket_entries, key=lambda item: item.name.casefold())
    for bucket in buckets:
        bucket_path = Path(bucket.path)
        if _is_link_or_reparse(
            bucket_path, bucket.stat(follow_symlinks=False)
        ) or not bucket.is_dir(follow_symlinks=False):
            raise PreviewBlocked(f"unexpected source-direct entry: {bucket.path}")
        with os.scandir(bucket.path) as source_entries:
            sources = sorted(source_entries, key=lambda item: item.name.casefold())
        for source in sources:
            source_path = Path(source.path)
            if _is_link_or_reparse(
                source_path, source.stat(follow_symlinks=False)
            ) or not source.is_dir(follow_symlinks=False):
                raise PreviewBlocked(f"unexpected source-direct bucket entry: {source.path}")
            group_path = Path(source.path)
            group_relative = _logical_relative(group_path, (artifact_root / "data").resolve())
            if group_relative in protected_groups:
                protected_group_count += 1
                digest.update(f"protected\0{group_relative}\n".encode())
                continue
            group_digest = hashlib.sha256()
            group_files = group_bytes = 0
            for path, stat in _walk_files(group_path):
                relative = _logical_relative(path, (artifact_root / "data").resolve())
                encoded = f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}"
                group_digest.update(encoded.encode())
                group_digest.update(b"\n")
                group_files += 1
                group_bytes += stat.st_size
            group_record = {
                "root": group_relative,
                "wholeTreeCandidate": True,
                "candidateFiles": group_files,
                "candidateBytes": group_bytes,
                "treeSha256": group_digest.hexdigest(),
            }
            encoded_record = json.dumps(group_record, sort_keys=True, separators=(",", ":"))
            detail_handle.write(encoded_record + "\n")
            digest.update(encoded_record.encode())
            digest.update(b"\n")
            candidate_groups += 1
            candidate_count += group_files
            candidate_bytes += group_bytes
            if time.monotonic() - last_progress >= 10:
                print(
                    f"scan {root_relative}: {candidate_groups} groups, {candidate_count} files, "
                    f"{candidate_bytes / (1024**3):.2f} GiB candidate",
                    flush=True,
                )
                last_progress = time.monotonic()
    return {
        "root": root_relative,
        "exists": True,
        "wholeTreeCandidate": False,
        "candidateGroups": candidate_groups,
        "candidateFiles": candidate_count,
        "candidateBytes": candidate_bytes,
        "protectedGroups": protected_group_count,
        "protectedFiles": None,
        "protectedBytes": None,
        "treeSha256": digest.hexdigest(),
    }


def _canonical_sha(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _write_live_path_cache(path: Path, live_paths: set[str]) -> dict[str, Any]:
    encoded = "".join(f"{value}\n" for value in sorted(live_paths)).encode("utf-8")
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(encoded)
    os.replace(temporary, path)
    return {
        "path": str(path.resolve()),
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "count": len(live_paths),
    }


def _load_live_path_cache(
    descriptor: Any, *, cache_path: Path, expected_wal_lsn: str
) -> set[str] | None:
    if not isinstance(descriptor, dict) or descriptor.get("walLsn") != expected_wal_lsn:
        return None
    if Path(str(descriptor.get("path", ""))).resolve() != cache_path.resolve():
        raise PreviewBlocked("live-path cache escaped the preview directory")
    if not cache_path.is_file() or _is_link_or_reparse(cache_path):
        raise PreviewBlocked("live-path cache is missing or unsafe")
    encoded = cache_path.read_bytes()
    if hashlib.sha256(encoded).hexdigest() != descriptor.get("sha256"):
        raise PreviewBlocked("live-path cache checksum is invalid")
    values = encoded.decode("utf-8").splitlines()
    if len(values) != descriptor.get("count") or values != sorted(set(values)):
        raise PreviewBlocked("live-path cache contents are invalid")
    return set(values)


def _load_execution_preview(
    preview_path: Path,
    *,
    expected_preview_sha256: str,
    confirmation: str,
) -> tuple[dict[str, Any], Path]:
    preview_path = preview_path.resolve()
    try:
        payload = json.loads(preview_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreviewBlocked(f"preview cannot be read: {error}") from error
    if payload.get("policy") != POLICY or payload.get("deletionExecuted") is not False:
        raise PreviewBlocked("preview policy or execution marker is invalid")
    if payload.get("gameId") != LEGACY_ID or payload.get("protectedGameId") != PROTECTED_ID:
        raise PreviewBlocked("preview game identity is invalid")
    actual_sha = str(payload.get("previewSha256", ""))
    fingerprint_payload = {
        key: value
        for key, value in payload.items()
        if key not in {"createdAtUnix", "previewSha256"}
    }
    if actual_sha != _canonical_sha(fingerprint_payload):
        raise PreviewBlocked("preview payload checksum is invalid")
    if expected_preview_sha256 != actual_sha:
        raise PreviewBlocked("expected preview checksum does not match")
    if confirmation != _required_confirmation(actual_sha):
        raise PreviewBlocked("exact managed-asset deletion confirmation is required")
    details = payload.get("details")
    if not isinstance(details, dict):
        raise PreviewBlocked("preview detail descriptor is missing")
    detail_path = Path(str(details.get("path", ""))).resolve()
    if detail_path.parent != preview_path.parent or detail_path.suffixes[-2:] != [
        ".paths",
        ".jsonl",
    ]:
        raise PreviewBlocked("preview detail path is outside the preview directory")
    if not detail_path.is_file() or _is_link_or_reparse(detail_path):
        raise PreviewBlocked("preview details are missing or unsafe")
    if hashlib.sha256(detail_path.read_bytes()).hexdigest() != details.get("sha256"):
        raise PreviewBlocked("preview detail checksum is invalid")
    return payload, detail_path


def _lock_reference_tables(connection: Any) -> None:
    discovered = {
        str(row.table_name)
        for row in connection.execute(
            text(
                """
SELECT DISTINCT table_name
FROM information_schema.columns
WHERE table_schema='public'
  AND data_type IN ('character varying','text')
  AND lower(column_name) LIKE '%path%'
"""
            )
        )
    }
    tables = (
        discovered
        | {table for table, _ in DIRECT_PATH_COLUMNS}
        | {table for table, _ in JSON_PATH_COLUMNS}
        | {"games", "jobs", "game_deletion_operations"}
    )
    for table_name in sorted(tables):
        if re.fullmatch(r"[a-z][a-z0-9_]*", table_name) is None:
            raise PreviewBlocked(f"unsafe database table name: {table_name}")
        connection.execute(text(f'LOCK TABLE public."{table_name}" IN SHARE MODE NOWAIT'))


def _record_target(record: dict[str, Any]) -> str:
    value = record.get("path", record.get("root"))
    if not isinstance(value, str) or _managed_relative(value) != value:
        raise PreviewBlocked("detail record contains an unsafe managed path")
    return value


def _record_is_live(record: dict[str, Any], live_paths: set[str]) -> bool:
    target = _record_target(record)
    if record.get("wholeTreeCandidate") is True:
        prefix = target.rstrip("/") + "/"
        return any(path == target or path.startswith(prefix) for path in live_paths)
    return target in live_paths


def _tree_fingerprint(
    artifact_root: Path,
    root_relative: str,
    *,
    managed_data_root: Path | None = None,
) -> tuple[int, int, str]:
    actual_root = (
        (artifact_root / "data").resolve()
        if managed_data_root is None
        else managed_data_root.resolve()
    )
    root = _artifact_path(artifact_root, root_relative, managed_data_root=actual_root)
    digest = hashlib.sha256()
    count = size = 0
    for path, stat in _walk_files(root):
        relative = _logical_relative(path, actual_root)
        digest.update(f"{relative}\0{stat.st_size}\0{stat.st_mtime_ns}".encode())
        digest.update(b"\n")
        count += 1
        size += stat.st_size
    return count, size, digest.hexdigest()


def _verify_record(
    artifact_root: Path,
    record: dict[str, Any],
    *,
    managed_data_root: Path | None = None,
) -> None:
    relative = _record_target(record)
    target = _artifact_path(artifact_root, relative, managed_data_root=managed_data_root)
    if _is_link_or_reparse(target):
        raise PreviewBlocked(f"candidate became a symlink: {relative}")
    if record.get("wholeTreeCandidate") is True:
        if not target.is_dir():
            raise PreviewBlocked(f"candidate tree is missing or changed: {relative}")
        actual = _tree_fingerprint(artifact_root, relative, managed_data_root=managed_data_root)
        expected = (
            int(record.get("candidateFiles", -1)),
            int(record.get("candidateBytes", -1)),
            str(record.get("treeSha256", "")),
        )
        if actual != expected:
            raise PreviewBlocked(f"candidate tree drifted since preview: {relative}")
        return
    if not target.is_file():
        raise PreviewBlocked(f"candidate file is missing or changed: {relative}")
    stat = target.stat()
    if stat.st_size != record.get("size") or stat.st_mtime_ns != record.get("mtimeNs"):
        raise PreviewBlocked(f"candidate file drifted since preview: {relative}")


def _quarantine_target(quarantine_root: Path, relative: str) -> Path:
    candidate = quarantine_root.joinpath(*PurePosixPath(relative).parts).resolve()
    if candidate == quarantine_root or quarantine_root not in candidate.parents:
        raise PreviewBlocked(f"quarantine path escapes its root: {relative}")
    return candidate


def _native_long_path(path: Path) -> Path:
    resolved = str(path.resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return Path(resolved)
    if resolved.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + resolved[2:])
    return Path("\\\\?\\" + resolved)


def _delete_quarantined(path: Path, *, parallel_children: bool = True) -> None:
    if not path.exists():
        return
    if _is_link_or_reparse(path):
        raise PreviewBlocked(f"quarantined target became a symlink: {path}")
    native_path = _native_long_path(path)
    if path.is_dir():
        children = list(path.iterdir())
        if parallel_children and len(children) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(children))) as executor:
                futures = [executor.submit(_delete_quarantine_child, child) for child in children]
                for future in futures:
                    future.result()
            with suppress(FileNotFoundError):
                native_path.rmdir()
        else:
            shutil.rmtree(native_path, onexc=_handle_rmtree_error)
    else:
        native_path.unlink()


def _delete_quarantine_child(path: Path) -> None:
    if _is_link_or_reparse(path):
        raise PreviewBlocked(f"quarantined child became a symlink: {path}")
    native_path = _native_long_path(path)
    if path.is_dir():
        shutil.rmtree(native_path, onexc=_handle_rmtree_error)
    else:
        with suppress(FileNotFoundError):
            native_path.unlink()


def _handle_rmtree_error(_function: Any, _path: str, error: BaseException) -> None:
    # Antivirus/indexing activity and overlapping directory enumeration on
    # Windows can report an entry that has already disappeared. That state is
    # the intended result, while every other filesystem error remains fatal.
    if isinstance(error, FileNotFoundError):
        return
    raise error


def _read_detail_records(detail_path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with detail_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise PreviewBlocked(f"invalid detail record at line {line_number}") from error
            if not isinstance(record, dict):
                raise PreviewBlocked(f"invalid detail record at line {line_number}")
            _record_target(record)
            records.append(record)
    return records


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PreviewBlocked(f"{label} cannot be read: {error}") from error
    if not isinstance(payload, dict):
        raise PreviewBlocked(f"{label} is not a JSON object")
    return payload


def _reconcile_interrupted_state_write(
    state_path: Path,
    state: dict[str, Any],
    *,
    expected_preview_sha256: str,
    records: list[dict[str, Any]],
    artifact_root: Path,
    managed_data_root: Path,
    quarantine_root: Path,
) -> dict[str, Any]:
    temporary = state_path.with_suffix(state_path.suffix + ".tmp")
    if not temporary.exists():
        return state
    temporary_state = _load_json_object(temporary, label="temporary execution receipt")
    if (
        temporary_state.get("policy") != EXECUTION_POLICY
        or temporary_state.get("previewSha256") != expected_preview_sha256
    ):
        raise PreviewBlocked("temporary execution receipt does not match this preview")
    canonical_line = int(state.get("nextLine", -1))
    temporary_line = int(temporary_state.get("nextLine", -1))
    pending = temporary_state.get("pending")
    if temporary_line < canonical_line:
        temporary.unlink()
        return state
    if temporary_line != canonical_line or not isinstance(pending, dict):
        raise PreviewBlocked("temporary execution receipt cannot be reconciled safely")
    if pending.get("line") != canonical_line or not 0 <= canonical_line < len(records):
        raise PreviewBlocked("temporary execution receipt cursor is inconsistent")
    relative = _record_target(records[canonical_line])
    if pending.get("target") != relative:
        raise PreviewBlocked("temporary execution receipt target is inconsistent")
    source = _artifact_path(artifact_root, relative, managed_data_root=managed_data_root)
    quarantine = _quarantine_target(quarantine_root, relative)
    source_exists = source.exists()
    quarantine_exists = quarantine.exists()
    if source_exists and not quarantine_exists:
        # The intent write did not reach the atomic detach. The canonical
        # receipt remains authoritative and the record may be retried.
        temporary.unlink()
        return state
    if not source_exists and quarantine_exists:
        # The atomic detach completed before the receipt replace. Promote the
        # durable intention so normal pending recovery can finish the record.
        state["pending"] = dict(pending)
        _atomic_json_write(state_path, state)
        return state
    raise PreviewBlocked("interrupted receipt target exists in both or neither managed locations")


def _bind_execution_root(
    state_path: Path,
    state: dict[str, Any],
    *,
    records: list[dict[str, Any]],
    artifact_root: Path,
    managed_data_root: Path,
    quarantine_root: Path,
) -> None:
    descriptor = _managed_root_descriptor(managed_data_root)
    existing = state.get("managedDataRoot")
    if existing is not None:
        if existing != descriptor:
            raise PreviewBlocked("execution receipt is bound to another managed data root")
        return
    next_line = int(state.get("nextLine", -1))
    if not 0 <= next_line <= len(records):
        raise PreviewBlocked("execution receipt cursor is invalid")
    pending = state.get("pending")
    if next_line < len(records):
        record = records[next_line]
        relative = _record_target(record)
        if pending is None:
            _verify_record(artifact_root, record, managed_data_root=managed_data_root)
        else:
            if not isinstance(pending, dict) or pending.get("target") != relative:
                raise PreviewBlocked("execution receipt pending record is invalid")
            source = _artifact_path(artifact_root, relative, managed_data_root=managed_data_root)
            quarantine = _quarantine_target(quarantine_root, relative)
            if source.exists() == quarantine.exists():
                raise PreviewBlocked("pending record cannot identify one durable location")
    state["managedDataRoot"] = descriptor
    _atomic_json_write(state_path, state)


def _execute_preview(
    preview_path: Path,
    *,
    expected_preview_sha256: str,
    confirmation: str,
    max_records: int,
    max_seconds: float,
    managed_data_root: Path | None = None,
) -> dict[str, Any]:
    if max_records < 1 or max_seconds <= 0 or max_seconds > 120:
        raise PreviewBlocked("execution bounds must be 1+ records and at most 120 seconds")
    preview, detail_path = _load_execution_preview(
        preview_path,
        expected_preview_sha256=expected_preview_sha256,
        confirmation=confirmation,
    )
    settings = ApiSettings.from_environment()
    artifact_root = settings.artifact_root.resolve()
    if artifact_root != Path(str(preview.get("artifactRoot", ""))).resolve():
        raise PreviewBlocked("configured artifact root differs from preview")
    state_path = preview_path.resolve().with_suffix(".execution.json")
    live_cache_path = preview_path.resolve().with_suffix(".live-paths.txt")
    quarantine_root = (
        preview_path.resolve().parent / "quarantine" / expected_preview_sha256
    ).resolve()
    selected_data_root = _validate_managed_data_root(artifact_root, managed_data_root)
    if state_path.exists():
        state = _load_json_object(state_path, label="execution receipt")
        if (
            state.get("policy") != EXECUTION_POLICY
            or state.get("previewSha256") != expected_preview_sha256
        ):
            raise PreviewBlocked("execution receipt does not match this preview")
    else:
        state = {
            "policy": EXECUTION_POLICY,
            "previewSha256": expected_preview_sha256,
            "nextLine": 0,
            "deletedFiles": 0,
            "deletedBytes": 0,
            "pending": None,
            "status": "executing",
        }
        _atomic_json_write(state_path, state)
    records = _read_detail_records(detail_path)
    state = _reconcile_interrupted_state_write(
        state_path,
        state,
        expected_preview_sha256=expected_preview_sha256,
        records=records,
        artifact_root=artifact_root,
        managed_data_root=selected_data_root,
        quarantine_root=quarantine_root,
    )
    _bind_execution_root(
        state_path,
        state,
        records=records,
        artifact_root=artifact_root,
        managed_data_root=selected_data_root,
        quarantine_root=quarantine_root,
    )
    next_line = int(state.get("nextLine", 0))
    if not 0 <= next_line <= len(records):
        raise PreviewBlocked("execution receipt cursor is invalid")

    engine = create_database_engine(settings)
    started = time.monotonic()
    processed = 0
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(text("SET LOCAL statement_timeout = '120s'"))
                _lock_reference_tables(connection)
                _operation_guard(connection)
                wal_lsn = str(connection.scalar(text("SELECT pg_current_wal_lsn()::text")))
                live_paths = _load_live_path_cache(
                    state.get("referenceSnapshot"),
                    cache_path=live_cache_path,
                    expected_wal_lsn=wal_lsn,
                )
                if live_paths is None:
                    live_paths = _collect_live_paths(connection)
                    wal_lsn = str(connection.scalar(text("SELECT pg_current_wal_lsn()::text")))
                    descriptor = _write_live_path_cache(live_cache_path, live_paths)
                    descriptor["walLsn"] = wal_lsn
                    state["referenceSnapshot"] = descriptor
                    _atomic_json_write(state_path, state)
                _expand_live_manifests(
                    artifact_root,
                    live_paths,
                    managed_data_root=selected_data_root,
                )
                if state.get("pending") is None and quarantine_root.exists():
                    _delete_quarantined(quarantine_root)
                with (
                    ThreadPoolExecutor(max_workers=8) as deletion_pool,
                    ThreadPoolExecutor(max_workers=8) as verification_pool,
                ):
                    deletions: set[Future[None]] = set()
                    verifications: dict[int, Future[None]] = {}
                    initial_pending = state.get("pending")
                    for index in range(next_line, min(len(records), next_line + 32)):
                        if index == next_line and initial_pending is not None:
                            continue
                        verifications[index] = verification_pool.submit(
                            _verify_record,
                            artifact_root,
                            records[index],
                            managed_data_root=selected_data_root,
                        )
                    for record in records[next_line:]:
                        if processed >= max_records or time.monotonic() - started >= max_seconds:
                            break
                        if len(deletions) >= 16:
                            done, deletions = wait(deletions, return_when=FIRST_COMPLETED)
                            for future in done:
                                future.result()
                        relative = _record_target(record)
                        if _record_is_live(record, live_paths):
                            raise PreviewBlocked(f"candidate gained a live reference: {relative}")
                        quarantine = _quarantine_target(quarantine_root, relative)
                        pending = state.get("pending")
                        if pending is not None:
                            if not isinstance(pending, dict):
                                raise PreviewBlocked("execution receipt pending record is invalid")
                            if (
                                pending.get("line") != next_line
                                or pending.get("target") != relative
                            ):
                                raise PreviewBlocked(
                                    "execution receipt has an inconsistent pending record"
                                )
                            if (
                                _artifact_path(
                                    artifact_root,
                                    relative,
                                    managed_data_root=selected_data_root,
                                ).exists()
                                and quarantine.exists()
                            ):
                                raise PreviewBlocked(
                                    "both source and quarantine exist for pending record"
                                )
                        else:
                            verification = verifications.pop(next_line, None)
                            if verification is None:
                                _verify_record(
                                    artifact_root,
                                    record,
                                    managed_data_root=selected_data_root,
                                )
                            else:
                                verification.result()
                            state["pending"] = {"line": next_line, "target": relative}
                            _atomic_json_write(state_path, state)
                        source = _artifact_path(
                            artifact_root,
                            relative,
                            managed_data_root=selected_data_root,
                        )
                        if source.exists():
                            quarantine.parent.mkdir(parents=True, exist_ok=True)
                            if quarantine.exists():
                                raise PreviewBlocked(f"quarantine collision: {relative}")
                            source.rename(quarantine)
                        elif not quarantine.exists() and pending is None:
                            raise PreviewBlocked(
                                f"pending candidate exists in neither location: {relative}"
                            )

                        # The durable receipt advances after the atomic detach.
                        # Physical removal may run concurrently; any remnant is
                        # still isolated under this preview's quarantine and is
                        # swept before the next batch or final completion.
                        state["deletedFiles"] = int(state["deletedFiles"]) + int(
                            record.get("candidateFiles", 1)
                        )
                        state["deletedBytes"] = int(state["deletedBytes"]) + int(
                            record.get("candidateBytes", record.get("size", 0))
                        )
                        next_line += 1
                        processed += 1
                        state["nextLine"] = next_line
                        state["pending"] = None
                        _atomic_json_write(state_path, state)
                        prefetch_index = next_line + 31
                        if prefetch_index < len(records) and prefetch_index not in verifications:
                            verifications[prefetch_index] = verification_pool.submit(
                                _verify_record,
                                artifact_root,
                                records[prefetch_index],
                                managed_data_root=selected_data_root,
                            )
                        if quarantine.exists():
                            deletions.add(
                                deletion_pool.submit(
                                    _delete_quarantined,
                                    quarantine,
                                    parallel_children=False,
                                )
                            )
                    for future in deletions:
                        future.result()
                if quarantine_root.exists():
                    _delete_quarantined(quarantine_root)
                state["status"] = "done" if next_line == len(records) else "executing"
                _atomic_json_write(state_path, state)
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
    state["recordsTotal"] = len(records)
    state["recordsProcessedThisRun"] = processed
    return state


def _create_preview(output: Path) -> dict[str, Any]:
    settings = ApiSettings.from_environment()
    artifact_root = settings.artifact_root.resolve()
    archive = (artifact_root / "legacy-chat-search" / "777-v0.1-layouts.sqlite3").resolve()
    if not archive.is_file() or _is_link_or_reparse(archive):
        raise PreviewBlocked("preserved legacy chat archive is missing")
    archive_sha = hashlib.sha256(archive.read_bytes()).hexdigest()

    engine = create_database_engine(settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text("SET LOCAL statement_timeout = '120s'"))
            operation = _operation_guard(connection)
            live_paths = _collect_live_paths(connection)
    finally:
        engine.dispose()
    print(f"live refs collected: {len(live_paths)}", flush=True)
    _expand_live_manifests(artifact_root, live_paths)
    print(f"live refs after manifest closure: {len(live_paths)}", flush=True)

    roots = (
        "data/crops/source-direct-v1",
        "data/crops/source-direct-v19",
        f"data/symbol-references/{LEGACY_ID}",
        "data/models/777",
        "data/training/777",
        f"data/training/{LEGACY_COMPACT_ID}",
        "data/image-review-geometry",
        "data/board-cell-processing-manifests",
        "data/page-geometry-manifests",
        "data/originals",
    )
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    detail_path = output.with_suffix(".paths.jsonl")
    with detail_path.open("w", encoding="utf-8", newline="\n") as detail:
        summaries = [
            (
                _measure_source_groups(artifact_root, root, live_paths, detail)
                if root.startswith("data/crops/source-direct-")
                else _measure_tree(artifact_root, root, live_paths, detail)
            )
            for root in roots
        ]
    detail_sha = hashlib.sha256(detail_path.read_bytes()).hexdigest()
    total_files = sum(item["candidateFiles"] for item in summaries)
    total_bytes = sum(item["candidateBytes"] for item in summaries)
    payload: dict[str, Any] = {
        "policy": POLICY,
        "createdAtUnix": int(time.time()),
        "gameId": LEGACY_ID,
        "protectedGameId": PROTECTED_ID,
        "databaseOperation": operation,
        "archive": {"path": str(archive), "sha256": archive_sha},
        "artifactRoot": str(artifact_root),
        "operatorRootProtected": str(PROTECTED_OPERATOR_ROOT),
        "liveManagedPathCount": len(live_paths),
        "roots": summaries,
        "candidateFiles": total_files,
        "candidateBytes": total_bytes,
        "candidateGiB": round(total_bytes / (1024**3), 3),
        "details": {"path": str(detail_path), "sha256": detail_sha},
        "deletionExecuted": False,
    }
    fingerprint_payload = {key: value for key, value in payload.items() if key != "createdAtUnix"}
    payload["previewSha256"] = _canonical_sha(fingerprint_payload)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-preview-sha256")
    parser.add_argument("--confirmation")
    parser.add_argument("--max-records", type=int, default=250)
    parser.add_argument("--max-seconds", type=float, default=90.0)
    parser.add_argument(
        "--managed-data-root",
        type=Path,
        help="Explicit data.detached-* root used only to resume an existing execution.",
    )
    args = parser.parse_args()
    try:
        if args.execute:
            if not args.expected_preview_sha256 or not args.confirmation:
                raise PreviewBlocked(
                    "execution requires --expected-preview-sha256 and --confirmation"
                )
            payload = _execute_preview(
                args.output,
                expected_preview_sha256=args.expected_preview_sha256,
                confirmation=args.confirmation,
                max_records=args.max_records,
                max_seconds=args.max_seconds,
                managed_data_root=args.managed_data_root,
            )
        else:
            if args.managed_data_root is not None:
                raise PreviewBlocked("--managed-data-root is valid only with --execute")
            payload = _create_preview(args.output)
    except PreviewBlocked as error:
        print(json.dumps({"status": "blocked", "error": str(error)}), flush=True)
        return 2
    print(json.dumps(payload, indent=2, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
