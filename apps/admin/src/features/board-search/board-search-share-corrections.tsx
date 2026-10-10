'use client';

import type {
  AdminApiClient,
  BoardSearchShareCorrectionPageResponse,
  BoardSearchShareCorrectionDetailResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  BoardSearchBoardLinesModal,
  type BoardLinesClient,
  formatZloty,
} from '@game-predictor/board-search-ui';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  boardSearchShareErrorMessage,
  formatBoardSearchShareDate,
} from './board-search-share-state';

export type BoardSearchShareCorrectionClient = Partial<
  Pick<
    AdminApiClient,
    | 'listBoardSearchShareCorrections'
    | 'getBoardSearchShareCorrection'
    | 'reviewBoardSearchShareCorrection'
  >
> &
  BoardLinesClient;

/** Indexed metadata only; board pixels and payouts load on an explicit click. */
export function BoardSearchShareCorrections({
  client,
  gameId,
  sessionId,
  symbols,
  pattern,
}: {
  readonly client: BoardSearchShareCorrectionClient;
  readonly gameId: string;
  readonly sessionId: string;
  readonly symbols: readonly SymbolResponse[];
  readonly pattern?: readonly string[];
}) {
  const [status, setStatus] = useState<'pending' | 'reviewed' | 'all'>(
    pattern === undefined ? 'pending' : 'all',
  );
  const [page, setPage] =
    useState<BoardSearchShareCorrectionPageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [detail, setDetail] =
    useState<BoardSearchShareCorrectionDetailResponse | null>(null);
  const [reviewBusy, setReviewBusy] = useState(false);
  const [modalVersion, setModalVersion] = useState(0);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const requestId = useRef(0);
  const detailRequestId = useRef(0);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const patternKey = JSON.stringify(pattern ?? null);
  const symbolName = (code: string | null, issue: string | null) =>
    issue === 'grid_issue'
      ? 'Zła siatka'
      : issue === 'unreadable'
        ? 'Nieczytelne'
        : issue === 'partial_visibility'
          ? 'Częściowo niewidoczne'
          : (symbols.find((symbol) => symbol.code === code)?.name ??
            code ??
            '?');

  const load = useCallback(
    async (before?: string) => {
      const id = ++requestId.current;
      setLoading(true);
      setError(null);
      try {
        const parsedPattern = JSON.parse(patternKey) as string[] | null;
        if (client.listBoardSearchShareCorrections === undefined)
          throw new Error('Lista poprawek nie jest dostępna.');
        const result = await client.listBoardSearchShareCorrections(sessionId, {
          status,
          limit: 25,
          ...(before === undefined ? {} : { before }),
          ...(parsedPattern === null ? {} : { pattern: parsedPattern }),
        });
        if (id !== requestId.current) return;
        if (result.data === undefined)
          throw new Error(
            boardSearchShareErrorMessage(
              result.error,
              'Nie udało się pobrać poprawek.',
            ),
          );
        const incoming = result.data;
        setPage((previous) =>
          before === undefined || previous === null
            ? incoming
            : {
                ...incoming,
                entries: [...previous.entries, ...incoming.entries],
              },
        );
      } catch (cause) {
        if (id === requestId.current)
          setError(
            cause instanceof Error
              ? cause.message
              : 'Nie udało się pobrać poprawek.',
          );
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [client, sessionId, status, patternKey],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setPage(null);
      void load();
    }, 0);
    return () => {
      window.clearTimeout(timer);
      ++requestId.current;
    };
  }, [load]);

  async function readDetail(
    sequenceNumber: number,
    preserveRevision = false,
    before?: string,
  ) {
    const id = ++detailRequestId.current;
    setReviewBusy(true);
    setReviewError(null);
    try {
      if (client.getBoardSearchShareCorrection === undefined)
        throw new Error('Historia poprawek nie jest dostępna.');
      const result = await client.getBoardSearchShareCorrection(
        sessionId,
        sequenceNumber,
        before === undefined ? {} : { before },
      );
      if (id !== detailRequestId.current) return;
      if (result.data === undefined)
        throw new Error(
          boardSearchShareErrorMessage(
            result.error,
            'Nie udało się pobrać historii poprawek.',
          ),
        );
      const incoming = result.data;
      if (
        preserveRevision &&
        detail !== null &&
        incoming.board.revision !== detail.board.revision
      ) {
        setReviewError(
          'Użytkownik dodał nową poprawkę. Odśwież zmiany i przejrzyj planszę ponownie.',
        );
        return;
      }
      if (
        before !== undefined &&
        detail !== null &&
        incoming.board.revision !== detail.board.revision
      ) {
        setReviewError(
          'Historia zmieniła się. Odśwież zmiany przed dalszym przeglądem.',
        );
        return;
      }
      setDetail((previous) =>
        before === undefined || previous === null
          ? incoming
          : {
              ...incoming,
              changes: [...previous.changes, ...incoming.changes],
            },
      );
      if (!preserveRevision && before === undefined)
        setModalVersion((value) => value + 1);
    } catch (cause) {
      if (id === detailRequestId.current)
        setReviewError(
          cause instanceof Error
            ? cause.message
            : 'Nie udało się pobrać historii.',
        );
    } finally {
      if (id === detailRequestId.current) setReviewBusy(false);
    }
  }

  async function acknowledge() {
    if (
      selected === null ||
      detail === null ||
      reviewBusy ||
      detail.nextCursor !== null
    )
      return;
    setReviewBusy(true);
    setReviewError(null);
    try {
      if (client.reviewBoardSearchShareCorrection === undefined)
        throw new Error('Zapis przeglądu nie jest dostępny.');
      const result = await client.reviewBoardSearchShareCorrection(
        sessionId,
        selected,
        {
          expectedRevision: detail.board.revision,
          expectedBoardVersion: detail.boardVersion,
        },
      );
      if (result.data === undefined)
        throw new Error(
          boardSearchShareErrorMessage(
            result.error,
            'Plansza zmieniła się. Odśwież zmiany i sprawdź ją ponownie.',
          ),
        );
      setSelected(null);
      setDetail(null);
      void load();
      trigger.current?.focus();
    } catch (cause) {
      setReviewError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się zapisać przeglądu.',
      );
    } finally {
      setReviewBusy(false);
    }
  }

  return (
    <section
      className="boardSearchShareCorrections"
      aria-label={
        pattern === undefined ? 'Poprawione plansze' : 'Poprawki wyszukiwania'
      }
    >
      <h4>
        {pattern === undefined
          ? 'Poprawione plansze'
          : 'Poprawki tego wyszukiwania'}
      </h4>
      {page !== null ? (
        <p>
          Poprawiono {page.totalCount} plansz · {page.pendingCount} do
          przeglądu.
        </p>
      ) : null}
      {pattern === undefined ? (
        <label>
          Stan przeglądu{' '}
          <select
            value={status}
            onChange={(event) => setStatus(event.target.value as typeof status)}
          >
            <option value="pending">Do przeglądu</option>
            <option value="all">Wszystkie</option>
            <option value="reviewed">Przejrzane</option>
          </select>
        </label>
      ) : null}
      <button
        type="button"
        className="secondaryButton"
        disabled={loading}
        onClick={() => void load()}
      >
        Odśwież poprawki
      </button>
      {loading ? <p role="status">Wczytywanie poprawek…</p> : null}
      {error !== null ? <p role="alert">{error}</p> : null}
      {page !== null && page.entries.length === 0 ? (
        <p>Brak plansz w tym stanie.</p>
      ) : null}
      {page !== null ? (
        <ul>
          {page.entries.map((board) => (
            <li key={board.sequenceNumber}>
              <strong>Plansza #{board.sequenceNumber}</strong> ·{' '}
              {board.changedCellCount} zmienionych pól ·{' '}
              {board.pending ? 'Do przeglądu' : 'Przejrzana'}
              {' · '}
              {formatBoardSearchShareDate(board.lastChangedAt)} ·{' '}
              {board.stakeGrosze === null
                ? 'stawka nieznana'
                : `stawka ${formatZloty(board.stakeGrosze)}`}
              {board.startSequenceNumber === null
                ? ''
                : board.startSequenceNumber === board.sequenceNumber
                  ? ' · plansza startowa'
                  : ` · dalsza plansza od #${board.startSequenceNumber}`}{' '}
              <button
                type="button"
                className="secondaryButton"
                onClick={(event) => {
                  trigger.current = event.currentTarget;
                  setSelected(board.sequenceNumber);
                  setDetail(null);
                  void readDetail(board.sequenceNumber);
                }}
              >
                Sprawdź poprawki
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {page?.nextCursor ? (
        <button
          type="button"
          className="secondaryButton"
          disabled={loading}
          onClick={() => void load(page.nextCursor ?? undefined)}
        >
          Starsze poprawione plansze
        </button>
      ) : null}
      {selected !== null && detail === null && reviewBusy ? (
        <p role="status">Wczytywanie historii planszy…</p>
      ) : null}
      {selected !== null && detail === null && reviewError !== null ? (
        <p role="alert">{reviewError}</p>
      ) : null}
      {selected !== null && detail !== null ? (
        <BoardSearchBoardLinesModal
          key={`${selected}:${modalVersion}`}
          api={client}
          gameId={gameId}
          sequenceNumber={selected}
          symbols={symbols}
          changedCellIndices={[
            ...new Set(detail.changes.map((change) => change.cellIndex)),
          ]}
          row={null}
          rulesVersionId={null}
          formatAmount={(credits) => `${credits} kr.`}
          startInEditMode
          onRecalculate={() => {
            void readDetail(selected);
          }}
          onCorrectionSaved={() => {
            void readDetail(selected, true);
          }}
          onClose={() => {
            ++detailRequestId.current;
            setSelected(null);
            setDetail(null);
            setReviewBusy(false);
            void load();
            trigger.current?.focus();
          }}
          reviewPanel={({ saving, refreshing, ready }) => (
            <section aria-label="Historia poprawek">
              <h4>
                Zmiany użytkownika
                {detail?.board.pending ? ' od ostatniego przeglądu' : ''}
              </h4>
              {reviewBusy ? <p role="status">Wczytywanie historii…</p> : null}
              {reviewError !== null ? <p role="alert">{reviewError}</p> : null}
              <ol>
                {detail?.changes.map((change) => (
                  <li key={change.id}>
                    Pole {change.cellIndex + 1}:{' '}
                    {symbolName(
                      change.beforeSymbolCode,
                      change.beforeQualityIssue,
                    )}{' '}
                    →{' '}
                    {symbolName(
                      change.afterSymbolCode,
                      change.afterQualityIssue,
                    )}{' '}
                    {change.beforeReviewState !== change.afterReviewState
                      ? ` · ${change.beforeReviewState === 'approved' ? 'zatwierdzone' : 'oczekujące'} → ${change.afterReviewState === 'approved' ? 'zatwierdzone' : 'oczekujące'}`
                      : ''}
                    · {formatBoardSearchShareDate(change.occurredAt)}
                  </li>
                ))}
              </ol>
              <button
                type="button"
                className="secondaryButton"
                disabled={reviewBusy || saving || refreshing}
                onClick={() => void readDetail(selected)}
              >
                Odśwież zmiany
              </button>
              {detail?.nextCursor ? (
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={reviewBusy}
                  onClick={() =>
                    void readDetail(
                      selected,
                      false,
                      detail.nextCursor ?? undefined,
                    )
                  }
                >
                  Starsze zmiany pól
                </button>
              ) : null}
              <button
                type="button"
                className="primaryButton"
                disabled={
                  reviewBusy ||
                  saving ||
                  refreshing ||
                  !ready ||
                  detail.nextCursor !== null ||
                  reviewError !== null ||
                  !detail.board.pending
                }
                onClick={() => void acknowledge()}
              >
                Oznacz jako przejrzane
              </button>
            </section>
          )}
        />
      ) : null}
    </section>
  );
}
