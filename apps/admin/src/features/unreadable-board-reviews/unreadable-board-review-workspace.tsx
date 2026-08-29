'use client';

import type {
  ResolveUnreadableCellRequest,
  SymbolResponse,
  UnreadableBoardReviewCellResponse,
  UnreadableBoardReviewDetailResponse,
  UnreadableBoardReviewPageResponse,
  UnreadableBoardReviewView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  loadUnreadableBoardDetail,
  loadUnreadableBoardPage,
  loadUnreadableBoardSymbols,
  resolveUnreadableCell,
} from './unreadable-board-review-actions';
import styles from './unreadable-board-review-workspace.module.css';

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
}

function initialCellSelections(
  detail: UnreadableBoardReviewDetailResponse,
  symbols: readonly SymbolResponse[],
): Record<number, string> {
  return Object.fromEntries(
    detail.cells.map((cell) => [
      cell.cellIndex,
      cell.assignedSymbolId ?? symbols[0]?.id ?? '',
    ]),
  );
}

export function UnreadableBoardReviewWorkspace({ apiBaseUrl, gameId }: Props) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
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
  const [savingCell, setSavingCell] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadPage = useCallback(
    async (cursor?: string) => {
      setLoading(true);
      setError(null);
      const result = await loadUnreadableBoardPage(api, gameId, view, cursor);
      if (!result.ok) {
        setError(result.error);
        setPage(null);
        setDetail(null);
        setLoading(false);
        return;
      }
      setPage(result.page);
      const first = result.page.items[0];
      if (first === undefined) {
        setDetail(null);
        setLoading(false);
        return;
      }
      const detailResult = await loadUnreadableBoardDetail(
        api,
        gameId,
        first.reviewItemId,
      );
      if (detailResult.ok) {
        setDetail(detailResult.detail);
        setSelectedByCell(initialCellSelections(detailResult.detail, symbols));
      } else {
        setError(detailResult.error);
        setDetail(null);
      }
      setLoading(false);
    },
    [api, gameId, symbols, view],
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
      void loadPage();
    });
    return () => {
      cancelled = true;
    };
  }, [loadPage]);

  async function openBoard(reviewItemId: string) {
    setLoading(true);
    setError(null);
    const result = await loadUnreadableBoardDetail(api, gameId, reviewItemId);
    if (result.ok) {
      setDetail(result.detail);
      setSelectedByCell(initialCellSelections(result.detail, symbols));
    } else setError(result.error);
    setLoading(false);
  }

  async function resolveCell(
    cell: UnreadableBoardReviewCellResponse,
    unknown: boolean,
  ) {
    if (detail === null || savingCell !== null) return;
    const targetSymbolId = selectedByCell[cell.cellIndex];
    if (!unknown && !targetSymbolId) return;
    const assignment: ResolveUnreadableCellRequest['assignment'] = unknown
      ? { kind: 'unknown' }
      : { kind: 'symbol', symbolId: targetSymbolId };
    setSavingCell(cell.cellIndex);
    setError(null);
    const result = await resolveUnreadableCell(
      api,
      gameId,
      detail.reviewItemId,
      cell.cellIndex,
      {
        assignment,
        expectedCropChecksumSha256: cell.cropChecksumSha256,
        expectedCropSampleId: cell.cropSampleId,
        expectedGeometryRevision: cell.geometryRevision,
        expectedRevision: cell.revision,
      },
    );
    if (!result.ok) {
      setError(result.error ?? 'Nie udało się zapisać decyzji.');
      setSavingCell(null);
      return;
    }
    const refreshed = await loadUnreadableBoardDetail(
      api,
      gameId,
      detail.reviewItemId,
    );
    if (refreshed.ok) {
      setDetail(refreshed.detail);
      if (
        view === 'pending' &&
        !refreshed.detail.cells.some(
          (candidate) =>
            candidate.qualityIssue === 'unreadable' &&
            candidate.reviewState === 'pending',
        )
      ) {
        await loadPage(cursorHistory.at(-1));
      }
    } else {
      await loadPage(cursorHistory.at(-1));
    }
    setSavingCell(null);
  }

  const activeIndex =
    detail === null
      ? -1
      : (page?.items.findIndex(
          (item) => item.reviewItemId === detail.reviewItemId,
        ) ?? -1);

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
            Słaby crop pozostaje poza treningiem. Możesz przypisać rzeczywisty
            symbol albo logiczne <strong>?</strong>.
          </p>
        </div>
        <label>
          Widok
          <select
            disabled={savingCell !== null}
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
      {loading && detail === null ? <p>Ładowanie kolejki…</p> : null}
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
              disabled={savingCell !== null}
              key={item.reviewItemId}
              onClick={() => void openBoard(item.reviewItemId)}
              type="button"
            >
              <strong>Plansza {item.sequenceNumber}</strong>
              <span>{item.pendingUnreadableCount} do ustalenia</span>
            </button>
          ))}
        </nav>
      ) : null}

      {detail !== null ? (
        <>
          <div className={styles.boardHeader}>
            <button
              disabled={activeIndex <= 0 || savingCell !== null}
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
                savingCell !== null
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
              const pending = unreadable && cell.reviewState === 'pending';
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
                  {pending ? (
                    <>
                      <select
                        aria-label={`Symbol pola ${cell.cellIndex + 1}`}
                        disabled={savingCell !== null}
                        onChange={(event) =>
                          setSelectedByCell((current) => ({
                            ...current,
                            [cell.cellIndex]: event.target.value,
                          }))
                        }
                        value={selectedByCell[cell.cellIndex] ?? ''}
                      >
                        {symbols.map((symbol) => (
                          <option key={symbol.id} value={symbol.id}>
                            {symbol.name}
                          </option>
                        ))}
                      </select>
                      <div className={styles.actions}>
                        <button
                          disabled={
                            savingCell !== null ||
                            !selectedByCell[cell.cellIndex]
                          }
                          onClick={() => void resolveCell(cell, false)}
                          type="button"
                        >
                          {savingCell === cell.cellIndex
                            ? 'Zapisywanie…'
                            : 'Przypisz'}
                        </button>
                        <button
                          disabled={savingCell !== null}
                          onClick={() => void resolveCell(cell, true)}
                          type="button"
                        >
                          Ustaw ?
                        </button>
                      </div>
                    </>
                  ) : (
                    <strong>{cell.assignedSymbolName ?? '?'}</strong>
                  )}
                  {unreadable ? (
                    <small>Nieczytelny · poza treningiem</small>
                  ) : null}
                </article>
              );
            })}
          </div>
        </>
      ) : null}

      <footer className={styles.pagination}>
        <button
          disabled={cursorHistory.length <= 1 || savingCell !== null}
          onClick={() => {
            const nextHistory = cursorHistory.slice(0, -1);
            setCursorHistory(nextHistory);
            void loadPage(nextHistory.at(-1));
          }}
          type="button"
        >
          Poprzednia strona
        </button>
        <button
          disabled={page?.nextCursor == null || savingCell !== null}
          onClick={() => {
            const cursor = page?.nextCursor;
            if (cursor === null || cursor === undefined) return;
            setCursorHistory((current) => [...current, cursor]);
            void loadPage(cursor);
          }}
          type="button"
        >
          Następna strona
        </button>
      </footer>
    </section>
  );
}
