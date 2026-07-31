import assert from 'node:assert/strict';
import test from 'node:test';

import {
  createImageFolderImport,
  selectImageFolder,
} from '../src/features/imports/image-folder-import-actions.ts';

test('selects a validated local folder through the typed client', async () => {
  const selection = {
    expiresAt: '2026-07-31T12:15:00Z',
    path: 'C:\\photos',
    selectionToken: 'token',
    status: 'selected',
    supportedFileCount: 12,
  };

  const result = await selectImageFolder({
    selectLocalImageFolder: async () => ({ data: selection }),
  });

  assert.deepEqual(result, { ok: true, selection });
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

test('preserves a stable folder validation error', async () => {
  const result = await selectImageFolder({
    selectLocalImageFolder: async () => ({
      error: {
        code: 'IMAGE_FOLDER_EMPTY',
        details: {},
        message: 'No supported files.',
      },
    }),
  });

  assert.deepEqual(result, {
    error: 'No supported files. (IMAGE_FOLDER_EMPTY)',
    ok: false,
  });
});
