'use client';

import type {
  AdminApiClient,
  SourceReplacementCandidateResponse,
  SourceReplacementBatchResponse,
  SourceReplacementCreateRequest,
  SourceReplacementManifestResponse,
  SourcePurgeCommand,
  SourcePurgePreviewResponse,
  SourcePurgeResult,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { SourceRetirementActions } from './source-retirement-actions';
import { SourceReplacementWorking } from './source-replacement-working';

export type SourceReplacementClient = Pick<
  AdminApiClient,
  | 'listSourceReplacementCandidates'
  | 'listSourceReplacementBatches'
  | 'getSourceReplacementBatch'
  | 'previewSourceReplacement'
  | 'planSourceReplacement'
  | 'exportSourceReplacementUrl'
  | 'previewSourceRetirement'
  | 'executeSourceRetirement'
  | 'exportSourceReplacementRequest'
  | 'previewSourcePurge'
  | 'executeSourcePurge'
>;

function isStoredCommand(
  value: unknown,
): value is SourceReplacementCreateRequest {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return (
    (record.mode === 'replace_preserve_history' ||
      record.mode === 'replace_delete_source') &&
    record.expectedRevision === 0 &&
    typeof record.idempotencyKey === 'string' &&
    uuid.test(record.idempotencyKey) &&
    typeof record.previewToken === 'string' &&
    /^[0-9a-f]{64}$/.test(record.previewToken) &&
    Array.isArray(record.sourceIds) &&
    record.sourceIds.length > 0 &&
    record.sourceIds.length <= 50 &&
    record.sourceIds.every(
      (id: unknown) => typeof id === 'string' && uuid.test(id),
    )
  );
}

const dependencyNames: Record<string, string> = {
  grid_cohorts: 'zbiory geometrii',
  symbol_cohorts: 'zbiory symboli',
  active_jobs: 'aktywne zadania',
  model_activations: 'aktywacje modeli',
  releases: 'wydania',
  pending_geometry: 'oczekujące geometrie',
};

const messages: Record<string, string> = {
  SOURCE_REPLACEMENT_NO_CONFIRMED_REASON:
    'Brak aktualnego potwierdzenia nieczytelności.',
  SOURCE_REPLACEMENT_JUDGMENT_AMBIGUOUS:
    'Sprzeczne starsze oceny. Oceń pole ponownie.',
  SOURCE_REPLACEMENT_SLOT_PENDING_CONFLICT:
    'Inne zdjęcie ma oczekującą planszę w tym zakresie.',
  SOURCE_REPLACEMENT_SLOT_OWNER_CONFLICT:
    'Część zakresu należy do innego zdjęcia.',
  SOURCE_REPLACEMENT_RANGE_AMBIGUOUS: 'Zakres zdjęcia wymaga wyjaśnienia.',
  SOURCE_REPLACEMENT_SEQUENCE_UNKNOWN:
    'Nie wszystkie plansze mają ustalony numer.',
  SOURCE_REPLACEMENT_CROP_STALE:
    'Geometria pola zmieniła się. Odśwież przegląd.',
  SOURCE_REPLACEMENT_ACTIVE_JOB: 'Poczekaj na zakończenie zadania gry.',
  SOURCE_REPLACEMENT_ALREADY_RESERVED_OR_RETIRED:
    'Zdjęcie jest już objęte wymianą.',
  SOURCE_REPLACEMENT_PURGE_IMPORT_UNFINISHED:
    'Najpierw dokończ istniejący import: otwórz „Import plansz” dla tej gry, zakończ import i jego weryfikację. Potem wróć po świeży podgląd usunięcia.',
  SOURCE_REPLACEMENT_PURGE_MODEL_BUSY:
    'Zdjęcie jest używane przez trwające uczenie symboli. Poczekaj na zakończenie tej pracy i odśwież podgląd.',
  SOURCE_REPLACEMENT_PURGE_GRID_BUSY:
    'Zdjęcie jest używane przez trwającą pracę nad siatką. Poczekaj na jej zakończenie i odśwież podgląd.',
  SOURCE_REPLACEMENT_PURGE_REVIEW_BUSY:
    'Zdjęcie ma aktywne przypisanie do weryfikacji. Zakończ tę weryfikację przed usunięciem.',
  SOURCE_REPLACEMENT_PURGE_RECOVERY_REQUIRED:
    'Nie można dokończyć usuwania: plik zmienił się lub jest używany przez inne dane. Zachowaj zapisane polecenie; wyjaśnij konflikt pliku przed ponowieniem.',
  SOURCE_REPLACEMENT_LEGACY_RETIRED:
    'To zdjęcie wycofano wcześniej z zachowaniem historii. Ten zapis nie uprawnia do fizycznego usunięcia.',
};

export function SourceReplacementPanel({
  apiBaseUrl,
  gameId,
  client,
}: {
  apiBaseUrl: string;
  gameId: string;
  client?: SourceReplacementClient;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [client, apiBaseUrl],
  );
  const [items, setItems] = useState<SourceReplacementCandidateResponse[]>([]);
  const [batches, setBatches] = useState<SourceReplacementBatchResponse[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [workingEntry, setWorkingEntry] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [manifest, setManifest] =
    useState<SourceReplacementManifestResponse | null>(null);
  const [pending, setPending] = useState<SourceReplacementCreateRequest | null>(
    null,
  );
  const [storageReady, setStorageReady] = useState(false);
  const saving = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const storageKey = `source-replacement-plan:${gameId}`;

  useEffect(() => {
    let live = true;
    queueMicrotask(() => {
      if (!live) return;
      setBusy(true);
      setManifest(null);
      setSelected([]);
      setError('');
      setStorageReady(false);
      try {
        const raw = localStorage.getItem(storageKey);
        const stored: unknown = raw ? JSON.parse(raw) : null;
        if (stored !== null && !isStoredCommand(stored))
          throw new Error('Niepoprawny zapis');
        setPending(stored);
        setStorageReady(true);
      } catch {
        setError(
          'Nie można odczytać zapamiętanego polecenia. Zachowaj zapis i odśwież stronę.',
        );
      }
      Promise.all([
        api.listSourceReplacementCandidates(gameId, offset),
        api.listSourceReplacementBatches(gameId),
      ])
        .then(([page, plans]) => {
          if (!live) return;
          if (!page.data || !plans.data)
            throw new Error('Nie udało się pobrać zdjęć i planów.');
          setItems(page.data.items);
          setNextOffset(page.data.nextOffset);
          setBatches(plans.data);
        })
        .catch((reason: unknown) => {
          if (live) setError(String(reason));
        })
        .finally(() => {
          if (live) setBusy(false);
        });
    });
    return () => {
      live = false;
    };
  }, [api, gameId, offset, storageKey]);

  async function preview() {
    setBusy(true);
    setError('');
    setManifest(null);
    try {
      const result = await api.previewSourceReplacement(gameId, {
        mode: 'replace_delete_source',
        sourceIds: selected,
      });
      if (!result.data)
        throw new Error(
          result.error?.message ?? 'Nie udało się przygotować podglądu.',
        );
      setManifest(result.data);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (busy || saving.current || !storageReady) return;
    saving.current = true;
    setBusy(true);
    setError('');
    try {
      const command =
        pending ??
        (manifest
          ? {
              mode: manifest.mode,
              sourceIds: manifest.selectedSourceIds,
              idempotencyKey: crypto.randomUUID(),
              expectedRevision: 0,
              previewToken: manifest.previewToken,
            }
          : null);
      if (!command) return;
      // Persist the exact command before any request; reload/retry never creates a new key.
      localStorage.setItem(storageKey, JSON.stringify(command));
      setPending(command);
      const result = await api.planSourceReplacement(gameId, command);
      if (!result.data) {
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(storageKey);
          setPending(null);
          setManifest(null);
        }
        throw new Error(
          result.error?.message ??
            'Odpowiedź nie potwierdza zapisu. Ponów to samo polecenie.',
        );
      }
      setManifest(result.data);
      localStorage.removeItem(storageKey);
      setPending(null);
      const plans = await api.listSourceReplacementBatches(gameId);
      if (plans.data) setBatches(plans.data);
    } catch (reason) {
      setError(String(reason));
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  async function open(id: string) {
    setBusy(true);
    setError('');
    try {
      const result = await api.getSourceReplacementBatch(gameId, id);
      if (!result.data) throw new Error('Nie udało się odczytać planu.');
      setManifest(result.data);
      return result.data;
    } catch (reason) {
      setError(String(reason));
      return null;
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Plan wymiany zdjęć">
      <h3>Usuń stare zdjęcie i pozostaw luki do uzupełnienia</h3>
      <p>
        Wybierz całe zdjęcia. Najpierw zapiszesz mały manifest luk. Fizyczne
        usunięcie zdjęcia i zbędnych danych jego plansz wymaga osobnego,
        świeżego podglądu i potwierdzenia. Modele i dane innych zdjęć pozostaną.
      </p>
      {error && <p role="alert">{error}</p>}
      {busy && <p role="status">Trwa odczyt lub zapis…</p>}
      {pending && (
        <button
          style={{ minHeight: 44, minWidth: 44 }}
          type="button"
          disabled={busy || !storageReady}
          onClick={() => void save()}
        >
          Ponów zapis planu
        </button>
      )}
      {!items.length && !busy && (
        <p>Brak zdjęć z zapisanymi ocenami nieczytelności na tej stronie.</p>
      )}
      {items.map((item) => (
        <label key={item.id} style={{ display: 'block', minHeight: 44 }}>
          <input
            type="checkbox"
            disabled={busy || !storageReady || !!pending}
            checked={selected.includes(item.id)}
            onChange={() => {
              setManifest(null);
              setSelected((previous) =>
                previous.includes(item.id)
                  ? previous.filter((id) => id !== item.id)
                  : [...previous, item.id],
              );
            }}
          />
          {item.relativePath} — plansze {item.firstSequence}–{item.lastSequence}
        </label>
      ))}
      <button
        style={{ minHeight: 44, minWidth: 44 }}
        type="button"
        disabled={busy || !storageReady || !!pending || offset === 0}
        onClick={() => setOffset(Math.max(0, offset - 50))}
      >
        Poprzednie zdjęcia
      </button>
      <button
        style={{ minHeight: 44, minWidth: 44 }}
        type="button"
        disabled={busy || !storageReady || !!pending || nextOffset === null}
        onClick={() => nextOffset !== null && setOffset(nextOffset)}
      >
        Następne zdjęcia
      </button>
      <button
        style={{ minHeight: 44, minWidth: 44 }}
        type="button"
        disabled={busy || !storageReady || !!pending || !selected.length}
        onClick={() => void preview()}
      >
        Podgląd całych zdjęć
      </button>
      {manifest && (
        <div>
          <p>
            {manifest.id
              ? 'Zapisany plan. Stan każdego zdjęcia jest podany poniżej.'
              : 'Podgląd przed zapisem planu.'}
          </p>
          {manifest.entries.map((entry) => (
            <article key={entry.sourceIds.join(',')}>
              <h4>Plansze {entry.sequenceNumbers.join(', ')}</h4>
              <p>
                Źródła: {entry.sourceIds.join(', ')}. Powody:{' '}
                {entry.reasons.length}. Plansze w zakresie:{' '}
                {entry.sequenceNumbers.length}.
              </p>
              {entry.reasons.map((reason, index) => (
                <p key={index}>
                  Nieczytelne pole: plansza {String(reason.sequence_number)},
                  pozycja {Number(reason.cell_index) + 1}.
                </p>
              ))}
              <p>
                Zachowane zależności:{' '}
                {Object.entries(entry.dependencies)
                  .map(
                    ([name, rows]) =>
                      `${dependencyNames[name] ?? name}: ${rows.length}`,
                  )
                  .join(', ')}
                .
              </p>
              {entry.blockers.map((blocker) => (
                <p key={blocker} role="alert">
                  {messages[blocker] ?? blocker}
                </p>
              ))}
            </article>
          ))}
          {!manifest.id && (
            <button
              style={{ minHeight: 44, minWidth: 44 }}
              type="button"
              disabled={
                busy ||
                !storageReady ||
                !!pending ||
                manifest.entries.some((entry) => entry.blockers.length > 0)
              }
              onClick={() => void save()}
            >
              Zapisz plan wymiany
            </button>
          )}
          {manifest.id && manifest.mode === 'replace_preserve_history' && (
            <SourceRetirementActions
              key={`${gameId}:${manifest.id}`}
              gameId={gameId}
              manifest={manifest}
              api={api}
              apiBaseUrl={apiBaseUrl}
              refresh={async (id) => {
                await open(id);
              }}
            />
          )}
          {manifest.id && manifest.mode === 'replace_delete_source' && (
            <SourcePurgeActions
              key={`${gameId}:${manifest.id}`}
              gameId={gameId}
              manifest={manifest}
              api={api}
              refresh={open}
            />
          )}
          {manifest.id &&
            manifest.entries.map((entry) =>
              entry.id &&
              [
                'gap_open',
                'retired',
                'importing',
                'awaiting_review',
                'restored',
              ].includes(entry.phase ?? '') ? (
                <div key={entry.id}>
                  <button
                    type="button"
                    aria-expanded={workingEntry === entry.id}
                    onClick={() =>
                      setWorkingEntry((current) =>
                        current === entry.id ? null : entry.id!,
                      )
                    }
                  >
                    Nowe zdjęcie: plansze {entry.sequenceNumbers.join(', ')}
                  </button>
                  {workingEntry === entry.id && (
                    <SourceReplacementWorking
                      key={`${gameId}:${entry.id}`}
                      apiBaseUrl={apiBaseUrl}
                      gameId={gameId}
                      batchId={manifest.id!}
                      entryId={entry.id}
                    />
                  )}
                </div>
              ) : null,
            )}
          {manifest.id && (
            <p>
              <a
                href={api.exportSourceReplacementUrl(
                  gameId,
                  manifest.id,
                  'json',
                )}
              >
                Pobierz JSON
              </a>
              {' · '}
              <a
                href={api.exportSourceReplacementUrl(
                  gameId,
                  manifest.id,
                  'csv',
                )}
              >
                Pobierz CSV
              </a>
            </p>
          )}
        </div>
      )}
      {batches.length > 0 && (
        <div>
          <h4>Zapisane plany</h4>
          {batches.map((batch) => (
            <button
              style={{ minHeight: 44, minWidth: 44 }}
              key={batch.id}
              type="button"
              disabled={busy || !storageReady}
              onClick={() => void open(batch.id)}
            >
              {batch.id} — {batch.status}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function purgeError(
  error: { code?: string; message?: string } | undefined,
  fallback: string,
) {
  return error?.code && messages[error.code]
    ? messages[error.code]
    : (error?.message ?? fallback);
}

function isPurgeCommand(
  value: unknown,
  batchId: string,
): value is SourcePurgeCommand {
  if (!value || typeof value !== 'object') return false;
  const command = value as Record<string, unknown>;
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return (
    command.mode === 'replace_delete_source' &&
    command.action === 'purge' &&
    command.batchId === batchId &&
    command.confirmed === true &&
    Number.isInteger(command.expectedRevision) &&
    Number(command.expectedRevision) >= 1 &&
    typeof command.entryId === 'string' &&
    uuid.test(command.entryId) &&
    typeof command.idempotencyKey === 'string' &&
    uuid.test(command.idempotencyKey) &&
    typeof command.previewToken === 'string' &&
    /^[a-f0-9]{64}$/.test(command.previewToken)
  );
}

function SourcePurgeActions({
  gameId,
  manifest,
  api,
  refresh,
}: {
  readonly gameId: string;
  readonly manifest: SourceReplacementManifestResponse;
  readonly api: SourceReplacementClient;
  readonly refresh: (
    batchId: string,
  ) => Promise<SourceReplacementManifestResponse | null>;
}) {
  const [preview, setPreview] = useState<SourcePurgePreviewResponse | null>(
    null,
  );
  const [pending, setPending] = useState<SourcePurgeCommand | null>(null);
  const [receipt, setReceipt] = useState<SourcePurgeResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const writing = useRef(false);
  const key = `source-replacement-purge:${gameId}:${manifest.id}`;
  const buttonStyle = { minHeight: 44, minWidth: 44 };
  useEffect(() => {
    let live = true;
    queueMicrotask(() => {
      if (!live) return;
      try {
        const raw = localStorage.getItem(key);
        const command: unknown = raw ? JSON.parse(raw) : null;
        if (command !== null && !isPurgeCommand(command, manifest.id!))
          throw new Error();
        setPending(command);
        setReady(true);
      } catch {
        setError(
          'Nie można odczytać zapisanego polecenia usunięcia. Zachowaj zapis i odśwież stronę. Wynik zapisany na serwerze można odtworzyć poniżej.',
        );
      }
    });
    return () => {
      live = false;
    };
  }, [key, manifest.id]);

  async function prepare(entryId: string, revision: number) {
    if (busy || pending || !ready) return;
    setBusy(true);
    setError('');
    setPreview(null);
    setConfirmed(false);
    try {
      const result = await api.previewSourcePurge(gameId, {
        mode: 'replace_delete_source',
        action: 'purge',
        batchId: manifest.id!,
        entryId,
        expectedRevision: revision,
      });
      if (!result.data)
        throw new Error(
          purgeError(
            result.error,
            'Nie udało się przygotować świeżego podglądu usunięcia.',
          ),
        );
      setPreview(result.data);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Nie udało się odczytać podglądu.',
      );
    } finally {
      setBusy(false);
    }
  }

  async function execute(serverCommand?: SourcePurgeCommand) {
    if (busy || writing.current) return;
    const command =
      serverCommand ??
      pending ??
      (preview && confirmed
        ? {
            mode: 'replace_delete_source' as const,
            action: 'purge' as const,
            batchId: preview.batchId,
            entryId: preview.entryId,
            expectedRevision: preview.revision,
            idempotencyKey: crypto.randomUUID(),
            previewToken: preview.previewToken,
            confirmed: true as const,
          }
        : null);
    if (!command || (!serverCommand && !ready)) return;
    writing.current = true;
    setBusy(true);
    setError('');
    try {
      // A server receipt is already durable. A new command must be persisted before DELETE.
      if (!serverCommand) localStorage.setItem(key, JSON.stringify(command));
      setPending(command);
      const result = await api.executeSourcePurge(gameId, command);
      if (!result.data) {
        const current = await refresh(command.batchId);
        const committed = current?.entries.some(
          (entry) => entry.id === command.entryId && entry.purge,
        );
        if (
          current &&
          !committed &&
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(key);
          setPending(null);
          setPreview(null);
          setConfirmed(false);
        }
        throw new Error(
          purgeError(
            result.error,
            'Brak potwierdzenia usunięcia. Ponów dokładnie zapisane polecenie lub odśwież stan.',
          ),
        );
      }
      setReceipt(result.data);
      setPending(null);
      setPreview(null);
      setConfirmed(false);
      try {
        localStorage.removeItem(key);
      } catch {
        /* The committed server receipt remains the recovery authority. */
      }
      if (await refresh(command.batchId)) setReceipt(null);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : 'Połączenie przerwane. Ponów zapisane polecenie; nie twórz kolejnego.',
      );
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }

  async function download() {
    if (busy || !selected.length) return;
    setBusy(true);
    setError('');
    try {
      const result = await api.exportSourceReplacementRequest(
        gameId,
        manifest.id!,
        selected,
      );
      if (!result.data)
        throw new Error(
          result.error?.message ??
            'Nie można pobrać wybranych luk. Odśwież plan.',
        );
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(result.data, null, 2)], {
          type: 'application/json',
        }),
      );
      const link = document.createElement('a');
      link.href = url;
      link.download = `replacement-request-${manifest.id}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : 'Nie udało się pobrać luk.',
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Fizyczne usunięcie zaplanowanego zdjęcia">
      <p>
        Usuwanie jest nieodwracalne. Zachowane będą numery luk, mały dowód
        operacji, modele i dane innych zdjęć.
      </p>
      {busy && (
        <p role="status">Sprawdzanie lub wykonywanie zapisanej operacji…</p>
      )}
      {error && <p role="alert">{error}</p>}
      <button
        type="button"
        style={buttonStyle}
        disabled={busy}
        onClick={() => void refresh(manifest.id!)}
      >
        Odśwież stan usuwania
      </button>
      {pending && (
        <div>
          <p>
            Wynik polecenia nie został potwierdzony. Ponowienie użyje tego
            samego zapisu, także po przeładowaniu.
          </p>
          <button
            type="button"
            style={buttonStyle}
            disabled={busy}
            onClick={() => void execute(pending)}
          >
            Ponów zapisane polecenie usunięcia
          </button>
        </div>
      )}
      {manifest.entries.map((entry) => {
        const result = receipt?.entryId === entry.id ? receipt : null;
        const purge = result?.purge ?? entry.purge;
        const phase = result?.phase ?? entry.phase;
        return (
          <article key={entry.id}>
            <h4>Całe zdjęcie — plansze {entry.sequenceNumbers.join(', ')}</h4>
            {!purge && phase === 'planned' && (
              <>
                <p>Zdjęcie nadal aktywne. Zapisano tylko manifest.</p>
                <button
                  type="button"
                  style={buttonStyle}
                  disabled={busy || !ready || !!pending}
                  onClick={() => void prepare(entry.id!, entry.revision ?? 0)}
                >
                  Świeży podgląd usunięcia {entry.sequenceNumbers.join(', ')}
                </button>
              </>
            )}
            {purge && (
              <>
                <p role="status">
                  {purge.fileStatus === 'finalized'
                    ? 'Usuwanie plików zakończone.'
                    : purge.fileStatus === 'recovery_required'
                      ? 'Usuwanie nie zostało zakończone: plik zmienił się lub jest współdzielony. Wymagane wyjaśnienie konfliktu.'
                      : purge.fileStatus === 'recovery_pending'
                        ? 'Wymagane dokończenie usuwania po przerwanym potwierdzeniu.'
                        : 'Zmiany bazy zapisane; usuwanie plików jeszcze niezakończone.'}
                </p>
                <p>
                  Zaplanowano {purge.fileCount} plików,{' '}
                  {purge.bytesToDelete.toLocaleString('pl-PL')} B. Potwierdzone
                  usunięte bajty:{' '}
                  {(purge.deletedBytes ?? 0).toLocaleString('pl-PL')} B.
                  Współdzielone pliki zachowane: {purge.sharedFileCount}. Pliki
                  już nieobecne: {purge.missingFileCount}.
                </p>
                <p>
                  Usunięte rekordy operacyjne:{' '}
                  {Object.values(purge.deletedRecords ?? {}).reduce(
                    (sum, count) => sum + count,
                    0,
                  )}
                  . Zachowane metadane i dowody:{' '}
                  {Object.values(purge.retainedMetadata).reduce(
                    (sum, count) => sum + count,
                    0,
                  )}
                  .
                </p>
                {purge.fileStatus !== 'finalized' && (
                  <button
                    type="button"
                    style={buttonStyle}
                    disabled={busy}
                    onClick={() => void execute(purge.command)}
                  >
                    Dokończ zapisane usunięcie{' '}
                    {entry.sequenceNumbers.join(', ')}
                  </button>
                )}
              </>
            )}
            {entry.id && phase === 'gap_open' && (
              <label style={{ display: 'block', minHeight: 44 }}>
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={selected.includes(entry.id)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, entry.id!]
                        : current.filter((id) => id !== entry.id),
                    )
                  }
                />
                Luka zarezerwowana — eksportuj plansze{' '}
                {entry.sequenceNumbers.join(', ')}
              </label>
            )}
          </article>
        );
      })}
      {preview && !pending && (
        <fieldset disabled={busy}>
          <legend>Potwierdzenie fizycznego usunięcia</legend>
          <p>
            Zostanie usunięte całe zdjęcie i zbędne dane{' '}
            {preview.sequenceNumbers.length} plansz:{' '}
            {preview.sequenceNumbers.join(', ')}. Nie można cofnąć tego
            usunięcia.
          </p>
          <p>
            Pliki do usunięcia: {preview.fileCount}, zaplanowane{' '}
            {preview.bytesToDelete.toLocaleString('pl-PL')} B. Współdzielone
            pliki pozostaną: {preview.sharedFileCount}. Już nieobecne:{' '}
            {preview.missingFileCount}.
          </p>
          <p>
            Rekordy operacyjne do usunięcia:{' '}
            {Object.values(preview.recordCounts).reduce(
              (sum, count) => sum + count,
              0,
            )}
            . Zachowane metadane i dowody:{' '}
            {Object.values(preview.retainedMetadata).reduce(
              (sum, count) => sum + count,
              0,
            )}
            . Wagi modeli i ich aktywacje pozostaną. Rozmiar pliku bazy danych
            nie musi się zmniejszyć.
          </p>
          <label style={{ display: 'block', minHeight: 44 }}>
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Potwierdzam bezpowrotne usunięcie całego wskazanego zdjęcia i
            zbędnych danych jego plansz
          </label>
          <button
            type="button"
            style={buttonStyle}
            disabled={!confirmed || busy}
            onClick={() => void execute()}
          >
            Usuń całe zdjęcie i pozostaw luki
          </button>
        </fieldset>
      )}
      {manifest.entries.some((entry) => entry.phase === 'gap_open') && (
        <p>
          Pobierz wybrane luki. Następnie otwórz „Uzupełnij luki z manifestu
          wymiany zdjęć”, przygotuj zamiennik i przejdź do „Import plansz”. Nowe
          plansze wymagają zwykłego sprawdzenia i zatwierdzenia.
        </p>
      )}
      <button
        type="button"
        style={buttonStyle}
        disabled={busy || !selected.length}
        onClick={() => void download()}
      >
        Pobierz wybrane luki do uzupełnienia
      </button>
    </section>
  );
}
