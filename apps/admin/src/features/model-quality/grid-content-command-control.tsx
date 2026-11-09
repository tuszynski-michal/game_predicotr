'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../catalog/catalog-api-error';
import {
  archiveContentCommand,
  clearContentCommand,
  contentCommandKey,
  readContentCommand,
  saveContentCommand,
  type ContentCommand,
  type ContentMode,
} from './grid-content-state';

/** Durable commands are kept only for exact replay, never used as editor drafts. */
export function useContentCommands(
  apiBaseUrl: string,
  gameId: string,
  mode: ContentMode,
  execute: (command: ContentCommand) => Promise<void>,
) {
  const key = contentCommandKey(apiBaseUrl, gameId, mode);
  const [pending, setPending] = useState<ContentCommand | null>(null);
  const [corrupt, setCorrupt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [initialized, setInitialized] = useState(false);
  const [error, setError] = useState('');
  const lock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    void Promise.resolve().then(() => {
      if (!mounted.current) return;
      try {
        setPending(readContentCommand(localStorage, key, gameId, mode));
      } catch (failure) {
        setCorrupt(true);
        setError(String(failure));
      }
      setInitialized(true);
    });
    return () => {
      mounted.current = false;
    };
  }, [key, gameId, mode]);
  async function send(command: ContentCommand, retry = false) {
    if (lock.current || !initialized || corrupt || (!retry && pending)) return;
    lock.current = true;
    setBusy(true);
    setError('');
    try {
      if (!retry) {
        saveContentCommand(localStorage, key, gameId, mode, command);
        setPending(command);
      } else if (
        JSON.stringify(readContentCommand(localStorage, key, gameId, mode)) !==
        JSON.stringify(command)
      )
        throw new Error(
          'Zapisane polecenie zmieniło się. Nie wysłano innej treści.',
        );
      await execute(command);
      clearContentCommand(localStorage, key, command.body.idempotencyKey);
      if (mounted.current) setPending(null);
    } catch (failure) {
      if (mounted.current)
        setError(
          failure instanceof Error
            ? failure.message
            : apiErrorMessage(
                failure,
                'Nie potwierdzono zapisu. Ponów dokładnie zapisane polecenie albo odśwież stan po konflikcie.',
              ),
        );
    } finally {
      lock.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const archive = useCallback(() => {
    if (lock.current) return;
    try {
      archiveContentCommand(localStorage, key);
      setPending(null);
      setCorrupt(false);
      setError(
        'Odłożono polecenie bez zmiany jego wyniku na serwerze. Odczytaj aktualny stan przed nowym zapisem.',
      );
    } catch {
      setError(
        'Nie udało się zachować polecenia. Nowy zapis pozostaje zablokowany.',
      );
    }
  }, [key]);
  return {
    pending,
    corrupt,
    busy,
    error,
    send,
    archive,
    blocked: !initialized || busy || corrupt || pending !== null,
  };
}

export function ContentCommandNotice({
  control,
}: {
  readonly control: ReturnType<typeof useContentCommands>;
}) {
  return (
    <>
      {control.error ? <p role="alert">{control.error}</p> : null}
      {control.pending || control.corrupt ? (
        <aside aria-label="Niepotwierdzone polecenie etykietowania">
          <p>
            Zapisane polecenie pozostaje do wyjaśnienia. Jego punktów i obwiedni
            nie odtwarzamy w edytorze.
          </p>
          <div className="gridContentActions">
            {control.pending ? (
              <button
                className="primaryButton"
                type="button"
                disabled={control.busy || control.corrupt}
                onClick={() => void control.send(control.pending!, true)}
              >
                Ponów dokładnie zapisane polecenie
              </button>
            ) : null}
            <button
              className="secondaryButton"
              type="button"
              disabled={control.busy}
              onClick={control.archive}
            >
              Zachowaj i odłóż polecenie
            </button>
          </div>
        </aside>
      ) : null}
      {control.busy ? (
        <p role="status" aria-busy="true">
          Zapisywanie etykietowania…
        </p>
      ) : null}
    </>
  );
}
