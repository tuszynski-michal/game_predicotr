import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildRemoteWorkspaceCommand,
  clampRemoteWorkspaceIndex,
  remoteOutputName,
  remoteWorkspaceItemStatus,
} from '../src/features/manual-selection/remote-selection-workspace-model.ts';

const item = {
  schemaVersion: 1,
  sessionId: 'session-1',
  batchId: 'batch-1',
  fileId: 'file-1',
  ordinal: 0,
  name: '1.jpg',
  relativePath: 'batch/1.jpg',
  sizeBytes: 100,
  lastModifiedMs: 1,
  mimeType: 'image/jpeg',
};

const decision = {
  action: 'accepted',
  operationId: 'operation-1',
  fileId: 'file-1',
  sourceIndex: 0,
  imagePath: 'batch/1.jpg',
  imageChecksumSha256: 'a'.repeat(64),
  outputName: 'seq_1-9.jpg',
  rangeStart: 1,
  rangeEnd: 9,
  selectionGeneration: 1,
};

test('keeps local, pending, confirmed, synced, and error states visibly distinct', () => {
  assert.equal(
    remoteWorkspaceItemStatus({ item, decisions: [decision], outbox: [] }).kind,
    'selected_local',
  );
  assert.equal(
    remoteWorkspaceItemStatus({
      item,
      decisions: [decision],
      outbox: [{ operationId: 'operation-1', state: 'pending' }],
    }).kind,
    'pending',
  );
  assert.equal(
    remoteWorkspaceItemStatus({
      item: {
        ...item,
        desiredSelected: true,
        serverStatus: 'selection_queued',
      },
      decisions: [decision],
      outbox: [],
    }).kind,
    'confirmed',
  );
  assert.equal(
    remoteWorkspaceItemStatus({
      item: { ...item, desiredSelected: true, serverStatus: 'synced' },
      decisions: [decision],
      outbox: [],
    }).kind,
    'synced',
  );
  assert.equal(
    remoteWorkspaceItemStatus({
      item,
      decisions: [decision],
      outbox: [{ operationId: 'operation-1', state: 'conflict' }],
    }).kind,
    'error',
  );
});

test('builds a scoped operation without an absolute host or source path', () => {
  const command = buildRemoteWorkspaceCommand({
    operationId: 'operation-1',
    sessionId: 'session-1',
    batchId: 'batch-1',
    clientInstanceId: 'client-1',
    clientSequence: 1,
    expectedServerRevision: 0,
    operationType: 'select',
    selectionGeneration: 1,
    rangeStart: 1,
    sourceIndex: 0,
    fileId: 'file-1',
    imagePath: 'batch/1.jpg',
    imageChecksumSha256: 'a'.repeat(64),
    outputName: remoteOutputName(1),
    visibleMilliseconds: 301.6,
    decoded: true,
  });
  assert.equal(command.rangeEnd, 9);
  assert.equal(command.outputName, 'seq_1-9.jpg');
  assert.equal(command.visibleMilliseconds, 302);
  assert.equal(command.imagePath, 'batch/1.jpg');
  assert.throws(() =>
    buildRemoteWorkspaceCommand({
      ...command,
      operationType: 'select',
      imagePath: 'C:/private/1.jpg',
    }),
  );
  assert.equal(clampRemoteWorkspaceIndex(10, -20, 15), 0);
  assert.equal(clampRemoteWorkspaceIndex(10, 20, 15), 14);
});
