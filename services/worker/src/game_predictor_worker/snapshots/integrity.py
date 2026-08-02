"""Canonical logical and physical checksums for production snapshots."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

GameRow = tuple[int, str, str, int, int, int, int, int, int, int]
SymbolRow = tuple[
    int,
    int,
    str,
    str,
    str | None,
    str | None,
    int,
    int,
    str | None,
]
LayoutRow = tuple[int, int, str, int]


class LogicalSnapshotChecksum:
    def __init__(
        self,
        *,
        release_version: str,
        created_at: str,
        schema_version: int,
        algorithm_version: str,
        game_count: int,
        symbol_count: int,
        layout_count: int,
    ) -> None:
        self._digest = hashlib.sha256()
        self._add(
            (
                "snapshot",
                release_version,
                created_at,
                schema_version,
                algorithm_version,
                game_count,
                symbol_count,
                layout_count,
            )
        )

    def add_game(self, row: GameRow) -> None:
        self._add(("game", *row))

    def add_symbol(self, row: SymbolRow) -> None:
        self._add(("symbol", *row))

    def add_layout(self, row: LayoutRow) -> None:
        self._add(("layout", *row))

    def hexdigest(self) -> str:
        return self._digest.hexdigest()

    def _add(self, value: tuple[object, ...]) -> None:
        self._digest.update(
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
            ).encode("ascii")
        )
        self._digest.update(b"\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
