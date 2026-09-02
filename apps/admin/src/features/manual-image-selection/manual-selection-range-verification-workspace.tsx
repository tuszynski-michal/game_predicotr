'use client';

import type {
  AdminApiClient,
  FilenameRangeVerificationItemResponse,
  SemiAutomaticSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import {
  jobProgressLabel,
  jobProgressPercent,
} from '@/features/jobs/job-state';
import {
  uploadSemiAutomaticSelectionFolder,
  type BrowserDirectoryHandle,
  type SemiAutomaticSelectionClient,
  type SemiAutomaticSourceFile,
  type SemiAutomaticSelectionUploadProgress,
} from '@/features/semi-automatic-image-selection/semi-automatic-selection-actions.ts';
import {
  isLocalDirectoryPickerActive,
  pickLocalDirectory,
  subscribeLocalDirectoryPickerActive,
} from '../../lib/local-directory-picker.ts';

import { ManualImageViewer, useManualImageViewer } from './manual-image-viewer';
import {
  deleteRepairFile,
  inspectRepairDirectory,
  writeRepairManifest,
  type RepairDirectorySnapshot,
} from './manual-selection-repair-storage.ts';

const EMPTY_UPLOAD: SemiAutomaticSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};
const POLL_INTERVAL_MS = 2_000;

type VerificationClient = SemiAutomaticSelectionClient &
  Pick<
    AdminApiClient,
    | 'getSemiAutomaticImageSelection'
    | 'getSemiAutomaticImageSelectionCapabilities'
    | 'listSemiAutomaticFilenameRangeVerifications'
  >;

export function ManualSelectionRangeVerificationWorkspace({
  apiBaseUrl,
  client,
}: {
  readonly apiBaseUrl: string;
  readonly client?: VerificationClient;
}) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const busyRef = useRef(false);
  const [snapshot, setSnapshot] = useState<RepairDirectorySnapshot | null>(
    null,
  );
  const [run, setRun] = useState<SemiAutomaticSelectionRunResponse | null>(
    null,
  );
  const [items, setItems] = useState<
    readonly FilenameRangeVerificationItemResponse[]
  >([]);
  const [cursor, setCursor] = useState(0);
  const [upload, setUpload] = useState(EMPTY_UPLOAD);
  const [busy, setBusy] = useState(false);
  const [directoryPickerActive, setDirectoryPickerActive] = useState(
    isLocalDirectoryPickerActive,
  );
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const flagged = useMemo(
    () => items.filter((item) => item.verificationStatus !== 'verified'),
    [items],
  );
  const safeCursor = Math.min(cursor, Math.max(0, flagged.length - 1));
  const current = flagged[safeCursor];
  const localImages = useMemo(() => {
    if (snapshot === null) return [];
    const handles = new Map(
      snapshot.files.map((file) => [
        file.fileName.toLocaleLowerCase('en-US'),
        file.handle,
      ]),
    );
    return flagged.flatMap((item) => {
      const fileName = baseName(item.sourceRelativePath);
      const handle = handles.get(fileName.toLocaleLowerCase('en-US'));
      return handle === undefined
        ? []
        : [{ handle, name: fileName, relativePath: fileName }];
    });
  }, [flagged, snapshot]);
  const handleViewerError = useCallback(
    (message: string) => setError(message),
    [],
  );
  const viewer = useManualImageViewer(
    localImages,
    current === undefined ? -1 : safeCursor,
    handleViewerError,
  );

  useEffect(() => {
    return subscribeLocalDirectoryPickerActive(() => {
      setDirectoryPickerActive(isLocalDirectoryPickerActive());
    });
  }, []);

  useEffect(() => {
    if (run === null || !isActive(run)) return undefined;
    let cancelled = false;
    let timer: number | null = null;
    const poll = async (): Promise<void> => {
      const result = await api.getSemiAutomaticImageSelection(run.id);
      if (cancelled) return;
      if (result.error !== undefined || result.data === undefined) {
        setNotice('Nie udało się odświeżyć progresu. Ponawiam próbę.');
      } else {
        setRun(result.data);
        if (!isActive(result.data)) {
          await loadVerificationItems(api, result.data.id, setItems, setError);
          return;
        }
      }
      timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    };
    timer = window.setTimeout(() => void poll(), POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [api, run]);

  async function chooseDirectory(): Promise<void> {
    if (busyRef.current) return;
    setError('');
    try {
      const directory = await pickReadWriteDirectory();
      const inspected = await inspectRepairDirectory(directory);
      await writeRepairManifest(directory, inspected.repairManifest);
      setSnapshot(inspected);
      setRun(null);
      setItems([]);
      setCursor(0);
      setUpload(EMPTY_UPLOAD);
      setNotice(
        `Wybrano ${inspected.files.length.toLocaleString('pl-PL')} plików seq_*.`,
      );
    } catch (cause) {
      if (!isPickerCancellation(cause)) setError(errorMessage(cause));
    }
  }

  async function start(): Promise<void> {
    if (snapshot === null || busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    setError('');
    setNotice('Przygotowuję bezpieczny staging i uruchamiam OCR zakresów.');
    try {
      const files: SemiAutomaticSourceFile[] = await Promise.all(
        snapshot.files.map(async (item) => ({
          file: await item.handle.getFile(),
          handle: item.handle,
          relativePath: item.fileName,
        })),
      );
      const result = await uploadSemiAutomaticSelectionFolder({
        api,
        direction: 'ascending',
        files,
        firstSequenceNumber: snapshot.repairManifest.collectionStart,
        lastSequenceNumber: snapshot.repairManifest.collectionEnd,
        mode: 'filename_verification',
        onProgress: setUpload,
        sourceDirectory: snapshot.directory as BrowserDirectoryHandle,
      });
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setRun(result.created.run);
      setNotice(
        'Weryfikacja działa w tle. Postęp jest odświeżany automatycznie.',
      );
      if (!isActive(result.created.run)) {
        await loadVerificationItems(
          api,
          result.created.run.id,
          setItems,
          setError,
        );
      }
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  async function removeCurrent(): Promise<void> {
    if (snapshot === null || current === undefined || busyRef.current) return;
    const fileName = baseName(current.sourceRelativePath);
    const selected = snapshot.files.find(
      (file) =>
        file.fileName.toLocaleLowerCase('en-US') ===
        fileName.toLocaleLowerCase('en-US'),
    );
    if (selected === undefined) {
      setError('Plik wskazany przez wynik OCR nie istnieje już w katalogu.');
      return;
    }
    busyRef.current = true;
    setBusy(true);
    setError('');
    try {
      const result = await deleteRepairFile({
        directory: snapshot.directory,
        fileName: selected.fileName,
        kind: 'delete',
        manifest: snapshot.repairManifest,
        outputManifest: snapshot.outputManifest,
        sourceIndex: current.sourceIndex,
        sourcePath: current.sourceRelativePath,
      });
      setSnapshot({
        ...snapshot,
        files: snapshot.files.filter(
          (file) => file.fileName !== selected.fileName,
        ),
        outputManifest: result.outputManifest,
        repairManifest: result.manifest,
      });
      setItems((existing) =>
        existing.filter((item) => item.sourceIndex !== current.sourceIndex),
      );
      setCursor(Math.min(safeCursor, Math.max(0, flagged.length - 2)));
      setNotice(
        `Usunięto ${selected.fileName}. Lukę uzupełnisz w „Uzupełnij luki”.`,
      );
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (
        event.key.toLocaleLowerCase('en-US') !== 'f' ||
        isEditable(event.target)
      )
        return;
      if (current === undefined || busyRef.current) return;
      event.preventDefault();
      void removeCurrent();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  });

  const uploadPercent =
    upload.totalBytes === 0
      ? 0
      : (upload.uploadedBytes / upload.totalBytes) * 100;
  const runPercent = run === null ? null : jobProgressPercent(run.job);

  if (items.length > 0 && snapshot !== null) {
    return (
      <section className="manualImageSelectionWorkspace manualImageSelectionActive">
        <header className="manualImageSelectionHeader">
          <div>
            <p className="eyebrow">Niezależnie od gry · lokalnie</p>
            <h2>Weryfikacja zakresów</h2>
            <p>
              {flagged.length === 0
                ? 'Wszystkie zakresy są zgodne.'
                : `Do ręcznej kontroli: ${safeCursor + 1} z ${flagged.length}`}
            </p>
          </div>
        </header>
        {current !== undefined ? (
          <>
            <p className="manualSelectionRepairWarning" role="status">
              {verificationMessage(current)}
            </p>
            <ManualImageViewer
              busy={busy}
              currentLabel={`Nazwa: ${formatRange(current.expectedRange)} · OCR: ${formatRange(current.observedRange)}`}
              currentPosition={safeCursor + 1}
              currentRelativePath={current.sourceRelativePath}
              imageCount={flagged.length}
              navigationStepLabel="skok: 1"
              nextDisabled={safeCursor >= flagged.length - 1}
              onNext={() =>
                setCursor((value) => Math.min(flagged.length - 1, value + 1))
              }
              onPrevious={() => setCursor((value) => Math.max(0, value - 1))}
              previousDisabled={safeCursor <= 0}
              state={viewer}
              toolbarStart={
                <span className="manualImageSelectionStep">skok: 1</span>
              }
            />
            <div className="manualImageSelectionActions">
              <button
                className="dangerButton"
                disabled={busy}
                onClick={() => void removeCurrent()}
                type="button"
              >
                Odrzuć i usuń F
              </button>
            </div>
          </>
        ) : null}
        <button
          className="secondaryButton"
          onClick={() => setItems([])}
          type="button"
        >
          Wróć do konfiguracji
        </button>
        {notice !== '' ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {error !== '' ? <p className="formError">{error}</p> : null}
      </section>
    );
  }

  return (
    <section className="manualImageSelectionWorkspace manualSelectionRepairSetup">
      <header className="manualImageSelectionHeader">
        <div>
          <p className="eyebrow">Niezależnie od gry · lokalnie</p>
          <h2>Weryfikacja zakresów</h2>
          <p>
            Sprawdź automatycznie, czy zakres z nazwy każdego pliku seq_* zgadza
            się z numerami widocznymi na zdjęciu.
          </p>
        </div>
      </header>
      <div className="manualImageSelectionSetup">
        <button
          className="secondaryButton"
          disabled={busy || directoryPickerActive}
          onClick={() => void chooseDirectory()}
          type="button"
        >
          Wybierz katalog z plikami seq_*
        </button>
        {snapshot !== null ? (
          <p className="manualImageSelectionReady">
            {snapshot.directory.name} ·{' '}
            {snapshot.files.length.toLocaleString('pl-PL')} plików
          </p>
        ) : null}
        <button
          className="primaryButton"
          disabled={busy || snapshot === null}
          onClick={() => void start()}
          type="button"
        >
          Start
        </button>
        {upload.totalFiles > 0 && run === null ? (
          <div className="jobProgressSection">
            <div className="jobProgressSummary">
              <strong>
                {upload.uploadedFiles} / {upload.totalFiles}
              </strong>
              <span>{uploadPercent.toFixed(1)}%</span>
            </div>
            <progress max={100} value={uploadPercent} />
          </div>
        ) : null}
        {run !== null ? (
          <div className="jobProgressSection">
            <div className="jobProgressSummary">
              <strong>{jobProgressLabel(run.job)}</strong>
              <span>
                {runPercent === null ? 'w toku' : `${runPercent.toFixed(1)}%`}
              </span>
            </div>
            <progress max={100} value={runPercent ?? 0} />
          </div>
        ) : null}
        {notice !== '' ? (
          <p className="manualImageSelectionStatus">{notice}</p>
        ) : null}
        {error !== '' ? (
          <p className="formError" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </section>
  );
}

async function loadVerificationItems(
  api: VerificationClient,
  runId: string,
  setItems: (items: readonly FilenameRangeVerificationItemResponse[]) => void,
  setError: (message: string) => void,
): Promise<void> {
  const items: FilenameRangeVerificationItemResponse[] = [];
  let after: number | undefined;
  do {
    const result = await api.listSemiAutomaticFilenameRangeVerifications(
      runId,
      after,
      500,
    );
    if (result.error !== undefined || result.data === undefined) {
      setError(
        apiErrorMessage(
          result.error,
          'Nie udało się pobrać wyników weryfikacji.',
        ),
      );
      return;
    }
    items.push(...result.data.items);
    after = result.data.nextAfterSourceIndex ?? undefined;
  } while (after !== undefined);
  setItems(items);
}

async function pickReadWriteDirectory(): Promise<FileSystemDirectoryHandle> {
  return pickLocalDirectory({ id: 'gp-range-verify', mode: 'readwrite' });
}

function isActive(run: SemiAutomaticSelectionRunResponse): boolean {
  return ['ready', 'running', 'paused', 'syncing_output'].includes(run.status);
}

function baseName(path: string): string {
  return path.replaceAll('\\', '/').split('/').at(-1) ?? path;
}

function formatRange(
  range: { readonly start: number; readonly end: number } | null,
): string {
  return range === null ? 'nie odczytano' : `${range.start}–${range.end}`;
}

function verificationMessage(
  item: FilenameRangeVerificationItemResponse,
): string {
  if (item.verificationStatus === 'mismatch')
    return 'OCR odczytał inny zakres niż nazwa pliku.';
  if (item.verificationStatus === 'invalid_filename')
    return 'Nazwa pliku nie zawiera poprawnego zakresu seq_*.';
  return 'Nie uzyskano pewnego dowodu z pięciu punktów obrazu. Sprawdź zdjęcie ręcznie.';
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error
    ? cause.message
    : 'Nie udało się wykonać operacji.';
}

function isPickerCancellation(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === 'AbortError';
}

function isEditable(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable ||
      ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName))
  );
}
