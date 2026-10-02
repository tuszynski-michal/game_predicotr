import type {
  AdminApiClient,
  OperationalImageReviewItemResponse,
  SymbolCellReviewListItemResponse,
} from '@game-predictor/admin-api-client';
import {
  manualGridCellPolygons,
  type ManualGridPoint,
} from '@game-predictor/manual-image-selection-core/manual-grid-qualification';

export type SymbolReviewSourceClient = Pick<
  AdminApiClient,
  'getOperationalImageReviewItem' | 'getOperationalImageReviewSourceAsset'
>;

/** Read the saved lattice; never substitute a draft or an invented grid. */
export function symbolReviewSourceCells(
  geometry: OperationalImageReviewItemResponse['geometry'],
) {
  const footprints = new Map<number, readonly ManualGridPoint[]>();
  if (Array.isArray(geometry.cells)) {
    for (const cell of geometry.cells) {
      if (
        typeof cell !== 'object' ||
        cell === null ||
        !Number.isInteger(cell.rowIndex) ||
        !Number.isInteger(cell.columnIndex) ||
        cell.rowIndex < 0 ||
        cell.rowIndex >= 3 ||
        cell.columnIndex < 0 ||
        cell.columnIndex >= 5
      )
        return [];
      const index = cell.rowIndex * 5 + cell.columnIndex;
      const quad = parseQuad(cell.sourceQuad);
      if (quad === null || footprints.has(index)) return [];
      footprints.set(index, quad);
    }
  }
  const raw =
    geometry.latticeBoundsQuad ??
    geometry.symbolGridQuad ??
    geometry.sourceQuad ??
    geometry.quad ??
    geometry.corners;
  const quad = parseQuad(raw);
  const derived = quad === null ? [] : manualGridCellPolygons(quad);
  const cells = Array.from(
    { length: 15 },
    (_, index) => footprints.get(index) ?? derived[index],
  );
  return cells.every(
    (cell): cell is readonly ManualGridPoint[] =>
      cell !== undefined &&
      cell.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)),
  )
    ? cells
    : [];
}

function parseQuad(raw: unknown): readonly ManualGridPoint[] | null {
  if (!Array.isArray(raw) || raw.length !== 4) return null;
  const points: ManualGridPoint[] = [];
  for (const value of raw) {
    const point = Array.isArray(value) ? { x: value[0], y: value[1] } : value;
    if (
      typeof point !== 'object' ||
      point === null ||
      typeof point.x !== 'number' ||
      !Number.isFinite(point.x) ||
      typeof point.y !== 'number' ||
      !Number.isFinite(point.y)
    )
      return null;
    points.push({ x: point.x, y: point.y });
  }
  return points;
}

export async function loadSymbolReviewSourceContext(
  api: SymbolReviewSourceClient,
  gameId: string,
  item: SymbolCellReviewListItemResponse,
): Promise<
  | {
      readonly ok: true;
      readonly blob: Blob;
      readonly cells: readonly (readonly ManualGridPoint[])[];
    }
  | { readonly ok: false; readonly error: string }
> {
  const context = { gameId, importJobId: item.importJobId };
  try {
    const detail = await api.getOperationalImageReviewItem(
      item.reviewItemId,
      context,
    );
    if (detail.error !== undefined || detail.data === undefined) {
      return { ok: false, error: 'Nie udało się pobrać kontekstu źródła.' };
    }
    const data = detail.data;
    if (
      data.id !== item.reviewItemId ||
      data.recognizedBoardId !== item.recognizedBoardId ||
      data.gameId !== gameId ||
      data.importJobId !== item.importJobId ||
      data.geometryRevision !== item.geometryRevision
    ) {
      return {
        ok: false,
        error: 'Geometria pola zmieniła się. Odśwież listę przed podglądem.',
      };
    }
    const cells = symbolReviewSourceCells(data.geometry);
    if (cells.length !== 15)
      return { ok: false, error: 'Brak zapisanej siatki do podglądu źródła.' };
    const asset = await api.getOperationalImageReviewSourceAsset(
      item.reviewItemId,
      context,
    );
    if (asset.error !== undefined || !(asset.data instanceof Blob)) {
      return { ok: false, error: 'Zdjęcie źródłowe jest niedostępne.' };
    }
    const digest = await crypto.subtle.digest(
      'SHA-256',
      await asset.data.arrayBuffer(),
    );
    const checksum = Array.from(new Uint8Array(digest), (byte) =>
      byte.toString(16).padStart(2, '0'),
    ).join('');
    if (checksum !== data.sourceChecksumSha256)
      return {
        ok: false,
        error: 'Zdjęcie źródłowe zmieniło się. Odśwież listę.',
      };
    return { ok: true, blob: asset.data, cells };
  } catch {
    return { ok: false, error: 'Nie udało się odczytać zdjęcia źródłowego.' };
  }
}
