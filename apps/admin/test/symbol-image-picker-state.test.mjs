import assert from 'node:assert/strict';
import test from 'node:test';

import {
  appendSymbolReferenceCandidatePage,
  canGoToNextSymbolReferencePage,
  canGoToPreviousSymbolReferencePage,
  currentSymbolReferenceCandidatePage,
} from '../src/features/symbols/symbol-image-picker-state.ts';

const first = { items: [{ observationId: 'first' }], nextCursor: 'cursor-1' };
const last = { items: [{ observationId: 'last' }], nextCursor: null };

test('retains already loaded pages and moves one page at a time', () => {
  const pages = appendSymbolReferenceCandidatePage([first], last);

  assert.deepEqual(pages, [first, last]);
  assert.equal(currentSymbolReferenceCandidatePage(pages, 0), first);
  assert.equal(currentSymbolReferenceCandidatePage(pages, 1), last);
  assert.equal(canGoToPreviousSymbolReferencePage(0), false);
  assert.equal(canGoToPreviousSymbolReferencePage(1), true);
  assert.equal(canGoToNextSymbolReferencePage(pages, 0), true);
  assert.equal(canGoToNextSymbolReferencePage(pages, 1), false);
});

test('allows fetching an unloaded next page only when the keyset cursor exists', () => {
  assert.equal(canGoToNextSymbolReferencePage([first], 0), true);
  assert.equal(canGoToNextSymbolReferencePage([last], 0), false);
  assert.equal(currentSymbolReferenceCandidatePage([first], 2), null);
});
