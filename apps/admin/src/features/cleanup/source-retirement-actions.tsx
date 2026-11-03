'use client';

import type {
  AdminApiClient,
  SourceReplacementManifestResponse,
  SourceRetirementCommand,
  SourceRetirementPreviewResponse,
} from '@game-predictor/admin-api-client';
import { useEffect, useRef, useState } from 'react';

type Client = Pick<
  AdminApiClient,
  | 'previewSourceRetirement'
  | 'executeSourceRetirement'
  | 'exportSourceReplacementRequest'
>;
const buttonStyle = { minHeight: 44, minWidth: 44 };

function storedCommand(value: unknown): value is SourceRetirementCommand {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  const uuid =
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
  return (
    v.mode === 'replace_preserve_history' &&
    (v.action === 'retire' || v.action === 'cancel') &&
    v.confirmed === true &&
    Number.isInteger(v.expectedRevision) &&
    Number(v.expectedRevision) >= 1 &&
    ['batchId', 'entryId', 'idempotencyKey'].every(
      (key) => typeof v[key] === 'string' && uuid.test(v[key] as string),
    ) &&
    (v.action === 'cancel' ||
      (typeof v.previewToken === 'string' &&
        /^[0-9a-f]{64}$/.test(v.previewToken)))
  );
}

export function SourceRetirementActions({
  gameId,
  manifest,
  api,
  refresh,
  apiBaseUrl,
}: {
  gameId: string;
  manifest: SourceReplacementManifestResponse;
  api: Client;
  refresh: (batchId: string) => Promise<void>;
  apiBaseUrl: string;
}) {
  const [preview, setPreview] =
    useState<SourceRetirementPreviewResponse | null>(null);
  const [cancel, setCancel] = useState<{
    entryId: string;
    revision: number;
  } | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [pending, setPending] = useState<SourceRetirementCommand | null>(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [resolutionUrls, setResolutionUrls] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const writing = useRef(false);
  const mounted = useRef(false);
  const storageKey = `source-retirement-command:${gameId}`;
  useEffect(() => {
    mounted.current = true;
    let alive = true;
    queueMicrotask(() => {
      if (!alive) return;
      setPreview(null);
      setCancel(null);
      setConfirmed(false);
      setSelected([]);
      setReady(false);
      setError('');
      setResolutionUrls([]);
      try {
        const raw = localStorage.getItem(storageKey);
        const value: unknown = raw ? JSON.parse(raw) : null;
        if (value !== null && !storedCommand(value))
          throw new Error('Niepoprawny zapis');
        setPending(value);
        setReady(true);
      } catch {
        setError(
          'Nie można odczytać polecenia wycofania. Zachowaj zapis; nowa operacja jest zablokowana.',
        );
      }
    });
    return () => {
      alive = false;
      mounted.current = false;
    };
  }, [storageKey, manifest.id]);

  async function prepare(entryId: string, revision: number) {
    if (!manifest.id || busy || pending || !ready) return;
    setBusy(true);
    setError('');
    setResolutionUrls([]);
    setPreview(null);
    setCancel(null);
    setConfirmed(false);
    try {
      const result = await api.previewSourceRetirement(gameId, {
        mode: 'replace_preserve_history',
        action: 'retire',
        batchId: manifest.id,
        entryId,
        expectedRevision: revision,
      });
      if (!result.data) {
        const urls = result.error?.details?.resolutionUrls;
        setResolutionUrls(
          Array.isArray(urls)
            ? urls.filter(
                (url): url is string =>
                  typeof url === 'string' &&
                  url.startsWith('/api/v1/admin/image-review-items/'),
              )
            : [],
        );
        throw new Error(
          result.error?.message ?? 'Nie udało się odczytać świeżego podglądu.',
        );
      }
      setPreview(result.data);
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (
      writing.current ||
      busy ||
      !ready ||
      !manifest.id ||
      (!pending && !confirmed)
    )
      return;
    const command: SourceRetirementCommand | null =
      pending ??
      (preview
        ? {
            mode: 'replace_preserve_history',
            action: 'retire',
            batchId: preview.batchId,
            entryId: preview.entryId,
            expectedRevision: preview.revision,
            previewToken: preview.previewToken,
            idempotencyKey: crypto.randomUUID(),
            confirmed: true,
          }
        : cancel
          ? {
              mode: 'replace_preserve_history',
              action: 'cancel',
              batchId: manifest.id,
              entryId: cancel.entryId,
              expectedRevision: cancel.revision,
              idempotencyKey: crypto.randomUUID(),
              confirmed: true,
            }
          : null);
    if (!command) return;
    writing.current = true;
    setBusy(true);
    setError('');
    try {
      localStorage.setItem(storageKey, JSON.stringify(command));
      setPending(command);
      const result = await api.executeSourceRetirement(gameId, command);
      if (!result.data) {
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(storageKey);
          setPending(null);
          setPreview(null);
          setCancel(null);
          setConfirmed(false);
        }
        throw new Error(
          result.error?.message ??
            'Brak potwierdzenia wyniku. Ponów dokładnie zapisane polecenie.',
        );
      }
      localStorage.removeItem(storageKey);
      setPending(null);
      setPreview(null);
      setCancel(null);
      setConfirmed(false);
      if (mounted.current) await refresh(command.batchId);
    } catch (reason) {
      setError(String(reason));
    } finally {
      writing.current = false;
      setBusy(false);
    }
  }

  async function download() {
    if (!manifest.id || busy || !selected.length) return;
    setBusy(true);
    setError('');
    try {
      // The configured authenticated client is authoritative, never a URL from a local file.
      const result = await api.exportSourceReplacementRequest(
        gameId,
        manifest.id,
        selected,
      );
      if (!result.data)
        throw new Error(
          result.error?.message ?? 'Nie można wyeksportować wybranych luk.',
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
    } catch (reason) {
      setError(String(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-label="Wycofanie zaplanowanych zdjęć">
      <p>
        Postęp:{' '}
        {manifest.entries.filter((entry) => entry.phase !== 'planned').length} z{' '}
        {manifest.entries.length} wpisów rozstrzygniętych. Otwarta luka czeka na
        zamiennik.
      </p>
      {error && <p role="alert">{error}</p>}
      {error &&
        resolutionUrls.map((url) => (
          <p key={url}>
            <a
              href={`${apiBaseUrl.replace(/\/$/, '')}${url}`}
              target="_blank"
              rel="noreferrer"
            >
              Zobacz zapis kolidującej planszy
            </a>
          </p>
        ))}
      {busy && <p role="status">Trwa odczyt lub zapis zdjęcia…</p>}
      {pending && (
        <div>
          <p>
            Niepotwierdzone polecenie dla wpisu {pending.entryId}. Mogło zostać
            wykonane; ponowienie odtworzy jego wynik.
          </p>
          <button
            style={buttonStyle}
            disabled={busy || !ready}
            onClick={() => void execute()}
          >
            Ponów zapisane polecenie wycofania
          </button>
        </div>
      )}
      {manifest.entries.map((entry) => (
        <div key={entry.id}>
          <p>
            Plansze {entry.sequenceNumbers.join(', ')} —{' '}
            {entry.phase === 'planned'
              ? 'aktywne, zaplanowane do wymiany'
              : entry.phase === 'gap_open'
                ? 'wycofane; otwarta zarezerwowana luka'
                : entry.phase === 'cancelled'
                  ? 'plan anulowany; zdjęcie aktywne'
                  : entry.phase}
            .
          </p>
          {entry.retired?.some(
            (event) => event.action === 'source_replacement_retired',
          ) && (
            <p>
              Źródło wycofano z zachowaniem pełnej historii. Własne oczekujące
              plansze i geometrie zamknięto; przyczyna jest zapisana w trwałym
              zdarzeniu źródła.
            </p>
          )}
          {entry.id && entry.phase === 'planned' && (
            <>
              <button
                style={buttonStyle}
                disabled={busy || !ready || !!pending}
                onClick={() => void prepare(entry.id!, entry.revision ?? 0)}
              >
                Świeży podgląd wycofania {entry.sequenceNumbers.join(', ')}
              </button>
              <button
                style={buttonStyle}
                disabled={busy || !ready || !!pending}
                onClick={() => {
                  setPreview(null);
                  setConfirmed(false);
                  setCancel({
                    entryId: entry.id!,
                    revision: entry.revision ?? 0,
                  });
                }}
              >
                Anuluj plan zdjęcia
              </button>
            </>
          )}
          {entry.id && entry.phase === 'gap_open' && (
            <label style={{ display: 'block', minHeight: 44 }}>
              <input
                type="checkbox"
                disabled={busy}
                checked={selected.includes(entry.id)}
                onChange={() =>
                  setSelected((old) =>
                    old.includes(entry.id!)
                      ? old.filter((id) => id !== entry.id)
                      : [...old, entry.id!],
                  )
                }
              />
              Eksportuj lukę {entry.sequenceNumbers.join(', ')}
            </label>
          )}
        </div>
      ))}
      {(preview || cancel) && !pending && (
        <div role="group" aria-label="Potwierdzenie operacji">
          {preview ? (
            <p>
              Wycofanie całego zdjęcia:{' '}
              {preview.entry.sequenceNumbers.join(', ')}. Aliasów:{' '}
              {preview.entry.sourceIds.length}. SHA:{' '}
              {preview.entry.sourceSha256}. Historia i pliki pozostaną; plansze
              znikną z bieżącego użycia. Luka nie wygasa.
            </p>
          ) : (
            <p>
              Anulowanie dotyczy wyłącznie niewykonanego planu. Zdjęcie
              pozostanie aktywne.
            </p>
          )}
          <label style={{ display: 'block', minHeight: 44 }}>
            <input
              type="checkbox"
              checked={confirmed}
              disabled={busy}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            Potwierdzam wskazane zdjęcie i operację
          </label>
          <button
            style={buttonStyle}
            disabled={busy || !confirmed}
            onClick={() => void execute()}
          >
            {preview ? 'Wycofaj całe zdjęcie' : 'Potwierdź anulowanie planu'}
          </button>
        </div>
      )}
      <button
        style={buttonStyle}
        disabled={busy || !selected.length}
        onClick={() => void download()}
      >
        Pobierz wybrane luki do uzupełnienia
      </button>
    </section>
  );
}
