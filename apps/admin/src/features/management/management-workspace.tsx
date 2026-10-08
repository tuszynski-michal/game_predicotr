'use client';

import type {
  ManagementPointResponse,
  ManagementMachineResponse,
  ManagementSnapshotResponse,
} from '@game-predictor/admin-api-client';
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from 'react';
import {
  executeManagementOperation,
  readManagementOperation,
  MANAGEMENT_PENDING_KEY,
  type ManagementOperation,
} from './management-operation';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { confirmBoardSearchDiscardDraft } from '@game-predictor/board-search-ui';
import {
  type ManagementGameClient,
  type ManagementStructureClient,
  managementSessionStorage,
} from './management-client';
import { ManagementGameWorkspace } from './management-game-workspace';
import {
  managementSlotWritesAllowed,
  managementSlotsAvailable,
} from './management-data-source';
import { readManagementSlotOperation } from './management-slot-operation';

export type ManagementClient = ManagementStructureClient &
  Partial<ManagementGameClient>;

interface Props {
  apiBaseUrl: string;
  client?: ManagementClient;
  storageNamespace?: string;
  onDirtyChange?: (dirty: boolean) => void;
}
type Editor =
  | { kind: 'point'; point?: ManagementPointResponse }
  | {
      kind: 'machine';
      point: ManagementPointResponse;
      machine?: ManagementMachineResponse;
    }
  | null;

export function ManagementWorkspace({
  apiBaseUrl,
  client,
  storageNamespace = 'local-owner',
  onDirtyChange,
}: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [snapshot, setSnapshot] = useState<ManagementSnapshotResponse | null>(
    null,
  );
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const busyRef = useRef(false);
  const loadGeneration = useRef(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [machineId, setMachineId] = useState<string | null>(null);
  const [gameId, setGameId] = useState<string | null>(null);
  const draftDirty = useRef(false);
  const changeDirty = useCallback(
    (dirty: boolean) => {
      draftDirty.current = dirty;
      onDirtyChange?.(dirty);
    },
    [onDirtyChange],
  );
  const navigationAllowed = () =>
    confirmBoardSearchDiscardDraft(draftDirty.current);
  const [editor, setEditor] = useState<Editor>(null);
  const [name, setName] = useState('');
  const [city, setCity] = useState('');
  const [street, setStreet] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [notice, setNotice] = useState('');
  // Keep the exact command after uncertain network failures; retry must use its UUID.
  const pending = useRef<ManagementOperation | null>(null);
  const [retryAvailable, setRetryAvailable] = useState(false);

  const load = useCallback(async () => {
    const generation = ++loadGeneration.current;
    setLoading(true);
    try {
      const response = await api.getManagementSnapshot();
      if (generation !== loadGeneration.current) return;
      if (!response.data) throw new Error('Nie udało się pobrać punktów.');
      setSnapshot(response.data);
      setError('');
    } catch (cause) {
      if (generation === loadGeneration.current)
        setError(cause instanceof Error ? cause.message : 'Błąd API.');
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, [api]);
  const invalidateLoad = useCallback(() => {
    ++loadGeneration.current;
  }, []);
  useEffect(() => {
    let cancelled = false;
    void Promise.resolve().then(() => {
      if (!cancelled) void load();
    });
    return () => {
      cancelled = true;
      invalidateLoad();
    };
  }, [load, invalidateLoad]);

  useEffect(() => {
    try {
      pending.current = readManagementOperation(window.sessionStorage);
      setRetryAvailable(pending.current !== null);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Błąd odzyskiwania operacji.',
      );
    }
  }, []);

  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (!active) return;
      const storage = managementSessionStorage();
      try {
        const pendingSlot = readManagementSlotOperation(
          storage,
          storageNamespace,
        );
        const raw: unknown = JSON.parse(
          storage?.getItem(
            `game-predictor:management:selection:${storageNamespace}`,
          ) ?? 'null',
        );
        if (pendingSlot) {
          setMachineId(pendingSlot.machineId);
          setGameId(pendingSlot.gameId);
        } else if (
          raw &&
          typeof raw === 'object' &&
          'machineId' in raw &&
          typeof raw.machineId === 'string' &&
          'gameId' in raw &&
          typeof raw.gameId === 'string'
        ) {
          setMachineId(raw.machineId);
          setGameId(raw.gameId);
        }
      } catch (cause) {
        setError(
          cause instanceof Error ? cause.message : 'Błąd odzyskiwania wyboru.',
        );
      }
    });
    return () => {
      active = false;
    };
  }, [storageNamespace]);

  const run = async (operation: ManagementOperation) => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    pending.current = operation;
    try {
      window.sessionStorage.setItem(
        MANAGEMENT_PENDING_KEY,
        JSON.stringify(operation),
      );
      const response = (await executeManagementOperation(api, operation)) as {
        data?: unknown;
        error?: { code?: string; message?: string };
        response?: Response;
      };
      if (!response.data) {
        if (response.response && response.response.status < 500) {
          window.sessionStorage.removeItem(MANAGEMENT_PENDING_KEY);
          pending.current = null;
          setRetryAvailable(false);
        }
        throw new Error(
          response.error?.message ??
            'Zapis odrzucony. Odśwież dane przed ponowieniem.',
        );
      }
      window.sessionStorage.removeItem(MANAGEMENT_PENDING_KEY);
      pending.current = null;
      setRetryAvailable(false);
      setEditor(null);
      setNotice('Zapisano. Historia pozostaje zachowana.');
      await load();
    } catch (cause) {
      setRetryAvailable(pending.current !== null);
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nieznany wynik zapisu. Ponów tę samą operację.',
      );
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const openEditor = (next: Editor) => {
    setEditor(next);
    setError('');
    setName(
      next?.kind === 'point'
        ? (next.point?.name ?? '')
        : (next?.machine?.name ?? ''),
    );
    setCity(next?.kind === 'point' ? (next.point?.city ?? '') : '');
    setStreet(next?.kind === 'point' ? (next.point?.street ?? '') : '');
  };
  const save = (event: FormEvent) => {
    event.preventDefault();
    if (!editor || !name.trim()) return;
    const operationId = crypto.randomUUID();
    if (editor.kind === 'point') {
      const point = editor.point;
      const body = {
        operationId,
        expectedRevision: point?.revision ?? 0,
        name: name.trim(),
        city: city.trim(),
        street: street.trim(),
        archived: point?.archived ?? false,
      };
      void run({
        kind: 'point',
        ...(point ? { pointId: point.id } : {}),
        body,
      });
    } else {
      const { point, machine } = editor;
      const body = {
        operationId,
        expectedRevision: machine?.revision ?? 0,
        name: name.trim(),
        archived: machine?.archived ?? false,
      };
      void run({
        kind: 'machine',
        pointId: point.id,
        ...(machine ? { machineId: machine.id } : {}),
        body,
      });
    }
  };
  const archivePoint = (point: ManagementPointResponse) => {
    if (!navigationAllowed()) return;
    if (
      !point.archived &&
      !window.confirm(
        `Archiwizować punkt ${point.name}? Maszyny i historia pozostaną zachowane.`,
      )
    )
      return;
    const body = {
      operationId: crypto.randomUUID(),
      expectedRevision: point.revision,
      name: point.name,
      city: point.city,
      street: point.street,
      archived: !point.archived,
    };
    void run({ kind: 'point', pointId: point.id, body });
  };
  const archiveMachine = (
    point: ManagementPointResponse,
    machine: ManagementMachineResponse,
  ) => {
    if (!navigationAllowed()) return;
    if (
      !machine.archived &&
      !window.confirm(
        `Archiwizować maszynę ${machine.name}? Historia pozostanie zachowana.`,
      )
    )
      return;
    const body = {
      operationId: crypto.randomUUID(),
      expectedRevision: machine.revision,
      name: machine.name,
      archived: !machine.archived,
    };
    void run({
      kind: 'machine',
      pointId: point.id,
      machineId: machine.id,
      body,
    });
  };
  const assign = (
    machine: ManagementMachineResponse,
    gameId: string,
    attach: boolean,
  ) => {
    if (!navigationAllowed()) return;
    const retained = machine.assignments
      .filter((row) => row.attached && row.gameId !== gameId)
      .map((row) => row.gameId);
    const body = {
      operationId: crypto.randomUUID(),
      expectedRevision: machine.revision,
      gameIds: attach ? [...retained, gameId] : retained,
    };
    void run({ kind: 'assignments', machineId: machine.id, body });
  };
  const disabled = busy || retryAvailable;
  const selected =
    snapshot?.points.find((point) => point.id === selectedId) ??
    snapshot?.points.find((point) =>
      point.machines.some((machine) => machine.id === machineId),
    );
  const machine = selected?.machines.find((row) => row.id === machineId);
  const assignment = machine?.assignments.find((row) => row.gameId === gameId);
  const chooseGame = (nextMachine: string, nextGame: string | null) => {
    if (nextMachine === machineId && nextGame === gameId) return;
    if (!navigationAllowed()) return;
    changeDirty(false);
    setMachineId(nextMachine);
    setGameId(nextGame);
    try {
      managementSessionStorage()?.setItem(
        `game-predictor:management:selection:${storageNamespace}`,
        JSON.stringify({ machineId: nextMachine, gameId: nextGame }),
      );
    } catch {
      /* Selection preference is optional; mutation receipts are stored separately. */
    }
  };
  return (
    <section className="catalog-panel" aria-label="Panel Administracyjny">
      <h2>Panel Administracyjny</h2>
      <div className="management-actions">
        <button onClick={() => void load()} disabled={busy}>
          Odśwież
        </button>
        <button
          onClick={() => openEditor({ kind: 'point' })}
          disabled={disabled}
        >
          Dodaj punkt
        </button>
        <label>
          <input
            type="checkbox"
            checked={showArchived}
            onChange={(event) => setShowArchived(event.target.checked)}
          />{' '}
          Pokaż archiwalne
        </label>
      </div>
      {loading ? <p role="status">Ładowanie punktów…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {retryAvailable ? (
        <button
          disabled={busy}
          onClick={() => {
            if (pending.current) void run(pending.current);
          }}
        >
          Ponów ten sam zapis
        </button>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}
      {snapshot && !snapshot.points.length ? (
        <p>Brak punktów. Dodaj pierwszy punkt.</p>
      ) : null}
      <div className="management-tiles">
        {snapshot?.points
          .filter((point) => showArchived || !point.archived)
          .map((point) => (
            <article className="management-tile" key={point.id}>
              <button
                aria-pressed={selectedId === point.id}
                onClick={() => {
                  if (!navigationAllowed()) return;
                  changeDirty(false);
                  setSelectedId(point.id);
                  setMachineId(null);
                  setGameId(null);
                }}
              >
                <strong>{point.name}</strong>
                <span>
                  {point.city}, {point.street}
                </span>
                <span>
                  {point.machines.length} maszyn
                  {point.archived ? ' · Archiwalny' : ''}
                </span>
              </button>
              <div className="management-actions">
                <button
                  disabled={disabled}
                  onClick={() => openEditor({ kind: 'point', point })}
                >
                  Edytuj punkt
                </button>
                <button disabled={disabled} onClick={() => archivePoint(point)}>
                  {point.archived ? 'Przywróć punkt' : 'Archiwizuj punkt'}
                </button>
              </div>
            </article>
          ))}
      </div>
      {selected ? (
        <section aria-label={`Maszyny: ${selected.name}`}>
          <h3>{selected.name} — maszyny</h3>
          {selected.archived ? (
            <p>Punkt archiwalny. Przywróć go przed edycją maszyn.</p>
          ) : (
            <button
              disabled={disabled}
              onClick={() => openEditor({ kind: 'machine', point: selected })}
            >
              Dodaj maszynę
            </button>
          )}
          {!selected.machines.length ? <p>Brak maszyn.</p> : null}
          <div className="management-tiles">
            {selected.machines
              .filter((machine) => showArchived || !machine.archived)
              .map((machine) => (
                <article className="management-tile" key={machine.id}>
                  <h4>
                    {machine.name}
                    {machine.archived ? ' · Archiwalna' : ''}
                  </h4>
                  <button
                    onClick={() =>
                      chooseGame(
                        machine.id,
                        machine.assignments.find(
                          (row) => row.attached && row.gameStatus === 'active',
                        )?.gameId ??
                          machine.assignments[0]?.gameId ??
                          null,
                      )
                    }
                  >
                    Otwórz gry maszyny {machine.name}
                  </button>
                  <div className="management-actions">
                    <button
                      disabled={disabled || selected.archived}
                      onClick={() =>
                        openEditor({
                          kind: 'machine',
                          point: selected,
                          machine,
                        })
                      }
                    >
                      Edytuj maszynę
                    </button>
                    <button
                      disabled={disabled || selected.archived}
                      onClick={() => archiveMachine(selected, machine)}
                    >
                      {machine.archived
                        ? 'Przywróć maszynę'
                        : 'Archiwizuj maszynę'}
                    </button>
                  </div>
                  <fieldset
                    disabled={disabled || selected.archived || machine.archived}
                  >
                    <legend>Przypisane gry</legend>
                    {snapshot?.activeGames.map((game) => (
                      <label className="management-game" key={game.id}>
                        <input
                          type="checkbox"
                          checked={machine.assignments.some(
                            (row) => row.gameId === game.id && row.attached,
                          )}
                          onChange={(event) =>
                            assign(machine, game.id, event.target.checked)
                          }
                        />
                        {game.name}
                      </label>
                    ))}
                    {!snapshot?.activeGames.length ? (
                      <p>Brak aktywnych gier w katalogu.</p>
                    ) : null}
                  </fieldset>
                  {machine.assignments
                    .filter(
                      (row) => !row.attached || row.gameStatus !== 'active',
                    )
                    .map((row) => (
                      <p key={row.gameId}>
                        {row.gameName} ·{' '}
                        {row.attached ? 'Gra nieaktywna' : 'Odłączona'} ·
                        Historia zachowana
                        {row.attached ? (
                          <button
                            disabled={
                              disabled || selected.archived || machine.archived
                            }
                            onClick={() => assign(machine, row.gameId, false)}
                          >
                            Odłącz {row.gameName}
                          </button>
                        ) : null}
                      </p>
                    ))}
                </article>
              ))}
          </div>
        </section>
      ) : null}
      {machine ? (
        <section aria-label={`Gry maszyny: ${machine.name}`}>
          <h3>{machine.name} — gry i zapisane stawki</h3>
          <label>
            Gra
            <select
              aria-label="Gra maszyny"
              value={gameId ?? ''}
              onChange={(event) => chooseGame(machine.id, event.target.value)}
            >
              <option value="" disabled>
                Wybierz grę
              </option>
              {machine.assignments.map((row) => (
                <option key={row.gameId} value={row.gameId}>
                  {row.gameName}
                  {!row.attached
                    ? ' · Odłączona'
                    : row.gameStatus !== 'active'
                      ? ' · Archiwalna'
                      : ''}
                </option>
              ))}
            </select>
          </label>
          {!machine.assignments.length ? (
            <p>Przypisz grę do maszyny, aby zapisać układ.</p>
          ) : null}
          {assignment && selected && managementSlotsAvailable(api) ? (
            <ManagementGameWorkspace
              key={`${machine.id}:${assignment.gameId}`}
              api={api as ManagementGameClient}
              machineId={machine.id}
              gameId={assignment.gameId}
              writeAllowed={managementSlotWritesAllowed(
                selected.archived,
                machine.archived,
                assignment,
              )}
              storageNamespace={storageNamespace}
              onDirtyChange={changeDirty}
            />
          ) : null}
        </section>
      ) : null}
      {editor ? (
        <form
          onSubmit={save}
          aria-label={
            editor.kind === 'point' ? 'Edycja punktu' : 'Edycja maszyny'
          }
        >
          <h3>{editor.kind === 'point' ? 'Punkt' : 'Maszyna'}</h3>
          <label>
            Nazwa
            <input
              required
              maxLength={200}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          {editor.kind === 'point' ? (
            <>
              <label>
                Miasto
                <input
                  required
                  maxLength={200}
                  value={city}
                  onChange={(event) => setCity(event.target.value)}
                />
              </label>
              <label>
                Ulica
                <input
                  required
                  maxLength={200}
                  value={street}
                  onChange={(event) => setStreet(event.target.value)}
                />
              </label>
            </>
          ) : null}
          <div className="management-actions">
            <button
              type="submit"
              disabled={
                disabled ||
                !name.trim() ||
                (editor.kind === 'point' && (!city.trim() || !street.trim()))
              }
            >
              Zapisz
            </button>
            <button
              type="button"
              disabled={disabled}
              onClick={() => setEditor(null)}
            >
              Anuluj
            </button>
          </div>
        </form>
      ) : null}
    </section>
  );
}
