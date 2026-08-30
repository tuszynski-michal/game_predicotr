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
// Every board owns two independent edge lines.  Adjacent boards are separated
// by a real screen gutter, so a shared 4x4 cell lattice would systematically
// crop labels/gaps instead of following the nine red frames.
export const PAGE_MESH_COLUMNS = PAGE_BOARD_COLUMNS * 2;
export const PAGE_MESH_ROWS = PAGE_BOARD_ROWS * 2;
export const PAGE_MESH_POINT_COUNT = PAGE_MESH_COLUMNS * PAGE_MESH_ROWS;

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
