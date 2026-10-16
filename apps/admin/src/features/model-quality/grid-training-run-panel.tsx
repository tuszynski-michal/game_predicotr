'use client';

import type {
  AdminApiClient,
  GameResponse,
  GridCohortHeader,
  GridModelVersionResponse,
  GridTrainingRunPreview,
  GridTrainingRunView,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { usesNeuralGridConfiguration } from '@/features/games/game-catalog-state';
import {
  COHORT_PAGE_LIMIT,
  answeredRefusal,
  clearModelCommand,
  cohortLabel,
  gameLabel,
  modelCommandKey,
  readAllPages,
  readModelCommand,
  reasonLabel,
  reasonList,
  runLabel,
  saveModelCommand,
  type PendingModelCommand,
} from './grid-model-state';

export type GridTrainingRunClient = Pick<
  AdminApiClient,
  | 'listGames'
  | 'listGridModelVersions'
  | 'listGridTrainingCohorts'
  | 'previewGridTrainingRun'
  | 'listGridTrainingRuns'
  | 'createGridTrainingRun'
  | 'cancelGridTrainingRun'
  | 'resumeGridTrainingRun'
>;

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: GridTrainingRunClient;
  /** Changes when another step changed shared data (TASK-1000, P2-1). */
  readonly refreshKey?: number;
  readonly onChanged?: () => void;
  /** Read interval while a run is queued or training; it only reads. */
  readonly pollMs?: number;
}

// Lease state only says whether the GPU is free now; the backend queues the run anyway.
const ACTIVE = new Set(['created', 'processing']);
const QUEUE_ONLY = new Set(['GRID_RUN_LEASE_BUSY', 'GRID_RUN_LEASE_UNKNOWN']);

/** TASK-1000: start, follow, cancel and resume geometry training from frozen cohorts. */
export function GridTrainingRunPanel(props: Props) {
  return <RunPanel key={`${props.apiBaseUrl}:${props.gameId}`} {...props} />;
}

function RunPanel({
  apiBaseUrl,
  gameId,
  client,
  refreshKey = 0,
  onChanged,
  pollMs = 15000,
}: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const storageKey = modelCommandKey(apiBaseUrl, gameId, 'run');
  const [cohorts, setCohorts] = useState<readonly GridCohortHeader[]>([]);
  const [runs, setRuns] = useState<readonly GridTrainingRunView[]>([]);
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [versions, setVersions] = useState<readonly GridModelVersionResponse[]>(
    [],
  );
  const [cohortId, setCohortId] = useState('');
  const [preview, setPreview] = useState<GridTrainingRunPreview | null>(null);
  const [shared, setShared] = useState<Record<string, string>>({});
  const [sharedOptions, setSharedOptions] = useState<
    Record<string, readonly GridCohortHeader[]>
  >({});
  const [pending, setPending] = useState<PendingModelCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const previewRequest = useRef(0);
  const activeRuns = useRef(new Set<string>());
  const hasActive = runs.some((run) => ACTIVE.has(run.status));

  // While a run is queued or training the list is re-read; the panel never writes here.
  useEffect(() => {
    if (!hasActive) return;
    const timer = setInterval(() => {
      void Promise.resolve()
        .then(refresh)
        .catch(() => setError('Nie udało się odświeżyć treningów.'));
    }, pollMs);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasActive, pollMs]);

  async function refresh() {
    // Each read starts in its own promise: one failing read never leaves another unhandled.
    const [cohortList, runList] = await Promise.all([
      readAllPages((cursor) =>
        api.listGridTrainingCohorts(gameId, {
          cursor,
          limit: COHORT_PAGE_LIMIT,
        }),
      ),
      Promise.resolve().then(() => api.listGridTrainingRuns(gameId)),
    ]);
    if (cohortList)
      setCohorts(cohortList.filter((item) => item.gameId === gameId));
    if (runList.data) {
      const next = runList.data.items.filter((item) => item.gameId === gameId);
      // A run the worker finished elsewhere makes its candidate visible to later steps.
      const finished = next.some(
        (item) =>
          !ACTIVE.has(item.status) && activeRuns.current.has(item.runId),
      );
      activeRuns.current = new Set(
        next
          .filter((item) => ACTIVE.has(item.status))
          .map((item) => item.runId),
      );
      setRuns(next);
      if (finished) onChanged?.();
    }
    if (!cohortList || !runList.data)
      setError('Nie udało się pobrać kohort albo treningów.');
  }

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      try {
        setPending(readModelCommand(window.localStorage, storageKey));
      } catch (failure) {
        setError(failure instanceof Error ? failure.message : String(failure));
      }
      void Promise.resolve()
        .then(() => Promise.all([api.listGames(), api.listGridModelVersions()]))
        .then(([gameList, versionList]) => {
          if (cancelled) return;
          if (gameList.data) setGames(gameList.data);
          if (versionList.data) setVersions(versionList.data);
        })
        .catch(() => !cancelled && setError('Nie udało się pobrać katalogu.'));
      void refresh().catch(
        () => !cancelled && setError('Nie udało się pobrać treningów.'),
      );
    });
    return () => {
      cancelled = true;
    };
    // The panel is keyed by game: a new game mounts a fresh panel.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, gameId]);

  useEffect(() => {
    if (refreshKey === 0) return;
    let cancelled = false;
    void Promise.resolve()
      .then(refresh)
      .catch(() => !cancelled && setError('Nie udało się pobrać treningów.'));
    return () => {
      cancelled = true;
    };
    // Another step changed the data this panel lists.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function choose(id: string) {
    // Every change, also to the empty choice, invalidates a preview still on its way.
    const token = (previewRequest.current += 1);
    setCohortId(id);
    setPreview(null);
    if (!id) return;
    const result = await api.previewGridTrainingRun(gameId, id);
    if (token !== previewRequest.current) return;
    if (result.data === undefined) {
      setError(
        apiErrorMessage(result.error, 'Nie udało się odczytać podglądu runu.'),
      );
      return;
    }
    setPreview(result.data);
  }

  async function toggleShared(otherGame: string, enabled: boolean) {
    setShared((current) => {
      const next = { ...current };
      if (enabled) next[otherGame] = '';
      else delete next[otherGame];
      return next;
    });
    if (!enabled || sharedOptions[otherGame]) return;
    const items = await readAllPages((cursor) =>
      api.listGridTrainingCohorts(otherGame, {
        cursor,
        limit: COHORT_PAGE_LIMIT,
      }),
    ).catch(() => undefined);
    if (items === undefined) {
      setError('Nie udało się pobrać kohort innej gry.');
      return;
    }
    setSharedOptions((current) => ({
      ...current,
      [otherGame]: items.filter(
        (item) => item.gameId === otherGame && item.status === 'frozen',
      ),
    }));
  }

  const preset = preview?.presets.find(
    (item) => item.presetId === preview.selectedPresetId,
  );
  const blockers = (preview?.apiBlockers ?? []).filter(
    (code) => !QUEUE_ONLY.has(code),
  );
  const sharedComplete = Object.values(shared).every(Boolean);
  const startBlocker = !preview
    ? 'Wybierz zamrożoną kohortę'
    : blockers.length
      ? reasonList(blockers)
      : !preset
        ? reasonLabel('GRID_RUN_PRESET_NOT_APPROVED')
        : !sharedComplete
          ? 'Wybierz kohortę w każdej zaznaczonej grze'
          : null;

  async function send(command: PendingModelCommand) {
    setBusy(true);
    setError('');
    try {
      saveModelCommand(window.localStorage, storageKey, command);
      setPending(command);
      const body = command.body as Parameters<
        GridTrainingRunClient['createGridTrainingRun']
      >[1];
      const result = await api.createGridTrainingRun(gameId, body);
      if (result.data === undefined) {
        const refused = answeredRefusal(result);
        if (refused) {
          clearModelCommand(
            window.localStorage,
            storageKey,
            String(command.body.idempotencyKey),
          );
          setPending(null);
        }
        setError(
          `${apiErrorMessage(result.error, 'Nie potwierdzono zlecenia runu.')} ${
            refused
              ? 'Backend odrzucił zlecenie; zapisane polecenie usunięto.'
              : 'Zapisane polecenie można ponowić.'
          }`,
        );
        return;
      }
      clearModelCommand(
        window.localStorage,
        storageKey,
        String(command.body.idempotencyKey),
      );
      setPending(null);
      await refresh();
      onChanged?.();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'Nie potwierdzono zlecenia runu.',
      );
    } finally {
      setBusy(false);
    }
  }

  function start() {
    if (!preview || !preset || startBlocker) return;
    const sharedCohorts = Object.entries(shared).map(
      ([otherGame, otherCohort]) => ({
        gameId: otherGame,
        cohortId: otherCohort,
      }),
    );
    void send({
      kind: 'run',
      target: cohortId,
      body: {
        idempotencyKey: crypto.randomUUID(),
        cohortId,
        presetId: preset.presetId,
        presetFingerprint: preset.fingerprint,
        ...(sharedCohorts.length ? { sharedCohorts } : {}),
      },
    });
  }

  async function control(
    run: GridTrainingRunView,
    action: 'cancel' | 'resume',
  ) {
    setBusy(true);
    setError('');
    try {
      const result =
        action === 'cancel'
          ? await api.cancelGridTrainingRun(gameId, run.runId)
          : await api.resumeGridTrainingRun(gameId, run.runId);
      if (result.data === undefined)
        setError(
          apiErrorMessage(result.error, 'Polecenie runu nie zostało przyjęte.'),
        );
      await refresh();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  const otherGames = games.filter(
    (game) =>
      game.id !== gameId &&
      usesNeuralGridConfiguration(
        game.shapeGeometryConfiguration ?? null,
        game.code,
      ),
  );
  return (
    <section className="modelQualityPanel" aria-labelledby="grid-training-runs">
      <h3 id="grid-training-runs">Trening geometrii</h3>
      <p>
        Run dostraja przypisaną bazę na zamrożonej kohorcie. Kandydat jest tylko
        rejestrowany; publikacja i aktywacja to osobne decyzje.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {pending ? (
        <div>
          <p>Zapisane zlecenie runu czeka na potwierdzenie.</p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void send(pending)}
          >
            Ponów zapisane zlecenie
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              window.localStorage.removeItem(storageKey);
              setPending(null);
            }}
          >
            Porzuć zapisane zlecenie
          </button>
        </div>
      ) : null}
      <label>
        Zamrożona kohorta
        <select
          value={cohortId}
          disabled={busy}
          onChange={(event) => void choose(event.target.value)}
        >
          <option value="">Wybierz kohortę</option>
          {cohorts
            .filter((item) => item.status === 'frozen')
            .map((item) => (
              <option key={item.id} value={item.id}>
                {cohortLabel(item)}
              </option>
            ))}
        </select>
      </label>
      {preview ? (
        <div aria-label="Podgląd runu">
          <p>
            Preset: {preset ? `${preset.presetId}` : 'brak zatwierdzonego'} ·
            plan {preview.cost?.plannedSteps ?? '—'} kroków · kwalifikacja:{' '}
            {preview.cohortQualification === 'eligible' ? 'tak' : 'nie'}
          </p>
          {preview.cohortReasons.length ? (
            <p>Powody kohorty: {reasonList(preview.cohortReasons)}</p>
          ) : null}
          {preview.apiBlockers.length ? (
            <p>Blokady: {reasonList(preview.apiBlockers)}</p>
          ) : null}
          <p>Worker sprawdzi przed startem: GPU, środowisko, VRAM i budżet.</p>
        </div>
      ) : null}
      {otherGames.length ? (
        <fieldset disabled={busy}>
          <legend>Wspólny kandydat z innymi grami (opcjonalnie)</legend>
          {otherGames.map((game) => (
            <div key={game.id}>
              <label>
                <input
                  type="checkbox"
                  checked={game.id in shared}
                  onChange={(event) =>
                    void toggleShared(game.id, event.target.checked)
                  }
                />{' '}
                {gameLabel(game)}
              </label>
              {game.id in shared ? (
                <select
                  aria-label={`Kohorta gry ${game.name}`}
                  value={shared[game.id]}
                  onChange={(event) =>
                    setShared((current) => ({
                      ...current,
                      [game.id]: event.target.value,
                    }))
                  }
                >
                  <option value="">Wybierz kohortę</option>
                  {(sharedOptions[game.id] ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {cohortLabel(item)}
                    </option>
                  ))}
                </select>
              ) : null}
            </div>
          ))}
        </fieldset>
      ) : null}
      <button
        type="button"
        disabled={busy || pending !== null || startBlocker !== null}
        onClick={start}
      >
        Uruchom trening
      </button>
      {startBlocker && preview ? (
        <p>Start niedostępny: {startBlocker}</p>
      ) : null}
      <button
        type="button"
        disabled={busy}
        onClick={() =>
          void Promise.resolve()
            .then(refresh)
            .then(() => onChanged?.())
            .catch(() => setError('Nie udało się odświeżyć treningów.'))
        }
      >
        Odśwież stan treningów
      </button>
      <ul aria-label="Treningi gry">
        {runs.map((run) => (
          <li key={run.runId}>
            {runLabel(run, versions)} · postęp {run.progressCurrent}/
            {run.progressTotal ?? '?'}
            {run.errorCode ? ` · ${reasonLabel(run.errorCode)}` : ''}
            {['created', 'processing'].includes(run.status) &&
            !run.cancelRequested ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void control(run, 'cancel')}
              >
                Anuluj
              </button>
            ) : null}
            {['failed', 'cancelled'].includes(run.status) ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void control(run, 'resume')}
              >
                Wznów
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
