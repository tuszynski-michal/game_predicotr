import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CROP_V11_FINGERPRINT,
  CROP_V11_POLICY,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import {
  CROP_V12_FINGERPRINT,
  CROP_V12_POLICY,
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';
import {
  CROP_V13_FINGERPRINT,
  CROP_V13_POLICY,
} from '@game-predictor/manual-image-selection-core/auto-crop-v13-minimum-height';

import {
  prepareSelectedImageCropInWorker,
  selectedImageCropWorkerResultMatchesRequest,
  shutdownSelectedImageCropWorkerPool,
} from '../src/features/semi-automatic-image-selection/selected-image-crop-worker-client.ts';
import { SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION } from '../src/features/semi-automatic-image-selection/selected-image-crop-worker-contract.ts';

test('worker result identity binds protocol, policy and detector fingerprint', () => {
  assert.equal(
    selectedImageCropWorkerResultMatchesRequest(
      {
        policyVersion: CROP_V12_POLICY,
        preparationFingerprint: CROP_V12_FINGERPRINT,
      },
      CROP_V12_POLICY,
    ),
    false,
  );
  assert.equal(
    selectedImageCropWorkerResultMatchesRequest(
      {
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        policyVersion: CROP_V12_POLICY,
        preparationFingerprint: `${CROP_V12_FINGERPRINT}-stale`,
      },
      CROP_V12_POLICY,
    ),
    false,
  );
  assert.equal(
    selectedImageCropWorkerResultMatchesRequest(
      {
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        policyVersion: CROP_V12_POLICY,
        preparationFingerprint: CROP_V12_FINGERPRINT,
      },
      CROP_V12_POLICY,
    ),
    true,
  );
  assert.equal(
    selectedImageCropWorkerResultMatchesRequest(
      {
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        policyVersion: CROP_V13_POLICY,
        preparationFingerprint: CROP_V13_FINGERPRINT,
      },
      CROP_V13_POLICY,
    ),
    true,
  );
  assert.equal(
    selectedImageCropWorkerResultMatchesRequest(
      {
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        policyVersion: CROP_V11_POLICY,
        preparationFingerprint: CROP_V11_FINGERPRINT,
      },
      CROP_V12_POLICY,
    ),
    false,
  );
});

test('four crop requests share one prepared anchor and occupy four worker slots', async () => {
  const originalWorker = globalThis.Worker;
  const originalOffscreenCanvas = globalThis.OffscreenCanvas;
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(
    globalThis,
    'navigator',
  );
  let created = 0;
  let activeCropRequests = 0;
  let maximumActiveCropRequests = 0;
  let anchorRequests = 0;
  const descriptor = {
    sourceName: 'anchor.jpg',
    sourceChecksumSha256: 'a'.repeat(64),
    sourceWidth: 100,
    sourceHeight: 200,
    boardBand: [
      { x: 10, y: 20 },
      { x: 90, y: 20 },
      { x: 10, y: 160 },
      { x: 90, y: 160 },
    ],
    medianBoardHeight: 40,
  };
  const preparedAnchor = {
    anchor: descriptor,
    analysis: {
      width: 100,
      height: 200,
      gray: new Uint8Array(20_000),
      scaleX: 1,
      scaleY: 1,
    },
    band: descriptor.boardBand,
    featureBand: descriptor.boardBand,
    features: [],
  };

  class ParallelWorker {
    listeners = new Map();

    constructor() {
      created += 1;
    }

    addEventListener(type, listener) {
      this.listeners.set(type, listener);
    }

    removeEventListener(type, listener) {
      if (this.listeners.get(type) === listener) this.listeners.delete(type);
    }

    terminate() {}

    postMessage(message) {
      if (message.kind === 'prepare_anchor') {
        anchorRequests += 1;
        queueMicrotask(() =>
          this.listeners.get('message')?.({
            data: {
              id: message.id,
              workerProtocolVersion:
                SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
              anchor: preparedAnchor,
            },
          }),
        );
        return;
      }
      activeCropRequests += 1;
      maximumActiveCropRequests = Math.max(
        maximumActiveCropRequests,
        activeCropRequests,
      );
      setImmediate(() => {
        activeCropRequests -= 1;
        this.listeners.get('message')?.({
          data: {
            id: message.id,
            workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
            result: {
              crop: { width: 100, height: 200, topY: 20, bottomY: 180 },
              strategy: 'safe_wide',
              classification: 'safe_wide',
              confidence: null,
              policyVersion: CROP_V12_POLICY,
              preparationFingerprint: CROP_V12_FINGERPRINT,
              evidence: {
                sampleWidth: 100,
                sampleHeight: 200,
                localBounds: [],
                chromaticCandidateCount: 0,
                structuralCandidateCount: 0,
                chromaticSupportedStrips: [],
                structuralSupportedStrips: [],
                evidenceIoU: null,
                boundaryExpanded: false,
                fallbackReason: 'no_candidate',
                selectionBasis: 'safe_wide',
                topBoardRowCandidateCount: 0,
                topBoardRowTopRatio: null,
              },
              blob: new Blob(['rendered']),
            },
          },
        });
      });
    }
  }

  Object.defineProperty(globalThis, 'navigator', {
    configurable: true,
    value: { hardwareConcurrency: 16 },
  });
  globalThis.Worker = ParallelWorker;
  globalThis.OffscreenCanvas = class {};
  shutdownSelectedImageCropWorkerPool();
  try {
    const anchor = { source: { name: 'anchor.jpg' }, descriptor };
    const results = await Promise.all(
      Array.from({ length: 4 }, (_, index) =>
        prepareSelectedImageCropInWorker(
          { name: `source-${index}.jpg` },
          CROP_V12_POLICY,
          anchor,
        ),
      ),
    );
    assert.equal(
      results.every((result) => result !== null),
      true,
    );
    assert.equal(anchorRequests, 1);
    assert.equal(created, 4);
    assert.equal(maximumActiveCropRequests, 4);
  } finally {
    shutdownSelectedImageCropWorkerPool();
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
    if (originalOffscreenCanvas === undefined)
      delete globalThis.OffscreenCanvas;
    else globalThis.OffscreenCanvas = originalOffscreenCanvas;
    if (navigatorDescriptor === undefined) delete globalThis.navigator;
    else Object.defineProperty(globalThis, 'navigator', navigatorDescriptor);
  }
});

test('shutting down the pool cancels an active request without waiting for timeout', async () => {
  const originalWorker = globalThis.Worker;
  const originalOffscreenCanvas = globalThis.OffscreenCanvas;
  class HangingWorker {
    addEventListener() {}
    removeEventListener() {}
    postMessage() {}
    terminate() {}
  }
  globalThis.Worker = HangingWorker;
  globalThis.OffscreenCanvas = class {};
  shutdownSelectedImageCropWorkerPool();
  try {
    const pending = prepareSelectedImageCropInWorker(
      { name: 'source.jpg' },
      CROP_V12_POLICY,
    );
    await new Promise((resolve) => setImmediate(resolve));
    shutdownSelectedImageCropWorkerPool();
    await assert.rejects(pending, /SELECTED_IMAGE_CROP_WORKER_CANCELLED/u);
  } finally {
    shutdownSelectedImageCropWorkerPool();
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
    if (originalOffscreenCanvas === undefined)
      delete globalThis.OffscreenCanvas;
    else globalThis.OffscreenCanvas = originalOffscreenCanvas;
  }
});

test('a stale worker gets one fresh retry before bounded main-thread fallback', async () => {
  const originalWorker = globalThis.Worker;
  const originalOffscreenCanvas = globalThis.OffscreenCanvas;
  let created = 0;
  let terminated = 0;
  let forceStale = false;

  class VersionedWorker {
    listeners = new Map();
    instanceNumber;

    constructor() {
      created += 1;
      this.instanceNumber = created;
    }

    addEventListener(type, listener) {
      this.listeners.set(type, listener);
    }

    removeEventListener(type, listener) {
      if (this.listeners.get(type) === listener) this.listeners.delete(type);
    }

    terminate() {
      terminated += 1;
    }

    postMessage(message) {
      const stale = this.instanceNumber === 1 || forceStale;
      queueMicrotask(() =>
        this.listeners.get('message')?.({
          data: {
            id: message.id,
            workerProtocolVersion: stale
              ? 0
              : SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
            result: {
              crop: { width: 100, height: 200, topY: 20, bottomY: 180 },
              strategy: 'safe_wide',
              classification: 'safe_wide',
              confidence: null,
              policyVersion: CROP_V12_POLICY,
              preparationFingerprint: stale
                ? `${CROP_V12_FINGERPRINT}-stale`
                : CROP_V12_FINGERPRINT,
              evidence: {
                sampleWidth: 100,
                sampleHeight: 200,
                localBounds: [],
                chromaticCandidateCount: 0,
                structuralCandidateCount: 0,
                chromaticSupportedStrips: [],
                structuralSupportedStrips: [],
                evidenceIoU: null,
                boundaryExpanded: false,
                fallbackReason: 'no_candidate',
                selectionBasis: 'safe_wide',
                topBoardRowCandidateCount: 0,
                topBoardRowTopRatio: null,
              },
              blob: new Blob(['rendered']),
            },
          },
        }),
      );
    }
  }

  globalThis.Worker = VersionedWorker;
  globalThis.OffscreenCanvas = class {};
  shutdownSelectedImageCropWorkerPool();
  try {
    const recovered = await prepareSelectedImageCropInWorker(
      { name: 'source.jpg' },
      CROP_V12_POLICY,
    );
    assert.notEqual(recovered, null);
    assert.equal(recovered.proposal.policyVersion, CROP_V12_POLICY);
    assert.equal(created, 2);
    assert.equal(terminated, 1);

    forceStale = true;
    assert.equal(
      await prepareSelectedImageCropInWorker(
        { name: 'next.jpg' },
        CROP_V12_POLICY,
      ),
      null,
    );
    assert.equal(created, 3);
    assert.equal(terminated, 3);
    assert.equal(
      await prepareSelectedImageCropInWorker(
        { name: 'after-fallback.jpg' },
        CROP_V12_POLICY,
      ),
      null,
    );
    assert.equal(created, 3);
  } finally {
    shutdownSelectedImageCropWorkerPool();
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
    if (originalOffscreenCanvas === undefined)
      delete globalThis.OffscreenCanvas;
    else globalThis.OffscreenCanvas = originalOffscreenCanvas;
  }
});
