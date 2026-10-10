"""Synthetic TASK-0800 candidate rows and managed source photos for TASK-0801 tests."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image

WIDTH = 120
HEIGHT = 90


def grid_nodes(left: float, top: float, width: float, height: float) -> list[list[float]]:
    return [
        [round(left + width * column / 5, 4), round(top + height * row / 3, 4)]
        for row in range(4)
        for column in range(6)
    ]


def jpeg_bytes(
    seed: int, size: tuple[int, int] = (WIDTH, HEIGHT), orientation: int | None = None
) -> bytes:
    image = Image.new("RGB", size, (seed * 37 % 256, seed * 91 % 256, seed * 53 % 256))
    for x in range(0, size[0], 8):
        for y in range(0, size[1], 8):
            if (x // 8 + y // 8 + seed) % 2:
                image.putpixel((x, y), (255, 255, 255))
    stream = io.BytesIO()
    if orientation is None:
        image.save(stream, "JPEG", quality=90)
    else:
        exif = Image.Exif()
        exif[0x0112] = orientation
        image.save(stream, "JPEG", quality=90, exif=exif.tobytes())
    return stream.getvalue()


def board_row(
    *,
    image_id: str,
    sha: str,
    family: str,
    level: str,
    position: int,
    sequence: int,
    boards_on_image: int = 3,
    expected: int | None = None,
    cells_below: int = 0,
    skew: float = 2.0,
    area: float = 0.02,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> dict[str, Any]:
    left = 4 + 38 * (position % 3)
    nodes = grid_nodes(left, 10, 30, 18)
    return {
        "schemaVersion": "production-geometry-candidate-v1",
        "candidateBoardsOnImage": boards_on_image,
        "expectedBoardsOnImage": boards_on_image if expected is None else expected,
        "coordinateSpace": "exif-normalized-rgb-pixels-v1",
        "difficulty": {
            "areaFraction": area,
            "maxAngleDeviationDeg": skew,
            "edgeRatioHorizontal": 1.0,
            "edgeRatioVertical": 1.0,
            "nodesOutsideImage": 0,
            "partialBoard": False,
        },
        "engine": {"sourceEngineKind": "structured_opencv_v1", "sourceEngineVersion": "v"},
        "family": {
            "familyId": family,
            "familyBasis": "import_source_directory",
            "importJobId": "job-" + family,
            "sourceDisplayName": family + " cut",
        },
        "gameId": "game",
        "geometry": {
            "nodes": nodes,
            "quad": [nodes[0], nodes[5], nodes[23], nodes[18]],
            "quadSource": "source_revision_symbol_grid_quad",
            "topology": {"columns": 5, "rows": 3},
            "nodeOrder": "row-major",
            "maxManifestDeviationPx": 0.0,
        },
        "importJobId": "job-" + family,
        "label": {"level": level, "basis": "test", "approvalActor": None},
        "orientedHeight": height,
        "orientedWidth": width,
        "partial": {"isPartial": False, "unavailableCellIndices": []},
        "positionIndex": position,
        "recognizedBoardId": f"{image_id}-b{position}",
        "sequenceNumber": sequence,
        "sourceChecksumSha256": sha,
        "sourceImageId": image_id,
        "sourceRelativePath": f"originals/{sha[:2]}/{sha}.jpg",
        "symbolSignals": {
            "cells": 15,
            "cellsBelowFilter": cells_below,
            "humanDecidedCells": 0,
            "minPredictionConfidence": 0.99,
        },
    }


class Dataset:
    """Writes photos under ``<root>/artifacts/data`` and rows to ``candidates.jsonl``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.artifacts = root / "artifacts"
        self.rows: list[dict[str, Any]] = []
        self.sequence = 0
        self.counter = 0

    def photo(
        self,
        family: str,
        levels: list[str],
        *,
        image_id: str | None = None,
        data: bytes | None = None,
        cells_below: list[int] | None = None,
        expected: int | None = None,
        skew: float | None = None,
        area: float | None = None,
        size: tuple[int, int] = (WIDTH, HEIGHT),
        write: bool = True,
    ) -> str:
        self.counter += 1
        image_id = image_id or f"img-{self.counter:04d}"
        data = data if data is not None else jpeg_bytes(self.counter)
        sha = hashlib.sha256(data).hexdigest()
        if write:
            path = self.artifacts / "data" / "originals" / sha[:2] / f"{sha}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for position, level in enumerate(levels):
            self.sequence += 1
            self.rows.append(
                board_row(
                    image_id=image_id,
                    sha=sha,
                    family=family,
                    level=level,
                    position=position,
                    sequence=self.sequence,
                    boards_on_image=len(levels),
                    expected=expected,
                    cells_below=(cells_below or [0] * len(levels))[position],
                    skew=skew if skew is not None else 1.0 + (self.counter % 7),
                    area=area if area is not None else 0.01 + (self.counter % 5) / 100,
                    width=size[0],
                    height=size[1],
                )
            )
        return image_id

    def write(self) -> Path:
        path = self.root / "export" / "candidates.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(json.dumps(row).encode() + b"\n" for row in self.rows))
        return path


def standard_dataset(root: Path, families: int = 7, per_level: int = 4) -> Dataset:
    """``families`` families with ``per_level`` S and B photos each, plus gold and rejects."""

    data = Dataset(root)
    for family in range(families):
        name = f"selection:fam{family}"
        for _ in range(per_level):
            data.photo(name, ["S", "S", "S"])
            data.photo(name, ["B", "B", "B"])
    data.photo("selection:fam0", ["G", "G", "G"], image_id="gold-full")
    data.photo("selection:fam1", ["G", "U", "U"], image_id="gold-mixed")
    data.photo("selection:fam2", ["S", "S", "S"], image_id="reject-filter", cells_below=[0, 2, 0])
    data.photo("selection:fam2", ["U", "U", "U"], image_id="reject-u")
    data.photo("selection:fam3", ["B", "B"], image_id="reject-incomplete", expected=3)
    return data
