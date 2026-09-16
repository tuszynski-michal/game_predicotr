import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';
import { SELECTED_IMAGE_CROP_JPEG_QUALITY } from '@game-predictor/manual-image-selection-core/crop';
import {
  ACTIVE_SELECTED_IMAGE_CROP_POLICY,
  assertCropPreparationPolicy,
  finishFourPointRegisteredCrop,
  prepareStructuralCrop,
} from '@game-predictor/manual-image-selection-core/crop-preparation';
import { CROP_V11_POLICY } from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import {
  CROP_V12_POLICY,
  prepareFourPointRegistrationAnchor,
  type FourPointCropAnchor,
  type PreparedFourPointRegistrationAnchor,
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

import { SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION } from './selected-image-crop-worker-contract.ts';

interface PrepareCropRequest {
  readonly id: number;
  readonly kind: 'prepare_crop';
  readonly source: File;
  readonly policy: string;
  readonly anchor: PreparedFourPointRegistrationAnchor | null;
}

interface PrepareAnchorRequest {
  readonly id: number;
  readonly kind: 'prepare_anchor';
  readonly source: File;
  readonly descriptor: FourPointCropAnchor;
}

type WorkerRequest = PrepareCropRequest | PrepareAnchorRequest;

interface WorkerScope {
  onmessage: ((event: MessageEvent<WorkerRequest>) => void) | null;
  postMessage(message: unknown): void;
}

const scope = globalThis as unknown as WorkerScope;

scope.onmessage = (event) => {
  const operation =
    event.data.kind === 'prepare_anchor'
      ? prepareAnchor(event.data).then((anchor) => ({ anchor }))
      : prepareCrop(event.data).then((result) => ({ result }));
  void operation
    .then((payload) =>
      scope.postMessage({
        id: event.data.id,
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        ...payload,
      }),
    )
    .catch((cause: unknown) =>
      scope.postMessage({
        id: event.data.id,
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        error: cause instanceof Error ? cause.message : 'UNKNOWN_ERROR',
      }),
    );
};

async function decodeSample(source: File): Promise<{
  readonly bitmap: ImageBitmap;
  readonly sample: { width: number; height: number; rgba: Uint8ClampedArray };
}> {
  const bitmap = await createImageBitmap(source, {
    imageOrientation: 'from-image',
  });
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  const context = canvas.getContext('2d', {
    alpha: false,
    willReadFrequently: true,
  });
  if (context === null) {
    bitmap.close();
    throw new Error('SELECTED_IMAGE_AUTO_CROP_CANVAS_UNAVAILABLE');
  }
  context.drawImage(bitmap, 0, 0);
  return {
    bitmap,
    sample: {
      width: bitmap.width,
      height: bitmap.height,
      rgba: context.getImageData(0, 0, bitmap.width, bitmap.height).data,
    },
  };
}

async function prepareAnchor(
  request: PrepareAnchorRequest,
): Promise<PreparedFourPointRegistrationAnchor> {
  const decoded = await decodeSample(request.source);
  try {
    return prepareFourPointRegistrationAnchor({
      anchor: request.descriptor,
      anchorImage: decoded.sample,
    });
  } finally {
    decoded.bitmap.close();
  }
}

async function prepareCrop(request: PrepareCropRequest): Promise<
  SelectedImageAutoCropProposal & {
    readonly blob: Blob;
    readonly performance: {
      readonly decodeMs: number;
      readonly analysisMs: number;
      readonly renderMs: number;
      readonly totalMs: number;
    };
  }
> {
  const startedAt = performance.now();
  const policy = request.policy ?? ACTIVE_SELECTED_IMAGE_CROP_POLICY;
  assertCropPreparationPolicy(policy);
  const bitmap = await createImageBitmap(request.source, {
    imageOrientation: 'from-image',
  });
  try {
    const sampleWidth =
      policy === CROP_V11_POLICY || policy === CROP_V12_POLICY
        ? bitmap.width
        : Math.min(SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH, bitmap.width);
    const sampleHeight = Math.max(
      1,
      Math.round((bitmap.height * sampleWidth) / bitmap.width),
    );
    const sampleCanvas = new OffscreenCanvas(sampleWidth, sampleHeight);
    const sampleContext = sampleCanvas.getContext('2d', {
      alpha: false,
      willReadFrequently: true,
    });
    if (sampleContext === null)
      throw new Error('SELECTED_IMAGE_AUTO_CROP_CANVAS_UNAVAILABLE');
    sampleContext.drawImage(bitmap, 0, 0, sampleWidth, sampleHeight);
    const pixels = sampleContext.getImageData(0, 0, sampleWidth, sampleHeight);
    const decodedAt = performance.now();
    const sourceSample = {
      width: sampleWidth,
      height: sampleHeight,
      rgba: pixels.data,
    };
    const noTimerYield = () => Promise.resolve();
    const proposal =
      policy === CROP_V12_POLICY
        ? await (async () => {
            const structural = await prepareStructuralCrop(
              sourceSample,
              noTimerYield,
            );
            return finishFourPointRegisteredCrop(
              sourceSample,
              structural,
              request.anchor === null
                ? null
                : {
                    descriptor: request.anchor.anchor,
                    prepared: request.anchor,
                  },
              noTimerYield,
            );
          })()
        : policy === CROP_V11_POLICY
          ? await prepareStructuralCrop(sourceSample, noTimerYield)
          : detectSelectedImageCropBand(
              { width: sampleWidth, height: sampleHeight, rgba: pixels.data },
              { width: bitmap.width, height: bitmap.height },
            );
    const analyzedAt = performance.now();
    const outputHeight = proposal.crop.bottomY - proposal.crop.topY;
    const outputCanvas = new OffscreenCanvas(bitmap.width, outputHeight);
    const outputContext = outputCanvas.getContext('2d', { alpha: false });
    if (outputContext === null)
      throw new Error('SELECTED_IMAGE_CROP_CANVAS_UNAVAILABLE');
    outputContext.drawImage(
      bitmap,
      0,
      proposal.crop.topY,
      bitmap.width,
      outputHeight,
      0,
      0,
      bitmap.width,
      outputHeight,
    );
    const blob = await outputCanvas.convertToBlob({
      type: 'image/jpeg',
      quality: SELECTED_IMAGE_CROP_JPEG_QUALITY,
    });
    const finishedAt = performance.now();
    return {
      ...proposal,
      blob,
      performance: {
        decodeMs: decodedAt - startedAt,
        analysisMs: analyzedAt - decodedAt,
        renderMs: finishedAt - analyzedAt,
        totalMs: finishedAt - startedAt,
      },
    };
  } finally {
    bitmap.close();
  }
}
