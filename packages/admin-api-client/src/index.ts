import { createClient as createGeneratedClient } from './generated/client';
import {
  activateGridProfile as activateGeneratedGridProfile,
  activateSymbolModel as activateGeneratedSymbolModel,
  approveManualImageSelection as approveGeneratedManualImageSelection,
  continueImageSelectionWithoutImage as continueGeneratedImageSelectionWithoutImage,
  archiveDatasetVersion as archiveGeneratedDatasetVersion,
  archiveGame as archiveGeneratedGame,
  archivePayline as archiveGeneratedPayline,
  archivePayoutRule as archiveGeneratedPayoutRule,
  archiveRulesVersion as archiveGeneratedRulesVersion,
  archiveSymbol as archiveGeneratedSymbol,
  buildMobileRelease as buildGeneratedMobileRelease,
  cancelBrowserImageSelection as cancelGeneratedBrowserImageSelection,
  cancelJob as cancelGeneratedJob,
  createBrowserImageSelection as createGeneratedBrowserImageSelection,
  createGridCalibrationCandidate as createGeneratedGridCalibrationCandidate,
  createImageSelection as createGeneratedImageSelection,
  createImageFolderImport as createGeneratedImageFolderImport,
  createNextCuratedImageImportBatch as createGeneratedNextCuratedImageImportBatch,
  createJob as createGeneratedJob,
  createGame as createGeneratedGame,
  createImageDiagnosticExport as createGeneratedImageDiagnosticExport,
  createOperationalImageReviewGeometryRevision as createGeneratedOperationalImageReviewGeometryRevision,
  freezeVerifiedImageReviewCohort as freezeGeneratedVerifiedImageReviewCohort,
  freezeVerifiedTrainingCohort as freezeGeneratedVerifiedTrainingCohort,
  finalizeBrowserImageSelection as finalizeGeneratedBrowserImageSelection,
  createMobileRelease as createGeneratedMobileRelease,
  createReviewFeedbackExport as createGeneratedReviewFeedbackExport,
  downloadMobileReleaseApk as downloadGeneratedMobileReleaseApk,
  downloadImageDiagnosticExport as downloadGeneratedImageDiagnosticExport,
  createPayline as createGeneratedPayline,
  createPayoutRule as createGeneratedPayoutRule,
  createRulesDraftFromPublished as createGeneratedRulesDraftFromPublished,
  createRulesVersion as createGeneratedRulesVersion,
  createReviewerSession as createGeneratedReviewerSession,
  createSymbol as createGeneratedSymbol,
  createSymbolTraining as createGeneratedSymbolTraining,
  deleteMobileRelease as deleteGeneratedMobileRelease,
  generateMockDataset as generateGeneratedMockDataset,
  getDatasetValidationReport as getGeneratedDatasetValidationReport,
  getDatasetVersion as getGeneratedDatasetVersion,
  getGame as getGeneratedGame,
  getHealth as getGeneratedHealth,
  getImageJobOperations as getGeneratedImageJobOperations,
  getBrowserImageSelection as getGeneratedBrowserImageSelection,
  getCuratedImageImportSource as getGeneratedCuratedImageImportSource,
  getImageSelection as getGeneratedImageSelection,
  getImageSelectionOutput as getGeneratedImageSelectionOutput,
  getImageSelectionOutputFile as getGeneratedImageSelectionOutputFile,
  getImageSelectionSelectedGroupFile as getGeneratedImageSelectionSelectedGroupFile,
  getManualImageSelectionFile as getGeneratedManualImageSelectionFile,
  handoffImageSelection as handoffGeneratedImageSelection,
  getImageDatasetCompleteness as getGeneratedImageDatasetCompleteness,
  getImageSequenceSourceSelection as getGeneratedImageSequenceSourceSelection,
  getImageStorageInventory as getGeneratedImageStorageInventory,
  getJob as getGeneratedJob,
  getLayoutImportIntegrityReport as getGeneratedLayoutImportIntegrityReport,
  getMobileRelease as getGeneratedMobileRelease,
  getOperationalImageReviewBoardAsset as getGeneratedOperationalImageReviewBoardAsset,
  getOperationalImageReviewCellAsset as getGeneratedOperationalImageReviewCellAsset,
  getOperationalImageReviewItem as getGeneratedOperationalImageReviewItem,
  getOperationalImageReviewSourceAsset as getGeneratedOperationalImageReviewSourceAsset,
  getPayline as getGeneratedPayline,
  getPayoutRule as getGeneratedPayoutRule,
  getRulesPublicationReadiness as getGeneratedRulesPublicationReadiness,
  getRulesVersion as getGeneratedRulesVersion,
  getLatestSymbolBootstrap as getGeneratedLatestSymbolBootstrap,
  getModelQuality as getGeneratedModelQuality,
  getReviewItem as getGeneratedReviewItem,
  getReviewFeedbackExport as getGeneratedReviewFeedbackExport,
  getReviewerIngressStatus as getGeneratedReviewerIngressStatus,
  getSymbol as getGeneratedSymbol,
  getSymbolModelIteration as getGeneratedSymbolModelIteration,
  listGames as listGeneratedGames,
  listGridCalibrationProfiles as listGeneratedGridCalibrationProfiles,
  listGridProfileActivations as listGeneratedGridProfileActivations,
  listCuratedImageImportSources as listGeneratedCuratedImageImportSources,
  listImageDiagnosticExports as listGeneratedImageDiagnosticExports,
  listImageSelectionGroupCandidates as listGeneratedImageSelectionGroupCandidates,
  listImageSelectionGroups as listGeneratedImageSelectionGroups,
  listJobs as listGeneratedJobs,
  listWorkerLanes as listGeneratedWorkerLanes,
  listLayoutImportNormalizedRows as listGeneratedLayoutImportNormalizedRows,
  listMobileReleases as listGeneratedMobileReleases,
  listOperationalImageReviewItems as listGeneratedOperationalImageReviewItems,
  listOperationalImageReviewResolutionEvents as listGeneratedOperationalImageReviewResolutionEvents,
  listVerifiedImageReviewCohorts as listGeneratedVerifiedImageReviewCohorts,
  listDatasetLayouts as listGeneratedDatasetLayouts,
  listDatasetVersions as listGeneratedDatasetVersions,
  listPaylines as listGeneratedPaylines,
  listPayoutRules as listGeneratedPayoutRules,
  listRulesVersions as listGeneratedRulesVersions,
  listRulesVersionSymbols as listGeneratedRulesVersionSymbols,
  listReviewBatches as listGeneratedReviewBatches,
  listReviewFeedbackExports as listGeneratedReviewFeedbackExports,
  listReviewItems as listGeneratedReviewItems,
  listReviewResolutions as listGeneratedReviewResolutions,
  listSymbols as listGeneratedSymbols,
  listSymbolImageCandidates as listGeneratedSymbolImageCandidates,
  listSymbolModelIterations as listGeneratedSymbolModelIterations,
  listSymbolModelActivations as listGeneratedSymbolModelActivations,
  publishRulesVersion as publishGeneratedRulesVersion,
  registerCuratedImageImportSource as registerGeneratedCuratedImageImportSource,
  previewVerifiedTrainingCohort as previewGeneratedVerifiedTrainingCohort,
  previewGridProfileActivation as previewGeneratedGridProfileActivation,
  previewSymbolModelActivation as previewGeneratedSymbolModelActivation,
  previewGameLayoutDataReset as previewGeneratedGameLayoutDataReset,
  previewMobileReleaseDeletion as previewGeneratedMobileReleaseDeletion,
  previewOperationalImageReviewGeometry as previewGeneratedOperationalImageReviewGeometry,
  publishDatasetVersion as publishGeneratedDatasetVersion,
  publishLayoutImportDataset as publishGeneratedLayoutImportDataset,
  rejectLayoutImportStaging as rejectGeneratedLayoutImportStaging,
  retryJob as retryGeneratedJob,
  rollbackSymbolModel as rollbackGeneratedSymbolModel,
  rollbackGridProfile as rollbackGeneratedGridProfile,
  rerunImageSelection as rerunGeneratedImageSelection,
  resetGameLayoutData as resetGeneratedGameLayoutData,
  retryImageJobFile as retryGeneratedImageJobFile,
  revokeReviewerSession as revokeGeneratedReviewerSession,
  resolveReviewItem as resolveGeneratedReviewItem,
  resolveOperationalImageReviewItem as resolveGeneratedOperationalImageReviewItem,
  selectLocalImageFolder as selectGeneratedLocalImageFolder,
  selectImageSequenceSource as selectGeneratedImageSequenceSource,
  selectSymbolImageCandidate as selectGeneratedSymbolImageCandidate,
  resolveSymbolBootstrap as resolveGeneratedSymbolBootstrap,
  startSymbolBootstrap as startGeneratedSymbolBootstrap,
  startReviewerIngress as startGeneratedReviewerIngress,
  stopReviewerIngress as stopGeneratedReviewerIngress,
  updateGame as updateGeneratedGame,
  updatePayline as updateGeneratedPayline,
  updatePayoutRule as updateGeneratedPayoutRule,
  updateRulesVersion as updateGeneratedRulesVersion,
  updateRulesVersionSymbol as updateGeneratedRulesVersionSymbol,
  updateSymbol as updateGeneratedSymbol,
  uploadBrowserImageSelectionFile as uploadGeneratedBrowserImageSelectionFile,
  uploadManualImageSelectionFile as uploadGeneratedManualImageSelectionFile,
  unlockReviewerSession as unlockGeneratedReviewerSession,
} from './generated/sdk.gen';
import type {
  BrowserImageSelectionCreate,
  CreateJobData,
  GridProfileActivationAction,
  GridProfileActivationCommand,
  CreateSymbolTrainingCommand,
  CleanupCommandRequest,
  CuratedImageImportBatchCreate,
  CuratedImageImportSourceCreate,
  ImageJobFileRetryRequest,
  ImageFolderImportCreate,
  ImageSelectionCreate,
  ImageSelectionManualApprovalCommand,
  ImageSelectionMissingImageCommand,
  ImageSelectionGroupStatus,
  ImageSequenceSourceOverrideCommand,
  JobStatus,
  JobType,
  ImageReviewView,
  LayoutImportRowStatus,
  MockDatasetCreate,
  MobileReleaseCreate,
  OperationalImageReviewResolutionCommand,
  OperationalImageReviewGeometryCommand,
  OperationalImageReviewGeometryPreviewCommand,
  VerifiedCohortFreezeCommand,
  VerifiedTrainingCohortFreezeCommand,
  GameCreate,
  GameUpdate,
  PaylineCreate,
  PaylineUpdate,
  PayoutRuleCreate,
  PayoutRuleUpdate,
  RulesVersionCreate,
  RulesVersionSymbolUpdate,
  RulesVersionUpdate,
  ReviewItemStatus,
  ReviewFeedbackExportCreate,
  ReviewResolutionCommand,
  ReviewerIngressCommand,
  ReviewerSessionCreate,
  ReviewerSessionUnlock,
  ReviewerSessionUnlockResponse,
  SymbolCreate,
  SymbolBootstrapResolveCommand,
  SymbolBootstrapStartCommand,
  SymbolImageSelectionCommand,
  SymbolUpdate,
  SymbolModelActivationAction,
  SymbolModelActivationCommand,
  WorkerLaneStatusResponse,
} from './generated/types.gen';

export type {
  AndroidBuildJobCreate,
  AndroidBuildJobPayload,
  BrowserImageSelectionCreate,
  BrowserImageSelectionUploadResponse,
  CleanupCommandRequest,
  CleanupCountResponse,
  CleanupPreviewResponse,
  CleanupResultResponse,
  CuratedImageImportBatchResponse,
  CuratedImageImportJobPayload,
  CuratedImageImportSourceCreate,
  CuratedImageImportSourceResponse,
  DatasetLayoutPageResponse,
  DatasetLayoutResponse,
  DatasetVersionResponse,
  DatasetValidationCheckCode,
  DatasetValidationCheckResponse,
  DatasetValidationCheckStatus,
  DatasetValidationReportResponse,
  DuplicateSignatureGroupResponse,
  ErrorResponse,
  GameCreate,
  GameResponse,
  GameStatus,
  GameUpdate,
  CreateGridCalibrationCandidateResponse,
  GeometryCohortResponse,
  GridCalibrationProfileResponse,
  GridProfileActivationAction,
  GridProfileActivationCommand,
  GridProfileActivationCommandResponse,
  GridProfileActivationPreviewResponse,
  GridProfileActivationResponse,
  GridProfileJobSnapshotPayload,
  HealthResponse,
  ImportJobCreate,
  ImportJobPayload,
  ImageImportJobPayload,
  ImageFolderImportCreate,
  ImageFolderImportResponse,
  ImageFolderSelectionResponse,
  ImageSelectionCreate,
  ImageSelectionCreateResponse,
  ImageSelectionHandoffResponse,
  ImageSelectionGroupCandidatesResponse,
  ImageSelectionGroupPageResponse,
  ImageSelectionGroupResponse,
  ImageSelectionGroupStatus,
  ImageSelectionJobPayload,
  ImageSelectionRunResponse,
  ImageSelectionCandidateResponse,
  ImageSelectionManualApprovalCommand,
  ImageSelectionManualApprovalResponse,
  ImageSelectionManualDecisionResponse,
  ImageSelectionManualFileResponse,
  ImageSelectionMissingImageCommand,
  ImageSelectionOutputFileResponse,
  ImageSelectionOutputResponse,
  ImageDiagnosticExportCreationResponse,
  ImageDatasetCompletenessResponse,
  ImageDiagnosticExportResponse,
  ImageJobFileErrorResponse,
  ImageJobFileResponse,
  ImageJobFileRetryRequest,
  ImageJobOperationsResponse,
  ImageJobStageCountResponse,
  ImageStorageInventoryResponse,
  ImageStorageNamespaceResponse,
  ImageReviewAction,
  ImageReviewView,
  ImageSequenceSourceCandidateResponse,
  ImageSequenceSourceOverrideCommand,
  ImageSequenceSourceSelectionResponse,
  JobErrorResponse,
  JobProgressResponse,
  JobResponse,
  JobStatus,
  JobType,
  LayoutImportDuplicateSequenceGroupResponse,
  LayoutImportDuplicateSignatureGroupResponse,
  LayoutImportErrorCodeCountResponse,
  LayoutImportIntegrityCheckCode,
  LayoutImportIntegrityCheckResponse,
  LayoutImportIntegrityCheckStatus,
  LayoutImportIntegrityReportResponse,
  LayoutImportNormalizedRowPageResponse,
  LayoutImportNormalizedRowResponse,
  LayoutImportRowStatus,
  LayoutImportStagingRejectionResponse,
  LayoutImportValidateJobPayload,
  MockDatasetCreate,
  MobileReleaseApkResponse,
  MobileReleaseBuildResponse,
  MobileReleaseCreate,
  MobileReleaseGameCreate,
  MobileReleaseGameResponse,
  MobileReleaseResponse,
  MobileReleaseSnapshotResponse,
  MobileReleaseStatus,
  ModelQualityAdvisoryThresholdResponse,
  ModelQualityResponse,
  OperationalImageReviewAlternativeResponse,
  OperationalImageReviewCellResponse,
  OperationalImageReviewCountsResponse,
  OperationalImageReviewGeometryCellResponse,
  OperationalImageReviewGeometryCommand,
  OperationalImageReviewGeometryPoint,
  OperationalImageReviewGeometryPreviewCommand,
  OperationalImageReviewGeometryResponse,
  OperationalImageReviewGeometryRevisionResponse,
  OperationalImageReviewItemResponse,
  OperationalImageReviewPageResponse,
  OperationalImageReviewResolutionCell,
  OperationalImageReviewResolutionCommand,
  OperationalImageReviewResolutionEventResponse,
  OperationalImageReviewResolutionResponse,
  VerifiedCohortExportResponse,
  VerifiedCohortFreezeCommand,
  VerifiedCohortFreezeResponse,
  VerifiedTrainingCohortFreezeCommand,
  VerifiedTrainingCohortFreezeResponse,
  VerifiedTrainingCohortPreviewResponse,
  VerifiedTrainingCohortResponse,
  CreateSymbolTrainingCommand,
  CreateSymbolTrainingResponse,
  SymbolModelIterationResponse,
  SymbolModelActivationAction,
  SymbolModelActivationCommand,
  SymbolModelActivationCommandResponse,
  SymbolModelActivationPreviewResponse,
  SymbolModelActivationResponse,
  SymbolTrainingCoverageResponse,
  PaylineCreate,
  PaylineResponse,
  PaylineUpdate,
  PayoutRuleCreate,
  PayoutRuleResponse,
  PayoutRuleUpdate,
  PayoutJobCreate,
  PayoutJobPayload,
  RulesPublicationIssueResponse,
  RulesPublicationReadinessResponse,
  RulesVersionCreate,
  RulesVersionResponse,
  RulesVersionStatus,
  RulesVersionSymbolResponse,
  RulesVersionSymbolUpdate,
  RulesVersionUpdate,
  ReviewAlternative,
  ReviewBatchResponse,
  ReviewBoardSnapshot,
  ReviewCellSnapshot,
  ReviewItemPageResponse,
  ReviewItemResponse,
  ReviewItemStatus,
  ReviewFeedbackExportCreateResponse,
  ReviewFeedbackExportResponse,
  ReviewResolutionAction,
  ReviewResolutionCommand,
  ReviewResolutionCommandResponse,
  ReviewResolutionLabel,
  ReviewResolutionResponse,
  ReviewerIngressCommand,
  ReviewerIngressStatusResponse,
  ReviewerSessionCreate,
  ReviewerSessionCreatedResponse,
  ReviewerSessionScopeResponse,
  ReviewerSessionUnlock,
  ReviewerSessionUnlockResponse,
  SymbolCreate,
  SymbolBootstrapCandidateResponse,
  SymbolBootstrapDefinitionCommand,
  SymbolBootstrapDefinitionResponse,
  SymbolBootstrapResolveCommand,
  SymbolBootstrapRunResponse,
  SymbolBootstrapStartCommand,
  SymbolBootstrapStatus,
  SymbolImageCandidatePageResponse,
  SymbolImageCandidateResponse,
  SymbolImageSelectionCommand,
  SymbolResponse,
  SymbolStatus,
  SymbolUpdate,
  WorkerLaneStatusResponse,
  SnapshotJobCreate,
  SnapshotJobPayload,
  ValidateJobCreate,
  ValidateJobPayload,
} from './generated/types.gen';

export interface AdminApiClientOptions {
  readonly baseUrl: string;
  readonly fetch?: typeof globalThis.fetch;
}

export type JobCreate = CreateJobData['body'];

export interface ListJobsOptions {
  readonly status?: JobStatus;
  readonly jobType?: JobType;
  readonly gameId?: string;
  readonly limit?: number;
}

export interface ListLayoutImportRowsOptions {
  readonly afterLineNumber?: number;
  readonly limit?: number;
  readonly status?: LayoutImportRowStatus;
  readonly errorCode?: string;
}

export interface ListReviewItemsOptions {
  readonly status?: ReviewItemStatus;
  readonly afterSelectionRank?: number;
  readonly limit?: number;
}

export interface OperationalImageReviewContext {
  readonly gameId: string;
  readonly importJobId: string;
}

export interface ListOperationalImageReviewItemsOptions extends OperationalImageReviewContext {
  readonly view?: ImageReviewView;
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly resumeAtFirstPending?: boolean;
  readonly sequenceNumber?: number;
  readonly limit?: number;
}

export interface ListVerifiedImageReviewCohortsOptions extends OperationalImageReviewContext {
  readonly limit?: number;
}

export function createAdminApiClient(options: AdminApiClientOptions) {
  const client = createGeneratedClient({
    baseUrl: options.baseUrl,
    headers: { 'X-Admin-Intent': 'local-owner' },
    ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
  });

  const confirmedTargetHeaders = (
    target: string,
  ): {
    'X-Admin-Confirmation': 'confirmed';
    'X-Admin-Target': string;
  } => ({
    'X-Admin-Confirmation': 'confirmed',
    'X-Admin-Target': target,
  });

  return {
    getHealth: () => getGeneratedHealth({ client }),
    getReviewerIngressStatus: () =>
      getGeneratedReviewerIngressStatus({ client }),
    startReviewerIngress: (body: ReviewerIngressCommand) =>
      startGeneratedReviewerIngress({
        body,
        client,
        headers: confirmedTargetHeaders('remote-reviewer'),
      }),
    stopReviewerIngress: (body: ReviewerIngressCommand) =>
      stopGeneratedReviewerIngress({
        body,
        client,
        headers: confirmedTargetHeaders('remote-reviewer'),
      }),
    createReviewerSession: (body: ReviewerSessionCreate) =>
      createGeneratedReviewerSession({
        body,
        client,
        headers: confirmedTargetHeaders('reviewer-session:new'),
      }),
    revokeReviewerSession: (sessionId: string) =>
      revokeGeneratedReviewerSession({
        client,
        headers: confirmedTargetHeaders(`reviewer-session:${sessionId}`),
        path: { session_id: sessionId },
      }),
    unlockReviewerSession: (sessionId: string, body: ReviewerSessionUnlock) =>
      unlockGeneratedReviewerSession({
        body,
        client,
        path: { session_id: sessionId },
      }),
    createJob: (body: JobCreate) =>
      createGeneratedJob({
        body,
        client,
        headers: confirmedTargetHeaders('job:new'),
      }),
    selectLocalImageFolder: () =>
      selectGeneratedLocalImageFolder({
        client,
        headers: confirmedTargetHeaders('image-folder:select'),
      }),
    createBrowserImageSelection: (body: BrowserImageSelectionCreate) =>
      createGeneratedBrowserImageSelection({ body, client }),
    getBrowserImageSelection: (uploadId: string) =>
      getGeneratedBrowserImageSelection({
        client,
        path: { upload_id: uploadId },
      }),
    uploadBrowserImageSelectionFile: (
      uploadId: string,
      fileIndex: number,
      relativePath: string,
      file: Blob | File,
    ) =>
      uploadGeneratedBrowserImageSelectionFile({
        body: file,
        client,
        headers: { 'X-Image-Relative-Path': relativePath },
        path: { file_index: fileIndex, upload_id: uploadId },
      }),
    finalizeBrowserImageSelection: (uploadId: string) =>
      finalizeGeneratedBrowserImageSelection({
        client,
        path: { upload_id: uploadId },
      }),
    cancelBrowserImageSelection: (uploadId: string) =>
      cancelGeneratedBrowserImageSelection({
        client,
        path: { upload_id: uploadId },
      }),
    createImageSelection: (body: ImageSelectionCreate) =>
      createGeneratedImageSelection({ body, client }),
    getImageSelection: (
      runId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      getGeneratedImageSelection({
        client,
        path: { run_id: runId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    rerunImageSelection: (runId: string) =>
      rerunGeneratedImageSelection({
        client,
        path: { run_id: runId },
      }),
    getImageSelectionOutput: (runId: string) =>
      getGeneratedImageSelectionOutput({
        client,
        path: { run_id: runId },
      }),
    getImageSelectionOutputFile: (runId: string, fileName: string) =>
      getGeneratedImageSelectionOutputFile({
        client,
        path: { file_name: fileName, run_id: runId },
      }),
    getImageSelectionSelectedGroupFile: (runId: string, groupId: string) =>
      getGeneratedImageSelectionSelectedGroupFile({
        client,
        path: { group_id: groupId, run_id: runId },
      }),
    handoffImageSelection: (runId: string) =>
      handoffGeneratedImageSelection({
        client,
        path: { run_id: runId },
      }),
    listImageSelectionGroups: (
      runId: string,
      options: {
        readonly status?: ImageSelectionGroupStatus;
        readonly afterGroupOrder?: number;
        readonly limit?: number;
      } = {},
    ) =>
      listGeneratedImageSelectionGroups({
        client,
        path: { run_id: runId },
        query: {
          ...(options.status === undefined ? {} : { status: options.status }),
          ...(options.afterGroupOrder === undefined
            ? {}
            : { afterGroupOrder: options.afterGroupOrder }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    listImageSelectionGroupCandidates: (
      runId: string,
      groupId: string,
      options: { readonly limit?: number } = {},
    ) =>
      listGeneratedImageSelectionGroupCandidates({
        client,
        path: { group_id: groupId, run_id: runId },
        query: {
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    uploadManualImageSelectionFile: (
      runId: string,
      groupId: string,
      fileName: string,
      file: Blob | File,
    ) =>
      uploadGeneratedManualImageSelectionFile({
        body: file,
        client,
        headers: {
          ...confirmedTargetHeaders(
            `image-selection:${runId}:${groupId}:manual-file`,
          ),
          'X-Image-File-Name': fileName,
        },
        path: { group_id: groupId, run_id: runId },
      }),
    getManualImageSelectionFile: (
      runId: string,
      groupId: string,
      candidateId: string,
    ) =>
      getGeneratedManualImageSelectionFile({
        client,
        path: {
          candidate_id: candidateId,
          group_id: groupId,
          run_id: runId,
        },
      }),
    approveManualImageSelection: (
      runId: string,
      groupId: string,
      body: ImageSelectionManualApprovalCommand,
    ) =>
      approveGeneratedManualImageSelection({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:approve`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    continueImageSelectionWithoutImage: (
      runId: string,
      groupId: string,
      body: ImageSelectionMissingImageCommand,
    ) =>
      continueGeneratedImageSelectionWithoutImage({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:missing-image`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    createImageFolderImport: (body: ImageFolderImportCreate) =>
      createGeneratedImageFolderImport({
        body,
        client,
        headers: confirmedTargetHeaders(`image-import:${body.gameId}`),
      }),
    registerCuratedImageImportSource: (body: CuratedImageImportSourceCreate) =>
      registerGeneratedCuratedImageImportSource({
        body,
        client,
        headers: confirmedTargetHeaders(
          `curated-image-import:${body.imageSelectionRunId}`,
        ),
      }),
    listCuratedImageImportSources: (gameId: string) =>
      listGeneratedCuratedImageImportSources({
        client,
        query: { gameId },
      }),
    getCuratedImageImportSource: (sourceId: string) =>
      getGeneratedCuratedImageImportSource({
        client,
        path: { source_id: sourceId },
      }),
    createNextCuratedImageImportBatch: (
      sourceId: string,
      body: CuratedImageImportBatchCreate,
    ) =>
      createGeneratedNextCuratedImageImportBatch({
        body,
        client,
        headers: confirmedTargetHeaders(
          `curated-image-import:${sourceId}:next-batch`,
        ),
        path: { source_id: sourceId },
      }),
    listJobs: (filters: ListJobsOptions = {}) =>
      listGeneratedJobs({
        client,
        query: {
          ...(filters.status === undefined ? {} : { status: filters.status }),
          ...(filters.jobType === undefined
            ? {}
            : { job_type: filters.jobType }),
          ...(filters.gameId === undefined ? {} : { game_id: filters.gameId }),
          ...(filters.limit === undefined ? {} : { limit: filters.limit }),
        },
      }),
    listWorkerLanes: () => listGeneratedWorkerLanes({ client }),
    getJob: (jobId: string) =>
      getGeneratedJob({ client, path: { job_id: jobId } }),
    cancelJob: (jobId: string) =>
      cancelGeneratedJob({
        client,
        headers: confirmedTargetHeaders(`job:${jobId}`),
        path: { job_id: jobId },
      }),
    retryJob: (jobId: string) =>
      retryGeneratedJob({ client, path: { job_id: jobId } }),
    getImageJobOperations: (jobId: string, fileLimit = 100) =>
      getGeneratedImageJobOperations({
        client,
        path: { job_id: jobId },
        query: { file_limit: fileLimit },
      }),
    retryImageJobFile: (
      jobId: string,
      fileExecutionKey: string,
      body: ImageJobFileRetryRequest,
      fileLimit = 100,
    ) =>
      retryGeneratedImageJobFile({
        body,
        client,
        path: {
          file_execution_key: fileExecutionKey,
          job_id: jobId,
        },
        query: { file_limit: fileLimit },
      }),
    getImageStorageInventory: () =>
      getGeneratedImageStorageInventory({ client }),
    getLatestSymbolBootstrap: (gameId: string) =>
      getGeneratedLatestSymbolBootstrap({
        client,
        path: { game_id: gameId },
      }),
    startSymbolBootstrap: (gameId: string, body: SymbolBootstrapStartCommand) =>
      startGeneratedSymbolBootstrap({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-bootstrap:${gameId}`),
        path: { game_id: gameId },
      }),
    resolveSymbolBootstrap: (
      gameId: string,
      bootstrapId: string,
      body: SymbolBootstrapResolveCommand,
    ) =>
      resolveGeneratedSymbolBootstrap({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-bootstrap:${bootstrapId}`),
        path: { bootstrap_id: bootstrapId, game_id: gameId },
      }),
    listSymbolImageCandidates: (
      gameId: string,
      symbolId: string,
      afterCursor?: string,
    ) =>
      listGeneratedSymbolImageCandidates({
        client,
        path: { game_id: gameId, symbol_id: symbolId },
        query: {
          limit: 10,
          ...(afterCursor === undefined ? {} : { afterCursor }),
        },
      }),
    symbolImageCandidateAssetUrl: (
      gameId: string,
      symbolId: string,
      observationId: string,
    ) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbols/${encodeURIComponent(symbolId)}/image-candidates/${encodeURIComponent(observationId)}/asset`,
    symbolImageAssetUrl: (gameId: string, symbolId: string) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbols/${encodeURIComponent(symbolId)}/image/asset`,
    selectSymbolImageCandidate: (
      gameId: string,
      symbolId: string,
      observationId: string,
      body: SymbolImageSelectionCommand,
    ) =>
      selectGeneratedSymbolImageCandidate({
        body,
        client,
        headers: confirmedTargetHeaders(
          `symbol-image:${gameId}:${symbolId}:${observationId}`,
        ),
        path: {
          game_id: gameId,
          observation_id: observationId,
          symbol_id: symbolId,
        },
      }),
    getImageDatasetCompleteness: (gameId: string) =>
      getGeneratedImageDatasetCompleteness({
        client,
        path: { game_id: gameId },
      }),
    getImageSequenceSourceSelection: (gameId: string, sequenceNumber: number) =>
      getGeneratedImageSequenceSourceSelection({
        client,
        path: { game_id: gameId, sequence_number: sequenceNumber },
      }),
    selectImageSequenceSource: (
      gameId: string,
      sequenceNumber: number,
      body: ImageSequenceSourceOverrideCommand,
    ) =>
      selectGeneratedImageSequenceSource({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-sequence-source:${gameId}:${sequenceNumber}`,
        ),
        path: { game_id: gameId, sequence_number: sequenceNumber },
      }),
    listOperationalImageReviewItems: (
      filters: ListOperationalImageReviewItemsOptions,
    ) =>
      listGeneratedOperationalImageReviewItems({
        client,
        query: {
          gameId: filters.gameId,
          importJobId: filters.importJobId,
          ...(filters.view === undefined ? {} : { view: filters.view }),
          ...(filters.afterCursor === undefined
            ? {}
            : { afterCursor: filters.afterCursor }),
          ...(filters.beforeCursor === undefined
            ? {}
            : { beforeCursor: filters.beforeCursor }),
          ...(filters.resumeAtFirstPending === undefined
            ? {}
            : { resumeAtFirstPending: filters.resumeAtFirstPending }),
          ...(filters.sequenceNumber === undefined
            ? {}
            : { sequenceNumber: filters.sequenceNumber }),
          ...(filters.limit === undefined ? {} : { limit: filters.limit }),
        },
      }),
    listVerifiedImageReviewCohorts: (
      filters: ListVerifiedImageReviewCohortsOptions,
    ) =>
      listGeneratedVerifiedImageReviewCohorts({
        client,
        query: {
          gameId: filters.gameId,
          importJobId: filters.importJobId,
          ...(filters.limit === undefined ? {} : { limit: filters.limit }),
        },
      }),
    freezeVerifiedImageReviewCohort: (
      context: OperationalImageReviewContext,
      body: VerifiedCohortFreezeCommand,
    ) =>
      freezeGeneratedVerifiedImageReviewCohort({
        body,
        client,
        query: context,
      }),
    getModelQuality: (
      gameId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      getGeneratedModelQuality({
        client,
        path: { game_id: gameId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    previewVerifiedTrainingCohort: (
      gameId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      previewGeneratedVerifiedTrainingCohort({
        client,
        path: { game_id: gameId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    freezeVerifiedTrainingCohort: (
      gameId: string,
      body: VerifiedTrainingCohortFreezeCommand,
    ) =>
      freezeGeneratedVerifiedTrainingCohort({
        body,
        client,
        headers: confirmedTargetHeaders(`verified-training-cohort:${gameId}`),
        path: { game_id: gameId },
      }),
    createSymbolTraining: (gameId: string, body: CreateSymbolTrainingCommand) =>
      createGeneratedSymbolTraining({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-model-iteration:${gameId}`),
        path: { game_id: gameId },
      }),
    listSymbolModelIterations: (
      gameId: string,
      options: { readonly limit?: number; readonly signal?: AbortSignal } = {},
    ) =>
      listGeneratedSymbolModelIterations({
        client,
        path: { game_id: gameId },
        query: { limit: options.limit ?? 50 },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    getSymbolModelIteration: (
      gameId: string,
      iterationId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      getGeneratedSymbolModelIteration({
        client,
        path: { game_id: gameId, iteration_id: iterationId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    listSymbolModelActivations: (
      gameId: string,
      options: { readonly limit?: number; readonly signal?: AbortSignal } = {},
    ) =>
      listGeneratedSymbolModelActivations({
        client,
        path: { game_id: gameId },
        query: { limit: options.limit ?? 50 },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    previewSymbolModelActivation: (
      gameId: string,
      iterationId: string,
      action: SymbolModelActivationAction,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      previewGeneratedSymbolModelActivation({
        client,
        path: { game_id: gameId, iteration_id: iterationId },
        query: { action },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    activateSymbolModel: (
      gameId: string,
      iterationId: string,
      body: SymbolModelActivationCommand,
    ) =>
      activateGeneratedSymbolModel({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-model-activation:${gameId}`),
        path: { game_id: gameId, iteration_id: iterationId },
      }),
    rollbackSymbolModel: (
      gameId: string,
      iterationId: string,
      body: SymbolModelActivationCommand,
    ) =>
      rollbackGeneratedSymbolModel({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-model-rollback:${gameId}`),
        path: { game_id: gameId, iteration_id: iterationId },
      }),
    createGridCalibrationCandidate: (gameId: string) =>
      createGeneratedGridCalibrationCandidate({
        client,
        headers: confirmedTargetHeaders(`grid-calibration-candidate:${gameId}`),
        path: { game_id: gameId },
      }),
    listGridCalibrationProfiles: (
      gameId: string,
      options: { readonly limit?: number; readonly signal?: AbortSignal } = {},
    ) =>
      listGeneratedGridCalibrationProfiles({
        client,
        path: { game_id: gameId },
        query: { limit: options.limit ?? 50 },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    listGridProfileActivations: (
      gameId: string,
      options: { readonly limit?: number; readonly signal?: AbortSignal } = {},
    ) =>
      listGeneratedGridProfileActivations({
        client,
        path: { game_id: gameId },
        query: { limit: options.limit ?? 50 },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    previewGridProfileActivation: (
      gameId: string,
      profileId: string,
      action: GridProfileActivationAction,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      previewGeneratedGridProfileActivation({
        client,
        path: { game_id: gameId, profile_id: profileId },
        query: { action },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    activateGridProfile: (
      gameId: string,
      profileId: string,
      body: GridProfileActivationCommand,
    ) =>
      activateGeneratedGridProfile({
        body,
        client,
        headers: confirmedTargetHeaders(`grid-profile-activation:${gameId}`),
        path: { game_id: gameId, profile_id: profileId },
      }),
    rollbackGridProfile: (
      gameId: string,
      profileId: string,
      body: GridProfileActivationCommand,
    ) =>
      rollbackGeneratedGridProfile({
        body,
        client,
        headers: confirmedTargetHeaders(`grid-profile-rollback:${gameId}`),
        path: { game_id: gameId, profile_id: profileId },
      }),
    getOperationalImageReviewItem: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedOperationalImageReviewItem({
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    getOperationalImageReviewSourceAsset: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedOperationalImageReviewSourceAsset({
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    getOperationalImageReviewBoardAsset: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedOperationalImageReviewBoardAsset({
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    getOperationalImageReviewCellAsset: (
      reviewItemId: string,
      cellIndex: number,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedOperationalImageReviewCellAsset({
        client,
        path: { cell_index: cellIndex, review_item_id: reviewItemId },
        query: context,
      }),
    previewOperationalImageReviewGeometry: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
      body: OperationalImageReviewGeometryPreviewCommand,
    ) =>
      previewGeneratedOperationalImageReviewGeometry({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    createOperationalImageReviewGeometryRevision: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
      body: OperationalImageReviewGeometryCommand,
    ) =>
      createGeneratedOperationalImageReviewGeometryRevision({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    resolveOperationalImageReviewItem: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
      body: OperationalImageReviewResolutionCommand,
    ) =>
      resolveGeneratedOperationalImageReviewItem({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    listOperationalImageReviewResolutionEvents: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
    ) =>
      listGeneratedOperationalImageReviewResolutionEvents({
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    createImageDiagnosticExport: (jobId: string) =>
      createGeneratedImageDiagnosticExport({
        client,
        path: { job_id: jobId },
      }),
    listImageDiagnosticExports: (jobId: string) =>
      listGeneratedImageDiagnosticExports({
        client,
        path: { job_id: jobId },
      }),
    downloadImageDiagnosticExport: (jobId: string, checksumSha256: string) =>
      downloadGeneratedImageDiagnosticExport({
        client,
        path: {
          checksum_sha256: checksumSha256,
          job_id: jobId,
        },
      }),
    getLayoutImportIntegrityReport: (validationJobId: string) =>
      getGeneratedLayoutImportIntegrityReport({
        client,
        path: { validation_job_id: validationJobId },
      }),
    listLayoutImportNormalizedRows: (
      validationJobId: string,
      options: ListLayoutImportRowsOptions = {},
    ) =>
      listGeneratedLayoutImportNormalizedRows({
        client,
        path: { validation_job_id: validationJobId },
        query: {
          ...(options.afterLineNumber === undefined
            ? {}
            : { after_line_number: options.afterLineNumber }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
          ...(options.status === undefined ? {} : { status: options.status }),
          ...(options.errorCode === undefined
            ? {}
            : { error_code: options.errorCode }),
        },
      }),
    rejectLayoutImportStaging: (validationJobId: string) =>
      rejectGeneratedLayoutImportStaging({
        client,
        headers: confirmedTargetHeaders(`validation-job:${validationJobId}`),
        path: { validation_job_id: validationJobId },
      }),
    publishLayoutImportDataset: (validationJobId: string) =>
      publishGeneratedLayoutImportDataset({
        client,
        headers: confirmedTargetHeaders(`validation-job:${validationJobId}`),
        path: { validation_job_id: validationJobId },
      }),
    listMobileReleases: () => listGeneratedMobileReleases({ client }),
    createMobileRelease: (body: MobileReleaseCreate) =>
      createGeneratedMobileRelease({
        body,
        client,
        headers: confirmedTargetHeaders('mobile-release:new'),
      }),
    getMobileRelease: (mobileReleaseId: string) =>
      getGeneratedMobileRelease({
        client,
        path: { mobile_release_id: mobileReleaseId },
      }),
    previewMobileReleaseDeletion: (mobileReleaseId: string) =>
      previewGeneratedMobileReleaseDeletion({
        client,
        path: { mobile_release_id: mobileReleaseId },
      }),
    deleteMobileRelease: (
      mobileReleaseId: string,
      body: CleanupCommandRequest,
    ) =>
      deleteGeneratedMobileRelease({
        body,
        client,
        headers: confirmedTargetHeaders(`mobile-release:${mobileReleaseId}`),
        path: { mobile_release_id: mobileReleaseId },
      }),
    downloadMobileReleaseApk: (mobileReleaseId: string) =>
      downloadGeneratedMobileReleaseApk({
        client,
        path: { mobile_release_id: mobileReleaseId },
      }),
    buildMobileRelease: (mobileReleaseId: string) =>
      buildGeneratedMobileRelease({
        client,
        headers: confirmedTargetHeaders(`mobile-release:${mobileReleaseId}`),
        path: { mobile_release_id: mobileReleaseId },
      }),
    listReviewBatches: () => listGeneratedReviewBatches({ client }),
    listReviewItems: (
      reviewBatchId: string,
      options: ListReviewItemsOptions = {},
    ) =>
      listGeneratedReviewItems({
        client,
        path: { review_batch_id: reviewBatchId },
        query: {
          ...(options.status === undefined ? {} : { status: options.status }),
          ...(options.afterSelectionRank === undefined
            ? {}
            : { after_selection_rank: options.afterSelectionRank }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    getReviewItem: (reviewItemId: string) =>
      getGeneratedReviewItem({
        client,
        path: { review_item_id: reviewItemId },
      }),
    resolveReviewItem: (reviewItemId: string, body: ReviewResolutionCommand) =>
      resolveGeneratedReviewItem({
        body,
        client,
        path: { review_item_id: reviewItemId },
      }),
    listReviewResolutions: (reviewItemId: string) =>
      listGeneratedReviewResolutions({
        client,
        path: { review_item_id: reviewItemId },
      }),
    createReviewFeedbackExport: (
      reviewBatchId: string,
      body: ReviewFeedbackExportCreate,
    ) =>
      createGeneratedReviewFeedbackExport({
        body,
        client,
        path: { review_batch_id: reviewBatchId },
      }),
    listReviewFeedbackExports: (reviewBatchId: string) =>
      listGeneratedReviewFeedbackExports({
        client,
        path: { review_batch_id: reviewBatchId },
      }),
    getReviewFeedbackExport: (feedbackExportId: string) =>
      getGeneratedReviewFeedbackExport({
        client,
        path: { feedback_export_id: feedbackExportId },
      }),
    listGames: () => listGeneratedGames({ client }),
    previewGameLayoutDataReset: (gameId: string) =>
      previewGeneratedGameLayoutDataReset({
        client,
        path: { game_id: gameId },
      }),
    resetGameLayoutData: (gameId: string, body: CleanupCommandRequest) =>
      resetGeneratedGameLayoutData({
        body,
        client,
        headers: confirmedTargetHeaders(`game-layout-data:${gameId}`),
        path: { game_id: gameId },
      }),
    createGame: (body: GameCreate) => createGeneratedGame({ body, client }),
    getGame: (gameId: string) =>
      getGeneratedGame({ client, path: { game_id: gameId } }),
    updateGame: (gameId: string, body: GameUpdate) =>
      updateGeneratedGame({ body, client, path: { game_id: gameId } }),
    archiveGame: (gameId: string) =>
      archiveGeneratedGame({
        client,
        headers: confirmedTargetHeaders(`game:${gameId}`),
        path: { game_id: gameId },
      }),
    listRulesVersions: (gameId: string) =>
      listGeneratedRulesVersions({ client, path: { game_id: gameId } }),
    createRulesVersion: (gameId: string, body: RulesVersionCreate) =>
      createGeneratedRulesVersion({
        body,
        client,
        path: { game_id: gameId },
      }),
    createRulesDraftFromPublished: (rulesVersionId: string) =>
      createGeneratedRulesDraftFromPublished({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getRulesVersion: (rulesVersionId: string) =>
      getGeneratedRulesVersion({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    updateRulesVersion: (rulesVersionId: string, body: RulesVersionUpdate) =>
      updateGeneratedRulesVersion({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getRulesPublicationReadiness: (rulesVersionId: string) =>
      getGeneratedRulesPublicationReadiness({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    publishRulesVersion: (rulesVersionId: string) =>
      publishGeneratedRulesVersion({
        client,
        headers: confirmedTargetHeaders(`rules-version:${rulesVersionId}`),
        path: { rules_version_id: rulesVersionId },
      }),
    archiveRulesVersion: (rulesVersionId: string) =>
      archiveGeneratedRulesVersion({
        client,
        headers: confirmedTargetHeaders(`rules-version:${rulesVersionId}`),
        path: { rules_version_id: rulesVersionId },
      }),
    listDatasetVersions: (gameId: string) =>
      listGeneratedDatasetVersions({
        client,
        path: { game_id: gameId },
      }),
    generateMockDataset: (gameId: string, body: MockDatasetCreate) =>
      generateGeneratedMockDataset({
        body,
        client,
        path: { game_id: gameId },
      }),
    getDatasetVersion: (datasetVersionId: string) =>
      getGeneratedDatasetVersion({
        client,
        path: { dataset_version_id: datasetVersionId },
      }),
    getDatasetValidationReport: (datasetVersionId: string) =>
      getGeneratedDatasetValidationReport({
        client,
        path: { dataset_version_id: datasetVersionId },
      }),
    listDatasetLayouts: (
      datasetVersionId: string,
      afterSequenceNumber = 0,
      limit = 25,
    ) =>
      listGeneratedDatasetLayouts({
        client,
        path: { dataset_version_id: datasetVersionId },
        query: {
          after_sequence_number: afterSequenceNumber,
          limit,
        },
      }),
    publishDatasetVersion: (datasetVersionId: string) =>
      publishGeneratedDatasetVersion({
        client,
        headers: confirmedTargetHeaders(`dataset-version:${datasetVersionId}`),
        path: { dataset_version_id: datasetVersionId },
      }),
    archiveDatasetVersion: (datasetVersionId: string) =>
      archiveGeneratedDatasetVersion({
        client,
        headers: confirmedTargetHeaders(`dataset-version:${datasetVersionId}`),
        path: { dataset_version_id: datasetVersionId },
      }),
    listPaylines: (rulesVersionId: string) =>
      listGeneratedPaylines({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    createPayline: (rulesVersionId: string, body: PaylineCreate) =>
      createGeneratedPayline({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getPayline: (rulesVersionId: string, paylineId: string) =>
      getGeneratedPayline({
        client,
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    updatePayline: (
      rulesVersionId: string,
      paylineId: string,
      body: PaylineUpdate,
    ) =>
      updateGeneratedPayline({
        body,
        client,
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    archivePayline: (rulesVersionId: string, paylineId: string) =>
      archiveGeneratedPayline({
        client,
        headers: confirmedTargetHeaders(`payline:${paylineId}`),
        path: {
          payline_id: paylineId,
          rules_version_id: rulesVersionId,
        },
      }),
    listRulesVersionSymbols: (rulesVersionId: string) =>
      listGeneratedRulesVersionSymbols({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    updateRulesVersionSymbol: (
      rulesVersionId: string,
      symbolId: string,
      body: RulesVersionSymbolUpdate,
    ) =>
      updateGeneratedRulesVersionSymbol({
        body,
        client,
        path: {
          rules_version_id: rulesVersionId,
          symbol_id: symbolId,
        },
      }),
    listPayoutRules: (rulesVersionId: string) =>
      listGeneratedPayoutRules({
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    createPayoutRule: (rulesVersionId: string, body: PayoutRuleCreate) =>
      createGeneratedPayoutRule({
        body,
        client,
        path: { rules_version_id: rulesVersionId },
      }),
    getPayoutRule: (rulesVersionId: string, payoutRuleId: string) =>
      getGeneratedPayoutRule({
        client,
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    updatePayoutRule: (
      rulesVersionId: string,
      payoutRuleId: string,
      body: PayoutRuleUpdate,
    ) =>
      updateGeneratedPayoutRule({
        body,
        client,
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    archivePayoutRule: (rulesVersionId: string, payoutRuleId: string) =>
      archiveGeneratedPayoutRule({
        client,
        headers: confirmedTargetHeaders(`payout-rule:${payoutRuleId}`),
        path: {
          payout_rule_id: payoutRuleId,
          rules_version_id: rulesVersionId,
        },
      }),
    listSymbols: (gameId: string) =>
      listGeneratedSymbols({ client, path: { game_id: gameId } }),
    createSymbol: (gameId: string, body: SymbolCreate) =>
      createGeneratedSymbol({
        body,
        client,
        path: { game_id: gameId },
      }),
    getSymbol: (gameId: string, symbolId: string) =>
      getGeneratedSymbol({
        client,
        path: { game_id: gameId, symbol_id: symbolId },
      }),
    updateSymbol: (gameId: string, symbolId: string, body: SymbolUpdate) =>
      updateGeneratedSymbol({
        body,
        client,
        path: { game_id: gameId, symbol_id: symbolId },
      }),
    archiveSymbol: (gameId: string, symbolId: string) =>
      archiveGeneratedSymbol({
        client,
        headers: confirmedTargetHeaders(`symbol:${symbolId}`),
        path: { game_id: gameId, symbol_id: symbolId },
      }),
  } as const;
}

export type AdminApiClient = ReturnType<typeof createAdminApiClient>;
