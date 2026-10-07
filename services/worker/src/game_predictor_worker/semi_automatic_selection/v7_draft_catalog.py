"""Bounded durable directory locators and independent unapproved draft metadata."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


def read_object(path: Path, *, maximum_bytes: int = 65536) -> dict[str, Any]:
    if path.resolve() != path.absolute():
        raise ValueError("Draft metadata must not traverse links.")
    with path.open("rb") as stream:
        content = stream.read(maximum_bytes + 1)
    if len(content) > maximum_bytes:
        raise ValueError("Draft metadata exceeds the bounded size.")
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Draft metadata must be an object.")
    return payload


def _publish(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.resolve() != path.parent.absolute():
        raise ValueError("Unsafe draft locator directory.")
    content = json.dumps(payload, sort_keys=True).encode("utf-8")
    temp = path.with_name(f".{path.name}.{uuid4()}.tmp")
    try:
        with temp.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp, path)
        except FileExistsError:
            if read_object(path) != payload:
                raise ValueError("Draft directory is already pinned to another location.") from None
    finally:
        temp.unlink(missing_ok=True)


def pin_draft_folder(
    artifact_root: Path, directory: Path, *, run_id: str, fingerprint: str
) -> None:
    UUID(run_id)
    if not directory.is_dir() or directory.resolve() != directory.absolute():
        raise ValueError("Unsafe draft directory.")
    payload: dict[str, object] = {
        "runId": run_id,
        "sourceFingerprint": fingerprint,
        "directory": str(directory),
        "approved": False,
    }
    _publish(artifact_root / "v7-draft-folders" / f"{run_id}.json", payload)
    root = directory.parent if directory.name == "propozycje" else directory
    _publish(root / "_selekcja_v7.json", payload)


def draft_folder(artifact_root: Path, *, run_id: str, fingerprint: str) -> Path | None:
    UUID(run_id)
    path = artifact_root / "v7-draft-folders" / f"{run_id}.json"
    if not path.exists():
        return None
    payload = read_object(path, maximum_bytes=4096)
    if payload.get("runId") != run_id or payload.get("sourceFingerprint") != fingerprint:
        raise ValueError("Draft locator has foreign source identity.")
    if not isinstance(payload.get("directory"), str):
        raise ValueError("Draft locator has no valid directory.")
    directory = Path(payload["directory"])
    if not directory.is_absolute() or directory.resolve() != directory.absolute():
        raise ValueError("Unsafe pinned draft directory.")
    return directory


def folder_reference(directory: Path) -> dict[str, Any] | None:
    if not directory.is_dir() or directory.resolve() != directory.absolute():
        raise ValueError("Unsafe review directory.")
    root = directory.parent if directory.name == "propozycje" else directory
    for name in ("_selekcja_v7.json", "_propozycje_gotowe.json"):
        path = root / name
        if path.exists():
            return read_object(path, maximum_bytes=4096)
    return None


def read_draft(
    directory: Path,
    *,
    run_id: str,
    start: int,
    end: int,
    source_count: int,
) -> dict[str, object] | None:
    name = f"seq_{start}-{end}.jpg"
    image, metadata = directory / name, directory / f"{name}.json"
    if not image.exists() or not metadata.exists():
        return None  # Completed export never recreates intentionally removed files.
    if image.resolve() != image.absolute():
        raise ValueError("Draft image must not traverse links.")
    payload = read_object(metadata)
    index = payload.get("sourceIndex")
    checksum = payload.get("sha256")
    if (
        payload.get("runId") != run_id
        or payload.get("rangeStart") != start
        or payload.get("rangeEnd") != end
        or payload.get("file") != name
        or payload.get("approved") is not False
        or payload.get("ocrProof") is not False
        or type(index) is not int
        or not 0 <= index < source_count
        or not isinstance(checksum, str)
        or len(checksum) != 64
        or any(char not in "0123456789abcdef" for char in checksum)
        or image.stat().st_size != payload.get("sourceSizeBytes")
    ):
        raise ValueError("Draft metadata is inconsistent with its run or source.")
    return {
        "sourceIndex": index,
        "sourceChecksumSha256": checksum,
        "estimated": payload.get("state") == "estimated",
        "reason": str(payload.get("reason", payload.get("state", "inferred"))),
        "directory": str(directory),
    }
