import type {
  V7LabelGeometrySessionMutation,
  V7LabelGeometrySlotResponse,
} from '@game-predictor/admin-api-client';

export interface PendingV7LabelGeometryOperation
  extends V7LabelGeometrySessionMutation {
  readonly sequence: number;
  readonly sessionId: string;
}

export interface V7LabelGeometryQueueState {
  readonly confirmedRevision: number;
  readonly pending: readonly PendingV7LabelGeometryOperation[];
  readonly stoppedReason: string | null;
}

export type V7LabelGeometryOperationInput = Omit<
  PendingV7LabelGeometryOperation,
  'expectedRevision' | 'sequence'
>;

export function enqueueV7LabelGeometryOperation(
  state: V7LabelGeometryQueueState,
  input: V7LabelGeometryOperationInput,
): V7LabelGeometryQueueState {
  if (state.stoppedReason !== null) {
    throw new Error('V7_LABEL_GEOMETRY_QUEUE_STOPPED');
  }
  const headSequence = state.pending.at(-1)?.sequence ?? -1;
  const operation: PendingV7LabelGeometryOperation = {
    ...input,
    expectedRevision: state.confirmedRevision + state.pending.length,
    sequence: headSequence + 1,
  };
  return { ...state, pending: [...state.pending, operation] };
}

export function nextV7LabelGeometryOperation(
  state: V7LabelGeometryQueueState,
): PendingV7LabelGeometryOperation | null {
  return state.stoppedReason === null ? (state.pending[0] ?? null) : null;
}

export function acknowledgeV7LabelGeometryOperation(
  state: V7LabelGeometryQueueState,
  operationId: string,
  receiptRevision: number,
): V7LabelGeometryQueueState {
  const head = state.pending[0];
  if (head === undefined || head.operationId !== operationId) {
    throw new Error('V7_LABEL_GEOMETRY_QUEUE_RECEIPT_OUT_OF_ORDER');
  }
  if (receiptRevision !== head.expectedRevision + 1) {
    throw new Error('V7_LABEL_GEOMETRY_QUEUE_RECEIPT_REVISION_INVALID');
  }
  return {
    confirmedRevision: receiptRevision,
    pending: state.pending.slice(1),
    stoppedReason: null,
  };
}

export function stopV7LabelGeometryQueue(
  state: V7LabelGeometryQueueState,
  reason: string,
): V7LabelGeometryQueueState {
  return { ...state, stoppedReason: reason };
}

export function resumeV7LabelGeometryQueue(
  state: V7LabelGeometryQueueState,
  confirmedRevision: number,
): V7LabelGeometryQueueState {
  if (state.pending.length !== 0) {
    throw new Error('V7_LABEL_GEOMETRY_QUEUE_PENDING_REBASE_FORBIDDEN');
  }
  return { confirmedRevision, pending: [], stoppedReason: null };
}

export function restoreV7LabelGeometryQueue(
  pending: readonly PendingV7LabelGeometryOperation[],
  serverRevision: number,
  stoppedReason: string | null,
): V7LabelGeometryQueueState {
  if (pending.length === 0) {
    return {
      confirmedRevision: serverRevision,
      pending: [],
      stoppedReason,
    };
  }
  const firstExpectedRevision = pending[0]!.expectedRevision;
  const revisionsAreContiguous = pending.every(
    (operation, index) =>
      operation.expectedRevision === firstExpectedRevision + index &&
      operation.sequence === pending[0]!.sequence + index,
  );
  const maximumKnownServerRevision =
    pending[pending.length - 1]!.expectedRevision + 1;
  if (
    !revisionsAreContiguous ||
    serverRevision < firstExpectedRevision ||
    serverRevision > maximumKnownServerRevision
  ) {
    return {
      confirmedRevision: firstExpectedRevision,
      pending,
      stoppedReason:
        stoppedReason ??
        'Lokalna kolejka nie odpowiada rewizji sesji na serwerze. Odrzuć ją przed wznowieniem.',
    };
  }
  return {
    // The server may have persisted a prefix whose receipt was lost. Replay
    // starts at the immutable expected revision of that first entry; a new
    // click therefore remains after the full persisted prefix.
    confirmedRevision: firstExpectedRevision,
    pending,
    stoppedReason,
  };
}

export function discardPendingV7LabelGeometryOperations(
  state: V7LabelGeometryQueueState,
): V7LabelGeometryQueueState {
  return {
    confirmedRevision: state.confirmedRevision,
    pending: [],
    stoppedReason: null,
  };
}

/**
 * Builds a display-only projection of one source's slots.  The durable queue
 * remains the authority for the operator's immediate intent, while `session`
 * remains the authority for profile readiness and all server-side decisions.
 *
 * A browser refresh restores the same pending operations from IndexedDB, so a
 * projected marker never becomes a transient, in-memory-only annotation.
 */
export function projectV7LabelGeometryPendingSlots(
  confirmedSlots: readonly V7LabelGeometrySlotResponse[],
  pending: readonly PendingV7LabelGeometryOperation[],
  sourceId: string,
): readonly V7LabelGeometrySlotResponse[] {
  const slots = new Map<number, V7LabelGeometrySlotResponse>(
    confirmedSlots
      .filter((slot) => slot.sourceId === sourceId)
      .map((slot) => [slot.positionIndex, slot]),
  );

  for (const operation of pending) {
    if (
      operation.sourceId !== sourceId ||
      operation.positionIndex === undefined ||
      operation.positionIndex === null
    ) {
      continue;
    }
    if (operation.kind === 'annotated') {
      if (operation.centerX === undefined || operation.centerY === undefined) {
        continue;
      }
      slots.set(operation.positionIndex, {
        centerX: operation.centerX,
        centerY: operation.centerY,
        cropAssessment: operation.cropAssessment ?? null,
        positionIndex: operation.positionIndex,
        sourceId,
        state: 'annotated',
      });
      continue;
    }
    if (operation.kind === 'unavailable') {
      slots.set(operation.positionIndex, {
        centerX: null,
        centerY: null,
        cropAssessment: null,
        positionIndex: operation.positionIndex,
        sourceId,
        state: 'unavailable',
      });
    }
  }
  return [...slots.values()].sort(
    (left, right) => left.positionIndex - right.positionIndex,
  );
}

export function normaliseV7LabelGeometryPoint(
  clientX: number,
  clientY: number,
  rect: Pick<DOMRect, 'height' | 'left' | 'top' | 'width'>,
): { readonly centerX: number; readonly centerY: number } {
  if (!(rect.width > 0) || !(rect.height > 0)) {
    throw new Error('V7_LABEL_GEOMETRY_IMAGE_RECT_INVALID');
  }
  return {
    centerX: clampUnit((clientX - rect.left) / rect.width),
    centerY: clampUnit((clientY - rect.top) / rect.height),
  };
}

export function isV7LabelGeometryPointInsideServerBounds(point: {
  readonly centerX: number;
  readonly centerY: number;
}): boolean {
  return (
    point.centerX > 0 &&
    point.centerX < 1 &&
    point.centerY > 0 &&
    point.centerY < 1
  );
}

/**
 * The durable browser record has sequencing fields which the server contract
 * deliberately rejects. Build the HTTP body explicitly instead of relying on
 * structural typing to drop those fields during JSON serialization.
 */
export function toV7LabelGeometrySessionMutation(
  operation: PendingV7LabelGeometryOperation,
): V7LabelGeometrySessionMutation {
  return {
    expectedRevision: operation.expectedRevision,
    kind: operation.kind,
    operationId: operation.operationId,
    sourceId: operation.sourceId,
    ...(operation.captureGroupId === undefined
      ? {}
      : { captureGroupId: operation.captureGroupId }),
    ...(operation.centerX === undefined ? {} : { centerX: operation.centerX }),
    ...(operation.centerY === undefined ? {} : { centerY: operation.centerY }),
    ...(operation.cropAssessment === undefined
      ? {}
      : { cropAssessment: operation.cropAssessment }),
    ...(operation.positionIndex === undefined
      ? {}
      : { positionIndex: operation.positionIndex }),
  };
}

/**
 * An object URL may only be used for the exact source that requested it. The
 * checksum prevents a delayed response for an old version of a source from
 * becoming clickable after the session has changed selection.
 */
export function v7LabelGeometryAssetKey(
  sessionId: string,
  sourceId: string,
  sourceChecksumSha256: string,
): string {
  return JSON.stringify([sessionId, sourceId, sourceChecksumSha256]);
}

function clampUnit(value: number): number {
  if (!Number.isFinite(value)) {
    throw new Error('V7_LABEL_GEOMETRY_POINT_INVALID');
  }
  return Math.min(1, Math.max(0, value));
}
