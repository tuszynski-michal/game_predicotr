export type PageGeometryPoint = Readonly<{
  x: number;
  y: number;
}>;

export type PageGeometryQuad = readonly [
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
];

export type PageGeometryCorners = readonly [
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
  PageGeometryPoint,
];

export type PageGeometryMesh = readonly PageGeometryPoint[];

export type PageGeometryGuideLine = readonly [
  PageGeometryPoint,
  PageGeometryPoint,
];

export function appendPageGeometryCorner(
  current: readonly PageGeometryPoint[],
  point: PageGeometryPoint,
): readonly PageGeometryPoint[] {
  return current.length >= 4 ? current : [...current, point];
}

export function completePageGeometryCorners(
  points: readonly PageGeometryPoint[],
): PageGeometryCorners | null {
  if (points.length !== 4) return null;
  const corners = [
    points[0],
    points[1],
    points[2],
    points[3],
  ] as PageGeometryCorners;
  return isClockwiseScreenQuad(corners) ? corners : null;
}

function cross(
  origin: PageGeometryPoint,
  first: PageGeometryPoint,
  second: PageGeometryPoint,
): number {
  return (
    (first.x - origin.x) * (second.y - origin.y) -
    (first.y - origin.y) * (second.x - origin.x)
  );
}

/**
 * Screen coordinates grow downwards, so LT -> PT -> PD -> LD has positive
 * cross products. Requiring every turn to be positive rejects crossed,
 * concave and degenerate click sequences before they reach the API.
 */
export function isClockwiseScreenQuad(corners: PageGeometryCorners): boolean {
  return corners.every((point, index) => {
    const next = corners[(index + 1) % corners.length]!;
    const afterNext = corners[(index + 2) % corners.length]!;
    return cross(point, next, afterNext) > 0;
  });
}

export const PAGE_BOARD_COLUMNS = 3;
export const PAGE_BOARD_ROWS = 3;
export const PAGE_BOARD_COUNT = PAGE_BOARD_COLUMNS * PAGE_BOARD_ROWS;
export const PAGE_BOARD_CORNER_COUNT = 4;
export const PAGE_BOARD_PLACEMENT_POINT_COUNT =
  PAGE_BOARD_COUNT * PAGE_BOARD_CORNER_COUNT;
// Every board owns two independent edge lines.  Adjacent boards are separated
// by a real screen gutter, so a shared 4x4 cell lattice would systematically
// crop labels/gaps instead of following the nine red frames.
export const PAGE_MESH_COLUMNS = PAGE_BOARD_COLUMNS * 2;
export const PAGE_MESH_ROWS = PAGE_BOARD_ROWS * 2;
export const PAGE_MESH_POINT_COUNT = PAGE_MESH_COLUMNS * PAGE_MESH_ROWS;

export function appendPageGeometryBoardCorner(
  current: readonly PageGeometryPoint[],
  point: PageGeometryPoint,
  boardCount = PAGE_BOARD_COUNT,
): readonly PageGeometryPoint[] {
  const targetPointCount =
    normalizePageGeometryBoardCount(boardCount) * PAGE_BOARD_CORNER_COUNT;
  return current.length >= targetPointCount ? current : [...current, point];
}

function normalizePageGeometryBoardCount(boardCount: number): number {
  return Number.isInteger(boardCount) &&
    boardCount >= 1 &&
    boardCount <= PAGE_BOARD_COUNT
    ? boardCount
    : PAGE_BOARD_COUNT;
}

function pageGeometryQuadCenter(quad: PageGeometryQuad): PageGeometryPoint {
  return {
    x: quad.reduce((sum, point) => sum + point.x, 0) / quad.length,
    y: quad.reduce((sum, point) => sum + point.y, 0) / quad.length,
  };
}

function isNextPageGeometryQuadRowMajor(
  quads: readonly PageGeometryQuad[],
  quad: PageGeometryQuad,
): boolean {
  const index = quads.length;
  const row = Math.floor(index / PAGE_BOARD_COLUMNS);
  const column = index % PAGE_BOARD_COLUMNS;
  const center = pageGeometryQuadCenter(quad);
  if (column > 0 && center.x <= pageGeometryQuadCenter(quads[index - 1]!).x) {
    return false;
  }
  return (
    row === 0 ||
    center.y > pageGeometryQuadCenter(quads[index - PAGE_BOARD_COLUMNS]!).y
  );
}

export function pageGeometryQuadsFromCornerPlacement(
  points: readonly PageGeometryPoint[],
  boardCount = PAGE_BOARD_COUNT,
): readonly PageGeometryQuad[] {
  const quads: PageGeometryQuad[] = [];
  const completedBoardCount = Math.min(
    normalizePageGeometryBoardCount(boardCount),
    Math.floor(points.length / PAGE_BOARD_CORNER_COUNT),
  );
  for (let boardIndex = 0; boardIndex < completedBoardCount; boardIndex += 1) {
    const offset = boardIndex * PAGE_BOARD_CORNER_COUNT;
    const quad = completePageGeometryCorners(points.slice(offset, offset + 4));
    if (quad === null || !isNextPageGeometryQuadRowMajor(quads, quad)) break;
    quads.push(quad);
  }
  return quads;
}

export function completePageGeometryBoardQuads(
  points: readonly PageGeometryPoint[],
  boardCount = PAGE_BOARD_COUNT,
): readonly PageGeometryQuad[] | null {
  const normalizedBoardCount = normalizePageGeometryBoardCount(boardCount);
  if (points.length !== normalizedBoardCount * PAGE_BOARD_CORNER_COUNT)
    return null;
  const quads = pageGeometryQuadsFromCornerPlacement(
    points,
    normalizedBoardCount,
  );
  return quads.length === normalizedBoardCount ? quads : null;
}

const PAGE_BOARD_EDGE_RATIOS = [
  0, 0.2933333333, 0.3533333333, 0.6466666667, 0.7066666667, 1,
] as const;

function lerp(
  left: PageGeometryPoint,
  right: PageGeometryPoint,
  ratio: number,
): PageGeometryPoint {
  return {
    x: left.x + (right.x - left.x) * ratio,
    y: left.y + (right.y - left.y) * ratio,
  };
}

function bilinear(
  corners: PageGeometryCorners,
  u: number,
  v: number,
): PageGeometryPoint {
  const upper = lerp(corners[0], corners[1], u);
  const lower = lerp(corners[3], corners[2], u);
  return lerp(upper, lower, v);
}

function projectivePoint(
  quad: PageGeometryQuad,
  u: number,
  v: number,
): PageGeometryPoint {
  const [topLeft, topRight, bottomRight, bottomLeft] = quad;
  const dx1 = topRight.x - bottomRight.x;
  const dx2 = bottomLeft.x - bottomRight.x;
  const dx3 = topLeft.x - topRight.x + bottomRight.x - bottomLeft.x;
  const dy1 = topRight.y - bottomRight.y;
  const dy2 = bottomLeft.y - bottomRight.y;
  const dy3 = topLeft.y - topRight.y + bottomRight.y - bottomLeft.y;
  const determinant = dx1 * dy2 - dx2 * dy1;
  if (Math.abs(determinant) < 1e-9) {
    return bilinear(quad, u, v);
  }
  const perspectiveX = (dx3 * dy2 - dx2 * dy3) / determinant;
  const perspectiveY = (dx1 * dy3 - dx3 * dy1) / determinant;
  const scale = perspectiveX * u + perspectiveY * v + 1;
  if (Math.abs(scale) < 1e-9) {
    return bilinear(quad, u, v);
  }
  return {
    x:
      ((topRight.x - topLeft.x + perspectiveX * topRight.x) * u +
        (bottomLeft.x - topLeft.x + perspectiveY * bottomLeft.x) * v +
        topLeft.x) /
      scale,
    y:
      ((topRight.y - topLeft.y + perspectiveX * topRight.y) * u +
        (bottomLeft.y - topLeft.y + perspectiveY * bottomLeft.y) * v +
        topLeft.y) /
      scale,
  };
}

/**
 * Project the logical 5 x 3 symbol-cell boundaries back onto the source quad.
 * The downstream cropper rectifies the same quad before splitting it into
 * equal slots, so these lines describe the prospective cuts rather than a
 * cosmetic axis-aligned approximation.
 */
export function pageGeometrySymbolCutLines(
  quad: PageGeometryQuad,
  rows = 3,
  columns = 5,
): readonly PageGeometryGuideLine[] {
  if (
    !Number.isInteger(rows) ||
    !Number.isInteger(columns) ||
    rows < 1 ||
    columns < 1
  ) {
    return [];
  }
  return [
    ...Array.from({ length: columns - 1 }, (_, index) => {
      const u = (index + 1) / columns;
      return [
        projectivePoint(quad, u, 0),
        projectivePoint(quad, u, 1),
      ] as const;
    }),
    ...Array.from({ length: rows - 1 }, (_, index) => {
      const v = (index + 1) / rows;
      return [
        projectivePoint(quad, 0, v),
        projectivePoint(quad, 1, v),
      ] as const;
    }),
  ];
}

export function createPageGeometryMesh(
  corners: PageGeometryCorners,
): PageGeometryMesh {
  return Array.from({ length: PAGE_MESH_POINT_COUNT }, (_, index) => {
    const row = Math.floor(index / PAGE_MESH_COLUMNS);
    const column = index % PAGE_MESH_COLUMNS;
    return bilinear(
      corners,
      PAGE_BOARD_EDGE_RATIOS[column]!,
      PAGE_BOARD_EDGE_RATIOS[row]!,
    );
  });
}

export function applyPageGeometryMeshOverrides(
  mesh: PageGeometryMesh,
  overrides: ReadonlyMap<number, PageGeometryPoint>,
): PageGeometryMesh {
  return mesh.map((point, index) => overrides.get(index) ?? point);
}

export function pageGeometryQuadsFromMesh(
  mesh: PageGeometryMesh,
): readonly PageGeometryQuad[] {
  if (mesh.length !== PAGE_MESH_POINT_COUNT) return [];
  return Array.from(
    { length: PAGE_BOARD_COLUMNS * PAGE_BOARD_ROWS },
    (_, index) => {
      const row = Math.floor(index / PAGE_BOARD_COLUMNS);
      const column = index % PAGE_BOARD_COLUMNS;
      const topLeft = row * 2 * PAGE_MESH_COLUMNS + column * 2;
      const topRight = topLeft + 1;
      const bottomLeft = topLeft + PAGE_MESH_COLUMNS;
      const bottomRight = bottomLeft + 1;
      return [
        mesh[topLeft]!,
        mesh[topRight]!,
        mesh[bottomRight]!,
        mesh[bottomLeft]!,
      ] as const;
    },
  );
}

export function pageGeometryMeshFromQuads(
  quads: readonly PageGeometryQuad[],
): PageGeometryMesh | null {
  if (quads.length !== PAGE_BOARD_COUNT) return null;
  const mesh: Array<PageGeometryPoint | undefined> = Array.from({
    length: PAGE_MESH_POINT_COUNT,
  });
  quads.forEach((quad, index) => {
    const row = Math.floor(index / PAGE_BOARD_COLUMNS);
    const column = index % PAGE_BOARD_COLUMNS;
    const topLeft = row * 2 * PAGE_MESH_COLUMNS + column * 2;
    const topRight = topLeft + 1;
    const bottomLeft = topLeft + PAGE_MESH_COLUMNS;
    const bottomRight = bottomLeft + 1;
    mesh[topLeft] = quad[0];
    mesh[topRight] = quad[1];
    mesh[bottomRight] = quad[2];
    mesh[bottomLeft] = quad[3];
  });
  return mesh.every((point) => point !== undefined)
    ? (mesh as PageGeometryPoint[])
    : null;
}

export function pageGeometryMeshPointPosition(index: number): Readonly<{
  column: number;
  row: number;
}> | null {
  if (!Number.isInteger(index) || index < 0 || index >= PAGE_MESH_POINT_COUNT) {
    return null;
  }
  return {
    column: index % PAGE_MESH_COLUMNS,
    row: Math.floor(index / PAGE_MESH_COLUMNS),
  };
}

export function isPageGeometryMeshBoundaryPoint(index: number): boolean {
  const position = pageGeometryMeshPointPosition(index);
  return (
    position !== null &&
    (position.column === 0 ||
      position.column === PAGE_MESH_COLUMNS - 1 ||
      position.row === 0 ||
      position.row === PAGE_MESH_ROWS - 1)
  );
}

export function pageGeometryPointFromRenderedCanvas({
  clientX,
  clientY,
  imageHeight,
  imageWidth,
  renderedHeight,
  renderedLeft,
  renderedTop,
  renderedWidth,
}: Readonly<{
  clientX: number;
  clientY: number;
  imageHeight: number;
  imageWidth: number;
  renderedHeight: number;
  renderedLeft: number;
  renderedTop: number;
  renderedWidth: number;
}>): PageGeometryPoint | null {
  if (
    imageHeight < 1 ||
    imageWidth < 1 ||
    renderedHeight <= 0 ||
    renderedWidth <= 0
  ) {
    return null;
  }
  return {
    x: ((clientX - renderedLeft) * imageWidth) / renderedWidth,
    y: ((clientY - renderedTop) * imageHeight) / renderedHeight,
  };
}
