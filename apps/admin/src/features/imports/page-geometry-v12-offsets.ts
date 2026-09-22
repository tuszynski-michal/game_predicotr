import type { PageGeometryPoint, PageGeometryQuad } from './page-geometry-mesh';

export interface V12FrameOffsets {
  readonly top: number;
  readonly bottom: number;
  readonly left: number;
  readonly right: number;
}
export type V12OffsetDraft = Partial<V12FrameOffsets>;

const finite = (value: number) =>
  Number.isFinite(value) && Math.abs(value) <= 100;

export function validV12FrameOffsets(value: unknown): value is V12FrameOffsets {
  if (!value || typeof value !== 'object') return false;
  const raw = value as V12FrameOffsets;
  return (
    finite(raw.top) &&
    finite(raw.bottom) &&
    finite(raw.left) &&
    finite(raw.right)
  );
}

export function validV12OffsetDraft(value: unknown): value is V12OffsetDraft {
  if (!value || typeof value !== 'object') return false;
  const raw = value as Record<string, unknown>;
  return (
    Object.keys(raw).every((key) =>
      ['top', 'bottom', 'left', 'right'].includes(key),
    ) &&
    Object.values(raw).every((item) => typeof item === 'number' && finite(item))
  );
}

function mapper(quad: PageGeometryQuad) {
  const [a, b, c, d] = quad;
  const dx1 = b.x - c.x;
  const dx2 = d.x - c.x;
  const dy1 = b.y - c.y;
  const dy2 = d.y - c.y;
  const dx3 = a.x - b.x + c.x - d.x;
  const dy3 = a.y - b.y + c.y - d.y;
  const determinant = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(determinant) < 1e-9) return null;
  const g = (dx3 * dy2 - dx2 * dy3) / determinant;
  const h = (dx1 * dy3 - dx3 * dy1) / determinant;
  const bx = b.x - a.x + g * b.x;
  const by = b.y - a.y + g * b.y;
  const dx = d.x - a.x + h * d.x;
  const dy = d.y - a.y + h * d.y;
  return {
    forward(u: number, v: number): PageGeometryPoint {
      const scale = g * u + h * v + 1;
      return {
        x: (a.x + bx * u + dx * v) / scale,
        y: (a.y + by * u + dy * v) / scale,
      };
    },
    inverse(point: PageGeometryPoint): { u: number; v: number } | null {
      const ax = point.x * g - bx;
      const ay = point.y * g - by;
      const cx = point.x * h - dx;
      const cy = point.y * h - dy;
      const det = ax * cy - ay * cx;
      if (Math.abs(det) < 1e-9) return null;
      const rx = a.x - point.x;
      const ry = a.y - point.y;
      return { u: (rx * cy - ry * cx) / det, v: (ax * ry - ay * rx) / det };
    },
  };
}

export function v12FrameFromGrid(
  grid: PageGeometryQuad,
  offsets: V12FrameOffsets,
): PageGeometryQuad | null {
  if (
    offsets.left < 0 ||
    offsets.right < 0 ||
    offsets.top < 0 ||
    offsets.bottom < 0
  )
    return null;
  if (offsets.left + offsets.right + offsets.top + offsets.bottom === 0)
    return null;
  return v12PreviewFrameFromGrid(grid, offsets);
}

export function v12PreviewFrameFromGrid(
  grid: PageGeometryQuad,
  offsets: V12FrameOffsets,
): PageGeometryQuad | null {
  if (!validV12FrameOffsets(offsets)) return null;
  const map = mapper(grid);
  if (map === null) return null;
  const left = -offsets.left / 100;
  const right = 1 + offsets.right / 100;
  const top = -offsets.top / 100;
  const bottom = 1 + offsets.bottom / 100;
  const result: PageGeometryQuad = [
    map.forward(left, top),
    map.forward(right, top),
    map.forward(right, bottom),
    map.forward(left, bottom),
  ];
  return result.every(
    (point) => Number.isFinite(point.x) && Number.isFinite(point.y),
  )
    ? result
    : null;
}

export function v12OffsetsFromPair(
  grid: PageGeometryQuad,
  frame: PageGeometryQuad,
): V12FrameOffsets | null {
  const map = mapper(grid);
  if (map === null) return null;
  const points = frame.map(map.inverse);
  if (points.some((point) => point === null)) return null;
  const [a, b, c, d] = points as { u: number; v: number }[];
  const offsets: V12FrameOffsets = {
    top: -50 * (a.v + b.v),
    bottom: 50 * (c.v + d.v - 2),
    left: -50 * (a.u + d.u),
    right: 50 * (b.u + c.u - 2),
  };
  const reconstructed = v12FrameFromGrid(grid, offsets);
  if (
    reconstructed === null ||
    reconstructed.some(
      (point, index) =>
        Math.hypot(point.x - frame[index]!.x, point.y - frame[index]!.y) > 2,
    )
  )
    return null;
  return offsets;
}
