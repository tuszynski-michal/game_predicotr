"""Read-only pilot: does a cell crop show the gold frame of a super symbol? (TASK-0937)

Two phases, both strictly read-only against PostgreSQL and the game artifacts:

``--prepare``
    Selects up to ``--limit`` cells (half the super symbol of series with a defined super
    symbol, half other cells of the same boards), renders a tight crop (the cell quad) and a
    crop with an 8 % margin from the managed original, and writes a contact sheet
    (``index.html``) plus ``labels.csv`` below ``--out/<run>/``. The operator fills
    ``frame_label_tight`` and ``frame_label_margin`` (``tak`` / ``nie`` / ``częściowo``), one
    independent question per crop, independently of the symbol class.
    A run directory is never overwritten: an existing ``--run`` is refused (exit 1).

``--evaluate --labels <labels.csv>``
    Computes the gold-pixel share on the perimeter band of every crop, sweeps the decision
    threshold and reports precision / recall / F1 against the manual labels, plus the
    agreement of the labels with the proxy "cell of the super symbol in a series board".
    Writes ``scores.csv`` next to the labels and the Markdown report.

Gold range (OpenCV HSV: H 0..179, S/V 0..255), all overridable on the command line:
hue 15..35 (about 30..70 degrees: yellow-orange), saturation >= 90, value >= 120.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import cv2
import numpy as np
from numpy.typing import NDArray
from PIL import Image

PILOT_VERSION = "gold-frame-pilot-v1"
CROP_SIZE = 96
MARGIN_RATIO = 0.08
BAND_RATIO = 0.12
LABEL_VALUES = ("tak", "nie", "częściowo")
LABEL_COLUMNS = (
    "cell_id",
    "board_sequence_number",
    "cell_index",
    "symbol_code",
    "in_series",
    "is_super_symbol",
    "frame_label_tight",
    "frame_label_margin",
)
DEFAULT_REPORT = Path("ai_docs/quality/MUMIE_GOLD_FRAME_PILOT_20261009.md")
VARIANTS = ("tight", "margin")
Quad = tuple[tuple[float, float], ...]
Rgb = NDArray[np.uint8]


class PilotError(RuntimeError):
    """Operator-readable failure."""


class RunExistsError(PilotError):
    """The run directory already exists; nothing was written."""


@dataclass(frozen=True, slots=True)
class GoldRange:
    hue_min: int = 15
    hue_max: int = 35
    saturation_min: int = 90
    value_min: int = 120


DEFAULT_GOLD = GoldRange()


@dataclass(frozen=True, slots=True)
class PilotCell:
    id: str
    sequence_number: int
    cell_index: int
    symbol_code: str
    in_series: bool
    is_super_symbol: bool
    source_checksum_sha256: str
    source_quad: Quad


@dataclass(slots=True)
class PrepareSummary:
    series_total: int = 0
    series_with_super: int = 0
    super_cells_available: int = 0
    selected_super: int = 0
    selected_control: int = 0
    selected_outside: int = 0
    selected_fallback: int = 0
    rendered: int = 0
    failed: dict[str, int] = field(default_factory=dict)


# ----------------------------------------------------------------- pure image metrics


def perimeter_mask(height: int, width: int, band_ratio: float = BAND_RATIO) -> NDArray[np.bool_]:
    """Pixels closer to the border than ``band_ratio`` of the shorter side."""

    band = max(1, round(min(height, width) * band_ratio))
    mask = np.ones((height, width), dtype=bool)
    mask[band : height - band, band : width - band] = False
    return mask


def gold_mask(rgb: Rgb, gold: GoldRange) -> NDArray[np.bool_]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, saturation, value = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    return (
        (hue >= gold.hue_min)
        & (hue <= gold.hue_max)
        & (saturation >= gold.saturation_min)
        & (value >= gold.value_min)
    )


def perimeter_gold_share(
    rgb: Rgb, gold: GoldRange = DEFAULT_GOLD, band_ratio: float = BAND_RATIO
) -> float:
    """Share of gold pixels on the outer band of the crop (0..1)."""

    mask = perimeter_mask(rgb.shape[0], rgb.shape[1], band_ratio)
    return float(gold_mask(rgb, gold)[mask].mean())


def interior_gold_share(
    rgb: Rgb, gold: GoldRange = DEFAULT_GOLD, band_ratio: float = BAND_RATIO
) -> float:
    """Share of gold pixels inside the band; context only (gold symbols exist too)."""

    mask = ~perimeter_mask(rgb.shape[0], rgb.shape[1], band_ratio)
    return float(gold_mask(rgb, gold)[mask].mean())


def expand_quad(quad: Quad, margin_ratio: float) -> Quad:
    """Grow a quad about its centroid by ``margin_ratio`` of its size on every side."""

    points = np.array(quad, dtype=np.float64)
    centre = points.mean(axis=0)
    grown = centre + (points - centre) * (1.0 + 2.0 * margin_ratio)
    return tuple((float(x), float(y)) for x, y in grown)


# ------------------------------------------------------------------------ metrics


@dataclass(frozen=True, slots=True)
class Confusion:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None

    @property
    def f1(self) -> float | None:
        precision, recall = self.precision, self.recall
        if precision is None or recall is None or precision + recall == 0:
            return None
        return 2 * precision * recall / (precision + recall)


def confusion(truth: Sequence[bool], predicted: Sequence[bool]) -> Confusion:
    pairs = list(zip(truth, predicted, strict=True))
    return Confusion(
        tp=sum(1 for t, p in pairs if t and p),
        fp=sum(1 for t, p in pairs if not t and p),
        fn=sum(1 for t, p in pairs if t and not p),
        tn=sum(1 for t, p in pairs if not t and not p),
    )


def sweep_thresholds(
    scores: Sequence[float], truth: Sequence[bool], thresholds: Sequence[float]
) -> list[tuple[float, Confusion]]:
    return [(t, confusion(truth, [score >= t for score in scores])) for t in thresholds]


def best_threshold(sweep: Sequence[tuple[float, Confusion]]) -> tuple[float, Confusion] | None:
    """Highest F1; ties go to the lower threshold."""

    scored = [(item, item[1].f1) for item in sweep if item[1].f1 is not None]
    if not scored:
        return None
    return max(scored, key=lambda pair: (pair[1] or 0.0, -pair[0][0]))[0]


def normalize_label(value: str) -> str | None:
    cleaned = value.strip().lower()
    table = {
        "tak": "tak",
        "nie": "nie",
        "częściowo": "częściowo",
        "czesciowo": "częściowo",
        "czesc": "częściowo",
    }
    return table.get(cleaned)


# --------------------------------------------------------------------- phase A (DB)

_CELL_SQL = """
SELECT c.id::text AS id,
       c.sequence_number AS sequence_number,
       c.cell_index AS cell_index,
       c.recognized_board_id::text AS recognized_board_id,
       c.geometry_revision AS geometry_revision,
       c.render_spec_checksum_sha256 AS render_spec_checksum_sha256,
       coalesce(s.code, c.prediction_symbol_code) AS symbol_code,
       (c.assigned_symbol_id IS NOT NULL AND c.assigned_symbol_id = :super_symbol_id)
         OR (c.assigned_symbol_id IS NULL AND :super_code IS NOT NULL
             AND c.prediction_symbol_code = :super_code) AS is_super
FROM game_data_v2.image_symbol_review_cells c
LEFT JOIN public.symbols s ON s.id = c.assigned_symbol_id
WHERE c.game_id = :game_id
  AND c.sequence_number BETWEEN :first AND :last
  AND c.asset_mode = 'virtual_source'
  AND c.source_available = true
  AND c.quality_issue IS NULL
  AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
  AND c.render_spec_checksum_sha256 IS NOT NULL
  AND c.recognized_board_id IS NOT NULL
"""

_FALLBACK_SQL = """
SELECT c.id::text AS id,
       c.sequence_number AS sequence_number,
       c.cell_index AS cell_index,
       c.recognized_board_id::text AS recognized_board_id,
       c.geometry_revision AS geometry_revision,
       c.render_spec_checksum_sha256 AS render_spec_checksum_sha256,
       coalesce(s.code, c.prediction_symbol_code) AS symbol_code
FROM game_data_v2.image_symbol_review_cells c
LEFT JOIN public.symbols s ON s.id = c.assigned_symbol_id
WHERE c.game_id = :game_id
  AND c.recognized_board_id IN (
    SELECT recognized_board_id FROM game_data_v2.image_symbol_review_cells
    WHERE game_id = :game_id AND recognized_board_id IS NOT NULL
      AND asset_mode = 'virtual_source' AND source_available = true
    GROUP BY recognized_board_id ORDER BY max(created_at) DESC LIMIT :boards)
  AND c.asset_mode = 'virtual_source'
  AND c.source_available = true
  AND c.quality_issue IS NULL
  AND (c.source_visibility IS NULL OR c.source_visibility = 'full')
  AND c.render_spec_checksum_sha256 IS NOT NULL
"""


def _quad(value: object, label: str) -> Quad:
    if not isinstance(value, list) or len(value) != 4:
        raise PilotError(f"{label} is not a quad.")
    return tuple((float(point["x"]), float(point["y"])) for point in value)


def _stable_key(identifier: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{identifier}".encode("ascii")).hexdigest()


def _attach_specs(
    connection: Any, game_id: str, rows: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    from game_predictor_api.storage.cell_render_specs import (
        CellRenderSpecError,
        CellRenderSpecKey,
        load_cell_render_specs,
    )

    keys = [
        CellRenderSpecKey(
            recognized_board_id=UUID(str(row["recognized_board_id"])),
            geometry_revision=int(row["geometry_revision"]),
            cell_index=int(row["cell_index"]),
            render_spec_checksum_sha256=str(row["render_spec_checksum_sha256"]),
        )
        for row in rows
    ]
    try:
        specs = load_cell_render_specs(
            connection, game_id=UUID(game_id), keys=keys, schema="game_data_v2"
        )
    except CellRenderSpecError as error:
        raise PilotError(f"{error.code}: {error.message}") from error
    return [{**row, "render_spec": specs[key]} for row, key in zip(rows, keys, strict=True)]


def _to_cell(row: Mapping[str, Any], *, in_series: bool, is_super: bool) -> PilotCell:
    spec = row["render_spec"]
    return PilotCell(
        id=str(row["id"]),
        sequence_number=int(row["sequence_number"]),
        cell_index=int(row["cell_index"]),
        symbol_code=str(row["symbol_code"] or ""),
        in_series=in_series,
        is_super_symbol=is_super,
        source_checksum_sha256=str(spec["sourceChecksumSha256"]),
        source_quad=_quad(spec.get("sourceQuad"), "sourceQuad"),
    )


def select_cells(
    *, game_code: str, limit: int, seed: int, board_fallback: int
) -> tuple[str, list[PilotCell], PrepareSummary]:
    """Read-only selection of the sample; returns the game id, cells and a summary."""

    from game_predictor_api.config import ApiSettings
    from sqlalchemy import create_engine, text

    settings = ApiSettings.from_environment()
    engine = create_engine(settings.database_url, connect_args={"connect_timeout": 10})
    summary = PrepareSummary()
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ", postgresql_readonly=True
        ) as connection:
            game = (
                connection.execute(
                    text("SELECT id::text AS id FROM public.games WHERE code = :code"),
                    {"code": game_code},
                )
                .mappings()
                .one_or_none()
            )
            if game is None:
                raise PilotError(f"Unknown game code {game_code}.")
            game_id = str(game["id"])
            connection.execute(
                text("SELECT set_config('game_predictor.game_id', :game_id, true)"),
                {"game_id": game_id},
            )
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            # The operator DB may not have migration 0152 yet: no table means no series.
            has_series_table = (
                connection.execute(
                    text("SELECT to_regclass('game_data_v2.super_game_series') IS NOT NULL")
                ).scalar_one()
                is True
            )
            series_rows: list[Any] = []
            if has_series_table:
                series_rows = list(
                    connection.execute(
                        text(
                            "SELECT g.start_sequence_number AS first, g.length AS length,"
                            " g.super_symbol_id::text AS super_symbol_id, s.code AS super_code"
                            " FROM game_data_v2.super_game_series g"
                            " JOIN public.symbols s ON s.id = g.super_symbol_id"
                            " WHERE g.game_id = :game_id AND g.super_symbol_id IS NOT NULL"
                            " ORDER BY g.trigger_sequence_number"
                        ),
                        {"game_id": game_id},
                    )
                    .mappings()
                    .all()
                )
                summary.series_total = int(
                    connection.execute(
                        text("SELECT count(*) FROM game_data_v2.super_game_series"),
                    ).scalar_one()
                )
            else:
                print("super_game_series table missing (migration 0152 not applied).")
            ranges: list[tuple[int, int]] = []
            if has_series_table:
                ranges = [
                    (int(row["first"]), int(row["first"]) + int(row["length"]) - 1)
                    for row in connection.execute(
                        text(
                            "SELECT start_sequence_number AS first, length AS length"
                            " FROM game_data_v2.super_game_series WHERE game_id = :game_id"
                        ),
                        {"game_id": game_id},
                    )
                    .mappings()
                    .all()
                ]
            summary.series_with_super = len(series_rows)
            supers: list[dict[str, Any]] = []
            controls: list[dict[str, Any]] = []
            for series in series_rows:
                rows = (
                    connection.execute(
                        text(_CELL_SQL),
                        {
                            "game_id": game_id,
                            "first": int(series["first"]),
                            "last": int(series["first"]) + int(series["length"]) - 1,
                            "super_symbol_id": series["super_symbol_id"],
                            "super_code": series["super_code"],
                        },
                    )
                    .mappings()
                    .all()
                )
                for row in rows:
                    (supers if row["is_super"] else controls).append(dict(row))
            summary.super_cells_available = len(supers)
            picked: list[tuple[dict[str, Any], bool, bool]] = []
            fallback = [
                dict(row)
                for row in connection.execute(
                    text(_FALLBACK_SQL), {"game_id": game_id, "boards": board_fallback}
                )
                .mappings()
                .all()
            ]
            fallback.sort(key=lambda row: _stable_key(row["id"], seed))
            if series_rows:
                # Three groups: super symbol in series, other cells of series boards and
                # a control group of cells on boards outside every series.
                third = limit // 3
                supers.sort(key=lambda row: _stable_key(row["id"], seed))
                controls.sort(key=lambda row: _stable_key(row["id"], seed))
                outside = [
                    row
                    for row in fallback
                    if not any(
                        first <= int(row["sequence_number"]) <= last for first, last in ranges
                    )
                ]
                chosen_super = supers[:third]
                chosen_outside = outside[:third]
                chosen_control = controls[: limit - len(chosen_super) - len(chosen_outside)]
                summary.selected_super = len(chosen_super)
                summary.selected_control = len(chosen_control)
                summary.selected_outside = len(chosen_outside)
                picked = (
                    [(row, True, True) for row in chosen_super]
                    + [(row, True, False) for row in chosen_control]
                    + [(row, False, False) for row in chosen_outside]
                )
            if not picked:
                picked = [(row, False, False) for row in fallback[:limit]]
                summary.selected_fallback = len(picked)
            with_specs = _attach_specs(connection, game_id, [item[0] for item in picked])
    finally:
        engine.dispose()
    cells = [
        _to_cell(row, in_series=flags[1], is_super=flags[2])
        for row, flags in zip(with_specs, picked, strict=True)
    ]
    return game_id, cells, summary


def render_crops(cell: PilotCell, rgb: Rgb) -> dict[str, Rgb]:
    from game_predictor_worker.images.virtual_cell_extraction import source_direct_warp_rgb

    quads = {
        "tight": cell.source_quad,
        "margin": expand_quad(cell.source_quad, MARGIN_RATIO),
    }
    return {
        name: source_direct_warp_rgb(
            rgb, source_quad=quad, output_width=CROP_SIZE, output_height=CROP_SIZE
        )
        for name, quad in quads.items()
    }


def write_sheet(run_dir: Path, rows: Sequence[Mapping[str, Any]], game_code: str) -> None:
    """Contact sheet with two independent questions per cell (tight crop, 8 % margin crop).

    The symbol class is deliberately NOT shown (independent labels).
    """

    questions = {
        "tight": "Ramka widoczna na wycinku V3 (ciasnym)?",
        "margin": "Ramka widoczna na wycinku z marginesem 8 %?",
    }
    buttons = "".join(
        f'<button type="button" data-v="{value}">{value}</button>' for value in LABEL_VALUES
    )

    def group(cell_id: str, variant: str) -> str:
        return (
            f'<div class="grp" data-k="{variant}">'
            f'<img src="cells/{cell_id}_{variant}.png" alt="{variant}">'
            f'<div class="q">{questions[variant]}</div><div class="btns">{buttons}</div></div>'
        )

    data = [
        {
            "id": row["cell_id"],
            "tight": row["frame_label_tight"],
            "margin": row["frame_label_margin"],
        }
        for row in rows
    ]
    cards = "\n".join(
        f'<div class="card" data-id="{html.escape(str(row["cell_id"]))}">'
        f'<div class="num">#{index + 1} <span class="cid">'
        f"{html.escape(str(row['cell_id']))[:8]}</span></div>"
        f'<div class="pair">{group(html.escape(str(row["cell_id"])), "tight")}'
        f"{group(html.escape(str(row['cell_id'])), 'margin')}</div></div>"
        for index, row in enumerate(rows)
    )
    meta = [{c: str(r[c]) for c in LABEL_COLUMNS[:-2]} for r in rows]
    page = f"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<title>Pilot złotej ramki - {html.escape(game_code)}</title>
<style>
body{{font:14px system-ui,sans-serif;margin:16px;background:#1b1b1b;color:#eee}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(460px,1fr));gap:10px}}
.card{{background:#2a2a2a;padding:8px;border-radius:6px}}
.pair{{display:flex;gap:10px}} .grp{{flex:1}}
.card img{{width:192px;height:192px;image-rendering:pixelated;background:#000}}
.q{{font-size:12px;margin-top:4px}}
.btns button{{margin:4px 4px 0 0;padding:6px 10px;cursor:pointer}}
.grp.done{{outline:2px solid #3a7}}
.btns button.on{{background:#3a7;color:#fff}}
.num{{font-weight:bold}} .cid{{color:#888;font-size:11px}}
.bar{{position:sticky;top:0;background:#111;padding:8px;z-index:2}}
</style></head><body>
<div class="bar">Dla każdej komórki dwa niezależne pytania: czy widać złotą ramkę wokół
symbolu na lewym (ciasnym wycinku V3) i na prawym (z marginesem 8 %)?
<span id="count"></span>
<button id="save" type="button">Pobierz labels.csv</button></div>
<div class="grid">
{cards}
</div>
<script>
const rows = {json.dumps(data, ensure_ascii=False)};
const meta = {json.dumps(meta, ensure_ascii=False)};
const key = "gold-frame-pilot-{html.escape(run_dir.name)}";
try {{ const saved = JSON.parse(localStorage.getItem(key) || "{{}}");
  rows.forEach(r => {{ if (saved[r.id]) {{ r.tight = saved[r.id].tight || r.tight;
    r.margin = saved[r.id].margin || r.margin; }} }}); }} catch (e) {{}}
const cards = document.querySelectorAll(".card");
function paint() {{
  let done = 0;
  cards.forEach((card, i) => {{
    card.querySelectorAll(".grp").forEach(g => {{
      const v = rows[i][g.dataset.k]; if (v) done++;
      g.classList.toggle("done", !!v);
      g.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === v));
    }});
  }});
  document.getElementById("count").textContent = " Oznaczone: " + done + " / " + 2 * rows.length;
  try {{ const o = {{}}; rows.forEach(r => {{ o[r.id] = {{tight: r.tight, margin: r.margin}}; }});
    localStorage.setItem(key, JSON.stringify(o)); }} catch (e) {{}}
}}
cards.forEach((card, i) => card.querySelectorAll(".grp").forEach(g =>
  g.querySelectorAll("button").forEach(b =>
    b.addEventListener("click", () => {{ rows[i][g.dataset.k] = b.dataset.v; paint(); }}))));
document.getElementById("save").addEventListener("click", () => {{
  const cols = {json.dumps(list(LABEL_COLUMNS))};
  const q = v => '"' + String(v).replace(/"/g, '""') + '"';
  const cell = (m, i, c) => c === "frame_label_tight" ? rows[i].tight
    : c === "frame_label_margin" ? rows[i].margin : m[c];
  const lines = [cols.join(",")];
  meta.forEach((m, i) => lines.push(cols.map(c => q(cell(m, i, c))).join(",")));
  const blob = new Blob(["\\ufeff" + lines.join("\\r\\n")], {{type: "text/csv;charset=utf-8"}});
  const a = document.createElement("a"); a.href = URL.createObjectURL(blob);
  a.download = "labels.csv"; a.click();
}});
paint();
</script></body></html>
"""
    (run_dir / "index.html").write_text(page, encoding="utf-8")


def prepare(arguments: argparse.Namespace) -> int:
    from game_predictor_worker.images.normalization import (
        CanonicalSourceLoader,
        CanonicalSourceLoadError,
    )
    from game_predictor_worker.images.virtual_cell_extraction import VirtualCellExtractionError

    run = arguments.run or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (arguments.out / run).resolve()
    if run_dir.exists():
        raise RunExistsError(
            f"run directory {run_dir} already exists; nothing was written. "
            "Use --run <new name> (existing labels and images are never overwritten)."
        )
    game_id, cells, summary = select_cells(
        game_code=arguments.game,
        limit=arguments.limit,
        seed=arguments.seed,
        board_fallback=arguments.fallback_boards,
    )
    print(
        f"game={arguments.game} ({game_id}) series={summary.series_total} "
        f"with_super_symbol={summary.series_with_super} "
        f"super_cells_available={summary.super_cells_available}"
    )
    if summary.series_with_super == 0:
        print(
            "NO ELIGIBLE SERIES: no series has a defined super symbol yet. Falling back to "
            f"{len(cells)} cells of recent cut boards (in_series=false); the measurement "
            "against super-symbol series must be repeated once series exist."
        )
    if not cells:
        print("No eligible cells found; nothing written.")
        return 0
    artifact_root = (arguments.artifact_root or Path("artifacts")).resolve()
    originals = artifact_root / "data" / "originals"
    cells_dir = run_dir / "cells"
    cells_dir.mkdir(parents=True, exist_ok=False)
    loader = CanonicalSourceLoader()
    frames: dict[str, Rgb] = {}
    rows: list[dict[str, Any]] = []
    for cell in cells:
        checksum = cell.source_checksum_sha256
        try:
            if checksum not in frames:
                if len(frames) >= 8:
                    frames.clear()
                frames[checksum] = loader.load(
                    originals / checksum[:2] / f"{checksum}.jpg",
                    expected_source_checksum_sha256=checksum,
                ).rgb
            crops = render_crops(cell, frames[checksum])
        except (CanonicalSourceLoadError, VirtualCellExtractionError) as error:
            code = str(getattr(error, "code", type(error).__name__))
            summary.failed[code] = summary.failed.get(code, 0) + 1
            continue
        except cv2.error:
            summary.failed["RENDER_FAILED"] = summary.failed.get("RENDER_FAILED", 0) + 1
            continue
        for name, crop in crops.items():
            Image.fromarray(crop).save(cells_dir / f"{cell.id}_{name}.png")
        summary.rendered += 1
        rows.append(
            {
                "cell_id": cell.id,
                "board_sequence_number": cell.sequence_number,
                "cell_index": cell.cell_index,
                "symbol_code": cell.symbol_code,
                "in_series": str(cell.in_series).lower(),
                "is_super_symbol": str(cell.is_super_symbol).lower(),
                "frame_label_tight": "",
                "frame_label_margin": "",
            }
        )
    # Interleave classes so the operator cannot infer the class from the position.
    rows.sort(key=lambda row: _stable_key(str(row["cell_id"]), arguments.seed + 1))
    with (run_dir / "labels.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    write_sheet(run_dir, rows, arguments.game)
    (run_dir / "prepare.json").write_text(
        json.dumps(
            {
                "version": PILOT_VERSION,
                "game": arguments.game,
                "seed": arguments.seed,
                "marginRatio": MARGIN_RATIO,
                "cropSize": CROP_SIZE,
                "summary": asdict(summary),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"rendered={summary.rendered} super={summary.selected_super} "
        f"series_other={summary.selected_control} outside_series={summary.selected_outside} "
        f"fallback={summary.selected_fallback} "
        f"failed={summary.failed}"
    )
    print(f"run dir: {run_dir}")
    print(f"contact sheet: {run_dir / 'index.html'}")
    print(f"labels: {run_dir / 'labels.csv'}")
    return 0


# --------------------------------------------------------------------- phase B


@dataclass(frozen=True, slots=True)
class ScoredRow:
    cell_id: str
    symbol_code: str
    in_series: bool
    is_super_symbol: bool
    labels: dict[str, str | None]
    scores: dict[str, float]
    interior: dict[str, float]

    @property
    def group(self) -> str:
        if self.is_super_symbol:
            return "super symbol w serii"
        return "inne komórki serii" if self.in_series else "poza seriami"


def read_labels(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in LABEL_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise PilotError(f"labels file lacks columns: {missing}")
        return [dict(row) for row in reader]


def score_rows(
    labels: Sequence[Mapping[str, str]], run_dir: Path, gold: GoldRange, band: float
) -> list[ScoredRow]:
    scored: list[ScoredRow] = []
    for row in labels:
        scores: dict[str, float] = {}
        interior: dict[str, float] = {}
        parsed: dict[str, str | None] = {}
        for name in VARIANTS:
            path = run_dir / "cells" / f"{row['cell_id']}_{name}.png"
            with Image.open(path) as image:
                rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
            scores[name] = perimeter_gold_share(rgb, gold, band)
            interior[name] = interior_gold_share(rgb, gold, band)
            raw = (row.get(f"frame_label_{name}") or "").strip()
            parsed[name] = normalize_label(raw) if raw else None
            if raw and parsed[name] is None:
                raise PilotError(f"cell {row['cell_id']}: unknown frame_label_{name} {raw!r}")
        scored.append(
            ScoredRow(
                cell_id=row["cell_id"],
                symbol_code=row["symbol_code"],
                in_series=row["in_series"].strip().lower() == "true",
                is_super_symbol=row["is_super_symbol"].strip().lower() == "true",
                labels=parsed,
                scores=scores,
                interior=interior,
            )
        )
    return scored


def _fmt(value: float | None) -> str:
    return "n/d" if value is None else f"{value:.3f}"


def _confusion_row(name: str, c: Confusion) -> str:
    return (
        f"| {name} | {c.tp} | {c.fp} | {c.fn} | {c.tn} | "
        f"{_fmt(c.precision)} | {_fmt(c.recall)} | {_fmt(c.f1)} |"
    )


_HEADER = (
    "| Wariant | TP | FP | FN | TN | Precyzja | Czułość | F1 |\n|---|---|---|---|---|---|---|---|"
)
_GROUPS = ("super symbol w serii", "inne komórki serii", "poza seriami")


def _visible(label: str | None) -> bool:
    return label in ("tak", "częściowo")


def visibility_summary(scored: Sequence[ScoredRow]) -> dict[str, int]:
    """Where the operator sees the frame; the main question: is it inside the V3 crop?"""

    both = [row for row in scored if row.labels["tight"] and row.labels["margin"]]
    return {
        "rated": len(both),
        "tight_visible": sum(1 for r in both if _visible(r.labels["tight"])),
        "tight_full": sum(1 for r in both if r.labels["tight"] == "tak"),
        "margin_visible": sum(1 for r in both if _visible(r.labels["margin"])),
        "only_margin": sum(
            1 for r in both if not _visible(r.labels["tight"]) and _visible(r.labels["margin"])
        ),
        "margin_only_full": sum(
            1 for r in both if r.labels["tight"] != "tak" and r.labels["margin"] == "tak"
        ),
        "neither": sum(
            1 for r in both if not _visible(r.labels["tight"]) and not _visible(r.labels["margin"])
        ),
    }


def build_report(
    scored: Sequence[ScoredRow],
    *,
    gold: GoldRange,
    band: float,
    thresholds: Sequence[float],
    labels_path: Path,
    min_labels: int,
) -> str:
    by_variant = {
        name: [row for row in scored if row.labels[name] is not None] for name in VARIANTS
    }
    lines = [
        "# Pilot wykrywania złotej ramki super symbolu (TASK-0937)",
        "",
        f"Wersja narzędzia: `{PILOT_VERSION}`. Skrypt: `scripts/m8_gold_frame_pilot.py` "
        "(tylko odczyt). Etykiety: " + f"`{labels_path.as_posix()}`.",
        "",
        "## Metoda",
        "",
        f"- Komórki: wycinek ciasny (kwadrat komórki V3, {CROP_SIZE} px) oraz wycinek z "
        f"marginesem {MARGIN_RATIO:.0%} z obrazu źródłowego.",
        "- Prawda odniesienia: niezależne ręczne etykiety operatora, osobno dla każdego "
        "wycinka (`frame_label_tight`, `frame_label_margin`: `tak` / `nie` / `częściowo`), "
        "nadane bez widoku klasy symbolu.",
        "- Trzy grupy próby: (1) super symbol w planszach serii, (2) inne komórki plansz "
        "serii, (3) komórki z plansz poza seriami (`in_series=false`). W trybie "
        "zastępczym (brak serii z super symbolem) próba zawiera tylko grupę (3).",
        f"- Metryka: udział „złotych” pikseli na obwodzie (zewnętrzne {band:.0%} krótszego "
        "boku wycinka); każdy wariant oceniany względem własnych etykiet.",
        f"- Zakres „złota” (HSV OpenCV): odcień {gold.hue_min}..{gold.hue_max}, "
        f"nasycenie >= {gold.saturation_min}, jasność >= {gold.value_min}.",
        "- Decyzja: udział >= próg. Próg przeszukiwany od 0 do 1; `częściowo` liczone jako "
        "pozytyw, a osobno z pominięciem tych komórek.",
        "",
        "## Próba",
        "",
        f"- Komórek w arkuszu: {len(scored)}; grupy: "
        + ", ".join(f"{g} {sum(1 for r in scored if r.group == g)}" for g in _GROUPS)
        + ".",
    ]
    for name in VARIANTS:
        counts = {v: sum(1 for r in by_variant[name] if r.labels[name] == v) for v in LABEL_VALUES}
        lines.append(
            f"- Wariant `{name}`: z etykietą {len(by_variant[name])} "
            f"(wymagane co najmniej {min_labels}); tak {counts['tak']}, nie {counts['nie']}, "
            f"częściowo {counts['częściowo']}."
        )
    lines.append("")
    ready = all(len(by_variant[name]) >= min_labels for name in VARIANTS)
    if not ready:
        lines += [
            "## Wyniki",
            "",
            "Brak wystarczającej liczby etykiet dla obu wariantów; metryki nie są raportowane.",
            "",
        ]
        for name in VARIANTS if scored else ():
            values = sorted(row.scores[name] for row in scored)
            lines.append(
                f"- Rozkład udziału złota na obwodzie, wariant `{name}`: "
                f"min {values[0]:.3f}, mediana {values[len(values) // 2]:.3f}, "
                f"maks {values[-1]:.3f}."
            )
        lines += ["", "## Rekomendacja", "", "do uzupełnienia po etykietach operatora", ""]
        return "\n".join(lines)

    vis = visibility_summary(scored)
    lines += [
        "## Czy wycinek V3 obejmuje ramkę?",
        "",
        f"Komórek ocenionych w obu wariantach: {vis['rated']}.",
        "",
        "| Miara | Komórek |",
        "|---|---|",
        f"| ramka widoczna na wycinku V3 (`tak` lub `częściowo`) | {vis['tight_visible']} |",
        f"| ramka w pełni widoczna na wycinku V3 (`tak`) | {vis['tight_full']} |",
        f"| ramka widoczna na wycinku z marginesem | {vis['margin_visible']} |",
        f"| ramka widoczna tylko z marginesem (V3: `nie`) | {vis['only_margin']} |",
        f"| ramka pełna tylko z marginesem (V3: `nie`/`częściowo`) | {vis['margin_only_full']} |",
        f"| ramki nie widać nigdzie | {vis['neither']} |",
        "",
        "## Wyniki heurystyki",
        "",
    ]
    for scheme, positives, excluded in (
        ("tak + częściowo = pozytyw", ("tak", "częściowo"), ()),
        ("tylko tak = pozytyw, częściowo pominięte", ("tak",), ("częściowo",)),
    ):
        lines += [f"### {scheme}", ""]
        best_rows: list[str] = []
        for name in VARIANTS:
            pool = [r for r in by_variant[name] if r.labels[name] not in excluded]
            truth = [r.labels[name] in positives for r in pool]
            sweep = sweep_thresholds([r.scores[name] for r in pool], truth, thresholds)
            best = best_threshold(sweep)
            lines += [
                f"Wariant `{name}` (własne etykiety), komórek {len(pool)}, pozytywów {sum(truth)}:",
                "",
                "| Próg | TP | FP | FN | TN | Precyzja | Czułość | F1 |",
                "|---|---|---|---|---|---|---|---|",
            ]
            for threshold, c in sweep:
                lines.append(
                    f"| {threshold:.2f} | {c.tp} | {c.fp} | {c.fn} | {c.tn} | "
                    f"{_fmt(c.precision)} | {_fmt(c.recall)} | {_fmt(c.f1)} |"
                )
            lines.append("")
            if best is not None:
                best_rows.append(_confusion_row(f"`{name}`, próg {best[0]:.2f}", best[1]))
        if best_rows:
            lines += ["Najlepszy próg wg F1:", "", _HEADER, *best_rows, ""]

    lines += ["## Zgodność etykiet z proxy „komórka super symbolu w serii”", "", _HEADER]
    for name in VARIANTS:
        for scheme, positives in (
            ("tak + częściowo", ("tak", "częściowo")),
            ("tylko tak", ("tak",)),
        ):
            truth = [r.labels[name] in positives for r in by_variant[name]]
            predicted = [r.is_super_symbol for r in by_variant[name]]
            lines.append(
                _confusion_row(f"`{name}`: proxy vs {scheme}", confusion(truth, predicted))
            )
    lines += ["", "Odsetek komórek z widoczną ramką (`tak` lub `częściowo`) wg grupy:", ""]
    lines += ["| Grupa | Komórek | Wycinek V3 | Z marginesem |", "|---|---|---|---|"]
    for group in _GROUPS:
        members = [r for r in scored if r.group == group]
        if not members:
            lines.append(f"| {group} | 0 | n/d | n/d |")
            continue
        cells = [str(len(members))]
        for name in VARIANTS:
            rated = [r for r in members if r.labels[name] is not None]
            hit = sum(1 for r in rated if _visible(r.labels[name]))
            cells.append(f"{hit}/{len(rated)}")
        lines.append(f"| {group} | " + " | ".join(cells) + " |")
    lines += ["", "## Rekomendacja", "", "do uzupełnienia po etykietach operatora", ""]
    return "\n".join(lines)


def evaluate(arguments: argparse.Namespace) -> int:
    labels_path: Path = arguments.labels.resolve()
    run_dir = labels_path.parent
    gold = GoldRange(
        hue_min=arguments.hue_min,
        hue_max=arguments.hue_max,
        saturation_min=arguments.saturation_min,
        value_min=arguments.value_min,
    )
    scored = score_rows(read_labels(labels_path), run_dir, gold, arguments.band)
    thresholds = [
        round(step * arguments.threshold_step, 4)
        for step in range(int(1 / arguments.threshold_step) + 1)
    ]
    with (run_dir / "scores.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["cell_id", "frame_label_tight", "frame_label_margin", "in_series", "is_super_symbol"]
            + [f"perimeter_{name}" for name in VARIANTS]
            + [f"interior_{name}" for name in VARIANTS]
        )
        for row in scored:
            writer.writerow(
                [
                    row.cell_id,
                    row.labels["tight"] or "",
                    row.labels["margin"] or "",
                    row.in_series,
                    row.is_super_symbol,
                ]
                + [f"{row.scores[name]:.4f}" for name in VARIANTS]
                + [f"{row.interior[name]:.4f}" for name in VARIANTS]
            )
    report = build_report(
        scored,
        gold=gold,
        band=arguments.band,
        thresholds=thresholds,
        labels_path=labels_path,
        min_labels=arguments.min_labels,
    )
    arguments.report.parent.mkdir(parents=True, exist_ok=True)
    arguments.report.write_text(report, encoding="utf-8")
    labelled = sum(1 for row in scored if all(row.labels[name] for name in VARIANTS))
    print(f"scored={len(scored)} labelled_both={labelled} report={arguments.report}")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--prepare", action="store_true", help="phase A (default)")
    mode.add_argument("--evaluate", action="store_true", help="phase B")
    parser.add_argument("--game", default="mumie")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--out", type=Path, default=Path("artifacts/gold-frame-pilot"))
    parser.add_argument("--run", help="run directory name below --out (default: UTC timestamp)")
    parser.add_argument("--artifact-root", type=Path, help="root holding data/originals")
    parser.add_argument("--seed", type=int, default=20261009)
    parser.add_argument("--fallback-boards", type=int, default=50)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-labels", type=int, default=30)
    parser.add_argument("--band", type=float, default=BAND_RATIO)
    parser.add_argument("--threshold-step", type=float, default=0.05)
    defaults = DEFAULT_GOLD
    parser.add_argument("--hue-min", type=int, default=defaults.hue_min)
    parser.add_argument("--hue-max", type=int, default=defaults.hue_max)
    parser.add_argument("--saturation-min", type=int, default=defaults.saturation_min)
    parser.add_argument("--value-min", type=int, default=defaults.value_min)
    arguments = parser.parse_args(argv)
    if arguments.evaluate and arguments.labels is None:
        parser.error("--evaluate requires --labels")
    if not 1 <= arguments.limit <= 500:
        parser.error("--limit must be 1..500")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    try:
        return evaluate(arguments) if arguments.evaluate else prepare(arguments)
    except RunExistsError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    except PilotError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
