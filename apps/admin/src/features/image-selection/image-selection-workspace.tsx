'use client';

import type { ImageSelectionRunResponse } from '@game-predictor/admin-api-client';
import {
  type ChangeEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  type ImageSelectionClient,
  type ImageSelectionUploadProgress,
  type ResumableImageSelectionUpload,
  cancelPhotoSelectionUpload,
  uploadPhotoSelectionFolder,
} from './image-selection-actions';

interface ImageSelectionWorkspaceProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageSelectionClient;
  readonly gameId: string;
  readonly gameName: string;
}

const EMPTY_PROGRESS: ImageSelectionUploadProgress = {
  totalBytes: 0,
  totalFiles: 0,
  uploadedBytes: 0,
  uploadedFiles: 0,
};

export function ImageSelectionWorkspace({
  apiBaseUrl,
  client,
  gameId,
  gameName,
}: ImageSelectionWorkspaceProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const [progress, setProgress] = useState(EMPTY_PROGRESS);
  const [resume, setResume] = useState<ResumableImageSelectionUpload | null>(
    null,
  );
  const [run, setRun] = useState<ImageSelectionRunResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  useEffect(() => {
    let cancelled = false;
    const runId = window.localStorage.getItem(storageKey(gameId));
    if (runId === null) return () => undefined;
    queueMicrotask(async () => {
      try {
        const result = await api.getImageSelection(runId);
        if (!cancelled && result.error === undefined && result.data !== undefined) {
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
      setError('Selekcja zdjęć obsługuje maksymalnie 30 000 plików JPEG na run.');
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

  const percentage =
    progress.totalBytes === 0
      ? 0
      : Math.min(100, (progress.uploadedBytes / progress.totalBytes) * 100);

  return (
    <section className="imageSelectionWorkspace" aria-labelledby="image-selection-title">
      <header className="imageSelectionHeader">
        <div>
          <p className="eyebrow">Aktywna gra · {gameName}</p>
          <h1 id="image-selection-title">Selekcja zdjęć</h1>
          <p>
            Wybierz duży folder. Moduł zapisze bezpieczny staging bez uruchamiania
            pełnego pipeline&apos;u layoutów.
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
      {notice ? <p className="feedbackBanner">{notice}</p> : null}

      {progress.totalFiles > 0 ? (
        <section className="imageSelectionProgress" aria-label="Postęp uploadu">
          <div>
            <strong>
              {progress.uploadedFiles.toLocaleString('pl-PL')} /{' '}
              {progress.totalFiles.toLocaleString('pl-PL')} plików
            </strong>
            <span>
              {formatBytes(progress.uploadedBytes)} / {formatBytes(progress.totalBytes)}
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
        <section className="imageSelectionRunCard" aria-label="Bieżący proces selekcji">
          <div>
            <p className="eyebrow">Bieżący run</p>
            <h2>{run.job.status === 'created' ? 'Gotowy do skanowania' : run.job.status}</h2>
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
        </section>
      ) : null}
    </section>
  );
}

function storageKey(gameId: string): string {
  return `game-predictor:image-selection-run:${gameId}`;
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(value / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}
