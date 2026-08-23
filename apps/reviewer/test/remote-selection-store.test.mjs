import assert from 'node:assert/strict';
import test from 'node:test';

import { IDBFactory, IDBKeyRange } from 'fake-indexeddb';

import {
  REMOTE_SELECTION_DATABASE_NAME,
  REMOTE_SELECTION_DATABASE_STORES,
  REMOTE_SELECTION_DATABASE_VERSION,
  RemoteSelectionIndexedDbStore,
  RemoteSelectionStoreError,
  requestBestEffortPersistentStorage,
} from '../src/features/manual-selection/remote-selection-store.ts';
import {
  WebkitDirectoryRemoteSourceAdapter,
  createRemoteSourceItemRecords,
} from '../src/features/manual-selection/remote-source-adapter.ts';

function command(sequence, overrides = {}) {
  return {
    schemaVersion: 'remote-manual-selection-operation-v1',
    operationId: `operation-${sequence}`,
    sessionId: 'session-1',
    batchId: 'batch-1',
    clientInstanceId: 'client-1',
    clientSequence: sequence,
    expectedServerRevision: 0,
    operationType: 'skip',
    selectionGeneration: sequence,
    rangeStart: sequence * 9 - 8,
    rangeEnd: sequence * 9,
    recordedAt: '2026-08-24T00:00:00.000Z',
    fileId: null,
    imagePath: null,
    sourceIndex: null,
    imageChecksumSha256: null,
    outputName: null,
    visibleMilliseconds: 0,
    decoded: false,
    targetOperationId: null,
    ...overrides,
  };
}

async function fixture(fileCount = 3) {
  const factory = new IDBFactory();
  const store = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const files = Array.from(
    { length: fileCount },
    (_, index) =>
      new File(['x'], `${index + 1}.jpg`, {
        lastModified: 1_700_000_000_000 + index,
        type: 'image/jpeg',
      }),
  );
  for (const file of files) {
    Object.defineProperty(file, 'webkitRelativePath', {
      value: `batch/${file.name}`,
    });
  }
  const indexed = await new WebkitDirectoryRemoteSourceAdapter(files).index();
  const now = '2026-08-24T00:00:00.000Z';
  const session = {
    schemaVersion: 1,
    sessionId: 'session-1',
    activeBatchId: 'batch-1',
    sourceDirectoryName: indexed.sourceDirectoryName,
    sourceKind: indexed.manifest.sourceKind,
    sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
    sourceHandle: null,
    permissionState: 'unsupported',
    persistenceGranted: false,
    updatedAt: now,
  };
  const batch = {
    schemaVersion: 1,
    sessionId: 'session-1',
    batchId: 'batch-1',
    sourceDirectoryName: indexed.sourceDirectoryName,
    sourceKind: indexed.manifest.sourceKind,
    sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
    firstLayout: 1,
    direction: 'ascending',
    cursorIndex: 0,
    fileCount,
    totalBytes: indexed.manifest.totalBytes,
    updatedAt: now,
  };
  await store.saveIndexedSource({
    session,
    batch,
    sourceItems: createRemoteSourceItemRecords(
      session.sessionId,
      batch.batchId,
      indexed.manifest,
      () => crypto.randomUUID(),
    ),
  });
  return { factory, store };
}

test('creates the explicit remote IndexedDB v1 stores and indexes', async () => {
  const { factory } = await fixture();
  const database = await openDatabase(factory);
  try {
    assert.equal(database.version, REMOTE_SELECTION_DATABASE_VERSION);
    assert.deepEqual(
      [...database.objectStoreNames].toSorted(),
      [...Object.values(REMOTE_SELECTION_DATABASE_STORES)].toSorted(),
    );
    const transaction = database.transaction(
      REMOTE_SELECTION_DATABASE_STORES.outbox,
      'readonly',
    );
    assert.deepEqual(
      [
        ...transaction.objectStore(REMOTE_SELECTION_DATABASE_STORES.outbox)
          .indexNames,
      ],
      ['operationId'],
    );
  } finally {
    database.close();
  }
});

test('restores cursor and exact pending operation IDs after a new store instance', async () => {
  const { factory, store } = await fixture(1000);
  await store.updateCursor('session-1', 'batch-1', 731);
  await store.appendOutboxOperation(command(1));
  await store.appendOutboxOperation(command(2));

  const afterCrash = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const restored = await afterCrash.restore('session-1', 25);

  assert.equal(restored.batch.cursorIndex, 731);
  assert.equal(restored.sourceItems.length, 25);
  assert.equal(restored.pendingOperationCount, 2);
  assert.deepEqual(
    restored.pendingOperations.map((record) => record.operationId),
    ['operation-1', 'operation-2'],
  );
});

test('append is idempotent and ack removes only explicitly confirmed operation IDs', async () => {
  const { store } = await fixture();
  assert.equal((await store.appendOutboxOperation(command(1))).created, true);
  assert.equal((await store.appendOutboxOperation(command(1))).created, false);
  await store.appendOutboxOperation(command(2));
  await store.appendOutboxOperation(command(3));

  assert.equal(
    await store.acknowledgeOperations('session-1', 'batch-1', [
      'operation-2',
      'unknown-operation',
    ]),
    1,
  );
  assert.deepEqual(
    (await store.listOutboxPage('session-1', 'batch-1')).map(
      (record) => record.operationId,
    ),
    ['operation-1', 'operation-3'],
  );
  assert.equal(await store.countPendingOperations('session-1', 'batch-1'), 2);
});

test('rejects operation ID reuse with different content and sequence gaps', async () => {
  const { store } = await fixture();
  await store.appendOutboxOperation(command(1));
  await assert.rejects(
    store.appendOutboxOperation(command(2, { operationId: 'operation-1' })),
    (error) =>
      error instanceof RemoteSelectionStoreError &&
      error.code === 'REMOTE_SELECTION_OUTBOX_OPERATION_CONFLICT',
  );
  await assert.rejects(
    store.appendOutboxOperation(command(3)),
    (error) =>
      error instanceof RemoteSelectionStoreError &&
      error.code === 'REMOTE_SELECTION_OUTBOX_SEQUENCE_INVALID',
  );
});

test('handle loss never deletes source cursor or pending outbox state', async () => {
  const { store } = await fixture();
  await store.updateCursor('session-1', 'batch-1', 2);
  await store.appendOutboxOperation(command(1));
  const session = await store.loadSession('session-1');
  await store.saveSession({
    ...session,
    permissionState: 'denied',
    sourceHandle: null,
    updatedAt: '2026-08-24T00:01:00.000Z',
  });

  const restored = await store.restore('session-1');
  assert.equal(restored.session.permissionState, 'denied');
  assert.equal(restored.batch.cursorIndex, 2);
  assert.equal(restored.pendingOperationCount, 1);
});

test('never accepts persistent Blob data and requests storage persistence best effort', async () => {
  const { store } = await fixture();
  const session = await store.loadSession('session-1');
  await assert.rejects(
    store.saveSession({ ...session, sourceHandle: new Blob(['jpeg']) }),
    (error) =>
      error instanceof RemoteSelectionStoreError &&
      error.code === 'REMOTE_SELECTION_BLOB_PERSISTENCE_FORBIDDEN',
  );
  assert.deepEqual(
    await requestBestEffortPersistentStorage({ persist: async () => true }),
    { granted: true, supported: true },
  );
  assert.deepEqual(await requestBestEffortPersistentStorage(undefined), {
    granted: false,
    supported: false,
  });
});

test('rejects absolute source paths before they reach durable storage', async () => {
  const { store } = await fixture();
  await assert.rejects(
    store.appendOutboxOperation(
      command(1, {
        imagePath: 'C:/private/source.jpg',
        operationType: 'select',
      }),
    ),
    (error) =>
      error instanceof RemoteSelectionStoreError &&
      error.code === 'REMOTE_SELECTION_SOURCE_PATH_INVALID',
  );
  await assert.rejects(
    store.saveTransferCheckpoint({
      schemaVersion: 1,
      sessionId: 'session-1',
      batchId: 'batch-1',
      fileId: 'file-1',
      generation: 1,
      sourceRelativePath: '../outside.jpg',
      expectedSizeBytes: 100,
      expectedChecksumSha256: null,
      acknowledgedBytes: 0,
      updatedAt: '2026-08-24T00:00:00.000Z',
    }),
    (error) =>
      error instanceof RemoteSelectionStoreError &&
      error.code === 'REMOTE_SELECTION_SOURCE_PATH_INVALID',
  );
});

test('reads only a bounded page when 15000 outbox records exist', async () => {
  const { factory, store } = await fixture(1);
  const database = await openDatabase(factory);
  const transaction = database.transaction(
    REMOTE_SELECTION_DATABASE_STORES.outbox,
    'readwrite',
  );
  const outbox = transaction.objectStore(
    REMOTE_SELECTION_DATABASE_STORES.outbox,
  );
  for (let sequence = 1; sequence <= 15_000; sequence += 1) {
    outbox.put({
      schemaVersion: 1,
      sessionId: 'session-1',
      batchId: 'batch-1',
      clientInstanceId: 'client-1',
      clientSequence: sequence,
      operationId: `seeded-operation-${sequence}`,
      commandChecksumSha256: 'a'.repeat(64),
      command: command(sequence, {
        operationId: `seeded-operation-${sequence}`,
      }),
      state: 'pending',
      attemptCount: 0,
      lastErrorCode: null,
      queuedAt: '2026-08-24T00:00:00.000Z',
      updatedAt: '2026-08-24T00:00:00.000Z',
    });
  }
  await transactionDone(transaction);
  database.close();

  const page = await store.listOutboxPage('session-1', 'batch-1', 0, 100);
  assert.equal(page.length, 100);
  assert.equal(page[0].clientSequence, 1);
  assert.equal(page.at(-1).clientSequence, 100);
  assert.equal(
    await store.countPendingOperations('session-1', 'batch-1'),
    15_000,
  );
});

function openDatabase(factory) {
  return new Promise((resolve, reject) => {
    const request = factory.open(
      REMOTE_SELECTION_DATABASE_NAME,
      REMOTE_SELECTION_DATABASE_VERSION,
    );
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}
