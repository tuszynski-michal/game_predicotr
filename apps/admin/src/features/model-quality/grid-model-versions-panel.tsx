'use client';

import type {
  AdminApiClient,
  GameGridModelAssignmentResponse,
  GridModelDefaultResponse,
  GridModelEvaluationView,
  GridModelHistoryEvent,
  GridModelVersionResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { evaluationVerdictLabels } from './grid-model-evaluation-state';
import {
  answeredRefusal,
  clearModelCommand,
  modelCommandKey,
  publishBlocker,
  readModelCommand,
  reasonLabel,
  saveModelCommand,
  shortDate,
  versionLabel,
  versionName,
  type PendingModelCommand,
} from './grid-model-state';

export type GridModelVersionsClient = Pick<
  AdminApiClient,
  | 'listGridModelVersions'
  | 'getGridModelDefault'
  | 'getGameGridModelAssignment'
  | 'getGameGridModelHistory'
  | 'listGridModelEvaluations'
  | 'getGridModelEvaluation'
  | 'publishGridModelVersion'
  | 'activateGameGridModel'
  | 'setGridModelDefault'
  | 'rollbackGameGridModel'
>;

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: GridModelVersionsClient;
  /** Changes when another step changed shared data (TASK-1000, P2-1). */
  readonly refreshKey?: number;
  readonly onChanged?: () => void;
}

const HISTORY_LABELS: Readonly<Record<string, string>> = {
  publish: 'publikacja',
  set_default: 'domyślna wersja',
  activate: 'aktywacja',
  rollback: 'przywrócenie',
  historical_assignment: 'przypisanie historyczne',
  bootstrap: 'przypisanie przy utworzeniu gry',
};

/** TASK-1000: publication, activation, default and rollback; nothing switches by itself. */
export function GridModelVersionsPanel(props: Props) {
  return <Versions key={`${props.apiBaseUrl}:${props.gameId}`} {...props} />;
}

function Versions({
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
  const storageKey = modelCommandKey(apiBaseUrl, gameId, 'versions');
  const [versions, setVersions] = useState<readonly GridModelVersionResponse[]>(
    [],
  );
  const [defaultModel, setDefaultModel] =
    useState<GridModelDefaultResponse | null>(null);
  const [assignment, setAssignment] =
    useState<GameGridModelAssignmentResponse | null>(null);
  const [history, setHistory] = useState<readonly GridModelHistoryEvent[]>([]);
  const [candidateId, setCandidateId] = useState('');
  const [evaluations, setEvaluations] = useState<
    readonly GridModelEvaluationView[]
  >([]);
  const [evaluation, setEvaluation] = useState<GridModelEvaluationView | null>(
    null,
  );
  const [pending, setPending] = useState<PendingModelCommand | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const request = useRef(0);
  const selectedCandidate = useRef('');
  const selectedEvaluation = useRef('');

  async function refresh() {
    // A new evaluation of the chosen candidate becomes selectable without choosing again.
    const candidate = selectedCandidate.current;
    if (candidate) {
      const token = request.current;
      void Promise.resolve()
        .then(() => api.listGridModelEvaluations(candidate))
        .then((result) => {
          if (
            token === request.current &&
            selectedCandidate.current === candidate &&
            result.data
          )
            setEvaluations(result.data.items);
        })
        .catch(() => undefined);
    }
    // The chosen evaluation is re-read too: a currentness check elsewhere may unblock it.
    const chosen = selectedEvaluation.current;
    if (chosen) {
      const token = request.current;
      void Promise.resolve()
        .then(() => api.getGridModelEvaluation(chosen))
        .then((result) => {
          if (
            token === request.current &&
            selectedEvaluation.current === chosen &&
            result.data?.evaluationId === chosen
          )
            setEvaluation(result.data);
        })
        .catch(() => undefined);
    }
    const [versionList, defaults, assigned, events] = await Promise.all([
      api.listGridModelVersions(),
      api.getGridModelDefault(),
      api.getGameGridModelAssignment(gameId),
      api.getGameGridModelHistory(gameId),
    ]);
    if (versionList.data) setVersions(versionList.data);
    if (defaults.data) setDefaultModel(defaults.data);
    if (assigned.data && assigned.data.gameId === gameId)
      setAssignment(assigned.data);
    if (events.data) setHistory(events.data);
    if (!versionList.data || !defaults.data || !assigned.data || !events.data)
      setError('Nie udało się odczytać katalogu wersji.');
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
      void refresh().catch(
        () => !cancelled && setError('Nie udało się odczytać katalogu wersji.'),
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
      .catch(
        () => !cancelled && setError('Nie udało się odczytać katalogu wersji.'),
      );
    return () => {
      cancelled = true;
    };
    // Another step changed the data this panel lists.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  async function chooseCandidate(id: string) {
    // Every change, also to the empty choice, invalidates a read still on its way.
    const token = (request.current += 1);
    selectedCandidate.current = id;
    selectedEvaluation.current = '';
    setCandidateId(id);
    setEvaluations([]);
    setEvaluation(null);
    if (!id) return;
    const result = await api.listGridModelEvaluations(id);
    if (token !== request.current) return;
    if (result.data) setEvaluations(result.data.items);
    else setError(apiErrorMessage(result.error, 'Nie udało się pobrać ocen.'));
  }

  async function chooseEvaluation(id: string) {
    const token = (request.current += 1);
    selectedEvaluation.current = id;
    setEvaluation(null);
    if (!id) return;
    const result = await api.getGridModelEvaluation(id);
    if (token !== request.current) return;
    if (result.data?.evaluationId === id) setEvaluation(result.data);
    else setError(apiErrorMessage(result.error, 'Nie udało się pobrać oceny.'));
  }

  async function send(command: PendingModelCommand) {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      saveModelCommand(window.localStorage, storageKey, command);
      setPending(command);
      const body = command.body as {
        idempotencyKey: string;
        expectedRevision: number;
      };
      const result =
        command.kind === 'publish'
          ? await api.publishGridModelVersion(command.target, {
              ...body,
              evaluationId: String(command.body.evaluationId),
            })
          : command.kind === 'activate'
            ? await api.activateGameGridModel(gameId, {
                ...body,
                versionId: command.target,
              })
            : command.kind === 'rollback'
              ? await api.rollbackGameGridModel(gameId, {
                  ...body,
                  versionId: command.target,
                })
              : await api.setGridModelDefault({
                  ...body,
                  versionId: command.target,
                });
      if (result.data === undefined) {
        const refused = answeredRefusal(result);
        if (refused) {
          clearModelCommand(
            window.localStorage,
            storageKey,
            body.idempotencyKey,
          );
          setPending(null);
          await refresh();
        }
        setError(
          `${apiErrorMessage(result.error, 'Polecenie nie zostało potwierdzone.')} ${
            refused
              ? 'Backend odrzucił polecenie; zapisane polecenie usunięto, odczytano aktualny stan.'
              : 'Zapisane polecenie można ponowić.'
          }`,
        );
        return;
      }
      clearModelCommand(window.localStorage, storageKey, body.idempotencyKey);
      setPending(null);
      setNotice('Polecenie potwierdzone.');
      await refresh();
      onChanged?.();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : 'Polecenie nie zostało potwierdzone.',
      );
    } finally {
      setBusy(false);
    }
  }

  function command(
    kind: PendingModelCommand['kind'],
    target: string,
    expectedRevision: number,
    extra: Record<string, unknown> = {},
  ) {
    void send({
      kind,
      target,
      body: { idempotencyKey: crypto.randomUUID(), expectedRevision, ...extra },
    });
  }

  const candidates = versions.filter(
    (item) => item.manifest.admission === 'not_evaluated' && !item.published,
  );
  const usable = versions.filter((item) => item.published);
  const currentId = assignment?.version?.manifest.versionId ?? null;
  const earlier = [
    ...new Set(
      history
        .filter((event) =>
          [
            'activate',
            'rollback',
            'historical_assignment',
            'bootstrap',
          ].includes(event.kind),
        )
        .map((event) => event.versionId),
    ),
  ].filter((id) => id && id !== currentId);
  const blocker = publishBlocker(evaluation);
  const locked = busy || pending !== null;
  return (
    <section
      className="modelQualityPanel"
      aria-labelledby="grid-model-versions"
    >
      <h3 id="grid-model-versions">Wersje geometrii</h3>
      <p>
        Publikacja, aktywacja w grze i wersja domyślna to osobne, jawne decyzje.
        Wynik oceny nie przełącza żadnej gry.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {pending ? (
        <div>
          <p>Zapisane polecenie wersji czeka na potwierdzenie.</p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void send(pending)}
          >
            Ponów zapisane polecenie
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              window.localStorage.removeItem(storageKey);
              setPending(null);
            }}
          >
            Porzuć zapisane polecenie
          </button>
        </div>
      ) : null}
      <p>
        W tej grze:{' '}
        {currentId ? versionName(versions, currentId) : 'brak przypisania'} ·
        domyślna:{' '}
        {defaultModel?.version
          ? `${versionLabel(defaultModel.version.manifest)} (${reasonLabel(defaultModel.reasonCode)})`
          : reasonLabel(
              defaultModel?.reasonCode ?? 'GRID_MODEL_DEFAULT_REQUIRED',
            )}
      </p>
      <fieldset disabled={locked}>
        <legend>Publikacja kandydata</legend>
        <label>
          Kandydat
          <select
            value={candidateId}
            onChange={(event) => void chooseCandidate(event.target.value)}
          >
            <option value="">Wybierz kandydata</option>
            {candidates.map((item) => (
              <option
                key={item.manifest.versionId}
                value={item.manifest.versionId}
              >
                {versionLabel(item.manifest)} · baza{' '}
                {versionName(versions, item.manifest.baseVersionId)}
              </option>
            ))}
          </select>
        </label>
        {candidateId ? (
          <label>
            Ocena
            <select
              value={evaluation?.evaluationId ?? ''}
              onChange={(event) => void chooseEvaluation(event.target.value)}
            >
              <option value="">Wybierz ocenę</option>
              {evaluations.map((item) => (
                <option key={item.evaluationId} value={item.evaluationId}>
                  {shortDate(item.createdAt)} ·{' '}
                  {item.verdict
                    ? evaluationVerdictLabels[item.verdict]
                    : item.status}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <button
          type="button"
          disabled={blocker !== null}
          onClick={() =>
            evaluation &&
            command('publish', candidateId, 0, {
              evaluationId: evaluation.reportId,
            })
          }
        >
          Opublikuj kandydata
        </button>
        {candidateId && blocker ? (
          <p>Publikacja niedostępna: {blocker}</p>
        ) : null}
      </fieldset>
      <ul aria-label="Opublikowane wersje">
        {usable.map((item) => {
          const reason = item.eligible
            ? null
            : reasonLabel(item.eligibilityReasonCode ?? item.reasonCode);
          const id = item.manifest.versionId;
          return (
            <li key={id}>
              {versionLabel(item.manifest)}
              {item.available ? '' : ` · ${reasonLabel(item.reasonCode)}`}
              {reason ? ` · ${reason}` : ''}
              <button
                type="button"
                disabled={locked || !item.eligible || id === currentId}
                onClick={() =>
                  command('activate', id, assignment?.revision ?? 0)
                }
              >
                Aktywuj w tej grze
              </button>
              <button
                type="button"
                disabled={
                  locked ||
                  !item.eligible ||
                  id === defaultModel?.version?.manifest.versionId
                }
                onClick={() =>
                  command('set_default', id, defaultModel?.revision ?? 0)
                }
              >
                Ustaw jako domyślną
              </button>
            </li>
          );
        })}
      </ul>
      {earlier.length ? (
        <ul aria-label="Wcześniejsze wersje gry">
          {earlier.map((id) => (
            <li key={id}>
              {versionName(versions, id)}
              <button
                type="button"
                disabled={locked}
                onClick={() =>
                  command('rollback', id, assignment?.revision ?? 0)
                }
              >
                Przywróć w tej grze
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <ul aria-label="Historia wersji gry">
        {history.map((event, index) => (
          <li key={`${event.kind}:${event.revision}:${index}`}>
            {shortDate(event.createdAt)} ·{' '}
            {HISTORY_LABELS[event.kind] ?? event.kind} ·{' '}
            {versionName(versions, event.versionId)}
          </li>
        ))}
      </ul>
    </section>
  );
}
