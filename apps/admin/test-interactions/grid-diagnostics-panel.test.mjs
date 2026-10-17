import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { JSDOM } from 'jsdom';
import { renderToStaticMarkup } from 'react-dom/server';

import {
  GridDiagnosticsControl,
  GridDiagnosticsPanel,
} from '../src/features/imports/grid-diagnostics-panel.tsx';

test('diagnostic panel separates units, explains overlapping slots and uses readable labels', () => {
  const report = {
    computedAt: '2026-10-14T18:00:00Z',
    counts: { added: 8 },
    diagnostics: {
      scope: 'whole_game',
      deferredSlotsByStatus: { pending: 3 },
      deferredSlotsByReason: { incomplete_lattice: 3 },
      deferredSlotCoverage: {
        already_added: 1,
        missing_slots: 2,
        missing_unique_sequences: 2,
      },
      flaggedGridBoards: 1,
      unconfirmedGeometryBoards: 8,
      flaggedUnconfirmedBoards: 1,
      symbolCells: {
        unknown: 4,
        pending: 10,
        unreadable: 1,
        low_confidence: 3,
      },
      lowConfidenceThreshold: 0.6,
      qualifyingReviewSequences: 8,
      canonicalSequences: 2,
      canonicalReviewOverlap: 2,
      duplicateQualifyingReviewRows: 1,
      reviewRowsByStatus: { pending: 9 },
      sourceImages: { total: 2, incomplete_uncertain: 2 },
      sourcePositions: { uncertain: 8, deferred: 2 },
      sourceGate: { geometry_incomplete: 2 },
      symbolCellIntersections: { unknown_pending: 4 },
      missingReasonSignals: { waiting_for_geometry: 2 },
      missingReasonIntersections: {},
    },
  };
  const html = renderToStaticMarkup(
    React.createElement(GridDiagnosticsPanel, { report }),
  );
  assert.match(html, /Nie sumuj zdjęć, slotów, plansz i komórek/);
  assert.match(html, /Nieznane symbole \(komórki\)/);
  assert.match(html, /60%/);
  assert.match(html, /już dodaną sekwencją: 1/);
  assert.match(html, /Stan zapisany bramki zdjęć/);
  assert.match(html, /Bieżąc|bieżącej klasyfikacji/);
  assert.doesNotMatch(
    html,
    /unknown_pending|incomplete_uncertain|incomplete_lattice|>pending/,
  );
  assert.doesNotMatch(html, /2026-10-14T18:00:00Z/);
  assert.equal(
    renderToStaticMarkup(
      React.createElement(GridDiagnosticsPanel, {
        report: { diagnostics: null },
      }),
    ),
    '',
  );
});

test('diagnostic reads are explicit and a late response cannot cross the game scope', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
  for (const key of [
    'window',
    'document',
    'HTMLElement',
    'Element',
    'Event',
    'MouseEvent',
  ]) {
    Object.defineProperty(globalThis, key, {
      configurable: true,
      value: dom.window[key],
    });
  }
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  const { createRoot } = await import('react-dom/client');
  const root = createRoot(document.querySelector('#root'));
  const requests = [];
  let resolveOld;
  const empty = (gameId) => ({
    gameId,
    computedAt: '2026-10-14T18:00:00Z',
    counts: { added: 0 },
    diagnostics: {
      scope: 'whole_game',
      deferredSlotsByStatus: {},
      deferredSlotsByReason: {},
      deferredSlotCoverage: {},
      sourceImages: {},
      sourcePositions: {},
      sourceGate: {},
      symbolCells: {},
      symbolCellIntersections: {},
      missingReasonSignals: {},
      missingReasonIntersections: {},
      reviewRowsByStatus: {},
      qualifyingReviewSequences: 0,
      canonicalSequences: 0,
      canonicalReviewOverlap: 0,
      duplicateQualifyingReviewRows: 0,
      flaggedGridBoards: 0,
      unconfirmedGeometryBoards: 0,
      flaggedUnconfirmedBoards: 0,
      lowConfidenceThreshold: 0.6,
    },
  });
  const api = {
    getBoardImportCoverage: (options) => {
      requests.push(options);
      return options.gameId === 'a'
        ? new Promise((resolve) => {
            resolveOld = resolve;
          })
        : Promise.resolve({ data: empty('b') });
    },
  };
  try {
    await act(async () =>
      root.render(
        React.createElement(GridDiagnosticsControl, {
          key: 'a',
          api,
          gameId: 'a',
        }),
      ),
    );
    assert.equal(requests.length, 0);
    await act(async () => document.querySelector('button').click());
    assert.equal(requests.length, 1);
    assert.equal(requests[0].includeDiagnostics, true);
    await act(async () =>
      root.render(
        React.createElement(GridDiagnosticsControl, {
          key: 'b',
          api,
          gameId: 'b',
        }),
      ),
    );
    await act(async () => resolveOld({ data: empty('a') }));
    assert.equal(document.querySelector('h4'), null);
    assert.equal(requests.length, 1);
    await act(async () => document.querySelector('button').click());
    assert.equal(requests[1].gameId, 'b');
    assert.match(document.body.textContent, /Uzgodnienie liczników całej gry/);
    await act(async () =>
      root.render(
        React.createElement(GridDiagnosticsControl, {
          key: 'b',
          api,
          gameId: 'b',
        }),
      ),
    );
    assert.equal(requests.length, 2);
  } finally {
    await act(async () => root.unmount());
    dom.window.close();
  }
});
