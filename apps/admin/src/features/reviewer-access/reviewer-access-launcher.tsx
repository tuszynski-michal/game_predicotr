'use client';

import type {
  GameResponse,
  JobResponse,
  OperationalImageReviewCountsResponse,
  ReviewerWorkAssignmentResponse,
  ReviewerWorkOpenedResponse,
  ReviewerWorkOverviewResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  closeReviewerWork,
  heartbeatReviewerWork,
  loadReviewerWork,
  openLocalReviewer,
  openOnlineReviewer,
  type ReviewerLauncherClient,
} from '@/features/reviewer-access/reviewer-access-actions';
import {
  hasImageImport,
  isImageImport,
  reviewableGames,
  reviewJobLabel,
  reviewReadyImports,
  selectReviewImportId,
} from '@/features/reviewer-access/reviewer-access-state';

export function ReviewerAccessLauncher({
  apiBaseUrl,
  client,
  gameId: controlledGameId,
  onOpenImports,
}: {
  readonly apiBaseUrl: string;
  readonly client?: ReviewerLauncherClient;
  readonly gameId?: string;
  readonly onOpenImports?: () => void;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [uncontrolledGameId, setGameId] = useState('');
  const gameId = controlledGameId ?? uncontrolledGameId;
  const [jobId, setJobId] = useState('');
  const [overview, setOverview] = useState<ReviewerWorkOverviewResponse | null>(
    null,
  );
  const [oneTimeOnlineAccess, setOneTimeOnlineAccess] =
    useState<ReviewerWorkOpenedResponse | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [loading, setLoading] = useState(true);
  const [reviewContextLoading, setReviewContextLoading] = useState(false);
  const [reviewCounts, setReviewCounts] =
    useState<OperationalImageReviewCountsResponse | null>(null);
  const [opening, setOpening] = useState<'local' | 'online' | null>(null);
  const [closingAssignmentId, setClosingAssignmentId] = useState<string | null>(
    null,
  );
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);
  const [localReviewUrl, setLocalReviewUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [gamesResult, jobsResult] = await Promise.all([
          api.listGames(),
          api.listJobs({
            jobType: 'import',
            limit: 200,
            ...(controlledGameId === undefined
              ? {}
              : { gameId: controlledGameId }),
          }),
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
  const gameHasImageImport = hasImageImport(jobs, gameId);
  const selectedAssignment =
    overview?.assignments.find((item) => item.importJobId === jobId) ?? null;

  async function refreshOverview(showError = true) {
    if (gameId === '') {
      setOverview(null);
      return;
    }
    const result = await loadReviewerWork(api, gameId);
    if (!result.ok) {
      if (showError) setError(result.error);
      return;
    }
    setOverview(result.overview);
  }

  useEffect(() => {
    let active = true;
    async function load() {
      if (gameId === '') {
        setOverview(null);
        return;
      }
      const result = await loadReviewerWork(api, gameId);
      if (!active) return;
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setOverview(result.overview);
    }
    void load();
    return () => {
      active = false;
    };
  }, [api, gameId]);

  const heartbeatIds = useMemo(
    () => overview?.assignments.map((item) => item.assignmentId) ?? [],
    [overview],
  );
  const heartbeatKey = heartbeatIds.join(',');
  useEffect(() => {
    if (heartbeatIds.length === 0) return;
    const timer = window.setInterval(() => {
      void Promise.all(
        heartbeatIds.map((assignmentId) =>
          heartbeatReviewerWork(api, assignmentId),
        ),
      ).then((results) => {
        if (results.some((ok) => !ok)) void refreshOverview(false);
      });
    }, 60_000);
    return () => window.clearInterval(timer);
    // The stable key deliberately restarts the timer only when assignment IDs change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, heartbeatKey]);

  useEffect(() => {
    let active = true;
    async function loadReviewContext() {
      setReviewCounts(null);
      if (gameId === '' || jobId === '') {
        setReviewContextLoading(false);
        return;
      }
      setReviewContextLoading(true);
      setError('');
      try {
        const result = await api.listOperationalImageReviewItems({
          gameId,
          importJobId: jobId,
          limit: 1,
          view: 'all',
        });
        if (!active) return;
        if (result.error !== undefined || result.data === undefined) {
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się sprawdzić plansz wybranego importu.',
            ),
          );
          return;
        }
        setReviewCounts(result.data.counts);
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
      reviewCounts !== null &&
      reviewCounts.total > 0 &&
      overview !== null &&
      opening === null &&
      closingAssignmentId === null
    );
  }

  async function launchLocalReviewer() {
    if (!canOpenWork()) return;
    const reviewerWindow = window.open('about:blank', '_blank');
    if (reviewerWindow !== null) reviewerWindow.opener = null;
    setOpening('local');
    setError('');
    setNotice('');
    setLocalReviewUrl(null);
    try {
      const result = await openLocalReviewer(api, {
        gameId,
        importJobId: jobId,
      });
      if (!result.ok) {
        reviewerWindow?.close();
        setError(result.error);
        return;
      }
      const reviewUrl = result.opened.assignment.reviewUrl;
      await refreshOverview(false);
      if (reviewUrl === null) {
        reviewerWindow?.close();
        setError('Lokalna aplikacja Reviewer nie zwróciła adresu.');
        return;
      }
      if (reviewerWindow === null) {
        setLocalReviewUrl(reviewUrl);
        setError(
          'Przeglądarka zablokowała nowe okno. Otwórz lokalny Reviewer z linku poniżej.',
        );
        return;
      }
      reviewerWindow.location.replace(reviewUrl);
    } finally {
      setOpening(null);
    }
  }

  async function createOnlineWork() {
    if (!canOpenWork() || selectedAssignment !== null) return;
    setOpening('online');
    setError('');
    setNotice('');
    setOneTimeOnlineAccess(null);
    setCopied(null);
    try {
      const result = await openOnlineReviewer(api, {
        gameId,
        importJobId: jobId,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (result.opened.created && result.opened.accessCode !== null) {
        setOneTimeOnlineAccess(result.opened);
      } else {
        setNotice(
          'Udostępnienie było już aktywne. Kod wejścia jest pokazywany tylko przy pierwszym utworzeniu.',
        );
      }
      await refreshOverview(false);
    } finally {
      setOpening(null);
    }
  }

  async function stopAssignment(assignment: ReviewerWorkAssignmentResponse) {
    if (closingAssignmentId !== null) return;
    setClosingAssignmentId(assignment.assignmentId);
    setError('');
    setNotice('');
    try {
      const result = await closeReviewerWork(api, assignment.assignmentId);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (
        oneTimeOnlineAccess?.assignment.assignmentId === assignment.assignmentId
      ) {
        setOneTimeOnlineAccess(null);
        setCopied(null);
      }
      await refreshOverview(false);
    } finally {
      setClosingAssignmentId(null);
    }
  }

  async function copy(value: string, kind: 'code' | 'link') {
    await navigator.clipboard.writeText(value);
    setCopied(kind);
  }

  return (
    <section
      className="catalogSection reviewerLauncher"
      id="operational-reviews"
    >
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Osobna aplikacja</p>
          <h1>Zatwierdzanie plansz</h1>
          <p className="lead">
            Wybierz gotowy import. Możesz pracować lokalnie albo udostępnić
            jednocześnie maksymalnie trzy różne importy online.
          </p>
        </div>
      </header>

      <div className="reviewerLauncherCard">
        <div className="reviewerLauncherControls">
          {controlledGameId === undefined ? (
            <label>
              Gra
              <select
                disabled={loading || opening !== null}
                onChange={(event) => {
                  const nextGameId = event.target.value;
                  setGameId(nextGameId);
                  setJobId(selectReviewImportId(jobs, nextGameId, ''));
                  setReviewCounts(null);
                  setOneTimeOnlineAccess(null);
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
            <label>
              Gotowy import zdjęć
              <select
                disabled={loading || opening !== null || reviewContextLoading}
                onChange={(event) => {
                  setJobId(event.target.value);
                  setReviewCounts(null);
                  setOneTimeOnlineAccess(null);
                  setCopied(null);
                  setNotice('');
                }}
                value={jobId}
              >
                {availableJobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {reviewJobLabel(job)}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          {selectedAssignment?.assignmentType === 'online' ? (
            <button
              className="secondaryButton"
              disabled={closingAssignmentId !== null}
              onClick={() => void stopAssignment(selectedAssignment)}
              type="button"
            >
              {closingAssignmentId === selectedAssignment.assignmentId
                ? 'Zatrzymywanie…'
                : 'Zatrzymaj udostępnianie'}
            </button>
          ) : selectedAssignment?.assignmentType === 'local' ? (
            <>
              <button
                className="secondaryButton"
                disabled={!canOpenWork()}
                onClick={() => void launchLocalReviewer()}
                type="button"
              >
                {opening === 'local' ? 'Otwieranie…' : 'Otwórz lokalnie'}
              </button>
              <button
                className="textButton"
                disabled={closingAssignmentId !== null}
                onClick={() => void stopAssignment(selectedAssignment)}
                type="button"
              >
                {closingAssignmentId === selectedAssignment.assignmentId
                  ? 'Kończenie…'
                  : 'Zakończ pracę lokalną'}
              </button>
            </>
          ) : (
            <>
              <button
                className="secondaryButton"
                disabled={!canOpenWork()}
                onClick={() => void launchLocalReviewer()}
                type="button"
              >
                {opening === 'local'
                  ? 'Uruchamianie lokalnie…'
                  : 'Otwórz lokalnie'}
              </button>
              <button
                className="primaryButton"
                disabled={!canOpenWork()}
                onClick={() => void createOnlineWork()}
                type="button"
              >
                {opening === 'online'
                  ? 'Tworzenie linku…'
                  : 'Utwórz link online'}
              </button>
            </>
          )}
        </div>

        {!loading && availableJobs.length === 0 ? (
          <div className="reviewerPrerequisite" role="status">
            <div>
              <strong>
                {gameHasImageImport
                  ? 'Import nie jest jeszcze gotowy do zatwierdzania'
                  : 'Brak importu zdjęć dla tej gry'}
              </strong>
              <p>
                {gameHasImageImport
                  ? 'Poczekaj na etap zatwierdzania albo sprawdź błąd w zakładce Joby.'
                  : 'Wczytaj zdjęcia i zakończ ich przetwarzanie, aby otworzyć Reviewer.'}
              </p>
            </div>
            {onOpenImports ? (
              <button
                className="secondaryButton"
                onClick={onOpenImports}
                type="button"
              >
                Przejdź do Import layoutów
              </button>
            ) : null}
          </div>
        ) : null}

        {reviewContextLoading ? (
          <p className="mutedText">Sprawdzam plansze wybranego importu…</p>
        ) : reviewCounts?.total === 0 ? (
          <div className="reviewerPrerequisite" role="status">
            <div>
              <strong>Wybrany import nie zawiera plansz</strong>
              <p>Doładuj zdjęcia lub wybierz inny gotowy import.</p>
            </div>
          </div>
        ) : reviewCounts ? (
          <dl
            className="reviewerReadinessSummary"
            aria-label="Stan plansz importu"
          >
            <div>
              <dt>Wszystkie plansze</dt>
              <dd>{reviewCounts.total.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Do zatwierdzenia</dt>
              <dd>{reviewCounts.pending.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Zakończone</dt>
              <dd>{reviewCounts.completed.toLocaleString('pl-PL')}</dd>
            </div>
          </dl>
        ) : null}

        {overview ? (
          <div
            className={`reviewerIngressStatus reviewerIngressStatus-${overview.ingress.state}`}
            role="status"
          >
            <span>
              Udostępnienia online:{' '}
              <strong>
                {overview.activeOnlineCount}/{overview.maximumOnlineCount}
              </strong>
            </span>
            <span>
              Wspólny Reviewer:{' '}
              <strong>
                {overview.ingress.reviewerReady
                  ? 'gotowy'
                  : overview.ingress.state === 'degraded'
                    ? 'problem'
                    : 'wyłączony'}
              </strong>
            </span>
          </div>
        ) : null}

        {selectedAssignment ? (
          <p className="mutedText" role="status">
            Wybrany import ma aktywną pracę{' '}
            <strong>
              {selectedAssignment.assignmentType === 'online'
                ? 'online'
                : 'lokalną'}
            </strong>
            {selectedAssignment.ready
              ? '.'
              : ' — Reviewer wymaga ponownego uruchomienia.'}
          </p>
        ) : null}

        {error ? (
          <p className="reviewerLauncherError" role="alert">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="reviewerLocalFallback" role="status">
            {notice}
          </p>
        ) : null}
        {localReviewUrl ? (
          <p className="reviewerLocalFallback" role="status">
            <a href={localReviewUrl} rel="noreferrer" target="_blank">
              Otwórz lokalny Reviewer
            </a>
          </p>
        ) : null}

        {oneTimeOnlineAccess?.accessCode &&
        oneTimeOnlineAccess.assignment.reviewUrl ? (
          <div className="reviewerSessionResult">
            <div>
              <span>Link aplikacji</span>
              <a
                href={oneTimeOnlineAccess.assignment.reviewUrl}
                rel="noreferrer"
                target="_blank"
              >
                {oneTimeOnlineAccess.assignment.reviewUrl}
              </a>
              <button
                className="textButton"
                onClick={() =>
                  void copy(oneTimeOnlineAccess.assignment.reviewUrl!, 'link')
                }
                type="button"
              >
                {copied === 'link' ? 'Skopiowano' : 'Kopiuj link'}
              </button>
            </div>
            <div>
              <span>Unikalny kod wejścia</span>
              <strong>{oneTimeOnlineAccess.accessCode}</strong>
              <button
                className="textButton"
                onClick={() =>
                  void copy(oneTimeOnlineAccess.accessCode!, 'code')
                }
                type="button"
              >
                {copied === 'code' ? 'Skopiowano' : 'Kopiuj kod'}
              </button>
            </div>
            <small>
              Kod jest pokazany tylko teraz. Po odświeżeniu lista aktywnych prac
              nie ujawnia kodu ani tokenów.
            </small>
          </div>
        ) : null}

        {overview && overview.assignments.length > 0 ? (
          <div className="reviewerWorkList">
            <h2>Aktywne prace</h2>
            <ul>
              {overview.assignments.map((assignment) => {
                const job = jobs.find(
                  (item) => item.id === assignment.importJobId,
                );
                return (
                  <li key={assignment.assignmentId}>
                    <div>
                      <strong>
                        {job
                          ? reviewJobLabel(job)
                          : assignment.importJobId.slice(0, 8)}
                      </strong>
                      <span>
                        {assignment.assignmentType === 'online'
                          ? 'Online'
                          : 'Lokalnie'}
                        {' · '}
                        {assignment.ready
                          ? 'Reviewer gotowy'
                          : 'wymaga uruchomienia'}
                      </span>
                    </div>
                    <button
                      className="textButton"
                      disabled={closingAssignmentId !== null}
                      onClick={() => void stopAssignment(assignment)}
                      type="button"
                    >
                      {closingAssignmentId === assignment.assignmentId
                        ? 'Zatrzymywanie…'
                        : assignment.assignmentType === 'online'
                          ? 'Zatrzymaj udostępnianie'
                          : 'Zakończ pracę'}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </section>
  );
}
