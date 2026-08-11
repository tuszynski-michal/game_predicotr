export function defaultManualCandidateIndex(
  candidateCount: number,
): number | null {
  if (!Number.isInteger(candidateCount) || candidateCount < 1) return null;
  if (candidateCount > 20) return 9;
  return Math.floor((candidateCount - 1) / 2);
}

export function nextUnresolvedManualIndex(
  unresolved: readonly boolean[],
  currentIndex: number,
): number {
  if (unresolved.length === 0) return 0;
  for (let offset = 1; offset <= unresolved.length; offset += 1) {
    const candidateIndex =
      (currentIndex + offset + unresolved.length) % unresolved.length;
    if (unresolved[candidateIndex]) return candidateIndex;
  }
  return Math.min(Math.max(currentIndex, 0), unresolved.length - 1);
}
