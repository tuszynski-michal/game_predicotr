'use client';

import type {
  CuratedImageImportJobPayload,
  CuratedImageImportSourceResponse,
  BrowserImageImportPreflightResponse,
  JobResponse,
  BrowserReadySelectionResponse,
  ImageDatasetCompletenessResponse,
  ImageFolderSelectionResponse,
  ImageSelectionHandoffResponse,
  ImageImportJobPayload,
  ImageSequenceSourceSelectionResponse,
  ImageImportEnginePolicyResponse,
  ManagedImageReprocessJobPayload,
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
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
  jobMatchesBoardCellProcessingMode,
} from './board-cell-processing-mode';
import { BoardCellProcessingModePicker } from './board-cell-processing-mode-picker';
import {
  type ImageFolderImportClient,
  createImageFolderImport,
  listReadyBrowserImageSelections,
  previewReadyBrowserImageImport,
  reprocessImageFolderImport,
  startBrowserPageGeometryPreflight,
  startReadyBrowserImageImport,
  uploadImageFolder,
} from './image-folder-import-actions';
import { sortReadyBoardImports } from './image-folder-import-state';
import { PageGeometryCorrectionPanel } from './page-geometry-correction-panel';

interface ImageFolderImportPanelProps {
  readonly apiBaseUrl: string;
  readonly client?: ImageFolderImportClient;
  readonly gameId: string;
  readonly initialHandoff?: ImageSelectionHandoffResponse | null;
  readonly onHandoffConsumed?: () => void;
}

type ImageImportJob = JobResponse & {
  readonly inputPayload:
    | ImageImportJobPayload
    | CuratedImageImportJobPayload
    | ManagedImageReprocessJobPayload;
};

type ImportAction =
  | 'choose-folder'
  | 'list-ready'
  | 'preflight'
  | 'geometry-preflight'
  | 'start-ready'
  | 'delete-ready'
  | 'reprocess-import'
  | 'start-import'
  | 'refresh-status'
  | 'inspect-sequence'
  | 'choose-source'
  | 'register-curated'
  | 'start-curated'
  | 'engine-policy';

function isImageImportJob(job: JobResponse): job is ImageImportJob {
  return (
    'importKind' in job.inputPayload &&
    job.inputPayload.importKind === 'image_directory'
  );
}

function curatedBatchTiming(job: JobResponse, imageCount: number) {
  if (job.startedAt === null || job.finishedAt === null || imageCount < 1) {
    return null;
  }
  const seconds = Math.max(
    0,
    (Date.parse(job.finishedAt) - Date.parse(job.startedAt)) / 1000,
  );
  if (!Number.isFinite(seconds)) return null;
  return {
    seconds,
    secondsPerImage: seconds / imageCount,
    imagesPerMinute: seconds === 0 ? 0 : (imageCount * 60) / seconds,
  };
}

function imageImportOutcome(job: ImageImportJob) {
  const totalWork = job.progress.total;
  if (totalWork === null || totalWork < 2 || totalWork % 2 !== 0) return null;
  const sourceCount = totalWork / 2;
  return {
    failedImages: job.progress.failed,
    pipelineImages: Math.max(
      0,
      Math.min(sourceCount, job.progress.current - sourceCount),
    ),
    reviewBoards: job.progress.review,
    sourceCount,
    succeededImages: Math.max(0, job.progress.succeeded - sourceCount),
  };
}

export function ImageFolderImportPanel({
  apiBaseUrl,
  client,
  gameId,
  initialHandoff = null,
  onHandoffConsumed,
}: ImageFolderImportPanelProps) {
  const api = useMemo(
    () => client ?? createConfiguredAdminApiClient(apiBaseUrl),
    [apiBaseUrl, client],
  );
  const [selection, setSelection] =
    useState<ImageFolderSelectionResponse | null>(null);
  const [selectionDisplayName, setSelectionDisplayName] = useState('');
  const [readySelections, setReadySelections] = useState<
    readonly BrowserReadySelectionResponse[]
  >([]);
  const [readyUploadId, setReadyUploadId] = useState<string | null>(null);
  const [preflight, setPreflight] =
    useState<BrowserImageImportPreflightResponse | null>(null);
  const [geometryPreflightJob, setGeometryPreflightJob] =
    useState<JobResponse | null>(null);
  const [enginePolicy, setEnginePolicy] =
    useState<ImageImportEnginePolicyResponse | null>(null);
  const boardCellProcessingMode = enginePolicy?.policy ?? 'verified_v19';
  const [curatedSources, setCuratedSources] = useState<
    readonly CuratedImageImportSourceResponse[]
  >([]);
  const [curatedBatchSize, setCuratedBatchSize] = useState('10');
  const registeredHandoffRef = useRef<string | null>(null);
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
  const geometryManifestChecksum =
    geometryPreflightJob?.progress.pageGeometryPreflight
      ?.geometryManifestChecksumSha256 ?? null;
  const refreshJobs = useCallback(async () => {
    const [
      jobsResult,
      completenessResult,
      curatedResult,
      readyResult,
      policyResult,
    ] = await Promise.all([
      api.listJobs({
        gameId,
        jobType: 'import',
        limit: 20,
      }),
      api.getImageDatasetCompleteness(gameId),
      api.listCuratedImageImportSources(gameId),
      listReadyBrowserImageSelections(api),
      api.getImageImportEnginePolicy(gameId),
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
    if (curatedResult.error === undefined && curatedResult.data !== undefined) {
      setCuratedSources(curatedResult.data);
    }
    if (readyResult.ok) {
      const gameReady = readyResult.data.filter(
        (item) => item.gameId === null || item.gameId === gameId,
      );
      setReadySelections(sortReadyBoardImports(gameReady));
      setReadyUploadId((current) => {
        if (
          current !== null &&
          !gameReady.some((item) => item.uploadId === current)
        ) {
          setPreflight(null);
          setGeometryPreflightJob(null);
          return null;
        }
        return current;
      });
    }
    if (policyResult.error === undefined && policyResult.data !== undefined) {
      setEnginePolicy(policyResult.data);
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

  const geometryPreflightJobId = geometryPreflightJob?.id;

  useEffect(() => {
    if (geometryPreflightJobId === undefined) return;
    let cancelled = false;
    const refreshGeometry = async () => {
      const result = await api.getJob(geometryPreflightJobId);
      if (
        !cancelled &&
        result.error === undefined &&
        result.data !== undefined
      ) {
        setGeometryPreflightJob(result.data);
      }
    };
    void refreshGeometry();
    const timer = window.setInterval(() => void refreshGeometry(), 3_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, geometryPreflightJobId]);

  useEffect(() => {
    if (
      initialHandoff === null ||
      initialHandoff.gameId !== gameId ||
      registeredHandoffRef.current === initialHandoff.runId
    ) {
      return;
    }
    registeredHandoffRef.current = initialHandoff.runId;
    setActiveAction('register-curated');
    setError('');
    void api
      .registerCuratedImageImportSource({
        gameId,
        imageSelectionRunId: initialHandoff.runId,
      })
      .then((result) => {
        if (result.error !== undefined || result.data === undefined) {
          setError(
            apiErrorMessage(
              result.error,
              'Nie udało się przygotować paczki do importu partiami.',
            ),
          );
          registeredHandoffRef.current = null;
          return;
        }
        const source = result.data;
        setCuratedSources((current) => [
          source,
          ...current.filter((item) => item.id !== source.id),
        ]);
        setFeedback(
          `Paczka ma ${source.totalEntries.toLocaleString('pl-PL')} zdjęć. Wybierz liczbę kolejnych zdjęć do przetworzenia.`,
        );
        onHandoffConsumed?.();
      })
      .catch(() => {
        registeredHandoffRef.current = null;
        setError('Nie udało się przygotować paczki do importu partiami.');
      })
      .finally(() => setActiveAction(null));
  }, [api, gameId, initialHandoff, onHandoffConsumed]);

  async function chooseFolder(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    if (enginePolicy === null) {
      input.value = '';
      setError('Poczekaj na wczytanie ustawienia silnika tej gry.');
      return;
    }
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
        gameId,
        (uploaded, total) => setUploadProgress({ total, uploaded }),
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setSelection(result.selection);
      setSelectionDisplayName(result.displayName);
      setReadyUploadId(result.uploadId);
      setPreflight(null);
      setGeometryPreflightJob(null);
      setFeedback(
        `Folder przesłany: ${result.selection.supportedFileCount} plików JPEG. Przygotowuję raport przed importem.`,
      );
      const preflightResult = await previewReadyBrowserImageImport(
        api,
        result.uploadId,
        gameId,
      );
      if (!preflightResult.ok) {
        setError(preflightResult.error);
        return;
      }
      setPreflight(preflightResult.data);
      if (preflightResult.data.geometryPreflightRequired) {
        const geometryResult = await startBrowserPageGeometryPreflight(
          api,
          result.uploadId,
          gameId,
        );
        if (!geometryResult.ok) {
          setError(geometryResult.error);
          return;
        }
        setGeometryPreflightJob(geometryResult.data.job);
      } else {
        setGeometryPreflightJob(null);
        setFeedback(
          'Raport jest gotowy. Nowy silnik rozpocznie bez historycznego profilu siatki i zapisze wyniki w trybie shadow.',
        );
      }
      const readyResult = await listReadyBrowserImageSelections(api);
      if (readyResult.ok) {
        setReadySelections(
          readyResult.data.filter(
            (item) => item.gameId === null || item.gameId === gameId,
          ),
        );
      }
    } catch {
      setError('Nie udało się otworzyć wyboru folderu. Spróbuj ponownie.');
    } finally {
      setUploadProgress(null);
      setActiveAction(null);
    }
  }

  async function prepareReadyImport(uploadId: string) {
    if (busy) return;
    setActiveAction('preflight');
    setError('');
    setFeedback('Sprawdzanie gotowego stagingu i decyzji kanonicznych…');
    try {
      const result = await previewReadyBrowserImageImport(
        api,
        uploadId,
        gameId,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setReadyUploadId(uploadId);
      setPreflight(result.data);
      if (result.data.geometryPreflightRequired) {
        const geometryResult = await startBrowserPageGeometryPreflight(
          api,
          uploadId,
          gameId,
        );
        if (!geometryResult.ok) {
          setError(geometryResult.error);
          return;
        }
        setGeometryPreflightJob(geometryResult.data.job);
        setFeedback(
          geometryResult.data.created
            ? 'Raport jest gotowy. Automatyczne przygotowanie geometrii oczekuje na worker.'
            : 'Raport jest gotowy. Przywrócono istniejący preflight geometrii.',
        );
      } else {
        setGeometryPreflightJob(null);
        setFeedback(
          'Raport jest gotowy. Nowy silnik rozpocznie bez historycznego profilu siatki i zapisze wyniki w trybie shadow.',
        );
      }
    } catch {
      setError('Nie udało się przygotować raportu przed importem plansz.');
    } finally {
      setActiveAction(null);
    }
  }

  async function startReadyImport() {
    if (
      busy ||
      readyUploadId === null ||
      preflight === null ||
      (preflight.geometryPreflightRequired &&
        (geometryPreflightJob?.status !== 'completed' ||
          geometryManifestChecksum === null))
    ) {
      return;
    }
    setActiveAction('start-ready');
    setError('');
    setFeedback('Ponowna weryfikacja raportu i tworzenie joba…');
    try {
      const result = await startReadyBrowserImageImport(
        api,
        readyUploadId,
        gameId,
        preflight.manifestChecksumSha256,
        preflight.preflightChecksumSha256,
        geometryPreflightJob?.id,
        geometryManifestChecksum ?? undefined,
        boardCellProcessingMode,
        preflight.imageEnginePolicyRevision,
        preflight.symbolModelInferenceFingerprint,
        preflight.gridProfileInferenceFingerprint,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      const imageJob = result.data.job;
      if (isImageImportJob(imageJob)) {
        if (
          !jobMatchesBoardCellProcessingMode(imageJob, boardCellProcessingMode)
        ) {
          setError(
            'API zwróciło import z innym snapshotem cięcia siatki niż wybrany. Odśwież raport przed ponowieniem.',
          );
          await refreshJobs();
          return;
        }
        setJobs((current) => [
          imageJob,
          ...current.filter((item) => item.id !== imageJob.id),
        ]);
      }
      setFeedback(
        result.data.created
          ? `Import ${imageJob.id} utworzony w trybie ${boardCellProcessingModeLabel(boardCellProcessingMode)} — oczekuje na worker.`
          : `Import ${imageJob.id} już istnieje w trybie ${boardCellProcessingModeLabel(boardCellProcessingMode)}. Nie utworzono drugiego joba.`,
      );
      setSelection(null);
      setSelectionDisplayName('');
      setPreflight(null);
      setGeometryPreflightJob(null);
      await refreshJobs();
    } catch {
      setError('Nie udało się utworzyć importu plansz.');
    } finally {
      setActiveAction(null);
    }
  }

  async function changeEnginePolicy(
    targetPolicy: 'verified_v19' | 'structured_shadow',
  ) {
    if (busy || enginePolicy === null || targetPolicy === enginePolicy.policy)
      return;
    setActiveAction('engine-policy');
    setError('');
    try {
      const preview = await api.previewImageImportEnginePolicy(gameId, {
        targetPolicy,
      });
      if (preview.error !== undefined || preview.data === undefined) {
        setError(
          apiErrorMessage(
            preview.error,
            'Nie udało się przygotować zmiany silnika.',
          ),
        );
        return;
      }
      const result = await api.updateImageImportEnginePolicy(gameId, {
        targetPolicy,
        expectedRevision: preview.data.current.revision,
        previewToken: preview.data.previewToken,
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się zapisać silnika gry.'),
        );
        return;
      }
      setEnginePolicy(result.data);
      setPreflight(null);
      setGeometryPreflightJob(null);
      if (readyUploadId !== null) {
        const refreshed = await previewReadyBrowserImageImport(
          api,
          readyUploadId,
          gameId,
        );
        if (!refreshed.ok) {
          setError(refreshed.error);
          return;
        }
        if (
          refreshed.data.imageEnginePolicy !== result.data.policy ||
          refreshed.data.imageEnginePolicyRevision !== result.data.revision
        ) {
          setError(
            'Raport nie odpowiada zapisanemu ustawieniu silnika. Odśwież status i spróbuj ponownie.',
          );
          return;
        }
        setPreflight(refreshed.data);
        setFeedback(
          result.data.policy === 'structured_shadow'
            ? 'Ustawienie zapisano. Raport stagingu odświeżono — cold-start nie wymaga historycznego profilu siatki.'
            : 'Ustawienie zapisano. Raport stagingu odświeżono — przygotuj wymaganą geometrię stron.',
        );
        return;
      }
      setFeedback(
        'Ustawienie zapisano. Będzie użyte przez następny raport i import tej gry.',
      );
    } catch {
      setError('Połączenie z lokalnym Admin API zostało przerwane.');
    } finally {
      setActiveAction(null);
    }
  }

  async function startGeometryPreflight() {
    if (
      busy ||
      readyUploadId === null ||
      preflight === null ||
      !preflight.geometryPreflightRequired
    ) {
      return;
    }
    setActiveAction('geometry-preflight');
    setError('');
    setFeedback('Tworzę job preflightu pełnej geometrii 3×3…');
    try {
      const result = await startBrowserPageGeometryPreflight(
        api,
        readyUploadId,
        gameId,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setGeometryPreflightJob(result.data.job);
      setFeedback(
        result.data.created
          ? `Preflight geometrii ${result.data.job.id} utworzony — oczekuje na worker.`
          : `Preflight geometrii ${result.data.job.id} już istnieje.`,
      );
    } catch {
      setError('Nie udało się utworzyć preflightu geometrii stron.');
    } finally {
      setActiveAction(null);
    }
  }

  async function rerunGeometryPreflightAfterCorrection() {
    setGeometryPreflightJob(null);
    await startGeometryPreflight();
  }

  async function deleteReadyStaging(uploadId: string) {
    if (
      busy ||
      !window.confirm('Usunąć nieużywany staging i zwolnić miejsce?')
    ) {
      return;
    }
    setActiveAction('delete-ready');
    setError('');
    try {
      const result = await api.cancelBrowserImageSelection(uploadId);
      if (result.error !== undefined) {
        setError(
          apiErrorMessage(result.error, 'Nie udało się usunąć stagingu.'),
        );
        return;
      }
      setReadySelections((current) =>
        current.filter((item) => item.uploadId !== uploadId),
      );
      if (readyUploadId === uploadId) {
        setReadyUploadId(null);
        setPreflight(null);
        setGeometryPreflightJob(null);
      }
      setFeedback('Nieużywany staging został usunięty.');
    } catch {
      setError('Nie udało się usunąć stagingu.');
    } finally {
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
      onHandoffConsumed?.();
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

  async function startCuratedBatch(source: CuratedImageImportSourceResponse) {
    const requested = Number(curatedBatchSize);
    if (!Number.isSafeInteger(requested) || requested < 1) {
      setError('Podaj dodatnią liczbę zdjęć w partii.');
      return;
    }
    if (busy || source.remainingEntries < 1) return;
    setActiveAction('start-curated');
    setError('');
    setFeedback('');
    try {
      const result = await api.createNextCuratedImageImportBatch(source.id, {
        imageCount: Math.min(requested, source.remainingEntries),
      });
      if (result.error !== undefined || result.data === undefined) {
        setError(
          apiErrorMessage(
            result.error,
            'Nie udało się uruchomić kolejnej partii zdjęć.',
          ),
        );
        return;
      }
      const updated = result.data;
      setCuratedSources((current) =>
        current.map((item) => (item.id === updated.id ? updated : item)),
      );
      const batch = updated.batches.at(-1);
      if (batch !== undefined && isImageImportJob(batch.job)) {
        const imageJob = batch.job;
        setJobs((current) => [
          imageJob,
          ...current.filter((item) => item.id !== imageJob.id),
        ]);
      }
      setFeedback(
        batch === undefined
          ? 'Kolejna partia została uruchomiona.'
          : `Uruchomiono partię ${batch.batchNumber}: zdjęcia ${batch.startIndex + 1}–${batch.endIndex}.`,
      );
    } catch {
      setError('Nie udało się uruchomić kolejnej partii zdjęć.');
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

  async function reprocessImport(sourceJob: ImageImportJob) {
    if (busy) return;
    setActiveAction('reprocess-import');
    setError('');
    setFeedback('');
    try {
      const result = await reprocessImageFolderImport(api, sourceJob.id);
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (isImageImportJob(result.job)) {
        const imageJob = result.job;
        setJobs((current) => [
          imageJob,
          ...current.filter((item) => item.id !== imageJob.id),
        ]);
      }
      setFeedback(
        'Utworzono nowy job z zachowanych oryginałów. Poprzedni wynik nie został usunięty.',
      );
    } catch {
      setError('Nie udało się ponownie przetworzyć zachowanych oryginałów.');
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
          <h2 id="image-import-title">Import plansz z folderu</h2>
          <p>
            Wybierz folder, rozpocznij import i kontroluj kompletność plansz
            aktywnej gry.
          </p>
        </div>
      </div>

      <BoardCellProcessingModePicker
        disabled={busy || enginePolicy === null}
        mode={boardCellProcessingMode}
        onChange={(mode) => void changeEnginePolicy(mode)}
      />
      {enginePolicy === null ? (
        <p className="mutedText" aria-live="polite">
          Wczytywanie ustawienia silnika tej gry…
        </p>
      ) : null}

      {error ? (
        <p className="feedbackBanner feedbackBannerError" role="alert">
          {error}
        </p>
      ) : null}
      {feedback ? <p className="feedbackBanner">{feedback}</p> : null}

      {activeAction === 'register-curated' ? (
        <p className="feedbackBanner" aria-live="polite">
          Przygotowywanie paczki z Selekcji Zdjęć…
        </p>
      ) : null}

      {curatedSources.map((source) => {
        const latestBatch = source.batches.at(-1);
        const batchBlocked =
          latestBatch !== undefined &&
          !['waiting_for_review', 'completed'].includes(latestBatch.job.status);
        return (
          <section className="curatedImportCard" key={source.id}>
            <header className="importCompletenessHeader">
              <div>
                <p className="eyebrow">Paczka z Selekcji Zdjęć</p>
                <h3>
                  {source.processedEntries.toLocaleString('pl-PL')} /{' '}
                  {source.totalEntries.toLocaleString('pl-PL')} przetworzonych
                </h3>
                <p>
                  Run {source.imageSelectionRunId.slice(0, 8)} · kolejność z
                  manifestu
                </p>
              </div>
              <strong className="importCompletionBadge">
                {source.remainingEntries.toLocaleString('pl-PL')} pozostało
              </strong>
            </header>
            <dl className="curatedImportMetrics">
              <div className="importMetric">
                <dt>Wszystkie zdjęcia</dt>
                <dd>{source.totalEntries.toLocaleString('pl-PL')}</dd>
              </div>
              <div className="importMetric">
                <dt>Zarezerwowane</dt>
                <dd>{source.reservedEntries.toLocaleString('pl-PL')}</dd>
              </div>
              <div className="importMetric">
                <dt>Zakończony pipeline</dt>
                <dd>{source.processedEntries.toLocaleString('pl-PL')}</dd>
              </div>
              <div className="importMetric">
                <dt>Błędy</dt>
                <dd>{source.failedEntries.toLocaleString('pl-PL')}</dd>
              </div>
            </dl>
            <div className="curatedImportControls">
              <label>
                <span>Liczba kolejnych zdjęć</span>
                <input
                  inputMode="numeric"
                  max={Math.max(1, source.remainingEntries)}
                  min={1}
                  onChange={(event) =>
                    setCuratedBatchSize(event.currentTarget.value)
                  }
                  type="number"
                  value={curatedBatchSize}
                />
              </label>
              <button
                aria-busy={activeAction === 'start-curated'}
                className="primaryButton"
                disabled={busy || batchBlocked || source.remainingEntries < 1}
                onClick={() => void startCuratedBatch(source)}
                type="button"
              >
                {activeAction === 'start-curated'
                  ? 'Uruchamianie…'
                  : source.remainingEntries < 1
                    ? 'Wszystkie zdjęcia wykorzystane'
                    : 'Przetwórz kolejne zdjęcia'}
              </button>
            </div>
            {latestBatch !== undefined ? (
              <p className="curatedImportStatus">
                Ostatnia partia #{latestBatch.batchNumber}: zdjęcia{' '}
                {latestBatch.startIndex + 1}–{latestBatch.endIndex} ·{' '}
                {latestBatch.job.status} · {latestBatch.job.progress.current}/
                {latestBatch.job.progress.total ?? '—'}
              </p>
            ) : (
              <p className="curatedImportStatus">
                Nie uruchomiono jeszcze żadnej partii. Domyślna liczba to 10.
              </p>
            )}
            {source.batches.length > 0 ? (
              <ol className="curatedBatchHistory" aria-label="Pomiary partii">
                {[...source.batches]
                  .reverse()
                  .slice(0, 10)
                  .map((batch) => {
                    const imageCount = batch.endIndex - batch.startIndex;
                    const timing = curatedBatchTiming(batch.job, imageCount);
                    return (
                      <li key={batch.id}>
                        <strong>#{batch.batchNumber}</strong>
                        <span>{imageCount.toLocaleString('pl-PL')} zdjęć</span>
                        <span>{batch.job.status}</span>
                        <span>
                          {timing === null
                            ? 'Pomiar po zakończeniu'
                            : `${timing.seconds.toFixed(1)} s · ${timing.secondsPerImage.toFixed(2)} s/zdj. · ${timing.imagesPerMinute.toFixed(1)} zdj./min`}
                        </span>
                      </li>
                    );
                  })}
              </ol>
            ) : null}
            {batchBlocked ? (
              <p className="curatedImportStatus">
                Następna partia będzie dostępna po zakończeniu bieżącego joba.
                Jeśli job zakończy się błędem, wznów go w zakładce Joby.
              </p>
            ) : null}
          </section>
        );
      })}

      {readySelections.length > 0 ? (
        <section
          className="importCompletenessCard"
          aria-labelledby="ready-layout-staging-title"
        >
          <header className="importCompletenessHeader">
            <div>
              <p className="eyebrow">Gotowy staging do wznowienia</p>
              <h3 id="ready-layout-staging-title">Import plansz z manifestu</h3>
              <p>
                Staging pozostaje dostępny po restarcie API i nie wymaga
                ponownego uploadu.
              </p>
            </div>
          </header>
          <ul className="importCompactList">
            {readySelections.map((ready) => {
              const active = ready.uploadId === readyUploadId;
              return (
                <li key={ready.uploadId}>
                  <strong>{ready.displayName}</strong>
                  <span>
                    {ready.uploadedFileCount.toLocaleString('pl-PL')} plików ·{' '}
                    {(ready.expectedTotalBytes / 1_000_000).toFixed(1)} MB ·{' '}
                    staging {ready.uploadId.slice(0, 8)}
                  </span>
                  <div className="importActionButtons">
                    <button
                      aria-busy={activeAction === 'preflight' && active}
                      className="secondaryButton"
                      disabled={busy}
                      onClick={() => void prepareReadyImport(ready.uploadId)}
                      type="button"
                    >
                      {activeAction === 'preflight' && active
                        ? 'Sprawdzanie…'
                        : active
                          ? 'Odśwież raport'
                          : 'Pokaż raport'}
                    </button>
                    <button
                      aria-busy={activeAction === 'delete-ready' && active}
                      className="secondaryButton"
                      disabled={busy}
                      onClick={() => void deleteReadyStaging(ready.uploadId)}
                      type="button"
                    >
                      Usuń nieużywany staging
                    </button>
                  </div>
                  {active && preflight !== null ? (
                    <dl className="importMetrics">
                      <div className="importMetric">
                        <dt>Źródła</dt>
                        <dd>
                          {preflight.sourceFileCount.toLocaleString('pl-PL')}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Nowe plansze</dt>
                        <dd>
                          {preflight.newSequenceCount.toLocaleString('pl-PL')}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Już zatwierdzone</dt>
                        <dd>
                          {preflight.reusedSequenceCount.toLocaleString(
                            'pl-PL',
                          )}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Pominięte źródła</dt>
                        <dd>
                          {preflight.skippedSourceCount.toLocaleString('pl-PL')}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Pierwszy nierozwiązany</dt>
                        <dd>{preflight.firstUnresolvedSequence ?? 'brak'}</dd>
                      </div>
                    </dl>
                  ) : null}
                  {active && preflight?.warnings.length ? (
                    <p className="curatedImportStatus">
                      Ostrzeżenia: {preflight.warnings.join(' · ')}
                    </p>
                  ) : null}
                  {active && preflight !== null ? (
                    <>
                      {preflight.geometryPreflightRequired ? (
                        <div className="importActionButtons">
                          <button
                            aria-busy={activeAction === 'geometry-preflight'}
                            className="secondaryButton"
                            disabled={busy}
                            onClick={() => void startGeometryPreflight()}
                            type="button"
                          >
                            {activeAction === 'geometry-preflight'
                              ? 'Tworzenie preflightu…'
                              : geometryPreflightJob === null
                                ? 'Przygotuj geometrię stron'
                                : 'Odśwież preflight geometrii'}
                          </button>
                          {geometryPreflightJob !== null ? (
                            <span className="curatedImportStatus">
                              Geometria: {geometryPreflightJob.status} ·{' '}
                              {geometryPreflightJob.progress.current}/
                              {geometryPreflightJob.progress.total ?? '—'} ·
                              poprawne {geometryPreflightJob.progress.succeeded}{' '}
                              · odroczone {geometryPreflightJob.progress.review}
                            </span>
                          ) : null}
                          {geometryPreflightJob?.status === 'completed' &&
                          geometryPreflightJob.progress.review > 0 ? (
                            <details>
                              <summary>
                                Ręczna korekta geometrii — zostaw na koniec (
                                {geometryPreflightJob.progress.review})
                              </summary>
                              <p className="curatedImportStatus">
                                Rozpoznane strony można już importować. Te
                                pozycje pozostają bezpiecznie odroczone i nie
                                trafią do cięcia ani rozpoznawania symboli.
                              </p>
                              <PageGeometryCorrectionPanel
                                api={api}
                                apiBaseUrl={apiBaseUrl}
                                gameId={gameId}
                                onSaved={rerunGeometryPreflightAfterCorrection}
                                preflightJobId={geometryPreflightJob.id}
                                uploadId={ready.uploadId}
                              />
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <p className="curatedImportStatus">
                          Cold-start nowego silnika: historyczny profil siatki
                          nie jest wymagany. Wynik strukturalny zostanie
                          zapisany w cieniu i nie zastąpi automatycznie
                          stabilnej geometrii.
                        </p>
                      )}
                    </>
                  ) : null}
                </li>
              );
            })}
          </ul>
        </section>
      ) : null}

      <div className="importActionToolbar">
        <div className="importActionButtons">
          <button
            aria-busy={
              activeAction === 'start-import' || activeAction === 'start-ready'
            }
            className="primaryButton"
            disabled={
              busy ||
              (preflight === null &&
                (readyUploadId !== null ||
                  selection?.selectionToken == null)) ||
              (preflight !== null &&
                preflight.geometryPreflightRequired &&
                (geometryPreflightJob?.status !== 'completed' ||
                  geometryManifestChecksum === null))
            }
            onClick={() =>
              void (preflight === null ? startImport() : startReadyImport())
            }
            type="button"
          >
            {activeAction === 'start-import' || activeAction === 'start-ready'
              ? 'Uruchamianie…'
              : preflight === null
                ? 'Rozpocznij import'
                : geometryPreflightJob !== null &&
                    geometryPreflightJob.progress.review > 0
                  ? 'Importuj rozpoznane strony'
                  : boardCellProcessingMode === 'verified_v19'
                    ? 'Rozpocznij import v20 z raportu'
                    : 'Rozpocznij import z raportu'}
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
            disabled={busy || enginePolicy === null}
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
                <dd>Tworzy job dopiero po aktualnym raporcie preflight.</dd>
              </div>
              <div>
                <dt>Wybierz folder</dt>
                <dd>
                  Otwiera natywne okno przeglądarki i przesyła JPEG-i do
                  trwałego stagingu lokalnego API.
                </dd>
              </div>
              <div>
                <dt>Gotowy staging</dt>
                <dd>
                  Pozwala wznowić raport lub usunąć staging po restarcie API bez
                  ponownego uploadu.
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
            {jobs.slice(0, 5).map((job) => {
              const outcome = imageImportOutcome(job);
              return (
                <li key={job.id}>
                  <strong>
                    {job.inputPayload.sourceDisplayName ?? 'Import obrazów'}
                  </strong>
                  <span>
                    {job.status} · {job.progress.current}/
                    {job.progress.total ?? '—'}
                  </span>
                  <span>
                    Silnik cięcia plansz: {boardCellProcessingJobLabel(job)}
                  </span>
                  {outcome === null ? null : (
                    <span>
                      Pipeline zdjęć: {outcome.pipelineImages}/
                      {outcome.sourceCount} · poprawne {outcome.succeededImages}{' '}
                      · błędy {outcome.failedImages} · plansze do review{' '}
                      {outcome.reviewBoards}
                    </span>
                  )}
                  {outcome !== null && outcome.failedImages > 0 ? (
                    <small role="alert">
                      Wynik jest niekompletny: część zdjęć nie utworzyła plansz.
                    </small>
                  ) : null}
                  {!['created', 'processing'].includes(job.status) ? (
                    <button
                      aria-busy={activeAction === 'reprocess-import'}
                      className="secondaryButton"
                      disabled={busy}
                      onClick={() => void reprocessImport(job)}
                      type="button"
                    >
                      Przetwórz ponownie z oryginałów
                    </button>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </section>
  );
}
