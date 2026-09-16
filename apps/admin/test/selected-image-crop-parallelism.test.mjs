import assert from 'node:assert/strict';
import test from 'node:test';

import {
  mapSelectedImageCropBatch,
  selectedImageCropWorkerConcurrency,
} from '../src/features/semi-automatic-image-selection/selected-image-crop-parallelism.ts';

test('worker concurrency is bounded by the available logical processors', () => {
  assert.equal(selectedImageCropWorkerConcurrency(2), 1);
  assert.equal(selectedImageCropWorkerConcurrency(4), 2);
  assert.equal(selectedImageCropWorkerConcurrency(8), 3);
  assert.equal(selectedImageCropWorkerConcurrency(12), 4);
  assert.equal(selectedImageCropWorkerConcurrency(32), 4);
  assert.equal(selectedImageCropWorkerConcurrency(undefined), 2);
});

test('bounded batch preserves input order when analyses finish out of order', async () => {
  let active = 0;
  let maximumActive = 0;
  const releases = new Map();
  const started = [];
  const pending = mapSelectedImageCropBatch([0, 1, 2, 3], 4, async (value) => {
    active += 1;
    maximumActive = Math.max(maximumActive, active);
    started.push(value);
    await new Promise((resolve) => releases.set(value, resolve));
    active -= 1;
    return `result-${value}`;
  });

  while (started.length < 4)
    await new Promise((resolve) => setImmediate(resolve));
  for (const value of [3, 2, 1, 0]) releases.get(value)();

  const results = await pending;
  assert.equal(maximumActive, 4);
  assert.deepEqual(
    results.map((result) =>
      result.status === 'fulfilled' ? result.value : 'rejected',
    ),
    ['result-0', 'result-1', 'result-2', 'result-3'],
  );
});

test('one rejected analysis does not stop the remaining batch', async () => {
  const results = await mapSelectedImageCropBatch(
    [0, 1, 2],
    2,
    async (value) => {
      if (value === 1) throw new Error('BROKEN_IMAGE');
      return value;
    },
  );
  assert.deepEqual(
    results.map((result) => result.status),
    ['fulfilled', 'rejected', 'fulfilled'],
  );
});
