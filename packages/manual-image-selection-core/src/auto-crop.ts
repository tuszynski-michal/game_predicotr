import {
  createDefaultSelectedImageCropBand,
  validateSelectedImageCropBand,
  type SelectedImageCropBand,
  type SelectedImageDimensions,
} from '@game-predictor/manual-image-selection-core/crop';

export const SELECTED_IMAGE_AUTO_CROP_POLICY =
  'selected-image-board-band-v10-top-board-row-guided' as const;
export const SELECTED_IMAGE_AUTO_CROP_V9_POLICY =
  'selected-image-board-band-v9-balanced-top-margin' as const;
export const SELECTED_IMAGE_AUTO_CROP_V8_POLICY =
  'selected-image-board-band-v8-tight-top-boundary' as const;
export const SELECTED_IMAGE_AUTO_CROP_V7_POLICY =
  'selected-image-board-band-v7-bounded-boundary-expansion' as const;
export const SELECTED_IMAGE_AUTO_CROP_V6_POLICY =
  'selected-image-board-band-v6-wide-blue-board-panel' as const;
export const SELECTED_IMAGE_AUTO_CROP_V5_POLICY =
  'selected-image-board-band-v5-blue-priority-multicolumn' as const;
export const SELECTED_IMAGE_AUTO_CROP_LEGACY_POLICY =
  'selected-image-board-band-v4-conservative-multicolumn' as const;
export const SELECTED_IMAGE_AUTO_CROP_SAMPLE_WIDTH = 512 as const;
/** Keep context above the panel without retaining the paytable above it. */
export const SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO = 0.045 as const;
export const SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO = 0.045 as const;
export const SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_TOP_RATIO = 0.05 as const;
export const SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_BOTTOM_RATIO = 0.95 as const;
const SELECTED_IMAGE_AUTO_CROP_MINIMUM_DETECTED_BAND_RATIO = 0.28;

export type SelectedImageAutoCropPolicyVersion =
  | 'selected-image-board-band-v11-full-layout-structural'
  | typeof SELECTED_IMAGE_AUTO_CROP_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_V9_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_V8_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_V7_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_V6_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_V5_POLICY
  | typeof SELECTED_IMAGE_AUTO_CROP_LEGACY_POLICY;

export type SelectedImageAutoCropStrategy =
  'top_board_row_guided' | 'blue_panel' | 'multicolumn_panel' | 'safe_wide';

export type SelectedImageAutoCropClassification =
  'high_confidence' | 'conservative' | 'safe_wide';

export type SelectedImageAutoCropSignal = 'chromatic' | 'structural';

export type SelectedImageAutoCropFallbackReason =
  'no_wide_evidence' | 'crop_too_short' | 'invalid_bounds' | null;

export interface SelectedImageAutoCropLocalBoundary {
  readonly signal: SelectedImageAutoCropSignal;
  readonly stripIndex: number;
  readonly topRatio: number;
  readonly bottomRatio: number;
}

export interface SelectedImageAutoCropEvidence {
  readonly sampleWidth: number;
  readonly sampleHeight: number;
  readonly localBounds: readonly SelectedImageAutoCropLocalBoundary[];
  readonly chromaticCandidateCount: number;
  readonly structuralCandidateCount: number;
  readonly chromaticSupportedStrips: readonly number[];
  readonly structuralSupportedStrips: readonly number[];
  readonly evidenceIoU: number | null;
  readonly boundaryExpanded: boolean;
  readonly fallbackReason: SelectedImageAutoCropFallbackReason;
  /** Absent on proposals persisted by policy v4. */
  readonly selectionBasis?:
    'top_board_row' | 'blue_panel' | 'multicolumn' | 'safe_wide';
  /** Present only for the v10 top-board-row refinement. */
  readonly topBoardRowCandidateCount?: number;
  readonly topBoardRowTopRatio?: number | null;
}

export interface SelectedImageAutoCropProposal {
  readonly crop: SelectedImageCropBand;
  readonly strategy: SelectedImageAutoCropStrategy;
  readonly classification: SelectedImageAutoCropClassification;
  readonly confidence: number | null;
  readonly structural?: import('./auto-crop-v11-boundaries.ts').StructuralCropEvidence;
  readonly policyVersion: SelectedImageAutoCropPolicyVersion;
  readonly evidence: SelectedImageAutoCropEvidence;
}

export type DetectedSelectedImageAutoCropProposal = Omit<
  SelectedImageAutoCropProposal,
  'policyVersion'
> & {
  readonly policyVersion: typeof SELECTED_IMAGE_AUTO_CROP_POLICY;
};

export interface SelectedImageAutoCropSample {
  readonly width: number;
  readonly height: number;
  readonly rgba: Uint8ClampedArray;
}

interface SignalCandidate {
  readonly start: number;
  readonly end: number;
  readonly localBounds: readonly LocalBoundary[];
  readonly score: number;
  readonly supportedStrips: readonly number[];
}

interface LocalBoundary {
  readonly top: number;
  readonly bottom: number;
}

interface SignalGrid {
  readonly scoresByStrip: readonly (readonly number[])[];
  readonly activeByStrip: readonly (readonly boolean[])[];
}

const STRIP_COUNT = 9;
const REQUIRED_STRIP_COUNT = 5;
const ANALYSIS_X_MARGIN_RATIO = 0.03;

export function detectSelectedImageCropBand(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
): DetectedSelectedImageAutoCropProposal {
  assertSample(sample);
  const bluePanel = detectBluePanel(sample, source);
  const baseline = bluePanel ?? detectMulticolumnPanel(sample, source);
  return refineTopFromBoardRow(sample, source, baseline);
}

interface BoardFrameCandidate {
  readonly left: number;
  readonly top: number;
  readonly width: number;
  readonly height: number;
}

/**
 * The broad panel remains the safe lower-bound detector.  V10 refines only
 * the error-prone top edge from three independently visible top-row boards.
 * Failure is deliberately a no-op, so it can never make a weak image tighter.
 */
function refineTopFromBoardRow(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
  baseline: DetectedSelectedImageAutoCropProposal,
): DetectedSelectedImageAutoCropProposal {
  const candidates = detectBoardFrameCandidates(sample);
  const baselineTop =
    (baseline.crop.topY / Math.max(1, source.height)) * sample.height;
  const row = selectTopBoardRow(candidates, sample, baselineTop);
  if (row === null) {
    return {
      ...baseline,
      evidence: {
        ...baseline.evidence,
        topBoardRowCandidateCount: candidates.length,
        topBoardRowTopRatio: null,
      },
    };
  }
  const medianHeight = percentile(
    row.map((candidate) => candidate.height),
    0.5,
  );
  const top = Math.max(
    0,
    Math.min(...row.map((candidate) => candidate.top)) -
      Math.max(
        3,
        Math.round(medianHeight * 0.22),
        Math.round(sample.height * 0.02),
      ),
  );
  const topY = Math.round((top / sample.height) * source.height);
  if (
    topY >= baseline.crop.bottomY ||
    baseline.crop.bottomY - topY <
      source.height * SELECTED_IMAGE_AUTO_CROP_MINIMUM_DETECTED_BAND_RATIO
  ) {
    return baseline;
  }
  return {
    ...baseline,
    crop: validateSelectedImageCropBand({
      ...source,
      topY,
      bottomY: baseline.crop.bottomY,
    }),
    strategy: 'top_board_row_guided',
    classification: 'high_confidence',
    confidence: Number(Math.max(0.9, baseline.confidence ?? 0).toFixed(3)),
    evidence: {
      ...baseline.evidence,
      selectionBasis: 'top_board_row',
      topBoardRowCandidateCount: candidates.length,
      topBoardRowTopRatio: Number((top / sample.height).toFixed(6)),
    },
  };
}

function detectBoardFrameCandidates(
  sample: SelectedImageAutoCropSample,
): readonly BoardFrameCandidate[] {
  const { width, height, rgba } = sample;
  const expanded = new Uint8Array(width * height);
  for (let y = Math.floor(height * 0.16); y < Math.ceil(height * 0.8); y += 1) {
    for (
      let x = Math.floor(width * 0.02);
      x < Math.ceil(width * 0.98);
      x += 1
    ) {
      if (!isBoardFrameRed(rgba, (y * width + x) * 4)) continue;
      for (let dy = -1; dy <= 1; dy += 1) {
        const py = y + dy;
        if (py < 0 || py >= height) continue;
        const start = Math.max(0, x - 3);
        const end = Math.min(width - 1, x + 3);
        expanded.fill(1, py * width + start, py * width + end + 1);
      }
    }
  }
  const visited = new Uint8Array(expanded.length);
  const result: BoardFrameCandidate[] = [];
  const queue: number[] = [];
  for (let index = 0; index < expanded.length; index += 1) {
    if (expanded[index] !== 1 || visited[index] === 1) continue;
    visited[index] = 1;
    queue.length = 0;
    queue.push(index);
    let head = 0;
    let minX = width;
    let maxX = 0;
    let minY = height;
    let maxY = 0;
    while (head < queue.length) {
      const current = queue[head++]!;
      const x = current % width;
      const y = Math.floor(current / width);
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y);
      maxY = Math.max(maxY, y);
      const neighbours = [
        current - 1,
        current + 1,
        current - width,
        current + width,
      ];
      for (const neighbour of neighbours) {
        if (neighbour < 0 || neighbour >= expanded.length) continue;
        const nx = neighbour % width;
        if (Math.abs(nx - x) > 1) continue;
        if (expanded[neighbour] !== 1 || visited[neighbour] === 1) continue;
        visited[neighbour] = 1;
        queue.push(neighbour);
      }
    }
    const candidateWidth = maxX - minX + 1;
    const candidateHeight = maxY - minY + 1;
    const aspect = candidateWidth / Math.max(1, candidateHeight);
    const areaRatio = (candidateWidth * candidateHeight) / (width * height);
    if (
      candidateWidth >= width * 0.075 &&
      candidateWidth <= width * 0.34 &&
      candidateHeight >= height * 0.025 &&
      candidateHeight <= height * 0.16 &&
      aspect >= 1.05 &&
      aspect <= 3.6 &&
      areaRatio >= 0.0015 &&
      areaRatio <= 0.06
    ) {
      result.push({
        left: minX,
        top: minY,
        width: candidateWidth,
        height: candidateHeight,
      });
    }
  }
  return result;
}

function selectTopBoardRow(
  candidates: readonly BoardFrameCandidate[],
  sample: SelectedImageAutoCropSample,
  baselineTop: number,
):
  | readonly [BoardFrameCandidate, BoardFrameCandidate, BoardFrameCandidate]
  | null {
  const ordered = [...candidates].sort(
    (left, right) => centreX(left) - centreX(right),
  );
  let best: {
    readonly row: readonly [
      BoardFrameCandidate,
      BoardFrameCandidate,
      BoardFrameCandidate,
    ];
    readonly score: number;
  } | null = null;
  for (let leftIndex = 0; leftIndex < ordered.length; leftIndex += 1) {
    for (
      let middleIndex = leftIndex + 1;
      middleIndex < ordered.length;
      middleIndex += 1
    ) {
      for (
        let rightIndex = middleIndex + 1;
        rightIndex < ordered.length;
        rightIndex += 1
      ) {
        const left = ordered[leftIndex]!;
        const middle = ordered[middleIndex]!;
        const right = ordered[rightIndex]!;
        if (!(
          centreX(left) < centreX(middle) && centreX(middle) < centreX(right)
        ))
          continue;
        const row = [left, middle, right] as const;
        const leftGap = centreX(middle) - centreX(left);
        const rightGap = centreX(right) - centreX(middle);
        const span = centreX(right) - centreX(left);
        if (
          span < sample.width * 0.28 ||
          span > sample.width * 0.72 ||
          Math.min(leftGap, rightGap) < sample.width * 0.075 ||
          Math.max(leftGap, rightGap) / Math.min(leftGap, rightGap) > 2.2
        )
          continue;
        const centres = row.map(
          (candidate) => candidate.top + candidate.height / 2,
        );
        const centreSpread = Math.max(...centres) - Math.min(...centres);
        if (centreSpread > sample.height * 0.075) continue;
        const widths = row.map((candidate) => candidate.width);
        const heights = row.map((candidate) => candidate.height);
        if (Math.max(...widths) / Math.max(1, Math.min(...widths)) > 1.75)
          continue;
        if (Math.max(...heights) / Math.max(1, Math.min(...heights)) > 1.8)
          continue;
        const rowTop = Math.min(...row.map((candidate) => candidate.top));
        if (
          rowTop <
            Math.max(
              sample.height * 0.16,
              baselineTop - sample.height * 0.08,
            ) ||
          rowTop >
            Math.min(sample.height * 0.68, baselineTop + sample.height * 0.24)
        )
          continue;
        const score =
          centreSpread +
          Math.abs(rowTop - baselineTop) * 0.35 +
          (Math.max(...widths) - Math.min(...widths)) * 0.2;
        if (best === null || score < best.score) best = { row, score };
      }
    }
  }
  return best?.row ?? null;
}

function centreX(candidate: BoardFrameCandidate): number {
  return candidate.left + candidate.width / 2;
}

function isBoardFrameRed(rgba: Uint8ClampedArray, offset: number): boolean {
  const red = rgba[offset] ?? 0;
  const green = rgba[offset + 1] ?? 0;
  const blue = rgba[offset + 2] ?? 0;
  return (
    red >= 48 &&
    red >= green * 1.16 &&
    red >= blue * 1.08 &&
    red - Math.min(green, blue) >= 18
  );
}

function detectMulticolumnPanel(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
): DetectedSelectedImageAutoCropProposal {
  const { width, height, rgba } = sample;
  const { chromatic, structural } = measureSignals(width, height, rgba);
  const chromaticCandidates = signalCandidates(chromatic, height, 0.075);
  const structuralCandidates = signalCandidates(structural, height, 0.085);
  const selected = selectEvidence(chromaticCandidates, structuralCandidates);
  if (selected === null)
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'no_wide_evidence',
    });

  const localBounds = selected.candidates.flatMap(
    (candidate) => candidate.localBounds,
  );
  let top =
    percentile(
      localBounds.map((boundary) => boundary.top),
      0.1,
    ) - Math.round(height * SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO);
  let bottom =
    percentile(
      localBounds.map((boundary) => boundary.bottom),
      0.9,
    ) + Math.round(height * SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO);
  const broadContent = broadContentRows(chromatic, structural, height);
  const initialTop = top;
  const initialBottom = bottom;
  [top, bottom] = expandPastBoundaryContent(top, bottom, broadContent, height);
  top = Math.max(0, top);
  bottom = Math.min(height, bottom + 1);
  if (
    (bottom - top) / height <
    SELECTED_IMAGE_AUTO_CROP_MINIMUM_DETECTED_BAND_RATIO
  )
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'crop_too_short',
    });

  try {
    return {
      crop: validateSelectedImageCropBand({
        ...source,
        topY: Math.round((top / height) * source.height),
        bottomY: Math.round((bottom / height) * source.height),
      }),
      strategy: 'multicolumn_panel',
      classification: selected.classification,
      confidence: Number(selected.confidence.toFixed(3)),
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence: buildEvidence({
        width,
        height,
        chromaticCandidates,
        structuralCandidates,
        selected,
        boundaryExpanded: top !== initialTop || bottom !== initialBottom,
        fallbackReason: null,
        selectionBasis: 'multicolumn',
      }),
    };
  } catch {
    return safeWideProposal(source, width, height, {
      chromaticCandidateCount: chromaticCandidates.length,
      structuralCandidateCount: structuralCandidates.length,
      fallbackReason: 'invalid_bounds',
    });
  }
}

function safeWideProposal(
  source: SelectedImageDimensions,
  sampleWidth: number,
  sampleHeight: number,
  summary: {
    readonly chromaticCandidateCount: number;
    readonly structuralCandidateCount: number;
    readonly fallbackReason: Exclude<SelectedImageAutoCropFallbackReason, null>;
  },
): DetectedSelectedImageAutoCropProposal {
  const evidence: SelectedImageAutoCropEvidence = {
    sampleWidth,
    sampleHeight,
    localBounds: [],
    chromaticCandidateCount: summary.chromaticCandidateCount,
    structuralCandidateCount: summary.structuralCandidateCount,
    chromaticSupportedStrips: [],
    structuralSupportedStrips: [],
    evidenceIoU: null,
    boundaryExpanded: false,
    fallbackReason: summary.fallbackReason,
    selectionBasis: 'safe_wide',
  };
  try {
    return {
      crop: validateSelectedImageCropBand({
        ...source,
        topY: Math.floor(
          source.height * SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_TOP_RATIO,
        ),
        bottomY: Math.ceil(
          source.height * SELECTED_IMAGE_AUTO_CROP_SAFE_WIDE_BOTTOM_RATIO,
        ),
      }),
      strategy: 'safe_wide',
      classification: 'safe_wide',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence,
    };
  } catch {
    return {
      crop: createDefaultSelectedImageCropBand(source),
      strategy: 'safe_wide',
      classification: 'safe_wide',
      confidence: 0,
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence,
    };
  }
}

/**
 * Preserve the reliable cabinet-specific signal for layouts whose 3x3 board
 * panel has a blue background. The generic chromatic detector can otherwise
 * merge that panel with the colorful paytable above it. Independent strip
 * evidence must still cover the left, centre and right side of the image.
 */
function detectBluePanel(
  sample: SelectedImageAutoCropSample,
  source: SelectedImageDimensions,
): DetectedSelectedImageAutoCropProposal | null {
  const { width, height, rgba } = sample;
  const xStart = Math.floor(width * 0.06);
  const xEnd = Math.ceil(width * 0.94);
  const usableWidth = Math.max(STRIP_COUNT, xEnd - xStart);
  const boundaries: Array<LocalBoundary & { readonly stripIndex: number }> = [];
  const stripPeaks: number[] = [];
  for (let strip = 0; strip < STRIP_COUNT; strip += 1) {
    const stripStart = xStart + Math.floor((usableWidth * strip) / STRIP_COUNT);
    const stripEnd =
      xStart + Math.floor((usableWidth * (strip + 1)) / STRIP_COUNT);
    const stripWidth = Math.max(1, stripEnd - stripStart);
    const rows = Array.from({ length: height }, (_, y) => {
      let blue = 0;
      for (let x = stripStart; x < stripEnd; x += 1) {
        if (isBoardPanelBlue(rgba, (y * width + x) * 4)) blue += 1;
      }
      return blue / stripWidth;
    });
    const smoothed = smoothRows(rows, Math.max(1, Math.round(height * 0.008)));
    const peak = Math.max(...smoothed);
    if (peak < 0.3) continue;
    const cluster = strongestRowCluster(
      smoothed,
      Math.max(0.18, peak * 0.42),
      Math.max(1, Math.round(height * 0.035)),
      Math.round(height * 0.12),
    );
    if (cluster === null) continue;
    const lengthRatio = (cluster.end - cluster.start + 1) / height;
    if (
      cluster.start < height * 0.12 ||
      cluster.start > height * 0.72 ||
      cluster.end < height * 0.45 ||
      lengthRatio < 0.18 ||
      lengthRatio > 0.68
    )
      continue;
    boundaries.push({
      stripIndex: strip,
      top: cluster.start,
      bottom: cluster.end,
    });
    stripPeaks.push(cluster.peak);
  }
  const supportedStrips = boundaries.map((boundary) => boundary.stripIndex);
  if (!hasWideSupport(supportedStrips)) return null;
  const topSpread =
    Math.max(...boundaries.map((boundary) => boundary.top)) -
    Math.min(...boundaries.map((boundary) => boundary.top));
  const bottomSpread =
    Math.max(...boundaries.map((boundary) => boundary.bottom)) -
    Math.min(...boundaries.map((boundary) => boundary.bottom));
  if (topSpread > height * 0.14 || bottomSpread > height * 0.16) return null;

  const panelTop = percentile(
    boundaries.map((boundary) => boundary.top),
    0.1,
  );
  const panelBottom = percentile(
    boundaries.map((boundary) => boundary.bottom),
    0.9,
  );
  const topPadding = Math.round(
    height * SELECTED_IMAGE_AUTO_CROP_TOP_PADDING_RATIO,
  );
  if (panelTop <= topPadding) return null;
  const bottomPadding = Math.round(
    height * SELECTED_IMAGE_AUTO_CROP_BOTTOM_PADDING_RATIO,
  );
  try {
    return {
      crop: validateSelectedImageCropBand({
        ...source,
        topY: Math.round(((panelTop - topPadding) / height) * source.height),
        bottomY: Math.round(
          (Math.min(height, panelBottom + 1 + bottomPadding) / height) *
            source.height,
        ),
      }),
      strategy: 'blue_panel',
      classification: 'high_confidence',
      confidence: Number(
        clamp01(
          0.58 +
            (supportedStrips.length / STRIP_COUNT) * 0.22 +
            (stripPeaks.reduce((total, peak) => total + peak, 0) /
              stripPeaks.length) *
              0.2,
        ).toFixed(3),
      ),
      policyVersion: SELECTED_IMAGE_AUTO_CROP_POLICY,
      evidence: {
        sampleWidth: width,
        sampleHeight: height,
        localBounds: boundaries.map((boundary) => ({
          signal: 'chromatic',
          stripIndex: boundary.stripIndex,
          topRatio: Number((boundary.top / height).toFixed(6)),
          bottomRatio: Number((boundary.bottom / height).toFixed(6)),
        })),
        chromaticCandidateCount: boundaries.length,
        structuralCandidateCount: 0,
        chromaticSupportedStrips: supportedStrips,
        structuralSupportedStrips: [],
        evidenceIoU: null,
        boundaryExpanded: false,
        fallbackReason: null,
        selectionBasis: 'blue_panel',
      },
    };
  } catch {
    return null;
  }
}

function isBoardPanelBlue(rgba: Uint8ClampedArray, offset: number): boolean {
  const red = rgba[offset] ?? 0;
  const green = rgba[offset + 1] ?? 0;
  const blue = rgba[offset + 2] ?? 0;
  const maximum = Math.max(red, green, blue);
  const minimum = Math.min(red, green, blue);
  return (
    blue >= 60 &&
    blue >= red * 1.12 &&
    blue >= green * 1.04 &&
    maximum - minimum >= 28
  );
}

interface RowCluster {
  readonly start: number;
  readonly end: number;
  readonly mean: number;
  readonly peak: number;
}

function strongestRowCluster(
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

function measureSignals(
  width: number,
  height: number,
  rgba: Uint8ClampedArray,
): { readonly chromatic: SignalGrid; readonly structural: SignalGrid } {
  const xStart = Math.floor(width * ANALYSIS_X_MARGIN_RATIO);
  const xEnd = Math.ceil(width * (1 - ANALYSIS_X_MARGIN_RATIO));
  const usableWidth = Math.max(STRIP_COUNT, xEnd - xStart);
  const chromaticScores = emptySignalScores(height);
  const structuralScores = emptySignalScores(height);
  for (let strip = 0; strip < STRIP_COUNT; strip += 1) {
    const stripStart = xStart + Math.floor((usableWidth * strip) / STRIP_COUNT);
    const stripEnd =
      xStart + Math.floor((usableWidth * (strip + 1)) / STRIP_COUNT);
    const stripWidth = Math.max(1, stripEnd - stripStart);
    for (let y = 0; y < height; y += 1) {
      let chromatic = 0;
      let legacyBlue = 0;
      let edgeCount = 0;
      let contrastTotal = 0;
      for (let x = stripStart; x < stripEnd; x += 1) {
        const offset = (y * width + x) * 4;
        const red = rgba[offset] ?? 0;
        const green = rgba[offset + 1] ?? 0;
        const blue = rgba[offset + 2] ?? 0;
        const maximum = Math.max(red, green, blue);
        const minimum = Math.min(red, green, blue);
        if (maximum >= 48 && maximum - minimum >= 30) chromatic += 1;
        if (
          blue >= 60 &&
          blue >= red * 1.12 &&
          blue >= green * 1.04 &&
          maximum - minimum >= 28
        ) {
          legacyBlue += 1;
        }
        if (x > stripStart && y > 0) {
          const luminance = luminanceAt(rgba, offset);
          const contrast =
            Math.abs(luminance - luminanceAt(rgba, offset - 4)) +
            Math.abs(luminance - luminanceAt(rgba, offset - width * 4));
          contrastTotal += Math.min(96, contrast) / 96;
          if (contrast >= 38) edgeCount += 1;
        }
      }
      chromaticScores[strip]![y] = Math.min(
        1,
        chromatic / stripWidth + (legacyBlue / stripWidth) * 0.15,
      );
      structuralScores[strip]![y] =
        (edgeCount / stripWidth) * 0.65 + (contrastTotal / stripWidth) * 0.35;
    }
  }
  return {
    chromatic: activateSignalGrid(chromaticScores, height, 0.055),
    structural: activateSignalGrid(structuralScores, height, 0.05),
  };
}

function emptySignalScores(height: number): number[][] {
  return Array.from({ length: STRIP_COUNT }, () =>
    Array.from({ length: height }, () => 0),
  );
}

function activateSignalGrid(
  scores: readonly (readonly number[])[],
  height: number,
  floor: number,
): SignalGrid {
  const radius = Math.max(1, Math.round(height * 0.008));
  const smoothed = scores.map((rows) => smoothRows(rows, radius));
  return {
    scoresByStrip: smoothed,
    activeByStrip: smoothed.map((rows) => {
      const threshold = Math.max(floor, percentile(rows, 0.7) * 0.78);
      return rows.map((value) => value >= threshold);
    }),
  };
}

function signalCandidates(
  signal: SignalGrid,
  height: number,
  minimumScore: number,
): SignalCandidate[] {
  const support = Array.from({ length: height }, (_, row) =>
    signal.activeByStrip.reduce(
      (total, strip) => total + (strip[row] === true ? 1 : 0),
      0,
    ),
  );
  const clusters = booleanClusters(
    support.map((count) => count >= REQUIRED_STRIP_COUNT),
    Math.max(1, Math.round(height * 0.025)),
    Math.max(2, Math.round(height * 0.08)),
  );
  return clusters.flatMap(({ start, end }) => {
    const supportedStrips = signal.activeByStrip.flatMap((rows, strip) =>
      rows.slice(start, end + 1).some(Boolean) ? [strip] : [],
    );
    if (!hasWideSupport(supportedStrips)) return [];
    const localBounds = supportedStrips.map((strip) => {
      const rows = signal.activeByStrip[strip]!;
      let top = start;
      let bottom = end;
      while (top <= end && rows[top] !== true) top += 1;
      while (bottom >= start && rows[bottom] !== true) bottom -= 1;
      return { top, bottom };
    });
    const meanSupport =
      support.slice(start, end + 1).reduce((sum, value) => sum + value, 0) /
      ((end - start + 1) * STRIP_COUNT);
    const meanSignal =
      supportedStrips.reduce((total, strip) => {
        const rows = signal.scoresByStrip[strip]!.slice(start, end + 1);
        return (
          total + rows.reduce((sum, value) => sum + value, 0) / rows.length
        );
      }, 0) / supportedStrips.length;
    const score = meanSupport * 0.65 + meanSignal * 0.35;
    return score >= minimumScore
      ? [{ start, end, localBounds, score, supportedStrips }]
      : [];
  });
}

function selectEvidence(
  chromatic: readonly SignalCandidate[],
  structural: readonly SignalCandidate[],
): {
  readonly candidates: readonly SignalCandidate[];
  readonly chromatic: SignalCandidate | null;
  readonly structural: SignalCandidate | null;
  readonly evidenceIoU: number | null;
  readonly classification: Exclude<
    SelectedImageAutoCropClassification,
    'safe_wide'
  >;
  readonly confidence: number;
} | null {
  let bestPair: {
    readonly chromatic: SignalCandidate;
    readonly structural: SignalCandidate;
    readonly iou: number;
  } | null = null;
  for (const color of chromatic) {
    for (const structure of structural) {
      const iou = intervalIoU(color, structure);
      if (
        bestPair === null ||
        iou > bestPair.iou ||
        (iou === bestPair.iou &&
          color.score + structure.score >
            bestPair.chromatic.score + bestPair.structural.score)
      ) {
        bestPair = { chromatic: color, structural: structure, iou };
      }
    }
  }
  if (bestPair !== null && bestPair.iou >= 0.65) {
    return {
      candidates: [bestPair.chromatic, bestPair.structural],
      chromatic: bestPair.chromatic,
      structural: bestPair.structural,
      evidenceIoU: bestPair.iou,
      classification: 'high_confidence',
      confidence: clamp01(
        0.72 +
          bestPair.iou * 0.18 +
          (bestPair.chromatic.score + bestPair.structural.score) * 0.1,
      ),
    };
  }
  const strongestColor = strongestCandidate(chromatic);
  const strongestStructure = strongestCandidate(structural);
  if (strongestColor === null && strongestStructure === null) return null;
  const candidates = [strongestColor, strongestStructure].filter(
    (candidate): candidate is SignalCandidate => candidate !== null,
  );
  return {
    candidates,
    chromatic: strongestColor,
    structural: strongestStructure,
    evidenceIoU:
      strongestColor === null || strongestStructure === null
        ? null
        : intervalIoU(strongestColor, strongestStructure),
    classification: 'conservative',
    confidence: clamp01(
      0.42 +
        (candidates.reduce((total, candidate) => total + candidate.score, 0) /
          candidates.length) *
          0.35,
    ),
  };
}

function buildEvidence(input: {
  readonly width: number;
  readonly height: number;
  readonly chromaticCandidates: readonly SignalCandidate[];
  readonly structuralCandidates: readonly SignalCandidate[];
  readonly selected: NonNullable<ReturnType<typeof selectEvidence>>;
  readonly boundaryExpanded: boolean;
  readonly fallbackReason: SelectedImageAutoCropFallbackReason;
  readonly selectionBasis: 'multicolumn';
}): SelectedImageAutoCropEvidence {
  const boundaries = (
    signal: SelectedImageAutoCropSignal,
    candidate: SignalCandidate | null,
  ): readonly SelectedImageAutoCropLocalBoundary[] =>
    candidate === null
      ? []
      : candidate.localBounds.map((boundary, index) => ({
          signal,
          stripIndex: candidate.supportedStrips[index] ?? index,
          topRatio: Number((boundary.top / input.height).toFixed(6)),
          bottomRatio: Number((boundary.bottom / input.height).toFixed(6)),
        }));
  return {
    sampleWidth: input.width,
    sampleHeight: input.height,
    localBounds: [
      ...boundaries('chromatic', input.selected.chromatic),
      ...boundaries('structural', input.selected.structural),
    ],
    chromaticCandidateCount: input.chromaticCandidates.length,
    structuralCandidateCount: input.structuralCandidates.length,
    chromaticSupportedStrips: input.selected.chromatic?.supportedStrips ?? [],
    structuralSupportedStrips: input.selected.structural?.supportedStrips ?? [],
    evidenceIoU:
      input.selected.evidenceIoU === null
        ? null
        : Number(input.selected.evidenceIoU.toFixed(6)),
    boundaryExpanded: input.boundaryExpanded,
    fallbackReason: input.fallbackReason,
    selectionBasis: input.selectionBasis,
  };
}

function broadContentRows(
  chromatic: SignalGrid,
  structural: SignalGrid,
  height: number,
): readonly boolean[] {
  return Array.from({ length: height }, (_, row) => {
    const activeStrips = Array.from({ length: STRIP_COUNT }, (_, strip) =>
      chromatic.activeByStrip[strip]![row] === true ||
      structural.activeByStrip[strip]![row] === true
        ? strip
        : -1,
    ).filter((strip) => strip >= 0);
    return hasWideSupport(activeStrips);
  });
}

function expandPastBoundaryContent(
  initialTop: number,
  initialBottom: number,
  contentRows: readonly boolean[],
  height: number,
): [number, number] {
  const safety = Math.max(1, Math.round(height * 0.03));
  const boundedTop = Math.max(0, initialTop);
  const boundedBottom = Math.min(height - 1, initialBottom);
  const top = boundedTop;
  const bottom = contentRows
    .slice(Math.max(0, boundedBottom - safety + 1), boundedBottom + 1)
    .some(Boolean)
    ? Math.min(height - 1, boundedBottom + safety)
    : boundedBottom;
  return [top, bottom];
}

function booleanClusters(
  active: readonly boolean[],
  allowedGap: number,
  minimumLength: number,
): Array<{ readonly start: number; readonly end: number }> {
  const clusters: Array<{ start: number; end: number }> = [];
  let start = -1;
  let lastActive = -1;
  for (let index = 0; index <= active.length; index += 1) {
    if (active[index] === true) {
      if (start < 0) start = index;
      lastActive = index;
    }
    if (
      start >= 0 &&
      active[index] !== true &&
      (index - lastActive > allowedGap || index === active.length)
    ) {
      if (lastActive - start + 1 >= minimumLength)
        clusters.push({ start, end: lastActive });
      start = -1;
      lastActive = -1;
    }
  }
  return clusters;
}

function hasWideSupport(strips: readonly number[]): boolean {
  const unique = new Set(strips);
  return (
    unique.size >= REQUIRED_STRIP_COUNT &&
    [0, 1, 2].some((strip) => unique.has(strip)) &&
    [3, 4, 5].some((strip) => unique.has(strip)) &&
    [6, 7, 8].some((strip) => unique.has(strip))
  );
}

function strongestCandidate(
  candidates: readonly SignalCandidate[],
): SignalCandidate | null {
  return (
    [...candidates].sort(
      (left, right) =>
        right.score - left.score ||
        right.end - right.start - (left.end - left.start) ||
        left.start - right.start,
    )[0] ?? null
  );
}

function intervalIoU(left: SignalCandidate, right: SignalCandidate): number {
  const intersection = Math.max(
    0,
    Math.min(left.end, right.end) - Math.max(left.start, right.start) + 1,
  );
  const union =
    Math.max(left.end, right.end) - Math.min(left.start, right.start) + 1;
  return union === 0 ? 0 : intersection / union;
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
