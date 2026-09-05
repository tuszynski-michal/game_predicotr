'use client';

import type {
  SaveUnreadableBoardRequest,
  SymbolResponse,
  UnreadableBoardReviewDetailResponse,
  UnreadableBoardReviewPageResponse,
  UnreadableBoardReviewView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  loadUnreadableBoardDetail,
  loadUnreadableBoardPage,
  loadUnreadableBoardSymbols,
  saveUnreadableBoard,
} from './unreadable-board-review-actions';
import styles from './unreadable-board-review-workspace.module.css';

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
}

const UNKNOWN_SELECTION = '__unknown__';

function initialCellSelections(
  detail: UnreadableBoardReviewDetailResponse,
): Record<number, string> {
  return Object.fromEntries(
    detail.cells.map((cell) => [
      cell.cellIndex,
      cell.assignedSymbolId ?? UNKNOWN_SELECTION,
    ]),
  );
}

function hasPendingUnreadable(
  detail: UnreadableBoardReviewDetailResponse,
): boolean {
  return detail.cells.some(
    (cell) =>
      cell.qualityIssue === 'unreadable' && cell.reviewState === 'pending',
  );
}

export function UnreadableBoardReviewWorkspace({ apiBaseUrl, gameId }: Props) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const requestVersion = useRef(0);
  const [view, setView] = useState<UnreadableBoardReviewView>('pending');
  const [page, setPage] = useState<UnreadableBoardReviewPageResponse | null>(
    null,
  );
  const [detail, setDetail] =
    useState<UnreadableBoardReviewDetailResponse | null>(null);
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [selectedByCell, setSelectedByCell] = useState<Record<number, string>>(
    {},
  );
  const [cursorHistory, setCursorHistory] = useState<
    readonly (string | undefined)[]
  >([undefined]);
  const [loading, setLoading] = useState(true);
  const [savingBoard, setSavingBoard] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async ({
      currentView,
      cursor,
    }: {
      currentView: UnreadableBoardReviewView;
      cursor?: string;
    }) => {
      const currentRequest = ++requestVersion.current;
      setLoading(true);
      setError(null);
      setPage(null);
      setDetail(null);
      const result = await loadUnreadableBoardPage(
        api,
        gameId,
        currentView,
        cursor,
      );
      if (currentRequest !== requestVersion.current) return;
      if (!result.ok) {
        setError(result.error);
        setLoading(false);
        return;
      }
      setPage(result.page);
      const first = result.page.items[0];
      if (first === undefined) {
        setLoading(false);
        return;
      }
      const detailResult = await loadUnreadableBoardDetail(
        api,
        gameId,
        first.reviewItemId,
      );
      if (currentRequest !== requestVersion.current) return;
      if (detailResult.ok) {
        setDetail(detailResult.detail);
        setSelectedByCell(initialCellSelections(detailResult.detail));
      } else {
        setError(detailResult.error);
      }
      setLoading(false);
    },
    [api, gameId],
  );

  useEffect(() => {
    let cancelled = false;
    void loadUnreadableBoardSymbols(api, gameId).then((result) => {
      if (cancelled) return;
      if (result.ok) setSymbols(result.symbols);
      else setError(result.error);
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (cancelled) return;
      setCursorHistory([undefined]);
      void loadPage({ currentView: view });
    });
    return () => {
      cancelled = true;
    };
  }, [loadPage, view]);

  async function openBoard(reviewItemId: string) {
    const currentRequest = ++requestVersion.current;
    setLoading(true);
    setError(null);
    const result = await loadUnreadableBoardDetail(api, gameId, reviewItemId);
    if (currentRequest !== requestVersion.current) return;
    if (result.ok) {
      setDetail(result.detail);
      setSelectedByCell(initialCellSelections(result.detail));
    } else {
      setError(result.error);
    }
    setLoading(false);
  }

  const canSave = detail !== null && hasPendingUnreadable(detail);
  const busy = loading || savingBoard;
  const activeIndex =
    detail === null
      ? -1
      : (page?.items.findIndex(
          (item) => item.reviewItemId === detail.reviewItemId,
        ) ?? -1);

  async function saveBoard() {
    if (detail === null || !canSave || savingBoard) return;
    const cells = detail.cells.map((cell) => {
      const selected = selectedByCell[cell.cellIndex];
      if (selected === undefined) return null;
      return {
        assignment:
          selected === UNKNOWN_SELECTION
            ? ({ kind: 'unknown' } as const)
            : ({ kind: 'symbol', symbolId: selected } as const),
        cellIndex: cell.cellIndex,
        expectedCropChecksumSha256: cell.cropChecksumSha256,
        expectedCropSampleId: cell.cropSampleId,
        expectedGeometryRevision: cell.geometryRevision,
        expectedRevision: cell.revision,
      };
    });
    if (cells.some((cell) => cell === null)) {
      setError('Wybierz symbol albo ? dla każdego pola planszy.');
      return;
    }
    setSavingBoard(true);
    setError(null);
    const result = await saveUnreadableBoard(api, gameId, detail.reviewItemId, {
      cells: cells as SaveUnreadableBoardRequest['cells'],
    });
    if (!result.ok) {
      setError(result.error ?? 'Nie udało się zapisać planszy.');
      setSavingBoard(false);
      return;
    }
    await loadPage({ currentView: view, cursor: cursorHistory.at(-1) });
    setSavingBoard(false);
  }

  return (
    <section
      className={styles.workspace}
      aria-labelledby="unreadable-board-title"
    >
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Ręczne rozstrzygnięcie</p>
          <h3 id="unreadable-board-title">Weryfikacja symbolu na planszy</h3>
          <p>
            Edytujesz całą planszę, a zapis jest atomowy. Wybór{' '}
            <strong>?</strong> oznacza nieczytelny crop bez katalogowego symbolu
            i wyklucza go z treningu.
          </p>
        </div>
        <label>
          Widok
          <select
            disabled={busy}
            onChange={(event) => {
              setCursorHistory([undefined]);
              setView(event.target.value as UnreadableBoardReviewView);
            }}
            value={view}
          >
            <option value="pending">Do ustalenia</option>
            <option value="all">Wszystkie nieczytelne</option>
          </select>
        </label>
      </header>

      {error !== null ? <p className={styles.error}>{error}</p> : null}
      {loading ? <p>Ładowanie kolejki…</p> : null}
      {!loading && page?.items.length === 0 ? (
        <div className={styles.empty}>
          <strong>Brak plansz w tym widoku</strong>
          <span>Nie ma nieczytelnych pól wymagających ręcznej decyzji.</span>
        </div>
      ) : null}

      {page !== null && page.items.length > 0 ? (
        <nav
          className={styles.queue}
          aria-label="Plansze z nieczytelnymi symbolami"
        >
          {page.items.map((item) => (
            <button
              aria-current={
                detail?.reviewItemId === item.reviewItemId ? 'true' : undefined
              }
              disabled={busy}
              key={item.reviewItemId}
              onClick={() => void openBoard(item.reviewItemId)}
              type="button"
            >
              <strong>Plansza {item.sequenceNumber}</strong>
              <span>
                {view === 'pending'
                  ? `${item.pendingUnreadableCount} do ustalenia`
                  : `${item.unreadableCount} nieczytelnych`}
              </span>
            </button>
          ))}
        </nav>
      ) : null}

      {detail !== null ? (
        <>
          <div className={styles.boardHeader}>
            <button
              disabled={activeIndex <= 0 || busy}
              onClick={() => {
                const item = page?.items[activeIndex - 1];
                if (item !== undefined) void openBoard(item.reviewItemId);
              }}
              type="button"
            >
              ← Poprzednia
            </button>
            <strong>Plansza {detail.sequenceNumber}</strong>
            <button
              disabled={
                page === null ||
                activeIndex < 0 ||
                activeIndex >= page.items.length - 1 ||
                busy
              }
              onClick={() => {
                const item = page?.items[activeIndex + 1];
                if (item !== undefined) void openBoard(item.reviewItemId);
              }}
              type="button"
            >
              Następna →
            </button>
          </div>
          <div
            className={styles.board}
            style={{
              gridTemplateColumns: `repeat(${detail.gridColumns}, minmax(0, 1fr))`,
            }}
          >
            {detail.cells.map((cell) => {
              const unreadable = cell.qualityIssue === 'unreadable';
              const selected =
                selectedByCell[cell.cellIndex] ?? UNKNOWN_SELECTION;
              return (
                <article className={styles.cell} key={cell.cellReviewId}>
                  {/* The API already returns a checksum-bound 100 px thumbnail. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    alt={`Pole ${cell.rowIndex + 1}/${cell.columnIndex + 1}`}
                    loading="lazy"
                    src={api.symbolCellReviewAssetUrl(
                      gameId,
                      cell.cellReviewId,
                      cell.cropChecksumSha256,
                    )}
                  />
                  <span className={styles.position}>
                    R{cell.rowIndex + 1} / K{cell.columnIndex + 1}
                  </span>
                  <select
                    aria-label={`Symbol pola ${cell.cellIndex + 1}`}
                    disabled={!canSave || busy}
                    onChange={(event) =>
                      setSelectedByCell((current) => ({
                        ...current,
                        [cell.cellIndex]: event.target.value,
                      }))
                    }
                    value={selected}
                  >
                    <option value={UNKNOWN_SELECTION}>?</option>
                    {symbols.map((symbol) => (
                      <option key={symbol.id} value={symbol.id}>
                        {symbol.name}
                      </option>
                    ))}
                  </select>
                  {unreadable ? (
                    <small>Nieczytelny · poza treningiem</small>
                  ) : (
                    <small>Aktualny crop</small>
                  )}
                </article>
              );
            })}
          </div>
          <div className={styles.saveBar}>
            <p>
              {canSave
                ? `Zapis obejmie wszystkie ${detail.cells.length} pól widocznych na tej planszy.`
                : 'Ta plansza jest już rozstrzygnięta; w tym widoku pozostaje tylko do odczytu.'}
            </p>
            <button
              disabled={!canSave || busy}
              onClick={() => void saveBoard()}
              type="button"
            >
              {savingBoard ? 'Zapisywanie…' : 'Zapisz i zatwierdź planszę'}
            </button>
          </div>
        </>
      ) : null}

      <footer className={styles.pagination}>
        <button
          disabled={cursorHistory.length <= 1 || busy}
          onClick={() => {
            const nextHistory = cursorHistory.slice(0, -1);
            setCursorHistory(nextHistory);
            void loadPage({
              currentView: view,
              cursor: nextHistory.at(-1),
            });
          }}
          type="button"
        >
          Poprzednia strona
        </button>
        <button
          disabled={page?.nextCursor == null || busy}
          onClick={() => {
            const cursor = page?.nextCursor;
            if (cursor === null || cursor === undefined) return;
            setCursorHistory((current) => [...current, cursor]);
            void loadPage({ currentView: view, cursor });
          }}
          type="button"
        >
          Następna strona
        </button>
      </footer>
    </section>
  );
}
