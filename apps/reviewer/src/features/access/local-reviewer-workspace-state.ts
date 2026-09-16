export type LocalReviewerWorkspaceMode = 'deferred' | 'grid';

export function initialLocalReviewerWorkspaceMode(
  gridReviewCount: number,
  deferredGeometryCount: number,
): LocalReviewerWorkspaceMode {
  return gridReviewCount === 0 && deferredGeometryCount > 0
    ? 'deferred'
    : 'grid';
}
