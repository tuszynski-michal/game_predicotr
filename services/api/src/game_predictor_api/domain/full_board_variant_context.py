"""Closed identity of an actual final content-experiment input, not an attempt."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .grid_model_registry import descriptor_sha256 as digest

Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Point = tuple[float, float]


class ClosedVariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class VariantContext(ClosedVariant):
    version: Literal["full-board-final-variant-v1"] = "full-board-final-variant-v1"
    candidateManifestSha256: Sha
    routingSha256: Sha
    selectedPath: Literal["combined"] | None
    stage: Literal["baseline", "wide"]
    screenPreset: dict[str, Any]
    screenGeometry: dict[str, Any] | None
    boardPreset: dict[str, Any]
    boardGeometry: dict[str, Any] | None
    preprocessingContract: Literal["neural-grid-content-preprocessing-v1"] = (
        "neural-grid-content-preprocessing-v1"
    )
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> VariantContext:
        if (
            self.screenPreset.get("long_side") != 768
            or self.screenPreset.get("train_canvas") != [768, 576]
            or self.boardPreset.get("canvas") != [320, 192]
            or self.boardPreset.get("margin") != 0.15
        ):
            raise ValueError("VARIANT_BASE_CONTEXT_INVALID")
        if self.stage == "baseline":
            if self.screenGeometry is not None or self.boardGeometry is not None:
                raise ValueError("VARIANT_BASE_CONTEXT_INVALID")
        elif (
            self.selectedPath != "combined"
            or self.screenGeometry != {"longSide": 1280, "trainCanvas": [1280, 960]}
            or self.boardGeometry != {"margin": 0.30, "canvas": [480, 288]}
        ):
            raise ValueError("VARIANT_WIDE_CONTEXT_INVALID")
        if self.sha256 != digest(self.model_dump(mode="json", exclude={"sha256"})):
            raise ValueError("VARIANT_CONTEXT_CHECKSUM")
        return self


class FinalDetection(ClosedVariant):
    nodes: Annotated[list[Point], Field(min_length=24, max_length=24)]
    screenQuad: Annotated[list[Point], Field(min_length=4, max_length=4)]


class PairedWitness(ClosedVariant):
    version: Literal["full-board-final-variant-witness-v1"] = "full-board-final-variant-witness-v1"
    sourceId: UUID
    sourceRepresentativeSha256: Sha
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    variantKey: Sha
    finalDetection: FinalDetection
    detectionNodesSha256: Sha
    origin: Literal["baseline", "replacement"]
    inputContentEvidence: dict[str, Any]
    sha256: Sha

    @model_validator(mode="after")
    def integrity(self) -> PairedWitness:
        proof = self.inputContentEvidence
        if (
            self.detectionNodesSha256
            != digest(self.finalDetection.model_dump(mode="json")["nodes"])
            or proof.get("sourceId") != str(self.sourceId)
            or proof.get("positionIndex") != self.positionIndex
            or proof.get("sourceRepresentativeSha256") != self.sourceRepresentativeSha256
            or proof.get("screenQuad") != self.finalDetection.model_dump(mode="json")["screenQuad"]
            or proof.get("sha256") != digest({k: v for k, v in proof.items() if k != "sha256"})
            or self.sha256 != digest(self.model_dump(mode="json", exclude={"sha256"}))
        ):
            raise ValueError("VARIANT_WITNESS_IDENTITY_INVALID")
        return self


def make_variant_context(**payload: Any) -> dict[str, Any]:
    body = {
        "version": "full-board-final-variant-v1",
        "preprocessingContract": "neural-grid-content-preprocessing-v1",
        **payload,
    }
    return require_variant_context({**body, "sha256": digest(body)})


def require_variant_context(value: object) -> dict[str, Any]:
    return VariantContext.model_validate(value).model_dump(mode="json")


def require_variant_witness(value: object, context: Mapping[str, Any]) -> dict[str, Any]:
    ctx = VariantContext.model_validate(context)
    witness = PairedWitness.model_validate(value)
    proof = witness.inputContentEvidence
    if (
        witness.variantKey != ctx.sha256
        or witness.origin != ("baseline" if ctx.stage == "baseline" else "replacement")
        or proof.get("boardPreset") != ctx.boardPreset
        or proof.get("geometry") != ctx.boardGeometry
        or proof.get("path") != ctx.selectedPath
        or digest(
            {
                "recognitionManifestSha256": ctx.candidateManifestSha256,
                "boardPreset": proof.get("boardPreset"),
                "routing": proof.get("routing"),
                "selectedPath": proof.get("path"),
            }
        )
        != ctx.routingSha256
    ):
        raise ValueError("VARIANT_WITNESS_CONTEXT_CHANGED")
    return witness.model_dump(mode="json")
