import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import path from 'node:path';
import crypto from 'node:crypto';

// Execute only the report's pure rendering logic in a stub DOM; no browser/network.
const file = process.argv[2];
const html = fs.readFileSync(file, 'utf8');
const data = JSON.parse(
  html.match(
    /<script id="data" type="application\/json">([\s\S]*?)<\/script>/,
  )[1],
);
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = {};
for (const id of [
  'data',
  'search',
  'filter',
  'framing',
  'lines',
  'count',
  'cards',
  'page',
  'prev',
  'next',
  'export',
]) {
  elements[id] = {
    textContent: '',
    innerHTML: '',
    value: '',
    checked: true,
    disabled: false,
    handlers: {},
    addEventListener(event, fn) {
      this.handlers[event] = fn;
    },
  };
}
elements.data.textContent = JSON.stringify(data);
elements.filter.value = 'all';
elements.framing.value = 'context';
let hidden = false;
const context = vm.createContext({
  document: {
    getElementById: (id) => elements[id],
    body: {
      classList: {
        toggle(_name, value) {
          hidden = value;
        },
      },
    },
  },
});
vm.runInContext(script, context, { timeout: 1500 });
assert.equal(new Set(data.map((row) => row.boardId)).size, data.length);
assert.equal(
  (elements.cards.innerHTML.match(/<article/g) || []).length,
  Math.min(12, data.length),
);
const snapshot = vm.runInContext('JSON.stringify(all)', context);
const rasterFiles = new Map();
for (const card of data) {
  const proof = card.productionCells;
  if (proof?.state !== 'available') {
    assert.equal(card.paired, false, 'no nine-detection/index fallback');
    continue;
  }
  for (const name of ['base', 'candidate']) {
    const model = proof.models[name];
    if (model.state !== 'available') continue;
    assert.deepEqual(model.cells.map((cell) => cell.cellIndex), Array.from({ length: 15 }, (_, i) => i));
    const available = model.cells.filter((cell) => cell.state === 'available');
    assert.equal(new Set(available.map((cell) => cell.image)).size, available.length);
    for (const cell of available) {
      const asset = path.resolve(path.dirname(file), cell.image);
      assert.ok(asset.startsWith(path.resolve(path.dirname(file)) + path.sep));
      const raw = fs.readFileSync(asset);
      assert.equal(raw.subarray(0, 8).toString('hex'), '89504e470d0a1a0a');
      assert.equal(crypto.createHash('sha256').update(raw).digest('hex'), cell.pngFileSha256);
      assert.notEqual(cell.pngFileSha256, cell.renderedPixelSha256);
      rasterFiles.set(asset, raw);
    }
  }
}
elements.framing.value = 'full';
elements.framing.handlers.change();
for (const card of data) {
  context.card = card;
  const [x, y, w, h] = vm.runInContext('bounds(card)', context);
  assert.ok(x <= 0 && y <= 0 && x + w >= card.width && y + h >= card.height);
  const points = [
    card.saved,
    card.base,
    card.candidate,
    ...card.baseAll,
    ...card.candidateAll,
  ]
    .filter(Boolean)
    .flat();
  for (const point of points) {
    const px = Array.isArray(point) ? point[0] : point.x;
    const py = Array.isArray(point) ? point[1] : point.y;
    assert.ok(px >= x && px <= x + w && py >= y && py <= y + h);
  }
  assert.ok(
    fs.existsSync(
      path.join(path.dirname(file), 'photos', card.sourceId + '.jpg'),
    ),
  );
  const svg = vm.runInContext(
    "lattice(card.base,'#fff',card.gridRows,card.gridColumns)",
    context,
  );
  if (card.base)
    assert.equal(
      (svg.match(/<polyline/g) || []).length,
      card.gridRows + card.gridColumns + 2,
    );
}
context.card = {
  width: 1200,
  height: 900,
  paired: true,
  saved: [
    { x: -100, y: 20 },
    { x: 1500, y: 1100 },
  ],
  baseAll: [],
  candidateAll: [],
};
const extreme = vm.runInContext('bounds(card)', context);
assert.ok(
  extreme[0] <= -100 &&
    extreme[1] <= 0 &&
    extreme[0] + extreme[2] >= 1500 &&
    extreme[1] + extreme[3] >= 1100,
);
assert.equal(
  vm.runInContext('JSON.stringify(all)', context),
  snapshot,
  'framing preserves all geometry and provenance',
);
for (const [asset, bytes] of rasterFiles) {
  assert.deepEqual(fs.readFileSync(asset), bytes, 'viewport preserves actual production PNG bytes');
}
elements.framing.value = 'context';
elements.framing.handlers.change();
if (data.length) {
  elements.search.value = String(data[0].sequence);
  elements.search.handlers.input();
  assert.ok(elements.cards.innerHTML.includes('Plansza #' + data[0].sequence));
}
elements.search.value = '';
elements.filter.value = 'changed';
elements.filter.handlers.input();
assert.equal(
  vm.runInContext('filtered().length', context),
  data.filter((row) => row.delta !== null && row.delta >= 1).length,
);
elements.filter.value = 'all';
elements.filter.handlers.input();
if (data.length > 12) {
  elements.next.handlers.click();
  assert.ok(elements.page.textContent.startsWith('Strona 2'));
  elements.prev.handlers.click();
}
elements.lines.checked = false;
elements.lines.handlers.change();
assert.ok(hidden);
const screenInput = vm.runInContext(`inputs({diagnostics:{base:{state:'available',stageLabel:'wejście ekranu',margin:null,image:'synthetic.png',tensorShape:[1,3,768,1024]}}})`, context);
assert.match(screenInput, /wejście ekranu; Margin: nie dotyczy/);
assert.doesNotMatch(screenInput, /Margin: 0\.15/);
assert.match(vm.runInContext("productionCells({productionCells:{state:'unavailable',reason:'missing'}})", context), /Wycinki niedostępne: missing/);
const flagged = vm.runInContext("cellCaption({assessment:{finalContentState:'preserved',wrongCell:true,tie:true,foreignFullSymbol:true}})", context);
assert.match(flagged, /obce pole/);
assert.match(flagged, /remis/);
assert.match(flagged, /pełny obcy symbol/);
console.log(
  JSON.stringify({
    boards: data.length,
    photos: new Set(data.map((row) => row.sourceId)).size,
    checks: [
      'context/full framing',
      'off-image nodes',
      'unchanged geometry',
      'search/filter/pagination',
      'grid topology',
      'image assets',
      '15 actual lossless PNGs and file hashes',
      'unchanged crop pixels after viewport changes',
    ],
  }),
);
