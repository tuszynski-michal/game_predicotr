// Edited-proposal tests run the real backend validator, so the configured Python
// environment must include Pydantic and the API dependencies. Set
// GAME_PREDICTOR_TEST_PYTHON to override the repository virtual environment.
import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'localStorage',
])
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { GridGeometryProposals, proposalCommandKey } =
  await import('../src/features/operational-reviews/grid-geometry-proposals.tsx');
const { reviewerProxyTarget } =
  await import('../src/security/reviewer-proxy-policy.ts');
const { OperationalReviewWorkspace } =
  await import('../src/features/operational-reviews/operational-review-workspace.tsx');
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.open = false;
};
dom.window.HTMLCanvasElement.prototype.getContext = () =>
  new Proxy(
    { drawImage: () => {} },
    { get: (obj, key) => obj[key] ?? (() => {}) },
  );
URL.createObjectURL = () => 'blob:proposal-preview';
URL.revokeObjectURL = () => {};
after(() => dom.window.close());
const uuid = '11111111-1111-4111-8111-111111111111';
const nodes = Array.from({ length: 24 }, (_, i) => ({
  x: 10 + (i % 6) * 20,
  y: 10 + Math.floor(i / 6) * 20,
}));
const item = {
  id: uuid,
  gameId: uuid,
  geometry: {},
  positionIndex: 0,
  sequenceNumber: 100,
  sourceChecksumSha256: 'a'.repeat(64),
  sourceWidth: 200,
  sourceHeight: 200,
  latticeNodes: nodes,
  geometryRevision: 0,
  resolutionRevision: 0,
  geometryQualification: null,
};
const completeQualification = {
  version: 'manual-geometry-qualification-v1',
  completenessStatus: 'complete',
  unavailableCellIndices: [],
  excludeFromGeometryTraining: false,
  exclusionReason: null,
};
const proposal = {
  id: uuid,
  revision: 1,
  state: 'pending',
  applicable: true,
  reasons: [],
  accepted: null,
  candidate: {
    originalGeometry: {
      corners: [nodes[0], nodes[5], nodes[23], nodes[18]],
      latticeNodes: nodes,
      geometryQualification: completeQualification,
    },
    originalCandidateSha256: 'b'.repeat(64),
    expectedGeometryRevision: 0,
    expectedResolutionRevision: 0,
    modelSnapshot: {
      model: { version: 'v-test', manifestChecksumSha256: 'c'.repeat(64) },
    },
  },
};
const settle = () =>
  act(async () => {
    await new Promise((r) => setTimeout(r, 10));
  });
test('discovery is read-only; lost response reuses create and acceptance IDs across remount', async () => {
  localStorage.clear();
  const calls = [];
  let lost = true,
    reloads = 0;
  const api = {
    listOperationalGridGeometryProposals: async () => ({
      data: {
        proposals: [],
        candidates: [
          {
            targetResultId: uuid,
            applicable: true,
            reasons: [],
            originalGeometry: proposal.candidate.originalGeometry,
            modelSnapshot: proposal.candidate.modelSnapshot,
          },
        ],
      },
    }),
    createOperationalGridGeometryProposal: async (...args) => {
      calls.push(['create', ...args]);
      return { data: { receipt: {}, current: proposal } };
    },
    acceptOperationalGridGeometryProposal: async (...args) => {
      calls.push(['accept', ...args]);
      if (lost) {
        lost = false;
        throw new Error('lost response');
      }
      return {
        data: {
          receipt: { state: 'accepted' },
          current: {
            ...proposal,
            state: 'accepted',
            applicable: false,
            reasons: ['PROPOSAL_ACCEPTED'],
          },
        },
      };
    },
  };
  const props = {
    api,
    apiBaseUrl: 'http://127.0.0.1:8000',
    importJobId: uuid,
    item,
    onChanged: () => reloads++,
  };
  let root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(GridGeometryProposals, props)),
  );
  await settle();
  assert.equal(calls.length, 0);
  assert.ok(
    document.querySelector(
      'svg[aria-label="Porównanie obecnej siatki i propozycji"]',
    ),
  );
  const button = () =>
    [...document.querySelectorAll('button')].find(
      (b) => b.textContent === 'Przyjmij propozycję',
    );
  await act(async () => button().click());
  assert.equal(reloads, 0);
  await act(async () => root.unmount());
  root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(React.createElement(GridGeometryProposals, props)),
  );
  await settle();
  await act(async () => button().click());
  assert.deepEqual(calls[0], calls[2]);
  assert.deepEqual(calls[1], calls[3]);
  assert.equal(reloads, 1);
  assert.ok(
    document.body.textContent.includes(
      'Historia decyzji nie potwierdza bieżącej geometrii',
    ),
  );
  await act(async () => root.unmount());
});

test('workspace mounts proposal discovery only in the grid issue view', async () => {
  let discoveries = 0;
  const discoveryViews = [];
  const board = {
    ...item,
    status: 'pending',
    sourceOrderIndex: 0,
    cells: Array.from({ length: 15 }, (_, i) => ({
      cellIndex: i,
      rowIndex: Math.floor(i / 5),
      columnIndex: i % 5,
      currentSymbolCode: 'A',
      predictedSymbolCode: 'A',
      confidence: 1,
      cropSampleId: `11111111-1111-4111-8111-${String(i).padStart(12, '0')}`,
      cropChecksumSha256: 'a'.repeat(64),
      alternatives: [],
    })),
  };
  const api = {
    listGames: async () => ({
      data: [{ id: uuid, code: 'test', name: 'Test', status: 'active' }],
    }),
    listJobs: async () => ({
      data: [
        {
          id: uuid,
          jobType: 'import',
          status: 'waiting_for_review',
          progress: { current: 1, total: 1 },
          inputPayload: { importKind: 'image_directory' },
          createdAt: '2026-10-15T00:00:00Z',
        },
      ],
    }),
    listSymbols: async () => ({
      data: [{ id: uuid, code: 'A', name: 'A', status: 'active' }],
    }),
    listOperationalImageReviewItems: async (query) => ({
      data: {
        gameId: uuid,
        importJobId: uuid,
        gridIssueView: query.gridIssueView,
        view: 'all',
        counts: {
          pending: 1,
          total: 1,
          accepted: 0,
          completed: 0,
          corrected: 0,
          rejected: 0,
          superseded: 0,
        },
        items: [board],
        nextCursor: null,
        previousCursor: null,
        queueVersion: 1,
        needsGridFixCount: 1,
      },
    }),
    listOperationalGridGeometryProposals: async () => {
      discoveries++;
      discoveryViews.push(
        document.querySelector(
          '[aria-label="Widok kolejki"] button[aria-pressed="true"]',
        ).textContent,
      );
      return { data: { proposals: [proposal], candidates: [] } };
    },
  };
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(OperationalReviewWorkspace, {
        client: api,
        apiBaseUrl: 'http://127.0.0.1:8000',
        gameId: uuid,
        importJobId: uuid,
      }),
    ),
  );
  await settle();
  assert.ok(
    document.body.textContent.includes('Układ #100'),
    document.body.textContent,
  );
  assert.equal(discoveries, 0);
  const gridView = [...document.querySelectorAll('button')].find((button) =>
    button.textContent.includes('Do poprawy siatki'),
  );
  assert.ok(gridView);
  await act(async () => gridView.click());
  await settle();
  assert.ok(discoveries >= 1);
  assert.ok(discoveryViews.every((view) => view.includes('Do poprawy siatki')));
  const countInIssueView = discoveries;
  const allView = [...document.querySelectorAll('button')].find(
    (button) => button.textContent === 'Wszystkie',
  );
  await act(async () => allView.click());
  await settle();
  assert.equal(discoveries, countInIssueView);
  await act(async () => root.unmount());
});
test('command persistence distinguishes changed bodies and proxy only exposes proposal routes', () => {
  localStorage.clear();
  const a = proposalCommandKey(localStorage, 'scope', { revision: 1 });
  assert.equal(proposalCommandKey(localStorage, 'scope', { revision: 1 }), a);
  assert.notEqual(
    proposalCommandKey(localStorage, 'scope', { revision: 2 }),
    a,
  );
  const base = `/api/v1/admin/image-review-items/${uuid}/grid-geometry-proposals`;
  assert.equal(reviewerProxyTarget('GET', base), base);
  assert.equal(
    reviewerProxyTarget('POST', `${base}/${uuid}/accept`),
    `${base}/${uuid}/accept`,
  );
  assert.equal(reviewerProxyTarget('DELETE', base), null);
});
for (const partial of [false, true]) {
  test(`edit opens the shared four-corner and exact-node editor; partial=${partial}; save retains candidate provenance`, async () => {
    localStorage.clear();
    const calls = [];
    let reloads = 0;
    const editing = [];
    const api = {
      listOperationalGridGeometryProposals: async () => ({
        data: { proposals: [proposal], candidates: [] },
      }),
      previewOperationalImageReviewGeometry: async () => ({
        data: new Blob(['preview'], { type: 'image/png' }),
      }),
      acceptOperationalGridGeometryProposal: async (...args) => {
        calls.push(args);
        return {
          data: {
            receipt: {},
            current: { ...proposal, state: 'accepted', applicable: false },
          },
        };
      },
    };
    const root = createRoot(document.getElementById('root'));
    await act(async () =>
      root.render(
        React.createElement(GridGeometryProposals, {
          api,
          apiBaseUrl: 'http://127.0.0.1:8000',
          importJobId: uuid,
          item,
          onChanged: () => reloads++,
          onEditingChange: (value) => editing.push(value),
        }),
      ),
    );
    await settle();
    const button = (text) =>
      [...document.querySelectorAll('button')].find(
        (b) => b.textContent === text,
      );
    await act(async () => button('Edytuj propozycję').click());
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });
    assert.ok(document.body.textContent.includes('Dokładna korekta'));
    assert.equal(editing.at(-1), true);
    assert.ok(button('Całe zdjęcie'));
    if (partial) {
      const partialControl = [...document.querySelectorAll('label')]
        .find((label) => label.textContent.trim() === 'Niepełna plansza')
        .querySelector('input');
      await act(async () => partialControl.click());
      await act(async () =>
        document
          .querySelector('input[aria-label="Pole 1 poza zdjęciem"]')
          .click(),
      );
      await act(async () => {
        await new Promise((r) => setTimeout(r, 200));
      });
    }
    await act(async () => button('Przyjmij własną korektę').click());
    assert.equal(calls.length, 1);
    assert.equal(calls[0][3].mode, 'edited');
    assert.equal(editing.at(-1), false);
    assert.equal(
      calls[0][3].originalCandidateSha256,
      proposal.candidate.originalCandidateSha256,
    );
    assert.deepEqual(calls[0][3].geometry.latticeNodes, nodes);
    if (partial) {
      assert.equal(
        calls[0][3].geometry.geometryQualification.completenessStatus,
        'pending_partial',
      );
      assert.equal(
        calls[0][3].geometry.geometryQualification.excludeFromGeometryTraining,
        true,
      );
      assert.deepEqual(
        calls[0][3].geometry.geometryQualification.unavailableCellIndices,
        [0],
      );
    } else {
      assert.deepEqual(
        calls[0][3].geometry.geometryQualification,
        completeQualification,
      );
    }
    const repository = fileURLToPath(new URL('../../../', import.meta.url));
    const python =
      [
        process.env.GAME_PREDICTOR_TEST_PYTHON,
        resolve(repository, '.venv/Scripts/python.exe'),
        resolve(repository, '../../.venv/Scripts/python.exe'),
        resolve(repository, '.venv/bin/python'),
      ].find((path) => path && existsSync(path)) ?? 'python';
    const validation = spawnSync(
      python,
      [
        '-c',
        `
import json, sys
from pydantic import ValidationError
from game_predictor_api.schemas.grid_geometry_proposals import ProposalAcceptCommand
body = json.load(sys.stdin)
ProposalAcceptCommand.model_validate(body)
body['geometry']['geometryQualification'] = None
try:
    ProposalAcceptCommand.model_validate(body)
except ValidationError:
    pass
else:
    raise AssertionError('null qualification must remain rejected')
`,
      ],
      {
        input: JSON.stringify(calls[0][3]),
        encoding: 'utf-8',
        timeout: 15000,
        env: {
          ...process.env,
          PYTHONPATH: resolve(repository, 'services/api/src'),
        },
      },
    );
    assert.equal(
      validation.status,
      0,
      validation.stderr || validation.error?.message,
    );
    assert.deepEqual(proposal.candidate.originalGeometry.latticeNodes, nodes);
    assert.equal(reloads, 1);
    await act(async () => root.unmount());
  });
}

test('correction integration reads current identity, retries errors and ignores late reads for the previous board', async () => {
  const { CorrectionGridProposals } =
    await import('../src/features/operational-reviews/correction-grid-proposals.tsx');
  const calls = [];
  let resolveOld;
  let failed = true;
  let changed = 0;
  const current = {
    ...item,
    id: 'next',
    importJobId: uuid,
    geometryRevision: 2,
  };
  const api = {
    getOperationalImageReviewItem: async (id) => {
      calls.push(['get', id]);
      if (id === uuid)
        return new Promise((resolve) => {
          resolveOld = resolve;
        });
      if (failed) {
        failed = false;
        throw new Error('offline');
      }
      return { data: current };
    },
    listOperationalGridGeometryProposals: async (id) => {
      calls.push(['list', id]);
      return {
        data: {
          candidates: [],
          proposals: [
            {
              ...proposal,
              candidate: { ...proposal.candidate, expectedGeometryRevision: 2 },
            },
          ],
        },
      };
    },
    createOperationalGridGeometryProposal: async () => {
      calls.push(['create']);
      throw new Error('not needed');
    },
    createOperationalImageReviewGeometryRevision: async () =>
      assert.fail('no manual write on mount'),
    previewOperationalImageReviewGeometry: async () =>
      assert.fail('no preview on mount'),
    acceptOperationalGridGeometryProposal: async (
      id,
      proposalId,
      context,
      body,
    ) => {
      calls.push(['accept', id, body]);
      return {
        data: {
          current: {
            ...proposal,
            state: 'accepted',
            applicable: false,
            reasons: [],
          },
        },
      };
    },
    rejectOperationalGridGeometryProposal: async () =>
      assert.fail('no reject on mount'),
  };
  const root = createRoot(document.getElementById('root'));
  const show = (review) =>
    act(async () =>
      root.render(
        React.createElement(CorrectionGridProposals, {
          api,
          apiBaseUrl: 'http://localhost',
          item: { ...review, reviewItemId: review.id },
          onChanged: () => changed++,
        }),
      ),
    );
  try {
    await show({ ...item, importJobId: uuid });
    await show(current);
    assert.match(document.body.textContent, /Nie udało się pobrać/);
    await act(async () => resolveOld({ data: { ...item, importJobId: uuid } }));
    assert.equal(
      calls.filter(([name]) => name === 'list').length,
      0,
      'old read cannot mount old proposals',
    );
    await act(async () =>
      [...document.querySelectorAll('button')]
        .find((b) => b.textContent === 'Odśwież propozycje')
        .click(),
    );
    await settle();
    assert.deepEqual(
      calls.filter(([name]) => name === 'list'),
      [['list', 'next']],
    );
    assert.equal(
      calls.some(([name]) => name === 'accept' || name === 'create'),
      false,
    );
    await act(async () =>
      [...document.querySelectorAll('button')]
        .find((b) => b.textContent === 'Przyjmij propozycję')
        .click(),
    );
    assert.equal(changed, 1);
    assert.equal(calls.at(-1)[1], 'next');
    assert.equal(calls.at(-1)[2].expectedGeometryRevision, 2);
  } finally {
    await act(async () => root.unmount());
  }
});

test('correction integration rejects mismatched source/revisions and tolerates legacy clients', async () => {
  const { CorrectionGridProposals } =
    await import('../src/features/operational-reviews/correction-grid-proposals.tsx');
  const root = createRoot(document.getElementById('root'));
  const board = { ...item, importJobId: uuid, reviewItemId: uuid };
  const unused = async () =>
    assert.fail('stale data must not discover or mutate proposals');
  const api = {
    getOperationalImageReviewItem: async () => ({
      data: { ...item, importJobId: uuid, geometryRevision: 99 },
    }),
    listOperationalGridGeometryProposals: unused,
    createOperationalGridGeometryProposal: unused,
    acceptOperationalGridGeometryProposal: unused,
    rejectOperationalGridGeometryProposal: unused,
    createOperationalImageReviewGeometryRevision: unused,
    previewOperationalImageReviewGeometry: unused,
  };
  try {
    await act(async () =>
      root.render(
        React.createElement(CorrectionGridProposals, {
          api,
          item: board,
          apiBaseUrl: '',
          onChanged() {},
        }),
      ),
    );
    assert.match(document.body.textContent, /aktualnej wersji planszy/);
    await act(async () =>
      root.render(
        React.createElement(CorrectionGridProposals, {
          api: {},
          item: board,
          apiBaseUrl: '',
          onChanged() {},
        }),
      ),
    );
    assert.equal(document.body.textContent, '');
  } finally {
    await act(async () => root.unmount());
  }
});

test('rejecting a model proposal keeps the grid issue open and only requests a queue refresh when opted in', async () => {
  localStorage.clear();
  const calls = [];
  let acceptedChanges = 0;
  let refreshes = 0;
  const api = {
    listOperationalGridGeometryProposals: async () => ({
      data: { proposals: [proposal], candidates: [] },
    }),
    rejectOperationalGridGeometryProposal: async (...args) => {
      calls.push(args);
      return {
        data: {
          current: {
            ...proposal,
            state: 'rejected',
            applicable: false,
            reasons: ['PROPOSAL_REJECTED'],
          },
        },
      };
    },
    acceptOperationalGridGeometryProposal: async () =>
      assert.fail('reject cannot approve geometry'),
  };
  const root = createRoot(document.getElementById('root'));
  try {
    await act(async () =>
      root.render(
        React.createElement(GridGeometryProposals, {
          api,
          apiBaseUrl: '',
          importJobId: uuid,
          item,
          onChanged: () => acceptedChanges++,
          onRejected: () => refreshes++,
        }),
      ),
    );
    await act(async () =>
      [...document.querySelectorAll('button')]
        .find((b) => b.textContent === 'Odrzuć propozycję')
        .click(),
    );
    assert.equal(calls.length, 1);
    assert.equal(acceptedChanges, 0);
    assert.equal(refreshes, 1);
    assert.match(
      document.body.textContent,
      /Zgłoszenie siatki pozostaje otwarte/,
    );
    assert.equal('geometry' in calls[0][3], false);
  } finally {
    await act(async () => root.unmount());
  }
});

test('an API read error is distinct from stale identity and can retry without refreshing the queue', async () => {
  const { CorrectionGridProposals } =
    await import('../src/features/operational-reviews/correction-grid-proposals.tsx');
  const root = createRoot(document.getElementById('root'));
  const unused = async () =>
    assert.fail('failed read cannot mutate or discover');
  const api = {
    getOperationalImageReviewItem: async () => ({ error: {} }),
    listOperationalGridGeometryProposals: unused,
    createOperationalGridGeometryProposal: unused,
    acceptOperationalGridGeometryProposal: unused,
    rejectOperationalGridGeometryProposal: unused,
    createOperationalImageReviewGeometryRevision: unused,
    previewOperationalImageReviewGeometry: unused,
  };
  try {
    await act(async () =>
      root.render(
        React.createElement(CorrectionGridProposals, {
          api,
          item: { ...item, importJobId: uuid, reviewItemId: uuid },
          apiBaseUrl: '',
          onChanged: unused,
          onReloadQueue: unused,
        }),
      ),
    );
    assert.match(document.body.textContent, /Nie udało się pobrać propozycji/);
    assert.doesNotMatch(document.body.textContent, /aktualnej wersji planszy/);
    assert.equal(
      [...document.querySelectorAll('button')].some(
        (b) => b.textContent === 'Odśwież kolejkę',
      ),
      false,
    );
    assert.ok(
      [...document.querySelectorAll('button')].some(
        (b) => b.textContent === 'Odśwież propozycje',
      ),
    );
  } finally {
    await act(async () => root.unmount());
  }
});
