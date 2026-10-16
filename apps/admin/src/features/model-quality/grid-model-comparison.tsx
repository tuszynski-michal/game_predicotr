'use client';

import type {
  GameResponse,
  GridCohortHeader,
  GridModelEvaluationGame,
  GridModelEvaluationRole,
  GridModelEvaluationView,
  GridModelVersionResponse,
  GridTrainingRunView,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { usesNeuralGridConfiguration } from '@/features/games/game-catalog-state';
import {
  cohortLabel,
  gameLabel,
  gameName,
  readAllPages,
  reasonLabel,
  reasonList,
  runLabel,
  shortDate,
} from './grid-model-state';
import {
  comparisonMetrics,
  currentnessLabels,
  evaluationDecisionLabels,
  evaluationCommand,
  evaluationFinished,
  evaluationVerdictLabels,
  formatMetric,
  metricChange,
  needsCurrentnessCheck,
  type GridModelEvaluationClient,
  type PendingEvaluationCommand,
} from './grid-model-evaluation-state';

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: GridModelEvaluationClient;
  /** Changes when another step changed shared data (TASK-1000, P2-1). */
  readonly refreshKey?: number;
  readonly onChanged?: () => void;
}

/** TASK-0997: base versus candidate per game, role and recording; never publishes. */
export function GridModelComparison(props: Props) {
  return <Comparison key={`${props.apiBaseUrl}:${props.gameId}`} {...props} />;
}

function Comparison({
  apiBaseUrl,
  gameId,
  client,
  refreshKey = 0,
  onChanged,
}: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [runs, setRuns] = useState<readonly GridTrainingRunView[]>([]);
  const [runId, setRunId] = useState('');
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [versions, setVersions] = useState<readonly GridModelVersionResponse[]>(
    [],
  );
  // Other games of the family: game -> chosen frozen cohort, picked by name and label.
  const [others, setOthers] = useState<Record<string, string>>({});
  const [otherCohorts, setOtherCohorts] = useState<
    Record<string, readonly GridCohortHeader[]>
  >({});
  const [evaluations, setEvaluations] = useState<
    readonly GridModelEvaluationView[]
  >([]);
  const [selected, setSelected] = useState<GridModelEvaluationView | null>(
    null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<PendingEvaluationCommand | null>(null);
  // Responses for an earlier candidate or an earlier detail request are ignored.
  const currentVersion = useRef<string | null>(null);
  const openRequest = useRef(0);
  const run = runs.find((item) => item.runId === runId);
  const versionId = run?.candidateVersionId ?? null;

  useEffect(() => {
    currentVersion.current = versionId;
    openRequest.current += 1;
  }, [versionId]);

  useEffect(() => {
    let cancelled = false;
    void Promise.resolve()
      .then(() => Promise.all([api.listGames(), api.listGridModelVersions()]))
      .then(([gameList, versionList]) => {
        if (cancelled) return;
        if (gameList.data) setGames(gameList.data);
        if (versionList.data) setVersions(versionList.data);
      })
      .catch(() => !cancelled && setError('Nie udało się pobrać katalogu.'));
    void Promise.resolve()
      .then(() => api.listGridTrainingRuns(gameId))
      .then((result) => {
        if (cancelled) return;
        if (result.data === undefined) {
          setError(
            apiErrorMessage(result.error, 'Nie udało się pobrać treningów.'),
          );
          return;
        }
        setRuns(result.data.items.filter((item) => item.candidateVersionId));
      })
      .catch(() => !cancelled && setError('Nie udało się pobrać treningów.'));
    return () => {
      cancelled = true;
    };
    // refreshKey: a finished run or a new version elsewhere re-reads the lists.
  }, [api, gameId, refreshKey]);

  const refresh = useCallback(async () => {
    if (!versionId) return;
    const result = await api.listGridModelEvaluations(versionId);
    if (currentVersion.current !== versionId) return;
    if (result.data === undefined) {
      setError(apiErrorMessage(result.error, 'Nie udało się pobrać ocen.'));
      return;
    }
    setEvaluations(result.data.items);
  }, [api, versionId]);

  useEffect(() => {
    queueMicrotask(() => {
      setEvaluations([]);
      setSelected(null);
      void refresh();
    });
  }, [refresh]);

  async function open(evaluationId: string) {
    const requested = versionId;
    const token = (openRequest.current += 1);
    const result = await api.getGridModelEvaluation(evaluationId);
    if (token !== openRequest.current || currentVersion.current !== requested)
      return;
    if (result.data === undefined) {
      setError(apiErrorMessage(result.error, 'Nie udało się pobrać oceny.'));
      return;
    }
    setSelected(result.data);
  }

  async function toggleOther(other: string, enabled: boolean) {
    setOthers((current) => {
      const next = { ...current };
      if (enabled) next[other] = '';
      else delete next[other];
      return next;
    });
    if (!enabled || otherCohorts[other]) return;
    const items = await readAllPages((cursor) =>
      api.listGridTrainingCohorts(other, { cursor, limit: 100 }),
    ).catch(() => undefined);
    if (items === undefined) {
      setError('Nie udało się pobrać kohort innej gry.');
      return;
    }
    setOtherCohorts((current) => ({
      ...current,
      [other]: items.filter(
        (item) => item.gameId === other && item.status === 'frozen',
      ),
    }));
  }

  async function start() {
    if (!run || !versionId) return;
    if (Object.values(others).some((cohort) => !cohort)) {
      setError('Wybierz kohortę w każdej zaznaczonej grze.');
      return;
    }
    setBusy(true);
    setError('');
    // A shared run's other cohorts are always part of its evaluation (D-560).
    const shared = Object.fromEntries(
      (run.sharedCohorts ?? []).map((pin) => [pin.gameId, pin.cohortId]),
    );
    const cohorts = [
      { gameId, cohortId: run.cohortId },
      ...Object.entries({ ...others, ...shared }).map(([other, cohortId]) => ({
        gameId: other,
        cohortId,
      })),
    ];
    const command = evaluationCommand(
      pending.current,
      { versionId, cohorts },
      () => crypto.randomUUID(),
    );
    pending.current = command;
    const token = (openRequest.current += 1);
    try {
      const result = await api.createGridModelEvaluation({
        idempotencyKey: command.key,
        versionId,
        cohorts,
      });
      // The selector is locked while busy; the guard also covers a remount race.
      if (token !== openRequest.current || currentVersion.current !== versionId)
        return;
      if (result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się uruchomić oceny.'),
        );
        return;
      }
      pending.current = null;
      setSelected(result.data);
      await refresh();
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    if (!selected?.report) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.verifyGridModelEvaluationCurrentness(
        selected.reportId,
      );
      if (result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się sprawdzić aktualności.'),
        );
        return;
      }
      if (result.data.failures.length)
        setError(
          `Bez nowego dowodu: ${result.data.failures
            .map(
              (item) =>
                `${gameName(games, item.gameId)} (${reasonLabel(item.code)})`,
            )
            .join(', ')}`,
        );
      await open(selected.evaluationId);
      onChanged?.();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="modelQualityPanel"
      aria-labelledby="grid-model-comparison"
    >
      <h3 id="grid-model-comparison">Porównanie kandydata z bazą</h3>
      <p>
        Oba modele analizują te same zdjęcia kontrolne od oryginalnego obrazu.
        Ocena nie publikuje ani nie aktywuje modelu; regresja dowolnej gry
        blokuje wspólny wynik.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      <label>
        Kandydat z treningu
        <select
          value={runId}
          disabled={busy}
          onChange={(event) => setRunId(event.target.value)}
        >
          <option value="">Wybierz trening</option>
          {runs.map((item) => (
            <option key={item.runId} value={item.runId}>
              {runLabel(item, versions)}
            </option>
          ))}
        </select>
      </label>
      {run ? (
        <>
          <fieldset disabled={busy} aria-label="Pozostałe gry rodziny">
            <legend>Pozostałe gry tej rodziny</legend>
            {games
              .filter(
                (game) =>
                  game.id !== gameId &&
                  !(run.sharedCohorts ?? []).some(
                    (pin) => pin.gameId === game.id,
                  ) &&
                  usesNeuralGridConfiguration(
                    game.shapeGeometryConfiguration ?? null,
                    game.code,
                  ),
              )
              .map((game) => (
                <div key={game.id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={game.id in others}
                      onChange={(event) =>
                        void toggleOther(game.id, event.target.checked)
                      }
                    />{' '}
                    {gameLabel(game)}
                  </label>
                  {game.id in others ? (
                    <select
                      aria-label={`Kohorta oceny gry ${game.name}`}
                      value={others[game.id]}
                      onChange={(event) =>
                        setOthers((current) => ({
                          ...current,
                          [game.id]: event.target.value,
                        }))
                      }
                    >
                      <option value="">Wybierz kohortę</option>
                      {(otherCohorts[game.id] ?? []).map((item) => (
                        <option key={item.id} value={item.id}>
                          {cohortLabel(item)}
                        </option>
                      ))}
                    </select>
                  ) : null}
                </div>
              ))}
            {(run.sharedCohorts ?? []).length ? (
              <p>
                Kohorty wspólnego treningu są oceniane zawsze:{' '}
                {(run.sharedCohorts ?? [])
                  .map((pin) => gameName(games, pin.gameId))
                  .join(', ')}
              </p>
            ) : null}
          </fieldset>
          <button type="button" disabled={busy} onClick={() => void start()}>
            Uruchom ocenę
          </button>
          <ul>
            {evaluations.map((item) => (
              <li key={item.evaluationId}>
                <button
                  type="button"
                  onClick={() => void open(item.evaluationId)}
                >
                  {shortDate(item.createdAt)} · {item.status}
                  {item.verdict
                    ? ` · ${evaluationVerdictLabels[item.verdict]}`
                    : ''}
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {selected ? (
        <EvaluationDetail
          view={selected}
          games={games}
          busy={busy}
          onRefresh={() => void open(selected.evaluationId)}
          onVerify={() => void verify()}
        />
      ) : null}
    </section>
  );
}

function EvaluationDetail({
  view,
  games,
  busy,
  onRefresh,
  onVerify,
}: {
  readonly view: GridModelEvaluationView;
  readonly games: readonly GameResponse[];
  readonly busy: boolean;
  readonly onRefresh: () => void;
  readonly onVerify: () => void;
}) {
  const report = view.report;
  return (
    <article aria-label="Wynik oceny">
      <p>
        Stan: {view.status} · postęp {view.progressCurrent}/
        {view.progressTotal ?? '?'}
        {view.errorCode ? ` · błąd ${view.errorCode}` : ''}
      </p>
      {!evaluationFinished(view) ? (
        <button type="button" onClick={onRefresh}>
          Odśwież
        </button>
      ) : null}
      {report ? (
        <>
          <p>
            Werdykt: <strong>{evaluationVerdictLabels[report.verdict]}</strong>{' '}
            · polityka {report.policyVersion} · parity{' '}
            {report.parity.passed ? 'zaliczone' : 'niezaliczone'}
          </p>
          <ul aria-label="Aktualność dowodów">
            {view.currentness.map((state) => (
              <li key={state.gameId}>
                {gameName(games, state.gameId)}:{' '}
                {currentnessLabels[state.state]}
              </li>
            ))}
          </ul>
          {needsCurrentnessCheck(view.currentness) ? (
            <button type="button" disabled={busy} onClick={onVerify}>
              Sprawdź aktualność
            </button>
          ) : null}
          {report.games.map((game) => (
            <GameComparison key={game.gameId} game={game} games={games} />
          ))}
        </>
      ) : null}
    </article>
  );
}

function GameComparison({
  game,
  games,
}: {
  readonly game: GridModelEvaluationGame;
  readonly games: readonly GameResponse[];
}) {
  return (
    <section aria-label={`Gra ${gameName(games, game.gameId)}`}>
      <h4>
        Gra {gameName(games, game.gameId)} · {game.mode}
      </h4>
      <p>
        Walidacja: {evaluationDecisionLabels[game.validation]} · regresja:{' '}
        {evaluationDecisionLabels[game.regression]} · pokrycie: {game.coverage}
      </p>
      {game.reasons.length ? <p>Powody: {reasonList(game.reasons)}</p> : null}
      <RoleTable title="VALIDATION" role={game.roles.VALIDATION} />
      <RoleTable
        title="REGRESSION (tylko końcowa kontrola)"
        role={game.roles.REGRESSION}
      />
    </section>
  );
}

function RoleTable({
  title,
  role,
}: {
  readonly title: string;
  readonly role: GridModelEvaluationRole;
}) {
  return (
    <table>
      <caption>{title}</caption>
      <thead>
        <tr>
          <th>Miara</th>
          <th>Baza</th>
          <th>Kandydat</th>
          {role.recordings.map((recording) => (
            <th key={recording.groupId}>
              Nagranie {recording.groupId.slice(0, 8)}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {comparisonMetrics.map((metric) => (
          <tr
            key={metric.key}
            data-change={metricChange(
              role.base,
              role.candidate,
              metric.key,
              metric.better,
            )}
          >
            <th>{metric.label}</th>
            <td>{formatMetric(role.base[metric.key])}</td>
            <td>{formatMetric(role.candidate[metric.key])}</td>
            {role.recordings.map((recording) => (
              <td key={recording.groupId}>
                {formatMetric(recording.base[metric.key])} →{' '}
                {formatMetric(recording.candidate[metric.key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
