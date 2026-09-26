import type {
  AnnotationRequest,
  AnnotationState,
  GeometryAnnotation,
  PhotoReview,
} from '../../../../packages/vision-lab-api-client/src/index';
export type PhotoFilter =
  'all' | 'missing' | 'started' | 'full' | 'review' | 'accepted' | 'correction';
export function photoVersions(rows: GeometryAnnotation[]) {
  return Object.fromEntries(
    rows.map((row) => [String(row.board_index), row.revision]),
  );
}
export function photoReviewStatus(
  rows: GeometryAnnotation[],
  review?: PhotoReview,
  sha?: string,
) {
  const issues = Object.values(review?.issues ?? {});
  const correction = issues.filter(
    (issue) => issue.status === 'needs_correction',
  ).length;
  const recheck = issues.filter(
    (issue) => issue.status === 'needs_review',
  ).length;
  const accepted = review?.accepted_board_revisions ?? {};
  const versions = photoVersions(rows);
  const complete =
    !issues.length &&
    sha === review?.source_sha256 &&
    Object.keys(accepted).length > 0 &&
    Object.keys(accepted).length === rows.length &&
    Object.entries(versions).every(
      ([index, revision]) => accepted[index] === revision,
    ) &&
    rows.some((row) => boardStatus(row) === 'full');
  return {
    status: correction ? 'correction' : complete ? 'accepted' : 'review',
    correction,
    recheck,
  } as const;
}
export const photoReviewLabel = {
  correction: 'Do poprawy',
  accepted: 'Zaakceptowane',
  review: 'Do przeglądu',
};
export function boardStatus(annotation?: GeometryAnnotation) {
  if (!annotation) return 'missing';
  if (annotation.presence === 'present' && annotation.full_approved)
    return 'full';
  return annotation.location_approved ? 'location' : 'draft';
}
export const statusLabel = {
  missing: 'Brak zapisu',
  full: 'Pełna siatka',
  location: 'Lokalizacja',
  draft: 'Szkic',
};
export function sourceAnnotations(
  state: AnnotationState | null,
  source: string,
) {
  return Object.values(state?.annotations ?? {})
    .filter((row) => row.source_id === source)
    .sort((a, b) => a.board_index - b.board_index);
}
export function photoCounts(rows: GeometryAnnotation[]) {
  const counts = { full: 0, location: 0, draft: 0, saved: rows.length };
  for (const row of rows) {
    const status = boardStatus(row);
    if (status !== 'missing') counts[status]++;
  }
  return counts;
}
export function matchesPhotoFilter(
  rows: GeometryAnnotation[],
  filter: PhotoFilter,
  review?: PhotoReview,
  sha?: string,
) {
  const counts = photoCounts(rows);
  return (
    filter === 'all' ||
    (filter === 'missing' && !counts.saved) ||
    (filter === 'started' && counts.saved > 0) ||
    (filter === 'full' && counts.full > 0) ||
    (['review', 'accepted', 'correction'].includes(filter) &&
      photoReviewStatus(rows, review, sha).status === filter)
  );
}
export function positionIndices(rows: GeometryAnnotation[]) {
  return [
    ...new Set([
      ...Array.from({ length: 9 }, (_, i) => i),
      ...rows.map((row) => row.board_index),
    ]),
  ].sort((a, b) => a - b);
}
export function nextApprovedPosition(request: AnnotationRequest) {
  const index = request.annotation.board_index;
  return request.action !== 'draft' && index >= 0 && index < 8
    ? index + 1
    : index;
}
export function approvalSummary(rows: GeometryAnnotation[]) {
  const full = new Set(
    rows
      .filter((row) => boardStatus(row) === 'full')
      .map((row) => row.board_index),
  );
  const missing = Array.from({ length: 9 }, (_, i) => i)
    .filter((i) => !full.has(i))
    .map((i) => i + 1);
  return missing.length
    ? `Pełne siatki: ${full.size}. Bez pełnego zatwierdzenia w pozycjach 1–9: ${missing.join(', ')}.`
    : 'Zatwierdzono 9 plansz w pozycjach 1–9.';
}
