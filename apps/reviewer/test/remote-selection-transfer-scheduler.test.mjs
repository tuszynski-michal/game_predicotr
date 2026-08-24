import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FetchRemoteSelectionTransferTransport,
  RemoteSelectionTransferHttpError,
  RemoteSelectionTransferScheduler,
  isRetryableTransferError,
  retryDelayMs,
} from '../src/features/manual-selection/remote-selection-transfer-scheduler.ts';

const ids = [
  '11111111-1111-4111-8111-111111111111',
  '22222222-2222-4222-8222-222222222222',
  '33333333-3333-4333-8333-333333333333',
  '44444444-4444-4444-8444-444444444444',
];

test('transfer transport invokes browser fetch with the global receiver', async () => {
  let receiverIsGlobalThis = false;
  const transferId = ids[0];
  const source = task('brand-check', 1);
  const transport = new FetchRemoteSelectionTransferTransport(
    '50000000-0000-4000-8000-000000000001',
    function fetchWithBrowserBrand() {
      receiverIsGlobalThis = this === globalThis;
      return Promise.resolve(
        Response.json({
          ...response(source, 'not_started'),
          transferId,
        }),
      );
    },
  );

  await transport.status(source, transferId, new AbortController().signal);

  assert.equal(receiverIsGlobalThis, true);
});

test('scheduler bounds concurrency, preserves priority and keeps only metadata', async () => {
  const started = [];
  const releases = [];
  let active = 0;
  let peak = 0;
  const transport = {
    async status(task) {
      return response(task, 'not_started');
    },
    async upload(task) {
      started.push(task.priority);
      active += 1;
      peak = Math.max(peak, active);
      await new Promise((resolve) => releases.push(resolve));
      active -= 1;
      return response(task, 'verified');
    },
  };
  const checkpoints = [];
  const scheduler = new RemoteSelectionTransferScheduler(
    transport,
    store(checkpoints),
    {
      createTransferId: sequenceIds(),
      maxConcurrency: 2,
      maxPendingBytes: 100,
    },
  );
  await scheduler.enqueue(task('a', 3));
  await scheduler.enqueue(task('b', 1));
  await scheduler.enqueue(task('c', 2));
  await settle();
  assert.equal(peak, 2);
  assert.deepEqual(started, [3, 1]);
  releases.shift()?.();
  releases.shift()?.();
  await settle();
  assert.deepEqual(started, [3, 1, 2]);
  releases.shift()?.();
  await settle();
  assert.deepEqual(scheduler.snapshot(), {
    active: 0,
    pendingBytes: 0,
    queued: 0,
  });
  assert.ok(checkpoints.every((value) => !('blob' in value)));
  assert.equal(
    checkpoints.filter((value) => value.status === 'verified').length,
    3,
  );
});

test('status-before-retry recovers lost acknowledgement without second upload', async () => {
  let statusCalls = 0;
  let uploadCalls = 0;
  let verified = false;
  const checkpoints = [];
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(input) {
        statusCalls += 1;
        return response(input, verified ? 'verified' : 'not_started');
      },
      async upload() {
        uploadCalls += 1;
        verified = true;
        throw new TypeError('lost response');
      },
    },
    store(checkpoints),
    {
      createTransferId: () => ids[0],
      sleep: async () => {},
    },
  );
  await scheduler.enqueue(task('a', 1));
  await waitFor(() => scheduler.snapshot().active === 0);
  assert.equal(uploadCalls, 1);
  assert.equal(statusCalls, 2);
  assert.equal(checkpoints.at(-1)?.status, 'verified');
});

test('refresh restores the stable transfer id from metadata checkpoint', async () => {
  let observedTransferId = null;
  let uploads = 0;
  const input = task('a', 1);
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(taskValue, transferId) {
        observedTransferId = transferId;
        return response(taskValue, 'verified');
      },
      async upload() {
        uploads += 1;
      },
    },
    {
      loadTransferCheckpoint: async () => ({
        schemaVersion: 1,
        sessionId: input.sessionId,
        batchId: input.batchId,
        fileId: input.fileId,
        generation: input.generation,
        sourceRelativePath: input.sourceRelativePath,
        expectedSizeBytes: input.expectedSizeBytes,
        expectedChecksumSha256: input.expectedChecksumSha256,
        acknowledgedBytes: input.expectedSizeBytes,
        transferId: ids[3],
        status: 'verified',
        updatedAt: new Date().toISOString(),
      }),
      saveTransferCheckpoint: async () => {},
    },
  );
  await scheduler.enqueue(input);
  await waitFor(() => scheduler.snapshot().active === 0);
  assert.equal(observedTransferId, ids[3]);
  assert.equal(uploads, 0);
});

test('failed recovery checkpoint starts a new immutable transfer attempt', async () => {
  const input = task('a', 1);
  const observed = [];
  const checkpoints = [
    {
      schemaVersion: 1,
      sessionId: input.sessionId,
      batchId: input.batchId,
      fileId: input.fileId,
      generation: input.generation,
      sourceRelativePath: input.sourceRelativePath,
      expectedSizeBytes: input.expectedSizeBytes,
      expectedChecksumSha256: input.expectedChecksumSha256,
      acknowledgedBytes: 0,
      transferId: ids[3],
      status: 'failed',
      updatedAt: new Date().toISOString(),
    },
  ];
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(taskValue, transferId) {
        observed.push(['status', transferId]);
        return response(taskValue, 'not_started');
      },
      async upload(taskValue, transferId) {
        observed.push(['upload', transferId]);
        return response(taskValue, 'verified');
      },
    },
    store(checkpoints),
    { createTransferId: () => ids[0] },
  );

  await scheduler.enqueue(input);
  await waitFor(() => scheduler.snapshot().active === 0);

  assert.deepEqual(observed, [
    ['status', ids[0]],
    ['upload', ids[0]],
  ]);
  assert.equal(checkpoints.at(-1)?.transferId, ids[0]);
  assert.equal(checkpoints.at(-1)?.status, 'verified');
});

test('synced status completes locally without loading or uploading the Blob', async () => {
  let loaded = 0;
  let uploaded = 0;
  const checkpoints = [];
  const input = {
    ...task('a', 1),
    loadBlob: async () => {
      loaded += 1;
      return new Blob(['0123456789'], { type: 'image/jpeg' });
    },
  };
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(taskValue) {
        return response(taskValue, 'synced');
      },
      async upload() {
        uploaded += 1;
      },
    },
    store(checkpoints),
    { createTransferId: () => ids[0] },
  );

  await scheduler.enqueue(input);
  await waitFor(() => scheduler.snapshot().active === 0);

  assert.equal(loaded, 0);
  assert.equal(uploaded, 0);
  assert.equal(checkpoints.at(-1)?.status, 'verified');
});

test('abort, quota, retry classification and jitter are fail-closed', async () => {
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(input) {
        return response(input, 'not_started');
      },
      async upload(_task, _id, _blob, signal) {
        await new Promise((resolve) =>
          signal.addEventListener('abort', resolve),
        );
        throw new DOMException('aborted', 'AbortError');
      },
    },
    store(),
    { createTransferId: () => ids[0], maxPendingBytes: 11 },
  );
  await scheduler.enqueue(task('a', 1));
  await settle();
  assert.equal(await scheduler.cancel(ids[2], 1), true);
  await waitFor(() => scheduler.snapshot().active === 0);

  const limited = new RemoteSelectionTransferScheduler(
    { status: async () => {}, upload: async () => {} },
    store(),
    { maxPendingBytes: 9 },
  );
  await assert.rejects(() => limited.enqueue(task('b', 1)), /byte budget/);
  assert.equal(
    isRetryableTransferError(
      new RemoteSelectionTransferHttpError(429, 'x', 'x'),
    ),
    true,
  );
  assert.equal(
    isRetryableTransferError(
      new RemoteSelectionTransferHttpError(413, 'x', 'x'),
    ),
    false,
  );
  assert.equal(
    retryDelayMs(1, 100, () => 0),
    75,
  );
  assert.equal(
    retryDelayMs(2, 100, () => 1),
    250,
  );
});

test('tombstone cancels every older generation and a cancelled checkpoint cannot restart', async () => {
  const checkpoints = [];
  const checkpointStore = store(checkpoints);
  const scheduler = new RemoteSelectionTransferScheduler(
    {
      async status(input) {
        return response(input, 'not_started');
      },
      async upload(_task, _id, _blob, signal) {
        await new Promise((resolve) =>
          signal.addEventListener('abort', resolve),
        );
        throw new DOMException('aborted', 'AbortError');
      },
    },
    checkpointStore,
    { createTransferId: () => ids[0], maxConcurrency: 2 },
  );
  await scheduler.enqueue(task('a', 1));
  await scheduler.enqueue({ ...task('a', 2), generation: 2 });
  await settle();

  assert.equal(await scheduler.cancelOlderGenerations(ids[2], 3), 2);
  await waitFor(() => scheduler.snapshot().active === 0);
  assert.equal(
    checkpoints.filter((checkpoint) => checkpoint.status === 'cancelled')
      .length,
    2,
  );

  const restored = new RemoteSelectionTransferScheduler(
    { status: async () => {}, upload: async () => {} },
    checkpointStore,
    { createTransferId: () => ids[1] },
  );
  assert.equal(await restored.enqueue(task('a', 1)), false);
  assert.deepEqual(restored.snapshot(), {
    active: 0,
    queued: 0,
    pendingBytes: 0,
  });
});

test('500-file concurrency sweep remains bounded without retaining Blob payloads', async () => {
  for (const concurrency of [1, 2, 4]) {
    let active = 0;
    let peak = 0;
    let completed = 0;
    const scheduler = new RemoteSelectionTransferScheduler(
      {
        async status(input) {
          return response(input, 'not_started');
        },
        async upload(input) {
          active += 1;
          peak = Math.max(peak, active);
          await Promise.resolve();
          active -= 1;
          completed += 1;
          return response(input, 'verified');
        },
      },
      store(),
      {
        createTransferId: () => crypto.randomUUID(),
        maxConcurrency: concurrency,
        maxPendingBytes: 10_000,
      },
    );
    for (let index = 0; index < 500; index += 1) {
      await scheduler.enqueue({
        ...task(`perf-${index}`, index),
        fileId: crypto.randomUUID(),
      });
    }
    await waitFor(() => completed === 500, 2_000);
    assert.ok(peak <= concurrency);
    assert.deepEqual(scheduler.snapshot(), {
      active: 0,
      pendingBytes: 0,
      queued: 0,
    });
  }
});

function task(label, priority) {
  return {
    sessionId: ids[0],
    batchId: ids[1],
    fileId: label === 'a' ? ids[2] : crypto.randomUUID(),
    generation: 1,
    sourceRelativePath: `${label}.jpg`,
    expectedSizeBytes: 10,
    expectedLastModifiedMs: 123,
    expectedChecksumSha256: 'a'.repeat(64),
    priority,
    loadBlob: async () => new Blob(['0123456789'], { type: 'image/jpeg' }),
  };
}

function response(input, status) {
  const finished = status === 'verified' || status === 'synced';
  return {
    transferId: status === 'not_started' ? null : ids[3],
    batchId: input.batchId,
    fileId: input.fileId,
    generation: input.generation,
    attempt: status === 'not_started' ? 0 : 1,
    declaredBytes: input.expectedSizeBytes,
    receivedBytes: finished ? input.expectedSizeBytes : 0,
    status,
    declaredChecksumSha256: input.expectedChecksumSha256,
    verifiedChecksumSha256: finished ? input.expectedChecksumSha256 : null,
  };
}

function sequenceIds() {
  let index = 0;
  return () => ids[index++] ?? crypto.randomUUID();
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
}

function store(checkpoints = []) {
  return {
    loadTransferCheckpoint: async (sessionId, batchId, fileId, generation) =>
      checkpoints.findLast(
        (value) =>
          value.sessionId === sessionId &&
          value.batchId === batchId &&
          value.fileId === fileId &&
          value.generation === generation,
      ) ?? null,
    saveTransferCheckpoint: async (value) => checkpoints.push(value),
  };
}

async function waitFor(predicate, attempts = 100) {
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    if (predicate()) return;
    await settle();
  }
  assert.fail('condition was not reached');
}
