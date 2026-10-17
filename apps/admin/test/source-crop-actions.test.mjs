import assert from 'node:assert/strict';
import test from 'node:test';

import {
  loadSourceCropRuns,
  planSourceCrop,
  refreshSourceCropRun,
  startSourceCrop,
} from '../src/features/storage/source-crop-actions.ts';

const previewed = (overrides = {}) => ({
  candidateBytes: 100,
  eligibleCount: 2,
  id: 'run-1',
  kind: 'crop',
  manifestChecksumSha256: 'c'.repeat(64),
  previewToken: 'token-1',
  status: 'previewed',
  ...overrides,
});

test('plans a run with the kind and scope and returns the planning run', async () => {
  const calls = [];
  const result = await planSourceCrop(
    {
      createSourceCropPreview: async (body) => {
        calls.push(body);
        return { data: { id: 'run-1', status: 'planning' } };
      },
    },
    'original_deletion',
    { gameId: 'game-1', limit: 10 },
  );
  assert.deepEqual(calls, [
    { kind: 'original_deletion', scope: { gameId: 'game-1', limit: 10 } },
  ]);
  assert.deepEqual(result, {
    ok: true,
    run: { id: 'run-1', status: 'planning' },
  });
});

test('reports API conflicts with the stable code and survives network loss', async () => {
  const conflict = await planSourceCrop(
    {
      createSourceCropPreview: async () => ({
        error: { code: 'SOURCE_CROP_RUN_ACTIVE', message: 'active' },
      }),
    },
    'crop',
    {},
  );
  assert.equal(conflict.ok, false);
  assert.match(conflict.error, /SOURCE_CROP_RUN_ACTIVE/);
  const lost = await refreshSourceCropRun(
    {
      getSourceCropRun: async () => {
        throw new Error('network');
      },
    },
    'run-1',
  );
  assert.deepEqual(lost, {
    error: 'Połączenie z lokalnym Admin API zostało przerwane.',
    ok: false,
  });
});

test('starts a crop run with the immutable checksum and token only', async () => {
  const calls = [];
  const result = await startSourceCrop(
    {
      startSourceCropRun: async (previewId, body) => {
        calls.push([previewId, body]);
        return { data: { id: 'run-1', status: 'created' } };
      },
    },
    previewed(),
    false,
  );
  assert.deepEqual(calls, [
    [
      'run-1',
      {
        confirmed: true,
        manifestChecksumSha256: 'c'.repeat(64),
        previewToken: 'token-1',
      },
    ],
  ]);
  assert.equal(result.ok, true);
});

test('deletion start sends acknowledgeIrreversible only after acknowledgement', async () => {
  const calls = [];
  const api = {
    startSourceCropRun: async (previewId, body) => {
      calls.push([previewId, body]);
      return { data: { id: 'run-1', status: 'created' } };
    },
  };
  const deletion = previewed({ kind: 'original_deletion' });
  const refused = await startSourceCrop(api, deletion, false);
  assert.equal(refused.ok, false);
  assert.equal(calls.length, 0);
  const accepted = await startSourceCrop(api, deletion, true);
  assert.equal(accepted.ok, true);
  assert.equal(calls[0][1].acknowledgeIrreversible, true);
  assert.equal(calls[0][1].confirmed, true);
});

test('refuses to start a run that is not previewed', async () => {
  let called = false;
  const api = {
    startSourceCropRun: async () => {
      called = true;
      return { data: {} };
    },
  };
  for (const run of [
    previewed({ status: 'planning' }),
    previewed({ previewToken: null }),
    previewed({ manifestChecksumSha256: null }),
  ]) {
    assert.equal((await startSourceCrop(api, run, true)).ok, false);
  }
  assert.equal(called, false);
});

test('maps a stale preview start error to a Polish message with the code', async () => {
  const stale = await startSourceCrop(
    {
      startSourceCropRun: async () => ({
        error: { code: 'SOURCE_CROP_PREVIEW_STALE', message: 'stale' },
      }),
    },
    previewed(),
    false,
  );
  assert.equal(stale.ok, false);
  assert.match(stale.error, /Zaplanuj przebieg ponownie/);
  assert.match(stale.error, /SOURCE_CROP_PREVIEW_STALE/);
});

test('loads the recent runs list', async () => {
  const calls = [];
  const result = await loadSourceCropRuns({
    listSourceCropRuns: async (limit) => {
      calls.push(limit);
      return { data: { runs: [previewed()] } };
    },
  });
  assert.equal(calls.length, 1);
  assert.equal(result.ok, true);
  assert.equal(result.runs.length, 1);
});
