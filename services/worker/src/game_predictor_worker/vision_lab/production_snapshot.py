"""Frozen training snapshot of production 777 geometry (TASK-0801).

Reads the TASK-0800 candidate manifest (streamed, never loaded whole), plans the
``production-geometry-split-v1`` split (:mod:`.production_split`), copies the
selected source photos byte for byte after a SHA-256 check and publishes an
immutable snapshot directory atomically, following the T01 pattern of
:mod:`.snapshot`: staging directory, ``fsync``-ed files, checksum verification,
one rename, and an idempotent retry that verifies instead of overwriting.

The folder format ``vision-lab-folder-v1`` cannot hold production grids (it has no
geometry, roles or split, and its inventory admits only images), so this module
defines the versioned format ``production-geometry-snapshot-v1``:

``images/<sha[:2]>/<sha>.<ext>``
    untouched copies of the source files, stored orientation (EXIF kept).
``samples.jsonl``
    one line per photo: role, family, difficulty, EXIF orientation, contrast and
    its boards with the 24 nodes in ``exif-normalized-rgb-pixels-v1``.
``split.json``
    policy, configuration, the role of every photo (``selection``), family groups,
    allocation per stratum and the checksum of ``samples.jsonl``.
``report.json``
    counts per role, level, family and difficulty bin, filter rejections and
    integrity exclusions; ``exclusions.jsonl`` lists the integrity exclusions.
``checks/``
    a visual check (grid drawn on oriented photos).
``manifest.json``
    format, snapshot ID and the SHA-256 of every other file.

The snapshot ID is the SHA-256 of the canonical format, policy configuration,
input checksum, contrast definition and selection, so the same seed and input
give the same ID and a re-run verifies the published snapshot without touching it.

Nothing here imports production storage (D-447).
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import time
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Final

import numpy as np
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from . import production_split as split
from .snapshot import canonical, reject_links, safe_file, sha

FORMAT: Final = "production-geometry-snapshot-v1"
SAMPLE_SCHEMA: Final = "production-geometry-snapshot-sample-v1"
CONTRAST_VERSION: Final = "board-rms-luma-contrast-v1"
CONTRAST_DEFINITION: Final = (
    "rmsContrast = population standard deviation of 8-bit luma (PIL 'L', ITU-R 601-2) "
    "of the EXIF-oriented photo inside the board quad polygon, divided by 255; "
    "lowContrast = rmsContrast below the 10th percentile (lower order statistic) of all "
    "training and development boards of the snapshot"
)
LOW_CONTRAST_PERCENTILE: Final = 10
COORDINATE_SPACE: Final = "exif-normalized-rgb-pixels-v1"
MAX_SOURCE_BYTES: Final = 64 * 1024 * 1024
EXIF_ORIENTATION_TAG: Final = 0x0112

INTEGRITY_PATH_UNSAFE: Final = "SOURCE_PATH_UNSAFE"
INTEGRITY_FILE_MISSING: Final = "SOURCE_FILE_MISSING"
INTEGRITY_CHECKSUM_MISMATCH: Final = "SOURCE_CHECKSUM_MISMATCH"
INTEGRITY_TOO_LARGE: Final = "SOURCE_FILE_TOO_LARGE"
INTEGRITY_DECODE_FAILED: Final = "SOURCE_DECODE_FAILED"
INTEGRITY_SIZE_MISMATCH: Final = "ORIENTED_SIZE_MISMATCH"

_IMAGE_SUFFIXES: Final = frozenset({".jpg", ".jpeg", ".png"})
_MANIFEST: Final = "manifest.json"
_SAMPLES: Final = "samples.jsonl"
_SPLIT: Final = "split.json"
_REPORT: Final = "report.json"
_EXCLUSIONS: Final = "exclusions.jsonl"


def dumps(value: object) -> bytes:
    return canonical(value) + b"\n"


@dataclass(frozen=True, slots=True)
class SourceHeader:
    relative_path: str
    oriented_width: int
    oriented_height: int
    family_display_name: str
    import_job_id: str


@dataclass(slots=True)
class CandidateScan:
    images: dict[str, split.ImageFacts]
    sources: dict[str, SourceHeader]
    sha256: str
    rows: int
    bytes: int


def iter_candidate_rows(path: Path, digest: Any | None = None) -> Iterator[dict[str, Any]]:
    """Stream JSON Lines rows; feed the raw bytes to ``digest`` when given."""

    with path.open("rb") as stream:
        for line in stream:
            if digest is not None:
                digest.update(line)
            if line.strip():
                yield json.loads(line)


def scan_candidates(path: Path) -> CandidateScan:
    """One streaming pass: compact facts per photo and the file checksum."""

    digest = hashlib.sha256()
    collector = split.ImageFactsCollector()
    sources: dict[str, SourceHeader] = {}
    rows = 0
    for row in iter_candidate_rows(path, digest):
        if row.get("schemaVersion") != "production-geometry-candidate-v1":
            raise ValueError("CANDIDATE_SCHEMA_UNSUPPORTED")
        collector.add(row)
        rows += 1
        image_id = str(row["sourceImageId"])
        if image_id not in sources:
            sources[image_id] = SourceHeader(
                relative_path=str(row["sourceRelativePath"]),
                oriented_width=int(row["orientedWidth"]),
                oriented_height=int(row["orientedHeight"]),
                family_display_name=str(row["family"].get("sourceDisplayName") or ""),
                import_job_id=str(row["importJobId"]),
            )
    return CandidateScan(collector.images(), sources, digest.hexdigest(), rows, path.stat().st_size)


def _slim_row(row: Mapping[str, Any]) -> dict[str, Any]:
    label = row["label"]
    geometry = row["geometry"]
    signals = row["symbolSignals"]
    return {
        "recognizedBoardId": row["recognizedBoardId"],
        "positionIndex": row["positionIndex"],
        "sequenceNumber": row["sequenceNumber"],
        "level": label["level"],
        "basis": label["basis"],
        "approvalActor": label.get("approvalActor"),
        "nodes": geometry["nodes"],
        "quad": geometry["quad"],
        "quadSource": geometry["quadSource"],
        "topology": geometry["topology"],
        "unavailableCellIndices": row["partial"]["unavailableCellIndices"],
        "symbolSignals": {
            "cellsBelowFilter": signals["cellsBelowFilter"],
            "humanDecidedCells": signals["humanDecidedCells"],
            "minPredictionConfidence": signals["minPredictionConfidence"],
        },
        "difficulty": row["difficulty"],
        "engine": {
            "sourceEngineKind": row["engine"].get("sourceEngineKind"),
            "sourceEngineVersion": row["engine"].get("sourceEngineVersion"),
        },
    }


def collect_rows(path: Path, image_ids: Iterable[str]) -> dict[str, list[dict[str, Any]]]:
    """Second streaming pass: the slim board rows of the wanted photos only."""

    wanted = set(image_ids)
    result: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_candidate_rows(path):
        image_id = str(row["sourceImageId"])
        if image_id in wanted:
            result[image_id].append(_slim_row(row))
    for rows in result.values():
        rows.sort(key=lambda item: int(item["positionIndex"]))
    return dict(result)


def resolve_source(artifact_root: Path, relative_path: str) -> Path:
    """``<artifact_root>/data/<relative>`` as the Admin API resolves managed sources."""

    relative = PurePosixPath(relative_path)
    if (
        not relative_path
        or relative.is_absolute()
        or ".." in relative.parts
        or "\\" in relative_path
        or relative.suffix.lower() not in _IMAGE_SUFFIXES
    ):
        raise ValueError(INTEGRITY_PATH_UNSAFE)
    managed = artifact_root.resolve() / "data"
    candidate = managed.joinpath(*relative.parts)
    if not candidate.resolve().is_relative_to(managed):
        raise ValueError(INTEGRITY_PATH_UNSAFE)
    return candidate


def exif_orientation(image: Image.Image) -> int:
    value = image.getexif().get(EXIF_ORIENTATION_TAG, 1)
    return int(value) if isinstance(value, int) and 1 <= value <= 8 else 1


@dataclass(frozen=True, slots=True)
class SourceFile:
    path: Path
    bytes: int
    exif_orientation: int | None


@dataclass(slots=True)
class SourceInspector:
    """Integrity check of one source photo, cached per photo.

    ``full`` reads the bytes, compares SHA-256, decodes with EXIF transposition and
    compares the oriented size with the manifest; ``stat`` only proves the file
    exists (preview, no reading of pixels).
    """

    artifact_root: Path
    scan: CandidateScan
    full: bool
    results: dict[str, str | None] = field(default_factory=dict)
    files: dict[str, SourceFile] = field(default_factory=dict)

    def __call__(self, image_id: str) -> str | None:
        if image_id not in self.results:
            self.results[image_id] = self._inspect(image_id)
        return self.results[image_id]

    def _inspect(self, image_id: str) -> str | None:
        header = self.scan.sources[image_id]
        try:
            path = resolve_source(self.artifact_root, header.relative_path)
        except ValueError:
            return INTEGRITY_PATH_UNSAFE
        if not path.is_file() or path.is_symlink():
            return INTEGRITY_FILE_MISSING
        size = path.stat().st_size
        if size > MAX_SOURCE_BYTES:
            return INTEGRITY_TOO_LARGE
        if not self.full:
            self.files[image_id] = SourceFile(path, size, None)
            return None
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != self.scan.images[image_id].sha256:
            return INTEGRITY_CHECKSUM_MISMATCH
        try:
            with Image.open(io.BytesIO(data)) as image:
                orientation = exif_orientation(image)
                oriented = ImageOps.exif_transpose(image)
                oriented.load()
                width, height = oriented.size
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, ValueError):
            return INTEGRITY_DECODE_FAILED
        if (width, height) != (header.oriented_width, header.oriented_height):
            return INTEGRITY_SIZE_MISMATCH
        self.files[image_id] = SourceFile(path, len(data), orientation)
        return None


def oriented_luma(data: bytes) -> tuple[np.ndarray, Image.Image]:
    with Image.open(io.BytesIO(data)) as image:
        oriented = ImageOps.exif_transpose(image).convert("RGB")
    return np.asarray(oriented.convert("L"), dtype=np.float64), oriented


def polygon_rms_contrast(luma: np.ndarray, quad: Iterable[Iterable[float]]) -> float | None:
    """RMS contrast (std / 255) of luma inside the polygon; ``None`` without pixels."""

    points = [(float(x), float(y)) for x, y in quad]
    height, width = luma.shape
    left = max(0, int(np.floor(min(x for x, _ in points))))
    top = max(0, int(np.floor(min(y for _, y in points))))
    right = min(width, int(np.ceil(max(x for x, _ in points))) + 1)
    bottom = min(height, int(np.ceil(max(y for _, y in points))) + 1)
    if right <= left or bottom <= top:
        return None
    mask_image = Image.new("1", (right - left, bottom - top), 0)
    ImageDraw.Draw(mask_image).polygon([(x - left, y - top) for x, y in points], fill=1)
    mask = np.asarray(mask_image, dtype=bool)
    values = luma[top:bottom, left:right][mask]
    if values.size == 0:
        return None
    return float(values.std() / 255.0)


def draw_grids(image: Image.Image, boards: Iterable[Mapping[str, Any]]) -> Image.Image:
    """Copy of the oriented photo with every board's 5 x 3 grid drawn on it."""

    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    for board in boards:
        nodes = [(float(x), float(y)) for x, y in board["nodes"]]
        rows = [nodes[r * 6 : r * 6 + 6] for r in range(4)]
        for line in rows:
            draw.line(line, fill=(255, 0, 255), width=2)
        for column in range(6):
            draw.line([rows[r][column] for r in range(4)], fill=(255, 0, 255), width=2)
    return canvas


def snapshot_identity(
    config: split.SplitConfig, input_facts: Mapping[str, Any], selection: list[list[str]]
) -> dict[str, Any]:
    return {
        "format": FORMAT,
        "policy": config.describe(),
        "input": dict(input_facts),
        "contrastVersion": CONTRAST_VERSION,
        "selection": selection,
    }


def snapshot_id_of(identity: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical(identity)).hexdigest()


def verify_snapshot(root: Path, *, published: bool = True) -> dict[str, Any]:
    """Check inventory, checksums and the snapshot ID (and directory name when published)."""

    reject_links(root)
    manifest: dict[str, Any] = json.loads(safe_file(root, _MANIFEST).read_bytes())
    if manifest.get("format") != FORMAT:
        raise ValueError("SNAPSHOT_FORMAT_UNSUPPORTED")
    inventory = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if inventory - {_MANIFEST} != set(manifest["files"]):
        raise ValueError("SNAPSHOT_INVENTORY_MISMATCH")
    for relative, checksum in manifest["files"].items():
        if sha(safe_file(root, relative)) != checksum:
            raise ValueError("SNAPSHOT_CHECKSUM_MISMATCH")
    split_document = json.loads(safe_file(root, _SPLIT).read_bytes())
    identity = {
        "format": manifest["format"],
        "policy": manifest["policy"],
        "input": manifest["input"],
        "contrastVersion": manifest["contrastVersion"],
        "selection": split_document["selection"],
    }
    if snapshot_id_of(identity) != manifest["snapshotId"]:
        raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")
    if published and root.name != manifest["snapshotId"]:
        raise ValueError("SNAPSHOT_IDENTITY_MISMATCH")
    for item in split_document["selection"]:
        if manifest["files"].get(image_relative_path(item[2], item[3])) != item[2]:
            raise ValueError("SNAPSHOT_IMAGE_NOT_REGISTERED")
    return manifest


def image_relative_path(checksum: str, suffix: str) -> str:
    return f"images/{checksum[:2]}/{checksum}{suffix}"


@dataclass(slots=True)
class BuildResult:
    mode: str
    summary: dict[str, Any]
    selected_bytes: int
    snapshot_id: str | None = None
    destination: Path | None = None
    status: str = "preview"
    timings: dict[str, float] = field(default_factory=dict)
    blockers: list[str] = field(default_factory=list)


def _blockers(
    plan: split.SplitPlan, summary: Mapping[str, Any], max_bytes: int, size: int
) -> list[str]:
    config = plan.config
    blockers = []
    for role, per_level in (
        (split.ROLE_TRAINING, config.training_per_level),
        (split.ROLE_DEVELOPMENT, config.development_per_level),
    ):
        counts = summary["roles"][role]["imagesByLevel"]
        for level in split.TRAINING_LEVELS:
            if counts.get(level, 0) < per_level:
                blockers.append(
                    f"{role.upper()}_{level}_BELOW_TARGET:{counts.get(level, 0)}<{per_level}"
                )
    if any(item["reason"] == "POOL_SMALLER_THAN_TARGET" for item in plan.shortfalls):
        blockers.append("POOL_SMALLER_THAN_TARGET")
    if summary["maxTrainingFamilyShare"] > float(config.family_cap_fraction) + 1e-9:
        blockers.append("FAMILY_SHARE_ABOVE_CAP")
    if size > max_bytes:
        blockers.append(f"COPY_SIZE_ABOVE_LIMIT:{size}>{max_bytes}")
    return blockers


def build_snapshot(
    candidates: Path,
    artifact_root: Path,
    output_root: Path,
    config: split.SplitConfig,
    *,
    preview: bool,
    max_copy_bytes: int = 3 * 1024**3,
    log: Callable[[str], None] = print,
) -> BuildResult:
    """Plan the split; in build mode copy, verify and publish the snapshot atomically."""

    timings: dict[str, float] = {}
    started = time.monotonic()
    scan = scan_candidates(candidates)
    timings["scanSeconds"] = round(time.monotonic() - started, 1)
    log(f"scanned {scan.rows} rows, {len(scan.images)} photos, sha256 {scan.sha256}")
    export_manifest = candidates.parent / "export_manifest.json"
    input_facts: dict[str, Any] = {
        "candidatesFile": candidates.name,
        "candidatesSha256": scan.sha256,
        "candidateRows": scan.rows,
        "photos": len(scan.images),
    }
    if export_manifest.is_file():
        exported = json.loads(export_manifest.read_bytes())
        recorded = exported.get("files", {}).get(candidates.name, {}).get("sha256")
        if recorded is not None and recorded != scan.sha256:
            raise ValueError("INPUT_CHECKSUM_MISMATCH")
        input_facts["exportId"] = exported.get("exportId")
        input_facts["exporterVersion"] = exported.get("exporterVersion")
        input_facts["gameId"] = exported.get("gameId")

    inspector = SourceInspector(artifact_root, scan, full=not preview)
    started = time.monotonic()
    plan = split.plan_split(scan.images, config, inspector)
    timings["planSeconds"] = round(time.monotonic() - started, 1)
    summary = split.split_summary(plan, scan.images)
    selected = sorted(plan.roles)
    selected_bytes = sum(inspector.files[i].bytes for i in selected)
    unique_bytes = sum({scan.images[i].sha256: inspector.files[i].bytes for i in selected}.values())
    summary["copy"] = {
        "photos": len(selected),
        "bytes": selected_bytes,
        "uniqueBytes": unique_bytes,
    }
    summary["integrityExclusionList"] = [
        {"imageId": i, "reason": r} for i, r in sorted(plan.integrity_exclusions.items())
    ]
    blockers = _blockers(plan, summary, max_copy_bytes, unique_bytes)
    result = BuildResult(
        mode="preview" if preview else "build",
        summary=summary,
        selected_bytes=unique_bytes,
        timings=timings,
        blockers=blockers,
    )
    selection = [
        [
            image_id,
            plan.roles[image_id],
            scan.images[image_id].sha256,
            PurePosixPath(scan.sources[image_id].relative_path).suffix.lower(),
        ]
        for image_id in selected
    ]
    identity = snapshot_identity(config, input_facts, selection)
    result.snapshot_id = snapshot_id_of(identity)
    if preview or blockers:
        result.status = "blocked" if blockers else "preview"
        return result

    destination = output_root / result.snapshot_id
    result.destination = destination
    if destination.exists():
        verify_snapshot(destination)
        result.status = "already_published_verified"
        return result
    output_root.mkdir(parents=True, exist_ok=True)
    reject_links(output_root.absolute())
    stage = Path(tempfile.mkdtemp(prefix=".production-geometry-", dir=output_root))
    try:
        started = time.monotonic()
        rows = collect_rows(candidates, selected)
        timings["collectRowsSeconds"] = round(time.monotonic() - started, 1)
        started = time.monotonic()
        files = _write_stage(stage, plan, scan, inspector, rows, identity, summary, log)
        timings["copySeconds"] = round(time.monotonic() - started, 1)
        manifest = {
            "format": FORMAT,
            "snapshotId": result.snapshot_id,
            "policy": identity["policy"],
            "input": identity["input"],
            "contrastVersion": CONTRAST_VERSION,
            "contrastDefinition": CONTRAST_DEFINITION,
            "coordinateSpace": COORDINATE_SPACE,
            "files": files,
        }
        with (stage / _MANIFEST).open("xb") as stream:
            stream.write(dumps(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        verify_snapshot(stage, published=False)
        try:
            stage.rename(destination)
        except OSError:
            if not destination.exists():
                raise
            verify_snapshot(destination)
            result.status = "already_published_verified"
            return result
        verify_snapshot(destination)
        result.status = "published"
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _write_file(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(data).hexdigest()


def _write_stage(
    stage: Path,
    plan: split.SplitPlan,
    scan: CandidateScan,
    inspector: SourceInspector,
    rows: Mapping[str, list[dict[str, Any]]],
    identity: Mapping[str, Any],
    summary: dict[str, Any],
    log: Callable[[str], None],
) -> dict[str, str]:
    files: dict[str, str] = {}
    records: list[dict[str, Any]] = []
    copied: set[str] = set()
    visual: dict[str, tuple[Image.Image, list[dict[str, Any]]]] = {}
    exif_counts: dict[str, int] = defaultdict(int)
    selected = sorted(plan.roles)
    for count, image_id in enumerate(selected, 1):
        image = scan.images[image_id]
        header = scan.sources[image_id]
        source = inspector.files[image_id]
        data = source.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != image.sha256:
            raise ValueError(f"SOURCE_CHANGED_DURING_BUILD: {image_id}")
        suffix = PurePosixPath(header.relative_path).suffix.lower()
        relative = image_relative_path(image.sha256, suffix)
        if relative not in copied:
            files[relative] = _write_file(stage / relative, data)
            copied.add(relative)
        luma, oriented = oriented_luma(data)
        board_rows = rows.get(image_id, [])
        if len(board_rows) != len(image.boards):
            raise ValueError(f"CANDIDATE_ROWS_CHANGED: {image_id}")
        role = plan.roles[image_id]
        boards = []
        for row in board_rows:
            contrast = polygon_rms_contrast(luma, row["quad"])
            boards.append(
                {
                    **row,
                    "evaluationTarget": role == split.ROLE_GOLD and row["level"] == "G",
                    "trainingTarget": role in (split.ROLE_TRAINING, split.ROLE_DEVELOPMENT),
                    "contrast": {
                        "rmsContrast": None if contrast is None else round(contrast, 6),
                    },
                }
            )
        orientation = source.exif_orientation or 1
        exif_counts[str(orientation)] += 1
        record: dict[str, Any] = {
            "schemaVersion": SAMPLE_SCHEMA,
            "imageId": image_id,
            "role": role,
            "imageLevel": split.photo_level_label(plan, image),
            "goldBasis": plan.gold_basis.get(image_id) if role == split.ROLE_GOLD else None,
            "familySeenInTraining": plan.family_seen_in_training.get(image_id)
            if role == split.ROLE_GOLD
            else None,
            "sourceChecksumSha256": image.sha256,
            "imagePath": relative,
            "sourceRelativePath": header.relative_path,
            "coordinateSpace": COORDINATE_SPACE,
            "exifOrientation": orientation,
            "orientedWidth": header.oriented_width,
            "orientedHeight": header.oriented_height,
            "familyId": image.family_id,
            "familyGroupId": plan.family_group_of[image.family_id],
            "familyDisplayName": header.family_display_name,
            "importJobId": header.import_job_id,
            "expectedBoardsOnImage": image.expected_boards,
            "difficulty": plan.difficulty.get(image_id),
            "contrast": {"imageRmsContrast": round(float(luma.std() / 255.0), 6)},
            "boards": boards,
        }
        records.append(record)
        if role == split.ROLE_TRAINING and "training" not in visual:
            visual["training"] = (oriented, boards)
        if (
            role == split.ROLE_GOLD
            and "gold" not in visual
            and any(b["evaluationTarget"] for b in boards)
        ):
            visual["gold"] = (oriented, boards)
        if orientation != 1 and "exif" not in visual:
            visual["exif"] = (oriented, boards)
        if count % 500 == 0:
            log(f"copied {count}/{len(selected)} photos")
    values = sorted(
        board["contrast"]["rmsContrast"]
        for record in records
        if record["role"] != split.ROLE_GOLD
        for board in record["boards"]
        if board["contrast"]["rmsContrast"] is not None
    )
    threshold = values[(len(values) * LOW_CONTRAST_PERCENTILE) // 100] if values else None
    low: dict[str, int] = defaultdict(int)
    for record in records:
        for board in record["boards"]:
            value = board["contrast"]["rmsContrast"]
            flag = threshold is not None and value is not None and value < threshold
            board["contrast"]["lowContrast"] = flag
            if flag:
                low[record["role"]] += 1
    role_order = {role: index for index, role in enumerate(split.ROLES)}
    records.sort(key=lambda r: (role_order[r["role"]], r["imageId"]))
    samples = b"".join(dumps(record) for record in records)
    files[_SAMPLES] = _write_file(stage / _SAMPLES, samples)
    for name, (oriented, boards) in sorted(visual.items()):
        stream = io.BytesIO()
        draw_grids(oriented, boards).save(stream, "JPEG", quality=90)
        files[f"checks/visual-{name}.jpg"] = _write_file(
            stage / "checks" / f"visual-{name}.jpg", stream.getvalue()
        )
    split_document = {
        "policyVersion": split.POLICY_VERSION,
        "policy": identity["policy"],
        "input": identity["input"],
        "selection": identity["selection"],
        "selectionColumns": ["imageId", "role", "sourceChecksumSha256", "suffix"],
        "familyGroups": {g: f for g, f in sorted(plan.family_groups.items())},
        "developmentFamilyGroups": plan.development_groups,
        "trainingFamilyGroups": plan.training_groups,
        "developmentFamilyOrder": plan.development_family_order,
        "difficultyEdges": plan.difficulty_edges,
        "allocations": plan.allocations,
        "shortfalls": plan.shortfalls,
        "samplesSha256": files[_SAMPLES],
        "samples": len(records),
    }
    files[_SPLIT] = _write_file(stage / _SPLIT, dumps(split_document))
    exclusions = b"".join(
        dumps({"imageId": i, "reason": r, "sourceRelativePath": scan.sources[i].relative_path})
        for i, r in sorted(plan.integrity_exclusions.items())
    )
    files[_EXCLUSIONS] = _write_file(stage / _EXCLUSIONS, exclusions)
    summary["contrast"] = {
        "definition": CONTRAST_DEFINITION,
        "lowContrastThreshold": threshold,
        "lowContrastBoardsByRole": dict(sorted(low.items())),
    }
    summary["exifOrientationCounts"] = dict(sorted(exif_counts.items()))
    summary["visualChecks"] = sorted(f"checks/visual-{name}.jpg" for name in visual)
    files[_REPORT] = _write_file(stage / _REPORT, dumps(summary))
    return dict(sorted(files.items()))
