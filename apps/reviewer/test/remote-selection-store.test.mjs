import assert from 'node:assert/strict';
import test from 'node:test';

import { IDBFactory, IDBKeyRange } from 'fake-indexeddb';

import {
  REMOTE_SELECTION_DATABASE_NAME,
  REMOTE_SELECTION_DATABASE_STORES,
  REMOTE_SELECTION_DATABASE_VERSION,
  RemoteSelectionIndexedDbStore,
  RemoteSelectionStoreError,
  remoteSelectionWorkspaceState,
  requestBestEffortPersistentStorage,
  restartRemoteSelectionLocalBatch,
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

test('finds a previously indexed source without making it the active batch first', async () => {
  const { store } = await fixture();
  const active = await store.loadBatch('session-1', 'batch-1');
  const activeSession = await store.loadSession('session-1');
  const source = new File(['other'], 'other.jpg', {
    lastModified: 1_700_000_001_000,
    type: 'image/jpeg',
  });
  Object.defineProperty(source, 'webkitRelativePath', {
    value: 'other-batch/other.jpg',
  });
  const indexed = await new WebkitDirectoryRemoteSourceAdapter([
    source,
  ]).index();
  const historical = {
    ...active,
    batchId: 'batch-historical',
    fileCount: indexed.manifest.fileCount,
    sourceDirectoryName: indexed.sourceDirectoryName,
    sourceKind: indexed.manifest.sourceKind,
    sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
    totalBytes: indexed.manifest.totalBytes,
    updatedAt: '2026-08-24T01:00:00.000Z',
  };
  await store.saveIndexedSource({
    batch: historical,
    session: {
      ...activeSession,
      activeBatchId: historical.batchId,
      sourceDirectoryName: indexed.sourceDirectoryName,
      sourceKind: indexed.manifest.sourceKind,
      sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
    },
    sourceItems: createRemoteSourceItemRecords(
      'session-1',
      historical.batchId,
      indexed.manifest,
    ),
  });
  await store.saveSession(activeSession);

  const found = await store.findBatchBySourceManifest({
    sessionId: 'session-1',
    sourceDirectoryName: indexed.sourceDirectoryName,
    sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
  });
  assert.equal(found?.batchId, 'batch-historical');
  assert.equal(
    (await store.loadSourceManifest('session-1', found.batchId))
      .manifestChecksumSha256,
    indexed.manifest.manifestChecksumSha256,
  );
  assert.equal(
    await store.findBatchBySourceManifest({
      sessionId: 'session-1',
      sourceDirectoryName: active.sourceDirectoryName,
      sourceManifestChecksumSha256: 'f'.repeat(64),
    }),
    null,
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

test('rebases all unsent operations in order after another tab consumed the client clock', async () => {
  const { store } = await fixture();
  await store.appendOutboxOperation(command(1));
  await store.appendOutboxOperation(command(2));
  await store.markOutboxOperation(
    'session-1',
    'batch-1',
    'operation-1',
    'conflict',
    'REMOTE_SELECTION_CLIENT_SEQUENCE_REPLAY',
  );

  assert.equal(
    await store.rebaseOutboxAfterClientSequenceReplay({
      batchId: 'batch-1',
      clientInstanceId: 'client-1',
      serverLastClientSequence: 14,
      serverRevision: 22,
      sessionId: 'session-1',
    }),
    2,
  );

  const rebased = await store.listOutboxPage('session-1', 'batch-1');
  assert.deepEqual(
    rebased.map((record) => ({
      expectedServerRevision: record.command.expectedServerRevision,
      operationId: record.operationId,
      sequence: record.clientSequence,
      state: record.state,
    })),
    [
      {
        expectedServerRevision: 22,
        operationId: 'operation-1',
        sequence: 15,
        state: 'pending',
      },
      {
        expectedServerRevision: 23,
        operationId: 'operation-2',
        sequence: 16,
        state: 'pending',
      },
    ],
  );
  const client = await store.loadClientInstance(
    'session-1',
    'batch-1',
    'client-1',
  );
  assert.equal(client.lastClientSequence, 16);
  assert.equal(client.lastKnownServerRevision, 22);
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

test('persists an accepted workspace decision and its outbox command atomically across refresh', async () => {
  const { factory, store } = await fixture(3);
  const source = await store.loadSourceItem('session-1', 'batch-1', 0);
  const select = command(1, {
    operationType: 'select',
    selectionGeneration: 1,
    sourceIndex: 0,
    fileId: source.fileId,
    imagePath: source.relativePath,
    imageChecksumSha256: 'a'.repeat(64),
    outputName: 'seq_1-9.jpg',
    decoded: true,
    visibleMilliseconds: 350,
  });
  const decision = {
    action: 'accepted',
    operationId: select.operationId,
    fileId: select.fileId,
    sourceIndex: 0,
    imagePath: select.imagePath,
    imageChecksumSha256: select.imageChecksumSha256,
    outputName: select.outputName,
    rangeStart: 1,
    rangeEnd: 9,
    selectionGeneration: 1,
  };

  await store.appendWorkspaceDecision({
    command: select,
    decision,
    nextCursorIndex: 1,
  });

  const afterRefresh = new RemoteSelectionIndexedDbStore(factory, IDBKeyRange);
  const restored = await afterRefresh.restore('session-1');
  assert.deepEqual(remoteSelectionWorkspaceState(restored.batch), {
    currentIndex: 1,
    decisions: [decision],
    navigationStep: 1,
    nextRangeStart: 10,
  });
  assert.deepEqual(
    restored.pendingOperations.map((record) => record.operationId),
    [select.operationId],
  );
});

test('undoes skip locally and accepted selection through an exact durable tombstone', async () => {
  const { store } = await fixture(3);
  const skip = command(1, { sourceIndex: 0, selectionGeneration: 0 });
  await store.appendWorkspaceDecision({
    command: skip,
    decision: {
      action: 'skipped',
      operationId: skip.operationId,
      fileId: null,
      sourceIndex: 0,
      imagePath: null,
      imageChecksumSha256: null,
      outputName: null,
      rangeStart: 1,
      rangeEnd: 9,
      selectionGeneration: 0,
    },
    nextCursorIndex: 0,
  });
  await store.undoLastWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    command: null,
  });
  assert.equal((await store.listOutboxPage('session-1', 'batch-1')).length, 1);
  assert.equal(
    remoteSelectionWorkspaceState(await store.loadBatch('session-1', 'batch-1'))
      .nextRangeStart,
    1,
  );

  const source = await store.loadSourceItem('session-1', 'batch-1', 0);
  const select = command(2, {
    expectedServerRevision: 1,
    operationType: 'select',
    rangeStart: 1,
    rangeEnd: 9,
    selectionGeneration: 1,
    sourceIndex: 0,
    fileId: source.fileId,
    imagePath: source.relativePath,
    imageChecksumSha256: 'b'.repeat(64),
    outputName: 'seq_1-9.jpg',
    decoded: true,
  });
  await store.appendWorkspaceDecision({
    command: select,
    decision: {
      action: 'accepted',
      operationId: select.operationId,
      fileId: select.fileId,
      sourceIndex: 0,
      imagePath: select.imagePath,
      imageChecksumSha256: select.imageChecksumSha256,
      outputName: select.outputName,
      rangeStart: 1,
      rangeEnd: 9,
      selectionGeneration: 1,
    },
    nextCursorIndex: 1,
  });
  const undo = command(3, {
    expectedServerRevision: 2,
    operationType: 'undo',
    rangeStart: 1,
    rangeEnd: 9,
    selectionGeneration: 2,
    sourceIndex: 0,
    fileId: source.fileId,
    imagePath: source.relativePath,
    outputName: 'seq_1-9.jpg',
    targetOperationId: select.operationId,
  });
  await store.undoLastWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    command: undo,
  });
  const outbox = await store.listOutboxPage('session-1', 'batch-1');
  assert.deepEqual(
    outbox.map((record) => record.command.operationType),
    ['skip', 'select', 'undo'],
  );
  assert.equal(outbox.at(-1).command.targetOperationId, select.operationId);
  assert.equal(
    remoteSelectionWorkspaceState(await store.loadBatch('session-1', 'batch-1'))
      .currentIndex,
    0,
  );
});

test('operator-local decisions persist without creating a host outbox', async () => {
  const { store } = await fixture(3);
  const source = await store.loadSourceItem('session-1', 'batch-1', 0);
  const decision = {
    action: 'accepted',
    operationId: 'operator-local-1',
    fileId: source.fileId,
    sourceIndex: 0,
    imagePath: source.relativePath,
    imageChecksumSha256: 'c'.repeat(64),
    outputName: 'seq_1-9.jpg',
    rangeStart: 1,
    rangeEnd: 9,
    selectionGeneration: 1,
  };

  const selected = await store.appendLocalWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    decision,
    nextCursorIndex: 1,
  });
  assert.deepEqual(remoteSelectionWorkspaceState(selected), {
    currentIndex: 1,
    decisions: [decision],
    navigationStep: 1,
    nextRangeStart: 10,
  });
  assert.equal((await store.listOutboxPage('session-1', 'batch-1')).length, 0);

  const undone = await store.undoLastLocalWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    expectedOperationId: decision.operationId,
  });
  assert.equal(remoteSelectionWorkspaceState(undone).currentIndex, 0);
  assert.equal(remoteSelectionWorkspaceState(undone).nextRangeStart, 1);
  assert.equal((await store.listOutboxPage('session-1', 'batch-1')).length, 0);
});

test('resumes an edited descending range from its last decision, not decision count', async () => {
  const { store } = await fixture(4);
  const existing = await store.loadBatch('session-1', 'batch-1');
  await store.saveBatch({
    ...existing,
    cursorIndex: 3,
    decisions: [
      {
        action: 'accepted',
        fileId: 'first-file',
        imageChecksumSha256: 'a'.repeat(64),
        imagePath: '4.jpg',
        operationId: 'first-decision',
        outputName: 'seq_28-36.jpg',
        rangeEnd: 36,
        rangeStart: 28,
        selectionGeneration: 1,
        sourceIndex: 3,
      },
    ],
    direction: 'descending',
    firstLayout: 28,
    nextRangeStart: undefined,
  });

  const restored = await store.loadBatch('session-1', 'batch-1');
  assert.equal(remoteSelectionWorkspaceState(restored).nextRangeStart, 19);

  const next = await store.appendLocalWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    decision: {
      action: 'skipped',
      fileId: null,
      imageChecksumSha256: null,
      imagePath: null,
      operationId: 'second-decision',
      outputName: null,
      rangeEnd: 27,
      rangeStart: 19,
      selectionGeneration: 2,
      sourceIndex: 3,
    },
    nextCursorIndex: 2,
  });

  assert.equal(remoteSelectionWorkspaceState(next).nextRangeStart, 10);
});

test('repairs a legacy descending batch to the next natural source item', () => {
  const workspace = remoteSelectionWorkspaceState({
    schemaVersion: 1,
    sessionId: 'session-1',
    batchId: 'batch-1',
    sourceDirectoryName: 'source',
    sourceKind: 'directory_picker',
    sourceManifestChecksumSha256: 'a'.repeat(64),
    firstLayout: 453_744,
    direction: 'descending',
    cursorIndex: 2_891,
    fileCount: 14_418,
    totalBytes: 1,
    decisions: [
      {
        action: 'accepted',
        operationId: 'operation-1',
        fileId: 'file-1',
        sourceIndex: 11_525,
        imagePath: '11526.jpg',
        imageChecksumSha256: 'b'.repeat(64),
        outputName: 'seq_441073-441081.jpg',
        rangeStart: 441_073,
        rangeEnd: 441_081,
        selectionGeneration: 1,
      },
    ],
    updatedAt: '2026-08-28T10:00:00.000Z',
  });

  assert.equal(workspace.currentIndex, 11_526);
  assert.equal(workspace.nextRangeStart, 441_064);
});

test('restarts an operator-local batch at the first source image and first range', async () => {
  const { store } = await fixture(3);
  const source = await store.loadSourceItem('session-1', 'batch-1', 0);
  const selected = await store.appendLocalWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    decision: {
      action: 'accepted',
      operationId: 'operator-local-reset',
      fileId: source.fileId,
      sourceIndex: 0,
      imagePath: source.relativePath,
      imageChecksumSha256: 'c'.repeat(64),
      outputName: 'seq_1-9.jpg',
      rangeStart: 1,
      rangeEnd: 9,
      selectionGeneration: 1,
    },
    nextCursorIndex: 1,
  });

  const ascending = restartRemoteSelectionLocalBatch(
    selected,
    '2026-08-24T01:00:00.000Z',
  );
  assert.deepEqual(remoteSelectionWorkspaceState(ascending), {
    currentIndex: 0,
    decisions: [],
    navigationStep: 1,
    nextRangeStart: 1,
  });
  assert.equal(ascending.hostRegistered, true);
  assert.equal(ascending.status, 'active');

  const descending = restartRemoteSelectionLocalBatch({
    ...selected,
    direction: 'descending',
  });
  assert.equal(descending.cursorIndex, 0);
  assert.equal(descending.nextRangeStart, 1);
  assert.deepEqual(descending.decisions, []);
});

test('missing local directories atomically reset progress and require strict source and output relink', async () => {
  const { store } = await fixture(3);
  const source = await store.loadSourceItem('session-1', 'batch-1', 0);
  await store.appendLocalWorkspaceDecision({
    sessionId: 'session-1',
    batchId: 'batch-1',
    decision: {
      action: 'accepted',
      operationId: 'operator-local-missing-directory',
      fileId: source.fileId,
      sourceIndex: 0,
      imagePath: source.relativePath,
      imageChecksumSha256: 'd'.repeat(64),
      outputName: 'seq_1-9.jpg',
      rangeStart: 1,
      rangeEnd: 9,
      selectionGeneration: 1,
    },
    nextCursorIndex: 1,
  });
  const session = await store.loadSession('session-1');
  await store.saveSession({
    ...session,
    sourceHandle: { kind: 'directory', name: 'batch' },
    permissionState: 'granted',
    outputDirectoryName: 'batch wybrane',
    outputHandle: { kind: 'directory', name: 'batch wybrane' },
    outputParentHandle: { kind: 'directory', name: 'parent' },
    outputParentPermissionState: 'granted',
    outputPermissionState: 'granted',
  });
  await store.saveBatch({
    ...(await store.loadBatch('session-1', 'batch-1')),
    hostRegistered: true,
    status: 'active',
  });
  const before = await store.restore('session-1');

  const relink = await store.resetLocalWorkspaceForDirectoryRelink({
    sessionId: 'session-1',
    batchId: 'batch-1',
    updatedAt: '2026-08-24T02:00:00.000Z',
  });
  const after = await store.restore('session-1');

  assert.deepEqual(remoteSelectionWorkspaceState(relink.batch), {
    currentIndex: 0,
    decisions: [],
    navigationStep: 1,
    nextRangeStart: 1,
  });
  assert.equal(relink.batch.hostRegistered, false);
  assert.equal(relink.batch.status, 'indexing');
  assert.equal(relink.session.sourceHandle, null);
  assert.equal(relink.session.outputHandle, null);
  assert.equal(relink.session.outputParentHandle, null);
  assert.equal(relink.session.outputDirectoryName, null);
  assert.equal(relink.session.permissionState, 'prompt');
  assert.equal(relink.session.outputPermissionState, 'prompt');
  assert.equal(relink.session.outputParentPermissionState, 'prompt');
  assert.equal(
    relink.session.sourceManifestChecksumSha256,
    before.session.sourceManifestChecksumSha256,
  );
  assert.deepEqual(
    after.sourceItems.map((item) => item.relativePath),
    before.sourceItems.map((item) => item.relativePath),
  );
  assert.equal(after.pendingOperationCount, 0);
});

test('loads a bounded seven-image preview window and predicts an operation clock', async () => {
  const { store } = await fixture(20);
  const window = await store.loadSourceItemsWindow(
    'session-1',
    'batch-1',
    10,
    20,
  );
  assert.deepEqual(
    window.map((item) => item.ordinal),
    [7, 8, 9, 10, 11, 12, 13],
  );
  await store.appendOutboxOperation(command(1));
  assert.deepEqual(
    await store.operationClock('session-1', 'batch-1', 'client-1'),
    {
      clientSequence: 2,
      expectedServerRevision: 1,
    },
  );
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
