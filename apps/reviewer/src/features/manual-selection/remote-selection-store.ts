'use client';

import {
  MANUAL_IMAGE_NAVIGATION_STEPS,
  buildRemoteSourceManifestV1,
  canonicalRemoteChecksumSha256,
  normalizeRemoteSourcePath,
  type RemoteManualSelectionDirection,
  type RemoteManualSelectionOperationCommandV1,
  type RemoteSourceKind,
  type RemoteSourceManifestEntryV1,
  type RemoteSourceManifestV1,
} from '@game-predictor/manual-image-selection-core';

export const REMOTE_SELECTION_DATABASE_NAME =
  'game-predictor-remote-manual-selection';
export const REMOTE_SELECTION_DATABASE_VERSION = 1;
export const REMOTE_SELECTION_DATABASE_STORES = Object.freeze({
  batches: 'batches',
  clientInstances: 'clientInstances',
  outbox: 'outbox',
  sessions: 'sessions',
  sourceItems: 'sourceItems',
  transferCheckpoints: 'transferCheckpoints',
});

const MAX_PAGE_SIZE = 500;

export type RemoteSourcePermissionState =
  'granted' | 'prompt' | 'denied' | 'unsupported' | 'error';

export interface RemoteSelectionLocalSessionRecord {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly activeBatchId: string | null;
  readonly sourceDirectoryName: string | null;
  readonly sourceKind: RemoteSourceKind | null;
  readonly sourceManifestChecksumSha256: string | null;
  readonly sourceHandle: FileSystemDirectoryHandle | null;
  readonly outputDirectoryName?: string | null;
  readonly outputHandle?: FileSystemDirectoryHandle | null;
  readonly outputParentHandle?: FileSystemDirectoryHandle | null;
  readonly outputParentPermissionState?: RemoteSourcePermissionState;
  readonly outputPermissionState?: RemoteSourcePermissionState;
  readonly permissionState: RemoteSourcePermissionState;
  readonly persistenceGranted: boolean | null;
  readonly updatedAt: string;
}

export interface RemoteSelectionLocalBatchRecord {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly batchId: string;
  readonly sourceDirectoryName: string;
  readonly sourceKind: RemoteSourceKind;
  readonly sourceManifestChecksumSha256: string;
  readonly firstLayout: number;
  readonly direction: RemoteManualSelectionDirection;
  readonly cursorIndex: number;
  readonly fileCount: number;
  readonly totalBytes: number;
  readonly collectionId?: string | null;
  readonly collectionName?: string | null;
  readonly batchName?: string | null;
  readonly hostRegistered?: boolean;
  readonly serverRevision?: number;
  readonly status?: 'indexing' | 'active' | 'finalizing' | 'completed';
  readonly nextRangeStart?: number;
  readonly navigationStep?: number;
  readonly decisions?: readonly RemoteSelectionWorkspaceDecision[];
  readonly updatedAt: string;
}

export interface RemoteSelectionWorkspaceDecision {
  readonly action: 'accepted' | 'skipped';
  readonly operationId: string;
  readonly fileId: string | null;
  readonly sourceIndex: number;
  readonly imagePath: string | null;
  readonly imageChecksumSha256: string | null;
  readonly outputName: string | null;
  readonly rangeStart: number;
  readonly rangeEnd: number;
  readonly selectionGeneration: number;
}

export interface RemoteSelectionWorkspaceState {
  readonly currentIndex: number;
  readonly decisions: readonly RemoteSelectionWorkspaceDecision[];
  readonly navigationStep: number;
  readonly nextRangeStart: number;
}

export interface RemoteSelectionOperationClock {
  readonly clientSequence: number;
  readonly expectedServerRevision: number;
}

export interface RemoteSelectionSourceItemRecord extends RemoteSourceManifestEntryV1 {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly batchId: string;
  readonly fileId: string;
  readonly desiredSelected?: boolean;
  readonly selectionGeneration?: number;
  readonly serverStatus?: string;
  readonly rangeStart?: number | null;
  readonly rangeEnd?: number | null;
  readonly outputName?: string | null;
  readonly hostChecksumSha256?: string | null;
  readonly lastServerRevision?: number;
}

export interface RemoteSelectionServerFileState {
  readonly fileId: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly sourceIndex: number;
  readonly relativePath: string;
  readonly desiredSelected: boolean;
  readonly selectionGeneration: number;
  readonly status: string;
  readonly rangeStart: number | null;
  readonly rangeEnd: number | null;
  readonly outputName: string | null;
  readonly hostChecksumSha256: string | null;
  readonly lastServerRevision: number | null;
}

export type RemoteSelectionOutboxState = 'pending' | 'sending' | 'conflict';

export interface RemoteSelectionOutboxRecord {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly batchId: string;
  readonly clientInstanceId: string;
  readonly clientSequence: number;
  readonly operationId: string;
  readonly commandChecksumSha256: string;
  readonly command: RemoteManualSelectionOperationCommandV1;
  readonly state: RemoteSelectionOutboxState;
  readonly attemptCount: number;
  readonly lastErrorCode: string | null;
  readonly queuedAt: string;
  readonly updatedAt: string;
}

export interface RemoteSelectionTransferCheckpointRecord {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly batchId: string;
  readonly fileId: string;
  readonly generation: number;
  readonly sourceRelativePath: string;
  readonly expectedSizeBytes: number;
  readonly expectedChecksumSha256: string | null;
  readonly acknowledgedBytes: number;
  readonly transferId?: string;
  readonly status?:
    'queued' | 'uploading' | 'verified' | 'cancelled' | 'failed';
  readonly updatedAt: string;
}

export interface RemoteSelectionClientInstanceRecord {
  readonly schemaVersion: 1;
  readonly sessionId: string;
  readonly batchId: string;
  readonly clientInstanceId: string;
  readonly lastClientSequence: number;
  readonly lastKnownServerRevision: number;
  readonly updatedAt: string;
}

export interface RemoteSelectionRestoreSnapshot {
  readonly session: RemoteSelectionLocalSessionRecord | null;
  readonly batch: RemoteSelectionLocalBatchRecord | null;
  readonly sourceItems: readonly RemoteSelectionSourceItemRecord[];
  readonly pendingOperations: readonly RemoteSelectionOutboxRecord[];
  readonly pendingOperationCount: number;
}

export class RemoteSelectionStoreError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'RemoteSelectionStoreError';
    this.code = code;
  }
}

export function remoteSelectionWorkspaceState(
  batch: RemoteSelectionLocalBatchRecord,
): RemoteSelectionWorkspaceState {
  const decisions = batch.decisions ?? [];
  const navigationStep = MANUAL_IMAGE_NAVIGATION_STEPS.includes(
    batch.navigationStep as (typeof MANUAL_IMAGE_NAVIGATION_STEPS)[number],
  )
    ? (batch.navigationStep ?? 1)
    : 1;
  return {
    currentIndex: batch.cursorIndex,
    decisions,
    navigationStep,
    nextRangeStart:
      batch.nextRangeStart ?? batch.firstLayout + decisions.length * 9,
  };
}

export function restartRemoteSelectionLocalBatch(
  batch: RemoteSelectionLocalBatchRecord,
  updatedAt = new Date().toISOString(),
): RemoteSelectionLocalBatchRecord {
  const restarted: RemoteSelectionLocalBatchRecord = {
    ...batch,
    cursorIndex: batch.direction === 'ascending' ? 0 : batch.fileCount - 1,
    decisions: [],
    hostRegistered: true,
    nextRangeStart: batch.firstLayout,
    status: 'active',
    updatedAt,
  };
  validateWorkspaceBatch(restarted);
  return restarted;
}

export class RemoteSelectionIndexedDbStore {
  private readonly factory: IDBFactory | undefined;
  private readonly keyRange: typeof IDBKeyRange | undefined;

  constructor(
    factory: IDBFactory | undefined = globalThis.indexedDB,
    keyRange: typeof IDBKeyRange | undefined = globalThis.IDBKeyRange,
  ) {
    this.factory = factory;
    this.keyRange = keyRange;
  }

  async saveSession(record: RemoteSelectionLocalSessionRecord): Promise<void> {
    assertMetadataOnly(record);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.sessions,
        'readwrite',
      );
      transaction
        .objectStore(REMOTE_SELECTION_DATABASE_STORES.sessions)
        .put(record);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async loadSession(
    sessionId: string,
  ): Promise<RemoteSelectionLocalSessionRecord | null> {
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.sessions,
        'readonly',
      );
      return (await requestResult(
        transaction
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.sessions)
          .get(sessionId),
      )) as RemoteSelectionLocalSessionRecord | null;
    } finally {
      database.close();
    }
  }

  async saveIndexedSource(input: {
    readonly session: RemoteSelectionLocalSessionRecord;
    readonly batch: RemoteSelectionLocalBatchRecord;
    readonly sourceItems: readonly RemoteSelectionSourceItemRecord[];
  }): Promise<void> {
    validateIndexedSource(input);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.sessions,
          REMOTE_SELECTION_DATABASE_STORES.batches,
          REMOTE_SELECTION_DATABASE_STORES.sourceItems,
        ],
        'readwrite',
      );
      transaction
        .objectStore(REMOTE_SELECTION_DATABASE_STORES.sessions)
        .put(input.session);
      transaction
        .objectStore(REMOTE_SELECTION_DATABASE_STORES.batches)
        .put(input.batch);
      const sourceStore = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.sourceItems,
      );
      for (const item of input.sourceItems) sourceStore.put(item);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async loadBatch(
    sessionId: string,
    batchId: string,
  ): Promise<RemoteSelectionLocalBatchRecord | null> {
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.batches,
        'readonly',
      );
      return (await requestResult(
        transaction
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.batches)
          .get([sessionId, batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
    } finally {
      database.close();
    }
  }

  async saveBatch(record: RemoteSelectionLocalBatchRecord): Promise<void> {
    validateWorkspaceBatch(record);
    assertMetadataOnly(record);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.batches,
        'readwrite',
      );
      transaction
        .objectStore(REMOTE_SELECTION_DATABASE_STORES.batches)
        .put(record);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async loadSourceItem(
    sessionId: string,
    batchId: string,
    ordinal: number,
  ): Promise<RemoteSelectionSourceItemRecord | null> {
    if (!Number.isSafeInteger(ordinal) || ordinal < 0) return null;
    const database = await this.open();
    try {
      return (await requestResult(
        database
          .transaction(REMOTE_SELECTION_DATABASE_STORES.sourceItems)
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.sourceItems)
          .get([sessionId, batchId, ordinal]),
      )) as RemoteSelectionSourceItemRecord | null;
    } finally {
      database.close();
    }
  }

  async loadSourceItemsWindow(
    sessionId: string,
    batchId: string,
    currentIndex: number,
    fileCount: number,
    radius = 3,
  ): Promise<RemoteSelectionSourceItemRecord[]> {
    if (
      !Number.isSafeInteger(currentIndex) ||
      currentIndex < 0 ||
      currentIndex >= fileCount ||
      !Number.isSafeInteger(radius) ||
      radius < 0
    ) {
      return [];
    }
    const first = Math.max(0, currentIndex - radius);
    const last = Math.min(fileCount - 1, currentIndex + radius);
    return this.listSourceItemsPage(
      sessionId,
      batchId,
      first - 1,
      last - first + 1,
    );
  }

  async operationClock(
    sessionId: string,
    batchId: string,
    clientInstanceId: string,
  ): Promise<RemoteSelectionOperationClock> {
    const [client, pendingCount] = await Promise.all([
      this.loadClientInstance(sessionId, batchId, clientInstanceId),
      this.countPendingOperations(sessionId, batchId),
    ]);
    return {
      clientSequence: (client?.lastClientSequence ?? 0) + 1,
      expectedServerRevision:
        (client?.lastKnownServerRevision ?? 0) + pendingCount,
    };
  }

  async appendWorkspaceDecision(input: {
    readonly command: RemoteManualSelectionOperationCommandV1;
    readonly decision: RemoteSelectionWorkspaceDecision;
    readonly nextCursorIndex: number;
    readonly queuedAt?: string;
  }): Promise<RemoteSelectionLocalBatchRecord> {
    const { command, decision } = input;
    validateOperationCommand(command);
    validateWorkspaceDecision(command, decision);
    const queuedAt = input.queuedAt ?? new Date().toISOString();
    const commandChecksumSha256 = await canonicalRemoteChecksumSha256(command);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.batches,
          REMOTE_SELECTION_DATABASE_STORES.outbox,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
        ],
        'readwrite',
      );
      const batches = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const batch = (await requestResult(
        batches.get([command.sessionId, command.batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (batch === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_BATCH_NOT_FOUND',
          'Remote selection batch does not exist.',
        );
      }
      const workspace = remoteSelectionWorkspaceState(batch);
      const persistedDecision = workspace.decisions.find(
        (candidate) => candidate.operationId === decision.operationId,
      );
      if (persistedDecision !== undefined) {
        if (
          JSON.stringify(persistedDecision) !== JSON.stringify(decision) ||
          workspace.currentIndex !== input.nextCursorIndex
        ) {
          transaction.abort();
          throw storeError(
            'REMOTE_SELECTION_WORKSPACE_DECISION_CONFLICT',
            'The operation ID is already bound to a different local decision.',
          );
        }
        await transactionComplete(transaction);
        return batch;
      }
      if (
        workspace.nextRangeStart !== decision.rangeStart ||
        input.nextCursorIndex < 0 ||
        input.nextCursorIndex >= batch.fileCount
      ) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_WORKSPACE_STALE',
          'The local workspace changed before the decision was persisted.',
        );
      }
      const outbox = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      const clients = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
      );
      await appendOutboxRecord(
        outbox,
        clients,
        command,
        commandChecksumSha256,
        queuedAt,
      );
      const next: RemoteSelectionLocalBatchRecord = {
        ...batch,
        cursorIndex: input.nextCursorIndex,
        decisions: [...workspace.decisions, decision],
        navigationStep: workspace.navigationStep,
        nextRangeStart: decision.rangeStart + 9,
        updatedAt: queuedAt,
      };
      validateWorkspaceBatch(next);
      batches.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async appendLocalWorkspaceDecision(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly decision: RemoteSelectionWorkspaceDecision;
    readonly nextCursorIndex: number;
    readonly updatedAt?: string;
  }): Promise<RemoteSelectionLocalBatchRecord> {
    const updatedAt = input.updatedAt ?? new Date().toISOString();
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.batches,
        'readwrite',
      );
      const batches = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const batch = (await requestResult(
        batches.get([input.sessionId, input.batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (batch === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_BATCH_NOT_FOUND',
          'Remote selection batch does not exist.',
        );
      }
      const workspace = remoteSelectionWorkspaceState(batch);
      if (
        workspace.nextRangeStart !== input.decision.rangeStart ||
        input.nextCursorIndex < 0 ||
        input.nextCursorIndex >= batch.fileCount
      ) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_WORKSPACE_STALE',
          'The local workspace changed before the decision was persisted.',
        );
      }
      const next: RemoteSelectionLocalBatchRecord = {
        ...batch,
        cursorIndex: input.nextCursorIndex,
        decisions: [...workspace.decisions, input.decision],
        navigationStep: workspace.navigationStep,
        nextRangeStart: input.decision.rangeStart + 9,
        updatedAt,
      };
      validateWorkspaceBatch(next);
      batches.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async undoLastLocalWorkspaceDecision(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly expectedOperationId: string;
    readonly updatedAt?: string;
  }): Promise<RemoteSelectionLocalBatchRecord | null> {
    const updatedAt = input.updatedAt ?? new Date().toISOString();
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.batches,
        'readwrite',
      );
      const batches = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const batch = (await requestResult(
        batches.get([input.sessionId, input.batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (batch === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_BATCH_NOT_FOUND',
          'Remote selection batch does not exist.',
        );
      }
      const workspace = remoteSelectionWorkspaceState(batch);
      const last = workspace.decisions.at(-1);
      if (last === undefined) {
        await transactionComplete(transaction);
        return null;
      }
      if (last.operationId !== input.expectedOperationId) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_WORKSPACE_STALE',
          'The last local decision changed before undo was persisted.',
        );
      }
      const next: RemoteSelectionLocalBatchRecord = {
        ...batch,
        cursorIndex: last.sourceIndex,
        decisions: workspace.decisions.slice(0, -1),
        navigationStep: workspace.navigationStep,
        nextRangeStart: last.rangeStart,
        updatedAt,
      };
      validateWorkspaceBatch(next);
      batches.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async undoLastWorkspaceDecision(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly command: RemoteManualSelectionOperationCommandV1 | null;
    readonly queuedAt?: string;
  }): Promise<RemoteSelectionLocalBatchRecord | null> {
    const queuedAt = input.queuedAt ?? new Date().toISOString();
    const commandChecksumSha256 =
      input.command === null
        ? null
        : await canonicalRemoteChecksumSha256(input.command);
    if (input.command !== null) validateOperationCommand(input.command);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.batches,
          REMOTE_SELECTION_DATABASE_STORES.outbox,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
        ],
        'readwrite',
      );
      const batches = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const batch = (await requestResult(
        batches.get([input.sessionId, input.batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (batch === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_BATCH_NOT_FOUND',
          'Remote selection batch does not exist.',
        );
      }
      const workspace = remoteSelectionWorkspaceState(batch);
      const last = workspace.decisions.at(-1);
      if (last === undefined) {
        await transactionComplete(transaction);
        return null;
      }
      if (last.action === 'accepted') {
        const command = input.command;
        if (
          command === null ||
          command.operationType !== 'undo' ||
          command.targetOperationId !== last.operationId ||
          command.fileId !== last.fileId ||
          commandChecksumSha256 === null
        ) {
          transaction.abort();
          throw storeError(
            'REMOTE_SELECTION_UNDO_COMMAND_INVALID',
            'Undo must target the exact accepted selection.',
          );
        }
        await appendOutboxRecord(
          transaction.objectStore(REMOTE_SELECTION_DATABASE_STORES.outbox),
          transaction.objectStore(
            REMOTE_SELECTION_DATABASE_STORES.clientInstances,
          ),
          command,
          commandChecksumSha256,
          queuedAt,
        );
      } else if (input.command !== null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_UNDO_COMMAND_INVALID',
          'A skipped range is undone locally and must not create a tombstone.',
        );
      }
      const next: RemoteSelectionLocalBatchRecord = {
        ...batch,
        cursorIndex: last.sourceIndex,
        decisions: workspace.decisions.slice(0, -1),
        navigationStep: workspace.navigationStep,
        nextRangeStart: last.rangeStart,
        updatedAt: queuedAt,
      };
      validateWorkspaceBatch(next);
      batches.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async updateCursor(
    sessionId: string,
    batchId: string,
    cursorIndex: number,
    updatedAt = new Date().toISOString(),
  ): Promise<RemoteSelectionLocalBatchRecord> {
    if (!Number.isSafeInteger(cursorIndex) || cursorIndex < 0) {
      throw storeError('REMOTE_SELECTION_CURSOR_INVALID', 'Cursor is invalid.');
    }
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.batches,
        'readwrite',
      );
      const store = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const current = (await requestResult(
        store.get([sessionId, batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (current === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_BATCH_NOT_FOUND',
          'Remote selection batch does not exist.',
        );
      }
      const next = { ...current, cursorIndex, updatedAt };
      store.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async listSourceItemsPage(
    sessionId: string,
    batchId: string,
    afterOrdinal = -1,
    limit = 100,
  ): Promise<RemoteSelectionSourceItemRecord[]> {
    return this.listPage<RemoteSelectionSourceItemRecord>(
      REMOTE_SELECTION_DATABASE_STORES.sourceItems,
      [sessionId, batchId, afterOrdinal + 1],
      [sessionId, batchId, Number.MAX_SAFE_INTEGER],
      limit,
    );
  }

  async loadSourceManifest(
    sessionId: string,
    batchId: string,
  ): Promise<RemoteSourceManifestV1> {
    const batch = await this.loadBatch(sessionId, batchId);
    if (batch === null) {
      throw storeError(
        'REMOTE_SELECTION_BATCH_NOT_FOUND',
        'Remote selection batch does not exist.',
      );
    }
    const metadata: Omit<RemoteSourceManifestEntryV1, 'ordinal'>[] = [];
    let afterOrdinal = -1;
    while (true) {
      const page = await this.listSourceItemsPage(
        sessionId,
        batchId,
        afterOrdinal,
        MAX_PAGE_SIZE,
      );
      if (page.length === 0) break;
      metadata.push(
        ...page.map((item) => ({
          lastModifiedMs: item.lastModifiedMs,
          mimeType: item.mimeType,
          name: item.name,
          relativePath: item.relativePath,
          sizeBytes: item.sizeBytes,
        })),
      );
      afterOrdinal = page.at(-1)?.ordinal ?? afterOrdinal;
      if (page.length < MAX_PAGE_SIZE) break;
    }
    const manifest = await buildRemoteSourceManifestV1(
      metadata,
      batch.sourceKind,
    );
    if (
      manifest.manifestChecksumSha256 !== batch.sourceManifestChecksumSha256
    ) {
      throw storeError(
        'REMOTE_SELECTION_SOURCE_MANIFEST_CORRUPTED',
        'Persisted source metadata does not match the batch manifest.',
      );
    }
    return manifest;
  }

  async appendOutboxOperation(
    command: RemoteManualSelectionOperationCommandV1,
    queuedAt = new Date().toISOString(),
  ): Promise<{
    readonly created: boolean;
    readonly record: RemoteSelectionOutboxRecord;
  }> {
    validateOperationCommand(command);
    const commandChecksumSha256 = await canonicalRemoteChecksumSha256(command);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.outbox,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
        ],
        'readwrite',
      );
      const outbox = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      const existing = (await requestResult(
        outbox.index('operationId').get(command.operationId),
      )) as RemoteSelectionOutboxRecord | null;
      if (existing !== null) {
        if (
          existing.sessionId !== command.sessionId ||
          existing.batchId !== command.batchId ||
          existing.commandChecksumSha256 !== commandChecksumSha256
        ) {
          transaction.abort();
          throw storeError(
            'REMOTE_SELECTION_OUTBOX_OPERATION_CONFLICT',
            'Operation ID is already bound to different content.',
          );
        }
        await transactionComplete(transaction);
        return { created: false, record: existing };
      }

      const clients = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
      );
      const clientKey = [
        command.sessionId,
        command.batchId,
        command.clientInstanceId,
      ];
      const client = (await requestResult(
        clients.get(clientKey),
      )) as RemoteSelectionClientInstanceRecord | null;
      const expectedSequence = (client?.lastClientSequence ?? 0) + 1;
      if (command.clientSequence !== expectedSequence) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_OUTBOX_SEQUENCE_INVALID',
          `Expected client sequence ${expectedSequence}.`,
        );
      }
      const record: RemoteSelectionOutboxRecord = {
        schemaVersion: 1,
        attemptCount: 0,
        batchId: command.batchId,
        clientInstanceId: command.clientInstanceId,
        clientSequence: command.clientSequence,
        command,
        commandChecksumSha256,
        lastErrorCode: null,
        operationId: command.operationId,
        queuedAt,
        sessionId: command.sessionId,
        state: 'pending',
        updatedAt: queuedAt,
      };
      assertMetadataOnly(record);
      outbox.put(record);
      clients.put({
        schemaVersion: 1,
        batchId: command.batchId,
        clientInstanceId: command.clientInstanceId,
        lastClientSequence: command.clientSequence,
        lastKnownServerRevision:
          client?.lastKnownServerRevision ?? command.expectedServerRevision,
        sessionId: command.sessionId,
        updatedAt: queuedAt,
      } satisfies RemoteSelectionClientInstanceRecord);
      await transactionComplete(transaction);
      return { created: true, record };
    } finally {
      database.close();
    }
  }

  async listOutboxPage(
    sessionId: string,
    batchId: string,
    afterClientSequence = 0,
    limit = 100,
  ): Promise<RemoteSelectionOutboxRecord[]> {
    return this.listPage<RemoteSelectionOutboxRecord>(
      REMOTE_SELECTION_DATABASE_STORES.outbox,
      [sessionId, batchId, afterClientSequence + 1],
      [sessionId, batchId, Number.MAX_SAFE_INTEGER],
      limit,
    );
  }

  async countPendingOperations(
    sessionId: string,
    batchId: string,
  ): Promise<number> {
    const range = this.boundedRange(
      [sessionId, batchId, 0],
      [sessionId, batchId, Number.MAX_SAFE_INTEGER],
    );
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
        'readonly',
      );
      return (await requestResult(
        transaction
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.outbox)
          .count(range),
      )) as number;
    } finally {
      database.close();
    }
  }

  async loadOutboxOperation(
    sessionId: string,
    batchId: string,
    operationId: string,
  ): Promise<RemoteSelectionOutboxRecord | null> {
    const database = await this.open();
    try {
      const record = (await requestResult(
        database
          .transaction(REMOTE_SELECTION_DATABASE_STORES.outbox)
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.outbox)
          .index('operationId')
          .get(operationId),
      )) as RemoteSelectionOutboxRecord | null;
      return record?.sessionId === sessionId && record.batchId === batchId
        ? record
        : null;
    } finally {
      database.close();
    }
  }

  async acknowledgeOperations(
    sessionId: string,
    batchId: string,
    operationIds: readonly string[],
  ): Promise<number> {
    const uniqueIds = [...new Set(operationIds)];
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
        'readwrite',
      );
      const outbox = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      const operationIndex = outbox.index('operationId');
      let removed = 0;
      for (const operationId of uniqueIds) {
        const record = (await requestResult(
          operationIndex.get(operationId),
        )) as RemoteSelectionOutboxRecord | null;
        if (
          record !== null &&
          record.sessionId === sessionId &&
          record.batchId === batchId
        ) {
          outbox.delete([sessionId, batchId, record.clientSequence]);
          removed += 1;
        }
      }
      await transactionComplete(transaction);
      return removed;
    } finally {
      database.close();
    }
  }

  async loadClientInstance(
    sessionId: string,
    batchId: string,
    clientInstanceId: string,
  ): Promise<RemoteSelectionClientInstanceRecord | null> {
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
        'readonly',
      );
      return (await requestResult(
        transaction
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.clientInstances)
          .get([sessionId, batchId, clientInstanceId]),
      )) as RemoteSelectionClientInstanceRecord | null;
    } finally {
      database.close();
    }
  }

  async markOutboxOperation(
    sessionId: string,
    batchId: string,
    operationId: string,
    state: RemoteSelectionOutboxState,
    lastErrorCode: string | null,
    updatedAt = new Date().toISOString(),
  ): Promise<RemoteSelectionOutboxRecord> {
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
        'readwrite',
      );
      const store = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      const current = (await requestResult(
        store.index('operationId').get(operationId),
      )) as RemoteSelectionOutboxRecord | null;
      if (
        current === null ||
        current.sessionId !== sessionId ||
        current.batchId !== batchId
      ) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_OUTBOX_OPERATION_NOT_FOUND',
          'The outbox operation does not exist in this batch.',
        );
      }
      const next: RemoteSelectionOutboxRecord = {
        ...current,
        attemptCount:
          state === 'sending' ? current.attemptCount + 1 : current.attemptCount,
        lastErrorCode,
        state,
        updatedAt,
      };
      store.put(next);
      await transactionComplete(transaction);
      return next;
    } finally {
      database.close();
    }
  }

  async rebaseOutboxAfterClientSequenceReplay(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly clientInstanceId: string;
    readonly serverLastClientSequence: number;
    readonly serverRevision: number;
    readonly updatedAt?: string;
  }): Promise<number> {
    if (
      !Number.isSafeInteger(input.serverLastClientSequence) ||
      input.serverLastClientSequence < 0 ||
      !Number.isSafeInteger(input.serverRevision) ||
      input.serverRevision < 0
    ) {
      throw storeError(
        'REMOTE_SELECTION_SERVER_CLOCK_INVALID',
        'The canonical server clock is invalid.',
      );
    }
    const records = (
      await this.listOutboxRecords(input.sessionId, input.batchId)
    )
      .filter((record) => record.clientInstanceId === input.clientInstanceId)
      .sort((left, right) => left.clientSequence - right.clientSequence);
    if (records.length === 0) return 0;

    const updatedAt = input.updatedAt ?? new Date().toISOString();
    const rebased = await Promise.all(
      records.map(async (record, index) => {
        const command: RemoteManualSelectionOperationCommandV1 = {
          ...record.command,
          clientSequence: input.serverLastClientSequence + index + 1,
          expectedServerRevision: input.serverRevision + index,
        };
        return {
          previous: record,
          next: {
            ...record,
            clientSequence: command.clientSequence,
            command,
            commandChecksumSha256: await canonicalRemoteChecksumSha256(command),
            lastErrorCode: null,
            state: 'pending' as const,
            updatedAt,
          },
        };
      }),
    );

    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.outbox,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
        ],
        'readwrite',
      );
      const outbox = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      for (const item of rebased) {
        const current = (await requestResult(
          outbox.index('operationId').get(item.previous.operationId),
        )) as RemoteSelectionOutboxRecord | null;
        if (
          current === null ||
          current.clientSequence !== item.previous.clientSequence ||
          current.commandChecksumSha256 !==
            item.previous.commandChecksumSha256 ||
          current.clientInstanceId !== input.clientInstanceId
        ) {
          transaction.abort();
          throw storeError(
            'REMOTE_SELECTION_OUTBOX_REBASE_STALE',
            'The local outbox changed while its server clock was being repaired.',
          );
        }
      }
      for (const item of rebased) {
        outbox.delete([
          input.sessionId,
          input.batchId,
          item.previous.clientSequence,
        ]);
      }
      for (const item of rebased) outbox.put(item.next);

      const clients = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
      );
      const clientKey = [
        input.sessionId,
        input.batchId,
        input.clientInstanceId,
      ];
      const client = (await requestResult(
        clients.get(clientKey),
      )) as RemoteSelectionClientInstanceRecord | null;
      if (client === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_CLIENT_INSTANCE_NOT_FOUND',
          'The local client instance does not exist.',
        );
      }
      clients.put({
        schemaVersion: client.schemaVersion,
        batchId: input.batchId,
        clientInstanceId: input.clientInstanceId,
        lastClientSequence: input.serverLastClientSequence + rebased.length,
        lastKnownServerRevision: input.serverRevision,
        sessionId: input.sessionId,
        updatedAt,
      } satisfies RemoteSelectionClientInstanceRecord);
      await transactionComplete(transaction);
      return rebased.length;
    } finally {
      database.close();
    }
  }

  async confirmOperation(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly clientInstanceId: string;
    readonly operationId: string;
    readonly commandChecksumSha256: string;
    readonly serverRevision: number;
    readonly file: RemoteSelectionServerFileState | null;
    readonly updatedAt?: string;
  }): Promise<void> {
    const updatedAt = input.updatedAt ?? new Date().toISOString();
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.outbox,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
          REMOTE_SELECTION_DATABASE_STORES.sourceItems,
        ],
        'readwrite',
      );
      const outbox = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
      );
      const record = (await requestResult(
        outbox.index('operationId').get(input.operationId),
      )) as RemoteSelectionOutboxRecord | null;
      if (
        record === null ||
        record.sessionId !== input.sessionId ||
        record.batchId !== input.batchId ||
        record.clientInstanceId !== input.clientInstanceId ||
        record.commandChecksumSha256 !== input.commandChecksumSha256
      ) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_CONFIRMATION_MISMATCH',
          'The server confirmation does not match the exact outbox operation.',
        );
      }
      if (input.file !== null) {
        await updateServerFileState(
          transaction.objectStore(REMOTE_SELECTION_DATABASE_STORES.sourceItems),
          input.file,
        );
      }
      const clients = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
      );
      const key = [input.sessionId, input.batchId, input.clientInstanceId];
      const client = (await requestResult(
        clients.get(key),
      )) as RemoteSelectionClientInstanceRecord | null;
      if (client === null) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_CLIENT_INSTANCE_NOT_FOUND',
          'The local client instance does not exist.',
        );
      }
      clients.put({
        ...client,
        lastKnownServerRevision: Math.max(
          client.lastKnownServerRevision,
          input.serverRevision,
        ),
        updatedAt,
      });
      outbox.delete([input.sessionId, input.batchId, record.clientSequence]);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async applyServerStateDelta(input: {
    readonly sessionId: string;
    readonly batchId: string;
    readonly clientInstanceId: string;
    readonly files: readonly RemoteSelectionServerFileState[];
    readonly nextRevision: number;
    readonly serverLastClientSequence?: number;
    readonly status?: 'indexing' | 'active' | 'finalizing' | 'completed';
    readonly updatedAt?: string;
  }): Promise<void> {
    if (
      input.serverLastClientSequence !== undefined &&
      (!Number.isSafeInteger(input.serverLastClientSequence) ||
        input.serverLastClientSequence < 0)
    ) {
      throw storeError(
        'REMOTE_SELECTION_SERVER_CLOCK_INVALID',
        'The canonical server client sequence is invalid.',
      );
    }
    const updatedAt = input.updatedAt ?? new Date().toISOString();
    const database = await this.open();
    try {
      const transaction = database.transaction(
        [
          REMOTE_SELECTION_DATABASE_STORES.batches,
          REMOTE_SELECTION_DATABASE_STORES.clientInstances,
          REMOTE_SELECTION_DATABASE_STORES.sourceItems,
        ],
        'readwrite',
      );
      const sourceItems = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.sourceItems,
      );
      try {
        for (const file of input.files) {
          await updateServerFileState(sourceItems, file);
        }
      } catch (cause) {
        transaction.abort();
        throw cause;
      }
      const clients = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.clientInstances,
      );
      const key = [input.sessionId, input.batchId, input.clientInstanceId];
      const client = (await requestResult(
        clients.get(key),
      )) as RemoteSelectionClientInstanceRecord | null;
      if (
        client === null ||
        input.nextRevision < client.lastKnownServerRevision
      ) {
        transaction.abort();
        throw storeError(
          'REMOTE_SELECTION_STATE_REVISION_INVALID',
          'The server state delta would roll back local canonical state.',
        );
      }
      clients.put({
        ...client,
        lastClientSequence: Math.max(
          client.lastClientSequence,
          input.serverLastClientSequence ?? client.lastClientSequence,
        ),
        lastKnownServerRevision: input.nextRevision,
        updatedAt,
      });
      const batches = transaction.objectStore(
        REMOTE_SELECTION_DATABASE_STORES.batches,
      );
      const batch = (await requestResult(
        batches.get([input.sessionId, input.batchId]),
      )) as RemoteSelectionLocalBatchRecord | null;
      if (batch !== null) {
        batches.put({
          ...batch,
          serverRevision: input.nextRevision,
          status: input.status ?? batch.status,
          updatedAt,
        });
      }
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async saveTransferCheckpoint(
    checkpoint: RemoteSelectionTransferCheckpointRecord,
  ): Promise<void> {
    if (
      normalizePersistedRelativePath(checkpoint.sourceRelativePath) !==
        checkpoint.sourceRelativePath ||
      !Number.isSafeInteger(checkpoint.generation) ||
      checkpoint.generation < 1 ||
      !Number.isSafeInteger(checkpoint.expectedSizeBytes) ||
      checkpoint.expectedSizeBytes < 0 ||
      !Number.isSafeInteger(checkpoint.acknowledgedBytes) ||
      checkpoint.acknowledgedBytes < 0 ||
      checkpoint.acknowledgedBytes > checkpoint.expectedSizeBytes ||
      (checkpoint.transferId !== undefined &&
        !/^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89aAbB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$/.test(
          checkpoint.transferId,
        )) ||
      (checkpoint.status !== undefined &&
        !['queued', 'uploading', 'verified', 'cancelled', 'failed'].includes(
          checkpoint.status,
        ))
    ) {
      throw storeError(
        'REMOTE_SELECTION_TRANSFER_CHECKPOINT_INVALID',
        'Transfer checkpoint metadata is invalid.',
      );
    }
    assertMetadataOnly(checkpoint);
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.transferCheckpoints,
        'readwrite',
      );
      transaction
        .objectStore(REMOTE_SELECTION_DATABASE_STORES.transferCheckpoints)
        .put(checkpoint);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async loadTransferCheckpoint(
    sessionId: string,
    batchId: string,
    fileId: string,
    generation: number,
  ): Promise<RemoteSelectionTransferCheckpointRecord | null> {
    const database = await this.open();
    try {
      const value = (await requestResult(
        database
          .transaction(REMOTE_SELECTION_DATABASE_STORES.transferCheckpoints)
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.transferCheckpoints)
          .get([sessionId, batchId, fileId, generation]),
      )) as RemoteSelectionTransferCheckpointRecord | undefined;
      return value ?? null;
    } finally {
      database.close();
    }
  }

  async restore(
    sessionId: string,
    pageSize = 100,
  ): Promise<RemoteSelectionRestoreSnapshot> {
    const session = await this.loadSession(sessionId);
    if (session?.activeBatchId === null || session === null) {
      return {
        batch: null,
        pendingOperationCount: 0,
        pendingOperations: [],
        session,
        sourceItems: [],
      };
    }
    const batchId = session.activeBatchId;
    const [batch, sourceItems, pendingOperations, pendingOperationCount] =
      await Promise.all([
        this.loadBatch(sessionId, batchId),
        this.listSourceItemsPage(sessionId, batchId, -1, pageSize),
        this.listOutboxPage(sessionId, batchId, 0, pageSize),
        this.countPendingOperations(sessionId, batchId),
      ]);
    return {
      batch,
      pendingOperationCount,
      pendingOperations,
      session,
      sourceItems,
    };
  }

  private async listPage<T>(
    storeName: string,
    lower: IDBValidKey,
    upper: IDBValidKey,
    limit: number,
  ): Promise<T[]> {
    const boundedLimit = pageLimit(limit);
    const database = await this.open();
    try {
      const transaction = database.transaction(storeName, 'readonly');
      const store = transaction.objectStore(storeName);
      const range = this.boundedRange(lower, upper);
      return await cursorPage<T>(store, range, boundedLimit);
    } finally {
      database.close();
    }
  }

  private async listOutboxRecords(
    sessionId: string,
    batchId: string,
  ): Promise<RemoteSelectionOutboxRecord[]> {
    const database = await this.open();
    try {
      const transaction = database.transaction(
        REMOTE_SELECTION_DATABASE_STORES.outbox,
        'readonly',
      );
      const range = this.boundedRange(
        [sessionId, batchId, 0],
        [sessionId, batchId, Number.MAX_SAFE_INTEGER],
      );
      return (await requestResult(
        transaction
          .objectStore(REMOTE_SELECTION_DATABASE_STORES.outbox)
          .getAll(range),
      )) as RemoteSelectionOutboxRecord[];
    } finally {
      database.close();
    }
  }

  private boundedRange(lower: IDBValidKey, upper: IDBValidKey): IDBKeyRange {
    if (this.keyRange === undefined) {
      throw storeError(
        'REMOTE_SELECTION_INDEXEDDB_UNAVAILABLE',
        'IndexedDB key ranges are unavailable.',
      );
    }
    return this.keyRange.bound(lower, upper);
  }

  private open(): Promise<IDBDatabase> {
    if (this.factory === undefined) {
      return Promise.reject(
        storeError(
          'REMOTE_SELECTION_INDEXEDDB_UNAVAILABLE',
          'IndexedDB is unavailable.',
        ),
      );
    }
    return new Promise((resolve, reject) => {
      const request = this.factory?.open(
        REMOTE_SELECTION_DATABASE_NAME,
        REMOTE_SELECTION_DATABASE_VERSION,
      );
      if (request === undefined) {
        reject(
          storeError(
            'REMOTE_SELECTION_INDEXEDDB_UNAVAILABLE',
            'IndexedDB is unavailable.',
          ),
        );
        return;
      }
      request.onupgradeneeded = (event) => {
        upgradeRemoteSelectionDatabase(
          request.result,
          request.transaction,
          event.oldVersion,
        );
      };
      request.onsuccess = () => {
        request.result.onversionchange = () => request.result.close();
        resolve(request.result);
      };
      request.onerror = () =>
        reject(
          request.error ??
            storeError(
              'REMOTE_SELECTION_INDEXEDDB_OPEN_FAILED',
              'Remote selection storage could not be opened.',
            ),
        );
      request.onblocked = () =>
        reject(
          storeError(
            'REMOTE_SELECTION_INDEXEDDB_UPGRADE_BLOCKED',
            'Close another tab to upgrade remote selection storage.',
          ),
        );
    });
  }
}

export function upgradeRemoteSelectionDatabase(
  database: IDBDatabase,
  transaction: IDBTransaction | null,
  oldVersion: number,
): void {
  if (oldVersion >= 1) return;
  if (transaction === null) {
    throw storeError(
      'REMOTE_SELECTION_INDEXEDDB_MIGRATION_FAILED',
      'IndexedDB upgrade transaction is unavailable.',
    );
  }
  database.createObjectStore(REMOTE_SELECTION_DATABASE_STORES.sessions, {
    keyPath: 'sessionId',
  });
  database.createObjectStore(REMOTE_SELECTION_DATABASE_STORES.batches, {
    keyPath: ['sessionId', 'batchId'],
  });
  database.createObjectStore(REMOTE_SELECTION_DATABASE_STORES.sourceItems, {
    keyPath: ['sessionId', 'batchId', 'ordinal'],
  });
  const outbox = database.createObjectStore(
    REMOTE_SELECTION_DATABASE_STORES.outbox,
    { keyPath: ['sessionId', 'batchId', 'clientSequence'] },
  );
  outbox.createIndex('operationId', 'operationId', { unique: true });
  database.createObjectStore(
    REMOTE_SELECTION_DATABASE_STORES.transferCheckpoints,
    { keyPath: ['sessionId', 'batchId', 'fileId', 'generation'] },
  );
  database.createObjectStore(REMOTE_SELECTION_DATABASE_STORES.clientInstances, {
    keyPath: ['sessionId', 'batchId', 'clientInstanceId'],
  });
}

export async function requestBestEffortPersistentStorage(
  storage: Pick<StorageManager, 'persist'> | undefined = globalThis.navigator
    ?.storage,
): Promise<{ readonly supported: boolean; readonly granted: boolean }> {
  if (typeof storage?.persist !== 'function') {
    return { granted: false, supported: false };
  }
  try {
    return { granted: await storage.persist(), supported: true };
  } catch {
    return { granted: false, supported: true };
  }
}

async function appendOutboxRecord(
  outbox: IDBObjectStore,
  clients: IDBObjectStore,
  command: RemoteManualSelectionOperationCommandV1,
  commandChecksumSha256: string,
  queuedAt: string,
): Promise<RemoteSelectionOutboxRecord> {
  const existing = (await requestResult(
    outbox.index('operationId').get(command.operationId),
  )) as RemoteSelectionOutboxRecord | null;
  if (existing !== null) {
    if (
      existing.sessionId !== command.sessionId ||
      existing.batchId !== command.batchId ||
      existing.commandChecksumSha256 !== commandChecksumSha256
    ) {
      throw storeError(
        'REMOTE_SELECTION_OUTBOX_OPERATION_CONFLICT',
        'Operation ID is already bound to different content.',
      );
    }
    return existing;
  }
  const clientKey = [
    command.sessionId,
    command.batchId,
    command.clientInstanceId,
  ];
  const client = (await requestResult(
    clients.get(clientKey),
  )) as RemoteSelectionClientInstanceRecord | null;
  const expectedSequence = (client?.lastClientSequence ?? 0) + 1;
  if (command.clientSequence !== expectedSequence) {
    throw storeError(
      'REMOTE_SELECTION_OUTBOX_SEQUENCE_INVALID',
      `Expected client sequence ${expectedSequence}.`,
    );
  }
  const record: RemoteSelectionOutboxRecord = {
    schemaVersion: 1,
    attemptCount: 0,
    batchId: command.batchId,
    clientInstanceId: command.clientInstanceId,
    clientSequence: command.clientSequence,
    command,
    commandChecksumSha256,
    lastErrorCode: null,
    operationId: command.operationId,
    queuedAt,
    sessionId: command.sessionId,
    state: 'pending',
    updatedAt: queuedAt,
  };
  assertMetadataOnly(record);
  outbox.put(record);
  clients.put({
    schemaVersion: 1,
    batchId: command.batchId,
    clientInstanceId: command.clientInstanceId,
    lastClientSequence: command.clientSequence,
    lastKnownServerRevision:
      client?.lastKnownServerRevision ?? command.expectedServerRevision,
    sessionId: command.sessionId,
    updatedAt: queuedAt,
  } satisfies RemoteSelectionClientInstanceRecord);
  return record;
}

function validateWorkspaceDecision(
  command: RemoteManualSelectionOperationCommandV1,
  decision: RemoteSelectionWorkspaceDecision,
): void {
  const accepted = decision.action === 'accepted';
  if (
    command.operationId !== decision.operationId ||
    command.rangeStart !== decision.rangeStart ||
    command.rangeEnd !== decision.rangeEnd ||
    command.selectionGeneration !== decision.selectionGeneration ||
    command.sourceIndex !== decision.sourceIndex ||
    (accepted && command.operationType !== 'select') ||
    (!accepted && command.operationType !== 'skip') ||
    (accepted &&
      (decision.fileId === null ||
        decision.imagePath === null ||
        decision.imageChecksumSha256 === null ||
        decision.outputName === null ||
        command.fileId !== decision.fileId ||
        command.imagePath !== decision.imagePath ||
        command.imageChecksumSha256 !== decision.imageChecksumSha256 ||
        command.outputName !== decision.outputName)) ||
    (!accepted &&
      (decision.fileId !== null ||
        decision.imagePath !== null ||
        decision.imageChecksumSha256 !== null ||
        decision.outputName !== null ||
        command.fileId !== null)) ||
    decision.rangeEnd !== decision.rangeStart + 8 ||
    !Number.isSafeInteger(decision.sourceIndex) ||
    decision.sourceIndex < 0
  ) {
    throw storeError(
      'REMOTE_SELECTION_WORKSPACE_DECISION_INVALID',
      'The workspace decision does not match its durable outbox command.',
    );
  }
}

function validateWorkspaceBatch(record: RemoteSelectionLocalBatchRecord): void {
  const workspace = remoteSelectionWorkspaceState(record);
  if (
    !Number.isSafeInteger(workspace.currentIndex) ||
    workspace.currentIndex < 0 ||
    workspace.currentIndex >= record.fileCount ||
    !Number.isSafeInteger(workspace.nextRangeStart) ||
    workspace.nextRangeStart < 1 ||
    workspace.decisions.some(
      (decision, index) =>
        decision.rangeStart !== record.firstLayout + index * 9 ||
        decision.rangeEnd !== decision.rangeStart + 8 ||
        !Number.isSafeInteger(decision.sourceIndex) ||
        decision.sourceIndex < 0 ||
        decision.sourceIndex >= record.fileCount,
    ) ||
    workspace.nextRangeStart !==
      record.firstLayout + workspace.decisions.length * 9 ||
    (record.serverRevision !== undefined &&
      (!Number.isSafeInteger(record.serverRevision) ||
        record.serverRevision < 0)) ||
    (record.status !== undefined &&
      !['indexing', 'active', 'finalizing', 'completed'].includes(
        record.status,
      ))
  ) {
    throw storeError(
      'REMOTE_SELECTION_WORKSPACE_STATE_INVALID',
      'The persisted remote workspace state is inconsistent.',
    );
  }
}

function validateIndexedSource(input: {
  readonly session: RemoteSelectionLocalSessionRecord;
  readonly batch: RemoteSelectionLocalBatchRecord;
  readonly sourceItems: readonly RemoteSelectionSourceItemRecord[];
}): void {
  const { batch, session, sourceItems } = input;
  if (
    session.sessionId !== batch.sessionId ||
    session.activeBatchId !== batch.batchId ||
    session.sourceManifestChecksumSha256 !==
      batch.sourceManifestChecksumSha256 ||
    batch.fileCount !== sourceItems.length ||
    sourceItems.some(
      (item, ordinal) =>
        item.sessionId !== session.sessionId ||
        item.batchId !== batch.batchId ||
        item.ordinal !== ordinal,
    )
  ) {
    throw storeError(
      'REMOTE_SELECTION_INDEXED_SOURCE_INVALID',
      'Indexed source records do not describe one consistent batch.',
    );
  }
  validateWorkspaceBatch(batch);
  assertMetadataOnly(input);
}

function validateOperationCommand(
  command: RemoteManualSelectionOperationCommandV1,
): void {
  if (
    command.schemaVersion !== 'remote-manual-selection-operation-v1' ||
    !Number.isSafeInteger(command.clientSequence) ||
    command.clientSequence < 1 ||
    command.operationId.length === 0 ||
    command.sessionId.length === 0 ||
    command.batchId.length === 0 ||
    command.clientInstanceId.length === 0
  ) {
    throw storeError(
      'REMOTE_SELECTION_OUTBOX_COMMAND_INVALID',
      'Outbox operation command is invalid.',
    );
  }
  if (
    command.imagePath !== null &&
    normalizePersistedRelativePath(command.imagePath) !== command.imagePath
  ) {
    throw storeError(
      'REMOTE_SELECTION_OUTBOX_COMMAND_INVALID',
      'Outbox image path must be a safe relative path.',
    );
  }
}

function normalizePersistedRelativePath(value: string): string {
  try {
    return normalizeRemoteSourcePath(value);
  } catch {
    throw storeError(
      'REMOTE_SELECTION_SOURCE_PATH_INVALID',
      'Persisted source paths must be relative and normalized.',
    );
  }
}

function assertMetadataOnly(value: unknown, seen = new Set<unknown>()): void {
  if (typeof Blob !== 'undefined' && value instanceof Blob) {
    throw storeError(
      'REMOTE_SELECTION_BLOB_PERSISTENCE_FORBIDDEN',
      'JPEG blobs must not be persisted in the remote selection database.',
    );
  }
  if (value === null || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  if (isFileSystemHandle(value)) return;
  for (const child of Object.values(value)) assertMetadataOnly(child, seen);
}

function isFileSystemHandle(value: object): boolean {
  return (
    'kind' in value &&
    (value.kind === 'directory' || value.kind === 'file') &&
    'name' in value &&
    typeof value.name === 'string'
  );
}

function pageLimit(value: number): number {
  if (!Number.isSafeInteger(value) || value < 1 || value > MAX_PAGE_SIZE) {
    throw storeError(
      'REMOTE_SELECTION_PAGE_LIMIT_INVALID',
      `Page limit must be between 1 and ${MAX_PAGE_SIZE}.`,
    );
  }
  return value;
}

function cursorPage<T>(
  store: IDBObjectStore,
  range: IDBKeyRange,
  limit: number,
): Promise<T[]> {
  return new Promise((resolve, reject) => {
    const values: T[] = [];
    const request = store.openCursor(range, 'next');
    request.onsuccess = () => {
      const cursor = request.result;
      if (cursor === null || values.length >= limit) {
        resolve(values);
        return;
      }
      values.push(cursor.value as T);
      cursor.continue();
    };
    request.onerror = () =>
      reject(request.error ?? new Error('REMOTE_SELECTION_IDB_CURSOR_FAILED'));
  });
}

function requestResult(request: IDBRequest): Promise<unknown> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result ?? null);
    request.onerror = () =>
      reject(request.error ?? new Error('REMOTE_SELECTION_IDB_READ_FAILED'));
  });
}

async function updateServerFileState(
  store: IDBObjectStore,
  file: RemoteSelectionServerFileState,
): Promise<void> {
  const current = (await requestResult(
    store.get([file.sessionId, file.batchId, file.sourceIndex]),
  )) as RemoteSelectionSourceItemRecord | null;
  if (
    current === null ||
    current.fileId !== file.fileId ||
    current.relativePath !== file.relativePath
  ) {
    throw storeError(
      'REMOTE_SELECTION_SERVER_FILE_SCOPE_MISMATCH',
      'Canonical server file state does not match the indexed source item.',
    );
  }
  const currentRevision = current.lastServerRevision ?? 0;
  const nextRevision = file.lastServerRevision ?? currentRevision;
  if (
    nextRevision < currentRevision ||
    file.selectionGeneration < (current.selectionGeneration ?? 0)
  ) {
    throw storeError(
      'REMOTE_SELECTION_SERVER_FILE_STALE',
      'Canonical server file state is older than the persisted state.',
    );
  }
  store.put({
    ...current,
    desiredSelected: file.desiredSelected,
    hostChecksumSha256: file.hostChecksumSha256,
    lastServerRevision: nextRevision,
    outputName: file.outputName,
    rangeEnd: file.rangeEnd,
    rangeStart: file.rangeStart,
    selectionGeneration: file.selectionGeneration,
    serverStatus: file.status,
  } satisfies RemoteSelectionSourceItemRecord);
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('REMOTE_SELECTION_IDB_ABORTED'));
    transaction.onerror = () =>
      reject(
        transaction.error ?? new Error('REMOTE_SELECTION_IDB_WRITE_FAILED'),
      );
  });
}

function storeError(code: string, message: string): RemoteSelectionStoreError {
  return new RemoteSelectionStoreError(code, message);
}
