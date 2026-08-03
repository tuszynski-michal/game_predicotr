'use client';

import type {
  ImageSelectionGroupResponse,
  ImageSelectionHandoffResponse,
  ImageSelectionRunResponse,
} from '@game-predictor/admin-api-client';
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  type ImageSelectionClient,
  type ImageSelectionUploadProgress,
  type ResumableImageSelectionUpload,
  cancelPhotoSelectionUpload,
  loadManualImageSelectionGroups,
  uploadPhotoSelectionFolder,
} from './image-selection-actions';
import { ManualImageSelectionModal } from './manual-image-selection-modal';

interface ImageSelectionWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageSelectionClient;
  readonly gameId: string;
  readonly gameName: string;
  readonly onOpenImports: (handoff: ImageSelectionHandoffResponse) => void;
}

const EMPTY_PROGRESS: ImageSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};

const RUN_POLL_INTERVAL_MS = 2_000;
const RUN_POLL_REQUEST_TIMEOUT_MS = 10_000;
const RUN_POLL_MAX_DURATION_MS = 45 * 60 * 1_000;
const RUN_POLL_ERROR_THRESHOLD = 3;

export function ImageSelectionWorkspace({
  apiBaseUrl,
  client,
  gameId,
  gameName,
  onOpenImports,
}: ImageSelectionWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const pollingWindowRef = useRef<{
    readonly deadline: number;
    readonly runId: string;
  } | null>(null);
  const [progress, setProgress] = useState(EMPTY_PROGRESS);
  const [resume, setResume] = useState<ResumableImageSelectionUpload | null>(
    null,
  );
  const [run, setRun] = useState<ImageSelectionRunResponse | null>(null);
  const [manualGroups, setManualGroups] = useState<
    ImageSelectionGroupResponse[]
  >([]);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualLoading, setManualLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [refreshWarning, setRefreshWarning] = useState('');
  const activeRunId = run?.id ?? null;
  const activeRunStatus = run?.job.status ?? null;

  useEffect(() => {
    let cancelled = false;
    const runId = window.localStorage.getItem(storageKey(gameId));
    if (runId === null) return () => undefined;
    queueMicrotask(async () => {
      try {
        const result = await getImageSelectionWithTimeout(api, runId);
        if (
          !cancelled &&
          result.error === undefined &&
          result.data !== undefined
        ) {
          setRun(result.data);
        } else if (!cancelled && result.error !== undefined) {
          window.localStorage.removeItem(storageKey(gameId));
        }
      } catch {
        if (!cancelled) {
          setError('Nie udało się przywrócić ostatniego procesu tej gry.');
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, gameId]);

  useEffect(() => {
    if (activeRunId === null || activeRunStatus === null) {
      return;
    }
    if (!isPollableRunStatus(activeRunStatus)) {
      pollingWindowRef.current = null;
      return;
    }

    let cancelled = false;
    let timerId: number | null = null;
    let consecutiveFailures = 0;
    if (pollingWindowRef.current?.runId !== activeRunId) {
      pollingWindowRef.current = {
        deadline: Date.now() + RUN_POLL_MAX_DURATION_MS,
        runId: activeRunId,
      };
    }
    const deadline = pollingWindowRef.current.deadline;

    const schedule = () => {
      if (cancelled) return;
      if (Date.now() >= deadline) {
        setRefreshWarning(
          'Automatyczne odświeżanie zatrzymano po 45 minutach. Odśwież stronę, aby ponownie sprawdzić proces.',
        );
        return;
      }
      timerId = window.setTimeout(() => void poll(), RUN_POLL_INTERVAL_MS);
    };

    const poll = async () => {
      try {
        const result = await getImageSelectionWithTimeout(api, activeRunId);
        if (cancelled) return;
        if (result.error !== undefined || result.data === undefined) {
          consecutiveFailures += 1;
        } else {
          consecutiveFailures = 0;
          setRefreshWarning('');
          setRun(result.data);
          if (!isPollableRunStatus(result.data.job.status)) return;
        }
      } catch {
        if (cancelled) return;
        consecutiveFailures += 1;
      }

      if (consecutiveFailures >= RUN_POLL_ERROR_THRESHOLD) {
        setRefreshWarning(
          'Nie udało się odświeżyć procesu. Panel spróbuje ponownie automatycznie.',
        );
      }
      schedule();
    };

    schedule();
    return () => {
      cancelled = true;
      if (timerId !== null) window.clearTimeout(timerId);
    };
  }, [activeRunId, activeRunStatus, api, gameId]);

  useEffect(() => {
    if (run === null) return;
    let cancelled = false;
    queueMicrotask(async () => {
      try {
        const groups = await loadManualImageSelectionGroups(api, run.id);
        if (!cancelled) setManualGroups(groups);
      } catch {
        if (!cancelled) {
          setError('Nie udało się odczytać wyjątków ręcznej selekcji.');
        }
      }
    });
    return () => {
      cancelled = true;
    };
  }, [api, run]);

  async function startUpload(files: readonly File[], activeResume = resume) {
    if (busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    const result = await uploadPhotoSelectionFolder(api, gameId, files, {
      onProgress: setProgress,
      resume: activeResume,
    });
    if (!result.ok) {
      setError(result.error);
      setResume(result.resume);
      setBusy(false);
      return;
    }
    setResume(null);
    setRun(result.created.run);
    setProgress(EMPTY_PROGRESS);
    window.localStorage.setItem(storageKey(gameId), result.created.run.id);
    setNotice(
      result.created.created
        ? 'Folder zapisany. Proces selekcji jest gotowy do uruchomienia przez worker.'
        : 'Ten sam folder był już zapisany. Przywrócono istniejący proces.',
    );
    setBusy(false);
  }

  async function chooseFolder(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const selectedFiles = Array.from(input.files ?? []).filter((file) =>
      /\.jpe?g$/i.test(file.name),
    );
    input.value = '';
    if (selectedFiles.length === 0) {
      setError('Wybrany folder nie zawiera plików JPEG.');
      return;
    }
    if (selectedFiles.length > 30_000) {
      setError(
        'Selekcja zdjęć obsługuje maksymalnie 30 000 plików JPEG na run.',
      );
      return;
    }
    await startUpload(selectedFiles, null);
  }

  async function cancelUpload() {
    if (resume === null || busy) return;
    setBusy(true);
    try {
      await cancelPhotoSelectionUpload(api, resume);
      setResume(null);
      setProgress(EMPTY_PROGRESS);
      setError('');
      setNotice('Niedokończony staging został usunięty.');
    } catch {
      setError('Nie udało się anulować niedokończonego uploadu.');
    } finally {
      setBusy(false);
    }
  }

  async function handoffToImport() {
    if (run === null || run.outputManifestSha256 === null || busy) return;
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await api.handoffImageSelection(run.id);
      if (result.error !== undefined || result.data === undefined) {
        setError('Nie udało się zweryfikować paczki wybranych zdjęć.');
        return;
      }
      onOpenImports(result.data);
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setBusy(false);
    }
  }

  async function openManualReview() {
    if (run === null || manualLoading) return;
    setManualLoading(true);
    setError('');
    try {
      const groups = await loadManualImageSelectionGroups(api, run.id);
      setManualGroups(groups);
      if (groups.length === 0) {
        setNotice('Ten run nie ma grup wymagających ręcznej decyzji.');
      } else {
        setManualOpen(true);
      }
    } catch {
      setError('Nie udało się odczytać wyjątków ręcznej selekcji.');
    } finally {
      setManualLoading(false);
    }
  }

  function updateManualGroup(updated: ImageSelectionGroupResponse) {
    setManualGroups((groups) =>
      groups.map((group) => (group.id === updated.id ? updated : group)),
    );
  }

  const percentage =
    progress.totalBytes === 0
      ? 0
      : Math.min(100, (progress.uploadedBytes / progress.totalBytes) * 100);

  return (
    <section
      className="imageSelectionWorkspace"
      aria-labelledby="image-selection-title"
    >
      <header className="imageSelectionHeader">
        <div>
          <p className="eyebrow">Aktywna gra · {gameName}</p>
          <h1 id="image-selection-title">Selekcja zdjęć</h1>
          <p>
            Wybierz duży folder. Moduł zapisze bezpieczny staging bez
            uruchamiania pełnego pipeline&apos;u layoutów.
          </p>
        </div>
        <input
          accept=".jpg,.jpeg,image/jpeg"
          hidden
          multiple
          onChange={(event) => void chooseFolder(event)}
          ref={(node) => {
            folderInputRef.current = node;
            if (node !== null) {
              node.webkitdirectory = true;
              node.setAttribute('webkitdirectory', '');
            }
          }}
          type="file"
        />
        <button
          aria-busy={busy}
          className="primaryButton"
          disabled={busy}
          onClick={() => folderInputRef.current?.click()}
          type="button"
        >
          {busy ? 'Przesyłanie…' : 'Wybierz folder zdjęć'}
        </button>
      </header>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {refreshWarning ? (
        <p className="feedbackBanner" role="status">
          {refreshWarning}
        </p>
      ) : null}
      {notice ? <p className="feedbackBanner">{notice}</p> : null}

      {progress.totalFiles > 0 ? (
        <section className="imageSelectionProgress" aria-label="Postęp uploadu">
          <div>
            <strong>
              {progress.uploadedFiles.toLocaleString('pl-PL')} /{' '}
              {progress.totalFiles.toLocaleString('pl-PL')} plików
            </strong>
            <span>
              {formatBytes(progress.uploadedBytes)} /{' '}
              {formatBytes(progress.totalBytes)}
            </span>
          </div>
          <progress max={100} value={percentage} />
          {resume !== null ? (
            <div className="imageSelectionRecoveryActions">
              <button
                className="primaryButton"
                disabled={busy}
                onClick={() => void startUpload(resume.files, resume)}
                type="button"
              >
                Ponów brakujące pliki
              </button>
              <button
                className="secondaryButton"
                disabled={busy}
                onClick={() => void cancelUpload()}
                type="button"
              >
                Anuluj staging
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {run !== null ? (
        <section
          className="imageSelectionRunCard"
          aria-label="Bieżący proces selekcji"
        >
          <div>
            <p className="eyebrow">Bieżący run</p>
            <h2>
              {run.job.status === 'created'
                ? 'Gotowy do skanowania'
                : run.job.status}
            </h2>
          </div>
          <dl>
            <div>
              <dt>Job</dt>
              <dd>{run.job.id.slice(0, 8)}</dd>
            </div>
            <div>
              <dt>Kolejność</dt>
              <dd>{run.orderingPolicy}</dd>
            </div>
            <div>
              <dt>Manifest</dt>
              <dd>{run.inputManifestSha256.slice(0, 12)}…</dd>
            </div>
          </dl>
          <div className="imageSelectionRecoveryActions">
            <button
              className="secondaryButton"
              disabled={busy || manualLoading}
              onClick={() => void openManualReview()}
              type="button"
            >
              {manualLoading
                ? 'Odczytywanie…'
                : `Uzupełnij wyjątki${manualGroups.length > 0 ? ` (${manualGroups.length})` : ''}`}
            </button>
            <button
              aria-busy={busy}
              className="primaryButton"
              disabled={busy || run.outputManifestSha256 === null}
              onClick={() => void handoffToImport()}
              type="button"
            >
              {busy ? 'Weryfikowanie…' : 'Przekaż do Importu layoutów'}
            </button>
            {run.outputManifestSha256 === null ? (
              <span>
                Akcja będzie dostępna po opublikowaniu kompletnego wyniku.
              </span>
            ) : null}
          </div>
        </section>
      ) : null}
      {manualOpen && run !== null && manualGroups.length > 0 ? (
        <ManualImageSelectionModal
          apiBaseUrl={apiBaseUrl}
          client={api}
          groups={manualGroups}
          onClose={() => setManualOpen(false)}
          onGroupUpdated={updateManualGroup}
          runId={run.id}
        />
      ) : null}
    </section>
  );
}

function storageKey(gameId: string): string {
  return `game-predictor:image-selection-run:${gameId}`;
}

function isPollableRunStatus(status: string): boolean {
  return status === 'created' || status === 'processing';
}

async function getImageSelectionWithTimeout(
  api: ImageSelectionClient,
  runId: string,
) {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(
    () => controller.abort(),
    RUN_POLL_REQUEST_TIMEOUT_MS,
  );
  try {
    return await api.getImageSelection(runId, { signal: controller.signal });
  } finally {
    window.clearTimeout(timeoutId);
  }
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
