'use client';

import type {
  AdminApiClient,
  GameResponse,
  GridCorrectionLearningPreview,
  GridCorrectionLearningView,
  GridModelDefaultResponse,
  GridModelEvaluationView,
  GridModelHistoryEvent,
  GridModelVersionResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { GridCorrectionApplyPanel } from './grid-correction-apply-panel';
import {
  archiveLearningCommand,
  clearLearningCommand,
  learningActive,
  learningCommandKey,
  learningRole,
  learningStage,
  learningStatus,
  readLearningCommand,
  type LearningCommand,
} from './grid-correction-learning-state';
import {
  answeredRefusal,
  gameName,
  reasonLabel,
  shortDate,
  versionName,
} from './grid-model-state';

export type GridCorrectionLearningClient = Pick<
  AdminApiClient,
  | 'getGridCorrectionLearningReady'
  | 'previewGridCorrectionLearning'
  | 'startGridCorrectionLearning'
  | 'listGridCorrectionLearning'
  | 'getGridCorrectionLearning'
  | 'cancelGridCorrectionLearning'
  | 'resumeGridCorrectionLearning'
  | 'getGridCorrectionLearningEvaluation'
  | 'verifyGridModelEvaluationCurrentness'
  | 'getGridModelDefault'
  | 'listGridModelVersions'
  | 'listGames'
  | 'getGameGridModelHistory'
  | 'getGameGridModelAssignment'
  | 'rollbackGameGridModel'
  | 'previewGridCorrectionApply'
  | 'startGridCorrectionApply'
  | 'listGridCorrectionApply'
  | 'getGridCorrectionApply'
  | 'resumeGridCorrectionApply'
>;

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: GridCorrectionLearningClient;
  readonly onChanged?: () => void;
}

export function GridCorrectionLearningPanel(props: Props) {
  return <Learning key={`${props.apiBaseUrl}:${props.gameId}`} {...props} />;
}

function Learning({ apiBaseUrl, gameId, client, onChanged }: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const storageKey = learningCommandKey(apiBaseUrl, gameId);
  const [ready, setReady] = useState<GridCorrectionLearningPreview | null>(
    null,
  );
  const [defaults, setDefaults] = useState<GridModelDefaultResponse | null>(
    null,
  );
  const [runs, setRuns] = useState<readonly GridCorrectionLearningView[]>([]);
  const [games, setGames] = useState<readonly GameResponse[]>([]);
  const [versions, setVersions] = useState<readonly GridModelVersionResponse[]>(
    [],
  );
  const [history, setHistory] = useState<readonly GridModelHistoryEvent[]>([]);
  const [selected, setSelected] = useState<GridCorrectionLearningView | null>(
    null,
  );
  const [evaluation, setEvaluation] = useState<GridModelEvaluationView | null>(
    null,
  );
  const [pending, setPending] = useState<LearningCommand | null>(null);
  const [corrupt, setCorrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [checkingCurrentness, setCheckingCurrentness] = useState(false);
  const [evaluationReading, setEvaluationReading] = useState(false);
  const [evaluationReadError, setEvaluationReadError] = useState('');
  const [currentnessUnconfirmed, setCurrentnessUnconfirmed] = useState(false);
  const [currentnessError, setCurrentnessError] = useState('');
  const [currentnessNotice, setCurrentnessNotice] = useState('');
  const [applyRefreshKey, setApplyRefreshKey] = useState(0);
  const [rollbackTarget, setRollbackTarget] = useState('');
  const [rollbackConfirmed, setRollbackConfirmed] = useState(false);
  const [exclusions, setExclusions] = useState<
    Record<string, { reason: string; confirmed: boolean }>
  >({});
  const generation = useRef(0);
  const readSequence = useRef(0);
  const chosen = useRef('');
  const locked = useRef(false);
  const refreshInFlight = useRef(false);
  const currentnessSequence = useRef(0);
  const currentnessInFlight = useRef(false);

  function invalidateCurrentnessCheck() {
    currentnessSequence.current += 1;
    currentnessInFlight.current = false;
    setCheckingCurrentness(false);
    setCurrentnessError('');
    setCurrentnessNotice('');
  }

  async function refresh() {
    invalidateCurrentnessCheck();
    setEvaluationReading(true);
    const token = ++readSequence.current;
    generation.current += 1;
    refreshInFlight.current = true;
    setRefreshing(true);
    setError('');
    const current = () => token === readSequence.current;
    async function retainChosenOnListFailure(failure: unknown): Promise<never> {
      // Refresh invalidated the previous detail request, so a failed list must
      // still re-read the operator's selection instead of stranding the old one.
      if (current() && chosen.current) await open(chosen.current);
      throw failure;
    }
    try {
      const results = await Promise.allSettled([
        api
          .getGridCorrectionLearningReady(gameId)
          .then((result) => {
            if (!current()) return;
            if (!result.data)
              throw new Error('Nie udało się odczytać gotowości korekt.');
            if (result.data.gameId !== gameId)
              throw new Error('Odpowiedź dotyczy innej gry.');
            setReady(result.data);
            setExclusions({});
          })
          .finally(() => {
            if (current()) setLoading(false);
          }),
        api.getGridModelDefault().then((result) => {
          if (!current()) return;
          if (!result.data)
            throw new Error('Nie udało się odczytać modelu domyślnego.');
          setDefaults(result.data);
        }),
        api.listGridCorrectionLearning(gameId).then(async (result) => {
          if (!current()) return;
          if (!result.data)
            return retainChosenOnListFailure(
              new Error('Nie udało się odczytać przebiegów uczenia.'),
            );
          setRuns(result.data.items);
          // Status does not wait for the more expensive readiness calculation.
          // Existing workflows are read only; no POST is replayed after reload.
          const active =
            result.data.items.find(
              (item) => item.learningId === chosen.current,
            ) ?? result.data.items[0];
          if (active) await open(active.learningId);
          else {
            chosen.current = '';
            generation.current += 1;
            setSelected(null);
            setEvaluation(null);
            setEvaluationReading(false);
            setEvaluationReadError('');
          }
        }, retainChosenOnListFailure),
        api.listGames().then((result) => {
          if (!current()) return;
          if (!result.data) throw new Error('Nie udało się odczytać gier.');
          setGames(result.data);
        }),
        api.listGridModelVersions().then((result) => {
          if (!current()) return;
          if (!result.data)
            throw new Error('Nie udało się odczytać wersji modeli.');
          setVersions(result.data);
        }),
        api.getGameGridModelHistory(gameId).then((result) => {
          if (!current()) return;
          if (!result.data)
            throw new Error('Nie udało się odczytać historii modeli.');
          setHistory(result.data);
        }),
      ]);
      if (!current()) return;
      const failures = results.filter((result) => result.status === 'rejected');
      if (failures.length)
        setError(failures.map((result) => String(result.reason)).join(' '));
      else setRefreshedAt(Date.now());
    } finally {
      if (current()) {
        refreshInFlight.current = false;
        setRefreshing(false);
      }
    }
  }

  async function open(id: string) {
    invalidateCurrentnessCheck();
    setEvaluationReading(true);
    setEvaluationReadError('');
    if (chosen.current !== id) {
      setSelected(null);
      setEvaluation(null);
    }
    chosen.current = id;
    const token = ++generation.current;
    try {
      const result = await api.getGridCorrectionLearning(gameId, id);
      if (token !== generation.current) return;
      if (
        !result.data ||
        result.data.gameId !== gameId ||
        result.data.learningId !== id
      )
        throw new Error('Nie udało się odczytać przebiegu uczenia.');
      setSelected(result.data);
      setEvaluation((existing) =>
        existing?.evaluationId === result.data.evaluationId ? existing : null,
      );
      setRuns((current) =>
        current.map((run) => (run.learningId === id ? result.data : run)),
      );
      if (result.data.evaluationId) {
        const report = await api.getGridCorrectionLearningEvaluation(
          gameId,
          id,
        );
        if (token !== generation.current) return;
        if (
          !report.data ||
          report.data.evaluationId !== result.data.evaluationId
        )
          throw new Error('Nie udało się odczytać raportu oceny.');
        setEvaluation(report.data);
        setApplyRefreshKey((current) => current + 1);
      } else setEvaluation(null);
      setCurrentnessUnconfirmed(false);
    } catch (failure) {
      if (token !== generation.current) return;
      const message = `${failure instanceof Error ? failure.message : String(failure)} Kliknij „Odśwież stan uczenia”, aby ponowić odczyt.`;
      setEvaluationReadError(message);
      throw new Error(message);
    } finally {
      if (token === generation.current) setEvaluationReading(false);
    }
  }

  async function verifyCurrentness() {
    if (
      currentnessInFlight.current ||
      !selected?.evaluationId ||
      !evaluation?.reportId ||
      evaluation.status !== 'completed' ||
      !evaluation.report ||
      evaluationReading ||
      Boolean(evaluationReadError) ||
      selected.evaluationId !== evaluation.evaluationId
    )
      return;
    currentnessInFlight.current = true;
    const token = ++currentnessSequence.current;
    const selection = generation.current;
    const learningId = selected.learningId;
    const evaluationId = evaluation.evaluationId;
    const reportId = evaluation.reportId;
    const current = () =>
      token === currentnessSequence.current &&
      selection === generation.current &&
      chosen.current === learningId;
    setCheckingCurrentness(true);
    setCurrentnessUnconfirmed(true);
    setCurrentnessError('');
    setCurrentnessNotice('');
    try {
      const result = await api.verifyGridModelEvaluationCurrentness(reportId);
      if (!current()) return;
      if (!result.data || result.data.reportId !== reportId)
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie potwierdzono aktualności oceny. Sprawdź ponownie.',
          ),
        );
      const report = await api.getGridCorrectionLearningEvaluation(
        gameId,
        learningId,
      );
      if (!current()) return;
      if (
        !report.data ||
        report.data.evaluationId !== evaluationId ||
        report.data.reportId !== reportId
      )
        throw new Error(
          'Nie udało się odczytać aktualnej oceny. Sprawdź ponownie.',
        );
      setEvaluation(report.data);
      setApplyRefreshKey((value) => value + 1);
      const failures = result.data.failures;
      if (failures.length)
        throw new Error(
          `Dowód nadal zablokowany: ${failures
            .map(
              (item) =>
                `${gameName(games, item.gameId)}: ${reasonLabel(item.code)}`,
            )
            .join('; ')}.`,
        );
      if (
        report.data.status !== 'completed' ||
        !report.data.report ||
        !report.data.currentness.length ||
        report.data.currentness.some((item) => item.state !== 'current')
      )
        throw new Error(
          'Ocena nadal wymaga aktualnego dowodu. Zastosowanie jest zablokowane.',
        );
      setCurrentnessUnconfirmed(false);
      setCurrentnessNotice(
        'Aktualność oceny potwierdzona. Podgląd zastosowania jest odświeżany.',
      );
    } catch (failure) {
      if (current())
        setCurrentnessError(
          failure instanceof Error ? failure.message : String(failure),
        );
    } finally {
      if (current()) {
        currentnessInFlight.current = false;
        setCheckingCurrentness(false);
      }
    }
  }

  useEffect(() => {
    let alive = true;
    queueMicrotask(() => {
      if (!alive) return;
      try {
        setPending(readLearningCommand(window.localStorage, storageKey));
      } catch (failure) {
        setCorrupt(true);
        setError(String(failure));
      }
      void refresh().catch((failure) => {
        if (alive) {
          setError(String(failure));
          setLoading(false);
        }
      });
    });
    return () => {
      alive = false;
      currentnessSequence.current += 1;
      generation.current += 1;
      readSequence.current += 1;
    };
    // The keyed panel owns exactly one game and API instance.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, gameId, storageKey]);

  useEffect(() => {
    if (!selected || !learningActive(selected.status)) return;
    const timer = window.setInterval(() => {
      void open(selected.learningId).catch((failure) =>
        setError(String(failure)),
      );
    }, 15_000);
    return () => window.clearInterval(timer);
    // Only the active selection is polled, by GET.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected?.learningId, selected?.status]);

  async function send(command: LearningCommand) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(command));
      setPending(command);
      let result;
      if (command.kind === 'start')
        result = await api.startGridCorrectionLearning(gameId, command.body);
      else if (command.kind === 'cancel')
        result = await api.cancelGridCorrectionLearning(gameId, command.target);
      else if (command.kind === 'resume')
        result = await api.resumeGridCorrectionLearning(gameId, command.target);
      else result = await api.rollbackGameGridModel(gameId, command.body);
      if (result.data || answeredRefusal(result)) {
        clearLearningCommand(window.localStorage, storageKey, command.key);
        setPending(null);
      }
      if (!result.data) {
        if (answeredRefusal(result)) await refresh();
        throw new Error(
          apiErrorMessage(
            result.error,
            'Nie potwierdzono wykonania. Ponów zapisane polecenie.',
          ),
        );
      }
      if ('learningId' in result.data) chosen.current = result.data.learningId;
      setNotice(
        command.kind === 'rollback'
          ? 'Przywrócono wersję dla nowych importów.'
          : 'Polecenie zapisane.',
      );
      setRollbackTarget('');
      setRollbackConfirmed(false);
      onChanged?.();
      await refresh();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : String(failure));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  }

  async function previewExclusions() {
    setBusy(true);
    setError('');
    try {
      const result = await api.previewGridCorrectionLearning(gameId, {
        importJobIds: [],
        exclusions: Object.entries(exclusions).map(([id, value]) => ({
          gameId: id,
          ...value,
        })),
      });
      if (!result.data || result.data.gameId !== gameId)
        throw new Error(
          apiErrorMessage(result.error, 'Nie udało się sprawdzić wyłączeń.'),
        );
      setReady(result.data);
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }

  async function rollback() {
    if (!rollbackTarget || !rollbackConfirmed) return;
    setBusy(true);
    setError('');
    try {
      const assignment = await api.getGameGridModelAssignment(gameId);
      if (
        !assignment.data ||
        assignment.data.gameId !== gameId ||
        assignment.data.revision === null
      )
        throw new Error('Nie udało się odczytać rewizji przypisania.');
      const key = crypto.randomUUID();
      await send({
        kind: 'rollback',
        target: rollbackTarget,
        key,
        body: {
          idempotencyKey: key,
          expectedRevision: assignment.data.revision,
          versionId: rollbackTarget,
        },
      });
    } catch (failure) {
      setError(String(failure));
    } finally {
      setBusy(false);
    }
  }

  const disabled = busy || pending !== null || corrupt;
  const evaluationComplete =
    evaluation?.status === 'completed' && Boolean(evaluation.report);
  const rollbackVersions = [...new Set(history.map((item) => item.versionId))];
  const exclusionsMatch =
    JSON.stringify(
      Object.entries(exclusions)
        .sort()
        .map(([id, value]) => ({ gameId: id, ...value })),
    ) ===
    JSON.stringify(
      [...(ready?.exclusions ?? [])].sort((a, b) =>
        a.gameId.localeCompare(b.gameId),
      ),
    );
  return (
    <section
      className="gridCorrectionLearning"
      aria-label="Uczenie siatek z korekt"
    >
      <h3>Ulepsz siatki z korekt</h3>
      <p>
        Wspólny model:{' '}
        {defaults?.version
          ? versionName(versions, defaults.version.manifest.versionId)
          : loading || (refreshing && defaults === null)
            ? 'Wczytywanie…'
            : defaults === null
              ? 'Nie udało się ustalić wersji'
              : 'Brak wersji domyślnej'}
        .
      </p>
      <p>
        Uczenie i ocena tworzą kandydata. Zastosowanie wersji wymaga osobnego
        potwierdzenia i dotyczy nowych importów.
      </p>
      {loading ? <p aria-busy="true">Sprawdzanie dostępnych korekt…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {corrupt ? (
        <p role="alert">
          Nieczytelne zapisane polecenie blokuje nowe zmiany. Zachowaj je przed
          odłożeniem.
        </p>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {pending ? (
        <aside aria-label="Niepotwierdzone polecenie">
          <p>
            Odpowiedź nie została potwierdzona. Zapisane polecenie pozostaje po
            przeładowaniu.
          </p>
          <button
            className="secondaryButton"
            type="button"
            disabled={busy}
            onClick={() => void send(pending)}
          >
            Ponów zapisane polecenie uczenia
          </button>
        </aside>
      ) : null}
      {pending || corrupt ? (
        <button
          className="secondaryButton"
          type="button"
          disabled={busy}
          onClick={() => {
            try {
              archiveLearningCommand(window.localStorage, storageKey);
              setPending(null);
              setCorrupt(false);
              setError('');
            } catch (failure) {
              setError(String(failure));
            }
          }}
        >
          Zachowaj i odłóż polecenie
        </button>
      ) : null}
      <button
        className="secondaryButton"
        type="button"
        disabled={busy || refreshing}
        aria-busy={refreshing}
        onClick={() => {
          if (refreshInFlight.current) return;
          void refresh().catch((failure) => setError(String(failure)));
        }}
      >
        {refreshing ? 'Odświeżanie stanu uczenia…' : 'Odśwież stan uczenia'}
      </button>
      {refreshedAt !== null ? (
        <p role="status">
          Stan odświeżony: {new Date(refreshedAt).toLocaleTimeString('pl-PL')}.
        </p>
      ) : null}
      {ready ? (
        <>
          <section aria-label="Dostępność zapisanych korekt">
            <h4>Dane do następnego uczenia</h4>
            <LearningProgress preview={ready} />
            {ready.dataAvailability ? (
              <>
                <p>
                  Dostępne przed buforami: {ready.dataAvailability.photos} zdjęć
                  / {ready.dataAvailability.boards} plansz po usunięciu kopii.
                </p>
                <p>
                  Sumaryczne minima: {ready.dataAvailability.minimumPhotos}{' '}
                  zdjęć / {ready.dataAvailability.minimumBoards} plansz. Brakuje
                  co najmniej: {ready.dataAvailability.photoDeficit} zdjęć /{' '}
                  {ready.dataAvailability.boardDeficit} plansz.
                </p>
                {ready.dataAvailability.splitStatus === 'minima' ? (
                  <p>
                    Za mało zapisanych korekt do minimów. Bufory i ochrona
                    danych mogą wymagać kolejnych zdjęć.
                  </p>
                ) : null}
                {ready.dataAvailability.splitStatus === 'infeasible' ? (
                  <p>
                    Sumaryczne minima nie wystarczają: bufory lub ochrona danych
                    uniemożliwiają bezpieczny podział. Start pozostaje
                    zablokowany.
                  </p>
                ) : null}
              </>
            ) : (
              <p>
                Liczba dostępnych korekt i braków nie została ustalona. Sprawdź
                przyczynę blokady.
              </p>
            )}
          </section>
          {!ready.progressCounts && ready.roleCounts.length ? (
            <>
              <table>
                <caption>Dostępne korekty po podziale i buforach</caption>
                <thead>
                  <tr>
                    <th>Przeznaczenie</th>
                    <th>Zdjęcia</th>
                    <th>Plansze</th>
                  </tr>
                </thead>
                <tbody>
                  {ready.roleCounts.map((role) => (
                    <tr key={role.role}>
                      <th>{learningRole[role.role]}</th>
                      <td>{role.photos}</td>
                      <td>{role.boards}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p>
                Zdjęcia buforowe: {ready.bufferPhotos}. Minima: uczenie 30
                plansz / 10 zdjęć; dobór i kontrola po 15 plansz / 5 zdjęć.
              </p>
            </>
          ) : !ready.progressCounts ? (
            <p>
              Podział na uczenie, dobór modelu i kontrolę końcową nie jest
              gotowy.
            </p>
          ) : null}
          <p>
            Zakres oceny:{' '}
            {ready.requiredGameIds.map((id) => gameName(games, id)).join(', ')}.
          </p>
          {!ready.priorScopeDocumented ? (
            <p>
              Historyczny zakres poprzedniej wersji nie jest udokumentowany.
            </p>
          ) : null}
          <p>
            Dowód oparty na zdjęciach. Nie potwierdza niezależności sesji ani
            nieznanego wcześniejszego użycia danych.
          </p>
          <ul>
            {ready.limitations.map((value) => (
              <li key={value}>{reasonLabel(value)}</li>
            ))}
          </ul>
          {ready.blockers.length ? (
            <ul aria-label="Braki blokujące uczenie">
              {ready.blockers.map((code) => (
                <li key={code}>{reasonLabel(code)}</li>
              ))}
            </ul>
          ) : null}
          <details>
            <summary>Zaawansowane: zakres oceny</summary>
            <p>
              Wyłączenie gry zachowuje historię i dane kontrolne. Wyłączona gra
              nie otrzyma nowej wersji.
            </p>
            {ready.priorGameIds
              .filter((id) => id !== gameId)
              .map((id) => (
                <fieldset key={id} disabled={disabled}>
                  <legend>{gameName(games, id)}</legend>
                  <label>
                    <input
                      type="checkbox"
                      checked={id in exclusions}
                      onChange={(event) => {
                        setExclusions((current) => {
                          const next = { ...current };
                          if (event.target.checked)
                            next[id] = { reason: '', confirmed: false };
                          else delete next[id];
                          return next;
                        });
                      }}
                    />
                    Wyłącz z nowej oceny
                  </label>
                  {exclusions[id] ? (
                    <>
                      <label>
                        Powód wyłączenia
                        <input
                          value={exclusions[id].reason}
                          onChange={(event) =>
                            setExclusions((current) => ({
                              ...current,
                              [id]: {
                                ...current[id],
                                reason: event.target.value,
                              },
                            }))
                          }
                        />
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={exclusions[id].confirmed}
                          onChange={(event) =>
                            setExclusions((current) => ({
                              ...current,
                              [id]: {
                                ...current[id],
                                confirmed: event.target.checked,
                              },
                            }))
                          }
                        />
                        Potwierdzam zawężenie oceny tej gry
                      </label>
                    </>
                  ) : null}
                </fieldset>
              ))}
            <button
              className="secondaryButton"
              type="button"
              disabled={
                disabled ||
                Object.values(exclusions).some(
                  (value) => !value.reason.trim() || !value.confirmed,
                )
              }
              onClick={() => void previewExclusions()}
            >
              Sprawdź zakres oceny
            </button>
          </details>
          {ready.pendingWorkerChecks.length ? (
            <p>
              Przy starcie worker sprawdzi:{' '}
              {ready.pendingWorkerChecks.map(reasonLabel).join('; ')}.
            </p>
          ) : null}
          <button
            className="primaryButton"
            type="button"
            disabled={
              disabled ||
              !ready.canStart ||
              !exclusionsMatch ||
              runs.some((item) => learningActive(item.status))
            }
            onClick={() => {
              const key = crypto.randomUUID();
              void send({
                kind: 'start',
                key,
                target: gameId,
                body: {
                  idempotencyKey: key,
                  previewSha256: ready.previewSha256,
                  importJobIds: ready.importJobIds,
                  exclusions: ready.exclusions,
                },
              });
            }}
          >
            Ulepsz siatki z korekt
          </button>
        </>
      ) : null}
      <h4>Przebiegi uczenia</h4>
      {!runs.length && !loading && !refreshing ? (
        <p>Brak wcześniejszych przebiegów uczenia.</p>
      ) : null}
      <ul className="gridCorrectionRunList" aria-label="Przebiegi uczenia">
        {runs.map((run) => (
          <li key={run.learningId}>
            <button
              className="primaryButton gridCorrectionRunButton"
              type="button"
              disabled={busy}
              onClick={() =>
                void open(run.learningId).catch((failure) =>
                  setError(String(failure)),
                )
              }
            >
              {shortDate(run.createdAt)} · {learningStatus[run.status]}
              {run.verdict ? ` · ${run.verdict}` : ''}
            </button>
          </li>
        ))}
      </ul>
      {selected ? (
        <article aria-label="Postęp uczenia">
          <p>
            Stan: {learningStatus[selected.status]} · {learningStage(selected)}
            {selected.errorCode ? ` · ${reasonLabel(selected.errorCode)}` : ''}
          </p>
          {learningActive(selected.status) ? (
            <button
              className="secondaryButton"
              type="button"
              disabled={disabled}
              onClick={() =>
                void send({
                  kind: 'cancel',
                  key: crypto.randomUUID(),
                  target: selected.learningId,
                })
              }
            >
              Anuluj uczenie
            </button>
          ) : null}
          {['failed', 'cancelled'].includes(selected.status) ? (
            <button
              className="primaryButton"
              type="button"
              disabled={disabled}
              onClick={() =>
                void send({
                  kind: 'resume',
                  key: crypto.randomUUID(),
                  target: selected.learningId,
                })
              }
            >
              Wznów uczenie
            </button>
          ) : null}
          {evaluation ? (
            <LearningReport view={evaluation} games={games} />
          ) : null}
          {selected.evaluationId ? (
            <section aria-label="Aktualność oceny">
              {evaluationReading ? (
                <p role="status" aria-busy="true">
                  Odczytywanie oceny…
                </p>
              ) : evaluationReadError ? (
                <p role="alert">{evaluationReadError}</p>
              ) : !evaluationComplete ? (
                <p>
                  {evaluation &&
                  ['created', 'processing', 'waiting_for_review'].includes(
                    evaluation.status,
                  )
                    ? 'Ocena jeszcze trwa. Sprawdzenie aktualności będzie dostępne po zakończeniu raportu.'
                    : 'Brak zakończonego raportu oceny. Odśwież stan uczenia, aby ponowić odczyt.'}
                </p>
              ) : (
                <p>
                  Wynik dotyczy zakończonego przebiegu. Nowe korekty nie
                  zmieniają jego wyniku. Sprawdzenie aktualności odczytuje
                  zapisane dowody; nie rozpoczyna uczenia ani zastosowania
                  modelu.
                </p>
              )}
              <button
                className="secondaryButton"
                type="button"
                disabled={
                  busy ||
                  evaluationReading ||
                  Boolean(evaluationReadError) ||
                  checkingCurrentness ||
                  !evaluation?.reportId ||
                  !evaluationComplete
                }
                aria-busy={checkingCurrentness}
                onClick={() => void verifyCurrentness()}
              >
                {checkingCurrentness
                  ? 'Sprawdzanie aktualności oceny…'
                  : 'Sprawdź aktualność oceny'}
              </button>
              {checkingCurrentness ? (
                <p role="status">Trwa sprawdzanie dowodów oceny…</p>
              ) : null}
              {currentnessError ? <p role="alert">{currentnessError}</p> : null}
              {currentnessNotice ? (
                <p role="status">{currentnessNotice}</p>
              ) : null}
            </section>
          ) : null}
          {selected.verdict === 'PASS' ? (
            <GridCorrectionApplyPanel
              api={api}
              apiBaseUrl={apiBaseUrl}
              gameId={gameId}
              learning={selected}
              games={games}
              versions={versions}
              previewRefreshKey={applyRefreshKey}
              evidenceBlocked={
                checkingCurrentness ||
                evaluationReading ||
                Boolean(evaluationReadError) ||
                currentnessUnconfirmed ||
                Boolean(
                  selected.evaluationId &&
                  (!evaluation ||
                    !evaluationComplete ||
                    evaluation.evaluationId !== selected.evaluationId ||
                    !evaluation.currentness?.length ||
                    evaluation.currentness.some(
                      (item) => item.state !== 'current',
                    )),
                )
              }
              onChanged={() => {
                onChanged?.();
                void refresh().catch((failure) => setError(String(failure)));
              }}
            />
          ) : null}
        </article>
      ) : null}
      <details>
        <summary>Historia modeli i przywrócenie</summary>
        <ul>
          {history.map((event, index) => (
            <li key={event.eventId ?? index}>
              {shortDate(event.createdAt)} · {event.kind} ·{' '}
              {versionName(versions, event.versionId)}
            </li>
          ))}
        </ul>
        {!history.length ? <p>Brak historii przypisań tej gry.</p> : null}
        <label>
          Wcześniejsza wersja
          <select
            disabled={disabled}
            value={rollbackTarget}
            onChange={(event) => {
              setRollbackTarget(event.target.value);
              setRollbackConfirmed(false);
            }}
          >
            <option value="">Wybierz wersję z historii</option>
            {rollbackVersions.map((id) => (
              <option key={id} value={id}>
                {versionName(versions, id)}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            disabled={disabled || !rollbackTarget}
            checked={rollbackConfirmed}
            onChange={(event) => setRollbackConfirmed(event.target.checked)}
          />
          Potwierdzam przywrócenie wersji dla nowych importów tej gry
        </label>
        <button
          className="secondaryButton"
          type="button"
          disabled={disabled || !rollbackTarget || !rollbackConfirmed}
          onClick={() => void rollback()}
        >
          Przywróć wersję gry
        </button>
      </details>
    </section>
  );
}

function LearningProgress({
  preview,
}: {
  readonly preview: GridCorrectionLearningPreview;
}) {
  const counts = preview.progressCounts;
  if (!counts) return <p>Szczegółowy przyrost korekt nie został ustalony.</p>;
  const rows = [
    ['Zatwierdzone korekty ogółem', counts.approved],
    ['Dostępne do uczenia (TRAIN)', counts.availableTrain],
    ['W zapisanych zestawach TRAIN', counts.usedTrain],
    ['Nowe do uczenia', counts.newTrain],
    ['Dobór modelu — zatwierdzone', counts.validation],
    ['Kontrola końcowa — zatwierdzone', counts.regression],
    ['Rezerwa do doboru — bez etykiet', counts.validationReserve],
    ['Rezerwa do kontroli — bez etykiet', counts.regressionReserve],
    ['Bufory między rolami', counts.buffers],
    ['Wyłączone z podziału', counts.excluded],
  ] as const;
  return (
    <>
      <table>
        <caption>Korekty i ochrona danych do następnego uczenia</caption>
        <thead>
          <tr>
            <th>Przeznaczenie</th>
            <th>Zdjęcia</th>
            <th>Plansze</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, count]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              <td>{count.photos}</td>
              <td>{count.boards}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p>
        Nowe do uczenia to zatwierdzone plansze, których aktualnej etykiety nie
        ma w zamrożonych zestawach TRAIN. Zapis w zestawie nie potwierdza
        zakończenia treningu modelu. Jedno zdjęcie może zawierać plansze z
        zapisanych zestawów i nowe plansze. Nie sumuj zdjęć z tych kategorii.
        Kategorie mogą się nakładać. Bufory obejmują też zdjęcia bez etykiet.
      </p>
      <p>
        Kontrole, kopie i bufory chronią ocenę. Nie każda korekta trafia do
        uczenia. Rezerwa bez etykiet nie jest wynikiem testu jakości i nie
        uzupełnia minimów kontroli. Uzupełnij korekty zarezerwowanych zdjęć albo
        dodaj nowy import, jeżeli brakuje bezpiecznych danych.
      </p>
      <p>
        Minima: uczenie 30 plansz / 10 zdjęć; dobór i kontrola po 15 plansz / 5
        zdjęć.
      </p>
      {counts.exclusionReasons.length ? (
        <ul aria-label="Powody wyłączenia korekt">
          {counts.exclusionReasons.map((item) => (
            <li key={item.reason}>
              {reasonLabel(item.reason)}: {item.photos} zdjęć / {item.boards}{' '}
              plansz.
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

function LearningReport({
  view,
  games,
}: {
  readonly view: GridModelEvaluationView;
  readonly games: readonly GameResponse[];
}) {
  const report = view.report;
  if (view.status !== 'completed')
    return (
      <p>
        Raport oceny:{' '}
        {['created', 'processing', 'waiting_for_review'].includes(view.status)
          ? 'W przygotowaniu'
          : 'Nieukończony'}
        .
      </p>
    );
  if (!report || report.schemaVersion !== 'grid-model-evaluation-read-v3')
    return <p>Raport oceny: {view.verdict ?? 'W przygotowaniu'}.</p>;
  return (
    <section aria-label="Wynik uczenia">
      <h4>Wynik: {report.verdict}</h4>
      <p>
        Częściowe zdjęcia oceniają wyłącznie oznaczone plansze. Brak miary
        fałszywych detekcji na nieoznaczonym obszarze.
      </p>
      {!view.currentness.length ||
      view.currentness.some((item) => item.state !== 'current') ? (
        <p role="alert">
          Dowody wymagają ponownego sprawdzenia aktualności przed zastosowaniem.
        </p>
      ) : (
        <p>Dowód oceny jest aktualny.</p>
      )}
      {report.games.map((game) => (
        <table key={game.gameId}>
          <caption>{gameName(games, game.gameId)}</caption>
          <thead>
            <tr>
              <th>Kontrola</th>
              <th>Zdjęcia / plansze</th>
              <th>Wykryte: baza / kandydat</th>
              <th>Poprawne: baza / kandydat</th>
              <th>Błąd: baza / kandydat</th>
            </tr>
          </thead>
          <tbody>
            {(['VALIDATION', 'REGRESSION'] as const).map((role) => (
              <tr key={role}>
                <th>{learningRole[role]}</th>
                <td>
                  {game.roles[role].candidate.photos} /{' '}
                  {game.roles[role].candidate.boards_expected}
                </td>
                <td>
                  {game.roles[role].base.boards_matched} /{' '}
                  {game.roles[role].candidate.boards_matched}
                </td>
                <td>
                  {game.roles[role].base.boards_correct} /{' '}
                  {game.roles[role].candidate.boards_correct}
                </td>
                <td>
                  {game.roles[role].base.normalized_error?.toFixed(4) ?? '—'} /{' '}
                  {game.roles[role].candidate.normalized_error?.toFixed(4) ??
                    '—'}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr>
              <td colSpan={5}>
                Pokrycie oznaczonych plansz:{' '}
                {game.coverage === 'complete' ? 'pełne' : 'niepełne'}.
                {game.reasons.length ? (
                  <ul>
                    {game.reasons.map((reason) => (
                      <li key={reason}>{reasonLabel(reason)}</li>
                    ))}
                  </ul>
                ) : null}
              </td>
            </tr>
          </tfoot>
        </table>
      ))}
    </section>
  );
}
