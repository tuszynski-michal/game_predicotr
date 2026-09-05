'use client';

import type { SelectedImageAutoCropProposal } from '@game-predictor/manual-image-selection-core/auto-crop';
import { SELECTED_IMAGE_AUTO_CROP_POLICY } from '@game-predictor/manual-image-selection-core/auto-crop';

import type { SelectedImageCropRenderedFile } from './selected-image-crop-storage';

interface WorkerResult {
  readonly proposal: SelectedImageAutoCropProposal;
  readonly rendered: SelectedImageCropRenderedFile;
}

let activeWorker: Worker | null = null;
let requestCount = 0;
let nextRequestId = 1;

export async function prepareSelectedImageCropInWorker(
  source: File,
  policy: string = SELECTED_IMAGE_AUTO_CROP_POLICY,
): Promise<WorkerResult | null> {
  if (typeof Worker === 'undefined' || typeof OffscreenCanvas === 'undefined')
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
    const timeout = setTimeout(() => {
      cleanup();
      worker.terminate();
      activeWorker = null;
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_TIMEOUT'));
    }, 120000);
    const onMessage = (
      event: MessageEvent<{
        readonly id: number;
        readonly result?: {
          readonly crop: SelectedImageAutoCropProposal['crop'];
          readonly strategy: SelectedImageAutoCropProposal['strategy'];
          readonly classification: SelectedImageAutoCropProposal['classification'];
          readonly confidence: number | null;
          readonly structural?: SelectedImageAutoCropProposal['structural'];
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
      if (event.data.error !== undefined) {
        reject(new Error(event.data.error));
        return;
      }
      const result = event.data.result;
      if (result === undefined) {
        reject(new Error('SELECTED_IMAGE_CROP_WORKER_RESULT_INVALID'));
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
      activeWorker?.terminate();
      activeWorker = null;
      reject(new Error('SELECTED_IMAGE_CROP_WORKER_FAILED'));
    };
    const cleanup = () => {
      clearTimeout(timeout);
      worker.removeEventListener('message', onMessage);
      worker.removeEventListener('error', onError);
    };
    worker.addEventListener('message', onMessage);
    worker.addEventListener('error', onError);
    worker.postMessage({ id, source, policy });
  });
}
