'use client';

import type {
  AdminApiClient,
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

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
import { orderOperationalReviewSymbols } from './operational-review-state';

type LoadState = 'error' | 'loading' | 'ready';

export type BoardGeometryCorrectionClient = Pick<
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
}: {
  readonly api: BoardGeometryCorrectionClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly importJobId: string;
}) {
  const [page, setPage] = useState<ImageGridReviewPageResponse | null>(null);
  const [history, setHistory] = useState<
    readonly ImageGridReviewPageResponse[]
  >([]);
  const [pageState, setPageState] = useState<LoadState>('loading');
  const [pageError, setPageError] = useState('');
  const [notice, setNotice] = useState('');
  const [symbols, setSymbols] = useState<readonly CorrectionSymbol[]>([]);
  const mounted = useRef(true);
  const requestId = useRef(0);

  useEffect(() => {
    let active = true;
    // Without the catalogue the screen still corrects grids; only the symbol
    // picker stays hidden.
    void api
      .listSymbols(gameId)
      .then((result) => {
        if (!active || result.error !== undefined || !result.data) return;
        setSymbols(
          orderOperationalReviewSymbols(result.data).map((symbol) => ({
            id: symbol.id,
            label: symbol.namePl ?? symbol.name,
          })),
        );
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [api, gameId]);

  const loadPage = useCallback(
    async (
      afterCursor: string | undefined,
      options: {
        readonly preserveNotice?: boolean;
        readonly resetHistory?: boolean;
      } = {},
    ) => {
      const currentRequest = ++requestId.current;
      setPageState('loading');
      setPageError('');
      if (!options.preserveNotice) setNotice('');
      let result;
      try {
        result = await api.listImageGridReviews({
          gameId,
          importJobId,
          limit: 1,
          view: 'correction',
          ...(afterCursor === undefined ? {} : { afterCursor }),
        });
      } catch {
        result = null;
      }
      if (!mounted.current || currentRequest !== requestId.current)
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
      if (options.resetHistory) setHistory([]);
      setPage(result.data);
      setPageState('ready');
      return true;
    },
    [api, gameId, importJobId],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void loadPage(undefined, { resetHistory: true }));
    return () => {
      mounted.current = false;
    };
  }, [loadPage]);

  const item = page?.items[0] ?? null;
  const remaining = page?.counts.correction ?? 0;
  const target = useBoardCorrectionTarget(api, apiBaseUrl, item);
  const targetKeyRef = useRef<string | null>(null);
  const hasNextRef = useRef(false);
  const reloadedForConflictRef = useRef<string | null>(null);
  useEffect(() => {
    targetKeyRef.current = target?.key ?? null;
    hasNextRef.current = page?.nextCursor != null;
  }, [page, target]);

  async function showNext() {
    if (page?.nextCursor === null || page?.nextCursor === undefined) return;
    const previousPage = page;
    if (await loadPage(page.nextCursor)) {
      setHistory((current) => [...current, previousPage]);
    }
  }

  function showPrevious() {
    const previous = history.at(-1);
    if (previous === undefined) return;
    requestId.current += 1;
    setHistory((current) => current.slice(0, -1));
    setPage(previous);
    setPageState('ready');
    setPageError('');
    setNotice('');
  }

  const handleSaved = useCallback(
    async (reviewItemId: string | null) => {
      reloadedForConflictRef.current = null;
      const deferred = targetKeyRef.current?.startsWith('deferred:') === true;
      setNotice(
        reviewItemId === null
          ? 'Plansza została już rozwiązana przez inną operację. Kolejka została odświeżona.'
          : deferred
            ? 'Siatka zapisana. Nowa plansza trafiła do Weryfikacji symboli.'
            : 'Siatka zapisana. Pola ze zmienionym wycinkiem wróciły do Weryfikacji symboli.',
      );
      // The saved board leaves the queue; the next one is the new first entry.
      await loadPage(undefined, { preserveNotice: true, resetHistory: true });
    },
    [loadPage],
  );

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
      await loadPage(undefined, { preserveNotice: true, resetHistory: true });
    },
    [loadPage],
  );

  return (
    <section
      aria-label="Korekta cięcia siatki"
      className="deferredGeometryQueue"
    >
      <header className="deferredGeometryHeader">
        <div>
          <span className="eyebrow">Jedna plansza naraz</span>
          <h2>Korekta cięcia siatki</h2>
          <p>
            Plansze odrzucone przez algorytm oraz plansze zgłoszone jako „Zła
            siatka”. Ustaw cztery narożniki, zapisz i przejdź dalej. Zapis
            zatwierdza tylko symbole, które wskażesz na kafelkach podglądu.
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
          action={() => void loadPage(undefined, { resetHistory: true })}
          error
          text={pageError}
        />
      ) : item === null || target === null ? (
        <div className="deferredGeometryComplete">
          <h3>Brak plansz do korekty</h3>
          <p>
            Ten import nie ma plansz odrzuconych przez algorytm ani zgłoszonych
            jako „Zła siatka”.
          </p>
        </div>
      ) : (
        <>
          <BoardGeometryCorrectionEditor
            key={target.key}
            onConflict={handleConflict}
            onSaved={handleSaved}
            symbols={symbols}
            target={target}
          />
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
              Do korekty: <strong>{remaining.toLocaleString('pl-PL')}</strong>
            </span>
            {page?.nextCursor == null ? (
              <button
                className="secondaryButton"
                disabled={history.length === 0}
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
    </section>
  );
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
