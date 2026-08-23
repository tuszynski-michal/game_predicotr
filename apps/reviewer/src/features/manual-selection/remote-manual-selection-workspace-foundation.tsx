'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  DirectoryHandleRemoteSourceAdapter,
  RemoteSourceAdapterError,
  WebkitDirectoryRemoteSourceAdapter,
  createRemoteSourceItemRecords,
  detectRemoteSourceMode,
  validateRemoteSourceRelink,
  type ReadableDirectoryHandle,
  type RemoteSourceIndexResult,
} from './remote-source-adapter';
import {
  RemoteSelectionIndexedDbStore,
  RemoteSelectionStoreError,
  requestBestEffortPersistentStorage,
  type RemoteSelectionLocalBatchRecord,
  type RemoteSelectionLocalSessionRecord,
  type RemoteSelectionRestoreSnapshot,
  type RemoteSourcePermissionState,
} from './remote-selection-store';
import {
  RemoteSelectionTabCoordinator,
  type RemoteSelectionTabState,
} from './remote-tab-coordinator';

type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: (options: {
    readonly id: string;
    readonly mode: 'read';
  }) => Promise<FileSystemDirectoryHandle>;
};

const EMPTY_TAB_STATE: RemoteSelectionTabState = {
  mode: 'read_only',
  ownerClientInstanceId: null,
  supported: typeof BroadcastChannel !== 'undefined',
};

export function RemoteManualSelectionWorkspaceFoundation({
  clientInstanceId,
  serverWriter,
  sessionId,
}: {
  readonly clientInstanceId: string;
  readonly serverWriter: boolean;
  readonly sessionId: string;
}) {
  const store = useMemo(() => new RemoteSelectionIndexedDbStore(), []);
  const [snapshot, setSnapshot] =
    useState<RemoteSelectionRestoreSnapshot | null>(null);
  const [tabState, setTabState] = useState(EMPTY_TAB_STATE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [sourceMode, setSourceMode] =
    useState<ReturnType<typeof detectRemoteSourceMode>>('unsupported');
  const fallbackInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const restored = await store.restore(sessionId);
    if (restored.session?.sourceHandle !== null && restored.session !== null) {
      const permission = await new DirectoryHandleRemoteSourceAdapter(
        restored.session.sourceHandle as ReadableDirectoryHandle,
      ).permissionState();
      if (permission !== restored.session.permissionState) {
        const session = { ...restored.session, permissionState: permission };
        await store.saveSession(session);
        setSnapshot({ ...restored, session });
        return;
      }
    }
    setSnapshot(restored);
  }, [sessionId, store]);

  useEffect(() => {
    let active = true;
    const timeout = window.setTimeout(() => {
      void refresh().catch((cause) => {
        if (active) setError(errorMessage(cause));
      });
    }, 0);
    return () => {
      active = false;
      window.clearTimeout(timeout);
    };
  }, [refresh]);

  useEffect(() => {
    const coordinator = new RemoteSelectionTabCoordinator(
      sessionId,
      clientInstanceId,
    );
    const unsubscribe = coordinator.subscribe(setTabState);
    void coordinator.start().then(setTabState);
    return () => {
      unsubscribe();
      coordinator.close();
    };
  }, [clientInstanceId, sessionId]);

  useEffect(() => {
    const timeout = window.setTimeout(
      () => setSourceMode(detectRemoteSourceMode(window)),
      0,
    );
    const input = fallbackInput.current;
    if (input !== null) {
      input.webkitdirectory = true;
      input.setAttribute('webkitdirectory', '');
    }
    return () => window.clearTimeout(timeout);
  }, []);

  const localWriter = tabState.mode === 'writer';
  const canWrite = serverWriter && localWriter;
  const session = snapshot?.session ?? null;
  const batch = snapshot?.batch ?? null;
  const permission = session?.permissionState ?? 'unsupported';

  async function chooseDirectory() {
    if (!canWrite || busy) return;
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
    if (picker === undefined) {
      fallbackInput.current?.click();
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Indeksowanie metadanych JPEG…');
    try {
      const handle = (await picker({
        id: 'game-predictor-remote-selection-source',
        mode: 'read',
      })) as ReadableDirectoryHandle;
      const adapter = new DirectoryHandleRemoteSourceAdapter(handle);
      const permissionState = await adapter.requestPermission();
      if (permissionState !== 'granted' && permissionState !== 'unsupported') {
        throw new RemoteSourceAdapterError(
          'REMOTE_SELECTION_SOURCE_PERMISSION_REQUIRED',
          'Nie przyznano prawa odczytu folderu źródłowego.',
        );
      }
      await persistIndexedSource(await adapter.index(), permissionState);
    } catch (cause) {
      if (!isPickerCancelled(cause)) setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function chooseFallback(files: FileList | null) {
    if (!canWrite || files === null || files.length === 0) return;
    setBusy(true);
    setError('');
    setNotice('Indeksowanie metadanych JPEG z wyboru sesyjnego…');
    try {
      await persistIndexedSource(
        await new WebkitDirectoryRemoteSourceAdapter([...files]).index(),
        'unsupported',
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      if (fallbackInput.current !== null) fallbackInput.current.value = '';
      setBusy(false);
    }
  }

  async function persistIndexedSource(
    indexed: RemoteSourceIndexResult,
    permissionState: RemoteSourcePermissionState,
  ) {
    const persistence = await requestBestEffortPersistentStorage();
    if (batch !== null) {
      const expected = await store.loadSourceManifest(sessionId, batch.batchId);
      validateRemoteSourceRelink(expected, indexed.manifest);
      const current = snapshot?.session;
      if (current === null || current === undefined) {
        throw new RemoteSelectionStoreError(
          'REMOTE_SELECTION_SESSION_NOT_FOUND',
          'Nie znaleziono lokalnego stanu sesji.',
        );
      }
      await store.saveSession({
        ...current,
        permissionState,
        persistenceGranted: persistence.granted,
        sourceDirectoryName: indexed.sourceDirectoryName,
        sourceHandle: indexed.sourceHandle,
        updatedAt: new Date().toISOString(),
      });
      await refresh();
      setNotice('Folder został bezpiecznie powiązany ponownie.');
      return;
    }

    const now = new Date().toISOString();
    const batchId = crypto.randomUUID();
    const localSession: RemoteSelectionLocalSessionRecord = {
      schemaVersion: 1,
      activeBatchId: batchId,
      permissionState,
      persistenceGranted: persistence.granted,
      sessionId,
      sourceDirectoryName: indexed.sourceDirectoryName,
      sourceHandle: indexed.sourceHandle,
      sourceKind: indexed.manifest.sourceKind,
      sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
      updatedAt: now,
    };
    const localBatch: RemoteSelectionLocalBatchRecord = {
      schemaVersion: 1,
      batchId,
      cursorIndex: 0,
      direction: 'ascending',
      fileCount: indexed.manifest.fileCount,
      firstLayout: 1,
      sessionId,
      sourceDirectoryName: indexed.sourceDirectoryName,
      sourceKind: indexed.manifest.sourceKind,
      sourceManifestChecksumSha256: indexed.manifest.manifestChecksumSha256,
      totalBytes: indexed.manifest.totalBytes,
      updatedAt: now,
    };
    await store.saveIndexedSource({
      batch: localBatch,
      session: localSession,
      sourceItems: createRemoteSourceItemRecords(
        sessionId,
        batchId,
        indexed.manifest,
      ),
    });
    await refresh();
    setNotice(
      `Zaindeksowano ${indexed.manifest.fileCount.toLocaleString('pl-PL')} JPEG-ów bez kopiowania ich danych.`,
    );
  }

  async function requestStoredPermission() {
    if (!canWrite || session === null || session.sourceHandle === null) return;
    setBusy(true);
    setError('');
    try {
      const permissionState = await new DirectoryHandleRemoteSourceAdapter(
        session.sourceHandle as ReadableDirectoryHandle,
      ).requestPermission();
      await store.saveSession({
        ...session,
        permissionState,
        updatedAt: new Date().toISOString(),
      });
      await refresh();
      if (permissionState !== 'granted' && permissionState !== 'unsupported') {
        setError(
          'Folder nadal wymaga ponownego wskazania lub zgody na odczyt.',
        );
      }
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="remoteSelectionWorkspaceFoundation" aria-live="polite">
      <h2>Źródło zdjęć</h2>
      {!serverWriter ? (
        <p>Host przyznał tej karcie wyłącznie odczyt.</p>
      ) : !localWriter ? (
        <p>
          Inna karta tej przeglądarki przygotowuje źródło. Ta karta jest tylko
          do odczytu.
        </p>
      ) : null}
      {!tabState.supported ? (
        <p>
          Ta przeglądarka nie obsługuje koordynacji kart. Nie otwieraj tej sesji
          równocześnie w drugiej karcie.
        </p>
      ) : null}

      {batch === null ? (
        <>
          <p>
            Wybierz lokalny folder JPEG. Zapisywane są wyłącznie uchwyt i
            metadane; obrazy nie są kopiowane do IndexedDB.
          </p>
          <button
            className="primaryButton"
            disabled={!canWrite || busy || sourceMode === 'unsupported'}
            onClick={() => void chooseDirectory()}
            type="button"
          >
            {busy ? 'Indeksowanie…' : 'Wybierz folder źródłowy'}
          </button>
          {sourceMode === 'webkitdirectory_reselect' ? (
            <p>
              Tryb zgodności wymaga ponownego wyboru tego folderu po każdym
              ponownym otwarciu przeglądarki.
            </p>
          ) : null}
        </>
      ) : (
        <div>
          <p>
            <strong>{batch.sourceDirectoryName}</strong> ·{' '}
            {batch.fileCount.toLocaleString('pl-PL')} JPEG · kursor{' '}
            {batch.cursorIndex + 1}/{batch.fileCount}
          </p>
          <p>
            Oczekujące operacje lokalne:{' '}
            <strong>{snapshot?.pendingOperationCount ?? 0}</strong>. Brak
            operacji nie oznacza synchronizacji bez potwierdzenia hosta.
          </p>
          {permission === 'prompt' ||
          permission === 'denied' ||
          permission === 'error' ? (
            <button
              className="primaryButton"
              disabled={!canWrite || busy}
              onClick={() => void requestStoredPermission()}
              type="button"
            >
              Ponów zgodę na odczyt
            </button>
          ) : null}
          {session?.sourceHandle === null ||
          session?.sourceKind === 'webkitdirectory_reselect' ||
          permission === 'denied' ||
          permission === 'error' ? (
            <button
              disabled={!canWrite || busy}
              onClick={() => void chooseDirectory()}
              type="button"
            >
              Wskaż ten sam folder ponownie
            </button>
          ) : null}
        </div>
      )}

      <input
        accept="image/jpeg,.jpg,.jpeg"
        aria-label="Wybierz folder JPEG w trybie zgodności"
        hidden
        multiple
        onChange={(event) => void chooseFallback(event.currentTarget.files)}
        ref={fallbackInput}
        type="file"
      />
      {notice ? <p>{notice}</p> : null}
      {error ? (
        <p className="reviewerAccessError" role="alert">
          {error}
        </p>
      ) : null}
      <small>
        Trwały outbox i kursor są gotowe do synchronizacji w TASK 9. Ten etap
        nie wysyła operacji ani danych JPEG do hosta.
      </small>
    </section>
  );
}

function errorMessage(cause: unknown): string {
  if (
    cause instanceof RemoteSourceAdapterError ||
    cause instanceof RemoteSelectionStoreError
  ) {
    return `${cause.message} (${cause.code})`;
  }
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się przygotować lokalnego źródła.';
}

function isPickerCancelled(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}
