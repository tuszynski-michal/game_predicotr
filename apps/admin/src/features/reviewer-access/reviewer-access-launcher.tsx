'use client';

import type {
  BrowserReadySelectionResponse,
  GameResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  GeometryCompletenessSection,
  type GeometryCompletenessClient,
} from '@/features/imports/geometry-completeness-section';
import {
  GridShadowPanel,
  type GridShadowPanelClient,
} from '@/features/grid-shadow/grid-shadow-panel';
import {
  hasImageImport,
  isImageImport,
  readyBoardImportStaging,
  reviewableGames,
} from '@/features/reviewer-access/reviewer-access-state';
import {
  buildPreparedLocalReviewUrl,
  closePreparedLocalReviewerWindow,
  navigatePreparedLocalReviewerWindow,
  prepareLocalReviewerWindow,
} from '@/features/reviewer-access/reviewer-local-window';
import { startLocalReviewerProcess } from '@/features/reviewer-access/reviewer-local-start';

type GridReviewLauncherClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'listGames'
  | 'listJobs'
  | 'listReadyBrowserImageSelections'
  | 'startLocalReviewer'
>;

export function ReviewerAccessLauncher({
  apiBaseUrl,
  client,
  gameId: controlledGameId,
  onOpenImports,
}: {
  readonly apiBaseUrl: string;
  readonly client?: GridReviewLauncherClient &
    GeometryCompletenessClient &
    Partial<GridShadowPanelClient>;
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
  const gameIdRef = useRef(gameId);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshToken, setRefreshToken] = useState(0);
  const [localReviewUrl, setLocalReviewUrl] = useState<string | null>(null);
  const [openingLocal, setOpeningLocal] = useState(false);
  const openingLocalRef = useRef(false);

  useEffect(() => {
    gameIdRef.current = gameId;
  }, [gameId]);

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
        const selectedGameId =
          controlledGameId ??
          (availableGames.some((game) => game.id === gameIdRef.current)
            ? gameIdRef.current
            : firstGameId);
        if (controlledGameId === undefined) setGameId(selectedGameId);
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
  }, [api, controlledGameId, refreshToken]);

  const availableStaging = readyBoardImportStaging(readyStaging, gameId);
  const gameHasImageImport = hasImageImport(jobs, gameId);

  // The Reviewer opens scoped to the whole game; no per-import counts are
  // loaded here (a game-wide count would be expensive).
  const canOpenWork = gameId !== '' && !loading && !openingLocal;

  async function launchLocalReviewer() {
    if (!canOpenWork || openingLocalRef.current) return;
    setError('');
    setLocalReviewUrl(null);
    const reviewUrl = buildPreparedLocalReviewUrl(window.location.href, {
      gameId,
    });
    if (reviewUrl === null) {
      setLocalReviewUrl(null);
      setError(
        'Lokalny Reviewer można otworzyć wyłącznie z lokalnego panelu Admina.',
      );
      return;
    }
    const reviewerWindow = prepareLocalReviewerWindow(
      window.location.href,
      { gameId },
      (url, target) => window.open(url, target),
    );
    openingLocalRef.current = true;
    setOpeningLocal(true);
    try {
      const result = await startLocalReviewerProcess(api);
      if (!result.ok) {
        closePreparedLocalReviewerWindow(reviewerWindow);
        setError(result.error);
        return;
      }
      setLocalReviewUrl(reviewUrl);
      if (reviewerWindow === null) {
        setError(
          'Przeglądarka zablokowała nowe okno. Otwórz lokalny Reviewer z linku poniżej.',
        );
        return;
      }
      if (!navigatePreparedLocalReviewerWindow(reviewerWindow, reviewUrl)) {
        setError(
          'Reviewer działa, ale nie udało się odświeżyć jego okna. Otwórz go z linku poniżej.',
        );
      }
    } finally {
      openingLocalRef.current = false;
      setOpeningLocal(false);
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
          <h1>Korekta cięcia siatki</h1>
          <p className="lead">
            Otwórz lokalny Reviewer, aby poprawić siatkę plansz odrzuconych
            przez algorytm, zgłoszonych jako „Zła siatka” oraz zdjęć z brakami.
            Jedna plansza naraz; zapis nie zatwierdza symboli.
          </p>
        </div>
      </header>

      <div className="reviewerLauncherCard">
        <div className="reviewerLauncherControls">
          {controlledGameId === undefined ? (
            <label>
              Gra
              <select
                disabled={loading || openingLocal}
                onChange={(event) => {
                  setGameId(event.target.value);
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
          <button
            className="secondaryButton"
            disabled={loading || openingLocal}
            onClick={() => setRefreshToken((current) => current + 1)}
            type="button"
          >
            Odśwież kolejkę
          </button>
          <button
            className="secondaryButton"
            disabled={!canOpenWork}
            onClick={() => void launchLocalReviewer()}
            type="button"
          >
            {openingLocal ? 'Uruchamianie lokalnie…' : 'Otwórz lokalnie'}
          </button>
        </div>

        {!loading && !gameHasImageImport ? (
          <div className="reviewerPrerequisite" role="status">
            <div>
              <strong>
                {availableStaging.length > 0
                  ? 'Gotowy staging plansz czeka na uruchomienie importu'
                  : 'Brak uruchomionego importu plansz dla tej gry'}
              </strong>
              <p>
                {availableStaging.length > 0
                  ? `Staging „${availableStaging[0].displayName}” zawiera ${availableStaging[0].uploadedFileCount.toLocaleString('pl-PL')} plików, ale nie jest jeszcze jobem importu plansz. Wróć do Importu plansz, pokaż raport, przygotuj geometrię stron i jawnie rozpocznij import. Dopiero utworzony job z kolejką plansz pojawi się tutaj.`
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
      {gameId !== '' ? (
        <GeometryCompletenessSection
          key={gameId}
          api={api}
          gameId={gameId}
          importActive={jobs.some(
            (job) =>
              job.gameId === gameId &&
              ['created', 'processing'].includes(job.status),
          )}
          imports={jobs
            .filter((job) => job.gameId === gameId)
            .map((job) => ({
              id: job.id,
              label: `${'sourceDisplayName' in job.inputPayload ? (job.inputPayload.sourceDisplayName ?? 'Import obrazów') : 'Import obrazów'} · ${job.id.slice(0, 8)}`,
            }))}
          onOpenReviewer={() => void launchLocalReviewer()}
          openReviewerDisabled={!canOpenWork}
          refreshToken={refreshToken}
        />
      ) : null}
      {gameId !== '' && hasGridShadowPanelClient(api) ? (
        <GridShadowPanel key={gameId} api={api} gameId={gameId} />
      ) : null}
    </section>
  );
}

function hasGridShadowPanelClient(
  api: GridReviewLauncherClient & Partial<GridShadowPanelClient>,
): api is GridReviewLauncherClient & GridShadowPanelClient {
  return [
    'startGridShadowJob',
    'listGridShadowResults',
    'getGridShadowResult',
    'imageGridReviewSourceAssetUrl',
    'getJob',
  ].every(
    (method) =>
      typeof api[method as keyof GridShadowPanelClient] === 'function',
  );
}
