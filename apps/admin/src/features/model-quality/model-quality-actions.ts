import type {
  AdminApiClient,
  CreateSymbolTrainingResponse,
  ModelQualityResponse,
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
>;

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
    const [qualityResult, previewResult, iterationResult, activationResult] =
      await Promise.all([
        api.getModelQuality(gameId, { signal }),
        api.previewVerifiedTrainingCohort(gameId, { signal }),
        api.listSymbolModelIterations(gameId, { limit: 20, signal }),
        api.listSymbolModelActivations(gameId, { limit: 50, signal }),
      ]);
    if (
      qualityResult.error !== undefined ||
      qualityResult.data === undefined ||
      previewResult.error !== undefined ||
      previewResult.data === undefined ||
      iterationResult.error !== undefined ||
      iterationResult.data === undefined ||
      activationResult.error !== undefined ||
      activationResult.data === undefined
    ) {
      return {
        error: apiErrorMessage(
          qualityResult.error ??
            previewResult.error ??
            iterationResult.error ??
            activationResult.error,
          'Nie udało się pobrać jakości modelu i kohorty.',
        ),
        ok: false,
      };
    }
    if (
      qualityResult.data.gameId !== gameId ||
      previewResult.data.gameId !== gameId
    ) {
      return {
        error: 'Odpowiedź API nie należy do wybranej gry.',
        ok: false,
      };
    }
    return {
      ok: true,
      preview: previewResult.data,
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
