import { createClient as createGeneratedClient } from './generated/client';
import {
  archiveDatasetVersion as archiveGeneratedDatasetVersion,
  archiveGame as archiveGeneratedGame,
  archivePayline as archiveGeneratedPayline,
  archivePayoutRule as archiveGeneratedPayoutRule,
  archiveRulesVersion as archiveGeneratedRulesVersion,
  archiveSymbol as archiveGeneratedSymbol,
  buildMobileRelease as buildGeneratedMobileRelease,
  cancelJob as cancelGeneratedJob,
  createJob as createGeneratedJob,
  createGame as createGeneratedGame,
  createMobileRelease as createGeneratedMobileRelease,
  downloadMobileReleaseApk as downloadGeneratedMobileReleaseApk,
  createPayline as createGeneratedPayline,
  createPayoutRule as createGeneratedPayoutRule,
  createRulesVersion as createGeneratedRulesVersion,
  createSymbol as createGeneratedSymbol,
  generateMockDataset as generateGeneratedMockDataset,
  getDatasetValidationReport as getGeneratedDatasetValidationReport,
  getDatasetVersion as getGeneratedDatasetVersion,
  getGame as getGeneratedGame,
  getHealth as getGeneratedHealth,
  getJob as getGeneratedJob,
  getLayoutImportIntegrityReport as getGeneratedLayoutImportIntegrityReport,
  getMobileRelease as getGeneratedMobileRelease,
  getPayline as getGeneratedPayline,
  getPayoutRule as getGeneratedPayoutRule,
  getRulesPublicationReadiness as getGeneratedRulesPublicationReadiness,
  getRulesVersion as getGeneratedRulesVersion,
  getSymbol as getGeneratedSymbol,
  listGames as listGeneratedGames,
  listJobs as listGeneratedJobs,
  listLayoutImportNormalizedRows as listGeneratedLayoutImportNormalizedRows,
  listMobileReleases as listGeneratedMobileReleases,
  listDatasetLayouts as listGeneratedDatasetLayouts,
  listDatasetVersions as listGeneratedDatasetVersions,
  listPaylines as listGeneratedPaylines,
  listPayoutRules as listGeneratedPayoutRules,
  listRulesVersions as listGeneratedRulesVersions,
  listRulesVersionSymbols as listGeneratedRulesVersionSymbols,
  listSymbols as listGeneratedSymbols,
  publishRulesVersion as publishGeneratedRulesVersion,
  publishDatasetVersion as publishGeneratedDatasetVersion,
  publishLayoutImportDataset as publishGeneratedLayoutImportDataset,
  rejectLayoutImportStaging as rejectGeneratedLayoutImportStaging,
  retryJob as retryGeneratedJob,
  updateGame as updateGeneratedGame,
  updatePayline as updateGeneratedPayline,
  updatePayoutRule as updateGeneratedPayoutRule,
  updateRulesVersion as updateGeneratedRulesVersion,
  updateRulesVersionSymbol as updateGeneratedRulesVersionSymbol,
  updateSymbol as updateGeneratedSymbol,
} from './generated/sdk.gen';
import type {
  CreateJobData,
  JobStatus,
  JobType,
  LayoutImportRowStatus,
  MockDatasetCreate,
  MobileReleaseCreate,
  GameCreate,
  GameUpdate,
  PaylineCreate,
  PaylineUpdate,
  PayoutRuleCreate,
  PayoutRuleUpdate,
  RulesVersionCreate,
  RulesVersionSymbolUpdate,
  RulesVersionUpdate,
  SymbolCreate,
  SymbolUpdate,
} from './generated/types.gen';

export type {
  AndroidBuildJobCreate,
  AndroidBuildJobPayload,
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
  HealthResponse,
  ImportJobCreate,
  ImportJobPayload,
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
  SymbolCreate,
  SymbolResponse,
  SymbolStatus,
  SymbolUpdate,
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

export function createAdminApiClient(options: AdminApiClientOptions) {
  const client = createGeneratedClient({
    baseUrl: options.baseUrl,
    ...(options.fetch === undefined ? {} : { fetch: options.fetch }),
  });

  return {
    getHealth: () => getGeneratedHealth({ client }),
    createJob: (body: JobCreate) => createGeneratedJob({ body, client }),
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
    getJob: (jobId: string) =>
      getGeneratedJob({ client, path: { job_id: jobId } }),
    cancelJob: (jobId: string) =>
      cancelGeneratedJob({ client, path: { job_id: jobId } }),
    retryJob: (jobId: string) =>
      retryGeneratedJob({ client, path: { job_id: jobId } }),
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
        path: { validation_job_id: validationJobId },
      }),
    publishLayoutImportDataset: (validationJobId: string) =>
      publishGeneratedLayoutImportDataset({
        client,
        path: { validation_job_id: validationJobId },
      }),
    listMobileReleases: () => listGeneratedMobileReleases({ client }),
    createMobileRelease: (body: MobileReleaseCreate) =>
      createGeneratedMobileRelease({ body, client }),
    getMobileRelease: (mobileReleaseId: string) =>
      getGeneratedMobileRelease({
        client,
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
        path: { mobile_release_id: mobileReleaseId },
      }),
    listGames: () => listGeneratedGames({ client }),
    createGame: (body: GameCreate) => createGeneratedGame({ body, client }),
    getGame: (gameId: string) =>
      getGeneratedGame({ client, path: { game_id: gameId } }),
    updateGame: (gameId: string, body: GameUpdate) =>
      updateGeneratedGame({ body, client, path: { game_id: gameId } }),
    archiveGame: (gameId: string) =>
      archiveGeneratedGame({ client, path: { game_id: gameId } }),
    listRulesVersions: (gameId: string) =>
      listGeneratedRulesVersions({ client, path: { game_id: gameId } }),
    createRulesVersion: (gameId: string, body: RulesVersionCreate) =>
      createGeneratedRulesVersion({
        body,
        client,
        path: { game_id: gameId },
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
        path: { rules_version_id: rulesVersionId },
      }),
    archiveRulesVersion: (rulesVersionId: string) =>
      archiveGeneratedRulesVersion({
        client,
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
        path: { dataset_version_id: datasetVersionId },
      }),
    archiveDatasetVersion: (datasetVersionId: string) =>
      archiveGeneratedDatasetVersion({
        client,
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
        path: { game_id: gameId, symbol_id: symbolId },
      }),
  } as const;
}

export type AdminApiClient = ReturnType<typeof createAdminApiClient>;
