import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createAdminApiClient } from '../../../packages/admin-api-client/src/index.ts';
import { SequenceSourceCandidates } from '../src/features/imports/sequence-source-candidates.tsx';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
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
after(() => dom.window.close());
const { operationalImageReviewSourceAssetUrl: sourceAssetUrl } =
  createAdminApiClient({ baseUrl: 'http://127.0.0.1:8000' });
const candidate = (id, extra = {}) => ({
  reviewItemId: id,
  importJobId: 'job',
  automaticRank: 1,
  qualityScore: 1,
  width: 1920,
  height: 1080,
  sequenceConfidence: 1,
  boardConfidence: 1,
  sourceRelativePath: `${id}.jpg`,
  selected: false,
  ...extra,
});

test('legacy ordinary sources still support selection and clearing the override', async () => {
  const root = createRoot(document.getElementById('root'));
  const chosen = [];
  try {
    await act(() =>
      root.render(
        React.createElement(SequenceSourceCandidates, {
          selection: {
            candidates: [
              candidate('current', { selected: true }),
              candidate('alternate'),
            ],
            manualOverrideReviewItemId: 'current',
          },
          sourceAssetUrl,
          busy: false,
          apiBaseUrl: 'http://127.0.0.1:8000',
          onChoose: (id) => chosen.push(id),
        }),
      ),
    );
    const buttons = [...document.querySelectorAll('button')];
    assert.equal(buttons.length, 2);
    await act(() => buttons[0].click());
    await act(() => buttons[1].click());
    assert.deepEqual(chosen, [null, 'alternate']);
  } finally {
    await act(() => root.unmount());
  }
});

test('reservation, bound replacement and restored history cannot select old sources', async () => {
  const root = createRoot(document.getElementById('root'));
  try {
    for (const state of [
      'reserved_gap',
      'pending_bound',
      'history_only',
      'available',
    ]) {
      await act(() =>
        root.render(
          React.createElement(SequenceSourceCandidates, {
            selection: {
              state,
              gameId: 'game',
              manualOverrideReviewItemId: null,
              replacementEntryId: 'entry',
              replacementManifestUrl:
                '/api/v1/admin/games/game/board-sources/batch',
              candidates: [
                candidate('old', {
                  sourceState: 'replaced',
                  selectable: false,
                }),
                candidate('new', {
                  selected: state !== 'reserved_gap',
                  selectable: state === 'available',
                }),
              ],
            },
            sourceAssetUrl,
            busy: false,
            apiBaseUrl: 'http://127.0.0.1:8000',
            onChoose: () => assert.fail('History must not be selectable'),
          }),
        ),
      );
      assert.match(
        document.body.textContent,
        /Zastąpione zdjęcie · tylko historia/u,
      );
      assert.equal(document.querySelectorAll('button').length, 0);
      const preview = [...document.querySelectorAll('a')].find(
        (link) => link.textContent === 'Podgląd zdjęcia',
      );
      assert.equal(
        preview.href,
        'http://127.0.0.1:8000/api/v1/admin/image-review-items/old/assets/source?gameId=game&importJobId=job',
      );
      if (state === 'reserved_gap' || state === 'pending_bound') {
        assert.equal(
          document.querySelector('a').href,
          'http://127.0.0.1:8000/api/v1/admin/games/game/board-sources/batch',
        );
      }
    }
  } finally {
    await act(() => root.unmount());
  }
});

test('empty reserved gap has an explanatory state and a manifest link', async () => {
  const root = createRoot(document.getElementById('root'));
  try {
    await act(() =>
      root.render(
        React.createElement(SequenceSourceCandidates, {
          selection: {
            state: 'reserved_gap',
            candidates: [],
            replacementManifestUrl: '/manifest',
          },
          sourceAssetUrl,
          busy: false,
          apiBaseUrl: 'http://127.0.0.1:8000',
          onChoose: () => assert.fail(),
        }),
      ),
    );
    assert.match(document.body.textContent, /Luka zarezerwowana/u);
    assert.equal(document.querySelectorAll('button').length, 0);
  } finally {
    await act(() => root.unmount());
  }
});
