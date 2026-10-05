import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  gridShadowMeshLines,
  gridShadowRequestId,
  gridShadowReviewerUrl,
  gridShadowSourceChoices,
} from '../src/features/grid-shadow/grid-shadow-state.ts';

test('five active sources are deduplicated without deriving extra slots from detections', () => {
  const sources = [
    { sourceImageId: 'a', sequenceNumber: 1 },
    { sourceImageId: 'a', sequenceNumber: 2 },
    { sourceImageId: 'b', sequenceNumber: 10 },
  ];
  assert.deepEqual(gridShadowSourceChoices(sources), [sources[0], sources[2]]);
});

test('comparison renders a displaced interior node, not only corner interpolation', () => {
  const nodes = Array.from({ length: 24 }, (_, index) => ({
    x: index % 6,
    y: Math.floor(index / 6),
  }));
  nodes[7] = { x: 1.2, y: 1.1 };
  const lines = gridShadowMeshLines(nodes);
  assert.equal(lines.length, 10);
  assert.match(lines[1], /1.2,1.1/);
  assert.match(lines[5], /1.2,1.1/);
  assert.deepEqual(gridShadowMeshLines(nodes.slice(0, 23)), []);
});

test('lost response and page restart reuse request identity for canonical sources', () => {
  const map = new Map();
  const storage = {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, value),
  };
  assert.equal(
    gridShadowRequestId(storage, 'g', ['b', 'a'], () => 'id-a'),
    'id-a',
  );
  assert.equal(
    gridShadowRequestId(storage, 'g', ['a', 'b'], () => 'id-b'),
    'id-a',
  );
  assert.equal(
    gridShadowRequestId(storage, 'g', ['c'], () => 'id-c'),
    'id-c',
  );
  assert.equal(
    gridShadowRequestId(storage, 'other', ['c'], () => 'id-d'),
    'id-d',
  );
});

test('shadow correction links are local, game/result/position scoped', () => {
  const url = new URL(
    gridShadowReviewerUrl('http://127.0.0.1:3000/?tab=review', 'g', 'r', 4),
  );
  assert.equal(url.port, '3001');
  assert.deepEqual(Object.fromEntries(url.searchParams), {
    mode: 'local',
    queue: 'grid-shadow',
    gameId: 'g',
    resultId: 'r',
    positionIndex: '4',
  });
  assert.equal(
    gridShadowReviewerUrl('https://example.test', 'g', 'r', 4),
    null,
  );
});
