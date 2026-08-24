'use client';

import type { RemoteManualSelectionOperationCommandV1 } from '@game-predictor/manual-image-selection-core';
import {
  RemoteSelectionIndexedDbStore,
  RemoteSelectionStoreError,
  type RemoteSelectionServerFileState,
  type RemoteSelectionSourceItemRecord,
} from './remote-selection-store.ts';

const PUBLIC_CONTROL_PREFIX = '/selection-api/api/v1/remote-manual-selections';
const MAX_RECONCILE_PAGES = 1_000;

export interface RemoteSelectionOperationOutcome {
  readonly operation: {
    readonly operationId: string;
    readonly commandChecksumSha256: string;
    readonly status: 'applied' | 'superseded';
    readonly appliedServerRevision: number;
    readonly outcomeCode: string;
  };
  readonly batch: {
    readonly batchId: string;
    readonly serverRevision: number;
    readonly lastClientSequence: number;
  };
  readonly file: RemoteSelectionServerFileState | null;
  readonly exactRetry: boolean;
}

export interface RemoteSelectionStateDeltaResponse {
  readonly batch: {
    readonly batchId: string;
    readonly serverRevision: number;
    readonly lastClientSequence: number;
    readonly status: 'indexing' | 'active' | 'finalizing' | 'completed';
  };
  readonly files: readonly RemoteSelectionServerFileState[];
  readonly nextRevision: number;
  readonly hasMore: boolean;
  readonly lastHeartbeatAt: string | null;
  readonly queue: {
    readonly pendingOperationCount: number;
    readonly uploadingTransferCount: number;
    readonly pendingTransferBytes: number;
    readonly materializingActionCount: number;
    readonly pendingHostActionCount: number;
    readonly syncedFileCount: number;
    readonly conflictFileCount: number;
    readonly recoveryFindings: readonly {
      readonly code: string;
      readonly count: number;
    }[];
  };
}

export function nextRemoteSelectionPollDelay(input: {
  readonly idlePolls: number;
  readonly online: boolean;
  readonly pending: boolean;
}): number {
  if (!input.online) return 15_000;
  if (input.pending) return 1_000;
  const exponent = Math.max(0, Math.min(3, Math.floor(input.idlePolls)));
  return Math.min(15_000, 2_000 * 2 ** exponent);
}

export interface RemoteSelectionControlTransport {
  applyOperation(
    command: RemoteManualSelectionOperationCommandV1,
  ): Promise<RemoteSelectionOperationOutcome>;
  getStateDelta(
    batchId: string,
    sinceRevision: number,
  ): Promise<RemoteSelectionStateDeltaResponse>;
}

export interface RemoteSelectionFinalizePreview {
  readonly batchId: string;
  readonly status: 'active' | 'finalizing' | 'completed';
  readonly serverRevision: number;
  readonly ready: boolean;
  readonly totalFileCount: number;
  readonly selectedFileCount: number;
  readonly syncedFileCount: number;
  readonly operationCount: number;
  readonly blockers: readonly {
    readonly code: string;
    readonly count: number;
  }[];
}

export interface RemoteSelectionFinalizedResult {
  readonly batch: {
    readonly batchId: string;
    readonly status: 'completed';
    readonly serverRevision: number;
  };
  readonly finalizedAt: string;
  readonly finalManifestChecksumSha256: string;
  readonly exactRetry: boolean;
}

export class RemoteSelectionControlApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'RemoteSelectionControlApiError';
    this.code = code;
    this.status = status;
  }
}

export class FetchRemoteSelectionControlTransport implements RemoteSelectionControlTransport {
  private readonly clientInstanceId: string;
  private readonly fetchImplementation: typeof globalThis.fetch;

  constructor(
    clientInstanceId: string,
    fetchImplementation: typeof globalThis.fetch = globalThis.fetch,
  ) {
    this.clientInstanceId = clientInstanceId;
    this.fetchImplementation = fetchImplementation;
  }

  async createCollection(input: {
    readonly collectionId: string;
    readonly sessionId: string;
    readonly name: string;
  }): Promise<{ readonly collectionId: string; readonly created: boolean }> {
    return this.json(`${PUBLIC_CONTROL_PREFIX}/collections`, {
      body: JSON.stringify(input),
      method: 'POST',
    });
  }

  async createBatch(
    collectionId: string,
    input: {
      readonly batchId: string;
      readonly sessionId: string;
      readonly name: string;
      readonly sourceManifestChecksumSha256: string;
      readonly firstLayout: number;
      readonly direction: 'ascending' | 'descending';
      readonly totalFileCount: number;
    },
  ): Promise<{
    readonly batch: { readonly batchId: string; readonly status: string };
    readonly created: boolean;
    readonly resumed: boolean;
  }> {
    return this.json(
      `${PUBLIC_CONTROL_PREFIX}/collections/${collectionId}/batches`,
      { body: JSON.stringify(input), method: 'POST' },
    );
  }

  async registerSourceItems(
    sessionId: string,
    batchId: string,
    sourceKind: 'directory_handle' | 'webkitdirectory_reselect',
    items: readonly RemoteSelectionSourceItemRecord[],
    complete: boolean,
  ): Promise<{
    readonly acceptedFileIds: readonly string[];
    readonly createdCount: number;
    readonly totalFileCount: number;
    readonly batch: { readonly batchId: string; readonly status: string };
  }> {
    return this.json(
      `${PUBLIC_CONTROL_PREFIX}/batches/${batchId}/source-items`,
      {
        body: JSON.stringify({
          complete,
          items: items.map((item) => ({
            fileId: item.fileId,
            lastModifiedMs: item.lastModifiedMs,
            mimeType: item.mimeType,
            relativePath: item.relativePath,
            sizeBytes: item.sizeBytes,
            sourceIndex: item.ordinal,
          })),
          sessionId,
          sourceKind,
        }),
        method: 'POST',
      },
    );
  }

  async registerCompleteSourceManifest(
    sessionId: string,
    batchId: string,
    sourceKind: 'directory_handle' | 'webkitdirectory_reselect',
    items: readonly RemoteSelectionSourceItemRecord[],
    pageSize = 100,
  ): Promise<void> {
    if (
      items.length === 0 ||
      !Number.isSafeInteger(pageSize) ||
      pageSize < 1 ||
      pageSize > 500
    ) {
      throw new RemoteSelectionControlApiError(
        422,
        'REMOTE_SELECTION_SOURCE_PAGE_INVALID',
        'A remote selection source page must contain between 1 and 500 items.',
      );
    }
    for (let offset = 0; offset < items.length; offset += pageSize) {
      const page = items.slice(offset, offset + pageSize);
      const complete = offset + page.length === items.length;
      const response = await this.registerSourceItems(
        sessionId,
        batchId,
        sourceKind,
        page,
        complete,
      );
      const expectedIds = page.map((item) => item.fileId);
      if (
        response.batch.batchId !== batchId ||
        response.acceptedFileIds.length !== expectedIds.length ||
        response.acceptedFileIds.some(
          (fileId, index) => fileId !== expectedIds[index],
        ) ||
        (complete && response.batch.status !== 'active')
      ) {
        throw new RemoteSelectionControlApiError(
          502,
          'REMOTE_SELECTION_SOURCE_CONFIRMATION_MISMATCH',
          'The server did not confirm the exact source metadata page.',
        );
      }
    }
  }

  async applyOperation(
    command: RemoteManualSelectionOperationCommandV1,
  ): Promise<RemoteSelectionOperationOutcome> {
    return this.json<RemoteSelectionOperationOutcome>(
      `${PUBLIC_CONTROL_PREFIX}/batches/${command.batchId}/operations`,
      {
        body: JSON.stringify(command),
        method: 'POST',
      },
    );
  }

  async getStateDelta(
    batchId: string,
    sinceRevision: number,
  ): Promise<RemoteSelectionStateDeltaResponse> {
    const query = new URLSearchParams({
      limit: '100',
      sinceRevision: String(sinceRevision),
    });
    return this.json<RemoteSelectionStateDeltaResponse>(
      `${PUBLIC_CONTROL_PREFIX}/batches/${batchId}/state?${query}`,
      { method: 'GET' },
    );
  }

  async finalizePreview(
    batchId: string,
  ): Promise<RemoteSelectionFinalizePreview> {
    return this.json<RemoteSelectionFinalizePreview>(
      `${PUBLIC_CONTROL_PREFIX}/batches/${batchId}/finalize-preview`,
      { method: 'GET' },
    );
  }

  async finalizeBatch(input: {
    readonly batchId: string;
    readonly sessionId: string;
    readonly expectedServerRevision: number;
  }): Promise<RemoteSelectionFinalizedResult> {
    return this.json<RemoteSelectionFinalizedResult>(
      `${PUBLIC_CONTROL_PREFIX}/batches/${input.batchId}/finalize`,
      {
        body: JSON.stringify({
          expectedServerRevision: input.expectedServerRevision,
          sessionId: input.sessionId,
        }),
        method: 'POST',
      },
    );
  }

  private async json<T>(path: string, init: RequestInit): Promise<T> {
    const headers = new Headers(init.headers);
    headers.set('Accept', 'application/json');
    headers.set('X-Remote-Selection-Client', this.clientInstanceId);
    if (init.body !== undefined)
      headers.set('Content-Type', 'application/json');
    const response = await this.fetchImplementation(path, {
      ...init,
      cache: 'no-store',
      credentials: 'same-origin',
      headers,
    });
    const payload = (await response.json().catch(() => null)) as unknown;
    if (!response.ok) {
      const error = isRecord(payload) ? payload : {};
      throw new RemoteSelectionControlApiError(
        response.status,
        typeof error.code === 'string'
          ? error.code
          : 'REMOTE_SELECTION_CONTROL_REQUEST_FAILED',
        typeof error.message === 'string'
          ? error.message
          : 'Remote selection control request failed.',
      );
    }
    if (!isRecord(payload)) {
      throw new RemoteSelectionControlApiError(
        502,
        'REMOTE_SELECTION_CONTROL_RESPONSE_INVALID',
        'Remote selection control response is invalid.',
      );
    }
    return payload as T;
  }
}

export interface RemoteSelectionDrainResult {
  readonly confirmedCount: number;
  readonly pendingCount: number;
  readonly conflictOperationId: string | null;
  readonly conflictCode: string | null;
}

export class RemoteSelectionOutboxSynchronizer {
  private readonly store: RemoteSelectionIndexedDbStore;
  private readonly transport: RemoteSelectionControlTransport;
  private latestState: RemoteSelectionStateDeltaResponse | null = null;

  constructor(
    store: RemoteSelectionIndexedDbStore,
    transport: RemoteSelectionControlTransport,
  ) {
    this.store = store;
    this.transport = transport;
  }

  status(): RemoteSelectionStateDeltaResponse | null {
    return this.latestState;
  }

  async reconcile(
    sessionId: string,
    batchId: string,
    clientInstanceId: string,
  ): Promise<number> {
    const client = await this.store.loadClientInstance(
      sessionId,
      batchId,
      clientInstanceId,
    );
    if (client === null) return 0;
    let revision = client.lastKnownServerRevision;
    for (let page = 0; page < MAX_RECONCILE_PAGES; page += 1) {
      const delta = await this.transport.getStateDelta(batchId, revision);
      validateStateDelta(delta, batchId, revision);
      this.latestState = delta;
      await this.store.applyServerStateDelta({
        batchId,
        clientInstanceId,
        files: delta.files,
        nextRevision: delta.nextRevision,
        sessionId,
        status: delta.batch.status,
      });
      revision = delta.nextRevision;
      if (!delta.hasMore) return revision;
    }
    throw new RemoteSelectionControlApiError(
      502,
      'REMOTE_SELECTION_STATE_DELTA_UNBOUNDED',
      'Remote selection state reconciliation exceeded its page limit.',
    );
  }

  async drain(
    sessionId: string,
    batchId: string,
    clientInstanceId: string,
    pageSize = 25,
  ): Promise<RemoteSelectionDrainResult> {
    let confirmedCount = 0;
    while (true) {
      const page = await this.store.listOutboxPage(
        sessionId,
        batchId,
        0,
        pageSize,
      );
      if (page.length === 0) {
        return {
          confirmedCount,
          conflictCode: null,
          conflictOperationId: null,
          pendingCount: 0,
        };
      }
      for (const record of page) {
        if (record.state === 'conflict') {
          return {
            confirmedCount,
            conflictCode: record.lastErrorCode,
            conflictOperationId: record.operationId,
            pendingCount: await this.store.countPendingOperations(
              sessionId,
              batchId,
            ),
          };
        }
        await this.store.markOutboxOperation(
          sessionId,
          batchId,
          record.operationId,
          'sending',
          null,
        );
        try {
          const outcome = await this.transport.applyOperation(record.command);
          validateOperationOutcome(outcome, record);
          await this.store.confirmOperation({
            batchId,
            clientInstanceId,
            commandChecksumSha256: record.commandChecksumSha256,
            file: outcome.file,
            operationId: record.operationId,
            serverRevision: outcome.batch.serverRevision,
            sessionId,
          });
          confirmedCount += 1;
        } catch (cause) {
          const code = errorCode(cause);
          const conflict = isControlledConflict(cause);
          await this.store.markOutboxOperation(
            sessionId,
            batchId,
            record.operationId,
            conflict ? 'conflict' : 'pending',
            code,
          );
          if (conflict) {
            try {
              await this.reconcile(sessionId, batchId, clientInstanceId);
            } catch {
              // The original conflicting operation remains durable even when
              // the diagnostic delta cannot currently be fetched.
            }
          }
          return {
            confirmedCount,
            conflictCode: conflict ? code : null,
            conflictOperationId: conflict ? record.operationId : null,
            pendingCount: await this.store.countPendingOperations(
              sessionId,
              batchId,
            ),
          };
        }
      }
    }
  }
}

function validateOperationOutcome(
  outcome: RemoteSelectionOperationOutcome,
  record: {
    readonly batchId: string;
    readonly operationId: string;
    readonly commandChecksumSha256: string;
    readonly command: {
      readonly batchId: string;
      readonly clientSequence: number;
      readonly sessionId: string;
    };
  },
): void {
  if (
    !isRecord(outcome) ||
    !isRecord(outcome.operation) ||
    !isRecord(outcome.batch) ||
    outcome.operation.operationId !== record.operationId ||
    outcome.operation.commandChecksumSha256 !== record.commandChecksumSha256 ||
    outcome.batch.batchId !== record.batchId ||
    record.command.batchId !== record.batchId ||
    !['applied', 'superseded'].includes(outcome.operation.status) ||
    !isNonNegativeSafeInteger(outcome.operation.appliedServerRevision) ||
    !isNonNegativeSafeInteger(outcome.batch.serverRevision) ||
    !isNonNegativeSafeInteger(outcome.batch.lastClientSequence) ||
    outcome.operation.appliedServerRevision > outcome.batch.serverRevision ||
    outcome.batch.lastClientSequence < record.command.clientSequence ||
    (outcome.file !== null &&
      (!isRecord(outcome.file) ||
        outcome.file.sessionId !== record.command.sessionId ||
        outcome.file.batchId !== record.batchId ||
        !isNonNegativeSafeInteger(outcome.file.selectionGeneration) ||
        (outcome.file.lastServerRevision !== null &&
          (!isNonNegativeSafeInteger(outcome.file.lastServerRevision) ||
            outcome.file.lastServerRevision > outcome.batch.serverRevision))))
  ) {
    throw new RemoteSelectionControlApiError(
      502,
      'REMOTE_SELECTION_CONFIRMATION_MISMATCH',
      'The server did not confirm the exact outbox operation.',
    );
  }
}

function isNonNegativeSafeInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && (value as number) >= 0;
}

function validateStateDelta(
  delta: RemoteSelectionStateDeltaResponse,
  batchId: string,
  previousRevision: number,
): void {
  if (
    !isRecord(delta) ||
    !isRecord(delta.batch) ||
    !isRecord(delta.queue) ||
    !Array.isArray(delta.files) ||
    !Array.isArray(delta.queue.recoveryFindings) ||
    !isNonNegativeSafeInteger(delta.nextRevision) ||
    typeof delta.hasMore !== 'boolean' ||
    delta.batch.batchId !== batchId ||
    !isNonNegativeSafeInteger(delta.batch.serverRevision) ||
    !isNonNegativeSafeInteger(delta.batch.lastClientSequence) ||
    !isNonNegativeSafeInteger(delta.queue.pendingOperationCount) ||
    !isNonNegativeSafeInteger(delta.queue.uploadingTransferCount) ||
    !isNonNegativeSafeInteger(delta.queue.pendingTransferBytes) ||
    !isNonNegativeSafeInteger(delta.queue.materializingActionCount) ||
    !isNonNegativeSafeInteger(delta.queue.pendingHostActionCount) ||
    !isNonNegativeSafeInteger(delta.queue.syncedFileCount) ||
    !isNonNegativeSafeInteger(delta.queue.conflictFileCount) ||
    (delta.lastHeartbeatAt !== null &&
      typeof delta.lastHeartbeatAt !== 'string') ||
    delta.queue.recoveryFindings.some(
      (finding) =>
        !isRecord(finding) ||
        typeof finding.code !== 'string' ||
        !isNonNegativeSafeInteger(finding.count),
    ) ||
    !['indexing', 'active', 'finalizing', 'completed'].includes(
      delta.batch.status,
    ) ||
    delta.nextRevision < previousRevision ||
    delta.nextRevision > delta.batch.serverRevision ||
    delta.files.some((file) => {
      if (!isRecord(file)) return true;
      const revision = file.lastServerRevision;
      return (
        typeof revision !== 'number' ||
        !Number.isSafeInteger(revision) ||
        revision <= previousRevision ||
        revision > delta.nextRevision
      );
    }) ||
    (delta.hasMore && delta.nextRevision === previousRevision)
  ) {
    throw new RemoteSelectionControlApiError(
      502,
      'REMOTE_SELECTION_STATE_DELTA_INVALID',
      'The canonical state delta is inconsistent.',
    );
  }
}

function isControlledConflict(cause: unknown): boolean {
  return (
    cause instanceof RemoteSelectionStoreError ||
    (cause instanceof RemoteSelectionControlApiError &&
      ((cause.status >= 400 && cause.status < 500 && cause.status !== 429) ||
        cause.status === 502))
  );
}

function errorCode(cause: unknown): string {
  if (
    cause instanceof RemoteSelectionControlApiError ||
    cause instanceof RemoteSelectionStoreError
  ) {
    return cause.code;
  }
  return 'REMOTE_SELECTION_NETWORK_RETRY';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
