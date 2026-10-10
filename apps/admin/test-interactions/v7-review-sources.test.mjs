import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createV7ReviewSourceFiles } from '../src/features/semi-automatic-image-selection/v7-review-sources.ts';
import { loadSemiAutomaticReviewSourceFiles } from '../src/features/semi-automatic-image-selection/semi-automatic-selection-actions.ts';

function fixture({
  wrongIndex = false,
  missing = false,
  failAsset = false,
} = {}) {
  const calls = [];
  const api = {
    async listSemiAutomaticImageSelectionSources(runId, after, limit) {
      calls.push(['metadata', runId, after, limit]);
      const index = after === undefined ? 0 : after + 1;
      return {
        data: {
          items: missing
            ? []
            : [
                {
                  sourceIndex: wrongIndex ? index + 1 : index,
                  relativePath: `folder/${index}.jpg`,
                  checksumSha256: 'a'.repeat(64),
                  sizeBytes: 4,
                },
              ],
          nextAfterSourceIndex: null,
        },
      };
    },
    async getSemiAutomaticImageSelectionSourceAsset(...args) {
      calls.push(['asset', ...args]);
      return failAsset
        ? { error: new Error('drift') }
        : { data: new Blob(['jpeg'], { type: 'image/jpeg' }) };
    },
  };
  return { api, calls };
}

test('V7 opens an index without reading all source pages; selected asset uses real SHA and name', async () => {
  const { api, calls } = fixture();
  const files = createV7ReviewSourceFiles(api, 'run', 3);
  assert.equal(files.length, 3);
  assert.deepEqual(calls, []);
  const file = await files[2].handle.getFile();
  assert.equal(file.name, '2.jpg');
  assert.equal(await file.text(), 'jpeg');
  assert.deepEqual(calls, [
    ['metadata', 'run', 1, 1],
    ['asset', 'run', 2, 'a'.repeat(64)],
  ]);
});

test('first source has no negative pagination index', async () => {
  const { api, calls } = fixture();
  await createV7ReviewSourceFiles(api, 'run', 1)[0].handle.getFile();
  assert.deepEqual(calls[0], ['metadata', 'run', undefined, 1]);
});

for (const options of [{ wrongIndex: true }, { missing: true }]) {
  test(`bad metadata never fetches an asset: ${JSON.stringify(options)}`, async () => {
    const { api, calls } = fixture(options);
    await assert.rejects(
      createV7ReviewSourceFiles(api, 'run', 1)[0].handle.getFile(),
      /metadanych/,
    );
    assert.equal(calls.length, 1);
  });
}

test('source drift failure stays a failed preview', async () => {
  const { api } = fixture({ failAsset: true });
  await assert.rejects(
    createV7ReviewSourceFiles(api, 'run', 1)[0].handle.getFile(),
    /zdjęcia źródłowego/,
  );
});

test('historical loader still reads metadata eagerly', async () => {
  const { api, calls } = fixture();
  const files = await loadSemiAutomaticReviewSourceFiles(api, 'old');
  assert.deepEqual(calls, [['metadata', 'old', undefined, undefined]]);
  assert.equal(files[0].relativePath, 'folder/0.jpg');
});

test('invalid source counts fail before any network access', () => {
  const { api, calls } = fixture();
  for (const count of [-1, 1.5, NaN])
    assert.throws(() => createV7ReviewSourceFiles(api, 'run', count));
  assert.deepEqual(createV7ReviewSourceFiles(api, 'run', 0), []);
  assert.deepEqual(calls, []);
});
