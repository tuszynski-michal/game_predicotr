import {
  detectSelectedImageCropBand,
  SELECTED_IMAGE_AUTO_CROP_POLICY,
  SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
} from '@game-predictor/manual-image-selection-core/auto-crop';
import {
  SELECTED_IMAGE_CROP_JPEG_QUALITY,
  type SelectedImageCropBand,
} from '@game-predictor/manual-image-selection-core/crop';

interface PrepareRequest {
  readonly id: number;
  readonly source: File;
}

interface WorkerScope {
  onmessage: ((event: MessageEvent<PrepareRequest>) => void) | null;
  postMessage(message: unknown): void;
}

const scope = globalThis as unknown as WorkerScope;

scope.onmessage = (event) => {
  void prepare(event.data)
    .then((result) => scope.postMessage({ id: event.data.id, result }))
    .catch((cause: unknown) =>
      scope.postMessage({
        id: event.data.id,
        error: cause instanceof Error ? cause.message : 'UNKNOWN_ERROR',
      }),
    );
};

async function prepare(request: PrepareRequest): Promise<{
  readonly crop: SelectedImageCropBand;
  readonly strategy: 'chromatic_panel' | 'texture_band' | 'safe_default';
  readonly confidence: number;
  readonly policyVersion: typeof SELECTED_IMAGE_AUTO_CROP_POLICY;
  readonly blob: Blob;
}> {
  const bitmap = await createImageBitmap(request.source, {
    imageOrientation: 'from-image',
  });
  try {
    const sampleWidth = Math.min(
      SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH,
      bitmap.width,
    );
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
    const proposal = detectSelectedImageCropBand(
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
