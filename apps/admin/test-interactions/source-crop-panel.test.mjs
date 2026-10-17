import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';

// React DOM detects DOM support (text input events) when first imported.
const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();

// The panel gets an injected client; request serialization (confirmation
// headers) is covered by the generated-client wrapper tests.
registerHooks({
  load(url, context, nextLoad) {
    if (url.endsWith('.css'))
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export default new Proxy({}, {get: (_, key) => key});',
      };
    if (url.endsWith('/src/api/admin-api-client.ts'))
      return {
        format: 'module',
        shortCircuit: true,
        source:
          'export function createConfiguredAdminApiClient() { throw new Error("Explicit source crop test client required"); }',
      };
    return nextLoad(url, context);
  },
});
const { SourceCropPanel } =
  await import('../src/features/storage/source-crop-panel.tsx');

const CROP_TITLE = 'Przycinanie zdjęć';
const DELETE_TITLE = 'Usuń oryginały przyciętych zdjęć';
const sha = (char) => char.repeat(64);

function run(overrides = {}) {
  return {
    candidateBytes: 0,
    checkpointIndex: 0,
    createdAt: '2026-10-17T10:00:00Z',
    eligibleCount: 0,
    errorCode: null,
    errorMessage: null,
    estimatedSavedBytes: 0,
    excludedCount: 0,
    exclusionCounts: {},
    failedCount: 0,
    failures: [],
    finishedAt: null,
    id: 'run-1',
    jobId: null,
    kind: 'crop',
    manifestChecksumSha256: null,
    outcomeCounts: {},
    planJobId: 'plan-job-1',
    previewToken: null,
    processedCount: 0,
    savedBytes: 0,
    scope: {},
    skippedCount: 0,
    startedAt: null,
    status: 'planning',
    succeededCount: 0,
    updatedAt: null,
    ...overrides,
  };
}

const MIB = 1024 ** 2;
const previewed = (overrides = {}) =>
  run({
    candidateBytes: 800 * MIB,
    eligibleCount: 40,
    estimatedSavedBytes: 500 * MIB,
    excludedCount: 7,
    exclusionCounts: { ALREADY_CROPPED: 5, GRID_ISSUE: 2 },
    manifestChecksumSha256: sha('c'),
    previewToken: 'token-1',
    status: 'previewed',
    ...overrides,
  });

/** Returns the scripted values in order and repeats the last one. */
function sequence(values) {
  let index = 0;
  return () => values[Math.min(index++, values.length - 1)];
}

function fixture(extra = {}) {
  const requests = [];
  return {
    requests,
    api: {
      async listGames() {
        requests.push(['listGames']);
        return {
          data: [
            { code: 'G1', id: 'game-1', name: 'Pierwsza gra' },
            { code: 'G2', id: 'game-2', name: 'Druga gra' },
          ],
        };
      },
      async listSourceCropRuns(limit) {
        requests.push(['list', limit]);
        return { data: { runs: [] } };
      },
      async createSourceCropPreview(body) {
        requests.push(['plan', body]);
        return { data: run({ kind: body.kind, scope: body.scope }) };
      },
      async getSourceCropRun(runId) {
        requests.push(['get', runId]);
        return { data: previewed() };
      },
      async startSourceCropRun(previewId, body) {
        requests.push(['start', previewId, body]);
        return { data: run({ id: previewId, status: 'created' }) };
      },
      ...extra,
    },
  };
}

async function mount(api, props = {}) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(SourceCropPanel, {
        apiBaseUrl: 'http://127.0.0.1:8000',
        client: api,
        pollIntervalMs: 5,
        ...props,
      }),
    ),
  );
  await waitFor(() => sectionOf(CROP_TITLE) !== undefined);
  return {
    async cleanup() {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}

async function waitFor(predicate, attempts = 200) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 5));
    });
  }
  assert.fail(`Condition not met. Page text: ${document.body.textContent}`);
}

function sectionOf(title) {
  return [...document.querySelectorAll('section[aria-labelledby]')].find(
    (element) => element.querySelector('h2')?.textContent === title,
  );
}
const crop = () => sectionOf(CROP_TITLE);
const deletion = () => sectionOf(DELETE_TITLE);
const buttonIn = (root, label) =>
  root &&
  [...root.querySelectorAll('button')].find(
    (element) => element.textContent.trim() === label,
  );
async function click(root, label) {
  const item = buttonIn(root, label);
  assert.ok(item, `Missing button: ${label}`);
  await act(async () => item.click());
}
async function setValue(element, value) {
  const prototype =
    element instanceof window.HTMLSelectElement
      ? window.HTMLSelectElement.prototype
      : element instanceof window.HTMLTextAreaElement
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
  const eventName =
    element instanceof window.HTMLSelectElement ? 'change' : 'input';
  await act(async () => {
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(
      element,
      value,
    );
    element.dispatchEvent(new window.Event(eventName, { bubbles: true }));
  });
}
async function chooseMode(root, label) {
  const radio = [...root.querySelectorAll('input[type="radio"]')].find(
    (element) => element.parentElement.textContent.trim() === label,
  );
  await act(async () => radio.click());
}
const text = (root) => root.textContent.replace(/\s+/g, ' ');

test('plans a crop run, polls the planning run and shows the preview', async () => {
  const f = fixture({
    getSourceCropRun: (() => {
      const next = sequence([run(), run(), previewed()]);
      return async (runId) => {
        f.requests.push(['get', runId]);
        return { data: next() };
      };
    })(),
  });
  const m = await mount(f.api);
  try {
    assert.equal(buttonIn(crop(), 'Zaplanuj przycinanie').disabled, false);
    await click(crop(), 'Zaplanuj przycinanie');
    assert.deepEqual(
      f.requests.find((item) => item[0] === 'plan'),
      ['plan', { kind: 'crop', scope: {} }],
    );
    assert.match(text(crop()), /Worker przygotowuje podgląd/);
    assert.equal(
      buttonIn(crop(), 'Zaplanuj przycinanie').disabled,
      true,
      'planning is locked while the worker builds the preview',
    );
    await waitFor(() =>
      /Podgląd$/.test(crop().querySelector('h3')?.textContent),
    );
    const preview = text(crop());
    assert.match(preview, /Kwalifikujące się\s*40/);
    assert.match(preview, /Wykluczone\s*7/);
    assert.match(preview, /Rozmiar oryginałów\s*800 MB/);
    assert.match(preview, /Szacowana oszczędność\s*500 MB/);
    assert.match(preview, /Już przycięte \(ALREADY_CROPPED\): 5/);
    assert.match(preview, /Problem z siatką \(GRID_ISSUE\): 2/);
    assert.equal(
      f.requests.filter((item) => item[0] === 'start').length,
      0,
      'a preview never starts the run',
    );
    assert.equal(
      f.requests.some(
        (item) => item[0] === 'plan' && item[1].kind === 'original_deletion',
      ),
      false,
    );
  } finally {
    await m.cleanup();
  }
});

test('sends game, checksum and limit scope and validates input before any request', async () => {
  const f = fixture();
  const m = await mount(f.api);
  try {
    await chooseMode(crop(), 'Jedna gra');
    await click(crop(), 'Zaplanuj przycinanie');
    assert.match(
      crop().querySelector('[role="alert"]').textContent,
      /Wybierz grę/,
    );
    assert.equal(f.requests.filter((item) => item[0] === 'plan').length, 0);
    await setValue(crop().querySelector('select'), 'game-2');
    await setValue(
      crop().querySelector('input[aria-label="Limit oryginałów"]'),
      '25',
    );
    await click(crop(), 'Zaplanuj przycinanie');
    assert.deepEqual(
      f.requests.filter((item) => item[0] === 'plan').map((item) => item[1]),
      [{ kind: 'crop', scope: { gameId: 'game-2', limit: 25 } }],
    );
  } finally {
    await m.cleanup();
  }

  const g = fixture();
  const n = await mount(g.api);
  try {
    await chooseMode(crop(), 'Lista sum SHA-256');
    await setValue(crop().querySelector('textarea'), 'not-a-sum');
    await click(crop(), 'Zaplanuj przycinanie');
    assert.match(crop().querySelector('[role="alert"]').textContent, /SHA-256/);
    assert.equal(g.requests.filter((item) => item[0] === 'plan').length, 0);
    await setValue(
      crop().querySelector('textarea'),
      `${sha('A')}\n${sha('b')}`,
    );
    await click(crop(), 'Zaplanuj przycinanie');
    assert.deepEqual(g.requests.find((item) => item[0] === 'plan')[1], {
      kind: 'crop',
      scope: { onlyChecksums: [sha('a'), sha('b')] },
    });
  } finally {
    await n.cleanup();
  }
});

test('starts a crop run only after the confirmation dialog and follows progress to the result', async () => {
  const getRun = sequence([
    run({
      ...previewed(),
      processedCount: 10,
      status: 'processing',
      succeededCount: 9,
      skippedCount: 1,
    }),
    run({
      ...previewed(),
      outcomeCounts: { alreadyCropped: 3, cropped: 36, failed: 1 },
      failedCount: 1,
      processedCount: 40,
      savedBytes: 480 * MIB,
      skippedCount: 3,
      status: 'completed',
      succeededCount: 36,
      failures: [
        {
          checksumSha256: sha('f'),
          code: 'ORIGINAL_CHANGED',
          message: 'Plik zmienił się na dysku',
        },
      ],
    }),
  ]);
  const f = fixture({
    async listSourceCropRuns() {
      return { data: { runs: [previewed()] } };
    },
    async getSourceCropRun(runId) {
      f.requests.push(['get', runId]);
      return { data: getRun() };
    },
    async startSourceCropRun(previewId, body) {
      f.requests.push(['start', previewId, body]);
      return { data: run({ ...previewed(), status: 'created' }) };
    },
  });
  const m = await mount(f.api);
  try {
    assert.match(text(crop()), /Kwalifikujące się\s*40/);
    await click(crop(), 'Uruchom przycinanie…');
    const dialog = document.querySelector('[role="dialog"]');
    assert.ok(dialog);
    assert.match(dialog.textContent, /Uruchomić przycinanie zdjęć\?/);
    assert.equal(f.requests.filter((item) => item[0] === 'start').length, 0);
    await click(dialog, 'Anuluj');
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(f.requests.filter((item) => item[0] === 'start').length, 0);

    await click(crop(), 'Uruchom przycinanie…');
    await click(
      document.querySelector('[role="dialog"]'),
      'Potwierdź i uruchom przycinanie',
    );
    assert.deepEqual(
      f.requests.filter((item) => item[0] === 'start'),
      [
        [
          'start',
          'run-1',
          {
            confirmed: true,
            manifestChecksumSha256: sha('c'),
            previewToken: 'token-1',
          },
        ],
      ],
    );
    assert.equal(document.querySelector('[role="dialog"]'), null);

    await waitFor(() => /Przetworzono 10 z 40/.test(text(crop())));
    assert.equal(
      crop()
        .querySelector('[role="progressbar"]')
        .getAttribute('aria-valuenow'),
      '25',
    );
    await waitFor(() => /Przycięte: 36/.test(text(crop())));
    const result = text(crop());
    assert.match(result, /Wynik/);
    assert.match(result, /Zakończony/);
    assert.match(result, /Zaoszczędzono\s*480 MB/);
    assert.match(result, /Błędy\s*1/);
    assert.match(result, /Już przycięte: 3/);
    assert.match(result, /Błędy pojedynczych oryginałów \(1\)/);
    assert.match(result, /ORIGINAL_CHANGED — Plik zmienił się na dysku/);
    assert.equal(
      crop()
        .querySelector('[role="progressbar"]')
        .getAttribute('aria-valuenow'),
      '100',
    );
    // A terminal run is no longer polled.
    const polls = f.requests.filter((item) => item[0] === 'get').length;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 40));
    });
    assert.equal(f.requests.filter((item) => item[0] === 'get').length, polls);
  } finally {
    await m.cleanup();
  }
});

test('shows errorCode and errorMessage of a failed run', async () => {
  const f = fixture({
    async listSourceCropRuns() {
      return {
        data: {
          runs: [
            run({
              ...previewed(),
              errorCode: 'SOURCE_CROP_TOOL_FAILED',
              errorMessage: 'Narzędzie przycinania zakończyło się błędem',
              processedCount: 12,
              status: 'failed',
            }),
          ],
        },
      };
    },
  });
  const m = await mount(f.api);
  try {
    const alert = crop().querySelector('[role="alert"]');
    assert.match(alert.textContent, /Przebieg zakończył się błędem/);
    assert.match(alert.textContent, /SOURCE_CROP_TOOL_FAILED/);
    assert.match(
      alert.textContent,
      /Narzędzie przycinania zakończyło się błędem/,
    );
    assert.match(text(crop()), /Błąd/);
    assert.match(text(crop()), /Przetworzono 12 z 40/);
    assert.equal(buttonIn(crop(), 'Zaplanuj przycinanie').disabled, false);
  } finally {
    await m.cleanup();
  }
});

test('surfaces active-run and stale-preview API errors in Polish with the code', async () => {
  const f = fixture({
    async createSourceCropPreview() {
      return {
        error: { code: 'SOURCE_CROP_RUN_ACTIVE', message: 'A run is active' },
      };
    },
  });
  const m = await mount(f.api);
  try {
    await click(crop(), 'Zaplanuj przycinanie');
    const alert = crop().querySelector('[role="alert"]');
    assert.match(
      alert.textContent,
      /Inny przebieg przycinania jest już aktywny/,
    );
    assert.match(alert.textContent, /SOURCE_CROP_RUN_ACTIVE/);
  } finally {
    await m.cleanup();
  }

  const g = fixture({
    async listSourceCropRuns() {
      return { data: { runs: [previewed()] } };
    },
    async startSourceCropRun() {
      return {
        error: { code: 'SOURCE_CROP_PREVIEW_STALE', message: 'stale' },
      };
    },
  });
  const n = await mount(g.api);
  try {
    await click(crop(), 'Uruchom przycinanie…');
    await click(
      document.querySelector('[role="dialog"]'),
      'Potwierdź i uruchom przycinanie',
    );
    assert.equal(document.querySelector('[role="dialog"]'), null);
    const alert = crop().querySelector('[role="alert"]');
    assert.match(alert.textContent, /Zaplanuj przebieg ponownie/);
    assert.match(alert.textContent, /SOURCE_CROP_PREVIEW_STALE/);
  } finally {
    await n.cleanup();
  }
});

test('does not offer a start when no originals are eligible', async () => {
  const f = fixture({
    async listSourceCropRuns() {
      return {
        data: {
          runs: [
            previewed({
              eligibleCount: 0,
              excludedCount: 3,
              exclusionCounts: { ORIGINAL_MISSING: 3 },
            }),
          ],
        },
      };
    },
  });
  const m = await mount(f.api);
  try {
    assert.equal(buttonIn(crop(), 'Uruchom przycinanie…').disabled, true);
    assert.match(text(crop()), /Brak pliku oryginału \(ORIGINAL_MISSING\): 3/);
  } finally {
    await m.cleanup();
  }
});

test('deletion step is visually separate, warns about no backup and gates start on acknowledgement', async () => {
  const f = fixture({
    async createSourceCropPreview(body) {
      f.requests.push(['plan', body]);
      return {
        data: run({ kind: 'original_deletion', scope: body.scope }),
      };
    },
    getSourceCropRun: (() => {
      const next = sequence([
        previewed({
          candidateBytes: 2048 * MIB,
          estimatedSavedBytes: 2048 * MIB,
          exclusionCounts: { NOT_CROPPED: 4 },
          kind: 'original_deletion',
        }),
      ]);
      return async (runId) => {
        f.requests.push(['get', runId]);
        return { data: next() };
      };
    })(),
    async startSourceCropRun(previewId, body) {
      f.requests.push(['start', previewId, body]);
      return {
        data: run({
          ...previewed({ kind: 'original_deletion' }),
          status: 'created',
        }),
      };
    },
  });
  const m = await mount(f.api);
  try {
    assert.ok(deletion(), 'separate deletion section exists');
    assert.notEqual(deletion(), crop());
    assert.ok(!crop().contains(deletion()));
    // The warning is visible before anything is planned.
    const warning = deletion().querySelector('[role="note"]');
    assert.match(warning.textContent, /Brak kopii zdjęć/);
    assert.match(warning.textContent, /nie można cofnąć/);
    assert.equal(crop().querySelector('[role="note"]'), null);

    await click(deletion(), 'Zaplanuj usunięcie oryginałów');
    assert.deepEqual(
      f.requests.find((item) => item[0] === 'plan'),
      ['plan', { kind: 'original_deletion', scope: {} }],
    );
    await waitFor(() => /Do zwolnienia\s*2 GB/.test(text(deletion())));
    const preview = text(deletion());
    assert.match(preview, /Rozmiar oryginałów\s*2 GB/);
    assert.match(
      preview,
      /Nieprzycięte \(brak zweryfikowanego cropu\) \(NOT_CROPPED\): 4/,
    );

    const checkbox = deletion().querySelector('input[type="checkbox"]');
    assert.ok(checkbox);
    assert.equal(checkbox.checked, false);
    assert.equal(buttonIn(deletion(), 'Usuń oryginały…').disabled, true);
    await act(async () => buttonIn(deletion(), 'Usuń oryginały…').click());
    assert.equal(document.querySelector('[role="dialog"]'), null);
    assert.equal(f.requests.filter((item) => item[0] === 'start').length, 0);

    await act(async () => checkbox.click());
    assert.equal(buttonIn(deletion(), 'Usuń oryginały…').disabled, false);
    await act(async () => checkbox.click());
    assert.equal(buttonIn(deletion(), 'Usuń oryginały…').disabled, true);
    await act(async () => checkbox.click());

    await click(deletion(), 'Usuń oryginały…');
    const dialog = document.querySelector('[role="dialog"]');
    assert.match(
      dialog.querySelector('[role="note"]').textContent,
      /Brak kopii zdjęć/,
    );
    assert.match(dialog.textContent, /Usunąć oryginały przyciętych zdjęć\?/);
    assert.equal(f.requests.filter((item) => item[0] === 'start').length, 0);
    await click(dialog, 'Tak, usuń oryginały bezpowrotnie');
    assert.deepEqual(
      f.requests.filter((item) => item[0] === 'start'),
      [
        [
          'start',
          'run-1',
          {
            acknowledgeIrreversible: true,
            confirmed: true,
            manifestChecksumSha256: sha('c'),
            previewToken: 'token-1',
          },
        ],
      ],
    );
  } finally {
    await m.cleanup();
  }
});

test('deletion result lists every outcome and per-original failures', async () => {
  const f = fixture({
    async listSourceCropRuns() {
      return {
        data: {
          runs: [
            run({
              ...previewed({ kind: 'original_deletion' }),
              failedCount: 1,
              failures: [
                {
                  checksumSha256: sha('e'),
                  code: 'ORIGINAL_CHANGED',
                  message: 'Oryginał zmieniony',
                },
              ],
              outcomeCounts: {
                alreadyDeleted: 2,
                cropChanged: 1,
                deleted: 30,
                failed: 1,
                notCropped: 4,
                notEligible: 2,
              },
              processedCount: 40,
              savedBytes: 1024 * MIB,
              skippedCount: 9,
              status: 'completed',
              succeededCount: 30,
            }),
          ],
        },
      };
    },
  });
  const m = await mount(f.api);
  try {
    const result = text(deletion());
    assert.match(result, /Zwolniono\s*1 GB/);
    assert.match(result, /Usunięte: 30/);
    assert.match(result, /Nieprzycięte: 4/);
    assert.match(result, /Już usunięte: 2/);
    assert.match(result, /Crop zmieniony: 1/);
    assert.match(result, /Niekwalifikujące się: 2/);
    assert.match(result, /Błędy: 1/);
    assert.match(result, /ORIGINAL_CHANGED — Oryginał zmieniony/);
    // The crop section is untouched by the deletion run.
    assert.equal(crop().querySelector('[role="progressbar"]'), null);
  } finally {
    await m.cleanup();
  }
});

test('resumes an executing run after reload and keeps polling it', async () => {
  const getRun = sequence([
    run({ ...previewed(), processedCount: 20, status: 'processing' }),
    run({
      ...previewed(),
      processedCount: 40,
      status: 'completed',
      succeededCount: 40,
    }),
  ]);
  const f = fixture({
    async listSourceCropRuns() {
      return {
        data: {
          runs: [
            run({ ...previewed(), processedCount: 5, status: 'processing' }),
          ],
        },
      };
    },
    async getSourceCropRun(runId) {
      f.requests.push(['get', runId]);
      return { data: getRun() };
    },
  });
  const m = await mount(f.api);
  try {
    assert.match(text(crop()), /W toku/);
    assert.equal(buttonIn(crop(), 'Zaplanuj przycinanie').disabled, true);
    await waitFor(() => /Zakończony/.test(text(crop())));
    assert.equal(buttonIn(crop(), 'Zaplanuj przycinanie').disabled, false);
  } finally {
    await m.cleanup();
  }
});
