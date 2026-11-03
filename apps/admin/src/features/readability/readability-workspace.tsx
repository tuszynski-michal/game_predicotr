'use client';

import type {
  AdminApiClient,
  ReadabilityItemResponse,
  ReadabilityStartRequest,
  ReadabilityCommandRequest,
  ReadabilityLabelRequest,
  ReadabilityPageResponse,
  ReadabilityWorkspaceResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { SymbolReviewSourceModal } from '@/features/symbol-reviews/symbol-review-source-modal';
import {
  canAcceptReadabilityModel,
  completeReadabilityCommand,
  readabilityCommandKey,
  readabilityTargets,
  pendingReadabilityCommand,
  type PendingReadabilityCommand,
  READABILITY_SELECTION_LIMIT,
} from './readability-state';
import { inclusiveSelectionRange } from '../symbol-reviews/selection-range';
import {
  createReadabilityLabelQueue,
  drainReadabilityLabelQueue,
  discardReadabilityLabelQueue,
  loadReadabilityLabelQueue,
  readabilityQueueProgress,
  READABILITY_MAX_SELECTION,
  type ReadabilityLabelQueue,
} from './readability-label-queue';
import styles from './readability-workspace.module.css';

export type ReadabilityClient = Pick<
  AdminApiClient,
  | 'getReadabilityWorkspace'
  | 'startReadabilityRun'
  | 'listReadabilityItems'
  | 'labelReadabilityItems'
  | 'fitReadabilityPilot'
  | 'acceptReadabilityModel'
  | 'exportReadabilityCsvUrl'
  | 'symbolCellReviewAssetUrl'
  | 'getOperationalImageReviewItem'
  | 'getOperationalImageReviewSourceAsset'
>;

interface Props {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: ReadabilityClient;
}

const stateLabels = {
  pending: 'Niepewna czytelność',
  readable: 'Czytelne',
  unreadable: 'Nieczytelne',
  skipped: 'Pominięte',
  stale: 'Zmienione piksele lub geometria',
  error: 'Błąd',
};

export function ReadabilityWorkspace(props: Props) {
  // Remount all state and invalidate pending requests when the game changes.
  return <ReadabilityGameWorkspace key={props.gameId} {...props} />;
}

function ReadabilityGameWorkspace({ apiBaseUrl, gameId, client }: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [workspace, setWorkspace] =
    useState<ReadabilityWorkspaceResponse | null>(null);
  const [runId, setRunId] = useState('');
  const [modelId, setModelId] = useState('');
  const [page, setPage] = useState<ReadabilityPageResponse | null>(null);
  const [offset, setOffset] = useState(0);
  const [state, setState] = useState('');
  const [historical, setHistorical] = useState('');
  const [problem, setProblem] = useState('');
  const [selected, setSelected] = useState<
    ReadonlyMap<string, ReadabilityItemResponse>
  >(new Map());
  const [label, setLabel] =
    useState<ReadabilityLabelRequest['state']>('pending');
  const [overlap, setOverlap] = useState('unknown');
  const [sharp, setSharp] = useState(false);
  const [similarReadable, setSimilarReadable] = useState(false);
  const [source, setSource] = useState<ReadabilityItemResponse | null>(null);
  const [zoom, setZoom] = useState<ReadabilityItemResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [pageLoading, setPageLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [refresh, setRefresh] = useState(0);
  const [pending, setPending] = useState<PendingReadabilityCommand | null>(
    null,
  );
  const [labelQueue, setLabelQueue] = useState<ReadabilityLabelQueue | null>(
    null,
  );
  const [queueUnreadable, setQueueUnreadable] = useState(false);
  const [discardRequested, setDiscardRequested] = useState(false);
  const selectionAnchor = useRef<string | null>(null);
  const selectionContext = useRef('');
  const alive = useRef(true);
  const commandBusy = useRef(false);
  useEffect(() => {
    alive.current = true;
    queueMicrotask(() => {
      if (!alive.current) return;
      try {
        setPending(pendingReadabilityCommand(gameId));
      } catch (cause) {
        setError(message(cause));
      }
      try {
        setLabelQueue(loadReadabilityLabelQueue(gameId));
      } catch (cause) {
        setQueueUnreadable(true);
        setError(message(cause));
      }
    });
    return () => {
      alive.current = false;
    };
  }, [gameId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      if (cancelled) return;
      setLoading(true);
      try {
        const result = await api.getReadabilityWorkspace(gameId);
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined)
          throw new Error(
            apiErrorMessage(
              result.error,
              'Nie udało się wczytać przeglądu jakości.',
            ),
          );
        const data = result.data;
        setWorkspace(data);
        setRunId((current) =>
          data.runs.some((run) => run.id === current)
            ? current
            : (data.runs[0]?.id ?? ''),
        );
        setModelId((current) =>
          data.models.some((model) => model.id === current)
            ? current
            : (data.models.find((model) => model.accepted)?.id ??
              data.models[0]?.id ??
              ''),
        );
      } catch (cause) {
        if (!cancelled) setError(message(cause));
      } finally {
        if (!cancelled) setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, refresh]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(async () => {
      if (cancelled) return;
      selectionAnchor.current = null;
      setPage(null);
      const context = JSON.stringify([
        gameId,
        runId,
        state,
        historical,
        problem,
        refresh,
      ]);
      if (selectionContext.current !== context) {
        selectionContext.current = context;
        setSelected(new Map());
      }
      setSource(null);
      setZoom(null);
      if (!runId) {
        setPageLoading(false);
        return;
      }
      setPageLoading(true);
      try {
        const result = await api.listReadabilityItems(gameId, runId, {
          offset,
          state: state
            ? (state as ReadabilityItemResponse['state'])
            : undefined,
          historical: historical ? historical === 'old' : undefined,
          problem: problem ? (problem as 'overlap' | 'unreadable') : undefined,
        });
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined)
          throw new Error(
            apiErrorMessage(result.error, 'Nie udało się wczytać pól.'),
          );
        setPage(result.data);
      } catch (cause) {
        if (!cancelled) setError(message(cause));
      } finally {
        if (!cancelled) setPageLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId, runId, offset, state, historical, problem, refresh]);

  const run = workspace?.runs.find((item) => item.id === runId);
  const model = workspace?.models.find((item) => item.id === modelId);
  const blocked = busy || loading || pageLoading || discardRequested;
  const selectedItems = [...selected.values()];

  async function command(
    name: string,
    payload: unknown,
    send: (
      key: string,
    ) => Promise<{ error?: unknown; data?: unknown; response?: Response }>,
  ) {
    if (commandBusy.current) return;
    commandBusy.current = true;
    setBusy(true);
    setError('');
    try {
      if (loadReadabilityLabelQueue(gameId) !== null)
        throw new Error('Najpierw ponów zapisaną kolejkę ocen.');
      const key = readabilityCommandKey(gameId, name, payload);
      setPending(pendingReadabilityCommand(gameId));
      const result = await send(key);
      if (result.error !== undefined || result.data === undefined) {
        // An explicit validation/conflict response permits correcting the command.
        // Missing responses and server failures keep the exact intent for recovery.
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          completeReadabilityCommand(gameId, name, payload);
          if (alive.current) setPending(null);
        }
        const detail = result.error as
          { code?: string; message?: string; detail?: string } | undefined;
        throw new Error(
          apiErrorMessage(
            result.error,
            detail?.message ??
              detail?.detail ??
              detail?.code ??
              'Komenda nie została potwierdzona. Ponów identyczną akcję; zachowamy jej klucz.',
          ),
        );
      }
      completeReadabilityCommand(gameId, name, payload);
      if (alive.current) {
        if (
          typeof result.data === 'object' &&
          result.data !== null &&
          'id' in result.data &&
          typeof result.data.id === 'string'
        ) {
          if (name === 'start') {
            setRunId(result.data.id);
            setOffset(0);
          }
          if (name.startsWith('fit:')) setModelId(result.data.id);
        }
        setPending(null);
        setRefresh((value) => value + 1);
      }
    } catch (cause) {
      if (alive.current) setError(message(cause));
    } finally {
      commandBusy.current = false;
      if (alive.current) setBusy(false);
    }
  }

  function retryPending() {
    if (!pending) return;
    const { command: name, payload } = pending;
    void command(name, payload, (idempotencyKey) => {
      if (name === 'start')
        return api.startReadabilityRun(gameId, {
          ...(payload as Omit<ReadabilityStartRequest, 'idempotencyKey'>),
          idempotencyKey,
        });
      const [kind, id] = name.split(':');
      if (kind === 'labels')
        return api.labelReadabilityItems(gameId, id, {
          ...(payload as Omit<ReadabilityLabelRequest, 'idempotencyKey'>),
          idempotencyKey,
        });
      const body = {
        ...(payload as Omit<ReadabilityCommandRequest, 'idempotencyKey'>),
        idempotencyKey,
      };
      if (kind === 'fit') return api.fitReadabilityPilot(gameId, id, body);
      if (kind === 'accept')
        return api.acceptReadabilityModel(gameId, id, body);
      throw new Error('Nieznana zapisana komenda.');
    });
  }

  function start(kind: 'pilot' | 'scan') {
    const body = {
      kind,
      modelId: kind === 'scan' ? modelId : null,
      seed: 'quality-pilot-v1',
    };
    void command('start', body, (idempotencyKey) =>
      api.startReadabilityRun(gameId, { ...body, idempotencyKey }),
    );
  }

  async function saveQueue() {
    if (commandBusy.current) return;
    commandBusy.current = true;
    setBusy(true);
    setError('');
    try {
      await drainReadabilityLabelQueue(
        gameId,
        (id, body) => api.labelReadabilityItems(gameId, id, body),
        (queue) => {
          if (alive.current) setLabelQueue(queue);
        },
        () => alive.current,
      );
      if (alive.current && loadReadabilityLabelQueue(gameId) === null)
        setRefresh((value) => value + 1);
    } catch (cause) {
      if (alive.current) setError(message(cause));
    } finally {
      commandBusy.current = false;
      if (alive.current) setBusy(false);
    }
  }

  function discardQueue() {
    if (commandBusy.current) return;
    try {
      discardReadabilityLabelQueue(gameId);
      setLabelQueue(null);
      setQueueUnreadable(false);
      setDiscardRequested(false);
      setSelected(new Map());
      selectionAnchor.current = null;
      setError('');
      setRefresh((value) => value + 1);
    } catch (cause) {
      setError(message(cause));
    }
  }

  function saveLabels() {
    if (!run || selectedItems.length === 0 || commandBusy.current) return;
    try {
      if (loadReadabilityLabelQueue(gameId) !== null)
        throw new Error('Najpierw ponów zapisaną kolejkę ocen.');
      if (selectedItems.length > READABILITY_MAX_SELECTION)
        throw new Error('Można wybrać najwyżej 10 000 pól.');
      const targets = [];
      for (
        let index = 0;
        index < selectedItems.length;
        index += READABILITY_SELECTION_LIMIT
      )
        targets.push(
          ...readabilityTargets(
            selectedItems.slice(index, index + READABILITY_SELECTION_LIMIT),
          ),
        );
      const body = {
        targets,
        state: label,
        overlap: overlap === 'unknown' ? null : overlap === 'yes',
        sharp: run.kind === 'pilot' && sharp,
        similarReadable: run.kind === 'pilot' && similarReadable,
      };
      if (targets.length > READABILITY_SELECTION_LIMIT) {
        setLabelQueue(createReadabilityLabelQueue(gameId, run.id, body));
        void saveQueue();
      } else {
        void command(`labels:${run.id}`, body, (idempotencyKey) =>
          api.labelReadabilityItems(gameId, run.id, {
            ...body,
            idempotencyKey,
          }),
        );
      }
    } catch (cause) {
      setError(message(cause));
    }
  }

  function toggle(item: ReadabilityItemResponse, shiftKey = false) {
    if (blocked || item.state === 'stale' || item.state === 'error') return;
    setError('');
    const range = shiftKey
      ? inclusiveSelectionRange(
          page?.items ?? [],
          selectionAnchor.current,
          item.cellId,
          (entry) => entry.cellId,
          (entry) => entry.state === 'stale' || entry.state === 'error',
        )
      : null;
    if (range !== null) {
      const next = new Map(selected);
      for (const entry of range)
        if (!next.has(entry.cellId)) next.set(entry.cellId, entry);
      if (next.size > READABILITY_MAX_SELECTION) {
        setError('Można wybrać najwyżej 10 000 pól. Cały zakres odrzucono.');
        return;
      }
      setSelected(next);
      return;
    }
    selectionAnchor.current = item.cellId;
    if (selected.has(item.cellId)) {
      const next = new Map(selected);
      next.delete(item.cellId);
      setSelected(next);
    } else if (selected.size >= READABILITY_MAX_SELECTION) {
      setError('Można wybrać najwyżej 10 000 pól.');
    } else {
      setSelected(new Map([...selected, [item.cellId, item]]));
    }
  }

  function changeFilter(set: (value: string) => void, value: string) {
    selectionAnchor.current = null;
    set(value);
    setOffset(0);
    setSelected(new Map());
  }

  function cropUrl(item: ReadabilityItemResponse) {
    return item.cropChecksumSha256 === null
      ? null
      : api.symbolCellReviewAssetUrl(
          gameId,
          item.cellId,
          item.cropChecksumSha256,
          item.renderSpecChecksumSha256,
        );
  }

  return (
    <section className={styles.workspace} aria-label="Podejrzane symbole">
      <h3>Podejrzane symbole</h3>
      <p>
        Pilot nie wymaga gotowego detektora: do 600 rzeczywistych pól i osobno
        200 pól audytu. Etykiety zapisuje człowiek. Fit i odbiór modelu są
        oddzielnymi akcjami. Pełny skan wymaga PASS i odbioru.
      </p>
      <div className={styles.toolbar}>
        <button
          type="button"
          className="primaryButton"
          disabled={blocked}
          onClick={() => start('pilot')}
        >
          Przygotuj pilot
        </button>
        <button
          type="button"
          className="secondaryButton"
          disabled={blocked}
          onClick={() => {
            setError('');
            setRefresh((value) => value + 1);
          }}
        >
          Odśwież przegląd
        </button>
      </div>
      {error ? (
        <p role="alert" className={styles.error}>
          {error}
        </p>
      ) : null}
      {labelQueue ? (
        <div role="status">
          <p>
            Kolejka ocen: wykonane {readabilityQueueProgress(labelQueue).done},
            pozostałe {readabilityQueueProgress(labelQueue).remaining}. Błąd
            wstrzymuje dalszy zapis; ponowienie zachowuje pola, rewizje i
            klucze.
          </p>
          <button
            type="button"
            className="secondaryButton"
            disabled={blocked}
            onClick={() => void saveQueue()}
          >
            Ponów zapisane oceny
          </button>
        </div>
      ) : null}
      {labelQueue !== null || queueUnreadable ? (
        <button
          type="button"
          className="secondaryButton"
          disabled={blocked}
          onClick={() => setDiscardRequested(true)}
        >
          Porzuć pozostałe porcje
        </button>
      ) : null}
      {discardRequested ? (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-label="Potwierdź porzucenie kolejki"
        >
          <p>
            {labelQueue
              ? `Wykonane ${readabilityQueueProgress(labelQueue).done} pól pozostają zapisane. Pozostałe ${readabilityQueueProgress(labelQueue).remaining} pól nie zostaną ponowione.`
              : 'Nie można odczytać postępu kolejki. Dotychczasowe zapisy pozostają.'}{' '}
            Niepotwierdzona porcja mogła już zostać zapisana. Porzucenie usuwa
            wyłącznie lokalny plan dalszych żądań, bez cofania zapisów.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => setDiscardRequested(false)}
          >
            Zachowaj kolejkę
          </button>
          <button type="button" disabled={busy} onClick={discardQueue}>
            Potwierdź porzucenie
          </button>
        </div>
      ) : null}
      {pending ? (
        <div role="status">
          <p>
            Komenda czeka na potwierdzenie. Ponowienie zachowa pierwotne pola,
            tożsamości, rewizje i klucz.
          </p>
          <button
            type="button"
            className="secondaryButton"
            disabled={blocked}
            onClick={retryPending}
          >
            Ponów zapisaną komendę
          </button>
        </div>
      ) : null}
      {busy ? <p role="status">Zapisywanie komendy…</p> : null}
      {loading ? <p role="status">Wczytywanie przeglądu jakości…</p> : null}
      {workspace !== null && workspace.runs.length === 0 ? (
        <p>Brak uruchomień. Przygotuj pilot, aby rozpocząć ocenę bez modelu.</p>
      ) : null}
      {workspace !== null && workspace.runs.length > 0 ? (
        <>
          <div className={styles.toolbar}>
            <label>
              Uruchomienie
              <select
                value={runId}
                disabled={busy}
                onChange={(event) => changeFilter(setRunId, event.target.value)}
              >
                {workspace.runs.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.kind === 'pilot' ? 'Pilot' : 'Skan'} · {item.status} ·{' '}
                    {item.id}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondaryButton"
              disabled={
                blocked ||
                run?.kind !== 'pilot' ||
                run.status !== 'completed' ||
                run.processedCount !== run.itemCount
              }
              onClick={() => {
                if (!run) return;
                const body = { expectedRevision: run.revision };
                void command(`fit:${run.id}`, body, (idempotencyKey) =>
                  api.fitReadabilityPilot(gameId, run.id, {
                    ...body,
                    idempotencyKey,
                  }),
                );
              }}
            >
              Zamroź etykiety i dopasuj model
            </button>
          </div>
          {run ? (
            <p>
              Postęp: {run.processedCount} / {run.itemCount} pól · rewizja{' '}
              {run.revision}
              {run.errorCode
                ? ` · ${run.errorCode}: ${run.errorMessage ?? ''}`
                : ''}
            </p>
          ) : null}
          <p>
            Fit wymaga kompletnych etykiet i izolowanych rodzin spełniających
            minima. Brak danych kończy się STOP.
          </p>
        </>
      ) : null}
      {workspace !== null && workspace.models.length > 0 ? (
        <>
          <div className={styles.toolbar}>
            <label>
              Model jakości
              <select
                value={modelId}
                disabled={busy}
                onChange={(event) => setModelId(event.target.value)}
              >
                {workspace.models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id} · {item.status}
                    {item.accepted ? ' · odebrany' : ''}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="secondaryButton"
              disabled={blocked || !model || !canAcceptReadabilityModel(model)}
              onClick={() => {
                if (!model) return;
                const body = { expectedRevision: model.revision };
                void command(`accept:${model.id}`, body, (idempotencyKey) =>
                  api.acceptReadabilityModel(gameId, model.id, {
                    ...body,
                    idempotencyKey,
                  }),
                );
              }}
            >
              Odbierz model po PASS
            </button>
            <button
              type="button"
              className="primaryButton"
              disabled={
                blocked ||
                !model?.accepted ||
                model.status !== 'completed' ||
                model.report.status !== 'PASS'
              }
              onClick={() => start('scan')}
            >
              Rozpocznij pełny skan
            </button>
          </div>
          {model ? (
            <>
              <p>
                Bramka: {String(model.report.status ?? 'brak wyniku')} ·{' '}
                {model.accepted ? 'Odbiór zapisany' : 'Brak odbioru'}
                {model.errorCode
                  ? ` · ${model.errorCode}: ${model.errorMessage ?? ''}`
                  : ''}
              </p>
              <details>
                <summary>Raport bramki modelu</summary>
                <pre>{JSON.stringify(model.report, null, 2)}</pre>
              </details>
            </>
          ) : null}
        </>
      ) : null}
      {runId ? (
        <>
          <div className={styles.toolbar}>
            <label>
              Stan pola
              <select
                value={state}
                disabled={busy}
                onChange={(event) => changeFilter(setState, event.target.value)}
              >
                <option value="">Wszystkie stany</option>
                {Object.entries(stateLabels).map(([value, title]) => (
                  <option key={value} value={value}>
                    {title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Historia
              <select
                value={historical}
                disabled={busy}
                onChange={(event) =>
                  changeFilter(setHistorical, event.target.value)
                }
              >
                <option value="">Stare i nowe</option>
                <option value="old">Historyczne unreadable</option>
                <option value="new">Bez historycznego unreadable</option>
              </select>
            </label>
            <label>
              Typ problemu
              <select
                value={problem}
                disabled={busy}
                onChange={(event) =>
                  changeFilter(setProblem, event.target.value)
                }
              >
                <option value="">Wszystkie problemy</option>
                <option value="overlap">Nałożenie</option>
                <option value="unreadable">Nieczytelność</option>
              </select>
            </label>
          </div>
          {pageLoading ? <p role="status">Wczytywanie pól…</p> : null}
          {page ? (
            <>
              <dl className={styles.report}>
                <div>
                  <dt>Pola / plansze / źródła</dt>
                  <dd>
                    {page.fields} / {page.boards} / {page.sources}
                  </dd>
                </div>
                <div>
                  <dt>Potwierdzone nieczytelne: pola / plansze / źródła</dt>
                  <dd>
                    {page.confirmedFields} / {page.confirmedBoards} /{' '}
                    {page.confirmedSources}
                  </dd>
                </div>
              </dl>
              <a href={api.exportReadabilityCsvUrl(gameId, runId)} download>
                Eksport CSV numerów
              </a>
              <p>
                Czytelne nie zatwierdza nazwy symbolu i nie usuwa historycznego
                problemu jakości. Nałożenie przy czytelnym polu nie kwalifikuje
                zdjęcia do wymiany.
              </p>
              <fieldset disabled={blocked}>
                <legend>
                  Ocena zaznaczonych pól ({selected.size} / 10 000)
                </legend>
                <p>
                  Zapis zastępuje obie etykiety i cechy zaznaczonych pól zgodnie
                  z poniższym wyborem.
                </p>
                <div className={styles.toolbar}>
                  <label>
                    Czytelność
                    <select
                      value={label}
                      onChange={(event) =>
                        setLabel(
                          event.target
                            .value as ReadabilityLabelRequest['state'],
                        )
                      }
                    >
                      <option value="pending">
                        Niepewna — bez etykiety czytelności
                      </option>
                      <option value="readable">Czytelne</option>
                      <option value="unreadable">Nieczytelne</option>
                      <option value="skipped">Pomiń</option>
                    </select>
                  </label>
                  <label>
                    Nałożenie
                    <select
                      value={overlap}
                      onChange={(event) => setOverlap(event.target.value)}
                    >
                      <option value="unknown">
                        Niepewne — bez etykiety nałożenia
                      </option>
                      <option value="yes">Tak</option>
                      <option value="no">Nie</option>
                    </select>
                  </label>
                  {run?.kind === 'pilot' ? (
                    <>
                      <label>
                        <input
                          type="checkbox"
                          checked={sharp}
                          onChange={(event) => setSharp(event.target.checked)}
                        />
                        Ostre pole
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={similarReadable}
                          onChange={(event) =>
                            setSimilarReadable(event.target.checked)
                          }
                        />
                        Trudne podobne czytelne
                      </label>
                    </>
                  ) : null}
                  <button
                    type="button"
                    className="primaryButton"
                    disabled={selectedItems.length === 0}
                    onClick={saveLabels}
                  >
                    Zapisz oceny
                  </button>
                  <button
                    type="button"
                    className="secondaryButton"
                    onClick={() => setSelected(new Map())}
                  >
                    Wyczyść zaznaczenie
                  </button>
                </div>
              </fieldset>
              {page.items.length === 0 ? (
                <p>Brak pól dla wybranych filtrów.</p>
              ) : null}
              <div className={styles.cards}>
                {page.items.map((item) => (
                  <article key={item.cellId} className={styles.card}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selected.has(item.cellId)}
                        disabled={
                          blocked ||
                          item.state === 'stale' ||
                          item.state === 'error'
                        }
                        onChange={() => {}}
                        onClick={(event) => toggle(item, event.shiftKey)}
                      />
                      Plansza {item.sequenceNumber} · pole {item.cellIndex + 1}
                    </label>
                    <p>
                      Wiersz {item.rowIndex + 1}, kolumna {item.columnIndex + 1}{' '}
                      ·{' '}
                      {item.sampleKind === 'audit'
                        ? 'Niezależny audyt 200'
                        : item.sampleKind === 'pilot'
                          ? 'Pilot'
                          : 'Skan'}
                    </p>
                    <p>
                      {stateLabels[item.state]} · nałożenie:{' '}
                      {item.overlap === null
                        ? 'niepewne'
                        : item.overlap
                          ? 'tak'
                          : 'nie'}
                    </p>
                    <p>
                      {item.historicalUnreadable
                        ? 'Historyczne unreadable'
                        : 'Bez historycznego unreadable'}
                    </p>
                    {item.sharp || item.similarReadable ? (
                      <p>
                        {[
                          item.sharp ? 'Ostre pole' : '',
                          item.similarReadable ? 'Trudne podobne czytelne' : '',
                        ]
                          .filter(Boolean)
                          .join(' · ')}
                      </p>
                    ) : null}
                    <p>Powody: {item.reasons.join(', ') || 'brak'}</p>
                    {item.overlapScore !== null ||
                    item.unreadableScore !== null ? (
                      <p>
                        Score nałożenia: {item.overlapScore ?? '—'} ·
                        nieczytelności: {item.unreadableScore ?? '—'} (bez
                        kalibracji prawdopodobieństwa)
                      </p>
                    ) : null}
                    {cropUrl(item) !== null ? (
                      <button
                        type="button"
                        className="secondaryButton"
                        onClick={() => setZoom(item)}
                        aria-label={`Powiększ pole ${item.cellIndex + 1} planszy ${item.sequenceNumber}`}
                      >
                        {/* eslint-disable-next-line @next/next/no-img-element -- revision-bound local crop */}
                        <img
                          className={styles.crop}
                          src={cropUrl(item)!}
                          alt={`Wycinek pola ${item.cellIndex + 1}`}
                          onError={(event) => {
                            event.currentTarget.alt =
                              'Wycinek niedostępny; otwórz całe źródło.';
                          }}
                        />
                      </button>
                    ) : (
                      <p>Brak wycinka.</p>
                    )}
                    <button
                      type="button"
                      className="secondaryButton"
                      onClick={() => setSource(item)}
                    >
                      Całe źródło · plansza {item.sequenceNumber}, pole{' '}
                      {item.cellIndex + 1}
                    </button>
                  </article>
                ))}
              </div>
              <div className={styles.toolbar}>
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={blocked || offset === 0}
                  onClick={() => setOffset(0)}
                >
                  Pierwsza strona
                </button>
                <button
                  type="button"
                  className="secondaryButton"
                  disabled={blocked || page.nextOffset === null}
                  onClick={() => {
                    if (page.nextOffset !== null) setOffset(page.nextOffset);
                  }}
                >
                  Następna strona
                </button>
              </div>
            </>
          ) : null}
        </>
      ) : null}
      {source ? (
        <SymbolReviewSourceModal
          api={api}
          gameId={gameId}
          item={source}
          onClose={() => setSource(null)}
        />
      ) : null}
      {zoom && cropUrl(zoom) ? (
        <CropZoom
          url={cropUrl(zoom)!}
          item={zoom}
          onClose={() => setZoom(null)}
        />
      ) : null}
    </section>
  );
}

function message(cause: unknown) {
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się wykonać operacji.';
}

function CropZoom({
  url,
  item,
  onClose,
}: {
  url: string;
  item: ReadabilityItemResponse;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    return () => element?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      aria-label="Powiększony wycinek"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <button type="button" className="secondaryButton" onClick={onClose}>
        Zamknij powiększenie
      </button>
      <p>
        Plansza {item.sequenceNumber} · pole {item.cellIndex + 1}
      </p>
      <div className={styles.cropZoom}>
        {/* eslint-disable-next-line @next/next/no-img-element -- revision-bound local crop */}
        <img src={url} alt="Powiększony wycinek pola" />
      </div>
    </dialog>
  );
}
