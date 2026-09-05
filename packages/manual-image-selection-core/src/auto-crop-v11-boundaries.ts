import {
  CROP_V11_POLICY,
  CROP_V11_CONFIG,
  median,
  luminance,
  detectStructuralLayout,
  type CropBox,
  type LayoutEvidence,
  type StructuralSample,
} from '@game-predictor/manual-image-selection-core/auto-crop-v11';
const w = (b: CropBox) => b.right - b.left,
  h = (b: CropBox) => b.bottom - b.top;
export interface StructuralCropEvidence {
  policy: typeof CROP_V11_POLICY;
  status: 'detected' | 'needs_manual_crop';
  reason:
    | LayoutEvidence['reason']
    | 'number_regions_missing'
    | 'source_support_incomplete';
  analysisWidth: number;
  analysisHeight: number;
  candidateCount: number;
  boards: readonly CropBox[];
  labels: readonly CropBox[];
  paddingPx: number;
  localizationUncertaintyPx: number;
  crop: { width: number; height: number; topY: number; bottomY: number };
}

export function findNumberRegions(
  sample: StructuralSample,
  boards: readonly CropBox[],
): CropBox[] {
  const gray = luminance(sample),
    result: CropBox[] = [];
  for (const [index, board] of boards.entries()) {
    const row = boards.slice(
      Math.floor(index / 3) * 3,
      Math.floor(index / 3) * 3 + 3,
    );
    const first = row[0]!,
      last = row.at(-1)!;
    const slope =
      boards.length === 9
        ? (last.top + last.bottom - (first.top + first.bottom)) /
          (last.left + last.right - (first.left + first.right))
        : 0;
    if (!Number.isFinite(slope) || Math.abs(slope) > 0.6) return [];
    const center = (board.left + board.right) / 2;
    const tiltExtent = (Math.abs(slope) * w(board)) / 2;
    const localTop = board.top + tiltExtent,
      localBottom = board.bottom - tiltExtent;
    const localHeight = localBottom - localTop;
    if (localHeight <= 0) return [];
    const pixel = (x: number, y: number) => {
      const sourceY = Math.round(y + slope * (x - center));
      return sourceY >= 0 && sourceY < sample.height
        ? gray[sourceY * sample.width + x]!
        : 0;
    };
    const l = Math.max(0, Math.floor(board.left + w(board) * 0.15)),
      r = Math.min(sample.width, Math.ceil(board.right - w(board) * 0.15));
    const t = Math.max(0, Math.floor(localTop + localHeight * 0.72)),
      b = Math.min(
        sample.height,
        Math.ceil(
          localBottom +
            localHeight * CROP_V11_CONFIG.numberSearchBelowBoardRatio,
        ),
      );
    const active: number[] = [];
    const transitionsByRow = new Map<number, number>();
    for (let y = t; y < b; y++) {
      let n = 0,
        transitions = 0;
      for (let x = l + 1; x < r; x++) {
        const bright = pixel(x, y) >= 180;
        n += Number(bright);
        if (bright !== pixel(x - 1, y) >= 180) transitions++;
      }
      transitionsByRow.set(y, transitions);
      if (n / (r - l) >= 0.12) active.push(y);
    }
    const bands: number[][] = [];
    for (const y of active) {
      const last = bands.at(-1);
      if (last && y - last.at(-1)! <= 2) last.push(y);
      else bands.push([y]);
    }
    const candidates = bands.filter(
      (rows) =>
        rows.length >= 2 &&
        rows.some((y) => (transitionsByRow.get(y) ?? 0) >= 6) &&
        rows.at(-1)! - rows[0]! + 1 <= h(board) * 0.28 &&
        (rows[0]! + rows.at(-1)!) / 2 >= localTop + localHeight * 0.85,
    );
    const boxes = candidates
      .map((rows) => {
        const top = rows[0]!,
          bottom = rows.at(-1)! + 1;
        let left = r,
          right = l;
        for (let y = top; y < bottom; y++)
          for (let x = l; x < r; x++)
            if (pixel(x, y) >= 180) {
              left = Math.min(left, x);
              right = Math.max(right, x + 1);
            }
        return { left, top, right, bottom };
      })
      .filter((box) => w(box) / h(box) >= 2 && w(box) >= w(board) * 0.25);
    boxes.sort(
      (a, b) =>
        Math.abs(a.bottom - localBottom) - Math.abs(b.bottom - localBottom),
    );
    if (!boxes.length) return [];
    if (
      boxes.length > 1 &&
      Math.abs(boxes[1]!.bottom - localBottom) -
        Math.abs(boxes[0]!.bottom - localBottom) <
        3
    )
      return [];
    const chosen = boxes[0]!;
    const ys = [
      slope * (chosen.left - center),
      slope * (chosen.right - center),
    ];
    result.push({
      ...chosen,
      top: Math.max(0, Math.floor(chosen.top + Math.min(...ys))),
      bottom: Math.min(
        sample.height,
        Math.ceil(chosen.bottom + Math.max(...ys)),
      ),
    });
  }
  return result;
}
export function boundStructuralCrop(
  layout: LayoutEvidence,
  labels: readonly CropBox[],
  source: { width: number; height: number },
): StructuralCropEvidence {
  if (
    !Number.isInteger(source.width) ||
    !Number.isInteger(source.height) ||
    source.width < 1 ||
    source.height < 1
  )
    throw new Error('CROP_V11_SOURCE_INVALID');
  const sx = source.width / layout.analysisWidth,
    sy = source.height / layout.analysisHeight;
  if (
    !Number.isFinite(sx) ||
    !Number.isFinite(sy) ||
    Math.abs(sx / sy - 1) > 0.01
  )
    throw new Error('CROP_V11_COORDINATES_INVALID');
  const map = (b: CropBox): CropBox => ({
    left: Math.floor(b.left * sx),
    top: Math.floor(b.top * sy),
    right: Math.ceil(b.right * sx),
    bottom: Math.ceil(b.bottom * sy),
  });
  const uncertainty = Math.ceil(2 * sy),
    medianBoardHeight = median(layout.boards.map(h)),
    topPadding =
      Math.ceil(
        Math.max(4, medianBoardHeight * CROP_V11_CONFIG.paddingRatio) * sy,
      ) + uncertainty,
    bottomPadding =
      Math.ceil(
        Math.max(4, medianBoardHeight * CROP_V11_CONFIG.bottomPaddingRatio) *
          sy,
      ) + uncertainty;
  const base: StructuralCropEvidence = {
    policy: CROP_V11_POLICY,
    status: 'needs_manual_crop',
    reason: layout.reason,
    analysisWidth: layout.analysisWidth,
    analysisHeight: layout.analysisHeight,
    candidateCount: layout.candidateCount,
    boards: layout.boards.map(map),
    labels: labels.map(map),
    paddingPx: Math.max(topPadding, bottomPadding),
    localizationUncertaintyPx: uncertainty,
    crop: { ...source, topY: 0, bottomY: source.height },
  };
  if (layout.status !== 'detected') return base;
  if (labels.length !== 9) return { ...base, reason: 'number_regions_missing' };
  const all = [...base.boards, ...base.labels];
  if (
    base.boards.length !== 9 ||
    all.some(
      (b) =>
        b.left <= 0 ||
        b.top <= 0 ||
        b.right >= source.width ||
        b.bottom >= source.height,
    )
  )
    return { ...base, reason: 'source_support_incomplete' };
  // A high threshold can retain only the lower, textured portion of every
  // top-row board. The independently confirmed number band supplies a second
  // lower edge: one median board height above it is a conservative estimate of
  // the missing board top. This only expands the crop and cannot cut content.
  const measuredTop = Math.min(...layout.boards.map((board) => board.top)),
    recoveredTopCandidate = Math.min(
      ...labels.map((label) => label.top - medianBoardHeight),
    ),
    recoveredTop = Math.floor(
      (measuredTop - recoveredTopCandidate >=
      medianBoardHeight * CROP_V11_CONFIG.topRecoveryMinimumGapRatio
        ? recoveredTopCandidate
        : measuredTop) * sy,
    ),
    topY = Math.max(
      0,
      Math.min(recoveredTop, ...all.map((b) => b.top)) - topPadding,
    ),
    bottomY = Math.min(
      source.height,
      Math.max(...all.map((b) => b.bottom)) + bottomPadding,
    );
  return {
    ...base,
    status: 'detected',
    reason: 'complete_layout',
    crop: { ...source, topY, bottomY },
  };
}
export function detectStructuralCrop(
  sample: StructuralSample,
  source: { width: number; height: number },
): StructuralCropEvidence {
  const layout = detectStructuralLayout(sample);
  return boundStructuralCrop(
    layout,
    layout.status === 'detected'
      ? findNumberRegions(sample, layout.boards)
      : [],
    source,
  );
}
export function validateStructuralEvidence(
  value: StructuralCropEvidence,
): void {
  const fail = () => {
    throw new Error('CROP_V11_EVIDENCE_INVALID');
  };
  if (
    !value ||
    value.policy !== CROP_V11_POLICY ||
    !['detected', 'needs_manual_crop'].includes(value.status) ||
    ![
      'complete_layout',
      'insufficient_boards',
      'incomplete_layout',
      'ambiguous_layout',
      'candidate_budget_exceeded',
      'number_regions_missing',
      'source_support_incomplete',
    ].includes(value.reason)
  )
    fail();
  const c = value.crop;
  if (
    !c ||
    ![
      c.width,
      c.height,
      c.topY,
      c.bottomY,
      value.analysisWidth,
      value.analysisHeight,
      value.paddingPx,
      value.localizationUncertaintyPx,
      value.candidateCount,
    ].every(Number.isInteger) ||
    c.width < 1 ||
    c.height < 1 ||
    c.topY < 0 ||
    c.bottomY > c.height ||
    c.topY >= c.bottomY ||
    value.analysisWidth < 8 ||
    value.analysisHeight < 8 ||
    Math.max(value.analysisWidth, value.analysisHeight) > 1600 ||
    value.candidateCount < 0 ||
    value.candidateCount > 96 ||
    value.paddingPx < 0 ||
    value.localizationUncertaintyPx < 0
  )
    fail();
  if (
    !Array.isArray(value.boards) ||
    !Array.isArray(value.labels) ||
    value.boards.length > 9 ||
    value.labels.length > 9
  )
    fail();
  const all = [...value.boards, ...value.labels];
  if (
    all.some(
      (b) =>
        ![b.left, b.top, b.right, b.bottom].every(Number.isFinite) ||
        b.left < 0 ||
        b.top < 0 ||
        b.right > c.width ||
        b.bottom > c.height ||
        w(b) <= 0 ||
        h(b) <= 0,
    )
  )
    fail();
  if (
    value.status === 'needs_manual_crop' &&
    (c.topY !== 0 || c.bottomY !== c.height)
  )
    fail();
  if (
    value.status === 'detected' &&
    (value.reason !== 'complete_layout' ||
      value.boards.length !== 9 ||
      value.labels.length !== 9 ||
      all.some((b) => b.top < c.topY || b.bottom > c.bottomY))
  )
    fail();
}
