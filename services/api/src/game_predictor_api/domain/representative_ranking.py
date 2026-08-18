"""Contracts for the manual representative-quality ranking experiment."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

REPRESENTATIVE_RANKER_MODEL_VERSION = "representative-quality-mlp-v1"
REPRESENTATIVE_RANKER_FEATURE_VERSION = "image-quality-metrics-seven-plus-position-v1"


@dataclass(frozen=True, slots=True)
class ImageSelectionRankingCohortPreview:
    positive_count: int
    reliable_pair_count: int
    excluded_ambiguous_count: int
    folder_count: int
    group_count: int
    manifest_checksum_sha256: str | None = None


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


__all__ = [
    "ImageSelectionRankingCohortPreview",
    "REPRESENTATIVE_RANKER_FEATURE_VERSION",
    "REPRESENTATIVE_RANKER_MODEL_VERSION",
    "RepresentativeRankerSnapshot",
]
