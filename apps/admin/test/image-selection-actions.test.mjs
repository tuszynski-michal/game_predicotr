import assert from 'node:assert/strict';
import test from 'node:test';

import {
  orderImageSelectionFiles,
  uploadPhotoSelectionFolder,
} from '../src/features/image-selection/image-selection-actions.ts';

function imageFile(name, relativePath = `photos/${name}`) {
  const file = new File(['jpeg'], name, { type: 'image/jpeg' });
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath });
  return file;
}

function uploadState(files, uploadedIndexes = []) {
  return {
    expectedFileCount: files.length,
    expectedTotalBytes: files.reduce((total, file) => total + file.size, 0),
    gameId: 'game-1',
    purpose: 'photo_selection',
    uploadId: 'upload-1',
    uploadedBytes: uploadedIndexes.reduce(
      (total, index) => total + files[index].size,
      0,
    ),
    uploadedFileCount: uploadedIndexes.length,
    uploadedFileIndexes: [...uploadedIndexes].sort((left, right) => left - right),
  };
}

function createdRun() {
  return {
    created: true,
    run: {
      id: 'run-1',
      inputManifestSha256: 'a'.repeat(64),
      job: { id: 'job-1', jobType: 'image_selection', status: 'created' },
      orderingPolicy: 'natural_relative_path_v1',
    },
  };
}

test('orders browser files by deterministic natural relative path', () => {
  const ordered = orderImageSelectionFiles([
    imageFile('photo-10.jpg'),
    imageFile('photo-2.jpg'),
    imageFile('photo-1.jpg'),
  ]);

  assert.deepEqual(
    ordered.map((file) => file.name),
    ['photo-1.jpg', 'photo-2.jpg', 'photo-10.jpg'],
  );
});

test('uploads at most four JPEGs concurrently', async () => {
  const files = Array.from({ length: 9 }, (_value, index) =>
    imageFile(`photo-${index + 1}.jpg`),
  );
  const completed = new Set();
  let active = 0;
  let maxActive = 0;
  const api = {
    createBrowserImageSelection: async () => ({ data: uploadState(files) }),
    uploadBrowserImageSelectionFile: async (_uploadId, index) => {
      active += 1;
      maxActive = Math.max(maxActive, active);
      await new Promise((resolve) => setImmediate(resolve));
      completed.add(index);
      active -= 1;
      return { data: uploadState(files, [...completed]) };
    },
    finalizeBrowserImageSelection: async () => ({
      data: { selectionToken: 'selection-token' },
    }),
    createImageSelection: async () => ({ data: createdRun() }),
  };

  const result = await uploadPhotoSelectionFolder(api, 'game-1', files);

  assert.equal(result.ok, true);
  assert.equal(maxActive, 4);
});

test('resumes only a failed file without selecting the folder again', async () => {
  const files = [
    imageFile('photo-1.jpg'),
    imageFile('photo-2.jpg'),
    imageFile('photo-3.jpg'),
  ];
  const completed = new Set();
  const attempts = new Map();
  let allowSecondFile = false;
  let createCalls = 0;
  let restoreCalls = 0;
  const api = {
    createBrowserImageSelection: async () => {
      createCalls += 1;
      return { data: uploadState(files) };
    },
    getBrowserImageSelection: async () => {
      restoreCalls += 1;
      return { data: uploadState(files, [...completed]) };
    },
    uploadBrowserImageSelectionFile: async (_uploadId, index) => {
      attempts.set(index, (attempts.get(index) ?? 0) + 1);
      if (index === 1 && !allowSecondFile) {
        return { error: { code: 'UPLOAD_FAILED', message: 'retry' } };
      }
      completed.add(index);
      return { data: uploadState(files, [...completed]) };
    },
    finalizeBrowserImageSelection: async () => ({
      data: { selectionToken: 'selection-token' },
    }),
    createImageSelection: async () => ({ data: createdRun() }),
  };

  const failed = await uploadPhotoSelectionFolder(api, 'game-1', files);
  assert.equal(failed.ok, false);
  assert.notEqual(failed.resume, null);

  allowSecondFile = true;
  const resumed = await uploadPhotoSelectionFolder(api, 'game-1', [], {
    resume: failed.resume,
  });

  assert.equal(resumed.ok, true);
  assert.equal(createCalls, 1);
  assert.equal(restoreCalls, 1);
  assert.equal(attempts.get(0), 1);
  assert.equal(attempts.get(1), 4);
  assert.equal(attempts.get(2), 1);
});
