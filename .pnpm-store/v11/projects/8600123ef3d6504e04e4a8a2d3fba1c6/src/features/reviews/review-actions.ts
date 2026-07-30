import type {
  AdminApiClient,
  ReviewBatchResponse,
  ReviewFeedbackExportResponse,
  ReviewItemResponse,
  ReviewItemStatus,
  ReviewResolutionCommand,
  ReviewResolutionResponse,
  SymbolResponse,
} from '@game-predictor/admin-api-client';

import { apiErrorMessage } from '../catalog/catalog-api-error.ts';
import { orderReviewItems } from './review-state.ts';

export type ReviewsClient = Pick<
  AdminApiClient,
  | 'createReviewFeedbackExport'
  | 'getReviewItem'
  | 'listReviewBatches'
  | 'listReviewFeedbackExports'
  | 'listReviewItems'
  | 'listReviewResolutions'
  | 'listSymbols'
  | 'resolveReviewItem'
>;

export type LoadReviewBatchesResult =
  | { readonly batches: readonly ReviewBatchResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadReviewBatches(
  api: ReviewsClient,
): Promise<LoadReviewBatchesResult> {
  try {
    const result = await api.listReviewBatches();
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać batchy manual review.',
        ),
        ok: false,
      };
    }
    return { batches: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type LoadReviewItemsResult =
  | {
      readonly items: readonly ReviewItemResponse[];
      readonly nextAfterSelectionRank: number | null;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false };

export async function loadReviewItems(
  api: ReviewsClient,
  reviewBatchId: string,
  status?: ReviewItemStatus,
): Promise<LoadReviewItemsResult> {
  try {
    const result = await api.listReviewItems(reviewBatchId, {
      afterSelectionRank: 0,
      limit: 100,
      ...(status === undefined ? {} : { status }),
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać kolejki manual review.',
        ),
        ok: false,
      };
    }
    return {
      items: orderReviewItems(result.data.items),
      nextAfterSelectionRank: result.data.nextAfterSelectionRank,
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export type LoadReviewItemResult =
  | { readonly item: ReviewItemResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false };

export async function loadReviewItem(
  api: ReviewsClient,
  reviewItemId: string,
): Promise<LoadReviewItemResult> {
  try {
    const result = await api.getReviewItem(reviewItemId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać szczegółów elementu review.',
        ),
        ok: false,
      };
    }
    return { item: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadReviewSymbols(
  api: ReviewsClient,
  gameId: string,
): Promise<
  | { readonly symbols: readonly SymbolResponse[]; readonly ok: true }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.listSymbols(gameId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać symboli do korekty.',
        ),
        ok: false,
      };
    }
    return {
      symbols: result.data.filter((symbol) => symbol.status === 'active'),
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function submitReviewResolution(
  api: ReviewsClient,
  reviewItemId: string,
  command: ReviewResolutionCommand,
): Promise<
  | {
      readonly item: ReviewItemResponse;
      readonly resolution: ReviewResolutionResponse;
      readonly created: boolean;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.resolveReviewItem(reviewItemId, command);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się zapisać decyzji review.',
        ),
        ok: false,
      };
    }
    return {
      item: result.data.item,
      resolution: result.data.resolution,
      created: result.data.created,
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadReviewResolutions(
  api: ReviewsClient,
  reviewItemId: string,
): Promise<
  | {
      readonly resolutions: readonly ReviewResolutionResponse[];
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.listReviewResolutions(reviewItemId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać historii decyzji.',
        ),
        ok: false,
      };
    }
    return { resolutions: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function createReviewFeedbackExport(
  api: ReviewsClient,
  reviewBatchId: string,
  createdBy: string,
): Promise<
  | {
      readonly feedbackExport: ReviewFeedbackExportResponse;
      readonly created: boolean;
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.createReviewFeedbackExport(reviewBatchId, {
      createdBy,
    });
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się utworzyć eksportu feedbacku.',
        ),
        ok: false,
      };
    }
    return {
      feedbackExport: result.data.feedbackExport,
      created: result.data.created,
      ok: true,
    };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}

export async function loadReviewFeedbackExports(
  api: ReviewsClient,
  reviewBatchId: string,
): Promise<
  | {
      readonly feedbackExports: readonly ReviewFeedbackExportResponse[];
      readonly ok: true;
    }
  | { readonly error: string; readonly ok: false }
> {
  try {
    const result = await api.listReviewFeedbackExports(reviewBatchId);
    if (result.error !== undefined || result.data === undefined) {
      return {
        error: apiErrorMessage(
          result.error,
          'Nie udało się pobrać eksportów feedbacku.',
        ),
        ok: false,
      };
    }
    return { feedbackExports: result.data, ok: true };
  } catch {
    return {
      error: 'Połączenie z lokalnym Admin API zostało przerwane.',
      ok: false,
    };
  }
}
