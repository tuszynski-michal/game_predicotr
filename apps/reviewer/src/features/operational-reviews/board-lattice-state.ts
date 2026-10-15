import type {
  OperationalImageReviewGeometryPoint,
  ImageGridReviewGeometryPreviewCommand,
} from '@game-predictor/admin-api-client';
import {
  manualGridQualification,
  type ManualGridFlags,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';
import { gridCellPolygonsWithoutPixels } from './board-geometry-correction-state.ts';
import {
  operationalReviewPointInLattice,
  type OperationalReviewGeometryCorners,
} from './operational-review-state.ts';

export type BoardLatticeNodes = readonly OperationalImageReviewGeometryPoint[];

/** The generated transport tuple has exactly 24 entries, validated before conversion. */
export function boardLatticePayload(
  nodes: BoardLatticeNodes,
): NonNullable<ImageGridReviewGeometryPreviewCommand['latticeNodes']> {
  const validated = parseBoardLattice(nodes);
  if (validated === null)
    throw new Error('Węzły muszą tworzyć poprawną siatkę 5 na 3.');
  return validated.map(({ x, y }) => ({ x, y })) as unknown as NonNullable<
    ImageGridReviewGeometryPreviewCommand['latticeNodes']
  >;
}

/** Exact source coordinates; a neural draft never goes through integer helpers. */
export function parseBoardLattice(value: unknown): BoardLatticeNodes | null {
  if (!Array.isArray(value) || value.length !== 24) return null;
  const nodes = value.map((point) => {
    if (!point || typeof point !== 'object') return null;
    const { x, y } = point as { readonly x?: unknown; readonly y?: unknown };
    return typeof x === 'number' &&
      Number.isFinite(x) &&
      typeof y === 'number' &&
      Number.isFinite(y)
      ? { x, y }
      : null;
  });
  if (nodes.some((point) => point === null)) return null;
  const lattice = nodes as BoardLatticeNodes;
  if (
    boardLatticeCells(lattice).some((cell) =>
      cell.some((a, i) => {
        const b = cell[(i + 1) % 4]!,
          c = cell[(i + 2) % 4]!;
        return (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x) <= 1e-8;
      }),
    )
  )
    return null;
  // A locally convex cell is insufficient: remote folds can cross other cells.
  const edges: readonly [number, number][] = lattice.flatMap((_, i) => [
    ...(i % 6 < 5 ? [[i, i + 1] as [number, number]] : []),
    ...(i < 18 ? [[i, i + 6] as [number, number]] : []),
  ]);
  const cross = (a: number, b: number, c: number) =>
    (lattice[b]!.x - lattice[a]!.x) * (lattice[c]!.y - lattice[a]!.y) -
    (lattice[b]!.y - lattice[a]!.y) * (lattice[c]!.x - lattice[a]!.x);
  const onSegment = (a: number, b: number, c: number) =>
    Math.abs(cross(a, b, c)) <= 1e-8 &&
    lattice[c]!.x >= Math.min(lattice[a]!.x, lattice[b]!.x) - 1e-8 &&
    lattice[c]!.x <= Math.max(lattice[a]!.x, lattice[b]!.x) + 1e-8 &&
    lattice[c]!.y >= Math.min(lattice[a]!.y, lattice[b]!.y) - 1e-8 &&
    lattice[c]!.y <= Math.max(lattice[a]!.y, lattice[b]!.y) + 1e-8;
  if (
    edges.some(([a, b], i) =>
      edges.slice(i + 1).some(([c, d]) => {
        if ([a, b].includes(c) || [a, b].includes(d)) return false;
        return (
          (cross(a, b, c) * cross(a, b, d) < 0 &&
            cross(c, d, a) * cross(c, d, b) < 0) ||
          onSegment(a, b, c) ||
          onSegment(a, b, d) ||
          onSegment(c, d, a) ||
          onSegment(c, d, b)
        );
      }),
    )
  )
    return null;
  return lattice;
}

/** Explicit regularization; never called by changing the handle mode. */
export function regularBoardLattice(
  corners: OperationalReviewGeometryCorners,
): BoardLatticeNodes {
  if (
    corners.some((a, i) => {
      const b = corners[(i + 1) % 4]!,
        c = corners[(i + 2) % 4]!;
      return (
        !Number.isFinite(a.x) ||
        !Number.isFinite(a.y) ||
        (b.x - a.x) * (c.y - b.y) - (b.y - a.y) * (c.x - b.x) <= 1e-8
      );
    })
  )
    throw new Error(
      'Narożniki muszą tworzyć wypukłą, nieprzecinającą się siatkę.',
    );
  const nodes = Array.from({ length: 24 }, (_, i) =>
    operationalReviewPointInLattice(
      corners,
      (i % 6) / 5,
      Math.floor(i / 6) / 3,
    ),
  );
  if (parseBoardLattice(nodes) === null)
    throw new Error('Narożniki nie tworzą poprawnej siatki.');
  return nodes;
}

/** Map exact nodes through the old/new outline, retaining internal corrections. */
export function transformedBoardLattice(
  nodes: BoardLatticeNodes,
  corners: OperationalReviewGeometryCorners,
): BoardLatticeNodes {
  regularBoardLattice(corners);
  const old = boardLatticeCorners(nodes);
  regularBoardLattice(old);
  // Normalize source coordinates to keep elimination stable for large photos.
  const x0 = old[0].x,
    y0 = old[0].y;
  const scale = Math.max(...old.map((p) => Math.hypot(p.x - x0, p.y - y0)));
  const rows = old.flatMap((p, i) => {
    const x = (p.x - x0) / scale,
      y = (p.y - y0) / scale;
    const q = corners[i]!;
    return [
      [x, y, 1, 0, 0, 0, -q.x * x, -q.x * y, q.x],
      [0, 0, 0, x, y, 1, -q.y * x, -q.y * y, q.y],
    ];
  });
  for (let i = 0; i < 8; i++) {
    let pivot = i;
    for (let j = i + 1; j < 8; j++)
      if (Math.abs(rows[j]![i]!) > Math.abs(rows[pivot]![i]!)) pivot = j;
    [rows[i], rows[pivot]] = [rows[pivot]!, rows[i]!];
    const divisor = rows[i]![i]!;
    if (Math.abs(divisor) < 1e-12)
      throw new Error('Nie można wyznaczyć homografii siatki.');
    for (let k = i; k <= 8; k++) rows[i]![k] = rows[i]![k]! / divisor;
    for (let j = 0; j < 8; j++)
      if (j !== i) {
        const factor = rows[j]![i]!;
        for (let k = i; k <= 8; k++)
          rows[j]![k] = rows[j]![k]! - factor * rows[i]![k]!;
      }
  }
  const h = rows.map((row) => row[8]!);
  const next = nodes.map((p) => {
    const x = (p.x - x0) / scale,
      y = (p.y - y0) / scale;
    const denominator = h[6]! * x + h[7]! * y + 1;
    if (denominator <= 1e-10) throw new Error('Homografia przecina siatkę.');
    return {
      x: (h[0]! * x + h[1]! * y + h[2]!) / denominator,
      y: (h[3]! * x + h[4]! * y + h[5]!) / denominator,
    };
  });
  // Anchor outer handles exactly to the requested coordinates.
  [0, 5, 23, 18].forEach((index, i) => {
    next[index] = { ...corners[i]! };
  });
  if (parseBoardLattice(next) === null)
    throw new Error('Przekształcenie przecina komórki siatki.');
  return next;
}

export function boardLatticeCorners(
  nodes: BoardLatticeNodes,
): OperationalReviewGeometryCorners {
  return [nodes[0]!, nodes[5]!, nodes[23]!, nodes[18]!].map(({ x, y }) => ({
    x,
    y,
  })) as OperationalReviewGeometryCorners;
}

/** View framing only; this rectangle never enters a geometry request. */
export function boardLatticeViewportExtent(
  nodes: BoardLatticeNodes,
): OperationalReviewGeometryCorners {
  const minX = Math.min(...nodes.map((p) => p.x)),
    maxX = Math.max(...nodes.map((p) => p.x));
  const minY = Math.min(...nodes.map((p) => p.y)),
    maxY = Math.max(...nodes.map((p) => p.y));
  return [
    { x: minX, y: minY },
    { x: maxX, y: minY },
    { x: maxX, y: maxY },
    { x: minX, y: maxY },
  ];
}

/** Legacy request corners are StrictInt; only this redundant transport outline is rounded. */
export function boardLatticeTransportCorners(
  nodes: BoardLatticeNodes,
): OperationalReviewGeometryCorners {
  return boardLatticeCorners(nodes).map(({ x, y }) => ({
    x: Math.round(x),
    y: Math.round(y),
  })) as OperationalReviewGeometryCorners;
}

export function boardLatticeCells(
  nodes: BoardLatticeNodes,
): readonly (readonly OperationalImageReviewGeometryPoint[])[] {
  if (nodes.length !== 24) return [];
  return Array.from({ length: 15 }, (_, index) => {
    const start = Math.floor(index / 5) * 6 + (index % 5);
    return [
      nodes[start]!,
      nodes[start + 1]!,
      nodes[start + 7]!,
      nodes[start + 6]!,
    ];
  });
}

export function boardLatticeUnavailable(
  nodes: BoardLatticeNodes,
  width: number,
  height: number,
): readonly number[] {
  return boardLatticeCells(nodes).flatMap((cell, index) =>
    cell.some(
      ({ x, y }) =>
        x < -1e-6 || y < -1e-6 || x > width - 1 + 1e-6 || y > height - 1 + 1e-6,
    )
      ? [index]
      : [],
  );
}

export function boardLatticeWithoutPixels(
  nodes: BoardLatticeNodes,
  width: number,
  height: number,
): readonly number[] {
  return gridCellPolygonsWithoutPixels(boardLatticeCells(nodes), width, height);
}

/** Reuse the existing qualification validator with the real lattice mask. */
export function boardLatticeQualification(
  flags: ManualGridFlags,
  nodes: BoardLatticeNodes,
  width: number,
  height: number,
) {
  if (parseBoardLattice(nodes) === null)
    throw new Error('Węzły muszą tworzyć poprawną siatkę 5 na 3.');
  const unavailable = [
    ...new Set([
      ...flags.manualUnavailable,
      ...boardLatticeUnavailable(nodes, width, height),
    ]),
  ].sort((a, b) => a - b);
  // The in-frame extent adds no unavailable fields. Only the supplied real
  // cell mask participates in the existing partial/training validation.
  return manualGridQualification(
    { ...flags, manualUnavailable: unavailable },
    [
      { x: 0, y: 0 },
      { x: width - 1, y: 0 },
      { x: width - 1, y: height - 1 },
      { x: 0, y: height - 1 },
    ],
    width,
    height,
  );
}

export function boardLatticePointInSource(
  point: OperationalImageReviewGeometryPoint,
  viewport: { readonly x: number; readonly y: number },
  width: number,
  height: number,
  allowOutside: boolean,
): OperationalImageReviewGeometryPoint {
  const x = point.x + viewport.x,
    y = point.y + viewport.y;
  return allowOutside
    ? { x, y }
    : {
        x: Math.max(0, Math.min(width - 1, x)),
        y: Math.max(0, Math.min(height - 1, y)),
      };
}

export function translatedBoardLattice(
  nodes: BoardLatticeNodes,
  delta: OperationalImageReviewGeometryPoint,
  width: number,
  height: number,
  allowOutside: boolean,
): BoardLatticeNodes {
  const dx = allowOutside
    ? delta.x
    : Math.max(
        -Math.min(...nodes.map((p) => p.x)),
        Math.min(width - 1 - Math.max(...nodes.map((p) => p.x)), delta.x),
      );
  const dy = allowOutside
    ? delta.y
    : Math.max(
        -Math.min(...nodes.map((p) => p.y)),
        Math.min(height - 1 - Math.max(...nodes.map((p) => p.y)), delta.y),
      );
  return nodes.map((p) => ({ x: p.x + dx, y: p.y + dy }));
}
