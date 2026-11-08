"""Explicit human content supervision; geometry points never imply cell visibility."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .grid_training_cohorts import digest

VISIBILITY_CONTRACT: Final = "grid-visibility-supervision-v1"
OUTPUT_CONTRACT: Final = "grid-output-peak24-visibility15-v2"
Sha = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Point = tuple[
    Annotated[float, Field(allow_inf_nan=False)], Annotated[float, Field(allow_inf_nan=False)]
]


class VisibilityClosed(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class CellContentReference(VisibilityClosed):
    state: Literal["visible", "occluded", "out_of_frame", "unknown"]
    quad: tuple[Point, Point, Point, Point] | None = None

    @model_validator(mode="after")
    def visible_content(self) -> CellContentReference:
        if self.state == "visible" and self.quad is None:
            raise ValueError("VISIBILITY_VISIBLE_CONTENT_REQUIRED")
        if self.quad is not None:
            cross = []
            for i in range(4):
                a, b, c = self.quad[i], self.quad[(i + 1) % 4], self.quad[(i + 2) % 4]
                cross.append((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]))
            if not (all(x > 0 for x in cross) or all(x < 0 for x in cross)):
                raise ValueError("VISIBILITY_CONTENT_QUAD_INVALID")
        return self


class BoardContentReference(VisibilityClosed):
    gameId: UUID
    sourceRepresentativeSha256: Sha
    positionIndex: Annotated[int, Field(strict=True, ge=0, le=8)]
    revision: Annotated[int, Field(strict=True, ge=1)]
    humanApproved: bool
    cells: Annotated[tuple[CellContentReference, ...], Field(min_length=15, max_length=15)]


class VisibilityClassCounts(VisibilityClosed):
    positiveCells: Annotated[int, Field(ge=0)]
    negativeCells: Annotated[int, Field(ge=0)]
    positivePhotos: Annotated[int, Field(ge=0)]
    negativePhotos: Annotated[int, Field(ge=0)]

    @property
    def qualified(self) -> bool:
        return (
            self.positiveCells >= 30
            and self.negativeCells >= 30
            and self.positivePhotos >= 5
            and self.negativePhotos >= 5
        )


class VisibilitySupervision(VisibilityClassCounts):
    version: Literal["grid-visibility-supervision-v1"] = VISIBILITY_CONTRACT
    referencesSha256: Sha
    games: dict[str, VisibilityClassCounts]

    @property
    def qualified(self) -> bool:
        return bool(self.games) and all(value.qualified for value in self.games.values())


def visibility_supervision(
    references: Sequence[BoardContentReference], *, game_ids: Sequence[str] = ()
) -> VisibilitySupervision:
    """Only real TRAIN labels, supplied by the guarded reader, before augmentation."""
    unique: dict[tuple[str, int], BoardContentReference] = {}
    for item in references:
        key = item.sourceRepresentativeSha256, item.positionIndex
        previous = unique.get(key)
        if previous is not None and previous != item:
            raise ValueError("VISIBILITY_REFERENCE_ALIAS_CONFLICT")
        unique[key] = item
    positive, negative = 0, 0
    positive_photos: set[str] = set()
    negative_photos: set[str] = set()
    games = {}
    for game in sorted(set(game_ids) | {str(item.gameId) for item in references}):
        members = [
            item for item in unique.values() if str(item.gameId) == game and item.humanApproved
        ]
        positives = [item for item in members for cell in item.cells if cell.state == "visible"]
        negatives = [
            item
            for item in members
            for cell in item.cells
            if cell.state in ("occluded", "out_of_frame")
        ]
        games[game] = VisibilityClassCounts(
            positiveCells=len(positives),
            negativeCells=len(negatives),
            positivePhotos=len({item.sourceRepresentativeSha256 for item in positives}),
            negativePhotos=len({item.sourceRepresentativeSha256 for item in negatives}),
        )
    for item in unique.values():
        if not item.humanApproved:
            continue
        for cell in item.cells:
            if cell.state == "visible":
                positive += 1
                positive_photos.add(item.sourceRepresentativeSha256)
            elif cell.state in ("occluded", "out_of_frame"):
                negative += 1
                negative_photos.add(item.sourceRepresentativeSha256)
    return VisibilitySupervision(
        positiveCells=positive,
        negativeCells=negative,
        positivePhotos=len(positive_photos),
        negativePhotos=len(negative_photos),
        referencesSha256=digest([unique[key].model_dump(mode="json") for key in sorted(unique)]),
        games=games,
    )


class GridOutputContract(VisibilityClosed):
    version: Literal["grid-output-peak24-visibility15-v2"] = OUTPUT_CONTRACT
    lossVersion: Literal["grid-node24-cell15-masked-v2"] = "grid-node24-cell15-masked-v2"
    nodeCount: Literal[24] = 24
    visibilityCount: Literal[15] = 15
    supervision: VisibilitySupervision
    trainedVisibility: bool = False

    @model_validator(mode="after")
    def trained(self) -> GridOutputContract:
        if self.trainedVisibility and not self.supervision.qualified:
            raise ValueError("VISIBILITY_TRAINING_EVIDENCE_REQUIRED")
        return self


def require_output_contract(
    bundle: Mapping[str, Any],
    expected: Mapping[str, Any] | None = None,
    *,
    require_expected: bool = False,
) -> GridOutputContract | None:
    """Verify the stored selected-checkpoint exposure, never infer training from output shape."""
    if bundle.get("format") != "neural-grid-bundle-v2":
        if (
            expected is not None
            or "gridOutputContract" in bundle
            or bundle.get("format") not in (None, "neural-grid-bundle-v1")
        ):
            raise ValueError("GRID_OUTPUT_BUNDLE_VERSION_INVALID")
        return None
    if require_expected and expected is None:
        raise ValueError("GRID_VISIBILITY_INPUT_CONTRACT_REQUIRED")
    contract = GridOutputContract.model_validate(bundle["gridOutputContract"])
    if bundle.get("model_version") != "neural-grid-v2":
        raise ValueError("GRID_OUTPUT_BUNDLE_VERSION_INVALID")
    provenance = bundle.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("GRID_VISIBILITY_EXPORT_EVIDENCE_INVALID")
    exposure = provenance.get("visibilityExposure")
    keys = {"positiveTargets", "negativeTargets", "optimizerSteps"}
    if (
        not isinstance(exposure, dict)
        or set(exposure) != keys
        or any(type(exposure[key]) is not int or exposure[key] < 0 for key in keys)
        or type(provenance.get("bestStep")) is not int
        or not 0 <= exposure["optimizerSteps"] <= provenance["bestStep"]
        or (exposure["optimizerSteps"] == 0)
        != (exposure["positiveTargets"] + exposure["negativeTargets"] == 0)
    ):
        raise ValueError("GRID_VISIBILITY_EXPORT_EVIDENCE_INVALID")
    trained = all(exposure[key] > 0 for key in keys)
    if contract.trainedVisibility != trained:
        raise ValueError("GRID_VISIBILITY_EXPORT_EVIDENCE_INVALID")
    if expected is not None:
        incoming = GridOutputContract.model_validate(expected)
        if (
            incoming.trainedVisibility
            or contract.model_copy(update={"trainedVisibility": False}) != incoming
        ):
            raise ValueError("GRID_VISIBILITY_INPUT_EXPORT_MISMATCH")
    return contract
