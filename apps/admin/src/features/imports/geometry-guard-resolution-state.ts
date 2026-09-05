import type {
  ImageGeometryGuardBoardTargetResponse,
  PageGeometryPoint,
} from '@game-predictor/admin-api-client';

export type GuardQuad = readonly [
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
];

export function guardQuadFromUnknown(value: unknown): GuardQuad | null {
  const raw =
    typeof value === 'object' && value !== null && 'quad' in value
      ? (value as { readonly quad?: unknown }).quad
      : value;
  if (!Array.isArray(raw) || raw.length !== 4) return null;
  const points = raw.map((point) => {
    if (
      typeof point !== 'object' ||
      point === null ||
      !('x' in point) ||
      !('y' in point) ||
      typeof point.x !== 'number' ||
      typeof point.y !== 'number' ||
      !Number.isFinite(point.x) ||
      !Number.isFinite(point.y)
    ) {
      return null;
    }
    return { x: Math.round(point.x), y: Math.round(point.y) };
  });
  return points.every((point) => point !== null)
    ? (points as unknown as GuardQuad)
    : null;
}

export function initialGuardQuad(
  target: ImageGeometryGuardBoardTargetResponse,
): GuardQuad | null {
  return (
    guardQuadFromUnknown(target.proposedSymbolGridQuad) ??
    guardQuadFromUnknown(target.analysisQuad) ??
    guardQuadFromUnknown(target.pageGeometry)
  );
}

export function guardGridLines(
  quad: GuardQuad,
): readonly (readonly [PageGeometryPoint, PageGeometryPoint])[] {
  const lines: Array<readonly [PageGeometryPoint, PageGeometryPoint]> = [];
  for (let column = 1; column < 5; column += 1) {
    lines.push([
      interpolateGuardQuad(quad, column / 5, 0),
      interpolateGuardQuad(quad, column / 5, 1),
    ]);
  }
  for (let row = 1; row < 3; row += 1) {
    lines.push([
      interpolateGuardQuad(quad, 0, row / 3),
      interpolateGuardQuad(quad, 1, row / 3),
    ]);
  }
  return lines;
}

export function toggleUnavailableCell(
  values: readonly number[],
  cellIndex: number,
): readonly number[] {
  const next = new Set(values);
  if (next.has(cellIndex)) next.delete(cellIndex);
  else next.add(cellIndex);
  return [...next].sort((left, right) => left - right);
}

export function toggleUnavailableGroup(
  values: readonly number[],
  cellIndices: readonly number[],
): readonly number[] {
  const next = new Set(values);
  const remove = cellIndices.every((cellIndex) => next.has(cellIndex));
  for (const cellIndex of cellIndices) {
    if (remove) next.delete(cellIndex);
    else next.add(cellIndex);
  }
  return [...next].sort((left, right) => left - right);
}

function interpolateGuardQuad(
  quad: GuardQuad,
  horizontal: number,
  vertical: number,
): PageGeometryPoint {
  const [topLeft, topRight, bottomRight, bottomLeft] = quad;
  const top = {
    x: topLeft.x + (topRight.x - topLeft.x) * horizontal,
    y: topLeft.y + (topRight.y - topLeft.y) * horizontal,
  };
  const bottom = {
    x: bottomLeft.x + (bottomRight.x - bottomLeft.x) * horizontal,
    y: bottomLeft.y + (bottomRight.y - bottomLeft.y) * horizontal,
  };
  return {
    x: top.x + (bottom.x - top.x) * vertical,
    y: top.y + (bottom.y - top.y) * vertical,
  };
}
