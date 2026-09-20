import type {
  BrowserReadySelectionResponse,
  GeometryEngineVariant,
  JobResponse,
} from '@game-predictor/admin-api-client';

const DEFAULT_READY_BOARD_IMPORT_GEOMETRY_VARIANT: GeometryEngineVariant =
  'selective_board_review_v1_1';

interface ReadyImportStartState {
  readonly geometryGuardResolutionManifestAvailable: boolean;
  readonly geometryGuardResolutionRequired: boolean;
  readonly geometryManifestAvailable: boolean;
  readonly geometryPreflightArtifactReady: boolean;
  readonly geometryPreflightCompleted: boolean;
  readonly geometryPreflightRequired: boolean;
  readonly symbolModelAvailable: boolean;
}

interface ReadyBoardImportLifecycleState {
  readonly geometryPreflightJobs: readonly JobResponse[];
  readonly importJobs: readonly JobResponse[];
  readonly reportPrepared: boolean;
  readonly selection: Pick<
    BrowserReadySelectionResponse,
    'manifestChecksumSha256' | 'uploadId' | 'importJobId' | 'importJobStatus'
  >;
}

export function readyBoardImportHasImport(
  selection: ReadyBoardImportLifecycleState['selection'],
  importJobs: readonly JobResponse[],
): boolean {
  return (
    selection.importJobId != null ||
    importJobs.some(
      (job) =>
        job.jobType === 'import' && jobMatchesReadySelection(job, selection),
    )
  );
}

function jobMatchesReadySelection(
  job: JobResponse,
  selection: ReadyBoardImportLifecycleState['selection'],
): boolean {
  const payload = job.inputPayload as unknown as Record<string, unknown>;
  return (
    payload.sourceSelectionId === selection.uploadId &&
    payload.sourceManifestSha256 === selection.manifestChecksumSha256
  );
}

export function readyBoardImportGeometryVariant(
  geometryPreflightJobs: readonly JobResponse[],
  selection: ReadyBoardImportLifecycleState['selection'],
): GeometryEngineVariant {
  const latest = geometryPreflightJobs
    .filter((job) => {
      const payload = job.inputPayload as unknown as Record<string, unknown>;
      const lateral = payload.lateralPartialGeometry;
      const variant =
        typeof lateral === 'object' && lateral !== null
          ? (lateral as Record<string, unknown>).variant
          : null;
      return (
        job.jobType === 'validate' &&
        payload.validationKind === 'page_geometry_preflight' &&
        jobMatchesReadySelection(job, selection) &&
        job.status !== 'cancelled' &&
        (payload.managedSourceJobId === undefined ||
          payload.managedSourceJobId === null) &&
        (variant === 'structured_lattice_v4_partial_sides' ||
          variant === 'selective_board_review_v1_1')
      );
    })
    .sort((left, right) => {
      const completed = (job: JobResponse) =>
        job.status === 'completed' &&
        typeof job.progress.pageGeometryPreflight
          ?.geometryManifestChecksumSha256 === 'string';
      return (
        Number(completed(right)) - Number(completed(left)) ||
        right.createdAt.localeCompare(left.createdAt) ||
        right.id.localeCompare(left.id)
      );
    })[0];
  const payload = latest?.inputPayload as unknown as
    Record<string, unknown> | undefined;
  const lateral = payload?.lateralPartialGeometry as
    Record<string, unknown> | undefined;
  if (lateral?.variant === 'selective_board_review_v1_1') {
    return 'selective_board_review_v1_1';
  }
  if (lateral?.variant === 'structured_lattice_v4_partial_sides') {
    return 'structured_lattice_v4_partial_sides';
  }
  return DEFAULT_READY_BOARD_IMPORT_GEOMETRY_VARIANT;
}

export function readyBoardImportLifecycleLabel(
  state: ReadyBoardImportLifecycleState,
): string {
  const imported = state.importJobs.find(
    (job) =>
      job.jobType === 'import' &&
      jobMatchesReadySelection(job, state.selection),
  );
  const importStatus = state.selection.importJobStatus ?? imported?.status;
  if (readyBoardImportHasImport(state.selection, state.importJobs)) {
    switch (importStatus) {
      case 'completed':
        return 'gotowy · import zakończony';
      case 'waiting_for_review':
        return 'pocięty · oczekuje na weryfikację plansz i symboli';
      case 'created':
        return 'import w kolejce';
      case 'processing':
        return 'trwa cięcie plansz i symboli';
      case 'failed':
        return 'import przerwany · sprawdź istniejący job';
      case 'cancelled':
        return 'import anulowany · sprawdź istniejący job';
      default:
        return 'staging przekazany do importu';
    }
  }
  const matchingGeometryJobs = state.geometryPreflightJobs.filter((job) => {
    const payload = job.inputPayload as unknown as Record<string, unknown>;
    return (
      job.jobType === 'validate' &&
      payload.validationKind === 'page_geometry_preflight' &&
      jobMatchesReadySelection(job, state.selection)
    );
  });
  const latestCompletedGeometry = matchingGeometryJobs
    .filter(
      (job) =>
        job.status === 'completed' &&
        typeof job.progress.pageGeometryPreflight
          ?.geometryManifestChecksumSha256 === 'string',
    )
    .sort(
      (left, right) =>
        right.createdAt.localeCompare(left.createdAt) ||
        right.id.localeCompare(left.id),
    )[0];
  const reviewRequired =
    latestCompletedGeometry?.progress.pageGeometryPreflight
      ?.provisionalReviewRequired;
  if (typeof reviewRequired === 'number' && reviewRequired > 0) {
    return `wymaga korekty geometrii · odroczone zdjęcia ${reviewRequired.toLocaleString('pl-PL')}`;
  }

  const geometryReady = matchingGeometryJobs.some(
    (job) =>
      job.status === 'completed' &&
      typeof job.progress.pageGeometryPreflight
        ?.geometryManifestChecksumSha256 === 'string' &&
      job.progress.pageGeometryPreflight.geometryManifestChecksumSha256.length >
        0,
  );
  if (geometryReady) {
    return 'oczekuje na operację · przygotowano siatkę';
  }
  if (state.reportPrepared || matchingGeometryJobs.length > 0) {
    return 'oczekuje na operację · przygotowano preflight';
  }
  return 'oczekuje na operację · załadowano folder';
}

export function canStartReadyImport(state: ReadyImportStartState): boolean {
  return (
    state.symbolModelAvailable &&
    (!state.geometryPreflightRequired ||
      (state.geometryPreflightCompleted &&
        state.geometryManifestAvailable &&
        state.geometryPreflightArtifactReady)) &&
    (!state.geometryGuardResolutionRequired ||
      state.geometryGuardResolutionManifestAvailable)
  );
}

export function pageGeometryPreflightOutcomeLabel(
  job: Pick<JobResponse, 'progress' | 'status'>,
  visibleGeometryCorrectionCount: number,
): string {
  if (job.status === 'completed') {
    return `odroczone zdjęcia ${visibleGeometryCorrectionCount.toLocaleString('pl-PL')}`;
  }

  const provisionalReviewRequired =
    job.progress.pageGeometryPreflight?.provisionalReviewRequired;
  if (typeof provisionalReviewRequired === 'number') {
    return `jeszcze nierozstrzygnięte zdjęcia ${provisionalReviewRequired.toLocaleString('pl-PL')}`;
  }

  return 'wynik końcowy jeszcze niegotowy';
}

function leadingRangeStart(displayName: string): number | null {
  const match = /^\s*(\d+)\s*-/.exec(displayName);
  if (match === null) return null;
  const value = Number(match[1]);
  return Number.isSafeInteger(value) ? value : null;
}

export function sortReadyBoardImports(
  selections: readonly BrowserReadySelectionResponse[],
): readonly BrowserReadySelectionResponse[] {
  return [...selections].sort((left, right) => {
    const leftStart = leadingRangeStart(left.displayName);
    const rightStart = leadingRangeStart(right.displayName);
    if (leftStart !== null && rightStart !== null && leftStart !== rightStart) {
      return leftStart - rightStart;
    }
    if (leftStart !== null && rightStart === null) return -1;
    if (leftStart === null && rightStart !== null) return 1;
    return (
      left.displayName.localeCompare(right.displayName, 'pl-PL', {
        numeric: true,
        sensitivity: 'base',
      }) || left.uploadId.localeCompare(right.uploadId)
    );
  });
}
