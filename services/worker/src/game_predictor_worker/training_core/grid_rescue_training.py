"""Versioned recipe and selection identity shared by admission and the child."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from ..geometry_core.rescue import GridRescueVariantV1
from .grid_training_admission import digest


def selection_input(parts: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    games = []
    for game_id, split in sorted(parts):
        if split.get("schemaVersion") != "grid-correction-split-v3":
            raise ValueError("SCREEN_SELECTION_POLICY_REQUIRED")
        sources = [
            {
                "sourceId": item["sourceId"],
                "sourceSha256": item["sourceSha256"],
                "pixelSha256": item["pixelSha256"],
                "labelsSha256": item["qualifiedLabelsSha256"],
            }
            for item in split["sources"]
            if item["role"] == "VALIDATION"
            and item["representative"]
            and item["eligibleBoards"] == 9
        ]
        if len(sources) < 5:
            raise ValueError("SCREEN_FULL_VALIDATION_REQUIRED")
        games.append(
            {
                "gameId": game_id,
                "splitSha256": split["sha256"],
                "sources": sorted(sources, key=lambda value: value["sourceId"]),
            }
        )
    if not games or len({game["gameId"] for game in games}) != len(games):
        raise ValueError("SCREEN_SELECTION_SCOPE_INVALID")
    value = {
        "contractVersion": "grid-checkpoint-input-v1",
        "policy": "all-validation-v1",
        "role": "VALIDATION",
        "purpose": "checkpoint-selection",
        "selectionExposed": True,
        "games": games,
    }
    return {**value, "sha256": digest(value)}


def rescue_recipe(baseline_sha: str, variant: Any, selection: Mapping[str, Any]) -> dict[str, Any]:
    parsed = None if variant is None else GridRescueVariantV1.model_validate(variant)
    value = {
        "contractVersion": "grid-rescue-recipe-v1",
        "baselinePresetSha256": baseline_sha,
        "variant": None if parsed is None else parsed.model_dump(mode="json"),
        "variantId": None if parsed is None else parsed.sha256,
        "schedule": "baseline-variant-alternate-v1",
        "selectionInputSha256": selection["sha256"],
    }
    return {**value, "sha256": digest(value)}


def require_recipe(
    value: Mapping[str, Any], baseline_sha: str, selection: Mapping[str, Any]
) -> GridRescueVariantV1 | None:
    expected = rescue_recipe(baseline_sha, value.get("variant"), selection)
    if dict(value) != expected:
        raise ValueError("GRID_RESCUE_RECIPE_MISMATCH")
    return (
        None if value["variant"] is None else GridRescueVariantV1.model_validate(value["variant"])
    )


def variant_step(step: int) -> bool:
    if type(step) is not int or step < 0:
        raise ValueError("Invalid optimizer step.")
    return step % 2 == 1


class TrainingExposure:
    """Only the trainer calls confirm after an actual, non-skipped optimizer step."""

    def __init__(self, recipe: Mapping[str, Any]) -> None:
        self.recipe = dict(recipe)
        self.value: dict[str, Any] = {
            "contractVersion": "stage-composed-train-v1",
            "architecture": "neural-grid-independent-screen-board-v1",
            "recipeSha256": recipe["sha256"],
            "lastStep": 0,
            "confirmedSteps": 0,
            "chainSha256": digest({"recipe": recipe["sha256"]}),
            "games": {},
        }

    def confirm(self, step: int, members: Sequence[Mapping[str, str]]) -> None:
        if type(step) is not int or step <= self.value["lastStep"] or not members:
            raise ValueError("GRID_RESCUE_EXPOSURE_INVALID")
        variant = self.recipe["variant"]
        active = variant is not None and variant_step(step - 1)
        stage_names = [
            f"{stage}:{'variant' if active and variant.get(stage) else 'baseline'}"
            for stage in ("screen", "board")
        ]
        for member in members:
            if set(member) != {"gameId", "sourceId", "sourceSha256", "cohortSha256"}:
                raise ValueError("GRID_RESCUE_EXPOSURE_MEMBER_INVALID")
            game = self.value["games"].setdefault(member["gameId"], {})
            for stage in stage_names:
                entry = game.setdefault(stage, {"confirmedItems": 0, "maxStep": 0, "sources": {}})
                entry["confirmedItems"] += 1
                entry["maxStep"] = step
                source = dict(member)
                key = digest(source)
                entry["sources"][key] = source
        self.value["chainSha256"] = digest(
            {
                "prior": self.value["chainSha256"],
                "step": step,
                "members": list(members),
                "stages": stage_names,
            }
        )
        self.value["lastStep"] = step
        self.value["confirmedSteps"] += 1

    def state(self) -> dict[str, Any]:
        value = copy.deepcopy(self.value)
        return {**value, "sha256": digest(value)}

    def restore(self, value: Mapping[str, Any], step: int) -> None:
        body = {key: item for key, item in value.items() if key != "sha256"}
        if (
            value.get("sha256") != digest(body)
            or set(body) != set(self.value)
            or body["contractVersion"] != self.value["contractVersion"]
            or body["architecture"] != self.value["architecture"]
            or body["recipeSha256"] != self.recipe["sha256"]
            or type(body["lastStep"]) is not int
            or not 0 <= body["lastStep"] <= step
            or type(body["confirmedSteps"]) is not int
            or not 0 <= body["confirmedSteps"] <= body["lastStep"]
        ):
            raise ValueError("GRID_RESCUE_EXPOSURE_MISMATCH")
        self.value = copy.deepcopy(body)
