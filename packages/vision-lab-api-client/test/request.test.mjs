import test from 'node:test';
import assert from 'node:assert/strict';
import {
  detectGeometry,
  saveAnnotation,
  saveFamily,
  createBackup,
  getAnnotations,
  freezeSplit,
} from '../src/generated/sdk.gen.ts';
import { boundary } from '../../../apps/vision-lab/src/lib/boundary.ts';
import { freezeAnnotations } from '../src/index.ts';

for (const policy of [
  undefined,
  'lab-geometry-cohort-777-targets-v2',
  'lab-geometry-whole-game-pilot-v1',
]) {
  test(`freeze wrapper preserves ${policy ?? 'original cohort'}, order and leakage maps`, async () => {
    const body = {
      request_id: 'cohort-split',
      expected_revision: 8,
      actor: 'operator',
      purpose: 'geometry',
      ...(policy ? { geometry_policy: policy } : {}),
      ...(policy === 'lab-geometry-whole-game-pilot-v1'
        ? {
            game_partitions: {
              a: 'development',
              b: 'validation',
              c: 'final_test',
              unseen: 'unseen_game',
            },
          }
        : {}),
      geometry_source_ids: ['b', 'a'],
      unseen_game_id: 'unseen',
      seed: 17,
      measurement_source_ids:
        policy === 'lab-geometry-whole-game-pilot-v1' ? [] : ['a'],
      difficulties:
        policy === 'lab-geometry-whole-game-pilot-v1'
          ? {}
          : { a: 'normal', alias: 'normal' },
    };
    const state = {
      revision: 9,
      split: {
        policy_version: policy ?? 'lab-geometry-cohort-split-v1',
        ...(body.game_partitions
          ? { game_partitions: body.game_partitions }
          : {}),
        geometry_source_ids: ['a', 'b'],
        leakage_components: {
          a: ['a', 'alias'],
          b: ['b'],
          excluded: ['excluded'],
        },
        leakage_component_fingerprints: {
          a: 'first',
          b: 'second',
          excluded: 'third',
        },
        assignments: { a: 'measurement', b: 'unseen_game' },
      },
    };
    const originalRequest = globalThis.Request;
    const originalFetch = globalThis.fetch;
    try {
      // Emulate the browser origin for the wrapper's existing relative base URL.
      globalThis.Request = class extends originalRequest {
        constructor(input, init) {
          super(
            typeof input === 'string'
              ? new URL(input, 'http://127.0.0.1:3102')
              : input,
            init,
          );
        }
      };
      globalThis.fetch = async (request) => {
        assert.equal(request.url, 'http://127.0.0.1:3102/api/lab/splits');
        assert.deepEqual(await request.json(), body);
        return new Response(JSON.stringify(state), {
          headers: { 'content-type': 'application/json' },
        });
      };
      assert.deepEqual(await freezeAnnotations(body), state);
    } finally {
      globalThis.Request = originalRequest;
      globalThis.fetch = originalFetch;
    }
  });
}

test('geometry-only state and explicit split purpose preserve the generated contract', async () => {
  const qualification = {
    source_id: 'historical-source',
    source_sha256: 'a'.repeat(64),
    expected_board_revisions: { 0: 2 },
    game_id: 'historical-game',
    purpose: 'geometry',
    policy_version: 'historical-777-lab-geometry-v1',
    decision_reference: 'D-453',
    actor: 'operator',
    decided_at: '2026-09-27',
    revision: 3,
  };
  const state = {
    snapshot_id: 'snapshot',
    revision: 3,
    annotations: {},
    families: {},
    timings: [],
    split: null,
    split_stale: false,
    photo_reviews: {},
    geometry_qualifications: { 'historical-source': qualification },
  };
  const response = await getAnnotations({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    throwOnError: true,
    fetch: async () =>
      new Response(JSON.stringify(state), {
        headers: { 'content-type': 'application/json' },
      }),
  });
  assert.deepEqual(response.data, state);
  const body = {
    request_id: 'geometry-split',
    expected_revision: 3,
    actor: 'operator',
    purpose: 'geometry',
    unseen_game_id: 'unseen',
    seed: 17,
    measurement_source_ids: ['a', 'b'],
    difficulties: { a: 'normal', b: 'normal' },
  };
  await freezeSplit({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body,
    throwOnError: true,
    fetch: async (request) => {
      assert.equal(request.url, 'http://127.0.0.1:3102/api/lab/splits');
      assert.deepEqual(await request.json(), body);
      return new Response(JSON.stringify(state), {
        headers: { 'content-type': 'application/json' },
      });
    },
  });
});
test('generated request uses JSON and declared source/topology, never a path', async () => {
  let captured;
  const fetch = async (request) => {
    captured = request;
    return new Response(
      JSON.stringify({
        source_id: 'source',
        topology: { columns: 3, rows: 3 },
        model_version: 'test',
        status: 'unsupported',
        boards: [],
        reasons: [],
        width: 0,
        height: 0,
      }),
      { headers: { 'content-type': 'application/json' } },
    );
  };
  const response = await detectGeometry({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body: { source_id: 'source', topology: { columns: 3, rows: 3 } },
    fetch,
    throwOnError: true,
  });
  assert.equal(captured.url, 'http://127.0.0.1:3102/api/lab/geometry');
  assert.equal(captured.headers.get('content-type'), 'application/json');
  assert.deepEqual(await captured.json(), {
    source_id: 'source',
    topology: { columns: 3, rows: 3 },
  });
  assert.equal(response.data.status, 'unsupported');
});
test('annotation and family requests preserve revision, explicit intent and idempotency', async () => {
  for (const [call, route, body] of [
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'reject-photo',
        expected_revision: 8,
        actor: 'operator',
        action: 'reject',
        source_id: 'source',
        source_sha256: 'a'.repeat(64),
        expected_board_revisions: { 0: 2, 4: 1 },
        board_indices: [],
        note: '',
      },
    ],
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'request-01',
        expected_revision: 7,
        actor: 'human',
        action: 'approve_location',
        annotation: {
          source_id: 'source',
          board_index: 0,
          topology: { columns: 3, rows: 3 },
          corners: [],
        },
      },
    ],
    [
      saveFamily,
      'families',
      {
        request_id: 'request-02',
        expected_revision: 8,
        actor: 'human',
        decision: {
          source_ids: ['a', 'b'],
          family_id: 'recording',
          evidence: 'verified recording',
          provenance: 'verified',
          related_source_ids: ['c'],
        },
      },
    ],
    [
      saveAnnotation,
      'annotations',
      {
        request_id: 'review-request-03',
        expected_revision: 9,
        actor: 'operator',
        action: 'mark',
        source_id: 'source',
        source_sha256: 'a'.repeat(64),
        expected_board_revisions: { 0: 2, 4: 1 },
        board_indices: [4],
        note: 'Left corner',
      },
    ],
  ]) {
    let captured;
    await call({
      baseUrl: 'http://127.0.0.1:3102/api/lab',
      body,
      throwOnError: true,
      fetch: async (request) => {
        captured = request;
        return new Response('{}', {
          headers: { 'content-type': 'application/json' },
        });
      },
    });
    assert.equal(captured.url, `http://127.0.0.1:3102/api/lab/${route}`);
    assert.equal(captured.headers.get('content-type'), 'application/json');
    assert.deepEqual(await captured.json(), body);
  }
});

test('backup sends explicit JSON through the same mutation boundary', async () => {
  let captured;
  await createBackup({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body: {},
    throwOnError: true,
    headers: { host: '127.0.0.1:3102', origin: 'http://127.0.0.1:3102' },
    fetch: async (request) => {
      captured = request;
      assert.equal(boundary(request), null);
      return new Response('{"backup_id":"test","revision":1}', {
        headers: { 'content-type': 'application/json' },
      });
    },
  });
  assert.equal(captured.headers.get('content-type'), 'application/json');
  assert.deepEqual(await captured.json(), {});
});

test('manual preview extends the geometry route without annotation writes', async () => {
  const body = {
    source_id: 'source',
    topology: { columns: 3, rows: 3 },
    preview_board: {
      position_index: 2,
      status: 'complete',
      nodes: [{ x: 12, y: 34, provenance: 'human' }],
    },
  };
  await detectGeometry({
    baseUrl: 'http://127.0.0.1:3102/api/lab',
    body,
    throwOnError: true,
    fetch: async (request) => {
      assert.equal(request.url, 'http://127.0.0.1:3102/api/lab/geometry');
      assert.deepEqual(await request.json(), body);
      return new Response('{}', {
        headers: { 'content-type': 'application/json' },
      });
    },
  });
});
