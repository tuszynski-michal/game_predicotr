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
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

import type { SelectedImageCropRenderedFile } from './selected-image-crop-storage';
import { SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION } from './selected-image-crop-worker-contract.ts';

interface WorkerResult {
  readonly proposal: SelectedImageAutoCropProposal;
  readonly rendered: SelectedImageCropRenderedFile;
}

interface WorkerResultIdentity {
  readonly workerProtocolVersion?: number;
  readonly policyVersion: SelectedImageAutoCropProposal['policyVersion'];
  readonly preparationFingerprint?: string;
}

let activeWorker: Worker | null = null;
let requestCount = 0;
let nextRequestId = 1;
let workerFallbackRequired = false;

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

export async function prepareSelectedImageCropInWorker(
  source: File,
  policy: string = ACTIVE_SELECTED_IMAGE_CROP_POLICY,
  anchor?: {
    readonly source: File;
    readonly descriptor: FourPointCropAnchor;
  } | null,
): Promise<WorkerResult | null> {
  return prepareSelectedImageCropInWorkerAttempt(source, policy, anchor, true);
}

async function prepareSelectedImageCropInWorkerAttempt(
  source: File,
  policy: string,
  anchor:
    | {
        readonly source: File;
        readonly descriptor: FourPointCropAnchor;
      }
    | null
    | undefined,
  canRetryStaleWorker: boolean,
): Promise<WorkerResult | null> {
  if (
    workerFallbackRequired ||
    typeof Worker === 'undefined' ||
    typeof OffscreenCanvas === 'undefined'
  )
    return null;
  if (activeWorker === null || requestCount >= 128) {
    activeWorker?.terminate();
    activeWorker = new Worker(
      new URL('./selected-image-crop-worker.ts', import.meta.url),
      { type: 'module' },
    );
    requestCount = 0;
  }
  const worker = activeWorker;
  const id = nextRequestId++;
  requestCount += 1;
  return new Promise((resolve, reject) => {
    const recoverFromStaleWorker = () => {
      worker.terminate();
      if (activeWorker === worker) activeWorker = null;
      if (canRetryStaleWorker) {
        void prepareSelectedImageCropInWorkerAttempt(
          source,
          policy,
          anchor,
          false,
        ).then(resolve, reject);
        return;
      }
      workerFallbackRequired = true;
      resolve(null);
    };
    const timeout = setTimeout(() => {
      cleanup();
      worker.terminate();
      activeWorker = null;
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_TIMEOUT'));
    }, 120000);
    const onMessage = (
      event: MessageEvent<{
        readonly id: number;
        readonly workerProtocolVersion?: number;
        readonly result?: {
          readonly crop: SelectedImageAutoCropProposal['crop'];
          readonly strategy: SelectedImageAutoCropProposal['strategy'];
          readonly classification: SelectedImageAutoCropProposal['classification'];
          readonly confidence: number | null;
          readonly structural?: SelectedImageAutoCropProposal['structural'];
          readonly registration?: SelectedImageAutoCropProposal['registration'];
          readonly preparationFingerprint?: string;
          readonly analysisLevels?: readonly number[];
          readonly policyVersion: SelectedImageAutoCropProposal['policyVersion'];
          readonly evidence: SelectedImageAutoCropProposal['evidence'];
          readonly blob: Blob;
        };
        readonly error?: string;
      }>,
    ) => {
      if (event.data.id !== id) return;
      cleanup();
      if (
        event.data.workerProtocolVersion !==
        SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION
      ) {
        recoverFromStaleWorker();
        return;
      }
      if (event.data.error !== undefined) {
        reject(new Error(event.data.error));
        return;
      }
      const result = event.data.result;
      if (result === undefined) {
        reject(new Error('SELECTED_IMAGE_CROP_WORKER_RESULT_INVALID'));
        return;
      }
      if (
        !selectedImageCropWorkerResultMatchesRequest(
          {
            ...result,
            workerProtocolVersion: event.data.workerProtocolVersion,
          },
          policy,
        )
      ) {
        recoverFromStaleWorker();
        return;
      }
      resolve({
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
      });
    };
    const onError = () => {
      cleanup();
      worker.terminate();
      if (activeWorker === worker) activeWorker = null;
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_FAILED'));
    };
    const cleanup = () => {
      clearTimeout(timeout);
      worker.removeEventListener('message', onMessage);
      worker.removeEventListener('error', onError);
    };
    worker.addEventListener('message', onMessage);
    worker.addEventListener('error', onError);
    worker.postMessage({ id, source, policy, anchor: anchor ?? null });
  });
}
