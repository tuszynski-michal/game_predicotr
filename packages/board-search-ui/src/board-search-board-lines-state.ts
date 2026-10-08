import type {
  BoardSearchBoardDetailResponse,
  BoardSearchCountMatchResponse,
  BoardSearchLineMatchResponse,
} from '@game-predictor/admin-api-client';

/**
 * Pure state for the board payline modal (D-470, TASK-0764). Lines come from
 * the API's payout evaluation, so a line starts only at the left edge and
 * stops at the first unknown cell; a game with a super game trigger symbol
 * (`payout-v4-wild-count`, D-535) also pays that symbol per count of its
 * cells on the board. This module only draws what paid.
 */

export interface BoardLinePoint {
  readonly x: number;
  readonly y: number;
}

/**
 * High-contrast palette readable on the dark board background. Past its end
 * the colours repeat with a dash pattern, so two lines never look the same.
 */
export const BOARD_LINE_COLORS: readonly string[] = Object.freeze([
  '#ffd23f',
  '#3ee6ff',
  '#ff5ca8',
  '#7cff6b',
  '#ff8c42',
  '#b98bff',
  '#ffffff',
  '#4d9dff',
]);

export interface BoardLineStyle {
  readonly color: string;
  readonly dashArray: string | undefined;
}

export function boardLineStyle(position: number): BoardLineStyle {
  const index = Math.max(0, position);
  const cycle = Math.floor(index / BOARD_LINE_COLORS.length);
  return {
    color: BOARD_LINE_COLORS[index % BOARD_LINE_COLORS.length] ?? '#ffffff',
    dashArray: cycle === 0 ? undefined : cycle === 1 ? '8 5' : '2 4',
  };
}

/** Stable identity of one winning line (at most one symbol pays per line). */
export function boardLineKey(match: BoardSearchLineMatchResponse): string {
  return `${match.paylineId}:${match.symbolCode}`;
}

/**
 * A payline's colour comes from its published `displayOrder` alone, so the
 * same line has the same colour on every board, whatever else won there.
 */
export function boardLineStyles(
  matches: readonly BoardSearchLineMatchResponse[],
): ReadonlyMap<string, BoardLineStyle> {
  return new Map(
    matches.map((match) => [
      boardLineKey(match),
      boardLineStyle(match.paylineDisplayOrder),
    ]),
  );
}

/** Arithmetic mean of the polygon's corners (cells are convex quads). */
export function boardLinesPolygonCentroid(
  points: readonly BoardLinePoint[],
): BoardLinePoint {
  if (points.length === 0) return { x: 0, y: 0 };
  let x = 0;
  let y = 0;
  for (const point of points) {
    x += point.x;
    y += point.y;
  }
  return { x: x / points.length, y: y / points.length };
}

export type BoardLineVisibility = ReadonlySet<string>;

/** Every line starts visible each time the modal opens for a board. */
export function initialBoardLineVisibility(
  matches: readonly BoardSearchLineMatchResponse[],
): BoardLineVisibility {
  return new Set(matches.map(boardLineKey));
}

export function toggleBoardLineVisibility(
  visibility: BoardLineVisibility,
  key: string,
): BoardLineVisibility {
  const next = new Set(visibility);
  if (next.has(key)) next.delete(key);
  else next.add(key);
  return next;
}

export function setAllBoardLinesVisibility(
  matches: readonly BoardSearchLineMatchResponse[],
  visible: boolean,
): BoardLineVisibility {
  return visible ? initialBoardLineVisibility(matches) : new Set();
}

export type BoardLinesConsistency =
  | { readonly kind: 'consistent' }
  | {
      readonly kind: 'inconsistent';
      readonly reason: 'payout' | 'rules' | 'lines';
    };

/**
 * The modal draws lines only when they explain exactly the table row it was
 * opened from: same rules version, same payout, and lines summing to it.
 * Anything else means data changed between the two requests.
 */
export function boardLinesConsistency(
  detail: Pick<
    BoardSearchBoardDetailResponse,
    'matches' | 'payoutCredits' | 'rules'
  > & {
    readonly countMatches?: readonly Pick<
      BoardSearchCountMatchResponse,
      'payoutCredits'
    >[];
  },
  rowPayoutCredits: number,
  rulesVersionId: string,
): BoardLinesConsistency {
  if (detail.rules.rulesVersionId !== rulesVersionId) {
    return { kind: 'inconsistent', reason: 'rules' };
  }
  if (detail.payoutCredits !== rowPayoutCredits) {
    return { kind: 'inconsistent', reason: 'payout' };
  }
  // Lines and count payouts together must explain the board payout.
  const sum =
    detail.matches.reduce((total, match) => total + match.payoutCredits, 0) +
    boardCountMatches(detail).reduce(
      (total, match) => total + match.payoutCredits,
      0,
    );
  if (sum !== detail.payoutCredits) {
    return { kind: 'inconsistent', reason: 'lines' };
  }
  return { kind: 'consistent' };
}

/**
 * Count payouts of a board detail; empty for games without a super game
 * trigger symbol (and for readers of an older response without the field).
 */
export function boardCountMatches<T>(detail: {
  readonly countMatches?: readonly T[];
}): readonly T[] {
  return detail.countMatches ?? [];
}

/** Cells counted for any trigger symbol, for highlighting on the board. */
export function boardCountedCells(
  countMatches: readonly Pick<BoardSearchCountMatchResponse, 'cells'>[],
): ReadonlySet<number> {
  return new Set(countMatches.flatMap((match) => match.cells));
}

/**
 * Small per-line offset (in cell-height fractions) so lines sharing cells
 * stay distinguishable; centred around zero.
 */
export function boardLineOffset(position: number, count: number): number {
  if (count <= 1) return 0;
  const spread = Math.min(0.24, 0.06 * (count - 1));
  return -spread / 2 + (spread * position) / (count - 1);
}

/** Row-major cell rectangles of the fallback 3 × 5 schema, in schema units. */
export const BOARD_SCHEMA_CELL = 100;

export function boardSchemaCellPolygon(
  cellIndex: number,
): readonly BoardLinePoint[] {
  const x = (cellIndex % 5) * BOARD_SCHEMA_CELL;
  const y = Math.floor(cellIndex / 5) * BOARD_SCHEMA_CELL;
  return [
    { x, y },
    { x: x + BOARD_SCHEMA_CELL, y },
    { x: x + BOARD_SCHEMA_CELL, y: y + BOARD_SCHEMA_CELL },
    { x, y: y + BOARD_SCHEMA_CELL },
  ];
}
