"""Paired study material, using CPU grid inference and the production fifteen-cell renderer."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from game_predictor_api.application.grid_model_evaluation import bundle_sha256
from game_predictor_api.domain.canonical_source import CanonicalSourceFrame
from game_predictor_api.domain.grid_model_snapshots import catalogue_model_version
from game_predictor_api.domain.image_geometry_v2 import SourcePoint, SourceQuad
from game_predictor_api.domain.neural_grid_proposal import (
    NeuralGridProposalError,
    associate_partial_slots,
    associate_quad_slots,
    lattice_cell_quads,
)
from game_predictor_api.storage.grid_engine_model_store import ManagedGridEngineModelStore
from game_predictor_worker.geometry_core.preprocessing import (
    board_rectifier,
    crop_board,
    screen_input,
)
from game_predictor_worker.images.grid_rescue_assessment import load_assessment_engine
from game_predictor_worker.images.normalization import CanonicalSourceLoader
from game_predictor_worker.images.production_cell_evaluation import render_cells
from game_predictor_worker.images.virtual_cell_extraction import VirtualCellRender
from PIL import Image, ImageDraw

Document = dict[str, Any]


def sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def engine_for(artifacts: Path, model: Document) -> Any:
    manifest = model["manifest"]
    directory = ManagedGridEngineModelStore(artifacts).require(catalogue_model_version(manifest))
    return load_assessment_engine(directory, bundle_sha256(manifest), 1)


def choose_sources(rows: list[Document], excluded: set[str]) -> list[Document]:
    eligible = []
    for r in sorted(rows, key=lambda r: sha(["mumie-grid-pilot-1", r["sha"], r["id"]])):
        if (
            r.get("excluded")
            or not r.get("pix")
            or not r["start"]
            or not r["end"]
            or not 1 <= r["end"] - r["start"] + 1 <= 9
        ):
            continue
        if excluded.intersection(tokens(r)):
            continue
        eligible.append(r)
    seen_pixels = set()
    seen_positions = set()
    sample = []
    for r in eligible:
        if r["pix"] in seen_pixels:
            continue
        pos = int(sha(["slot", r["sha"]]), 16) % (r["end"] - r["start"] + 1)
        if r["start"] + pos in seen_positions:
            continue
        sample.append({**r, "position": pos})
        seen_pixels.add(r["pix"])
        seen_positions.add(r["start"] + pos)
        if len(sample) == 100:
            break
    if len(sample) != 100:
        raise ValueError(
            f"Tylko {len(sample)} kwalifikowanych zdjęć ze znaną pozycją. Potrzeba 100."
        )
    return sample


def tokens(row: Document) -> set[str]:
    return {row["sha"], row["pix"], *row["groups"], *row["aliases"]}


def infer(
    engine: Any,
    frame: CanonicalSourceFrame,
    row: Document,
    context: Document,
    dest: Path,
    *,
    diagnostic: bool = False,
) -> Document:
    dest.mkdir(parents=True, exist_ok=True)
    found = engine.analyse(frame.rgb)
    if diagnostic:
        inner = getattr(engine, "engine", engine)
        raster, _, _ = screen_input(frame.rgb, inner.settings.screen)
        Image.fromarray(raster).save(dest / "screen-input.png")
        rescue = getattr(engine, "last_result", None)
        if rescue is not None and rescue.redetect_calls:
            raster, _, _ = screen_input(
                frame.rgb, inner.settings.screen, geometry=engine.variant.screen
            )
            Image.fromarray(raster).save(dest / "screen-retry.png")
    valid = []
    quads = []
    for d in found:
        if d.nodes is None:
            continue
        points = [{"x": float(x), "y": float(y)} for x, y in np.asarray(d.nodes).reshape(-1, 2)]
        try:
            lattice_cell_quads(points, width=frame.rgb.shape[1], height=frame.rgb.shape[0])
        except NeuralGridProposalError:
            continue
        quad = SourceQuad(tuple(SourcePoint(**points[i]) for i in (0, 5, 23, 18)))
        valid.append(d)
        quads.append(quad)
    count = row["end"] - row["start"] + 1
    ordered = associate_quad_slots(quads, count) if len(valid) == len(found) == count else None
    slots = (
        dict(enumerate(ordered))
        if ordered is not None
        else (associate_partial_slots(quads, count) or {})
    )
    pos = row["position"]
    if pos not in slots:
        return {
            "state": "missing",
            "cells": [],
            **({"redetected": bool(rescue and rescue.redetect_calls)} if diagnostic else {}),
        }
    detection = valid[slots[pos]]
    nodes = np.asarray(detection.nodes).reshape(24, 2)
    ctx = {
        **context,
        "sequenceRangeStart": row["start"],
        "sequenceRangeEnd": row["end"],
        "importJobId": row["job"],
        "fileExecutionKey": row["execution"],
    }

    def save(cell: VirtualCellRender) -> None:
        Image.fromarray(cell.rgb).save(dest / f"{cell.cell_index}.png")

    details = render_cells(
        frame,
        nodes,
        {"positionIndex": pos, "sequenceNumber": row["start"] + pos},
        ctx,
        raster_sink=save,
    )
    if diagnostic:
        inner = getattr(engine, "engine", engine)
        rescue = getattr(engine, "last_result", None)
        variant = (
            engine.variant.board
            if rescue is not None
            and pos in rescue.replacement_positions
            and engine.path in ("board_only", "combined")
            else None
        )
        matrix = board_rectifier(detection.screen_quad, inner.settings.board, geometry=variant)
        rgb = crop_board(frame.rgb, matrix, inner.settings.board, geometry=variant)
        Image.fromarray(rgb).save(dest / "input.png")
        overlay = Image.fromarray(frame.rgb)
        draw = ImageDraw.Draw(overlay)
        screen = [tuple(map(float, p)) for p in detection.screen_quad]
        draw.line([*screen, screen[0]], fill="yellow", width=3)
        grid = nodes.reshape(4, 6, 2)
        for line in [*grid, *grid.transpose(1, 0, 2)]:
            draw.line([tuple(map(float, p)) for p in line], fill="cyan", width=2)
        overlay.save(dest / "geometry.png")
    return {
        "state": "detected",
        "cells": [item["reason"] is None for item in details],
        **({"redetected": bool(rescue and rescue.redetect_calls)} if diagnostic else {}),
    }


def frame_for(row: Document) -> CanonicalSourceFrame:
    frame = CanonicalSourceLoader().load(
        Path(row["file"]), expected_source_checksum_sha256=row["sha"]
    )
    if frame.pixel_checksum_sha256 != row["pix"]:
        raise ValueError("Zmieniła się znormalizowana treść zdjęcia.")
    return frame


def score(
    cards: list[Document], key: dict[str, str], votes: Document, quality_pass: bool
) -> Document:
    if len(cards) != 100 or len(key) != 100 or len(votes) != 100 or set(key) != set(votes):
        raise ValueError("Potrzeba odpowiedzi dla dokładnie stu zapieczętowanych par.")
    result = {
        "baseNeedsFix": 0,
        "candidateNeedsFix": 0,
        "repaired": 0,
        "worsened": 0,
        "newClippedSymbols": 0,
        "previouslyFullNowUnassessable": 0,
        "unassessableCells": 0,
    }
    for card in cards:
        token = card["id"]
        pair = votes[token]
        if set(pair) != {"A", "B"} or key[token] not in ("A", "B"):
            raise ValueError("Niepełna para ocen.")
        for side in ("A", "B"):
            evidence = card[side]
            statuses = pair[side]
            if not isinstance(statuses, list) or len(statuses) != 15:
                raise ValueError("Wymagana ocena 15 pozycji.")
            for index, status in enumerate(statuses):
                available = evidence["state"] == "detected" and evidence["cells"][index]
                if (
                    available and status not in ("full", "fullFix", "cut", "sourceCut", "unknown")
                ) or (not available and status != "missing"):
                    raise ValueError("Ocena niezgodna z dostępnością pola.")
        a = pair[key[token]]
        b = pair["B" if key[token] == "A" else "A"]
        before = any(v != "full" for v in a)
        after = any(v != "full" for v in b)
        result["baseNeedsFix"] += int(before)
        result["candidateNeedsFix"] += int(after)
        result["repaired"] += int(before and not after)
        result["worsened"] += int(after and not before)
        result["newClippedSymbols"] += sum(
            x in ("full", "fullFix") and y == "cut" for x, y in zip(a, b, strict=False)
        )
        result["previouslyFullNowUnassessable"] += sum(
            x in ("full", "fullFix") and y in ("missing", "unknown", "sourceCut")
            for x, y in zip(a, b, strict=False)
        )
        result["unassessableCells"] += sum("unknown" in xy for xy in zip(a, b, strict=False))
    result["net"] = result["repaired"] - result["worsened"]
    passed = (
        quality_pass
        and result["net"] >= 5
        and result["newClippedSymbols"]
        == result["previouslyFullNowUnassessable"]
        == result["unassessableCells"]
        == 0
    )
    return {**result, "boards": 100, "qualityPass": quality_pass, "recommendActivation": passed}
