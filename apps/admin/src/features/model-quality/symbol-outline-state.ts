/**
 * D-608: pure helpers of the symbol outline review window. Proposals come from the
 * operator's approved grids; approving writes the ordinary content label unchanged.
 */
import type {
  ContentOutlineProposal,
  ContentWriteCommand,
} from '@game-predictor/admin-api-client';

export type OutlineView = 'todo' | 'approved' | 'all';
export const OUTLINE_PAGE_SIZE = 48;

/** Board crop around all outlines, with a relative margin, clamped to the photo. */
export function outlineViewBox(
  item: Pick<ContentOutlineProposal, 'cells' | 'source'>,
  margin: number,
): [number, number, number, number] {
  const { width, height } = item.source;
  const points = (item.cells ?? []).flatMap((cell) => cell.quad ?? []);
  if (!points.length) return [0, 0, width, height];
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
  const mx = (maxX - minX) * margin;
  const my = (maxY - minY) * margin;
  const x0 = Math.max(0, minX - mx);
  const y0 = Math.max(0, minY - my);
  const x1 = Math.min(width, maxX + mx);
  const y1 = Math.min(height, maxY + my);
  return [x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
}

/** A board can be approved only when it has a usable grid and no approved label yet. */
export function outlineSelectable(item: ContentOutlineProposal): boolean {
  return item.cells != null && !item.contentApproved;
}

/** The same command the ordinary editor sends with „Zapisz i zatwierdź”. */
export function outlineApprovalCommand(
  item: ContentOutlineProposal,
  idempotencyKey: string,
): ContentWriteCommand {
  if (!outlineSelectable(item) || !item.cells)
    throw new Error('Ta plansza nie ma propozycji do zatwierdzenia.');
  return {
    idempotencyKey,
    sourceId: item.source.sourceId,
    expectedSourceSha256: item.source.sourceSha256,
    expectedPixelSha256: item.source.sourceRepresentativeSha256,
    positionIndex: item.positionIndex,
    sequenceNumber: item.sequenceNumber,
    expectedRevision: item.contentRevision,
    cells: item.cells,
    origin: 'manual',
    humanApproval: true,
  };
}

/** Selection keeps whole proposals, so boards chosen on other pages can be approved too. */
export type OutlineSelection = ReadonlyMap<string, ContentOutlineProposal>;

export function toggleSelection(
  selected: OutlineSelection,
  item: ContentOutlineProposal,
): Map<string, ContentOutlineProposal> {
  const next = new Map(selected);
  if (next.has(item.boardId)) next.delete(item.boardId);
  else if (outlineSelectable(item)) next.set(item.boardId, item);
  return next;
}

/** Selects every selectable board of the page; keeps choices from other pages. */
export function selectPage(
  selected: OutlineSelection,
  items: readonly ContentOutlineProposal[],
): Map<string, ContentOutlineProposal> {
  const next = new Map(selected);
  for (const item of items)
    if (outlineSelectable(item)) next.set(item.boardId, item);
  return next;
}

export function symbolOutlinesWindowUrl(currentHref: string, gameId: string) {
  const url = new URL('/symbol-outlines', currentHref);
  url.searchParams.set('gameId', gameId);
  return url.toString();
}
