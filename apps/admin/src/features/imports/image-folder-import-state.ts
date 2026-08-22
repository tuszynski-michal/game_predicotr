import type { BrowserReadySelectionResponse } from '@game-predictor/admin-api-client';

function leadingRangeStart(displayName: string): number | null {
  const match = /^\s*(\d+)\s*-/.exec(displayName);
  if (match === null) return null;
  const value = Number(match[1]);
  return Number.isSafeInteger(value) ? value : null;
}

export function sortReadyBoardImports(
  selections: readonly BrowserReadySelectionResponse[],
): readonly BrowserReadySelectionResponse[] {
  return [...selections].sort((left, right) => {
    const leftStart = leadingRangeStart(left.displayName);
    const rightStart = leadingRangeStart(right.displayName);
    if (leftStart !== null && rightStart !== null && leftStart !== rightStart) {
      return leftStart - rightStart;
    }
    if (leftStart !== null && rightStart === null) return -1;
    if (leftStart === null && rightStart !== null) return 1;
    return (
      left.displayName.localeCompare(right.displayName, 'pl-PL', {
        numeric: true,
        sensitivity: 'base',
      }) || left.uploadId.localeCompare(right.uploadId)
    );
  });
}
