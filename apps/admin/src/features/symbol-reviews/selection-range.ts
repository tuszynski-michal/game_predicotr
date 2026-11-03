/** Resolve endpoints before excluding locked rows; virtualization is irrelevant. */
export function inclusiveSelectionRange<T>(
  items: readonly T[],
  anchorId: string | null,
  targetId: string,
  id: (item: T) => string,
  locked: (item: T) => boolean,
): readonly T[] | null {
  const start = items.findIndex((item) => id(item) === anchorId);
  const end = items.findIndex((item) => id(item) === targetId);
  if (start < 0 || end < 0) return null;
  return items
    .slice(Math.min(start, end), Math.max(start, end) + 1)
    .filter((item) => !locked(item));
}
