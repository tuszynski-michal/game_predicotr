import type {
  BrowserImageImportPreflightResponse,
  BrowserReadySelectionResponse,
  JobResponse,
  NeuralGridSnapshotPayload,
  CatalogueNeuralGridSnapshotPayload,
} from '@game-predictor/admin-api-client';

// D-544: each grid engine profile pins its own frozen neural model.
const NEURAL_IMPORT_PROFILES: ReadonlySet<string> = new Set([
  'grid_profile_777_v2',
  'grid_profile_mumie_v1',
]);

export function neuralImportSnapshot(
  job: JobResponse | null | undefined,
): NeuralGridSnapshotPayload | CatalogueNeuralGridSnapshotPayload | null {
  if (!job || !('neuralGridProposal' in job.inputPayload)) return null;
  const snapshot = job.inputPayload.neuralGridProposal;
  if (snapshot?.contractVersion === 'neural-grid-proposal-snapshot-v2') {
    return snapshot.gameId === job.gameId &&
      Number.isSafeInteger(snapshot.expectedLayoutCount) &&
      snapshot.expectedLayoutCount > 0 &&
      snapshot.catalogueManifest.modelKind === 'neural_grid' &&
      snapshot.catalogueManifest.schemaVersion === 'grid-model-catalogue-v1'
      ? snapshot
      : null;
  }
  return snapshot?.contractVersion === 'neural-grid-proposal-snapshot-v1' &&
    Number.isSafeInteger(snapshot.expectedLayoutCount) &&
    snapshot.expectedLayoutCount > 0 &&
    NEURAL_IMPORT_PROFILES.has(snapshot.model?.profile) &&
    snapshot.model.modelKind === 'neural_grid' &&
    snapshot.model.schemaVersion === 'grid-engine-model-manifest-v1'
    ? snapshot
    : null;
}

export function neuralImportModelExportId(
  job: JobResponse | null | undefined,
): string | null {
  const snapshot = neuralImportSnapshot(job);
  if (!snapshot) return null;
  return snapshot.contractVersion === 'neural-grid-proposal-snapshot-v2'
    ? snapshot.catalogueManifest.inferenceManifest.exportId
    : snapshot.model.exportId;
}

export function isNeuralGeometryPreflight(
  job: JobResponse | null | undefined,
): boolean {
  return (
    job?.jobType === 'validate' &&
    'preflightPolicyVersion' in job.inputPayload &&
    job.inputPayload.preflightPolicyVersion ===
      'page-geometry-preflight-v13-neural-mumie-pilot' &&
    neuralImportSnapshot(job) !== null
  );
}

function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (value && typeof value === 'object')
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`)
      .join(',')}}`;
  return JSON.stringify(value) ?? 'undefined';
}

export function neuralGeometryMatchesReport(
  job: JobResponse,
  report: BrowserImageImportPreflightResponse,
): boolean {
  const pinned = report.geometryPreflightJob;
  if (!isNeuralGeometryPreflight(job) || !isNeuralGeometryPreflight(pinned))
    return false;
  const payload = job.inputPayload as unknown as Record<string, unknown>;
  const pinnedPayload = pinned!.inputPayload as unknown as Record<
    string,
    unknown
  >;
  const managed = payload.managedSourceJobId;
  return (
    job.gameId === report.gameId &&
    pinned!.gameId === report.gameId &&
    payload.sourceSelectionId === report.uploadId &&
    payload.sourceManifestSha256 === report.manifestChecksumSha256 &&
    pinnedPayload.sourceSelectionId === report.uploadId &&
    pinnedPayload.sourceManifestSha256 === report.manifestChecksumSha256 &&
    report.geometryEngineVariant == null &&
    canonical(neuralImportSnapshot(job)) ===
      canonical(neuralImportSnapshot(pinned)) &&
    (managed == null ||
      managed === pinnedPayload.managedSourceJobId ||
      managed === report.existingImportJob?.id)
  );
}

export function readySelectionHasNeuralImport(
  jobs: readonly JobResponse[],
  selection: Pick<
    BrowserReadySelectionResponse,
    'uploadId' | 'manifestChecksumSha256'
  >,
  gameId: string,
): boolean {
  return jobs.some((job) => {
    const payload = job.inputPayload as unknown as Record<string, unknown>;
    return (
      job.jobType === 'import' &&
      payload.importKind === 'image_directory' &&
      job.gameId === gameId &&
      neuralImportSnapshot(job) !== null &&
      payload.sourceSelectionId === selection.uploadId &&
      payload.sourceManifestSha256 === selection.manifestChecksumSha256
    );
  });
}

/**
 * TASK-1041: a V3 import skips sources whose network detections have no board
 * slot binding. The operator confirms the exact count for one staging and one
 * frozen geometry manifest; a new preflight or count needs a new confirmation.
 */
export interface NeuralUnboundSkipConfirmation {
  readonly uploadId: string;
  readonly geometryManifestChecksumSha256: string | null;
  readonly sourceCount: number;
}

export function neuralUnboundSkipConfirmed(
  report: Pick<
    BrowserImageImportPreflightResponse,
    'uploadId' | 'neuralUnboundSourceCount'
  >,
  geometryManifestChecksumSha256: string | null,
  confirmation: NeuralUnboundSkipConfirmation | null,
): boolean {
  const count = report.neuralUnboundSourceCount ?? 0;
  return (
    count === 0 ||
    (confirmation !== null &&
      confirmation.uploadId === report.uploadId &&
      confirmation.geometryManifestChecksumSha256 ===
        geometryManifestChecksumSha256 &&
      confirmation.sourceCount === count)
  );
}

export function neuralUnboundSourcesLabel(
  sourceCount: number,
  attestedBoardCount: number,
): string {
  return `Pominięte bez przypisania plansz: ${sourceCount.toLocaleString('pl-PL')} zdjęć (zakresy z nazw plików: ${attestedBoardCount.toLocaleString('pl-PL')} plansz)`;
}

export function neuralUnboundReasonLabel(reasonCode: string): string {
  if (reasonCode === 'NEURAL_GRID_SLOT_BINDING_REQUIRED')
    return 'wykrycia sieci nie pasują jednoznacznie do plansz z zakresu';
  if (reasonCode === 'NEURAL_GRID_SOURCE_TIME_LIMIT')
    return 'przekroczony czas analizy zdjęcia';
  return reasonCode;
}

/** A new frozen manifest may materialize an operator-bound source after a pending-only run. */
export function canResumeNeuralImport(
  report: BrowserImageImportPreflightResponse,
  jobs: readonly JobResponse[],
): boolean {
  const geometry = report.geometryPreflightJob;
  if (
    !geometry ||
    !neuralGeometryMatchesReport(geometry, report) ||
    geometry.status !== 'completed' ||
    geometry.progress.pageGeometryPreflight?.complete !== true
  )
    return false;
  const checksum =
    geometry.progress.pageGeometryPreflight.geometryManifestChecksumSha256;
  if (!checksum) return false;
  const previous = report.existingImportJob;
  if (
    !previous ||
    neuralImportSnapshot(previous) === null ||
    !['completed', 'failed', 'cancelled'].includes(previous.status)
  )
    return false;
  const payload = previous.inputPayload as unknown as Record<string, unknown>;
  if (
    payload.sourceSelectionId !== report.uploadId ||
    payload.sourceManifestSha256 !== report.manifestChecksumSha256 ||
    previous.gameId !== report.gameId
  )
    return false;
  const descriptor = payload.pageGeometryManifest as
    Record<string, unknown> | undefined;
  if (
    !descriptor ||
    (descriptor.preflightJobId === geometry.id &&
      descriptor.checksumSha256 === checksum)
  )
    return false;
  return !jobs.some((job) => {
    const candidate = job.inputPayload as unknown as Record<string, unknown>;
    return (
      job.jobType === 'import' &&
      job.gameId === report.gameId &&
      candidate.sourceSelectionId === report.uploadId &&
      candidate.sourceManifestSha256 === report.manifestChecksumSha256 &&
      !['completed', 'failed', 'cancelled'].includes(job.status)
    );
  });
}
