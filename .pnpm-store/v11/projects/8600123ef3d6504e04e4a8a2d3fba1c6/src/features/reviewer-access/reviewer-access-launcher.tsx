'use client';

import type {
  GameResponse,
  JobResponse,
  OperationalImageReviewCountsResponse,
  ReviewerIngressStatusResponse,
  ReviewerSessionCreatedResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  type ReviewerLauncherClient,
  loadReviewerIngress,
  publishReviewerSession,
  stopReviewerPublishing,
} from '@/features/reviewer-access/reviewer-access-actions';
import {
  hasImageImport,
  isImageImport,
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
  const [session, setSession] = useState<ReviewerSessionCreatedResponse | null>(
    null,
  );
  const [ingress, setIngress] = useState<ReviewerIngressStatusResponse | null>(
    null,
  );
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [reviewContextLoading, setReviewContextLoading] = useState(false);
  const [reviewCounts, setReviewCounts] =
    useState<OperationalImageReviewCountsResponse | null>(null);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError('');
      setReviewCounts(null);
      setReviewContextLoading(false);
      try {
        const [gamesResult, jobsResult, ingressResult] = await Promise.all([
          api.listGames(),
          api.listJobs({
            jobType: 'import',
            limit: 200,
            ...(controlledGameId === undefined
              ? {}
              : { gameId: controlledGameId }),
          }),
          loadReviewerIngress(api),
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
        const activeGames = gamesResult.data.filter(
          (game) => game.status === 'active',
        );
        setGames(activeGames);
        const imageJobs = jobsResult.data.filter(isImageImport);
        const firstGameId =
          activeGames.find((game) =>
            imageJobs.some((job) => job.gameId === game.id),
          )?.id ??
          activeGames[0]?.id ??
          '';
        setJobs(imageJobs);
        const selectedGameId = controlledGameId ?? firstGameId;
        if (controlledGameId === undefined) {
          setGameId(firstGameId);
        }
        setJobId(selectReviewImportId(imageJobs, selectedGameId, ''));
        if (ingressResult.ok) {
          setIngress(ingressResult.ingress);
        } else {
          setError(ingressResult.error);
        }
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

  async function createSession() {
    if (
      gameId === '' ||
      jobId === '' ||
      reviewCounts === null ||
      reviewCounts.total === 0 ||
      creating
    )
      return;
    setCreating(true);
    setError('');
    setSession(null);
    setCopied(null);
    try {
      const result = await publishReviewerSession(api, {
        gameId,
        importJobId: jobId,
        lifetimeMinutes: 480,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setIngress(result.ingress);
      setSession(result.session);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setCreating(false);
    }
  }

  async function copy(value: string, kind: 'code' | 'link') {
    await navigator.clipboard.writeText(value);
    setCopied(kind);
  }

  async function revokeSession() {
    if (session === null || revoking) return;
    setRevoking(true);
    setError('');
    try {
      const result = await api.revokeReviewerSession(session.sessionId);
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się unieważnić sesji recenzenta.',
          ),
        );
        return;
      }
      setSession(null);
      setCopied(null);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setRevoking(false);
    }
  }

  async function stopPublishing() {
    if (stopping || ingress?.state === 'stopped') return;
    setStopping(true);
    setError('');
    try {
      const result = await stopReviewerPublishing(
        api,
        session?.sessionId ?? null,
      );
      if ('ingress' in result && result.ingress !== undefined) {
        setIngress(result.ingress);
      }
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setSession(null);
      setCopied(null);
    } finally {
      setStopping(false);
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
          <h1>Zatwierdzanie plansz</h1>
          <p className="lead">
            Jednym kliknięciem uruchom osobną aplikację Reviewer, wystaw ją
            przez czasowy tunel HTTPS i utwórz dostęp ograniczony do jednej gry
            oraz importu.
          </p>
        </div>
      </header>

      <div className="reviewerLauncherCard">
        <div className="reviewerLauncherControls">
          {controlledGameId === undefined ? (
            <label>
              Gra
              <select
                disabled={loading || creating}
                onChange={(event) => {
                  const nextGameId = event.target.value;
                  setGameId(nextGameId);
                  setJobId(selectReviewImportId(jobs, nextGameId, ''));
                  setReviewCounts(null);
                  setSession(null);
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
                disabled={loading || creating || reviewContextLoading}
                onChange={(event) => {
                  setJobId(event.target.value);
                  setReviewCounts(null);
                  setSession(null);
                  setCopied(null);
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
          <button
            className="primaryButton"
            disabled={
              loading ||
              creating ||
              stopping ||
              gameId === '' ||
              jobId === '' ||
              reviewContextLoading ||
              reviewCounts?.total === 0 ||
              reviewCounts === null
            }
            onClick={() => void createSession()}
            type="button"
          >
            {creating
              ? 'Uruchamianie i tworzenie…'
              : ingress?.state === 'running'
                ? 'Utwórz nowy link online'
                : 'Utwórz link i wystaw online'}
          </button>
          <button
            className="secondaryButton"
            disabled={
              loading ||
              creating ||
              stopping ||
              ingress === null ||
              ingress.state === 'stopped'
            }
            onClick={() => void stopPublishing()}
            type="button"
          >
            {stopping ? 'Zatrzymywanie…' : 'Zatrzymaj udostępnianie'}
          </button>
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

        {ingress ? (
          <div
            className={`reviewerIngressStatus reviewerIngressStatus-${ingress.state}`}
            role="status"
          >
            <span>
              Udostępnianie:{' '}
              <strong>
                {ingress.state === 'running'
                  ? 'online'
                  : ingress.state === 'stopped'
                    ? 'wyłączone'
                    : ingress.state === 'degraded'
                      ? 'problem z aplikacją Reviewer'
                      : 'nieaktualny stan'}
              </strong>
            </span>
            {ingress.publicOrigin ? (
              <a href={ingress.publicOrigin} rel="noreferrer" target="_blank">
                {ingress.publicOrigin}
              </a>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="reviewerLauncherError" role="alert">
            {error}
          </p>
        ) : null}

        {session ? (
          <div className="reviewerSessionResult">
            <div>
              <span>Link aplikacji</span>
              <a href={session.reviewUrl} rel="noreferrer" target="_blank">
                {session.reviewUrl}
              </a>
              <button
                className="textButton"
                onClick={() => void copy(session.reviewUrl, 'link')}
                type="button"
              >
                {copied === 'link' ? 'Skopiowano' : 'Kopiuj link'}
              </button>
            </div>
            <div>
              <span>Unikalny kod wejścia</span>
              <strong>{session.accessCode}</strong>
              <button
                className="textButton"
                onClick={() => void copy(session.accessCode, 'code')}
                type="button"
              >
                {copied === 'code' ? 'Skopiowano' : 'Kopiuj kod'}
              </button>
            </div>
            <small>
              Ważny do{' '}
              {new Intl.DateTimeFormat('pl-PL', {
                dateStyle: 'short',
                timeStyle: 'short',
              }).format(new Date(session.expiresAt))}
              . Kod zostanie pokazany tylko dla tej utworzonej sesji.
            </small>
            <button
              className="textButton"
              disabled={revoking}
              onClick={() => void revokeSession()}
              type="button"
            >
              {revoking ? 'Unieważnianie…' : 'Unieważnij sesję'}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}
