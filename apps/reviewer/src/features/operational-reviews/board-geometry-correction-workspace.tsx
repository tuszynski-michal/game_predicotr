'use client';

import type {
  AdminApiClient,
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import {
  CorrectionGridProposals,
  type CorrectionGridProposalsClient,
} from './correction-grid-proposals';

import { apiErrorMessage } from '../catalog/catalog-api-error';

import {
  type BoardGeometryCorrectionTarget,
  deferredBoardGeometryTarget,
  reportedBoardGeometryTarget,
} from './board-geometry-correction-target';
import {
  BoardGeometryCorrectionEditor,
  type CorrectionSymbol,
} from './deferred-board-cell-geometry-editor';
import {
  GeometryCorrectionHistory,
  type GeometryCorrectionHistoryClient,
} from './geometry-correction-history';
import {
  type BoardRejectionClient,
  rejectDeferredSlot,
  rejectReviewItem,
} from './board-rejection-actions.ts';
import type { BoardRejectionRequest } from './board-rejection-state.ts';
import { RejectBoardControl } from './reject-board-control';
import { buildOperationalReviewSymbolShortcuts } from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';
type PageAnchor = {
  readonly page: ImageGridReviewPageResponse;
  readonly afterCursor: string | undefined;
};
type PageLoadOptions = {
  readonly preserveNotice?: boolean;
  readonly resetHistory?: boolean;
  readonly skipSavedSlot?: ImageGridReviewItemResponse;
  readonly history?: readonly PageAnchor[];
};

export type BoardGeometryCorrectionClient = CorrectionGridProposalsClient &
  GeometryCorrectionHistoryClient &
  BoardRejectionClient &
  Pick<
    AdminApiClient,
    | 'createImageGridReviewGeometryRevision'
    | 'getImageGridReviewCorrectionSymbols'
    | 'getPendingBoardCellGeometryCorrectionContext'
    | 'imageGridReviewSourceAssetUrl'
    | 'listImageGridReviews'
    | 'listPendingBoardCellGeometry'
    | 'listSymbols'
    | 'previewImageGridReviewGeometry'
    | 'previewPendingBoardCellGeometryCorrection'
    | 'previewPendingBoardCellGeometrySymbols'
    | 'resolvePendingBoardCellGeometryManually'
  >;

/**
 * The single manual grid-correction screen (D-462, TASK-0726): one board and
 * its grid at a time, from one queue of deferred geometries and boards with a
 * `Zła siatka` report. Saving the geometry finishes the correction and moves
 * on; there is no board or photo approval here. Symbols are approved only
 * for the cells the operator assigns on the preview (D-488).
 */
export function BoardGeometryCorrectionWorkspace({
  api,
  apiBaseUrl,
  gameId,
  importJobId,
  keyboardEnabled = true,
  reviewAll = false,
}: {
  readonly api: BoardGeometryCorrectionClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  /** Optional: without it the queue spans the whole game (TASK-0962). */
  readonly importJobId?: string | undefined;
  /** False while a sibling tab is shown; keeps the editor mounted. */
  readonly keyboardEnabled?: boolean;
  /** Explicit human check of ordinary boards, using the same guarded editor. */
  readonly reviewAll?: boolean;
}) {
  const [proposalEditing, setProposalEditing] = useState(false);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [page, setPage] = useState<ImageGridReviewPageResponse | null>(null);
  const [history, setHistory] = useState<readonly PageAnchor[]>([]);
  const [currentPageCursor, setCurrentPageCursor] = useState<
    string | undefined
  >();
  const lastPageRequest = useRef<{
    afterCursor: string | undefined;
    options: PageLoadOptions;
  }>({ afterCursor: undefined, options: {} });
  const [pageState, setPageState] = useState<LoadState>('loading');
  const [reachedReviewEnd, setReachedReviewEnd] = useState(false);
  const [pageError, setPageError] = useState('');
  const [notice, setNotice] = useState('');
  const [symbols, setSymbols] = useState<readonly CorrectionSymbol[]>([]);
  const mounted = useRef(true);
  const requestId = useRef(0);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const scopeKey = JSON.stringify([
    gameId,
    importJobId,
    reviewAll,
    sourceFilter,
  ]);
  const activeScopeRef = useRef(scopeKey);
  useLayoutEffect(() => {
    activeScopeRef.current = scopeKey;
  }, [scopeKey]);

  useEffect(() => {
    let active = true;
    // Without the catalogue the screen still corrects grids; only the symbol
    // picker stays hidden.
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (!active || result.error !== undefined || !result.data) return;
        // The keys are the ones of the symbol verification screen: 1-9, 0,
        // then letters, in the catalogue order of "Zarządzanie grami".
        setSymbols(
          buildOperationalReviewSymbolShortcuts(result.data).map(
            ({ key, symbol }) => ({
              id: symbol.id,
              label: symbol.namePl ?? symbol.name,
              shortcut: key,
            }),
          ),
        );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [api, gameId]);

  const loadPage = useCallback(
    async (afterCursor: string | undefined, options: PageLoadOptions = {}) => {
      if (!mounted.current || activeScopeRef.current !== scopeKey) return false;
      const currentRequest = ++requestId.current;
      lastPageRequest.current = { afterCursor, options };
      setPageState('loading');
      setReachedReviewEnd(false);
      setPageError('');
      if (!options.preserveNotice) setNotice('');
      let result: Awaited<
        ReturnType<BoardGeometryCorrectionClient['listImageGridReviews']>
      > | null = null;
      let cursor = afterCursor;
      // Resolving a deferred slot may replace its UUID with a review UUID.
      // Skip that one logical position without skipping another source that
      // happens to have the same sequence number. Never poll indefinitely.
      for (let attempt = 0; attempt < 2; attempt += 1) {
        try {
          result = await api.listImageGridReviews({
            gameId,
            ...(reviewAll && sourceFilter
              ? { sourceImageId: sourceFilter }
              : {}),
            ...(importJobId === undefined ? {} : { importJobId }),
            counts: reviewAll ? 'none' : 'correction',
            limit: 1,
            view: reviewAll ? 'all' : 'correction',
            ...(cursor === undefined ? {} : { afterCursor: cursor }),
          });
        } catch {
          result = null;
        }
        if (
          !mounted.current ||
          currentRequest !== requestId.current ||
          activeScopeRef.current !== scopeKey
        )
          return false;
        if (
          result === null ||
          result.error !== undefined ||
          result.data === undefined
        )
          break;
        const saved = options.skipSavedSlot;
        const next = result.data.items[0];
        if (
          saved === undefined ||
          next === undefined ||
          saved.importJobId !== next.importJobId ||
          saved.sourceImageId !== next.sourceImageId ||
          saved.positionIndex !== next.positionIndex
        )
          break;
        if (result.data.nextCursor == null) {
          result = {
            ...result,
            data: {
              ...result.data,
              items: [],
              nextCursor: null,
              previousCursor: null,
            },
          };
          break;
        }
        if (attempt === 1) {
          setPageState('error');
          setPageError(
            'Kolejka ponownie zwróciła zapisaną pozycję. Odśwież zakres.',
          );
          return false;
        }
        cursor = result.data.nextCursor;
      }
      if (
        !mounted.current ||
        currentRequest !== requestId.current ||
        activeScopeRef.current !== scopeKey
      )
        return false;
      if (result === null) {
        setPageState('error');
        setPageError('Połączenie z lokalnym Admin API zostało przerwane.');
        return false;
      }
      if (result.error !== undefined || result.data === undefined) {
        setPageState('error');
        setPageError(
          apiErrorMessage(
            result.error,
            'Nie udało się pobrać kolejki korekty cięcia siatki.',
          ),
        );
        return false;
      }
      if (options.history !== undefined) setHistory(options.history);
      else if (options.resetHistory) setHistory([]);
      setCurrentPageCursor(cursor);
      setPage(result.data);
      setReachedReviewEnd(
        options.skipSavedSlot !== undefined && result.data.items.length === 0,
      );
      setPageState('ready');
      return true;
    },
    [api, gameId, importJobId, reviewAll, sourceFilter, scopeKey],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void loadPage(undefined, { resetHistory: true }));
    return () => {
      mounted.current = false;
    };
  }, [loadPage]);

  const item = page?.items[0] ?? null;
  // TASK-0969 x TASK-0962: corrections are listed per import. Without a chosen
  // import (game scope) the history follows the import of the board on screen
  // and keeps the last one after the queue empties, so the last save stays
  // revertable.
  const [lastItemImportJobId, setLastItemImportJobId] = useState<
    string | undefined
  >(undefined);
  const itemImportJobId = item?.importJobId;
  if (itemImportJobId && itemImportJobId !== lastItemImportJobId) {
    setLastItemImportJobId(itemImportJobId);
  }
  const historyImportJobId = importJobId ?? lastItemImportJobId;
  const remaining = page?.counts.correction ?? 0;
  const target = useBoardCorrectionTarget(api, apiBaseUrl, item);
  const targetKeyRef = useRef<string | null>(null);
  const hasNextRef = useRef(false);
  const reloadedForConflictRef = useRef<string | null>(null);
  useLayoutEffect(() => {
    targetKeyRef.current = target?.key ?? null;
    hasNextRef.current = page?.nextCursor != null;
  }, [page?.nextCursor, target?.key]);

  async function showNext() {
    if (page?.nextCursor === null || page?.nextCursor === undefined) return;
    await loadPage(page.nextCursor, {
      history: [...history, { page, afterCursor: currentPageCursor }],
    });
  }

  async function showPrevious() {
    const previous = history.at(-1);
    if (previous === undefined) return;
    if (reviewAll) {
      await loadPage(previous.afterCursor, { history: history.slice(0, -1) });
      return;
    }
    requestId.current += 1;
    setHistory((current) => current.slice(0, -1));
    setPage(previous.page);
    setCurrentPageCursor(previous.afterCursor);
    setPageState('ready');
    setPageError('');
    setNotice('');
  }

  const handleSaved = useCallback(
    async (reviewItemId: string | null, savedNotice?: string) => {
      if (
        !mounted.current ||
        activeScopeRef.current !== scopeKey ||
        targetKeyRef.current !== target?.key
      )
        return;
      reloadedForConflictRef.current = null;
      const deferred = targetKeyRef.current?.startsWith('deferred:') === true;
      setNotice(
        savedNotice ??
          (reviewItemId === null
            ? 'Plansza została już rozwiązana przez inną operację. Kolejka została odświeżona.'
            : deferred
              ? 'Siatka zapisana. Nowa plansza trafiła do Weryfikacji symboli.'
              : 'Siatka zapisana. Pola ze zmienionym wycinkiem wróciły do Weryfikacji symboli.'),
      );
      setHistoryRefresh((value) => value + 1);
      if (reviewAll && page !== null) {
        const saved = page.items[0];
        const nextHistory = [
          ...history,
          { page, afterCursor: currentPageCursor },
        ];
        if (page.nextCursor == null || saved === undefined) {
          requestId.current += 1;
          setHistory(nextHistory);
          setPage({
            ...page,
            items: [],
            nextCursor: null,
            previousCursor: null,
          });
          setPageState('ready');
          setPageError('');
          setReachedReviewEnd(true);
          return;
        }
        await loadPage(page.nextCursor, {
          preserveNotice: true,
          history: nextHistory,
          skipSavedSlot: saved,
        });
      } else {
        // Correction entries leave their queue when saved.
        await loadPage(undefined, { preserveNotice: true, resetHistory: true });
      }
    },
    [
      loadPage,
      page,
      reviewAll,
      scopeKey,
      target?.key,
      history,
      currentPageCursor,
    ],
  );

  // TASK-0970: a rejected slot or board leaves the queue; the history lists
  // the rejection so it can be undone until a replacement owns the sequence.
  const handleRejected = useCallback(async () => {
    setNotice(
      'Plansza została odrzucona. Zdjęcie czeka na zdjęcie zastępcze albo wyjątek operatora.',
    );
    setHistoryRefresh((value) => value + 1);
    await loadPage(reviewAll ? currentPageCursor : undefined, {
      preserveNotice: true,
      resetHistory: !reviewAll,
    });
  }, [loadPage, reviewAll, currentPageCursor]);

  const handleRejectionRefused = useCallback(
    async (message: string) => {
      setNotice(message);
      setHistoryRefresh((value) => value + 1);
      await loadPage(reviewAll ? currentPageCursor : undefined, {
        preserveNotice: true,
        resetHistory: !reviewAll,
      });
    },
    [loadPage, reviewAll, currentPageCursor],
  );

  const submitRejection = useCallback(
    (request: BoardRejectionRequest) => {
      if (item === null) throw new Error('No board to reject.');
      const scope = { gameId: item.gameId, importJobId: item.importJobId };
      if (item.slotKind === 'deferred_geometry' && item.pendingGeometryId) {
        return rejectDeferredSlot(
          api,
          scope,
          {
            expectedGeometryRevision: item.geometryRevision,
            pendingGeometryId: item.pendingGeometryId,
          },
          request,
        );
      }
      if (item.reviewItemId === null) {
        throw new Error('The board has no review item.');
      }
      return rejectReviewItem(
        api,
        scope,
        {
          geometryRevision: item.geometryRevision,
          resolutionRevision: item.resolutionRevision,
          reviewItemId: item.reviewItemId,
        },
        request,
      );
    },
    [api, item],
  );

  const handleReverted = useCallback(async () => {
    await loadPage(reviewAll ? currentPageCursor : undefined, {
      preserveNotice: true,
      resetHistory: !reviewAll,
    });
  }, [loadPage, reviewAll, currentPageCursor]);

  const handleConflict = useCallback(
    async (message: string) => {
      const key = targetKeyRef.current;
      if (key !== null && reloadedForConflictRef.current === key) {
        // The reload returned the same board version: do not loop, keep the
        // error visible and let the operator skip the board.
        setNotice(
          `${message} Kolejka nadal wskazuje tę planszę — ${
            hasNextRef.current ? 'pomiń ją na razie.' : 'wróć do niej później.'
          }`,
        );
        return;
      }
      reloadedForConflictRef.current = key;
      setNotice(`${message} Wczytano aktualny stan kolejki.`);
      await loadPage(reviewAll ? currentPageCursor : undefined, {
        preserveNotice: true,
        resetHistory: !reviewAll,
      });
    },
    [loadPage, reviewAll, currentPageCursor],
  );

  return (
    <section
      aria-label="Korekta cięcia siatki"
      className="deferredGeometryQueue"
    >
      <header className="deferredGeometryHeader">
        <div>
          <span className="eyebrow">Jedna plansza naraz</span>
          <h2>{reviewAll ? 'Geometria zdjęć' : 'Korekta cięcia siatki'}</h2>
          <p>
            {reviewAll ? (
              'Sprawdź geometrię wszystkich plansz wybranych pełnych zdjęć, także dobrych propozycji. Zapisz sprawdzoną siatkę, nawet bez zmiany punktów. To ludzka weryfikacja geometrii; symbole zatwierdza się osobno.'
            ) : (
              <>
                Plansze odrzucone przez algorytm oraz plansze zgłoszone jako
                „Zła siatka”. Ustaw cztery narożniki, zapisz i przejdź dalej.
                Zapis zatwierdza tylko symbole, które wskażesz na kafelkach
                podglądu.
              </>
            )}
          </p>
        </div>
      </header>

      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}

      {pageState === 'loading' ? (
        <CorrectionState text="Pobieram jedną planszę do korekty." />
      ) : pageState === 'error' ? (
        <CorrectionState
          action={() => {
            const request = lastPageRequest.current;
            void loadPage(request.afterCursor, request.options);
          }}
          error
          text={pageError}
        />
      ) : item === null || target === null ? (
        <div className="deferredGeometryComplete">
          <h3>
            {reviewAll && reachedReviewEnd
              ? 'Koniec zakresu'
              : reviewAll
                ? 'Brak plansz w tym zakresie'
                : 'Brak plansz do korekty'}
          </h3>
          <p>
            {reviewAll && reachedReviewEnd
              ? 'Zapisano ostatnią planszę w tym zakresie. Możesz wrócić do początku.'
              : reviewAll
                ? 'Wybierz istniejący import z opisanymi źródłami.'
                : 'W tym zakresie nie ma plansz odrzuconych przez algorytm ani zgłoszonych jako „Zła siatka”.'}
          </p>
          {reviewAll && reachedReviewEnd ? (
            <button
              className="secondaryButton"
              type="button"
              onClick={() => void loadPage(undefined, { resetHistory: true })}
            >
              Od początku
            </button>
          ) : null}
          {reviewAll && history.length > 0 ? (
            <button
              className="secondaryButton"
              type="button"
              onClick={() => void showPrevious()}
            >
              ← Poprzednia
            </button>
          ) : null}
          {reviewAll && sourceFilter ? (
            <button
              className="secondaryButton"
              type="button"
              onClick={() => setSourceFilter(null)}
            >
              Wszystkie zdjęcia
            </button>
          ) : null}
        </div>
      ) : (
        <>
          <div className="boardRejectionBar">
            <RejectBoardControl<unknown>
              consequences={rejectionConsequences(item)}
              key={target.key}
              onDone={handleRejected}
              onRefused={handleRejectionRefused}
              subject={`sekwencja ${item.sequenceNumber}, pozycja ${item.positionIndex}`}
              submit={submitRejection}
            />
          </div>
          <CorrectionGridProposals
            key={`proposals:${target.key}`}
            api={api}
            apiBaseUrl={apiBaseUrl}
            item={item}
            onEditingChange={setProposalEditing}
            onChanged={() => {
              void handleSaved(
                item.reviewItemId,
                'Przyjęto propozycję siatki. Zatwierdzone punkty zapisano; odświeżono kolejkę.',
              );
            }}
            onRejected={() => {
              setNotice(
                'Odrzucono propozycję. Zgłoszenie siatki pozostaje otwarte; możesz poprawić tę planszę ręcznie.',
              );
              void loadPage(currentPageCursor, {
                preserveNotice: true,
              });
            }}
            onReloadQueue={() => {
              setNotice(
                'Odświeżono bieżącą kolejkę. Wczytano aktualną wersję planszy.',
              );
              void loadPage(currentPageCursor, {
                preserveNotice: true,
              });
            }}
          />
          <BoardGeometryCorrectionEditor
            viewportControls
            key={target.key}
            keyboardEnabled={keyboardEnabled && !proposalEditing}
            onConflict={handleConflict}
            onSaved={handleSaved}
            symbols={symbols}
            target={target}
          />
          {reviewAll ? (
            <div className="deferredGeometryNavigation">
              <button
                className="secondaryButton"
                type="button"
                onClick={() =>
                  setSourceFilter(sourceFilter ? null : item.sourceImageId)
                }
              >
                {sourceFilter
                  ? 'Wszystkie zdjęcia'
                  : 'Sprawdź wszystkie plansze tego zdjęcia'}
              </button>
              <span>
                Pozycja na zdjęciu: {item.positionIndex + 1} z 9. Zapis i
                przyciski nawigacji przechodzą przez istniejący zakres.
              </span>
            </div>
          ) : null}
          {reviewAll ? (
            <p role="status">
              Zapisana geometria nie potwierdza ludzkiej weryfikacji. Sprawdź i
              zapisz ją ręcznie. Pełne zdjęcie wymaga sprawdzenia wszystkich
              jego plansz; symbol nie jest etykietą geometrii.
            </p>
          ) : null}
          <footer className="deferredGeometryNavigation">
            <button
              className="secondaryButton"
              disabled={history.length === 0}
              onClick={showPrevious}
              type="button"
            >
              ← Poprzednia
            </button>
            <span>
              {reviewAll ? 'Plansza' : 'Do korekty:'}{' '}
              <strong>
                {reviewAll
                  ? item.sequenceNumber
                  : remaining.toLocaleString('pl-PL')}
              </strong>
            </span>
            {page?.nextCursor == null ? (
              <button
                className="secondaryButton"
                disabled={!reviewAll && history.length === 0}
                onClick={() => void loadPage(undefined, { resetHistory: true })}
                type="button"
              >
                Od początku
              </button>
            ) : (
              <button
                className="secondaryButton"
                onClick={() => void showNext()}
                type="button"
              >
                Pomiń na razie →
              </button>
            )}
          </footer>
        </>
      )}
      {historyImportJobId === undefined ? null : (
        <GeometryCorrectionHistory
          api={api}
          gameId={gameId}
          importJobId={historyImportJobId}
          onReverted={handleReverted}
          refreshToken={historyRefresh}
        />
      )}
    </section>
  );
}

/** What the confirmation says the rejection does (plan: W7, W8, risks). */
function rejectionConsequences(
  item: ImageGridReviewItemResponse,
): readonly string[] {
  const common = [
    'Zdjęcie zostaje niekompletne i czeka na zdjęcie zastępcze albo wyjątek operatora; pozostałe plansze tego zdjęcia nie są cięte na symbole.',
    'Odrzucenie można cofnąć w sekcji „Ostatnie korekty”, dopóki sekwencji nie przejmie inna plansza.',
  ];
  return item.slotKind === 'deferred_geometry'
    ? [
        'Slot zniknie z kolejki korekty cięcia siatki i nie powstanie z niego plansza.',
        ...common,
      ]
    : [
        'Plansza wypadnie z kolejki korekty, z weryfikacji symboli i z wyszukiwarki. Weryfikacje symboli już zapisane na niej zostają w historii.',
        'Kanonicznego właściciela sekwencji nie można odrzucić.',
        ...common,
      ];
}

function useBoardCorrectionTarget(
  api: BoardGeometryCorrectionClient,
  apiBaseUrl: string,
  item: ImageGridReviewItemResponse | null,
): BoardGeometryCorrectionTarget | null {
  return useMemo(() => {
    if (item === null) return null;
    if (item.slotKind === 'deferred_geometry' && item.pendingGeometryId) {
      return deferredBoardGeometryTarget({
        api,
        apiBaseUrl,
        pendingId: item.pendingGeometryId,
        scope: { gameId: item.gameId, importJobId: item.importJobId },
        symbolsApi: api,
      });
    }
    return reportedBoardGeometryTarget({ api, item, symbolsApi: api });
  }, [api, apiBaseUrl, item]);
}

function CorrectionState({
  action,
  error = false,
  text,
}: {
  readonly action?: () => void;
  readonly error?: boolean;
  readonly text: string;
}) {
  return (
    <div className={error ? 'emptyState errorState' : 'emptyState'}>
      <h3>{error ? 'Nie udało się wczytać korekty' : 'Wczytywanie korekty'}</h3>
      <p>{text}</p>
      {action ? (
        <button className="secondaryButton" onClick={action} type="button">
          Spróbuj ponownie
        </button>
      ) : null}
    </div>
  );
}
