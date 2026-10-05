import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  gridShadowBoardGeometryTarget,
  gridShadowCornerProposal,
} from '../src/features/operational-reviews/grid-shadow-correction-target.ts';

const nodes = Array.from({ length: 24 }, (_, index) => ({
  x: 10 + (index % 6) * 20,
  y: 10 + Math.floor(index / 6) * 20,
}));
const item = {
  gameId: 'g',
  importJobId: 'j',
  slotKind: 'current_review',
  slotId: 's',
  reviewItemId: 'review',
  pendingGeometryId: null,
  sourceChecksumSha256: 'a'.repeat(64),
  sourceWidth: 200,
  sourceHeight: 200,
  positionIndex: 2,
  sequenceNumber: 3,
  geometryRevision: 1,
  resolutionRevision: 0,
  geometry: { quad: [nodes[0], nodes[5], nodes[23], nodes[18]] },
  gridRows: 3,
  gridColumns: 5,
};
const slot = {
  positionIndex: 2,
  sequenceNumber: 3,
  state: 'needs_review',
  reviewItem: item,
  neuralNodes24: nodes,
  reasonCodes: [],
  cellVisibility: Array(15).fill('full'),
};
const result = {
  id: 'r',
  gameId: 'g',
  stale: false,
  sourceWidth: 200,
  sourceHeight: 200,
  modelProfile: 'mumie',
  modelVersion: 'v1',
  reasons: [],
  output: { slots: [slot] },
};

test('four external corners are a stated sketch; full interior nodes are not pretended preserved', async () => {
  const api = {
    getGridShadowResult: async () => ({ data: result }),
    imageGridReviewSourceAssetUrl: () => '/source',
  };
  const target = gridShadowBoardGeometryTarget({
    api,
    apiBaseUrl: '',
    result,
    slot,
  });
  const loaded = await target.load();
  assert.equal(loaded.ok, true);
  assert.match(loaded.view.suggestionNotice, /nie zachowuje pełnych 24 węzłów/);
  assert.deepEqual(gridShadowCornerProposal(nodes), [
    nodes[0],
    nodes[5],
    nodes[23],
    nodes[18],
  ]);
  assert.equal(gridShadowCornerProposal(nodes.slice(0, 23)), null);
});

test('stale proposal cannot call any existing write endpoint', async () => {
  let writes = 0;
  let current = result;
  const api = {
    getGridShadowResult: async () => ({ data: current }),
    createImageGridReviewGeometryRevision: async () => {
      writes++;
      return { data: {} };
    },
    imageGridReviewSourceAssetUrl: () => '/source',
  };
  const target = gridShadowBoardGeometryTarget({
    api,
    apiBaseUrl: '',
    result,
    slot,
  });
  current = { ...result, stale: true };
  const response = await target.save(
    [nodes[0], nodes[5], nodes[23], nodes[18]],
    { partial: false, exclude: false },
    'save',
  );
  assert.equal(response.isConflict, true);
  assert.equal(writes, 0);
  assert.equal(
    gridShadowBoardGeometryTarget({
      api,
      apiBaseUrl: '',
      result: current,
      slot,
    }),
    null,
  );
});

test('review revision drift blocks an old suggestion even if result is incorrectly reported current', async () => {
  const current = {
    ...result,
    output: {
      slots: [{ ...slot, reviewItem: { ...item, geometryRevision: 2 } }],
    },
  };
  const api = {
    getGridShadowResult: async () => ({ data: current }),
    imageGridReviewSourceAssetUrl: () => '/source',
  };
  const target = gridShadowBoardGeometryTarget({
    api,
    apiBaseUrl: '',
    result,
    slot,
  });
  assert.equal((await target.load()).isConflict, true);
});

test('missing neural detection keeps the active slot available to ordinary manual correction', async () => {
  const missing = { ...slot, state: 'missing', neuralNodes24: null };
  const current = { ...result, output: { slots: [missing] } };
  const api = {
    getGridShadowResult: async () => ({ data: current }),
    imageGridReviewSourceAssetUrl: () => '/source',
  };
  const target = gridShadowBoardGeometryTarget({
    api,
    apiBaseUrl: '',
    result: current,
    slot: missing,
  });
  const loaded = await target.load();
  assert.equal(loaded.ok, true);
  assert.match(
    loaded.view.suggestionNotice,
    /Numer planszy pozostaje bez zmian/,
  );
  assert.deepEqual(loaded.view.suggestedCorners, item.geometry.quad);
});

test('an identical submitted correction replays after its response is lost and the result becomes stale', async () => {
  let current = result;
  let calls = 0;
  let applied = 0;
  const api = {
    getGridShadowResult: async () => ({ data: current }),
    imageGridReviewSourceAssetUrl: () => '/source',
    createImageGridReviewGeometryRevision: async () => {
      calls++;
      if (calls === 1) {
        applied++;
        current = { ...result, stale: true };
        throw new Error('response lost after commit');
      }
      return { data: {} };
    },
  };
  const target = gridShadowBoardGeometryTarget({
    api,
    apiBaseUrl: '',
    result,
    slot,
  });
  const corners = [nodes[0], nodes[5], nodes[23], nodes[18]];
  const flags = { partial: false, exclude: false };
  assert.equal((await target.save(corners, flags, 'same-command')).ok, false);
  assert.equal((await target.save(corners, flags, 'same-command')).ok, true);
  assert.equal(calls, 2);
  assert.equal(applied, 1);
  assert.equal(
    (await target.save(corners, flags, 'new-command')).isConflict,
    true,
  );
  assert.equal(
    (await target.save(corners, { ...flags, partial: true }, 'same-command'))
      .isConflict,
    true,
  );
  assert.equal(calls, 2);
});
