'use client';

import type {
  AdminApiClient,
  SourceReplacementCandidateResponse,
  SourceReplacementBatchResponse,
  SourceReplacementCreateRequest,
  SourceReplacementManifestResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

export type SourceReplacementClient = Pick<
  AdminApiClient,
  | 'listSourceReplacementCandidates'
  | 'listSourceReplacementBatches'
  | 'getSourceReplacementBatch'
  | 'previewSourceReplacement'
  | 'planSourceReplacement'
  | 'exportSourceReplacementUrl'
>;

function isStoredCommand(
  value: unknown,
): value is SourceReplacementCreateRequest {
  if (!value || typeof value !== 'object') return false;
  const record = value as Record<string, unknown>;
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return (
    record.mode === 'replace_preserve_history' &&
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
        mode: 'replace_preserve_history',
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
              mode: 'replace_preserve_history' as const,
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
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Plan wymiany zdjęć">
      <h3>Wymiana zdjęć z zachowaniem historii</h3>
      <p>
        Wybierz całe zdjęcia. Zapis planu zachowuje plansze, modele i historię.
        Wycofanie zdjęć będzie osobnym krokiem.
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
            {manifest.status === 'planned'
              ? 'Plan zapisany. Zdjęcia nadal są aktywne.'
              : 'Podgląd przed zapisem planu.'}
          </p>
          {manifest.entries.map((entry) => (
            <article key={entry.sourceIds.join(',')}>
              <h4>Plansze {entry.sequenceNumbers.join(', ')}</h4>
              <p>
                Źródła: {entry.sourceIds.join(', ')}. Powody:{' '}
                {entry.reasons.length}. Plansze w historii:{' '}
                {entry.boards.length}.
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
