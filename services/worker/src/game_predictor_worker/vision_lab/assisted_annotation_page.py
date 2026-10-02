"""Single-page operator UI of the assisted complete-photo annotation (TASK-0824).

The page is an embedded HTML/JS asset with Polish operator texts; its long lines are
data, not Python, hence the file-level E501 exemption.
"""

# ruff: noqa: E501

from typing import Final

PAGE: Final = r"""<!doctype html>
<html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kompletne zdjęcia – siatki</title>
<style>
:root { color-scheme: light dark; --bg:#f4f4f2; --fg:#1d1d1b; --muted:#6b6b66; --panel:#ffffff;
  --line:#d6d6d0; --ok:#1f7a3a; --bad:#b3261e; --warn:#8a6d00; }
@media (prefers-color-scheme: dark) { :root { --bg:#161615; --fg:#ecebe6; --muted:#a3a29b;
  --panel:#22221f; --line:#3a3a36; --ok:#5cc27c; --bad:#ff8a80; --warn:#e3c35a; } }
* { box-sizing:border-box; }
body { margin:0; font:14px/1.35 system-ui, sans-serif; background:var(--bg); color:var(--fg);
  height:100vh; display:flex; flex-direction:column; overflow:hidden; }
header { padding:6px 12px; display:flex; gap:14px; flex-wrap:wrap; align-items:center;
  border-bottom:1px solid var(--line); }
.layout { flex:1; display:flex; min-height:0; }
#stageWrap { flex:1; min-width:0; position:relative; background:#000; }
svg#stage { width:100%; height:100%; display:block; touch-action:none; user-select:none; }
aside { width:330px; overflow:auto; padding:8px 12px; border-left:1px solid var(--line);
  background:var(--panel); }
.badge { padding:1px 8px; border-radius:10px; background:var(--panel); border:1px solid var(--line);
  font-weight:600; }
.ok { color:var(--ok); } .bad { color:var(--bad); } .warn { color:var(--warn); }
.muted { color:var(--muted); }
#boards div { padding:3px 4px; border-radius:4px; cursor:pointer; }
#boards div.sel { outline:2px solid #ff00ff; }
kbd { border:1px solid var(--muted); border-radius:4px; padding:0 4px; font-size:12px; }
#message { min-height:2.6em; white-space:pre-wrap; }
input[type=number] { width:64px; font-size:16px; }
button { font:inherit; }
dl.keys { display:grid; grid-template-columns:auto 1fr; gap:2px 8px; margin:6px 0; }
dl.keys dt { white-space:nowrap; } dl.keys dd { margin:0; }
</style></head><body>
<header>
  <strong>Kompletne zdjęcia: siatki 5 × 3</strong>
  <span id="pos" class="badge"></span>
  <span id="photoState" class="badge"></span>
  <span id="progress" class="muted"></span>
  <span id="timing" class="muted"></span>
</header>
<div class="layout">
  <div id="stageWrap"><svg id="stage" xmlns="http://www.w3.org/2000/svg"
    preserveAspectRatio="xMidYMid meet"><image id="photo" x="0" y="0"/><g id="overlay"></g></svg></div>
  <aside>
    <div id="file" class="muted"></div>
    <p id="message"></p>
    <div><button id="retry" hidden>Ponów identyczne żądanie (Y)</button></div>
    <h3>Plansze</h3>
    <div id="boards"></div>
    <h3>Zdjęcie</h3>
    <label>Liczba plansz na zdjęciu:
      <input id="count" type="number" min="1" max="9" step="1"></label>
    <button id="complete">Zatwierdź zdjęcie</button>
    <p class="muted" id="completeHint"></p>
    <h3>Klawisze</h3>
    <dl class="keys">
      <dt><kbd>A</kbd> / <kbd>Enter</kbd></dt><dd>akceptuj zaznaczoną planszę</dd>
      <dt><kbd>Tab</kbd> / <kbd>Shift+Tab</kbd></dt><dd>następna / poprzednia plansza</dd>
      <dt>przeciągnij narożnik</dt><dd>korekta siatki (liczona projekcyjnie)</dd>
      <dt><kbd>1</kbd>–<kbd>9</kbd></dt><dd>numer pozycji planszy (dla nowych)</dd>
      <dt><kbd>N</kbd></dt><dd>nowa plansza: kliknij 4 narożniki LG, PG, PD, LD</dd>
      <dt><kbd>X</kbd> / <kbd>Delete</kbd></dt><dd>odrzuć propozycję / usuń planszę</dd>
      <dt><kbd>R</kbd></dt><dd>cofnij akceptację planszy</dd>
      <dt><kbd>U</kbd> / <kbd>Ctrl+Z</kbd></dt><dd>cofnij ostatnie przesunięcie narożnika</dd>
      <dt><kbd>C</kbd></dt><dd>wpisz liczbę plansz; <kbd>Enter</kbd> zatwierdza zdjęcie</dd>
      <dt><kbd>Spacja</kbd> / <kbd>PageDown</kbd></dt><dd>następne zdjęcie</dd>
      <dt><kbd>PageUp</kbd></dt><dd>poprzednie zdjęcie</dd>
      <dt><kbd>J</kbd></dt><dd>następne niekompletne zdjęcie</dd>
      <dt><kbd>Z</kbd></dt><dd>powiększenie planszy / całe zdjęcie</dd>
      <dt><kbd>H</kbd></dt><dd>ukryj / pokaż siatki</dd>
      <dt><kbd>O</kbd></dt><dd>pokaż odrzucone propozycje (<kbd>X</kbd> przywraca)</dd>
      <dt><kbd>Esc</kbd></dt><dd>przerwij rysowanie</dd>
    </dl>
    <p class="muted">Kolory: zielony – zaakceptowana, ciemnozielony – zapis z wcześniejszej
    pracy w labie (zablokowany), pomarańczowy – propozycja sieci (nie jest etykietą),
    żółty – cofnięta akceptacja, różowy – zmieniona lub nowa, szary – odrzucona.</p>
  </aside>
</div>
<script>
"use strict";
const $ = (id) => document.getElementById(id);
const SVGNS = "http://www.w3.org/2000/svg";
const CORNERS = [0, 5, 23, 18];
const GAMES = {mumie: "Mumie", blazing: "Blazing", gang: "Gang"};
const ORIGINS = {proposal_unchanged: "propozycja bez zmian", proposal_corrected: "propozycja poprawiona",
  manual: "narysowana ręcznie", existing_lab: "wcześniejsza praca w labie"};
const MESSAGES = {
  ASSISTED_EXISTING_BOARD_LOCKED: "Ta pozycja ma zapis z wcześniejszej pracy w labie; zmienisz ją tylko w edytorze T03.",
  GEOMETRY_OUTSIDE_SOURCE: "Siatka wychodzi poza zdjęcie – przesuń narożniki do kadru.",
  ASSISTED_BOARD_COUNT_MISMATCH: "Liczba plansz nie zgadza się z liczbą zaakceptowanych siatek.",
  ASSISTED_BOARD_NOT_ACCEPTED: "Na zdjęciu jest plansza z cofniętą akceptacją – zaakceptuj ją albo usuń.",
  ASSISTED_QUAD_INVALID: "Nieprawidłowy czworokąt – narożniki w kolejności LG, PG, PD, LD.",
  ASSISTED_BOARD_REVISION_CONFLICT: "Pozycja zmieniła się w innym miejscu – wczytano aktualny stan.",
  ANNOTATION_REVISION_CONFLICT: "Magazyn zmienił się w innym miejscu – wczytano aktualny stan.",
  ASSISTED_PHOTO_GEOMETRY_CHANGED: "Siatki zdjęcia zmieniły się – wczytano aktualny stan.",
  ANNOTATION_STORE_BUSY: "Magazyn anotacji zajęty (inny proces) – spróbuj ponownie.",
  PHOTO_CORRECTIONS_REQUIRED: "Zdjęcie ma oznaczenia „Do poprawy” z przeglądu T03d – rozwiąż je w edytorze labu.",
  ASSISTED_PROPOSAL_ALREADY_USED: "Ta propozycja jest już zapisana na innej pozycji.",
  ASSISTED_PHOTO_ALREADY_COMPLETE: "Zdjęcie jest już kompletne.",
  ASSISTED_BOARD_COUNT_REQUIRED: "Wpisz liczbę plansz na zdjęciu.",
  ASSISTED_HOLDOUT_FORBIDDEN: "Reels i Treasure są wyłączone z tego przepływu.",
  ASSISTED_GAME_FORBIDDEN: "Ta gra nie należy do tego przepływu.",
};
const RELOAD = new Set(["ANNOTATION_REVISION_CONFLICT", "ASSISTED_BOARD_REVISION_CONFLICT",
  "ASSISTED_PHOTO_GEOMETRY_CHANGED", "ASSISTED_EXISTING_BOARD_LOCKED", "ASSISTED_PROPOSAL_STATE_UNCHANGED",
  "ASSISTED_PROPOSAL_ALREADY_USED", "ASSISTED_PHOTO_ALREADY_COMPLETE", "ASSISTED_BOARD_ALREADY_REMOVED",
  "ASSISTED_BOARD_NOT_FOUND"]);

let queue = null, photo = null, index = 0, items = [], sel = -1;
let zoom = true, showGrid = true, showDismissed = false, busy = false, pending = null;
let drawing = null, drag = null;
let lastActivity = performance.now(), unsent = [];

function store(key, value) { try { localStorage.setItem(key, value); } catch (e) {} }
function recall(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
function say(text, kind) { $("message").textContent = text || ""; $("message").className = kind || ""; }
function fmt(ms) {
  if (ms == null) return "–";
  const s = Math.round(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
function requestId() {
  const raw = (crypto.randomUUID ? crypto.randomUUID() : String(Math.random()) + Date.now());
  return "assist-" + raw.replace(/[^a-zA-Z0-9]/g, "").slice(0, 40);
}

// --- activity: gaps up to 30 s count as active time --------------------------------------
function activity() {
  const now = performance.now(), gap = now - lastActivity;
  lastActivity = now;
  if (gap <= 0 || gap > 30000) return;
  const last = unsent.length - 1;
  if (last >= 0 && unsent[last] + gap <= 30000) unsent[last] += Math.round(gap);
  else unsent.push(Math.round(gap));
}
for (const name of ["pointermove", "pointerdown", "keydown", "wheel"])
  window.addEventListener(name, activity, {passive: true, capture: true});
function unsentMs() { return unsent.reduce((a, b) => a + b, 0); }

// --- projective grid ----------------------------------------------------------------------
function solve(A, b) {
  const n = b.length, M = A.map((row, i) => [...row, b[i]]);
  for (let c = 0; c < n; c++) {
    let p = c;
    for (let r = c + 1; r < n; r++) if (Math.abs(M[r][c]) > Math.abs(M[p][c])) p = r;
    [M[c], M[p]] = [M[p], M[c]];
    if (Math.abs(M[c][c]) < 1e-12) return null;
    for (let r = 0; r < n; r++) {
      if (r === c) continue;
      const f = M[r][c] / M[c][c];
      for (let k = c; k <= n; k++) M[r][k] -= f * M[c][k];
    }
  }
  return M.map((row, i) => row[n] / row[i]);
}
function gridNodes(corners) {
  const src = [[0, 0], [5, 0], [5, 3], [0, 3]], A = [], b = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i], [u, v] = corners[i];
    A.push([x, y, 1, 0, 0, 0, -u * x, -u * y]); b.push(u);
    A.push([0, 0, 0, x, y, 1, -v * x, -v * y]); b.push(v);
  }
  const h = solve(A, b);
  if (!h) return null;
  const out = [];
  for (let r = 0; r < 4; r++) for (let c = 0; c < 6; c++) {
    const w = h[6] * c + h[7] * r + 1;
    out.push([(h[0] * c + h[1] * r + h[2]) / w, (h[3] * c + h[4] * r + h[5]) / w]);
  }
  return out;
}
const cornersOf = (nodes) => CORNERS.map((i) => [nodes[i][0], nodes[i][1]]);
const centre = (c) => [c.reduce((s, p) => s + p[0], 0) / 4, c.reduce((s, p) => s + p[1], 0) / 4];

// --- items --------------------------------------------------------------------------------
function buildItems() {
  items = [];
  for (const b of photo.boards) {
    if (b.presence !== "present" || !b.nodes.length) continue;
    items.push({kind: "saved", slot: b.board_index, revision: b.revision, status: b.status,
      locked: b.locked, origin: b.origin, proposal_id: b.proposal_id, nodes: b.nodes,
      corners: cornersOf(b.nodes), edited: false, undo: []});
  }
  for (const p of photo.proposals) {
    if (p.used_by != null || p.covered_by != null) continue;
    if (p.dismissed && !showDismissed) continue;
    items.push({kind: p.dismissed ? "dismissed" : "proposal", slot: null, manualSlot: false,
      proposal_id: p.proposal_id, score: p.score, reasons: p.reasons, nodes: p.nodes,
      corners: cornersOf(p.nodes), edited: false, undo: []});
  }
  assignSlots();
  sortItems();
}
function sortItems() {
  items.sort((a, b) => {
    const ca = centre(a.corners), cb = centre(b.corners);
    const h = Math.max(1, Math.hypot(a.corners[3][0] - a.corners[0][0], a.corners[3][1] - a.corners[0][1]) / 2);
    return Math.abs(ca[1] - cb[1]) > h ? ca[1] - cb[1] : ca[0] - cb[0];
  });
}
function median(values) { const s = [...values].sort((a, b) => a - b); return s[Math.floor(s.length / 2)] || 1; }
function ranks(values) {
  const order = values.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]);
  const out = new Array(values.length); let rank = 0;
  order.forEach(([v, i], k) => { if (k > 0 && v - order[k - 1][0] > 0.5) rank++; out[i] = rank; });
  return [out, rank + 1];
}
function assignSlots() {
  const shown = items.filter((it) => it.kind !== "dismissed");
  if (!shown.length) return;
  let ux = [0, 0], vy = [0, 0];
  const ws = [], hs = [];
  for (const it of shown) {
    const c = it.corners;
    const a = [(c[1][0] - c[0][0] + c[2][0] - c[3][0]) / 2, (c[1][1] - c[0][1] + c[2][1] - c[3][1]) / 2];
    const b = [(c[3][0] - c[0][0] + c[2][0] - c[1][0]) / 2, (c[3][1] - c[0][1] + c[2][1] - c[1][1]) / 2];
    const la = Math.hypot(...a) || 1, lb = Math.hypot(...b) || 1;
    ux = [ux[0] + a[0] / la, ux[1] + a[1] / la]; vy = [vy[0] + b[0] / lb, vy[1] + b[1] / lb];
    ws.push(la); hs.push(lb);
  }
  const nu = Math.hypot(...ux) || 1, nv = Math.hypot(...vy) || 1;
  ux = [ux[0] / nu, ux[1] / nu]; vy = [vy[0] / nv, vy[1] / nv];
  const W = median(ws), H = median(hs);
  const cs = shown.map((it) => centre(it.corners));
  const [cols, nCols] = ranks(cs.map((p) => (p[0] * ux[0] + p[1] * ux[1]) / W));
  const [rows, nRows] = ranks(cs.map((p) => (p[0] * vy[0] + p[1] * vy[1]) / H));
  const votes = {};
  shown.forEach((it, i) => {
    if (it.kind !== "saved") return;
    const key = `${Math.floor(it.slot / 3) - rows[i]},${(it.slot % 3) - cols[i]}`;
    votes[key] = (votes[key] || 0) + 1;
  });
  let offset = [0, 0], best = 0;
  for (const [key, n] of Object.entries(votes)) if (n > best) { best = n; offset = key.split(",").map(Number); }
  shown.forEach((it, i) => {
    if (it.kind === "saved" || it.manualSlot) return;
    const r = rows[i] + offset[0], c = cols[i] + offset[1];
    it.slot = (nRows <= 3 && nCols <= 3 && r >= 0 && r < 3 && c >= 0 && c < 3) ? r * 3 + c : null;
  });
}
function slotConflict(it) {
  if (it.slot == null) return true;
  return items.some((o) => o !== it && o.kind !== "dismissed" && o.slot === it.slot);
}
function current() { return sel >= 0 && sel < items.length ? items[sel] : null; }
function selectFirstOpen() {
  const open = items.findIndex((it) => it.kind === "proposal" || it.kind === "new" ||
    (it.kind === "saved" && it.status === "revoked"));
  sel = open >= 0 ? open : (items.length ? 0 : -1);
}

// --- rendering ----------------------------------------------------------------------------
function colour(it) {
  if (it.kind === "dismissed") return "#9e9e9e";
  if (it.edited || it.kind === "new") return "#ff40ff";
  if (it.kind === "proposal") return "#ff9100";
  if (it.status === "revoked") return "#ffd600";
  if (it.locked) return "#00a040";
  return "#00e676";
}
function el(name, attrs) {
  const node = document.createElementNS(SVGNS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}
function viewBox() {
  const W = photo.width || 1, H = photo.height || 1, it = current();
  if (!zoom || !it || drawing) return [0, 0, W, H];
  const xs = it.corners.map((p) => p[0]), ys = it.corners.map((p) => p[1]);
  const w = Math.max(...xs) - Math.min(...xs), h = Math.max(...ys) - Math.min(...ys);
  const m = Math.max(w, h) * 0.35;
  return [Math.min(...xs) - m, Math.min(...ys) - m, w + 2 * m, h + 2 * m];
}
function render() {
  if (!photo) return;
  const svg = $("stage"), g = $("overlay");
  const vb = viewBox();
  svg.setAttribute("viewBox", vb.join(" "));
  const unit = vb[2] / 900;
  g.textContent = "";
  items.forEach((it, i) => {
    const selected = i === sel, col = colour(it);
    if (showGrid || selected) {
      const lines = [];
      for (let r = 0; r < 4; r++) lines.push(it.nodes.slice(r * 6, r * 6 + 6));
      for (let c = 0; c < 6; c++) lines.push([0, 1, 2, 3].map((r) => it.nodes[r * 6 + c]));
      for (const line of lines) g.appendChild(el("polyline", {points: line.map((p) => p.join(",")).join(" "),
        fill: "none", stroke: col, "stroke-width": selected ? 3 : 1.6, "vector-effect": "non-scaling-stroke",
        "stroke-dasharray": it.kind === "proposal" || it.kind === "dismissed" ? "6 4" : ""}));
    }
    const [cx, cy] = centre(it.corners);
    const label = el("text", {x: cx, y: cy, fill: col, "font-size": 26 * unit, "font-weight": 700,
      "text-anchor": "middle", "dominant-baseline": "middle", stroke: "#000", "stroke-width": 0.8 * unit,
      "paint-order": "stroke", "pointer-events": "none"});
    label.textContent = (it.slot == null ? "?" : String(it.slot + 1)) + (it.locked ? " L" : "");
    g.appendChild(label);
    if (selected && !it.locked && it.kind !== "dismissed") {
      it.corners.forEach((p, k) => {
        const handle = el("circle", {cx: p[0], cy: p[1], r: 9 * unit, fill: "rgba(255,0,255,0.35)",
          stroke: "#ff00ff", "stroke-width": 2, "vector-effect": "non-scaling-stroke", style: "cursor:move"});
        handle.addEventListener("pointerdown", (event) => startDrag(event, k));
        g.appendChild(handle);
      });
    }
  });
  if (drawing) for (const p of drawing) g.appendChild(el("circle", {cx: p[0], cy: p[1], r: 6 * unit, fill: "#ff00ff"}));
  renderPanel();
}
function itemText(it) {
  const slot = it.slot == null ? "?" : it.slot + 1;
  const conflict = it.kind !== "saved" && it.kind !== "dismissed" && slotConflict(it) ? " – ustaw pozycję 1–9" : "";
  if (it.kind === "saved") {
    const state = it.locked ? "zaakceptowana wcześniej (lab, zablokowana)"
      : it.status === "revoked" ? "cofnięta akceptacja" : "zaakceptowana";
    return `Poz. ${slot}: ${state} · ${ORIGINS[it.origin] || it.origin}${it.edited ? " · zmieniona" : ""}`;
  }
  if (it.kind === "dismissed") return `Odrzucona propozycja (${it.score})`;
  if (it.kind === "new") return `Poz. ${slot}: nowa plansza${conflict}`;
  const flags = it.reasons.filter((r) => r !== "NEURAL_GRID_GATE_UNCALIBRATED").join(", ");
  return `Poz. ${slot}: propozycja ${it.score}${it.edited ? " · poprawiona" : ""}${flags ? " · " + flags : ""}${conflict}`;
}
function renderPanel() {
  const list = $("boards");
  list.textContent = "";
  items.forEach((it, i) => {
    const row = document.createElement("div");
    row.textContent = itemText(it);
    row.style.color = colour(it) === "#00e676" || colour(it) === "#00a040" ? "var(--ok)" : "";
    if (i === sel) row.className = "sel";
    row.addEventListener("click", () => { sel = i; render(); });
    list.appendChild(row);
  });
  const accepted = items.filter((it) => it.kind === "saved" && it.status !== "revoked").length;
  const open = items.filter((it) => it.kind === "proposal" || it.kind === "new").length;
  $("completeHint").textContent = photo.complete
    ? `Zdjęcie kompletne: ${photo.confirmed_board_count} plansz.`
    : `Zaakceptowane: ${accepted}; nierozstrzygnięte propozycje: ${open}. Propozycje nie są etykietami.`;
  $("photoState").textContent = photo.complete ? "kompletne" : "niekompletne";
  $("photoState").className = "badge " + (photo.complete ? "ok" : "warn");
  $("pos").textContent = `Zdjęcie ${index + 1} / ${photo.total} · ${GAMES[photo.game]}`;
  $("file").textContent = photo.filename + (photo.training_set_files.length ? "  ←  " + photo.training_set_files.join(", ") : "  (wcześniejsza anotacja labu)");
  $("retry").hidden = !pending;
  renderProgress();
}
function renderProgress() {
  if (!queue) return;
  const parts = Object.entries(queue.games).map(([k, g]) => `${GAMES[k]} ${g.complete}/${g.total}`);
  $("progress").textContent = `Kompletne: ${queue.complete}/${queue.total} · ` + parts.join(" · ");
  const t = queue.timing;
  $("timing").textContent = `Na tym zdjęciu: ${fmt((photo ? photo.active_ms : 0) + unsentMs())} · ` +
    `średnio: ${fmt(t.mean_active_ms)} (n=${t.complete_photos}) · pierwsze 10: ${fmt(t.first_ten_mean_active_ms)}`;
}
setInterval(renderProgress, 1000);

// --- dragging and drawing -------------------------------------------------------------------
function svgPoint(event) {
  const svg = $("stage"), point = svg.createSVGPoint();
  point.x = event.clientX; point.y = event.clientY;
  const p = point.matrixTransform(svg.getScreenCTM().inverse());
  return [p.x, p.y];
}
function startDrag(event, corner) {
  const it = current();
  if (!it || it.locked || pending) return;
  event.preventDefault(); event.stopPropagation();
  it.undo.push(it.corners.map((p) => [...p]));
  drag = {corner, item: it};
  $("stage").setPointerCapture(event.pointerId);
}
$("stage").addEventListener("pointermove", (event) => {
  if (!drag) return;
  const it = drag.item, p = svgPoint(event), corners = it.corners.map((c) => [...c]);
  corners[drag.corner] = p;
  const nodes = gridNodes(corners);
  if (!nodes) return;
  it.corners = corners; it.nodes = nodes; it.edited = true;
  render();
});
$("stage").addEventListener("pointerup", () => { drag = null; });
$("stage").addEventListener("pointerdown", (event) => {
  if (!drawing) return;
  drawing.push(svgPoint(event));
  if (drawing.length === 4) {
    const corners = drawing, nodes = gridNodes(corners);
    drawing = null;
    if (!nodes) { say(MESSAGES.ASSISTED_QUAD_INVALID, "bad"); render(); return; }
    items.push({kind: "new", slot: null, manualSlot: false, proposal_id: "", nodes, corners,
      edited: true, undo: []});
    assignSlots(); sortItems();
    sel = items.findIndex((it) => it.corners === corners);
    say("Nowa plansza – sprawdź pozycję i zaakceptuj (A).", "");
  } else say(`Rysowanie: kliknięto ${drawing.length}/4 narożników (LG, PG, PD, LD).`, "");
  render();
});

// --- server ---------------------------------------------------------------------------------
async function fetchJson(url) {
  const response = await fetch(url, {cache: "no-store"});
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
async function loadQueue() { queue = await fetchJson("/api/queue"); }
async function loadPhoto(i, keepMessage) {
  index = Math.max(0, Math.min(i, queue.total - 1));
  store("assisted.index", String(index));
  photo = await fetchJson(`/api/photos/${index}`);
  $("photo").setAttribute("href", `/api/images/${photo.source_id}`);
  $("photo").setAttribute("width", photo.width || 1);
  $("photo").setAttribute("height", photo.height || 1);
  $("count").value = photo.confirmed_board_count || "";
  unsent = [];
  buildItems(); selectFirstOpen();
  if (!keepMessage) say(photo.proposal_status === "no_board" ? "Sieć nie znalazła plansz – narysuj je (N)." : "");
  render();
  if (index + 1 < queue.total) {
    const next = queue.items[index + 1];
    if (next) new Image().src = `/api/images/${next.source_id}`;
  }
}
function base(action) {
  const intervals = unsent; unsent = [];
  return {request_id: requestId(), expected_revision: photo.revision, action, source_id: photo.source_id,
    activity_intervals_ms: intervals};
}
async function send(body) {
  if (busy) return false;
  busy = true; pending = body; render();
  let response;
  try {
    response = await fetch("/api/decisions", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body)});
  } catch (error) {
    busy = false;
    say("Brak odpowiedzi serwera – decyzja może być zapisana albo nie. Naciśnij Y, aby ponowić identyczne żądanie.", "bad");
    render();
    return false;
  }
  busy = false; pending = null;
  if (!response.ok) {
    unsent = (body.activity_intervals_ms || []).concat(unsent);
    let code = (await response.text()).trim();
    try { code = JSON.parse(code).detail || code; } catch (e) {}
    say(MESSAGES[code] || `Odrzucono: ${code}`, "bad");
    if (RELOAD.has(code)) await refresh(true);
    else render();
    return false;
  }
  photo = await response.json();
  const keepSel = current();
  buildItems();
  selectFirstOpen();
  if (keepSel && keepSel.kind === "saved" && body.action === "revoke_board")
    sel = items.findIndex((it) => it.slot === keepSel.slot && it.kind === "saved");
  render();
  return true;
}
async function retry() {
  if (!pending || busy) return;
  await send(pending);
}
async function refresh(keepMessage) {
  await loadQueue();
  await loadPhoto(index, keepMessage);
}

// --- actions --------------------------------------------------------------------------------
function revisionOf(slot) { return photo.board_revisions[String(slot)] || 0; }
async function acceptBoard() {
  const it = current();
  if (!it || pending) return;
  if (it.locked) { say(MESSAGES.ASSISTED_EXISTING_BOARD_LOCKED, "bad"); return; }
  if (it.kind === "dismissed") { say("Najpierw przywróć propozycję (X).", "bad"); return; }
  if (it.kind === "saved" && it.status === "accepted" && !it.edited) { say("Plansza jest już zaakceptowana.", ""); return; }
  if (it.kind !== "saved" && slotConflict(it)) { say("Ustaw numer pozycji klawiszem 1–9 (pozycja pusta lub zajęta).", "bad"); return; }
  const body = base("accept_board");
  body.board_index = it.slot;
  body.expected_board_revision = it.kind === "saved" ? it.revision : revisionOf(it.slot);
  body.correction_count = it.undo.length;
  if (it.proposal_id) {
    body.proposal_id = it.proposal_id;
    const unchanged = !it.edited && (it.kind === "proposal" || it.origin === "proposal_unchanged");
    body.origin = unchanged ? "proposal_unchanged" : "proposal_corrected";
    if (!unchanged) body.corners = it.corners;
  } else {
    body.origin = "manual"; body.corners = it.corners;
  }
  if (await send(body)) say(`Zaakceptowano pozycję ${body.board_index + 1} (${ORIGINS[body.origin]}).`, "ok");
}
async function revokeBoard() {
  const it = current();
  if (!it || pending) return;
  if (it.kind !== "saved" || it.locked || it.status !== "accepted") { say("Cofnąć można tylko akceptację z tego przepływu.", "bad"); return; }
  const body = base("revoke_board");
  body.board_index = it.slot; body.expected_board_revision = it.revision;
  if (await send(body)) say(`Cofnięto akceptację pozycji ${it.slot + 1}; zdjęcie nie jest kompletne.`, "warn");
}
async function removeItem() {
  const it = current();
  if (!it || pending) return;
  if (it.kind === "new") { items.splice(sel, 1); selectFirstOpen(); render(); return; }
  if (it.locked) { say(MESSAGES.ASSISTED_EXISTING_BOARD_LOCKED, "bad"); return; }
  const body = base(it.kind === "proposal" ? "dismiss_proposal" : it.kind === "dismissed" ? "restore_proposal" : "remove_board");
  if (it.kind === "saved") { body.board_index = it.slot; body.expected_board_revision = it.revision; }
  else body.proposal_id = it.proposal_id;
  if (await send(body)) say(body.action === "restore_proposal" ? "Przywrócono propozycję." :
    body.action === "dismiss_proposal" ? "Odrzucono propozycję (nie jest etykietą)." : "Usunięto planszę z tego zdjęcia.", "");
}
async function completePhoto() {
  if (pending || !photo) return;
  const count = parseInt($("count").value, 10);
  if (!(count >= 1 && count <= 9)) { say(MESSAGES.ASSISTED_BOARD_COUNT_REQUIRED, "bad"); $("count").focus(); return; }
  const body = base("complete_photo");
  body.confirmed_board_count = count;
  body.expected_board_revisions = photo.board_revisions;
  if (await send(body)) {
    $("count").blur();
    await loadQueue();
    say(`Zdjęcie zatwierdzone jako kompletne (${count} plansz).`, "ok");
    await nextIncomplete(true);
  }
}
async function go(delta) { if (!pending && !busy) await loadPhoto(index + delta); }
async function nextIncomplete(keepMessage) {
  const n = queue.items.length;
  for (let k = 1; k <= n; k++) {
    const j = (index + k) % n;
    if (queue.items[j].status !== "complete") { await loadPhoto(j, keepMessage); return; }
  }
  say("Wszystkie zdjęcia są kompletne.", "ok");
}
function undoCorner() {
  const it = current();
  if (!it || !it.undo.length) return;
  it.corners = it.undo.pop(); it.nodes = gridNodes(it.corners);
  it.edited = it.undo.length > 0 || it.kind === "new";
  if (!it.edited && it.kind !== "new") {
    const source = it.kind === "saved" ? photo.boards.find((b) => b.board_index === it.slot)
      : photo.proposals.find((p) => p.proposal_id === it.proposal_id);
    if (source) it.nodes = source.nodes;
  }
  render();
}

$("retry").addEventListener("click", retry);
$("complete").addEventListener("click", completePhoto);
$("count").addEventListener("keydown", (event) => {
  if (event.key === "Enter") { event.preventDefault(); completePhoto(); }
  else if (event.key === "Escape") $("count").blur();
  else if (event.key.length === 1 && !/[0-9]/.test(event.key)) {
    event.preventDefault();  // only digits; "C" again just selects the value
    if (event.key.toLowerCase() === "c") $("count").select();
  }
  event.stopPropagation();
});
document.addEventListener("keydown", (event) => {
  if (!photo || event.target === $("count")) return;
  const key = event.key;
  if ((event.ctrlKey || event.metaKey) && key.toLowerCase() === "z") { undoCorner(); event.preventDefault(); return; }
  if (event.ctrlKey || event.metaKey || event.altKey) return;
  const lower = key.toLowerCase();
  if (key === "Tab") {
    if (items.length) sel = (sel + (event.shiftKey ? items.length - 1 : 1)) % items.length;
    render();
  } else if (lower === "a" || key === "Enter") acceptBoard();
  else if (lower === "r") revokeBoard();
  else if (lower === "x" || key === "Delete") removeItem();
  else if (lower === "u") undoCorner();
  else if (lower === "n") { drawing = []; say("Rysowanie: kliknij 4 narożniki (LG, PG, PD, LD). Esc przerywa.", ""); render(); }
  else if (key === "Escape") { drawing = null; say(""); render(); }
  else if (lower === "c") { $("count").focus(); $("count").select(); }
  else if (key === " " || key === "PageDown") go(1);
  else if (key === "PageUp") go(-1);
  else if (lower === "j") nextIncomplete(false);
  else if (lower === "z") { zoom = !zoom; render(); }
  else if (lower === "h") { showGrid = !showGrid; render(); }
  else if (lower === "o") { showDismissed = !showDismissed; buildItems(); selectFirstOpen(); render(); }
  else if (lower === "y") retry();
  else if (/^[1-9]$/.test(key)) {
    const it = current();
    if (it && (it.kind === "proposal" || it.kind === "new")) { it.slot = Number(key) - 1; it.manualSlot = true; render(); }
    else say("Numer pozycji ustawia się tylko dla nowej planszy lub propozycji.", "");
  } else return;
  event.preventDefault();
});
window.addEventListener("beforeunload", (event) => { if (pending) { event.preventDefault(); event.returnValue = ""; } });

(async () => {
  try {
    await loadQueue();
    const saved = parseInt(recall("assisted.index"), 10);
    if (Number.isInteger(saved) && saved >= 0 && saved < queue.total) await loadPhoto(saved);
    else {
      const first = queue.items.findIndex((it) => it.status !== "complete");
      await loadPhoto(first >= 0 ? first : 0);
    }
  } catch (error) { say("Nie można wczytać stanu: " + error.message, "bad"); }
})();
</script></body></html>
"""
