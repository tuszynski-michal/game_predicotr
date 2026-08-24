import type { RemoteSelectionIndexedDbStore } from './remote-selection-store.ts';

const DEFAULT_MAX_CONCURRENCY = 2;
const DEFAULT_MAX_PENDING_BYTES = 256 * 1024 * 1024;
const DEFAULT_MAX_ATTEMPTS = 5;
const DEFAULT_BASE_BACKOFF_MS = 750;

export type RemoteSelectionTransferStatus =
  | 'not_started'
  | 'queued'
  | 'uploading'
  | 'stored_temp'
  | 'verified'
  | 'synced'
  | 'cancelled'
  | 'failed'
  | 'retrying';

export interface RemoteSelectionTransferResponse {
  readonly transferId: string | null;
  readonly batchId: string;
  readonly fileId: string;
  readonly generation: number;
  readonly attempt: number;
  readonly declaredBytes: number;
  readonly receivedBytes: number;
  readonly status: RemoteSelectionTransferStatus;
  readonly declaredChecksumSha256: string | null;
  readonly verifiedChecksumSha256: string | null;
}

export interface RemoteSelectionTransferTask {
  readonly sessionId: string;
  readonly batchId: string;
  readonly fileId: string;
  readonly generation: number;
  readonly sourceRelativePath: string;
  readonly expectedSizeBytes: number;
  readonly expectedLastModifiedMs: number;
  readonly expectedChecksumSha256: string;
  readonly priority: number;
  readonly loadBlob: () => Promise<Blob>;
}

export interface RemoteSelectionTransferTransport {
  status(
    task: RemoteSelectionTransferTask,
    transferId: string,
    signal: AbortSignal,
  ): Promise<RemoteSelectionTransferResponse>;
  upload(
    task: RemoteSelectionTransferTask,
    transferId: string,
    blob: Blob,
    signal: AbortSignal,
  ): Promise<RemoteSelectionTransferResponse>;
}

export interface RemoteSelectionTransferSchedulerOptions {
  readonly maxConcurrency?: number;
  readonly maxPendingBytes?: number;
  readonly maxAttempts?: number;
  readonly baseBackoffMs?: number;
  readonly random?: () => number;
  readonly sleep?: (milliseconds: number) => Promise<void>;
  readonly createTransferId?: () => string;
}

interface QueueItem {
  readonly task: RemoteSelectionTransferTask;
  readonly transferId: string;
  readonly ordinal: number;
  readonly controller: AbortController;
}

export class RemoteSelectionTransferHttpError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'RemoteSelectionTransferHttpError';
    this.status = status;
    this.code = code;
  }
}

export class RemoteSelectionTransferScheduler {
  private readonly maxConcurrency: number;
  private readonly maxPendingBytes: number;
  private readonly maxAttempts: number;
  private readonly baseBackoffMs: number;
  private readonly random: () => number;
  private readonly sleep: (milliseconds: number) => Promise<void>;
  private readonly createTransferId: () => string;
  private readonly queue: QueueItem[] = [];
  private readonly active = new Map<string, QueueItem>();
  private pendingBytes = 0;
  private ordinal = 0;
  private readonly transport: RemoteSelectionTransferTransport;
  private readonly store: Pick<
    RemoteSelectionIndexedDbStore,
    'loadTransferCheckpoint' | 'saveTransferCheckpoint'
  >;

  constructor(
    transport: RemoteSelectionTransferTransport,
    store: Pick<
      RemoteSelectionIndexedDbStore,
      'loadTransferCheckpoint' | 'saveTransferCheckpoint'
    >,
    options: RemoteSelectionTransferSchedulerOptions = {},
  ) {
    this.transport = transport;
    this.store = store;
    this.maxConcurrency = positiveInteger(
      options.maxConcurrency ?? DEFAULT_MAX_CONCURRENCY,
      'maxConcurrency',
    );
    this.maxPendingBytes = positiveInteger(
      options.maxPendingBytes ?? DEFAULT_MAX_PENDING_BYTES,
      'maxPendingBytes',
    );
    this.maxAttempts = positiveInteger(
      options.maxAttempts ?? DEFAULT_MAX_ATTEMPTS,
      'maxAttempts',
    );
    this.baseBackoffMs = positiveInteger(
      options.baseBackoffMs ?? DEFAULT_BASE_BACKOFF_MS,
      'baseBackoffMs',
    );
    this.random = options.random ?? Math.random;
    this.sleep = options.sleep ?? delay;
    this.createTransferId =
      options.createTransferId ?? (() => crypto.randomUUID());
  }

  async enqueue(task: RemoteSelectionTransferTask): Promise<boolean> {
    validateTask(task);
    const key = transferKey(task);
    if (
      this.active.has(key) ||
      this.queue.some((item) => transferKey(item.task) === key)
    ) {
      return false;
    }
    if (this.pendingBytes + task.expectedSizeBytes > this.maxPendingBytes) {
      throw new RemoteSelectionTransferHttpError(
        429,
        'REMOTE_SELECTION_TRANSFER_BACKPRESSURE',
        'The local transfer queue byte budget is exhausted.',
      );
    }
    const restored = await this.store.loadTransferCheckpoint(
      task.sessionId,
      task.batchId,
      task.fileId,
      task.generation,
    );
    if (
      this.active.has(key) ||
      this.queue.some((item) => transferKey(item.task) === key)
    ) {
      return false;
    }
    const item = {
      task,
      transferId:
        restored?.transferId && restored.transferId.length > 0
          ? restored.transferId
          : this.createTransferId(),
      ordinal: this.ordinal++,
      controller: new AbortController(),
    };
    this.queue.push(item);
    this.pendingBytes += task.expectedSizeBytes;
    this.queue.sort(compareQueueItems);
    await this.store.saveTransferCheckpoint(
      checkpoint(
        task,
        item.transferId,
        restored?.acknowledgedBytes ?? 0,
        'queued',
      ),
    );
    this.pump();
    return true;
  }

  cancel(fileId: string, generation: number): boolean {
    const keySuffix = `:${fileId}:${generation}`;
    const queueIndex = this.queue.findIndex((item) =>
      transferKey(item.task).endsWith(keySuffix),
    );
    if (queueIndex >= 0) {
      const [item] = this.queue.splice(queueIndex, 1);
      if (item !== undefined) this.pendingBytes -= item.task.expectedSizeBytes;
      return true;
    }
    const active = [...this.active.entries()].find(([key]) =>
      key.endsWith(keySuffix),
    );
    if (active === undefined) return false;
    active[1].controller.abort();
    return true;
  }

  snapshot(): {
    readonly active: number;
    readonly queued: number;
    readonly pendingBytes: number;
  } {
    return {
      active: this.active.size,
      queued: this.queue.length,
      pendingBytes: this.pendingBytes,
    };
  }

  private pump(): void {
    while (this.active.size < this.maxConcurrency && this.queue.length > 0) {
      const item = this.queue.shift();
      if (item === undefined) return;
      const key = transferKey(item.task);
      this.active.set(key, item);
      void this.run(item).finally(() => {
        this.active.delete(key);
        this.pendingBytes -= item.task.expectedSizeBytes;
        this.pump();
      });
    }
  }

  private async run(item: QueueItem): Promise<void> {
    const { task, transferId, controller } = item;
    for (let attempt = 1; attempt <= this.maxAttempts; attempt += 1) {
      if (controller.signal.aborted) return;
      try {
        const status = await this.transport.status(
          task,
          transferId,
          controller.signal,
        );
        if (status.status === 'verified' || status.status === 'synced') {
          await this.store.saveTransferCheckpoint(
            checkpoint(task, transferId, task.expectedSizeBytes, 'verified'),
          );
          return;
        }
        const blob = await task.loadBlob();
        assertFreshBlob(task, blob);
        await this.store.saveTransferCheckpoint(
          checkpoint(task, transferId, 0, 'uploading'),
        );
        const uploaded = await this.transport.upload(
          task,
          transferId,
          blob,
          controller.signal,
        );
        if (uploaded.status !== 'verified' && uploaded.status !== 'synced') {
          throw new RemoteSelectionTransferHttpError(
            502,
            'REMOTE_SELECTION_TRANSFER_NOT_VERIFIED',
            'The transfer response did not confirm verification.',
          );
        }
        await this.store.saveTransferCheckpoint(
          checkpoint(task, transferId, task.expectedSizeBytes, 'verified'),
        );
        return;
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (!isRetryableTransferError(cause) || attempt === this.maxAttempts) {
          await this.store.saveTransferCheckpoint(
            checkpoint(task, transferId, 0, 'failed'),
          );
          return;
        }
        await this.sleep(
          retryDelayMs(attempt, this.baseBackoffMs, this.random),
        );
      }
    }
  }
}

export class FetchRemoteSelectionTransferTransport implements RemoteSelectionTransferTransport {
  private readonly clientInstanceId: string;
  private readonly fetchImplementation: typeof globalThis.fetch;
  private readonly apiPrefix: string;

  constructor(
    clientInstanceId: string,
    fetchImplementation: typeof globalThis.fetch = globalThis.fetch,
    apiPrefix = '/selection-api/api/v1/remote-manual-selections',
  ) {
    this.clientInstanceId = clientInstanceId;
    this.fetchImplementation = fetchImplementation;
    this.apiPrefix = apiPrefix;
  }

  async status(
    task: RemoteSelectionTransferTask,
    transferId: string,
    signal: AbortSignal,
  ): Promise<RemoteSelectionTransferResponse> {
    const parameters = new URLSearchParams({
      generation: String(task.generation),
      transferId,
    });
    return this.request(`${this.fileUrl(task)}/transfer?${parameters}`, {
      headers: this.baseHeaders(),
      method: 'GET',
      signal,
    });
  }

  async upload(
    task: RemoteSelectionTransferTask,
    transferId: string,
    blob: Blob,
    signal: AbortSignal,
  ): Promise<RemoteSelectionTransferResponse> {
    const headers = this.baseHeaders();
    headers.set('Content-Type', 'application/octet-stream');
    headers.set('X-Remote-Selection-Transfer-Id', transferId);
    headers.set('X-Remote-Selection-Generation', String(task.generation));
    headers.set(
      'X-Remote-Selection-Source-Mtime',
      String(task.expectedLastModifiedMs),
    );
    headers.set(
      'X-Remote-Selection-Checksum-Sha256',
      task.expectedChecksumSha256,
    );
    return this.request(`${this.fileUrl(task)}/content`, {
      body: blob,
      headers,
      method: 'PUT',
      signal,
    });
  }

  private fileUrl(task: RemoteSelectionTransferTask): string {
    return `${this.apiPrefix}/batches/${task.batchId}/files/${task.fileId}`;
  }

  private baseHeaders(): Headers {
    return new Headers({
      Accept: 'application/json',
      'X-Remote-Selection-Client': this.clientInstanceId,
    });
  }

  private async request(
    url: string,
    init: RequestInit,
  ): Promise<RemoteSelectionTransferResponse> {
    const response = await this.fetchImplementation(url, init);
    const payload = (await response.json()) as Record<string, unknown>;
    if (!response.ok) {
      throw new RemoteSelectionTransferHttpError(
        response.status,
        typeof payload.code === 'string'
          ? payload.code
          : 'REMOTE_SELECTION_TRANSFER_FAILED',
        typeof payload.message === 'string'
          ? payload.message
          : 'The transfer request failed.',
      );
    }
    return payload as unknown as RemoteSelectionTransferResponse;
  }
}

export function isRetryableTransferError(cause: unknown): boolean {
  if (cause instanceof DOMException && cause.name === 'AbortError')
    return false;
  if (cause instanceof RemoteSelectionTransferHttpError) {
    return (
      cause.status === 408 ||
      cause.status === 425 ||
      cause.status === 429 ||
      cause.status >= 500
    );
  }
  return cause instanceof TypeError;
}

export function retryDelayMs(
  attempt: number,
  baseBackoffMs = DEFAULT_BASE_BACKOFF_MS,
  random: () => number = Math.random,
): number {
  const exponential = baseBackoffMs * 2 ** Math.max(0, attempt - 1);
  return Math.round(
    exponential * (0.75 + Math.max(0, Math.min(1, random())) * 0.5),
  );
}

function checkpoint(
  task: RemoteSelectionTransferTask,
  transferId: string,
  acknowledgedBytes: number,
  status: 'queued' | 'uploading' | 'verified' | 'failed',
) {
  return {
    schemaVersion: 1 as const,
    sessionId: task.sessionId,
    batchId: task.batchId,
    fileId: task.fileId,
    generation: task.generation,
    sourceRelativePath: task.sourceRelativePath,
    expectedSizeBytes: task.expectedSizeBytes,
    expectedChecksumSha256: task.expectedChecksumSha256,
    acknowledgedBytes,
    transferId,
    status,
    updatedAt: new Date().toISOString(),
  };
}

function assertFreshBlob(task: RemoteSelectionTransferTask, blob: Blob): void {
  if (blob.size !== task.expectedSizeBytes) {
    throw new RemoteSelectionTransferHttpError(
      409,
      'REMOTE_SELECTION_SOURCE_CHANGED',
      'The local source size changed after selection.',
    );
  }
  if (
    typeof File !== 'undefined' &&
    blob instanceof File &&
    blob.lastModified !== task.expectedLastModifiedMs
  ) {
    throw new RemoteSelectionTransferHttpError(
      409,
      'REMOTE_SELECTION_SOURCE_CHANGED',
      'The local source modification time changed after selection.',
    );
  }
}

function validateTask(task: RemoteSelectionTransferTask): void {
  if (
    !Number.isSafeInteger(task.generation) ||
    task.generation < 1 ||
    !Number.isSafeInteger(task.expectedSizeBytes) ||
    task.expectedSizeBytes < 1 ||
    !/^[0-9a-f]{64}$/.test(task.expectedChecksumSha256)
  ) {
    throw new RemoteSelectionTransferHttpError(
      422,
      'REMOTE_SELECTION_TRANSFER_TASK_INVALID',
      'The transfer task metadata is invalid.',
    );
  }
}

function transferKey(task: RemoteSelectionTransferTask): string {
  return `${task.sessionId}:${task.batchId}:${task.fileId}:${task.generation}`;
}

function compareQueueItems(left: QueueItem, right: QueueItem): number {
  return (
    left.task.priority - right.task.priority || left.ordinal - right.ordinal
  );
}

function positiveInteger(value: number, name: string): number {
  if (!Number.isSafeInteger(value) || value < 1) {
    throw new TypeError(`${name} must be a positive integer.`);
  }
  return value;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}
