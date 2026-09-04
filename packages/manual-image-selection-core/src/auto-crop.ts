import {
  createDefaultSelectedImageCropBand,
  validateSelectedImageCropBand,
  type SelectedImageCropBand,
  type SelectedImageDimensions,
} from '@game-predictor/manual-image-selection-core/crop';

export const SELECTED_IMAGE_AUTO_CROP_POLICY =
  'selected-image-board-band-v2' as const;
export const SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH = 256 as const;
export const SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO = 0.075 as const;
export const SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO = 0.045 as const;

export type SelectedImageAutoCropStrategy =
  'chromatic_panel' | 'texture_band' | 'safe_default';

export interface SelectedImageAutoCropProposal {
  readonly crop: SelectedImageCropBand;
  readonly strategy: SelectedImageAutoCropStrategy;
  readonly confidence: number;
  readonly policyVersion: typeof SELECTED_IMAGE_AUTO_CROP_POLICY;
}

export interface SelectedImageAutoCropSample {
  readonly width: number;
  readonly height: number;
  readonly rgba: Uint8ClampedArray;
}

interface RowCluster {
  readonly start: number;
  readonly end: number;
  readonly mean: number;
  readonly peak: number;
}

export function detectSelectedImageCropBand(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
): SelectedImageAutoCropProposal {
  assertSample(sample);
  const defaultCrop = createDefaultSelectedImageCropBand(source);
  const blueRows: number[] = [];
  const textureRows: number[] = [];
  const { width, height, rgba } = sample;
  const xStart = Math.floor(width * 0.04);
  const xEnd = Math.ceil(width * 0.96);
  const usableWidth = Math.max(1, xEnd - xStart);

  for (let y = 0; y < height; y += 1) {
    let blue = 0;
    let textured = 0;
    for (let x = xStart; x < xEnd; x += 1) {
      const offset = (y * width + x) * 4;
      const red = rgba[offset] ?? 0;
      const green = rgba[offset + 1] ?? 0;
      const blueChannel = rgba[offset + 2] ?? 0;
      const maximum = Math.max(red, green, blueChannel);
      const minimum = Math.min(red, green, blueChannel);
      if (
        blueChannel >= 60 &&
        blueChannel >= red * 1.12 &&
        blueChannel >= green * 1.04 &&
        maximum - minimum >= 28
      ) {
        blue += 1;
      }
      if (x > xStart && y > 0) {
        const leftOffset = offset - 4;
        const upperOffset = offset - width * 4;
        const luminance = luminanceAt(rgba, offset);
        const contrast =
          Math.abs(luminance - luminanceAt(rgba, leftOffset)) +
          Math.abs(luminance - luminanceAt(rgba, upperOffset));
        if (contrast >= 42) textured += 1;
      }
    }
    blueRows.push(blue / usableWidth);
    textureRows.push(textured / usableWidth);
  }

  const smoothBlue = smoothRows(
    blueRows,
    Math.max(1, Math.round(height * 0.008)),
  );
  const bluePeak = Math.max(...smoothBlue);
  if (bluePeak >= 0.18) {
    const threshold = Math.max(0.09, bluePeak * 0.32);
    const cluster = strongestCluster(
      smoothBlue,
      threshold,
      Math.max(1, Math.round(height * 0.035)),
      Math.round(height * 0.14),
    );
    if (cluster !== null) {
      return proposalFromCluster(
        cluster,
        sample,
        source,
        'chromatic_panel',
        clamp01(0.55 + cluster.mean * 0.7 + cluster.peak * 0.25),
      );
    }
  }

  const smoothTexture = smoothRows(
    textureRows,
    Math.max(1, Math.round(height * 0.012)),
  );
  const textureThreshold = Math.max(0.08, percentile(smoothTexture, 0.58));
  const textureCluster = strongestCluster(
    smoothTexture,
    textureThreshold,
    Math.max(1, Math.round(height * 0.025)),
    Math.round(height * 0.2),
  );
  if (textureCluster !== null && textureCluster.peak >= 0.13) {
    return proposalFromCluster(
      textureCluster,
      sample,
      source,
      'texture_band',
      clamp01(0.38 + textureCluster.mean * 0.8),
    );
  }

  return {
    crop: defaultCrop,
    strategy: 'safe_default',
    confidence: 0,
    policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
  };
}

function proposalFromCluster(
  cluster: RowCluster,
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
  strategy: Exclude<SelectedImageAutoCropStrategy, 'safe_default'>,
  confidence: number,
): SelectedImageAutoCropProposal {
  const topPadding = Math.round(
    sample.height * SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO,
  );
  if (cluster.start <= topPadding) {
    return {
      crop: createDefaultSelectedImageCropBand(source),
      strategy: 'safe_default',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
    };
  }
  const bottomPadding = Math.round(
    sample.height * SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO,
  );
  const topRatio = (cluster.start - topPadding) / sample.height;
  const bottomRatio =
    Math.min(sample.height, cluster.end + 1 + bottomPadding) / sample.height;
  let crop: SelectedImageCropBand;
  try {
    crop = validateSelectedImageCropBand({
      ...source,
      topY: Math.round(topRatio * source.height),
      bottomY: Math.round(bottomRatio * source.height),
    });
  } catch {
    crop = createDefaultSelectedImageCropBand(source);
    return {
      crop,
      strategy: 'safe_default',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
    };
  }
  return {
    crop,
    strategy,
    confidence: Number(confidence.toFixed(3)),
    policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
  };
}

function strongestCluster(
  values: readonly number[],
  threshold: number,
  allowedGap: number,
  minimumLength: number,
): RowCluster | null {
  const clusters: RowCluster[] = [];
  let start = -1;
  let lastActive = -1;
  for (let index = 0; index <= values.length; index += 1) {
    const active = index < values.length && (values[index] ?? 0) >= threshold;
    if (active) {
      if (start < 0) start = index;
      lastActive = index;
    }
    if (
      start >= 0 &&
      !active &&
      (index - lastActive > allowedGap || index === values.length)
    ) {
      const end = lastActive;
      if (end - start + 1 >= minimumLength) {
        const segment = values.slice(start, end + 1);
        clusters.push({
          start,
          end,
          mean:
            segment.reduce((total, value) => total + value, 0) / segment.length,
          peak: Math.max(...segment),
        });
      }
      start = -1;
      lastActive = -1;
    }
  }
  return (
    clusters.sort((left, right) => {
      const leftScore = (left.end - left.start + 1) * (left.mean + left.peak);
      const rightScore =
        (right.end - right.start + 1) * (right.mean + right.peak);
      return rightScore - leftScore || left.start - right.start;
    })[0] ?? null
  );
}

function smoothRows(values: readonly number[], radius: number): number[] {
  const prefix = [0];
  for (const value of values) prefix.push(prefix[prefix.length - 1]! + value);
  return values.map((_, index) => {
    const start = Math.max(0, index - radius);
    const end = Math.min(values.length, index + radius + 1);
    return (prefix[end]! - prefix[start]!) / (end - start);
  });
}

function percentile(values: readonly number[], ratio: number): number {
  const sorted = [...values].sort((left, right) => left - right);
  return (
    sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * ratio))] ?? 0
  );
}

function luminanceAt(rgba: Uint8ClampedArray, offset: number): number {
  return (
    (rgba[offset] ?? 0) * 0.299 +
    (rgba[offset + 1] ?? 0) * 0.587 +
    (rgba[offset + 2] ?? 0) * 0.114
  );
}

function assertSample(sample: SelectedImageAutoCropSample): void {
  if (
    !Number.isInteger(sample.width) ||
    !Number.isInteger(sample.height) ||
    sample.width <= 0 ||
    sample.height <= 0 ||
    sample.rgba.length !== sample.width * sample.height * 4
  ) {
    throw new Error('SELECTED_IMAGE_AUTO_CROP_SAMPLE_INVALID');
  }
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
