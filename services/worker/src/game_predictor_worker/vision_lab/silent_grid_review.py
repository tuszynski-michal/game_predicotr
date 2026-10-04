"""Operator review of the TASK-0831 silent-grid suspects (loopback page, port 8107).

``python -m game_predictor_worker.vision_lab.silent_grid_review serve --audit <dir>``
``python -m game_predictor_worker.vision_lab.silent_grid_review report --audit <dir>``

The page shows the comparison images of ``cases.json`` (saved grid red, network green)
with the identifiers of the existing grid-correction tools, and records one verdict per
item: ``network`` (the network is right, the saved grid is wrong), ``saved`` (the saved
grid is right) or ``unsure``. Verdicts are appended to ``review/history.jsonl`` (fsync,
source of truth, bound to the SHA-256 of ``cases.json``) and mirrored to
``review/decisions.json``. Nothing is written to the database: a correction is made by
the operator in the existing tools. ``label_review`` was not reused because its sample,
crops and verdicts (good/bad/unreadable on one grid) are a different contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict

from .label_review import LoopbackBoundary

VERDICTS: Final = ("network", "saved", "unsure")
DEFAULT_PORT: Final = 8107
_CASE_NAME: Final = re.compile(r"^[nps][0-9]{5}\.jpg$")


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    with temporary.open("wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _dumps(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


class RevisionConflictError(ValueError):
    pass


class VerdictStore:
    def __init__(self, audit: Path) -> None:
        self.audit = audit
        content = (audit / "cases.json").read_bytes()
        self.cases_sha256 = hashlib.sha256(content).hexdigest()
        self.items: list[dict[str, Any]] = json.loads(content)["items"]
        self.by_id = {str(item["itemId"]): item for item in self.items}
        self.root = audit / "review"
        self.root.mkdir(exist_ok=True)
        self.lock = threading.Lock()
        self.verdicts: dict[str, str] = {}
        self.revision = 0
        self._load()

    def _load(self) -> None:
        path = self.root / "history.jsonl"
        if path.exists():
            data = path.read_bytes()
            complete, _, torn = data.rpartition(b"\n")
            if torn:
                with path.open("r+b") as stream:
                    stream.truncate(len(complete) + 1 if complete else 0)
                    stream.flush()
                    os.fsync(stream.fileno())
            for line in complete.split(b"\n") if complete else []:
                event = json.loads(line)
                if event.get("casesSha256") != self.cases_sha256:
                    raise ValueError("SILENT_GRID_REVIEW_HISTORY_FOREIGN_CASES")
                if event.get("revision") != self.revision + 1 or event["itemId"] not in self.by_id:
                    raise ValueError("SILENT_GRID_REVIEW_HISTORY_CORRUPT")
                self._apply(event["itemId"], event.get("verdict"))
                self.revision = event["revision"]
        self._mirror()

    def _apply(self, item_id: str, verdict: str | None) -> None:
        if verdict is None:
            self.verdicts.pop(item_id, None)
        elif verdict in VERDICTS:
            self.verdicts[item_id] = verdict
        else:
            raise ValueError("SILENT_GRID_REVIEW_VERDICT_INVALID")

    def _mirror(self) -> None:
        _atomic_write(
            self.root / "decisions.json",
            _dumps(
                {
                    "casesSha256": self.cases_sha256,
                    "revision": self.revision,
                    "verdicts": dict(sorted(self.verdicts.items())),
                }
            ),
        )

    def decide(self, item_id: str, verdict: str | None, base_revision: int) -> None:
        with self.lock:
            if item_id not in self.by_id:
                raise KeyError(item_id)
            if verdict is not None and verdict not in VERDICTS:
                raise ValueError("SILENT_GRID_REVIEW_VERDICT_INVALID")
            if base_revision != self.revision:
                raise RevisionConflictError("SILENT_GRID_REVIEW_REVISION_CONFLICT")
            event = {
                "revision": self.revision + 1,
                "casesSha256": self.cases_sha256,
                "itemId": item_id,
                "verdict": verdict,
                "previous": self.verdicts.get(item_id),
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            with (self.root / "history.jsonl").open("ab") as stream:
                stream.write(_dumps(event) + b"\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._apply(item_id, verdict)
            self.revision += 1
            self._mirror()

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {"revision": self.revision, "verdicts": dict(self.verdicts), "items": self.items}

    def summary(self) -> dict[str, Any]:
        with self.lock:
            table: dict[str, Counter[str]] = {}
            for item in self.items:
                verdict = self.verdicts.get(str(item["itemId"]), "open")
                table.setdefault(str(item["class"]), Counter())[verdict] += 1
            return {
                "casesSha256": self.cases_sha256,
                "revision": self.revision,
                "byClass": {k: dict(sorted(v.items())) for k, v in sorted(table.items())},
            }


class VerdictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    itemId: str
    verdict: str | None
    baseRevision: int


def create_app(store: VerdictStore, port: int = DEFAULT_PORT) -> FastAPI:
    application = FastAPI(
        title="Silent grid review", docs_url=None, redoc_url=None, openapi_url=None
    )
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

    @application.post("/api/verdicts")
    def decide(body: VerdictRequest) -> dict[str, Any]:
        try:
            store.decide(body.itemId, body.verdict, body.baseRevision)
        except KeyError as error:
            raise HTTPException(404, "ITEM_NOT_FOUND") from error
        except RevisionConflictError as error:
            raise HTTPException(409, str(error)) from error
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        return {"revision": store.revision, "verdicts": dict(store.verdicts)}

    @application.get("/cases/{name}")
    def case(name: str) -> Response:
        if not _CASE_NAME.match(name):
            raise HTTPException(404, "CASE_NOT_FOUND")
        path = store.audit / "cases" / name
        if not path.is_file():
            raise HTTPException(404, "CASE_NOT_FOUND")
        return Response(
            path.read_bytes(),
            media_type="image/jpeg",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    return application


PAGE: Final = """<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ciche błędy siatek 777</title>
<style>
:root { color-scheme: light dark; --bg:#f4f4f2; --fg:#1d1d1b; --muted:#6b6b66; --panel:#fff;
  --net:#1f7a3a; --saved:#b3261e; --unsure:#8a6d00; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe6; --muted:#a3a29b;
  --panel:#22221f; --net:#5cc27c; --saved:#ff8a80; --unsure:#e3c35a; } }
body { margin:0; font:14px/1.4 system-ui, sans-serif; background:var(--bg); color:var(--fg); }
header, footer { padding:6px 16px; display:flex; gap:14px; flex-wrap:wrap; align-items:center; }
main { display:flex; gap:16px; padding:0 16px; flex-wrap:wrap; }
img { max-width:min(calc(100vw - 32px), 1100px); max-height:calc(100vh - 120px); display:block; }
aside { flex:1 1 280px; min-width:260px; background:var(--panel); padding:8px 12px;
  border-radius:8px; overflow-wrap:anywhere; }
.badge { padding:2px 10px; border-radius:12px; background:var(--panel); font-weight:600; }
.network { color:var(--net); } .saved { color:var(--saved); } .unsure { color:var(--unsure); }
kbd { border:1px solid var(--muted); border-radius:4px; padding:0 5px; }
.muted { color:var(--muted); } code { font-size:12px; } dt { color:var(--muted); margin-top:4px; }
dd { margin:0; } a { color:inherit; }
</style></head><body>
<header><strong>Ciche błędy siatek 777</strong>
<label>Klasa <select id="filter"></select></label>
<span id="pos" class="badge"></span><span id="current" class="badge"></span>
<span id="progress" class="muted"></span><span id="error" class="saved"></span></header>
<main><div><img id="case" alt="porównanie siatek"></div><aside id="meta"></aside></main>
<footer><span><kbd>1</kbd> sieć ma rację (zapis zły)</span><span><kbd>2</kbd> zapis ma rację</span>
<span><kbd>3</kbd> nie wiem</span><span><kbd>→</kbd> dalej</span><span><kbd>←</kbd> wstecz</span>
<span><kbd>U</kbd> cofnij</span>
<span class="muted">czerwony = zapis, zielony = sieć run 1</span></footer>
<script>
const LABELS = {network: "sieć ma rację", saved: "zapis ma rację", unsure: "nie wiem"};
let state = null, items = [], index = 0, busy = false;
const $ = (id) => document.getElementById(id);
const ENTITIES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"};
const esc = (v) => String(v ?? "-").replace(/[&<>"]/g, (c) => ENTITIES[c]);
const num = (v) => v == null ? "-" : Number(v).toFixed(3);
function applyFilter() {
  const value = $("filter").value;
  items = state.items.filter((i) => value === "all" || i.class === value);
  index = Math.min(index, Math.max(items.length - 1, 0));
}
function render() {
  if (!items.length) { $("pos").textContent = "0 / 0"; return; }
  const item = items[index], verdict = state.verdicts[item.itemId];
  $("pos").textContent = `${index + 1} / ${items.length}`;
  $("current").textContent = verdict ? LABELS[verdict] : "bez oceny";
  $("current").className = "badge " + (verdict || "");
  const judged = Object.keys(state.verdicts).length;
  $("progress").textContent = `ocenione: ${judged} / ${state.items.length}`;
  $("case").src = "/" + item.image;
  const c = item.correction || {};
  const queue = c.reviewerCorrectionQueue
    ? `<a href="${esc(c.reviewerCorrectionQueue)}" target="_blank" rel="noopener">`
      + "kolejka korekty (Reviewer)</a>"
    : "-";
  $("meta").innerHTML = `<dl>
<dt>pozycja / klasa</dt><dd>${esc(item.itemId)} · ${esc(item.class)}</dd>
<dt>poziom etykiety</dt><dd>${esc(item.level)} (${esc(item.basis)})</dd>
<dt>NME / maks. / IoU</dt>
<dd>${num(item.nme)} / ${num(item.maxError)} / ${num(item.iou)}</dd>
<dt>przesunięcie → NME</dt>
<dd>${esc(JSON.stringify(item.shift))} → ${num(item.shiftNme)}</dd>
<dt>komórki z decyzją człowieka</dt>
<dd>${esc(item.humanDecidedCells)} / ${esc(item.cells)}</dd>
<dt>numer sekwencji · pozycja</dt>
<dd>${esc(c.sequenceNumber)} · ${esc(item.positionIndex)}</dd>
<dt>rodzina</dt><dd>${esc(item.family)} · rola ${esc(item.snapshotRole)}</dd>
<dt>sourceImageId</dt><dd><code>${esc(item.imageId)}</code></dd>
<dt>recognizedBoardId</dt><dd><code>${esc(c.recognizedBoardId)}</code></dd>
<dt>importJobId</dt><dd><code>${esc(c.importJobId)}</code></dd>
<dt>komórka do „Zła siatka”</dt><dd><code>${esc(c.gridIssueCellReviewId)}</code></dd>
<dt>korekta</dt><dd>${queue}</dd></dl>`;
}
async function load() {
  state = await (await fetch("/api/state", {cache: "no-store"})).json();
  const classes = ["all", ...new Set(state.items.map((i) => i.class))];
  const select = $("filter");
  if (!select.options.length) {
    const option = (c) => `<option value="${esc(c)}">${esc(c)}</option>`;
    select.innerHTML = classes.map(option).join("");
    select.onchange = () => { index = 0; applyFilter(); render(); select.blur(); };
  }
  applyFilter();
}
function nextOpen(from) {
  for (let i = from; i < items.length; i++) if (!state.verdicts[items[i].itemId]) return i;
  return Math.min(from, items.length - 1);
}
async function decide(verdict) {
  if (busy || !items.length) return;
  busy = true; $("error").textContent = "";
  const item = items[index];
  try {
    const response = await fetch("/api/verdicts", {method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({itemId: item.itemId, verdict, baseRevision: state.revision})});
    if (!response.ok) {
      $("error").textContent = `Zapis odrzucony (${response.status}); odświeżono stan.`;
      await load();
    } else {
      const result = await response.json();
      state.revision = result.revision; state.verdicts = result.verdicts;
      if (verdict) index = nextOpen(Math.min(index + 1, items.length - 1));
    }
  } catch (error) { $("error").textContent = "Brak połączenia; ocena nie została zapisana."; }
  finally { busy = false; render(); }
}
document.addEventListener("keydown", (event) => {
  if (!state || event.ctrlKey || event.metaKey || event.altKey) return;
  if (event.target.tagName === "SELECT") return;
  const key = event.key.toLowerCase();
  if (key === "1") decide("network");
  else if (key === "2") decide("saved");
  else if (key === "3") decide("unsure");
  else if (key === "u" || key === "delete") decide(null);
  else if (key === "arrowright") { index = Math.min(index + 1, items.length - 1); render(); }
  else if (key === "arrowleft") { index = Math.max(index - 1, 0); render(); }
  else return;
  event.preventDefault();
});
load().then(() => { index = nextOpen(0); render(); });
</script></body></html>
"""


def main(argv: Sequence[str] | None = None) -> None:
    root = argparse.ArgumentParser(prog="silent_grid_review")
    commands = root.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--audit", type=Path, required=True)
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)
    report = commands.add_parser("report")
    report.add_argument("--audit", type=Path, required=True)
    args = root.parse_args(argv)
    store = VerdictStore(args.audit)
    if args.command == "report":
        print(json.dumps(store.summary(), indent=1))
        return
    import uvicorn

    uvicorn.run(create_app(store, args.port), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
