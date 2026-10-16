'use client';

import type {
  GameGridModelAssignmentResponse,
  GridCohortHeader,
  GridModelVersionResponse,
  GridCohortMember,
  GridCohortEligibility,
  GridCohortRecording,
  JobResponse,
  SourceRecordingGroupResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { usesNeuralGridConfiguration } from '@/features/games/game-catalog-state';
import {
  sendGridCohortCommand,
  type GridCohortClient,
} from './grid-cohort-actions';
import {
  cohortUuid,
  gridCohortSelectionKey,
  readGridCohortCommand,
  reserveGridCohortCommand,
  clearGridCohortCommand,
  discardGridCohortCommand,
  type GridCohortCommand,
} from './grid-cohort-command-storage';
import {
  RECORDING_PAGE_LIMIT,
  cohortLabel,
  readAllPages,
  reasonLabel,
  reasonList,
  versionLabel,
} from './grid-model-state';
import { RecordingImportPicker } from './recording-import-picker';
import {
  recordingGroupLabel,
  recordingImportLabel,
} from './recording-groups-state';

const qualificationLabels: Record<string, string> = {
  eligible: 'kwalifikuje się',
  blocked: 'zablokowana',
  unresolved: 'nierozstrzygnięta',
};
type Role = 'TRAIN' | 'VALIDATION' | 'REGRESSION';

const statuses: Record<GridCohortHeader['status'], string> = {
  preparing: 'Przygotowanie metadanych',
  preview_ready: 'Podgląd gotowy',
  materializing: 'Kopiowanie źródeł',
  ready_to_freeze: 'Gotowa do zamrożenia',
  frozen: 'Zamrożona',
  failed: 'Błąd',
  canceled: 'Anulowana',
};
const lines = (value: string) =>
  value
    .trim()
    .split(/[\r\n]+/)
    .filter(Boolean);
const message = (error: unknown) =>
  error instanceof Error ? error.message : 'Nie udało się odczytać danych.';
function failureDetails(error: unknown): string {
  if (!error || typeof error !== 'object') return '';
  const value = error as { code?: unknown; message?: unknown };
  return [value.code, value.message]
    .filter((part) => typeof part === 'string')
    .join(': ');
}

export function GridCohortPreview({
  apiBaseUrl,
  gameId,
  client,
  refreshKey = 0,
  onChanged,
}: {
  apiBaseUrl: string;
  gameId: string;
  client?: GridCohortClient;
  /** Changes when another step changed shared data (TASK-1000, P2-1). */
  refreshKey?: number;
  onChanged?: () => void;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [client, apiBaseUrl],
  );
  const epoch = useRef(0),
    request = useRef(0),
    listRequest = useRef(0),
    busyRef = useRef(false);
  const selectedRef = useRef<string | null>(null);
  const [items, setItems] = useState<GridCohortHeader[]>([]);
  const [nextList, setNextList] = useState<string | null>(null);
  const [header, setHeader] = useState<GridCohortHeader | null>(null);
  const [members, setMembers] = useState<GridCohortMember[]>([]);
  const [nextMember, setNextMember] = useState<number | null>(null);
  const [eligibility, setEligibility] = useState<GridCohortEligibility | null>(
    null,
  );
  const [pending, setPending] = useState<GridCohortCommand | null>(null);
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const [assignment, setAssignment] =
    useState<GameGridModelAssignmentResponse | null>(null);
  const [groups, setGroups] = useState<SourceRecordingGroupResponse[]>([]);
  const [versions, setVersions] = useState<GridModelVersionResponse[]>([]);
  // Empty: the base of the game's assignment; otherwise a named catalogue version.
  const [baseChoice, setBaseChoice] = useState('');
  // Empty: the default family of the chosen base; otherwise a named training family.
  const [familyChoice, setFamilyChoice] = useState('');
  // Assignments of the other V3 games: their training families (forks) of a base.
  const [peers, setPeers] = useState<
    { name: string; assignment: GameGridModelAssignmentResponse }[]
  >([]);
  const [jobs, setJobs] = useState<JobResponse[]>([]);
  const [chosen, setChosen] = useState<Record<string, Role>>({});
  const [importJobId, setImportJobId] = useState(''),
    [selection, setSelection] = useState('');
  const [selectorKind, setSelectorKind] = useState<'sources' | 'import'>(
    'import',
  );
  const [mode, setMode] = useState<'grid-only' | 'screen+grid'>('grid-only');
  const [completion, setCompletion] = useState('');

  async function list(cursor?: string, currentEpoch = epoch.current) {
    const token = ++listRequest.current;
    const result = await api
      .listGridTrainingCohorts(gameId, {
        cursor,
        limit: 20,
      })
      .catch((failure) => {
        if (currentEpoch === epoch.current && token === listRequest.current)
          throw failure;
        return null;
      });
    if (
      !result ||
      currentEpoch !== epoch.current ||
      token !== listRequest.current
    )
      return;
    if (!result.data) throw new Error('Nie udało się pobrać kohort.');
    if (result.data.items.some((row) => row.gameId !== gameId))
      throw new Error('Odrzucono odpowiedź innej gry.');
    setItems(result.data.items);
    setNextList(result.data.nextCursor);
  }

  async function load(id: string, cursor?: number) {
    const currentEpoch = epoch.current,
      token = ++request.current;
    selectedRef.current = id;
    setHeader(null);
    setMembers([]);
    setEligibility(null);
    setNextMember(null);
    const result = await Promise.all([
      api.getGridTrainingCohort(gameId, id),
      api.getGridTrainingCohortMembers(gameId, id, { cursor, limit: 200 }),
      api.getGridTrainingCohortEligibility(gameId, id),
    ]).catch((failure) => {
      if (
        currentEpoch === epoch.current &&
        token === request.current &&
        selectedRef.current === id
      )
        throw failure;
      return null;
    });
    if (
      !result ||
      currentEpoch !== epoch.current ||
      token !== request.current ||
      selectedRef.current !== id
    )
      return;
    if (!result[0].data || !result[1].data || !result[2].data)
      throw new Error('Nie udało się odczytać kohorty.');
    if (result[0].data.gameId !== gameId || result[0].data.id !== id)
      throw new Error('Odrzucono odpowiedź innej kohorty.');
    setHeader(result[0].data);
    setMembers(result[1].data.items);
    setNextMember(result[1].data.nextCursor);
    setEligibility(result[2].data);
    window.localStorage.setItem(gridCohortSelectionKey(apiBaseUrl, gameId), id);
  }

  // A missing read never aborts the other reads of the panel.
  function readContext(currentEpoch: number) {
    void Promise.resolve()
      .then(() =>
        // Each read starts in its own promise: one failing read never leaves another unhandled.
        Promise.all([
          Promise.resolve().then(() => api.getGameGridModelAssignment(gameId)),
          readAllPages((after) =>
            api.listSourceRecordingGroups(gameId, {
              limit: RECORDING_PAGE_LIMIT,
              after,
            }),
          ),
          Promise.resolve().then(() => api.listGridModelVersions()),
        ]),
      )
      .then(([assigned, recorded, catalogue]) => {
        if (currentEpoch !== epoch.current) return;
        if (assigned.data?.gameId === gameId) setAssignment(assigned.data);
        if (recorded) setGroups(recorded);
        if (catalogue.data) setVersions(catalogue.data);
      })
      .catch(() => {
        if (currentEpoch === epoch.current)
          setError('Nie udało się odczytać przypisania lub nagrań gry.');
      });
    void Promise.resolve()
      .then(() => api.listGames())
      .then(async (catalogue) => {
        const others = (catalogue.data ?? []).filter(
          (game) =>
            game.id !== gameId &&
            usesNeuralGridConfiguration(
              game.shapeGeometryConfiguration ?? null,
              game.code,
            ),
        );
        const read = await Promise.all(
          others.map((game) =>
            Promise.resolve()
              .then(() => api.getGameGridModelAssignment(game.id))
              .then((result) =>
                result.data?.gameId === game.id
                  ? { name: game.name, assignment: result.data }
                  : null,
              )
              .catch(() => null),
          ),
        );
        if (currentEpoch !== epoch.current) return;
        setPeers(read.filter((item) => item !== null));
      })
      .catch(() => undefined);
  }

  useEffect(() => {
    if (refreshKey === 0) return;
    readContext(epoch.current);
    // Another step (activation, a new recording) changed the context of the form.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    const currentEpoch = ++epoch.current;
    queueMicrotask(() => {
      if (currentEpoch !== epoch.current) return;
      busyRef.current = false;
      selectedRef.current = null;
      setItems([]);
      setHeader(null);
      setMembers([]);
      setEligibility(null);
      setNextList(null);
      setNextMember(null);
      setPending(null);
      setStorageBlocked(false);
      setBusy(false);
      setError('');
      setNotice('');
      setAssignment(null);
      setGroups([]);
      setVersions([]);
      setBaseChoice('');
      setFamilyChoice('');
      setPeers([]);
      setChosen({});
      setImportJobId('');
      setSelection('');
      setCompletion('');
      readContext(currentEpoch);
      try {
        setPending(
          readGridCohortCommand(window.localStorage, apiBaseUrl, gameId),
        );
      } catch (failure) {
        setError(message(failure));
        setStorageBlocked(true);
      }
      void list(undefined, currentEpoch).catch((failure) => {
        if (currentEpoch === epoch.current) setError(message(failure));
      });
      try {
        const id = window.localStorage.getItem(
          gridCohortSelectionKey(apiBaseUrl, gameId),
        );
        if (id && cohortUuid.test(id))
          void load(id).catch((failure) => {
            if (currentEpoch === epoch.current) setError(message(failure));
          });
      } catch (failure) {
        setError(message(failure));
        setStorageBlocked(true);
      }
    });
    return () => {
      epoch.current = currentEpoch + 1;
      request.current = 0;
    };
    // A changed scope discards only view state. Stored commands remain scoped to their game.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, apiBaseUrl, gameId]);

  async function execute(command: GridCohortCommand, retry = false) {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    setNotice('');
    const currentEpoch = epoch.current;
    try {
      if (!retry)
        reserveGridCohortCommand(
          window.localStorage,
          apiBaseUrl,
          gameId,
          command,
        );
      else if (
        JSON.stringify(
          readGridCohortCommand(window.localStorage, apiBaseUrl, gameId),
        ) !== JSON.stringify(command)
      )
        throw new Error('Zapisane polecenie uległo zmianie.');
      setPending(command);
      const result = await sendGridCohortCommand(api, gameId, command);
      if (!result.data)
        throw new Error(
          `${failureDetails(result.error)} Zapis niepotwierdzony. Ponów dokładnie zapisane polecenie albo odczytaj stan.`,
        );
      if (
        'cohort' in result.data &&
        (result.data.cohort.gameId !== gameId ||
          ('cohortId' in command && result.data.cohort.id !== command.cohortId))
      )
        throw new Error('Odrzucono odpowiedź innej kohorty.');
      if (result.data.receipt.idempotencyKey !== command.body.idempotencyKey)
        throw new Error('Odpowiedź nie potwierdza zapisanego polecenia.');
      clearGridCohortCommand(
        window.localStorage,
        apiBaseUrl,
        gameId,
        command.body.idempotencyKey,
      );
      if (currentEpoch !== epoch.current) return;
      setPending(null);
      setNotice(
        'Polecenie potwierdzone. To nie jest ocena jakości modelu ani zgoda na trening.',
      );
      onChanged?.();
      await list();
      if ('cohort' in result.data) await load(result.data.cohort.id);
      else if (selectedRef.current) await load(selectedRef.current);
    } catch (failure) {
      if (currentEpoch === epoch.current) setError(message(failure));
    } finally {
      if (currentEpoch === epoch.current) {
        busyRef.current = false;
        setBusy(false);
      }
    }
  }

  // The base defaults to the game's assignment; another named catalogue version can
  // be the common base of a shared candidate. The backend checks the lineage.
  const assignedId = assignment?.version?.manifest.versionId ?? null;
  const baseManifest = baseChoice
    ? versions.find((item) => item.manifest.versionId === baseChoice)?.manifest
    : assignment?.version?.manifest;
  const baseVersionId = baseManifest?.versionId ?? null;
  // A shared candidate needs one family and base in every cohort (D-560): besides the
  // base's own family, the training families (forks) of every game assigned to this base
  // are offered by name, so games with different forks can share one.
  const families = new Map<string, string>();
  if (baseManifest)
    families.set(
      baseManifest.familyId,
      `${baseManifest.familyLabel} (rodzina bazy)`,
    );
  for (const peer of [
    ...(assignment ? [{ name: 'tej gry', assignment }] : []),
    ...peers.map((item) => ({
      name: `gry ${item.name}`,
      assignment: item.assignment,
    })),
  ])
    if (
      baseVersionId &&
      peer.assignment.version?.manifest.versionId === baseVersionId &&
      peer.assignment.trainingFamilyId &&
      !families.has(peer.assignment.trainingFamilyId)
    )
      families.set(
        peer.assignment.trainingFamilyId,
        `${peer.assignment.trainingFamilyLabel ?? 'Rodzina treningowa'} (rodzina treningowa ${peer.name})`,
      );
  const defaultFamily =
    baseVersionId && baseVersionId === assignedId
      ? (assignment?.trainingFamilyId ?? baseManifest?.familyId ?? null)
      : (baseManifest?.familyId ?? null);
  const familyId =
    familyChoice && families.has(familyChoice) ? familyChoice : defaultFamily;
  const bases = versions.filter(
    (item) =>
      item.available &&
      item.manifest.versionId !== assignedId &&
      (item.published || item.manifest.admission !== 'not_evaluated'),
  );
  // The photos of the chosen recordings: one import per recording, plus an optional
  // import picked by name. Recordings of different roles usually differ in import.
  const recordingImports = groups
    .filter((group) => group.id in chosen && group.importJobId)
    .map((group) => String(group.importJobId));
  const imports = [
    ...new Set(
      [...recordingImports, importJobId].filter((id) => cohortUuid.test(id)),
    ),
  ];
  const withoutImport = groups.filter(
    (group) => group.id in chosen && !group.importJobId,
  );

  function prepare() {
    try {
      if (!familyId || !baseVersionId)
        throw new Error(
          'Gra nie ma przypisanej wersji geometrii; najpierw ją przypisz albo wybierz bazę.',
        );
      const roles: GridCohortRecording[] = Object.entries(chosen).map(
        ([groupId, role]) => ({ groupId, role }),
      );
      if (!roles.length) throw new Error('Wybierz nagrania i ich role.');
      if (selectorKind === 'import' && !imports.length)
        throw new Error('Wybierz nagrania z importów albo import zdjęć.');
      const selector =
        selectorKind !== 'import'
          ? { sourceIds: selection.split(/[\s,;]+/).filter(Boolean) }
          : imports.length === 1
            ? { importJobId: imports[0] }
            : { importJobIds: imports };
      void execute({
        kind: 'prepare',
        body: {
          idempotencyKey: crypto.randomUUID(),
          familyId,
          baseVersionId,
          mode,
          selector,
          recordings: roles,
        },
      });
    } catch (failure) {
      setError(message(failure));
    }
  }

  function complete() {
    const sources = lines(completion).map((line) => {
      const [
        sourceId,
        expectedSourceSha256,
        expectedSourceGeometryRevisionId,
        expectedGeometrySha256,
      ] = line.trim().split(/\s+/);
      return {
        sourceId,
        expectedSourceSha256,
        expectedSourceGeometryRevisionId,
        expectedGeometrySha256,
      };
    });
    void execute({
      kind: 'complete',
      body: { idempotencyKey: crypto.randomUUID(), sources },
    });
  }

  function page(kind: 'prepare-page' | 'materialize-page') {
    if (!header) return;
    const cursor =
      kind === 'prepare-page'
        ? header.nextCaptureCursor
        : header.nextMaterializationCursor;
    if (cursor === null) return;
    void execute({
      kind,
      cohortId: header.id,
      body: {
        idempotencyKey: crypto.randomUUID(),
        expectedRevision: header.revision,
        cursor,
      },
    });
  }
  const locked = busy || pending !== null || storageBlocked;
  return (
    <section className="modelQualityCard" aria-label="Kohorty geometrii V3">
      <h3>Dane do doszkalania geometrii V3</h3>
      <p>
        Aktualne etykiety człowieka. Plansze i ekrany kwalifikujemy osobno.
        Automatyczna akceptacja nie tworzy etykiety.
      </p>
      <p>
        TRAIN grid-only: 30 plansz z 10 zdjęć. VALIDATION i REGRESSION: po 15
        plansz i 5 pełnych zdjęć z osobnych nagrań. Przy 9 planszach to po 45
        etykiet. TRAIN screen+grid: 10 pełnych zdjęć. Wagi korekt i sprawdzeń
        bez zmian: 4:1.
      </p>
      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}
      {(pending || storageBlocked) && (
        <div>
          <p>
            Zapisane polecenie oczekuje na rozstrzygnięcie. Odświeżenie
            odczytuje stan bez ponawiania zapisu.
          </p>
          <button
            type="button"
            disabled={busy || !pending || storageBlocked}
            onClick={() => pending && void execute(pending, true)}
          >
            Ponów zapisane polecenie
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              try {
                discardGridCohortCommand(
                  window.localStorage,
                  apiBaseUrl,
                  gameId,
                );
                setPending(null);
                setStorageBlocked(false);
                setError('');
              } catch (failure) {
                setError(message(failure));
              }
            }}
          >
            Porzuć lokalne polecenie z zachowaniem kopii
          </button>
        </div>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => void list().catch((f) => setError(message(f)))}
      >
        Odśwież listę kohort
      </button>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void load(item.id).catch((f) => setError(message(f)))
              }
            >
              {cohortLabel(item)}
            </button>
          </li>
        ))}
      </ul>
      {nextList && (
        <button
          type="button"
          disabled={busy}
          onClick={() => void list(nextList).catch((f) => setError(message(f)))}
        >
          Następna strona kohort
        </button>
      )}
      <fieldset disabled={locked}>
        <legend>Przygotuj kohortę</legend>
        <label>
          Baza treningowa{' '}
          <select
            value={baseChoice}
            onChange={(e) => {
              setBaseChoice(e.target.value);
              setFamilyChoice('');
            }}
          >
            <option value="">
              {assignment?.version
                ? `Z przypisania gry: ${assignment.trainingFamilyLabel ?? assignment.version.manifest.familyLabel} · ${versionLabel(assignment.version.manifest)}`
                : 'Brak przypisanej wersji — wybierz bazę'}
            </option>
            {bases.map((item) => (
              <option
                key={item.manifest.versionId}
                value={item.manifest.versionId}
              >
                {versionLabel(item.manifest)}
              </option>
            ))}
          </select>
        </label>
        {families.size > 1 ? (
          <label>
            Rodzina treningowa{' '}
            <select
              value={familyId ?? ''}
              onChange={(e) => setFamilyChoice(e.target.value)}
            >
              {[...families].map(([id, label]) => (
                <option key={id} value={id}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <p>
          Wybór bazy i rodziny nie zmienia przypisania gry. Kohorty wspólnego
          kandydata muszą mieć tę samą rodzinę i bazę.
        </p>
        <label>
          Tryb{' '}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as typeof mode)}
          >
            <option value="grid-only">Tylko siatki</option>
            <option value="screen+grid">Ekran i siatki</option>
          </select>
        </label>
        <RecordingImportPicker
          api={api}
          gameId={gameId}
          value={importJobId}
          disabled={locked || selectorKind !== 'import'}
          onChange={setImportJobId}
          onLoaded={setJobs}
        />
        <fieldset aria-label="Nagrania kohorty" disabled={locked}>
          <legend>Nagrania i role</legend>
          {groups.length === 0 ? (
            <p>Gra nie ma jeszcze zarejestrowanych nagrań.</p>
          ) : null}
          {groups.map((group) => (
            <div key={group.id}>
              <label>
                <input
                  type="checkbox"
                  checked={group.id in chosen}
                  onChange={(e) =>
                    setChosen((current) => {
                      const next = { ...current };
                      if (e.target.checked)
                        next[group.id] = (group.role ?? 'TRAIN') as Role;
                      else delete next[group.id];
                      return next;
                    })
                  }
                />{' '}
                {recordingGroupLabel(group, jobs)}
              </label>
              {group.id in chosen ? (
                <select
                  aria-label={`Rola: ${recordingGroupLabel(group, jobs)}`}
                  value={chosen[group.id]}
                  onChange={(e) =>
                    setChosen((current) => ({
                      ...current,
                      [group.id]: e.target.value as Role,
                    }))
                  }
                >
                  <option value="TRAIN">TRAIN</option>
                  <option value="VALIDATION">VALIDATION</option>
                  <option value="REGRESSION">REGRESSION</option>
                </select>
              ) : null}
            </div>
          ))}
        </fieldset>
        <p>
          Importy w kohorcie:{' '}
          {imports.length
            ? imports
                .map((id) => {
                  const job = jobs.find((item) => item.id === id);
                  return job ? recordingImportLabel(job) : 'import spoza listy';
                })
                .join('; ')
            : 'brak — wybierz nagrania albo import'}
        </p>
        {withoutImport.length ? (
          <p>
            Nagrania bez importu ({withoutImport.length}): dodaj import z ich
            zdjęciami albo użyj dokładnego wyboru zdjęć.
          </p>
        ) : null}
        <details>
          <summary>Zaawansowane: dokładny wybór zdjęć</summary>
          <label>
            <input
              type="checkbox"
              checked={selectorKind === 'sources'}
              onChange={(e) =>
                setSelectorKind(e.target.checked ? 'sources' : 'import')
              }
            />{' '}
            Zamiast importu użyj identyfikatorów zdjęć (do 200)
          </label>
          <textarea
            aria-label="Identyfikatory zdjęć"
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
          />
        </details>
        <button type="button" onClick={prepare}>
          Przygotuj metadane kohorty
        </button>
      </fieldset>
      {header && (
        <div>
          <h4>
            {statuses[header.status]} — {cohortLabel(header)}
          </h4>
          <p>Rewizja: {header.revision}.</p>
          <p>
            Kwalifikacja metadanych:{' '}
            {eligibility
              ? (qualificationLabels[eligibility.qualification] ??
                eligibility.qualification)
              : 'Nie odczytano'}
            . {reasonList(eligibility?.reasons)}
          </p>
          <p>
            Cofnięcie ludzkiego zatwierdzenia:{' '}
            {eligibility?.humanLabelWithdrawn == null
              ? 'nie ustalono'
              : eligibility.humanLabelWithdrawn
                ? 'potwierdzone'
                : 'nie stwierdzono'}
            . Aktualne powiązanie źródeł:{' '}
            {eligibility?.liveSourceLinked == null
              ? 'nie ustalono'
              : eligibility.liveSourceLinked
                ? 'potwierdzone'
                : 'odłączone'}
            . Aktualna dostępność kopii: nie sprawdzono.
          </p>
          <p>
            Kwalifikacja metadanych nie jest pozwoleniem na uruchomienie
            treningu.
          </p>
          <table>
            <caption>
              Metadane: wymagane / kwalifikujące się / brakujące. Kopie są
              sprawdzane osobno.
            </caption>
            <thead>
              <tr>
                <th>Rola</th>
                <th>Plansze</th>
                <th>Zdjęcia</th>
                <th>Pełne zdjęcia / screen</th>
                <th>Sprawdzone kopie: plansze / zdjęcia / pełne zdjęcia</th>
                <th>Nagranie</th>
              </tr>
            </thead>
            <tbody>
              {header.summary.roles.map((role) => (
                <tr key={role.role}>
                  <th>{role.role}</th>
                  <td>
                    {role.requiredBoards} / {role.eligibleBoards} /{' '}
                    {role.missingBoards}
                  </td>
                  <td>
                    {role.requiredPhotos} / {role.eligiblePhotos} /{' '}
                    {role.missingPhotos}
                  </td>
                  <td>
                    {role.requiredFullPhotos} / {role.eligibleFullPhotos} /{' '}
                    {role.missingFullPhotos}
                  </td>
                  <td>
                    {role.materializedBoards} / {role.materializedPhotos} /{' '}
                    {role.materializedFullPhotos}
                  </td>
                  <td>
                    {role.recordingRequired
                      ? 'Wymagane niezależne nagranie'
                      : 'Według zapisanej polityki'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul>
            {Object.entries(header.summary.reasonCounts).map(
              ([reason, count]) => (
                <li key={reason}>
                  {reasonLabel(reason)}: {count}
                </li>
              ),
            )}
          </ul>
          <p>
            Podgląd SHA: {header.previewSha256 ?? 'Jeszcze niedostępny'}.
            Manifest SHA: {header.manifestSha256 ?? 'Jeszcze niedostępny'}.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() =>
              void load(header.id).catch((f) => setError(message(f)))
            }
          >
            Odczytaj aktualny stan kohorty
          </button>
          <button
            type="button"
            disabled={
              locked ||
              header.status !== 'preparing' ||
              header.nextCaptureCursor === null
            }
            onClick={() => page('prepare-page')}
          >
            Przygotuj następną stronę metadanych (do 200)
          </button>
          <button
            type="button"
            disabled={
              locked ||
              !['preview_ready', 'materializing'].includes(header.status) ||
              header.nextMaterializationCursor === null
            }
            onClick={() => page('materialize-page')}
          >
            Skopiuj następną stronę źródeł (do 5)
          </button>
          <button
            type="button"
            disabled={
              locked ||
              header.status !== 'ready_to_freeze' ||
              !header.previewSha256 ||
              !header.manifestSha256
            }
            onClick={() => {
              if (header.previewSha256 && header.manifestSha256)
                void execute({
                  kind: 'freeze',
                  cohortId: header.id,
                  body: {
                    idempotencyKey: crypto.randomUUID(),
                    expectedRevision: header.revision,
                    expectedPreviewSha256: header.previewSha256,
                    expectedManifestSha256: header.manifestSha256,
                  },
                });
            }}
          >
            Zamroź sprawdzoną kohortę
          </button>
          <button
            type="button"
            disabled={locked || ['frozen', 'canceled'].includes(header.status)}
            onClick={() =>
              void execute({
                kind: 'cancel',
                cohortId: header.id,
                body: {
                  idempotencyKey: crypto.randomUUID(),
                  expectedRevision: header.revision,
                },
              })
            }
          >
            Anuluj przygotowanie kohorty
          </button>
          <ul>
            {members.map((member) => (
              <li key={member.sourceId}>
                Zdjęcie {member.sourceId.slice(0, 8)}:{' '}
                {member.role ?? 'Rola nieustalona'},{' '}
                {qualificationLabels[member.qualification] ??
                  member.qualification}
                . Plansze: {member.boardEligibleCount}. Ekran:{' '}
                {member.screenEligible
                  ? 'kwalifikuje się'
                  : 'nie kwalifikuje się'}
                . Metadane: {member.metadataMissing ? 'brakujące' : 'obecne'}.{' '}
                {reasonList(member.reasons)}
              </li>
            ))}
          </ul>
          {nextMember !== null && (
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void load(header.id, nextMember).catch((f) =>
                  setError(message(f)),
                )
              }
            >
              Następna strona członków
            </button>
          )}
        </div>
      )}
      <details>
        <summary>Zaawansowane: uzupełnienie tożsamości starszych zdjęć</summary>
        <fieldset disabled={locked}>
          <legend>Jawnie uzupełnij tożsamość wybranych zdjęć</legend>
          <p>
            1–5 zdjęć. Każdy wiersz: UUID zdjęcia, oczekiwany SHA zdjęcia, UUID
            rewizji źródła, SHA geometrii. Odczyt ekranu nie uruchamia tej
            operacji.
          </p>
          <label>
            Wybrane źródła i oczekiwane wartości
            <textarea
              value={completion}
              onChange={(e) => setCompletion(e.target.value)}
            />
          </label>
          <button type="button" onClick={complete}>
            Uzupełnij wybrane tożsamości
          </button>
        </fieldset>
      </details>
    </section>
  );
}
