'use client';

import type {
  GridCohortHeader,
  GridCohortMember,
  GridCohortEligibility,
  GridCohortRecording,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
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
}: {
  apiBaseUrl: string;
  gameId: string;
  client?: GridCohortClient;
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
  const [family, setFamily] = useState(''),
    [base, setBase] = useState(''),
    [selection, setSelection] = useState('');
  const [selectorKind, setSelectorKind] = useState<'sources' | 'import'>(
    'sources',
  );
  const [mode, setMode] = useState<'grid-only' | 'screen+grid'>('grid-only');
  const [recordings, setRecordings] = useState(''),
    [completion, setCompletion] = useState('');

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
      setFamily('');
      setBase('');
      setSelection('');
      setRecordings('');
      setCompletion('');
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

  function prepare() {
    try {
      const roles = lines(recordings).map((line) => {
        const [groupId, role] = line.trim().split(/\s+/);
        if (
          !cohortUuid.test(groupId ?? '') ||
          !['TRAIN', 'VALIDATION', 'REGRESSION'].includes(role)
        )
          throw new Error(
            'Podaj identyfikator nagrania i rolę w każdym wierszu.',
          );
        return { groupId, role } as GridCohortRecording;
      });
      const selector =
        selectorKind === 'import'
          ? { importJobId: selection.trim() }
          : { sourceIds: selection.split(/[\s,;]+/).filter(Boolean) };
      void execute({
        kind: 'prepare',
        body: {
          idempotencyKey: crypto.randomUUID(),
          familyId: family.trim(),
          baseVersionId: base.trim(),
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
              {item.id} — {statuses[item.status]}
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
          Rodzina modelu{' '}
          <input value={family} onChange={(e) => setFamily(e.target.value)} />
        </label>
        <label>
          Wersja bazowa{' '}
          <input value={base} onChange={(e) => setBase(e.target.value)} />
        </label>
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
        <label>
          Wybór źródeł{' '}
          <select
            value={selectorKind}
            onChange={(e) =>
              setSelectorKind(e.target.value as typeof selectorKind)
            }
          >
            <option value="sources">Identyfikatory zdjęć (do 200)</option>
            <option value="import">Jeden import</option>
          </select>
          <textarea
            value={selection}
            onChange={(e) => setSelection(e.target.value)}
          />
        </label>
        <label>
          Nagrania: UUID i rola TRAIN, VALIDATION albo REGRESSION, po jednym na
          wiersz (do 200)
          <textarea
            value={recordings}
            onChange={(e) => setRecordings(e.target.value)}
          />
        </label>
        <button type="button" onClick={prepare}>
          Przygotuj metadane kohorty
        </button>
      </fieldset>
      {header && (
        <div>
          <h4>
            {statuses[header.status]} — {header.id}
          </h4>
          <p>
            Rewizja: {header.revision}. Baza: {header.baseVersionId}. Tryb:{' '}
            {header.mode}.
          </p>
          <p>
            Kwalifikacja metadanych:{' '}
            {eligibility?.qualification ?? 'Nie odczytano'}.{' '}
            {eligibility?.reasons.join(', ')}
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
                  {reason}: {count}
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
                {member.sourceId}: {member.role ?? 'Rola nieustalona'},{' '}
                {member.qualification}. Plansze: {member.boardEligibleCount}.
                Ekran:{' '}
                {member.screenEligible
                  ? 'kwalifikuje się'
                  : 'nie kwalifikuje się'}
                . Metadane: {member.metadataMissing ? 'brakujące' : 'obecne'}.{' '}
                {member.reasons.join(', ')}
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
    </section>
  );
}
