'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  inspectOperatorLocalOutputDirectory,
  resetOperatorLocalOutputDirectory,
  resumeOperatorLocalBatch,
  writeOperatorLocalManifest,
} from './operator-local-selection-output';
import {
  clearRemoteManualSelectionScroll,
  RemoteManualSelectionWorkspace,
} from './remote-manual-selection-workspace';
import {
  DirectoryHandleRemoteSourceAdapter,
  REMOTE_SOURCE_DIRECTORY_PICKER_ID,
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
  remoteSelectionWorkspaceState,
  requestBestEffortPersistentStorage,
  restartRemoteSelectionLocalBatch,
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
    readonly mode: 'read' | 'readwrite';
  }) => Promise<FileSystemDirectoryHandle>;
};

const REMOTE_OUTPUT_PARENT_PICKER_ID = 'gp-rms-output-parent';

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

  const refresh = useCallback(
    async (repairMissingOutput = false) => {
      const restored = await store.restore(sessionId);
      let restoredSession = restored.session;
      let restoredBatch = restored.batch;
      if (restoredSession?.sourceHandle !== null && restoredSession !== null) {
        const adapter = new DirectoryHandleRemoteSourceAdapter(
          restoredSession.sourceHandle as ReadableDirectoryHandle,
        );
        const permission = await adapter.permissionState();
        setSourceReader(
          permission === 'granted' || permission === 'unsupported'
            ? adapter
            : null,
        );
        if (permission !== restoredSession.permissionState) {
          restoredSession = { ...restoredSession, permissionState: permission };
        }
      }
      if (
        restoredSession?.outputHandle !== null &&
        restoredSession?.outputHandle !== undefined
      ) {
        const permission = await directoryPermissionState(
          restoredSession.outputHandle,
          'readwrite',
        );
        if (permission !== restoredSession.outputPermissionState) {
          restoredSession = {
            ...restoredSession,
            outputPermissionState: permission,
          };
        }
      }
      if (
        repairMissingOutput &&
        restoredSession !== null &&
        restoredBatch !== null &&
        (restoredSession.permissionState === 'error' ||
          restoredSession.outputPermissionState === 'error')
      ) {
        const relink = await store.resetLocalWorkspaceForDirectoryRelink({
          batchId: restoredBatch.batchId,
          sessionId: restoredSession.sessionId,
        });
        restoredBatch = relink.batch;
        restoredSession = relink.session;
        setSourceReader(null);
        clearRemoteManualSelectionScroll(
          restoredSession.sessionId,
          restoredBatch.batchId,
        );
        setNotice(
          'Zapisany folder zdjęć lub folder wynikowy jest niedostępny. Selekcja została zresetowana — wskaż ponownie oba katalogi.',
        );
      }
      if (
        repairMissingOutput &&
        restoredSession !== null &&
        restoredBatch !== null &&
        restoredSession.outputParentHandle !== null &&
        restoredSession.outputParentHandle !== undefined &&
        restoredSession.outputDirectoryName
      ) {
        const outputParent = restoredSession.outputParentHandle;
        const outputDirectoryName = restoredSession.outputDirectoryName;
        const parentPermission = await directoryPermissionState(
          outputParent,
          'readwrite',
        );
        restoredSession = {
          ...restoredSession,
          outputParentPermissionState: parentPermission,
        };
        if (parentPermission === 'error') {
          const relink = await store.resetLocalWorkspaceForDirectoryRelink({
            batchId: restoredBatch.batchId,
            sessionId: restoredSession.sessionId,
          });
          restoredBatch = relink.batch;
          restoredSession = relink.session;
          setSourceReader(null);
          clearRemoteManualSelectionScroll(
            restoredSession.sessionId,
            restoredBatch.batchId,
          );
          setNotice(
            'Katalog nadrzędny wyniku jest niedostępny. Selekcja została zresetowana — wskaż ponownie folder zdjęć i katalog zapisu.',
          );
        }
        if (
          parentPermission === 'granted' ||
          parentPermission === 'unsupported'
        ) {
          let liveOutput: FileSystemDirectoryHandle | null = null;
          let outputWasMissing = false;
          try {
            liveOutput =
              await outputParent.getDirectoryHandle(outputDirectoryName);
          } catch (cause) {
            if (!isNotFoundError(cause)) throw cause;
            outputWasMissing = true;
          }
          const outputState =
            liveOutput === null
              ? null
              : await inspectOperatorLocalOutputDirectory(liveOutput);
          const lostProgressFiles =
            outputWasMissing ||
            (outputState?.kind === 'empty' &&
              restoredBatch.hostRegistered === true);
          if (lostProgressFiles) {
            const relink = await store.resetLocalWorkspaceForDirectoryRelink({
              batchId: restoredBatch.batchId,
              sessionId: restoredSession.sessionId,
            });
            restoredBatch = relink.batch;
            restoredSession = relink.session;
            setSourceReader(null);
            clearRemoteManualSelectionScroll(
              restoredSession.sessionId,
              restoredBatch.batchId,
            );
            setNotice(
              `Folder wynikowy „${outputDirectoryName}” jest niedostępny. Selekcja została zresetowana — wskaż ponownie folder zdjęć i katalog zapisu.`,
            );
          } else if (liveOutput !== null) {
            restoredSession = {
              ...restoredSession,
              outputHandle: liveOutput,
              outputPermissionState: 'granted',
            };
          }
        }
      }
      if (restoredSession !== restored.session && restoredSession !== null) {
        await store.saveSession(restoredSession);
      }
      setSnapshot({
        ...restored,
        batch: restoredBatch,
        session: restoredSession,
      });
      if (restoredBatch !== null) {
        setCollectionName(restoredBatch.collectionName ?? 'Zdjęcia');
        setBatchName(
          restoredBatch.batchName ?? restoredBatch.sourceDirectoryName,
        );
        setFirstLayout(String(restoredBatch.firstLayout));
        setDirection(restoredBatch.direction);
      }
    },
    [sessionId, store],
  );

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

  const recoverUnavailableDirectories = useCallback(
    async (cause: unknown): Promise<boolean> => {
      if (!isDirectoryUnavailableError(cause)) return false;
      const restored = await store.restore(sessionId);
      if (restored.session === null || restored.batch === null) return false;
      const relink = await store.resetLocalWorkspaceForDirectoryRelink({
        batchId: restored.batch.batchId,
        sessionId,
      });
      setSourceReader(null);
      clearRemoteManualSelectionScroll(sessionId, relink.batch.batchId);
      setSnapshot({
        ...restored,
        batch: relink.batch,
        session: relink.session,
      });
      setError('');
      setNotice(
        'Folder zdjęć lub folder wynikowy jest niedostępny. Selekcja zaczyna się od początku — wskaż ponownie folder zdjęć, a następnie katalog zapisu.',
      );
      return true;
    },
    [sessionId, store],
  );

  useEffect(() => {
    if (!canWrite) return;
    const repair = () => {
      void refresh(true).catch((cause) => {
        void recoverUnavailableDirectories(cause).then((recovered) => {
          if (!recovered) setError(errorMessage(cause));
        });
      });
    };
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') repair();
    };
    repair();
    window.addEventListener('focus', repair);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('focus', repair);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [canWrite, recoverUnavailableDirectories, refresh]);

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
        id: REMOTE_SOURCE_DIRECTORY_PICKER_ID,
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
      if (
        !isPickerCancelled(cause) &&
        !(await recoverUnavailableDirectories(cause))
      )
        setError(errorMessage(cause));
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
      if (!(await recoverUnavailableDirectories(cause)))
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
      outputDirectoryName: null,
      outputHandle: null,
      outputParentHandle: null,
      outputParentPermissionState: 'prompt',
      outputPermissionState: 'prompt',
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
      `Zaindeksowano ${indexed.manifest.fileCount.toLocaleString('pl-PL')} JPEG-ów bez kopiowania danych. Wybierz katalog, w którym ma powstać sąsiedni folder wynikowy.`,
    );
  }

  async function chooseOutputParent() {
    if (!canWrite || busy || session === null || batch === null) return;
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
    if (picker === undefined) {
      setError(
        'Ta przeglądarka nie obsługuje trwałego zapisu do lokalnego folderu.',
      );
      return;
    }
    const sourceName = session.sourceDirectoryName?.trim();
    if (!sourceName) {
      setError('Najpierw wybierz folder źródłowy.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const parent = await picker({
        id: REMOTE_OUTPUT_PARENT_PICKER_ID,
        mode: 'readwrite',
      });
      const outputName = `${sourceName} wybrane`;
      const output = await parent.getDirectoryHandle(outputName, {
        create: true,
      });
      const outputState = await inspectOperatorLocalOutputDirectory(output);
      const resumed =
        outputState.kind === 'resumable'
          ? await resumeOperatorLocalBatch(
              outputState.manifest,
              batch,
              (ordinal) =>
                store.loadSourceItem(sessionId, batch.batchId, ordinal),
            )
          : null;
      const updated: RemoteSelectionLocalSessionRecord = {
        ...session,
        outputDirectoryName: outputName,
        outputHandle: output,
        outputParentHandle: parent,
        outputParentPermissionState: 'granted',
        outputPermissionState: 'granted',
        updatedAt: new Date().toISOString(),
      };
      await store.saveSession(updated);
      if (resumed !== null) {
        await writeOperatorLocalManifest(output, {
          allowSessionAdoption: true,
          batchId: resumed.batchId,
          currentIndex: resumed.cursorIndex,
          decisions: resumed.decisions ?? [],
          direction: resumed.direction,
          fileCount: resumed.fileCount,
          firstLayout: resumed.firstLayout,
          nextRangeStart: resumed.nextRangeStart ?? resumed.firstLayout,
          sessionId: resumed.sessionId,
          sourceDirectoryName: resumed.sourceDirectoryName,
          sourceManifestChecksumSha256: resumed.sourceManifestChecksumSha256,
        });
        await store.saveBatch(resumed);
        setFirstLayout(String(resumed.firstLayout));
        setDirection(resumed.direction);
        await refresh();
        setNotice(
          `Wznowiono selekcję od zdjęcia ${resumed.cursorIndex + 1}; następny zakres to ${resumed.nextRangeStart}–${(resumed.nextRangeStart ?? resumed.firstLayout) + 8}.`,
        );
        return;
      }
      await refresh();
      setNotice(
        `Folder wynikowy „${outputName}” jest pusty i gotowy do nowej selekcji.`,
      );
    } catch (cause) {
      if (
        !isPickerCancelled(cause) &&
        !(await recoverUnavailableDirectories(cause))
      )
        setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function activateBatch() {
    if (
      !canWrite ||
      busy ||
      batch === null ||
      session?.outputHandle === null ||
      session?.outputHandle === undefined
    )
      return;
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
    setNotice('Przygotowywanie lokalnego folderu i manifestu…');
    try {
      const outputState = await inspectOperatorLocalOutputDirectory(
        session.outputHandle,
      );
      if (outputState.kind === 'resumable') {
        const resumed = await resumeOperatorLocalBatch(
          outputState.manifest,
          batch,
          (ordinal) => store.loadSourceItem(sessionId, batch.batchId, ordinal),
        );
        await writeOperatorLocalManifest(session.outputHandle, {
          allowSessionAdoption: true,
          batchId: resumed.batchId,
          currentIndex: resumed.cursorIndex,
          decisions: resumed.decisions ?? [],
          direction: resumed.direction,
          fileCount: resumed.fileCount,
          firstLayout: resumed.firstLayout,
          nextRangeStart: resumed.nextRangeStart ?? resumed.firstLayout,
          sessionId: resumed.sessionId,
          sourceDirectoryName: resumed.sourceDirectoryName,
          sourceManifestChecksumSha256: resumed.sourceManifestChecksumSha256,
        });
        await store.saveBatch(resumed);
        setFirstLayout(String(resumed.firstLayout));
        setDirection(resumed.direction);
        await refresh();
        setNotice(
          `Wznowiono selekcję od zdjęcia ${resumed.cursorIndex + 1}; następny zakres to ${resumed.nextRangeStart}–${(resumed.nextRangeStart ?? resumed.firstLayout) + 8}.`,
        );
        return;
      }
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
      const configuredWorkspace = remoteSelectionWorkspaceState(configured);
      await writeOperatorLocalManifest(session.outputHandle, {
        batchId: configured.batchId,
        currentIndex: configuredWorkspace.currentIndex,
        decisions: configuredWorkspace.decisions,
        direction: configured.direction,
        fileCount: configured.fileCount,
        firstLayout: configured.firstLayout,
        nextRangeStart: configuredWorkspace.nextRangeStart,
        sessionId: session.sessionId,
        sourceDirectoryName: configured.sourceDirectoryName,
        sourceManifestChecksumSha256: configured.sourceManifestChecksumSha256,
      });
      await store.saveBatch(configured);
      await store.saveBatch({
        ...configured,
        hostRegistered: true,
        status: 'active',
        updatedAt: new Date().toISOString(),
      });
      await refresh();
      setNotice(
        'Sesja lokalna jest aktywna. Decyzje i JPEG-i nie będą wysyłane na komputer właściciela linku.',
      );
    } catch (cause) {
      if (!(await recoverUnavailableDirectories(cause)))
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
      if (!(await recoverUnavailableDirectories(cause)))
        setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function requestStoredOutputPermission() {
    if (
      !canWrite ||
      session?.outputHandle === null ||
      session?.outputHandle === undefined
    )
      return;
    setBusy(true);
    setError('');
    try {
      const permission = await requestDirectoryPermission(
        session.outputHandle,
        'readwrite',
      );
      await store.saveSession({
        ...session,
        outputPermissionState: permission,
        updatedAt: new Date().toISOString(),
      });
      await refresh();
      if (permission !== 'granted' && permission !== 'unsupported') {
        if (permission === 'error') {
          await recoverUnavailableDirectories(
            new DOMException(
              'Output directory is unavailable.',
              'NotFoundError',
            ),
          );
        } else {
          setError('Folder wynikowy nadal wymaga zgody na zapis.');
        }
      }
    } catch (cause) {
      if (!(await recoverUnavailableDirectories(cause)))
        setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  async function restartSelection() {
    if (!canWrite || busy || session === null || batch === null) return;
    if (
      !window.confirm(
        'Restart usunie wybrane JPEG-i i zapisany postęp tej selekcji. Rozpocząć od pierwszego zdjęcia?',
      )
    )
      return;
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker;
    let parent = session.outputParentHandle ?? null;
    if (parent === null) {
      if (picker === undefined) {
        setError(
          'Wskaż ponownie katalog nadrzędny w przeglądarce obsługującej zapis do folderu.',
        );
        return;
      }
      try {
        parent = await picker({
          id: REMOTE_OUTPUT_PARENT_PICKER_ID,
          mode: 'readwrite',
        });
      } catch (cause) {
        if (!isPickerCancelled(cause)) setError(errorMessage(cause));
        return;
      }
    } else {
      const permission = await requestDirectoryPermission(parent, 'readwrite');
      if (permission !== 'granted' && permission !== 'unsupported') {
        setError(
          'Nie przyznano prawa do odtworzenia folderu wynikowego. Wybierz ponownie katalog nadrzędny.',
        );
        return;
      }
    }
    const outputName =
      session.outputDirectoryName ?? `${batch.sourceDirectoryName} wybrane`;
    setBusy(true);
    setError('');
    setNotice('Restartowanie lokalnej selekcji…');
    try {
      const output = await resetOperatorLocalOutputDirectory(
        parent,
        outputName,
        batch,
      );
      const restarted = restartRemoteSelectionLocalBatch(batch);
      await writeBatchManifest(output, session.sessionId, restarted);
      await store.saveBatch(restarted);
      await store.saveSession({
        ...session,
        outputDirectoryName: outputName,
        outputHandle: output,
        outputParentHandle: parent,
        outputParentPermissionState: 'granted',
        outputPermissionState: 'granted',
        updatedAt: new Date().toISOString(),
      });
      clearRemoteManualSelectionScroll(session.sessionId, batch.batchId);
      await refresh();
      setNotice(
        `Selekcja została uruchomiona od początku. Folder „${outputName}” zawiera nowy manifest tej sesji.`,
      );
    } catch (cause) {
      if (!(await recoverUnavailableDirectories(cause)))
        setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  if (
    batch?.hostRegistered &&
    session !== null &&
    session.outputHandle !== null &&
    session.outputHandle !== undefined
  ) {
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
        {session.outputPermissionState !== 'granted' &&
        session.outputPermissionState !== 'unsupported' ? (
          <section className="remoteSelectionSourceRecovery">
            <p>
              Przywróć prawo zapisu do folderu „{session.outputDirectoryName}”.
              Postęp i decyzje pozostały zapisane na tym urządzeniu.
            </p>
            <button
              disabled={!canWrite || busy}
              onClick={() => void requestStoredOutputPermission()}
              type="button"
            >
              Ponów zgodę na zapis
            </button>
          </section>
        ) : null}
        <section className="remoteSelectionSourceRecovery">
          <p>
            Restart wraca do pierwszego zdjęcia, zeruje zakres i usuwa wyłącznie
            zweryfikowane pliki tej selekcji z folderu wynikowego.
          </p>
          <button
            className="secondaryButton"
            disabled={!canWrite || busy}
            onClick={() => void restartSelection()}
            type="button"
          >
            {busy ? 'Restartowanie…' : 'Restart selekcji'}
          </button>
        </section>
        <RemoteManualSelectionWorkspace
          key={`${batch.batchId}:${batch.updatedAt}`}
          batch={batch}
          canWrite={
            canWrite &&
            (session.outputPermissionState === 'granted' ||
              session.outputPermissionState === 'unsupported')
          }
          session={session}
          sourceReader={sourceReader}
          store={store}
          outputDirectory={session.outputHandle}
          onStorageUnavailable={recoverUnavailableDirectories}
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
          {sourceReader === null ? (
            <>
              <p>
                Wskaż ponownie folder zawierający te same zdjęcia. Aplikacja
                sprawdzi jego manifest przed przywróceniem dostępu.
              </p>
              <button
                className="secondaryButton"
                disabled={!canWrite || busy || sourceMode === 'unsupported'}
                onClick={() => void chooseDirectory()}
                type="button"
              >
                {busy ? 'Sprawdzanie…' : 'Wybierz ponownie folder zdjęć'}
              </button>
            </>
          ) : null}
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
            className="secondaryButton"
            disabled={!canWrite || busy || sourceReader === null}
            onClick={() => void chooseOutputParent()}
            type="button"
          >
            {session?.outputDirectoryName
              ? `Wynik: ${session.outputDirectoryName}`
              : 'Wybierz katalog zawierający folder źródłowy'}
          </button>
          <p>
            Przeglądarka nie udostępnia ścieżki nadrzędnej folderu źródłowego.
            Wskaż więc katalog, w którym znajduje się „
            {batch.sourceDirectoryName}”. Aplikacja utworzy obok niego „
            {batch.sourceDirectoryName} wybrane”.
          </p>
          <button
            className="primaryButton"
            disabled={
              !canWrite ||
              busy ||
              sourceReader === null ||
              session?.outputHandle === null ||
              session?.outputHandle === undefined
            }
            onClick={() => void activateBatch()}
            type="button"
          >
            {busy ? 'Przygotowywanie…' : 'Rozpocznij lokalną selekcję'}
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
        Podglądy, pozycja, zoom, decyzje i wybrane JPEG-i pozostają na tym
        urządzeniu. Do właściciela linku nie jest wysyłany żaden obraz ani
        decyzja.
      </small>
    </section>
  );
}

async function writeBatchManifest(
  output: FileSystemDirectoryHandle,
  sessionId: string,
  batch: RemoteSelectionLocalBatchRecord,
): Promise<void> {
  const workspace = remoteSelectionWorkspaceState(batch);
  await writeOperatorLocalManifest(output, {
    batchId: batch.batchId,
    currentIndex: workspace.currentIndex,
    decisions: workspace.decisions,
    direction: batch.direction,
    fileCount: batch.fileCount,
    firstLayout: batch.firstLayout,
    nextRangeStart: workspace.nextRangeStart,
    sessionId,
    sourceDirectoryName: batch.sourceDirectoryName,
    sourceManifestChecksumSha256: batch.sourceManifestChecksumSha256,
  });
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

function isNotFoundError(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'NotFoundError';
}

function isDirectoryUnavailableError(cause: unknown): boolean {
  if (isNotFoundError(cause)) return true;
  if (
    typeof cause === 'object' &&
    cause !== null &&
    'code' in cause &&
    cause.code === 'REMOTE_SELECTION_SOURCE_FILE_MISSING'
  )
    return true;
  return (
    cause instanceof Error &&
    /requested file or directory could not be found/i.test(cause.message)
  );
}

function formatBytes(value: number): string {
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KiB`;
  return `${(value / 1024 ** 2).toFixed(1)} MiB`;
}

async function directoryPermissionState(
  directory: FileSystemDirectoryHandle,
  mode: 'read' | 'readwrite',
): Promise<RemoteSourcePermissionState> {
  type PermissionDirectory = FileSystemDirectoryHandle & {
    queryPermission?: (descriptor: {
      mode: 'read' | 'readwrite';
    }) => Promise<PermissionState>;
  };
  const query = (directory as PermissionDirectory).queryPermission;
  if (query === undefined) return 'unsupported';
  try {
    return await query.call(directory, { mode });
  } catch {
    return 'error';
  }
}

async function requestDirectoryPermission(
  directory: FileSystemDirectoryHandle,
  mode: 'read' | 'readwrite',
): Promise<RemoteSourcePermissionState> {
  type PermissionDirectory = FileSystemDirectoryHandle & {
    requestPermission?: (descriptor: {
      mode: 'read' | 'readwrite';
    }) => Promise<PermissionState>;
  };
  const request = (directory as PermissionDirectory).requestPermission;
  if (request === undefined) return 'unsupported';
  try {
    return await request.call(directory, { mode });
  } catch {
    return 'error';
  }
}
