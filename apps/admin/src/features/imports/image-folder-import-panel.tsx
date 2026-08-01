'use client';

import type {
  ImageDatasetCompletenessResponse,
  ImageFolderSelectionResponse,
  ImageImportJobPayload,
  ImageSequenceSourceSelectionResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';
import {
  type ChangeEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';

import { createConfiguredAdminApiClient } from '@/api/admin-api-client';

import {
  type ImageFolderImportClient,
  createImageFolderImport,
  uploadImageFolder,
} from './image-folder-import-actions';

interface ImageFolderImportPanelProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageFolderImportClient;
  readonly gameId: string;
}

type ImageImportJob = JobResponse & {
  readonly inputPayload: ImageImportJobPayload;
};

type ImportAction =
  | 'choose-folder'
  | 'start-import'
  | 'refresh-status'
  | 'inspect-sequence'
  | 'choose-source';

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
  const [selectionDisplayName, setSelectionDisplayName] = useState('');
  const [jobs, setJobs] = useState<readonly ImageImportJob[]>([]);
  const [activeAction, setActiveAction] = useState<ImportAction | null>(null);
  const [error, setError] = useState('');
  const [feedback, setFeedback] = useState('');
  const [completeness, setCompleteness] =
    useState<ImageDatasetCompletenessResponse | null>(null);
  const [sequenceNumber, setSequenceNumber] = useState('');
  const [sourceSelection, setSourceSelection] =
    useState<ImageSequenceSourceSelectionResponse | null>(null);
  const [uploadProgress, setUploadProgress] = useState<{
    readonly total: number;
    readonly uploaded: number;
  } | null>(null);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const busy = activeAction !== null;

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
      if (!cancelled) {
        void refreshJobs().catch(() => {
          if (!cancelled) {
            setError('Nie udało się pobrać aktualnego statusu importu.');
          }
        });
      }
    });
    return () => {
      cancelled = true;
    };
  }, [refreshJobs]);

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
    if (busy) return;
    setActiveAction('choose-folder');
    setUploadProgress({ total: selectedFiles.length, uploaded: 0 });
    setError('');
    setFeedback('');
    try {
      const result = await uploadImageFolder(
        api,
        selectedFiles,
        (uploaded, total) => setUploadProgress({ total, uploaded }),
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setSelection(result.selection);
      setSelectionDisplayName(result.displayName);
      setFeedback(
        `Folder zweryfikowany: ${result.selection.supportedFileCount} plików JPEG.`,
      );
    } catch {
      setError('Nie udało się otworzyć wyboru folderu. Spróbuj ponownie.');
    } finally {
      setUploadProgress(null);
      setActiveAction(null);
    }
  }

  async function startImport() {
    if (busy || selection?.selectionToken == null) return;
    setActiveAction('start-import');
    setError('');
    setFeedback('');
    try {
      const result = await createImageFolderImport(
        api,
        gameId,
        selection.selectionToken,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setSelection(null);
      setSelectionDisplayName('');
      const imageJob = result.job;
      if (isImageImportJob(imageJob)) {
        setJobs((current) => [imageJob, ...current]);
      }
      setFeedback(
        `Import ${result.job.id} utworzony. Postęp jest dostępny w zakładce Joby.`,
      );
    } catch {
      setError('Nie udało się rozpocząć importu. Spróbuj ponownie.');
    } finally {
      setActiveAction(null);
    }
  }

  async function refreshStatus() {
    if (busy) return;
    setActiveAction('refresh-status');
    setError('');
    try {
      await refreshJobs();
      setFeedback('Status importu został odświeżony.');
    } catch {
      setError('Nie udało się odświeżyć statusu importu.');
    } finally {
      setActiveAction(null);
    }
  }

  async function inspectSequence() {
    const parsed = Number(sequenceNumber);
    if (!Number.isSafeInteger(parsed) || parsed < 1) {
      setError('Podaj dodatni numer sekwencji.');
      return;
    }
    if (busy) return;
    setActiveAction('inspect-sequence');
    setError('');
    try {
      const result = await api.getImageSequenceSourceSelection(gameId, parsed);
      if (result.error !== undefined || result.data === undefined) {
        setSourceSelection(null);
        setError('Brak zaakceptowanego źródła dla podanej sekwencji.');
        return;
      }
      setSourceSelection(result.data);
    } catch {
      setSourceSelection(null);
      setError('Nie udało się pobrać źródeł dla podanej sekwencji.');
    } finally {
      setActiveAction(null);
    }
  }

  async function chooseSource(reviewItemId: string | null) {
    if (sourceSelection === null || busy) return;
    setActiveAction('choose-source');
    setError('');
    try {
      const result = await api.selectImageSequenceSource(
        gameId,
        sourceSelection.sequenceNumber,
        { reviewItemId, selectedBy: 'local-owner' },
      );
      if (result.error !== undefined || result.data === undefined) {
        setError('Nie udało się zapisać wyboru źródła.');
        return;
      }
      setSourceSelection(result.data);
      await refreshJobs();
    } catch {
      setError('Nie udało się zapisać wyboru źródła.');
    } finally {
      setActiveAction(null);
    }
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
            Wybierz folder, rozpocznij import i kontroluj kompletność layoutów
            aktywnej gry.
          </p>
        </div>
      </div>

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}

      <div className="importActionToolbar">
        <div className="importActionButtons">
          <button
            aria-busy={activeAction === 'start-import'}
            className="primaryButton"
            disabled={busy || selection?.selectionToken == null}
            onClick={() => void startImport()}
            type="button"
          >
            {activeAction === 'start-import'
              ? 'Uruchamianie…'
              : 'Rozpocznij import'}
          </button>
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
            aria-busy={activeAction === 'choose-folder'}
            className="secondaryButton"
            disabled={busy}
            onClick={() => folderInputRef.current?.click()}
            type="button"
          >
            {activeAction === 'choose-folder'
              ? `Przesyłanie ${uploadProgress?.uploaded ?? 0}/${uploadProgress?.total ?? 0}…`
              : 'Wybierz folder'}
          </button>
          <button
            aria-busy={activeAction === 'refresh-status'}
            className="secondaryButton"
            disabled={busy}
            onClick={() => void refreshStatus()}
            type="button"
          >
            {activeAction === 'refresh-status'
              ? 'Odświeżanie…'
              : 'Odśwież status'}
          </button>
        </div>
        <div className="importActionHelp">
          <button
            aria-describedby="image-import-actions-help"
            aria-label="Pomoc dotycząca akcji importu"
            className="importHelpTrigger"
            type="button"
          >
            ?
          </button>
          <div
            className="importHelpTooltip"
            id="image-import-actions-help"
            role="tooltip"
          >
            <strong>Co robią te akcje?</strong>
            <dl>
              <div>
                <dt>Rozpocznij import</dt>
                <dd>Tworzy job po poprawnym wyborze folderu.</dd>
              </div>
              <div>
                <dt>Wybierz folder</dt>
                <dd>
                  Otwiera natywne okno przeglądarki i przesyła JPEG-i do
                  lokalnego API.
                </dd>
              </div>
              <div>
                <dt>Odśwież status</dt>
                <dd>Aktualizuje kompletność i listę ostatnich importów.</dd>
              </div>
            </dl>
          </div>
        </div>
      </div>

      {selection?.status === 'selected' ? (
        <dl className="diagnosticList">
          <div>
            <dt>Wybrany folder</dt>
            <dd>{selectionDisplayName}</dd>
          </div>
          <div>
            <dt>Obsługiwane pliki</dt>
            <dd>{selection.supportedFileCount}</dd>
          </div>
        </dl>
      ) : null}

      {completeness ? (
        <section
          aria-labelledby="image-import-completeness-title"
          className="importCompletenessCard"
        >
          <header className="importCompletenessHeader">
            <div>
              <p className="eyebrow">Kompletność zaakceptowanych plansz</p>
              <h3 id="image-import-completeness-title">
                {completeness.uniqueSequenceCount.toLocaleString('pl-PL')} /{' '}
                {completeness.expectedLayoutCount.toLocaleString('pl-PL')}
              </h3>
            </div>
            <strong className="importCompletionBadge">
              {completeness.completionPercentage.toFixed(2)}%
            </strong>
          </header>
          <dl className="importMetrics">
            <div className="importMetric">
              <dt>Brakujące</dt>
              <dd>
                {completeness.missingSequenceCount.toLocaleString('pl-PL')}
              </dd>
            </div>
            <div className="importMetric">
              <dt>Duplikaty numeru</dt>
              <dd>{completeness.duplicateSequenceCount}</dd>
            </div>
            <div className="importMetric">
              <dt>Ręczne wybory źródła</dt>
              <dd>{completeness.manualOverrideCount}</dd>
            </div>
          </dl>
          {completeness.missingSequenceNumbers.length > 0 ? (
            <details className="importMissingSequences">
              <summary>
                Pierwsze luki ({completeness.missingSequenceNumbers.length}
                {completeness.missingSequenceNumbersTruncated ? '+' : ''})
              </summary>
              <div className="importMissingSequenceChips">
                {completeness.missingSequenceNumbers.map((missingNumber) => (
                  <span key={missingNumber}>{missingNumber}</span>
                ))}
              </div>
            </details>
          ) : null}
        </section>
      ) : null}

      <section className="importSourceInspector">
        <header className="importSubsectionHeader">
          <p className="eyebrow">Źródła tej samej sekwencji</p>
          <p>Sprawdź ranking jakości lub wskaż ręcznie lepsze zdjęcie.</p>
        </header>
        <div className="importSourceControls">
          <label>
            <span>Numer sekwencji</span>
            <input
              aria-label="Numer sekwencji do sprawdzenia"
              inputMode="numeric"
              min={1}
              onChange={(event) => setSequenceNumber(event.currentTarget.value)}
              placeholder="np. 29"
              type="number"
              value={sequenceNumber}
            />
          </label>
          <button
            aria-busy={activeAction === 'inspect-sequence'}
            className="secondaryButton"
            disabled={busy}
            onClick={() => void inspectSequence()}
            type="button"
          >
            {activeAction === 'inspect-sequence'
              ? 'Pobieranie…'
              : 'Pokaż źródła'}
          </button>
          {sourceSelection?.manualOverrideReviewItemId ? (
            <button
              aria-busy={activeAction === 'choose-source'}
              className="secondaryButton"
              disabled={busy}
              onClick={() => void chooseSource(null)}
              type="button"
            >
              Przywróć wybór automatyczny
            </button>
          ) : null}
        </div>
        {sourceSelection ? (
          <ul className="importCompactList">
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
                    className="secondaryButton"
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
      </section>

      <section className="importHistorySection">
        <header className="importSubsectionHeader">
          <p className="eyebrow">Ostatnie importy tej gry</p>
          <p>Pełne filtrowanie i diagnostyka pozostają w zakładce Joby.</p>
        </header>
        {jobs.length === 0 ? (
          <p className="importEmptyState">
            Nie utworzono jeszcze importu zdjęć.
          </p>
        ) : (
          <ul className="importCompactList">
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
    </section>
  );
}
