"""Immutable raw-folder snapshots, preserving occurrences and duplicate provenance."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

VERSION = "vision-lab-folder-v1"


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_file(root: Path, relative: str) -> Path:
    path = root / relative
    if "\\" in relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise ValueError("SNAPSHOT_PATH_INVALID")
    reject_links(path)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("SNAPSHOT_PATH_INVALID")
    return path


def reject_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.exists() or part.is_symlink():
            metadata = part.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 1024:
                raise ValueError("SNAPSHOT_REPARSE_POINT")


def verify(root: Path, manifest: dict[str, Any]) -> None:
    reject_links(root)
    if manifest.get("format") == VERSION:
        identity = {"format": VERSION, "entries": manifest["entries"]}
        if hashlib.sha256(canonical(identity)).hexdigest() != manifest["snapshotId"]:
            raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")
        expected = {
            f"images/{entry['sha256']}.img": entry["sha256"] for entry in manifest["entries"]
        }
        if expected != manifest["files"]:
            raise ValueError("SNAPSHOT_INVENTORY_MISMATCH")
    inventory = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if inventory - {"manifest.json"} != set(manifest["files"]):
        raise ValueError("SNAPSHOT_INVENTORY_MISMATCH")
    for relative, checksum in manifest["files"].items():
        if sha(safe_file(root, relative)) != checksum:
            raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
    if manifest.get("format") != VERSION:
        frozen = json.loads(safe_file(root, "frozen_identity.json").read_bytes())
        identity = {
            "input": manifest["input"],
            "exporterVersion": manifest["exporterVersion"],
            "rows": [
                [
                    row["gameId"],
                    row["table"],
                    row["key"],
                    row["fingerprint"],
                    row["storageGeneration"],
                ]
                for row in frozen["rows"]
            ],
        }
        if (
            hashlib.sha256(canonical(identity)).hexdigest() != manifest["snapshotId"]
            or frozen["snapshotId"] != manifest["snapshotId"]
        ):
            raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")


def import_folder(source: Path, output: Path) -> Path:
    reject_links(source.absolute())
    reject_links(output.absolute())
    source = source.resolve(strict=True)
    output = output.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("SOURCE_OUTPUT_OVERLAP")
    entries = []
    originals: dict[str, Path] = {}
    for path in sorted(source.rglob("*"), key=lambda p: p.relative_to(source).as_posix()):
        if not path.is_file() or path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        relative = path.relative_to(source).as_posix()
        path = safe_file(source, relative)
        game = Path(relative).parts[0] if len(Path(relative).parts) > 1 else source.name
        checksum = sha(path)
        originals.setdefault(checksum, path)
        entries.append(
            {
                "id": hashlib.sha256(canonical([relative, checksum])).hexdigest(),
                "gameId": "local-" + hashlib.sha256(game.encode()).hexdigest()[:24],
                "gameName": game,
                "filename": relative,
                "sha256": checksum,
                "familyCandidate": path.stem.split("__", 1)[0],
                "role": "comparison_only" if game.strip() == "777" else "data",
            }
        )
    if not entries:
        raise ValueError("NO_IMAGES")
    identity = {"format": VERSION, "entries": entries}
    snapshot_id = hashlib.sha256(canonical(identity)).hexdigest()
    destination = output / snapshot_id
    files = {f"images/{digest}.img": digest for digest in sorted(originals)}
    manifest = {**identity, "snapshotId": snapshot_id, "files": files}
    if destination.exists():
        if json.loads(safe_file(destination, "manifest.json").read_bytes()) != manifest:
            raise ValueError("SNAPSHOT_CONFLICT")
        verify(destination, manifest)
        return destination
    output.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".folder-", dir=output))
    try:
        (stage / "images").mkdir()
        for relative, checksum in files.items():
            with originals[checksum].open("rb") as src, (stage / relative).open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
        verify(stage, manifest)
        for entry in entries:
            if sha(safe_file(source, entry["filename"])) != entry["sha256"]:
                raise ValueError("SOURCE_CHANGED_DURING_IMPORT")
        with (stage / "manifest.json").open("xb") as stream:
            stream.write(canonical(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            stage.rename(destination)
        except FileExistsError:
            if json.loads((destination / "manifest.json").read_bytes()) != manifest:
                raise ValueError("SNAPSHOT_CONFLICT") from None
            verify(destination, manifest)
        return destination
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(import_folder(args.source, args.output))


if __name__ == "__main__":
    main()
