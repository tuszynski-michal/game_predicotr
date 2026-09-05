/** Independent experimental detector. No file names, source history or RGB gates. */
export const CROP_V11_POLICY =
  'selected-image-board-band-v11-full-layout-structural' as const;
export const CROP_V11_CONFIG = Object.freeze({
  levels: [960, 1600] as const,
  maxCandidates: 96,
  maxRows: 192,
  luminanceThresholds: [0, 95, 135, 175] as const,
  dilationRadii: [2, 3, 4, 5, 6] as const,
  paddingRatio: 0.2,
  dilationAspects: [1, 2] as const,
  candidateBoundsVersion: 'undilated-support-v2',
});
export const CROP_V11_FINGERPRINT = `${CROP_V11_POLICY}|bilinear-rgba-v1|number-bands-v3-row-shear-complete-band|${JSON.stringify(CROP_V11_CONFIG)}`;
export interface CropBox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}
export interface StructuralBoard extends CropBox {
  textureTiles: number;
  support: number;
}
export interface StructuralSample {
  width: number;
  height: number;
  rgba: Uint8ClampedArray;
}
export interface LayoutEvidence {
  status: 'detected' | 'needs_manual_crop';
  reason:
    | 'complete_layout'
    | 'insufficient_boards'
    | 'incomplete_layout'
    | 'ambiguous_layout'
    | 'candidate_budget_exceeded';
  boards: readonly StructuralBoard[];
  candidateCount: number;
  analysisWidth: number;
  analysisHeight: number;
}
const w = (b: CropBox) => b.right - b.left;
const h = (b: CropBox) => b.bottom - b.top;
const cx = (b: CropBox) => (b.left + b.right) / 2;
const cy = (b: CropBox) => (b.top + b.bottom) / 2;
export function median(values: readonly number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(sorted.length / 2)] ?? 0;
}
function intersection(a: CropBox, b: CropBox): number {
  return (
    Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left)) *
    Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top))
  );
}
function similar(a: CropBox, b: CropBox): boolean {
  return intersection(a, b) / Math.min(w(a) * h(a), w(b) * h(b)) > 0.65;
}
export function sameStructuralCandidate(a: CropBox, b: CropBox): boolean {
  // Containment alone is not duplicate evidence: a larger component can include
  // a label, an arrow or multiple boards. Do not grow the smaller one into it.
  return intersection(a, b) / Math.max(w(a) * h(a), w(b) * h(b)) > 0.65;
}
export function removeDilationHalo(
  box: CropBox,
  rx: number,
  ry: number,
  width = Infinity,
  height = Infinity,
): CropBox {
  // A clipped halo does not prove where source support ends. Keep the image
  // boundary so the existing incomplete-source gate still rejects it.
  return {
    left: box.left === 0 ? 0 : box.left + rx,
    top: box.top === 0 ? 0 : box.top + ry,
    right: box.right === width ? width : box.right - rx,
    bottom: box.bottom === height ? height : box.bottom - ry,
  };
}
export function validateStructuralSample(s: StructuralSample): void {
  if (
    !Number.isInteger(s.width) ||
    !Number.isInteger(s.height) ||
    s.width < 8 ||
    s.height < 8 ||
    Math.max(s.width, s.height) > 1600 ||
    s.rgba.length !== s.width * s.height * 4
  )
    throw new Error('CROP_V11_SAMPLE_INVALID');
}
export function luminance(s: StructuralSample): Uint8Array {
  const gray = new Uint8Array(s.width * s.height);
  for (let i = 0; i < gray.length; i++)
    gray[i] = Math.round(
      0.299 * s.rgba[i * 4]! +
        0.587 * s.rgba[i * 4 + 1]! +
        0.114 * s.rgba[i * 4 + 2]!,
    );
  return gray;
}
// Integral binary dilation, O(pixels), regardless of structuring-element size.
function dilate(
  mask: Uint8Array,
  width: number,
  height: number,
  rx: number,
  ry: number,
): Uint8Array {
  const stride = width + 1,
    sums = new Uint32Array(stride * (height + 1));
  for (let y = 0; y < height; y++) {
    let row = 0;
    for (let x = 0; x < width; x++) {
      row += mask[y * width + x]!;
      sums[(y + 1) * stride + x + 1] = sums[y * stride + x + 1]! + row;
    }
  }
  const result = new Uint8Array(mask.length);
  for (let y = 0; y < height; y++)
    for (let x = 0; x < width; x++) {
      const l = Math.max(0, x - rx),
        r = Math.min(width, x + rx + 1),
        t = Math.max(0, y - ry),
        b = Math.min(height, y + ry + 1);
      result[y * width + x] = Number(
        sums[b * stride + r]! -
          sums[b * stride + l]! -
          sums[t * stride + r]! +
          sums[t * stride + l]! >
          0,
      );
    }
  return result;
}
function components(
  mask: Uint8Array,
  width: number,
  height: number,
): CropBox[] {
  const seen = new Uint8Array(mask.length),
    queue = new Int32Array(mask.length),
    boxes: CropBox[] = [];
  for (let seed = 0; seed < mask.length; seed++) {
    if (!mask[seed] || seen[seed]) continue;
    let head = 0,
      tail = 1,
      l = seed % width,
      r = l,
      t = Math.floor(seed / width),
      b = t;
    queue[0] = seed;
    seen[seed] = 1;
    while (head < tail) {
      const i = queue[head++]!,
        x = i % width,
        y = Math.floor(i / width);
      l = Math.min(l, x);
      r = Math.max(r, x);
      t = Math.min(t, y);
      b = Math.max(b, y);
      for (const n of [
        x > 0 ? i - 1 : -1,
        x + 1 < width ? i + 1 : -1,
        y > 0 ? i - width : -1,
        y + 1 < height ? i + width : -1,
      ])
        if (n >= 0 && mask[n] && !seen[n]) {
          seen[n] = 1;
          queue[tail++] = n;
        }
    }
    if (tail >= 8) boxes.push({ left: l, top: t, right: r + 1, bottom: b + 1 });
  }
  return boxes;
}
function texture(gray: Uint8Array, width: number, box: CropBox): number {
  // Interior texture must span both axes, not merely a bright rectangular border.
  let supported = 0;
  for (let ty = 0; ty < 3; ty++)
    for (let tx = 0; tx < 3; tx++) {
      const l = Math.ceil(box.left + w(box) * (0.08 + tx * 0.28)),
        r = Math.floor(box.left + w(box) * (0.08 + (tx + 1) * 0.28));
      const t = Math.ceil(box.top + h(box) * (0.08 + ty * 0.28)),
        b = Math.floor(box.top + h(box) * (0.08 + (ty + 1) * 0.28));
      let edges = 0,
        count = 0;
      for (let y = t; y < b; y++)
        for (let x = l; x < r; x++) {
          const i = y * width + x;
          count++;
          if (
            Math.abs(gray[i]! - gray[i - 1]!) +
              Math.abs(gray[i]! - gray[i - width]!) >
            32
          )
            edges++;
        }
      if (count > 0 && edges / count >= 0.1) supported++;
    }
  return supported;
}
export function detectStructuralCandidates(s: StructuralSample): {
  boards: StructuralBoard[];
  overflow: boolean;
} {
  validateStructuralSample(s);
  const gray = luminance(s),
    all: StructuralBoard[] = [];
  const scale = Math.max(s.width, s.height) / 960;
  for (const threshold of CROP_V11_CONFIG.luminanceThresholds) {
    const mask = new Uint8Array(gray.length);
    for (let y = 1; y < s.height - 1; y++)
      for (let x = 1; x < s.width - 1; x++) {
        const i = y * s.width + x;
        // Local gradient retains lettering and fruit alike; flat lights cannot suffice.
        mask[i] = Number(
          gray[i]! >= threshold &&
            Math.abs(gray[i]! - gray[i - 1]!) +
              Math.abs(gray[i]! - gray[i - s.width]!) >
              20,
        );
      }
    for (const aspect of CROP_V11_CONFIG.dilationAspects)
      for (const radius of CROP_V11_CONFIG.dilationRadii) {
        const rx = Math.max(1, Math.round(radius * scale * aspect)),
          ry = Math.max(1, Math.round((radius * scale) / aspect));
        for (const expanded of components(
          dilate(mask, s.width, s.height, rx, ry),
          s.width,
          s.height,
        )) {
          // Dilation joins nearby symbol edges; it must not enlarge the measured
          // support. Keeping that synthetic halo makes adjacent rows overlap.
          const box = removeDilationHalo(expanded, rx, ry, s.width, s.height);
          if (
            w(box) < s.width * 0.065 ||
            w(box) > s.width * 0.42 ||
            h(box) < s.height * 0.018 ||
            h(box) > s.height * 0.19 ||
            w(box) / h(box) < 1.15 ||
            w(box) / h(box) > 4.2
          )
            continue;
          const tiles = texture(gray, s.width, box);
          if (tiles < 7) continue;
          const match = all.find((existing) =>
            sameStructuralCandidate(existing, box),
          );
          if (match) {
            // Retain the union as uncertainty, never select the tightest threshold box.
            match.left = Math.min(match.left, box.left);
            match.top = Math.min(match.top, box.top);
            match.right = Math.max(match.right, box.right);
            match.bottom = Math.max(match.bottom, box.bottom);
            match.support++;
            match.textureTiles = Math.min(match.textureTiles, tiles);
          } else all.push({ ...box, textureTiles: tiles, support: 1 });
        }
      }
  }
  all.sort((a, b) => b.support - a.support || a.top - b.top || a.left - b.left);
  return {
    boards: all.slice(0, CROP_V11_CONFIG.maxCandidates),
    overflow: all.length > CROP_V11_CONFIG.maxCandidates,
  };
}
export function selectStructuralLayout(
  candidates: readonly StructuralBoard[],
  width: number,
  height: number,
): LayoutEvidence {
  const base = {
    boards: [] as StructuralBoard[],
    candidateCount: candidates.length,
    analysisWidth: width,
    analysisHeight: height,
  };
  const reject = (reason: LayoutEvidence['reason']): LayoutEvidence => ({
    ...base,
    status: 'needs_manual_crop',
    reason,
  });
  if (candidates.length > 96) return reject('candidate_budget_exceeded');
  if (candidates.length < 9) return reject('insufficient_boards');
  const sorted = [...candidates].sort((a, b) => cx(a) - cx(b) || cy(a) - cy(b));
  const rows: StructuralBoard[][] = [];
  for (let i = 0; i < sorted.length; i++)
    for (let j = i + 1; j < sorted.length; j++)
      for (let k = j + 1; k < sorted.length; k++) {
        const row = [sorted[i]!, sorted[j]!, sorted[k]!],
          [a, b, c] = row as [
            StructuralBoard,
            StructuralBoard,
            StructuralBoard,
          ];
        const mw = median(row.map(w)),
          mh = median(row.map(h));
        if (
          Math.max(...row.map(w)) / Math.min(...row.map(w)) > 1.7 ||
          Math.max(...row.map(h)) / Math.min(...row.map(h)) > 1.8
        )
          continue;
        const dx1 = cx(b) - cx(a),
          dx2 = cx(c) - cx(b),
          slope = (cy(c) - cy(a)) / (cx(c) - cx(a));
        if (
          dx1 < mw * 0.9 ||
          dx2 < mw * 0.9 ||
          dx1 > mw * 2 ||
          dx2 > mw * 2 ||
          Math.abs(slope) > 0.6 ||
          Math.abs(cy(b) - (cy(a) + slope * dx1)) > mh * 0.22 ||
          row.some((x, idx) =>
            row.slice(idx + 1).some((y) => intersection(x, y) > 0),
          )
        )
          continue;
        rows.push(row);
        if (rows.length > CROP_V11_CONFIG.maxRows)
          return reject('candidate_budget_exceeded');
      }
  rows.sort((a, b) => median(a.map(cy)) - median(b.map(cy)));
  const layouts: StructuralBoard[][] = [];
  for (let i = 0; i < rows.length; i++)
    for (let j = i + 1; j < rows.length; j++)
      for (let k = j + 1; k < rows.length; k++) {
        const rs = [rows[i]!, rows[j]!, rows[k]!],
          flat = rs.flat();
        if (
          new Set(flat).size !== 9 ||
          flat.some((a, idx) =>
            flat.slice(idx + 1).some((b) => intersection(a, b) > 0),
          )
        )
          continue;
        const mw = median(flat.map(w)),
          mh = median(flat.map(h));
        // Cabinet buttons can form another row below the panel. Cross-row scale
        // consistency is required too, not only three similar objects per row.
        if (
          Math.max(...flat.map(w)) / Math.min(...flat.map(w)) > 1.7 ||
          Math.max(...flat.map(h)) / Math.min(...flat.map(h)) > 1.8
        )
          continue;
        let valid = true;
        for (let col = 0; col < 3; col++) {
          const a = rs[0]![col]!,
            b = rs[1]![col]!,
            c = rs[2]![col]!;
          const dy1 = cy(b) - cy(a),
            dy2 = cy(c) - cy(b);
          if (
            dy1 < mh * 0.95 ||
            dy2 < mh * 0.95 ||
            dy1 > mh * 2.4 ||
            dy2 > mh * 2.4 ||
            Math.max(dy1, dy2) / Math.min(dy1, dy2) > 1.6 ||
            Math.abs(cx(b) - cx(a)) > mw * 0.65 ||
            Math.abs(cx(c) - cx(b)) > mw * 0.65
          )
            valid = false;
        }
        if (
          valid &&
          !layouts.some((previous) =>
            previous.every((box, idx) => similar(box, flat[idx]!)),
          )
        )
          layouts.push(flat);
        if (layouts.length > 1) return reject('ambiguous_layout');
      }
  return layouts.length === 1
    ? {
        ...base,
        status: 'detected',
        reason: 'complete_layout',
        boards: layouts[0]!,
      }
    : reject('incomplete_layout');
}
export function detectStructuralLayout(
  sample: StructuralSample,
): LayoutEvidence {
  const candidates = detectStructuralCandidates(sample);
  if (candidates.overflow)
    return {
      status: 'needs_manual_crop',
      reason: 'candidate_budget_exceeded',
      boards: [],
      candidateCount: 96,
      analysisWidth: sample.width,
      analysisHeight: sample.height,
    };
  return selectStructuralLayout(candidates.boards, sample.width, sample.height);
}
