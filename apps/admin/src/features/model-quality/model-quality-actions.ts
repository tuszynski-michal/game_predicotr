import type {
  AdminApiClient,
  CreateGridCalibrationCandidateResponse,
  CreateSymbolTrainingResponse,
  GridCalibrationProfileResponse,
  GeometryCohortDiagnosticsResponse,
  GridProfileActivationAction,
  GridProfileActivationCommandResponse,
  GridProfileActivationPreviewResponse,
  GridProfileActivationResponse,
  ModelQualityResponse,
  JobResponse,
  PendingSymbolReinferencePreviewResponse,
  PendingGridReinferencePreviewResponse,
  SymbolModelActivationAction,
  SymbolModelActivationCommandResponse,
  SymbolModelActivationPreviewResponse,
  SymbolModelActivationResponse,
  SymbolModelIterationResponse,
  VerifiedTrainingCohortFreezeResponse,
  VerifiedTrainingCohortPreviewResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';

export type ModelQualityClient = Pick<
  AdminApiClient,
  | 'freezeVerifiedTrainingCohort'
  | 'createSymbolTraining'
  | 'getModelQuality'
  | 'activateSymbolModel'
  | 'listSymbolModelActivations'
  | 'listSymbolModelIterations'
  | 'previewSymbolModelActivation'
  | 'previewVerifiedTrainingCohort'
  | 'rollbackSymbolModel'
  | 'previewPendingSymbolReinference'
  | 'startPendingSymbolReinference'
>;

export type PendingSymbolReinferenceResult =
  | {
      readonly ok: true;
      readonly preview: PendingSymbolReinferencePreviewResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function previewPendingSymbolReinference(
  api: ModelQualityClient,
  gameId: string,
): Promise<PendingSymbolReinferenceResult> {
  try {
    const result = await api.previewPendingSymbolReinference(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać oczekujących predykcji.',
        ),
        ok: false,
      };
    }
    return { ok: true, preview: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startPendingSymbolReinference(
  api: ModelQualityClient,
  gameId: string,
): Promise<
  | { readonly error: string; readonly ok: false }
  | { readonly job: JobResponse; readonly ok: true }
> {
  try {
    const result = await api.startPendingSymbolReinference(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić przeliczenia.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type GridQualityClient = Pick<
  AdminApiClient,
  | 'activateGridProfile'
  | 'createGridCalibrationCandidate'
  | 'listGridCalibrationProfiles'
  | 'listGridProfileActivations'
  | 'previewGridProfileActivation'
  | 'rollbackGridProfile'
  | 'getGridCalibrationCohortDiagnostics'
  | 'previewPendingGridReinference'
  | 'startPendingGridReinference'
>;

export type GridQualityLoadResult =
  | {
      readonly ok: true;
      readonly profiles: readonly GridCalibrationProfileResponse[];
      readonly activations: readonly GridProfileActivationResponse[];
      readonly diagnostics: GeometryCohortDiagnosticsResponse;
    }
  | { readonly error: string; readonly ok: false };

export type GridCandidateResult =
  | {
      readonly ok: true;
      readonly response: CreateGridCalibrationCandidateResponse;
    }
  | { readonly error: string; readonly ok: false };

export type GridActivationPreviewResult =
  | {
      readonly ok: true;
      readonly preview: GridProfileActivationPreviewResponse;
    }
  | { readonly error: string; readonly ok: false };

export type GridActivationResult =
  | {
      readonly ok: true;
      readonly response: GridProfileActivationCommandResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function loadGridQuality(
  api: GridQualityClient,
  gameId: string,
  signal?: AbortSignal,
): Promise<GridQualityLoadResult> {
  try {
    const [profileResult, activationResult, diagnosticsResult] =
      await Promise.all([
        api.listGridCalibrationProfiles(gameId, { limit: 20, signal }),
        api.listGridProfileActivations(gameId, { limit: 50, signal }),
        api.getGridCalibrationCohortDiagnostics(gameId, { signal }),
      ]);
    if (
      profileResult.error !== undefined ||
      profileResult.data === undefined ||
      activationResult.error !== undefined ||
      activationResult.data === undefined ||
      diagnosticsResult.error !== undefined ||
      diagnosticsResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          profileResult.error ??
            activationResult.error ??
            diagnosticsResult.error,
          'Nie udało się pobrać stanu kalibracji siatki.',
        ),
        ok: false,
      };
    }
    return {
      ok: true,
      profiles: profileResult.data,
      activations: activationResult.data,
      diagnostics: diagnosticsResult.data,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { error: 'REQUEST_ABORTED', ok: false };
    }
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type PendingGridReinferenceResult =
  | {
      readonly ok: true;
      readonly preview: PendingGridReinferencePreviewResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function previewPendingGridReinference(
  api: GridQualityClient,
  gameId: string,
): Promise<PendingGridReinferenceResult> {
  try {
    const result = await api.previewPendingGridReinference(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać oczekującej siatki.',
        ),
        ok: false,
      };
    }
    return { ok: true, preview: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function startPendingGridReinference(
  api: GridQualityClient,
  gameId: string,
): Promise<
  | { readonly error: string; readonly ok: false }
  | { readonly job: JobResponse; readonly ok: true }
> {
  try {
    const result = await api.startPendingGridReinference(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się uruchomić odświeżenia siatki.',
        ),
        ok: false,
      };
    }
    return { job: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function createGridCandidate(
  api: GridQualityClient,
  gameId: string,
): Promise<GridCandidateResult> {
  try {
    const result = await api.createGridCalibrationCandidate(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć kandydata kalibracji siatki.',
        ),
        ok: false,
      };
    }
    return { ok: true, response: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function previewGridActivation(
  api: GridQualityClient,
  input: {
    readonly action: GridProfileActivationAction;
    readonly gameId: string;
    readonly profileId: string;
  },
): Promise<GridActivationPreviewResult> {
  try {
    const result = await api.previewGridProfileActivation(
      input.gameId,
      input.profileId,
      input.action,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować aktywacji kalibracji siatki.',
        ),
        ok: false,
      };
    }
    return { ok: true, preview: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function confirmGridActivation(
  api: GridQualityClient,
  input: {
    readonly action: GridProfileActivationAction;
    readonly actor: string;
    readonly gameId: string;
    readonly idempotencyKey: string;
    readonly preview: GridProfileActivationPreviewResponse;
  },
): Promise<GridActivationResult> {
  const command = {
    actor: input.actor,
    expectedCurrentProfileId: input.preview.currentProfileId,
    expectedProfileChecksumSha256: input.preview.profileChecksumSha256,
    idempotencyKey: input.idempotencyKey,
    reason:
      input.action === 'rollback'
        ? 'Owner-confirmed grid calibration rollback.'
        : 'Owner-confirmed grid calibration activation.',
  } as const;
  try {
    const result =
      input.action === 'rollback'
        ? await api.rollbackGridProfile(
            input.gameId,
            input.preview.profileId,
            command,
          )
        : await api.activateGridProfile(
            input.gameId,
            input.preview.profileId,
            command,
          );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zmienić aktywnego profilu siatki.',
        ),
        ok: false,
      };
    }
    return { ok: true, response: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type ModelQualityLoadResult =
  | {
      readonly ok: true;
      readonly preview: VerifiedTrainingCohortPreviewResponse;
      readonly quality: ModelQualityResponse;
      readonly iterations: readonly SymbolModelIterationResponse[];
      readonly activations: readonly SymbolModelActivationResponse[];
    }
  | { readonly error: string; readonly ok: false };

export type ModelQualityFreezeResult =
  | {
      readonly freeze: VerifiedTrainingCohortFreezeResponse;
      readonly training: CreateSymbolTrainingResponse;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export type ModelActivationPreviewResult =
  | {
      readonly ok: true;
      readonly preview: SymbolModelActivationPreviewResponse;
    }
  | { readonly error: string; readonly ok: false };

export type ModelActivationResult =
  | {
      readonly ok: true;
      readonly response: SymbolModelActivationCommandResponse;
    }
  | { readonly error: string; readonly ok: false };

export async function loadModelQuality(
  api: ModelQualityClient,
  gameId: string,
  signal?: AbortSignal,
): Promise<ModelQualityLoadResult> {
  try {
    const [qualityResult, iterationResult, activationResult] =
      await Promise.all([
        api.getModelQuality(gameId, { signal }),
        api.listSymbolModelIterations(gameId, { limit: 20, signal }),
        api.listSymbolModelActivations(gameId, { limit: 50, signal }),
      ]);
    if (
      qualityResult.error !== undefined ||
      qualityResult.data === undefined ||
      iterationResult.error !== undefined ||
      iterationResult.data === undefined ||
      activationResult.error !== undefined ||
      activationResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          qualityResult.error ??
            iterationResult.error ??
            activationResult.error,
          'Nie udało się pobrać jakości modelu i kohorty.',
        ),
        ok: false,
      };
    }
    if (qualityResult.data.gameId !== gameId) {
      return {
        error: 'Odpowiedź API nie należy do wybranej gry.',
        ok: false,
      };
    }
    return {
      ok: true,
      preview: modelQualityPreview(qualityResult.data),
      quality: qualityResult.data,
      iterations: iterationResult.data,
      activations: activationResult.data,
    };
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return { error: 'REQUEST_ABORTED', ok: false };
    }
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

function modelQualityPreview(
  quality: ModelQualityResponse,
): VerifiedTrainingCohortPreviewResponse {
  return {
    cellSampleCount: quality.cellSampleCount,
    gameId: quality.gameId,
    incompleteItemCount: quality.incompleteItemCount,
    manifestChecksumSha256: quality.manifestChecksumSha256,
    manifestSchemaVersion: quality.manifestSchemaVersion,
    pendingItemCount: quality.pendingItemCount,
    protectedItemCount: quality.protectedItemCount,
    rejectedItemCount: quality.rejectedItemCount,
    resolvedLayoutCount: quality.resolvedLayoutCount,
    sourceImageCount: quality.sourceImageCount,
    trainingExclusions: quality.trainingExclusions,
    warnings: quality.warnings,
  };
}

export async function previewModelActivation(
  api: ModelQualityClient,
  input: {
    readonly action: SymbolModelActivationAction;
    readonly gameId: string;
    readonly iterationId: string;
  },
): Promise<ModelActivationPreviewResult> {
  try {
    const result = await api.previewSymbolModelActivation(
      input.gameId,
      input.iterationId,
      input.action,
    );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się przygotować aktywacji modelu.',
        ),
        ok: false,
      };
    }
    return { ok: true, preview: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function confirmModelActivation(
  api: ModelQualityClient,
  input: {
    readonly action: SymbolModelActivationAction;
    readonly actor: string;
    readonly gameId: string;
    readonly idempotencyKey: string;
    readonly preview: SymbolModelActivationPreviewResponse;
  },
): Promise<ModelActivationResult> {
  const command = {
    actor: input.actor,
    expectedCurrentModelIterationId: input.preview.currentModelIterationId,
    expectedManifestChecksumSha256:
      input.preview.candidateManifestChecksumSha256,
    idempotencyKey: input.idempotencyKey,
    reason:
      input.action === 'rollback'
        ? 'Owner-confirmed rollback from Admin model quality workspace.'
        : 'Owner-confirmed activation from Admin model quality workspace.',
  } as const;
  try {
    const result =
      input.action === 'rollback'
        ? await api.rollbackSymbolModel(
            input.gameId,
            input.preview.modelIterationId,
            command,
          )
        : await api.activateSymbolModel(
            input.gameId,
            input.preview.modelIterationId,
            command,
          );
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zmienić aktywnego modelu.',
        ),
        ok: false,
      };
    }
    return { ok: true, response: result.data };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function freezeModelQualityCohort(
  api: ModelQualityClient,
  input: {
    readonly actor: string;
    readonly gameId: string;
    readonly idempotencyKey: string;
    readonly manifestChecksumSha256: string;
  },
): Promise<ModelQualityFreezeResult> {
  try {
    const result = await api.freezeVerifiedTrainingCohort(input.gameId, {
      createdBy: input.actor,
      expectedManifestChecksumSha256: input.manifestChecksumSha256,
      idempotencyKey: input.idempotencyKey,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zamrozić kohorty treningowej.',
        ),
        ok: false,
      };
    }
    if (result.data.cohort.gameId !== input.gameId) {
      return {
        error: 'Zamrożona kohorta nie należy do wybranej gry.',
        ok: false,
      };
    }
    const trainingResult = await api.createSymbolTraining(input.gameId, {
      cohortId: result.data.cohort.id,
      idempotencyKey: input.idempotencyKey,
    });
    if (
      trainingResult.error !== undefined ||
      trainingResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          trainingResult.error,
          'Kohorta zostaÅ‚a zamroÅ¼ona, ale nie udaÅ‚o siÄ™ uruchomiÄ‡ treningu.',
        ),
        ok: false,
      };
    }
    return { freeze: result.data, training: trainingResult.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
