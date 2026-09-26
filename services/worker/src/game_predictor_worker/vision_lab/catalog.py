"""Adapt immutable DB and raw-file snapshots into a bounded gallery registry."""

import hashlib
import io
import json
from collections import Counter, OrderedDict
from pathlib import Path
from threading import Lock

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from .contracts import Cell, GeometryEngine, GeometryResult, Source, Topology
from .geometry import BaselineEngine, cell_quads, crop_cell
from .snapshot import VERSION, canonical, reject_links, safe_file, verify

MAX_SOURCE_BYTES = 64 * 1024 * 1024


class InvalidImageError(ValueError):
    """A readable source file whose pixel stream cannot be decoded."""


class Catalog:
    def __init__(self, root: Path | None, engine: GeometryEngine | None = None) -> None:
        self.sources: dict[str, Source] = {}
        self.paths: dict[str, Path] = {}
        self.assets: OrderedDict[str, bytes] = OrderedDict()
        self.engine = engine or BaselineEngine()
        self.lock = Lock()
        if root is None:
            return
        manifest = json.loads(safe_file(root, "manifest.json").read_bytes())
        verify(root, manifest)
        folder = manifest.get("format") == VERSION
        if not folder and manifest.get("schemaVersion") != 1:
            raise ValueError("SNAPSHOT_FORMAT_UNSUPPORTED")
        entries = manifest["entries"] if folder else manifest["input"]["entries"]
        counts = Counter(e["sha256" if folder else "expectedSourceSha256"] for e in entries)
        for entry in entries:
            checksum = entry["sha256" if folder else "expectedSourceSha256"]
            relative = (
                f"images/{checksum}.img" if folder else f"images/{checksum[:2]}/{checksum}.jpg"
            )
            if manifest["files"].get(relative) != checksum:
                raise ValueError("SOURCE_NOT_REGISTERED")
            source_id = entry["id" if folder else "sourceImageId"]
            asset_id = hashlib.sha256(canonical(["source", source_id, checksum])).hexdigest()
            self.paths[asset_id] = safe_file(root, relative)
            self.sources[source_id] = Source(
                id=source_id,
                game_id=entry["gameId"],
                game_name=entry.get("gameName", entry["gameId"]),
                filename=entry.get("filename", source_id),
                sha256=checksum,
                asset_id=asset_id,
                source_kind="folder" if folder else "database",
                family_candidate=entry.get("familyCandidate", entry.get("sourceFamilyId", "")),
                role=entry["role"],
                duplicate_count=counts[checksum],
            )

    def _register(self, data: bytes) -> str:
        asset_id = hashlib.sha256(data).hexdigest()
        self.assets[asset_id] = data
        self.assets.move_to_end(asset_id)
        while len(self.assets) > 512:
            self.assets.popitem(last=False)
        return asset_id

    def image(self, source: Source) -> Image.Image:
        path = self.paths[source.asset_id]
        reject_links(path)
        # File access errors are infrastructure. Hash and decoder share this one bounded read.
        with path.open("rb") as stream:
            data = stream.read(MAX_SOURCE_BYTES + 1)
        if len(data) > MAX_SOURCE_BYTES:
            raise InvalidImageError("IMAGE_FILE_TOO_LARGE")
        if hashlib.sha256(data).hexdigest() != source.sha256:
            raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
        try:
            with Image.open(io.BytesIO(data)) as image:
                return ImageOps.exif_transpose(image).convert("RGB")
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
            raise InvalidImageError("IMAGE_DECODE_FAILED") from error

    def asset(self, asset_id: str) -> bytes:
        with self.lock:
            if asset_id in self.assets:
                return self.assets[asset_id]
            source = next((s for s in self.sources.values() if s.asset_id == asset_id), None)
            if source is None:
                raise KeyError(asset_id)
            return encode(self.image(source))

    def detect(self, source_id: str, topology: Topology) -> GeometryResult:
        source = self.sources[source_id]
        with self.lock:
            try:
                rgb = np.asarray(self.image(source), dtype=np.uint8)
            except InvalidImageError:
                return GeometryResult(
                    source_id=source_id,
                    topology=topology,
                    model_version="baseline",
                    status="invalid_image",
                    reasons=["IMAGE_DECODE_FAILED"],
                )
            result = self.engine.detect(source_id, rgb, topology)
            for board in result.boards:
                if board.status in {"absent", "occluded", "unreadable"} and not board.nodes:
                    continue
                try:
                    quads = cell_quads(board, topology)
                except ValueError as error:
                    board.status = "needs_review"
                    board.reasons.append(str(error))
                    continue
                for index, quad in enumerate(quads):
                    crop = crop_cell(rgb, quad)
                    asset_id = (
                        None if crop is None else self._register(encode(Image.fromarray(crop)))
                    )
                    board.cells.append(
                        Cell(
                            index=index,
                            asset_id=asset_id,
                            status="outside_source" if crop is None else "available",
                        )
                    )
            return result


def encode(image: Image.Image) -> bytes:
    stream = io.BytesIO()
    image.save(stream, "JPEG", quality=92)
    return stream.getvalue()
