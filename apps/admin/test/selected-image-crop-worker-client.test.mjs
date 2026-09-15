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

test('a stale worker is terminated once and the current tab keeps using fallback', async () => {
  const originalWorker = globalThis.Worker;
  const originalOffscreenCanvas = globalThis.OffscreenCanvas;
  let created = 0;
  let terminated = 0;

  class StaleWorker {
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

    terminate() {
      terminated += 1;
    }

    postMessage(message) {
      queueMicrotask(() =>
        this.listeners.get('message')?.({
          data: {
            id: message.id,
            workerProtocolVersion: 0,
            result: {
              policyVersion: CROP_V12_POLICY,
              preparationFingerprint: `${CROP_V12_FINGERPRINT}-stale`,
            },
          },
        }),
      );
    }
  }

  globalThis.Worker = StaleWorker;
  globalThis.OffscreenCanvas = class {};
  try {
    assert.equal(
      await prepareSelectedImageCropInWorker(
        { name: 'source.jpg' },
        CROP_V12_POLICY,
      ),
      null,
    );
    assert.equal(terminated, 1);
    assert.equal(
      await prepareSelectedImageCropInWorker(
        { name: 'next.jpg' },
        CROP_V12_POLICY,
      ),
      null,
    );
    assert.equal(created, 1);
  } finally {
    if (originalWorker === undefined) delete globalThis.Worker;
    else globalThis.Worker = originalWorker;
    if (originalOffscreenCanvas === undefined) delete globalThis.OffscreenCanvas;
    else globalThis.OffscreenCanvas = originalOffscreenCanvas;
  }
});
