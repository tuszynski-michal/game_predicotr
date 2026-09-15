'use client';

import type { SelectedImageAutoCropProposal } from '@game-predictor/manual-image-selection-core/auto-crop';
import { ACTIVE_SELECTED_IMAGE_CROP_POLICY } from '@game-predictor/manual-image-selection-core/crop-preparation';
import {
  CROP_V11_FINGERPRINT,
  CROP_V11_POLICY,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import {
  CROP_V12_FINGERPRINT,
  CROP_V12_POLICY,
  type FourPointCropAnchor,
  type PreparedFourPointRegistrationAnchor,
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

import type { SelectedImageCropRenderedFile } from './selected-image-crop-storage';
import { SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION } from './selected-image-crop-worker-contract.ts';
import { selectedImageCropWorkerConcurrency } from './selected-image-crop-parallelism.ts';

export interface SelectedImageCropWorkerPerformance {
  readonly decodeMs: number;
  readonly analysisMs: number;
  readonly renderMs: number;
  readonly totalMs: number;
}

interface WorkerResult {
  readonly proposal: SelectedImageAutoCropProposal;
  readonly rendered: SelectedImageCropRenderedFile;
  readonly performance: SelectedImageCropWorkerPerformance | null;
}

interface WorkerResultIdentity {
  readonly workerProtocolVersion?: number;
  readonly policyVersion: SelectedImageAutoCropProposal['policyVersion'];
  readonly preparationFingerprint?: string;
}

interface WorkerResponse {
  readonly id: number;
  readonly workerProtocolVersion?: number;
  readonly result?: SelectedImageAutoCropProposal & {
    readonly blob: Blob;
    readonly performance?: SelectedImageCropWorkerPerformance;
  };
  readonly anchor?: PreparedFourPointRegistrationAnchor;
  readonly error?: string;
}

interface WorkerSlot {
  readonly worker: Worker;
  requestCount: number;
  busy: boolean;
  cancel: (() => void) | null;
}

const workerSlots: WorkerSlot[] = [];
const slotWaiters: Array<() => void> = [];
let nextRequestId = 1;
let workerFallbackRequired = false;
let preparedAnchorCache = new WeakMap<
  File,
  Promise<PreparedFourPointRegistrationAnchor | null>
>();

function browserWorkerConcurrency(): number {
  const hardwareConcurrency =
    typeof navigator === 'undefined'
      ? undefined
      : navigator.hardwareConcurrency;
  return selectedImageCropWorkerConcurrency(hardwareConcurrency);
}

export function selectedImageCropAnalysisConcurrency(): number {
  if (
    workerFallbackRequired ||
    typeof Worker === 'undefined' ||
    typeof OffscreenCanvas === 'undefined'
  )
    return 1;
  return browserWorkerConcurrency();
}

export function selectedImageCropWorkerResultMatchesRequest(
  result: WorkerResultIdentity,
  requestedPolicy: string,
): boolean {
  if (
    result.workerProtocolVersion !==
      SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION ||
    result.policyVersion !== requestedPolicy
  )
    return false;
  if (requestedPolicy === CROP_V12_POLICY)
    return result.preparationFingerprint === CROP_V12_FINGERPRINT;
  if (requestedPolicy === CROP_V11_POLICY)
    return result.preparationFingerprint === CROP_V11_FINGERPRINT;
  return true;
}

function createWorkerSlot(): WorkerSlot {
  return {
    worker: new Worker(
      new URL('./selected-image-crop-worker.ts', import.meta.url),
      {
        type: 'module',
      },
    ),
    requestCount: 0,
    busy: false,
    cancel: null,
  };
}

function wakeNextSlotWaiter(): void {
  slotWaiters.shift()?.();
}

function discardWorkerSlot(slot: WorkerSlot): void {
  slot.cancel = null;
  slot.worker.terminate();
  const index = workerSlots.indexOf(slot);
  if (index >= 0) workerSlots.splice(index, 1);
  wakeNextSlotWaiter();
}

function releaseWorkerSlot(slot: WorkerSlot): void {
  if (workerFallbackRequired || slot.requestCount >= 128) {
    discardWorkerSlot(slot);
    return;
  }
  slot.busy = false;
  wakeNextSlotWaiter();
}

function disableWorkerPool(): void {
  workerFallbackRequired = true;
  for (const slot of [...workerSlots]) if (!slot.busy) discardWorkerSlot(slot);
  preparedAnchorCache = new WeakMap();
  while (slotWaiters.length) wakeNextSlotWaiter();
}

export function shutdownSelectedImageCropWorkerPool(): void {
  for (const slot of [...workerSlots]) {
    if (slot.cancel !== null) slot.cancel();
    else discardWorkerSlot(slot);
  }
  workerFallbackRequired = false;
  preparedAnchorCache = new WeakMap();
  while (slotWaiters.length) wakeNextSlotWaiter();
}

async function acquireWorkerSlot(): Promise<WorkerSlot | null> {
  while (true) {
    if (
      workerFallbackRequired ||
      typeof Worker === 'undefined' ||
      typeof OffscreenCanvas === 'undefined'
    )
      return null;
    const available = workerSlots.find((slot) => !slot.busy);
    if (available !== undefined) {
      available.busy = true;
      available.requestCount += 1;
      return available;
    }
    if (workerSlots.length < browserWorkerConcurrency()) {
      const slot = createWorkerSlot();
      slot.busy = true;
      slot.requestCount = 1;
      workerSlots.push(slot);
      return slot;
    }
    await new Promise<void>((resolve) => slotWaiters.push(resolve));
  }
}

async function sendWorkerRequest<T>(
  message: (id: number) => object,
  read: (response: WorkerResponse) => T,
  canRetryStaleWorker: boolean,
): Promise<T | null> {
  const slot = await acquireWorkerSlot();
  if (slot === null) return null;
  const id = nextRequestId++;
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      clearTimeout(timeout);
      slot.cancel = null;
      slot.worker.removeEventListener('message', onMessage);
      slot.worker.removeEventListener('error', onError);
    };
    const recoverFromStaleWorker = () => {
      cleanup();
      discardWorkerSlot(slot);
      if (canRetryStaleWorker) {
        void sendWorkerRequest(message, read, false).then(resolve, reject);
        return;
      }
      disableWorkerPool();
      resolve(null);
    };
    const onMessage = (event: MessageEvent<WorkerResponse>) => {
      if (event.data.id !== id) return;
      if (
        event.data.workerProtocolVersion !==
        SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION
      ) {
        recoverFromStaleWorker();
        return;
      }
      cleanup();
      if (event.data.error !== undefined) {
        releaseWorkerSlot(slot);
        reject(new Error(event.data.error));
        return;
      }
      try {
        const value = read(event.data);
        releaseWorkerSlot(slot);
        resolve(value);
      } catch (cause) {
        if (
          cause instanceof Error &&
          cause.message === 'SELECTED_IMAGE_CROP_WORKER_STALE_RESULT'
        ) {
          recoverFromStaleWorker();
          return;
        }
        releaseWorkerSlot(slot);
        reject(cause);
      }
    };
    const onError = () => {
      cleanup();
      discardWorkerSlot(slot);
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_FAILED'));
    };
    const timeout = setTimeout(() => {
      cleanup();
      discardWorkerSlot(slot);
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_TIMEOUT'));
    }, 120000);
    slot.cancel = () => {
      cleanup();
      discardWorkerSlot(slot);
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_CANCELLED'));
    };
    slot.worker.addEventListener('message', onMessage);
    slot.worker.addEventListener('error', onError);
    slot.worker.postMessage({ id, ...message(id) });
  });
}

async function prepareAnchorInWorker(anchor: {
  readonly source: File;
  readonly descriptor: FourPointCropAnchor;
}): Promise<PreparedFourPointRegistrationAnchor | null> {
  let pending = preparedAnchorCache.get(anchor.source);
  if (pending === undefined) {
    pending = sendWorkerRequest(
      () => ({
        kind: 'prepare_anchor',
        source: anchor.source,
        descriptor: anchor.descriptor,
      }),
      (response) => {
        if (response.anchor === undefined)
          throw new Error('SELECTED_IMAGE_CROP_WORKER_ANCHOR_INVALID');
        return response.anchor;
      },
      true,
    );
    preparedAnchorCache.set(anchor.source, pending);
    void pending.catch(() => {
      if (preparedAnchorCache.get(anchor.source) === pending)
        preparedAnchorCache.delete(anchor.source);
    });
  }
  return pending;
}

export async function prepareSelectedImageCropInWorker(
  source: File,
  policy: string = ACTIVE_SELECTED_IMAGE_CROP_POLICY,
  anchor?: {
    readonly source: File;
    readonly descriptor: FourPointCropAnchor;
  } | null,
): Promise<WorkerResult | null> {
  const preparedAnchor =
    policy === CROP_V12_POLICY && anchor
      ? await prepareAnchorInWorker(anchor)
      : null;
  if (policy === CROP_V12_POLICY && anchor && preparedAnchor === null)
    return null;
  return sendWorkerRequest(
    () => ({
      kind: 'prepare_crop',
      source,
      policy,
      anchor: preparedAnchor,
    }),
    (response) => {
      const result = response.result;
      if (result === undefined)
        throw new Error('SELECTED_IMAGE_CROP_WORKER_RESULT_INVALID');
      if (
        !selectedImageCropWorkerResultMatchesRequest(
          {
            ...result,
            workerProtocolVersion: response.workerProtocolVersion,
          },
          policy,
        )
      )
        throw new Error('SELECTED_IMAGE_CROP_WORKER_STALE_RESULT');
      return {
        proposal: {
          crop: result.crop,
          strategy: result.strategy,
          classification: result.classification,
          confidence: result.confidence,
          policyVersion: result.policyVersion,
          evidence: result.evidence,
          ...(result.structural
            ? {
                structural: result.structural,
                preparationFingerprint: result.preparationFingerprint,
                analysisLevels: result.analysisLevels,
              }
            : {}),
          ...(result.registration ? { registration: result.registration } : {}),
        },
        rendered: {
          blob: result.blob,
          dimensions: {
            width: result.crop.width,
            height: result.crop.bottomY - result.crop.topY,
          },
        },
        performance: result.performance ?? null,
      };
    },
    true,
  );
}
