import { CROP_V11_FINGERPRINT } from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import type {
  CropBox,
  StructuralSample,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11';
import type { StructuralCropEvidence } from '@game-predictor/manual-image-selection-core/auto-crop-v11-boundaries';

export const CROP_V12_POLICY =
  'selected-image-board-band-v12-four-point-anchor-registration' as const;

export const CROP_V12_CONFIG = Object.freeze({
  analysisLongEdge: 640,
  descriptorBits: 128,
  descriptorRadius: 11,
  featureGridColumns: 10,
  featureGridRows: 8,
  maximumAnchorFeatures: 160,
  maximumTargetFeatures: 320,
  minimumMatches: 9,
  structuralCrossCheckMinimumInliers: 5,
  structuralCrossCheckMinimumInlierRatio: 0.35,
  minimumInlierRatio: 0.42,
  minimumCoveredQuadrants: 3,
  minimumAnchorSpanRatio: 0.42,
  maximumDescriptorDistance: 48,
  maximumDescriptorRatio: 0.78,
  ransacIterations: 420,
  inlierResidualPx: 4.5,
  maximumP90ResidualPx: 3.5,
  minimumAxisScale: 0.68,
  maximumAxisScale: 1.48,
  maximumAxisCosine: 0.38,
  searchMarginRatio: 0.22,
  anchorFeatureHorizontalContextRatio: 0.08,
  anchorFeatureTopContextRatio: 0.7,
  anchorFeatureBottomContextRatio: 0.18,
  cropPaddingBoardHeightRatio: 0.28,
  minimumCropHeightRatio: 0.22,
  maximumCropHeightRatio: 0.78,
  algorithmVersion: 'oriented-brief-affine-ransac-v1',
});

export const CROP_V12_FINGERPRINT = `${CROP_V12_POLICY}|structural:${CROP_V11_FINGERPRINT}|${JSON.stringify(CROP_V12_CONFIG)}`;

export interface CropPoint {
  readonly x: number;
  readonly y: number;
}

export type FourPointBoardBand = readonly [
  CropPoint,
  CropPoint,
  CropPoint,
  CropPoint,
];

export interface FourPointCropAnchor {
  readonly sourceName: string;
  readonly sourceChecksumSha256: string;
  readonly sourceWidth: number;
  readonly sourceHeight: number;
  readonly boardBand: FourPointBoardBand;
  readonly medianBoardHeight: number;
}

export interface FourPointRegistrationEvidence {
  readonly policy: typeof CROP_V12_POLICY;
  readonly status: 'registered' | 'needs_manual_crop';
  readonly reason:
    | 'registered_from_four_point_anchor'
    | 'anchor_invalid'
    | 'insufficient_features'
    | 'insufficient_matches'
    | 'insufficient_spatial_support'
    | 'registration_residual_too_high'
    | 'registration_transform_invalid'
    | 'structural_registration_conflict'
    | 'registered_band_out_of_bounds';
  readonly anchorSourceName: string;
  readonly anchorSourceChecksumSha256: string;
  readonly anchorBoardBand: FourPointBoardBand;
  readonly registeredBoardBand: FourPointBoardBand | null;
  readonly matchCount: number;
  readonly inlierCount: number;
  readonly inlierRatio: number | null;
  readonly p90ResidualPx: number | null;
  readonly coveredQuadrants: number;
  readonly analysisWidth: number;
  readonly analysisHeight: number;
}

interface Feature {
  readonly x: number;
  readonly y: number;
  readonly score: number;
  readonly descriptor: Uint32Array;
}

interface Match {
  readonly from: Feature;
  readonly to: Feature;
  readonly distance: number;
}

interface AffineTransform {
  readonly a: number;
  readonly b: number;
  readonly c: number;
  readonly d: number;
  readonly e: number;
  readonly f: number;
}

interface AnalysisImage {
  readonly width: number;
  readonly height: number;
  readonly gray: Uint8Array;
  readonly scaleX: number;
  readonly scaleY: number;
}

const boxHeight = (box: CropBox) => box.bottom - box.top;

function median(values: readonly number[]): number {
  const sorted = [...values].sort((left, right) => left - right);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}

function assertSha256(value: string): void {
  if (!/^[a-f0-9]{64}$/.test(value)) throw new Error('CROP_V12_ANCHOR_INVALID');
}

export function fourPointAnchorFromStructuralEvidence(input: {
  readonly sourceName: string;
  readonly sourceChecksumSha256: string;
  readonly evidence: StructuralCropEvidence;
}): FourPointCropAnchor {
  const { evidence } = input;
  assertSha256(input.sourceChecksumSha256);
  if (
    evidence.status !== 'detected' ||
    evidence.boards.length !== 9 ||
    evidence.labels.length !== 9
  )
    throw new Error('CROP_V12_ANCHOR_INVALID');
  const board = (index: number) => evidence.boards[index]!;
  const label = (index: number) => evidence.labels[index]!;
  const boardBand: FourPointBoardBand = [
    { x: board(0).left, y: board(0).top },
    { x: board(2).right, y: board(2).top },
    {
      x: board(6).left,
      y: Math.max(board(6).bottom, label(6).bottom),
    },
    {
      x: board(8).right,
      y: Math.max(board(8).bottom, label(8).bottom),
    },
  ];
  validateBand(boardBand, evidence.crop.width, evidence.crop.height);
  return {
    sourceName: input.sourceName,
    sourceChecksumSha256: input.sourceChecksumSha256,
    sourceWidth: evidence.crop.width,
    sourceHeight: evidence.crop.height,
    boardBand,
    medianBoardHeight: median(evidence.boards.map(boxHeight)),
  };
}

function validateBand(
  band: FourPointBoardBand,
  width: number,
  height: number,
): void {
  if (
    band.some(
      (point) =>
        !Number.isFinite(point.x) ||
        !Number.isFinite(point.y) ||
        point.x < 0 ||
        point.y < 0 ||
        point.x > width ||
        point.y > height,
    ) ||
    band[0].x >= band[1].x ||
    band[2].x >= band[3].x ||
    Math.max(band[0].y, band[1].y) >= Math.min(band[2].y, band[3].y)
  )
    throw new Error('CROP_V12_ANCHOR_INVALID');
}

function sampleGray(source: StructuralSample): AnalysisImage {
  const ratio = Math.min(
    1,
    CROP_V12_CONFIG.analysisLongEdge / Math.max(source.width, source.height),
  );
  const width = Math.max(16, Math.round(source.width * ratio));
  const height = Math.max(16, Math.round(source.height * ratio));
  const gray = new Uint8Array(width * height);
  for (let y = 0; y < height; y += 1) {
    const sourceY = Math.min(
      source.height - 1,
      Math.floor(((y + 0.5) * source.height) / height),
    );
    for (let x = 0; x < width; x += 1) {
      const sourceX = Math.min(
        source.width - 1,
        Math.floor(((x + 0.5) * source.width) / width),
      );
      const offset = (sourceY * source.width + sourceX) * 4;
      gray[y * width + x] = Math.round(
        source.rgba[offset]! * 0.299 +
          source.rgba[offset + 1]! * 0.587 +
          source.rgba[offset + 2]! * 0.114,
      );
    }
  }
  return {
    width,
    height,
    gray,
    scaleX: width / source.width,
    scaleY: height / source.height,
  };
}

function pointInBand(point: CropPoint, band: FourPointBoardBand): boolean {
  let sign = 0;
  const polygon = [band[0], band[1], band[3], band[2]];
  for (let index = 0; index < polygon.length; index += 1) {
    const first = polygon[index]!;
    const second = polygon[(index + 1) % polygon.length]!;
    const cross =
      (second.x - first.x) * (point.y - first.y) -
      (second.y - first.y) * (point.x - first.x);
    if (Math.abs(cross) < 1e-6) continue;
    const nextSign = Math.sign(cross);
    if (sign !== 0 && nextSign !== sign) return false;
    sign = nextSign;
  }
  return true;
}

function scaleBand(
  band: FourPointBoardBand,
  scaleX: number,
  scaleY: number,
): FourPointBoardBand {
  return band.map((point) => ({
    x: point.x * scaleX,
    y: point.y * scaleY,
  })) as unknown as FourPointBoardBand;
}

function featureContextBand(
  band: FourPointBoardBand,
  width: number,
  height: number,
): FourPointBoardBand {
  const left = Math.min(band[0].x, band[2].x);
  const right = Math.max(band[1].x, band[3].x);
  const top = Math.min(band[0].y, band[1].y);
  const bottom = Math.max(band[2].y, band[3].y);
  const bandWidth = right - left;
  const bandHeight = bottom - top;
  return [
    {
      x: Math.max(
        0,
        left - bandWidth * CROP_V12_CONFIG.anchorFeatureHorizontalContextRatio,
      ),
      y: Math.max(
        0,
        top - bandHeight * CROP_V12_CONFIG.anchorFeatureTopContextRatio,
      ),
    },
    {
      x: Math.min(
        width,
        right + bandWidth * CROP_V12_CONFIG.anchorFeatureHorizontalContextRatio,
      ),
      y: Math.max(
        0,
        top - bandHeight * CROP_V12_CONFIG.anchorFeatureTopContextRatio,
      ),
    },
    {
      x: Math.max(
        0,
        left - bandWidth * CROP_V12_CONFIG.anchorFeatureHorizontalContextRatio,
      ),
      y: Math.min(
        height,
        bottom + bandHeight * CROP_V12_CONFIG.anchorFeatureBottomContextRatio,
      ),
    },
    {
      x: Math.min(
        width,
        right + bandWidth * CROP_V12_CONFIG.anchorFeatureHorizontalContextRatio,
      ),
      y: Math.min(
        height,
        bottom + bandHeight * CROP_V12_CONFIG.anchorFeatureBottomContextRatio,
      ),
    },
  ];
}

function cornerScore(gray: Uint8Array, width: number, x: number, y: number) {
  const gx = gray[y * width + x + 1]! - gray[y * width + x - 1]!;
  const gy = gray[(y + 1) * width + x]! - gray[(y - 1) * width + x]!;
  return Math.abs(gx * gy) + Math.min(Math.abs(gx), Math.abs(gy)) * 48;
}

function descriptorPairs(): readonly [number, number, number, number][] {
  let state = 0x5f3759df;
  const next = () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 0x1_0000_0000;
  };
  const radius = CROP_V12_CONFIG.descriptorRadius;
  return Array.from(
    { length: CROP_V12_CONFIG.descriptorBits },
    () =>
      [
        Math.round((next() * 2 - 1) * radius),
        Math.round((next() * 2 - 1) * radius),
        Math.round((next() * 2 - 1) * radius),
        Math.round((next() * 2 - 1) * radius),
      ] as [number, number, number, number],
  );
}

const DESCRIPTOR_PAIRS = descriptorPairs();

function describe(image: AnalysisImage, x: number, y: number): Uint32Array {
  const descriptor = new Uint32Array(CROP_V12_CONFIG.descriptorBits / 32);
  for (const [index, pair] of DESCRIPTOR_PAIRS.entries()) {
    const first = image.gray[(y + pair[1]) * image.width + x + pair[0]]!;
    const second = image.gray[(y + pair[3]) * image.width + x + pair[2]]!;
    if (first < second) descriptor[index >>> 5]! |= 1 << (index & 31);
  }
  return descriptor;
}

function detectFeatures(
  image: AnalysisImage,
  band: FourPointBoardBand | null,
  limit: number,
): Feature[] {
  const radius = CROP_V12_CONFIG.descriptorRadius + 2;
  const candidates: Omit<Feature, 'descriptor'>[] = [];
  const minX = band
    ? Math.max(radius, Math.floor(Math.min(...band.map((point) => point.x))))
    : radius;
  const maxX = band
    ? Math.min(
        image.width - radius - 1,
        Math.ceil(Math.max(...band.map((point) => point.x))),
      )
    : image.width - radius - 1;
  const minY = band
    ? Math.max(radius, Math.floor(Math.min(...band.map((point) => point.y))))
    : radius;
  const maxY = band
    ? Math.min(
        image.height - radius - 1,
        Math.ceil(Math.max(...band.map((point) => point.y))),
      )
    : image.height - radius - 1;
  const columns = CROP_V12_CONFIG.featureGridColumns;
  const rows = CROP_V12_CONFIG.featureGridRows;
  for (let row = 0; row < rows; row += 1) {
    const top = Math.floor(minY + ((maxY - minY) * row) / rows);
    const bottom = Math.ceil(minY + ((maxY - minY) * (row + 1)) / rows);
    for (let column = 0; column < columns; column += 1) {
      const left = Math.floor(minX + ((maxX - minX) * column) / columns);
      const right = Math.ceil(minX + ((maxX - minX) * (column + 1)) / columns);
      const local: Omit<Feature, 'descriptor'>[] = [];
      for (let y = Math.max(radius, top); y < Math.min(maxY, bottom); y += 2)
        for (
          let x = Math.max(radius, left);
          x < Math.min(maxX, right);
          x += 2
        ) {
          if (band && !pointInBand({ x, y }, band)) continue;
          const score = cornerScore(image.gray, image.width, x, y);
          if (score >= 850) local.push({ x, y, score });
        }
      local.sort(
        (leftFeature, rightFeature) => rightFeature.score - leftFeature.score,
      );
      candidates.push(...local.slice(0, 3));
    }
  }
  candidates.sort((left, right) => right.score - left.score);
  const selected: Feature[] = [];
  for (const candidate of candidates) {
    if (
      selected.some(
        (feature) =>
          (feature.x - candidate.x) ** 2 + (feature.y - candidate.y) ** 2 < 36,
      )
    )
      continue;
    selected.push({
      ...candidate,
      descriptor: describe(image, candidate.x, candidate.y),
    });
    if (selected.length >= limit) break;
  }
  return selected;
}

function popcount(value: number): number {
  value -= (value >>> 1) & 0x55555555;
  value = (value & 0x33333333) + ((value >>> 2) & 0x33333333);
  return (((value + (value >>> 4)) & 0x0f0f0f0f) * 0x01010101) >>> 24;
}

function hamming(left: Uint32Array, right: Uint32Array): number {
  let distance = 0;
  for (let index = 0; index < left.length; index += 1)
    distance += popcount((left[index]! ^ right[index]!) >>> 0);
  return distance;
}

function matchFeatures(
  anchor: readonly Feature[],
  target: readonly Feature[],
  anchorSize: AnalysisImage,
  targetSize: AnalysisImage,
): Match[] {
  const matches: Match[] = [];
  const marginX = targetSize.width * CROP_V12_CONFIG.searchMarginRatio;
  const marginY = targetSize.height * CROP_V12_CONFIG.searchMarginRatio;
  for (const from of anchor) {
    const expectedX = (from.x / anchorSize.width) * targetSize.width;
    const expectedY = (from.y / anchorSize.height) * targetSize.height;
    let best: Feature | null = null;
    let bestDistance = Infinity;
    let secondDistance = Infinity;
    for (const to of target) {
      if (
        Math.abs(to.x - expectedX) > marginX ||
        Math.abs(to.y - expectedY) > marginY
      )
        continue;
      const distance = hamming(from.descriptor, to.descriptor);
      if (distance < bestDistance) {
        secondDistance = bestDistance;
        bestDistance = distance;
        best = to;
      } else if (distance < secondDistance) secondDistance = distance;
    }
    if (
      best &&
      bestDistance <= CROP_V12_CONFIG.maximumDescriptorDistance &&
      (secondDistance === Infinity ||
        bestDistance / Math.max(1, secondDistance) <=
          CROP_V12_CONFIG.maximumDescriptorRatio)
    )
      matches.push({ from, to: best, distance: bestDistance });
  }
  const bestByTarget = new Map<string, Match>();
  for (const match of matches) {
    const key = `${match.to.x}:${match.to.y}`;
    const existing = bestByTarget.get(key);
    if (!existing || match.distance < existing.distance)
      bestByTarget.set(key, match);
  }
  return [...bestByTarget.values()];
}

function solve3(
  values: readonly number[],
  output: readonly number[],
): readonly number[] | null {
  const matrix = Array.from({ length: 3 }, (_, row) => [
    values[row * 3]!,
    values[row * 3 + 1]!,
    values[row * 3 + 2]!,
    output[row]!,
  ]);
  for (let column = 0; column < 3; column += 1) {
    let pivot = column;
    for (let row = column + 1; row < 3; row += 1)
      if (Math.abs(matrix[row]![column]!) > Math.abs(matrix[pivot]![column]!))
        pivot = row;
    if (Math.abs(matrix[pivot]![column]!) < 1e-7) return null;
    [matrix[column], matrix[pivot]] = [matrix[pivot]!, matrix[column]!];
    const divisor = matrix[column]![column]!;
    for (let index = column; index < 4; index += 1)
      matrix[column]![index] = matrix[column]![index]! / divisor;
    for (let row = 0; row < 3; row += 1) {
      if (row === column) continue;
      const factor = matrix[row]![column]!;
      for (let index = column; index < 4; index += 1)
        matrix[row]![index] =
          matrix[row]![index]! - factor * matrix[column]![index]!;
    }
  }
  return [matrix[0]![3]!, matrix[1]![3]!, matrix[2]![3]!];
}

function affineFromThree(matches: readonly Match[]): AffineTransform | null {
  const matrix = matches.flatMap((match) => [match.from.x, match.from.y, 1]);
  const x = solve3(
    matrix,
    matches.map((match) => match.to.x),
  );
  const y = solve3(
    matrix,
    matches.map((match) => match.to.y),
  );
  return x && y
    ? { a: x[0]!, b: x[1]!, c: x[2]!, d: y[0]!, e: y[1]!, f: y[2]! }
    : null;
}

function transformPoint(
  transform: AffineTransform,
  point: CropPoint,
): CropPoint {
  return {
    x: transform.a * point.x + transform.b * point.y + transform.c,
    y: transform.d * point.x + transform.e * point.y + transform.f,
  };
}

function residual(transform: AffineTransform, match: Match): number {
  const point = transformPoint(transform, match.from);
  return Math.hypot(point.x - match.to.x, point.y - match.to.y);
}

function seededTriples(length: number): readonly [number, number, number][] {
  const triples: [number, number, number][] = [];
  const maximum = Math.min(
    CROP_V12_CONFIG.ransacIterations,
    (length * (length - 1) * (length - 2)) / 6,
  );
  // Enumerating bounded unique triples avoids the unbounded coupon-collector
  // behaviour of random sampling when the requested budget approaches C(n,3).
  for (
    let offset = 1;
    offset < length - 1 && triples.length < maximum;
    offset += 1
  )
    for (
      let first = 0;
      first < length && triples.length < maximum;
      first += 1
    ) {
      const second = (first + offset) % length;
      const third = (second + offset + 1) % length;
      if (new Set([first, second, third]).size !== 3) continue;
      triples.push([first, second, third]);
    }
  return triples;
}

function fitAffine(matches: readonly Match[]): {
  readonly transform: AffineTransform;
  readonly inliers: readonly Match[];
  readonly p90: number;
} | null {
  let best: {
    transform: AffineTransform;
    inliers: readonly Match[];
    p90: number;
  } | null = null;
  for (const triple of seededTriples(matches.length)) {
    const transform = affineFromThree(triple.map((index) => matches[index]!));
    if (!transform) continue;
    const inliers = matches.filter(
      (match) => residual(transform, match) <= CROP_V12_CONFIG.inlierResidualPx,
    );
    if (inliers.length < 3) continue;
    const residuals = inliers
      .map((match) => residual(transform, match))
      .sort((a, b) => a - b);
    const p90 =
      residuals[
        Math.min(residuals.length - 1, Math.floor(residuals.length * 0.9))
      ]!;
    if (
      !best ||
      inliers.length > best.inliers.length ||
      (inliers.length === best.inliers.length && p90 < best.p90)
    )
      best = { transform, inliers, p90 };
  }
  return best;
}

function validTransform(transform: AffineTransform): boolean {
  const firstScale = Math.hypot(transform.a, transform.d);
  const secondScale = Math.hypot(transform.b, transform.e);
  const determinant = transform.a * transform.e - transform.b * transform.d;
  const axisCosine =
    Math.abs(transform.a * transform.b + transform.d * transform.e) /
    Math.max(1e-7, firstScale * secondScale);
  return (
    determinant > 0 &&
    firstScale >= CROP_V12_CONFIG.minimumAxisScale &&
    firstScale <= CROP_V12_CONFIG.maximumAxisScale &&
    secondScale >= CROP_V12_CONFIG.minimumAxisScale &&
    secondScale <= CROP_V12_CONFIG.maximumAxisScale &&
    axisCosine <= CROP_V12_CONFIG.maximumAxisCosine
  );
}

function coveredQuadrants(
  matches: readonly Match[],
  band: FourPointBoardBand,
): number {
  const centerX = band.reduce((sum, point) => sum + point.x, 0) / 4;
  const centerY = band.reduce((sum, point) => sum + point.y, 0) / 4;
  return new Set(
    matches.map(
      (match) =>
        `${Number(match.from.x >= centerX)}:${Number(match.from.y >= centerY)}`,
    ),
  ).size;
}

function evidenceBase(
  anchor: FourPointCropAnchor,
  analysis: AnalysisImage,
): Omit<
  FourPointRegistrationEvidence,
  | 'status'
  | 'reason'
  | 'registeredBoardBand'
  | 'matchCount'
  | 'inlierCount'
  | 'inlierRatio'
  | 'p90ResidualPx'
  | 'coveredQuadrants'
> {
  return {
    policy: CROP_V12_POLICY,
    anchorSourceName: anchor.sourceName,
    anchorSourceChecksumSha256: anchor.sourceChecksumSha256,
    anchorBoardBand: anchor.boardBand,
    analysisWidth: analysis.width,
    analysisHeight: analysis.height,
  };
}

export function registerFourPointBoardBand(input: {
  readonly anchor: FourPointCropAnchor;
  readonly anchorImage: StructuralSample;
  readonly targetImage: StructuralSample;
  readonly structuralCrossCheck?: boolean;
}): FourPointRegistrationEvidence {
  const anchorAnalysis = sampleGray(input.anchorImage);
  const targetAnalysis = sampleGray(input.targetImage);
  const base = evidenceBase(input.anchor, targetAnalysis);
  try {
    if (
      input.anchor.sourceWidth !== input.anchorImage.width ||
      input.anchor.sourceHeight !== input.anchorImage.height
    )
      throw new Error('CROP_V12_ANCHOR_INVALID');
    validateBand(
      input.anchor.boardBand,
      input.anchor.sourceWidth,
      input.anchor.sourceHeight,
    );
  } catch {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'anchor_invalid',
      registeredBoardBand: null,
      matchCount: 0,
      inlierCount: 0,
      inlierRatio: null,
      p90ResidualPx: null,
      coveredQuadrants: 0,
    };
  }
  const anchorBand = scaleBand(
    input.anchor.boardBand,
    anchorAnalysis.scaleX,
    anchorAnalysis.scaleY,
  );
  const anchorFeatureBand = featureContextBand(
    anchorBand,
    anchorAnalysis.width,
    anchorAnalysis.height,
  );
  const anchorFeatures = detectFeatures(
    anchorAnalysis,
    anchorFeatureBand,
    CROP_V12_CONFIG.maximumAnchorFeatures,
  );
  const targetFeatures = detectFeatures(
    targetAnalysis,
    null,
    CROP_V12_CONFIG.maximumTargetFeatures,
  );
  if (anchorFeatures.length < CROP_V12_CONFIG.minimumMatches) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'insufficient_features',
      registeredBoardBand: null,
      matchCount: 0,
      inlierCount: 0,
      inlierRatio: null,
      p90ResidualPx: null,
      coveredQuadrants: 0,
    };
  }
  const matches = matchFeatures(
    anchorFeatures,
    targetFeatures,
    anchorAnalysis,
    targetAnalysis,
  );
  if (matches.length < CROP_V12_CONFIG.minimumMatches) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'insufficient_matches',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: 0,
      inlierRatio: null,
      p90ResidualPx: null,
      coveredQuadrants: 0,
    };
  }
  const fitted = fitAffine(matches);
  if (!fitted) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'registration_transform_invalid',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: 0,
      inlierRatio: 0,
      p90ResidualPx: null,
      coveredQuadrants: 0,
    };
  }
  const inlierRatio = fitted.inliers.length / matches.length;
  const minimumInliers = input.structuralCrossCheck
    ? CROP_V12_CONFIG.structuralCrossCheckMinimumInliers
    : CROP_V12_CONFIG.minimumMatches;
  const minimumInlierRatio = input.structuralCrossCheck
    ? CROP_V12_CONFIG.structuralCrossCheckMinimumInlierRatio
    : CROP_V12_CONFIG.minimumInlierRatio;
  const quadrants = coveredQuadrants(fitted.inliers, anchorFeatureBand);
  const xs = fitted.inliers.map((match) => match.from.x);
  const ys = fitted.inliers.map((match) => match.from.y);
  const spanX =
    (Math.max(...xs) - Math.min(...xs)) /
    Math.max(
      1,
      Math.max(...anchorFeatureBand.map((p) => p.x)) -
        Math.min(...anchorFeatureBand.map((p) => p.x)),
    );
  const spanY =
    (Math.max(...ys) - Math.min(...ys)) /
    Math.max(
      1,
      Math.max(...anchorFeatureBand.map((p) => p.y)) -
        Math.min(...anchorFeatureBand.map((p) => p.y)),
    );
  if (
    fitted.inliers.length < minimumInliers ||
    inlierRatio < minimumInlierRatio ||
    quadrants < CROP_V12_CONFIG.minimumCoveredQuadrants ||
    Math.min(spanX, spanY) < CROP_V12_CONFIG.minimumAnchorSpanRatio
  ) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'insufficient_spatial_support',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: fitted.inliers.length,
      inlierRatio,
      p90ResidualPx: fitted.p90,
      coveredQuadrants: quadrants,
    };
  }
  if (fitted.p90 > CROP_V12_CONFIG.maximumP90ResidualPx) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'registration_residual_too_high',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: fitted.inliers.length,
      inlierRatio,
      p90ResidualPx: fitted.p90,
      coveredQuadrants: quadrants,
    };
  }
  if (!validTransform(fitted.transform)) {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'registration_transform_invalid',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: fitted.inliers.length,
      inlierRatio,
      p90ResidualPx: fitted.p90,
      coveredQuadrants: quadrants,
    };
  }
  const registered = anchorBand.map((point) =>
    transformPoint(fitted.transform, point),
  ) as unknown as FourPointBoardBand;
  const sourceBand = scaleBand(
    registered,
    1 / targetAnalysis.scaleX,
    1 / targetAnalysis.scaleY,
  );
  try {
    validateBand(sourceBand, input.targetImage.width, input.targetImage.height);
  } catch {
    return {
      ...base,
      status: 'needs_manual_crop',
      reason: 'registered_band_out_of_bounds',
      registeredBoardBand: null,
      matchCount: matches.length,
      inlierCount: fitted.inliers.length,
      inlierRatio,
      p90ResidualPx: fitted.p90,
      coveredQuadrants: quadrants,
    };
  }
  return {
    ...base,
    status: 'registered',
    reason: 'registered_from_four_point_anchor',
    registeredBoardBand: sourceBand,
    matchCount: matches.length,
    inlierCount: fitted.inliers.length,
    inlierRatio,
    p90ResidualPx: fitted.p90,
    coveredQuadrants: quadrants,
  };
}

export function cropFromRegisteredBoardBand(input: {
  readonly evidence: FourPointRegistrationEvidence;
  readonly sourceWidth: number;
  readonly sourceHeight: number;
  readonly anchorMedianBoardHeight: number;
}): {
  readonly width: number;
  readonly height: number;
  readonly topY: number;
  readonly bottomY: number;
} | null {
  const band = input.evidence.registeredBoardBand;
  if (input.evidence.status !== 'registered' || band === null) return null;
  const sideHeight = (value: FourPointBoardBand) =>
    (Math.hypot(value[2].x - value[0].x, value[2].y - value[0].y) +
      Math.hypot(value[3].x - value[1].x, value[3].y - value[1].y)) /
    2;
  const targetBoardHeight =
    input.anchorMedianBoardHeight *
    (sideHeight(band) /
      Math.max(1, sideHeight(input.evidence.anchorBoardBand)));
  const padding = Math.max(
    6,
    Math.ceil(targetBoardHeight * CROP_V12_CONFIG.cropPaddingBoardHeightRatio),
  );
  const topY = Math.max(
    0,
    Math.floor(Math.min(...band.map((point) => point.y)) - padding),
  );
  const bottomY = Math.min(
    input.sourceHeight,
    Math.ceil(Math.max(...band.map((point) => point.y)) + padding),
  );
  const ratio = (bottomY - topY) / input.sourceHeight;
  if (
    ratio < CROP_V12_CONFIG.minimumCropHeightRatio ||
    ratio > CROP_V12_CONFIG.maximumCropHeightRatio
  )
    return null;
  return {
    width: input.sourceWidth,
    height: input.sourceHeight,
    topY,
    bottomY,
  };
}

export function validateFourPointRegistrationEvidence(
  value: FourPointRegistrationEvidence,
): void {
  assertSha256(value.anchorSourceChecksumSha256);
  if (
    value.policy !== CROP_V12_POLICY ||
    !['registered', 'needs_manual_crop'].includes(value.status) ||
    ![
      'registered_from_four_point_anchor',
      'anchor_invalid',
      'insufficient_features',
      'insufficient_matches',
      'insufficient_spatial_support',
      'registration_residual_too_high',
      'registration_transform_invalid',
      'structural_registration_conflict',
      'registered_band_out_of_bounds',
    ].includes(value.reason) ||
    !Number.isInteger(value.matchCount) ||
    !Number.isInteger(value.inlierCount) ||
    !Number.isInteger(value.coveredQuadrants) ||
    value.matchCount < 0 ||
    value.inlierCount < 0 ||
    value.inlierCount > value.matchCount ||
    (value.inlierRatio !== null &&
      (!Number.isFinite(value.inlierRatio) ||
        value.inlierRatio < 0 ||
        value.inlierRatio > 1)) ||
    (value.p90ResidualPx !== null &&
      (!Number.isFinite(value.p90ResidualPx) || value.p90ResidualPx < 0)) ||
    value.coveredQuadrants < 0 ||
    value.coveredQuadrants > 4 ||
    !Number.isInteger(value.analysisWidth) ||
    !Number.isInteger(value.analysisHeight) ||
    value.analysisWidth < 16 ||
    value.analysisHeight < 16 ||
    Math.max(value.analysisWidth, value.analysisHeight) >
      CROP_V12_CONFIG.analysisLongEdge
  )
    throw new Error('CROP_V12_EVIDENCE_INVALID');
  validateBand(
    value.anchorBoardBand,
    Number.MAX_SAFE_INTEGER,
    Number.MAX_SAFE_INTEGER,
  );
  if (value.status === 'registered') {
    if (
      value.reason !== 'registered_from_four_point_anchor' ||
      value.registeredBoardBand === null ||
      value.inlierRatio === null ||
      value.p90ResidualPx === null
    )
      throw new Error('CROP_V12_EVIDENCE_INVALID');
    validateBand(
      value.registeredBoardBand,
      Number.MAX_SAFE_INTEGER,
      Number.MAX_SAFE_INTEGER,
    );
  } else if (value.registeredBoardBand !== null)
    throw new Error('CROP_V12_EVIDENCE_INVALID');
}
