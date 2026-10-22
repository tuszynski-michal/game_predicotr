"""Preserve a legacy checkout without overwriting its active replacement.

Each invocation has a wall-clock budget and checkpoints verified files in a
local SQLite receipt. The source is read-only. Different/missing destination
files are copied exclusively into a separate archive, never into the active
checkout. Git objects are secured separately with a verified bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from functools import lru_cache
from pathlib import Path
from typing import Any

EXCLUDED_NAMES = {".git", "node_modules", ".next", "__pycache__", ".pytest_cache"}
EXCLUDED_ROOTS = {".mypy_cache", ".ruff_cache", ".pnpm-store"}
CONTRACT = "legacy-copy-preservation-v1"


def io_path(path: Path) -> Path:
    """Use Win32 extended paths for every archive operation, including hardlinks."""
    value = str(path.absolute())
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return path
    if value.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + value[2:])
    return Path("\\\\?\\" + value)


def fingerprint(path: Path) -> tuple[int, int]:
    info = io_path(path).stat(follow_symlinks=False)
    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise ValueError(f"Reparse point is not an ordinary file: {path}")
    if not stat.S_ISREG(info.st_mode):
        raise ValueError(f"Not an ordinary file: {path}")
    return info.st_size, info.st_mtime_ns


def checksum(path: Path) -> str:
    before = fingerprint(path)
    with io_path(path).open("rb") as stream:
        result = hashlib.file_digest(stream, "sha256").hexdigest()
    if fingerprint(path) != before:
        raise ValueError(f"File changed while hashing: {path}")
    return result


def validate_roots(source: Path, destination: Path, output: Path) -> None:
    roots = [p.resolve(strict=True) for p in (source, destination)]
    resolved_output = output.resolve()
    if roots[0] == roots[1] or roots[0].is_relative_to(roots[1]):
        raise ValueError("Source must be independent from the active destination")
    if roots[1].is_relative_to(roots[0]) or resolved_output.is_relative_to(roots[0]):
        raise ValueError("Destination/output cannot be inside the legacy source")
    if resolved_output == roots[1] or roots[1].is_relative_to(resolved_output):
        raise ValueError("Output cannot contain the active checkout")
    for root in (source, destination):
        if root.is_symlink() or root.is_junction():
            raise ValueError("Checkout roots cannot be links")


def inventory(source: Path) -> tuple[list[str], list[dict[str, str]], list[str]]:
    files: list[str] = []
    links: list[dict[str, str]] = []
    errors: list[str] = []
    pending = [source]
    last_progress = time.monotonic()
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(io_path(directory)) as entries:
                for entry in entries:
                    path = directory / entry.name
                    rel = path.relative_to(source)
                    if entry.name == ".git":
                        continue
                    if entry.name.startswith(".venv") or (
                        len(rel.parts) == 1 and entry.name in EXCLUDED_ROOTS
                    ):
                        continue
                    info = entry.stat(follow_symlinks=False)
                    if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                        links.append({"path": rel.as_posix(), "target": os.readlink(io_path(path))})
                    elif entry.is_dir(follow_symlinks=False):
                        if ".tooling" not in rel.parts and (
                            entry.name in EXCLUDED_NAMES
                            or entry.name in EXCLUDED_ROOTS
                            or entry.name.startswith(("pytest", ".pytest"))
                            or "pytest-run" in entry.name
                        ):
                            continue
                        pending.append(path)
                    elif entry.is_file(follow_symlinks=False):
                        files.append(rel.as_posix())
        except OSError as error:
            errors.append(f"{directory}: {error}")
        if time.monotonic() - last_progress >= 5:
            print(f"inventory_files={len(files)} pending_directories={len(pending)}", flush=True)
            last_progress = time.monotonic()
    return sorted(files), links, errors


def ordinary_target(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or ":" in relative:
        raise ValueError("Unsafe relative path")
    candidate = root / rel
    validate_parent(root, candidate.parent)
    if io_path(candidate).is_symlink() or io_path(candidate).is_junction():
        raise ValueError(f"Target crosses a link: {candidate}")
    return candidate


@lru_cache(maxsize=100_000)
def validate_parent(root: Path, parent: Path) -> None:
    """Validate each directory once per bounded, read-only inventory pass."""
    if parent == root:
        if io_path(root).is_symlink() or io_path(root).is_junction():
            raise ValueError(f"Target crosses a link: {root}")
        return
    validate_parent(root, parent.parent)
    if io_path(parent).is_symlink() or io_path(parent).is_junction():
        raise ValueError(f"Target crosses a link: {parent}")


def archive_file(source: Path, target: Path, expected: str) -> None:
    actual_target = io_path(target)
    actual_target.parent.mkdir(parents=True, exist_ok=True)
    if not actual_target.exists():
        descriptor, name = tempfile.mkstemp(prefix=".retirement-copy-", dir=actual_target.parent)
        temporary = Path(name)
        try:
            digest = hashlib.sha256()
            with io_path(source).open("rb") as incoming, os.fdopen(descriptor, "wb") as outgoing:
                for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                    outgoing.write(chunk)
                    digest.update(chunk)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if digest.hexdigest() != expected:
                raise ValueError(f"Source changed during archive copy: {source}")
            # Verify a previously published target; never replace it.
            with suppress(FileExistsError):
                os.link(temporary, actual_target)
        finally:
            temporary.unlink(missing_ok=True)
    if checksum(target) != expected:
        raise ValueError(f"Archive differs from source (no overwrite): {target}")


def open_receipt(output: Path, source: Path, destination: Path) -> sqlite3.Connection:
    output.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(output / "files.sqlite")
    database.execute("create table if not exists metadata (key text primary key, value text)")
    database.execute(
        "create table if not exists files (relative text primary key, size integer, "
        "source_mtime text, sha256 text, copy_path text, copy_mtime text, kind text)"
    )
    expected = {"contract": CONTRACT, "source": str(source), "destination": str(destination)}
    existing = dict(database.execute("select key,value from metadata"))
    if existing and existing != expected:
        database.close()
        raise ValueError("Receipt belongs to different roots or a different contract")
    database.executemany("insert or ignore into metadata values (?,?)", expected.items())
    database.commit()
    return database


def preserve_entry(
    source: Path,
    destination: Path,
    archive: Path,
    relative: str,
    previous: tuple[Any, ...] | None,
) -> tuple[Any, ...] | None:
    original = source / relative
    validate_parent(source, original.parent)
    size, mtime = fingerprint(original)
    if previous and (size, str(mtime)) == previous[:2]:
        copy = Path(previous[3])
        copy_root = archive if previous[5] == "archive" else destination
        validate_parent(copy_root, copy.parent)
        try:
            if fingerprint(copy) == (size, int(previous[4])):
                return None
        except FileNotFoundError:
            pass
    digest = checksum(original)
    live = ordinary_target(destination, relative)
    kind = "active_copy"
    if not io_path(live).is_file() or fingerprint(live)[0] != size or checksum(live) != digest:
        kind = "archive"
        live = ordinary_target(archive, relative)
        archive_file(original, live, digest)
    if fingerprint(original) != (size, mtime):
        raise ValueError(f"Source changed during preservation: {original}")
    copy_size, copy_mtime = fingerprint(live)
    if copy_size != size:
        raise ValueError(f"Copy changed during verification: {live}")
    return relative, size, str(mtime), digest, str(live), str(copy_mtime), kind


def verify_files(
    source: Path,
    destination: Path,
    output: Path,
    *,
    seconds: float = 90,
    resume_inventory: bool = False,
) -> dict[str, Any]:
    validate_roots(source, destination, output)
    validate_parent.cache_clear()
    source, destination, output = source.resolve(), destination.resolve(), output.resolve()
    deadline = time.monotonic() + seconds
    inventory_path = output / "inventory.json"
    if resume_inventory:
        cached = json.loads(inventory_path.read_text(encoding="utf-8"))
        if cached["source"] != str(source):
            raise ValueError("Cached inventory belongs to a different source")
        files, links, errors = cached["files"], cached["links"], cached["errors"]
        for relative in files:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or ":" in relative:
                raise ValueError("Unsafe path in cached inventory")
        print(f"cached_inventory_files={len(files)}; final fresh inventory required", flush=True)
    else:
        files, links, errors = inventory(source)
        output.mkdir(parents=True, exist_ok=True)
        inventory_path.write_text(
            json.dumps({"source": str(source), "files": files, "links": links, "errors": errors}),
            encoding="utf-8",
        )
    archive = output / "legacy-files"
    result: dict[str, Any] = {
        "contract": CONTRACT,
        "source": str(source),
        "destination": str(destination),
        "files": len(files),
        "links": links,
        "inventory_errors": errors,
        "verification_errors": [],
        "complete": False,
    }
    with open_receipt(output, source, destination) as database:
        rows = {
            row[0]: row[1:]
            for row in database.execute(
                "select relative,size,source_mtime,sha256,copy_path,copy_mtime,kind from files"
            )
        }
        checked = 0
        last_progress = time.monotonic()
        if resume_inventory:
            # Finish new work before rechecking already verified receipts.
            files.sort(key=lambda relative: relative in rows)

        def preserve_batch(
            batch: list[str],
        ) -> tuple[int, list[tuple[Any, ...]], list[dict[str, str]]]:
            completed = 0
            records: list[tuple[Any, ...]] = []
            failures: list[dict[str, str]] = []
            for relative in batch:
                if time.monotonic() >= deadline:
                    break
                try:
                    record = preserve_entry(
                        source, destination, archive, relative, rows.get(relative)
                    )
                    if record is not None:
                        records.append(record)
                    completed += 1
                except (OSError, ValueError) as error:
                    failures.append({"path": relative, "error": str(error)})
            return completed, records, failures

        # Bounded batches keep memory independent from the inventory size.
        with ThreadPoolExecutor(max_workers=16) as pool:
            for offset in range(0, len(files), 1024):
                if time.monotonic() >= deadline:
                    break
                pending = [
                    pool.submit(preserve_batch, files[index : min(index + 64, len(files))])
                    for index in range(offset, min(offset + 1024, len(files)), 64)
                ]
                for future in pending:
                    completed, records, failures = future.result()
                    database.executemany(
                        "insert or replace into files values (?,?,?,?,?,?,?)", records
                    )
                    checked += completed
                    result["verification_errors"].extend(failures)
                database.commit()
                if time.monotonic() - last_progress >= 5:
                    print(f"verified={checked}/{len(files)}", flush=True)
                    last_progress = time.monotonic()
        database.commit()
        result["checked_this_pass"] = checked
        result["preserved_by_kind"] = dict(
            database.execute("select kind,count(*) from files group by kind")
        )
        result["bytes_by_kind"] = dict(
            database.execute("select kind,sum(size) from files group by kind")
        )
        ready = checked == len(files) and not errors and not result["verification_errors"]
        result["ready_for_fresh_inventory"] = ready
        result["complete"] = ready and not resume_inventory
    (output / "files-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def legacy_values(value: Any, prefix: str, key: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, dict):
        for name, item in value.items():
            yield from legacy_values(item, prefix, f"{key}.{name}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from legacy_values(item, prefix, f"{key}[{index}]")
    elif isinstance(value, str):
        normalized, root = value.casefold().replace("\\", "/"), prefix.casefold().replace("\\", "/")
        if normalized == root or normalized.startswith(root.rstrip("/") + "/"):
            yield key, value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=90, choices=range(1, 106))
    parser.add_argument("--resume-inventory", action="store_true")
    args = parser.parse_args()
    result = verify_files(
        args.source,
        args.destination,
        args.output,
        seconds=args.seconds,
        resume_inventory=args.resume_inventory,
    )
    compact = {
        k: v
        for k, v in result.items()
        if k not in {"links", "verification_errors", "inventory_errors"}
    }
    compact["verification_error_count"] = len(result["verification_errors"])
    compact["inventory_error_count"] = len(result["inventory_errors"])
    compact["error_examples"] = result["verification_errors"][:2]
    print(json.dumps(compact, ensure_ascii=False))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
