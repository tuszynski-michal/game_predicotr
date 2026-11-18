"""Measured changes to historically approved Mumie TRAIN geometry, in rectified cell units."""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import cv2
import numpy as np
from game_predictor_worker.geometry_core.preprocessing import (
    CORNERS,
    corners,
    lattice_homography,
    quad_is_usable,
    transform_points,
)
from game_predictor_worker.images.production_cell_evaluation import render_cells
from PIL import Image, ImageDraw
from sqlalchemy import text
from sqlalchemy.engine import Connection

from scripts.mumie_grid_pilot_review import frame_for, tokens
from scripts.mumie_grid_pilot_sources import (
    GAME,
    historical,
    imported,
    recording_context,
    render_context,
)

Document = dict[str, Any]
INNER = [row * 6 + column for row in (1, 2) for column in range(1, 5)]
PERIMETER = [index for index in range(24) if index not in INNER]


def coordinates(nodes: list[Document]) -> Any:
    return np.array([(p["x"], p["y"]) for p in nodes], dtype=np.float32)


def paired_geometry(previous: Any, corrected: Any) -> dict[str, float] | None:
    """Compare in the corrected plane; remove the corner transform to isolate internal warp."""
    if not all(quad_is_usable(corners(nodes)) for nodes in (previous, corrected)):
        return None
    try:
        to_corrected = np.linalg.inv(lattice_homography(corners(corrected)))
        to_previous = np.linalg.inv(lattice_homography(corners(previous)))
    except np.linalg.LinAlgError:
        return None
    target = transform_points(corrected, to_corrected)
    actual = transform_points(previous, to_corrected)
    local = transform_points(previous, to_previous)
    delta = actual - target
    residual = local - target
    previous_center = transform_points(
        np.array([[2.5, 1.5]], np.float32), to_corrected @ lattice_homography(corners(previous))
    )[0]
    return {
        "perimeter": float(np.max(np.abs(delta[PERIMETER]))),
        "corner": float(np.max(np.abs(delta[list(CORNERS)]))),
        "centre": float(np.max(np.abs(previous_center - [2.5, 1.5]))),
        "inside": float(np.max(np.abs(delta[INNER]))),
        "insideAfterCornerAlignment": float(np.max(np.abs(residual[INNER]))),
        "topInward": float(np.mean(delta[:6, 1])),
        "bottomInward": -float(np.mean(delta[-6:, 1])),
        "leftInward": float(np.mean(delta[::6, 0])),
        "rightInward": -float(np.mean(delta[5::6, 0])),
    }


def describe(rows: list[Document]) -> Document:
    if not rows:
        return {"pairs": 0}

    def column(name: str) -> Any:
        return np.array([r["metrics"][name] for r in rows])

    rim = column("perimeter") > 0.25
    interior = column("insideAfterCornerAlignment") > 0.25
    return {
        "pairs": len(rows),
        "photos": len({r["photo"] for r in rows}),
        "previousSource": dict(Counter(r["prior_kind"] for r in rows)),
        "p50p90p99": {
            name: np.round(np.percentile(column(name), [50, 90, 99]), 4).tolist()
            for name in rows[0]["metrics"]
        },
        "overQuarterCell": {
            "perimeterOnly": int(np.count_nonzero(rim & ~interior)),
            "internalOnly": int(np.count_nonzero(~rim & interior)),
            "both": int(np.count_nonzero(rim & interior)),
            "neither": int(np.count_nonzero(~rim & ~interior)),
            "centre": int(np.count_nonzero(column("centre") > 0.25)),
            "inward": {
                side: int(np.count_nonzero(column(side + "Inward") > 0.25))
                for side in ("top", "bottom", "left", "right")
            },
        },
    }


def comparison_cases(rows: list[Document]) -> list[Document]:
    remaining = sorted(rows, key=lambda row: (row["sequence_number"], row["source_id"]))
    selected = []
    for metric, rank in (
        ("perimeter", 0.95),
        ("insideAfterCornerAlignment", 0.95),
        ("perimeter", 0.5),
        ("perimeter", 0.1),
    ):
        if not remaining:
            break
        ordered = sorted(remaining, key=lambda r: r["metrics"][metric])
        row = ordered[round(rank * (len(ordered) - 1))]
        selected.append(row)
        remaining = [other for other in remaining if other["photo"] != row["photo"]]
    return selected


def grid_preview(frame: Any, nodes: Any, reference: Any) -> Image.Image:
    image = Image.fromarray(frame.rgb)
    draw = ImageDraw.Draw(image)
    for grid, color in ((nodes, "#e5561c"), (reference, "#09e36d")):
        values = grid.reshape(4, 6, 2)
        for line in [*values, *values.transpose(1, 0, 2)]:
            draw.line([tuple(map(float, point)) for point in line], fill=color, width=2)
    combined = np.vstack((nodes, reference))
    left, top = np.floor(combined.min(axis=0) - 12).astype(int)
    right, bottom = np.ceil(combined.max(axis=0) + 12).astype(int)
    return image.crop(
        (max(0, left), max(0, top), min(image.width, right), min(image.height, bottom))
    )


def cell_sheet(
    frame: Any, nodes: Any, target: Document, context: Document
) -> tuple[Image.Image, list[Document]]:
    cfg = context["renderConfiguration"]
    width, height = cfg["outputWidth"], cfg["outputHeight"]
    sheet = Image.new("RGB", (5 * width, 3 * height), "gray")

    def collect(rendered: Any) -> None:
        row, col = divmod(rendered.cell_index, 5)
        sheet.paste(Image.fromarray(rendered.rgb), (col * width, row * height))

    return sheet, render_cells(frame, nodes, target, context, raster_sink=collect)


def cell_support(details: list[Document], reference: Any) -> list[float | None]:
    """Fraction of each manually outlined field covered by the actual sampled source support."""
    values: list[float | None] = []
    for index, observation in enumerate(details):
        row, col = divmod(index, 5)
        field = reference[
            [row * 6 + col, row * 6 + col + 1, (row + 1) * 6 + col + 1, (row + 1) * 6 + col]
        ]
        support = observation.get("support")
        if support is None or len(support) < 3 or not quad_is_usable(field, min_area=0):
            values.append(None)
            continue
        area, _ = cv2.intersectConvexConvex(field, np.asarray(support, np.float32))
        values.append(float(np.clip(area / cv2.contourArea(field), 0, 1)))
    return values


def preview_cards(
    conn: Connection, artifacts: Path, rows: list[Document], directory: Path
) -> list[Document]:
    lookup = {r["id"]: r for r in imported(conn, artifacts, sorted({r["job"] for r in rows}))}
    cards, articles = [], []
    for row in rows:
        seq = row["sequence_number"]
        if seq != row["sequence_range_start"] + row["position_index"]:
            raise ValueError("Niejednoznaczna pozycja sekwencji.")
        frame = frame_for({**row, "file": lookup[row["id"]]["file"]})
        source = render_context(
            conn, row["job"], revision_topology=row["topology_rules_version_id"]
        )
        context = {
            **source,
            "importJobId": row["job"],
            "fileExecutionKey": row["file_execution_key"],
            "sequenceRangeStart": row["sequence_range_start"],
            "sequenceRangeEnd": row["sequence_range_end"],
        }
        target = {"positionIndex": row["position_index"], "sequenceNumber": seq}
        grid_preview(frame, row["previous"], row["corrected"]).save(directory / f"{seq}-grid.png")
        case = {"sequence": seq, "padding": source["renderConfiguration"]["paddingFraction"]}
        for key in ("previous", "corrected"):
            image, details = cell_sheet(frame, row[key], target, context)
            width, height = image.width // 5, image.height // 3
            tiles = Image.new("RGB", (image.width + 4, image.height + 2), "#eee")
            for index in range(15):
                y, x = divmod(index, 5)
                box = (width * x, height * y, width * (x + 1), height * (y + 1))
                tiles.paste(image.crop(box), ((width + 1) * x, (height + 1) * y))
            tiles.save(directory / f"{seq}-{key}.png")
            support = cell_support(details, row["corrected"])
            case[key] = {
                "coveredFraction": support,
                "rendered": sum(d["reason"] is None for d in details),
            }
        cards.append(case)
        figures = []
        for name, caption in (
            ("grid", "Stara siatka na pomarańczowo, ręczna na zielono"),
            ("previous", "Przed korektą"),
            ("corrected", "Po korekcie"),
        ):
            figures.append(
                f'<figure><img alt="{caption}" src="{seq}-{name}.png">'
                f"<figcaption>{caption}</figcaption></figure>"
            )
        articles.append(f"<article><h2>Plansza {seq}</h2>{''.join(figures)}</article>")
    template = Path(__file__).with_name("templates") / "mumie-training-geometry.html"
    (directory / "index.html").write_text(
        template.read_text(encoding="utf8").replace("<!--cases-->", "".join(articles)),
        encoding="utf8",
    )
    return cards


def analyse_training(
    conn: Connection,
    ledger: sqlite3.Connection,
    base: Document,
    artifacts: Path,
    preview: Path | None,
) -> Document:
    _, pairs = historical(conn, base, exact_train=True)
    rows = [
        {
            **r,
            "id": r["source_id"],
            "job": r["import_id"],
            "pix": r["photo"],
            "sha": r["checksum_sha256"],
        }
        for r in pairs
    ]
    owner = "training-history-" + base["manifest"]["cohortId"]
    protected = {
        v[0] for v in ledger.execute("select token from reservations where study <> ?", (owner,))
    }
    if protected:
        recording_context(conn, rows)
    permitted: list[Document] = []
    excluded: Counter[str] = Counter()
    for row in rows:
        if protected and tokens(row) & protected:
            excluded["protected"] += 1
            continue
        previous = next(v for pos, v in row["neighbors"] if int(pos) == row["position_index"])
        row["previous"], row["corrected"] = coordinates(previous), coordinates(row["edited"])
        metrics = paired_geometry(row["previous"], row["corrected"])
        if metrics is None:
            excluded["unusableGeometry"] += 1
            continue
        row["metrics"] = metrics
        permitted.append(row)
    labels = conn.execute(
        text("""
        select (select count(*) from jsonb_array_elements(m.frozen->'positions') p
                 where p#>'{label,nodes}' is not null) as boards,
               count(*) as photos
        from grid_training_cohort_members m
        where m.game_id=:game and m.cohort_id=:cohort and m.role='TRAIN'
          and m.frozen->'used'='true'::jsonb
        group by 1 order by 1
    """),
        {"game": GAME, "cohort": base["manifest"]["cohortId"]},
    ).all()
    cohort = {
        "labelledBoardsPerPhoto": {n: total for n, total in labels},
        "fullPhotos": sum(total for n, total in labels if n == 9),
        "partialPhotos": sum(total for n, total in labels if 0 < n < 9),
    }
    result = {
        "cohort": base["manifest"]["cohortId"],
        "baseVersion": base["manifest"]["versionId"],
        "frozenTrainingCounts": cohort,
        "excluded": dict(excluded),
        **describe(permitted),
        "byPriorSource": {
            kind: describe([row for row in permitted if row["prior_kind"] == kind])
            for kind in sorted({row["prior_kind"] for row in permitted})
        },
    }
    if preview is None:
        return result
    if preview.exists() or not permitted:
        raise ValueError("Podgląd wymaga nowego katalogu oraz dopuszczonych par TRAIN.")
    selected = comparison_cases(permitted)
    if not protected:
        recording_context(conn, selected)
    with ledger:
        for token in sorted(set().union(*(tokens(row) for row in selected))):
            ledger.execute("insert or ignore into reservations values (?,?)", (token, owner))
            if (
                ledger.execute("select study from reservations where token=?", (token,)).fetchone()[
                    0
                ]
                != owner
            ):
                raise ValueError("Zdjęcie lub nagranie zarezerwowano do sprawdzianu.")
    preview.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=preview.parent) as staging:
        directory = Path(staging) / "preview"
        directory.mkdir()
        result["cases"] = preview_cards(conn, artifacts, selected, directory)
        directory.rename(preview)
    result["preview"] = str(preview.resolve() / "index.html")
    return result
