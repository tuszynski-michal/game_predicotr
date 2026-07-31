'use client';

import type {
  ImageDatasetCompletenessResponse,
  ImageFolderSelectionResponse,
  ImageImportJobPayload,
  ImageSequenceSourceSelectionResponse,
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
  const [completeness, setCompleteness] =
    useState<ImageDatasetCompletenessResponse | null>(null);
  const [sequenceNumber, setSequenceNumber] = useState('');
  const [sourceSelection, setSourceSelection] =
    useState<ImageSequenceSourceSelectionResponse | null>(null);

  const refreshJobs = useCallback(async () => {
    const [jobsResult, completenessResult] = await Promise.all([
      api.listJobs({
        gameId,
        jobType: 'import',
        limit: 20,
      }),
      api.getImageDatasetCompleteness(gameId),
    ]);
    if (jobsResult.error === undefined && jobsResult.data !== undefined) {
      setJobs(jobsResult.data.filter(isImageImportJob));
    }
    if (
      completenessResult.error === undefined &&
      completenessResult.data !== undefined
    ) {
      setCompleteness(completenessResult.data);
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

  async function inspectSequence() {
    const parsed = Number(sequenceNumber);
    if (!Number.isSafeInteger(parsed) || parsed < 1) {
      setError('Podaj dodatni numer sekwencji.');
      return;
    }
    setBusy(true);
    setError('');
    const result = await api.getImageSequenceSourceSelection(gameId, parsed);
    setBusy(false);
    if (result.error !== undefined || result.data === undefined) {
      setSourceSelection(null);
      setError('Brak zaakceptowanego źródła dla podanej sekwencji.');
      return;
    }
    setSourceSelection(result.data);
  }

  async function chooseSource(reviewItemId: string | null) {
    if (sourceSelection === null || busy) return;
    setBusy(true);
    setError('');
    const result = await api.selectImageSequenceSource(
      gameId,
      sourceSelection.sequenceNumber,
      { reviewItemId, selectedBy: 'local-owner' },
    );
    setBusy(false);
    if (result.error !== undefined || result.data === undefined) {
      setError('Nie udało się zapisać wyboru źródła.');
      return;
    }
    setSourceSelection(result.data);
    await refreshJobs();
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

      {completeness ? (
        <div className="gamesPanel">
          <div className="listHeader">
            <div>
              <p className="eyebrow">Kompletność zaakceptowanych plansz</p>
              <h3>
                {completeness.uniqueSequenceCount.toLocaleString('pl-PL')} /{' '}
                {completeness.expectedLayoutCount.toLocaleString('pl-PL')}
              </h3>
            </div>
            <strong>{completeness.completionPercentage.toFixed(2)}%</strong>
          </div>
          <dl className="diagnosticList">
            <div>
              <dt>Brakujące</dt>
              <dd>{completeness.missingSequenceCount.toLocaleString('pl-PL')}</dd>
            </div>
            <div>
              <dt>Duplikaty numeru</dt>
              <dd>{completeness.duplicateSequenceCount}</dd>
            </div>
            <div>
              <dt>Ręczne wybory źródła</dt>
              <dd>{completeness.manualOverrideCount}</dd>
            </div>
          </dl>
          {completeness.missingSequenceNumbers.length > 0 ? (
            <p>
              Pierwsze luki: {completeness.missingSequenceNumbers.join(', ')}
              {completeness.missingSequenceNumbersTruncated ? '…' : ''}
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="listHeader">
        <div>
          <p className="eyebrow">Źródła tej samej sekwencji</p>
          <p>Sprawdź ranking jakości lub wskaż ręcznie lepsze zdjęcie.</p>
        </div>
      </div>
      <div className="inlineActions">
        <input
          aria-label="Numer sekwencji do sprawdzenia"
          inputMode="numeric"
          min={1}
          onChange={(event) => setSequenceNumber(event.currentTarget.value)}
          placeholder="Numer sekwencji"
          type="number"
          value={sequenceNumber}
        />
        <button disabled={busy} onClick={() => void inspectSequence()} type="button">
          Pokaż źródła
        </button>
        {sourceSelection?.manualOverrideReviewItemId ? (
          <button disabled={busy} onClick={() => void chooseSource(null)} type="button">
            Przywróć wybór automatyczny
          </button>
        ) : null}
      </div>
      {sourceSelection ? (
        <ul className="compactList">
          {sourceSelection.candidates.map((candidate) => (
            <li key={candidate.reviewItemId}>
              <strong>
                #{candidate.automaticRank} · jakość{' '}
                {(candidate.qualityScore * 100).toFixed(1)}%
                {candidate.selected ? ' · wybrane' : ''}
              </strong>
              <span>
                {candidate.width} × {candidate.height} · OCR{' '}
                {(candidate.sequenceConfidence * 100).toFixed(1)}% · plansza{' '}
                {(candidate.boardConfidence * 100).toFixed(1)}%
              </span>
              <small>{candidate.sourceRelativePath}</small>
              {!candidate.selected ? (
                <button
                  disabled={busy}
                  onClick={() => void chooseSource(candidate.reviewItemId)}
                  type="button"
                >
                  Wybierz to źródło
                </button>
              ) : null}
            </li>
          ))}
        </ul>
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
