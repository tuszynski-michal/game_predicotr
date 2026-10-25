/** Pure presentation of share-link query log entries (D-472). */

type Entry = {
  readonly kind: string;
  readonly request: Readonly<Record<string, unknown>>;
  readonly resultSummary: Readonly<Record<string, unknown>>;
  readonly outcomeCode: string;
};

const CELL = /^(\d{1,2}):(.+)$/;

/** 15 cells: a symbol code, `?` or `null` (not part of the pattern). */
export function boardSearchQueryPatternCells(
  entry: Entry,
): readonly (string | null)[] | null {
  if (entry.kind !== 'search') return null;
  const cells = entry.request.cells;
  if (!Array.isArray(cells)) return null;
  const board: (string | null)[] = Array<string | null>(15).fill(null);
  for (const value of cells) {
    if (typeof value !== 'string') continue;
    const match = CELL.exec(value);
    if (match === null) continue;
    const index = Number(match[1]);
    if (Number.isInteger(index) && index >= 0 && index < 15) {
      board[index] = match[2] ?? null;
    }
  }
  return board;
}

/** v2 never falls back to the legacy cells field. */
export function boardSearchQueryPatterns(
  entry: Entry,
): readonly (readonly (string | null)[])[] {
  if (entry.kind !== 'search') return [];
  if (entry.request.version === 2) {
    if (!Array.isArray(entry.request.patterns)) return [];
    return entry.request.patterns.flatMap((pattern: unknown) => {
      if (
        pattern === null ||
        typeof pattern !== 'object' ||
        !('cells' in pattern)
      )
        return [];
      const cells = boardSearchQueryPatternCells({
        ...entry,
        request: { cells: pattern.cells },
      });
      return cells === null ? [] : [cells];
    });
  }
  const cells = boardSearchQueryPatternCells(entry);
  return cells === null ? [] : [cells];
}

/**
 * When the entry's query was made, newest first. A grouped search carries
 * the time of every search of its pattern (TASK-0816).
 */
export function boardSearchQueryOccurrenceTimes(entry: {
  readonly occurredAt: string;
  readonly occurrenceTimes?: readonly string[] | null;
}): readonly string[] {
  const times = entry.occurrenceTimes;
  return Array.isArray(times) && times.length > 0 ? times : [entry.occurredAt];
}

export interface BoardSearchQueryRange {
  readonly spinCount: number;
  readonly startSequenceNumber: number;
  /**
   * The stake the recipient viewed the range at (D-487): grosze, `null` for
   * the base stake, `undefined` when it was not recorded (older entries).
   */
  readonly stakeGrosze: number | null | undefined;
}

/** The range the recipient opened after a search, when one was recorded. */
export function boardSearchQueryFollowUpRange(entry: {
  readonly followUpApproximateWin?: Readonly<Record<string, unknown>> | null;
}): BoardSearchQueryRange | null {
  const request = entry.followUpApproximateWin;
  if (request === null || request === undefined) return null;
  const { spinCount, stakeGrosze, startSequenceNumber } = request;
  const stake =
    typeof stakeGrosze === 'number' &&
    Number.isInteger(stakeGrosze) &&
    stakeGrosze > 0
      ? stakeGrosze
      : stakeGrosze === null
        ? null
        : undefined;
  return typeof spinCount === 'number' &&
    Number.isInteger(spinCount) &&
    spinCount > 0 &&
    typeof startSequenceNumber === 'number' &&
    Number.isInteger(startSequenceNumber)
    ? { spinCount, stakeGrosze: stake, startSequenceNumber }
    : null;
}

function numberValue(value: unknown): string {
  return typeof value === 'number' && Number.isFinite(value)
    ? value.toLocaleString('pl-PL')
    : '?';
}

export function describeBoardSearchQueryEntry(entry: Entry): {
  readonly title: string;
  readonly details: string;
} {
  const ok = entry.outcomeCode === 'ok';
  const request = entry.request;
  const summary = entry.resultSummary;
  if (entry.kind === 'search') {
    const scope =
      request.scope === 'approved_only'
        ? 'tylko zatwierdzone'
        : 'wszystkie plansze';
    const sequence = request.version === 2;
    const numbers = sequence
      ? summary.firstEndSequenceNumbers
      : summary.firstSequenceNumbers;
    const found = Array.isArray(numbers)
      ? (numbers as unknown[])
          .filter((item): item is number => typeof item === 'number')
          .map((item) => `#${item}`)
          .join(', ')
      : '';
    return {
      details: ok
        ? `${sequence ? `Ciąg: ${numberValue(summary.patternCount)} układów · ` : ''}Zakres: ${scope} · limit ${numberValue(request.limit)} · wyniki: ${numberValue(summary.resultCount)}${found ? ` (${sequence ? 'końce ciągów: ' : ''}${found}${Number(summary.resultCount) > 5 ? ', …' : ''})` : ''}`
        : `Zakres: ${scope} · limit ${numberValue(request.limit)}`,
      title: 'Wyszukiwanie',
    };
  }
  if (entry.kind === 'approximate_win') {
    return {
      details: ok
        ? `Plansza startowa #${numberValue(request.startSequenceNumber)} · ${numberValue(request.spinCount)} spinów · wypłaty ${numberValue(summary.recognizedPayoutCredits)} · koszt ${numberValue(summary.spinCostCredits)} · bilans ${numberValue(summary.balanceCredits)} kredytów`
        : `Plansza startowa #${numberValue(request.startSequenceNumber)} · ${numberValue(request.spinCount)} spinów`,
      title: 'Przybliżona wygrana',
    };
  }
  if (entry.kind === 'board_detail') {
    return {
      details: ok
        ? `Plansza #${numberValue(request.sequenceNumber)} · wypłata ${numberValue(summary.payoutCredits)} kredytów${summary.documentStale === true ? ' · nieaktualny odczyt' : ''}`
        : `Plansza #${numberValue(request.sequenceNumber)}`,
      title: 'Plansza z liniami',
    };
  }
  return { details: '', title: entry.kind };
}
