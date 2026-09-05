'use client';

import type {
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
  ImageGridReviewView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  approveGridReviewSource,
  loadGridReviewPage,
  loadGridReviewSource,
  rejectGridReview,
  type GridReviewsClient,
} from './grid-review-actions';
import { GridReviewEditor } from './grid-review-editor';
import {
  GRID_REVIEW_SOURCE_PAGE_LIMIT,
  GRID_REVIEW_VIEWS,
  gridReviewSourceStats,
  isGridReviewTypingTarget,
  orderGridReviewSourceItems,
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
  const [anchorPage, setAnchorPage] =
    useState<ImageGridReviewPageResponse | null>(null);
  const [sourceItems, setSourceItems] = useState<
    readonly ImageGridReviewItemResponse[]
  >([]);
  const [selectedReviewItemId, setSelectedReviewItemId] = useState<string>('');
  const [editing, setEditing] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [rejectConfirmation, setRejectConfirmation] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const requestId = useRef(0);
  const submitLock = useRef(false);
  const navigationRef = useRef<GridReviewNavigation>({});
  const anchorItem = anchorPage?.items[0] ?? null;
  const sourceStats = useMemo(
    () => gridReviewSourceStats(sourceItems),
    [sourceItems],
  );

  const hydrateSource = useCallback(
    async (
      anchor: ImageGridReviewPageResponse,
      request: number,
    ): Promise<boolean> => {
      const sourceItem = anchor.items[0];
      if (sourceItem === undefined) {
        setAnchorPage(anchor);
        setSourceItems([]);
        setSelectedReviewItemId('');
        return true;
      }
      const sourceResult = await loadGridReviewSource(api, {
        gameId,
        importJobId,
        sourceImageId: sourceItem.sourceImageId,
      });
      if (request !== requestId.current) return false;
      if (!sourceResult.ok) {
        setError(sourceResult.error);
        return false;
      }
      const items = orderGridReviewSourceItems(sourceResult.page.items);
      setAnchorPage(anchor);
      setSourceItems(items);
      setSelectedReviewItemId((current) =>
        items.some((candidate) => candidate.reviewItemId === current)
          ? current
          : (items[0]?.reviewItemId ?? ''),
      );
      return true;
    },
    [api, gameId, importJobId],
  );

  const loadPage = useCallback(
    async (navigation: GridReviewNavigation = {}) => {
      const currentRequest = ++requestId.current;
      navigationRef.current = navigation;
      setLoading(true);
      setError('');
      setRejectConfirmation(false);
      const result = await loadGridReviewPage(api, {
        gameId,
        importJobId,
        navigation,
        view,
      });
      if (currentRequest !== requestId.current) return;
      if (!result.ok) {
        setLoading(false);
        setError(
          result.isConflict
            ? `${result.error} Kolejka zmieniła się — wczytaj aktualną pozycję.`
            : result.error,
        );
        return;
      }
      await hydrateSource(result.page, currentRequest);
      if (currentRequest === requestId.current) setLoading(false);
    },
    [api, gameId, hydrateSource, importJobId, view],
  );

  useEffect(() => {
    queueMicrotask(() => void loadPage());
  }, [loadPage]);

  const moveSource = useCallback(
    async (direction: 'next' | 'previous') => {
      if (anchorItem === null || submitting) return false;
      const currentSourceId = anchorItem.sourceImageId;
      let cursor =
        direction === 'next'
          ? anchorPage?.nextCursor
          : anchorPage?.previousCursor;
      for (
        let scanned = 0;
        scanned < GRID_REVIEW_SOURCE_PAGE_LIMIT;
        scanned += 1
      ) {
        if (cursor === null || cursor === undefined) break;
        const currentRequest = ++requestId.current;
        setLoading(true);
        const result = await loadGridReviewPage(api, {
          gameId,
          importJobId,
          navigation:
            direction === 'next'
              ? { afterCursor: cursor }
              : { beforeCursor: cursor },
          view,
        });
        if (currentRequest !== requestId.current) return false;
        if (!result.ok) {
          setLoading(false);
          setError(result.error);
          return false;
        }
        const candidate = result.page.items[0];
        if (candidate === undefined) break;
        if (candidate.sourceImageId !== currentSourceId) {
          navigationRef.current =
            direction === 'next'
              ? { afterCursor: cursor }
              : { beforeCursor: cursor };
          await hydrateSource(result.page, currentRequest);
          if (currentRequest === requestId.current) setLoading(false);
          return true;
        }
        cursor =
          direction === 'next'
            ? result.page.nextCursor
            : result.page.previousCursor;
      }
      setLoading(false);
      return false;
    },
    [
      anchorItem,
      anchorPage,
      api,
      gameId,
      hydrateSource,
      importJobId,
      submitting,
      view,
    ],
  );

  const refreshAfterMutation = useCallback(async () => {
    setRejectConfirmation(false);
    if (!(await moveSource('next'))) await loadPage();
  }, [loadPage, moveSource]);

  const approveSource = useCallback(async () => {
    if (sourceItems.length === 0 || submitLock.current) return;
    if (
      sourceItems.some((candidate) => candidate.state === 'needs_correction')
    ) {
      setError('Najpierw popraw plansze oznaczone jako „Do poprawy”.');
      return;
    }
    submitLock.current = true;
    setSubmitting(true);
    setError('');
    setNotice('');
    const result = await approveGridReviewSource(api, sourceItems);
    if (!result.ok) {
      setSubmitting(false);
      submitLock.current = false;
      setError(
        result.isConflict
          ? `${result.error} Wczytuję aktualne dane zdjęcia.`
          : result.error,
      );
      if (result.isConflict) await loadPage(navigationRef.current);
      return;
    }
    const changed = result.approval.changedCount;
    setNotice(
      changed === 0
        ? 'Całe zdjęcie było już zatwierdzone.'
        : `Zatwierdzono geometrię ${changed} plansz z jednego zdjęcia.`,
    );
    await refreshAfterMutation();
    setSubmitting(false);
    submitLock.current = false;
  }, [api, loadPage, refreshAfterMutation, sourceItems]);

  const rejectSource = useCallback(async () => {
    if (sourceItems.length === 0 || submitLock.current) return;
    if (!rejectConfirmation) {
      setRejectConfirmation(true);
      setNotice(
        `Potwierdź odrzucenie całego zdjęcia i ${sourceItems.length} aktywnych plansz.`,
      );
      return;
    }
    submitLock.current = true;
    setSubmitting(true);
    setError('');
    let rejected = 0;
    for (const candidate of sourceItems) {
      const result = await rejectGridReview(api, candidate);
      if (!result.ok) {
        setSubmitting(false);
        submitLock.current = false;
        setError(result.error);
        if (result.isConflict) await loadPage(navigationRef.current);
        return;
      }
      rejected += 1;
    }
    setNotice(`Odrzucono ${rejected} plansz z tego zdjęcia.`);
    await refreshAfterMutation();
    setSubmitting(false);
    submitLock.current = false;
  }, [api, loadPage, refreshAfterMutation, rejectConfirmation, sourceItems]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.repeat || isGridReviewTypingTarget(event.target) || editing) {
        return;
      }
      if (event.key === 'Enter' || event.key.toLowerCase() === 'f') {
        event.preventDefault();
        void approveSource();
        return;
      }
      if (event.key === 'ArrowRight') {
        event.preventDefault();
        void moveSource('next');
      }
      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        void moveSource('previous');
      }
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [approveSource, editing, moveSource]);

  return (
    <div className="gridReviewWorkspace">
      <header className="gridReviewHeader">
        <div>
          <p className="eyebrow">Geometria plansz</p>
          <h1>Zatwierdzanie cięcia siatki</h1>
          <p className="lead">
            Weryfikujesz komplet aktywnych plansz jednego zdjęcia źródłowego.
            Symbole są w osobnym widoku.
          </p>
        </div>
        {anchorPage ? (
          <dl className="gridReviewCounts">
            <div>
              <dt>Do walidacji</dt>
              <dd>
                {anchorPage.counts.needsValidation.toLocaleString('pl-PL')}
              </dd>
            </div>
            <div>
              <dt>Do poprawy</dt>
              <dd>
                {anchorPage.counts.needsCorrection.toLocaleString('pl-PL')}
              </dd>
            </div>
            <div>
              <dt>Zatwierdzone</dt>
              <dd>{anchorPage.counts.approved.toLocaleString('pl-PL')}</dd>
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
          <h2>Wczytywanie geometrii zdjęcia</h2>
          <p>Pobieram jeden obraz źródłowy i wszystkie jego aktywne sloty.</p>
        </section>
      ) : anchorItem === null ? (
        <section className="gridReviewState">
          <h2>Brak plansz w tym filtrze</h2>
          <p>Wybierz inny filtr albo wróć po zakończeniu kolejnego importu.</p>
        </section>
      ) : (
        <>
          <section
            className="gridReviewSourceStats"
            aria-label="Statystyki zdjęcia źródłowego"
          >
            <div>
              <span>Aktywne plansze</span>
              <strong>{sourceStats.totalBoards}</strong>
            </div>
            <div>
              <span>Zatwierdzone</span>
              <strong>{sourceStats.approvedBoards}</strong>
            </div>
            <div>
              <span>Do walidacji</span>
              <strong>{sourceStats.needsValidationBoards}</strong>
            </div>
            <div>
              <span>Do poprawy</span>
              <strong>{sourceStats.needsCorrectionBoards}</strong>
            </div>
            <div>
              <span>Ręczne rewizje</span>
              <strong>{sourceStats.manualBoards}</strong>
            </div>
          </section>
          <GridReviewEditor
            api={api}
            items={sourceItems}
            key={anchorItem.sourceImageId}
            onEditingChange={setEditing}
            onSaved={() => {
              setNotice(
                'Zapisano geometrię i przechodzę do kolejnego zdjęcia.',
              );
              void refreshAfterMutation();
            }}
            onSelect={setSelectedReviewItemId}
            selectedReviewItemId={selectedReviewItemId}
          />
          <footer className="gridReviewActions">
            <button
              className="secondaryButton"
              disabled={submitting || anchorPage?.previousCursor === null}
              onClick={() => void moveSource('previous')}
              type="button"
            >
              ← Poprzednie zdjęcie
            </button>
            <div className="gridReviewWholeImageActions">
              <button
                className="dangerButton"
                disabled={submitting}
                onClick={() => void rejectSource()}
                type="button"
              >
                {rejectConfirmation
                  ? 'Potwierdź odrzucenie zdjęcia'
                  : 'Odrzuć całe zdjęcie'}
              </button>
              <button
                aria-label="Zatwierdź całe zdjęcie i przejdź do następnego"
                className="primaryButton gridReviewApprove"
                disabled={
                  submitting || sourceStats.needsCorrectionBoards > 0 || editing
                }
                onClick={() => void approveSource()}
                type="button"
              >
                {submitting
                  ? 'Zapisywanie…'
                  : 'Zatwierdź całe zdjęcie (Enter / F)'}
              </button>
            </div>
            <button
              className="secondaryButton"
              disabled={submitting || anchorPage?.nextCursor === null}
              onClick={() => void moveSource('next')}
              type="button"
            >
              Następne zdjęcie →
            </button>
          </footer>
        </>
      )}
    </div>
  );
}
