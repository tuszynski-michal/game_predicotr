'use client';

import {
  REMOTE_SELECTION_OPERATION_SCHEMA,
  normalizeRemoteSourcePath,
  type RemoteManualSelectionOperationCommandV1,
} from '@game-predictor/manual-image-selection-core';
import type {
  RemoteSelectionOutboxRecord,
  RemoteSelectionSourceItemRecord,
  RemoteSelectionTransferCheckpointRecord,
  RemoteSelectionWorkspaceDecision,
} from './remote-selection-store.ts';

export type RemoteWorkspaceItemStatus =
  | 'unselected'
  | 'selected_local'
  | 'pending'
  | 'confirmed'
  | 'synced'
  | 'error';

export interface RemoteWorkspaceStatusView {
  readonly kind: RemoteWorkspaceItemStatus;
  readonly label: string;
}

export function remoteWorkspaceItemStatus(input: {
  readonly item: RemoteSelectionSourceItemRecord;
  readonly decisions: readonly RemoteSelectionWorkspaceDecision[];
  readonly outbox: readonly RemoteSelectionOutboxRecord[];
  readonly checkpoint?: RemoteSelectionTransferCheckpointRecord | null;
}): RemoteWorkspaceStatusView {
  const decision = [...input.decisions]
    .reverse()
    .find(
      (candidate) =>
        candidate.action === 'accepted' &&
        candidate.fileId === input.item.fileId,
    );
  const operation =
    decision === undefined
      ? undefined
      : input.outbox.find(
          (candidate) => candidate.operationId === decision.operationId,
        );
  if (
    operation?.state === 'conflict' ||
    input.checkpoint?.status === 'failed' ||
    input.item.serverStatus === 'failed'
  ) {
    return { kind: 'error', label: 'Błąd — wymaga uwagi' };
  }
  if (decision !== undefined && operation?.state === 'pending') {
    return { kind: 'pending', label: 'Oczekuje na hosta' };
  }
  if (decision !== undefined && operation?.state === 'sending') {
    return { kind: 'pending', label: 'Wysyłanie decyzji' };
  }
  if (
    input.item.desiredSelected === true &&
    input.item.serverStatus === 'synced'
  ) {
    return { kind: 'synced', label: 'Zsynchronizowano' };
  }
  if (
    input.item.desiredSelected === true ||
    input.checkpoint?.status === 'queued' ||
    input.checkpoint?.status === 'uploading' ||
    input.checkpoint?.status === 'verified'
  ) {
    return { kind: 'confirmed', label: 'Potwierdzono — plik w tle' };
  }
  if (decision !== undefined) {
    return { kind: 'selected_local', label: 'Wybrano lokalnie' };
  }
  return { kind: 'unselected', label: 'Niewybrane' };
}

export function buildRemoteWorkspaceCommand(input: {
  readonly operationId: string;
  readonly sessionId: string;
  readonly batchId: string;
  readonly clientInstanceId: string;
  readonly clientSequence: number;
  readonly expectedServerRevision: number;
  readonly operationType: 'viewed' | 'select' | 'skip' | 'undo';
  readonly selectionGeneration: number;
  readonly rangeStart: number;
  readonly sourceIndex: number;
  readonly fileId: string | null;
  readonly imagePath: string | null;
  readonly imageChecksumSha256: string | null;
  readonly outputName: string | null;
  readonly visibleMilliseconds: number;
  readonly decoded: boolean;
  readonly targetOperationId?: string | null;
  readonly recordedAt?: string;
}): RemoteManualSelectionOperationCommandV1 {
  const imagePath =
    input.imagePath === null
      ? null
      : normalizeRemoteSourcePath(input.imagePath);
  return {
    schemaVersion: REMOTE_SELECTION_OPERATION_SCHEMA,
    batchId: input.batchId,
    clientInstanceId: input.clientInstanceId,
    clientSequence: input.clientSequence,
    decoded: input.decoded,
    expectedServerRevision: input.expectedServerRevision,
    fileId: input.fileId,
    imageChecksumSha256: input.imageChecksumSha256,
    imagePath,
    operationId: input.operationId,
    operationType: input.operationType,
    outputName: input.outputName,
    rangeEnd: input.rangeStart + 8,
    rangeStart: input.rangeStart,
    recordedAt: input.recordedAt ?? new Date().toISOString(),
    selectionGeneration: input.selectionGeneration,
    sessionId: input.sessionId,
    sourceIndex: input.sourceIndex,
    targetOperationId: input.targetOperationId ?? null,
    visibleMilliseconds: Math.max(0, Math.round(input.visibleMilliseconds)),
  };
}

export async function sha256File(file: File): Promise<string> {
  const digest = await crypto.subtle.digest(
    'SHA-256',
    await file.arrayBuffer(),
  );
  return Array.from(new Uint8Array(digest), (byte) =>
    byte.toString(16).padStart(2, '0'),
  ).join('');
}

export function remoteOutputName(rangeStart: number): string {
  return `seq_${rangeStart}-${rangeStart + 8}.jpg`;
}

export function clampRemoteWorkspaceIndex(
  current: number,
  delta: number,
  count: number,
): number {
  return Math.max(0, Math.min(count - 1, current + delta));
}

export function advanceRemoteTransferScanCursor(input: {
  readonly currentCursor: number;
  readonly scanStartCursor: number;
  readonly scannedThroughOrdinal: number;
}): number {
  return input.currentCursor === input.scanStartCursor
    ? input.scannedThroughOrdinal
    : input.currentCursor;
}
