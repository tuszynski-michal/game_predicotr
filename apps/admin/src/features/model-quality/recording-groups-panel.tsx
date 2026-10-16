'use client';

import type {
  AdminApiClient,
  GridModelManifest,
  JobResponse,
  SourceRecordingCommandRequest,
  SourceRecordingGroupResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import {
  completeRecordingCommand,
  discardRecordingCommand,
  readRecordingCommand,
  recordingCommandKey,
  reserveRecordingCommand,
} from './recording-groups-command';
import {
  recordingGroupLabel,
  recordingReasonLabel,
  recordingSourceIds,
} from './recording-groups-state';
import { RecordingImportPicker } from './recording-import-picker';
import {
  clearRecordingRegistration,
  discardRecordingRegistration,
  nextRecordingMembershipCommand,
  readRecordingRegistration,
  saveRecordingRegistration,
  type RecordingRegistration,
} from './recording-registration';

type RecordingClient = Pick<
  AdminApiClient,
  | 'getGameGridModelAssignment'
  | 'listSourceRecordingGroups'
  | 'commandSourceRecordingGroups'
  | 'listJobs'
>;
type Props = {
  readonly apiBaseUrl: string;
  readonly gameId: string;
  readonly client?: RecordingClient;
  /** A confirmed recording change lets later steps re-read (TASK-1000). */
  readonly onChanged?: () => void;
};
const message = (cause: unknown) =>
  cause instanceof Error
    ? cause.message
    : 'Operacja nagrania jest niedostępna.';
const qualificationLabels = {
  unresolved: 'Nierozstrzygnięte pochodzenie',
  blocked: 'Dane chronione lub konflikt',
  eligible: 'Pochodzenie rozstrzygnięte',
};

export function RecordingGroupsPanel(props: Props) {
  return (
    <RecordingWorkspace
      key={`${props.apiBaseUrl}:${props.gameId}`}
      {...props}
    />
  );
}

function RecordingWorkspace({ apiBaseUrl, gameId, client, onChanged }: Props) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [groups, setGroups] = useState<SourceRecordingGroupResponse[]>([]);
  const [manifest, setManifest] = useState<GridModelManifest | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState('');
  const [sourceIds, setSourceIds] = useState('');
  const [importJobId, setImportJobId] = useState('');
  const [importJobs, setImportJobs] = useState<JobResponse[]>([]);
  const [registration, setRegistration] =
    useState<RecordingRegistration | null>(null);
  const [registrationBusy, setRegistrationBusy] = useState(false);
  const [recordingConfirmed, setRecordingConfirmed] = useState(false);
  const registrationRunning = useRef(false);
  const stopRegistration = useRef(false);
  const [page, setPage] = useState(1);
  const [role, setRole] = useState<'TRAIN' | 'VALIDATION' | 'REGRESSION'>(
    'TRAIN',
  );
  const [otherGroupId, setOtherGroupId] = useState('');
  const [independent, setIndependent] = useState(false);
  const [pending, setPending] = useState<SourceRecordingCommandRequest | null>(
    null,
  );
  const [hasPending, setHasPending] = useState(false);
  const [storageReady, setStorageReady] = useState(false);
  const [discardConfirmed, setDiscardConfirmed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const alive = useRef(false);
  const locked = useRef(false);
  const readGeneration = useRef(0);
  const scopeGeneration = useRef(0);
  const selected = groups.find((group) => group.id === selectedId) ?? null;
  const disabled =
    busy ||
    loading ||
    hasPending ||
    !storageReady ||
    registrationBusy ||
    registration !== null;

  async function load(familyId?: string, after?: string) {
    const generation = ++readGeneration.current;
    setLoading(true);
    try {
      const result = await api.listSourceRecordingGroups(gameId, {
        familyId,
        limit: 100,
        after,
      });
      if (!alive.current || generation !== readGeneration.current) return;
      if (result.data === undefined)
        throw new Error('Nie udało się odczytać nagrań tej gry.');
      setGroups((previous) =>
        after
          ? [
              ...previous,
              ...result.data.items.filter(
                (group) => !previous.some((item) => item.id === group.id),
              ),
            ]
          : result.data.items,
      );
      setNextCursor(result.data.nextCursor ?? null);
    } catch (cause) {
      if (alive.current && generation === readGeneration.current)
        setError(message(cause));
    } finally {
      if (alive.current && generation === readGeneration.current)
        setLoading(false);
    }
  }

  useEffect(() => {
    alive.current = true;
    readGeneration.current++;
    scopeGeneration.current++;
    let cancelled = false;
    void (async () => {
      try {
        setHasPending(
          localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)) !==
            null,
        );
        setPending(readRecordingCommand(localStorage, apiBaseUrl, gameId));
        setRegistration(
          readRecordingRegistration(localStorage, apiBaseUrl, gameId),
        );
        setStorageReady(true);
      } catch {
        setHasPending(true);
        setStorageReady(false);
        setError(
          'Nie można odczytać zapisanego polecenia. Zachowano je do odzyskania.',
        );
      }
      let family: string | undefined;
      try {
        const result = await api.getGameGridModelAssignment(gameId);
        if (cancelled) return;
        if (
          result.data !== undefined &&
          result.data.gameId === gameId &&
          result.data.version?.manifest
        ) {
          setManifest(result.data.version.manifest);
          family = result.data.version.manifest.familyId;
        } else {
          setNotice(
            'Brak potwierdzonej rodziny geometrii. Przypisanie ról i rozstrzygnięcie pozostają niedostępne.',
          );
        }
      } catch {
        if (cancelled) return;
        setNotice(
          'Nie odczytano rodziny geometrii. Przypisanie ról i rozstrzygnięcie pozostają niedostępne.',
        );
      }
      if (!cancelled) await load(family);
    })();
    return () => {
      cancelled = true;
      alive.current = false;
      stopRegistration.current = true;
    };
    // The workspace is remounted for each API/game scope. A changed client starts a new read.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, apiBaseUrl, gameId]);

  async function execute(
    command: SourceRecordingCommandRequest,
    retry = false,
    fromRegistration = false,
  ) {
    if (locked.current || (!retry && disabled && !fromRegistration))
      return null;
    locked.current = true;
    const generation = scopeGeneration.current;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const exact = retry
        ? readRecordingCommand(localStorage, apiBaseUrl, gameId)
        : reserveRecordingCommand(localStorage, apiBaseUrl, gameId, command);
      if (!exact) throw new Error('Nie znaleziono polecenia do ponowienia.');
      setPending(exact);
      setHasPending(true);
      const result = await api.commandSourceRecordingGroups(gameId, exact);
      if (!alive.current || generation !== scopeGeneration.current) return null;
      if (result.data === undefined) {
        const status = result.response?.status;
        throw new Error(
          status === 409
            ? 'Konflikt nagrania (HTTP 409). Odśwież stan; zapisane polecenie zachowano do ponowienia albo jawnego porzucenia.'
            : 'Nie otrzymano potwierdzenia zapisu. Ponów dokładne zapisane polecenie.',
        );
      }
      const receipt = result.data;
      if (
        receipt.idempotencyKey !== exact.idempotencyKey ||
        receipt.commandKind !== exact.kind ||
        (exact.kind !== 'prepare' && receipt.group.id !== exact.groupId)
      ) {
        throw new Error(
          'Odpowiedź nie potwierdza zapisanego polecenia. Zachowano je do ponowienia.',
        );
      }
      if (receipt.statusCode < 200 || receipt.statusCode >= 300)
        throw new Error(
          'Serwer odmówił zmiany nagrania. Polecenie zachowano do odzyskania.',
        );
      completeRecordingCommand(localStorage, apiBaseUrl, gameId, exact);
      const remaining = readRecordingCommand(localStorage, apiBaseUrl, gameId);
      setPending(remaining);
      setHasPending(remaining !== null);
      setGroups((previous) => [
        receipt.group,
        ...previous.filter((item) => item.id !== receipt.group.id),
      ]);
      setSelectedId(receipt.group.id);
      if (
        exact.kind === 'attach' &&
        typeof receipt.group.nextPageIndex === 'number'
      )
        setPage(receipt.group.nextPageIndex + 1);
      if (exact.kind === 'prepare') {
        setPage(1);
        setIndependent(false);
      }
      setNotice(
        exact.kind === 'freeze'
          ? 'Zapisano prowizoryczne rozstrzygnięcie pochodzenia. Nie zamrożono kohorty ani nie uruchomiono treningu.'
          : 'Potwierdzono zapis nagrania.',
      );
      onChanged?.();
      return receipt.group;
    } catch (cause) {
      if (alive.current && generation === scopeGeneration.current) {
        setError(message(cause));
        try {
          setHasPending(
            localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)) !==
              null,
          );
        } catch {
          setStorageReady(false);
          setHasPending(true);
        }
      }
      return null;
    } finally {
      locked.current = false;
      if (alive.current && generation === scopeGeneration.current)
        setBusy(false);
    }
  }

  function prepare() {
    try {
      if (sourceIds.trim() && importJobId.trim())
        throw new Error('Wybierz identyfikatory zdjęć albo jeden import.');
      const selection = importJobId.trim()
        ? { importJobId: importJobId.trim() }
        : { sourceIds: recordingSourceIds(sourceIds) };
      if (
        typeof selection.importJobId === 'string' &&
        !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
          selection.importJobId,
        )
      )
        throw new Error('Identyfikator importu musi być poprawnym UUID.');
      if (!recordingConfirmed)
        throw new Error('Potwierdź wybór całego nagrania.');
      const preparation: SourceRecordingCommandRequest = {
        kind: 'prepare',
        idempotencyKey: crypto.randomUUID(),
        expectedRevision: 0,
        selection,
      };
      const intent = { prepare: preparation, groupId: null };
      if (readRecordingRegistration(localStorage, apiBaseUrl, gameId) !== null)
        throw new Error('Najpierw wznów zapisaną rejestrację.');
      saveRecordingRegistration(localStorage, apiBaseUrl, gameId, intent);
      setRegistration(intent);
      void register(intent, false);
    } catch (cause) {
      setError(message(cause));
    }
  }

  async function register(intent: RecordingRegistration, resume: boolean) {
    if (registrationRunning.current) return;
    registrationRunning.current = true;
    stopRegistration.current = false;
    setRegistrationBusy(true);
    setError('');
    try {
      let currentIntent = intent;
      let group: SourceRecordingGroupResponse | null = null;
      const outstanding = readRecordingCommand(
        localStorage,
        apiBaseUrl,
        gameId,
      );
      if (outstanding) {
        if (
          !['prepare', 'attach', 'complete'].includes(outstanding.kind) ||
          (currentIntent.groupId &&
            outstanding.groupId !== currentIntent.groupId)
        )
          throw new Error('Zapisane polecenie nie należy do tej rejestracji.');
        group = await execute(outstanding, true, true);
        if (!group) return;
      } else if (!currentIntent.groupId) {
        group = await execute(currentIntent.prepare, false, true);
        if (!group) return;
      }
      if (!alive.current) return;
      if (group && currentIntent.groupId !== group.id) {
        currentIntent = { ...currentIntent, groupId: group.id };
        saveRecordingRegistration(
          localStorage,
          apiBaseUrl,
          gameId,
          currentIntent,
        );
        setRegistration(currentIntent);
      }
      if (resume && currentIntent.groupId) {
        const fresh = await api.listSourceRecordingGroups(gameId, {
          groupId: currentIntent.groupId,
          familyId: manifest?.familyId,
          limit: 1,
        });
        if (!alive.current) return;
        group =
          fresh.data?.items.find((item) => item.id === currentIntent.groupId) ??
          null;
        if (!group)
          throw new Error(
            'Nie odczytano zapisanego nagrania tej gry. Rejestrację zachowano.',
          );
      }
      if (!group) throw new Error('Brak potwierdzonego stanu nagrania.');
      for (let step = 0; step <= group.pageCount + 1; step++) {
        if (!alive.current || stopRegistration.current) {
          if (alive.current)
            setNotice('Rejestracja zatrzymana. Możesz ją jawnie wznowić.');
          return;
        }
        const command = nextRecordingMembershipCommand(group);
        if (command === null) {
          clearRecordingRegistration(
            localStorage,
            apiBaseUrl,
            gameId,
            currentIntent,
          );
          setRegistration(null);
          setNotice(
            'Zarejestrowano całe nagranie. Niezależność i rolę potwierdź osobno.',
          );
          return;
        }
        const previous = group;
        const updated = await execute(command, false, true);
        if (!updated || !alive.current) return;
        group = updated;
        if (
          command.kind === 'attach' &&
          (!('registeredPages' in group) ||
            !('registeredPages' in previous) ||
            typeof group.registeredPages !== 'number' ||
            typeof previous.registeredPages !== 'number' ||
            group.registeredPages <= previous.registeredPages)
        )
          throw new Error(
            'Brak potwierdzonego postępu partii. Rejestrację zatrzymano.',
          );
      }
      throw new Error(
        'Nie potwierdzono zakończenia rejestracji. Wznów po odświeżeniu stanu.',
      );
    } catch (cause) {
      if (alive.current) setError(message(cause));
    } finally {
      registrationRunning.current = false;
      if (alive.current) setRegistrationBusy(false);
    }
  }

  function mutate(
    kind: SourceRecordingCommandRequest['kind'],
    extra: Partial<SourceRecordingCommandRequest> = {},
  ) {
    if (!selected) return;
    void execute({
      kind,
      idempotencyKey: crypto.randomUUID(),
      expectedRevision: selected.revision,
      groupId: selected.id,
      ...extra,
    });
  }

  function discard() {
    try {
      discardRecordingCommand(
        localStorage,
        apiBaseUrl,
        gameId,
        discardConfirmed,
      );
      if (discardConfirmed)
        discardRecordingRegistration(localStorage, apiBaseUrl, gameId);
      setRegistration(
        readRecordingRegistration(localStorage, apiBaseUrl, gameId),
      );
      setPending(readRecordingCommand(localStorage, apiBaseUrl, gameId));
      setHasPending(
        localStorage.getItem(recordingCommandKey(apiBaseUrl, gameId)) !== null,
      );
      setStorageReady(true);
      setDiscardConfirmed(false);
      setError('');
      setNotice(
        'Zachowano surowe polecenie w archiwum. Porzucenie lokalnego wpisu nie cofa zapisu na serwerze.',
      );
    } catch (cause) {
      setError(message(cause));
    }
  }

  return (
    <section
      className="modelQualityPanel recordingGroupsPanel"
      aria-label="Nagrania i role kontrolne"
    >
      <h3>Nagrania i role kontrolne</h3>
      <p>
        Jedna grupa obejmuje całe nagranie. Folder ani brak duplikatu nie
        dowodzą niezależności. Role dotyczą geometrii.
      </p>
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {loading ? (
        <p aria-busy="true">Odczytywanie nagrań…</p>
      ) : groups.length === 0 ? (
        <p>
          Brak zarejestrowanych nagrań. Pochodzenie źródeł pozostaje
          nierozstrzygnięte.
        </p>
      ) : null}
      <button
        type="button"
        disabled={busy || loading}
        onClick={() => void load(manifest?.familyId)}
      >
        Odśwież nagrania
      </button>
      {nextCursor ? (
        <button
          type="button"
          disabled={busy || loading}
          onClick={() => void load(manifest?.familyId, nextCursor)}
        >
          Wczytaj kolejne nagrania
        </button>
      ) : null}
      {registration ? (
        <aside aria-label="Postęp rejestracji nagrania">
          <p>
            {registrationBusy
              ? 'Rejestrowanie nagrania partiami…'
              : 'Rejestracja nagrania oczekuje na jawne wznowienie.'}
          </p>
          {registrationBusy ? (
            <button
              type="button"
              onClick={() => {
                stopRegistration.current = true;
              }}
            >
              Zatrzymaj po bieżącej partii
            </button>
          ) : (
            <button
              type="button"
              disabled={busy || loading}
              onClick={() => void register(registration, true)}
            >
              Wznów rejestrację nagrania
            </button>
          )}
        </aside>
      ) : null}
      {hasPending || registration ? (
        <aside aria-label="Odzyskiwanie polecenia nagrania">
          <p>
            Zapisane polecenie oczekuje na potwierdzenie. Nowe zmiany są
            zablokowane.
          </p>
          {pending && !registration ? (
            <button
              type="button"
              disabled={busy || registrationBusy}
              onClick={() => void execute(pending, true)}
            >
              Ponów dokładne polecenie
            </button>
          ) : null}
          <label>
            <input
              type="checkbox"
              checked={discardConfirmed}
              disabled={busy}
              onChange={(event) => setDiscardConfirmed(event.target.checked)}
            />
            Potwierdzam porzucenie lokalnego polecenia po zapisaniu archiwum.
            Zapis na serwerze może już istnieć.
          </label>
          <button
            type="button"
            disabled={busy || registrationBusy || !discardConfirmed}
            onClick={discard}
          >
            Zachowaj archiwum i porzuć polecenie
          </button>
        </aside>
      ) : null}
      <fieldset disabled={disabled}>
        <legend>Nowe nagranie</legend>
        <RecordingImportPicker
          api={api}
          gameId={gameId}
          value={importJobId}
          disabled={disabled}
          onLoaded={setImportJobs}
          onChange={(id) => {
            setImportJobId(id);
            setSourceIds('');
          }}
        />
        <details>
          <summary>Zaawansowane: dokładny wybór zdjęć</summary>
          <label>
            Identyfikatory zdjęć (maksymalnie 200)
            <textarea
              value={sourceIds}
              onChange={(event) => {
                setSourceIds(event.target.value);
                setImportJobId('');
              }}
            />
          </label>
        </details>
        <label>
          <input
            type="checkbox"
            checked={recordingConfirmed}
            onChange={(event) => setRecordingConfirmed(event.target.checked)}
          />
          Potwierdzam, że wybrany import lub dokładny wybór zdjęć obejmuje całe
          nagranie.
        </label>
        <p>
          Rejestracja utrwala wybór zdjęć. Niezależność i rolę potwierdzisz
          osobno.
        </p>
        <button
          type="button"
          disabled={!recordingConfirmed || (!importJobId && !sourceIds.trim())}
          onClick={prepare}
        >
          Zarejestruj nagranie
        </button>
      </fieldset>
      {groups.length > 0 ? (
        <>
          <label>
            Nagranie
            <select
              aria-label="Nagranie"
              value={selectedId}
              disabled={busy}
              onChange={(event) => {
                setSelectedId(event.target.value);
                setPage(1);
                setIndependent(false);
                setOtherGroupId('');
              }}
            >
              <option value="">Wybierz nagranie</option>
              {groups.map((group) => (
                <option key={group.id} value={group.id}>
                  {recordingGroupLabel(group, importJobs)} ·{' '}
                  {group.registeredSources}/{group.expectedSources} ·{' '}
                  {group.role ?? 'bez roli'} ·{' '}
                  {qualificationLabels[group.qualification]}
                </option>
              ))}
            </select>
          </label>
          {selected ? (
            <fieldset disabled={disabled}>
              <legend>Wybrane nagranie</legend>
              <p>
                {qualificationLabels[selected.qualification]} ·{' '}
                {selected.role ?? 'Bez roli'} · rewizja {selected.revision}
              </p>
              <p>
                Członkostwo: {selected.registeredSources}/
                {selected.expectedSources}.{' '}
                {selected.membershipComplete
                  ? 'Kompletne.'
                  : 'Niekompletne; kwalifikacja zablokowana.'}
              </p>
              <p>
                Deklaracja:{' '}
                {selected.declared
                  ? selected.independent
                    ? 'potwierdzona niezależność'
                    : 'brak niezależności'
                  : 'brak deklaracji'}
                .
              </p>
              {selected.reasonCodes.length ? (
                <ul>
                  {selected.reasonCodes.map((reason) => (
                    <li key={reason}>{recordingReasonLabel(reason)}</li>
                  ))}
                </ul>
              ) : null}
              <details>
                <summary>
                  Zaawansowane: identyfikatory i partie nagrania
                </summary>
                <p>
                  Identyfikator nagrania: <code>{selected.id}</code>
                </p>
                <p>Kody stanu: {selected.reasonCodes.join(', ')}</p>
                {selected.manifestSha256 ? (
                  <p>
                    Manifest nagrania: <code>{selected.manifestSha256}</code>
                  </p>
                ) : null}
                {!selected.membershipComplete && selected.manifestId ? (
                  <>
                    <label>
                      Strona członkostwa (1–{selected.pageCount})
                      <input
                        type="number"
                        min={1}
                        max={selected.pageCount}
                        value={page}
                        onChange={(event) =>
                          setPage(Number(event.target.value))
                        }
                      />
                    </label>
                    <button
                      type="button"
                      disabled={
                        !Number.isInteger(page) ||
                        page < 1 ||
                        page > selected.pageCount
                      }
                      onClick={() =>
                        mutate('attach', {
                          manifestId: selected.manifestId,
                          pageIndex: page - 1,
                        })
                      }
                    >
                      Zarejestruj stronę manifestu
                    </button>
                    <button
                      type="button"
                      disabled={
                        selected.registeredSources !== selected.expectedSources
                      }
                      onClick={() => mutate('complete')}
                    >
                      Potwierdź kompletne członkostwo
                    </button>
                  </>
                ) : null}
              </details>
              <label>
                <input
                  type="checkbox"
                  checked={independent}
                  onChange={(event) => setIndependent(event.target.checked)}
                />
                Potwierdzam, że manifest obejmuje całe nagranie i jest
                niezależny od nagrań kontrolnych.
              </label>
              <button
                type="button"
                disabled={!selected.membershipComplete || !independent}
                onClick={() =>
                  mutate('declare', { independenceConfirmed: true })
                }
              >
                Zapisz deklarację niezależności
              </button>
              <label>
                Rola nagrania
                <select
                  value={role}
                  onChange={(event) =>
                    setRole(event.target.value as typeof role)
                  }
                >
                  <option value="TRAIN">TRAIN — trening</option>
                  <option value="VALIDATION">VALIDATION — walidacja</option>
                  <option value="REGRESSION">REGRESSION — regresja</option>
                </select>
              </label>
              <button
                type="button"
                disabled={
                  !manifest ||
                  !selected.membershipComplete ||
                  !selected.declared
                }
                onClick={() =>
                  mutate('assign_role', { familyId: manifest!.familyId, role })
                }
              >
                Przypisz rolę nagrania
              </button>
              <button
                type="button"
                disabled={
                  !manifest ||
                  !selected.membershipComplete ||
                  !selected.declared ||
                  !selected.role
                }
                onClick={() =>
                  mutate('freeze', {
                    familyId: manifest!.familyId,
                    baseVersionId: manifest!.versionId,
                  })
                }
              >
                Zapisz prowizoryczne rozstrzygnięcie
              </button>
              {selected.resolutionId ? (
                <p>
                  Zapisane rozstrzygnięcie jest prowizoryczne. Trening i trwała
                  ochrona wymagają odrębnej kwalifikacji kohorty.
                </p>
              ) : null}
              <button
                type="button"
                disabled={!selected.declared && !selected.role}
                onClick={() => mutate('retract')}
              >
                Wycofaj deklarację roboczą
              </button>
              <label>
                To samo nagranie w tej grze
                <select
                  value={otherGroupId}
                  onChange={(event) => setOtherGroupId(event.target.value)}
                >
                  <option value="">Wybierz drugą grupę</option>
                  {groups
                    .filter((group) => group.id !== selected.id)
                    .map((group) => (
                      <option key={group.id} value={group.id}>
                        {recordingGroupLabel(group, importJobs)}
                      </option>
                    ))}
                </select>
              </label>
              <button
                type="button"
                disabled={!otherGroupId}
                onClick={() => mutate('alias', { otherGroupId })}
              >
                Potwierdź alias nagrania
              </button>
            </fieldset>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
