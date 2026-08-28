'use client';

import type {
  ImageGridReviewPageResponse,
  ImageGridReviewView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  approveGridReview,
  loadGridReviewPage,
  type GridReviewsClient,
} from './grid-review-actions';
import { GridReviewEditor } from './grid-review-editor';
import {
  GRID_REVIEW_VIEWS,
  isGridReviewTypingTarget,
  type GridReviewNavigation,
} from './grid-review-state';

export function GridReviewWorkspace({
  apiBaseUrl,
  client,
  gameId,
  importJobId,
}: {
  readonly apiBaseUrl: string;
  readonly client?: GridReviewsClient;
  readonly gameId: string;
  readonly importJobId: string;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [view, setView] = useState<ImageGridReviewView>('needs_validation');
  const [page, setPage] = useState<ImageGridReviewPageResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const requestId = useRef(0);
  const submitLock = useRef(false);
  const navigationRef = useRef<GridReviewNavigation>({});
  const item = page?.items[0] ?? null;

  const loadPage = useCallback(
    async (navigation: GridReviewNavigation = {}) => {
      const currentRequest = ++requestId.current;
      navigationRef.current = navigation;
      setLoading(true);
      setError('');
      const result = await loadGridReviewPage(api, {
        gameId,
        importJobId,
        navigation,
        view,
      });
      if (currentRequest !== requestId.current) return;
      setLoading(false);
      if (!result.ok) {
        setError(
          result.isConflict
            ? `${result.error} Kolejka zmieniła się — wczytaj aktualną pozycję.`
            : result.error,
        );
        return;
      }
      setPage(result.page);
    },
    [api, gameId, importJobId, view],
  );

  useEffect(() => {
    queueMicrotask(() => void loadPage());
  }, [loadPage]);

  const moveAfterSuccess = useCallback(async () => {
    const nextCursor = page?.nextCursor;
    if (nextCursor !== null && nextCursor !== undefined) {
      await loadPage({ afterCursor: nextCursor });
      return;
    }
    await loadPage();
  }, [loadPage, page?.nextCursor]);

  const approve = useCallback(async () => {
    if (item === null || submitLock.current) return;
    submitLock.current = true;
    setSubmitting(true);
    setError('');
    setNotice('');
    const result = await approveGridReview(api, item);
    if (!result.ok) {
      setSubmitting(false);
      submitLock.current = false;
      setError(
        result.isConflict
          ? `${result.error} Wczytuję aktualną rewizję.`
          : result.error,
      );
      if (result.isConflict) await loadPage(navigationRef.current);
      return;
    }
    setNotice(`Zatwierdzono geometrię planszy ${item.sequenceNumber}.`);
    await moveAfterSuccess();
    setSubmitting(false);
    submitLock.current = false;
  }, [api, item, loadPage, moveAfterSuccess]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (
        event.repeat ||
        isGridReviewTypingTarget(event.target) ||
        document.querySelector('.gridReviewEditor .isEditing') !== null
      ) {
        return;
      }
      if (event.key === 'Enter' || event.key.toLowerCase() === 'f') {
        event.preventDefault();
        void approve();
        return;
      }
      if (event.key === 'ArrowRight' && page?.nextCursor !== null) {
        event.preventDefault();
        void loadPage({ afterCursor: page?.nextCursor ?? undefined });
      }
      if (event.key === 'ArrowLeft' && page?.previousCursor !== null) {
        event.preventDefault();
        void loadPage({ beforeCursor: page?.previousCursor ?? undefined });
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [approve, loadPage, page?.nextCursor, page?.previousCursor]);

  return (
    <div className="gridReviewWorkspace">
      <header className="gridReviewHeader">
        <div>
          <p className="eyebrow">Geometria plansz</p>
          <h1>Zatwierdzanie cięcia siatki</h1>
          <p className="lead">
            Zatwierdź położenie siatki albo popraw cztery narożniki. Symbole są
            weryfikowane w osobnym widoku.
          </p>
        </div>
        {page ? (
          <dl className="gridReviewCounts">
            <div>
              <dt>Do walidacji</dt>
              <dd>{page.counts.needsValidation.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Do poprawy</dt>
              <dd>{page.counts.needsCorrection.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Zatwierdzone</dt>
              <dd>{page.counts.approved.toLocaleString('pl-PL')}</dd>
            </div>
          </dl>
        ) : null}
      </header>

      <nav aria-label="Filtr walidacji siatki" className="gridReviewFilters">
        {GRID_REVIEW_VIEWS.map((option) => (
          <button
            aria-pressed={view === option.value}
            className={view === option.value ? 'isActive' : undefined}
            disabled={submitting}
            key={option.value}
            onClick={() => {
              setNotice('');
              setView(option.value);
            }}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </nav>

      {notice ? (
        <p className="operationalReviewNotice" role="status">
          {notice}
        </p>
      ) : null}
      {error ? (
        <div className="gridReviewError" role="alert">
          <p>{error}</p>
          <button
            className="secondaryButton"
            onClick={() => void loadPage()}
            type="button"
          >
            Wczytaj ponownie
          </button>
        </div>
      ) : null}
      {loading ? (
        <section className="gridReviewState">
          <h2>Wczytywanie siatki</h2>
          <p>Pobieram jeden oryginalny obraz i jego bieżącą geometrię.</p>
        </section>
      ) : item === null ? (
        <section className="gridReviewState">
          <h2>Brak plansz w tym filtrze</h2>
          <p>Wybierz inny filtr albo wróć po zakończeniu kolejnego importu.</p>
        </section>
      ) : (
        <>
          <GridReviewEditor
            api={api}
            item={item}
            key={`${item.reviewItemId}:${item.geometryRevision}`}
            onSaved={() => {
              setNotice(
                `Zapisano i zatwierdzono nową geometrię planszy ${item.sequenceNumber}.`,
              );
              void moveAfterSuccess();
            }}
          />
          <footer className="gridReviewActions">
            <button
              className="secondaryButton"
              disabled={submitting || page?.previousCursor === null}
              onClick={() =>
                void loadPage({
                  beforeCursor: page?.previousCursor ?? undefined,
                })
              }
              type="button"
            >
              ← Poprzednia
            </button>
            <button
              aria-label="Zatwierdź geometrię i przejdź do następnej planszy"
              className="primaryButton gridReviewApprove"
              disabled={submitting || item.state === 'needs_correction'}
              onClick={() => void approve()}
              type="button"
            >
              {submitting ? 'Zatwierdzanie…' : 'Zatwierdź (Enter / F)'}
            </button>
            <button
              className="secondaryButton"
              disabled={submitting || page?.nextCursor === null}
              onClick={() =>
                void loadPage({ afterCursor: page?.nextCursor ?? undefined })
              }
              type="button"
            >
              Następna →
            </button>
          </footer>
        </>
      )}
    </div>
  );
}
