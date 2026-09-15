import assert from 'node:assert/strict';
import test from 'node:test';

import {
  acquireSelectedImageCropPreparationLease,
  SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING,
  withSelectedImageCropPreparationLease,
} from '../src/features/semi-automatic-image-selection/selected-image-crop-preparation-lease.ts';

test('the preparation lease excludes a second writer and releases after abort', async () => {
  let held = false;
  let abortCount = 0;
  const options = [];
  const file = {
    async createWritable(received) {
      options.push(received);
      if (held)
        throw new DOMException(
          'The file is already locked.',
          'InvalidStateError',
        );
      held = true;
      return {
        async abort() {
          held = false;
          abortCount += 1;
        },
      };
    },
  };
  const stateDirectory = {
    async getFileHandle(name, received) {
      assert.equal(name, 'browser-preparation.lock');
      assert.deepEqual(received, { create: true });
      return file;
    },
  };
  const outputDirectory = {
    async getDirectoryHandle(name, received) {
      assert.equal(name, '.manual-image-crop-state');
      assert.deepEqual(received, { create: true });
      return stateDirectory;
    },
  };

  const first = await acquireSelectedImageCropPreparationLease(outputDirectory);
  await assert.rejects(
    acquireSelectedImageCropPreparationLease(outputDirectory),
    new RegExp(SELECTED_IMAGE_CROP_PREPARATION_ALREADY_RUNNING, 'u'),
  );
  assert.deepEqual(options[0], {
    keepExistingData: true,
    mode: 'exclusive',
  });

  await first.release();
  await first.release();
  assert.equal(abortCount, 1);
  const next = await acquireSelectedImageCropPreparationLease(outputDirectory);
  await next.release();
  assert.equal(abortCount, 2);

  await assert.rejects(
    withSelectedImageCropPreparationLease(outputDirectory, async () => {
      throw new Error('operation failed');
    }),
    /operation failed/u,
  );
  assert.equal(abortCount, 3);
  const afterFailure =
    await acquireSelectedImageCropPreparationLease(outputDirectory);
  await afterFailure.release();
  assert.equal(abortCount, 4);
});
