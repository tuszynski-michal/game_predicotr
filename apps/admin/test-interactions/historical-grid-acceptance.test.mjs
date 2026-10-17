import assert from 'node:assert/strict';
import test from 'node:test';
import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { JSDOM } from 'jsdom';
import { HistoricalGridAcceptanceControl } from '../src/features/imports/historical-grid-acceptance.tsx';

const gameId = '11111111-1111-4111-8111-111111111111';
const operationId = '22222222-2222-4222-8222-222222222222';
const report = (phase, runCursor = 0) => ({
  gameId,
  operationId,
  phase,
  preparationState: null,
  statusOnly: true,
  materializesNewCells: false,
  startedAt: '2026-10-14T12:00:00Z',
  previewCursor: phase === 'previewing' ? 0 : 1,
  runCursor,
  sourceCount: phase === 'previewing' ? 0 : 1,
  revisionCount: 1,
  eligibleCount: 1,
  acceptedCount: runCursor,
  skippedCount: 0,
  previewReasons: {},
  runReasons: {},
  items: [],
  nextItemCursor: null,
});

async function mount(api) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
  const previous = {};
  for (const [key, value] of Object.entries({
    window: dom.window,
    document: dom.window.document,
    HTMLElement: dom.window.HTMLElement,
    localStorage: dom.window.localStorage,
    IS_REACT_ACT_ENVIRONMENT: true,
  })) {
    previous[key] = globalThis[key];
    globalThis[key] = value;
  }
  const root = createRoot(document.getElementById('root'));
  await act(async () =>
    root.render(
      React.createElement(HistoricalGridAcceptanceControl, { api, gameId }),
    ),
  );
  return {
    dom,
    async cleanup() {
      await act(async () => root.unmount());
      for (const [key, value] of Object.entries(previous))
        globalThis[key] = value;
      dom.window.close();
    },
  };
}

function button(text) {
  return [...document.querySelectorAll('button')].find((item) =>
    item.textContent.includes(text),
  );
}

test('preview never runs acceptance; confirmation drives pages and lost response resumes the same operation', async () => {
  let creates = 0,
    confirms = 0,
    runs = 0;
  let current = report('previewing');
  const api = {
    async createHistoricalGridAcceptance() {
      creates++;
      return { data: current };
    },
    async previewHistoricalGridAcceptanceNext() {
      current = report('previewed');
      return { data: current };
    },
    async confirmHistoricalGridAcceptance(_game, _operation, body) {
      assert.equal(body.confirmed, true);
      confirms++;
      current = report('running');
      return { data: current };
    },
    async runHistoricalGridAcceptanceNext(_game, _operation, body) {
      assert.equal(body.expectedCursor, 0);
      assert.ok(body.idempotencyKey);
      runs++;
      current = report('done', 1);
      throw new Error('Lost response');
    },
    async getHistoricalGridAcceptance(game, operation) {
      assert.equal(game, gameId);
      assert.equal(operation, operationId);
      return { data: current };
    },
  };
  const mounted = await mount(api);
  try {
    await act(async () => button('Przygotuj podgląd').click());
    assert.equal(runs, 0);
    assert.equal(confirms, 0);
    assert.equal(button('Zatwierdź').disabled, true);
    await act(async () =>
      document.querySelector('input[type="checkbox"]').click(),
    );
    await act(async () => button('Zatwierdź').click());
    assert.equal(confirms, 1);
    assert.equal(runs, 1);
    assert.match(document.body.textContent, /Lost response/);
    const saved = JSON.parse(
      localStorage.getItem(`historical-grid-acceptance-v1:${gameId}`),
    );
    assert.equal(saved.operationId, operationId);
    assert.ok(saved.runKey);
    await act(async () => button('Wznów').click());
    assert.equal(creates, 1);
    assert.equal(runs, 1);
    assert.match(document.body.textContent, /Zaakceptowane: 1/);
  } finally {
    await mounted.cleanup();
  }
});

test('SHA time limit stops the automatic loop and keeps the saved preview', async () => {
  let previews = 0;
  const api = {
    async createHistoricalGridAcceptance() {
      return { data: report('previewing') };
    },
    async previewHistoricalGridAcceptanceNext() {
      previews++;
      return {
        data: {
          ...report('previewing'),
          preparationState: 'HISTORICAL_EVIDENCE_VERIFICATION_TIME_LIMIT',
        },
      };
    },
  };
  const mounted = await mount(api);
  try {
    await act(async () => button('Przygotuj podgląd').click());
    assert.equal(previews, 1);
    assert.match(document.body.textContent, /30 sekund/);
    assert.equal(
      JSON.parse(
        localStorage.getItem(`historical-grid-acceptance-v1:${gameId}`),
      ).operationId,
      operationId,
    );
    assert.equal(button('Zatwierdź'), undefined);
  } finally {
    await mounted.cleanup();
  }
});
