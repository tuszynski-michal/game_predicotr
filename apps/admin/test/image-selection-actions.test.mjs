import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadManualImageSelectionGroups,
  orderImageSelectionFiles,
  uploadPhotoSelectionFolder,
} from '../src/features/image-selection/image-selection-actions.ts';

test('loads the bounded group cursor and keeps only manual queue items', async () => {
  const cursors = [];
  const api = {
    listImageSelectionGroups: async (_runId, options) => {
      cursors.push(options.afterGroupOrder);
      return options.afterGroupOrder === undefined
        ? {
            data: {
              items: [
                { groupOrder: 0, id: 'auto', status: 'auto_selected' },
                { groupOrder: 1, id: 'pending', status: 'manual_required' },
              ],
              nextAfterGroupOrder: 1,
            },
          }
        : {
            data: {
              items: [
                {
                  groupOrder: 2,
                  id: 'approved',
                  status: 'manually_selected',
                },
              ],
              nextAfterGroupOrder: null,
            },
          };
    },
  };

  const result = await loadManualImageSelectionGroups(api, 'run-1');

  assert.deepEqual(cursors, [undefined, 1]);
  assert.deepEqual(
    result.map((group) => group.id),
    ['pending', 'approved'],
  );
});

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
    uploadedFileIndexes: [...uploadedIndexes].sort(
      (left, right) => left - right,
    ),
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

test('retries run creation without uploading the finalized folder again', async () => {
  const files = [imageFile('photo-1.jpg')];
  let createRunCalls = 0;
  let uploadCalls = 0;
  let finalizeCalls = 0;
  const api = {
    createBrowserImageSelection: async () => ({ data: uploadState(files) }),
    getBrowserImageSelection: async () => ({
      data: uploadState(files, [0]),
    }),
    uploadBrowserImageSelectionFile: async () => {
      uploadCalls += 1;
      return { data: uploadState(files, [0]) };
    },
    finalizeBrowserImageSelection: async () => {
      finalizeCalls += 1;
      return { data: { selectionToken: `selection-token-${finalizeCalls}` } };
    },
    createImageSelection: async () => {
      createRunCalls += 1;
      return createRunCalls === 1
        ? { error: { code: 'TRANSIENT_CONFLICT', message: 'retry' } }
        : { data: createdRun() };
    },
  };

  const failed = await uploadPhotoSelectionFolder(api, 'game-1', files);

  assert.equal(failed.ok, false);
  assert.notEqual(failed.resume, null);

  const resumed = await uploadPhotoSelectionFolder(api, 'game-1', [], {
    resume: failed.resume,
  });

  assert.equal(resumed.ok, true);
  assert.equal(uploadCalls, 1);
  assert.equal(finalizeCalls, 2);
  assert.equal(createRunCalls, 2);
});
