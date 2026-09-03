import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createImageFolderImport,
  listReadyBrowserImageSelections,
  previewReadyBrowserImageImport,
  reprocessImageFolderImport,
  startReadyBrowserImageImport,
  uploadImageFolder,
} from '../src/features/imports/image-folder-import-actions.ts';

test('uploads a browser-native folder and returns a validated selection', async () => {
  const selection = {
    expiresAt: '2026-07-31T12:15:00Z',
    path: 'C:\\photos',
    selectionToken: 'token',
    status: 'selected',
    supportedFileCount: 12,
  };
  const file = new File(['jpeg'], 'layout.jpg', { type: 'image/jpeg' });
  Object.defineProperty(file, 'webkitRelativePath', {
    value: 'photos/layout.jpg',
  });
  const calls = [];
  const progress = [];

  const result = await uploadImageFolder(
    {
      cancelBrowserImageSelection: async () => ({ data: undefined }),
      createBrowserImageSelection: async (body) => {
        calls.push(['create', body]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: file.size,
            uploadId: 'upload-1',
            uploadedBytes: 0,
            uploadedFileCount: 0,
          },
        };
      },
      finalizeBrowserImageSelection: async (uploadId) => {
        calls.push(['finalize', uploadId]);
        return { data: selection };
      },
      uploadBrowserImageSelectionFile: async (...args) => {
        calls.push(['upload', ...args]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: file.size,
            uploadId: 'upload-1',
            uploadedBytes: file.size,
            uploadedFileCount: 1,
          },
        };
      },
    },
    [file],
    (uploaded, total) => progress.push([uploaded, total]),
  );

  assert.deepEqual(result, {
    displayName: 'photos',
    kind: 'uploaded',
    ok: true,
    selection,
    uploadId: 'upload-1',
    uploadPlan: null,
  });
  assert.deepEqual(calls[0], [
    'create',
    {
      displayName: 'photos',
      expectedFileCount: 1,
      expectedTotalBytes: file.size,
    },
  ]);
  assert.deepEqual(calls[1].slice(0, 5), [
    'upload',
    'upload-1',
    0,
    'photos/layout.jpg',
    file,
  ]);
  assert.deepEqual(calls[2], ['finalize', 'upload-1']);
  assert.deepEqual(progress, [[1, 1]]);
});

test('filters fully imported seq ranges before uploading browser JPEG bytes', async () => {
  const existing = new File(['old'], 'seq_1-9.jpg', { type: 'image/jpeg' });
  const missing = new File(['new'], 'seq_10-18.jpg', { type: 'image/jpeg' });
  const calls = [];
  const result = await uploadImageFolder(
    {
      cancelBrowserImageSelection: async () => ({ data: undefined }),
      createBrowserImageSelection: async (body) => {
        calls.push(['create', body]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: missing.size,
            uploadId: 'upload-1',
            uploadedBytes: 0,
            uploadedFileCount: 0,
          },
        };
      },
      finalizeBrowserImageSelection: async () => ({
        data: { status: 'selected', supportedFileCount: 1 },
      }),
      planBrowserImageSelectionUpload: async (body) => {
        calls.push(['plan', body]);
        return {
          data: {
            filesToUpload: [
              {
                relativePath: 'seq_10-18.jpg',
                sizeBytes: missing.size,
                sourceIndex: 1,
                uploadIndex: 0,
              },
            ],
            missingSequenceCount: 9,
            partialSourceCount: 0,
            planChecksumSha256: 'a'.repeat(64),
            reusedSequenceCount: 9,
            selectedFileCount: 2,
            selectedTotalBytes: existing.size + missing.size,
            skippedCompleteSources: [
              {
                relativePath: 'seq_1-9.jpg',
                sequenceRangeEnd: 9,
                sequenceRangeStart: 1,
                sourceIndex: 0,
              },
            ],
            skippedCompleteSourceCount: 1,
            uploadFileCount: 1,
            uploadTotalBytes: missing.size,
            gameId: 'game-1',
          },
        };
      },
      uploadBrowserImageSelectionFile: async (...args) => {
        calls.push(['upload', ...args]);
        return {
          data: {
            expectedFileCount: 1,
            expectedTotalBytes: missing.size,
            uploadedBytes: missing.size,
            uploadedFileCount: 1,
          },
        };
      },
    },
    [existing, missing],
    'game-1',
  );

  assert.equal(result.ok, true);
  assert.equal(calls[0][0], 'plan');
  assert.deepEqual(calls[1], [
    'create',
    {
      displayName: 'seq_1-9.jpg',
      expectedFileCount: 1,
      expectedTotalBytes: missing.size,
      gameId: 'game-1',
      skippedCanonicalRanges: [
        { sequenceRangeEnd: 9, sequenceRangeStart: 1 },
      ],
      uploadPlanChecksumSha256: 'a'.repeat(64),
    },
  ]);
  assert.equal(calls[2][3], 'seq_10-18.jpg');
});

test('reprocesses an import from its managed originals', async () => {
  const job = {
    id: 'job-2',
    inputPayload: { importKind: 'image_directory', schemaVersion: 4 },
    jobType: 'import',
    status: 'created',
  };
  let sourceJobId;

  const result = await reprocessImageFolderImport(
    {
      reprocessManagedImageImport: async (value) => {
        sourceJobId = value;
        return { data: { job } };
      },
    },
    'job-1',
  );

  assert.equal(sourceJobId, 'job-1');
  assert.deepEqual(result, { job, ok: true });
});

test('creates an image import only from the approved selection token', async () => {
  let body;
  const job = {
    id: 'job-1',
    inputPayload: { importKind: 'image_directory' },
    jobType: 'import',
    status: 'created',
  };

  const result = await createImageFolderImport(
    {
      createImageFolderImport: async (value) => {
        body = value;
        return { data: { job } };
      },
    },
    'game-1',
    'approved-token',
  );

  assert.deepEqual(body, {
    gameId: 'game-1',
    selectionToken: 'approved-token',
  });
  assert.deepEqual(result, { job, ok: true });
});

test('preserves a stable browser folder validation error', async () => {
  const file = new File(['jpeg'], 'layout.jpg', { type: 'image/jpeg' });
  const result = await uploadImageFolder(
    {
      createBrowserImageSelection: async () => ({
        error: {
          code: 'IMAGE_FOLDER_EMPTY',
          details: {},
          message: 'No supported files.',
        },
      }),
    },
    [file],
  );

  assert.deepEqual(result, {
    error: 'No supported files. (IMAGE_FOLDER_EMPTY)',
    ok: false,
  });
});

test('previews and starts a recovered browser staging idempotently', async () => {
  const calls = [];
  const api = {
    listReadyBrowserImageSelections: async () => ({
      data: [{ uploadId: 'upload-1', displayName: '1-18' }],
    }),
    previewReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['preview', uploadId, body]);
      return {
        data: {
          uploadId,
          gameId: body.gameId,
          manifestChecksumSha256: 'a'.repeat(64),
          preflightChecksumSha256: 'b'.repeat(64),
          sourceFileCount: 2,
          attestedFileCount: 2,
          newSequenceCount: 9,
          reusedSequenceCount: 9,
          skippedSourceCount: 1,
          partialSourceCount: 0,
          alternativeSourceCount: 0,
          firstUnresolvedSequence: 10,
          lastUnresolvedSequence: 18,
          warnings: [],
          displayName: '1-18',
        },
      };
    },
    startReadyBrowserImageImport: async (uploadId, body) => {
      calls.push(['start', uploadId, body]);
      return {
        data: {
          created: false,
          job: { id: 'job-1' },
          preflight: {},
        },
      };
    },
  };

  assert.equal((await listReadyBrowserImageSelections(api)).ok, true);
  const preview = await previewReadyBrowserImageImport(
    api,
    'upload-1',
    'game-1',
  );
  assert.equal(preview.ok, true);
  const started = await startReadyBrowserImageImport(
    api,
    'upload-1',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-1',
    'c'.repeat(64),
    'verified_v19',
  );

  assert.equal(started.ok, true);
  assert.deepEqual(calls, [
    ['preview', 'upload-1', { gameId: 'game-1' }],
    [
      'start',
      'upload-1',
      {
        gameId: 'game-1',
        boardCellProcessingMode: 'verified_v19',
        imageEnginePolicy: 'verified_v19',
        geometryManifestChecksumSha256: 'c'.repeat(64),
        geometryPreflightJobId: 'geometry-job-1',
        manifestChecksumSha256: 'a'.repeat(64),
        preflightChecksumSha256: 'b'.repeat(64),
      },
    ],
  ]);
});

test('pins the game engine policy for a ready browser staging', async () => {
  let command;
  const result = await startReadyBrowserImageImport(
    {
      startReadyBrowserImageImport: async (_uploadId, body) => {
        command = body;
        return {
          data: {
            created: true,
            job: { id: 'job-v20' },
            preflight: {},
          },
        };
      },
    },
    'upload-v20',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-v20',
    'c'.repeat(64),
    'verified_v19',
  );

  assert.equal(result.ok, true);
  assert.equal(command.boardCellProcessingMode, 'verified_v19');
});

test('pins the cold-start geometry manifest for structured shadow', async () => {
  let command;
  const result = await startReadyBrowserImageImport(
    {
      startReadyBrowserImageImport: async (_uploadId, body) => {
        command = body;
        return {
          data: {
            created: true,
            job: { id: 'job-shadow' },
            preflight: {},
          },
        };
      },
    },
    'upload-shadow',
    'game-1',
    'a'.repeat(64),
    'b'.repeat(64),
    'geometry-job-shadow',
    'c'.repeat(64),
    'structured_shadow',
    2,
  );

  assert.equal(result.ok, true);
  assert.equal(command.imageEnginePolicy, 'structured_shadow');
  assert.equal(command.imageEnginePolicyRevision, 2);
  assert.equal(command.geometryPreflightJobId, 'geometry-job-shadow');
  assert.equal(command.geometryManifestChecksumSha256, 'c'.repeat(64));
});
