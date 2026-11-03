import type { DesktopWorkspace, DesktopWorkspaceUpdate } from '../contracts.ts';
import { sourceLookup } from '../source-index.ts';

/** Updates carry every mutable field, so revision gaps need no replay. */
export function applyWorkspaceUpdate(
  workspace: DesktopWorkspace | null,
  update: DesktopWorkspaceUpdate,
): DesktopWorkspace {
  const { sourceId, baseRevision, acceptedImageIds, ...scalars } = update;
  if (
    !workspace ||
    update.projectId !== workspace.projectId ||
    sourceId !== (workspace.source?.id ?? null) ||
    !Number.isSafeInteger(update.revision) ||
    update.revision < workspace.revision
  )
    throw new Error('Odpowiedź dotyczy innego projektu, źródła lub rewizji.');
  if (
    acceptedImageIds === undefined &&
    (baseRevision !== workspace.revision ||
      update.acceptedCount !== workspace.acceptedCount ||
      update.skippedCount !== workspace.skippedCount ||
      update.decisionCount !== workspace.decisionCount)
  )
    throw new Error('Aktualizacja wymaga pełnego snapshotu.');
  const accepted = acceptedImageIds ?? workspace.acceptedImageIds;
  const index = workspace.source ? sourceLookup(workspace.source) : null;
  if (
    (update.currentImageId !== null &&
      !index?.byId.has(update.currentImageId)) ||
    acceptedImageIds?.some((id) => !index?.byId.has(id))
  )
    throw new Error('Odpowiedź wymaga pełnego indeksu źródła.');
  return {
    ...scalars,
    acceptedImageIds: accepted,
    source: workspace.source,
    view: workspace.view,
  };
}
