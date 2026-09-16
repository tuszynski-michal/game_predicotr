import type {
  AdminApiClient,
  BrowserImageImportPreflightResponse,
  BrowserImageImportStart,
  BrowserImageImportStartResponse,
  BrowserImageUploadPlanResponse,
  BrowserPageGeometryPreflightResponse,
  BrowserReadySelectionResponse,
  GeometryEngineVariant,
  ImageGeometryGuardResolutionManifestResponse,
  ImageFolderSelectionResponse,
  JobResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ImageFolderImportClient = Pick<
  AdminApiClient,
  | 'createBrowserImageSelection'
  | 'planBrowserImageSelectionUpload'
  | 'uploadBrowserImageSelectionFile'
  | 'finalizeBrowserImageSelection'
  | 'listReadyBrowserImageSelections'
  | 'previewReadyBrowserImageImport'
  | 'startReadyBrowserImageImport'
  | 'startBrowserPageGeometryPreflight'
  | 'listBrowserPageGeometryReviewSources'
  | 'createBrowserPageGeometryOverride'
  | 'excludeBrowserPageGeometrySource'
  | 'listImageGeometryGuardBoards'
  | 'createImageGeometryGuardDecisions'
  | 'previewImageGeometryGuardDecision'
  | 'startImageGeometryGuardReportReconstruction'
  | 'sealImageGeometryGuardResolutionManifest'
  | 'cancelBrowserImageSelection'
  | 'getImageDatasetCompleteness'
  | 'getImageSequenceSourceSelection'
  | 'registerCuratedImageImportSource'
  | 'listCuratedImageImportSources'
  | 'createNextCuratedImageImportBatch'
  | 'listJobs'
  | 'getJob'
  | 'retryJob'
  | 'reprocessManagedImageImport'
  | 'listImageGridReviews'
  | 'startLocalReviewer'
  | 'selectImageSequenceSource'
  | 'getImageImportEnginePolicy'
  | 'previewImageImportEnginePolicy'
  | 'updateImageImportEnginePolicy'
>;

export type PageRegistrationVariant = 'standard_v0_10' | 'board_area_test';
export const LATERAL_PARTIAL_VARIANT: GeometryEngineVariant =
  'structured_lattice_v4_partial_sides';
export const SELECTIVE_BOARD_VARIANT: GeometryEngineVariant =
  'selective_board_review_v1_1';
const LATERAL_PARTIAL_POLICY_VERSIONS = new Set([
  'structured-lattice-v4-lateral-partial-v1',
  'structured-lattice-v4-lateral-partial-v2',
  'structured-lattice-v4-lateral-partial-v3',
  'structured-lattice-v4-selective-frame-v1',
]);

function isSupportedLateralPartialGeometry(
  value: unknown,
  variant: GeometryEngineVariant,
): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const snapshot = value as Record<string, unknown>;
  return (
    snapshot.variant === variant &&
    typeof snapshot.policyVersion === 'string' &&
    LATERAL_PARTIAL_POLICY_VERSIONS.has(snapshot.policyVersion)
  );
}

export function replayGeometryPreflightProgress(
  report: BrowserImageImportPreflightResponse,
  job: JobResponse,
  expectedJobId: string,
): BrowserImageImportPreflightResponse {
  if (job.id !== expectedJobId || !geometryPreflightMatchesReport(job, report))
    return report;
  const completed =
    job.status === 'completed' &&
    job.progress.pageGeometryPreflight?.geometryManifestChecksumSha256 !==
      undefined;
  return {
    ...report,
    geometryPreflightArtifactBlockerCode: completed
      ? null
      : report.geometryPreflightArtifactBlockerCode,
    geometryPreflightArtifactBlockerMessage: completed
      ? null
      : report.geometryPreflightArtifactBlockerMessage,
    geometryPreflightArtifactReady: completed,
    geometryPreflightJob: job,
  };
}

export function geometryPreflightMatchesReport(
  job: JobResponse,
  report: BrowserImageImportPreflightResponse,
): boolean {
  const payload = jobPayload(job);
  const lateral = payload.lateralPartialGeometry;
  const variant = report.geometryEngineVariant;
  return (
    job.jobType === 'validate' &&
    job.gameId === report.gameId &&
    payload.validationKind === 'page_geometry_preflight' &&
    payload.sourceSelectionId === report.uploadId &&
    payload.sourceManifestSha256 === report.manifestChecksumSha256 &&
    (payload.managedSourceJobId === undefined ||
      payload.managedSourceJobId === null) &&
    (variant !== undefined && variant !== null
      ? isSupportedLateralPartialGeometry(lateral, variant)
      : lateral === undefined)
  );
}

export interface PersistedGuardContextIdentity {
  readonly browserSelectionId: string;
  readonly gameId: string;
  readonly guardJobId: string;
  readonly pageGeometryManifestChecksumSha256: string;
  readonly sourceManifestChecksumSha256: string;
}

export interface ActiveGuardReportIdentity {
  readonly gameId: string;
  readonly geometryEngineVariant?: GeometryEngineVariant;
  readonly preflight: BrowserImageImportPreflightResponse | null;
  readonly readyUploadId: string | null;
}

export function persistedGuardContextIdentityStatusFromLatest(input: {
  readonly activeGuardJobIdRef: { readonly current: string | null };
  readonly activeReportIdentityRef: {
    readonly current: ActiveGuardReportIdentity;
  };
  readonly identity: PersistedGuardContextIdentity;
  readonly manifest: ImageGeometryGuardResolutionManifestResponse | null;
  readonly pageGeometryPreflightJob: JobResponse | null;
}): 'foreign' | 'match' | 'stale' | 'v4_rebind_forbidden' {
  const current = input.activeReportIdentityRef.current;
  if (current.preflight === null || current.readyUploadId === null) {
    return 'stale';
  }
  return persistedGuardContextIdentityStatus({
    currentGameId: current.gameId,
    currentGuardJobId: input.activeGuardJobIdRef.current,
    currentUploadId: current.readyUploadId,
    geometryEngineVariant: current.geometryEngineVariant,
    identity: input.identity,
    manifest: input.manifest,
    pageGeometryPreflightJob: input.pageGeometryPreflightJob,
    report: current.preflight,
  });
}

export function persistedGuardContextIdentityStatus(input: {
  readonly currentGameId: string;
  readonly currentGuardJobId: string | null;
  readonly currentUploadId: string;
  readonly geometryEngineVariant?: GeometryEngineVariant;
  readonly identity: PersistedGuardContextIdentity;
  readonly manifest: ImageGeometryGuardResolutionManifestResponse | null;
  readonly pageGeometryPreflightJob: JobResponse | null;
  readonly report: BrowserImageImportPreflightResponse;
}): 'foreign' | 'match' | 'stale' | 'v4_rebind_forbidden' {
  if (
    input.identity.gameId !== input.currentGameId ||
    input.identity.browserSelectionId !== input.currentUploadId ||
    (input.report.geometryEngineVariant ?? undefined) !==
      input.geometryEngineVariant
  ) {
    return 'stale';
  }
  if (input.geometryEngineVariant !== undefined) {
    return 'v4_rebind_forbidden';
  }
  if (
    input.currentGuardJobId === null ||
    input.identity.guardJobId !== input.currentGuardJobId
  ) {
    return 'stale';
  }
  if (
    input.identity.sourceManifestChecksumSha256 !==
      input.report.manifestChecksumSha256 ||
    (input.manifest !== null &&
      (input.manifest.sourceManifestChecksumSha256 !==
        input.report.manifestChecksumSha256 ||
        input.manifest.guardJobId !== input.identity.guardJobId ||
        input.manifest.pageGeometryManifestChecksumSha256 !==
          input.identity.pageGeometryManifestChecksumSha256))
  ) {
    return 'foreign';
  }
  if (input.pageGeometryPreflightJob === null) {
    return input.manifest === null ? 'match' : 'foreign';
  }
  const payload = jobPayload(input.pageGeometryPreflightJob);
  const checksum =
    input.pageGeometryPreflightJob.progress.pageGeometryPreflight
      ?.geometryManifestChecksumSha256;
  return payload.sourceSelectionId === input.currentUploadId &&
    input.pageGeometryPreflightJob.gameId === input.currentGameId &&
    payload.sourceManifestSha256 === input.report.manifestChecksumSha256 &&
    checksum === input.identity.pageGeometryManifestChecksumSha256 &&
    payload.lateralPartialGeometry === undefined
    ? 'match'
    : 'foreign';
}

export function pageRegistrationVariantFromJob(
  job: JobResponse | undefined,
): string {
  if (job === undefined) return 'brak przypiętego snapshotu';
  const payload = jobPayload(job);
  return payload.preflightPolicyVersion ===
    'page-geometry-preflight-v3-board-area-mask'
    ? 'board_area_test'
    : payload.validationKind === 'page_geometry_preflight'
      ? 'standard_v0_10'
      : 'nieznany snapshot';
}

export function imageImportJobMatchesReportIdentity(
  job: JobResponse,
  gameId: string,
  uploadId: string,
  report: BrowserImageImportPreflightResponse,
  variant: GeometryEngineVariant | undefined,
): boolean {
  const payload = jobPayload(job);
  const rollout = payload.imageGeometryRollout;
  const lateral =
    typeof rollout === 'object' && rollout !== null
      ? (rollout as Record<string, unknown>).lateralPartialGeometry
      : undefined;
  const variantMatches =
    variant !== undefined
      ? isSupportedLateralPartialGeometry(lateral, variant)
      : lateral === undefined;
  const symbol = payload.symbolModel;
  const grid = payload.gridProfile;
  const symbolMatches = symbolSnapshotMatchesReport(symbol, report);
  const rolloutMatches =
    (typeof rollout === 'object' &&
      rollout !== null &&
      (rollout as Record<string, unknown>).rolloutRevision ===
        report.imageEnginePolicyRevision) ||
    (rollout === undefined &&
      report.imageEnginePolicy === 'verified_v19' &&
      report.imageEnginePolicyRevision === 0 &&
      variant === undefined);
  return (
    job.gameId === gameId &&
    payload.sourceSelectionId === uploadId &&
    payload.sourceManifestSha256 === report.manifestChecksumSha256 &&
    rolloutMatches &&
    symbolMatches &&
    typeof grid === 'object' &&
    grid !== null &&
    (grid as Record<string, unknown>).inferenceFingerprint ===
      report.gridProfileInferenceFingerprint &&
    variantMatches
  );
}

export function symbolSnapshotMatchesReport(
  value: unknown,
  report: BrowserImageImportPreflightResponse,
): boolean {
  if (typeof value !== 'object' || value === null) return false;
  const snapshot = value as Record<string, unknown>;
  if (
    typeof report.symbolModelSnapshotFingerprint !== 'string' ||
    snapshot.inferenceFingerprint !== report.symbolModelSnapshotFingerprint
  ) {
    return false;
  }
  if (report.symbolModelInferenceFingerprint !== null) {
    return (
      snapshot.inferenceFingerprint ===
        report.symbolModelInferenceFingerprint &&
      snapshot.inferenceMode !== 'unclassified'
    );
  }
  const classCodes = snapshot.classCodes;
  return (
    report.unclassifiedColdStartAllowed === true &&
    snapshot.inferenceMode === 'unclassified' &&
    snapshot.modelVersion === 'cold-start-unclassified-v1' &&
    snapshot.onnxRelativePath ===
      'unclassified/cold-start-unclassified-v1.no-onnx' &&
    snapshot.storageRoot === 'repository' &&
    snapshot.inputSize === 64 &&
    snapshot.temperature === 1 &&
    snapshot.iterationId === undefined &&
    Array.isArray(classCodes) &&
    classCodes.length >= 2 &&
    classCodes.every((code) => typeof code === 'string' && code.length > 0)
  );
}

type Failure = { readonly error: string; readonly ok: false };

const UPLOAD_PROGRESS_PAINT_INTERVAL = 25;

export function filterImageFolderImportFiles(
  files: readonly File[],
): readonly File[] {
  return files.filter((file) => /\.jpe?g$/iu.test(file.name));
}

async function yieldForUploadProgressPaint(uploadedFileCount: number) {
  if (
    uploadedFileCount !== 1 &&
    uploadedFileCount % UPLOAD_PROGRESS_PAINT_INTERVAL !== 0
  ) {
    return;
  }
  await new Promise<void>((resolve) => globalThis.setTimeout(resolve, 0));
}

export type BoardCellProcessingMode = NonNullable<
  BrowserImageImportStart['boardCellProcessingMode']
>;

export async function uploadImageFolder(
  api: ImageFolderImportClient,
  files: readonly File[],
  gameIdOrProgress?: string | ((uploaded: number, total: number) => void),
  progressCallback?: (uploaded: number, total: number) => void,
): Promise<
  | {
      readonly displayName: string;
      readonly kind: 'uploaded';
      readonly ok: true;
      readonly selection: ImageFolderSelectionResponse;
      readonly uploadId: string;
      readonly uploadPlan: BrowserImageUploadPlanResponse | null;
    }
  | {
      readonly displayName: string;
      readonly kind: 'nothing_to_upload';
      readonly ok: true;
      readonly uploadPlan: BrowserImageUploadPlanResponse;
    }
  | Failure
> {
  let uploadId: string | null = null;
  try {
    const gameId =
      typeof gameIdOrProgress === 'string' ? gameIdOrProgress : undefined;
    const onProgress =
      typeof gameIdOrProgress === 'function'
        ? gameIdOrProgress
        : progressCallback;
    let filesToUpload = files;
    let uploadPlan: BrowserImageUploadPlanResponse | null = null;
    if (typeof gameId === 'string') {
      const planned = await api.planBrowserImageSelectionUpload({
        gameId,
        files: files.map((file, sourceIndex) => ({
          relativePath: file.webkitRelativePath || file.name,
          sizeBytes: file.size,
          sourceIndex,
        })),
      });
      if (planned.error !== undefined || planned.data === undefined) {
        return {
          error: apiErrorMessage(
            planned.error,
            'Nie udało się sprawdzić, które zdjęcia wymagają importu.',
          ),
          ok: false,
        };
      }
      uploadPlan = planned.data;
      filesToUpload = planned.data.filesToUpload.map((item) => {
        const file = files[item.sourceIndex];
        if (file === undefined) {
          throw new Error('Plan uploadu wskazuje nieistniejący plik lokalny.');
        }
        return file;
      });
      if (filesToUpload.length === 0) {
        return {
          displayName:
            (
              files[0]?.webkitRelativePath ||
              files[0]?.name ||
              'Wybrane pliki'
            ).split('/')[0] || 'Wybrane pliki',
          kind: 'nothing_to_upload',
          ok: true,
          uploadPlan,
        };
      }
    }
    const totalBytes = filesToUpload.reduce(
      (total, file) => total + file.size,
      0,
    );
    const firstRelativePath = files[0]?.webkitRelativePath || files[0]?.name;
    const displayName = firstRelativePath?.split('/')[0] || 'Wybrane pliki';
    const created = await api.createBrowserImageSelection({
      displayName,
      expectedFileCount: filesToUpload.length,
      expectedTotalBytes: totalBytes,
      ...(gameId === undefined ? {} : { gameId }),
      ...(uploadPlan === null
        ? {}
        : {
            skippedCanonicalRanges: uploadPlan.skippedCompleteSources.map(
              (source) => ({
                sequenceRangeEnd: source.sequenceRangeEnd,
                sequenceRangeStart: source.sequenceRangeStart,
              }),
            ),
            uploadPlanChecksumSha256: uploadPlan.planChecksumSha256,
          }),
    });
    if (created.error !== undefined || created.data === undefined) {
      return {
        error: apiErrorMessage(
          created.error,
          'Nie udało się rozpocząć przesyłania wybranego folderu.',
        ),
        ok: false,
      };
    }
    uploadId = created.data.uploadId;
    for (const [index, file] of filesToUpload.entries()) {
      const uploaded = await api.uploadBrowserImageSelectionFile(
        uploadId,
        index,
        file.webkitRelativePath || file.name,
        file,
      );
      if (uploaded.error !== undefined || uploaded.data === undefined) {
        await cancelBrowserUpload(api, uploadId);
        return {
          error: apiErrorMessage(
            uploaded.error,
            `Nie udało się przesłać pliku ${index + 1} z ${filesToUpload.length}.`,
          ),
          ok: false,
        };
      }
      onProgress?.(
        uploaded.data.uploadedFileCount,
        uploaded.data.expectedFileCount,
      );
      // A large local folder can produce thousands of very fast sequential
      // fetch completions. Yield a macrotask after the first acknowledgement
      // and then periodically so React can paint server-confirmed progress.
      await yieldForUploadProgressPaint(uploaded.data.uploadedFileCount);
    }
    const finalized = await api.finalizeBrowserImageSelection(uploadId);
    if (finalized.error !== undefined || finalized.data === undefined) {
      await cancelBrowserUpload(api, uploadId);
      return {
        error: apiErrorMessage(
          finalized.error,
          'Nie udało się zweryfikować przesłanego folderu zdjęć.',
        ),
        ok: false,
      };
    }
    const finalizedUploadId = uploadId;
    uploadId = null;
    return {
      displayName,
      kind: 'uploaded',
      ok: true,
      selection: finalized.data,
      uploadId: finalizedUploadId,
      uploadPlan,
    };
  } catch {
    if (uploadId !== null) {
      await cancelBrowserUpload(api, uploadId);
    }
    return {
      error: 'Przesyłanie folderu do lokalnego Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function listReadyBrowserImageSelections(
  api: ImageFolderImportClient,
): Promise<
  | {
      readonly data: readonly BrowserReadySelectionResponse[];
      readonly ok: true;
    }
  | Failure
> {
  try {
    const result = await api.listReadyBrowserImageSelections();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać gotowych stagingów importu plansz.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function previewReadyBrowserImageImport(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
  geometryEngineVariant?: GeometryEngineVariant,
): Promise<
  | { readonly data: BrowserImageImportPreflightResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.previewReadyBrowserImageImport(uploadId, {
      gameId,
      ...(geometryEngineVariant === undefined ? {} : { geometryEngineVariant }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować raportu przed importem plansz.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startReadyBrowserImageImport(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
  manifestChecksumSha256: string,
  preflightChecksumSha256: string,
  geometryPreflightJobId: string | undefined,
  geometryManifestChecksumSha256: string | undefined,
  boardCellProcessingMode: BoardCellProcessingMode,
  imageEnginePolicyRevision: number,
  symbolModelInferenceFingerprint?: string,
  gridProfileInferenceFingerprint?: string,
  geometryGuardResolutionManifestId?: string,
  geometryGuardResolutionManifestChecksumSha256?: string,
  geometryEngineVariant?: GeometryEngineVariant,
  symbolModelSnapshotFingerprint?: string,
): Promise<
  | { readonly data: BrowserImageImportStartResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.startReadyBrowserImageImport(uploadId, {
      gameId,
      manifestChecksumSha256,
      preflightChecksumSha256,
      ...(symbolModelInferenceFingerprint === undefined
        ? {}
        : { symbolModelInferenceFingerprint }),
      ...(gridProfileInferenceFingerprint === undefined
        ? {}
        : { gridProfileInferenceFingerprint }),
      ...(geometryPreflightJobId === undefined
        ? {}
        : { geometryPreflightJobId }),
      ...(geometryManifestChecksumSha256 === undefined
        ? {}
        : { geometryManifestChecksumSha256 }),
      ...(geometryGuardResolutionManifestId === undefined
        ? {}
        : { geometryGuardResolutionManifestId }),
      ...(geometryGuardResolutionManifestChecksumSha256 === undefined
        ? {}
        : { geometryGuardResolutionManifestChecksumSha256 }),
      ...(geometryEngineVariant === undefined ? {} : { geometryEngineVariant }),
      ...(symbolModelSnapshotFingerprint === undefined
        ? {}
        : { symbolModelSnapshotFingerprint }),
      boardCellProcessingMode,
      imageEnginePolicy: boardCellProcessingMode,
      ...(imageEnginePolicyRevision === undefined
        ? {}
        : { imageEnginePolicyRevision }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć importu plansz.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startBrowserPageGeometryPreflight(
  api: ImageFolderImportClient,
  uploadId: string,
  gameId: string,
  pageRegistrationVariant: PageRegistrationVariant = 'standard_v0_10',
  geometryEngineVariant?: GeometryEngineVariant,
  managedSourceJobId?: string,
): Promise<
  | { readonly data: BrowserPageGeometryPreflightResponse; readonly ok: true }
  | Failure
> {
  try {
    const result = await api.startBrowserPageGeometryPreflight(uploadId, {
      gameId,
      pageRegistrationVariant,
      ...(geometryEngineVariant === undefined ? {} : { geometryEngineVariant }),
      ...(managedSourceJobId === undefined ? {} : { managedSourceJobId }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć preflightu geometrii stron.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function retryBrowserPageGeometryPreflight(
  api: ImageFolderImportClient,
  jobId: string,
): Promise<{ readonly data: JobResponse; readonly ok: true } | Failure> {
  try {
    const result = await api.retryJob(jobId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się ponowić preflightu geometrii stron.',
        ),
        ok: false,
      };
    }
    return { data: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

async function cancelBrowserUpload(
  api: ImageFolderImportClient,
  uploadId: string,
): Promise<void> {
  try {
    await api.cancelBrowserImageSelection(uploadId);
  } catch {
    // The original upload failure remains the actionable error for the owner.
  }
}

export async function reprocessImageFolderImport(
  api: ImageFolderImportClient,
  sourceJobId: string,
  continueWithManualGeometry = false,
  options?: {
    readonly geometryEngineVariant?: GeometryEngineVariant;
    readonly geometryManifestChecksumSha256?: string;
    readonly geometryPreflightJobId?: string;
  },
): Promise<{ readonly job: JobResponse; readonly ok: true } | Failure> {
  try {
    const result =
      options === undefined
        ? await api.reprocessManagedImageImport(
            sourceJobId,
            continueWithManualGeometry,
          )
        : await api.reprocessManagedImageImport(
            sourceJobId,
            continueWithManualGeometry,
            options,
          );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się ponownie przetworzyć zachowanych oryginałów.',
        ),
        ok: false,
      };
    }
    return { job: result.data.job, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

function jobPayload(job: JobResponse): Record<string, unknown> {
  return job.inputPayload as unknown as Record<string, unknown>;
}

export function findManagedV4GeometryPreflight(
  sourceJob: JobResponse,
  candidates: readonly JobResponse[],
  pageRegistrationVariant?: PageRegistrationVariant,
): JobResponse | null {
  const source = jobPayload(sourceJob);
  const sourceSelectionId = source.sourceSelectionId;
  const sourceManifestSha256 = source.sourceManifestSha256;
  if (
    typeof sourceSelectionId !== 'string' ||
    typeof sourceManifestSha256 !== 'string'
  ) {
    return null;
  }
  return (
    candidates.find((candidate) => {
      const payload = jobPayload(candidate);
      const lateral = payload.lateralPartialGeometry;
      const pageVariantMatches =
        pageRegistrationVariant === undefined ||
        (pageRegistrationVariant === 'board_area_test'
          ? payload.preflightPolicyVersion ===
            'page-geometry-preflight-v3-board-area-mask'
          : payload.validationKind === 'page_geometry_preflight' &&
            payload.preflightPolicyVersion !==
              'page-geometry-preflight-v3-board-area-mask');
      return (
        candidate.jobType === 'validate' &&
        candidate.gameId === sourceJob.gameId &&
        payload.validationKind === 'page_geometry_preflight' &&
        payload.sourceSelectionId === sourceSelectionId &&
        payload.sourceManifestSha256 === sourceManifestSha256 &&
        payload.managedSourceJobId === sourceJob.id &&
        isSupportedLateralPartialGeometry(lateral, LATERAL_PARTIAL_VARIANT) &&
        pageVariantMatches
      );
    }) ?? null
  );
}

export async function reprocessManagedV4OrPrepare(
  api: ImageFolderImportClient,
  sourceJob: JobResponse,
  candidates: readonly JobResponse[],
  pageRegistrationVariant: PageRegistrationVariant,
): Promise<
  | {
      readonly job: JobResponse;
      readonly kind: 'preflight_created' | 'preflight_waiting' | 'reprocessed';
      readonly ok: true;
    }
  | Failure
> {
  const payload = jobPayload(sourceJob);
  const sourceSelectionId = payload.sourceSelectionId;
  if (
    typeof sourceSelectionId !== 'string' ||
    typeof sourceJob.gameId !== 'string'
  ) {
    return {
      error: 'Zachowany import nie ma tożsamości źródłowego stagingu.',
      ok: false,
    };
  }
  let preflight = findManagedV4GeometryPreflight(
    sourceJob,
    candidates,
    pageRegistrationVariant,
  );
  if (preflight?.status === 'created' || preflight?.status === 'processing') {
    const refreshed = await api.getJob(preflight.id);
    if (refreshed.error !== undefined || refreshed.data === undefined) {
      return {
        error: apiErrorMessage(
          refreshed.error,
          'Nie udało się odświeżyć statusu przypiętego preflightu v0.10.4.',
        ),
        ok: false,
      };
    }
    const exactRefreshed = findManagedV4GeometryPreflight(
      sourceJob,
      [refreshed.data],
      pageRegistrationVariant,
    );
    if (exactRefreshed?.id !== preflight.id) {
      return {
        error:
          'Odświeżony preflight nie pasuje do źródła i wariantu managed-original.',
        ok: false,
      };
    }
    preflight = exactRefreshed;
  }
  if (preflight?.status === 'completed') {
    const checksum =
      preflight.progress.pageGeometryPreflight?.geometryManifestChecksumSha256;
    if (typeof checksum !== 'string') {
      return {
        error: 'Zakończony preflight nie ma niezmiennego manifestu geometrii.',
        ok: false,
      };
    }
    const result = await reprocessImageFolderImport(api, sourceJob.id, false, {
      geometryEngineVariant: LATERAL_PARTIAL_VARIANT,
      geometryManifestChecksumSha256: checksum,
      geometryPreflightJobId: preflight.id,
    });
    return result.ok
      ? { job: result.job, kind: 'reprocessed', ok: true }
      : result;
  }
  if (preflight?.status === 'created' || preflight?.status === 'processing') {
    return { job: preflight, kind: 'preflight_waiting', ok: true };
  }
  if (preflight?.status === 'failed') {
    const retried = await retryBrowserPageGeometryPreflight(api, preflight.id);
    return retried.ok
      ? { job: retried.data, kind: 'preflight_created', ok: true }
      : retried;
  }
  const prepared = await startBrowserPageGeometryPreflight(
    api,
    sourceSelectionId,
    sourceJob.gameId,
    pageRegistrationVariant,
    LATERAL_PARTIAL_VARIANT,
    sourceJob.id,
  );
  return prepared.ok
    ? { job: prepared.data.job, kind: 'preflight_created', ok: true }
    : prepared;
}
