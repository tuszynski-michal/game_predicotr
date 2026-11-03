'use client';

import { useCallback, useEffect, useState } from 'react';
import type {
  BrowserImageImportStart,
  BrowserImageImportStartResponse,
} from '@game-predictor/admin-api-client';
import type { ImageFolderImportClient } from './image-folder-import-actions';
import { apiErrorMessage } from '../catalog/catalog-api-error';

/** Recovery does not require a new report or the old staging directory to still exist. */
export function ReplacementStartRecovery({
  api,
  gameId,
  disabled,
  refreshKey,
  onRecovered,
}: {
  readonly api: ImageFolderImportClient;
  readonly gameId: string;
  readonly disabled: boolean;
  readonly refreshKey: string | null;
  readonly onRecovered: (
    result: BrowserImageImportStartResponse,
  ) => Promise<void>;
}) {
  const [pending, setPending] = useState<
    { key: string; uploadId: string; body: BrowserImageImportStart }[]
  >([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    try {
      const prefix = `replacement-start:${gameId}:`;
      const found = [];
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (!key?.startsWith(prefix)) continue;
        const body = JSON.parse(
          localStorage.getItem(key)!,
        ) as BrowserImageImportStart;
        if (
          body.gameId !== gameId ||
          body.replacementSelection?.request.gameId !== gameId ||
          !Array.isArray(body.replacementSelection.files) ||
          typeof body.manifestChecksumSha256 !== 'string' ||
          typeof body.preflightChecksumSha256 !== 'string'
        )
          throw new Error();
        found.push({ key, uploadId: key.slice(prefix.length), body });
      }
      setPending(found);
    } catch {
      setError(
        'Nie można odtworzyć zapisanych potwierdzeń importu. Sprawdź pamięć przeglądarki i odśwież stronę.',
      );
    }
  }, [gameId]);
  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) load();
    });
    return () => {
      active = false;
    };
  }, [load, refreshKey]);
  async function replay(item: (typeof pending)[number]) {
    setBusy(true);
    setError('');
    try {
      const result = await api.startReadyBrowserImageImport(
        item.uploadId,
        item.body,
      );
      if (!result.data) {
        if (
          result.response &&
          result.response.status >= 400 &&
          result.response.status < 500
        ) {
          localStorage.removeItem(item.key);
          load();
        }
        throw new Error(
          apiErrorMessage(result.error, 'Brak potwierdzenia importu.'),
        );
      }
      localStorage.removeItem(item.key);
      load();
      await onRecovered(result.data);
    } catch (cause) {
      setError(
        `${cause instanceof Error ? cause.message : 'Przerwano połączenie.'} Ponów zapisane potwierdzenie; przy odmowie serwera przygotuj świeży raport.`,
      );
    } finally {
      setBusy(false);
    }
  }
  if (!pending.length && !error) return null;
  return (
    <section aria-label="Odzyskanie potwierdzenia importu zamiennika">
      <h3>Oczekujące potwierdzenie importu</h3>
      <p>
        Połączenie mogło zostać przerwane po utworzeniu importu. Odtwórz jego
        zapisany wynik przed rozpoczęciem kolejnego.
      </p>
      {pending.map((item) => (
        <button
          type="button"
          key={item.key}
          disabled={disabled || busy}
          onClick={() => void replay(item)}
        >
          Odtwórz potwierdzenie: plansze{' '}
          {item.body
            .replacementSelection!.files.map(
              (file) => `${file.rangeStart}–${file.rangeEnd}`,
            )
            .join(', ')}
        </button>
      ))}
      {busy && <p role="status">Odczyt zapisanego wyniku importu…</p>}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
