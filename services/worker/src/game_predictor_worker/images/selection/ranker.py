"""Deterministic, shadow-only representative ranking from manual selections.

The ranker deliberately lives beside the selector rather than inside the group
boundary code. It consumes human-labelled candidates and can only order images
which the v10.21 selector has already put in the same group.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
from torch import Tensor, nn

from ..image_file import sha256_file
from .contracts import ImageQualityMetrics, SelectionGroupResult

RANKER_MODEL_VERSION = "representative-quality-mlp-v1"
RANKER_COHORT_KIND = "representative-quality-ranking-cohort-v1"
RANKER_FEATURE_VERSION = "image-quality-metrics-seven-plus-position-v1"
RANKER_FEATURE_NAMES = (
    "sharpness",
    "exposure",
    "highlight_retention",
    "glare_resistance",
    "perspective",
    "border_margin",
    "board_visibility",
    "relative_position",
)
RANKER_INPUT_SIZE = 8
RANKER_HIDDEN_SIZES = (16, 8)
MINIMUM_PROMOTION_GROUPS = 300
MINIMUM_PROMOTION_PAIRS = 1000
MAX_MANUAL_AUDIT_BAD_RECOMMENDATIONS = 0


@dataclass(frozen=True, slots=True)
class RankingCohortPreview:
    positive_count: int
    reliable_pair_count: int
    excluded_ambiguous_count: int
    folder_count: int
    group_count: int
    manifest_checksum_sha256: str | None = None

    def to_dict(self) -> dict[str, int | str | None]:
        return {
            "excludedAmbiguousCount": self.excluded_ambiguous_count,
            "folderCount": self.folder_count,
            "groupCount": self.group_count,
            "manifestChecksumSha256": self.manifest_checksum_sha256,
            "positiveCount": self.positive_count,
            "reliablePairCount": self.reliable_pair_count,
        }


@dataclass(frozen=True, slots=True)
class RepresentativeRankerSnapshot:
    feature_version: str
    model_version: str
    model_checksum_sha256: str
    model_relative_path: str
    standardization_mean: tuple[float, ...]
    standardization_scale: tuple[float, ...]
    status: str
    metrics: Mapping[str, float]
    cohort_checksum_sha256: str

    def __post_init__(self) -> None:
        if self.feature_version != RANKER_FEATURE_VERSION:
            raise ValueError("Unsupported representative ranker feature version.")
        if self.model_version != RANKER_MODEL_VERSION:
            raise ValueError("Unsupported representative ranker model version.")
        if len(self.standardization_mean) != RANKER_INPUT_SIZE:
            raise ValueError("Ranker standardization mean has an invalid size.")
        if len(self.standardization_scale) != RANKER_INPUT_SIZE:
            raise ValueError("Ranker standardization scale has an invalid size.")
        if any(value <= 0 for value in self.standardization_scale):
            raise ValueError("Ranker standardization scale must be positive.")
        for checksum in (self.model_checksum_sha256, self.cohort_checksum_sha256):
            if len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum):
                raise ValueError("Ranker checksums must be SHA-256 values.")
        if self.status not in {"shadow", "candidate", "active", "rejected"}:
            raise ValueError("Invalid representative ranker status.")

    def to_dict(self) -> dict[str, object]:
        return {
            "cohortChecksumSha256": self.cohort_checksum_sha256,
            "featureNames": list(RANKER_FEATURE_NAMES),
            "featureVersion": self.feature_version,
            "metrics": dict(self.metrics),
            "modelChecksumSha256": self.model_checksum_sha256,
            "modelRelativePath": self.model_relative_path,
            "modelVersion": self.model_version,
            "standardization": {
                "mean": list(self.standardization_mean),
                "scale": list(self.standardization_scale),
            },
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> RepresentativeRankerSnapshot:
        standardization = _mapping(value.get("standardization"))
        mean = _sequence(standardization.get("mean"))
        scale = _sequence(standardization.get("scale"))
        metrics = value.get("metrics", {})
        return cls(
            feature_version=str(value.get("featureVersion", "")),
            model_version=str(value.get("modelVersion", "")),
            model_checksum_sha256=_checksum(value.get("modelChecksumSha256")),
            model_relative_path=_text(value, "modelRelativePath"),
            standardization_mean=tuple(_float_value(item) for item in mean),
            standardization_scale=tuple(_float_value(item) for item in scale),
            status=str(value.get("status", "shadow")),
            metrics={key: _float_value(item) for key, item in _mapping(metrics).items()},
            cohort_checksum_sha256=_checksum(value.get("cohortChecksumSha256")),
        )


class _RepresentativeQualityMLP(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.layers = nn.Sequential(
            nn.Linear(RANKER_INPUT_SIZE, 16),
            nn.ReLU(),
            nn.Linear(16, 8),
            nn.ReLU(),
            nn.Linear(8, 1),
        )

    def forward(self, value: Tensor) -> Tensor:
        return self.layers(value)


def quality_features(metrics: ImageQualityMetrics, relative_position: float) -> np.ndarray:
    """Return seven raw quality metrics plus the candidate's group position."""

    if not 0 <= relative_position <= 1:
        raise ValueError("Relative candidate position must be between zero and one.")
    return cast(
        np.ndarray,
        np.asarray((*metrics.values()[:7], float(relative_position)), dtype=np.float32),
    )


def build_ranking_cohort(
    trace_manifest: Mapping[str, object],
    output_manifest: Mapping[str, object],
    *,
    source_roots: Sequence[Path],
) -> tuple[dict[str, object], RankingCohortPreview]:
    """Freeze reliable manual events into a content-addressed feature cohort."""

    _require_manifest(trace_manifest, "manual-image-selection-trace-v1")
    _require_manifest(output_manifest, "manual-image-selection-output-v1")
    events = _sequence(trace_manifest.get("events"))
    output_items = _sequence(output_manifest.get("items"))
    accepted_by_path: dict[str, tuple[str, int, int, str]] = {}
    positive_paths: set[str] = set()
    for item in output_items:
        value = _mapping(item)
        path = _text(value, "imagePath")
        checksum = _checksum(value.get("imageChecksum"))
        key = _group_key(value, trace_manifest)
        accepted_by_path[path] = (
            key,
            _int_value(value.get("rangeStart")),
            _int_value(value.get("rangeEnd")),
            checksum,
        )
        positive_paths.add(path)
    accepted_elsewhere: dict[str, set[str]] = defaultdict(set)
    for event in events:
        value = _mapping(event)
        if value.get("kind") == "accepted":
            accepted_elsewhere[_text(value, "imagePath")].add(_group_key(value, trace_manifest))

    views_by_group: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for event in events:
        value = _mapping(event)
        if (
            value.get("kind") == "viewed"
            and value.get("decoded") is True
            and _number(value.get("visibleMilliseconds")) >= 300
        ):
            views_by_group[_group_key(value, trace_manifest)].append(value)

    feature_rows: list[dict[str, object]] = []
    pair_rows: list[dict[str, object]] = []
    excluded_ambiguous = 0
    descriptor_cache: dict[str, np.ndarray] = {}
    metric_cache: dict[str, ImageQualityMetrics] = {}
    path_cache: dict[str, Path | None] = {}

    def resolve(path_text: str) -> Path | None:
        if path_text not in path_cache:
            path_cache[path_text] = _resolve_source(path_text, source_roots)
        return path_cache[path_text]

    def inspect(path_text: str) -> tuple[Path, ImageQualityMetrics, np.ndarray] | None:
        path = resolve(path_text)
        if path is None:
            return None
        try:
            checksum = sha256_file(path)
            if path_text in accepted_by_path and checksum != accepted_by_path[path_text][3]:
                return None
            if path_text not in metric_cache:
                metric_cache[path_text] = _measure_quality(path)
                descriptor_cache[path_text] = _appearance_descriptor(path)
            return path, metric_cache[path_text], descriptor_cache[path_text]
        except (OSError, ValueError, cv2.error):
            return None

    for path_text, (group_key, range_start, range_end, checksum) in sorted(
        accepted_by_path.items(), key=lambda item: (item[1][0], item[0])
    ):
        inspected_positive = inspect(path_text)
        if inspected_positive is None:
            excluded_ambiguous += 1
            continue
        positive_index = len(feature_rows)
        feature_rows.append(
            _feature_row(
                group_key=group_key,
                folder_key=_folder_key(path_text),
                path=path_text,
                checksum=checksum,
                metrics=inspected_positive[1],
                relative_position=_relative_position(path_text, views_by_group[group_key]),
                label="positive",
                range_start=range_start,
                range_end=range_end,
            )
        )
        positive_descriptor = inspected_positive[2]
        candidates = views_by_group[group_key]
        for event in candidates:
            candidate_path = _text(event, "imagePath")
            if candidate_path == path_text or candidate_path in positive_paths:
                continue
            if accepted_elsewhere.get(candidate_path, set()) - {group_key}:
                excluded_ambiguous += 1
                continue
            inspected_candidate = inspect(candidate_path)
            if inspected_candidate is None:
                excluded_ambiguous += 1
                continue
            distance = float(np.mean(np.square(positive_descriptor - inspected_candidate[2])))
            if distance > 0.12:
                excluded_ambiguous += 1
                continue
            negative_index = len(feature_rows)
            feature_rows.append(
                _feature_row(
                    group_key=group_key,
                    folder_key=_folder_key(candidate_path),
                    path=candidate_path,
                    checksum=sha256_file(inspected_candidate[0]),
                    metrics=inspected_candidate[1],
                    relative_position=_relative_position(candidate_path, candidates),
                    label="negative",
                    range_start=range_start,
                    range_end=range_end,
                )
            )
            pair_rows.append(
                {
                    "confidence": round(max(0.0, min(1.0, 1.0 - distance / 0.12)), 6),
                    "groupKey": group_key,
                    "negative": negative_index,
                    "positive": positive_index,
                }
            )

    folders = {str(row["folderKey"]) for row in feature_rows}
    groups = {str(row["groupKey"]) for row in feature_rows if row["label"] == "positive"}
    payload: dict[str, object] = {
        "featureNames": list(RANKER_FEATURE_NAMES),
        "featureVersion": RANKER_FEATURE_VERSION,
        "kind": RANKER_COHORT_KIND,
        "modelVersion": RANKER_MODEL_VERSION,
        "pairs": pair_rows,
        "samples": feature_rows,
        "schemaVersion": 1,
        "sourceFolderCount": len(folders),
        "sourceGroupCount": len(groups),
    }
    checksum = _canonical_checksum(payload)
    payload["manifestChecksumSha256"] = checksum
    preview = RankingCohortPreview(
        positive_count=sum(row["label"] == "positive" for row in feature_rows),
        reliable_pair_count=len(pair_rows),
        excluded_ambiguous_count=excluded_ambiguous,
        folder_count=len(folders),
        group_count=len(groups),
        manifest_checksum_sha256=checksum,
    )
    return payload, preview


def write_ranking_cohort(
    payload: Mapping[str, object],
    output_directory: Path,
) -> tuple[Path, str]:
    """Write a checksum-addressed cohort manifest without overwriting content."""

    body = dict(payload)
    body.pop("manifestChecksumSha256", None)
    checksum = _canonical_checksum(body)
    if payload.get("manifestChecksumSha256") not in {None, checksum}:
        raise ValueError("Ranking cohort manifest checksum does not match content.")
    target = output_directory.resolve() / "data" / "ranker-cohorts" / f"{checksum}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    content = _canonical_json({**body, "manifestChecksumSha256": checksum})
    if target.exists() and target.read_bytes() != content:
        raise ValueError("A content-addressed ranking cohort has changed.")
    if not target.exists():
        temporary = target.with_suffix(".part")
        temporary.write_bytes(content)
        os.replace(temporary, target)
    return target, checksum


def train_ranker(
    cohort: Mapping[str, object],
    *,
    output_directory: Path,
    seed: int = 20260818,
    epochs: int = 240,
) -> tuple[RepresentativeRankerSnapshot, dict[str, object]]:
    """Train the fixed MLP on a cumulative cohort and export an ONNX snapshot."""

    _require_manifest(cohort, RANKER_COHORT_KIND)
    samples = [_mapping(item) for item in _sequence(cohort.get("samples"))]
    pairs = [_mapping(item) for item in _sequence(cohort.get("pairs"))]
    if not pairs:
        raise ValueError("The ranking cohort has no reliable pairs.")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)
    features = np.asarray(
        [
            _feature_vector(sample)
            for sample in samples
        ],
        dtype=np.float32,
    )
    pair_values = [
        (_int_value(pair.get("positive")), _int_value(pair.get("negative")))
        for pair in pairs
    ]
    train_pairs, test_pairs = _split_pairs(pair_values, samples)
    if not train_pairs:
        train_pairs = pair_values
    train_indexes = sorted({index for pair in train_pairs for index in pair})
    mean = features[train_indexes].mean(axis=0)
    scale = features[train_indexes].std(axis=0)
    scale = np.where(scale < 1e-6, 1.0, scale).astype(np.float32)
    normalized = (features - mean) / scale
    model = _RepresentativeQualityMLP()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    tensor_features = torch.from_numpy(normalized)
    positive = torch.tensor([pair[0] for pair in train_pairs], dtype=torch.long)
    negative = torch.tensor([pair[1] for pair in train_pairs], dtype=torch.long)
    model.train()
    for _ in range(max(1, epochs)):
        optimizer.zero_grad(set_to_none=True)
        difference = model(tensor_features[positive]) - model(tensor_features[negative])
        loss = torch.nn.functional.softplus(-difference).mean()
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.no_grad():
        scores = model(tensor_features).reshape(-1).numpy()
    baseline_scores = np.asarray([_baseline_score(sample) for sample in samples])
    model_pairwise = _pairwise_accuracy(scores, test_pairs or pair_values)
    baseline_pairwise = _pairwise_accuracy(baseline_scores, test_pairs or pair_values)
    body = _canonical_json(
        {
            "cohortChecksumSha256": _checksum(cohort.get("manifestChecksumSha256")),
            "featureVersion": RANKER_FEATURE_VERSION,
            "mean": mean.tolist(),
            "scale": scale.tolist(),
            "seed": seed,
            "modelVersion": RANKER_MODEL_VERSION,
        }
    )
    model_checksum = hashlib.sha256(body).hexdigest()
    model_directory = output_directory.resolve() / "data" / "ranker-models"
    model_directory.mkdir(parents=True, exist_ok=True)
    model_path = model_directory / f"{model_checksum}.onnx"
    dummy = torch.zeros((1, RANKER_INPUT_SIZE), dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy,
        model_path,
        input_names=["features"],
        output_names=["score"],
        opset_version=17,
        dynamo=False,
        dynamic_axes={"features": {0: "batch"}, "score": {0: "batch"}},
    )
    model_checksum = hashlib.sha256(model_path.read_bytes()).hexdigest()
    onnx_parity_error = _onnx_parity_error(
        model,
        model_path,
        normalized,
    )
    report: dict[str, object] = {
        "baselinePairwiseAccuracy": baseline_pairwise,
        "cohortChecksumSha256": _checksum(cohort.get("manifestChecksumSha256")),
        "featureVersion": RANKER_FEATURE_VERSION,
        "modelPairwiseAccuracy": model_pairwise,
        "onnxParityMaxAbsError": onnx_parity_error,
        "pairCount": len(pair_values),
        "seed": seed,
        "testPairCount": len(test_pairs),
        "trainPairCount": len(train_pairs),
    }
    snapshot = RepresentativeRankerSnapshot(
        feature_version=RANKER_FEATURE_VERSION,
        model_version=RANKER_MODEL_VERSION,
        model_checksum_sha256=model_checksum,
        model_relative_path=model_path.relative_to(output_directory.resolve()).as_posix(),
        standardization_mean=tuple(float(value) for value in mean),
        standardization_scale=tuple(float(value) for value in scale),
        status="shadow",
        metrics={
            "baselinePairwiseAccuracy": baseline_pairwise,
            "modelPairwiseAccuracy": model_pairwise,
            "onnxParityMaxAbsError": onnx_parity_error,
        },
        cohort_checksum_sha256=_checksum(cohort.get("manifestChecksumSha256")),
    )
    return snapshot, report


def shadow_rank(
    snapshot: RepresentativeRankerSnapshot,
    features: Sequence[Sequence[float]],
    *,
    model_path: Path,
) -> tuple[int, ...]:
    """Return a rank order without changing selector decisions or boundaries."""

    if len(features) <= 1:
        return tuple(range(len(features)))
    if sha256_file(model_path) != snapshot.model_checksum_sha256:
        raise ValueError("Representative ranker model checksum mismatch.")
    import onnxruntime as ort

    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    values = np.asarray(features, dtype=np.float32)
    normalized = (values - np.asarray(snapshot.standardization_mean)) / np.asarray(
        snapshot.standardization_scale
    )
    normalized = normalized.astype(np.float32)
    scores = session.run(["score"], {"features": normalized})[0].reshape(-1)
    return tuple(sorted(range(len(features)), key=lambda index: (-float(scores[index]), index)))


def _onnx_parity_error(
    model: nn.Module,
    model_path: Path,
    normalized_features: np.ndarray,
) -> float:
    import onnxruntime as ort

    with torch.no_grad():
        expected = model(torch.from_numpy(normalized_features)).reshape(-1).numpy()
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    actual = session.run(["score"], {"features": normalized_features})[0].reshape(-1)
    if expected.shape != actual.shape:
        raise ValueError("PyTorch and ONNX ranker outputs have different shapes.")
    return float(np.max(np.abs(expected - actual)))


def shadow_recommendations(
    snapshot: RepresentativeRankerSnapshot,
    groups: Sequence[SelectionGroupResult],
    *,
    model_path: Path,
) -> dict[str, object]:
    """Create audit-only ranking metadata for already formed selector groups."""

    import onnxruntime as ort

    if sha256_file(model_path) != snapshot.model_checksum_sha256:
        raise ValueError("Representative ranker model checksum mismatch.")
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    rows: list[dict[str, object]] = []
    agreements = 0
    considered = 0
    for group in groups:
        candidates = list(group.top_candidates)
        if group.selected_candidate is not None and all(
            item.source.checksum_sha256 != group.selected_candidate.source.checksum_sha256
            for item in candidates
        ):
            candidates.append(group.selected_candidate)
        if not candidates:
            continue
        minimum = min(item.source.order_index for item in candidates)
        maximum = max(item.source.order_index for item in candidates)
        values = [
            quality_features(
                item.quality,
                float(
                    max(0, item.source.order_index - minimum)
                    / max(1, maximum - minimum)
                ),
            )
            for item in candidates
        ]
        normalized = (np.asarray(values, dtype=np.float32) - np.asarray(
            snapshot.standardization_mean
        )) / np.asarray(snapshot.standardization_scale)
        normalized = normalized.astype(np.float32)
        scores = session.run(["score"], {"features": normalized})[0].reshape(-1)
        order = tuple(
            sorted(range(len(values)), key=lambda index: (-float(scores[index]), index))
        )
        heuristic = (
            group.selected_candidate.source.checksum_sha256
            if group.selected_candidate is not None
            else candidates[0].source.checksum_sha256
        )
        recommendation = candidates[order[0]].source.checksum_sha256
        considered += 1
        agreements += int(heuristic == recommendation)
        rows.append(
            {
                "groupOrder": group.group_order,
                "heuristicSelectedChecksumSha256": heuristic,
                "modelRecommendedChecksumSha256": recommendation,
                "modelOrder": [candidates[index].source.checksum_sha256 for index in order],
            }
        )
    return {
        "agreementCount": agreements,
        "consideredGroupCount": considered,
        "modelChecksumSha256": snapshot.model_checksum_sha256,
        "modelVersion": snapshot.model_version,
        "mode": "shadow",
        "recommendations": rows,
    }


def promotion_gate(
    preview: RankingCohortPreview,
    report: Mapping[str, object],
) -> dict[str, object]:
    improvement = _number(report.get("modelPairwiseAccuracy")) - _number(
        report.get("baselinePairwiseAccuracy")
    )
    eligible = (
        preview.group_count >= MINIMUM_PROMOTION_GROUPS
        and preview.reliable_pair_count >= MINIMUM_PROMOTION_PAIRS
        and preview.folder_count >= 2
        and improvement >= 0.05
    )
    return {
        "eligible": eligible,
        "improvement": improvement,
        "minimumFolders": 2,
        "minimumGroups": MINIMUM_PROMOTION_GROUPS,
        "minimumPairs": MINIMUM_PROMOTION_PAIRS,
        "status": "candidate" if eligible else "shadow",
    }


def _feature_row(
    *,
    group_key: str,
    folder_key: str,
    path: str,
    checksum: str,
    metrics: ImageQualityMetrics,
    relative_position: float,
    label: str,
    range_start: int,
    range_end: int,
) -> dict[str, object]:
    return {
        "checksumSha256": checksum,
        "features": quality_features(metrics, relative_position).tolist(),
        "folderKey": folder_key,
        "groupKey": group_key,
        "label": label,
        "rangeEnd": range_end,
        "rangeStart": range_start,
        "relativePosition": relative_position,
        "sourceRelativePath": path,
    }


def _measure_quality(path: Path) -> ImageQualityMetrics:
    with Image.open(path) as source:
        source.load()
        rgb = np.asarray(ImageOps.exif_transpose(source).convert("RGB"), dtype=np.uint8)
    height, width = rgb.shape[:2]
    region = rgb[int(height * 0.16) : int(height * 0.82), int(width * 0.08) : int(width * 0.92)]
    if region.size == 0:
        region = rgb
    gray = cv2.cvtColor(region, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    laplacian = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    sharpness = laplacian / (laplacian + 420.0)
    exposure = max(0.0, 1.0 - abs(float(np.mean(gray)) - 127.5) / 127.5)
    clipped = float(np.mean((gray <= 4) | (gray >= 251)))
    highlight = max(0.0, 1.0 - clipped * 2.5)
    glare = float(np.mean((hsv[:, :, 2] >= 242) & (hsv[:, :, 1] <= 45)))
    glare_resistance = max(0.0, 1.0 - glare * 6.0)
    edges = np.abs(cv2.Laplacian(gray, cv2.CV_32F))
    contrast = float(np.std(gray))
    mean_edges = float(np.mean(edges))
    visibility = max(
        0.0,
        min(
            1.0,
            0.55 * contrast / (contrast + 30.0)
            + 0.45 * mean_edges / (mean_edges + 18.0),
        ),
    )
    border_margin = max(0.0, min(1.0, 1.0 - mean_edges / (mean_edges + 24.0)))
    values = (
        sharpness,
        exposure,
        highlight,
        glare_resistance,
        visibility,
        border_margin,
        visibility,
    )
    return ImageQualityMetrics(
        *tuple(round(max(0.0, min(1.0, value)), 6) for value in values),
        round(max(0.0, min(1.0, float(np.mean(values)))), 6),
    )


def _appearance_descriptor(path: Path) -> np.ndarray:
    with Image.open(path) as source:
        source.load()
        resized = ImageOps.exif_transpose(source).convert("L").resize((16, 16))
        rgb = np.asarray(resized, dtype=np.float32)
    return cast(np.ndarray, rgb / 255.0)


def _relative_position(path: str, events: Sequence[Mapping[str, object]]) -> float:
    indexes = [
        _int_value(value.get("sourceIndex"))
        for value in events
        if isinstance(value.get("sourceIndex"), int)
    ]
    if len(indexes) < 2:
        return 0.5
    current = next(
        (
            _int_value(value.get("sourceIndex"))
            for value in events
            if value.get("imagePath") == path
        ),
        indexes[len(indexes) // 2],
    )
    return float(max(0.0, min(1.0, (current - min(indexes)) / max(1, max(indexes) - min(indexes)))))


def _resolve_source(path_text: str, roots: Sequence[Path]) -> Path | None:
    relative = PurePosixPath(path_text)
    if relative.is_absolute() or ".." in relative.parts or "\\" in path_text:
        return None
    for root in roots:
        candidate = (root.resolve() / Path(*relative.parts)).resolve()
        if candidate.is_relative_to(root.resolve()) and candidate.is_file():
            return candidate
    return None


def _folder_key(path_text: str) -> str:
    path = PurePosixPath(path_text)
    return path.parts[0] if len(path.parts) > 1 else "."


def _group_key(value: Mapping[str, object], trace: Mapping[str, object]) -> str:
    session = str(value.get("sessionKey", trace.get("sessionKey", "")))
    return f"{session}:{_int_value(value.get('rangeStart'))}-{_int_value(value.get('rangeEnd'))}"


def _feature_vector(sample: Mapping[str, object]) -> np.ndarray:
    values = sample.get("features")
    if not isinstance(values, Sequence) or len(values) != RANKER_INPUT_SIZE:
        raise ValueError("Ranking sample has invalid feature vector.")
    return cast(
        np.ndarray,
        np.asarray([_float_value(value) for value in values], dtype=np.float32),
    )


def _split_pairs(
    pairs: Sequence[tuple[int, int]],
    samples: Sequence[Mapping[str, object]],
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    train: list[tuple[int, int]] = []
    test: list[tuple[int, int]] = []
    for pair in pairs:
        key = str(samples[pair[0]].get("groupKey", ""))
        bucket = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % 5
        (test if bucket == 0 else train).append(pair)
    return train, test


def _pairwise_accuracy(scores: np.ndarray, pairs: Sequence[tuple[int, int]]) -> float:
    if not pairs:
        return 0.0
    return float(np.mean([scores[positive] > scores[negative] for positive, negative in pairs]))


def _baseline_score(sample: Mapping[str, object]) -> float:
    values = _feature_vector(sample)
    return float(np.mean(values[:7]))


def _require_manifest(value: Mapping[str, object], kind: str) -> None:
    if value.get("schemaVersion") != 1 or (
        kind != RANKER_COHORT_KIND and value.get("kind") not in {None, kind}
    ):
        raise ValueError(f"Invalid {kind} manifest.")


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError("Expected object in ranker manifest.")
    return cast(Mapping[str, object], value)


def _sequence(value: object) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise ValueError("Expected array in ranker manifest.")
    return value


def _text(value: Mapping[str, object], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str) or not item:
        raise ValueError(f"Missing {key} in ranker manifest.")
    return item


def _checksum(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        char not in "0123456789abcdef" for char in value
    ):
        raise ValueError("Invalid ranker checksum.")
    return value


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0.0
    return float(value)


def _float_value(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError("Expected a finite numeric ranker value.")
    return float(value)


def _int_value(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("Expected an integer ranker value.")
    return value


def _canonical_json(value: Mapping[str, object]) -> bytes:
    text = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return f"{text}\n".encode()


def _canonical_checksum(value: Mapping[str, object]) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


__all__ = [
    "RANKER_COHORT_KIND",
    "RANKER_FEATURE_NAMES",
    "RANKER_FEATURE_VERSION",
    "RANKER_MODEL_VERSION",
    "RankingCohortPreview",
    "RepresentativeRankerSnapshot",
    "build_ranking_cohort",
    "promotion_gate",
    "quality_features",
    "shadow_rank",
    "shadow_recommendations",
    "train_ranker",
    "write_ranking_cohort",
]
