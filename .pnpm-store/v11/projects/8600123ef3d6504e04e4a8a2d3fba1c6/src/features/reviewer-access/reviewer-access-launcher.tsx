'use client';

import type {
  GameResponse,
  JobResponse,
  ReviewerIngressStatusResponse,
  ReviewerSessionCreatedResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  loadReviewerIngress,
  publishReviewerSession,
  stopReviewerPublishing,
} from '@/features/reviewer-access/reviewer-access-actions';

export function ReviewerAccessLauncher({
  apiBaseUrl,
}: {
  readonly apiBaseUrl: string;
}) {
  const api = useMemo(
    () => createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl],
  );
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [jobs, setJobs] = useState<readonly JobResponse[]>([]);
  const [gameId, setGameId] = useState('');
  const [jobId, setJobId] = useState('');
  const [session, setSession] = useState<ReviewerSessionCreatedResponse | null>(
    null,
  );
  const [ingress, setIngress] = useState<ReviewerIngressStatusResponse | null>(
    null,
  );
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      setError('');
      try {
        const [gamesResult, jobsResult, ingressResult] = await Promise.all([
          api.listGames(),
          api.listJobs({ jobType: 'import', limit: 200 }),
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
        const imageJobs = jobsResult.data.filter(
          (job) =>
            job.jobType === 'import' &&
            'importKind' in job.inputPayload &&
            job.inputPayload.importKind === 'image_directory',
        );
        const firstGameId =
          activeGames.find((game) =>
            imageJobs.some((job) => job.gameId === game.id),
          )?.id ??
          activeGames[0]?.id ??
          '';
        setJobs(imageJobs);
        setGameId(firstGameId);
        setJobId(imageJobs.find((job) => job.gameId === firstGameId)?.id ?? '');
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
  }, [api]);

  const availableJobs = jobs.filter((job) => job.gameId === gameId);

  async function createSession() {
    if (gameId === '' || jobId === '' || creating) return;
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
          <label>
            Gra
            <select
              disabled={loading || creating}
              onChange={(event) => {
                const nextGameId = event.target.value;
                setGameId(nextGameId);
                setJobId(
                  jobs.find((job) => job.gameId === nextGameId)?.id ?? '',
                );
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
          <label>
            Import zdjęć
            <select
              disabled={loading || creating || availableJobs.length === 0}
              onChange={(event) => {
                setJobId(event.target.value);
                setSession(null);
              }}
              value={jobId}
            >
              {availableJobs.length === 0 ? (
                <option value="">Brak importów</option>
              ) : (
                availableJobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.id.slice(0, 8)} · {job.status}
                  </option>
                ))
              )}
            </select>
          </label>
          <button
            className="primaryButton"
            disabled={
              loading || creating || stopping || gameId === '' || jobId === ''
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
