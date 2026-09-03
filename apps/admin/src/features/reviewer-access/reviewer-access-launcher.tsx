'use client';

import type {
  BoardCellGeometryJobCountsResponse,
  BrowserReadySelectionResponse,
  GameResponse,
  ImageGridReviewPageResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  hasImageImport,
  hasReviewerWork,
  gridReviewTotal,
  isImageImport,
  readyBoardImportStaging,
  reviewableGames,
  reviewJobLabel,
  reviewReadyImports,
  selectReviewImportId,
} from '@/features/reviewer-access/reviewer-access-state';
import {
  buildPreparedLocalReviewUrl,
  prepareLocalReviewerWindow,
} from '@/features/reviewer-access/reviewer-local-window';

type GridReviewLauncherClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'listGames'
  | 'listJobs'
  | 'listReadyBrowserImageSelections'
  | 'listImageGridReviews'
  | 'listPendingBoardCellGeometry'
>;

export function ReviewerAccessLauncher({
  apiBaseUrl,
  client,
  gameId: controlledGameId,
  onOpenImports,
}: {
  readonly apiBaseUrl: string;
  readonly client?: GridReviewLauncherClient;
  readonly gameId?: string;
  readonly onOpenImports?: () => void;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [readyStaging, setReadyStaging] = useState<
    readonly BrowserReadySelectionResponse[]
  >([]);
  const [uncontrolledGameId, setGameId] = useState('');
  const gameId = controlledGameId ?? uncontrolledGameId;
  const [jobId, setJobId] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reviewContextLoading, setReviewContextLoading] = useState(false);
  const [gridReviewCounts, setGridReviewCounts] = useState<
    ImageGridReviewPageResponse['counts'] | null
  >(null);
  const [deferredGeometryCounts, setDeferredGeometryCounts] =
    useState<BoardCellGeometryJobCountsResponse | null>(null);
  const [localReviewUrl, setLocalReviewUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [gamesResult, jobsResult, stagingResult] = await Promise.all([
          api.listGames(),
          api.listJobs({
            jobType: 'import',
            limit: 200,
            ...(controlledGameId === undefined
              ? {}
              : { gameId: controlledGameId }),
          }),
          api.listReadyBrowserImageSelections(),
        ]);
        if (!active) return;
        if (
          gamesResult.error !== undefined ||
          gamesResult.data === undefined ||
          jobsResult.error !== undefined ||
          jobsResult.data === undefined
        ) {
          setError(
            apiErrorMessage(
              gamesResult.error ?? jobsResult.error,
              'Nie udało się pobrać kontekstu aplikacji recenzenta.',
            ),
          );
          return;
        }
        const availableGames = reviewableGames(gamesResult.data);
        const imageJobs = jobsResult.data.filter(isImageImport);
        const firstGameId =
          availableGames.find((game) =>
            imageJobs.some((job) => job.gameId === game.id),
          )?.id ??
          availableGames[0]?.id ??
          '';
        setGames(availableGames);
        setJobs(imageJobs);
        setReadyStaging(
          stagingResult.error === undefined && stagingResult.data !== undefined
            ? stagingResult.data
            : [],
        );
        const selectedGameId = controlledGameId ?? firstGameId;
        if (controlledGameId === undefined) setGameId(firstGameId);
        setJobId(selectReviewImportId(imageJobs, selectedGameId, ''));
      } catch {
        if (active) {
          setError('Połączenie z lokalnym Admin API zostało przerwane.');
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [api, controlledGameId]);

  const availableJobs = reviewReadyImports(jobs, gameId);
  const availableStaging = readyBoardImportStaging(readyStaging, gameId);
  const gameHasImageImport = hasImageImport(jobs, gameId);
  const selectedJob = availableJobs.find((job) => job.id === jobId) ?? null;

  useEffect(() => {
    let active = true;
    async function loadReviewContext() {
      setGridReviewCounts(null);
      setDeferredGeometryCounts(null);
      if (gameId === '' || jobId === '') {
        setReviewContextLoading(false);
        return;
      }
      setReviewContextLoading(true);
      setError('');
      try {
        const [gridResult, deferredResult] = await Promise.all([
          api.listImageGridReviews({
            gameId,
            importJobId: jobId,
            limit: 1,
            view: 'all',
          }),
          api.listPendingBoardCellGeometry({
            gameId,
            importJobId: jobId,
            limit: 1,
            status: 'pending',
          }),
        ]);
        if (!active) return;
        if (
          gridResult.error !== undefined ||
          gridResult.data === undefined ||
          deferredResult.error !== undefined ||
          deferredResult.data === undefined
        ) {
          setError(
            apiErrorMessage(
              gridResult.error ?? deferredResult.error,
              'Nie udało się sprawdzić plansz wybranego importu.',
            ),
          );
          return;
        }
        setGridReviewCounts(gridResult.data.counts);
        setDeferredGeometryCounts(deferredResult.data.counts);
      } catch {
        if (active) {
          setError('Połączenie z lokalnym Admin API zostało przerwane.');
        }
      } finally {
        if (active) setReviewContextLoading(false);
      }
    }
    void loadReviewContext();
    return () => {
      active = false;
    };
  }, [api, gameId, jobId]);

  function canOpenWork() {
    return (
      gameId !== '' &&
      jobId !== '' &&
      !loading &&
      !reviewContextLoading &&
      hasReviewerWork(gridReviewCounts, deferredGeometryCounts)
    );
  }

  function launchLocalReviewer() {
    if (!canOpenWork()) return;
    setError('');
    const reviewUrl = buildPreparedLocalReviewUrl(window.location.href, {
      gameId,
      importJobId: jobId,
    });
    if (reviewUrl === null) {
      setLocalReviewUrl(null);
      setError(
        'Lokalny Reviewer można otworzyć wyłącznie z lokalnego panelu Admina.',
      );
      return;
    }
    setLocalReviewUrl(reviewUrl);
    const reviewerWindow = prepareLocalReviewerWindow(
      window.location.href,
      { gameId, importJobId: jobId },
      (url, target) => window.open(url, target),
    );
    if (reviewerWindow === null) {
      setError(
        'Przeglądarka zablokowała nowe okno. Otwórz lokalny Reviewer z linku poniżej.',
      );
    }
  }

  return (
    <section
      className="catalogSection reviewerLauncher"
      id="operational-reviews"
    >
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Osobna aplikacja</p>
          <h1>Zatwierdzanie cięcia siatki</h1>
          <p className="lead">
            Otwórz lokalny Reviewer, aby zatwierdzić lub poprawić geometrię
            wybranego importu.
          </p>
        </div>
      </header>

      <div className="reviewerLauncherCard">
        <div className="reviewerLauncherControls">
          {controlledGameId === undefined ? (
            <label>
              Gra
              <select
                disabled={loading}
                onChange={(event) => {
                  const nextGameId = event.target.value;
                  setGameId(nextGameId);
                  setJobId(selectReviewImportId(jobs, nextGameId, ''));
                  setGridReviewCounts(null);
                  setDeferredGeometryCounts(null);
                  setLocalReviewUrl(null);
                }}
                value={gameId}
              >
                {games.map((game) => (
                  <option key={game.id} value={game.id}>
                    {game.name}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          {availableJobs.length > 0 ? (
            <label className="reviewerImportChoice">
              Gotowy import plansz
              <select
                className="reviewerImportSelect"
                disabled={loading || reviewContextLoading}
                onChange={(event) => {
                  setJobId(event.target.value);
                  setGridReviewCounts(null);
                  setDeferredGeometryCounts(null);
                  setLocalReviewUrl(null);
                }}
                title={
                  selectedJob === null ? undefined : reviewJobLabel(selectedJob)
                }
                value={jobId}
              >
                {availableJobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {reviewJobLabel(job)}
                  </option>
                ))}
              </select>
              {selectedJob !== null ? (
                <span className="reviewerSelectedImportId">
                  ID: <code>{selectedJob.id}</code>
                </span>
              ) : null}
            </label>
          ) : null}

          <button
            className="secondaryButton"
            disabled={!canOpenWork()}
            onClick={launchLocalReviewer}
            type="button"
          >
            Otwórz lokalnie
          </button>
        </div>

        {!loading && availableJobs.length === 0 ? (
          <div className="reviewerPrerequisite" role="status">
            <div>
              <strong>
                {availableStaging.length > 0
                  ? 'Gotowy staging plansz czeka na uruchomienie importu'
                  : gameHasImageImport
                    ? 'Import nie jest jeszcze gotowy do zatwierdzania'
                    : 'Brak uruchomionego importu plansz dla tej gry'}
              </strong>
              <p>
                {availableStaging.length > 0
                  ? `Staging „${availableStaging[0].displayName}” zawiera ${availableStaging[0].uploadedFileCount.toLocaleString('pl-PL')} plików, ale nie jest jeszcze jobem importu plansz. Wróć do Importu plansz, pokaż raport, przygotuj geometrię stron i jawnie rozpocznij import. Dopiero utworzony job z kolejką plansz pojawi się tutaj.`
                  : gameHasImageImport
                    ? 'Poczekaj na etap zatwierdzania albo sprawdź błąd w zakładce Joby.'
                    : 'Wczytaj zdjęcia, przygotuj import plansz i zakończ jego przetwarzanie, aby otworzyć Reviewer.'}
              </p>
            </div>
            {onOpenImports ? (
              <button
                className="secondaryButton"
                onClick={onOpenImports}
                type="button"
              >
                Przejdź do Importu plansz
              </button>
            ) : null}
          </div>
        ) : null}

        {reviewContextLoading ? (
          <p className="mutedText">Sprawdzam plansze wybranego importu…</p>
        ) : gridReviewCounts !== null &&
          gridReviewTotal(gridReviewCounts) === 0 &&
          deferredGeometryCounts?.pending === 0 ? (
          <div className="reviewerPrerequisite" role="status">
            <div>
              <strong>Wybrany import nie zawiera plansz</strong>
              <p>Doładuj zdjęcia lub wybierz inny gotowy import.</p>
            </div>
          </div>
        ) : gridReviewCounts && deferredGeometryCounts ? (
          <dl
            className="reviewerReadinessSummary"
            aria-label="Stan plansz importu"
          >
            <div>
              <dt>Wszystkie plansze</dt>
              <dd>
                {(
                  gridReviewTotal(gridReviewCounts) +
                  deferredGeometryCounts.total
                ).toLocaleString('pl-PL')}
              </dd>
            </div>
            <div>
              <dt>Do walidacji</dt>
              <dd>
                {gridReviewCounts.needsValidation.toLocaleString('pl-PL')}
              </dd>
            </div>
            <div>
              <dt>Zakończone</dt>
              <dd>{gridReviewCounts.approved.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Do korekty siatki</dt>
              <dd>
                {(
                  gridReviewCounts.needsCorrection +
                  deferredGeometryCounts.pending
                ).toLocaleString('pl-PL')}
              </dd>
            </div>
          </dl>
        ) : null}

        {error ? (
          <p className="reviewerLauncherError" role="alert">
            {error}
          </p>
        ) : null}
        {localReviewUrl ? (
          <p className="reviewerLocalFallback" role="status">
            <a href={localReviewUrl} rel="noreferrer" target="_blank">
              Otwórz lokalny Reviewer
            </a>
          </p>
        ) : null}
      </div>
    </section>
  );
}
