'use client';

import type {
  AdminApiClient,
  SuperGameStateResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';
import {
  SeriesBadges,
  SuperGameSeriesPanel,
  type SuperGameSeriesViewClient,
} from '@game-predictor/board-search-ui';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  COMPLETENESS_FILTER_OPTIONS,
  DEFINED_FILTER_OPTIONS,
  RUN_VERIFICATION_FILTER_OPTIONS,
  SERIES_STATE_POLL_INTERVAL_MS,
  type CompletenessFilter,
  type DefinedFilter,
  type RunVerificationFilter,
  type SeriesFilters,
  applySeriesListPage,
  changeSeriesFilters,
  createSeriesListState,
  deriveResultMessage,
  failSeriesList,
  nextUndefinedSeriesQuery,
  parseSeriesBoardRange,
  pickSeriesRulesVersion,
  reloadSeriesList,
  replaceSeriesInList,
  seriesBoardRange,
  seriesBoardRangeLabel,
  seriesCountsCaption,
  seriesListQuery,
  seriesRangeLabel,
  seriesRulesVersionOptions,
  shouldPollSeriesState,
  startLoadingMoreSeries,
  superGameSeriesErrorMessage,
  superGameStateBanner,
  undefinedSeriesCountLabel,
} from './super-game-series-state';
import styles from './super-game-series-workspace.module.css';

export type SuperGameSeriesClient = Pick<
  AdminApiClient,
  | 'applySymbolCellReviewDecision'
  | 'boardSearchBoardViewUrl'
  | 'deriveSuperGameSeries'
  | 'getBoardSearchBoardDetail'
  | 'getSuperGameSeriesState'
  | 'listRulesVersions'
  | 'listSuperGameSeries'
  | 'listSuperGameSeriesBoards'
  | 'listSymbols'
  | 'refreshBoardSearchBoardDocument'
  | 'setSuperGameSeriesSuperSymbol'
  | 'symbolImageAssetUrl'
>;

interface SuperGameSeriesWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: SuperGameSeriesClient;
  readonly gameId: string;
  /** The opened series (`?series=`); `null` shows the list. */
  readonly seriesId: string | null;
  readonly onSeriesChange: (seriesId: string | null) => void;
}

type Toast = { readonly kind: 'success' | 'error'; readonly text: string };

const TOAST_DURATION_MS = 6000;

/**
 * The shared series view (TASK-1058) over the Admin client: the search for
 * the next series without a super symbol is the Admin list query with the
 * list filters (`nextUndefinedSeriesQuery`).
 */
function seriesViewClient(
  api: SuperGameSeriesClient,
): SuperGameSeriesViewClient {
  return {
    applySymbolCellReviewDecision: (...args) =>
      api.applySymbolCellReviewDecision(...args),
    boardSearchBoardViewUrl: (...args) => api.boardSearchBoardViewUrl(...args),
    getBoardSearchBoardDetail: (...args) =>
      api.getBoardSearchBoardDetail(...args),
    listNextUndefinedSuperGameSeries: (gameId, query) =>
      api.listSuperGameSeries(
        gameId,
        nextUndefinedSeriesQuery(query.filters, query.afterTrigger),
      ),
    listSuperGameSeriesBoards: (...args) =>
      api.listSuperGameSeriesBoards(...args),
    refreshBoardSearchBoardDocument: (...args) =>
      api.refreshBoardSearchBoardDocument(...args),
    setSuperGameSeriesSuperSymbol: (...args) =>
      api.setSuperGameSeriesSuperSymbol(...args),
    symbolImageAssetUrl: (...args) => api.symbolImageAssetUrl(...args),
  };
}

export function SuperGameSeriesWorkspace({
  apiBaseUrl,
  client,
  gameId,
  onSeriesChange,
  seriesId,
}: SuperGameSeriesWorkspaceProps) {
  const api = useMemo<SuperGameSeriesClient>(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const viewClient = useMemo(() => seriesViewClient(api), [api]);

  const [symbols, setSymbols] = useState<readonly SymbolResponse[]>([]);
  const [rules, setRules] = useState<{
    readonly loaded: boolean;
    readonly versionId: string | null;
    readonly options: ReturnType<typeof seriesRulesVersionOptions>;
  }>({ loaded: false, options: [], versionId: null });
  const [filters, setFilters] = useState<SeriesFilters>(
    () => createSeriesListState().filters,
  );
  const [list, setList] = useState(() => createSeriesListState());
  const [reloadToken, setReloadToken] = useState(0);
  const [symbolsToken, setSymbolsToken] = useState(0);
  const [symbolsError, setSymbolsError] = useState<string | null>(null);
  const [generation, setGeneration] = useState<SuperGameStateResponse | null>(
    null,
  );
  const [deriving, setDeriving] = useState(false);
  // A change makes the opened series read itself again (after „Przelicz
  // serie” finished).
  const [viewToken, setViewToken] = useState(0);
  const [toast, setToast] = useState<Toast | null>(null);
  const toastTimer = useRef<number | null>(null);
  const listRef = useRef(list);
  useEffect(() => {
    listRef.current = list;
  });

  const showToast = useCallback((next: Toast) => {
    setToast(next);
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(
      () => setToast(null),
      TOAST_DURATION_MS,
    );
  }, []);

  useEffect(
    () => () => {
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    },
    [],
  );

  // Symbols (ordinary list, trigger symbols); a failure is shown and retried.
  useEffect(() => {
    let cancelled = false;
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          setSymbolsError(
            superGameSeriesErrorMessage(
              result.error,
              'Nie udało się pobrać katalogu symboli.',
            ),
          );
          return;
        }
        setSymbolsError(null);
        setSymbols(result.data);
      })
      .catch(() => {
        if (!cancelled) {
          setSymbolsError(
            'Połączenie z lokalnym Admin API zostało przerwane podczas pobierania symboli.',
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, symbolsToken]);

  // The rules version used to read the cells of a board.
  useEffect(() => {
    let cancelled = false;
    void api
      .listRulesVersions(gameId)
      .then((result) => {
        if (cancelled) return;
        const versions = result.data ?? [];
        setRules({
          loaded: true,
          options: seriesRulesVersionOptions(versions),
          versionId: pickSeriesRulesVersion(versions),
        });
      })
      .catch(() => {
        if (!cancelled)
          setRules({ loaded: true, options: [], versionId: null });
      });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  // First page of the list for the current filters.
  useEffect(() => {
    let cancelled = false;
    const loadGeneration = listRef.current.generation;
    void api
      .listSuperGameSeries(gameId, seriesListQuery(filters, null))
      .then((result) => {
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              superGameSeriesErrorMessage(
                result.error,
                'Nie udało się pobrać listy serii.',
              ),
            ),
          );
          return;
        }
        const page = result.data;
        if (listRef.current.generation !== loadGeneration) return;
        setGeneration(page.superGameState);
        setList((state) =>
          applySeriesListPage(state, {
            cursor: null,
            generation: loadGeneration,
            response: page,
          }),
        );
      })
      .catch(() => {
        if (!cancelled) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              'Połączenie z lokalnym Admin API zostało przerwane.',
            ),
          );
        }
      });
    return () => {
      cancelled = true;
    };
  }, [api, filters, gameId, reloadToken]);

  const stale = shouldPollSeriesState(generation);

  // A new load generation: pages and errors of earlier requests are dropped.
  const reloadList = useCallback(() => {
    setList((state) => reloadSeriesList(state));
    setReloadToken((token) => token + 1);
  }, []);

  const reloadAll = useCallback(() => {
    reloadList();
    setViewToken((token) => token + 1);
  }, [reloadList]);

  // While the generation is stale, its freshness is polled; when it becomes
  // fresh the list and the opened series are read again.
  useEffect(() => {
    if (!stale) return;
    const timer = window.setInterval(() => {
      void api
        .getSuperGameSeriesState(gameId)
        .then((result) => {
          if (result.data === undefined) return;
          setGeneration(result.data);
          if (result.data.fresh) {
            reloadAll();
            showToast({
              kind: 'success',
              text: 'Serie zostały przeliczone. Lista jest odświeżona.',
            });
          }
        })
        .catch(() => undefined);
    }, SERIES_STATE_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [api, gameId, reloadAll, showToast, stale]);

  function changeFilters(next: SeriesFilters) {
    setFilters(next);
    setList((state) => changeSeriesFilters(state, next));
  }

  function loadMore() {
    if (list.status === 'loading' || list.nextCursor === null) return;
    const cursor = list.nextCursor;
    const loadGeneration = list.generation;
    const currentFilters = list.filters;
    setList((state) => startLoadingMoreSeries(state));
    void api
      .listSuperGameSeries(gameId, seriesListQuery(currentFilters, cursor))
      .then((result) => {
        if (listRef.current.generation !== loadGeneration) return;
        if (result.error !== undefined || result.data === undefined) {
          setList((state) =>
            failSeriesList(
              state,
              loadGeneration,
              superGameSeriesErrorMessage(
                result.error,
                'Nie udało się pobrać kolejnych serii.',
              ),
            ),
          );
          return;
        }
        const page = result.data;
        setGeneration(page.superGameState);
        setList((state) =>
          applySeriesListPage(state, {
            cursor,
            generation: loadGeneration,
            response: page,
          }),
        );
      })
      .catch(() => {
        setList((state) =>
          failSeriesList(
            state,
            loadGeneration,
            'Połączenie z lokalnym Admin API zostało przerwane.',
          ),
        );
      });
  }

  function derive() {
    setDeriving(true);
    void api
      .deriveSuperGameSeries(gameId)
      .then((result) => {
        if (result.error !== undefined || result.data === undefined) {
          showToast({
            kind: 'error',
            text: superGameSeriesErrorMessage(
              result.error,
              'Nie udało się zakolejkować przeliczania serii.',
            ),
          });
          return;
        }
        setGeneration(result.data.superGameState);
        showToast({ kind: 'success', text: deriveResultMessage(result.data) });
      })
      .catch(() =>
        showToast({
          kind: 'error',
          text: 'Połączenie z lokalnym Admin API zostało przerwane.',
        }),
      )
      .finally(() => setDeriving(false));
  }

  function openSeries(id: string) {
    onSeriesChange(id);
  }

  function closeSeries() {
    onSeriesChange(null);
  }

  const banner = superGameStateBanner(generation);

  return (
    <section
      aria-label="Supergry"
      className={styles.workspace}
      data-testid="super-game-series-workspace"
    >
      <header className={styles.header}>
        <div>
          <p className="eyebrow">Supergry</p>
          <h3>Serie supergry</h3>
          <p>
            Serie są wyprowadzane z pociętych plansz. Super symbol widać tylko
            na zdjęciach (złota ramka), więc wybiera go operator.
          </p>
        </div>
        <button
          className="primaryButton"
          disabled={deriving}
          onClick={derive}
          type="button"
        >
          {deriving ? 'Kolejkuję…' : 'Przelicz serie'}
        </button>
      </header>

      {banner !== null ? (
        <p className={styles.banner} role="status">
          {banner}
        </p>
      ) : null}

      {symbolsError !== null ? (
        <div className={styles.error} role="alert">
          <p>{symbolsError}</p>
          <button
            className="secondaryButton"
            onClick={() => setSymbolsToken((token) => token + 1)}
            type="button"
          >
            Spróbuj ponownie
          </button>
        </div>
      ) : null}

      {seriesId !== null ? (
        <SuperGameSeriesPanel
          client={viewClient}
          filters={filters}
          gameId={gameId}
          onBack={closeSeries}
          onBoardEdited={reloadList}
          onSeriesChange={openSeries}
          onSeriesLoaded={(series) =>
            setList((state) => replaceSeriesInList(state, series))
          }
          onSeriesSaved={reloadList}
          onSuperGameStateChange={setGeneration}
          refreshToken={viewToken}
          rulesVersionId={rules.loaded ? rules.versionId : undefined}
          rulesVersions={rules.options}
          seriesId={seriesId}
          symbols={symbols}
        />
      ) : (
        <SeriesList
          list={list}
          onChangeFilters={changeFilters}
          onLoadMore={loadMore}
          onOpen={openSeries}
          onReload={() => {
            // The list refresh also retries a failed symbol catalog.
            if (symbolsError !== null) setSymbolsToken((token) => token + 1);
            reloadList();
          }}
          symbols={symbols}
        />
      )}

      {toast !== null ? (
        <p
          className={`${styles.toast} ${
            toast.kind === 'success' ? styles.toastSuccess : styles.toastError
          }`}
          role="status"
        >
          {toast.text}
        </p>
      ) : null}
    </section>
  );
}

function SeriesList({
  list,
  onChangeFilters,
  onLoadMore,
  onOpen,
  onReload,
  symbols,
}: {
  readonly list: ReturnType<typeof createSeriesListState>;
  readonly onChangeFilters: (filters: SeriesFilters) => void;
  readonly onLoadMore: () => void;
  readonly onOpen: (seriesId: string) => void;
  readonly onReload: () => void;
  readonly symbols: readonly SymbolResponse[];
}) {
  const { filters } = list;
  const range = seriesBoardRange(filters);
  const [fromText, setFromText] = useState(
    range.from === null ? '' : String(range.from),
  );
  const [toText, setToText] = useState(
    range.to === null ? '' : String(range.to),
  );
  const [rangeError, setRangeError] = useState<string | null>(null);
  const rangeLabel = seriesBoardRangeLabel(filters);

  function applyRange() {
    const parsed = parseSeriesBoardRange(fromText, toText);
    if (!parsed.ok) {
      setRangeError(parsed.message);
      return;
    }
    setRangeError(null);
    onChangeFilters({
      ...filters,
      fromSequence: parsed.range.from,
      toSequence: parsed.range.to,
    });
  }

  function clearRange() {
    setFromText('');
    setToText('');
    setRangeError(null);
    onChangeFilters({ ...filters, fromSequence: null, toSequence: null });
  }

  return (
    <>
      <div className={styles.toolbar}>
        <div className={styles.counter} data-testid="undefined-series-count">
          <strong>{undefinedSeriesCountLabel(list.counts)}</strong>
          <span>{seriesCountsCaption(list.counts)}</span>
        </div>
        <button className="secondaryButton" onClick={onReload} type="button">
          Odśwież listę
        </button>
        <div className={styles.filters}>
          <label>
            <span>Kompletność</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  completeness: event.currentTarget.value as CompletenessFilter,
                })
              }
              value={filters.completeness}
            >
              {COMPLETENESS_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Wiarygodność przebiegu</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  runVerification: event.currentTarget
                    .value as RunVerificationFilter,
                })
              }
              value={filters.runVerification}
            >
              {RUN_VERIFICATION_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span>Super symbol</span>
            <select
              onChange={(event) =>
                onChangeFilters({
                  ...filters,
                  defined: event.currentTarget.value as DefinedFilter,
                })
              }
              value={filters.defined}
            >
              {DEFINED_FILTER_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>

      <form
        aria-label="Zakres plansz"
        className={styles.range}
        onSubmit={(event) => {
          event.preventDefault();
          applyRange();
        }}
      >
        <label>
          <span>Plansze od</span>
          <input
            inputMode="numeric"
            onChange={(event) => setFromText(event.currentTarget.value)}
            placeholder="1"
            value={fromText}
          />
        </label>
        <label>
          <span>do</span>
          <input
            inputMode="numeric"
            onChange={(event) => setToText(event.currentTarget.value)}
            placeholder="bez końca"
            value={toText}
          />
        </label>
        <button className="secondaryButton" type="submit">
          Zastosuj zakres
        </button>
        {rangeLabel !== null ? (
          <>
            <button
              className="secondaryButton"
              onClick={clearRange}
              type="button"
            >
              Wyczyść zakres
            </button>
            <span className={styles.rangeActive} data-testid="board-range">
              Zakres triggera: {rangeLabel}
            </span>
          </>
        ) : (
          <span className={styles.hint}>
            Zakres dotyczy numeru planszy wyzwalającej serii.
          </span>
        )}
      </form>
      {rangeError !== null ? (
        <p className={styles.error} role="alert">
          {rangeError}
        </p>
      ) : null}

      {list.error !== null ? (
        <p className={styles.error} role="alert">
          {list.error}
        </p>
      ) : null}

      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Wyzwalacz</th>
              <th>Pozycje</th>
              <th>Długość</th>
              <th>Retriggery</th>
              <th>Oznaczenia</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {list.items.map((series) => (
              <tr key={series.id}>
                <td>#{series.triggerSequenceNumber}</td>
                <td>{seriesRangeLabel(series)}</td>
                <td>{series.length}</td>
                <td>{series.retriggerSequenceNumbers.length}</td>
                <td>
                  <SeriesBadges series={series} symbols={symbols} />
                </td>
                <td>
                  <button
                    className="secondaryButton"
                    onClick={() => onOpen(series.id)}
                    type="button"
                  >
                    Otwórz
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {list.status === 'loading' && list.items.length === 0 ? (
          <p className={styles.empty}>Wczytuję serie…</p>
        ) : null}
        {list.status !== 'loading' && list.items.length === 0 ? (
          <p className={styles.empty}>
            Brak serii dla wybranych filtrów. Użyj „Przelicz serie”, jeśli
            plansze zostały dodane lub zmienione.
          </p>
        ) : null}
      </div>

      <footer className={styles.listFooter}>
        <span>Wczytano: {list.items.length}</span>
        {list.nextCursor !== null ? (
          <button
            className="secondaryButton"
            disabled={list.status === 'loading'}
            onClick={onLoadMore}
            type="button"
          >
            {list.status === 'loading'
              ? 'Wczytuję…'
              : list.status === 'error'
                ? 'Ponów wczytanie'
                : 'Wczytaj kolejne'}
          </button>
        ) : null}
      </footer>
    </>
  );
}
