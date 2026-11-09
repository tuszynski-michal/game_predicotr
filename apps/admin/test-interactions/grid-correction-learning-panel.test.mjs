import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
const bootstrap = new JSDOM('<div></div>');
globalThis.window = bootstrap.window;
globalThis.document = bootstrap.window.document;
const { createRoot } = await import('react-dom/client');
delete globalThis.window;
delete globalThis.document;
bootstrap.window.close();
const { GridCorrectionLearningPanel } =
  await import('../src/features/model-quality/grid-correction-learning-panel.tsx');
const { learningCommandKey } =
  await import('../src/features/model-quality/grid-correction-learning-state.ts');
const GAME = '11111111-1111-4111-8111-111111111111',
  OTHER = '22222222-2222-4222-8222-222222222222',
  RUN = '33333333-3333-4333-8333-333333333333';
const apiBaseUrl = 'http://127.0.0.1:8000';
const READ_ONLY_METHODS = new Set([
  'getGridCorrectionLearningReady',
  'getGridModelDefault',
  'listGridCorrectionLearning',
  'listGames',
  'listGridModelVersions',
  'getGameGridModelHistory',
  'getGridCorrectionLearning',
  'getGridCorrectionLearningEvaluation',
  'previewGridCorrectionApply',
  'listGridCorrectionApply',
  'getGridCorrectionApply',
  'getGameGridModelAssignment',
  'getGridTrainingRun',
]);
function assertOnlyReads(calls) {
  assert.deepEqual(
    calls.filter(([name]) => !READ_ONLY_METHODS.has(name)),
    [],
  );
}
const readiness = {
  gameId: GAME,
  baseVersionId: 'base',
  defaultRevision: 2,
  importJobIds: ['import'],
  roleCounts: [
    { role: 'TRAIN', photos: 12, boards: 32 },
    { role: 'VALIDATION', photos: 5, boards: 16 },
    { role: 'REGRESSION', photos: 5, boards: 16 },
  ],
  bufferPhotos: 20,
  priorScopeDocumented: false,
  priorGameIds: [],
  historicalCohorts: [],
  exclusions: [],
  requiredGameIds: [GAME, OTHER],
  blockers: [],
  pendingWorkerChecks: [],
  canStart: true,
  evidenceLevel: 'photo-only',
  limitations: [],
  previewSha256: 'a'.repeat(64),
};
const run = {
  learningId: RUN,
  gameId: GAME,
  status: 'completed',
  stage: 'completed',
  baseVersionId: 'base',
  defaultRevision: 2,
  candidateVersionId: 'candidate',
  evaluationId: null,
  verdict: 'PASS',
  requiredGameIds: [GAME, OTHER],
  createdAt: '2026-11-02T12:00:00Z',
};
const applyPreview = {
  gameId: GAME,
  learningId: RUN,
  versionId: 'candidate',
  versionLabel: 'Model 2',
  defaultVersionId: 'base',
  baseVersionId: 'base',
  defaultRevision: 2,
  additionalGameIds: [],
  requiredGameIds: [GAME, OTHER],
  targets: [
    {
      gameId: GAME,
      gameLabel: 'Mumie',
      assignmentRevision: 3,
      assignedVersionId: 'actual',
      requiresComparison: true,
    },
  ],
  excludedGameIds: [],
  limitations: [],
  evidenceLevel: 'photo-only',
  blockers: [],
  canApply: true,
  previewSha256: 'b'.repeat(64),
};
const progressCounts = {
  approved: { photos: 67, boards: 196 },
  availableTrain: { photos: 44, boards: 130 },
  usedTrain: { photos: 26, boards: 77 },
  newTrain: { photos: 19, boards: 53 },
  validation: { photos: 6, boards: 17 },
  regression: { photos: 7, boards: 20 },
  validationReserve: { photos: 5, boards: 0 },
  regressionReserve: { photos: 4, boards: 0 },
  buffers: { photos: 20, boards: 26 },
  excluded: { photos: 10, boards: 29 },
  exclusionReasons: [
    { reason: 'GRID_CORRECTION_PROTECTED_NEIGHBORHOOD', photos: 2, boards: 3 },
    { reason: 'GRID_CORRECTION_BUFFER', photos: 8, boards: 26 },
  ],
};
const evaluatedRun = { ...run, evaluationId: 'evaluation' };
function evaluation(state = 'stale', id = 'evaluation') {
  return {
    evaluationId: id,
    reportId: `report-${id}`,
    versionId: 'candidate',
    status: 'completed',
    verdict: 'PASS',
    report: {
      schemaVersion: 'grid-model-evaluation-read-v3',
      scope: {
        currentGameId: GAME,
        requiredGameIds: [GAME, OTHER],
        exclusions: [],
      },
      verdict: 'PASS',
      games: [],
    },
    currentness: [{ gameId: GAME, cohortId: 'cohort', state }],
  };
}
function fixture(overrides = {}) {
  const calls = [];
  const implementations = {
    getGridCorrectionLearningReady: () => ({ data: readiness }),
    getGridModelDefault: () => ({ data: { version: null, revision: 2 } }),
    listGridCorrectionLearning: () => ({ data: { items: [] } }),
    listGames: () => ({
      data: [
        { id: GAME, name: 'Mumie', code: 'mumie' },
        { id: OTHER, name: '777', code: '777' },
      ],
    }),
    listGridModelVersions: () => ({ data: [] }),
    getGameGridModelHistory: () => ({ data: [] }),
    getGridCorrectionLearning: () => ({ data: run }),
    previewGridCorrectionApply: () => ({ data: applyPreview }),
    listGridCorrectionApply: () => ({ data: { items: [] } }),
    ...overrides,
  };
  const api = new Proxy(
    {},
    {
      get:
        (_, name) =>
        async (...args) => {
          calls.push([name, ...structuredClone(args)]);
          if (!(name in implementations))
            throw new Error(`Unexpected call ${name}`);
          return implementations[name](...args);
        },
    },
  );
  return { api, calls };
}
async function mount(api, saved = {}, gameId = GAME) {
  const dom = new JSDOM('<div id="root"></div>', {
    url: 'http://127.0.0.1:3000',
  });
  for (const [key, value] of Object.entries(saved))
    dom.window.localStorage.setItem(key, value);
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
      React.createElement(GridCorrectionLearningPanel, {
        apiBaseUrl,
        gameId,
        client: api,
      }),
    ),
  );
  return {
    saved: () => Object.fromEntries(Object.entries(dom.window.localStorage)),
    close: async () => {
      await act(async () => root.unmount());
      dom.window.close();
      Object.assign(globalThis, previous);
    },
  };
}
async function click(text) {
  const button = [...document.querySelectorAll('button')].find(
    (item) => item.textContent === text,
  );
  assert.ok(button, text);
  await act(async () => button.click());
}
const settle = () =>
  act(async () => new Promise((resolve) => setTimeout(resolve, 10)));
async function check(text) {
  const label = [...document.querySelectorAll('label')].find((item) =>
    item.textContent.includes(text),
  );
  assert.ok(label, text);
  await act(async () => label.querySelector('input').click());
}

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function findButton(text) {
  const button = [...document.querySelectorAll('button')].find(
    (item) => item.textContent === text,
  );
  assert.ok(button, text);
  return button;
}

test('calibrated v5 retains raw quality display when automation is unqualified', async () => {
  const value = evaluation('current');
  value.report = {
    ...value.report,
    schemaVersion: 'grid-model-evaluation-read-v5',
    rawQualitySchemaVersion: 'grid-model-evaluation-read-v3',
    scope: { currentGameId: GAME },
    automaticCalibration: [
      {
        gameId: GAME,
        state: 'unqualified',
        reasonCodes: ['CALIBRATION_MINIMUM'],
      },
    ],
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({ data: value }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(document.body.textContent, /Wynik: PASS/);
    assert.match(document.body.textContent, /Dowód oceny jest aktualny/);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('v6 content verdict controls the result even when historical raw quality passed; variant shortages remain manual', async () => {
  const value = evaluation('current');
  const counts = {
    preserved: 14,
    borderline: 1,
    clipped: 0,
    missing: 0,
    wrongCells: 0,
    ties: 0,
    foreignSymbols: 0,
    ambiguousBoards: 0,
    usableBoards: 0,
  };
  const role = {
    state: 'ready',
    reasonCodes: [],
    photos: 5,
    fullPhotos: 5,
    slots: 15,
    visible: 15,
    unknown: 0,
    base: { ...counts, preserved: 15, borderline: 0, usableBoards: 1 },
    candidate: counts,
    degradedInstances: 1,
  };
  value.verdict = 'REVISE';
  value.report = {
    ...value.report,
    schemaVersion: 'grid-model-evaluation-read-v6',
    verdict: 'REVISE',
    rawQuality: { verdict: 'PASS' },
    contentEvaluation: [
      {
        gameId: GAME,
        state: 'ready',
        reasonCodes: [],
        u: 0.001,
        delta: 0.001,
        measurementSha256: 'a'.repeat(64),
        renderConfigurationSha256s: ['b'.repeat(64)],
        classifierSnapshotSha256s: ['c'.repeat(64)],
        freshRegression: true,
        roles: { VALIDATION: role, REGRESSION: role },
      },
    ],
    automaticCalibration: [
      {
        gameId: GAME,
        state: 'unqualified',
        reasonCodes: ['VARIANT_MINIMA'],
        allowedVariants: [{ sha256: 'wide', stage: 'wide' }],
        variants: [
          {
            variantKey: 'wide',
            state: 'unqualified',
            reasonCodes: ['VARIANT_MINIMA'],
            b: { baselineBadSources: 2, baselineGoodSources: 1 },
            regression: { baselineBadSources: 1, baselineGoodSources: 2 },
          },
        ],
      },
    ],
  };
  const finished = {
    ...evaluatedRun,
    verdict: 'REVISE',
    contentExperiment: 'full-symbol-content-experiment-v1',
    contentExperimentPlanSha256: 'd'.repeat(64),
    trainingRunId: 'training',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [finished] } }),
    getGridCorrectionLearning: () => ({ data: finished }),
    getGridCorrectionLearningEvaluation: () => ({ data: value }),
    getGridTrainingRun: () => ({
      data: {
        runId: 'training',
        gameId: GAME,
        budget: {
          usedSeconds: 13.5,
          maxSeconds: 7200,
          reservedSteps: 4,
          maxSteps: 4800,
        },
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(
      document.body.textContent,
      /Zawartość końcowych wycinków: REVISE/,
    );
    assert.match(document.body.textContent, /Nie zastępuje wyniku zawartości/);
    assert.match(
      document.body.textContent,
      /Szerszy wycinek: Kontrole B: 2 błędnych/,
    );
    assert.match(document.body.textContent, /Zużyto 13.5 z 7200/);
    assert.match(document.body.textContent, /wymaga kalibracji/);
    assert.equal(
      document.querySelector('[aria-label="Zastosowanie wersji"]'),
      null,
    );
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('failed worker budget read stays unavailable and manual refresh retries the same unchanged run', async () => {
  let budgetReads = 0;
  const unchangedRun = {
    ...run,
    verdict: 'REVISE',
    trainingRunId: 'training',
    contentExperiment: 'full-symbol-content-experiment-v1',
    updatedAt: '2026-11-09T01:00:00Z',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [unchangedRun] } }),
    getGridCorrectionLearning: () => ({ data: structuredClone(unchangedRun) }),
    getGridTrainingRun: () => {
      budgetReads += 1;
      return budgetReads === 1
        ? { error: { code: 'BUDGET_UNAVAILABLE' } }
        : {
            data: {
              runId: 'training',
              gameId: GAME,
              budget: {
                usedSeconds: 17.25,
                maxSeconds: 7200,
                reservedSteps: 9,
                maxSteps: 4800,
              },
            },
          };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.equal(budgetReads, 1);
    const budget = () =>
      document.querySelector('[aria-label="Budżet eksperymentu"]').textContent;
    assert.match(budget(), /Brak potwierdzonego odczytu zużycia budżetu/);
    assert.match(budget(), /Nie udało się potwierdzić/);
    assert.doesNotMatch(budget(), /Zużyto 0/);
    await click('Odśwież stan uczenia');
    await settle();
    assert.equal(budgetReads, 2);
    assert.match(budget(), /Zużyto 17.3 z 7200/);
    assert.doesNotMatch(budget(), /Nie udało się potwierdzić/);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('growth counts show new TRAIN separately from protected controls and unlabelled reserves', async () => {
  let counts = progressCounts;
  const setup = fixture({
    getGridCorrectionLearningReady: () => ({
      data: { ...readiness, progressCounts: counts },
    }),
  });
  const view = await mount(setup.api);
  const values = (label) => {
    const row = [...document.querySelectorAll('tr')].find(
      (item) => item.querySelector('th')?.textContent === label,
    );
    assert.ok(row, label);
    return [...row.querySelectorAll('td')].map((item) =>
      Number(item.textContent),
    );
  };
  try {
    await settle();
    assert.deepEqual(values('Zatwierdzone korekty ogółem'), [67, 196]);
    assert.deepEqual(values('Dostępne do uczenia (TRAIN)'), [44, 130]);
    assert.deepEqual(values('W zapisanych zestawach TRAIN'), [26, 77]);
    assert.deepEqual(values('Nowe do uczenia'), [19, 53]);
    assert.deepEqual(values('Rezerwa do doboru — bez etykiet'), [5, 0]);
    assert.match(
      document.body.textContent,
      /Rezerwa bez etykiet nie jest wynikiem testu jakości/,
    );
    assert.match(document.body.textContent, /Nie sumuj zdjęć/);
    assert.match(
      document.querySelector('[aria-label="Powody wyłączenia korekt"]')
        .textContent,
      /Zdjęcia są zbyt blisko chronionych kontroli albo nie mają bezpiecznego przydziału: 2 zdjęć \/ 3 plansz/,
    );
    counts = {
      ...counts,
      approved: { photos: 68, boards: 199 },
      availableTrain: { photos: 45, boards: 133 },
      newTrain: { photos: 20, boards: 56 },
    };
    await click('Odśwież stan uczenia');
    await settle();
    assert.deepEqual(values('Dostępne do uczenia (TRAIN)'), [45, 133]);
    assert.deepEqual(values('Nowe do uczenia'), [20, 56]);
    counts = {
      ...counts,
      approved: { photos: 69, boards: 202 },
      regression: { photos: 8, boards: 23 },
    };
    await click('Odśwież stan uczenia');
    await settle();
    assert.deepEqual(values('Dostępne do uczenia (TRAIN)'), [45, 133]);
    assert.deepEqual(values('Kontrola końcowa — zatwierdzone'), [8, 23]);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('explicit currentness check deduplicates clicks and refreshes evaluation and apply preview', async () => {
  const proof = deferred(),
    preview = deferred();
  let verified = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({
      data: evaluation(verified ? 'current' : 'stale'),
    }),
    previewGridCorrectionApply: () =>
      verified
        ? preview.promise
        : {
            data: {
              ...applyPreview,
              canApply: false,
              blockers: ['GRID_MODEL_EVALUATION_STALE'],
            },
          },
    verifyGridModelEvaluationCurrentness: () => proof.promise,
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assertOnlyReads(setup.calls);
    assert.match(
      document.body.textContent,
      /Dowody wymagają ponownego sprawdzenia/,
    );
    const button = findButton('Sprawdź aktualność oceny');
    await act(async () => {
      button.click();
      button.click();
    });
    assert.equal(button.disabled, true);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    assert.equal(
      setup.calls.filter(
        ([name]) => name === 'verifyGridModelEvaluationCurrentness',
      ).length,
      1,
    );
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    verified = true;
    await act(async () =>
      proof.resolve({
        data: {
          reportId: 'report-evaluation',
          currentness: evaluation('current').currentness,
          failures: [],
        },
      }),
    );
    await settle();
    assert.match(document.body.textContent, /Aktualność oceny potwierdzona/);
    assert.doesNotMatch(
      document.body.textContent,
      /Dowody wymagają ponownego sprawdzenia/,
    );
    assert.ok(
      setup.calls.filter(
        ([name]) => name === 'getGridCorrectionLearningEvaluation',
      ).length >= 2,
    );
    assert.equal(
      document.querySelector(
        '[aria-label="Zastosowanie wersji"] input[type="checkbox"]',
      ),
      null,
    );
    await act(async () => preview.resolve({ data: applyPreview }));
    await settle();
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    await check('Potwierdzam ograniczony dowód');
    assert.equal(findButton('Zastosuj wersję').disabled, false);
    assert.deepEqual(
      setup.calls
        .filter(([name]) => !READ_ONLY_METHODS.has(name))
        .map(([name]) => name),
      ['verifyGridModelEvaluationCurrentness'],
    );
    assert.deepEqual(
      setup.calls
        .find(([name]) => name === 'verifyGridModelEvaluationCurrentness')
        .slice(1),
      ['report-evaluation'],
    );
  } finally {
    await view.close();
  }
});

test('protected unlabelled control outside the correction queue is excluded rather than counted as reserve', async () => {
  const setup = fixture({
    getGridCorrectionLearningReady: () => ({
      data: {
        ...readiness,
        progressCounts: {
          ...progressCounts,
          validationReserve: { photos: 0, boards: 0 },
          regressionReserve: { photos: 0, boards: 0 },
          buffers: { photos: 53, boards: 0 },
          excluded: { photos: 1, boards: 0 },
          exclusionReasons: [
            {
              reason: 'GRID_CORRECTION_CONTROL_NOT_PENDING',
              photos: 1,
              boards: 0,
            },
          ],
        },
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    for (const label of [
      'Rezerwa do doboru — bez etykiet',
      'Rezerwa do kontroli — bez etykiet',
    ]) {
      const row = [...document.querySelectorAll('tr')].find(
        (item) => item.querySelector('th')?.textContent === label,
      );
      assert.deepEqual(
        [...row.querySelectorAll('td')].map((cell) => Number(cell.textContent)),
        [0, 0],
      );
    }
    const excluded = [...document.querySelectorAll('tr')].find(
      (item) =>
        item.querySelector('th')?.textContent === 'Wyłączone z podziału',
    );
    assert.deepEqual(
      [...excluded.querySelectorAll('td')].map((cell) =>
        Number(cell.textContent),
      ),
      [1, 0],
    );
    assert.match(
      document.body.textContent,
      /Chronione zdjęcie kontrolne bez etykiet nie oczekuje na korektę: 1 zdjęć \/ 0 plansz/,
    );
    assert.match(
      document.body.textContent,
      /Bufory obejmują też zdjęcia bez etykiet/,
    );
    assert.match(
      document.body.textContent,
      /Zapis w zestawie nie potwierdza zakończenia treningu modelu/,
    );
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

for (const [status, hasReport] of [
  ['processing', false],
  ['processing', true],
  ['completed', false],
]) {
  test(`verification waits for completed evaluation with a real report: ${status}, report=${hasReport}`, async () => {
    const setup = fixture({
      listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
      getGridCorrectionLearning: () => ({ data: evaluatedRun }),
      getGridCorrectionLearningEvaluation: () => ({
        data: {
          ...evaluation('current'),
          status,
          report: hasReport ? evaluation('current').report : null,
        },
      }),
    });
    const view = await mount(setup.api);
    try {
      await settle();
      const button = findButton('Sprawdź aktualność oceny');
      assert.equal(button.disabled, true);
      assert.equal(button.getAttribute('aria-busy'), 'false');
      await act(async () => button.click());
      assert.equal(findButton('Zastosuj wersję').disabled, true);
      assert.doesNotMatch(
        document.body.textContent,
        /Wynik dotyczy zakończonego przebiegu|Dowód oceny jest aktualny/,
      );
      assert.match(
        document.body.textContent,
        status === 'processing'
          ? /Ocena jeszcze trwa/
          : /Brak zakończonego raportu oceny/,
      );
      assertOnlyReads(setup.calls);
    } finally {
      await view.close();
    }
  });
}

for (const failureAt of ['workflow', 'evaluation']) {
  test(`failed ${failureAt} GET ends loading, keeps new apply blocked and explains refresh retry`, async () => {
    const pendingRead = deferred();
    let workflowReads = 0,
      evaluationReads = 0;
    const setup = fixture({
      listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
      getGridCorrectionLearning: () => {
        workflowReads += 1;
        return failureAt === 'workflow' && workflowReads === 2
          ? pendingRead.promise
          : { data: evaluatedRun };
      },
      getGridCorrectionLearningEvaluation: () => {
        evaluationReads += 1;
        return failureAt === 'evaluation' && evaluationReads === 2
          ? pendingRead.promise
          : { data: evaluation('current') };
      },
    });
    const view = await mount(setup.api);
    try {
      await settle();
      await click('Odśwież stan uczenia');
      await settle();
      assert.match(
        document.querySelector(
          '[aria-label="Aktualność oceny"] [role="status"]',
        ).textContent,
        /Odczytywanie oceny/,
      );
      await act(async () => pendingRead.reject(new Error('Scoped GET lost')));
      await settle();
      const section = document.querySelector('[aria-label="Aktualność oceny"]');
      assert.equal(section.querySelector('[aria-busy="true"]'), null);
      assert.match(
        section.textContent,
        /Kliknij „Odśwież stan uczenia”, aby ponowić odczyt/,
      );
      assert.equal(findButton('Sprawdź aktualność oceny').disabled, true);
      assert.equal(findButton('Zastosuj wersję').disabled, true);
      await click('Odśwież stan uczenia');
      await settle();
      assert.equal(findButton('Sprawdź aktualność oceny').disabled, false);
      assert.doesNotMatch(
        section.textContent,
        /Scoped GET lost|Odczytywanie oceny/,
      );
      assertOnlyReads(setup.calls);
    } finally {
      await view.close();
    }
  });
}

test('changed labels remain blocked after explicit verification and cannot be bypassed by confirmation', async () => {
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({ data: evaluation() }),
    verifyGridModelEvaluationCurrentness: () => ({
      data: {
        reportId: 'report-evaluation',
        currentness: evaluation().currentness,
        failures: [{ gameId: GAME, code: 'GRID_COHORT_LABEL_STALE' }],
      },
    }),
    // Even an inconsistent cached optimistic preview cannot bypass the failed proof.
    previewGridCorrectionApply: () => ({ data: applyPreview }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Sprawdź aktualność oceny');
    await settle();
    assert.match(
      document.body.textContent,
      /Etykieta człowieka zmieniła się lub wycofano ją/,
    );
    assert.doesNotMatch(
      document.body.textContent,
      /Aktualność oceny potwierdzona/,
    );
    await check('Potwierdzam ograniczony dowód');
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    assert.equal(
      setup.calls.some(([name]) => name === 'startGridCorrectionApply'),
      false,
    );
  } finally {
    await view.close();
  }
});

for (const failureAt of [
  'verification-response',
  'evaluation-read',
  'preview-read',
]) {
  test(`currentness ${failureAt} failure stays blocked until explicit retry`, async () => {
    let attempts = 0,
      reads = 0;
    const setup = fixture({
      listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
      getGridCorrectionLearning: () => ({ data: evaluatedRun }),
      getGridCorrectionLearningEvaluation: () => {
        reads += 1;
        if (failureAt === 'evaluation-read' && attempts === 1)
          throw new Error('Evaluation read lost');
        return { data: evaluation('current') };
      },
      verifyGridModelEvaluationCurrentness: () => {
        attempts += 1;
        if (failureAt === 'verification-response' && attempts === 1)
          throw new Error('Verification response lost');
        return {
          data: {
            reportId: 'report-evaluation',
            currentness: evaluation('current').currentness,
            failures: [],
          },
        };
      },
      previewGridCorrectionApply: () => {
        if (failureAt === 'preview-read' && attempts === 1)
          throw new Error('Preview read lost');
        return { data: applyPreview };
      },
    });
    const view = await mount(setup.api);
    try {
      await settle();
      await check('Potwierdzam ograniczony dowód');
      assert.equal(findButton('Zastosuj wersję').disabled, false);
      await click('Sprawdź aktualność oceny');
      await settle();
      assert.match(document.body.textContent, /lost/);
      const apply = [...document.querySelectorAll('button')].find(
        (item) => item.textContent === 'Zastosuj wersję',
      );
      assert.ok(!apply || apply.disabled);
      if (failureAt !== 'preview-read')
        assert.doesNotMatch(
          document.body.textContent,
          /Aktualność oceny potwierdzona/,
        );
      await click('Sprawdź aktualność oceny');
      await settle();
      await check('Potwierdzam ograniczony dowód');
      assert.equal(findButton('Zastosuj wersję').disabled, false);
      assert.equal(attempts, 2);
      assert.ok(reads >= 2);
      assert.equal(
        setup.calls.some(([name]) => /^(start|resume|rollback)/.test(name)),
        false,
      );
    } finally {
      await view.close();
    }
  });
}

test('a late verification response cannot replace a different selected workflow', async () => {
  const proof = deferred();
  const next = {
    ...evaluatedRun,
    learningId: 'next-run',
    evaluationId: 'next-evaluation',
    createdAt: '2026-11-03T12:00:00Z',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({
      data: { items: [evaluatedRun, next] },
    }),
    getGridCorrectionLearning: (_game, id) => ({
      data: id === RUN ? evaluatedRun : next,
    }),
    getGridCorrectionLearningEvaluation: (_game, id) => ({
      data: evaluation('stale', id === RUN ? 'evaluation' : 'next-evaluation'),
    }),
    previewGridCorrectionApply: (_game, id) => ({
      data: { ...applyPreview, learningId: id, canApply: false },
    }),
    verifyGridModelEvaluationCurrentness: () => proof.promise,
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Sprawdź aktualność oceny');
    const selectionReads = setup.calls.length;
    const nextButton = document.querySelectorAll(
      '[aria-label="Przebiegi uczenia"] button',
    )[1];
    await act(async () => nextButton.click());
    await settle();
    const oldReads = setup.calls.filter(
      ([name, , id]) =>
        name === 'getGridCorrectionLearningEvaluation' && id === RUN,
    ).length;
    await act(async () =>
      proof.resolve({
        data: {
          reportId: 'report-evaluation',
          currentness: evaluation('current').currentness,
          failures: [],
        },
      }),
    );
    await settle();
    assert.doesNotMatch(
      document.body.textContent,
      /Aktualność oceny potwierdzona/,
    );
    assert.equal(findButton('Sprawdź aktualność oceny').disabled, false);
    assert.equal(
      setup.calls.filter(
        ([name, , id]) =>
          name === 'getGridCorrectionLearningEvaluation' && id === RUN,
      ).length,
      oldReads,
    );
    assertOnlyReads(setup.calls.slice(selectionReads));
  } finally {
    await view.close();
  }
});

test('a verification response after unmount cannot read the old game evaluation', async () => {
  const proof = deferred();
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({ data: evaluation() }),
    verifyGridModelEvaluationCurrentness: () => proof.promise,
  });
  const view = await mount(setup.api);
  await settle();
  await click('Sprawdź aktualność oceny');
  await view.close();
  const reads = setup.calls.length;
  const next = fixture({
    getGridCorrectionLearningReady: () => ({
      data: { ...readiness, gameId: OTHER },
    }),
  });
  const second = await mount(next.api, {}, OTHER);
  try {
    await act(async () =>
      proof.resolve({
        data: {
          reportId: 'report-evaluation',
          currentness: evaluation('current').currentness,
          failures: [],
        },
      }),
    );
    await settle();
    assert.equal(setup.calls.length, reads);
    assert.doesNotMatch(
      document.body.textContent,
      /Aktualność oceny potwierdzona/,
    );
    assertOnlyReads(next.calls);
  } finally {
    await second.close();
  }
});

test('an old evaluation read after verification cannot replace a new selected evaluation', async () => {
  const report = deferred();
  let verified = false;
  const next = {
    ...evaluatedRun,
    learningId: 'next-run',
    evaluationId: 'next-evaluation',
    createdAt: '2026-11-03T12:00:00Z',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({
      data: { items: [evaluatedRun, next] },
    }),
    getGridCorrectionLearning: (_game, id) => ({
      data: id === RUN ? evaluatedRun : next,
    }),
    getGridCorrectionLearningEvaluation: (_game, id) =>
      id === RUN && verified
        ? report.promise
        : {
            data: evaluation(
              'stale',
              id === RUN ? 'evaluation' : 'next-evaluation',
            ),
          },
    previewGridCorrectionApply: (_game, id) => ({
      data: { ...applyPreview, learningId: id, canApply: false },
    }),
    verifyGridModelEvaluationCurrentness: () => {
      verified = true;
      return {
        data: {
          reportId: 'report-evaluation',
          currentness: evaluation('current').currentness,
          failures: [],
        },
      };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Sprawdź aktualność oceny');
    await settle();
    const selectionReads = setup.calls.length;
    await act(async () =>
      document
        .querySelectorAll('[aria-label="Przebiegi uczenia"] button')[1]
        .click(),
    );
    await settle();
    await act(async () => report.resolve({ data: evaluation('current') }));
    await settle();
    assert.doesNotMatch(
      document.body.textContent,
      /Aktualność oceny potwierdzona|Dowód oceny jest aktualny/,
    );
    assert.match(
      document.body.textContent,
      /Dowody wymagają ponownego sprawdzenia/,
    );
    assert.equal(findButton('Sprawdź aktualność oceny').disabled, false);
    assertOnlyReads(setup.calls.slice(selectionReads));
  } finally {
    await view.close();
  }
});

test('a stale optimistic apply response cannot overwrite the fresh blocked preview', async () => {
  const oldPreview = deferred();
  let verified = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({
      data: evaluation('current'),
    }),
    previewGridCorrectionApply: () =>
      verified
        ? {
            data: {
              ...applyPreview,
              canApply: false,
              blockers: ['GRID_APPLY_ASSIGNMENT_CHANGED'],
            },
          }
        : oldPreview.promise,
    verifyGridModelEvaluationCurrentness: () => {
      verified = true;
      return {
        data: {
          reportId: 'report-evaluation',
          currentness: evaluation('current').currentness,
          failures: [],
        },
      };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Sprawdź aktualność oceny');
    await settle();
    assert.match(
      document.body.textContent,
      /Przypisana wersja gry zmieniła się/,
    );
    await act(async () => oldPreview.resolve({ data: applyPreview }));
    await settle();
    await check('Potwierdzam ograniczony dowód');
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    assert.match(
      document.body.textContent,
      /Przypisana wersja gry zmieniła się/,
    );
  } finally {
    await view.close();
  }
});

test('a manual refresh after a lost verification response waits for an authoritative evaluation read', async () => {
  const list = deferred();
  let lost = false;
  const setup = fixture({
    listGridCorrectionLearning: () =>
      lost ? list.promise : { data: { items: [evaluatedRun] } },
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({
      data: evaluation('current'),
    }),
    verifyGridModelEvaluationCurrentness: () => {
      lost = true;
      throw new Error('Verification response lost');
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await check('Potwierdzam ograniczony dowód');
    await click('Sprawdź aktualność oceny');
    await settle();
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    await click('Odśwież stan uczenia');
    await settle();
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    await act(async () => list.resolve({ data: { items: [evaluatedRun] } }));
    await settle();
    await check('Potwierdzam ograniczony dowód');
    assert.equal(findButton('Zastosuj wersję').disabled, false);
    assert.equal(
      setup.calls.filter(
        ([name]) => name === 'verifyGridModelEvaluationCurrentness',
      ).length,
      1,
    );
  } finally {
    await view.close();
  }
});

test('reload reconciles a lost successful verification response by GET without replaying POST', async () => {
  let verified = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({
      data: evaluation(verified ? 'current' : 'stale'),
    }),
    previewGridCorrectionApply: () => ({
      data: { ...applyPreview, canApply: verified },
    }),
    verifyGridModelEvaluationCurrentness: () => {
      verified = true;
      throw new Error('Verification response lost');
    },
  });
  const first = await mount(setup.api);
  await settle();
  await click('Sprawdź aktualność oceny');
  await settle();
  assert.match(document.body.textContent, /Verification response lost/);
  const saved = first.saved();
  await first.close();
  const second = await mount(setup.api, saved);
  try {
    await settle();
    assert.match(document.body.textContent, /Dowód oceny jest aktualny/);
    await check('Potwierdzam ograniczony dowód');
    assert.equal(findButton('Zastosuj wersję').disabled, false);
    assert.equal(
      setup.calls.filter(
        ([name]) => name === 'verifyGridModelEvaluationCurrentness',
      ).length,
      1,
    );
    assert.equal(
      setup.calls.some(([name]) => /^(start|resume|rollback)/.test(name)),
      false,
    );
  } finally {
    await second.close();
  }
});

test('pending default model is shown as loading even when readiness is already known', async () => {
  const defaults = deferred();
  const setup = fixture({ getGridModelDefault: () => defaults.promise });
  const view = await mount(setup.api);
  try {
    await settle();
    const model = document.querySelector('.gridCorrectionLearning > p');
    assert.match(model.textContent, /Wczytywanie/);
    assert.doesNotMatch(model.textContent, /Nie udało się ustalić/);
    await act(async () =>
      defaults.resolve({ data: { version: null, revision: 2 } }),
    );
    await settle();
    assert.match(model.textContent, /Brak wersji domyślnej/);
  } finally {
    await view.close();
  }
});

test('a failed refresh list still completes the operator selection invalidated by refresh', async () => {
  const oldDetail = deferred();
  let lists = 0,
    details = 0;
  const first = { ...run, verdict: null };
  const next = {
    ...run,
    learningId: 'chosen-next',
    verdict: null,
    status: 'failed',
    errorCode: 'FRESH_SELECTED_B',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => {
      if (++lists === 2) throw new Error('List read failed');
      return { data: { items: [first, next] } };
    },
    getGridCorrectionLearning: (_game, id) =>
      id === RUN
        ? { data: first }
        : ++details === 1
          ? oldDetail.promise
          : { data: next },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [
      ...document.querySelectorAll('[aria-label="Przebiegi uczenia"] button'),
    ].find((b) => b.textContent.endsWith('Błąd'));
    await act(async () => button.click());
    await click('Odśwież stan uczenia');
    await settle();
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_SELECTED_B/,
    );
    assert.match(document.body.textContent, /List read failed/);
    await act(async () =>
      oldDetail.resolve({ data: { ...next, errorCode: 'OLD_SELECTED_B' } }),
    );
    await settle();
    assert.doesNotMatch(document.body.textContent, /OLD_SELECTED_B/);
    assert.equal(details, 2);
  } finally {
    await view.close();
  }
});

for (const changed of [false, true]) {
  test(`report fetch failure ${changed ? 'clears a changed evaluation' : 'retains the same evaluation'}`, async () => {
    let refreshing = false;
    const setup = fixture({
      listGridCorrectionLearning: () => ({
        data: { items: [{ ...run, verdict: null }] },
      }),
      getGridCorrectionLearning: () => ({
        data: {
          ...run,
          verdict: null,
          evaluationId: refreshing && changed ? 'new-report' : 'old-report',
        },
      }),
      getGridCorrectionLearningEvaluation: () => {
        if (refreshing) throw new Error('Report read failed');
        return {
          data: { ...evaluation('current', 'old-report'), report: null },
        };
      },
    });
    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(document.body.textContent, /Raport oceny: PASS/);
      refreshing = true;
      await click('Odśwież stan uczenia');
      await settle();
      assert.match(document.body.textContent, /Report read failed/);
      assert.equal(
        document.body.textContent.includes('Raport oceny: PASS'),
        !changed,
      );
    } finally {
      await view.close();
    }
  });
}

test('slow readiness does not hide existing workflow status on entry', async () => {
  const ready = deferred();
  const failed = {
    ...run,
    verdict: null,
    status: 'failed',
    errorCode: 'VISIBLE_HISTORY',
  };
  const setup = fixture({
    getGridCorrectionLearningReady: () => ready.promise,
    listGridCorrectionLearning: () => ({ data: { items: [failed] } }),
    getGridCorrectionLearning: () => ({ data: failed }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /VISIBLE_HISTORY/,
    );
    const button = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Odświeżanie stanu uczenia…',
    );
    assert.ok(button?.disabled);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    await act(async () => ready.resolve({ data: readiness }));
    await settle();
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('manual refresh immediately loads, deduplicates clicks and shows fresh status before readiness', async (t) => {
  let now = Date.parse('2026-11-03T12:00:00Z');
  t.mock.method(Date, 'now', () => now);
  const ready = deferred();
  let reads = 0,
    changed = false;
  const setup = fixture({
    getGridCorrectionLearningReady: () =>
      ++reads === 1 ? { data: readiness } : ready.promise,
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null }] },
    }),
    getGridCorrectionLearning: () => ({
      data: {
        ...run,
        verdict: null,
        errorCode: changed ? 'FRESH_STATUS' : 'PREVIOUS_STATUS',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const previous = [...document.querySelectorAll('[role="status"]')].find(
      (p) => p.textContent.startsWith('Stan odświeżony:'),
    ).textContent;
    now += 1000;
    changed = true;
    const button = [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Odśwież stan uczenia',
    );
    await act(async () => {
      button.click();
      assert.equal(button.disabled, false); // before React commits this event batch
      button.click();
    });
    assert.equal(button.textContent, 'Odświeżanie stanu uczenia…');
    assert.equal(button.disabled, true);
    assert.equal(button.getAttribute('aria-busy'), 'true');
    await settle();
    assert.equal(reads, 2);
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_STATUS/,
    );
    await act(async () => ready.resolve({ data: readiness }));
    await settle();
    assert.equal(button.disabled, false);
    assert.equal(button.getAttribute('aria-busy'), 'false');
    assert.equal(button.textContent, 'Odśwież stan uczenia');
    const confirmation = [...document.querySelectorAll('[role="status"]')].find(
      (p) => p.textContent.startsWith('Stan odświeżony:'),
    ).textContent;
    assert.notEqual(confirmation, previous);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('readiness failure preserves workflow data and releases refresh for explicit retry', async () => {
  let reads = 0;
  const setup = fixture({
    getGridCorrectionLearningReady: () => {
      if (++reads === 2) throw new Error('Readiness timed out');
      return { data: readiness };
    },
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null }] },
    }),
    getGridCorrectionLearning: () => ({
      data: {
        ...run,
        verdict: null,
        errorCode: reads > 1 ? 'FRESH_AFTER_FAILURE' : 'RETAINED_WORKFLOW',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Odśwież stan uczenia');
    await settle();
    assert.match(document.body.textContent, /Readiness timed out/);
    assert.match(
      document.querySelector('[aria-label="Postęp uczenia"]').textContent,
      /FRESH_AFTER_FAILURE/,
    );
    await click('Odśwież stan uczenia');
    await settle();
    assert.equal(reads, 3);
    assert.doesNotMatch(document.body.textContent, /Readiness timed out/);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

test('late refresh responses after unmount cannot replace another game or trigger a stale status read', async () => {
  const oldReady = deferred(),
    oldList = deferred();
  const old = fixture({
    getGridCorrectionLearningReady: () => oldReady.promise,
    listGridCorrectionLearning: () => oldList.promise,
  });
  const first = await mount(old.api);
  await first.close();
  const next = {
    ...run,
    gameId: OTHER,
    verdict: null,
    errorCode: 'NEW_GAME_STATUS',
  };
  const fresh = fixture({
    getGridCorrectionLearningReady: () => ({
      data: { ...readiness, gameId: OTHER },
    }),
    listGridCorrectionLearning: () => ({ data: { items: [next] } }),
    getGridCorrectionLearning: () => ({ data: next }),
  });
  const second = await mount(fresh.api, {}, OTHER);
  try {
    await settle();
    await act(async () => {
      oldReady.resolve({ data: readiness });
      oldList.resolve({
        data: { items: [{ ...run, errorCode: 'OLD_GAME_STATUS' }] },
      });
    });
    await settle();
    assert.match(document.body.textContent, /NEW_GAME_STATUS/);
    assert.doesNotMatch(document.body.textContent, /OLD_GAME_STATUS/);
    assert.equal(
      old.calls.some(([name]) => name === 'getGridCorrectionLearning'),
      false,
    );
  } finally {
    await second.close();
  }
});

test('refresh after an explicit resume supersedes an older in-flight refresh', async () => {
  const oldReady = deferred(),
    oldList = deferred();
  let readyReads = 0,
    listReads = 0,
    resumed = false;
  const previous = { ...run, status: 'failed', verdict: null };
  const latest = {
    ...run,
    status: 'created',
    verdict: null,
    errorCode: 'LATEST_RESUMED',
  };
  const setup = fixture({
    getGridCorrectionLearningReady: () => {
      if (++readyReads === 2) return oldReady.promise;
      return { data: readiness };
    },
    listGridCorrectionLearning: () => {
      if (++listReads === 2) return oldList.promise;
      return { data: { items: [resumed ? latest : previous] } };
    },
    getGridCorrectionLearning: () => ({ data: resumed ? latest : previous }),
    resumeGridCorrectionLearning: () => {
      resumed = true;
      return { data: latest };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await click('Odśwież stan uczenia');
    await click('Wznów uczenie');
    await settle();
    assert.match(document.body.textContent, /LATEST_RESUMED/);
    await act(async () => {
      oldReady.resolve({
        data: { ...readiness, blockers: ['STALE_READINESS'], canStart: false },
      });
      oldList.resolve({
        data: { items: [{ ...previous, errorCode: 'STALE_WORKFLOW' }] },
      });
    });
    await settle();
    assert.match(document.body.textContent, /LATEST_RESUMED/);
    assert.doesNotMatch(
      document.body.textContent,
      /STALE_READINESS|STALE_WORKFLOW/,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'resumeGridCorrectionLearning')
        .length,
      1,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'getGridCorrectionLearning')
        .length,
      2,
    );
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (b) => b.textContent === 'Odśwież stan uczenia',
      ).disabled,
      false,
    );
  } finally {
    await view.close();
  }
});

test('entry reads readiness and history without creating a workflow, even when ready', async () => {
  const { api, calls } = fixture();
  const view = await mount(api);
  try {
    await settle();
    assert.match(document.body.textContent, /32/);
    assert.match(document.body.textContent, /nie jest udokumentowany/);
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (button) => button.textContent === 'Przywróć wersję gry',
      ).disabled,
      true,
    );
    assert.ok(calls.length >= 6);
    assertOnlyReads(calls);
  } finally {
    await view.close();
  }
});
test('lost start response survives reload and exact command is retried only by explicit action', async () => {
  let failures = 1;
  const setup = fixture({
    startGridCorrectionLearning: () => {
      if (failures--) throw new Error('lost response');
      return { data: { ...run, verdict: null, status: 'created' } };
    },
  });
  let view = await mount(setup.api);
  await settle();
  await click('Ulepsz siatki z korekt');
  const first = setup.calls.find(
    ([name]) => name === 'startGridCorrectionLearning',
  );
  const saved = view.saved();
  assert.ok(saved[learningCommandKey(apiBaseUrl, GAME)]);
  await view.close();
  const count = setup.calls.filter(
    ([name]) => name === 'startGridCorrectionLearning',
  ).length;
  view = await mount(setup.api, saved);
  try {
    await settle();
    assert.equal(
      setup.calls.filter(([name]) => name === 'startGridCorrectionLearning')
        .length,
      count,
    );
    await click('Ponów zapisane polecenie uczenia');
    assert.deepEqual(
      setup.calls
        .filter(([name]) => name === 'startGridCorrectionLearning')
        .at(-1),
      first,
    );
    assert.equal(view.saved()[learningCommandKey(apiBaseUrl, GAME)], undefined);
  } finally {
    await view.close();
  }
});
test('apply requires limited-evidence confirmation and other games remain opt-in', async () => {
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    startGridCorrectionApply: () => ({
      data: {
        applyId: 'apply',
        gameId: GAME,
        learningId: RUN,
        versionId: 'candidate',
        status: 'created',
        steps: [],
        createdAt: '2026-11-02',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [...document.querySelectorAll('button')].find(
      (item) => item.textContent === 'Zastosuj wersję',
    );
    assert.ok(button.disabled);
    assertOnlyReads(setup.calls);
    await check('Potwierdzam ograniczony dowód');
    assert.equal(button.disabled, false);
    await click('Zastosuj wersję');
    const call = setup.calls.find(
      ([name]) => name === 'startGridCorrectionApply',
    );
    assert.deepEqual(call[3].additionalGameIds, []);
    assert.equal(call[3].confirmLimitedEvidence, true);
    assert.equal(call[3].previewSha256, applyPreview.previewSha256);
  } finally {
    await view.close();
  }
});
test('partial success with stale evaluated evidence can resume the same apply while new apply stays blocked', async () => {
  const partial = {
    applyId: 'durable-apply',
    gameId: GAME,
    learningId: RUN,
    versionId: 'candidate',
    status: 'failed',
    createdAt: '2026-11-02',
    errorCode: 'GRID_MODEL_REVISION_CONFLICT',
    steps: [
      {
        kind: 'publish',
        gameId: null,
        status: 'completed',
        receipt: { revision: 1 },
      },
      { kind: 'activate', gameId: GAME, status: 'pending' },
    ],
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({ data: evaluation('stale') }),
    listGridCorrectionApply: () => ({ data: { items: [partial] } }),
    resumeGridCorrectionApply: () => ({
      data: { ...partial, status: 'created' },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    assert.match(document.body.textContent, /Wykonane kroki są zachowane/);
    assertOnlyReads(setup.calls);
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    assert.equal(findButton('Wznów zastosowanie').disabled, false);
    assert.equal(
      setup.calls.some(([name]) => name === 'resumeGridCorrectionApply'),
      false,
    );
    await click('Wznów zastosowanie');
    assert.deepEqual(
      setup.calls
        .find(([name]) => name === 'resumeGridCorrectionApply')
        .slice(1),
      [GAME, RUN, 'durable-apply'],
    );
    await settle();
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    assert.equal(
      setup.calls.some(([name]) => name === 'startGridCorrectionApply'),
      false,
    );
  } finally {
    await view.close();
  }
});

test('lost apply response replays the exact durable command after remount despite stale evaluated evidence', async () => {
  let attempts = 0,
    stale = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [evaluatedRun] } }),
    getGridCorrectionLearning: () => ({ data: evaluatedRun }),
    getGridCorrectionLearningEvaluation: () => ({
      data: evaluation(stale ? 'stale' : 'current'),
    }),
    startGridCorrectionApply: () => {
      attempts++;
      throw new Error('lost apply response');
    },
  });
  let view = await mount(setup.api);
  await settle();
  await check('Potwierdzam ograniczony dowód');
  await click('Zastosuj wersję');
  const first = setup.calls.find(
      ([name]) => name === 'startGridCorrectionApply',
    ),
    saved = view.saved();
  await view.close();
  stale = true;
  const beforeRemount = setup.calls.length;
  view = await mount(setup.api, saved);
  try {
    await settle();
    assert.equal(attempts, 1);
    assertOnlyReads(setup.calls.slice(beforeRemount));
    assert.equal(findButton('Zastosuj wersję').disabled, true);
    assert.equal(
      findButton('Ponów zapisane polecenie zastosowania').disabled,
      false,
    );
    await click('Ponów zapisane polecenie zastosowania');
    assert.equal(attempts, 2);
    assert.deepEqual(
      setup.calls
        .filter(([name]) => name === 'startGridCorrectionApply')
        .at(-1),
      first,
    );
    assert.equal(findButton('Zastosuj wersję').disabled, true);
  } finally {
    await view.close();
  }
});

test('foreign default conflict refreshes preview and requires new confirmation without automatic retraining', async () => {
  let changed = false;
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    previewGridCorrectionApply: () => ({
      data: changed
        ? {
            ...applyPreview,
            canApply: false,
            blockers: ['GRID_APPLY_DEFAULT_CHANGED'],
            previewSha256: 'c'.repeat(64),
          }
        : applyPreview,
    }),
    startGridCorrectionApply: () => {
      changed = true;
      return {
        error: { detail: 'GRID_APPLY_DEFAULT_CHANGED' },
        response: { status: 409 },
      };
    },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await check('Potwierdzam ograniczony dowód');
    await click('Zastosuj wersję');
    assert.match(
      document.body.textContent,
      /Inna baza wymaga nowego przebiegu uczenia/,
    );
    assert.equal(
      [...document.querySelectorAll('button')].find(
        (item) => item.textContent === 'Zastosuj wersję',
      ).disabled,
      true,
    );
    assert.equal(
      setup.calls.filter(([name]) => name === 'startGridCorrectionApply')
        .length,
      1,
    );
    assert.equal(
      setup.calls.some(([name]) => name === 'startGridCorrectionLearning'),
      false,
    );
    assert.equal(
      document.body.textContent.includes(
        'Ponów zapisane polecenie zastosowania',
      ),
      false,
    );
  } finally {
    await view.close();
  }
});

test('another game is opt-in and changing scope clears the previous confirmation', async () => {
  const setup = fixture({
    listGridCorrectionLearning: () => ({ data: { items: [run] } }),
    previewGridCorrectionApply: (_game, _learning, ids) => ({
      data: {
        ...applyPreview,
        additionalGameIds: ids,
        targets: [
          ...applyPreview.targets,
          ...ids.map((id) => ({
            gameId: id,
            assignedVersionId: 'base',
            assignmentRevision: 1,
            requiresComparison: false,
          })),
        ],
      },
    }),
    startGridCorrectionApply: () => ({
      data: {
        applyId: 'apply',
        gameId: GAME,
        learningId: RUN,
        versionId: 'candidate',
        status: 'created',
        steps: [],
        createdAt: '2026-11-02',
      },
    }),
  });
  const view = await mount(setup.api);
  try {
    await settle();
    await check('Potwierdzam ograniczony dowód');
    await check('777');
    await settle();
    const button = [...document.querySelectorAll('button')].find(
      (item) => item.textContent === 'Zastosuj wersję',
    );
    assert.equal(button.disabled, true);
    await check('Potwierdzam ograniczony dowód');
    await click('Zastosuj wersję');
    assert.deepEqual(
      setup.calls.find(([name]) => name === 'startGridCorrectionApply')[3]
        .additionalGameIds,
      [OTHER],
    );
  } finally {
    await view.close();
  }
});

test('a late workflow answer cannot replace a later explicit selection', async () => {
  let resolveOld;
  const oldAnswer = new Promise((resolve) => {
    resolveOld = resolve;
  });
  const next = {
    ...run,
    learningId: 'next-run',
    verdict: 'REVISE',
    errorCode: 'NEW_SELECTION',
  };
  const setup = fixture({
    listGridCorrectionLearning: () => ({
      data: { items: [{ ...run, verdict: null, status: 'created' }, next] },
    }),
    getGridCorrectionLearning: (_game, id) =>
      id === RUN ? oldAnswer : { data: next },
  });
  const view = await mount(setup.api);
  try {
    await settle();
    const button = [...document.querySelectorAll('button')].find((item) =>
      item.textContent.endsWith('REVISE'),
    );
    assert.ok(button);
    await act(async () => button.click());
    await act(async () =>
      resolveOld({ data: { ...run, errorCode: 'OLD_SELECTION' } }),
    );
    assert.match(document.body.textContent, /NEW_SELECTION/);
    assert.doesNotMatch(document.body.textContent, /OLD_SELECTION/);
    assertOnlyReads(setup.calls);
  } finally {
    await view.close();
  }
});

for (const [availability, expected] of [
  [
    {
      photos: 12,
      boards: 34,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 8,
      boardDeficit: 26,
      splitStatus: 'minima',
    },
    /Brakuje co najmniej: 8 zdjęć \/ 26 plansz/,
  ],
  [
    {
      photos: 40,
      boards: 80,
      minimumPhotos: 20,
      minimumBoards: 60,
      photoDeficit: 0,
      boardDeficit: 0,
      splitStatus: 'infeasible',
    },
    /bufory lub ochrona danych uniemożliwiają bezpieczny podział/,
  ],
  [null, /Liczba dostępnych korekt i braków nie została ustalona/],
])
  test(`blocked availability remains honest: ${availability?.splitStatus ?? 'unknown'}`, async () => {
    const setup = fixture({
      getGridCorrectionLearningReady: () => ({
        data: {
          ...readiness,
          dataAvailability: availability,
          roleCounts: [],
          canStart: false,
          blockers: ['GRID_COHORT_MINIMUM_NOT_MET'],
        },
      }),
    });

    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(document.body.textContent, expected);
      assert.equal(
        [...document.querySelectorAll('button')].find(
          (item) => item.textContent === 'Ulepsz siatki z korekt',
        ).disabled,
        true,
      );
      assert.doesNotMatch(document.body.textContent, /Zdjęcia buforowe: 0/);
      if (availability === null)
        assert.doesNotMatch(
          document.body.textContent,
          /Dostępne przed buforami: 0/,
        );
    } finally {
      await view.close();
    }
  });

for (const status of ['completed', 'failed'])
  test(`own default explains ${status} history without offering impossible opt-in`, async () => {
    const operation = {
      applyId: 'apply',
      gameId: GAME,
      learningId: RUN,
      versionId: 'candidate',
      status,
      createdAt: '2026-11-02',
      steps: [
        {
          kind: 'publish',
          gameId: null,
          status: 'completed',
          receipt: { kind: 'already-published' },
        },
        { kind: 'set_default', gameId: null, status: 'completed' },
        {
          kind: 'activate',
          gameId: GAME,
          status: status === 'completed' ? 'completed' : 'pending',
        },
      ],
    };
    const setup = fixture({
      listGridCorrectionLearning: () => ({ data: { items: [run] } }),
      previewGridCorrectionApply: () => ({
        data: {
          ...applyPreview,
          defaultVersionId: 'candidate',
          canApply: false,
          blockers: ['GRID_APPLY_ALREADY_DEFAULT'],
          targets: [],
        },
      }),
      listGridCorrectionApply: () => ({ data: { items: [operation] } }),
    });
    const view = await mount(setup.api);
    try {
      await settle();
      assert.match(
        document.body.textContent,
        /Kandydat jest już wersją domyślną/,
      );
      assert.match(
        document.body.textContent,
        /Potwierdzono istniejącą publikację/,
      );
      assert.doesNotMatch(
        document.body.textContent,
        /Inna baza wymaga nowego przebiegu|Zastosuj także w innych ocenionych grach/,
      );
      assert.equal(
        [...document.querySelectorAll('button')].some(
          (button) => button.textContent === 'Zastosuj wersję',
        ),
        false,
      );
      assert.equal(
        [...document.querySelectorAll('button')].some(
          (button) => button.textContent === 'Wznów zastosowanie',
        ),
        status === 'failed',
      );
    } finally {
      await view.close();
    }
  });

test('detector full-photo deficit explains real geometry verification separately from symbols', async () => {
  const { api, calls } = fixture({
    getGridCorrectionLearningReady: async () => ({
      data: {
        ...readiness,
        detectorReadiness: {
          fullPhotos: 0,
          partialPhotos: 4,
          photos: 4,
          partialExcludedFromDetector: 4,
          roles: [],
          reasonCodes: ['SCREEN_FULL_PHOTOS_REQUIRED'],
        },
      },
    }),
  });
  const ui = await mount(api);
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  assert.match(document.body.textContent, /Geometria zdjęć/);
  assert.match(document.body.textContent, /Symbole nie są etykietą geometrii/);
  assert.match(
    document.body.textContent,
    /Brak kalibracji automatu nie blokuje/,
  );
  const link = [...document.querySelectorAll('a')].find(
    (x) => x.textContent === 'Otwórz narzędzie geometrii',
  );
  assert.equal(new URL(link.href).searchParams.get('section'), 'reviews');
  assertOnlyReads(calls);
  await ui.close();
});

test('screen mode requires an explicit preview and keeps resolved historical pins separate from user overrides', async () => {
  const historical = [
    { gameId: OTHER, cohortId: 'cohort-other', manifestSha256: 'b'.repeat(64) },
  ];
  const { api, calls } = fixture({
    previewGridCorrectionLearning: async (_game, body) => ({
      data: {
        ...readiness,
        trainingMode: body.trainingMode,
        rescueVariant: null,
        historicalCohorts: historical,
      },
    }),
    startGridCorrectionLearning: async () => ({ error: { code: 'LOST' } }),
  });
  const ui = await mount(api);
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  const select = document.querySelector('select[aria-label="Cel uczenia"]');
  await act(async () => {
    select.value = 'screen+grid';
    select.dispatchEvent(new window.Event('change', { bubbles: true }));
  });
  assert.equal(findButton('Ulepsz siatki z korekt').disabled, true);
  assertOnlyReads(calls);
  await act(async () => findButton('Sprawdź zakres/podział').click());
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
  const preview = calls.find((x) => x[0] === 'previewGridCorrectionLearning');
  assert.equal(preview[2].trainingMode, 'screen+grid');
  assert.deepEqual(preview[2].historicalCohorts, []);
  assert.equal(findButton('Ulepsz siatki z korekt').disabled, false);
  await act(async () => findButton('Ulepsz siatki z korekt').click());
  const command = calls.find((x) => x[0] === 'startGridCorrectionLearning')[2];
  assert.equal(command.trainingMode, 'screen+grid');
  assert.deepEqual(command.historicalCohorts, []);
  await ui.close();
});

test('refresh excludes an explicit preview and retains the refreshed list and selected run', async () => {
  const ready = deferred(),
    list = deferred();
  let reads = 0,
    lists = 0;
  const { api, calls } = fixture({
    getGridCorrectionLearningReady: () =>
      ++reads === 1 ? { data: readiness } : ready.promise,
    listGridCorrectionLearning: () =>
      ++lists === 1 ? { data: { items: [] } } : list.promise,
    getGridCorrectionLearning: () => ({
      data: { ...run, errorCode: 'FRESH_RUN' },
    }),
  });
  const ui = await mount(api);
  try {
    await settle();
    await click('Odśwież stan uczenia');
    const preview = findButton('Sprawdź zakres/podział');
    assert.equal(preview.disabled, true);
    await act(async () => preview.click());
    assert.equal(
      calls.filter(([name]) => name === 'previewGridCorrectionLearning').length,
      0,
    );
    await act(async () => {
      list.resolve({ data: { items: [run] } });
      ready.resolve({ data: readiness });
    });
    await settle();
    assert.match(document.body.textContent, /FRESH_RUN/);
    assert.equal(findButton('Sprawdź zakres/podział').disabled, false);
    assertOnlyReads(calls);
  } finally {
    await ui.close();
  }
});

test('legacy refresh restores the grid-only options key after returning from screen mode', async () => {
  const { api, calls } = fixture({
    previewGridCorrectionLearning: (_game, body) => ({
      data: { ...readiness, trainingMode: body.trainingMode },
    }),
  });
  const ui = await mount(api);
  try {
    await settle();
    const mode = document.querySelector('select[aria-label="Cel uczenia"]');
    for (const value of ['screen+grid', 'grid-only']) {
      await act(async () => {
        mode.value = value;
        mode.dispatchEvent(new window.Event('change', { bubbles: true }));
      });
      if (value === 'screen+grid') await click('Sprawdź zakres/podział');
    }
    assert.equal(findButton('Ulepsz siatki z korekt').disabled, true);
    await click('Odśwież stan uczenia');
    await settle();
    assert.equal(findButton('Ulepsz siatki z korekt').disabled, false);
    assert.equal(
      calls.filter(([name]) => name === 'previewGridCorrectionLearning').length,
      1,
    );
  } finally {
    await ui.close();
  }
});

for (const withB of [false, true])
  test(`explicit v4 ${withB ? 'B component' : 'without B'} stays advanced, read-only until start and pins exactly previewed purposes`, async () => {
    const SOURCE = '44444444-4444-4444-8444-444444444444',
      COPY = '55555555-5555-4555-8555-555555555555';
    const { api, calls } = fixture({
      previewGridCorrectionLearning: async (_game, body) => ({
        data: {
          ...readiness,
          trainingMode: body.trainingMode,
          policyVersion: body.policyVersion,
          validationAssignments: body.validationAssignments,
          validationComponents: [
            {
              componentKey: 'c'.repeat(64),
              sources: [
                {
                  sourceId: SOURCE,
                  displayName: '462201-462209.jpg',
                  rangeStart: 462201,
                  rangeEnd: 462209,
                  qualifiedBoards: 9,
                },
                {
                  sourceId: COPY,
                  displayName: '462201-462209-copy.jpg',
                  rangeStart: 462201,
                  rangeEnd: 462209,
                  qualifiedBoards: 9,
                },
              ],
              priorRoles: [],
              priorPurposes: [],
              options: [
                { purpose: 'A', allowed: true, reasonCodes: [] },
                { purpose: 'B', allowed: true, reasonCodes: [] },
                { purpose: 'BUFFER', allowed: true, reasonCodes: [] },
              ],
            },
          ],
          validationPurposeCounts: {
            A: { photos: 5, boards: 45, fullPhotos: 5 },
            B: {
              photos: withB ? 1 : 0,
              boards: withB ? 9 : 0,
              fullPhotos: withB ? 1 : 0,
            },
          },
        },
      }),
      startGridCorrectionLearning: async () => ({ error: { code: 'LOST' } }),
    });
    const ui = await mount(api);
    await settle();
    const advanced = [...document.querySelectorAll('details')].find(
      (x) =>
        x.querySelector('summary')?.textContent ===
        'Zaawansowane: zakres oceny',
    );
    assert.equal(advanced.open, false);
    await check('Osobny test automatycznej akceptacji');
    assert.equal(findButton('Ulepsz siatki z korekt').disabled, true);
    assert.equal(
      calls.some((x) => x[0] === 'previewGridCorrectionLearning'),
      false,
    );
    await click('Sprawdź zakres/podział');
    await settle();
    let expected = {};
    if (withB) {
      const select = document.querySelector(
        'select[aria-label="Przeznaczenie 462201-462209.jpg"]',
      );
      await act(async () => {
        select.value = 'B';
        select.dispatchEvent(new window.Event('change', { bubbles: true }));
      });
      assert.equal(findButton('Ulepsz siatki z korekt').disabled, true);
      await click('Sprawdź zakres/podział');
      await settle();
      expected = { [SOURCE]: 'B', [COPY]: 'B' };
    }
    assert.equal(
      calls.some((x) => x[0] === 'startGridCorrectionLearning'),
      false,
    );
    assert.match(document.body.textContent, /Brak B nie blokuje/);
    assert.equal(findButton('Ulepsz siatki z korekt').disabled, false);
    await click('Ulepsz siatki z korekt');
    const command = calls.find(
      (x) => x[0] === 'startGridCorrectionLearning',
    )[2];
    assert.equal(command.policyVersion, 'application-grid-corrections-v4');
    assert.equal(command.trainingMode, 'grid-only');
    assert.deepEqual(command.validationAssignments, expected);
    assert.deepEqual(
      calls.filter((x) => x[0] === 'previewGridCorrectionLearning').at(-1)[2]
        .validationAssignments,
      expected,
    );
    await ui.close();
  });

for (const version of ['v1', 'v2', 'v3', 'v4'])
  test(`legacy ${version} quality report remains readable without automatic qualification`, async () => {
    const view = evaluation('current');
    view.report.schemaVersion = 'grid-model-evaluation-read-' + version;
    if (version === 'v1' || version === 'v2') delete view.report.scope;
    const { api, calls } = fixture({
      listGridCorrectionLearning: async () => ({
        data: { items: [evaluatedRun] },
      }),
      getGridCorrectionLearning: async () => ({ data: evaluatedRun }),
      getGridCorrectionLearningEvaluation: async () => ({ data: view }),
    });
    const ui = await mount(api);
    await act(async () => new Promise((resolve) => setTimeout(resolve, 30)));
    assert.match(document.body.textContent, /PASS/);
    assert.doesNotMatch(document.body.textContent, /Automat.*kwalifikuje się/);
    assertOnlyReads(calls);
    await ui.close();
  });
