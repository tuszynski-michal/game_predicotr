import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createImageFolderImport,
  reprocessImageFolderImport,
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
  );

  assert.deepEqual(result, { displayName: 'photos', ok: true, selection });
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
