import test from 'node:test';
import assert from 'node:assert/strict';
import {
  captureHandlePointer,
  fitViewport,
  fullViewport,
  sourcePoint,
} from '../src/lib/editor-viewport.ts';

test('numbered handle suppresses native text/image drag before pointer capture', () => {
  const calls = [];
  captureHandlePointer({
    pointerId: 7,
    preventDefault: () => calls.push('prevent-native'),
    currentTarget: {
      ownerSVGElement: {
        setPointerCapture: (id) => calls.push(`capture-${id}`),
      },
    },
  });
  assert.deepEqual(calls, ['prevent-native', 'capture-7']);
});
import { LatestPreview } from '../src/lib/latest-preview.ts';

test('zoom maps screen to original pixels and preserves modest margin', () => {
  const size = { width: 1000, height: 800 };
  const nodes = [
    { x: 100, y: 120 },
    { x: 400, y: 300 },
  ];
  const view = fitViewport(nodes, size);
  assert.deepEqual(view, {
    x: 76,
    y: 105.6,
    width: 348,
    height: 208.79999999999998,
  });
  const point = sourcePoint(
    250,
    150,
    { left: 50, top: 50, width: 400, height: 200 },
    view,
    size,
  );
  assert.equal(point.x, 250);
  assert.equal(point.y, 210);
  assert.deepEqual(fullViewport(size), { x: 0, y: 0, ...size });
  assert.deepEqual(fitViewport([], size), fullViewport(size));
});
test('drag snapshot stays fixed until explicit release fit', () => {
  const size = { width: 1000, height: 800 };
  const frozen = fullViewport(size);
  const edited = [
    { x: 100, y: 100 },
    { x: 200, y: 200 },
  ];
  sourcePoint(
    100,
    100,
    { left: 0, top: 0, width: 500, height: 400 },
    frozen,
    size,
  );
  assert.deepEqual(frozen, fullViewport(size));
  assert.notDeepEqual(fitViewport(edited, size), frozen);
});
test('only newest response wins; invalidation suppresses in-flight success and failure', async () => {
  const order = new LatestPreview();
  const accepted = [];
  let oldResolve;
  const older = order.run(
    () =>
      new Promise((resolve) => {
        oldResolve = resolve;
      }),
    (value) => accepted.push(value),
    () => accepted.push('error'),
  );
  await order.run(
    async () => 'new',
    (value) => accepted.push(value),
    () => {},
  );
  oldResolve('old');
  await older;
  assert.deepEqual(accepted, ['new']);
  let reject;
  const cancelled = order.run(
    () =>
      new Promise((_, r) => {
        reject = r;
      }),
    (value) => accepted.push(value),
    () => accepted.push('error'),
  );
  order.invalidate();
  reject(new Error('stale'));
  await cancelled;
  assert.deepEqual(accepted, ['new']);
});
