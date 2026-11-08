"""Versioned recipe and selection identity shared by admission and the child."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any

from ..geometry_core.rescue import GridRescueVariantV1
from .grid_training_admission import digest


class ContentTrainingExposure:
    """Per-component receipts from completed optimizer steps and actual raster sizes."""

    def __init__(self, plan: Mapping[str, Any], arm: str) -> None:
        from .grid_content_experiment import arm_spec, require_plan

        self.plan = require_plan(plan)
        self.spec = arm_spec(plan, arm)
        self.value: dict[str, Any] = {
            "contract": "content-stage-exposure-v1",
            "planSha256": self.plan["sha256"],
            "arm": arm,
            "lastStep": 0,
            "confirmedSteps": 0,
            "chainSha256": digest([]),
            "games": {},
        }

    def confirm_components(
        self,
        step: int,
        *,
        screen_members: Sequence[Mapping[str, str]],
        board_members: Sequence[Mapping[str, str]],
        screen_canvas: tuple[int, int] | None,
        board_canvas: tuple[int, int] | None,
    ) -> None:
        if type(step) is not int or not self.value["lastStep"] < step <= 1200:
            raise ValueError("CONTENT_EXPOSURE_STEP_INVALID")
        variant = self.spec["multiscale"] and (step - 1) % 2 == 1
        expected = {
            "screen": (1280, 960) if variant else (768, 576),
            "board": (480, 288) if variant else (320, 192),
        }
        receipt: dict[str, Any] = {}
        updated = copy.deepcopy(self.value)
        for stage, members, canvas in (
            ("screen", screen_members, screen_canvas),
            ("board", board_members, board_canvas),
        ):
            if not members:
                continue
            if canvas != expected[stage]:
                raise ValueError("CONTENT_EXPOSURE_RASTER_INVALID")
            mode = "variant" if variant else "baseline"
            for member in members:
                if set(member) != {"gameId", "sourceId", "sourceSha256", "cohortSha256"} or member[
                    "gameId"
                ] not in {c["gameId"] for c in self.plan["cohorts"]}:
                    raise ValueError("CONTENT_EXPOSURE_MEMBER_INVALID")
                from .grid_content_experiment import _sha

                _sha(member["sourceSha256"])
                _sha(member["cohortSha256"])
                if not member["sourceId"] or member["cohortSha256"] != next(
                    c["manifestSha256"]
                    for c in self.plan["cohorts"]
                    if c["gameId"] == member["gameId"]
                ):
                    raise ValueError("CONTENT_EXPOSURE_MEMBER_INVALID")
                game = updated["games"].setdefault(member["gameId"], {})
                key = stage + ":" + mode
                item = game.setdefault(
                    key, {"canvas": list(canvas), "confirmedItems": 0, "maxStep": 0, "sources": {}}
                )
                item["confirmedItems"] += 1
                item["maxStep"] = step
                item["sources"][digest(dict(member))] = dict(member)
            receipt[stage] = {"canvas": list(canvas), "members": [dict(m) for m in members]}
        if not receipt:
            raise ValueError("CONTENT_EXPOSURE_EMPTY")
        updated["chainSha256"] = digest(
            {"previous": self.value["chainSha256"], "step": step, "components": receipt}
        )
        updated["lastStep"] = step
        updated["confirmedSteps"] += 1
        self.value = updated

    def state(self) -> dict[str, Any]:
        value = copy.deepcopy(self.value)
        return {**value, "sha256": digest(value)}

    def restore(self, value: Mapping[str, Any], step: int) -> None:
        body = {k: copy.deepcopy(v) for k, v in value.items() if k != "sha256"}
        if (
            value.get("sha256") != digest(body)
            or set(body) != set(self.value)
            or body.get("contract") != self.value["contract"]
            or body.get("planSha256") != self.plan["sha256"]
            or body.get("arm") != self.spec["arm"]
            or not 0 <= body["confirmedSteps"] <= body["lastStep"] <= step <= 1200
        ):
            raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
        from .grid_content_experiment import _count, _sha

        _count(body["confirmedSteps"], step)
        _count(body["lastStep"], step)
        _sha(body["chainSha256"])
        cohorts = {c["gameId"]: c["manifestSha256"] for c in self.plan["cohorts"]}
        for game_id, stages in body["games"].items():
            if game_id not in cohorts or not stages:
                raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
            for key, row in stages.items():
                allowed = {"screen:baseline": [768, 576], "board:baseline": [320, 192]}
                if self.spec["multiscale"]:
                    allowed.update({"screen:variant": [1280, 960], "board:variant": [480, 288]})
                if (
                    key not in allowed
                    or set(row) != {"canvas", "confirmedItems", "maxStep", "sources"}
                    or row["canvas"] != allowed[key]
                    or not row["sources"]
                ):
                    raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
                if (
                    _count(row["confirmedItems"]) < len(row["sources"])
                    or not _count(row["maxStep"], body["lastStep"]) >= 1
                ):
                    raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
                for sha, member in row["sources"].items():
                    if (
                        set(member) != {"gameId", "sourceId", "sourceSha256", "cohortSha256"}
                        or digest(member) != sha
                        or member["gameId"] != game_id
                        or member["cohortSha256"] != cohorts[game_id]
                        or not member["sourceId"]
                    ):
                        raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
                    _sha(member["sourceSha256"])
        if bool(body["games"]) != bool(body["confirmedSteps"]):
            raise ValueError("CONTENT_EXPOSURE_STATE_INVALID")
        self.value = body


def selection_input(parts: Sequence[tuple[str, Mapping[str, Any]]]) -> dict[str, Any]:
    games = []
    purpose_aware = bool(parts) and all(
        split.get("schemaVersion") == "grid-correction-split-v4" for _, split in parts
    )
    for game_id, split in sorted(parts):
        if split.get("schemaVersion") != (
            "grid-correction-split-v4" if purpose_aware else "grid-correction-split-v3"
        ):
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
            and (not purpose_aware or item.get("validationPurpose") == "A")
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
        "contractVersion": "grid-checkpoint-input-v2"
        if purpose_aware
        else "grid-checkpoint-input-v1",
        "policy": "validation-purpose-a-v1" if purpose_aware else "all-validation-v1",
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
