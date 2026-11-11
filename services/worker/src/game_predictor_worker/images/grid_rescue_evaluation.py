"""Original-photo selection of a single recipe's actual bounded runtime paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any, cast

import numpy as np
import torch

from ..geometry_core.inference import BoardDetection, DecodeSettings, NeuralGridEngine
from ..geometry_core.rescue import GridRescueVariantV1
from ..training_core.evaluation_precision import evaluation_precision
from ..training_core.grid_correction_metrics import (
    aggregate_checkpoint_metrics,
    checkpoint_metrics,
    evaluate_photo,
    photo_selection_key,
)
from ..training_core.grid_evaluation import predictions
from ..training_core.grid_rescue_training import TrainingExposure
from ..training_core.grid_training_admission import digest
from ..training_core.neural_grid_network import BoardExport, ScreenExport
from .grid_rescue_strategy import ROUTING_POLICY, completeness_routing, execute_path

PATH_COMPONENTS = {
    "screen_only": ("screen:variant", "board:baseline"),
    "board_only": ("screen:baseline", "board:variant"),
    "combined": ("screen:variant", "board:variant"),
}


def _detect(engine: NeuralGridEngine, rgb: Any, geometry: Any) -> list[BoardDetection]:
    return engine.detect(rgb, geometry=geometry)


def _recrop(
    engine: NeuralGridEngine, rgb: Any, position: int, detection: BoardDetection, geometry: Any
) -> BoardDetection:
    return engine.recrop(rgb, detection, geometry=geometry)


def torch_engine(network: Any, recipe: Any, device: str) -> NeuralGridEngine:
    screen_graph, board_graph = (
        ScreenExport(network.screen).eval(),
        BoardExport(network.board).eval(),
    )

    def screen(pixels: np.ndarray) -> Any:
        with evaluation_precision():
            return tuple(
                value.float().cpu().numpy()
                for value in screen_graph(torch.from_numpy(pixels).to(device))
            )

    def board(pixels: np.ndarray) -> Any:
        with evaluation_precision():
            return tuple(
                value.float().cpu().numpy()
                for value in board_graph(torch.from_numpy(pixels).to(device))
            )

    return NeuralGridEngine(screen, board, DecodeSettings.of(recipe))


def has_exposure(
    exposure: Mapping[str, Any], path: str, games: Sequence[str], best_step: int
) -> bool:
    if (
        exposure.get("contractVersion") != "stage-composed-train-v1"
        or exposure.get("architecture") != "neural-grid-independent-screen-board-v1"
    ):
        return False
    if exposure.get("sha256") != digest({k: v for k, v in exposure.items() if k != "sha256"}):
        return False
    for game in games:
        for stage in PATH_COMPONENTS[path]:
            value = exposure.get("games", {}).get(game, {}).get(stage, {})
            if (
                not value.get("sources")
                or value.get("confirmedItems", 0) < 1
                or not 1 <= value.get("maxStep", 0) <= best_step
            ):
                return False
    return True


class ScreenCorrectionEvaluator:
    def __init__(
        self,
        parts: Sequence[Any],
        recipe: Any,
        device: str,
        variant: GridRescueVariantV1 | None,
        selection: Mapping[str, Any],
        exposure: TrainingExposure,
    ) -> None:
        self.parts, self.recipe, self.device = list(parts), recipe, device
        self.variant, self.selection, self.exposure = variant, dict(selection), exposure
        self.routing = (
            completeness_routing(selection, DecodeSettings.of(recipe).board)
            if selection.get("policy") == "validation-purpose-a-v1"
            else None
        )
        expected = {item["gameId"]: item["sources"] for item in selection["games"]}
        actual = {}
        for part in parts:
            if part.role != "VALIDATION":
                raise ValueError("GRID_TRAINING_VALIDATION_ONLY")
            sources = []
            for source, targets in part.rows:
                if len(targets) != 9 or source.get("screenEligible") is not True:
                    raise ValueError("GRID_TRAINING_FULL_DATA_DRIFT")
                sources.append(
                    {
                        "sourceId": source["sourceId"],
                        "sourceSha256": source["sourceIdentity"]["checksum_sha256"],
                        "pixelSha256": source["sourceIdentity"]["normalized_pixel_checksum_sha256"],
                        "labelsSha256": digest(source["targets"]),
                    }
                )
            actual[str(part.snapshot.manifest["gameId"])] = sorted(
                sources, key=lambda item: item["sourceId"]
            )
        if expected != actual or len(actual) != len(parts):
            raise ValueError("GRID_TRAINING_SELECTION_INPUT_DRIFT")

    def __call__(self, network: Any) -> dict[str, float]:
        result = self.measure(
            torch_engine(network, self.recipe, self.device), self.exposure.state()
        )
        return cast(dict[str, float], result["metrics"])

    def measure(
        self, engine: NeuralGridEngine, exposure: Mapping[str, Any], *, parity: Any = None
    ) -> dict[str, Any]:
        paths = () if self.variant is None else self.variant.paths
        baseline: dict[str, Any] = {}
        proof: dict[str, Any] = {
            path: {
                "games": {},
                "redetectCalls": 0,
                "cropCalls": 0,
                "invocations": [],
                "routingPolicy": ROUTING_POLICY
                if self.routing is None
                else self.routing["version"],
                **({"routing": self.routing} if self.routing is not None else {}),
            }
            for path in paths
        }
        for part in self.parts:
            game = str(part.snapshot.manifest["gameId"])
            base_photos = []
            path_photos: dict[str, list[Any]] = {path: [] for path in paths}
            for index, (source, _) in enumerate(part.rows):
                rgb = part.rgb(index)
                labels = [label for label, _ in part.targets(index)]
                if parity is not None:
                    parity.path = "baseline"
                found = engine.analyse(rgb)
                base_photos.append(
                    evaluate_photo(
                        source["sourceId"],
                        source["sourceId"],
                        labels,
                        predictions(found),
                        full_geometry=True,
                    )
                )
                for path in paths:
                    if parity is not None:
                        parity.path = path
                    assert self.variant is not None
                    result = execute_path(
                        found,
                        width=rgb.shape[1],
                        height=rgb.shape[0],
                        variant=self.variant,
                        path=path,
                        expected_positions=set(range(9)),
                        routing=self.routing,
                        detect=partial(_detect, engine, rgb),
                        recrop=partial(_recrop, engine, rgb),
                    )
                    proof[path]["redetectCalls"] += result.redetect_calls
                    proof[path]["cropCalls"] += sum(result.crop_calls.values())
                    proof[path]["invocations"].append(
                        {
                            "gameId": game,
                            "sourceId": source["sourceId"],
                            "redetect": result.redetect_calls,
                            "cropPositions": sorted(result.crop_calls),
                            "reasons": list(result.reasons),
                        }
                    )
                    path_photos[path].append(
                        evaluate_photo(
                            source["sourceId"],
                            source["sourceId"],
                            labels,
                            predictions(result.detections),
                            full_geometry=True,
                        )
                    )
            baseline[game] = checkpoint_metrics(base_photos, photo_first=True)
            for path in paths:
                proof[path]["games"][game] = checkpoint_metrics(path_photos[path], photo_first=True)
        base_metrics = aggregate_checkpoint_metrics(list(baseline.values()), photo_first=True)
        selected = None
        selected_metrics = base_metrics
        for path in sorted(paths):
            item = proof[path]
            games = item["games"]
            exposed = has_exposure(exposure, path, sorted(baseline), int(exposure["lastStep"]))
            exercised = item["cropCalls"] > 0 and (
                path == "board_only" or item["redetectCalls"] > 0
            )
            nonregression = all(
                photo_selection_key(games[game], 0) >= photo_selection_key(baseline[game], 0)
                for game in baseline
            )
            improved = any(
                photo_selection_key(games[game], 0) > photo_selection_key(baseline[game], 0)
                for game in baseline
            )
            item["admittedOnA"] = exposed and exercised and nonregression and improved
            item["reasonCodes"] = (
                (["GRID_RESCUE_TRAIN_EXPOSURE_REQUIRED"] if not exposed else [])
                + (["GRID_RESCUE_PATH_NOT_EXERCISED"] if not exercised else [])
                + (["GRID_RESCUE_A_NONREGRESSION_REQUIRED"] if not nonregression else [])
                + (["GRID_RESCUE_A_IMPROVEMENT_REQUIRED"] if not improved else [])
            )
            metrics = aggregate_checkpoint_metrics(list(games.values()), photo_first=True)
            if item["admittedOnA"] and photo_selection_key(metrics, 0) > photo_selection_key(
                selected_metrics, 0
            ):
                selected, selected_metrics = path, metrics
        return {
            "contractVersion": "grid-rescue-selection-v1",
            "selectionInputSha256": self.selection["sha256"],
            "baseline": baseline,
            "pathProofs": proof,
            "selectedPath": selected,
            "metrics": selected_metrics,
            "tiePolicy": "baseline-then-lexical-path-v1",
        }
