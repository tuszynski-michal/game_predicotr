'use client';

import type {
  PendingV7LabelGeometryOperation,
  V7LabelGeometryQueueState,
} from './v7-label-geometry-calibration-queue.ts';
import { restoreV7LabelGeometryQueue } from './v7-label-geometry-calibration-queue.ts';

export type V7LabelGeometryCropAssessment =
  | 'contained'
  | 'clipped'
  | 'uncertain';

export interface V7LabelGeometryCalibrationLocalView {
  readonly activePositionIndex: number;
  readonly activeSourceId: string | null;
  readonly cropAssessment: V7LabelGeometryCropAssessment;
  readonly manifestFingerprint: string;
  readonly queueStoppedReason?: string | null;
  readonly sessionId: string;
  readonly updatedAt: string;
}

interface V7LabelGeometryQueueRecord extends PendingV7LabelGeometryOperation {
  readonly key: [string, number];
}

export interface V7LabelGeometryCalibrationLocalState {
  readonly queue: V7LabelGeometryQueueState;
  readonly view: V7LabelGeometryCalibrationLocalView;
}

const DATABASE_NAME = 'game-predictor-v7-label-geometry-calibration';
const DATABASE_VERSION = 1;
const QUEUE_STORE = 'queue';
const VIEW_STORE = 'views';

export class V7LabelGeometryCalibrationLocalStore {
  constructor(
    private readonly factory: IDBFactory | undefined = globalThis.indexedDB,
  ) {}

  async load(
    sessionId: string,
    confirmedRevision: number,
  ): Promise<V7LabelGeometryCalibrationLocalState | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const [view, records] = await Promise.all([
        requestResult<V7LabelGeometryCalibrationLocalView | null>(
          database.transaction(VIEW_STORE, 'readonly').objectStore(VIEW_STORE).get(sessionId),
        ),
        requestAll<V7LabelGeometryQueueRecord>(
          database.transaction(QUEUE_STORE, 'readonly').objectStore(QUEUE_STORE),
        ),
      ]);
      if (view === null) return null;
      const pending = records
        .filter((record) => record.sessionId === sessionId)
        .sort((left, right) => left.sequence - right.sequence)
        .map(toPendingOperation);
      return {
        queue: restoreV7LabelGeometryQueue(
          pending,
          confirmedRevision,
          view.queueStoppedReason ?? null,
        ),
        view,
      };
    } finally {
      database.close();
    }
  }

  async loadMostRecent(): Promise<V7LabelGeometryCalibrationLocalView | null> {
    if (this.factory === undefined) return null;
    const database = await this.open();
    try {
      const views = await requestAll<V7LabelGeometryCalibrationLocalView>(
        database.transaction(VIEW_STORE, 'readonly').objectStore(VIEW_STORE),
      );
      return (
        [...views].sort((left, right) => {
          const timestamp = Date.parse(right.updatedAt) - Date.parse(left.updatedAt);
          return timestamp || right.sessionId.localeCompare(left.sessionId);
        })[0] ?? null
      );
    } finally {
      database.close();
    }
  }

  async saveView(view: V7LabelGeometryCalibrationLocalView): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(VIEW_STORE, 'readwrite');
      transaction.objectStore(VIEW_STORE).put(view);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async appendOperation(
    operation: PendingV7LabelGeometryOperation,
  ): Promise<void> {
    if (this.factory === undefined) {
      throw new Error('V7_LABEL_GEOMETRY_INDEXED_DB_UNAVAILABLE');
    }
    const database = await this.open();
    try {
      const transaction = database.transaction(QUEUE_STORE, 'readwrite');
      transaction.objectStore(QUEUE_STORE).add({
        ...operation,
        key: [operation.sessionId, operation.sequence],
      } satisfies V7LabelGeometryQueueRecord);
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  async removeHead(
    sessionId: string,
    sequence: number,
    operationId: string,
  ): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const transaction = database.transaction(QUEUE_STORE, 'readwrite');
      const store = transaction.objectStore(QUEUE_STORE);
      const key: [string, number] = [sessionId, sequence];
      const completion = transactionComplete(transaction);
      try {
        await deleteMatchingHead(store, key, operationId, transaction);
        await completion;
      } catch (cause) {
        await completion.catch(() => undefined);
        throw cause;
      }
    } finally {
      database.close();
    }
  }

  async discardPending(sessionId: string): Promise<void> {
    if (this.factory === undefined) return;
    const database = await this.open();
    try {
      const existing = await requestAll<V7LabelGeometryQueueRecord>(
        database.transaction(QUEUE_STORE, 'readonly').objectStore(QUEUE_STORE),
      );
      const transaction = database.transaction(QUEUE_STORE, 'readwrite');
      const store = transaction.objectStore(QUEUE_STORE);
      for (const record of existing) {
        if (record.sessionId === sessionId) store.delete(record.key);
      }
      await transactionComplete(transaction);
    } finally {
      database.close();
    }
  }

  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = this.factory?.open(DATABASE_NAME, DATABASE_VERSION);
      if (request === undefined) {
        reject(new Error('V7_LABEL_GEOMETRY_INDEXED_DB_UNAVAILABLE'));
        return;
      }
      request.onupgradeneeded = () => {
        if (!request.result.objectStoreNames.contains(VIEW_STORE)) {
          request.result.createObjectStore(VIEW_STORE, { keyPath: 'sessionId' });
        }
        if (!request.result.objectStoreNames.contains(QUEUE_STORE)) {
          request.result.createObjectStore(QUEUE_STORE, { keyPath: 'key' });
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(request.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_OPEN_FAILED'));
    });
  }
}

function toPendingOperation(
  record: V7LabelGeometryQueueRecord,
): PendingV7LabelGeometryOperation {
  return {
    captureGroupId: record.captureGroupId,
    centerX: record.centerX,
    centerY: record.centerY,
    cropAssessment: record.cropAssessment,
    expectedRevision: record.expectedRevision,
    kind: record.kind,
    operationId: record.operationId,
    positionIndex: record.positionIndex,
    sequence: record.sequence,
    sessionId: record.sessionId,
    sourceId: record.sourceId,
  };
}

function deleteMatchingHead(
  store: IDBObjectStore,
  key: [string, number],
  operationId: string,
  transaction: IDBTransaction,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = store.get(key);
    request.onsuccess = () => {
      const existing = request.result as V7LabelGeometryQueueRecord | undefined;
      if (existing?.operationId !== operationId) {
        transaction.abort();
        reject(new Error('V7_LABEL_GEOMETRY_LOCAL_QUEUE_HEAD_CHANGED'));
        return;
      }
      store.delete(key);
      resolve();
    };
    request.onerror = () =>
      reject(
        request.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_READ_FAILED'),
      );
  });
}

function requestResult<T>(request: IDBRequest): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve((request.result ?? null) as T);
    request.onerror = () =>
      reject(request.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_READ_FAILED'));
  });
}

function requestAll<T>(store: IDBObjectStore): Promise<T[]> {
  return new Promise((resolve, reject) => {
    const request = store.getAll();
    request.onsuccess = () => resolve(request.result as T[]);
    request.onerror = () =>
      reject(request.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_READ_FAILED'));
  });
}

function transactionComplete(transaction: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onabort = () =>
      reject(transaction.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_ABORTED'));
    transaction.onerror = () =>
      reject(transaction.error ?? new Error('V7_LABEL_GEOMETRY_INDEXED_DB_FAILED'));
  });
}
