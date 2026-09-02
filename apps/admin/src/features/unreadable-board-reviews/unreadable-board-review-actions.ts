import type {
  SaveUnreadableBoardRequest,
  SymbolResponse,
  UnreadableBoardReviewDetailResponse,
  UnreadableBoardReviewPageResponse,
  UnreadableBoardReviewView,
} from '@game-predictor/admin-api-client';

import type { createConfiguredAdminApiClient } from '@/api/admin-api-client';
import { apiErrorMessage } from '@/features/catalog/catalog-api-error';

export type UnreadableBoardReviewClient = Pick<
  ReturnType<typeof createConfiguredAdminApiClient>,
  | 'getUnreadableBoardReview'
  | 'listSymbols'
  | 'listUnreadableBoardReviews'
  | 'saveUnreadableBoardReview'
  | 'symbolCellReviewAssetUrl'
>;

export async function loadUnreadableBoardPage(
  api: UnreadableBoardReviewClient,
  gameId: string,
  view: UnreadableBoardReviewView,
  afterCursor?: string,
): Promise<
  | { readonly ok: true; readonly page: UnreadableBoardReviewPageResponse }
  | { readonly error: string; readonly ok: false }
> {
  const result = await api.listUnreadableBoardReviews({
    gameId,
    limit: 25,
    view,
    ...(afterCursor === undefined ? {} : { afterCursor }),
  });
  if (result.error !== undefined || result.data === undefined) {
    return {
      error: apiErrorMessage(
        result.error,
        'Nie udało się pobrać plansz z nieczytelnymi symbolami.',
      ),
      ok: false,
    };
  }
  return { ok: true, page: result.data };
}

export async function loadUnreadableBoardDetail(
  api: UnreadableBoardReviewClient,
  gameId: string,
  reviewItemId: string,
): Promise<
  | { readonly detail: UnreadableBoardReviewDetailResponse; readonly ok: true }
  | { readonly error: string; readonly ok: false }
> {
  const result = await api.getUnreadableBoardReview(gameId, reviewItemId);
  if (result.error !== undefined || result.data === undefined) {
    return {
      error: apiErrorMessage(
        result.error,
        'Nie udało się pobrać bieżącej planszy.',
      ),
      ok: false,
    };
  }
  return { detail: result.data, ok: true };
}

export async function loadUnreadableBoardSymbols(
  api: UnreadableBoardReviewClient,
  gameId: string,
): Promise<
  | { readonly ok: true; readonly symbols: readonly SymbolResponse[] }
  | { readonly error: string; readonly ok: false }
> {
  const result = await api.listSymbols(gameId);
  if (result.error !== undefined || result.data === undefined) {
    return {
      error: apiErrorMessage(
        result.error,
        'Nie udało się pobrać katalogu symboli.',
      ),
      ok: false,
    };
  }
  return {
    ok: true,
    symbols: result.data
      .filter((symbol) => symbol.status === 'active')
      .sort(
        (left, right) =>
          left.displayOrder - right.displayOrder ||
          left.code.localeCompare(right.code),
      ),
  };
}

export async function saveUnreadableBoard(
  api: UnreadableBoardReviewClient,
  gameId: string,
  reviewItemId: string,
  body: SaveUnreadableBoardRequest,
): Promise<{ readonly error?: string; readonly ok: boolean }> {
  const result = await api.saveUnreadableBoardReview(
    gameId,
    reviewItemId,
    body,
  );
  if (result.error !== undefined || result.data === undefined) {
    return {
      error: apiErrorMessage(
        result.error,
        'Nie udało się atomowo zapisać decyzji całej planszy.',
      ),
      ok: false,
    };
  }
  return { ok: true };
}
