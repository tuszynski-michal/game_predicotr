"""Fenced run artifacts use checksum names and same-volume atomic publication."""

import hashlib
import os
import tempfile
from pathlib import Path

from .run_contracts import Artifact
from .snapshot import safe_file


def publish(root: Path, run_id: str, attempt: int, content: bytes, suffix: str) -> Artifact:
    checksum = hashlib.sha256(content).hexdigest()
    relative = f"{run_id}/attempt-{attempt}/{checksum}.{suffix}"
    path = safe_file(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".run-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError("RUN_ARTIFACT_CONFLICT")
        else:
            os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return Artifact(relative_path=relative, sha256=checksum)


def verify_artifact(root: Path, artifact: Artifact) -> Path:
    path = safe_file(root, artifact.relative_path)
    with path.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != artifact.sha256:
        raise ValueError("RUN_ARTIFACT_CHECKSUM_MISMATCH")
    return path
