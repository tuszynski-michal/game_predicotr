import type {
  AdminApiClient,
  SourceCropRunResponse,
} from '@game-predictor/admin-api-client';

import type { SourceCropKind, SourceCropScope } from './source-crop-state.ts';
import { isStartable, sourceCropErrorMessage } from './source-crop-state.ts';

export type SourceCropClient = Pick<
  AdminApiClient,
  | 'createSourceCropPreview'
  | 'getSourceCropRun'
  | 'listGames'
  | 'listSourceCropRuns'
  | 'startSourceCropRun'
>;

export type SourceCropRunResult =
  | { readonly ok: true; readonly run: SourceCropRunResponse }
  | { readonly ok: false; readonly error: string };

const CONNECTION_LOST = 'Połączenie z lokalnym Admin API zostało przerwane.';

/** Requests a plan; the worker builds the preview, so the run starts as planning. */
export async function planSourceCrop(
  api: SourceCropClient,
  kind: SourceCropKind,
  scope: SourceCropScope,
): Promise<SourceCropRunResult> {
  try {
    const result = await api.createSourceCropPreview({ kind, scope });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: sourceCropErrorMessage(
          result.error,
          'Nie udało się zaplanować przebiegu.',
        ),
        ok: false,
      };
    }
    return { ok: true, run: result.data };
  } catch {
    return { error: CONNECTION_LOST, ok: false };
  }
}

export async function refreshSourceCropRun(
  api: SourceCropClient,
  runId: string,
): Promise<SourceCropRunResult> {
  try {
    const result = await api.getSourceCropRun(runId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: sourceCropErrorMessage(
          result.error,
          'Nie udało się odczytać postępu przebiegu.',
        ),
        ok: false,
      };
    }
    return { ok: true, run: result.data };
  } catch {
    return { error: CONNECTION_LOST, ok: false };
  }
}

/**
 * Starts a previewed run with the immutable manifest checksum and token. A
 * deletion run is never sent without the irreversibility acknowledgement.
 */
export async function startSourceCrop(
  api: SourceCropClient,
  run: SourceCropRunResponse,
  acknowledgeIrreversible: boolean,
): Promise<SourceCropRunResult> {
  if (
    !isStartable(run) ||
    run.manifestChecksumSha256 == null ||
    run.previewToken == null
  ) {
    return {
      error: 'Podgląd nie jest gotowy do uruchomienia. Zaplanuj go ponownie.',
      ok: false,
    };
  }
  if (run.kind === 'original_deletion' && !acknowledgeIrreversible) {
    return {
      error:
        'Zaznacz, że rozumiesz nieodwracalność usunięcia oryginałów (brak kopii zdjęć).',
      ok: false,
    };
  }
  try {
    const result = await api.startSourceCropRun(run.id, {
      ...(run.kind === 'original_deletion'
        ? { acknowledgeIrreversible: true }
        : {}),
      confirmed: true,
      manifestChecksumSha256: run.manifestChecksumSha256,
      previewToken: run.previewToken,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: sourceCropErrorMessage(
          result.error,
          'Nie udało się uruchomić przebiegu. Zaplanuj go ponownie.',
        ),
        ok: false,
      };
    }
    return { ok: true, run: result.data };
  } catch {
    return { error: CONNECTION_LOST, ok: false };
  }
}

export type LoadRunsResult =
  | { readonly ok: true; readonly runs: readonly SourceCropRunResponse[] }
  | { readonly ok: false; readonly error: string };

export async function loadSourceCropRuns(
  api: SourceCropClient,
): Promise<LoadRunsResult> {
  try {
    const result = await api.listSourceCropRuns(20);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: sourceCropErrorMessage(
          result.error,
          'Nie udało się odczytać ostatnich przebiegów przycinania.',
        ),
        ok: false,
      };
    }
    return { ok: true, runs: result.data.runs };
  } catch {
    return { error: CONNECTION_LOST, ok: false };
  }
}
