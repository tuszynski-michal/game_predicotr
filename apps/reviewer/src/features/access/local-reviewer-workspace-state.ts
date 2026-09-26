export type LocalReviewerWorkspaceMode = 'deferred' | 'grid';

export function initialLocalReviewerWorkspaceMode(
  _gridReviewCount: number,
  deferredGeometryCount: number,
): LocalReviewerWorkspaceMode {
  return deferredGeometryCount > 0 ? 'deferred' : 'grid';
}
