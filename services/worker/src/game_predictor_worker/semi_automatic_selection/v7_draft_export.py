"""Independent per-range draft files, with source checksums and no domain writes."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from uuid import uuid4

from .contracts import SemiAutomaticSelectionSource


def publish_draft(
    source_root: Path,
    target_root: Path,
    source: SemiAutomaticSelectionSource,
    *,
    start: int,
    end: int,
    metadata: dict[str, object],
) -> bool:
    """Publish exclusively; an identical retry completes a missing sidecar only."""
    relative = PurePosixPath(source.relative_path)
    if relative.is_absolute() or ".." in relative.parts or "\\" in str(relative):
        raise ValueError("Unsafe draft source path.")
    root = source_root.resolve(strict=True)
    original = root.joinpath(*relative.parts).resolve(strict=True)
    if not original.is_relative_to(root) or not 0 < start <= end < start + 9:
        raise ValueError("Unsafe draft source or range.")
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root.resolve(strict=True)
    if target != target_root.absolute():
        raise ValueError("Draft output must not traverse directory junctions.")
    if target == root or target.is_relative_to(root):
        raise ValueError("Draft outputs must be outside the source folder.")
    name = f"seq_{start}-{end}.jpg"
    output = target / name
    sidecar = target / f"{name}.json"
    payload = {
        **metadata,
        "file": name,
        "rangeStart": start,
        "rangeEnd": end,
        "sourceIndex": source.source_index,
        "sourceRelativePath": source.relative_path,
        "sourceSizeBytes": source.size_bytes,
        "sha256": source.checksum_sha256,
        "approved": False,
        "ocrProof": False,
    }
    if sidecar.exists() and json.loads(sidecar.read_text(encoding="utf-8")) != payload:
        raise ValueError(f"Draft metadata conflict: {name}")
    created = False
    if output.exists():
        if output.stat().st_size != source.size_bytes or _digest(output) != source.checksum_sha256:
            raise ValueError(f"Draft file conflict: {name}")
    else:
        temp = target / f".{name}.{uuid4()}.tmp"
        try:
            with original.open("rb") as reader, temp.open("xb") as writer:
                checksum = hashlib.sha256()
                while chunk := reader.read(1024 * 1024):
                    checksum.update(chunk)
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
            if (
                checksum.hexdigest() != source.checksum_sha256
                or temp.stat().st_size != source.size_bytes
            ):
                raise ValueError(f"Draft source changed: {name}")
            try:
                os.link(temp, output)
                created = True
            except FileExistsError:
                if _digest(output) != source.checksum_sha256:
                    raise ValueError(f"Concurrent draft file conflict: {name}") from None
        finally:
            temp.unlink(missing_ok=True)
    content = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
    temp = target / f".{name}.{uuid4()}.json.tmp"
    try:
        with temp.open("xb") as writer:
            writer.write(content)
            writer.flush()
            os.fsync(writer.fileno())
        try:
            os.link(temp, sidecar)
        except FileExistsError:
            if sidecar.read_bytes() != content:
                raise ValueError(f"Concurrent draft metadata conflict: {name}") from None
    finally:
        temp.unlink(missing_ok=True)
    return created


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()
