import { createClient as createGeneratedClient } from './generated/client';
import {
  acknowledgeSemiAutomaticImageSelectionOutput as acknowledgeGeneratedSemiAutomaticImageSelectionOutput,
  activateGridProfile as activateGeneratedGridProfile,
  activateSymbolModel as activateGeneratedSymbolModel,
  applySymbolCellReviewDecision as applyGeneratedSymbolCellReviewDecision,
  approveImageGridReviewGeometry as approveGeneratedImageGridReviewGeometry,
  approveImageGridReviewSourceGeometry as approveGeneratedImageGridReviewSourceGeometry,
  approveManualImageSelection as approveGeneratedManualImageSelection,
  continueImageSelectionWithoutImage as continueGeneratedImageSelectionWithoutImage,
  confirmImageSelectionGroupRange as confirmGeneratedImageSelectionGroupRange,
  discardDuplicateImageSelectionGroup as discardGeneratedDuplicateImageSelectionGroup,
  archiveDatasetVersion as archiveGeneratedDatasetVersion,
  archiveGame as archiveGeneratedGame,
  archivePayline as archiveGeneratedPayline,
  archivePayoutRule as archiveGeneratedPayoutRule,
  archiveRulesVersion as archiveGeneratedRulesVersion,
  deleteSymbol as deleteGeneratedSymbol,
  buildMobileRelease as buildGeneratedMobileRelease,
  closeReviewerWorkAssignment as closeGeneratedReviewerWorkAssignment,
  cancelBrowserImageSelection as cancelGeneratedBrowserImageSelection,
  cancelSemiAutomaticImageSelection as cancelGeneratedSemiAutomaticImageSelection,
  cancelJob as cancelGeneratedJob,
  createBrowserImageSelection as createGeneratedBrowserImageSelection,
  planBrowserImageSelectionUpload as planGeneratedBrowserImageSelectionUpload,
  createBrowserPageGeometryOverride as createGeneratedBrowserPageGeometryOverride,
  createImageGeometryGuardDecisions as createGeneratedImageGeometryGuardDecisions,
  previewImageGeometryGuardDecision as previewGeneratedImageGeometryGuardDecision,
  listImageGeometryGuardBoards as listGeneratedImageGeometryGuardBoards,
  sealImageGeometryGuardResolutionManifest as sealGeneratedImageGeometryGuardResolutionManifest,
  startImageGeometryGuardReportReconstruction as startGeneratedImageGeometryGuardReportReconstruction,
  listReadyBrowserImageSelections as listGeneratedReadyBrowserImageSelections,
  previewReadyBrowserImageImport as previewGeneratedReadyBrowserImageImport,
  startReadyBrowserImageImport as startGeneratedReadyBrowserImageImport,
  startBrowserPageGeometryPreflight as startGeneratedBrowserPageGeometryPreflight,
  createGridCalibrationCandidate as createGeneratedGridCalibrationCandidate,
  createImageSelection as createGeneratedImageSelection,
  createImageFolderImport as createGeneratedImageFolderImport,
  createImageGridReviewGeometryRevision as createGeneratedImageGridReviewGeometryRevision,
  createImageGridReviewSourceGeometryRevision as createGeneratedImageGridReviewSourceGeometryRevision,
  createSymbolCellPreviewBatch as createGeneratedSymbolCellPreviewBatch,
  createVirtualCellPreviewBatch as createGeneratedVirtualCellPreviewBatch,
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
  createSemiAutomaticImageSelection as createGeneratedSemiAutomaticImageSelection,
  decideSemiAutomaticFilenameRangeVerification as decideGeneratedSemiAutomaticFilenameRangeVerification,
  downloadMobileReleaseApk as downloadGeneratedMobileReleaseApk,
  downloadImageDiagnosticExport as downloadGeneratedImageDiagnosticExport,
  createPayline as createGeneratedPayline,
  createPayoutRule as createGeneratedPayoutRule,
  createRulesDraftFromPublished as createGeneratedRulesDraftFromPublished,
  createRulesVersion as createGeneratedRulesVersion,
  createReviewerSession as createGeneratedReviewerSession,
  createRemoteManualSelectionSession as createGeneratedRemoteManualSelectionSession,
  createSymbol as createGeneratedSymbol,
  createSymbolTraining as createGeneratedSymbolTraining,
  deleteMobileRelease as deleteGeneratedMobileRelease,
  deleteBoardSourceRanges as deleteGeneratedBoardSourceRanges,
  deleteCancelledImageSelectionJob as deleteGeneratedCancelledImageSelectionJob,
  deleteSemiAutomaticFilenameVerificationHistory as deleteGeneratedSemiAutomaticFilenameVerificationHistory,
  generateMockDataset as generateGeneratedMockDataset,
  getDatasetValidationReport as getGeneratedDatasetValidationReport,
  getDatasetVersion as getGeneratedDatasetVersion,
  getGame as getGeneratedGame,
  getHealth as getGeneratedHealth,
  getImageJobOperations as getGeneratedImageJobOperations,
  getImageGridReviewSourceAsset as getGeneratedImageGridReviewSourceAsset,
  getImageImportEnginePolicy as getGeneratedImageImportEnginePolicy,
  previewImageImportEnginePolicy as previewGeneratedImageImportEnginePolicy,
  updateImageImportEnginePolicy as updateGeneratedImageImportEnginePolicy,
  getBrowserImageSelection as getGeneratedBrowserImageSelection,
  getBrowserPageGeometrySourceAsset as getGeneratedBrowserPageGeometrySourceAsset,
  getCuratedImageImportSource as getGeneratedCuratedImageImportSource,
  getImageSelection as getGeneratedImageSelection,
  getImageSelectionCandidateFile as getGeneratedImageSelectionCandidateFile,
  getImageSelectionOutput as getGeneratedImageSelectionOutput,
  getImageSelectionOutputFile as getGeneratedImageSelectionOutputFile,
  getImageSelectionSelectedGroupFile as getGeneratedImageSelectionSelectedGroupFile,
  getManualImageSelectionFile as getGeneratedManualImageSelectionFile,
  handoffImageSelection as handoffGeneratedImageSelection,
  getImageDatasetCompleteness as getGeneratedImageDatasetCompleteness,
  getImageSequenceSourceSelection as getGeneratedImageSequenceSourceSelection,
  getImageStorageInventory as getGeneratedImageStorageInventory,
  getStorageGcRun as getGeneratedStorageGcRun,
  getSymbolCellReviewCounts as getGeneratedSymbolCellReviewCounts,
  createStorageGcPreview as createGeneratedStorageGcPreview,
  refreshImageStorageInventory as refreshGeneratedImageStorageInventory,
  startStorageGcRun as startGeneratedStorageGcRun,
  getSymbolCellReviewProjectionStatus as getGeneratedSymbolCellReviewProjectionStatus,
  getSemiAutomaticImageSelectionSourceAsset as getGeneratedSemiAutomaticImageSelectionSourceAsset,
  getSemiAutomaticImageSelection as getGeneratedSemiAutomaticImageSelection,
  getSemiAutomaticImageSelectionCapabilities as getGeneratedSemiAutomaticImageSelectionCapabilities,
  getUnreadableBoardReview as getGeneratedUnreadableBoardReview,
  getJob as getGeneratedJob,
  getLayoutImportIntegrityReport as getGeneratedLayoutImportIntegrityReport,
  getMobileRelease as getGeneratedMobileRelease,
  getOperationalImageReviewBoardAsset as getGeneratedOperationalImageReviewBoardAsset,
  getOperationalImageReviewCellAsset as getGeneratedOperationalImageReviewCellAsset,
  getOperationalImageReviewItem as getGeneratedOperationalImageReviewItem,
  getOperationalImageReviewSourceAsset as getGeneratedOperationalImageReviewSourceAsset,
  getPayline as getGeneratedPayline,
  getPayoutRule as getGeneratedPayoutRule,
  getPendingBoardCellGeometry as getGeneratedPendingBoardCellGeometry,
  getPendingBoardCellGeometryCorrectionContext as getGeneratedPendingBoardCellGeometryCorrectionContext,
  getPendingBoardCellGeometrySource as getGeneratedPendingBoardCellGeometrySource,
  getRulesPublicationReadiness as getGeneratedRulesPublicationReadiness,
  getSymbolCellReviewBulkOperation as getGeneratedSymbolCellReviewBulkOperation,
  getRulesVersion as getGeneratedRulesVersion,
  getModelQuality as getGeneratedModelQuality,
  getReviewItem as getGeneratedReviewItem,
  getReviewFeedbackExport as getGeneratedReviewFeedbackExport,
  getRemoteManualSelectionSession as getGeneratedRemoteManualSelectionSession,
  getRemoteManualSelectionRecoveryStatus as getGeneratedRemoteManualSelectionRecoveryStatus,
  getReviewerIngressStatus as getGeneratedReviewerIngressStatus,
  heartbeatReviewerWorkAssignment as heartbeatGeneratedReviewerWorkAssignment,
  getSymbol as getGeneratedSymbol,
  getSymbolModelIteration as getGeneratedSymbolModelIteration,
  listGames as listGeneratedGames,
  listBrowserPageGeometryReviewSources as listGeneratedBrowserPageGeometryReviewSources,
  listGridCalibrationProfiles as listGeneratedGridCalibrationProfiles,
  listGridProfileActivations as listGeneratedGridProfileActivations,
  getGridCalibrationCohortDiagnostics as getGeneratedGridCalibrationCohortDiagnostics,
  listCuratedImageImportSources as listGeneratedCuratedImageImportSources,
  listImageDiagnosticExports as listGeneratedImageDiagnosticExports,
  listImageGridReviews as listGeneratedImageGridReviews,
  listImageSelectionGroupCandidates as listGeneratedImageSelectionGroupCandidates,
  listImageSelectionGroups as listGeneratedImageSelectionGroups,
  listImageSelections as listGeneratedImageSelections,
  listJobs as listGeneratedJobs,
  listWorkerLanes as listGeneratedWorkerLanes,
  listLayoutImportNormalizedRows as listGeneratedLayoutImportNormalizedRows,
  listMobileReleases as listGeneratedMobileReleases,
  listOperationalImageReviewItems as listGeneratedOperationalImageReviewItems,
  listOperationalImageReviewResolutionEvents as listGeneratedOperationalImageReviewResolutionEvents,
  listPendingBoardCellGeometry as listGeneratedPendingBoardCellGeometry,
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
  listReviewerWorkAssignments as listGeneratedReviewerWorkAssignments,
  listRemoteManualSelectionSessions as listGeneratedRemoteManualSelectionSessions,
  listSemiAutomaticFilenameRangeVerifications as listGeneratedSemiAutomaticFilenameRangeVerifications,
  listSemiAutomaticImageSelections as listGeneratedSemiAutomaticImageSelections,
  listSemiAutomaticImageSelectionRanges as listGeneratedSemiAutomaticImageSelectionRanges,
  listSymbols as listGeneratedSymbols,
  listSymbolCellReviews as listGeneratedSymbolCellReviews,
  listUnreadableBoardReviews as listGeneratedUnreadableBoardReviews,
  listApprovedSymbolReferenceCandidates as listGeneratedApprovedSymbolReferenceCandidates,
  listSymbolModelIterations as listGeneratedSymbolModelIterations,
  listSymbolModelActivations as listGeneratedSymbolModelActivations,
  publishRulesVersion as publishGeneratedRulesVersion,
  registerCuratedImageImportSource as registerGeneratedCuratedImageImportSource,
  reprocessManagedImageImport as reprocessGeneratedManagedImageImport,
  previewVerifiedTrainingCohort as previewGeneratedVerifiedTrainingCohort,
  previewGridProfileActivation as previewGeneratedGridProfileActivation,
  previewSymbolModelActivation as previewGeneratedSymbolModelActivation,
  previewGameLayoutDataReset as previewGeneratedGameLayoutDataReset,
  previewBoardSourceCleanup as previewGeneratedBoardSourceCleanup,
  previewMobileReleaseDeletion as previewGeneratedMobileReleaseDeletion,
  previewOperationalImageReviewGeometry as previewGeneratedOperationalImageReviewGeometry,
  previewImageGridReviewGeometry as previewGeneratedImageGridReviewGeometry,
  previewPendingBoardCellGeometryCorrection as previewGeneratedPendingBoardCellGeometryCorrection,
  previewPendingSymbolReinference as previewGeneratedPendingSymbolReinference,
  previewPendingGridReinference as previewGeneratedPendingGridReinference,
  previewSymbolCellReviewBulkOperation as previewGeneratedSymbolCellReviewBulkOperation,
  startPendingSymbolReinference as startGeneratedPendingSymbolReinference,
  startPendingGridReinference as startGeneratedPendingGridReinference,
  startSymbolCellReviewBulkOperation as startGeneratedSymbolCellReviewBulkOperation,
  publishDatasetVersion as publishGeneratedDatasetVersion,
  publishLayoutImportDataset as publishGeneratedLayoutImportDataset,
  openLocalReviewerWork as openGeneratedLocalReviewerWork,
  openOnlineReviewerWork as openGeneratedOnlineReviewerWork,
  rejectLayoutImportStaging as rejectGeneratedLayoutImportStaging,
  retryJob as retryGeneratedJob,
  rollbackSymbolModel as rollbackGeneratedSymbolModel,
  rollbackGridProfile as rollbackGeneratedGridProfile,
  rerunImageSelection as rerunGeneratedImageSelection,
  rejectImageSelectionReviewGroup as rejectGeneratedImageSelectionReviewGroup,
  resetGameLayoutData as resetGeneratedGameLayoutData,
  restoreRejectedImageSelectionGroup as restoreGeneratedRejectedImageSelectionGroup,
  retryImageJobFile as retryGeneratedImageJobFile,
  pauseSemiAutomaticImageSelection as pauseGeneratedSemiAutomaticImageSelection,
  revokeReviewerSession as revokeGeneratedReviewerSession,
  revokeRemoteManualSelectionSession as revokeGeneratedRemoteManualSelectionSession,
  reopenRemoteManualSelectionBatch as reopenGeneratedRemoteManualSelectionBatch,
  resolveReviewItem as resolveGeneratedReviewItem,
  resolveOperationalImageReviewItem as resolveGeneratedOperationalImageReviewItem,
  resolveUnreadableBoardReviewCell as resolveGeneratedUnreadableBoardReviewCell,
  resumeSemiAutomaticImageSelection as resumeGeneratedSemiAutomaticImageSelection,
  saveUnreadableBoardReview as saveGeneratedUnreadableBoardReview,
  resolvePendingBoardCellGeometryManually as resolveGeneratedPendingBoardCellGeometryManually,
  selectLocalImageFolder as selectGeneratedLocalImageFolder,
  selectRemoteManualSelectionHostBase as selectGeneratedRemoteManualSelectionHostBase,
  selectImageSequenceSource as selectGeneratedImageSequenceSource,
  selectApprovedSymbolReferenceCandidate as selectGeneratedApprovedSymbolReferenceCandidate,
  searchGameBoards as searchGeneratedGameBoards,
  startLocalReviewer as startGeneratedLocalReviewer,
  startReviewerIngress as startGeneratedReviewerIngress,
  startSymbolCellReviewProjectionBackfill as startGeneratedSymbolCellReviewProjectionBackfill,
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
  BrowserImageUploadPlanResponse,
  BrowserImageImportPreflightCreate,
  BrowserImageImportStart,
  BrowserImageImportJobPayload,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryPreflightCreate,
  BoardCellGeometryManualPreviewCommand,
  BoardCellGeometryManualResolutionCommand,
  BoardCellGeometryPendingStatus,
  BoardSearchResponse,
  BoardSearchResultResponse,
  BoardSearchScoreResponse,
  BoardSearchScope,
  BoardSourceCleanupCommandRequest,
  BoardSourceCleanupPreviewRequest,
  CreateGridCalibrationCandidateCommand,
  CreateJobData,
  GridEndToEndGateReportCommand,
  GridProfileActivationAction,
  GridProfileActivationCommand,
  CreateSymbolTrainingCommand,
  CleanupCommandRequest,
  CuratedImageImportBatchCreate,
  CuratedImageImportSourceCreate,
  ImageJobFileRetryRequest,
  ImageFolderImportCreate,
  ImageGridReviewApprovalCommand,
  ImageGridReviewSourceApprovalCommand,
  ImageGridReviewGeometryCommand,
  ImageGridReviewSourceGeometryCommand,
  ImageGridReviewGeometryPreviewCommand,
  ImageGridReviewView,
  ImageImportEnginePolicyPreviewRequest,
  ImageImportEnginePolicyResponse,
  ImageImportEnginePolicyUpdateRequest,
  ImageGeometryGuardDecisionBatchCreate,
  ImageGeometryGuardDecisionItemCreate,
  ImageGeometryGuardBoardTargetResponse,
  ImageGeometryGuardManifestSealCreate,
  ImageGeometryGuardPreviewCreate,
  PageGeometryPoint,
  ResolvedBrowserImageImportJobPayload,
  ImageSelectionCreate,
  ImageSelectionDuplicateRangeCommand,
  ImageSelectionGroupDecisionCommand,
  ImageSelectionManualApprovalCommand,
  ImageSelectionMissingImageCommand,
  ImageSelectionRangeConfirmationCommand,
  ImageSelectionRerunCommand,
  ImageSelectionGroupStatus,
  ImageSequenceSourceOverrideCommand,
  JobStatus,
  JobType,
  ImageReviewGridIssueView,
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
  ReviewerLocalCommand,
  ReviewerSessionCreate,
  ReviewerSessionUnlock,
  ReviewerSessionUnlockResponse,
  ReviewerWorkActionCommand,
  ReviewerWorkOpenCommand,
  RemoteManualSelectionSessionCreate,
  RemoteSelectionReopenCommand,
  RemoteSelectionRecoveryStatusResponse,
  SymbolCreate,
  ApprovedSymbolReferenceSelectionCommand,
  SymbolUpdate,
  SymbolModelActivationAction,
  SymbolModelActivationCommand,
  SymbolCellReviewFilterState,
  SymbolCellReviewAction,
  SymbolCellReviewBulkOperationRequest,
  SymbolCellReviewBulkOperationResponse,
  SymbolCellReviewBulkOperationStartRequest,
  SymbolCellReviewBulkOperationStartResponse,
  SymbolCellReviewBulkPreviewResponse,
  SymbolCellReviewMutationRequest,
  SymbolCellReviewMutationResponse,
  SymbolCellReviewProjectionStartResponse,
  SymbolCellReviewProjectionStatusResponse,
  FilenameRangeVerificationItemResponse,
  FilenameRangeVerificationPageResponse,
  FilenameRangeVerificationReviewDecisionUpdate,
  SymbolCellPreviewBatchRequest,
  SemiAutomaticSelectionOutputAcknowledgement,
  SemiAutomaticSelectionCreate,
  SemiAutomaticSelectionRangeResponse,
  SemiAutomaticSelectionRunResponse,
  SemiAutomaticSelectionRunPageResponse,
  StorageGcRunCreate,
  VirtualCellPreviewBatchRequest,
  VirtualCellPreviewTileResponse,
  ResolveUnreadableCellRequest,
  SaveUnreadableBoardRequest,
  SaveUnreadableBoardResponse,
  UnreadableBoardReviewDetailResponse,
  UnreadableBoardReviewCellResponse,
  UnreadableBoardReviewListItemResponse,
  UnreadableBoardReviewPageResponse,
  UnreadableBoardReviewView,
  WorkerLaneStatusResponse,
} from './generated/types.gen';

export type {
  AndroidBuildJobCreate,
  AndroidBuildJobPayload,
  BrowserImageImportPreflightResponse,
  BrowserImageImportJobPayload,
  BrowserImageImportStart,
  BrowserImageImportStartResponse,
  BrowserPageGeometryOverrideCreate,
  BrowserPageGeometryOverrideResponse,
  BrowserPageGeometryPreflightCreate,
  BrowserPageGeometryPreflightResponse,
  BrowserPageGeometryReviewSourceResponse,
  BrowserPageGeometryReviewSourcesResponse,
  ImageGeometryGuardDecisionBatchCreate,
  ImageGeometryGuardDecisionBatchResponse,
  ImageGeometryGuardDecisionItemCreate,
  ImageGeometryGuardBoardTargetResponse,
  ImageGeometryGuardManifestSealCreate,
  ImageGeometryGuardPreviewCreate,
  ImageGeometryGuardPreviewResponse,
  ImageGeometryGuardQueueResponse,
  ImageGeometryGuardReportReconstructionResponse,
  ImageGeometryGuardResolutionManifestResponse,
  PageGeometryPoint,
  ResolvedBrowserImageImportJobPayload,
  BoardCellGeometryCorrectionContextResponse,
  BoardCellGeometryJobCountsResponse,
  BoardCellGeometryManualPreviewCommand,
  BoardCellGeometryManualResolutionCommand,
  BoardCellGeometryManualResolutionResponse,
  BoardCellGeometryPendingPageResponse,
  BoardCellGeometryPendingReason,
  BoardCellGeometryPendingResponse,
  BoardCellGeometryPendingStatus,
  BoardSearchResponse,
  BoardSearchResultResponse,
  BoardSearchScoreResponse,
  BoardSearchScope,
  BoardSourceCleanupCommandRequest,
  BoardSourceCleanupPreviewRequest,
  BrowserImageSelectionCreate,
  BrowserImageSelectionUploadResponse,
  BrowserImageUploadPlanResponse,
  BrowserReadySelectionResponse,
  CleanupCommandRequest,
  CleanupCountResponse,
  CleanupPreviewResponse,
  CleanupResultResponse,
  CuratedImageImportBatchResponse,
  CuratedImageImportJobPayload,
  CuratedImageImportSourceCreate,
  CuratedImageImportSourceResponse,
  ManagedImageReprocessJobPayload,
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
  CreateGridCalibrationCandidateCommand,
  GeometryCohortDiagnosticsResponse,
  GeometryCohortResponse,
  GridCalibrationProfileResponse,
  GridEndToEndGateReportCommand,
  GridEndToEndGateSource,
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
  ImageImportEnginePolicyPreviewRequest,
  ImageImportEnginePolicyResponse,
  ImageImportEnginePolicyUpdateRequest,
  ImageFolderImportResponse,
  ImageFolderSelectionResponse,
  ImageGridReviewApprovalCommand,
  ImageGridReviewApprovalResponse,
  ImageGridReviewSourceApprovalCommand,
  ImageGridReviewSourceApprovalResponse,
  ImageGridReviewGeometryCommand,
  ImageGridReviewSourceGeometryCommand,
  ImageGridReviewSourceGeometryResponse,
  ImageGridReviewGeometryPreviewCommand,
  ImageGridReviewGeometryResponse,
  ImageGridReviewItemResponse,
  ImageGridReviewPageResponse,
  ImageGridReviewState,
  ImageGridReviewView,
  ImageSelectionCreate,
  ImageSelectionCreateResponse,
  ImageSelectionDuplicateRangeCommand,
  ImageSelectionGroupDecisionCommand,
  ImageSelectionHandoffResponse,
  ImageSelectionGroupCandidatesResponse,
  ImageSelectionGroupPageResponse,
  ImageSelectionGroupResponse,
  ImageSelectionGroupStatus,
  ImageSelectionJobPayload,
  ImageSelectionJobDeletionResponse,
  ImageSelectionRunResponse,
  ImageSelectionRunPageResponse,
  ImageSelectionCandidateResponse,
  ImageSelectionManualApprovalCommand,
  ImageSelectionManualApprovalResponse,
  ImageSelectionManualDecisionResponse,
  ImageSelectionManualFileResponse,
  ImageSelectionMissingImageCommand,
  ImageSelectionOutputFileResponse,
  ImageSelectionOutputResponse,
  ImageSelectionRangeConfirmationCommand,
  ImageDiagnosticExportCreationResponse,
  ImageDatasetCompletenessResponse,
  ImageDiagnosticExportResponse,
  ImageJobFileErrorResponse,
  ImageJobFileResponse,
  ImageJobFileRetryRequest,
  ImageJobOperationsResponse,
  ImageJobStageCountResponse,
  ImageStorageInventoryResponse,
  StorageGcPreviewResponse,
  StorageGcRunCreate,
  StorageGcRunResponse,
  ImageStorageNamespaceResponse,
  ImageReviewAction,
  ImageReviewGridIssueView,
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
  PendingSymbolReinferencePreviewResponse,
  PendingGridReinferencePreviewResponse,
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
  SymbolCellReviewCountsResponse,
  SymbolCellReviewCountSnapshotResponse,
  SymbolCellReviewAction,
  SymbolCellReviewBulkExplicitSelectionRequest,
  SymbolCellReviewBulkExplicitTargetRequest,
  SymbolCellReviewBulkFilterSelectionRequest,
  SymbolCellReviewBulkOperationRequest,
  SymbolCellReviewBulkOperationResponse,
  SymbolCellReviewBulkOperationStartRequest,
  SymbolCellReviewBulkOperationStartResponse,
  SymbolCellReviewBulkPreviewResponse,
  SymbolCellReviewProjectionStartResponse,
  SymbolCellReviewProjectionStatusResponse,
  FilenameRangeVerificationItemResponse,
  FilenameRangeVerificationPageResponse,
  FilenameRangeVerificationReviewDecisionResponse,
  FilenameRangeVerificationReviewDecisionUpdate,
  SemiAutomaticSelectionOutputAcknowledgement,
  SemiAutomaticSelectionCapabilitiesResponse,
  SemiAutomaticSelectionCreate,
  SemiAutomaticSelectionCreateResponse,
  SemiAutomaticSelectionRangeResponse,
  SemiAutomaticSelectionRunResponse,
  SemiAutomaticSelectionRunPageResponse,
  SymbolCellReviewFilterState,
  SymbolCellReviewListItemResponse,
  SymbolCellReviewMutationRequest,
  SymbolCellReviewMutationResponse,
  SymbolCellReviewPageResponse,
  SymbolCellPreviewBatchRequest,
  VirtualCellPreviewBatchRequest,
  VirtualCellPreviewTileResponse,
  ResolveUnreadableCellRequest,
  SaveUnreadableBoardRequest,
  SaveUnreadableBoardResponse,
  UnreadableBoardReviewCellResponse,
  UnreadableBoardReviewDetailResponse,
  UnreadableBoardReviewListItemResponse,
  UnreadableBoardReviewPageResponse,
  UnreadableBoardReviewView,
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
  ReviewerLocalCommand,
  ReviewerSessionCreate,
  ReviewerSessionCreatedResponse,
  ReviewerSessionScopeResponse,
  ReviewerSessionUnlock,
  ReviewerSessionUnlockResponse,
  ReviewerWorkActionCommand,
  ReviewerWorkAssignmentResponse,
  ReviewerWorkClosedResponse,
  ReviewerWorkHeartbeatResponse,
  ReviewerWorkOpenCommand,
  ReviewerWorkOpenedResponse,
  RemoteManualSelectionSessionCreate,
  ReviewerWorkOverviewResponse,
  RemoteManualSelectionBaseCapabilityResponse,
  RemoteManualSelectionBatchMonitorResponse,
  RemoteManualSelectionSessionCreatedResponse,
  RemoteManualSelectionSessionListResponse,
  RemoteManualSelectionSessionMonitorResponse,
  RemoteManualSelectionSessionResponse,
  RemoteSelectionReopenCommand,
  RemoteSelectionRecoveryStatusResponse,
  ApprovedSymbolReferenceCandidatePageResponse,
  ApprovedSymbolReferenceCandidateResponse,
  ApprovedSymbolReferenceSelectionCommand,
  SymbolCreate,
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

export type ImageGridReviewContext = OperationalImageReviewContext;

export interface ListImageGridReviewsOptions {
  readonly gameId: string;
  readonly view?: ImageGridReviewView;
  readonly importJobId?: string;
  readonly sourceImageId?: string;
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly limit?: number;
}

export interface ListOperationalImageReviewItemsOptions extends OperationalImageReviewContext {
  readonly gridIssueView?: ImageReviewGridIssueView;
  readonly view?: ImageReviewView;
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly resumeAtFirstPending?: boolean;
  readonly sequenceNumber?: number;
  readonly limit?: number;
}

export interface ListSymbolCellReviewsOptions {
  readonly gameId: string;
  readonly symbolId: string | 'unknown';
  readonly state?: SymbolCellReviewFilterState;
  readonly afterCursor?: string;
  readonly beforeCursor?: string;
  readonly limit?: number;
  readonly maxConfidence?: number;
  readonly minConfidence?: number;
}

export interface GetSymbolCellReviewCountsOptions {
  readonly catalogRevision: number;
  readonly gameId: string;
  readonly maxConfidence?: number;
  readonly minConfidence?: number;
  readonly state?: SymbolCellReviewFilterState;
  readonly symbolId: string | 'unknown';
}

export interface ListUnreadableBoardReviewsOptions {
  readonly gameId: string;
  readonly view?: UnreadableBoardReviewView;
  readonly afterCursor?: string;
  readonly limit?: number;
}

export interface ListPendingBoardCellGeometryOptions extends OperationalImageReviewContext {
  readonly status?: BoardCellGeometryPendingStatus;
  readonly cursor?: string;
  readonly limit?: number;
}

export interface ListVerifiedImageReviewCohortsOptions extends OperationalImageReviewContext {
  readonly limit?: number;
}

export interface SearchGameBoardsOptions {
  readonly cells: readonly BoardSearchQueryCell[];
  readonly scope?: BoardSearchScope;
  readonly limit?: number;
}

export interface BoardSearchQueryCell {
  readonly cellIndex: number;
  readonly symbolCode: string | null;
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
    getSemiAutomaticImageSelectionCapabilities: () =>
      getGeneratedSemiAutomaticImageSelectionCapabilities({ client }),
    createSemiAutomaticImageSelection: (body: SemiAutomaticSelectionCreate) =>
      createGeneratedSemiAutomaticImageSelection({ body, client }),
    getSemiAutomaticImageSelection: (runId: string) =>
      getGeneratedSemiAutomaticImageSelection({
        client,
        path: { run_id: runId },
      }),
    listSemiAutomaticImageSelections: (
      workflowMode: 'selection' | 'filename_verification',
      offset = 0,
      limit = 20,
    ) =>
      listGeneratedSemiAutomaticImageSelections({
        client,
        query: { workflowMode, offset, limit },
      }),
    listSemiAutomaticImageSelectionRanges: (
      runId: string,
      afterExpectedIndex?: number,
      limit = 500,
    ) =>
      listGeneratedSemiAutomaticImageSelectionRanges({
        client,
        path: { run_id: runId },
        query: {
          ...(afterExpectedIndex === undefined
            ? {}
            : { after_expected_index: afterExpectedIndex }),
          limit,
        },
      }),
    listSemiAutomaticFilenameRangeVerifications: (
      runId: string,
      afterSourceIndex?: number,
      limit = 500,
    ) =>
      listGeneratedSemiAutomaticFilenameRangeVerifications({
        client,
        path: { run_id: runId },
        query: {
          ...(afterSourceIndex === undefined
            ? {}
            : { after_source_index: afterSourceIndex }),
          limit,
        },
      }),
    decideSemiAutomaticFilenameRangeVerification: (
      runId: string,
      sourceIndex: number,
      body: FilenameRangeVerificationReviewDecisionUpdate,
    ) =>
      decideGeneratedSemiAutomaticFilenameRangeVerification({
        body,
        client,
        path: { run_id: runId, source_index: sourceIndex },
      }),
    deleteSemiAutomaticFilenameVerificationHistory: (runId: string) =>
      deleteGeneratedSemiAutomaticFilenameVerificationHistory({
        client,
        headers: confirmedTargetHeaders(`filename-verification:${runId}`),
        path: { run_id: runId },
      }),
    pauseSemiAutomaticImageSelection: (runId: string) =>
      pauseGeneratedSemiAutomaticImageSelection({
        client,
        path: { run_id: runId },
      }),
    resumeSemiAutomaticImageSelection: (runId: string) =>
      resumeGeneratedSemiAutomaticImageSelection({
        client,
        path: { run_id: runId },
      }),
    cancelSemiAutomaticImageSelection: (runId: string) =>
      cancelGeneratedSemiAutomaticImageSelection({
        client,
        path: { run_id: runId },
      }),
    getSemiAutomaticImageSelectionSourceAsset: (
      runId: string,
      sourceIndex: number,
      expectedChecksumSha256: string,
    ) =>
      getGeneratedSemiAutomaticImageSelectionSourceAsset({
        client,
        path: { run_id: runId, source_index: sourceIndex },
        query: { expected_checksum_sha256: expectedChecksumSha256 },
      }),
    acknowledgeSemiAutomaticImageSelectionOutput: (
      runId: string,
      expectedIndex: number,
      body: SemiAutomaticSelectionOutputAcknowledgement,
    ) =>
      acknowledgeGeneratedSemiAutomaticImageSelectionOutput({
        body,
        client,
        path: { expected_index: expectedIndex, run_id: runId },
      }),
    getImageImportEnginePolicy: (gameId: string) =>
      getGeneratedImageImportEnginePolicy({
        client,
        path: { game_id: gameId },
      }),
    previewImageImportEnginePolicy: (
      gameId: string,
      body: ImageImportEnginePolicyPreviewRequest,
    ) =>
      previewGeneratedImageImportEnginePolicy({
        body,
        client,
        path: { game_id: gameId },
      }),
    updateImageImportEnginePolicy: (
      gameId: string,
      body: ImageImportEnginePolicyUpdateRequest,
    ) =>
      updateGeneratedImageImportEnginePolicy({
        body,
        client,
        path: { game_id: gameId },
      }),
    getReviewerIngressStatus: () =>
      getGeneratedReviewerIngressStatus({ client }),
    startLocalReviewer: (body: ReviewerLocalCommand) =>
      startGeneratedLocalReviewer({
        body,
        client,
        headers: confirmedTargetHeaders('local-reviewer'),
      }),
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
    selectRemoteManualSelectionHostBase: () =>
      selectGeneratedRemoteManualSelectionHostBase({ client }),
    createRemoteManualSelectionSession: (
      body: RemoteManualSelectionSessionCreate,
    ) =>
      createGeneratedRemoteManualSelectionSession({
        body,
        client,
        headers: confirmedTargetHeaders('remote-manual-selection-session:new'),
      }),
    listRemoteManualSelectionSessions: (limit = 100) =>
      listGeneratedRemoteManualSelectionSessions({
        client,
        query: { limit },
      }),
    getRemoteManualSelectionSession: (sessionId: string, batchLimit = 100) =>
      getGeneratedRemoteManualSelectionSession({
        client,
        path: { session_id: sessionId },
        query: { batch_limit: batchLimit },
      }),
    getRemoteManualSelectionRecoveryStatus: (
      sessionId: string,
      batchId: string,
    ) =>
      getGeneratedRemoteManualSelectionRecoveryStatus({
        client,
        path: { batch_id: batchId, session_id: sessionId },
      }),
    revokeRemoteManualSelectionSession: (sessionId: string) =>
      revokeGeneratedRemoteManualSelectionSession({
        client,
        headers: confirmedTargetHeaders(
          `remote-manual-selection-session:${sessionId}`,
        ),
        path: { session_id: sessionId },
      }),
    reopenRemoteManualSelectionBatch: (
      sessionId: string,
      body: RemoteSelectionReopenCommand,
    ) =>
      reopenGeneratedRemoteManualSelectionBatch({
        body,
        client,
        headers: confirmedTargetHeaders(
          `remote-manual-selection-batch:${body.batchId}:reopen`,
        ),
        path: { session_id: sessionId },
      }),
    listReviewerWorkAssignments: (gameId: string) =>
      listGeneratedReviewerWorkAssignments({
        client,
        path: { game_id: gameId },
      }),
    openLocalReviewerWork: (
      gameId: string,
      importJobId: string,
      body: ReviewerWorkOpenCommand,
    ) =>
      openGeneratedLocalReviewerWork({
        body,
        client,
        headers: confirmedTargetHeaders(`reviewer-work:${importJobId}:local`),
        path: { game_id: gameId, import_job_id: importJobId },
      }),
    openOnlineReviewerWork: (
      gameId: string,
      importJobId: string,
      body: ReviewerWorkOpenCommand,
    ) =>
      openGeneratedOnlineReviewerWork({
        body,
        client,
        headers: confirmedTargetHeaders(`reviewer-work:${importJobId}:online`),
        path: { game_id: gameId, import_job_id: importJobId },
      }),
    heartbeatReviewerWorkAssignment: (
      assignmentId: string,
      body: ReviewerWorkActionCommand,
    ) =>
      heartbeatGeneratedReviewerWorkAssignment({
        body,
        client,
        path: { assignment_id: assignmentId },
      }),
    closeReviewerWorkAssignment: (
      assignmentId: string,
      body: ReviewerWorkActionCommand,
    ) =>
      closeGeneratedReviewerWorkAssignment({
        body,
        client,
        headers: confirmedTargetHeaders(`reviewer-work:${assignmentId}`),
        path: { assignment_id: assignmentId },
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
    planBrowserImageSelectionUpload: (body: {
      gameId: string;
      files: Array<{
        sourceIndex: number;
        relativePath: string;
        sizeBytes: number;
      }>;
    }) => planGeneratedBrowserImageSelectionUpload({ body, client }),
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
    listReadyBrowserImageSelections: () =>
      listGeneratedReadyBrowserImageSelections({
        client,
        query: { purpose: 'layout_import' },
      }),
    previewReadyBrowserImageImport: (
      uploadId: string,
      body: BrowserImageImportPreflightCreate,
    ) =>
      previewGeneratedReadyBrowserImageImport({
        body,
        client,
        path: { upload_id: uploadId },
      }),
    startReadyBrowserImageImport: (
      uploadId: string,
      body: BrowserImageImportStart,
    ) =>
      startGeneratedReadyBrowserImageImport({
        body,
        client,
        headers: confirmedTargetHeaders(`image-import:${body.gameId}`),
        path: { upload_id: uploadId },
      }),
    startBrowserPageGeometryPreflight: (
      uploadId: string,
      body: BrowserPageGeometryPreflightCreate,
    ) =>
      startGeneratedBrowserPageGeometryPreflight({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-import:${body.gameId}:page-geometry-preflight`,
        ),
        path: { upload_id: uploadId },
      }),
    listImageGeometryGuardBoards: (
      uploadId: string,
      guardJobId: string,
      gameId: string,
    ) =>
      listGeneratedImageGeometryGuardBoards({
        client,
        path: { guard_job_id: guardJobId, upload_id: uploadId },
        query: { game_id: gameId },
      }),
    createImageGeometryGuardDecisions: (
      uploadId: string,
      guardJobId: string,
      body: ImageGeometryGuardDecisionBatchCreate,
    ) =>
      createGeneratedImageGeometryGuardDecisions({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-import:${body.gameId}:geometry-guard-decisions`,
        ),
        path: { guard_job_id: guardJobId, upload_id: uploadId },
      }),
    previewImageGeometryGuardDecision: (
      uploadId: string,
      guardJobId: string,
      body: ImageGeometryGuardPreviewCreate,
    ) =>
      previewGeneratedImageGeometryGuardDecision({
        body,
        client,
        path: { guard_job_id: guardJobId, upload_id: uploadId },
      }),
    startImageGeometryGuardReportReconstruction: (
      uploadId: string,
      guardJobId: string,
      gameId: string,
    ) =>
      startGeneratedImageGeometryGuardReportReconstruction({
        body: { gameId },
        client,
        headers: confirmedTargetHeaders(
          `image-import:${gameId}:geometry-guard-report-reconstruction`,
        ),
        path: { guard_job_id: guardJobId, upload_id: uploadId },
      }),
    sealImageGeometryGuardResolutionManifest: (
      uploadId: string,
      guardJobId: string,
      body: ImageGeometryGuardManifestSealCreate,
    ) =>
      sealGeneratedImageGeometryGuardResolutionManifest({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-import:${body.gameId}:geometry-guard-manifest`,
        ),
        path: { guard_job_id: guardJobId, upload_id: uploadId },
      }),
    listBrowserPageGeometryReviewSources: (
      uploadId: string,
      preflightJobId: string,
      gameId: string,
    ) =>
      listGeneratedBrowserPageGeometryReviewSources({
        client,
        path: { preflight_job_id: preflightJobId, upload_id: uploadId },
        query: { game_id: gameId },
      }),
    getBrowserPageGeometrySourceAsset: (
      uploadId: string,
      sourceChecksumSha256: string,
      gameId: string,
    ) =>
      getGeneratedBrowserPageGeometrySourceAsset({
        client,
        path: {
          source_checksum_sha256: sourceChecksumSha256,
          upload_id: uploadId,
        },
        query: { game_id: gameId },
      }),
    createBrowserPageGeometryOverride: (
      uploadId: string,
      body: BrowserPageGeometryOverrideCreate,
    ) =>
      createGeneratedBrowserPageGeometryOverride({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-import:${body.gameId}:page-geometry-override`,
        ),
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
    listImageSelections: (
      gameId: string,
      options: {
        readonly offset?: number;
        readonly limit?: number;
      } = {},
    ) =>
      listGeneratedImageSelections({
        client,
        query: {
          gameId,
          ...(options.offset === undefined ? {} : { offset: options.offset }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    rerunImageSelection: (runId: string, body?: ImageSelectionRerunCommand) =>
      rerunGeneratedImageSelection({
        ...(body === undefined ? {} : { body }),
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
    getImageSelectionCandidateFile: (
      runId: string,
      groupId: string,
      candidateId: string,
    ) =>
      getGeneratedImageSelectionCandidateFile({
        client,
        path: {
          candidate_id: candidateId,
          group_id: groupId,
          run_id: runId,
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
    discardDuplicateImageSelectionGroup: (
      runId: string,
      groupId: string,
      body: ImageSelectionDuplicateRangeCommand,
    ) =>
      discardGeneratedDuplicateImageSelectionGroup({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:discard-duplicate`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    confirmImageSelectionGroupRange: (
      runId: string,
      groupId: string,
      body: ImageSelectionRangeConfirmationCommand,
    ) =>
      confirmGeneratedImageSelectionGroupRange({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:confirm-range`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    rejectImageSelectionReviewGroup: (
      runId: string,
      groupId: string,
      body: ImageSelectionGroupDecisionCommand,
    ) =>
      rejectGeneratedImageSelectionReviewGroup({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:reject`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    restoreRejectedImageSelectionGroup: (
      runId: string,
      groupId: string,
      body: ImageSelectionGroupDecisionCommand,
    ) =>
      restoreGeneratedRejectedImageSelectionGroup({
        body,
        client,
        headers: confirmedTargetHeaders(
          `image-selection:${runId}:${groupId}:restore`,
        ),
        path: { group_id: groupId, run_id: runId },
      }),
    createImageFolderImport: (body: ImageFolderImportCreate) =>
      createGeneratedImageFolderImport({
        body,
        client,
        headers: confirmedTargetHeaders(`image-import:${body.gameId}`),
      }),
    reprocessManagedImageImport: (sourceJobId: string) =>
      reprocessGeneratedManagedImageImport({
        client,
        headers: confirmedTargetHeaders(
          `image-import:${sourceJobId}:reprocess`,
        ),
        path: { source_job_id: sourceJobId },
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
    deleteCancelledImageSelectionJob: (jobId: string) =>
      deleteGeneratedCancelledImageSelectionJob({
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
    refreshImageStorageInventory: () =>
      refreshGeneratedImageStorageInventory({ client }),
    createStorageGcPreview: () => createGeneratedStorageGcPreview({ client }),
    startStorageGcRun: (body: StorageGcRunCreate) =>
      startGeneratedStorageGcRun({
        body,
        client,
        headers: confirmedTargetHeaders(`storage-gc:${body.previewId}`),
      }),
    getStorageGcRun: (runId: string) =>
      getGeneratedStorageGcRun({ client, path: { run_id: runId } }),
    listApprovedSymbolReferenceCandidates: (
      gameId: string,
      symbolId: string,
      afterCursor?: string,
    ) =>
      listGeneratedApprovedSymbolReferenceCandidates({
        client,
        path: { game_id: gameId, symbol_id: symbolId },
        query: {
          limit: 20,
          ...(afterCursor === undefined ? {} : { afterCursor }),
        },
      }),
    approvedSymbolReferenceCandidateAssetUrl: (
      gameId: string,
      symbolId: string,
      observationId: string,
    ) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbols/${encodeURIComponent(symbolId)}/approved-image-candidates/${encodeURIComponent(observationId)}/asset`,
    symbolImageAssetUrl: (gameId: string, symbolId: string) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbols/${encodeURIComponent(symbolId)}/image/asset`,
    selectApprovedSymbolReferenceCandidate: (
      gameId: string,
      symbolId: string,
      observationId: string,
      body: ApprovedSymbolReferenceSelectionCommand,
    ) =>
      selectGeneratedApprovedSymbolReferenceCandidate({
        body,
        client,
        headers: confirmedTargetHeaders(
          `symbol-reference:${gameId}:${symbolId}:${observationId}`,
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
    searchGameBoards: (gameId: string, options: SearchGameBoardsOptions) =>
      searchGeneratedGameBoards({
        client,
        path: { game_id: gameId },
        query: {
          cell: options.cells.map(
            (cell) => `${cell.cellIndex}:${cell.symbolCode ?? '?'}`,
          ),
          ...(options.scope === undefined ? {} : { scope: options.scope }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
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
          ...(filters.gridIssueView === undefined
            ? {}
            : { gridIssueView: filters.gridIssueView }),
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
    createGridCalibrationCandidate: (
      gameId: string,
      body?: CreateGridCalibrationCandidateCommand,
    ) =>
      createGeneratedGridCalibrationCandidate({
        ...(body === undefined ? {} : { body }),
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
    getGridCalibrationCohortDiagnostics: (
      gameId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      getGeneratedGridCalibrationCohortDiagnostics({
        client,
        path: { game_id: gameId },
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
    previewPendingSymbolReinference: (
      gameId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      previewGeneratedPendingSymbolReinference({
        client,
        path: { game_id: gameId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    startPendingSymbolReinference: (gameId: string) =>
      startGeneratedPendingSymbolReinference({
        client,
        headers: confirmedTargetHeaders(`pending-symbol-reinference:${gameId}`),
        path: { game_id: gameId },
      }),
    previewPendingGridReinference: (
      gameId: string,
      options: { readonly signal?: AbortSignal } = {},
    ) =>
      previewGeneratedPendingGridReinference({
        client,
        path: { game_id: gameId },
        ...(options.signal === undefined ? {} : { signal: options.signal }),
      }),
    startPendingGridReinference: (gameId: string) =>
      startGeneratedPendingGridReinference({
        client,
        headers: confirmedTargetHeaders(`pending-grid-reinference:${gameId}`),
        path: { game_id: gameId },
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
    operationalImageReviewBoardAssetUrl: (
      reviewItemId: string,
      context: OperationalImageReviewContext,
    ) => {
      const query = new URLSearchParams({
        gameId: context.gameId,
        importJobId: context.importJobId,
      });
      return `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/image-review-items/${encodeURIComponent(reviewItemId)}/assets/board?${query.toString()}`;
    },
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
    listImageGridReviews: (options: ListImageGridReviewsOptions) =>
      listGeneratedImageGridReviews({
        client,
        path: { game_id: options.gameId },
        query: {
          ...(options.view === undefined ? {} : { view: options.view }),
          ...(options.importJobId === undefined
            ? {}
            : { importJobId: options.importJobId }),
          ...(options.sourceImageId === undefined
            ? {}
            : { sourceImageId: options.sourceImageId }),
          ...(options.afterCursor === undefined
            ? {}
            : { afterCursor: options.afterCursor }),
          ...(options.beforeCursor === undefined
            ? {}
            : { beforeCursor: options.beforeCursor }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    getImageGridReviewSourceAsset: (
      reviewItemId: string,
      gameId: string,
      expectedSourceChecksumSha256: string,
    ) =>
      getGeneratedImageGridReviewSourceAsset({
        client,
        path: { review_item_id: reviewItemId },
        query: { expectedSourceChecksumSha256, gameId },
      }),
    imageGridReviewSourceAssetUrl: (
      reviewItemId: string,
      gameId: string,
      expectedSourceChecksumSha256: string,
    ) => {
      const query = new URLSearchParams({
        expectedSourceChecksumSha256,
        gameId,
      });
      return `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/image-reviews/${encodeURIComponent(reviewItemId)}/source-asset?${query.toString()}`;
    },
    approveImageGridReviewGeometry: (
      reviewItemId: string,
      gameId: string,
      body: ImageGridReviewApprovalCommand,
    ) =>
      approveGeneratedImageGridReviewGeometry({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: { gameId },
      }),
    approveImageGridReviewSourceGeometry: (
      gameId: string,
      body: ImageGridReviewSourceApprovalCommand,
    ) =>
      approveGeneratedImageGridReviewSourceGeometry({
        body,
        client,
        path: { game_id: gameId },
      }),
    previewImageGridReviewGeometry: (
      reviewItemId: string,
      context: ImageGridReviewContext,
      body: ImageGridReviewGeometryPreviewCommand,
    ) =>
      previewGeneratedImageGridReviewGeometry({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    createImageGridReviewGeometryRevision: (
      reviewItemId: string,
      context: ImageGridReviewContext,
      body: ImageGridReviewGeometryCommand,
    ) =>
      createGeneratedImageGridReviewGeometryRevision({
        body,
        client,
        path: { review_item_id: reviewItemId },
        query: context,
      }),
    createImageGridReviewSourceGeometryRevision: (
      gameId: string,
      context: ImageGridReviewContext,
      body: ImageGridReviewSourceGeometryCommand,
    ) =>
      createGeneratedImageGridReviewSourceGeometryRevision({
        body,
        client,
        path: { game_id: gameId },
        query: context,
      }),
    getSymbolCellReviewProjectionStatus: (gameId: string) =>
      getGeneratedSymbolCellReviewProjectionStatus({
        client,
        path: { game_id: gameId },
      }),
    startSymbolCellReviewProjectionBackfill: (gameId: string) =>
      startGeneratedSymbolCellReviewProjectionBackfill({
        client,
        headers: confirmedTargetHeaders(
          `symbol-cell-review-projection:${gameId}`,
        ),
        path: { game_id: gameId },
      }),
    listSymbolCellReviews: (options: ListSymbolCellReviewsOptions) =>
      listGeneratedSymbolCellReviews({
        client,
        path: { game_id: options.gameId },
        query: {
          symbolId: options.symbolId,
          ...(options.state === undefined ? {} : { state: options.state }),
          ...(options.afterCursor === undefined
            ? {}
            : { afterCursor: options.afterCursor }),
          ...(options.beforeCursor === undefined
            ? {}
            : { beforeCursor: options.beforeCursor }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
          ...(options.maxConfidence === undefined
            ? {}
            : { maxConfidence: options.maxConfidence }),
          ...(options.minConfidence === undefined
            ? {}
            : { minConfidence: options.minConfidence }),
        },
      }),
    getSymbolCellReviewCounts: (options: GetSymbolCellReviewCountsOptions) =>
      getGeneratedSymbolCellReviewCounts({
        client,
        path: { game_id: options.gameId },
        query: {
          symbolId: options.symbolId,
          catalogRevision: options.catalogRevision,
          ...(options.state === undefined ? {} : { state: options.state }),
          ...(options.maxConfidence === undefined
            ? {}
            : { maxConfidence: options.maxConfidence }),
          ...(options.minConfidence === undefined
            ? {}
            : { minConfidence: options.minConfidence }),
        },
      }),
    createVirtualCellPreviewBatch: (
      gameId: string,
      body: VirtualCellPreviewBatchRequest,
    ) =>
      createGeneratedVirtualCellPreviewBatch({
        body,
        client,
        headers: confirmedTargetHeaders(`virtual-cell-preview:${gameId}`),
        path: { game_id: gameId },
      }),
    createSymbolCellPreviewBatch: (
      gameId: string,
      body: SymbolCellPreviewBatchRequest,
    ) =>
      createGeneratedSymbolCellPreviewBatch({
        body,
        client,
        headers: confirmedTargetHeaders(`symbol-cell-preview:${gameId}`),
        path: { game_id: gameId },
      }),
    symbolCellPreviewAtlasUrl: (gameId: string, batchKey: string) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbol-cell-preview-batches/${encodeURIComponent(batchKey)}/atlas`,
    virtualCellPreviewAtlasUrl: (gameId: string, batchKey: string) =>
      `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/virtual-cell-preview-batches/${encodeURIComponent(batchKey)}/atlas`,
    symbolCellReviewAssetUrl: (
      gameId: string,
      cellReviewId: string,
      expectedCropChecksumSha256: string,
      expectedRenderSpecChecksumSha256?: string | null,
    ) => {
      const query = new URLSearchParams({
        expectedCropChecksumSha256,
        thumbnailSize: '100',
      });
      if (expectedRenderSpecChecksumSha256 != null) {
        query.set(
          'expectedRenderSpecChecksumSha256',
          expectedRenderSpecChecksumSha256,
        );
      }
      return `${options.baseUrl.replace(/\/$/, '')}/api/v1/admin/games/${encodeURIComponent(gameId)}/symbol-cell-reviews/${encodeURIComponent(cellReviewId)}/asset?${query.toString()}`;
    },
    listUnreadableBoardReviews: (options: ListUnreadableBoardReviewsOptions) =>
      listGeneratedUnreadableBoardReviews({
        client,
        path: { game_id: options.gameId },
        query: {
          ...(options.view === undefined ? {} : { view: options.view }),
          ...(options.afterCursor === undefined
            ? {}
            : { afterCursor: options.afterCursor }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    getUnreadableBoardReview: (gameId: string, reviewItemId: string) =>
      getGeneratedUnreadableBoardReview({
        client,
        path: { game_id: gameId, review_item_id: reviewItemId },
      }),
    resolveUnreadableBoardReviewCell: (
      gameId: string,
      reviewItemId: string,
      cellIndex: number,
      body: ResolveUnreadableCellRequest,
    ) =>
      resolveGeneratedUnreadableBoardReviewCell({
        body,
        client,
        path: {
          cell_index: cellIndex,
          game_id: gameId,
          review_item_id: reviewItemId,
        },
      }),
    saveUnreadableBoardReview: (
      gameId: string,
      reviewItemId: string,
      body: SaveUnreadableBoardRequest,
    ) =>
      saveGeneratedUnreadableBoardReview({
        body,
        client,
        path: { game_id: gameId, review_item_id: reviewItemId },
      }),
    applySymbolCellReviewDecision: (
      gameId: string,
      cellReviewId: string,
      body: SymbolCellReviewMutationRequest,
    ) =>
      applyGeneratedSymbolCellReviewDecision({
        body,
        client,
        path: { cell_review_id: cellReviewId, game_id: gameId },
      }),
    previewSymbolCellReviewBulkOperation: (
      gameId: string,
      body: SymbolCellReviewBulkOperationRequest,
    ) =>
      previewGeneratedSymbolCellReviewBulkOperation({
        body,
        client,
        path: { game_id: gameId },
      }),
    startSymbolCellReviewBulkOperation: (
      gameId: string,
      body: SymbolCellReviewBulkOperationStartRequest,
    ) =>
      startGeneratedSymbolCellReviewBulkOperation({
        body,
        client,
        path: { game_id: gameId },
      }),
    getSymbolCellReviewBulkOperation: (gameId: string, operationId: string) =>
      getGeneratedSymbolCellReviewBulkOperation({
        client,
        path: { game_id: gameId, operation_id: operationId },
      }),
    listPendingBoardCellGeometry: (
      options: ListPendingBoardCellGeometryOptions,
    ) =>
      listGeneratedPendingBoardCellGeometry({
        client,
        path: {
          game_id: options.gameId,
          import_job_id: options.importJobId,
        },
        query: {
          ...(options.status === undefined ? {} : { status: options.status }),
          ...(options.cursor === undefined ? {} : { cursor: options.cursor }),
          ...(options.limit === undefined ? {} : { limit: options.limit }),
        },
      }),
    getPendingBoardCellGeometry: (
      pendingId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedPendingBoardCellGeometry({
        client,
        path: {
          game_id: context.gameId,
          import_job_id: context.importJobId,
          pending_id: pendingId,
        },
      }),
    getPendingBoardCellGeometryCorrectionContext: (
      pendingId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedPendingBoardCellGeometryCorrectionContext({
        client,
        path: {
          game_id: context.gameId,
          import_job_id: context.importJobId,
          pending_id: pendingId,
        },
      }),
    getPendingBoardCellGeometrySource: (
      pendingId: string,
      context: OperationalImageReviewContext,
    ) =>
      getGeneratedPendingBoardCellGeometrySource({
        client,
        path: {
          game_id: context.gameId,
          import_job_id: context.importJobId,
          pending_id: pendingId,
        },
      }),
    previewPendingBoardCellGeometryCorrection: (
      pendingId: string,
      context: OperationalImageReviewContext,
      body: BoardCellGeometryManualPreviewCommand,
    ) =>
      previewGeneratedPendingBoardCellGeometryCorrection({
        body,
        client,
        path: {
          game_id: context.gameId,
          import_job_id: context.importJobId,
          pending_id: pendingId,
        },
      }),
    resolvePendingBoardCellGeometryManually: (
      pendingId: string,
      context: OperationalImageReviewContext,
      body: BoardCellGeometryManualResolutionCommand,
    ) =>
      resolveGeneratedPendingBoardCellGeometryManually({
        body,
        client,
        path: {
          game_id: context.gameId,
          import_job_id: context.importJobId,
          pending_id: pendingId,
        },
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
    previewBoardSourceCleanup: (
      gameId: string,
      body: BoardSourceCleanupPreviewRequest,
    ) =>
      previewGeneratedBoardSourceCleanup({
        body,
        client,
        path: { game_id: gameId },
      }),
    deleteBoardSourceRanges: (
      gameId: string,
      body: BoardSourceCleanupCommandRequest,
    ) =>
      deleteGeneratedBoardSourceRanges({
        body,
        client,
        headers: confirmedTargetHeaders(`board-source-ranges:${gameId}`),
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
    deleteSymbol: (gameId: string, symbolId: string) =>
      deleteGeneratedSymbol({
        client,
        headers: confirmedTargetHeaders(`symbol:${symbolId}`),
        path: { game_id: gameId, symbol_id: symbolId },
      }),
  } as const;
}

export type AdminApiClient = ReturnType<typeof createAdminApiClient>;
