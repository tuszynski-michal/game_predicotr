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
  prepareSelectedImageCropInWorker,
  selectedImageCropWorkerResultMatchesRequest,
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
        policyVersion: CROP_V11_POLICY,
        preparationFingerprint: CROP_V11_FINGERPRINT,
      },
      CROP_V12_POLICY,
    ),
    false,
  );
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
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
    if (originalOffscreenCanvas === undefined)
      delete globalThis.OffscreenCanvas;
    else globalThis.OffscreenCanvas = originalOffscreenCanvas;
  }
});
