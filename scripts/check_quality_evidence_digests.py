"""Verify that every digest pinned in ``ai_docs/quality/*.json`` matches its file.

TASK-0940: the quality reports are checksum-bound to each other. Two kinds of
reference are checked against the raw SHA-256 of the current file bytes (no
canonicalisation; ``.gitattributes`` pins these JSON files to LF):

* every object with a ``path`` or ``relativePath`` into a tracked repository
  directory plus a ``sha256`` field, and
* every digest listed in ``ai_docs/quality/evidence-digest-references.json``,
  which names the pinned file for fields that carry a digest without a path
  (for example ``benchmarkReportSha256``).

Exit code 0 when every reference matches, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
QUALITY_DIRECTORY = REPOSITORY_ROOT / "ai_docs" / "quality"
REFERENCE_TABLE = QUALITY_DIRECTORY / "evidence-digest-references.json"
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
# Only paths that point into tracked repository directories are references; other
# ``path`` values in the reports are corpus-relative image names or local files.
_TRACKED_PREFIXES = ("ai_docs/", "services/", "scripts/", "apps/", "packages/", "infra/")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _walk(node: Any, pointer: str = "") -> Iterator[tuple[str, Any]]:
    yield pointer, node
    if isinstance(node, dict):
        for key, value in node.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            yield from _walk(value, f"{pointer}/{escaped}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, f"{pointer}/{index}")


def _resolve(document: Any, pointer: str) -> Any:
    node = document
    for part in pointer.split("/")[1:]:
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _check_target(
    owner: str, location: str, relative: str, expected: str, problems: list[str]
) -> None:
    if not relative.startswith(_TRACKED_PREFIXES):
        return
    target = REPOSITORY_ROOT / relative
    if not target.is_file():
        problems.append(f"{owner} {location}: referenced file {relative} does not exist")
        return
    actual = file_sha256(target)
    if actual != expected:
        problems.append(
            f"{owner} {location}: {relative} pinned {expected[:12]}..., actual {actual[:12]}..."
        )


def find_mismatches() -> list[str]:
    problems: list[str] = []
    for path in sorted(QUALITY_DIRECTORY.glob("*.json")):
        owner = path.relative_to(REPOSITORY_ROOT).as_posix()
        document = json.loads(path.read_text(encoding="utf-8"))
        for pointer, node in _walk(document):
            if not isinstance(node, dict):
                continue
            digest = node.get("sha256")
            reference = node.get("path", node.get("relativePath"))
            if (
                isinstance(digest, str)
                and _DIGEST.match(digest)
                and isinstance(reference, str)
                and reference
            ):
                _check_target(owner, pointer or "/", reference, digest, problems)
    table = json.loads(REFERENCE_TABLE.read_text(encoding="utf-8"))
    for entry in table["references"]:
        owner_path = REPOSITORY_ROOT / entry["file"]
        document = json.loads(owner_path.read_text(encoding="utf-8"))
        try:
            value = _resolve(document, entry["pointer"])
        except (KeyError, IndexError, ValueError):
            problems.append(f"{entry['file']} {entry['pointer']}: pinned field is missing")
            continue
        if not isinstance(value, str) or not _DIGEST.match(value):
            problems.append(f"{entry['file']} {entry['pointer']}: not a SHA-256 value")
            continue
        _check_target(entry["file"], entry["pointer"], entry["target"], value, problems)
    return problems


def main() -> int:
    problems = find_mismatches()
    for problem in problems:
        print(problem)
    print(f"{len(problems)} mismatches")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
