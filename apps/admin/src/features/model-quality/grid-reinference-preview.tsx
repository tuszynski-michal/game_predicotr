'use client';

import { useEffect, useRef, useState } from 'react';
import type {
  GridReinferenceResponse,
  GridReinferenceSelector,
  GridReinferenceTargetPage,
} from '@game-predictor/admin-api-client';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  clearGridCommand,
  discardGridCommand,
  gridCommandKey,
  gridViewKey,
  readGridCommand,
  saveGridCommand,
  type GridCommand,
} from './grid-reinference-command';
import {
  defaultGridSelector,
  gridReinferenceStateLabels,
  sendGridCommand,
  type GridReinferenceClient,
} from './grid-reinference-state';
import { GridReinferenceReport } from './grid-reinference-report';

const categoryLabels = {
  grid_issue: 'Zła siatka',
  deferred: 'Odroczone pozycje plansz',
  unconfirmed: 'Siatki niepotwierdzone',
  all_automatic: 'Wszystkie automatyczne',
} as const;
const commandLabels = {
  prepare: 'Przygotowanie zakresu',
  freeze: 'Zamrożenie zakresu',
  ack: 'Potwierdzenie pilota',
  start: 'Uruchomienie rozpoznania',
  resume: 'Wznowienie',
  cancel: 'Anulowanie',
} as const;
const message = (error: unknown) =>
  error instanceof Error ? error.message : 'Nie udało się odczytać operacji.';

export function GridReinferencePreview(props: {
  api: GridReinferenceClient;
  apiBaseUrl: string;
  gameId: string;
}) {
  return (
    <GridReinferenceWorkspace
      key={`${props.apiBaseUrl}:${props.gameId}`}
      {...props}
    />
  );
}

function GridReinferenceWorkspace({
  api,
  apiBaseUrl,
  gameId,
}: {
  api: GridReinferenceClient;
  apiBaseUrl: string;
  gameId: string;
}) {
  const [operations, setOperations] = useState<GridReinferenceResponse[]>([]);
  const [historyCursor, setHistoryCursor] = useState<string | null>(null);
  const [operation, setOperation] = useState<GridReinferenceResponse | null>(
    null,
  );
  const [targets, setTargets] = useState<GridReinferenceTargetPage | null>(
    null,
  );
  const [pilots, setPilots] = useState<GridReinferenceResponse[]>([]);
  const [pilotCursor, setPilotCursor] = useState<string | null>(null);
  const [pilotId, setPilotId] = useState('');
  const [selector, setSelector] = useState(defaultGridSelector);
  const [scope, setScope] = useState<'pilot' | 'broader'>('pilot');
  const [broadConfirmed, setBroadConfirmed] = useState(false);
  const [discardConfirmed, setDiscardConfirmed] = useState(false);
  const [pending, setPending] = useState<GridCommand | null>(null);
  const [hasRawPending, setHasRawPending] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const alive = useRef(true);
  const locked = useRef(false);
  const selectedId = useRef<string | null>(null);
  const current = (token: number) =>
    alive.current && generation.current === token;

  function persistView(
    id: string | null,
    nextSelector = selector,
    nextScope = scope,
  ) {
    localStorage.setItem(
      gridViewKey(apiBaseUrl, gameId),
      JSON.stringify({
        operationId: id,
        selector: nextSelector,
        scope: nextScope,
      }),
    );
  }

  async function readOperation(id: string, token: number) {
    const result = await api.getGridReinference(gameId, id);
    if (!current(token)) return;
    if (result.data === undefined)
      throw new Error(
        apiErrorMessage(result.error, 'Nie udało się odczytać operacji.'),
      );
    setOperation(result.data);
    if (result.data.manifestSha256 !== null) {
      const pages = await api.getGridReinferenceTargets(gameId, id);
      if (!current(token)) return;
      if (pages.data === undefined)
        throw new Error(
          apiErrorMessage(pages.error, 'Nie udało się odczytać celów.'),
        );
      setTargets(pages.data);
    } else {
      setTargets(null);
    }
    if (result.data.executionScope === 'broader') {
      const found = await api.listGridReinferenceOperations(gameId, {
        limit: 50,
        compatibleWithOperationId: id,
      });
      if (!current(token)) return;
      if (found.data === undefined)
        throw new Error(
          apiErrorMessage(
            found.error,
            'Nie udało się odczytać zgodnych pilotów.',
          ),
        );
      setPilots(found.data.items);
      setPilotCursor(found.data.nextCursor);
    }
  }

  async function selectOperation(id: string) {
    const token = ++generation.current;
    selectedId.current = id;
    setOperation(null);
    setTargets(null);
    setPilots([]);
    setPilotId('');
    setBroadConfirmed(false);
    setError('');
    try {
      persistView(id);
      await readOperation(id, token);
    } catch (cause) {
      if (current(token)) setError(message(cause));
    }
  }

  useEffect(() => {
    alive.current = true;
    const token = ++generation.current;
    void (async () => {
      try {
        let savedCommand: GridCommand | null = null;
        try {
          savedCommand = readGridCommand(localStorage, apiBaseUrl, gameId);
        } catch (cause) {
          if (current(token)) setError(message(cause));
        }
        if (!current(token)) return;
        setPending(savedCommand);
        setHasRawPending(
          localStorage.getItem(gridCommandKey(apiBaseUrl, gameId)) !== null,
        );
        const rawView = localStorage.getItem(gridViewKey(apiBaseUrl, gameId));
        const view = rawView ? JSON.parse(rawView) : null;
        if (view?.selector?.categories?.length) setSelector(view.selector);
        if (view?.scope === 'broader') setScope('broader');
        const result = await api.listGridReinferenceOperations(gameId, {
          limit: 50,
        });
        if (!current(token)) return;
        if (result.data === undefined)
          throw new Error(
            apiErrorMessage(result.error, 'Nie udało się odczytać historii.'),
          );
        setOperations(result.data.items);
        setHistoryCursor(result.data.nextCursor);
        const id = savedCommand?.operationId ?? view?.operationId ?? null;
        if (typeof id === 'string') {
          selectedId.current = id;
          await readOperation(id, token);
        }
      } catch (cause) {
        if (current(token)) {
          setError(message(cause));
          try {
            setHasRawPending(
              localStorage.getItem(gridCommandKey(apiBaseUrl, gameId)) !== null,
            );
          } catch {
            /* The storage error is already visible. */
          }
        }
      }
    })();
    return () => {
      alive.current = false;
    };
    // The keyed workspace owns one API/game identity for its lifetime.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, apiBaseUrl, gameId]);

  async function run(command: GridCommand, retry = false) {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    setError('');
    const token = ++generation.current;
    try {
      const exact = retry
        ? readGridCommand(localStorage, apiBaseUrl, gameId)
        : saveGridCommand(localStorage, apiBaseUrl, gameId, command);
      if (exact === null) throw new Error('Brak zapisanego polecenia.');
      setPending(exact);
      setHasRawPending(true);
      const result = await sendGridCommand(api, gameId, exact);
      if (result.data === undefined) {
        const stale =
          result.response?.status === 409
            ? 'HTTP 409: nieaktualna komenda, rewizja, manifest lub blokada wykonania. '
            : '';
        throw new Error(
          stale +
            apiErrorMessage(
              result.error,
              'Nieznany wynik polecenia. Zachowano dokładne polecenie do jawnego ponowienia.',
            ),
        );
      }
      if (!current(token)) return;
      // Persist the resulting identity before clearing the successful command.
      localStorage.setItem(
        gridViewKey(apiBaseUrl, gameId),
        JSON.stringify({
          operationId: result.data.operationId,
          selector,
          scope,
        }),
      );
      clearGridCommand(localStorage, apiBaseUrl, gameId, exact);
      if (!current(token)) return;
      setPending(null);
      setHasRawPending(false);
      selectedId.current = result.data.operationId;
      setOperation(result.data);
      setBroadConfirmed(false);
      setOperations((items) => [
        result.data!,
        ...items.filter(
          (item) => item.operationId !== result.data!.operationId,
        ),
      ]);
      await readOperation(result.data.operationId, token);
    } catch (cause) {
      if (current(token)) setError(message(cause));
    } finally {
      locked.current = false;
      if (current(token)) setBusy(false);
    }
  }

  function prepare() {
    void run({
      kind: 'prepare',
      operationId: null,
      body: {
        idempotencyKey: crypto.randomUUID(),
        selector,
        executionScope: scope,
      },
    });
  }
  function command(kind: 'freeze' | 'start' | 'ack' | 'resume' | 'cancel') {
    if (!operation) return;
    const base = {
      idempotencyKey: crypto.randomUUID(),
      expectedRevision: operation.revision,
    };
    const operationId = operation.operationId;
    if (kind === 'freeze' && operation.manifestSha256)
      void run({
        kind,
        operationId,
        body: { ...base, manifestSha256: operation.manifestSha256 },
      });
    if (kind === 'start' && operation.manifestSha256)
      void run({
        kind,
        operationId,
        body: {
          ...base,
          manifestSha256: operation.manifestSha256,
          broadScopeConfirmed: broadConfirmed,
        },
      });
    if (kind === 'resume')
      void run({
        kind,
        operationId,
        body: { ...base, expectedPhase: operation.phase },
      });
    if (kind === 'cancel') void run({ kind, operationId, body: base });
    const pilot = pilots.find((item) => item.operationId === pilotId);
    if (kind === 'ack' && pilot?.reportSha256)
      void run({
        kind,
        operationId,
        body: {
          ...base,
          pilotOperationId: pilot.operationId,
          pilotReportSha256: pilot.reportSha256,
        },
      });
  }

  async function more(kind: 'history' | 'pilot' | 'targets') {
    const token = generation.current;
    setError('');
    try {
      if (kind === 'targets' && operation && targets?.nextCursor) {
        const result = await api.getGridReinferenceTargets(
          gameId,
          operation.operationId,
          targets.nextCursor,
        );
        if (!current(token)) return;
        if (!result.data)
          throw new Error(
            apiErrorMessage(result.error, 'Nie udało się odczytać celów.'),
          );
        setTargets(result.data);
      } else {
        const result = await api.listGridReinferenceOperations(gameId, {
          limit: 50,
          cursor: (kind === 'pilot' ? pilotCursor : historyCursor) ?? undefined,
          compatibleWithOperationId:
            kind === 'pilot' ? operation?.operationId : undefined,
        });
        if (!current(token)) return;
        if (!result.data)
          throw new Error(
            apiErrorMessage(result.error, 'Nie udało się odczytać historii.'),
          );
        if (kind === 'pilot') {
          setPilots((items) => [...items, ...result.data!.items]);
          setPilotCursor(result.data.nextCursor);
        } else {
          setOperations((items) => [...items, ...result.data!.items]);
          setHistoryCursor(result.data.nextCursor);
        }
      }
    } catch (cause) {
      if (current(token)) setError(message(cause));
    }
  }

  const blocked = busy || hasRawPending;
  return (
    <section aria-label="Ponowne rozpoznanie siatek">
      <h3>Ponowne rozpoznanie siatek</h3>
      <p>
        Aktualna przypisana baza, bez nowego treningu. Przygotowanie i
        uruchomienie są osobnymi działaniami.
      </p>
      <fieldset disabled={busy}>
        <legend>Nowy zakres</legend>
        {(Object.keys(categoryLabels) as (keyof typeof categoryLabels)[]).map(
          (category) => (
            <label key={category}>
              <input
                type="checkbox"
                checked={selector.categories?.includes(category) ?? false}
                onChange={(event) => {
                  const next: GridReinferenceSelector = {
                    ...selector,
                    categories: event.target.checked
                      ? [...(selector.categories ?? []), category]
                      : selector.categories?.filter(
                          (item) => item !== category,
                        ),
                  };
                  try {
                    persistView(selectedId.current, next);
                    setSelector(next);
                  } catch (cause) {
                    setError(message(cause));
                  }
                }}
              />
              {categoryLabels[category]}
            </label>
          ),
        )}
        <label>
          Tryb
          <select
            value={scope}
            onChange={(event) => {
              const next = event.target.value as 'pilot' | 'broader';
              try {
                persistView(selectedId.current, selector, next);
                setScope(next);
              } catch (cause) {
                setError(message(cause));
              }
            }}
          >
            <option value="pilot">Pilot — do 100 wystąpień zdjęć</option>
            <option value="broader">Szeroki zakres — nowy manifest</option>
          </select>
        </label>
        <button
          type="button"
          disabled={blocked || !selector.categories?.length}
          onClick={prepare}
        >
          Przygotuj nowy {scope === 'pilot' ? 'pilot' : 'szeroki zakres'}
        </button>
      </fieldset>
      {hasRawPending ? (
        <section aria-label="Zapisane polecenie">
          <p>
            Zapisane polecenie:{' '}
            {pending ? commandLabels[pending.kind] : 'uszkodzony wpis'}. Wynik
            mógł zostać zapisany na serwerze.
          </p>
          <details>
            <summary>Identyfikator zapisanego polecenia</summary>
            {pending?.body.idempotencyKey}
          </details>
          <button
            type="button"
            disabled={busy || pending === null}
            onClick={() => pending && void run(pending, true)}
          >
            Ponów dokładne polecenie
          </button>
          <label>
            <input
              type="checkbox"
              checked={discardConfirmed}
              onChange={(event) => setDiscardConfirmed(event.target.checked)}
            />
            Potwierdzam porzucenie lokalnego polecenia. Operacja na serwerze
            może istnieć.
          </label>
          <button
            type="button"
            disabled={busy || !discardConfirmed}
            onClick={() => {
              try {
                discardGridCommand(
                  localStorage,
                  apiBaseUrl,
                  gameId,
                  discardConfirmed,
                );
                setPending(null);
                setHasRawPending(false);
                setDiscardConfirmed(false);
                setError('');
              } catch (cause) {
                setError(message(cause));
              }
            }}
          >
            Archiwizuj i porzuć polecenie
          </button>
        </section>
      ) : null}
      <label>
        Zapisana operacja
        <select
          aria-label="Zapisana operacja"
          value={operation?.operationId ?? ''}
          disabled={busy}
          onChange={(event) => void selectOperation(event.target.value)}
        >
          <option value="" disabled>
            Wybierz operację
          </option>
          {operations.map((item) => (
            <option key={item.operationId} value={item.operationId}>
              {gridReinferenceStateLabels[item.state] ?? item.state} —{' '}
              {item.preparationStartedAt} — {item.operationId.slice(-8)}
            </option>
          ))}
        </select>
      </label>
      <p>
        Historia ma stabilną kolejność identyfikatorów, nie kolejność czasu
        utworzenia.
      </p>
      {historyCursor ? (
        <button type="button" onClick={() => void more('history')}>
          Dalsza historia
        </button>
      ) : null}
      {operation ? (
        <>
          <button
            type="button"
            disabled={busy}
            onClick={() => void selectOperation(operation.operationId)}
          >
            Odśwież operację
          </button>
          {operation.state === 'prepared' ? (
            <button
              type="button"
              disabled={blocked}
              onClick={() => command('freeze')}
            >
              Zamroź podgląd zakresu
            </button>
          ) : null}
          {operation.executionScope === 'broader' &&
          operation.state === 'frozen' ? (
            <section aria-label="Potwierdzenie pilota">
              <label>
                Zgodny zakończony pilot
                <select
                  value={pilotId}
                  onChange={(event) => setPilotId(event.target.value)}
                >
                  <option value="">Wybierz raport pilota</option>
                  {pilots.map((item) => (
                    <option key={item.operationId} value={item.operationId}>
                      {item.preparationStartedAt} — raport {item.reportSha256}
                    </option>
                  ))}
                </select>
              </label>
              {pilotCursor ? (
                <button type="button" onClick={() => void more('pilot')}>
                  Dalsze zgodne piloty
                </button>
              ) : null}
              <p>
                Potwierdzenie przypina raport i autora. Nie potwierdza jakości
                modelu.
              </p>
              <button
                type="button"
                disabled={blocked || !pilotId}
                onClick={() => command('ack')}
              >
                Potwierdź raport pilota
              </button>
              <label>
                <input
                  type="checkbox"
                  checked={broadConfirmed}
                  onChange={(event) => setBroadConfirmed(event.target.checked)}
                />
                Potwierdzam uruchomienie szerokiego zakresu
              </label>
            </section>
          ) : null}
          {operation.state === 'frozen' ? (
            <button
              type="button"
              disabled={
                blocked ||
                (operation.executionScope === 'broader' &&
                  (!operation.pilotAcknowledgement || !broadConfirmed))
              }
              onClick={() => command('start')}
            >
              Uruchom rozpoznanie
            </button>
          ) : null}
          {['preparing', 'prepared', 'frozen', 'queued', 'running'].includes(
            operation.state,
          ) ? (
            <button
              type="button"
              disabled={blocked}
              onClick={() => command('cancel')}
            >
              Anuluj operację
            </button>
          ) : null}
          {['failed', 'cancelled'].includes(operation.state) &&
          !operation.executionQuarantine ? (
            <button
              type="button"
              disabled={blocked}
              onClick={() => command('resume')}
            >
              Wznów zapisaną fazę
            </button>
          ) : null}
          <GridReinferenceReport
            operation={operation}
            targets={targets}
            busy={busy}
            onNext={() => void more('targets')}
          />
        </>
      ) : null}
      {error ? <p role="alert">{error}</p> : null}
    </section>
  );
}
