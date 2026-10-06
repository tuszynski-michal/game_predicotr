"""Preview or explicitly install immutable Mumie feedback controls create-only.

The default only verifies source inputs and existing targets. ``--apply``
publishes verified originals/proofs before the descriptor, using atomic,
create-only hard links. Interrupted copies remain safe to retry; existing
different files are never replaced. No database or runtime state is changed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import UUID

REPOSITORY = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPOSITORY / "services/api/src"), str(REPOSITORY / "services/worker/src")]

from game_predictor_api.storage.protected_control_truth import load_control_truth  # noqa: E402
from game_predictor_worker.symbols import protected_sources as protections  # noqa: E402

MAX_INPUT_BYTES = 64 * 1024 * 1024


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _read(path: Path, checksum: str | None = None) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError(f"Input is missing, unsafe or exceeds 64 MiB: {path}")
    with path.open("rb") as file:
        content = file.read(MAX_INPUT_BYTES + 1)
    if len(content) > MAX_INPUT_BYTES:
        raise ValueError(f"Input exceeds 64 MiB: {path}")
    if checksum is not None and hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError(f"Input checksum changed: {path}")
    return content


def _object(content: bytes) -> dict[str, Any]:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object.")
    return value


def _checked(content: bytes) -> dict[str, Any]:
    envelope = _object(content)
    payload = envelope.get("payload")
    if not isinstance(payload, dict) or _digest(payload) != envelope.get("sha256"):
        raise ValueError("Input envelope checksum is invalid.")
    return payload


def _target(data_root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    if (
        path.is_absolute()
        or not path.parts
        or ".." in path.parts
        or "\\" in relative
        or ":" in relative
    ):
        raise ValueError("Unsafe managed destination path.")
    candidate = data_root.joinpath(*path.parts)
    # Check each component before resolving, rather than hiding a symlink by
    # resolving it first. An existing directory link is not an install target.
    for component in (candidate, *candidate.parents):
        if component.is_symlink():
            raise ValueError("Managed destination contains a symlink.")
        if component == data_root:
            break
    resolved = candidate.resolve()
    if not resolved.is_relative_to(data_root.resolve()):
        raise ValueError("Destination is outside managed storage.")
    return candidate


@dataclass(frozen=True)
class _Copy:
    source: Path
    relative: str
    checksum: str


def _publish(copy: _Copy, data_root: Path) -> bool:
    content = _read(copy.source, copy.checksum)
    target = _target(data_root, copy.relative)
    if target.exists():
        _read(target, copy.checksum)
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=".feedback-", delete=False
        ) as file:
            temporary = file.name
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        # Unlike replace/rename on POSIX, link can never overwrite an existing
        # target. Both paths share a volume; Windows NTFS supports this operation.
        try:
            os.link(temporary, target)
        except FileExistsError:
            _read(target, copy.checksum)
            return False
        _read(target, copy.checksum)
        return True
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def install_controls(
    *,
    artifact_root: Path,
    descriptor: Path,
    source_inventory: Path,
    proof_copy_plan: Path,
    apply: bool = False,
) -> dict[str, object]:
    """Validate the complete immutable input set before the first publication."""
    descriptor_bytes = _read(descriptor)
    payload = _checked(descriptor_bytes)
    if _digest(payload) != protections.DESCRIPTOR_SHA256:
        raise ValueError("Descriptor does not match the frozen pilot identity.")
    if payload.get("gameId") != protections.MUMIE_GAME_ID:
        raise ValueError("Descriptor does not belong to the Mumie pilot.")
    inventory = _checked(_read(source_inventory))
    originals = {row["sourceByteSha256"]: Path(row["sourcePath"]) for row in inventory["rows"]}
    expected_sources = {row["sourceByteSha256"] for row in payload["rows"]}
    if set(originals) != expected_sources:
        raise ValueError("Source inventory differs from the frozen whole-photo exclusions.")
    copies: list[_Copy] = []
    for row in payload["rows"]:
        source = originals[row["sourceByteSha256"]]
        _read(source, row["sourceByteSha256"])
        pixels = protections.source_pixel_identity(
            source.parent, source.name, row["sourceByteSha256"]
        )
        if pixels != row["normalizedPixelChecksumSha256"]:
            raise ValueError("An original differs from its frozen normalized pixel identity.")
        copies.append(_Copy(source, row["sourceRelativePath"], row["sourceByteSha256"]))
    plan = _object(_read(proof_copy_plan))
    if plan.get("descriptorChecksumSha256") != protections.DESCRIPTOR_SHA256:
        raise ValueError("Proof copy plan belongs to another descriptor.")
    expected_proofs = {
        row["relativePath"]: row["fileChecksumSha256"] for row in payload["controlTruthProofs"]
    }
    actual_proofs = {row["relativePath"]: row["fileChecksumSha256"] for row in plan["proofs"]}
    if actual_proofs != expected_proofs or len(actual_proofs) != len(plan["proofs"]):
        raise ValueError("Proof copy plan differs from immutable control truth support.")
    for row in plan["proofs"]:
        copies.append(
            _Copy(Path(row["sourcePath"]), row["relativePath"], row["fileChecksumSha256"])
        )
    copies.append(
        _Copy(descriptor, protections.DESCRIPTOR_PATH, hashlib.sha256(descriptor_bytes).hexdigest())
    )
    if len({copy.relative for copy in copies}) != len(copies):
        raise ValueError("Install destinations must be unique.")
    data_root = artifact_root.resolve() / "data"
    existing = 0
    for copy in copies:
        _read(copy.source, copy.checksum)
        target = _target(data_root, copy.relative)
        if target.exists():
            _read(target, copy.checksum)
            existing += 1
    created = 0
    if apply:
        for copy in copies:
            created += int(_publish(copy, data_root))
        protections.load_protected_sources(artifact_root, protections.MUMIE_GAME_ID)
        truths, reference = load_control_truth(artifact_root, UUID(protections.MUMIE_GAME_ID))
        if reference != protections.ProtectedSources(frozenset(), frozenset()).reference():
            raise ValueError("Installed controls have a different frozen identity.")
        truth_count = len(truths)
    else:
        truth_count = len(payload["controlTruthRows"])
    return {
        "format": "mumie-feedback-controls-install-receipt-v1",
        "mode": "apply" if apply else "preview",
        "artifactRoot": str(artifact_root.resolve()),
        "descriptorChecksumSha256": protections.DESCRIPTOR_SHA256,
        "sourcePhotos": len(expected_sources),
        "proofFiles": len(expected_proofs),
        "humanControls": truth_count,
        "filesToCreate": len(copies) - existing,
        "filesCreated": created,
        "existingVerifiedFiles": existing,
        "databaseWrites": 0,
        "modelActivations": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--descriptor", type=Path, required=True)
    parser.add_argument("--source-inventory", type=Path, required=True)
    parser.add_argument("--proof-copy-plan", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        receipt = install_controls(
            artifact_root=args.artifact_root,
            descriptor=args.descriptor,
            source_inventory=args.source_inventory,
            proof_copy_plan=args.proof_copy_plan,
            apply=args.apply,
        )
    except (ValueError, OSError) as error:
        parser.exit(1, f"Feedback controls installation rejected: {error}\n")
    print(json.dumps(receipt, sort_keys=True, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
