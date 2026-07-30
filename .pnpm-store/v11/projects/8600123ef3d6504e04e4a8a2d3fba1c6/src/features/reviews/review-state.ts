import type {
  ReviewCellSnapshot,
  ReviewItemResponse,
  ReviewItemStatus,
} from '@game-predictor/admin-api-client';

const REVIEW_STATUS_LABELS: Readonly<Record<ReviewItemStatus, string>> = {
  pending: 'Oczekuje na decyzję',
  accepted: 'Zaakceptowany',
  corrected: 'Poprawiony',
  rejected: 'Odrzucony',
};

export const REVIEW_STATUS_OPTIONS = Object.keys(
  REVIEW_STATUS_LABELS,
) as readonly ReviewItemStatus[];

export type ReviewAssetKind = 'board' | 'source';

export function reviewStatusLabel(status: ReviewItemStatus): string {
  return REVIEW_STATUS_LABELS[status];
}

export function formatReviewConfidence(value: number): string {
  if (!Number.isFinite(value)) return 'Nieprawidłowa wartość';
  const bounded = Math.min(1, Math.max(0, value));
  return `${(bounded * 100).toLocaleString('pl-PL', {
    maximumFractionDigits: 1,
    minimumFractionDigits: 1,
  })}%`;
}

export function orderReviewItems(
  items: readonly ReviewItemResponse[],
): readonly ReviewItemResponse[] {
  return [...items].sort(
    (left, right) => left.snapshot.selectionRank - right.snapshot.selectionRank,
  );
}

export function reviewCell(
  item: ReviewItemResponse,
  cellIndex: number,
): ReviewCellSnapshot | null {
  const cell = item.snapshot.cells[cellIndex];
  return cell?.cellIndex === cellIndex ? cell : null;
}

export function adjacentReviewItemId(
  items: readonly ReviewItemResponse[],
  currentItemId: string,
  direction: -1 | 1,
): string | null {
  const currentIndex = items.findIndex((item) => item.id === currentItemId);
  const adjacent = items[currentIndex + direction];
  return adjacent?.id ?? null;
}

export function reviewAssetUrl(
  apiBaseUrl: string,
  reviewItemId: string,
  asset: ReviewAssetKind | 'cell',
  cellIndex?: number,
): string {
  const base = apiBaseUrl.endsWith('/') ? apiBaseUrl : `${apiBaseUrl}/`;
  const encodedItemId = encodeURIComponent(reviewItemId);
  const suffix =
    asset === 'cell' ? `cells/${requireCellIndex(cellIndex)}` : asset;
  return new URL(
    `api/v1/admin/review-items/${encodedItemId}/assets/${suffix}`,
    base,
  ).toString();
}

function requireCellIndex(cellIndex: number | undefined): number {
  if (
    cellIndex === undefined ||
    !Number.isInteger(cellIndex) ||
    cellIndex < 0 ||
    cellIndex >= 15
  ) {
    throw new RangeError('Review cell index must be between 0 and 14.');
  }
  return cellIndex;
}
