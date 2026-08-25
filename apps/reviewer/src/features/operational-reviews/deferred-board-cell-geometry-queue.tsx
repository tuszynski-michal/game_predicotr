'use client';

import type { BoardCellGeometryPendingPageResponse } from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  type DeferredBoardCellGeometryClient,
  loadDeferredBoardCellGeometryPage,
} from './deferred-board-cell-geometry-actions';
import { DeferredBoardCellGeometryEditor } from './deferred-board-cell-geometry-editor';

type LoadState = 'error' | 'loading' | 'ready';

interface DeferredBoardCellGeometryQueueProps {
  readonly active: boolean;
  readonly api: DeferredBoardCellGeometryClient;
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly importJobId: string;
  readonly onActivate: () => void;
  readonly onClose: () => void;
  readonly onOrdinaryQueueChanged: () => void;
}

export function DeferredBoardCellGeometryQueue({
  active,
  api,
  apiBaseUrl,
  gameId,
  importJobId,
  onActivate,
  onClose,
  onOrdinaryQueueChanged,
}: DeferredBoardCellGeometryQueueProps) {
  const [page, setPage] = useState<BoardCellGeometryPendingPageResponse | null>(
    null,
  );
  const [history, setHistory] = useState<
    readonly BoardCellGeometryPendingPageResponse[]
  >([]);
  const [pageState, setPageState] = useState<LoadState>('loading');
  const [pageError, setPageError] = useState('');
  const [notice, setNotice] = useState('');
  const mounted = useRef(true);
  const requestId = useRef(0);
  const scope = useMemo(() => ({ gameId, importJobId }), [gameId, importJobId]);

  const loadPage = useCallback(
    async (
      cursor: string | undefined,
      options: {
        readonly preserveNotice?: boolean;
        readonly resetHistory?: boolean;
      } = {},
    ) => {
      const currentRequest = ++requestId.current;
      setPageState('loading');
      setPageError('');
      if (!options.preserveNotice) setNotice('');
      const result = await loadDeferredBoardCellGeometryPage(
        api,
        scope,
        cursor,
      );
      if (!mounted.current || currentRequest !== requestId.current)
        return false;
      if (!result.ok) {
        setPageState('error');
        setPageError(result.error);
        return false;
      }
      if (options.resetHistory) setHistory([]);
      setPage(result.page);
      setPageState('ready');
      return true;
    },
    [api, scope],
  );

  useEffect(() => {
    mounted.current = true;
    queueMicrotask(() => void loadPage(undefined, { resetHistory: true }));
    return () => {
      mounted.current = false;
    };
  }, [loadPage]);

  const item = page?.items[0] ?? null;
  const pendingCount = page?.counts.pending ?? 0;

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

  const handleMaterialized = useCallback(
    async (reviewItemId: string | null) => {
      setNotice(
        reviewItemId === null
          ? 'Plansza została już rozwiązana przez inną operację. Kolejka została odświeżona.'
          : 'Geometria została zapisana. Plansza trafiła do zwykłego zatwierdzania symboli.',
      );
      onOrdinaryQueueChanged();
      await loadPage(undefined, { preserveNotice: true, resetHistory: true });
    },
    [loadPage, onOrdinaryQueueChanged],
  );

  const handleConflict = useCallback(
    async (message: string) => {
      setNotice(`${message} Wczytano aktualny stan kolejki.`);
      await loadPage(undefined, { preserveNotice: true, resetHistory: true });
    },
    [loadPage],
  );

  if (!active) {
    return (
      <section className="deferredGeometryEntry" aria-label="Korekta geometrii">
        <div>
          <span className="eyebrow">Końcowy fallback</span>
          <strong>Korekta siatki symboli</strong>
          <p>
            {pageState === 'loading'
              ? 'Sprawdzam odroczone plansze…'
              : pageState === 'error'
                ? pageError
                : pendingCount === 0
                  ? 'Ten import nie ma plansz wymagających ręcznego ustawienia siatki.'
                  : `${pendingCount.toLocaleString('pl-PL')} plansz czeka na ustawienie czterech narożników.`}
          </p>
        </div>
        <button
          className="secondaryButton"
          disabled={pageState !== 'ready' || pendingCount === 0}
          onClick={onActivate}
          type="button"
        >
          Otwórz korektę siatki
        </button>
      </section>
    );
  }

  return (
    <section className="deferredGeometryQueue">
      <header className="deferredGeometryHeader">
        <div>
          <span className="eyebrow">Końcowy fallback</span>
          <h2>Korekta geometrii symboli 5 × 3</h2>
          <p>
            Ustaw cztery narożniki zewnętrznej siatki. Po zapisie plansza trafi
            do tej samej kolejki zatwierdzania symboli co pozostałe plansze.
          </p>
        </div>
        <button className="secondaryButton" onClick={onClose} type="button">
          Wróć do zatwierdzania
        </button>
      </header>

      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}

      {pageState === 'loading' ? (
        <DeferredGeometryState text="Pobieram jedną odroczoną planszę." />
      ) : pageState === 'error' ? (
        <DeferredGeometryState
          action={() => void loadPage(undefined, { resetHistory: true })}
          error
          text={pageError}
        />
      ) : item === null ? (
        <div className="deferredGeometryComplete">
          <h3>Brak odroczonych plansz</h3>
          <p>
            Wszystkie wyjątki geometrii zostały rozwiązane albo supersedowane.
          </p>
          <button className="primaryButton" onClick={onClose} type="button">
            Przejdź do zatwierdzania symboli
          </button>
        </div>
      ) : (
        <>
          <DeferredBoardCellGeometryEditor
            api={api}
            apiBaseUrl={apiBaseUrl}
            itemId={item.id}
            key={`${item.id}:${item.expectedGeometryRevision}:${item.expectedReviewResolutionRevision}`}
            onConflict={handleConflict}
            onMaterialized={handleMaterialized}
            scope={scope}
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
              Do korekty:{' '}
              <strong>{pendingCount.toLocaleString('pl-PL')}</strong>
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

function DeferredGeometryState({
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
