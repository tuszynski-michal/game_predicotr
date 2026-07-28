"""Deterministic, streaming fixtures for manual-import acceptance runs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

DEFAULT_ACCEPTANCE_LAYOUT_COUNT = 500_000
DEFAULT_ACCEPTANCE_SEED = 50_027
DEFAULT_DUPLICATE_GROUP_COUNT = 6
DEFAULT_CELL_COUNT = 15
DEFAULT_SYMBOL_COUNT = 11


@dataclass(frozen=True, slots=True)
class LayoutImportFixtureResult:
    path: Path
    layout_count: int
    seed: int
    duplicate_group_count: int
    size_bytes: int
    sha256: str
    elapsed_seconds: float
    maximum_buffered_record_count: int

    def to_dict(self) -> dict[str, int | float | str]:
        return {
            "duplicateGroupCount": self.duplicate_group_count,
            "elapsedSeconds": round(self.elapsed_seconds, 4),
            "layoutCount": self.layout_count,
            "maximumBufferedRecordCount": self.maximum_buffered_record_count,
            "path": self.path.as_posix(),
            "seed": self.seed,
            "sha256": self.sha256,
            "sizeBytes": self.size_bytes,
        }


def deterministic_cells(
    sequence_number: int,
    *,
    seed: int = DEFAULT_ACCEPTANCE_SEED,
    cell_count: int = DEFAULT_CELL_COUNT,
    symbol_count: int = DEFAULT_SYMBOL_COUNT,
) -> tuple[int, ...]:
    """Encode a unique sequence position as bounded base-N symbol cells."""
    if sequence_number < 1:
        raise ValueError("sequence_number must be positive.")
    if seed < 0:
        raise ValueError("seed cannot be negative.")
    if cell_count < 1:
        raise ValueError("cell_count must be positive.")
    if symbol_count < 2:
        raise ValueError("symbol_count must be at least two.")

    value = sequence_number - 1 + seed
    capacity = symbol_count**cell_count
    if value >= capacity:
        raise ValueError("The fixture position exceeds the configured cell capacity.")
    cells: list[int] = []
    for _ in range(cell_count):
        cells.append((value % symbol_count) + 1)
        value //= symbol_count
    return tuple(cells)


def write_layout_import_fixture(
    path: Path,
    *,
    layout_count: int = DEFAULT_ACCEPTANCE_LAYOUT_COUNT,
    seed: int = DEFAULT_ACCEPTANCE_SEED,
    duplicate_group_count: int = DEFAULT_DUPLICATE_GROUP_COUNT,
    progress: Callable[[int, int], None] | None = None,
) -> LayoutImportFixtureResult:
    """Write a strict JSONL v1 source without materializing the dataset."""
    if layout_count < 1:
        raise ValueError("layout_count must be positive.")
    if duplicate_group_count < 0:
        raise ValueError("duplicate_group_count cannot be negative.")
    if duplicate_group_count and layout_count < duplicate_group_count * 2:
        raise ValueError("The layout count is too small for distinct duplicate groups.")

    resolved_path = path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = perf_counter()
    digest = hashlib.sha256()
    duplicate_start = layout_count - duplicate_group_count + 1

    with resolved_path.open("wb") as output:
        for sequence_number in range(1, layout_count + 1):
            source_sequence = (
                sequence_number - duplicate_start + 1
                if duplicate_group_count and sequence_number >= duplicate_start
                else sequence_number
            )
            payload = {
                "schemaVersion": 1,
                "sequenceNumber": sequence_number,
                "cells": list(
                    deterministic_cells(
                        source_sequence,
                        seed=seed,
                    )
                ),
            }
            encoded = (
                json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
            output.write(encoded)
            digest.update(encoded)
            if progress is not None:
                progress(sequence_number, layout_count)

    return LayoutImportFixtureResult(
        path=resolved_path,
        layout_count=layout_count,
        seed=seed,
        duplicate_group_count=duplicate_group_count,
        size_bytes=resolved_path.stat().st_size,
        sha256=digest.hexdigest(),
        elapsed_seconds=perf_counter() - started_at,
        maximum_buffered_record_count=1,
    )


def write_blocked_layout_import_fixture(
    path: Path,
    *,
    layout_count: int = 20,
    seed: int = DEFAULT_ACCEPTANCE_SEED,
) -> LayoutImportFixtureResult:
    """Write a validly parsed source with one duplicate and one missing sequence."""
    if layout_count < 3:
        raise ValueError("The blocked fixture needs at least three rows.")
    resolved_path = path.resolve()
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = perf_counter()
    digest = hashlib.sha256()
    faulty_line_number = layout_count // 2

    with resolved_path.open("wb") as output:
        for line_number in range(1, layout_count + 1):
            sequence_number = (
                line_number - 1
                if line_number == faulty_line_number
                else line_number
            )
            payload = {
                "schemaVersion": 1,
                "sequenceNumber": sequence_number,
                "cells": list(
                    deterministic_cells(
                        line_number,
                        seed=seed,
                    )
                ),
            }
            encoded = (
                json.dumps(payload, separators=(",", ":"), ensure_ascii=True) + "\n"
            ).encode("utf-8")
            output.write(encoded)
            digest.update(encoded)

    return LayoutImportFixtureResult(
        path=resolved_path,
        layout_count=layout_count,
        seed=seed,
        duplicate_group_count=0,
        size_bytes=resolved_path.stat().st_size,
        sha256=digest.hexdigest(),
        elapsed_seconds=perf_counter() - started_at,
        maximum_buffered_record_count=1,
    )
