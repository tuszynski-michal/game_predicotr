'use client';

import type {
  CuratedImageImportJobPayload,
  CuratedImageImportSourceResponse,
  BrowserImageImportPreflightResponse,
  JobResponse,
  BrowserReadySelectionResponse,
  BrowserPageGeometryReviewSourceResponse,
  ImageDatasetCompletenessResponse,
  ImageFolderSelectionResponse,
  ImageSelectionHandoffResponse,
  ImageImportJobPayload,
  ImageSequenceSourceSelectionResponse,
  ImageImportEnginePolicyResponse,
  GeometryEngineVariant,
  ManagedImageReprocessJobPayload,
  PinnedManagedImageReprocessJobPayload,
  BrowserImageImportJobPayload,
  ResolvedBrowserImageImportJobPayload,
  ImageGeometryGuardResolutionManifestResponse,
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
import { resolveAdminApiBaseUrl } from '@/config/admin-api';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';
import { jobProgressLabel } from '@/features/jobs/job-state';

import {
  boardCellProcessingJobLabel,
  boardCellProcessingModeLabel,
  jobMatchesBoardCellProcessingMode,
} from './board-cell-processing-mode';
import {
  type ImageFolderImportClient,
  type PageRegistrationVariant,
  DEFAULT_GEOMETRY_ENGINE_VARIANT,
  LATERAL_PARTIAL_VARIANT,
  SELECTIVE_BOARD_VARIANT,
  filterImageFolderImportFiles,
  geometryPreflightMatchesReport,
  listReadyBrowserImageSelections,
  imageImportJobMatchesReportIdentity,
  pageRegistrationVariantFromJob,
  previewReadyBrowserImageImport,
  persistedGuardContextIdentityStatusFromLatest,
  replayGeometryPreflightProgress,
  reprocessManagedV4OrPrepare,
  reprocessImageFolderImport,
  retryBrowserPageGeometryPreflight,
  startBrowserPageGeometryPreflight,
  startReadyBrowserImageImport,
  uploadImageFolder,
} from './image-folder-import-actions';
import {
  canStartReadyImport,
  pageGeometryPreflightOutcomeLabel,
  readyBoardImportGeometryVariant,
  readyBoardImportHasImport,
  readyBoardImportLifecycleLabel,
  sortReadyBoardImports,
} from './image-folder-import-state';
import { PageGeometryCorrectionPanel } from './page-geometry-correction-panel';
import { GeometryGuardResolutionPanel } from './geometry-guard-resolution-panel';
import { ImportGeometryReviewSummary } from './import-geometry-review-summary';

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
    | BrowserImageImportJobPayload
    | ResolvedBrowserImageImportJobPayload
    | CuratedImageImportJobPayload
    | ManagedImageReprocessJobPayload
    | PinnedManagedImageReprocessJobPayload;
};

type ImportAction =
  | 'choose-folder'
  | 'list-ready'
  | 'preflight'
  | 'geometry-preflight'
  | 'start-ready'
  | 'delete-ready'
  | 'reprocess-import'
  | 'refresh-status'
  | 'inspect-sequence'
  | 'choose-source'
  | 'register-curated'
  | 'start-curated'
  | 'engine-policy';

function replacementPreviewStorageKey(gameId: string, uploadId: string) {
  return `page-geometry-replacement-preview:${gameId}:${uploadId}`;
}

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
  const progress = job.progress.imageImport;
  if (progress)
    return {
      failedImages: progress.failedSources,
      pipelineImages: progress.processedSources,
      reviewBoards: progress.reviewSources,
      sourceCount: progress.pipelineTotal,
      succeededImages: progress.succeededSources,
    };
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

function shortChecksum(value: string | null | undefined): string {
  return value === null || value === undefined ? 'brak' : value.slice(0, 12);
}

function symbolModelReadinessText(
  preflight: BrowserImageImportPreflightResponse,
): string {
  if (
    preflight.symbolModelReady &&
    preflight.symbolModelInferenceFingerprint !== null
  ) {
    return `gotowy · ${shortChecksum(preflight.symbolModelInferenceFingerprint)}`;
  }
  if (preflight.unclassifiedColdStartAllowed) {
    return 'pierwszy import — cropy trafią jako oczekujące ?';
  }
  return preflight.symbolModelBlockerCode === 'SYMBOL_MODEL_ACTIVATION_REQUIRED'
    ? 'blokada — aktywuj gotowego kandydata'
    : 'blokada — wytrenuj i aktywuj model gry';
}

function symbolModelNextStep(
  preflight: BrowserImageImportPreflightResponse,
): string | null {
  if (preflight.symbolModelReady) return null;
  if (preflight.unclassifiedColdStartAllowed) {
    return 'Gra nie ma jeszcze zatwierdzonych cropów ani modelu. Pierwszy import utworzy plansze i komórki jako oczekujące „?”. Po ich zatwierdzeniu wytrenuj i aktywuj model, a następnie uruchom reinferencję.';
  }
  return preflight.symbolModelBlockerCode === 'SYMBOL_MODEL_ACTIVATION_REQUIRED'
    ? 'Raport i geometria są dostępne, ale start importu wymaga aktywacji gotowego kandydata modelu symboli.'
    : 'Raport i geometria są dostępne, ale przed startem importu zatwierdź aktualne cropy w Ulepszaniu modelu symboli, wybierz „Ulepsz rozpoznawanie”, a następnie aktywuj model tej gry.';
}

function jobSnapshotText(job: ImageImportJob, field: string, key: string) {
  const payload = job.inputPayload as unknown as Record<string, unknown>;
  const snapshot = payload[field];
  if (typeof snapshot !== 'object' || snapshot === null) return null;
  const value = (snapshot as Record<string, unknown>)[key];
  return typeof value === 'string' ? value : null;
}

function geometryEngineJobLabel(job: ImageImportJob): string {
  const payload = job.inputPayload as unknown as Record<string, unknown>;
  const rollout = payload.imageGeometryRollout;
  if (typeof rollout === 'object' && rollout !== null) {
    const lateral = (rollout as Record<string, unknown>)[
      'lateralPartialGeometry'
    ];
    if (typeof lateral === 'object' && lateral !== null) {
      if (
        (lateral as Record<string, unknown>).variant === SELECTIVE_BOARD_VARIANT
      ) {
        return 'v1.1 — korekta niepewnych plansz';
      }
      return 'v1.0 — niepełne boki';
    }
    const version = (rollout as Record<string, unknown>)[
      'geometryEngineVersion'
    ];
    if (typeof version === 'string') return version;
  }
  return boardCellProcessingJobLabel(job);
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
  const [replacementPreview, setReplacementPreview] = useState<{
    readonly checksum: string;
    readonly uploadId: string;
    readonly source: BrowserPageGeometryReviewSourceResponse | null;
    readonly saved: boolean;
  } | null>(null);
  const [readyUploadId, setReadyUploadId] = useState<string | null>(null);
  useEffect(() => {
    if (readyUploadId === null) return;
    try {
      const stored = window.localStorage.getItem(
        replacementPreviewStorageKey(gameId, readyUploadId),
      );
      if (stored !== null) {
        const parsed: unknown = JSON.parse(stored);
        if (
          typeof parsed === 'object' &&
          parsed !== null &&
          'checksum' in parsed &&
          typeof parsed.checksum === 'string' &&
          /^[0-9a-f]{64}$/.test(parsed.checksum)
        ) {
          const candidate = 'source' in parsed ? parsed.source : null;
          const source =
            typeof candidate === 'object' &&
            candidate !== null &&
            'sourceChecksumSha256' in candidate &&
            candidate.sourceChecksumSha256 === parsed.checksum &&
            'sourceRelativePath' in candidate &&
            typeof candidate.sourceRelativePath === 'string' &&
            'expectedBoardCount' in candidate &&
            typeof candidate.expectedBoardCount === 'number' &&
            candidate.expectedBoardCount > 0
              ? (candidate as BrowserPageGeometryReviewSourceResponse)
              : null;
          queueMicrotask(() =>
            setReplacementPreview({
              checksum: parsed.checksum as string,
              saved: 'saved' in parsed && parsed.saved === true,
              source,
              uploadId: readyUploadId,
            }),
          );
        }
      }
    } catch {
      // A private browser session can disable storage; the current view still works.
    }
  }, [gameId, readyUploadId]);
  const [preflight, setPreflight] =
    useState<BrowserImageImportPreflightResponse | null>(null);
  const [geometryPreflightJob, setGeometryPreflightJob] =
    useState<JobResponse | null>(null);
  const [pendingGeometryCorrectionState, setPendingGeometryCorrectionState] =
    useState<{
      readonly jobId: string;
      readonly count: number;
    } | null>(null);
  const [pageRegistrationVariant, setPageRegistrationVariant] =
    useState<PageRegistrationVariant>('standard_v0_10');
  const [geometryEngineVariant, setGeometryEngineVariant] = useState<
    GeometryEngineVariant | undefined
  >(DEFAULT_GEOMETRY_ENGINE_VARIANT);
  const [geometryGuardResolutionManifest, setGeometryGuardResolutionManifest] =
    useState<ImageGeometryGuardResolutionManifestResponse | null>(null);
  const [enginePolicy, setEnginePolicy] =
    useState<ImageImportEnginePolicyResponse | null>(null);
  const boardCellProcessingMode = enginePolicy?.policy ?? 'verified_v19';
  const lateralCapability = enginePolicy?.geometryEngineVariants?.find(
    (candidate) => candidate.variant === LATERAL_PARTIAL_VARIANT,
  );
  const lateralVariantAvailable = lateralCapability?.enabled === true;
  const selectiveCapability = enginePolicy?.geometryEngineVariants?.find(
    (candidate) => candidate.variant === SELECTIVE_BOARD_VARIANT,
  );
  const [curatedSources, setCuratedSources] = useState<
    readonly CuratedImageImportSourceResponse[]
  >([]);
  const [curatedBatchSize, setCuratedBatchSize] = useState('10');
  const registeredHandoffRef = useRef<string | null>(null);
  const [jobs, setJobs] = useState<readonly ImageImportJob[]>([]);
  const [geometryPreflightJobs, setGeometryPreflightJobs] = useState<
    readonly JobResponse[]
  >([]);
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
  const activeReportIdentityRef = useRef({
    gameId,
    geometryEngineVariant,
    preflight,
    readyUploadId,
  });
  const activeGuardJobIdRef = useRef<string | null>(null);
  useEffect(() => {
    activeReportIdentityRef.current = {
      gameId,
      geometryEngineVariant,
      preflight,
      readyUploadId,
    };
  }, [gameId, geometryEngineVariant, preflight, readyUploadId]);
  const folderInputRef = useRef<HTMLInputElement | null>(null);
  const busy = activeAction !== null;
  const activeBrowserGeometryPreflightJob =
    preflight !== null &&
    geometryPreflightJob !== null &&
    geometryPreflightMatchesReport(geometryPreflightJob, preflight)
      ? geometryPreflightJob
      : null;
  const geometryManifestChecksum =
    activeBrowserGeometryPreflightJob?.progress.pageGeometryPreflight
      ?.geometryManifestChecksumSha256 ?? null;
  const failedGeometryGuardJob = useMemo(
    () =>
      readyUploadId === null ||
      preflight === null ||
      geometryEngineVariant === LATERAL_PARTIAL_VARIANT
        ? null
        : (jobs.find((job) => {
            return (
              job.status === 'failed' &&
              job.error?.code === 'IMAGE_GEOMETRY_SYSTEMIC_REGRESSION' &&
              imageImportJobMatchesReportIdentity(
                job,
                gameId,
                readyUploadId,
                preflight,
                geometryEngineVariant,
              )
            );
          }) ?? null),
    [gameId, geometryEngineVariant, jobs, preflight, readyUploadId],
  );
  useEffect(() => {
    activeGuardJobIdRef.current = failedGeometryGuardJob?.id ?? null;
  }, [failedGeometryGuardJob?.id]);
  const foreignGeometryGuardJob = useMemo(() => {
    if (readyUploadId === null || preflight === null) return null;
    return (
      jobs.find((job) => {
        const payload = job.inputPayload as unknown as Record<string, unknown>;
        return (
          job.status === 'failed' &&
          job.error?.code === 'IMAGE_GEOMETRY_SYSTEMIC_REGRESSION' &&
          payload.sourceSelectionId === readyUploadId &&
          !imageImportJobMatchesReportIdentity(
            job,
            gameId,
            readyUploadId,
            preflight,
            geometryEngineVariant,
          )
        );
      }) ?? null
    );
  }, [gameId, geometryEngineVariant, jobs, preflight, readyUploadId]);
  const handleGuardManifestInvalidated = useCallback(() => {
    setGeometryGuardResolutionManifest(null);
  }, []);
  const handleGuardManifestSealed = useCallback(
    (manifest: ImageGeometryGuardResolutionManifestResponse) => {
      setGeometryGuardResolutionManifest(manifest);
      setFeedback(
        'Manifest decyzji został przypięty. Import nadal wymaga jawnego kliknięcia przycisku startu.',
      );
    },
    [],
  );
  const handlePersistedGuardContextLoaded = useCallback(
    (
      manifest: ImageGeometryGuardResolutionManifestResponse | null,
      pageGeometryPreflightJob: JobResponse | null,
      identity: {
        readonly browserSelectionId: string;
        readonly gameId: string;
        readonly guardJobId: string;
        readonly pageGeometryManifestChecksumSha256: string;
        readonly sourceManifestChecksumSha256: string;
      },
    ) => {
      const identityStatus = persistedGuardContextIdentityStatusFromLatest({
        activeGuardJobIdRef,
        activeReportIdentityRef,
        identity,
        manifest,
        pageGeometryPreflightJob,
      });
      if (identityStatus === 'stale') return;
      if (identityStatus === 'v4_rebind_forbidden') {
        setError(
          'IMAGE_LATERAL_PARTIAL_GUARD_REBIND_REQUIRED: decyzje guarda v3 nie mogą zastąpić raportu v1.0.',
        );
        return;
      }
      if (identityStatus === 'foreign') {
        setError(
          'IMAGE_GEOMETRY_GUARD_IDENTITY_MISMATCH: zapisany guard nie należy do bieżącego stagingu, manifestu i wariantu.',
        );
        return;
      }
      setGeometryGuardResolutionManifest(manifest);
      if (pageGeometryPreflightJob !== null) {
        setGeometryPreflightJob(pageGeometryPreflightJob);
      }
    },
    [],
  );
  const readyImportStartAllowed =
    preflight !== null &&
    !readySelections.some(
      (selection) =>
        selection.uploadId === preflight.uploadId &&
        readyBoardImportHasImport(selection),
    ) &&
    preflight.geometryEngineVariantEnabled &&
    canStartReadyImport({
      geometryGuardResolutionManifestAvailable:
        geometryGuardResolutionManifest !== null,
      geometryGuardResolutionRequired: failedGeometryGuardJob !== null,
      geometryManifestAvailable: geometryManifestChecksum !== null,
      geometryPreflightArtifactReady:
        preflight.geometryPreflightArtifactReady ?? false,
      geometryPreflightCompleted:
        activeBrowserGeometryPreflightJob?.status === 'completed',
      geometryPreflightRequired: preflight.geometryPreflightRequired,
      symbolModelAvailable:
        preflight.symbolModelReady ||
        (preflight.unclassifiedColdStartAllowed ?? false),
    });

  const refreshJobs = useCallback(async () => {
    const [
      jobsResult,
      completenessResult,
      curatedResult,
      readyResult,
      policyResult,
      geometryPreflightsResult,
    ] = await Promise.all([
      api.listJobs({
        gameId,
        jobType: 'import',
        limit: 200,
      }),
      api.getImageDatasetCompleteness(gameId),
      api.listCuratedImageImportSources(gameId),
      listReadyBrowserImageSelections(api),
      api.getImageImportEnginePolicy(gameId),
      api.listJobs({
        gameId,
        jobType: 'validate',
        limit: 200,
      }),
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
          setGeometryGuardResolutionManifest(null);
          return null;
        }
        return current;
      });
    }
    if (policyResult.error === undefined && policyResult.data !== undefined) {
      const policy = policyResult.data;
      setEnginePolicy(policy);
    }
    if (
      geometryPreflightsResult.error === undefined &&
      geometryPreflightsResult.data !== undefined
    ) {
      setGeometryPreflightJobs(
        geometryPreflightsResult.data.filter((job) => {
          const payload = job.inputPayload as unknown as Record<
            string,
            unknown
          >;
          return payload.validationKind === 'page_geometry_preflight';
        }),
      );
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

  const geometryPreflightJobId = activeBrowserGeometryPreflightJob?.id;
  const geometryPreflightJobStatus = activeBrowserGeometryPreflightJob?.status;
  const visibleGeometryCorrectionCount =
    pendingGeometryCorrectionState !== null &&
    pendingGeometryCorrectionState.jobId === geometryPreflightJobId
      ? pendingGeometryCorrectionState.count
      : (geometryPreflightJob?.progress.review ?? 0);
  const handlePendingGeometryCorrectionCountChange = useCallback(
    (count: number) => {
      if (geometryPreflightJobId === undefined) return;
      setPendingGeometryCorrectionState({
        count,
        jobId: geometryPreflightJobId,
      });
    },
    [geometryPreflightJobId],
  );

  useEffect(() => {
    if (
      geometryPreflightJobId === undefined ||
      !['created', 'processing'].includes(geometryPreflightJobStatus ?? '')
    )
      return;
    let cancelled = false;
    const refreshGeometry = async () => {
      const result = await api.getJob(geometryPreflightJobId);
      if (
        !cancelled &&
        result.error === undefined &&
        result.data !== undefined
      ) {
        const updated = result.data;
        const activeReport = activeReportIdentityRef.current.preflight;
        if (
          activeReport === null ||
          !geometryPreflightMatchesReport(updated, activeReport)
        ) {
          return;
        }
        setGeometryPreflightJob(updated);
        setGeometryPreflightJobs((current) => [
          updated,
          ...current.filter((job) => job.id !== updated.id),
        ]);
        setPreflight((current) =>
          current === null
            ? null
            : replayGeometryPreflightProgress(
                current,
                updated,
                geometryPreflightJobId,
              ),
        );
      }
    };
    void refreshGeometry();
    const timer = window.setInterval(() => void refreshGeometry(), 3_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [api, geometryPreflightJobId, geometryPreflightJobStatus]);

  useEffect(() => {
    if (
      replacementPreview?.uploadId !== readyUploadId ||
      (replacementPreview.source != null && !replacementPreview.saved) ||
      preflight === null ||
      geometryPreflightJob !== null ||
      readyUploadId === null
    )
      return;
    let cancelled = false;
    const recoverReplacementPreflight = async () => {
      const result = await previewReadyBrowserImageImport(
        api,
        readyUploadId,
        gameId,
        geometryEngineVariant,
      );
      if (cancelled || !result.ok || result.data.geometryPreflightJob == null)
        return;
      const recovered = result.data.geometryPreflightJob;
      if (!geometryPreflightMatchesReport(recovered, result.data)) return;
      setPreflight(result.data);
      setGeometryPreflightJob(recovered);
      setGeometryPreflightJobs((current) => [
        recovered,
        ...current.filter((job) => job.id !== recovered.id),
      ]);
    };
    void recoverReplacementPreflight();
    const timer = window.setInterval(
      () => void recoverReplacementPreflight(),
      15_000,
    );
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [
    api,
    gameId,
    geometryEngineVariant,
    geometryPreflightJob,
    preflight,
    readyUploadId,
    replacementPreview,
  ]);

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
    const selectedFiles = filterImageFolderImportFiles(
      Array.from(input.files ?? []),
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
      if (result.kind === 'nothing_to_upload') {
        setUploadProgress(null);
        setFeedback(
          `Nie przesłano JPEG-ów: ${result.uploadPlan.skippedCompleteSourceCount.toLocaleString('pl-PL')} kompletnych zakresów ma już zaimportowane plansze.`,
        );
        return;
      }
      setSelection(result.selection);
      setSelectionDisplayName(result.displayName);
      setReadyUploadId(result.uploadId);
      setPreflight(null);
      setGeometryPreflightJob(null);
      setGeometryGuardResolutionManifest(null);
      setFeedback(
        result.uploadPlan === null
          ? `Folder przesłany: ${result.selection.supportedFileCount} plików JPEG. Przygotowuję raport przed importem.`
          : `Przesłano ${result.uploadPlan.uploadFileCount.toLocaleString('pl-PL')} z ${result.uploadPlan.selectedFileCount.toLocaleString('pl-PL')} JPEG-ów. Pominięto ${result.uploadPlan.skippedCompleteSourceCount.toLocaleString('pl-PL')} kompletnych zakresów. Przygotowuję raport przed importem.`,
      );
      const preflightResult = await previewReadyBrowserImageImport(
        api,
        result.uploadId,
        gameId,
        geometryEngineVariant,
      );
      if (!preflightResult.ok) {
        setError(preflightResult.error);
        return;
      }
      setPreflight(preflightResult.data);
      setGeometryPreflightJob(
        preflightResult.data.geometryPreflightJob ?? null,
      );
      if (preflightResult.data.geometryPreflightRequired) {
        setFeedback(
          'Raport jest gotowy. Kliknij „Przygotuj geometrię stron”, aby jawnie uruchomić analizę.',
        );
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

  async function prepareReadyImport(
    uploadId: string,
    requestedVariant: GeometryEngineVariant | undefined = geometryEngineVariant,
  ) {
    if (busy) return;
    setActiveAction('preflight');
    setError('');
    setFeedback('Sprawdzanie gotowego stagingu i decyzji kanonicznych…');
    try {
      const keepsPersistedGuardContext =
        readyUploadId === uploadId &&
        geometryEngineVariant === requestedVariant;
      const result = await previewReadyBrowserImageImport(
        api,
        uploadId,
        gameId,
        requestedVariant,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setReadyUploadId(uploadId);
      setPreflight(result.data);
      setGeometryEngineVariant(requestedVariant);
      if (requestedVariant === undefined) {
        globalThis.localStorage?.removeItem(
          `image-import-geometry-engine:${gameId}`,
        );
      } else {
        globalThis.localStorage?.setItem(
          `image-import-geometry-engine:${gameId}`,
          requestedVariant,
        );
      }
      setGeometryPreflightJob(result.data.geometryPreflightJob ?? null);
      if (result.data.pageRegistrationVariant != null) {
        setPageRegistrationVariant(result.data.pageRegistrationVariant);
      }
      if (
        result.data.existingImportJob != null &&
        isImageImportJob(result.data.existingImportJob)
      ) {
        const restored = result.data.existingImportJob;
        setJobs((current) => [
          restored,
          ...current.filter((item) => item.id !== restored.id),
        ]);
      }
      if (!keepsPersistedGuardContext) {
        setGeometryGuardResolutionManifest(null);
      }
      const modelNextStep = symbolModelNextStep(result.data);
      if (result.data.geometryPreflightRequired) {
        const geometryFeedback = result.data.geometryPreflightArtifactReady
          ? 'Raport odtworzył zapisany preflight; samo otwarcie nie uruchomiło joba.'
          : `Raport jest gotowy bez uruchamiania joba. ${result.data.geometryPreflightArtifactBlockerMessage ?? 'Jawnie przygotuj geometrię stron.'}`;
        setFeedback(
          modelNextStep === null
            ? geometryFeedback
            : `${geometryFeedback} ${modelNextStep}`,
        );
      } else {
        setGeometryPreflightJob(null);
        const geometryFeedback =
          'Raport jest gotowy. Nowy silnik rozpocznie bez historycznego profilu siatki i zapisze wyniki w trybie shadow.';
        setFeedback(
          modelNextStep === null
            ? geometryFeedback
            : `${geometryFeedback} ${modelNextStep}`,
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
      !readyImportStartAllowed
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
        activeBrowserGeometryPreflightJob?.id,
        geometryManifestChecksum ?? undefined,
        boardCellProcessingMode,
        preflight.imageEnginePolicyRevision,
        preflight.symbolModelInferenceFingerprint ?? undefined,
        preflight.gridProfileInferenceFingerprint,
        geometryGuardResolutionManifest?.id,
        geometryGuardResolutionManifest?.manifestChecksumSha256,
        geometryEngineVariant,
        preflight.symbolModelSnapshotFingerprint ?? undefined,
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
          ? `Import ${imageJob.id} utworzony w ${geometryEngineVariant === SELECTIVE_BOARD_VARIANT ? 'v1.1' : 'v1.0'} — oczekuje na worker.`
          : `Import ${imageJob.id} już istnieje w ${geometryEngineVariant === SELECTIVE_BOARD_VARIANT ? 'v1.1' : 'v1.0'}. Nie utworzono drugiego joba.`,
      );
      try {
        window.localStorage.removeItem(
          replacementPreviewStorageKey(gameId, readyUploadId),
        );
      } catch {
        // Import state is durable in the API even when browser storage is unavailable.
      }
      setReplacementPreview(null);
      setSelection(null);
      setSelectionDisplayName('');
      setPreflight(null);
      setGeometryPreflightJob(null);
      setGeometryGuardResolutionManifest(null);
      await refreshJobs();
    } catch {
      setError('Nie udało się utworzyć importu plansz.');
    } finally {
      setActiveAction(null);
    }
  }

  async function startGeometryPreflight() {
    if (
      busy ||
      readyUploadId === null ||
      preflight === null ||
      !preflight.geometryPreflightRequired ||
      !preflight.geometryEngineVariantEnabled
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
        pageRegistrationVariant,
        geometryEngineVariant,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setGeometryPreflightJob(result.data.job);
      setGeometryPreflightJobs((current) => [
        result.data.job,
        ...current.filter((job) => job.id !== result.data.job.id),
      ]);
      setPreflight((current) =>
        current === null
          ? null
          : {
              ...current,
              geometryPreflightArtifactBlockerCode:
                'IMAGE_PAGE_GEOMETRY_PREFLIGHT_IN_PROGRESS',
              geometryPreflightArtifactBlockerMessage:
                'Preflight geometrii jest w trakcie wykonywania.',
              geometryPreflightArtifactReady: false,
              geometryPreflightJob: result.data.job,
            },
      );
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

  async function handlePageGeometrySourceReplaced(
    ready: BrowserReadySelectionResponse,
    replacementChecksumSha256: string,
    source: BrowserPageGeometryReviewSourceResponse,
  ) {
    const variant = geometryEngineVariant;
    const replacedUploadId = readyUploadId;
    const replacementSource: BrowserPageGeometryReviewSourceResponse = {
      ...source,
      sourceChecksumSha256: replacementChecksumSha256,
      reviewReason: 'review_required',
      geometryOrigin: 'manual_template',
      existingFinalQuads: null,
      existingOverrideRevision: null,
      existingSlotQualifications: null,
      automaticPartialProposals: null,
      savedSincePreflight: false,
    };
    const preview = {
      checksum: replacementChecksumSha256,
      saved: false,
      source: replacementSource,
      uploadId: ready.uploadId,
    };
    setReplacementPreview(preview);
    try {
      window.localStorage.setItem(
        replacementPreviewStorageKey(gameId, ready.uploadId),
        JSON.stringify(preview),
      );
    } catch {
      // The in-memory preview remains available for this session.
    }
    setReadySelections((current) =>
      sortReadyBoardImports([
        ready,
        ...current.filter(
          (item) =>
            item.uploadId !== ready.uploadId &&
            item.uploadId !== replacedUploadId,
        ),
      ]),
    );
    const report = await previewReadyBrowserImageImport(
      api,
      ready.uploadId,
      gameId,
      variant,
    );
    if (!report.ok) throw new Error(report.error);
    setReadyUploadId(ready.uploadId);
    setPreflight(report.data);
    setGeometryPreflightJob(report.data.geometryPreflightJob ?? null);
    setGeometryGuardResolutionManifest(null);
    setFeedback(
      `Nowe zdjęcie jest w katalogu cut i stagingu ${ready.uploadId.slice(0, 8)}. Możesz teraz poprawić jego geometrię, a następnie jawnie uruchomić preflight w ${variant === SELECTIVE_BOARD_VARIANT ? 'v1.1' : 'v1.0'}.`,
    );
  }

  function markReplacementDraftSaved() {
    if (replacementPreview === null) return;
    const savedPreview = { ...replacementPreview, saved: true };
    setReplacementPreview(savedPreview);
    try {
      window.localStorage.setItem(
        replacementPreviewStorageKey(gameId, savedPreview.uploadId),
        JSON.stringify(savedPreview),
      );
    } catch {
      // The saved override remains durable in the API.
    }
  }

  async function retryGeometryPreflight() {
    if (busy || geometryPreflightJob?.status !== 'failed') return;
    setActiveAction('geometry-preflight');
    setError('');
    setFeedback('Ponawiam istniejący preflight pełnej geometrii 3×3…');
    try {
      const result = await retryBrowserPageGeometryPreflight(
        api,
        geometryPreflightJob.id,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      setGeometryPreflightJob(result.data);
      setFeedback(
        `Preflight geometrii ${result.data.id} ponowiony — oczekuje na worker.`,
      );
    } catch {
      setError('Nie udało się ponowić preflightu geometrii stron.');
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
      let refreshedReport: BrowserImageImportPreflightResponse | null = null;
      if (readyUploadId !== null && preflight !== null) {
        const reportResult = await previewReadyBrowserImageImport(
          api,
          readyUploadId,
          gameId,
          geometryEngineVariant,
        );
        if (!reportResult.ok) {
          setError(reportResult.error);
          return;
        }
        refreshedReport = reportResult.data;
        setPreflight(refreshedReport);
        setGeometryPreflightJob(refreshedReport.geometryPreflightJob ?? null);
        if (refreshedReport.pageRegistrationVariant != null) {
          setPageRegistrationVariant(refreshedReport.pageRegistrationVariant);
        }
      }
      const refreshedGeometryPreflightJobId =
        refreshedReport?.geometryPreflightJob?.id ?? geometryPreflightJobId;
      if (refreshedGeometryPreflightJobId !== undefined) {
        const result = await api.getJob(refreshedGeometryPreflightJobId);
        if (result.error === undefined && result.data !== undefined) {
          const updated = result.data;
          const activeReport =
            refreshedReport ?? activeReportIdentityRef.current.preflight;
          if (
            activeReport === null ||
            !geometryPreflightMatchesReport(updated, activeReport)
          ) {
            setError(
              'IMAGE_PAGE_GEOMETRY_PREFLIGHT_IDENTITY_MISMATCH: odpowiedź nie należy do aktywnego raportu.',
            );
            return;
          }
          setGeometryPreflightJob(updated);
          setGeometryPreflightJobs((current) => [
            updated,
            ...current.filter((job) => job.id !== updated.id),
          ]);
          setPreflight((current) =>
            current === null
              ? null
              : replayGeometryPreflightProgress(
                  current,
                  updated,
                  refreshedGeometryPreflightJobId,
                ),
          );
        }
      }
      const modelNextStep =
        refreshedReport === null ? null : symbolModelNextStep(refreshedReport);
      setFeedback(
        modelNextStep === null
          ? 'Status importu i raport modelu zostały odświeżone.'
          : `Status importu i raport modelu zostały odświeżone. ${modelNextStep}`,
      );
    } catch {
      setError('Nie udało się odświeżyć statusu importu.');
    } finally {
      setActiveAction(null);
    }
  }

  async function reprocessImport(sourceJob: ImageImportJob, manual = false) {
    if (busy) return;
    setActiveAction('reprocess-import');
    setError('');
    setFeedback('');
    try {
      const result = await reprocessImageFolderImport(
        api,
        sourceJob.id,
        manual,
      );
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

  async function reprocessManagedV4(sourceJob: ImageImportJob) {
    if (busy || !lateralVariantAvailable) return;
    setActiveAction('reprocess-import');
    setError('');
    setFeedback('Sprawdzam przypięty preflight v1.0…');
    try {
      const result = await reprocessManagedV4OrPrepare(
        api,
        sourceJob,
        geometryPreflightJobs,
        pageRegistrationVariant,
      );
      if (!result.ok) {
        setError(result.error);
        return;
      }
      if (result.kind === 'reprocessed' && isImageImportJob(result.job)) {
        const imageJob = result.job;
        setJobs((current) => [
          imageJob,
          ...current.filter((job) => job.id !== imageJob.id),
        ]);
        setFeedback(
          'Utworzono idempotentny run v1.0 z zachowanych oryginałów i przypiętego manifestu.',
        );
        return;
      }
      setGeometryPreflightJobs((current) => [
        result.job,
        ...current.filter((job) => job.id !== result.job.id),
      ]);
      setFeedback(
        result.kind === 'preflight_created'
          ? 'Jawnie przygotowano preflight v1.0 z zachowanych oryginałów. Po ukończeniu kliknij ponownie „Przetwórz w v1.0”.'
          : 'Preflight v1.0 nadal pracuje. Nie utworzono drugiego joba.',
      );
    } catch {
      setError('Nie udało się przygotować managed-original runu v1.0.');
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

      <fieldset className="importActionToolbar">
        <legend>Silnik siatki dla tego wykonania</legend>
        <label>
          <input
            checked={geometryEngineVariant === LATERAL_PARTIAL_VARIANT}
            disabled={busy || !lateralVariantAvailable}
            name="geometry-engine-variant"
            onChange={() => {
              setGeometryEngineVariant(LATERAL_PARTIAL_VARIANT);
              setPreflight(null);
              setGeometryPreflightJob(null);
              setGeometryGuardResolutionManifest(null);
            }}
            type="radio"
          />
          v1.0 — niepełne boki
        </label>
        <label>
          <input
            checked={geometryEngineVariant === SELECTIVE_BOARD_VARIANT}
            disabled={busy || selectiveCapability?.enabled !== true}
            name="geometry-engine-variant"
            onChange={() => {
              setGeometryEngineVariant(SELECTIVE_BOARD_VARIANT);
              setPreflight(null);
              setGeometryPreflightJob(null);
              setGeometryGuardResolutionManifest(null);
            }}
            type="radio"
          />
          v1.1 — korekta 1–2 niepewnych plansz
        </label>
        {!lateralVariantAvailable ? (
          <p className="mutedText" role="status">
            {`${lateralCapability?.blockerCode ?? 'IMAGE_GEOMETRY_ENGINE_VARIANT_NOT_ENABLED'}: ${lateralCapability?.blockerMessage ?? 'Silnik v1.0 jest niedostępny.'}`}
          </p>
        ) : null}
      </fieldset>
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
                ponownego uploadu. Lista obejmuje tylko fizyczne stagingi gotowe
                do wznowienia; historia zakończonych importów pozostaje w
                zakładce Joby.
              </p>
            </div>
          </header>
          <ul className="importCompactList">
            {readySelections.map((ready) => {
              const imported = readyBoardImportHasImport(ready);
              const active = ready.uploadId === readyUploadId && !imported;
              const lifecycleLabel = readyBoardImportLifecycleLabel({
                geometryPreflightJobs,
                reportPrepared:
                  preflight?.uploadId === ready.uploadId &&
                  preflight.manifestChecksumSha256 ===
                    ready.manifestChecksumSha256,
                selection: ready,
              });
              return (
                <li key={ready.uploadId}>
                  <strong>{ready.displayName}</strong>
                  <span>
                    {ready.uploadedFileCount.toLocaleString('pl-PL')} plików ·{' '}
                    {(ready.expectedTotalBytes / 1_000_000).toFixed(1)} MB ·{' '}
                    staging {ready.uploadId.slice(0, 8)} · {lifecycleLabel}
                  </span>
                  {!imported ? (
                    <div className="importActionButtons">
                      <button
                        aria-busy={activeAction === 'preflight' && active}
                        className="secondaryButton"
                        disabled={busy}
                        onClick={() =>
                          void prepareReadyImport(
                            ready.uploadId,
                            active
                              ? geometryEngineVariant
                              : readyBoardImportGeometryVariant(
                                  geometryPreflightJobs,
                                  ready,
                                ),
                          )
                        }
                        type="button"
                      >
                        {activeAction === 'preflight' && active
                          ? 'Sprawdzanie…'
                          : active
                            ? 'Odśwież raport'
                            : 'Pokaż raport'}
                      </button>
                      <button
                        className="secondaryButton"
                        disabled={busy || selectiveCapability?.enabled !== true}
                        onClick={() =>
                          void prepareReadyImport(
                            ready.uploadId,
                            SELECTIVE_BOARD_VARIANT,
                          )
                        }
                        type="button"
                      >
                        Przetwórz w v1.1
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
                  ) : null}
                  {imported ? (
                    <p className="curatedImportStatus">
                      Ten staging nie wymaga ponownego importu. Weryfikacja symboli
                      nie zmienia statusu importu plansz. Brakujące geometrie
                      popraw w „Zatwierdzanie cięcia siatki” → „Niepełne siatki do
                      ręcznej korekty”.
                    </p>
                  ) : null}
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
                      <div className="importMetric">
                        <dt>Źródło geometrii 3×3</dt>
                        <dd>
                          {geometryManifestChecksum === null
                            ? 'blokada — brak dokładnego manifestu'
                            : 'dokładny manifest preflightu'}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Manifest / preflight</dt>
                        <dd>
                          {shortChecksum(geometryManifestChecksum)} ·{' '}
                          {activeBrowserGeometryPreflightJob?.id ?? 'brak'}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Pokrycie geometrii źródeł</dt>
                        <dd>
                          {geometryPreflightJob === null
                            ? 'oczekuje'
                            : `${geometryPreflightJob.progress.succeeded.toLocaleString('pl-PL')}/${preflight.sourceFileCount.toLocaleString('pl-PL')}`}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Wariant dopasowania zdjęcia</dt>
                        <dd>
                          {preflight.pageRegistrationVariant ??
                            pageRegistrationVariant}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Model symboli — wersja</dt>
                        <dd>{symbolModelReadinessText(preflight)}</dd>
                      </div>
                      <div className="importMetric">
                        <dt>Wersja silnika siatki</dt>
                        <dd>
                          {preflight.geometryEngineVariant ===
                          SELECTIVE_BOARD_VARIANT
                            ? 'v1.1 — korekta plansz'
                            : preflight.geometryEngineVariant ===
                                LATERAL_PARTIAL_VARIANT
                              ? 'v1.0 — niepełne boki'
                              : boardCellProcessingModeLabel(
                                  boardCellProcessingMode,
                                )}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Fingerprint profilu</dt>
                        <dd>
                          {shortChecksum(
                            preflight.gridProfileInferenceFingerprint,
                          )}
                        </dd>
                      </div>
                      <div className="importMetric">
                        <dt>Test ochronny ≥98%</dt>
                        <dd>
                          {preflight.sourceFileCount >= 100 ||
                          preflight.newSequenceCount >= 500
                            ? 'oczekuje — wykona się przed materializacją'
                            : 'niewymagany dla małego importu'}
                        </dd>
                      </div>
                    </dl>
                  ) : null}
                  {active && preflight?.warnings.length ? (
                    <p className="curatedImportStatus">
                      Ostrzeżenia: {preflight.warnings.join(' · ')}
                    </p>
                  ) : null}
                  {active && preflight !== null
                    ? (() => {
                        const nextStep = symbolModelNextStep(preflight);
                        return nextStep === null ? null : (
                          <p className="curatedImportStatus">{nextStep}</p>
                        );
                      })()
                    : null}
                  {active && foreignGeometryGuardJob !== null ? (
                    <p
                      className="feedbackBanner feedbackBannerError"
                      role="alert"
                    >
                      IMAGE_GEOMETRY_GUARD_IDENTITY_MISMATCH: guard z runu{' '}
                      {foreignGeometryGuardJob.id} ma inny manifest, wariant lub
                      rewizję. Nie zostanie automatycznie przepięty.
                    </p>
                  ) : null}
                  {active && preflight !== null ? (
                    <>
                      {preflight.geometryPreflightRequired ? (
                        <div className="importActionButtons">
                          <button
                            aria-busy={activeAction === 'geometry-preflight'}
                            className="secondaryButton"
                            disabled={
                              busy || !preflight.geometryEngineVariantEnabled
                            }
                            onClick={() =>
                              geometryPreflightJob?.status === 'failed'
                                ? void retryGeometryPreflight()
                                : geometryPreflightJob === null
                                  ? void startGeometryPreflight()
                                  : void refreshStatus()
                            }
                            type="button"
                          >
                            {activeAction === 'geometry-preflight'
                              ? 'Tworzenie preflightu…'
                              : geometryPreflightJob?.status === 'failed'
                                ? 'Ponów preflight'
                                : geometryPreflightJob === null
                                  ? 'Przygotuj geometrię stron'
                                  : 'Odśwież preflight geometrii'}
                          </button>
                          {!preflight.geometryEngineVariantEnabled ? (
                            <span className="curatedImportStatus" role="status">
                              {preflight.geometryEngineVariantBlockerCode}:{' '}
                              {preflight.geometryEngineVariantBlockerMessage}
                            </span>
                          ) : preflight.geometryPreflightArtifactBlockerMessage ? (
                            <span className="curatedImportStatus" role="status">
                              {preflight.geometryPreflightArtifactBlockerCode}:{' '}
                              {
                                preflight.geometryPreflightArtifactBlockerMessage
                              }
                            </span>
                          ) : null}
                          {geometryPreflightJob !== null ? (
                            <span className="curatedImportStatus">
                              Geometria zdjęć: {geometryPreflightJob.status} ·{' '}
                              {jobProgressLabel(geometryPreflightJob)} ·
                              zarejestrowane zdjęcia{' '}
                              {geometryPreflightJob.progress.succeeded} ·
                              {pageGeometryPreflightOutcomeLabel(
                                geometryPreflightJob,
                                visibleGeometryCorrectionCount,
                              )}
                            </span>
                          ) : null}
                          {replacementPreview?.uploadId === ready.uploadId &&
                          geometryPreflightJob === null &&
                          replacementPreview.source != null &&
                          !replacementPreview.saved ? (
                            <section
                              aria-label="Korekta geometrii strony"
                              className="pageGeometryCorrection"
                            >
                              <h3>Popraw geometrię podmienionego zdjęcia</h3>
                              <p>
                                Po zapisaniu korekty uruchom preflight
                                przyciskiem powyżej.
                              </p>
                              <PageGeometryCorrectionPanel
                                api={api}
                                apiBaseUrl={apiBaseUrl}
                                gameId={gameId}
                                initialReplacementSource={
                                  replacementPreview.source
                                }
                                onDraftSaved={markReplacementDraftSaved}
                                onSubmitSaved={
                                  rerunGeometryPreflightAfterCorrection
                                }
                                onSourceReplaced={
                                  handlePageGeometrySourceReplaced
                                }
                                preflightJobId={`replacement-draft:${ready.uploadId}`}
                                uploadId={ready.uploadId}
                              />
                            </section>
                          ) : null}
                          {replacementPreview?.uploadId === ready.uploadId &&
                          geometryPreflightJob === null &&
                          replacementPreview.saved ? (
                            <p className="curatedImportStatus" role="status">
                              Zapisano geometrię podmienionego zdjęcia. Uruchom
                              preflight przyciskiem powyżej.
                            </p>
                          ) : null}
                          {replacementPreview?.uploadId === ready.uploadId &&
                          geometryPreflightJob !== null &&
                          geometryPreflightJob.status !== 'completed' ? (
                            <section
                              aria-label="Korekta geometrii strony"
                              className="pageGeometryCorrection"
                            >
                              <h3>Preflight podmienionego zdjęcia w toku</h3>
                              <img
                                alt="Nowe zdjęcie źródłowe po podmianie"
                                style={{
                                  display: 'block',
                                  maxWidth: '100%',
                                  height: 'auto',
                                }}
                                src={`${resolveAdminApiBaseUrl(apiBaseUrl)}/api/v1/admin/image-imports/browser-selections/${encodeURIComponent(ready.uploadId)}/page-geometry-sources/${encodeURIComponent(replacementPreview.checksum)}/asset?game_id=${encodeURIComponent(gameId)}`}
                              />
                              <p>
                                Po ukończeniu preflightu otworzy się wynik w
                                edytorze geometrii.
                              </p>
                            </section>
                          ) : null}
                          {geometryPreflightJob?.status === 'completed' ? (
                            <details
                              open={
                                replacementPreview?.uploadId === ready.uploadId
                              }
                            >
                              <summary>
                                Ręczna korekta zdjęć geometrii — zostaw na
                                koniec ({visibleGeometryCorrectionCount})
                              </summary>
                              <p className="curatedImportStatus">
                                Każda pozycja oznacza jedno zdjęcie zawierające
                                dziewięć plansz. Ponowna korekta wcześniej
                                zarejestrowanego zdjęcia zmienia jego geometrię,
                                ale nie zwiększa licznika zarejestrowanych.
                                Plansze powstaną dopiero po uruchomieniu
                                importu.
                              </p>
                              <PageGeometryCorrectionPanel
                                allowRegisteredSourceInspection
                                api={api}
                                apiBaseUrl={apiBaseUrl}
                                focusSourceChecksumSha256={
                                  replacementPreview?.uploadId ===
                                  ready.uploadId
                                    ? replacementPreview.checksum
                                    : undefined
                                }
                                gameId={gameId}
                                onPendingSourceCountChange={
                                  handlePendingGeometryCorrectionCountChange
                                }
                                onSubmitSaved={
                                  rerunGeometryPreflightAfterCorrection
                                }
                                onSourceReplaced={
                                  handlePageGeometrySourceReplaced
                                }
                                preflightJobId={geometryPreflightJob.id}
                                uploadId={ready.uploadId}
                              />
                            </details>
                          ) : null}
                          {failedGeometryGuardJob !== null ? (
                            <details open>
                              <summary>
                                Rozlicz problematyczne plansze
                                {geometryGuardResolutionManifest === null
                                  ? ' — wymagane przed nowym importem'
                                  : ' — manifest gotowy'}
                              </summary>
                              <GeometryGuardResolutionPanel
                                api={api}
                                apiBaseUrl={apiBaseUrl}
                                gameId={gameId}
                                guardJobId={failedGeometryGuardJob.id}
                                onManifestInvalidated={
                                  handleGuardManifestInvalidated
                                }
                                onManifestSealed={handleGuardManifestSealed}
                                onPersistedContextLoaded={
                                  handlePersistedGuardContextLoaded
                                }
                                uploadId={ready.uploadId}
                              />
                            </details>
                          ) : null}
                        </div>
                      ) : (
                        <p className="curatedImportStatus">
                          Ten historyczny raport nie zawiera wymaganego
                          manifestu geometrii. Odśwież raport przed rozpoczęciem
                          importu.
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
        <label>
          Dopasowanie geometrii zdjęcia
          <select
            disabled={busy}
            onChange={(event) =>
              setPageRegistrationVariant(
                event.target.value as PageRegistrationVariant,
              )
            }
            value={pageRegistrationVariant}
          >
            <option value="standard_v0_10">Standardowe v0.10</option>
            <option value="board_area_test">Obszar plansz — testowe</option>
          </select>
        </label>
        <div className="importActionButtons">
          <button
            aria-busy={activeAction === 'start-ready'}
            className="primaryButton"
            disabled={busy || !readyImportStartAllowed}
            onClick={() => void startReadyImport()}
            type="button"
          >
            {activeAction === 'start-ready'
              ? 'Uruchamianie…'
              : preflight === null
                ? 'Przygotuj raport, aby rozpocząć import'
                : geometryPreflightJob !== null &&
                    geometryPreflightJob.progress.review > 0
                  ? 'Importuj rozpoznane strony'
                  : geometryGuardResolutionManifest !== null
                    ? 'Rozpocznij nowy import z rozliczeniami'
                    : preflight.unclassifiedColdStartAllowed
                      ? 'Rozpocznij pierwszy import bez modelu'
                      : `Rozpocznij import ${geometryEngineVariant === SELECTIVE_BOARD_VARIANT ? 'v1.1' : 'v1.0'} z raportu`}
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
                <dd>
                  Aktualizuje kompletność, ostatnie importy i otwarty raport
                  modelu.
                </dd>
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
              const pageManifestChecksum = jobSnapshotText(
                job,
                'pageGeometryManifest',
                'checksumSha256',
              );
              const pagePreflightJobId = jobSnapshotText(
                job,
                'pageGeometryManifest',
                'preflightJobId',
              );
              const gridProfileVersion = jobSnapshotText(
                job,
                'gridProfile',
                'profileVersion',
              );
              const cellGeometryVersion = jobSnapshotText(
                job,
                'boardCellProcessing',
                'geometryVersion',
              );
              const pageRegistrationJob = geometryPreflightJobs.find(
                (candidate) => candidate.id === pagePreflightJobId,
              );
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
                    Wersja silnika siatki / Silnik cięcia plansz:{' '}
                    {geometryEngineJobLabel(job)}
                  </span>
                  {pageManifestChecksum !== null &&
                  pagePreflightJobId !== null ? (
                    <span>
                      Geometria stron 3×3: dokładny manifest{' '}
                      {shortChecksum(pageManifestChecksum)} · preflight{' '}
                      {pagePreflightJobId}
                    </span>
                  ) : (
                    <span>Geometria stron 3×3: brak manifestu</span>
                  )}
                  {gridProfileVersion !== null ? (
                    <span>
                      Wariant dopasowania geometrii zdjęcia:{' '}
                      {pageRegistrationVariantFromJob(pageRegistrationJob)} ·
                      profil {gridProfileVersion}
                    </span>
                  ) : null}
                  {cellGeometryVersion !== null ? (
                    <span>Silnik komórek 3×5: {cellGeometryVersion}</span>
                  ) : null}
                  <span>
                    Wersja modelu symboli:{' '}
                    {jobSnapshotText(
                      job,
                      'symbolModel',
                      'inferenceFingerprint',
                    ) ?? 'historyczny snapshot'}
                  </span>
                  {job.progress.geometrySystemicGuard ? (
                    <span>
                      Test ochronny:{' '}
                      {job.progress.geometrySystemicGuard.passed
                        ? 'zaliczony'
                        : job.progress.geometrySystemicGuard.qualityWarningOnly
                          ? 'ostrzeżenie — import jest kontynuowany, niepewne siatki do ręcznej korekty'
                          : 'zablokowany'}{' '}
                      · próbka{' '}
                      {job.progress.geometrySystemicGuard.sampleBoardCount}{' '}
                      plansz · 3×3{' '}
                      {(
                        job.progress.geometrySystemicGuard
                          .pageRegistrationReadyRate * 100
                      ).toFixed(2)}
                      % · 3×5{' '}
                      {(
                        job.progress.geometrySystemicGuard
                          .finalCellGridReadyRate * 100
                      ).toFixed(2)}
                      % · raport{' '}
                      {shortChecksum(
                        job.progress.geometrySystemicGuard.reportChecksumSha256,
                      )}
                    </span>
                  ) : (
                    <span>
                      Test ochronny: niewymagany albo jeszcze nieuruchomiony
                    </span>
                  )}
                  {outcome === null ? null : (
                    <span>
                      Pipeline zdjęć: {outcome.pipelineImages}/
                      {outcome.sourceCount} · poprawne {outcome.succeededImages}{' '}
                      · błędy techniczne zdjęć {outcome.failedImages} · zdjęcia
                      do review {outcome.reviewBoards}
                    </span>
                  )}
                  {outcome !== null && outcome.failedImages > 0 ? (
                    <small role="alert">
                      Wynik jest niekompletny: część zdjęć nie utworzyła plansz.
                    </small>
                  ) : null}
                  <ImportGeometryReviewSummary
                    api={api}
                    gameId={gameId}
                    jobId={job.id}
                    technicalErrorCount={outcome?.failedImages ?? 0}
                  />
                  {job.status === 'failed' &&
                  job.error?.code === 'IMAGE_GEOMETRY_SYSTEMIC_REGRESSION' ? (
                    <button
                      className="primaryButton"
                      disabled={busy}
                      onClick={() => void reprocessImport(job, true)}
                      type="button"
                    >
                      Kontynuuj z ręczną korektą
                    </button>
                  ) : null}
                  {!['created', 'processing'].includes(job.status) ? (
                    <>
                      <button
                        aria-busy={activeAction === 'reprocess-import'}
                        className="secondaryButton"
                        disabled={busy}
                        onClick={() => void reprocessImport(job)}
                        type="button"
                      >
                        Przetwórz ponownie z oryginałów
                      </button>
                      <button
                        aria-busy={activeAction === 'reprocess-import'}
                        className="secondaryButton"
                        disabled={busy || !lateralVariantAvailable}
                        onClick={() => void reprocessManagedV4(job)}
                        type="button"
                      >
                        Przetwórz w v1.0
                      </button>
                    </>
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
