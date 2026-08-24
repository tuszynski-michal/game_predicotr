import assert from 'node:assert/strict';
import test from 'node:test';

import { IDBFactory, IDBKeyRange } from 'fake-indexeddb';
import { canonicalRemoteChecksumSha256 } from '@game-predictor/manual-image-selection-core';

import { RemoteSelectionIndexedDbStore } from '../src/features/manual-selection/remote-selection-store.ts';
import {
  WebkitDirectoryRemoteSourceAdapter,
  createRemoteSourceItemRecords,
} from '../src/features/manual-selection/remote-source-adapter.ts';
import {
  FetchRemoteSelectionControlTransport,
  nextRemoteSelectionPollDelay,
  RemoteSelectionControlApiError,
  RemoteSelectionOutboxSynchronizer,
  RemoteSelectionSyncCoordinator,
} from '../src/features/manual-selection/remote-selection-sync.ts';
import { RemoteSelectionInteractionQueue } from '../src/features/manual-selection/remote-selection-interaction-queue.ts';

const sessionId = '10000000-0000-4000-8000-000000000001';
const batchId = '20000000-0000-4000-8000-000000000002';
const clientInstanceId = '30000000-0000-4000-8000-000000000003';

const emptyQueueStatus = {
  pendingOperationCount: 0,
  uploadingTransferCount: 0,
  pendingTransferBytes: 0,
  materializingActionCount: 0,
  pendingHostActionCount: 0,
  syncedFileCount: 0,
  conflictFileCount: 0,
  recoveryFindings: [],
};

test('delta polling backs off while idle and stays responsive for pending work', () => {
  assert.equal(
    nextRemoteSelectionPollDelay({ idlePolls: 0, online: true, pending: true }),
    1_000,
  );
  assert.deepEqual(
    [0, 1, 2, 3, 10].map((idlePolls) =>
      nextRemoteSelectionPollDelay({ idlePolls, online: true, pending: false }),
    ),
    [2_000, 4_000, 8_000, 15_000, 15_000],
  );
  assert.equal(
    nextRemoteSelectionPollDelay({
      idlePolls: 0,
      online: false,
      pending: true,
    }),
    15_000,
  );
});

test('coalesced sync reruns after a request arrives during an active pass', async () => {
  const coordinator = new RemoteSelectionSyncCoordinator();
  let releaseFirst;
  const firstBlocked = new Promise((resolve) => {
    releaseFirst = resolve;
  });
  const calls = [];
  const first = coordinator.run(async () => {
    calls.push('first');
    await firstBlocked;
  });
  const second = coordinator.run(async () => {
    calls.push('second');
  });

  releaseFirst();
  await Promise.all([first, second]);

  assert.deepEqual(calls, ['first', 'second']);
});

test('interaction queue preserves four rapid decisions in request order', async () => {
  const queue = new RemoteSelectionInteractionQueue();
  const persisted = [];
  const requests = Array.from({ length: 4 }, (_, index) =>
    queue.enqueue(async () => {
      await Promise.resolve();
      persisted.push(index + 1);
    }),
  );

  await Promise.all(requests);
  await queue.idle();

  assert.deepEqual(persisted, [1, 2, 3, 4]);
});

async function fixture() {
  const factory = new IDBFactory();
  const store = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const file = new File(['jpeg'], '1.jpg', {
    lastModified: 1_700_000_000_000,
    type: 'image/jpeg',
  });
  Object.defineProperty(file, 'webkitRelativePath', {
    value: 'batch/1.jpg',
  });
  const indexed = await new WebkitDirectoryRemoteSourceAdapter([file]).index();
  const sourceItems = createRemoteSourceItemRecords(
    sessionId,
    batchId,
    indexed.manifest,
    () => '40000000-0000-4000-8000-000000000004',
  );
  const now = '2026-08-24T00:00:00.000Z';
  await store.saveIndexedSource({
    session: {
      schemaVersion: 1,
      activeBatchId: batchId,
      permissionState: 'unsupported',
      persistenceGranted: false,
      sessionId,
      sourceDirectoryName: indexed.sourceDirectoryName,
      sourceHandle: null,
      sourceKind: indexed.manifest.sourceKind,
      sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
      updatedAt: now,
    },
    batch: {
      schemaVersion: 1,
      batchId,
      cursorIndex: 0,
      direction: 'ascending',
      fileCount: 1,
      firstLayout: 1,
      sessionId,
      sourceDirectoryName: indexed.sourceDirectoryName,
      sourceKind: indexed.manifest.sourceKind,
      sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
      totalBytes: indexed.manifest.totalBytes,
      updatedAt: now,
    },
    sourceItems,
  });
  return { factory, sourceItem: sourceItems[0], store };
}

function command(sequence, sourceItem) {
  return {
    schemaVersion: 'remote-manual-selection-operation-v1',
    operationId: `50000000-0000-4000-8000-${String(sequence).padStart(12, '0')}`,
    sessionId,
    batchId,
    clientInstanceId,
    clientSequence: sequence,
    expectedServerRevision: sequence - 1,
    operationType: 'select',
    selectionGeneration: sequence,
    rangeStart: sequence * 9 - 8,
    rangeEnd: sequence * 9,
    recordedAt: '2026-08-24T00:00:00.000Z',
    fileId: sourceItem.fileId,
    imagePath: sourceItem.relativePath,
    sourceIndex: sourceItem.ordinal,
    imageChecksumSha256: 'a'.repeat(64),
    outputName: `seq_${sequence * 9 - 8}-${sequence * 9}.jpg`,
    visibleMilliseconds: 400,
    decoded: true,
    targetOperationId: null,
  };
}

function fileState(sourceItem, revision = 1) {
  return {
    batchId,
    desiredSelected: true,
    fileId: sourceItem.fileId,
    hostChecksumSha256: null,
    lastServerRevision: revision,
    outputName: 'seq_1-9.jpg',
    rangeEnd: 9,
    rangeStart: 1,
    relativePath: sourceItem.relativePath,
    selectionGeneration: 1,
    sessionId,
    sourceIndex: sourceItem.ordinal,
    status: 'selection_queued',
  };
}

async function outcome(commandValue, sourceItem, exactRetry) {
  return {
    batch: {
      batchId,
      lastClientSequence: 1,
      serverRevision: 1,
    },
    exactRetry,
    file: { ...fileState(sourceItem), lastServerRevision: null },
    operation: {
      appliedServerRevision: 1,
      commandChecksumSha256: await canonicalRemoteChecksumSha256(commandValue),
      operationId: commandValue.operationId,
      outcomeCode: 'applied',
      status: 'applied',
    },
  };
}

test('lost response survives refresh and exact replay removes only confirmed opId', async () => {
  const { factory, sourceItem, store } = await fixture();
  const operation = command(1, sourceItem);
  await store.appendOutboxOperation(operation);
  let applied = false;
  const transport = {
    async applyOperation(value) {
      if (!applied) {
        applied = true;
        throw new TypeError('connection lost after server commit');
      }
      return outcome(value, sourceItem, true);
    },
    async getStateDelta() {
      return {
        batch: {
          batchId,
          lastClientSequence: 1,
          serverRevision: 1,
          status: 'active',
        },
        files: [fileState(sourceItem)],
        hasMore: false,
        lastHeartbeatAt: null,
        nextRevision: 1,
        queue: emptyQueueStatus,
      };
    },
  };

  const interrupted = await new RemoteSelectionOutboxSynchronizer(
    store,
    transport,
  ).drain(sessionId, batchId, clientInstanceId);
  assert.equal(interrupted.confirmedCount, 0);
  assert.equal(interrupted.pendingCount, 1);

  const restoredStore = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const resumed = await new RemoteSelectionOutboxSynchronizer(
    restoredStore,
    transport,
  ).drain(sessionId, batchId, clientInstanceId);
  assert.equal(resumed.confirmedCount, 1);
  assert.equal(resumed.pendingCount, 0);
  assert.equal(
    await restoredStore.countPendingOperations(sessionId, batchId),
    0,
  );
  const persisted = await restoredStore.listSourceItemsPage(sessionId, batchId);
  assert.equal(persisted[0].desiredSelected, true);
  assert.equal(persisted[0].selectionGeneration, 1);
});

test('controlled conflict reconciles canonical delta but retains exact outbox record', async () => {
  const { sourceItem, store } = await fixture();
  const operation = command(1, sourceItem);
  await store.appendOutboxOperation(operation);
  const transport = {
    async applyOperation() {
      throw new RemoteSelectionControlApiError(
        409,
        'REMOTE_SELECTION_REVISION_CONFLICT',
        'stale',
      );
    },
    async getStateDelta() {
      return {
        batch: {
          batchId,
          lastClientSequence: 1,
          serverRevision: 1,
          status: 'active',
        },
        files: [fileState(sourceItem)],
        hasMore: false,
        lastHeartbeatAt: null,
        nextRevision: 1,
        queue: emptyQueueStatus,
      };
    },
  };
  const result = await new RemoteSelectionOutboxSynchronizer(
    store,
    transport,
  ).drain(sessionId, batchId, clientInstanceId);

  assert.equal(result.conflictOperationId, operation.operationId);
  assert.equal(result.conflictCode, 'REMOTE_SELECTION_REVISION_CONFLICT');
  assert.equal(result.pendingCount, 1);
  const pending = await store.listOutboxPage(sessionId, batchId);
  assert.equal(pending[0].state, 'conflict');
  assert.equal(pending[0].operationId, operation.operationId);
  const client = await store.loadClientInstance(
    sessionId,
    batchId,
    clientInstanceId,
  );
  assert.equal(client.lastKnownServerRevision, 1);
});

test('mismatched confirmation never acknowledges the local operation', async () => {
  const { sourceItem, store } = await fixture();
  const operation = command(1, sourceItem);
  await store.appendOutboxOperation(operation);
  const transport = {
    async applyOperation(value) {
      const response = await outcome(value, sourceItem, false);
      return {
        ...response,
        operation: {
          ...response.operation,
          operationId: '90000000-0000-4000-8000-000000000009',
        },
      };
    },
    async getStateDelta() {
      throw new Error('not needed');
    },
  };
  const result = await new RemoteSelectionOutboxSynchronizer(
    store,
    transport,
  ).drain(sessionId, batchId, clientInstanceId);

  assert.equal(result.pendingCount, 1);
  assert.equal(result.conflictCode, 'REMOTE_SELECTION_CONFIRMATION_MISMATCH');
  assert.equal(await store.countPendingOperations(sessionId, batchId), 1);
});

test('malformed revision outcome never acknowledges the local operation', async () => {
  const { sourceItem, store } = await fixture();
  const operation = command(1, sourceItem);
  await store.appendOutboxOperation(operation);
  const transport = {
    async applyOperation(value) {
      const response = await outcome(value, sourceItem, false);
      return {
        ...response,
        operation: {
          ...response.operation,
          appliedServerRevision: response.batch.serverRevision + 1,
        },
      };
    },
    async getStateDelta() {
      throw new Error('not needed');
    },
  };
  const result = await new RemoteSelectionOutboxSynchronizer(
    store,
    transport,
  ).drain(sessionId, batchId, clientInstanceId);

  assert.equal(result.pendingCount, 1);
  assert.equal(result.conflictCode, 'REMOTE_SELECTION_CONFIRMATION_MISMATCH');
  assert.equal(await store.countPendingOperations(sessionId, batchId), 1);
});

test('source bootstrap sends bounded ordered pages and activates only the last page', async () => {
  const requests = [];
  const transport = new FetchRemoteSelectionControlTransport(
    clientInstanceId,
    async (path, init) => {
      const body = JSON.parse(init.body);
      requests.push({ body, path: String(path) });
      return Response.json({
        acceptedFileIds: body.items.map((item) => item.fileId),
        batch: {
          batchId,
          status: body.complete ? 'active' : 'indexing',
        },
        createdCount: body.items.length,
        totalFileCount: requests.reduce(
          (total, request) => total + request.body.items.length,
          0,
        ),
      });
    },
  );
  const items = Array.from({ length: 5 }, (_, ordinal) => ({
    schemaVersion: 1,
    batchId,
    fileId: `40000000-0000-4000-8000-${String(ordinal).padStart(12, '0')}`,
    lastModifiedMs: ordinal,
    mimeType: 'image/jpeg',
    name: `${ordinal}.jpg`,
    ordinal,
    relativePath: `${ordinal}.jpg`,
    sessionId,
    sizeBytes: ordinal + 1,
  }));

  await transport.registerCompleteSourceManifest(
    sessionId,
    batchId,
    'directory_handle',
    items,
    2,
  );

  assert.deepEqual(
    requests.map((request) => request.body.items.length),
    [2, 2, 1],
  );
  assert.deepEqual(
    requests.map((request) => request.body.complete),
    [false, false, true],
  );
  assert.ok(
    requests.every((request) =>
      request.path.endsWith(`/batches/${batchId}/source-items`),
    ),
  );
});

test('control transport invokes browser fetch with the global receiver', async () => {
  let receiverIsGlobalThis = false;
  const transport = new FetchRemoteSelectionControlTransport(
    clientInstanceId,
    function fetchWithBrowserBrand() {
      receiverIsGlobalThis = this === globalThis;
      return Promise.resolve(
        Response.json({
          collectionId: '50000000-0000-4000-8000-000000000000',
          created: true,
        }),
      );
    },
  );

  await transport.createCollection({
    collectionId: '50000000-0000-4000-8000-000000000000',
    name: 'Stage 2',
    sessionId,
  });

  assert.equal(receiverIsGlobalThis, true);
});

test('finalization preview and command use exact batch scope and revision', async () => {
  const requests = [];
  const transport = new FetchRemoteSelectionControlTransport(
    clientInstanceId,
    async (path, init) => {
      requests.push({
        body: init.body === undefined ? null : JSON.parse(init.body),
        client: new Headers(init.headers).get('X-Remote-Selection-Client'),
        method: init.method,
        path: String(path),
      });
      return Response.json(
        init.method === 'GET'
          ? {
              batchId,
              blockers: [],
              operationCount: 2,
              ready: true,
              selectedFileCount: 1,
              serverRevision: 7,
              status: 'active',
              syncedFileCount: 1,
              totalFileCount: 2,
            }
          : {
              batch: { batchId, serverRevision: 8, status: 'completed' },
              exactRetry: false,
              finalManifestChecksumSha256: 'f'.repeat(64),
              finalizedAt: '2026-08-24T16:00:00.000Z',
            },
      );
    },
  );

  const preview = await transport.finalizePreview(batchId);
  const finalized = await transport.finalizeBatch({
    batchId,
    expectedServerRevision: preview.serverRevision,
    sessionId,
  });

  assert.equal(preview.ready, true);
  assert.equal(finalized.batch.status, 'completed');
  assert.deepEqual(requests, [
    {
      body: null,
      client: clientInstanceId,
      method: 'GET',
      path: `/selection-api/api/v1/remote-manual-selections/batches/${batchId}/finalize-preview`,
    },
    {
      body: { expectedServerRevision: 7, sessionId },
      client: clientInstanceId,
      method: 'POST',
      path: `/selection-api/api/v1/remote-manual-selections/batches/${batchId}/finalize`,
    },
  ]);
});

test('completed server state survives a fresh IndexedDB store instance', async () => {
  const { factory, sourceItem, store } = await fixture();
  await store.appendOutboxOperation(command(1, sourceItem));
  await store.applyServerStateDelta({
    batchId,
    clientInstanceId,
    files: [],
    nextRevision: 0,
    sessionId,
    status: 'completed',
  });

  const restored = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const batch = await restored.loadBatch(sessionId, batchId);

  assert.equal(batch.status, 'completed');
  assert.equal(batch.serverRevision, 0);
});
