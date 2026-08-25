import assert from 'node:assert/strict';
import test from 'node:test';

import {
  continueWithAutomaticallySelectedImages,
  loadAutomaticallySelectedImageSelectionGroups,
  loadImageSelectionGroupsAfter,
  loadImageSelectionReviewQueues,
  loadManualImageSelectionGroups,
  orderImageSelectionFiles,
  saveFinalizedImageSelectionGroups,
  saveImageSelectionOutputToFolder,
  uploadPhotoSelectionFolder,
  visibleImageSelectionRuns,
} from '../src/features/image-selection/image-selection-actions.ts';
import { restoreOutputDirectory } from '../src/features/image-selection/image-selection-output-directory.ts';

test('restores a remembered output directory only with read-write permission', async () => {
  let permissionRequests = 0;
  const directory = {
    getFileHandle: async () => {
      throw new Error('not used');
    },
    queryPermission: async () => 'prompt',
    requestPermission: async () => {
      permissionRequests += 1;
      return 'granted';
    },
  };
  const restored = await restoreOutputDirectory(
    { load: async () => directory, save: async () => undefined },
    'game-1',
    'run-1',
  );

  assert.equal(restored, directory);
  assert.equal(permissionRequests, 1);
});

test('does not restore a remembered output directory after permission denial', async () => {
  const restored = await restoreOutputDirectory(
    {
      load: async () => ({
        getFileHandle: async () => {
          throw new Error('not used');
        },
        queryPermission: async () => 'denied',
      }),
      save: async () => undefined,
    },
    'game-1',
    'run-1',
  );

  assert.equal(restored, null);
});

test('shows only active and useful image-selection runs', () => {
  const run = (id, status, current, total) => ({
    id,
    job: { progress: { current, total }, status },
  });

  assert.deepEqual(
    visibleImageSelectionRuns([
      run('created', 'created', 0, 100),
      run('processing', 'processing', 20, 100),
      run('full-review', 'waiting_for_review', 100, 100),
      run('partial-review', 'waiting_for_review', 20, 100),
      run('completed', 'completed', 100, 100),
      run('cancelled', 'cancelled', 20, 100),
      run('failed', 'failed', 20, 100),
    ]).map(({ id }) => id),
    ['created', 'processing', 'full-review', 'completed'],
  );
});

test('loads every automatically selected group through the server-side status filter', async () => {
  const requests = [];
  const api = {
    listImageSelectionGroups: async (_runId, options) => {
      requests.push(options);
      return options.afterGroupOrder === undefined
        ? {
            data: {
              items: [{ groupOrder: 2, id: 'auto-1', status: 'auto_selected' }],
              nextAfterGroupOrder: 2,
            },
          }
        : {
            data: {
              items: [{ groupOrder: 7, id: 'auto-2', status: 'auto_selected' }],
              nextAfterGroupOrder: null,
            },
          };
    },
  };

  const result = await loadAutomaticallySelectedImageSelectionGroups(
    api,
    'run-1',
  );

  assert.deepEqual(
    requests.map(({ afterGroupOrder, limit, status }) => ({
      afterGroupOrder,
      limit,
      status,
    })),
    [
      { afterGroupOrder: undefined, limit: 100, status: 'auto_selected' },
      { afterGroupOrder: 2, limit: 100, status: 'auto_selected' },
    ],
  );
  assert.deepEqual(
    result.map((group) => group.id),
    ['auto-1', 'auto-2'],
  );
});

test('loads only image-selection groups after the progressive export cursor', async () => {
  const cursors = [];
  const api = {
    listImageSelectionGroups: async (_runId, options) => {
      cursors.push(options.afterGroupOrder);
      return options.afterGroupOrder === 17
        ? {
            data: {
              items: [{ groupOrder: 18 }, { groupOrder: 19 }],
              nextAfterGroupOrder: 19,
            },
          }
        : {
            data: {
              items: [{ groupOrder: 20 }],
              nextAfterGroupOrder: null,
            },
          };
    },
  };

  const result = await loadImageSelectionGroupsAfter(api, 'run-1', 17);

  assert.deepEqual(cursors, [17, 19]);
  assert.deepEqual(
    result.groups.map((group) => group.groupOrder),
    [18, 19, 20],
  );
  assert.equal(result.lastGroupOrder, 20);
});

test('saves each finalized group immediately without overwriting conflicts', async () => {
  const payload = new Blob(['selected-jpeg'], { type: 'image/jpeg' });
  const saved = new Map();
  const api = {
    getImageSelectionSelectedGroupFile: async () => ({ data: payload }),
  };
  const directory = {
    getFileHandle: async (fileName, options) => {
      if (options?.create !== true && !saved.has(fileName)) {
        throw new DOMException('missing', 'NotFoundError');
      }
      return {
        createWritable: async () => ({
          abort: async () => undefined,
          close: async () => undefined,
          write: async (blob) =>
            saved.set(fileName, new File([blob], fileName)),
        }),
        getFile: async () => saved.get(fileName),
      };
    },
  };
  const completed = new Set();
  const groups = [
    {
      groupOrder: 0,
      id: 'group-1',
      rangeEnd: 9,
      rangeStart: 1,
      selectedCandidateId: 'candidate-1',
      status: 'auto_selected',
    },
  ];

  const first = await saveFinalizedImageSelectionGroups(
    api,
    'run-1',
    groups,
    directory,
    completed,
  );
  const replay = await saveFinalizedImageSelectionGroups(
    api,
    'run-1',
    groups,
    directory,
    completed,
  );

  assert.deepEqual(first, { error: null, savedCount: 1 });
  assert.deepEqual(replay, { error: null, savedCount: 0 });
  assert.equal(await saved.get('seq_1-9.jpg').text(), 'selected-jpeg');
});

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
                {
                  groupOrder: 3,
                  id: 'missing',
                  status: 'missing_image',
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
    ['pending', 'approved', 'missing'],
  );
});

test('splits representative, range and rejected review queues', async () => {
  const statuses = [
    'manual_required',
    'range_required',
    'range_confirmed',
    'rejected_by_user',
    'skipped_unreadable',
  ];
  const queues = await loadImageSelectionReviewQueues(
    {
      listImageSelectionGroups: async () => ({
        data: {
          items: statuses.map((status, groupOrder) => ({
            groupOrder,
            id: status,
            rangeEnd: null,
            rangeStart: null,
            status,
          })),
          nextAfterGroupOrder: null,
        },
      }),
    },
    'run-1',
  );

  assert.deepEqual(
    queues.representative.map((group) => group.id),
    ['manual_required'],
  );
  assert.deepEqual(
    queues.range.map((group) => group.id),
    ['range_required', 'range_confirmed'],
  );
  assert.deepEqual(
    queues.rejected.map((group) => group.id),
    ['rejected_by_user'],
  );
});

test('prefills only a bounded unambiguous range gap for a missing image', async () => {
  const api = {
    listImageSelectionGroups: async () => ({
      data: {
        items: [
          {
            groupOrder: 0,
            id: 'previous',
            rangeStart: 1,
            rangeEnd: 9,
            status: 'auto_selected',
          },
          {
            groupOrder: 1,
            id: 'missing',
            rangeStart: null,
            rangeEnd: null,
            status: 'manual_required',
          },
          {
            groupOrder: 2,
            id: 'next',
            rangeStart: 19,
            rangeEnd: 27,
            status: 'auto_selected',
          },
        ],
        nextAfterGroupOrder: null,
      },
    }),
  };

  const [missing] = await loadManualImageSelectionGroups(api, 'run-1');

  assert.equal(missing.rangeStart, 10);
  assert.equal(missing.rangeEnd, 18);
});

test('does not assign the same suggested range to multiple unresolved groups', async () => {
  const api = {
    listImageSelectionGroups: async () => ({
      data: {
        items: [
          {
            groupOrder: 0,
            id: 'previous',
            rangeStart: 1,
            rangeEnd: 9,
            status: 'auto_selected',
          },
          {
            groupOrder: 1,
            id: 'first-missing',
            rangeStart: null,
            rangeEnd: null,
            status: 'manual_required',
          },
          {
            groupOrder: 2,
            id: 'second-missing',
            rangeStart: null,
            rangeEnd: null,
            status: 'manual_required',
          },
          {
            groupOrder: 3,
            id: 'next',
            rangeStart: 19,
            rangeEnd: 27,
            status: 'auto_selected',
          },
        ],
        nextAfterGroupOrder: null,
      },
    }),
  };

  const missing = await loadManualImageSelectionGroups(api, 'run-1');

  assert.deepEqual(
    missing.map((group) => [group.id, group.rangeStart, group.rangeEnd]),
    [
      ['first-missing', null, null],
      ['second-missing', null, null],
    ],
  );
});

test('continues with automatic selections without inventing unknown ranges', async () => {
  const commands = [];
  const api = {
    continueImageSelectionWithoutImage: async (_runId, groupId, command) => {
      commands.push({ command, groupId });
      return {
        data: {
          group: {
            id: groupId,
            rangeEnd: null,
            rangeStart: null,
            status: 'missing_image',
          },
        },
      };
    },
  };

  const result = await continueWithAutomaticallySelectedImages(
    api,
    'run-1',
    [
      {
        id: 'unknown',
        rangeEnd: null,
        rangeStart: null,
        status: 'manual_required',
      },
      {
        id: 'known',
        rangeEnd: 18,
        rangeStart: 10,
        status: 'manual_required',
      },
      { id: 'auto', status: 'auto_selected' },
    ],
    () => 'decision-key',
  );

  assert.equal(result.error, null);
  assert.equal(result.skippedCount, 2);
  assert.deepEqual(commands, [
    { command: { idempotencyKey: 'decision-key' }, groupId: 'unknown' },
    { command: { idempotencyKey: 'decision-key' }, groupId: 'known' },
  ]);
});

test('saves verified output under deterministic sequence names', async () => {
  const payload = new Blob(['jpeg-content'], { type: 'image/jpeg' });
  const checksum = await sha256(payload);
  const saved = new Map();
  const api = {
    getImageSelectionOutput: async () => ({
      data: {
        files: [
          {
            checksumSha256: checksum,
            fileName: 'seq_1-9.jpg',
            rangeEnd: 9,
            rangeStart: 1,
            sizeBytes: payload.size,
          },
        ],
        manifestSha256: 'a'.repeat(64),
        runId: 'run-1',
      },
    }),
    getImageSelectionOutputFile: async () => ({ data: payload }),
  };
  const directory = {
    getFileHandle: async (fileName) => ({
      createWritable: async () => ({
        abort: async () => undefined,
        close: async () => undefined,
        write: async (blob) => saved.set(fileName, await blob.text()),
      }),
    }),
  };

  const result = await saveImageSelectionOutputToFolder(api, 'run-1', {
    pickDirectory: async () => directory,
  });

  assert.deepEqual(result, { cancelled: false, error: null, savedCount: 1 });
  assert.equal(saved.get('seq_1-9.jpg'), 'jpeg-content');
});

test('explains how to recover when a stale API cannot list output files', async () => {
  const api = {
    getImageSelectionOutput: async () => ({
      error: { detail: 'Not Found' },
    }),
  };

  const result = await saveImageSelectionOutputToFolder(api, 'run-1', {
    pickDirectory: async () => ({
      getFileHandle: async () => {
        throw new Error('must not write without a verified output');
      },
    }),
  });

  assert.deepEqual(result, {
    cancelled: false,
    error:
      'Nie udało się zweryfikować listy wybranych zdjęć. Uruchom ponownie lokalne Admin API i spróbuj ponownie.',
    savedCount: 0,
  });
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

async function sha256(blob) {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await blob.arrayBuffer(),
  );
  return Buffer.from(digest).toString('hex');
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

  const result = await uploadPhotoSelectionFolder(api, 'game-1', files, {
    firstSequenceNumber: 1,
  });

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

  const failed = await uploadPhotoSelectionFolder(api, 'game-1', files, {
    firstSequenceNumber: 1,
  });
  assert.equal(failed.ok, false);
  assert.notEqual(failed.resume, null);

  allowSecondFile = true;
  const resumed = await uploadPhotoSelectionFolder(api, 'game-1', [], {
    firstSequenceNumber: 1,
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

  const failed = await uploadPhotoSelectionFolder(api, 'game-1', files, {
    firstSequenceNumber: 1,
  });

  assert.equal(failed.ok, false);
  assert.notEqual(failed.resume, null);

  const resumed = await uploadPhotoSelectionFolder(api, 'game-1', [], {
    firstSequenceNumber: 1,
    resume: failed.resume,
  });

  assert.equal(resumed.ok, true);
  assert.equal(uploadCalls, 1);
  assert.equal(finalizeCalls, 2);
  assert.equal(createRunCalls, 2);
});

test('requires the first layout number before creating browser staging', async () => {
  let createCalls = 0;
  const result = await uploadPhotoSelectionFolder(
    {
      createBrowserImageSelection: async () => {
        createCalls += 1;
        return { data: uploadState([]) };
      },
    },
    'game-1',
    [imageFile('photo-1.jpg')],
  );

  assert.equal(result.ok, false);
  assert.match(result.error, /numer pierwszej planszy/i);
  assert.equal(createCalls, 0);
});
