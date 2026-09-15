import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
  type SelectedImageAutoCropProposal,
} from '@game-predictor/manual-image-selection-core/auto-crop';
import { SELECTED_IMAGE_CROP_JPEG_QUALITY } from '@game-predictor/manual-image-selection-core/crop';
import {
  ACTIVE_SELECTED_IMAGE_CROP_POLICY,
  prepareFourPointRegisteredCrop,
  prepareStructuralCrop,
  assertCropPreparationPolicy,
} from '@game-predictor/manual-image-selection-core/crop-preparation';
import { CROP_V11_POLICY } from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import {
  CROP_V12_POLICY,
  type FourPointCropAnchor,
} from '@game-predictor/manual-image-selection-core/auto-crop-v12-registration';

import { SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION } from './selected-image-crop-worker-contract.ts';

interface PrepareRequest {
  readonly id: number;
  readonly source: File;
  readonly policy: string;
  readonly anchor: {
    readonly source: File;
    readonly descriptor: FourPointCropAnchor;
  } | null;
}

interface WorkerScope {
  onmessage: ((event: MessageEvent<PrepareRequest>) => void) | null;
  postMessage(message: unknown): void;
}

const scope = globalThis as unknown as WorkerScope;

scope.onmessage = (event) => {
  void prepare(event.data)
    .then((result) =>
      scope.postMessage({
        id: event.data.id,
        workerProtocolVersion: SELECTED_IMAGE_CROP_WORKER_PROTOCOL_VERSION,
        result,
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

async function prepare(
  request: PrepareRequest,
): Promise<SelectedImageAutoCropProposal & { readonly blob: Blob }> {
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
    const sourceSample = {
      width: sampleWidth,
      height: sampleHeight,
      rgba: pixels.data,
    };
    let anchorBitmap: ImageBitmap | null = null;
    const proposal =
      policy === CROP_V12_POLICY
        ? await prepareFourPointRegisteredCrop(
            sourceSample,
            request.anchor === null
              ? null
              : {
                  descriptor: request.anchor.descriptor,
                  image: await (async () => {
                    anchorBitmap = await createImageBitmap(
                      request.anchor!.source,
                      { imageOrientation: 'from-image' },
                    );
                    const canvas = new OffscreenCanvas(
                      anchorBitmap.width,
                      anchorBitmap.height,
                    );
                    const context = canvas.getContext('2d', {
                      alpha: false,
                      willReadFrequently: true,
                    });
                    if (context === null)
                      throw new Error(
                        'SELECTED_IMAGE_AUTO_CROP_CANVAS_UNAVAILABLE',
                      );
                    context.drawImage(anchorBitmap, 0, 0);
                    return {
                      width: anchorBitmap.width,
                      height: anchorBitmap.height,
                      rgba: context.getImageData(
                        0,
                        0,
                        anchorBitmap.width,
                        anchorBitmap.height,
                      ).data,
                    };
                  })(),
                },
            () => new Promise((resolve) => setTimeout(resolve, 0)),
          ).finally(() => anchorBitmap?.close())
        : policy === CROP_V11_POLICY
          ? await prepareStructuralCrop(
              sourceSample,
              () => new Promise((resolve) => setTimeout(resolve, 0)),
            )
          : detectSelectedImageCropBand(
              { width: sampleWidth, height: sampleHeight, rgba: pixels.data },
              { width: bitmap.width, height: bitmap.height },
            );
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
    return { ...proposal, blob };
  } finally {
    bitmap.close();
  }
}
