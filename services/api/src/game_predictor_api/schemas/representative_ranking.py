"""OpenAPI value objects for the shadow representative ranker."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from game_predictor_api.schemas.catalog import ApiModel

Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class ImageSelectionRankingCohortPreview(ApiModel):
    positive_count: int = Field(ge=0)
    reliable_pair_count: int = Field(ge=0)
    excluded_ambiguous_count: int = Field(ge=0)
    folder_count: int = Field(ge=0)
    group_count: int = Field(ge=0)
    manifest_checksum_sha256: Sha256 | None = None


class RepresentativeRankerSnapshot(ApiModel):
    feature_version: str
    model_version: str
    model_checksum_sha256: Sha256
    model_relative_path: str
    standardization_mean: list[float] = Field(min_length=8, max_length=8)
    standardization_scale: list[float] = Field(min_length=8, max_length=8)
    status: str
    cohort_checksum_sha256: Sha256
    metrics: dict[str, float]


__all__ = ["ImageSelectionRankingCohortPreview", "RepresentativeRankerSnapshot"]
