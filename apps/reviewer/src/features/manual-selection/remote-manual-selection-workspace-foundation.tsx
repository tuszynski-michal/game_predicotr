'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RemoteManualSelectionWorkspace } from './remote-manual-selection-workspace';
import {
  DirectoryHandleRemoteSourceAdapter,
  RemoteSourceAdapterError,
  WebkitDirectoryRemoteSourceAdapter,
  createRemoteSourceItemRecords,
  detectRemoteSourceMode,
  validateRemoteSourceRelink,
  type ReadableDirectoryHandle,
  type RemoteSourceFileReader,
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
import { FetchRemoteSelectionControlTransport } from './remote-selection-sync';
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
  const transport = useMemo(
    () => new FetchRemoteSelectionControlTransport(clientInstanceId),
    [clientInstanceId],
  );
  const [snapshot, setSnapshot] =
    useState<RemoteSelectionRestoreSnapshot | null>(null);
  const [tabState, setTabState] = useState(EMPTY_TAB_STATE);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [collectionName, setCollectionName] = useState('Zdjęcia');
  const [batchName, setBatchName] = useState('');
  const [firstLayout, setFirstLayout] = useState('1');
  const [direction, setDirection] = useState<'ascending' | 'descending'>(
    'ascending',
  );
  const [sourceReader, setSourceReader] =
    useState<RemoteSourceFileReader | null>(null);
  const [sourceMode, setSourceMode] =
    useState<ReturnType<typeof detectRemoteSourceMode>>('unsupported');
  const fallbackInput = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const restored = await store.restore(sessionId);
    if (restored.session?.sourceHandle !== null && restored.session !== null) {
      const adapter = new DirectoryHandleRemoteSourceAdapter(
        restored.session.sourceHandle as ReadableDirectoryHandle,
      );
      const permission = await adapter.permissionState();
      setSourceReader(
        permission === 'granted' || permission === 'unsupported'
          ? adapter
          : null,
      );
      if (permission !== restored.session.permissionState) {
        const session = { ...restored.session, permissionState: permission };
        await store.saveSession(session);
        setSnapshot({ ...restored, session });
        return;
      }
    }
    setSnapshot(restored);
    if (restored.batch !== null) {
      setCollectionName(restored.batch.collectionName ?? 'Zdjęcia');
      setBatchName(
        restored.batch.batchName ?? restored.batch.sourceDirectoryName,
      );
      setFirstLayout(String(restored.batch.firstLayout));
      setDirection(restored.batch.direction);
    }
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
      await persistIndexedSource(
        await adapter.index(),
        permissionState,
        adapter,
      );
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
      const adapter = new WebkitDirectoryRemoteSourceAdapter([...files]);
      await persistIndexedSource(await adapter.index(), 'unsupported', adapter);
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
    reader: RemoteSourceFileReader,
  ) {
    const persistence = await requestBestEffortPersistentStorage();
    if (batch !== null) {
      const expected = await store.loadSourceManifest(sessionId, batch.batchId);
      validateRemoteSourceRelink(expected, indexed.manifest);
      if (session === null) {
        throw new RemoteSelectionStoreError(
          'REMOTE_SELECTION_SESSION_NOT_FOUND',
          'Nie znaleziono lokalnego stanu sesji.',
        );
      }
      await store.saveSession({
        ...session,
        permissionState,
        persistenceGranted: persistence.granted,
        sourceDirectoryName: indexed.sourceDirectoryName,
        sourceHandle: indexed.sourceHandle,
        updatedAt: new Date().toISOString(),
      });
      setSourceReader(reader);
      await refresh();
      setNotice('Folder został bezpiecznie powiązany ponownie.');
      return;
    }

    const now = new Date().toISOString();
    const batchId = crypto.randomUUID();
    const parsedFirstLayout = Number.parseInt(firstLayout, 10) || 1;
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
      batchName: indexed.sourceDirectoryName,
      collectionId: crypto.randomUUID(),
      collectionName: 'Zdjęcia',
      cursorIndex: 0,
      decisions: [],
      direction,
      fileCount: indexed.manifest.fileCount,
      firstLayout: parsedFirstLayout,
      hostRegistered: false,
      navigationStep: 1,
      nextRangeStart: parsedFirstLayout,
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
    setSourceReader(reader);
    setBatchName(indexed.sourceDirectoryName);
    await refresh();
    setNotice(
      `Zaindeksowano ${indexed.manifest.fileCount.toLocaleString('pl-PL')} JPEG-ów bez kopiowania danych. Uzupełnij nazwy i aktywuj partię.`,
    );
  }

  async function activateBatch() {
    if (!canWrite || busy || batch === null) return;
    const parsedFirstLayout = Number.parseInt(firstLayout, 10);
    if (
      collectionName.trim() === '' ||
      batchName.trim() === '' ||
      !Number.isSafeInteger(parsedFirstLayout) ||
      parsedFirstLayout < 1
    ) {
      setError(
        'Podaj nazwy kolekcji i partii oraz dodatni pierwszy numer planszy.',
      );
      return;
    }
    setBusy(true);
    setError('');
    setNotice('Tworzenie kolekcji i rejestrowanie manifestu źródła…');
    try {
      const collectionId = batch.collectionId ?? crypto.randomUUID();
      const configured: RemoteSelectionLocalBatchRecord = {
        ...batch,
        batchName: batchName.trim(),
        collectionId,
        collectionName: collectionName.trim(),
        cursorIndex: direction === 'ascending' ? 0 : batch.fileCount - 1,
        direction,
        firstLayout: parsedFirstLayout,
        nextRangeStart: parsedFirstLayout,
        updatedAt: new Date().toISOString(),
      };
      await store.saveBatch(configured);
      await transport.createCollection({
        collectionId,
        name: configured.collectionName ?? 'Zdjęcia',
        sessionId,
      });
      await transport.createBatch(collectionId, {
        batchId: configured.batchId,
        direction: configured.direction,
        firstLayout: configured.firstLayout,
        name: configured.batchName ?? configured.sourceDirectoryName,
        sessionId,
        sourceManifestChecksumSha256: configured.sourceManifestChecksumSha256,
        totalFileCount: configured.fileCount,
      });
      const sourceItems = [];
      for (let after = -1; after < configured.fileCount - 1;) {
        const page = await store.listSourceItemsPage(
          sessionId,
          configured.batchId,
          after,
          500,
        );
        if (page.length === 0) break;
        sourceItems.push(...page);
        after = page.at(-1)?.ordinal ?? after;
      }
      if (sourceItems.length !== configured.fileCount) {
        throw new RemoteSelectionStoreError(
          'REMOTE_SELECTION_SOURCE_MANIFEST_INCOMPLETE',
          'Lokalny manifest źródła jest niekompletny.',
        );
      }
      await transport.registerCompleteSourceManifest(
        sessionId,
        configured.batchId,
        configured.sourceKind,
        sourceItems,
        500,
      );
      await store.saveBatch({
        ...configured,
        hostRegistered: true,
        updatedAt: new Date().toISOString(),
      });
      await refresh();
      setNotice('Partia jest aktywna. Możesz rozpocząć ręczną selekcję.');
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function requestStoredPermission() {
    if (!canWrite || session === null || session.sourceHandle === null) return;
    setBusy(true);
    setError('');
    try {
      const adapter = new DirectoryHandleRemoteSourceAdapter(
        session.sourceHandle as ReadableDirectoryHandle,
      );
      const permissionState = await adapter.requestPermission();
      await store.saveSession({
        ...session,
        permissionState,
        updatedAt: new Date().toISOString(),
      });
      if (permissionState === 'granted' || permissionState === 'unsupported')
        setSourceReader(adapter);
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

  if (batch?.hostRegistered && session !== null) {
    return (
      <>
        {sourceReader === null ? (
          <section className="remoteSelectionSourceRecovery">
            <p>
              Przywróć dostęp do lokalnego folderu, aby wyświetlać podglądy i
              wysyłać wybrane JPEG-i. Decyzje i kursor pozostały zapisane.
            </p>
            {session.sourceHandle !== null ? (
              <button
                disabled={!canWrite || busy}
                onClick={() => void requestStoredPermission()}
                type="button"
              >
                Ponów zgodę
              </button>
            ) : null}
            <button
              disabled={!canWrite || busy}
              onClick={() => void chooseDirectory()}
              type="button"
            >
              Wskaż ten sam folder
            </button>
          </section>
        ) : null}
        <RemoteManualSelectionWorkspace
          batch={batch}
          canWrite={canWrite}
          clientInstanceId={clientInstanceId}
          session={session}
          sourceReader={sourceReader}
          store={store}
        />
        {error ? (
          <p className="reviewerAccessError" role="alert">
            {error}
          </p>
        ) : null}
      </>
    );
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
            metadane; obrazy nie są kopiowane do IndexedDB ani wysyłane przed
            wyborem.
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
              Tryb zgodności wymaga ponownego wyboru tego folderu po ponownym
              otwarciu przeglądarki.
            </p>
          ) : null}
        </>
      ) : (
        <div className="remoteSelectionSetup">
          <p>
            <strong>{batch.sourceDirectoryName}</strong> ·{' '}
            {batch.fileCount.toLocaleString('pl-PL')} JPEG ·{' '}
            {formatBytes(batch.totalBytes)}
          </p>
          <label>
            Kolekcja
            <input
              maxLength={200}
              onChange={(event) => setCollectionName(event.target.value)}
              value={collectionName}
            />
          </label>
          <label>
            Partia
            <input
              maxLength={200}
              onChange={(event) => setBatchName(event.target.value)}
              value={batchName}
            />
          </label>
          <label>
            Pierwsza plansza
            <input
              min="1"
              onChange={(event) => setFirstLayout(event.target.value)}
              type="number"
              value={firstLayout}
            />
          </label>
          <label>
            Kolejność
            <select
              onChange={(event) =>
                setDirection(event.target.value as 'ascending' | 'descending')
              }
              value={direction}
            >
              <option value="ascending">Rosnąco</option>
              <option value="descending">Malejąco</option>
            </select>
          </label>
          <button
            className="primaryButton"
            disabled={!canWrite || busy}
            onClick={() => void activateBatch()}
            type="button"
          >
            {busy ? 'Rejestrowanie…' : 'Utwórz i aktywuj partię'}
          </button>
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
        Podglądy pozostają lokalne. Host otrzymuje metadane, decyzje oraz
        wyłącznie JPEG-i jawnie zatwierdzone przez operatora.
      </small>
    </section>
  );
}

function errorMessage(cause: unknown): string {
  if (
    cause instanceof RemoteSourceAdapterError ||
    cause instanceof RemoteSelectionStoreError
  )
    return `${cause.message} (${cause.code})`;
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się przygotować lokalnego źródła.';
}

function isPickerCancelled(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}

function formatBytes(value: number): string {
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}
