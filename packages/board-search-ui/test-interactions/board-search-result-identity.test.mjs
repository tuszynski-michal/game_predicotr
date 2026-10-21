import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { JSDOM } from 'jsdom';
import React, { act, useState } from 'react';

const dom = new JSDOM('<!doctype html><div id="root"></div>', {
  url: 'http://localhost',
});
for (const key of [
  'window',
  'document',
  'HTMLElement',
  'Element',
  'Event',
  'MouseEvent',
  'KeyboardEvent',
  'Image',
]) {
  Object.defineProperty(globalThis, key, {
    configurable: true,
    value: dom.window[key],
  });
}
dom.window.HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute('open', '');
};
dom.window.HTMLDialogElement.prototype.close = function () {
  this.removeAttribute('open');
};
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { createRoot } = await import('react-dom/client');
const { BoardSearchResults } = await import('../src/board-search-results.tsx');
after(() => dom.window.close());

function result(
  sequenceNumber,
  checksum = String(sequenceNumber).padStart(64, '0'),
) {
  return {
    assetMode: 'operational_review',
    boardChecksumSha256: checksum,
    importJobId: 'job',
    reviewItemId: `review-${sequenceNumber}`,
    recognizedBoardId: `board-${sequenceNumber}`,
    sequenceNumber,
    status: 'pending',
    score: {
      score: 100,
      exactMatchCount: 1,
      alternativeMatchCount: 0,
      mismatchCount: 0,
      unknownCount: 0,
    },
  };
}
const client = {
  boardSearchBoardViewUrl: (game, sequence, checksum) =>
    `http://localhost/${game}/${sequence}/${checksum}.webp`,
  getBoardSearchBoardDetail: async () => ({
    error: { message: 'Detail unavailable' },
  }),
  symbolImageAssetUrl: () => '',
};
async function click(node) {
  assert.ok(node);
  await act(async () =>
    node.dispatchEvent(new dom.window.MouseEvent('click', { bubbles: true })),
  );
}
function button(text) {
  return [...document.querySelectorAll('button')].find(
    (node) => node.textContent.trim() === text,
  );
}
function assertSinglePreview(sequence) {
  const images = document.querySelectorAll('.boardSearchBoardAsset');
  assert.equal(images.length, 1, 'exactly one result photo remains in the DOM');
  assert.match(images[0].src, new RegExp(`/${sequence}/`));
}

for (const compact of [false, true]) {
  test(`opening the board window and navigating never duplicates the photo (compact=${compact})`, async (context) => {
    const errors = [];
    context.mock.method(console, 'error', (...args) =>
      errors.push(args.join(' ')),
    );
    function Harness() {
      const [state, setState] = useState({
        activeIndex: 0,
        results: [result(10), result(19), result(27)],
      });
      return React.createElement(BoardSearchResults, {
        client,
        gameId: 'game',
        state,
        onStateChange: setState,
        onBoardEdited() {},
        symbols: [],
        compact,
      });
    }
    const root = createRoot(document.getElementById('root'));
    try {
      await act(async () => root.render(React.createElement(Harness)));
      for (const [sequence, key] of [
        [19, 'ArrowRight'],
        [27, 'ArrowRight'],
        [19, 'ArrowLeft'],
        [10, 'ArrowLeft'],
      ]) {
        await click(document.querySelector('[aria-label^="Pokaż planszę #"]'));
        assert.equal(document.querySelectorAll('dialog[open]').length, 1);
        // Arrow navigation also works while the board window is open.
        const section = document.querySelector(
          '[aria-label="Wyniki wyszukiwania plansz"]',
        );
        await act(async () =>
          section.dispatchEvent(
            new dom.window.KeyboardEvent('keydown', { bubbles: true, key }),
          ),
        );
        assertSinglePreview(sequence);
        assert.equal(document.querySelectorAll('dialog[open]').length, 1);
        await click(button('Zamknij'));
        assert.equal(document.querySelectorAll('dialog').length, 0);
        assertSinglePreview(sequence);
      }
      assert.deepEqual(
        errors,
        [],
        'React should report no duplicate-key or reconciliation warnings',
      );
    } finally {
      await act(async () => root.unmount());
      // Clear any orphaned DOM even when running against the broken implementation.
      document.getElementById('root').replaceChildren();
    }
    assert.equal(document.getElementById('root').children.length, 0);
  });
}

for (const change of ['game', 'checksum']) {
  test(`changing the ${change} resets the previous photo fallback and board window`, async () => {
    const calls = [];
    const api = {
      ...client,
      operationalImageReviewBoardAssetUrl: () =>
        'http://localhost/fallback.jpg',
      getOperationalImageReviewItem: async () => ({ data: { geometry: {} } }),
      getBoardSearchBoardDetail: async (...args) => {
        calls.push(args);
        return { error: { message: 'Detail unavailable' } };
      },
    };
    const root = createRoot(document.getElementById('root'));
    function render(gameId, checksum) {
      return root.render(
        React.createElement(BoardSearchResults, {
          client: api,
          gameId,
          state: { activeIndex: 0, results: [result(10, checksum)] },
          onStateChange() {},
          onBoardEdited() {},
          symbols: [],
        }),
      );
    }
    try {
      await act(async () => render('mumie-a1', 'a'.repeat(64)));
      await act(async () =>
        document
          .querySelector('.boardSearchBoardAsset')
          .dispatchEvent(new dom.window.Event('error')),
      );
      assert.match(
        document.querySelector('.boardSearchBoardAsset').src,
        /fallback\.jpg$/,
      );
      await click(button('Pokaż planszę'));
      assert.equal(calls.length, 1);
      const nextGame = change === 'game' ? '777-a2' : 'mumie-a1';
      const nextChecksum = (change === 'checksum' ? 'b' : 'a').repeat(64);
      await act(async () => render(nextGame, nextChecksum));
      assertSinglePreview(10);
      assert.equal(
        document.querySelector('.boardSearchBoardAsset').src,
        `http://localhost/${nextGame}/10/${nextChecksum}.webp`,
      );
      assert.equal(
        calls.length,
        2,
        'board window reloads for the new image identity',
      );
      assert.equal(calls[1][0], nextGame);
      assert.equal(document.querySelectorAll('dialog[open]').length, 1);
    } finally {
      await act(async () => root.unmount());
      document.getElementById('root').replaceChildren();
    }
  });
}
