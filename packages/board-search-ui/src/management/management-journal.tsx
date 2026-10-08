'use client';

import type {
  ManagementJournalEntry,
  ManagementStake,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {
  type ManagementGameClient,
  managementError,
} from './management-client';
import { managementAmount, managementDate } from './management-cards';
import { MANAGEMENT_STAKES } from './management-slot-state';

/** Display only; the stored actor remains bound to its immutable session UUID. */
export function managementActorLabel(actor: string): string {
  if (actor === 'local-owner') return 'Administrator lokalny';
  const match = /^management-share:[0-9a-f-]{36}:(.*)$/i.exec(actor);
  return match ? match[1] || 'Udostępniony panel' : actor;
}

const ACTIONS: Record<string, string> = {
  search: 'Wyszukiwanie',
  'stake.save': 'Zapis układu',
  'stake.replace': 'Zastąpienie układu',
  'stake.clear': 'Wyczyszczenie stawki',
  'stake.recalculate': 'Zmiana wyniku',
  'symbol.correct': 'Korekta symbolu',
  'point.write': 'Zmiana punktu',
  'machine.write': 'Zmiana maszyny',
  'assignments.write': 'Zmiana przypisanych gier',
};
function describeState(state: ManagementJournalEntry['after']): string {
  const parts: string[] = [];
  if (state.empty === true) parts.push('Pusta stawka');
  const sequence = state.sequenceNumber ?? state.startSequenceNumber;
  if (typeof sequence === 'number') parts.push(`Plansza #${sequence}`);
  if (typeof state.spinCount === 'number')
    parts.push(`Zakres: ${state.spinCount} spinów`);
  if (typeof state.cellIndex === 'number')
    parts.push(`Pole ${state.cellIndex + 1}`);
  if ('symbolCode' in state)
    parts.push(`Symbol: ${state.symbolCode ?? 'nieznany'}`);
  if (typeof state.name === 'string') parts.push(state.name);
  if (typeof state.city === 'string') parts.push(`Miasto: ${state.city}`);
  if (typeof state.street === 'string') parts.push(`Ulica: ${state.street}`);
  if (typeof state.archived === 'boolean')
    parts.push(state.archived ? 'Zarchiwizowany' : 'Aktywny');
  if ('qualityIssue' in state) {
    const qualityLabels: Record<string, string> = {
      grid_issue: 'Błąd siatki',
      unreadable: 'Nieczytelny symbol',
      blurry: 'Rozmyty symbol',
      partial_visibility: 'Częściowo widoczny symbol',
    };
    parts.push(
      state.qualityIssue === null
        ? 'Brak problemów jakości'
        : typeof state.qualityIssue === 'string'
          ? (qualityLabels[state.qualityIssue] ?? 'Problem jakości')
          : 'Problem jakości',
    );
  }
  if ('reviewState' in state)
    parts.push(
      state.reviewState === 'approved'
        ? 'Symbol zatwierdzony'
        : 'Symbol do weryfikacji',
    );
  if (state.status === 'active') parts.push('Aktywny');
  if (state.status === 'archived') parts.push('Zarchiwizowany');
  if (typeof state.resultCount === 'number')
    parts.push(`Wyniki: ${state.resultCount}`);
  if (Array.isArray(state.sequenceNumbers))
    parts.push(
      `Plansze: ${
        state.sequenceNumbers
          .filter((value) => typeof value === 'number')
          .map((value) => `#${value}`)
          .join(', ') || 'brak'
      }`,
    );
  if (Array.isArray(state.pinnedSpinPositions))
    parts.push(
      `Przypięte spiny: ${state.pinnedSpinPositions.filter((value) => typeof value === 'number').join(', ') || 'brak'}`,
    );
  if (
    Array.isArray(state.unavailablePinPositions) &&
    state.unavailablePinPositions.length
  )
    parts.push(
      `Niedostępne spiny: ${state.unavailablePinPositions.filter((value) => typeof value === 'number').join(', ')}`,
    );
  if (Array.isArray(state.startSymbolCodes))
    parts.push(
      `Symbole planszy: ${state.startSymbolCodes.map((value) => (typeof value === 'string' ? value : '?')).join(', ')}`,
    );
  const amount = (credits: number) =>
    typeof state.stakeGrosze === 'number' && typeof state.spinCost === 'number'
      ? managementAmount(credits, state.stakeGrosze, state.spinCost)
      : `${credits.toLocaleString('pl-PL')} kredytów`;
  const summary = state.summary;
  if (
    typeof summary === 'object' &&
    summary !== null &&
    !Array.isArray(summary)
  ) {
    const values = summary as Record<string, unknown>;
    for (const [key, label] of [
      ['recognizedPayoutCredits', 'Wypłaty'],
      ['spinCostCredits', 'Koszt spinów'],
      ['balanceCredits', 'Bilans'],
    ]) {
      if (typeof values[key] === 'number')
        parts.push(`${label}: ${amount(values[key])}`);
    }
  }
  if (Array.isArray(state.pinnedPoints)) {
    for (const value of state.pinnedPoints) {
      if (
        typeof value !== 'object' ||
        value === null ||
        !('spinNumber' in value) ||
        typeof value.spinNumber !== 'number' ||
        !('balanceCredits' in value) ||
        typeof value.balanceCredits !== 'number'
      )
        continue;
      parts.push(
        `Spin ${value.spinNumber}: bilans ${amount(value.balanceCredits)}`,
      );
    }
  }
  if (typeof state.savedAt === 'string')
    parts.push(`Zapis: ${managementDate(state.savedAt)}`);
  if (state.staleErrorCode) parts.push('Wynik wymaga ponownego sprawdzenia');
  if (Array.isArray(state.assignments)) {
    const assignments = state.assignments.flatMap((assignment) => {
      if (
        typeof assignment !== 'object' ||
        assignment === null ||
        !('gameName' in assignment) ||
        typeof assignment.gameName !== 'string' ||
        !('attached' in assignment) ||
        typeof assignment.attached !== 'boolean'
      )
        return [];
      return [
        `${assignment.gameName}: ${assignment.attached ? 'przypisana' : 'odłączona'}`,
      ];
    });
    parts.push(`Gry: ${assignments.join(', ') || 'brak'}`);
  }
  const query = state.query;
  if (typeof query === 'object' && query !== null && !Array.isArray(query)) {
    const value = query as Record<string, unknown>;
    if (Array.isArray(value.cells)) {
      const cells = value.cells.flatMap((cell) => {
        if (
          typeof cell !== 'object' ||
          cell === null ||
          !('cellIndex' in cell) ||
          typeof cell.cellIndex !== 'number' ||
          !('symbolCode' in cell)
        )
          return [];
        return [`pole ${cell.cellIndex + 1}: ${cell.symbolCode ?? 'nieznany'}`];
      });
      parts.push(`Wzór: ${cells.join(', ') || 'dowolna plansza'}`);
    }
    if (typeof value.limit === 'number')
      parts.push(`Limit wyników: ${value.limit}`);
    if (value.scope === 'approved_only')
      parts.push('Tylko zaakceptowane plansze');
    if (value.scope === 'all_searchable')
      parts.push('Wszystkie dostępne plansze');
  }
  return parts.join(' · ') || 'Brak zapisanego układu';
}

export function ManagementJournal({
  api,
  machineId,
  gameId,
  revision,
  accessAllowed = true,
  onHistory,
}: {
  api: ManagementGameClient;
  machineId: string;
  gameId: string;
  revision: number;
  accessAllowed?: boolean;
  onHistory: (
    versionId: string,
    stake: ManagementStake,
    pins: readonly number[],
  ) => void;
}) {
  const accessRef = useRef(accessAllowed);
  useLayoutEffect(() => {
    accessRef.current = accessAllowed;
  }, [accessAllowed]);
  const [entries, setEntries] = useState<ManagementJournalEntry[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const load = useCallback(
    async (before?: string) => {
      if (!accessRef.current) return;
      const id = ++generation.current;
      controller.current?.abort();
      const next = new AbortController();
      controller.current = next;
      setLoading(true);
      setError('');
      try {
        const response = await api.listManagementJournal(machineId, {
          gameId,
          before,
          limit: 20,
          signal: next.signal,
        });
        if (
          !accessRef.current ||
          next.signal.aborted ||
          id !== generation.current
        )
          return;
        if (!response.data || response.error !== undefined)
          throw new Error(
            managementError(response.error, 'Nie udało się wczytać dziennika.'),
          );
        const data = response.data;
        setEntries((current) =>
          before
            ? [
                ...current,
                ...data.entries.filter(
                  (entry) => !current.some((old) => old.id === entry.id),
                ),
              ]
            : data.entries,
        );
        setCursor(data.nextCursor);
      } catch (cause) {
        if (!next.signal.aborted && id === generation.current)
          setError(managementError(cause, 'Nie udało się wczytać dziennika.'));
      } finally {
        if (!next.signal.aborted && id === generation.current)
          setLoading(false);
      }
    },
    [api, machineId, gameId],
  );
  const cancel = useCallback(() => {
    ++generation.current;
    controller.current?.abort();
  }, []);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (active && accessAllowed) void load();
    });
    return () => {
      active = false;
      cancel();
    };
  }, [load, cancel, revision, accessAllowed]);
  const history = (
    entry: ManagementJournalEntry,
    id: string,
    side: 'before' | 'after',
  ) => {
    if (!accessRef.current) return;
    if (!MANAGEMENT_STAKES.includes(entry.stakeGrosze as ManagementStake))
      return;
    const value = entry[side].pinnedSpinPositions;
    const pins = Array.isArray(value)
      ? value.filter(
          (pin): pin is number =>
            typeof pin === 'number' && Number.isInteger(pin),
        )
      : [];
    onHistory(id, entry.stakeGrosze as ManagementStake, pins);
  };
  return (
    <section className="management-journal" aria-label="Dziennik maszyny">
      <h3>Dziennik</h3>
      {loading ? <p role="status">Wczytywanie dziennika…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && !entries.length ? (
        <p>Brak wpisów w dzienniku.</p>
      ) : null}
      <ol>
        {entries.map((entry) => (
          <li key={entry.id}>
            <p>
              <strong>{ACTIONS[entry.action] ?? 'Zmiana'}</strong> ·{' '}
              {managementDate(entry.createdAt)} ·{' '}
              {managementActorLabel(entry.actor)}
            </p>
            {entry.stakeGrosze !== null ? (
              <p>
                Stawka: {(entry.stakeGrosze / 100).toLocaleString('pl-PL')} zł
              </p>
            ) : null}
            <details>
              <summary>Zmiany przed / po</summary>
              <p>Przed: {describeState(entry.before)}</p>
              <p>Po: {describeState(entry.after)}</p>
            </details>
            <div className="management-actions">
              {entry.beforeResultId ? (
                <button
                  disabled={!accessAllowed}
                  onClick={() =>
                    history(entry, entry.beforeResultId!, 'before')
                  }
                >
                  Wynik przed zmianą
                </button>
              ) : null}
              {entry.afterResultId ? (
                <button
                  disabled={!accessAllowed}
                  onClick={() => history(entry, entry.afterResultId!, 'after')}
                >
                  Zapisany wynik po zmianie
                </button>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      {cursor ? (
        <button
          disabled={loading || !accessAllowed}
          onClick={() => void load(cursor)}
        >
          Starsze wpisy
        </button>
      ) : error ? (
        <button
          disabled={loading || !accessAllowed}
          onClick={() => void load()}
        >
          Ponów dziennik
        </button>
      ) : null}
    </section>
  );
}
