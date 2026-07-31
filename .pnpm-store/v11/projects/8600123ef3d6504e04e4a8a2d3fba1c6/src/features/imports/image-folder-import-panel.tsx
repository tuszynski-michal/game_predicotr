'use client';

import type {
  ImageFolderSelectionResponse,
  ImageImportJobPayload,
  JobResponse,
} from '@game-predictor/admin-api-client';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  type ImageFolderImportClient,
  createImageFolderImport,
  selectImageFolder,
} from './image-folder-import-actions';

interface ImageFolderImportPanelProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageFolderImportClient;
  readonly gameId: string;
}

type ImageImportJob = JobResponse & {
  readonly inputPayload: ImageImportJobPayload;
};

function isImageImportJob(job: JobResponse): job is ImageImportJob {
  return (
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'image_directory'
  );
}

export function ImageFolderImportPanel({
  apiBaseUrl,
  client,
  gameId,
}: ImageFolderImportPanelProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [selection, setSelection] =
    useState<ImageFolderSelectionResponse | null>(null);
  const [jobs, setJobs] = useState<readonly ImageImportJob[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');

  const refreshJobs = useCallback(async () => {
    const result = await api.listJobs({
      gameId,
      jobType: 'import',
      limit: 20,
    });
    if (result.error === undefined && result.data !== undefined) {
      setJobs(result.data.filter(isImageImportJob));
    }
  }, [api, gameId]);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      if (!cancelled) void refreshJobs();
    });
    return () => {
      cancelled = true;
    };
  }, [refreshJobs]);

  async function chooseFolder() {
    if (busy) return;
    setBusy(true);
    setError('');
    setFeedback('');
    const result = await selectImageFolder(api);
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    if (result.selection.status === 'cancelled') {
      setSelection(null);
      setFeedback('Anulowano wybór folderu. Nie utworzono importu.');
      return;
    }
    setSelection(result.selection);
    setFeedback(
      `Folder zweryfikowany: ${result.selection.supportedFileCount} plików JPEG.`,
    );
  }

  async function startImport() {
    if (busy || selection?.selectionToken == null) return;
    setBusy(true);
    setError('');
    setFeedback('');
    const result = await createImageFolderImport(
      api,
      gameId,
      selection.selectionToken,
    );
    setBusy(false);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setSelection(null);
    const imageJob = result.job;
    if (isImageImportJob(imageJob)) {
      setJobs((current) => [imageJob, ...current]);
    }
    setFeedback(
      `Import ${result.job.id} utworzony. Uruchom worker i obserwuj zakładkę Joby.`,
    );
  }

  return (
    <section
      className="editorPanel importComposer"
      aria-labelledby="image-import-title"
    >
      <div className="editorHeader">
        <div>
          <p className="eyebrow">Źródło zdjęć</p>
          <h2 id="image-import-title">Import layoutów z folderu</h2>
          <p>
            Wybierz lokalny folder JPEG. Oryginały zostaną skopiowane do
            kontrolowanego storage, a import będzie można bezpiecznie wznowić.
          </p>
        </div>
      </div>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}

      <div className="inlineActions">
        <button
          disabled={busy}
          onClick={() => void chooseFolder()}
          type="button"
        >
          {busy ? 'Oczekiwanie…' : 'Wybierz folder'}
        </button>
        <button
          className="primaryButton"
          disabled={busy || selection?.selectionToken == null}
          onClick={() => void startImport()}
          type="button"
        >
          Rozpocznij import
        </button>
        <button
          disabled={busy}
          onClick={() => void refreshJobs()}
          type="button"
        >
          Odśwież status
        </button>
      </div>

      {selection?.status === 'selected' ? (
        <dl className="diagnosticList">
          <div>
            <dt>Wybrany folder</dt>
            <dd>{selection.path}</dd>
          </div>
          <div>
            <dt>Obsługiwane pliki</dt>
            <dd>{selection.supportedFileCount}</dd>
          </div>
        </dl>
      ) : null}

      <div className="listHeader">
        <div>
          <p className="eyebrow">Ostatnie importy tej gry</p>
          <p>Pełne filtrowanie i diagnostyka pozostają w zakładce Joby.</p>
        </div>
      </div>
      {jobs.length === 0 ? (
        <p className="emptyState">Nie utworzono jeszcze importu zdjęć.</p>
      ) : (
        <ul className="compactList">
          {jobs.slice(0, 5).map((job) => (
            <li key={job.id}>
              <strong>
                {job.inputPayload.sourceDisplayName ?? 'Import obrazów'}
              </strong>
              <span>
                {job.status} · {job.progress.current}/
                {job.progress.total ?? '—'}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
