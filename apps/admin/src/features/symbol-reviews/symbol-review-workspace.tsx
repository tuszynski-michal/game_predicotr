'use client';

/* Symbol-cell assets are checksum-bound local Admin API responses. */
/* eslint-disable @next/next/no-img-element */

import type {
  GameResponse,
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  loadSymbolReviewGames,
  loadSymbolReviewPage,
  loadSymbolReviewSymbols,
  type LoadSymbolReviewPageOptions,
  type SymbolReviewClient,
} from './symbol-review-actions';
import {
  createSymbolReviewWorkspaceState,
  symbolReviewWorkspaceReducer,
  type SymbolReviewFilters,
} from './symbol-review-state';
import styles from './symbol-review-workspace.module.css';

type LoadState = 'error' | 'loading' | 'ready';

const INITIAL_FILTERS: SymbolReviewFilters = {
  gameId: null,
  state: 'all',
  symbolId: null,
};

interface SymbolReviewWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SymbolReviewClient;
}

export function SymbolReviewWorkspace({
  apiBaseUrl,
  client,
}: SymbolReviewWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [workspace, dispatch] = useReducer(
    symbolReviewWorkspaceReducer,
    INITIAL_FILTERS,
    createSymbolReviewWorkspaceState,
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [gamesState, setGamesState] = useState<LoadState>('loading');
  const [symbolsState, setSymbolsState] = useState<LoadState>('ready');
  const [pageState, setPageState] = useState<LoadState>('ready');
  const [error, setError] = useState('');
  const [projectionRebuilding, setProjectionRebuilding] = useState(false);
  const [paging, setPaging] = useState(false);
  const [reloadRevision, setReloadRevision] = useState(0);
  const gamesRequestId = useRef(0);
  const symbolsRequestId = useRef(0);
  const pageRequestId = useRef(0);
  const prefetchRequestId = useRef(0);

  const filters = workspace.filters;
  const currentPage = workspace.pages.current;
  const currentItems = currentPage?.items ?? [];
  const activeGame = games.find((game) => game.id === filters.gameId) ?? null;
  const hasLoadError =
    gamesState === 'error' || symbolsState === 'error' || pageState === 'error';

  const changeFilters = useCallback((nextFilters: SymbolReviewFilters) => {
    pageRequestId.current += 1;
    prefetchRequestId.current += 1;
    setError('');
    setProjectionRebuilding(false);
    dispatch({ filters: nextFilters, type: 'filters_changed' });
  }, []);

  useEffect(() => {
    const requestId = ++gamesRequestId.current;
    setGamesState('loading');
    setError('');
    void loadSymbolReviewGames(api).then((result) => {
      if (requestId !== gamesRequestId.current) return;
      if (!result.ok) {
        setGamesState('error');
        setError(result.error);
        return;
      }
      setGames(result.games);
      setGamesState('ready');
      const selectedGameId = result.games.some(
        (game) => game.id === workspace.filters.gameId,
      )
        ? workspace.filters.gameId
        : (result.games[0]?.id ?? null);
      if (selectedGameId !== workspace.filters.gameId) {
        changeFilters({
          ...workspace.filters,
          gameId: selectedGameId,
          symbolId: null,
        });
      }
    });
    return () => {
      gamesRequestId.current += 1;
    };
  }, [api, changeFilters, reloadRevision]);

  useEffect(() => {
    if (filters.gameId === null) {
      setSymbols([]);
      setSymbolsState('ready');
      return;
    }
    const requestId = ++symbolsRequestId.current;
    setSymbolsState('loading');
    void loadSymbolReviewSymbols(api, filters.gameId).then((result) => {
      if (requestId !== symbolsRequestId.current) return;
      if (!result.ok) {
        setSymbolsState('error');
        setError(result.error);
        return;
      }
      setSymbols(result.symbols);
      setSymbolsState('ready');
      const selectedSymbolId = result.symbols.some(
        (symbol) => symbol.id === filters.symbolId,
      )
        ? filters.symbolId
        : (result.symbols[0]?.id ?? null);
      if (selectedSymbolId !== filters.symbolId) {
        changeFilters({ ...filters, symbolId: selectedSymbolId });
      }
    });
    return () => {
      symbolsRequestId.current += 1;
    };
  }, [
    api,
    changeFilters,
    filters.gameId,
    filters.symbolId,
    filters.state,
    reloadRevision,
  ]);

  useEffect(() => {
    const pageFilters = asPageFilters(filters);
    if (pageFilters === null) {
      dispatch({ type: 'clear_pages' });
      setPageState('ready');
      return;
    }
    const requestId = ++pageRequestId.current;
    prefetchRequestId.current += 1;
    setPageState('loading');
    setError('');
    setProjectionRebuilding(false);
    void loadSymbolReviewPage(api, pageFilters).then((result) => {
      if (requestId !== pageRequestId.current) return;
      if (!result.ok) {
        setPageState('error');
        setError(result.error);
        setProjectionRebuilding(result.isProjectionRebuilding);
        return;
      }
      dispatch({ page: result.page, type: 'initial_page_loaded' });
      setPageState('ready');
    });
  }, [api, filters, reloadRevision]);

  useEffect(() => {
    const pageFilters = asPageFilters(filters);
    if (
      pageFilters === null ||
      currentPage?.nextCursor === null ||
      currentPage === null
    ) {
      return;
    }
    const requestId = ++prefetchRequestId.current;
    void loadSymbolReviewPage(api, {
      ...pageFilters,
      afterCursor: currentPage.nextCursor,
    }).then((result) => {
      if (requestId !== prefetchRequestId.current || !result.ok) return;
      dispatch({ page: result.page, type: 'next_page_prefetched' });
    });
  }, [api, currentPage, filters]);

  async function movePage(direction: -1 | 1) {
    const pageFilters = asPageFilters(filters);
    if (paging || pageFilters === null || currentPage === null) {
      return;
    }
    const cached =
      direction === 1 ? workspace.pages.next : workspace.pages.previous;
    if (cached !== null) {
      dispatch({
        page: cached,
        type: direction === 1 ? 'next_page_loaded' : 'previous_page_loaded',
      });
      return;
    }
    const cursor =
      direction === 1 ? currentPage.nextCursor : currentPage.previousCursor;
    if (cursor === null) return;
    setPaging(true);
    setError('');
    const result = await loadSymbolReviewPage(api, {
      ...pageFilters,
      ...(direction === 1 ? { afterCursor: cursor } : { beforeCursor: cursor }),
    });
    setPaging(false);
    if (!result.ok) {
      setError(result.error);
      setProjectionRebuilding(result.isProjectionRebuilding);
      return;
    }
    dispatch({
      page: result.page,
      type: direction === 1 ? 'next_page_loaded' : 'previous_page_loaded',
    });
  }

  return (
    <section aria-label="Weryfikacja symboli" className={styles.workspace}>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Lokalny workflow · cropy symboli</p>
          <h1>Weryfikacja symboli</h1>
          <p className="lead">
            Przeglądaj aktualne cropy po jednym symbolu. Zaznaczanie i masowe
            decyzje zostaną dodane w następnym etapie.
          </p>
        </div>
      </header>

      <div className={styles.filters}>
        <label>
          Gra
          <select
            disabled={gamesState !== 'ready'}
            onChange={(event) =>
              changeFilters({
                ...filters,
                gameId: event.target.value || null,
                symbolId: null,
              })
            }
            value={filters.gameId ?? ''}
          >
            {games.length === 0 ? <option value="">Brak gier</option> : null}
            {games.map((game) => (
              <option key={game.id} value={game.id}>
                {game.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Symbol
          <select
            disabled={filters.gameId === null || symbolsState !== 'ready'}
            onChange={(event) =>
              changeFilters({
                ...filters,
                symbolId: event.target.value || null,
              })
            }
            value={filters.symbolId ?? ''}
          >
            {symbols.length === 0 ? (
              <option value="">Brak aktywnych symboli</option>
            ) : null}
            {symbols.map((symbol) => (
              <option key={symbol.id} value={symbol.id}>
                {symbol.name}
              </option>
            ))}
            <option value="unknown">Nierozpoznany (?)</option>
          </select>
        </label>
        <fieldset
          disabled={filters.gameId === null || symbolsState !== 'ready'}
        >
          <legend>Stan</legend>
          <SymbolReviewStateOption
            checked={filters.state === 'all'}
            label="Wszystkie"
            onChange={() => changeFilters({ ...filters, state: 'all' })}
            value="all"
          />
          <SymbolReviewStateOption
            checked={filters.state === 'approved'}
            label="Zatwierdzone"
            onChange={() => changeFilters({ ...filters, state: 'approved' })}
            value="approved"
          />
          <SymbolReviewStateOption
            checked={filters.state === 'pending'}
            label="Oczekujące"
            onChange={() => changeFilters({ ...filters, state: 'pending' })}
            value="pending"
          />
        </fieldset>
      </div>

      {gamesState === 'loading' ||
      symbolsState === 'loading' ||
      pageState === 'loading' ? (
        <SymbolReviewStatus
          text="Wczytywanie bounded strony cropów…"
          title="Wczytywanie"
        />
      ) : null}
      {hasLoadError ? (
        <SymbolReviewStatus
          action={() => setReloadRevision((revision) => revision + 1)}
          error
          text={
            projectionRebuilding
              ? 'Widok jest jeszcze przebudowywany dla tej gry. Poczekaj na backfill i spróbuj ponownie.'
              : error
          }
          title={
            projectionRebuilding
              ? 'Trwa przygotowanie widoku'
              : 'Nie udało się pobrać cropów'
          }
        />
      ) : null}
      {pageState === 'ready' && currentPage !== null ? (
        <>
          <div className={styles.summary}>
            <span>
              {activeGame?.name ?? 'Gra'} · {stateLabel(filters.state)} ·{' '}
              {symbolLabel(filters.symbolId, symbols)}
            </span>
            <span>
              Wyniki: {currentPage.counts.allCount} · zatwierdzone:{' '}
              {currentPage.counts.approvedCount} · oczekujące:{' '}
              {currentPage.counts.pendingCount}
            </span>
          </div>
          {currentItems.length === 0 ? (
            <SymbolReviewEmpty />
          ) : (
            <>
              <div className={styles.grid}>
                {currentItems.map((item) => (
                  <SymbolReviewCard
                    api={api}
                    gameId={filters.gameId!}
                    item={item}
                    key={item.id}
                  />
                ))}
              </div>
              <nav aria-label="Strony cropów" className={styles.pagination}>
                <button
                  className="secondaryButton"
                  disabled={
                    paging ||
                    (workspace.pages.previous === null &&
                      currentPage.previousCursor === null)
                  }
                  onClick={() => void movePage(-1)}
                  type="button"
                >
                  ← Poprzednia strona
                </button>
                <span>Po 60 cropów · w pamięci najwyżej 3 strony</span>
                <button
                  className="secondaryButton"
                  disabled={
                    paging ||
                    (workspace.pages.next === null &&
                      currentPage.nextCursor === null)
                  }
                  onClick={() => void movePage(1)}
                  type="button"
                >
                  Następna strona →
                </button>
              </nav>
            </>
          )}
        </>
      ) : null}
    </section>
  );
}

function SymbolReviewStateOption({
  checked,
  label,
  onChange,
  value,
}: {
  readonly checked: boolean;
  readonly label: string;
  readonly onChange: () => void;
  readonly value: SymbolCellReviewFilterState;
}) {
  return (
    <label>
      <input
        checked={checked}
        name="symbol-review-state"
        onChange={onChange}
        type="radio"
        value={value}
      />
      {label}
    </label>
  );
}

function SymbolReviewCard({
  api,
  gameId,
  item,
}: {
  readonly api: SymbolReviewClient;
  readonly gameId: string;
  readonly item: SymbolCellReviewListItemResponse;
}) {
  const [imageFailed, setImageFailed] = useState(false);
  const imageUrl = api.symbolCellReviewAssetUrl(
    gameId,
    item.id,
    item.cropChecksumSha256,
  );
  return (
    <article className={styles.card}>
      {imageFailed ? (
        <div
          aria-label="Brak aktualnego cropa"
          className={styles.assetFallback}
          role="img"
        >
          ?
        </div>
      ) : (
        <img
          alt={`Crop ${item.assignedSymbolName ?? 'nierozpoznany'} z planszy ${item.sequenceNumber}`}
          loading="lazy"
          onError={() => setImageFailed(true)}
          src={imageUrl}
        />
      )}
      <div className={styles.cardBody}>
        <strong>{item.assignedSymbolName ?? 'Nierozpoznany (?)'}</strong>
        <span>
          Plansza #{item.sequenceNumber} · R{item.rowIndex + 1}/K
          {item.columnIndex + 1}
        </span>
        <span>
          {item.reviewState === 'approved' ? 'Zatwierdzony' : 'Oczekuje'}
        </span>
        {item.hasGridIssue ? <em>Zła siatka</em> : null}
      </div>
    </article>
  );
}

function SymbolReviewEmpty() {
  return (
    <div className={styles.empty}>
      <h2>Brak cropów dla wybranego filtra</h2>
      <p>Zmień symbol albo stan, aby zobaczyć inne bieżące wyniki.</p>
    </div>
  );
}

function SymbolReviewStatus({
  action,
  error = false,
  text,
  title,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
  readonly title: string;
}) {
  return (
    <div
      className={
        error ? 'feedbackBanner feedbackBannerError' : 'feedbackBanner'
      }
      role={error ? 'alert' : 'status'}
    >
      <div>
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}

function stateLabel(state: SymbolCellReviewFilterState): string {
  if (state === 'approved') return 'zatwierdzone';
  if (state === 'pending') return 'oczekujące';
  return 'wszystkie';
}

function symbolLabel(
  symbolId: string | 'unknown' | null,
  symbols: readonly SymbolResponse[],
): string {
  if (symbolId === 'unknown') return 'Nierozpoznany (?)';
  return symbols.find((symbol) => symbol.id === symbolId)?.name ?? 'Symbol';
}

function asPageFilters(
  filters: SymbolReviewFilters,
): LoadSymbolReviewPageOptions | null {
  if (filters.gameId === null || filters.symbolId === null) {
    return null;
  }
  return {
    gameId: filters.gameId,
    state: filters.state,
    symbolId: filters.symbolId,
  };
}
