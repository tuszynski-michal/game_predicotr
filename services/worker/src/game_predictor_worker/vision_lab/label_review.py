"""Operator review of production grid labels: 300 S and 300 B boards (TASK-0801).

The existing photo review (:mod:`.photo_review`) works on the lab annotation
state of a lab folder snapshot (sources, human annotations, accepted board
revisions). Production grids are not lab annotations, so showing them there would
mean rebuilding that data model. This is the smallest standalone tool instead:

* ``prepare`` draws the sample from the whole filtered candidate manifest (not only
  from the training selection), one board per photo, renders one crop per board
  and publishes ``sample.json`` and ``crops/`` atomically (immutable afterwards);
* ``serve`` runs a loopback-only page on ``127.0.0.1`` with keyboard decisions
  ``good / bad / unreadable``, skip, back and undo; every decision is appended to
  ``history.jsonl`` (fsync, the source of truth) and mirrored atomically to
  ``decisions.json``, so closing the page or the process loses nothing;
* ``report`` writes ``summary.json``: the share of ``bad`` among judged boards per
  level with a 95% Wilson interval. Whether S/B are fit for training is the
  operator's decision.

The page does not show the label level of an item (blind review); items of both
levels are interleaved in seeded order. Nothing here imports production storage.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import tempfile
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
from PIL import Image, ImageOps
from pydantic import BaseModel, ConfigDict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from . import production_split as split
from .production_snapshot import (
    COORDINATE_SPACE,
    SourceInspector,
    collect_rows,
    dumps,
    scan_candidates,
)

SAMPLE_SCHEMA: Final = "production-geometry-label-review-sample-v1"
DECISIONS_SCHEMA: Final = "production-geometry-label-review-decisions-v1"
SUMMARY_SCHEMA: Final = "production-geometry-label-review-summary-v1"
DECISIONS: Final = ("good", "bad", "unreadable")
DEFAULT_PORT: Final = 8103
CROP_LONG_SIDE: Final = 960
CROP_MARGIN: Final = 0.25
WILSON_Z_95: Final = 1.959963984540054

_SAMPLE: Final = "sample.json"
_HISTORY: Final = "history.jsonl"
_DECISIONS: Final = "decisions.json"
_SUMMARY: Final = "summary.json"
_CROP_NAME: Final = re.compile(r"^[0-9]{4}\.jpg$")


@dataclass(frozen=True, slots=True)
class ReviewPick:
    level: str
    image_id: str
    board_id: str


def gold_related(images: Mapping[str, split.ImageFacts]) -> set[str]:
    gold_shas = {image.sha256 for image in images.values() if "G" in image.levels}
    return {image_id for image_id, image in images.items() if image.sha256 in gold_shas}


def review_population(images: Mapping[str, split.ImageFacts]) -> dict[str, list[str]]:
    """Filter-passing S and B photos of the whole manifest (gold-related photos excluded)."""

    excluded = gold_related(images)
    population: dict[str, list[str]] = {level: [] for level in split.TRAINING_LEVELS}
    for image_id in sorted(images):
        image = images[image_id]
        if image_id in excluded or split.filter_reasons(image):
            continue
        level = split.image_level(image)
        if level is not None:
            population[level].append(image_id)
    return population


def select_review_sample(
    images: Mapping[str, split.ImageFacts],
    seed: int,
    per_level: int,
    check: Callable[[str], str | None],
) -> tuple[list[ReviewPick], dict[str, str]]:
    """``per_level`` photos per level in seeded order, one seeded board each.

    Photos failing the integrity ``check`` are skipped and returned with the reason.
    """

    picks: list[ReviewPick] = []
    excluded: dict[str, str] = {}
    for level, ids in review_population(images).items():
        ordered = sorted(ids, key=lambda i: split.order_key(seed, f"label-review|{level}", i))
        taken = 0
        for image_id in ordered:
            if taken == per_level:
                break
            reason = check(image_id)
            if reason is not None:
                excluded[image_id] = reason
                continue
            board = min(
                images[image_id].boards,
                key=lambda b: split.order_key(
                    seed, "label-review-board", f"{image_id}|{b.board_id}"
                ),
            )
            picks.append(ReviewPick(level, image_id, board.board_id))
            taken += 1
        if taken < per_level:
            raise ValueError(f"LABEL_REVIEW_POPULATION_INSUFFICIENT: {level} {taken}<{per_level}")
    picks.sort(
        key=lambda p: split.order_key(seed, "label-review-order", f"{p.image_id}|{p.board_id}")
    )
    return picks, excluded


def wilson_interval(
    failures: int, total: int, z: float = WILSON_Z_95
) -> tuple[float, float] | None:
    if total <= 0:
        return None
    p = failures / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, centre - half), min(1.0, centre + half)


def summarize(items: Sequence[Mapping[str, Any]], decisions: Mapping[str, str]) -> dict[str, Any]:
    levels: dict[str, dict[str, Any]] = {}
    for level in sorted({str(item["level"]) for item in items}):
        level_items = [item for item in items if item["level"] == level]
        counts = dict.fromkeys(DECISIONS, 0)
        for item in level_items:
            decision = decisions.get(str(item["itemId"]))
            if decision is not None:
                counts[decision] += 1
        judged = counts["good"] + counts["bad"]
        interval = wilson_interval(counts["bad"], judged)
        levels[level] = {
            "items": len(level_items),
            **counts,
            "undecided": len(level_items) - sum(counts.values()),
            "judged": judged,
            "badRate": counts["bad"] / judged if judged else None,
            "wilson95": list(interval) if interval else None,
        }
    return {
        "schemaVersion": SUMMARY_SCHEMA,
        "definition": (
            "badRate = bad / (good + bad); 'unreadable' and undecided items are excluded "
            "from the rate; wilson95 = Wilson score interval, z = 1.96"
        ),
        "levels": levels,
        "decided": len(decisions),
        "items": len(items),
        "badItems": [
            {
                "itemId": item["itemId"],
                "level": item["level"],
                "imageId": item["imageId"],
                "recognizedBoardId": item["recognizedBoardId"],
            }
            for item in items
            if decisions.get(str(item["itemId"])) == "bad"
        ],
    }


def render_crop(
    oriented: Image.Image, nodes: Sequence[Sequence[float]]
) -> tuple[bytes, int, int, list[list[float]]]:
    """Board crop with margin, upscaled so its long side is ``CROP_LONG_SIDE``; nodes moved
    into crop pixels. The grid is drawn by the page so it can be hidden."""

    xs = [float(x) for x, _ in nodes]
    ys = [float(y) for _, y in nodes]
    margin = CROP_MARGIN * max(max(xs) - min(xs), max(ys) - min(ys))
    left = max(0.0, min(xs) - margin)
    top = max(0.0, min(ys) - margin)
    right = min(float(oriented.width), max(xs) + margin)
    bottom = min(float(oriented.height), max(ys) + margin)
    scale = CROP_LONG_SIDE / max(right - left, bottom - top)
    width = max(1, round((right - left) * scale))
    height = max(1, round((bottom - top) * scale))
    crop = oriented.resize(
        (width, height), Image.Resampling.LANCZOS, box=(left, top, right, bottom)
    )
    stream = io.BytesIO()
    crop.save(stream, "JPEG", quality=92)
    moved = [
        [
            round((x - left) * width / (right - left), 2),
            round((y - top) * height / (bottom - top), 2),
        ]
        for x, y in zip(xs, ys, strict=True)
    ]
    return stream.getvalue(), width, height, moved


def prepare_review(
    candidates: Path,
    artifact_root: Path,
    output: Path,
    seed: int,
    per_level: int = 300,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Draw the sample, render crops and publish ``sample.json`` + ``crops/`` atomically."""

    scan = scan_candidates(candidates)
    log(f"scanned {scan.rows} rows, {len(scan.images)} photos")
    inspector = SourceInspector(artifact_root, scan, full=True)
    picks, excluded = select_review_sample(scan.images, seed, per_level, inspector)
    identity = {
        "schemaVersion": SAMPLE_SCHEMA,
        "seed": seed,
        "perLevel": per_level,
        "candidatesSha256": scan.sha256,
        "filter": split.SplitConfig(seed=seed).describe()["filter"],
        "picks": [[p.level, p.image_id, p.board_id] for p in picks],
    }
    sample_id = hashlib.sha256(dumps(identity)).hexdigest()
    if output.exists():
        existing = verify_sample(output)
        if existing["sampleId"] != sample_id:
            raise ValueError("LABEL_REVIEW_DIRECTORY_HOLDS_ANOTHER_SAMPLE")
        return existing
    rows = collect_rows(candidates, {p.image_id for p in picks})
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".label-review-", dir=output.parent))
    try:
        (stage / "crops").mkdir()
        items = []
        for number, pick in enumerate(picks, 1):
            row = next(r for r in rows[pick.image_id] if r["recognizedBoardId"] == pick.board_id)
            data = inspector.files[pick.image_id].path.read_bytes()
            if hashlib.sha256(data).hexdigest() != scan.images[pick.image_id].sha256:
                raise ValueError(f"SOURCE_CHANGED_DURING_PREPARE: {pick.image_id}")
            with Image.open(io.BytesIO(data)) as image:
                oriented = ImageOps.exif_transpose(image).convert("RGB")
            crop, width, height, nodes = render_crop(oriented, row["nodes"])
            name = f"{number:04d}.jpg"
            with (stage / "crops" / name).open("xb") as stream:
                stream.write(crop)
                stream.flush()
                os.fsync(stream.fileno())
            header = scan.sources[pick.image_id]
            items.append(
                {
                    "itemId": f"{number:04d}",
                    "level": pick.level,
                    "imageId": pick.image_id,
                    "recognizedBoardId": pick.board_id,
                    "positionIndex": row["positionIndex"],
                    "sequenceNumber": row["sequenceNumber"],
                    "familyId": scan.images[pick.image_id].family_id,
                    "familyDisplayName": header.family_display_name,
                    "sourceChecksumSha256": scan.images[pick.image_id].sha256,
                    "sourceRelativePath": header.relative_path,
                    "sourceNodes": row["nodes"],
                    "crop": f"crops/{name}",
                    "cropSha256": hashlib.sha256(crop).hexdigest(),
                    "cropWidth": width,
                    "cropHeight": height,
                    "cropNodes": nodes,
                }
            )
            if number % 100 == 0:
                log(f"rendered {number}/{len(picks)} crops")
        sample = {
            **identity,
            "sampleId": sample_id,
            "coordinateSpace": COORDINATE_SPACE,
            "integrityExclusions": [
                {"imageId": i, "reason": r} for i, r in sorted(excluded.items())
            ],
            "population": {
                level: len(ids) for level, ids in review_population(scan.images).items()
            },
            "items": items,
        }
        with (stage / _SAMPLE).open("xb") as stream:
            stream.write(dumps(sample))
            stream.flush()
            os.fsync(stream.fileno())
        verify_sample(stage)
        stage.rename(output)
        return verify_sample(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def verify_sample(root: Path) -> dict[str, Any]:
    sample: dict[str, Any] = json.loads((root / _SAMPLE).read_bytes())
    if sample.get("schemaVersion") != SAMPLE_SCHEMA:
        raise ValueError("LABEL_REVIEW_SAMPLE_UNSUPPORTED")
    identity = {
        key: sample[key]
        for key in ("schemaVersion", "seed", "perLevel", "candidatesSha256", "filter", "picks")
    }
    if hashlib.sha256(dumps(identity)).hexdigest() != sample["sampleId"]:
        raise ValueError("LABEL_REVIEW_SAMPLE_IDENTITY_MISMATCH")
    for item in sample["items"]:
        path = root / item["crop"]
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["cropSha256"]:
            raise ValueError(f"LABEL_REVIEW_CROP_CHECKSUM_MISMATCH: {item['itemId']}")
    return sample


def _atomic_write(path: Path, data: bytes) -> None:
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class RevisionConflictError(ValueError):
    pass


class ReviewStore:
    """Decisions of one published sample; ``history.jsonl`` is the source of truth."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.sample = verify_sample(root)
        self.items = {str(item["itemId"]): item for item in self.sample["items"]}
        self.lock = threading.Lock()
        self.decisions: dict[str, str] = {}
        self.revision = 0
        self._load()

    def _load(self) -> None:
        path = self.root / _HISTORY
        if not path.exists():
            self._write_decisions()
            return
        data = path.read_bytes()
        complete, _, torn = data.rpartition(b"\n")
        if torn:
            # A crash in the middle of an append leaves an unterminated last line.
            with path.open("r+b") as stream:
                stream.truncate(len(complete) + 1 if complete else 0)
                stream.flush()
                os.fsync(stream.fileno())
        for line in complete.split(b"\n") if complete else []:
            event = json.loads(line)
            if event.get("sampleId") != self.sample["sampleId"]:
                raise ValueError("LABEL_REVIEW_HISTORY_FOREIGN_SAMPLE")
            if event.get("revision") != self.revision + 1 or event.get("itemId") not in self.items:
                raise ValueError("LABEL_REVIEW_HISTORY_CORRUPT")
            self._apply(event["itemId"], event.get("decision"))
            self.revision = event["revision"]
        self._write_decisions()

    def _apply(self, item_id: str, decision: str | None) -> None:
        if decision is None:
            self.decisions.pop(item_id, None)
        elif decision in DECISIONS:
            self.decisions[item_id] = decision
        else:
            raise ValueError("LABEL_REVIEW_DECISION_INVALID")

    def _write_decisions(self) -> None:
        _atomic_write(
            self.root / _DECISIONS,
            dumps(
                {
                    "schemaVersion": DECISIONS_SCHEMA,
                    "sampleId": self.sample["sampleId"],
                    "revision": self.revision,
                    "decisions": dict(sorted(self.decisions.items())),
                }
            ),
        )

    def decide(self, item_id: str, decision: str | None, base_revision: int) -> None:
        with self.lock:
            if item_id not in self.items:
                raise KeyError(item_id)
            if decision is not None and decision not in DECISIONS:
                raise ValueError("LABEL_REVIEW_DECISION_INVALID")
            if base_revision != self.revision:
                raise RevisionConflictError("LABEL_REVIEW_REVISION_CONFLICT")
            event = {
                "revision": self.revision + 1,
                "sampleId": self.sample["sampleId"],
                "itemId": item_id,
                "decision": decision,
                "previous": self.decisions.get(item_id),
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            with (self.root / _HISTORY).open("ab") as stream:
                stream.write(dumps(event))
                stream.flush()
                os.fsync(stream.fileno())
            self._apply(item_id, decision)
            self.revision += 1
            self._write_decisions()

    def summary(self) -> dict[str, Any]:
        with self.lock:
            result = summarize(self.sample["items"], self.decisions)
            result.update(sampleId=self.sample["sampleId"], revision=self.revision)
            return result

    def write_summary(self) -> dict[str, Any]:
        result = self.summary()
        _atomic_write(self.root / _SUMMARY, dumps(result))
        return result

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "sampleId": self.sample["sampleId"],
                "revision": self.revision,
                "decisions": dict(self.decisions),
                "items": [
                    {
                        "itemId": item["itemId"],
                        "crop": item["crop"],
                        "width": item["cropWidth"],
                        "height": item["cropHeight"],
                        "nodes": item["cropNodes"],
                    }
                    for item in self.sample["items"]
                ],
            }


class LoopbackBoundary(BaseHTTPMiddleware):
    """Only ``127.0.0.1``/``localhost`` on the served port; writes need the own origin."""

    def __init__(self, app: Any, port: int) -> None:
        super().__init__(app)
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.origins = {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("host") not in self.hosts:
            return Response("HOST_FORBIDDEN", 403)
        origin = request.headers.get("origin")
        if origin is not None and origin not in self.origins:
            return Response("ORIGIN_FORBIDDEN", 403)
        if request.method not in {"GET", "HEAD"}:
            if origin not in self.origins:
                return Response("ORIGIN_REQUIRED", 403)
            content_type = request.headers.get("content-type", "").split(";", 1)[0].strip()
            if content_type != "application/json":
                return Response("JSON_REQUIRED", 415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response


class DecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    decision: str | None
    baseRevision: int


def create_review_app(store: ReviewStore, port: int = DEFAULT_PORT) -> FastAPI:
    application = FastAPI(title="Label review", docs_url=None, redoc_url=None, openapi_url=None)
    application.add_middleware(LoopbackBoundary, port=port)

    @application.get("/", response_class=HTMLResponse)
    def page() -> str:
        return PAGE

    @application.get("/api/state")
    def state() -> dict[str, Any]:
        return store.state()

    @application.get("/api/summary")
    def summary() -> dict[str, Any]:
        return store.summary()

    @application.post("/api/decisions")
    def decide(body: DecisionRequest) -> dict[str, Any]:
        try:
            store.decide(body.itemId, body.decision, body.baseRevision)
        except KeyError as error:
            raise HTTPException(404, "ITEM_NOT_FOUND") from error
        except RevisionConflictError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return store.state()

    @application.get("/crops/{name}")
    def crop(name: str) -> Response:
        if not _CROP_NAME.match(name):
            raise HTTPException(404, "CROP_NOT_FOUND")
        path = store.root / "crops" / name
        if not path.is_file():
            raise HTTPException(404, "CROP_NOT_FOUND")
        return Response(
            path.read_bytes(),
            media_type="image/jpeg",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    return application


PAGE: Final = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Przegląd etykiet siatek</title>
<style>
:root { color-scheme: light dark; --bg:#f4f4f2; --fg:#1d1d1b; --muted:#6b6b66; --good:#1f7a3a;
  --bad:#b3261e; --skip:#8a6d00; --panel:#ffffff; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe6; --muted:#a3a29b;
  --panel:#22221f; --good:#5cc27c; --bad:#ff8a80; --skip:#e3c35a; } }
body { margin:0; font:15px/1.4 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
header, footer { padding:8px 16px; display:flex; gap:16px; flex-wrap:wrap; align-items:center; }
main { display:flex; justify-content:center; padding:0 16px; }
.stage { position:relative; line-height:0; }
.stage img { display:block; width:auto; height:auto;
  max-width:min(calc(100vw - 32px), 1200px); max-height:calc(100vh - 140px); }
.stage svg { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
.badge { padding:2px 10px; border-radius:12px; background:var(--panel); font-weight:600; }
.good { color:var(--good); } .bad { color:var(--bad); } .unreadable { color:var(--skip); }
kbd { border:1px solid var(--muted); border-radius:4px; padding:0 5px; }
.muted { color:var(--muted); } pre { background:var(--panel); padding:8px; overflow:auto; }
</style></head><body>
<header><strong>Przegląd etykiet siatek 5 × 3</strong>
<span id="pos" class="badge"></span><span id="current" class="badge"></span>
<span id="progress" class="muted"></span><span id="error" class="bad"></span></header>
<main><div class="stage" id="stage">
<img id="crop" alt="wycinek planszy"><svg id="grid"></svg></div></main>
<footer><span><kbd>G</kbd>/<kbd>1</kbd> dobra</span><span><kbd>Z</kbd>/<kbd>2</kbd> zła</span>
<span><kbd>N</kbd>/<kbd>3</kbd> nie da się ocenić</span><span><kbd>→</kbd> pomiń</span>
<span><kbd>←</kbd> wstecz</span><span><kbd>U</kbd> cofnij decyzję</span>
<span><kbd>H</kbd> ukryj/pokaż siatkę</span><span><kbd>S</kbd> podsumowanie</span></footer>
<section id="summary" hidden style="padding:0 16px"><pre id="summaryText"></pre></section>
<script>
const LABELS = {good: "dobra", bad: "zła", unreadable: "nie da się ocenić"};
let state = null, index = 0, gridVisible = true, busy = false;
const $ = (id) => document.getElementById(id);
function firstUndecided(from) {
  const open = (i) => !state.decisions[state.items[i].itemId];
  for (let i = from; i < state.items.length; i++) if (open(i)) return i;
  for (let i = 0; i < from; i++) if (open(i)) return i;
  return Math.min(from, state.items.length - 1);
}
function render() {
  const item = state.items[index];
  const decision = state.decisions[item.itemId];
  $("pos").textContent = `${index + 1} / ${state.items.length}`;
  $("current").textContent = decision ? LABELS[decision] : "bez decyzji";
  $("current").className = "badge " + (decision || "");
  const done = Object.keys(state.decisions).length;
  $("progress").textContent = `ocenione: ${done} / ${state.items.length}`;
  $("crop").src = "/" + item.crop;
  const svg = $("grid");
  svg.setAttribute("viewBox", `0 0 ${item.width} ${item.height}`);
  const n = item.nodes, lines = [];
  for (let r = 0; r < 4; r++) lines.push(n.slice(r * 6, r * 6 + 6));
  for (let c = 0; c < 6; c++) lines.push([0, 1, 2, 3].map((r) => n[r * 6 + c]));
  const style = 'fill="none" stroke="#ff00ff" stroke-width="2" vector-effect="non-scaling-stroke"';
  const points = (l) => l.map((p) => p.join(",")).join(" ");
  svg.innerHTML = gridVisible
    ? lines.map((l) => `<polyline ${style} points="${points(l)}"/>`).join("")
    : "";
}
async function load() {
  const response = await fetch("/api/state", {cache: "no-store"});
  state = await response.json();
}
async function decide(decision) {
  if (busy) return;
  busy = true; $("error").textContent = "";
  const item = state.items[index];
  try {
    const response = await fetch("/api/decisions", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({itemId: item.itemId, decision, baseRevision: state.revision})});
    if (!response.ok) {
      $("error").textContent = `Zapis odrzucony (${response.status}); odświeżono stan.`;
      await load();
    } else {
      state = await response.json();
      if (decision) index = firstUndecided(Math.min(index + 1, state.items.length - 1));
    }
  } catch (error) {
    $("error").textContent = "Brak połączenia z serwerem przeglądu; decyzja nie została zapisana.";
  } finally { busy = false; render(); }
}
async function toggleSummary() {
  const section = $("summary");
  section.hidden = !section.hidden;
  if (!section.hidden) {
    const data = await (await fetch("/api/summary", {cache: "no-store"})).json();
    $("summaryText").textContent = JSON.stringify(data.levels, null, 2);
  }
}
document.addEventListener("keydown", (event) => {
  if (!state || event.ctrlKey || event.metaKey || event.altKey) return;
  const key = event.key.toLowerCase();
  if (key === "g" || key === "1") decide("good");
  else if (key === "z" || key === "2") decide("bad");
  else if (key === "n" || key === "3") decide("unreadable");
  else if (key === "u" || key === "delete") decide(null);
  else if (key === "arrowright") { index = Math.min(index + 1, state.items.length - 1); render(); }
  else if (key === "arrowleft" || key === "backspace") { index = Math.max(index - 1, 0); render(); }
  else if (key === "h") { gridVisible = !gridVisible; render(); }
  else if (key === "s") toggleSummary();
  else return;
  event.preventDefault();
});
load().then(() => { index = firstUndecided(0); render(); });
</script></body></html>
"""


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="loopback review page on 127.0.0.1")
    serve.add_argument("--review", type=Path, required=True)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    report = commands.add_parser("report", help="write and print summary.json")
    report.add_argument("--review", type=Path, required=True)
    arguments = parser.parse_args(argv)
    store = ReviewStore(arguments.review.resolve())
    if arguments.command == "report":
        print(json.dumps(store.write_summary(), indent=2, ensure_ascii=False))
        return
    import uvicorn

    uvicorn.run(create_review_app(store, arguments.port), host="127.0.0.1", port=arguments.port)


if __name__ == "__main__":
    main()
