import type {
  BrowserImageImportPreflightResponse,
  BrowserReadySelectionResponse,
  JobResponse,
  NeuralGridSnapshotPayload,
} from '@game-predictor/admin-api-client';

export function neuralImportSnapshot(
  job: JobResponse | null | undefined,
): NeuralGridSnapshotPayload | null {
  if (!job || !('neuralGridProposal' in job.inputPayload)) return null;
  const snapshot = job.inputPayload.neuralGridProposal;
  return snapshot?.contractVersion === 'neural-grid-proposal-snapshot-v1' &&
    Number.isSafeInteger(snapshot.expectedLayoutCount) &&
    snapshot.expectedLayoutCount > 0 &&
    snapshot.model?.profile === 'grid_profile_mumie_v1' &&
    snapshot.model.modelKind === 'neural_grid' &&
    snapshot.model.schemaVersion === 'grid-engine-model-manifest-v1'
    ? snapshot
    : null;
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
